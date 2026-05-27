from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GuardrailLog


async def list_for_chat(
    session: AsyncSession, chat_id: UUID, *, limit: int = 200
) -> list[GuardrailLog]:
    from app.models.models import Message  # local import to avoid circularity

    rows = await session.scalars(
        select(GuardrailLog)
        .join(Message, GuardrailLog.message_id == Message.message_id)
        .where(Message.chat_id == chat_id)
        .order_by(GuardrailLog.checked_at.desc())
        .limit(limit)
    )
    return list(rows)


async def log(
    session: AsyncSession,
    *,
    message_id: UUID,
    guardrail_type: str,
    result: str,
    confidence: float | None = None,
    blocked_reason: str | None = None,
) -> GuardrailLog:
    row = GuardrailLog(
        message_id=message_id,
        guardrail_type=guardrail_type,
        result=result,
        confidence=confidence,
        blocked_reason=blocked_reason,
    )
    session.add(row)
    await session.flush()
    return row
