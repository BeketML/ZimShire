from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Chat


async def create_chat(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_title: str | None,
    model: str | None,
    provider: str | None,
) -> Chat:
    chat = Chat(user_id=user_id, chat_title=chat_title, model=model, provider=provider)
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    return chat


async def get_chat(session: AsyncSession, chat_id: UUID) -> Chat | None:
    return await session.scalar(select(Chat).where(Chat.chat_id == chat_id))


async def touch_chat(session: AsyncSession, chat_id: UUID) -> None:
    await session.execute(
        update(Chat).where(Chat.chat_id == chat_id).values(updated_at=func.now())
    )
