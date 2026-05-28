"""Semantic cache repository — pgvector cosine similarity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.models import SemanticCache


async def find_similar(
    session: AsyncSession, *, embedding: list[float]
) -> tuple[SemanticCache, float] | None:
    stmt = text(
        """
        SELECT id,
               1 - (query_embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM semantic_cache
        WHERE expires_at IS NULL OR expires_at > NOW()
        ORDER BY query_embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """
    ).bindparams(bindparam("embedding"))
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    res = await session.execute(stmt, {"embedding": embedding_str})
    row = res.first()
    if row is None or float(row.similarity) < settings.semantic_similarity_threshold:
        return None
    cache_row = await session.scalar(select(SemanticCache).where(SemanticCache.id == row.id))
    if cache_row is None:
        return None
    return cache_row, float(row.similarity)


async def list_semantic(
    session: AsyncSession, *, limit: int = 50
) -> list[SemanticCache]:
    rows = await session.scalars(
        select(SemanticCache).order_by(SemanticCache.expires_at.desc().nullslast()).limit(limit)
    )
    return list(rows)


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
    ttl: timedelta | None = None,
) -> None:
    if ttl is None:
        ttl = settings.semantic_cache_ttl
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
