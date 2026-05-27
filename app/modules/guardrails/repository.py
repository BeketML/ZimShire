from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GuardrailLog


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
