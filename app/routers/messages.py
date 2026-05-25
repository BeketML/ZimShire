"""Conversation history GET + SSE-streamed turn POST."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.db.database import AsyncSessionLocal
from app.repositories import chat_repo, message_repo, rag_repo
from app.schemas.messages import HistoryResponse, MessageCreate, MessageItem, SourceItem
from app.services.chat_service import persist_assistant_turn
from app.services.graph_service import get_graph, get_store
from app.services.langfuse_service import new_trace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["messages"])


# ---- GET /chats/{chat_id}/messages ---------------------------------------


@router.get("/{chat_id}/messages", response_model=HistoryResponse)
async def list_messages(chat_id: UUID, db: AsyncSession = Depends(get_db)) -> HistoryResponse:
    chat = await chat_repo.get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")

    rows = await message_repo.list_messages(db, chat_id)
    items: list[MessageItem] = []
    for m in rows:
        sources_payload: list[SourceItem] = []
        if m.role == "assistant":
            retrievals = await rag_repo.list_for_message(db, m.message_id)
            for r in retrievals:
                if r.used_in_response:
                    sources_payload.append(
                        SourceItem(
                            letter_year=r.letter_year,
                            passage=r.passage_snippet or "",
                            similarity_score=float(r.similarity_score or 0.0),
                            qdrant_point_id=r.qdrant_point_id,
                        )
                    )
        items.append(
            MessageItem(
                message_id=m.message_id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                grounded=m.grounded,
                sources=sources_payload,
                langfuse_trace_id=m.langfuse_trace_id,
                created_at=m.created_at,
            )
        )
    return HistoryResponse(chat_id=chat_id, messages=items)


# ---- POST /chats/{chat_id}/messages — SSE --------------------------------


def _chunk_text(text: str, words_per_chunk: int = 4) -> list[str]:
    words = text.split(" ")
    if not words:
        return []
    return [" ".join(words[i : i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


async def _stream_turn(chat_id: UUID, body: MessageCreate) -> "AsyncGenerator[str, None]":
    """End-to-end SSE generator (no FastAPI dep on `db` here — we open our own sessions)."""
    # 1. Verify chat & persist human message in a short-lived session
    async with AsyncSessionLocal() as session:
        chat = await chat_repo.get_chat(session, chat_id)
        if chat is None:
            yield _sse({"type": "error", "detail": "chat not found"})
            yield _sse({"type": "done", "message_id": None, "grounded": None, "sources": []})
            return
        human = await message_repo.create_human_message(
            session, chat_id=chat_id, content=body.content
        )
        await session.commit()
        chat_model = body.model or chat.model
        chat_user_id = chat.user_id
        human_message_id = human.message_id

    trace_id = new_trace_id()

    # 2. Run the graph to completion (Stages 4-9)
    graph = get_graph()
    store = get_store()
    config = {
        "configurable": {
            "thread_id": str(chat_id),
            "user_id": str(chat_user_id),
            "chat_id": str(chat_id),
            "model": chat_model,
            "human_message_id": str(human_message_id),
        }
    }
    inputs = {"messages": [HumanMessage(content=body.content)]}

    final_state: dict = {}
    try:
        async for chunk in graph.astream(inputs, config=config, stream_mode="values"):
            final_state = chunk
    except Exception as e:
        logger.exception("graph run failed: %s", e)
        yield _sse({"type": "error", "detail": str(e)})
        yield _sse(
            {
                "type": "done",
                "message_id": None,
                "grounded": None,
                "sources": [],
                "langfuse_trace_id": trace_id,
                "cache_hit": False,
            }
        )
        return

    # 3. Handle input_blocked path (no streamable content)
    if final_state.get("input_blocked"):
        reason = final_state.get("input_blocked_reason") or "Query rejected by input guardrail."
        yield _sse({"type": "blocked", "reason": reason})
        yield _sse(
            {
                "type": "done",
                "message_id": None,
                "grounded": None,
                "sources": [],
                "langfuse_trace_id": trace_id,
                "cache_hit": False,
            }
        )
        return

    # 4. Stream approved draft_answer as token events (Stage 9.5)
    approved_text = final_state.get("draft_answer") or ""
    for piece in _chunk_text(approved_text):
        yield _sse({"type": "token", "content": piece + " "})

    # 5. Persist Stage 10
    async with AsyncSessionLocal() as session:
        assistant_msg = await persist_assistant_turn(
            session,
            chat_id=chat_id,
            user_id=chat_user_id,
            user_query=body.content,
            final_state=final_state,
            langfuse_trace_id=trace_id,
            store=store,
        )
        await session.commit()

    # 6. Final done event
    yield _sse(
        {
            "type": "done",
            "message_id": str(assistant_msg.message_id),
            "grounded": final_state.get("grounded"),
            "sources": final_state.get("sources") or [],
            "langfuse_trace_id": trace_id,
            "cache_hit": bool(final_state.get("cache_hit")),
        }
    )


@router.post("/{chat_id}/messages")
async def post_message(chat_id: UUID, body: MessageCreate):
    return StreamingResponse(
        _stream_turn(chat_id, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
