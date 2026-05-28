"""Faithfulness guardrail node — checks RAG answer against retrieved chunks."""
from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.prompts import GUARDRAIL_FAITHFULNESS_PROMPT
from app.modules.agents.state import ZimShireState
from app.modules.guardrails.gateways import write_guardrail_log
from app.services.llm import get_guardrail_model

logger = logging.getLogger(__name__)

FAITHFULNESS_SCORE_THRESHOLD = 0.75
FAITHFULNESS_MIN_STRONG_HITS = 2


def _message_id(config: RunnableConfig) -> UUID | None:
    raw = config.get("configurable", {}).get("human_message_id")
    if not raw:
        return None
    return UUID(raw) if isinstance(raw, str) else raw


async def faithfulness_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    import json

    rag_invoked = bool(state.get("rag_invoked"))
    mid = _message_id(config)

    if not rag_invoked:
        await write_guardrail_log(
            message_id=mid, guardrail_type="faithfulness", result="passed"
        )
        return {"grounded": None, "sources": []}

    chunks = state.get("rag_agent_chunks") or []
    if not chunks:
        await write_guardrail_log(
            message_id=mid,
            guardrail_type="faithfulness",
            result="blocked",
            blocked_reason="RAG invoked but returned no chunks",
        )
        return {"grounded": False, "sources": []}

    rag_answer = state.get("draft_answer") or ""
    passages = "\n\n".join(
        f"[{c.get('letter_year')}] {c.get('passage_snippet', '')}" for c in chunks
    )

    try:
        llm = get_guardrail_model()
        resp = await llm.ainvoke([
            SystemMessage(content=GUARDRAIL_FAITHFULNESS_PROMPT),
            HumanMessage(
                content=f"QUERY:\n{state.get('query', '')}\n\n"
                        f"RETRIEVED PASSAGES:\n{passages}\n\n"
                        f"SYNTHESIZED ANSWER:\n{rag_answer}"
            ),
        ])
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        grounded = bool(result.get("grounded", True))
        score = float(result.get("score", 1.0))
    except Exception as exc:
        logger.warning("faithfulness_guardrail LLM call failed (%s) — falling back to threshold check", exc)
        strong = [c for c in chunks if (c.get("similarity_score") or 0.0) >= FAITHFULNESS_SCORE_THRESHOLD]
        grounded = len(strong) >= FAITHFULNESS_MIN_STRONG_HITS
        score = len(strong) / len(chunks) if chunks else 0.0

    strong_hits = sorted(chunks, key=lambda c: c.get("similarity_score") or 0.0, reverse=True)
    sources = [
        {
            "letter_year": c.get("letter_year"),
            "passage": c.get("passage_snippet", ""),
            "similarity_score": float(c.get("similarity_score") or 0.0),
            "qdrant_point_id": str(c.get("qdrant_point_id", "")),
        }
        for c in strong_hits
        if (c.get("similarity_score") or 0.0) >= FAITHFULNESS_SCORE_THRESHOLD
    ][:5]

    await write_guardrail_log(
        message_id=mid,
        guardrail_type="faithfulness",
        result="passed" if grounded else "blocked",
        confidence=score,
        blocked_reason=None if grounded else f"faithfulness score {score:.2f} < 0.70",
    )
    return {"grounded": grounded, "sources": sources if grounded else []}
