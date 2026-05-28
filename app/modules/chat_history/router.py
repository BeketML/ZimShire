"""HTTP endpoints for inspecting short-term and long-term memory."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.modules.agents import get_graph, get_store
from app.modules.chat_history.long_term.schemas import UserProfile
from app.modules.chat_history.long_term.service import LongTermMemoryService
from app.modules.chat_history.short_term.gateways import load_messages_from_checkpointer
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.modules.chats.repository import get_chat
from app.modules.users import repository as user_repo

router = APIRouter(tags=["chat_history"])

_short_term_svc = ShortTermMemoryService()


# ── Long-term memory ─────────────────────────────────────────────────────────


class RawStoreItem(BaseModel):
    namespace: str
    key: str
    value: dict[str, Any]


class LongTermMemoryResponse(BaseModel):
    user_id: UUID
    search_query: str
    # Aggregated profile (merged view across all store items)
    profile: UserProfile
    # Every raw item in the store — see exactly what is persisted
    raw_store_items: list[RawStoreItem]
    interests_count: int
    has_profile_meta: bool


@router.get("/users/{user_id}/memory/long-term", response_model=LongTermMemoryResponse)
async def get_long_term_memory(
    user_id: UUID,
    query: str = Query(default="", max_length=500, description="Optional: filter interests by semantic similarity"),
    db: AsyncSession = Depends(get_db),
) -> LongTermMemoryResponse:
    user = await user_repo.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    store = get_store()
    svc = LongTermMemoryService(store)
    profile, raw = await svc.load_profile_with_raw(str(user_id), query)

    interests = [r for r in raw if r["namespace"].endswith("/interests")]
    has_meta = any(r["namespace"].endswith("/profile") for r in raw)

    return LongTermMemoryResponse(
        user_id=user_id,
        search_query=query,
        profile=profile,
        raw_store_items=[RawStoreItem(**r) for r in raw],
        interests_count=len(interests),
        has_profile_meta=has_meta,
    )


# ── Short-term memory ────────────────────────────────────────────────────────


class TurnPairSchema(BaseModel):
    index: int
    human: str
    assistant: str


class ShortTermMemoryResponse(BaseModel):
    user_id: UUID
    chat_id: UUID
    thread_id: str
    # All turn pairs stored in the checkpoint
    all_turn_pairs: list[TurnPairSchema]
    total_turns: int
    # Last N pairs (what the agent actually uses as context)
    recent_turn_pairs: list[TurnPairSchema]
    context_window: int
    formatted: str
    message_count: int


@router.get(
    "/users/{user_id}/chats/{chat_id}/memory/short-term",
    response_model=ShortTermMemoryResponse,
)
async def get_short_term_memory(
    user_id: UUID,
    chat_id: UUID,
    limit_turn_pairs: int = Query(default=10, ge=1, le=50, description="How many recent pairs to show as agent context"),
    db: AsyncSession = Depends(get_db),
) -> ShortTermMemoryResponse:
    chat = await get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    if chat.user_id != user_id:
        raise HTTPException(status_code=403, detail="chat does not belong to user")

    thread_id = str(chat_id)
    graph = get_graph()
    messages = await load_messages_from_checkpointer(graph, thread_id=thread_id)

    # All pairs ever in this chat
    all_ctx = _short_term_svc._extract(messages, limit=9999)
    all_pairs = [
        TurnPairSchema(index=i, human=p.human, assistant=p.assistant)
        for i, p in enumerate(all_ctx.turn_pairs, start=1)
    ]

    # Recent N pairs (what the agent uses)
    recent_ctx = _short_term_svc._extract(messages, limit=limit_turn_pairs)
    recent_pairs = [
        TurnPairSchema(index=len(all_pairs) - len(recent_ctx.turn_pairs) + i, human=p.human, assistant=p.assistant)
        for i, p in enumerate(recent_ctx.turn_pairs, start=1)
    ]

    return ShortTermMemoryResponse(
        user_id=user_id,
        chat_id=chat_id,
        thread_id=thread_id,
        all_turn_pairs=all_pairs,
        total_turns=len(all_pairs),
        recent_turn_pairs=recent_pairs,
        context_window=limit_turn_pairs,
        formatted=recent_ctx.format_for_prompt(),
        message_count=len(messages),
    )
