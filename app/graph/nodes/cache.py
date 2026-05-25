"""Semantic cache check (bonus task).

Embeds the latest user query, looks up the closest vector in `semantic_cache`,
and short-circuits the graph if cosine similarity ≥ threshold.
On error or no hit, returns a clean cache_miss (the graph proceeds normally).
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.db.database import AsyncSessionLocal
from app.graph.state import ZimShireState
from app.repositories import cache_repo
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)


async def semantic_cache_check(state: ZimShireState, config: RunnableConfig) -> dict:
    query = state.get("query") or ""
    if not query.strip():
        return {"cache_hit": False}

    try:
        vector = await embed_text(query)
    except Exception as e:
        logger.warning("semantic_cache_check embed failed: %s", e)
        return {"cache_hit": False}

    try:
        async with AsyncSessionLocal() as session:
            result = await cache_repo.find_similar(session, embedding=vector)
            if result is None:
                return {"cache_hit": False}
            row, similarity = result
            await cache_repo.bump_hit(session, row.id)
            await session.commit()
    except Exception as e:
        logger.warning("semantic_cache_check lookup failed: %s", e)
        return {"cache_hit": False}

    raw_sources = (row.sources or {}).get("items", []) if isinstance(row.sources, dict) else []
    sources: list[dict[str, Any]] = []
    for s in raw_sources:
        sources.append(
            {
                "letter_year": s.get("letter_year"),
                "passage": s.get("passage", ""),
                "similarity_score": float(s.get("similarity_score") or 0.0),
                "qdrant_point_id": str(s.get("qdrant_point_id", "")),
            }
        )

    return {
        "cache_hit": True,
        "draft_answer": row.cached_response,
        "grounded": True if sources else None,
        "sources": sources,
        "messages": [AIMessage(content=row.cached_response)],
    }
