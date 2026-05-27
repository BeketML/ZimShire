from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User


async def create_user(session: AsyncSession) -> User:
    user = User()
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.scalar(select(User).where(User.user_id == user_id))
