"""Preflight pipeline nodes: input_guardrail, semantic_cache_check, load_memory."""
from __future__ import annotations

# ── input_guardrail ─────────────────────────────────────────────────────────

import json
import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.core.config import settings
from app.core.prompts import GUARDRAIL_INPUT_PROMPT
from app.modules.agents.graph.state import ZimShireState
from app.modules.guardrails.gateways import write_guardrail_log
from app.services.llm import get_guardrail_model

logger = logging.getLogger(__name__)


def _message_id(config: RunnableConfig) -> UUID | None:
    raw = config.get("configurable", {}).get("human_message_id")
    if not raw:
        return None
    return UUID(raw) if isinstance(raw, str) else raw


async def input_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    last_human = ""
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", None) == "human":
            last_human = m.content if isinstance(m.content, str) else str(m.content)
            break

    mid = _message_id(config)

    try:
        llm = get_guardrail_model()
        resp = await llm.ainvoke(
            [SystemMessage(content=GUARDRAIL_INPUT_PROMPT), HumanMessage(content=last_human)]
        )
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        blocked = bool(result.get("blocked"))
        reason = result.get("reason") or None
    except Exception as exc:
        # Explicit: fail-open (allow) or fail-closed (block) on LLM error
        blocked = not settings.fail_open_on_guardrail_error
        reason = None
        if blocked:
            logger.error("input_guardrail LLM failed (%s) — blocking (fail-closed)", exc, exc_info=True)
        else:
            logger.warning("input_guardrail LLM failed (%s) — allowing through (fail-open)", exc)

    await write_guardrail_log(
        message_id=mid,
        guardrail_type="input",
        result="blocked" if blocked else "passed",
        blocked_reason=reason if blocked else None,
    )

    if blocked:
        safe_msg = AIMessage(
            content=(
                "I can only help with investment research questions grounded in "
                "Warren Buffett's philosophy and public market data. "
                "Try: 'How did Buffett evaluate Coca-Cola's moat?' or "
                "'What does Apple's P/E ratio say about its margin of safety?'"
            )
        )
        return {
            "query": last_human,
            "input_blocked": True,
            "input_blocked_reason": reason,
            "messages": [safe_msg],
        }

    return {"query": last_human, "input_blocked": False, "input_blocked_reason": None}


# ── semantic_cache_check ─────────────────────────────────────────────────────

from app.modules.cache.gateways import lookup_semantic
from app.services.embedding import embed_text


async def semantic_cache_check(state: ZimShireState, config: RunnableConfig) -> dict:
    query = state.get("query") or ""
    if not query.strip():
        return {"cache_hit": False}

    try:
        vector = await embed_text(query)
    except Exception as exc:
        logger.warning("semantic_cache_check embed failed: %s", exc)
        return {"cache_hit": False}

    result = await lookup_semantic(vector)
    if result is None:
        return {"cache_hit": False}

    row, _sim = result
    raw_sources = (row.sources or {}).get("items", []) if isinstance(row.sources, dict) else []
    sources: list[dict[str, Any]] = [
        {
            "letter_year": s.get("letter_year"),
            "passage": s.get("passage", ""),
            "similarity_score": float(s.get("similarity_score") or 0.0),
            "qdrant_point_id": str(s.get("qdrant_point_id", "")),
        }
        for s in raw_sources
    ]

    return {
        "cache_hit": True,
        "draft_answer": row.cached_response,
        "grounded": True if sources else None,
        "sources": sources,
        "messages": [AIMessage(content=row.cached_response)],
    }


# ── load_memory ──────────────────────────────────────────────────────────────

from app.modules.chat_history.long_term.service import LongTermMemoryService


async def load_memory(state: ZimShireState, config: RunnableConfig, *, store: BaseStore) -> dict:
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return {"user_profile": {}}

    query = state.get("query") or ""
    svc = LongTermMemoryService(store)
    profile = await svc.load_profile(str(user_id), query)
    return {"user_profile": profile.model_dump()}
