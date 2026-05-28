from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.models import User
from app.modules.users import repository

logger = logging.getLogger(__name__)


async def create_user(
    session: AsyncSession, *, name: str | None = None, surname: str | None = None
) -> User:
    user = await repository.create_user(session, name=name, surname=surname)
    await session.commit()

    # Initialise long-term memory profile in the store (best-effort)
    try:
        from app.modules.agents import get_store
        from app.modules.chat_history.long_term.service import LongTermMemoryService
        store = get_store()
        svc = LongTermMemoryService(store)
        await svc.init_user(str(user.user_id), name=name, surname=surname)
    except Exception as exc:
        logger.warning("init_user store failed for %s: %s", user.user_id, exc)

    return user


async def get_user(session: AsyncSession, user_id: UUID) -> User:
    user = await repository.get_user(session, user_id)
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    return user
