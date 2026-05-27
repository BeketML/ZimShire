"""Semantic cache check node."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.modules.agents.state import ZimShireState
from app.modules.cache.gateways import lookup_semantic
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)


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
