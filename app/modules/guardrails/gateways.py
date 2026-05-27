"""Guardrail log gateway — callable from graph nodes without injected session."""
from __future__ import annotations

import logging
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.modules.guardrails import repository

logger = logging.getLogger(__name__)


async def write_guardrail_log(
    *,
    message_id: UUID | None,
    guardrail_type: str,
    result: str,
    confidence: float | None = None,
    blocked_reason: str | None = None,
) -> None:
    if message_id is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            await repository.log(
                session,
                message_id=message_id,
                guardrail_type=guardrail_type,
                result=result,
                confidence=confidence,
                blocked_reason=blocked_reason,
            )
            await session.commit()
    except Exception as exc:
        logger.warning("guardrail_logs insert failed: %s", exc)
