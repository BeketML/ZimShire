"""Stage 10 — persist the completed graph turn to Postgres."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.modules.cache.gateways import write_semantic
from app.modules.chats.repository import touch_chat
from app.modules.messages.repository import create_assistant_message
from app.modules.rag_retrievals.repository import bulk_create as bulk_create_rag
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
    draft = final_state.get("draft_answer", "")
    grounded = final_state.get("grounded")
    sources = final_state.get("sources") or []

    # 1. Insert assistant message
    assistant_msg = await create_assistant_message(
        session,
        chat_id=chat_id,
        content=draft,
        grounded=grounded,
        langfuse_trace_id=langfuse_trace_id,
    )

    # 2. Insert rag_retrievals (N rows for N Qdrant hits)
    rag_chunks = final_state.get("rag_agent_chunks") or []
    if rag_chunks:
        used_ids = {str(s.get("qdrant_point_id")) for s in sources if s.get("qdrant_point_id")}
        await bulk_create_rag(
            session,
            message_id=assistant_msg.message_id,
            chunks=rag_chunks,
            used_point_ids=used_ids,
        )

    # 3. Semantic cache write (skip if this was a cache hit)
    if draft and not final_state.get("cache_hit"):
        try:
            vector = await embed_text(user_query)
            await write_semantic(
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
        except Exception as exc:
            logger.warning("semantic_cache insert failed: %s", exc)

    # 4. Long-term memory: aput per ticker from market context
    if store is not None:
        market_text = (final_state.get("collected_context") or {}).get("market", "")
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
            except Exception as exc:
                logger.warning("store.aput for %s failed: %s", ticker, exc)

    # 5. Touch chat updated_at
    await touch_chat(session, chat_id)
    return assistant_msg
