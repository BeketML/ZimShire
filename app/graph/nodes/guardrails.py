"""Guardrails — Phase 2 STUBS (always pass).

Phase 3 will replace these with real LiteLLM classifiers per
`docs/agent_architecture.md` §5.1, §5.6, §5.7. For now they:
  * Extract `query` from latest human message (input_guardrail).
  * Persist a `guardrail_logs` row with result="passed".
  * Apply the faithfulness threshold (≥ 0.75, ≥ 2 strong hits) — this one is
    real because it has no LLM dependency.
"""
from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from app.db.database import AsyncSessionLocal
from app.graph.state import ZimShireState
from app.repositories import guardrail_repo

logger = logging.getLogger(__name__)

FAITHFULNESS_SCORE_THRESHOLD = 0.75
FAITHFULNESS_MIN_STRONG_HITS = 2


def _human_message_id(config: RunnableConfig) -> UUID | None:
    raw = config.get("configurable", {}).get("human_message_id")
    if not raw:
        return None
    return UUID(raw) if isinstance(raw, str) else raw


async def _log(
    *,
    message_id: UUID | None,
    guardrail_type: str,
    result: str,
    blocked_reason: str | None = None,
    confidence: float | None = None,
) -> None:
    if message_id is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            await guardrail_repo.log(
                session,
                message_id=message_id,
                guardrail_type=guardrail_type,
                result=result,
                confidence=confidence,
                blocked_reason=blocked_reason,
            )
            await session.commit()
    except Exception as e:
        logger.warning("guardrail_logs insert failed: %s", e)


async def input_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    last_human = ""
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", None) == "human":
            last_human = m.content if isinstance(m.content, str) else str(m.content)
            break
    await _log(
        message_id=_human_message_id(config),
        guardrail_type="input",
        result="passed",
    )
    return {
        "query": last_human,
        "input_blocked": False,
        "input_blocked_reason": None,
    }


async def output_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    await _log(
        message_id=_human_message_id(config),
        guardrail_type="output",
        result="passed",
    )
    return {"output_blocked": False, "output_rewritten": False, "output_blocked_reason": None}


async def faithfulness_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    rag_invoked = bool(state.get("rag_invoked"))
    chunks = state.get("rag_agent_chunks") or []

    if not rag_invoked:
        await _log(
            message_id=_human_message_id(config),
            guardrail_type="faithfulness",
            result="passed",
        )
        return {"grounded": None, "sources": []}

    strong = [c for c in chunks if (c.get("similarity_score") or 0.0) >= FAITHFULNESS_SCORE_THRESHOLD]
    grounded = len(strong) >= FAITHFULNESS_MIN_STRONG_HITS

    sources = [
        {
            "letter_year": c.get("letter_year"),
            "passage": c.get("passage_snippet", ""),
            "similarity_score": float(c.get("similarity_score") or 0.0),
            "qdrant_point_id": str(c.get("qdrant_point_id", "")),
        }
        for c in strong
    ]
    await _log(
        message_id=_human_message_id(config),
        guardrail_type="faithfulness",
        result="passed" if grounded else "blocked",
        blocked_reason=None if grounded else "fewer than 2 strong RAG hits",
    )
    return {"grounded": grounded, "sources": sources}
