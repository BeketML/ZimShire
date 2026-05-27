from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.models import Chat
from app.modules.chats import repository
from app.modules.users import repository as user_repo


async def create_chat(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_title: str | None,
) -> Chat:
    user = await user_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError(f"user_id {user_id} not found")
    chat = await repository.create_chat(
        session,
        user_id=user_id,
        chat_title=chat_title,
        model=settings.default_chat_model,
        provider=settings.default_provider,
    )
    await session.commit()
    return chat


async def get_chat(session: AsyncSession, chat_id: UUID) -> Chat:
    chat = await repository.get_chat(session, chat_id)
    if chat is None:
        raise NotFoundError(f"chat {chat_id} not found")
    return chat
