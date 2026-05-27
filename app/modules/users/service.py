from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.models import User
from app.modules.users import repository


async def create_user(session: AsyncSession) -> User:
    user = await repository.create_user(session)
    await session.commit()
    return user


async def get_user(session: AsyncSession, user_id: UUID) -> User:
    user = await repository.get_user(session, user_id)
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    return user
