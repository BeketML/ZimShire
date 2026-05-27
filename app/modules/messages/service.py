"""Stage 10 — persist the completed graph turn to Postgres."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.modules.cache.gateways import write_semantic
from app.modules.chat_history.long_term.service import LongTermMemoryService
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.modules.chats.repository import touch_chat
from app.modules.messages.repository import create_assistant_message
from app.modules.rag_retrievals.repository import bulk_create as bulk_create_rag
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)

_short_term_svc = ShortTermMemoryService()


def _extract_market_tickers(final_state: dict) -> list[str]:
    for result in final_state.get("subagent_results") or []:
        if result.get("agent_name") != "market":
            continue
        raw = result.get("raw_artifacts") or {}
        market_data = raw.get("market_data") or {}
        if isinstance(market_data, dict) and market_data:
            return [k for k in market_data if not k.startswith("_")]
        tickers = raw.get("tickers") or []
        if tickers:
            return list(tickers)

    market_text = (final_state.get("collected_context") or {}).get("market", "")
    if not market_text:
        return []
    try:
        parsed = json.loads(market_text)
        if isinstance(parsed, dict):
            return list(parsed.keys())
    except json.JSONDecodeError:
        pass
    return []


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

    # 4. Long-term memory (skip for cache hits and blocked turns)
    if store is not None and not final_state.get("cache_hit") and not final_state.get("input_blocked"):
        all_messages: list[BaseMessage] = final_state.get("messages") or []
        recent_turns = _short_term_svc._extract(all_messages, limit=5).turn_pairs
        market_tickers = _extract_market_tickers(final_state)

        svc = LongTermMemoryService(store)
        try:
            from app.modules.chat_history.long_term.schemas import UserProfile
            current_profile_dict = final_state.get("user_profile") or {}
            current_profile = UserProfile(
                tracked_companies=current_profile_dict.get("tracked_companies", []),
                research_interests=current_profile_dict.get("research_interests", []),
                preferences=current_profile_dict.get("preferences", {}),
                explicit_memories=current_profile_dict.get("explicit_memories", []),
            )
            # Fire-and-forget in background task
            asyncio.create_task(
                svc.persist_from_turn(
                    user_id=str(user_id),
                    user_query=user_query,
                    draft_answer=draft,
                    recent_turns=recent_turns,
                    current_profile=current_profile,
                    market_tickers=market_tickers,
                )
            )
        except Exception as exc:
            logger.warning("long_term memory persist failed: %s", exc)

    # 5. Touch chat updated_at
    await touch_chat(session, chat_id)
    return assistant_msg
