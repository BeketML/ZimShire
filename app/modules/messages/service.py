"""Stage 10 — persist the completed graph turn to Postgres."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.modules.chat_history.long_term.schemas import UserProfile
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.modules.messages.commands import (
    CreateAssistantMessageCommand,
    InsertRAGRetrievalsCommand,
    TouchChatCommand,
    UpdateLongTermMemoryCommand,
    WriteSemanticCacheCommand,
)
from app.modules.messages.handlers import (
    handle_create_assistant_message,
    handle_insert_rag_retrievals,
    handle_touch_chat,
    handle_update_long_term_memory,
    handle_write_semantic_cache,
)
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


async def _safe_update_memory(cmd: UpdateLongTermMemoryCommand, store) -> None:
    try:
        await handle_update_long_term_memory(cmd, store)
    except Exception as exc:
        logger.error("long_term_memory update failed for user=%s: %s", cmd.user_id, exc)


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
    assistant_msg = await handle_create_assistant_message(
        session,
        CreateAssistantMessageCommand(
            chat_id=chat_id,
            content=draft,
            grounded=grounded,
            langfuse_trace_id=langfuse_trace_id,
        ),
    )

    # 2. Insert rag_retrievals
    rag_chunks = final_state.get("rag_agent_chunks") or []
    used_ids = frozenset(str(s.get("qdrant_point_id")) for s in sources if s.get("qdrant_point_id"))
    await handle_insert_rag_retrievals(
        session,
        InsertRAGRetrievalsCommand(
            message_id=assistant_msg.message_id,
            chunks=rag_chunks,
            used_point_ids=used_ids,
        ),
    )

    # 3. Semantic cache write
    if draft and not final_state.get("cache_hit"):
        try:
            vector = await embed_text(user_query)
        except Exception as exc:
            logger.warning("embed_text failed, skipping cache write: %s", exc)
            vector = []
        await handle_write_semantic_cache(
            WriteSemanticCacheCommand(
                query=user_query,
                response=draft,
                sources=tuple(
                    {
                        "letter_year": s.get("letter_year"),
                        "passage": s.get("passage"),
                        "similarity_score": s.get("similarity_score"),
                        "qdrant_point_id": s.get("qdrant_point_id"),
                    }
                    for s in sources
                ),
                embedding=tuple(vector),
            )
        )

    # 4. Long-term memory (fire-and-forget)
    if store is not None and not final_state.get("cache_hit") and not final_state.get("input_blocked"):
        all_messages: list[BaseMessage] = final_state.get("messages") or []
        recent_turns = _short_term_svc._extract(all_messages, limit=5).turn_pairs
        market_tickers = _extract_market_tickers(final_state)
        current_profile_dict = final_state.get("user_profile") or {}
        current_profile = UserProfile(
            tracked_companies=current_profile_dict.get("tracked_companies", []),
            research_interests=current_profile_dict.get("research_interests", []),
            preferences=current_profile_dict.get("preferences", {}),
            explicit_memories=current_profile_dict.get("explicit_memories", []),
        )
        asyncio.create_task(
            _safe_update_memory(
                UpdateLongTermMemoryCommand(
                    user_id=user_id,
                    query=user_query,
                    draft_answer=draft,
                    recent_turns=recent_turns,
                    current_profile=current_profile,
                    market_tickers=market_tickers,
                ),
                store,
            )
        )

    # 5. Touch chat updated_at
    await handle_touch_chat(session, TouchChatCommand(chat_id=chat_id))
    return assistant_msg
