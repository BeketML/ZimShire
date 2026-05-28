"""Market data cache repository — TTL-keyed by (ticker, data_type)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import MarketDataCache

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
    stmt = (
        pg_insert(MarketDataCache)
        .values(ticker=ticker, data_type=data_type, payload=payload, expires_at=expires)
        .on_conflict_do_update(
            constraint="uq_market_cache_ticker_type",
            set_={"payload": payload, "expires_at": expires},
        )
    )
    await session.execute(stmt)
    await session.flush()


async def list_market(
    session: AsyncSession, *, limit: int = 100
) -> list[MarketDataCache]:
    rows = await session.scalars(
        select(MarketDataCache).order_by(MarketDataCache.fetched_at.desc()).limit(limit)
    )
    return list(rows)
