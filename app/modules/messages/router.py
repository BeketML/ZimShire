"""GET message history + POST SSE streaming research turn."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_db
from app.modules.chats.repository import get_chat
from app.modules.messages import repository as msg_repo
from app.modules.messages.schemas import (
    HistoryResponse,
    MessageCreate,
    MessageItem,
    SourceItem,
)
from app.modules.messages.service import persist_assistant_turn
from app.modules.rag_retrievals.repository import list_for_message
from app.modules.agents.service import get_graph, get_store
from app.services.langfuse_service import (
    flush as langfuse_flush,
    get_trace_id,
    make_callback_handler,
    trace_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["messages"])


# ── GET /chats/{chat_id}/messages ──────────────────────────────────────────


@router.get("/{chat_id}/messages", response_model=HistoryResponse)
async def list_messages(
    chat_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    chat = await get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    if chat.user_id != user_id:
        raise HTTPException(status_code=403, detail="chat does not belong to user")

    rows = await msg_repo.list_messages(db, chat_id)
    items: list[MessageItem] = []
    for m in rows:
        sources_payload: list[SourceItem] = []
        if m.role == "assistant":
            retrievals = await list_for_message(db, m.message_id)
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


# ── POST /chats/{chat_id}/messages ─────────────────────────────────────────


def _chunk_text(text: str, words_per_chunk: int = 4) -> list[str]:
    words = text.split(" ")
    return [" ".join(words[i : i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)] if words else []


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


async def _stream_turn(chat_id: UUID, user_id: UUID, body: MessageCreate):
    async with AsyncSessionLocal() as session:
        human = await msg_repo.create_human_message(
            session, chat_id=chat_id, content=body.query
        )
        await session.commit()
        human_message_id = human.message_id

    handler = make_callback_handler()

    graph = get_graph()
    store = get_store()
    config = {
        "configurable": {
            "thread_id": str(chat_id),
            "user_id": str(user_id),
            "chat_id": str(chat_id),
            "human_message_id": str(human_message_id),
            "query": body.query,
        },
        "callbacks": [handler] if handler is not None else [],
    }
    inputs = {
        "messages": [HumanMessage(content=body.query)],
        "query": body.query,
    }

    final_state: dict = {}
    try:
        with trace_context(user_id=str(user_id), session_id=str(chat_id)):
            async for chunk in graph.astream(inputs, config=config, stream_mode="values"):
                final_state = chunk
    except Exception as exc:
        logger.exception("graph run failed: %s", exc)
        trace_id = get_trace_id(handler)
        yield _sse({"type": "error", "detail": str(exc)})
        yield _sse({"type": "done", "message_id": None, "grounded": None, "sources": [], "langfuse_trace_id": trace_id})
        langfuse_flush()
        return

    trace_id = get_trace_id(handler)

    if final_state.get("input_blocked"):
        reason = final_state.get("input_blocked_reason") or "Query rejected by input guardrail."
        yield _sse({"type": "blocked", "reason": reason})
        yield _sse({"type": "done", "message_id": None, "grounded": None, "sources": [], "langfuse_trace_id": trace_id})
        langfuse_flush()
        return

    approved_text = final_state.get("draft_answer") or ""
    for piece in _chunk_text(approved_text):
        yield _sse({"type": "token", "content": piece + " "})

    async with AsyncSessionLocal() as session:
        assistant_msg = await persist_assistant_turn(
            session,
            chat_id=chat_id,
            user_id=user_id,
            user_query=body.query,
            final_state=final_state,
            langfuse_trace_id=trace_id,
            store=store,
        )
        await session.commit()

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
    langfuse_flush()


@router.post("/{chat_id}/messages")
async def post_message(
    chat_id: UUID,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    chat = await get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    if chat.user_id != body.user_id:
        raise HTTPException(status_code=403, detail="chat does not belong to user")
    return StreamingResponse(
        _stream_turn(chat_id, body.user_id, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
