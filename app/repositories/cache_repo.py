"""Cache repos: market_data_cache (TTL by ticker+data_type) + semantic_cache (pgvector).

Semantic cache reads/writes the raw vector via pgvector's `<=>` cosine-distance op.
Distance is in [0, 2]; we convert to similarity = 1 - distance / 2 (cosine in [-1, 1]).
For unit vectors from text-embedding-3-small the simple `1 - distance` is fine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MarketDataCache, SemanticCache

# ---- market_data_cache ----------------------------------------------------

MARKET_DEFAULT_TTL = timedelta(hours=1)


async def get_valid_market(
    session: AsyncSession, *, ticker: str, data_type: str
) -> MarketDataCache | None:
    now = datetime.now(timezone.utc)
    return await session.scalar(
        select(MarketDataCache)
        .where(MarketDataCache.ticker == ticker)
        .where(MarketDataCache.data_type == data_type)
        .where(MarketDataCache.expires_at > now)
        .order_by(MarketDataCache.fetched_at.desc())
        .limit(1)
    )


async def upsert_market(
    session: AsyncSession,
    *,
    ticker: str,
    data_type: str,
    payload: dict[str, Any],
    ttl: timedelta = MARKET_DEFAULT_TTL,
) -> None:
    expires = datetime.now(timezone.utc) + ttl
    session.add(
        MarketDataCache(
            ticker=ticker, data_type=data_type, payload=payload, expires_at=expires
        )
    )
    await session.flush()


# ---- semantic_cache (pgvector) -------------------------------------------

SEMANTIC_SIMILARITY_THRESHOLD = 0.92


async def find_similar(
    session: AsyncSession, *, embedding: list[float]
) -> tuple[SemanticCache, float] | None:
    """Return (row, similarity) for the most similar cached query above threshold."""
    stmt = text(
        """
        SELECT id, original_query, cached_response, sources, hit_count,
               1 - (query_embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM semantic_cache
        WHERE expires_at IS NULL OR expires_at > NOW()
        ORDER BY query_embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """
    ).bindparams(bindparam("embedding"))
    res = await session.execute(stmt, {"embedding": embedding})
    row = res.first()
    if row is None:
        return None
    sim = float(row.similarity)
    if sim < SEMANTIC_SIMILARITY_THRESHOLD:
        return None
    cache_row = await session.scalar(select(SemanticCache).where(SemanticCache.id == row.id))
    if cache_row is None:
        return None
    return cache_row, sim


async def bump_hit(session: AsyncSession, cache_id) -> None:
    await session.execute(
        update(SemanticCache)
        .where(SemanticCache.id == cache_id)
        .values(hit_count=SemanticCache.hit_count + 1)
    )


async def insert_semantic(
    session: AsyncSession,
    *,
    embedding: list[float],
    original_query: str,
    cached_response: str,
    sources: list[dict] | None,
    ttl: timedelta | None = timedelta(days=7),
) -> None:
    expires = datetime.now(timezone.utc) + ttl if ttl else None
    row = SemanticCache(
        query_embedding=embedding,
        original_query=original_query,
        cached_response=cached_response,
        sources={"items": sources} if sources else None,
        hit_count=0,
        expires_at=expires,
    )
    session.add(row)
    await session.flush()
