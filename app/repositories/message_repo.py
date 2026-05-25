from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message


async def create_human_message(
    session: AsyncSession, *, chat_id: UUID, content: str
) -> Message:
    msg = Message(chat_id=chat_id, role="human", content=content)
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg


async def create_assistant_message(
    session: AsyncSession,
    *,
    chat_id: UUID,
    content: str,
    grounded: bool | None,
    langfuse_trace_id: str | None,
) -> Message:
    msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=content,
        grounded=grounded,
        langfuse_trace_id=langfuse_trace_id,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg


async def list_messages(session: AsyncSession, chat_id: UUID) -> list[Message]:
    rows = await session.scalars(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    return list(rows)
