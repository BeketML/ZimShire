"""Debug / inspect endpoints — read-only views into cache and per-chat logs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.modules.cache import repository as cache_repo
from app.modules.guardrails import repository as guardrail_repo
from app.modules.rag_retrievals import repository as rag_repo

router = APIRouter(prefix="/debug", tags=["inspect"])


# ── Schemas ────────────────────────────────────────────────────────────────


class SemanticCacheRow(BaseModel):
    id: UUID
    original_query: str
    hit_count: int
    expires_at: datetime | None

    class Config:
        from_attributes = True


class MarketCacheRow(BaseModel):
    id: UUID
    ticker: str
    data_type: str
    fetched_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class RagRetrievalRow(BaseModel):
    id: UUID
    message_id: UUID
    letter_year: int | None
    passage_snippet: str | None
    similarity_score: float | None
    used_in_response: bool | None
    created_at: datetime

    class Config:
        from_attributes = True


class GuardrailLogRow(BaseModel):
    id: UUID
    message_id: UUID
    guardrail_type: str
    result: str
    confidence: float | None
    blocked_reason: str | None
    checked_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/semantic-cache", response_model=list[SemanticCacheRow])
async def list_semantic_cache(
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[SemanticCacheRow]:
    rows = await cache_repo.list_semantic(db, limit=limit)
    return [SemanticCacheRow.model_validate(r) for r in rows]


@router.get("/market-data-cache", response_model=list[MarketCacheRow])
async def list_market_cache(
    limit: int = Query(100, ge=1, le=500, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[MarketCacheRow]:
    rows = await cache_repo.list_market(db, limit=limit)
    return [MarketCacheRow.model_validate(r) for r in rows]


@router.get("/chats/{chat_id}/rag-retrievals", response_model=list[RagRetrievalRow])
async def list_rag_retrievals(
    chat_id: UUID,
    limit: int = Query(200, ge=1, le=1000, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[RagRetrievalRow]:
    rows = await rag_repo.list_for_chat(db, chat_id, limit=limit)
    return [RagRetrievalRow.model_validate(r) for r in rows]


@router.get("/chats/{chat_id}/guardrail-logs", response_model=list[GuardrailLogRow])
async def list_guardrail_logs(
    chat_id: UUID,
    limit: int = Query(200, ge=1, le=1000, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[GuardrailLogRow]:
    rows = await guardrail_repo.list_for_chat(db, chat_id, limit=limit)
    return [GuardrailLogRow.model_validate(r) for r in rows]
