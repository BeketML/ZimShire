"""Helpers used by the messages router to persist a completed graph turn."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.repositories import cache_repo, chat_repo, message_repo, rag_repo
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)


async def persist_assistant_turn(
    session: AsyncSession,
    *,
    chat_id: UUID,
    user_id: UUID,
    user_query: str,
    final_state: dict,
    langfuse_trace_id: str,
    store=None,
) -> Message:
    """Stage 10 — persist assistant row, rag_retrievals, semantic_cache, store memory, touch chat."""
    draft = final_state.get("draft_answer", "")
    grounded = final_state.get("grounded")
    sources = final_state.get("sources") or []

    assistant_msg = await message_repo.create_assistant_message(
        session,
        chat_id=chat_id,
        content=draft,
        grounded=grounded,
        langfuse_trace_id=langfuse_trace_id,
    )

    rag_chunks = final_state.get("rag_agent_chunks") or []
    if rag_chunks:
        used_ids = {str(s.get("qdrant_point_id")) for s in sources if s.get("qdrant_point_id")}
        await rag_repo.bulk_create(
            session,
            message_id=assistant_msg.message_id,
            chunks=rag_chunks,
            used_point_ids=used_ids,
        )

    # Semantic cache write (only when grounded answer + small response) — bonus
    if draft and not final_state.get("cache_hit"):
        try:
            vector = await embed_text(user_query)
            await cache_repo.insert_semantic(
                session,
                embedding=vector,
                original_query=user_query,
                cached_response=draft,
                sources=[
                    {
                        "letter_year": s.get("letter_year"),
                        "passage": s.get("passage"),
                        "similarity_score": s.get("similarity_score"),
                        "qdrant_point_id": s.get("qdrant_point_id"),
                    }
                    for s in sources
                ],
                ttl=timedelta(days=7),
            )
        except Exception as e:
            logger.warning("semantic_cache insert failed: %s", e)

    # Long-term memory: aput per ticker discovered this turn (bonus)
    if store is not None:
        market_text = final_state.get("market_agent_result") or ""
        tickers: list[str] = []
        if market_text:
            try:
                parsed = json.loads(market_text)
                if isinstance(parsed, dict):
                    tickers = list(parsed.keys())
            except json.JSONDecodeError:
                pass
        for ticker in tickers:
            try:
                await store.aput(
                    ("users", str(user_id), "interests"),
                    key=ticker,
                    value={"company": ticker, "interest": user_query},
                )
            except Exception as e:
                logger.warning("store.aput for %s failed: %s", ticker, e)

    await chat_repo.touch_chat(session, chat_id)
    return assistant_msg
