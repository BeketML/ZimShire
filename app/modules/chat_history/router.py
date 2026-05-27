"""HTTP endpoints for inspecting short-term and long-term memory."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.modules.agents.service import get_graph, get_store
from app.modules.chat_history.long_term.schemas import UserProfile
from app.modules.chat_history.long_term.service import LongTermMemoryService
from app.modules.chat_history.short_term.gateways import load_messages_from_checkpointer
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.modules.chats.repository import get_chat
from app.modules.users import repository as user_repo

router = APIRouter(tags=["chat_history"])

_short_term_svc = ShortTermMemoryService()


class TurnPairSchema(BaseModel):
    human: str
    assistant: str


class ShortTermMemoryResponse(BaseModel):
    user_id: UUID
    chat_id: UUID
    thread_id: str
    turn_pairs: list[TurnPairSchema]
    formatted: str
    message_count: int


class LongTermMemoryResponse(BaseModel):
    user_id: UUID
    profile: UserProfile
    search_query: str = ""


@router.get("/users/{user_id}/memory/long-term", response_model=LongTermMemoryResponse)
async def get_long_term_memory(
    user_id: UUID,
    query: str = Query(default="", max_length=500),
    db: AsyncSession = Depends(get_db),
) -> LongTermMemoryResponse:
    user = await user_repo.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    store = get_store()
    svc = LongTermMemoryService(store)
    profile = await svc.load_profile(str(user_id), query)
    return LongTermMemoryResponse(user_id=user_id, profile=profile, search_query=query)


@router.get(
    "/users/{user_id}/chats/{chat_id}/memory/short-term",
    response_model=ShortTermMemoryResponse,
)
async def get_short_term_memory(
    user_id: UUID,
    chat_id: UUID,
    limit_turn_pairs: int = Query(default=5, ge=1, le=20),
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
    ctx = _short_term_svc._extract(messages, limit=limit_turn_pairs)

    return ShortTermMemoryResponse(
        user_id=user_id,
        chat_id=chat_id,
        thread_id=thread_id,
        turn_pairs=[TurnPairSchema(human=p.human, assistant=p.assistant) for p in ctx.turn_pairs],
        formatted=ctx.format_for_prompt(),
        message_count=len(messages),
    )
