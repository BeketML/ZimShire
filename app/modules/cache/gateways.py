"""Cache gateways — callable from graph nodes without injected session."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.cache import repository

logger = logging.getLogger(__name__)


async def lookup_market(ticker: str, data_type: str) -> dict | None:
    try:
        async with AsyncSessionLocal() as session:
            row = await repository.get_valid_market(session, ticker=ticker, data_type=data_type)
            return row.payload if row else None
    except Exception as exc:
        logger.error("cache.lookup_market(%s, %s) failed: %s", ticker, data_type, exc, exc_info=True)
        return None


async def store_market(ticker: str, data_type: str, payload: dict[str, Any]) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await repository.upsert_market(session, ticker=ticker, data_type=data_type, payload=payload)
            await session.commit()
    except Exception as exc:
        logger.error("cache.store_market(%s, %s) failed: %s", ticker, data_type, exc, exc_info=True)


async def lookup_semantic(embedding: list[float]):
    """Return (SemanticCache row, similarity) or None."""
    try:
        async with AsyncSessionLocal() as session:
            result = await repository.find_similar(session, embedding=embedding)
            if result is None:
                return None
            row, sim = result
            await repository.bump_hit(session, row.id)
            await session.commit()
            return row, sim
    except Exception as exc:
        logger.error("cache.lookup_semantic failed: %s", exc, exc_info=True)
        return None


async def write_semantic(
    *,
    embedding: list[float],
    original_query: str,
    cached_response: str,
    sources: list[dict] | None,
    ttl: timedelta | None = None,
) -> None:
    if ttl is None:
        ttl = settings.semantic_cache_ttl
    try:
        async with AsyncSessionLocal() as session:
            await repository.insert_semantic(
                session,
                embedding=embedding,
                original_query=original_query,
                cached_response=cached_response,
                sources=sources,
                ttl=ttl,
            )
            await session.commit()
    except Exception as exc:
        logger.error("cache.write_semantic failed: %s", exc, exc_info=True)
