"""GET message history + POST SSE streaming research turn."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_turn_service
from app.core.dependencies import get_db
from app.modules.chats.repository import get_chat
from app.modules.messages import repository as msg_repo
from app.modules.messages.schemas import (
    HistoryResponse,
    MessageCreate,
    MessageItem,
    SourceItem,
)
from app.modules.messages.turn_service import TurnOrchestrationService
from app.modules.rag_retrievals.repository import list_for_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["messages"])


# ── GET /chats/{chat_id}/messages ──────────────────────────────────────────


@router.get("/{chat_id}/messages", response_model=HistoryResponse)
async def list_messages(
    chat_id: UUID,
    user_id: UUID = Query(..., description="Owner user_id for ownership verification"),
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


@router.post("/{chat_id}/messages")
async def post_message(
    chat_id: UUID,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    turn_svc: TurnOrchestrationService = Depends(get_turn_service),
):
    chat = await get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    if chat.user_id != body.user_id:
        raise HTTPException(status_code=403, detail="chat does not belong to user")
    return StreamingResponse(
        turn_svc.stream_turn(chat_id, body.user_id, body.query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
