"""One async handler per persist command — each does exactly one DB concern."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.modules.cache.gateways import write_semantic
from app.modules.chat_history.long_term.service import LongTermMemoryService
from app.modules.chats.repository import touch_chat
from app.modules.messages.commands import (
    CreateAssistantMessageCommand,
    InsertRAGRetrievalsCommand,
    TouchChatCommand,
    UpdateLongTermMemoryCommand,
    WriteSemanticCacheCommand,
)
from app.modules.messages.repository import create_assistant_message
from app.modules.rag_retrievals.repository import bulk_create as bulk_create_rag

logger = logging.getLogger(__name__)


async def handle_create_assistant_message(
    session: AsyncSession, cmd: CreateAssistantMessageCommand
) -> Message:
    return await create_assistant_message(
        session,
        chat_id=cmd.chat_id,
        content=cmd.content,
        grounded=cmd.grounded,
        langfuse_trace_id=cmd.langfuse_trace_id,
    )


async def handle_insert_rag_retrievals(
    session: AsyncSession, cmd: InsertRAGRetrievalsCommand
) -> None:
    if not cmd.chunks:
        return
    await bulk_create_rag(
        session,
        message_id=cmd.message_id,
        chunks=list(cmd.chunks),
        used_point_ids=set(cmd.used_point_ids),
    )


async def handle_write_semantic_cache(cmd: WriteSemanticCacheCommand) -> None:
    if not cmd.embedding:
        return
    try:
        await write_semantic(
            embedding=list(cmd.embedding),
            original_query=cmd.query,
            cached_response=cmd.response,
            sources=list(cmd.sources) if cmd.sources else None,
            ttl=timedelta(days=7),
        )
    except Exception as exc:
        logger.warning("semantic_cache insert failed: %s", exc)


async def handle_update_long_term_memory(
    cmd: UpdateLongTermMemoryCommand, store
) -> None:
    svc = LongTermMemoryService(store)
    await svc.persist_from_turn(
        user_id=str(cmd.user_id),
        user_query=cmd.query,
        draft_answer=cmd.draft_answer,
        recent_turns=cmd.recent_turns,
        current_profile=cmd.current_profile,
        market_tickers=cmd.market_tickers,
    )


async def handle_touch_chat(session: AsyncSession, cmd: TouchChatCommand) -> None:
    await touch_chat(session, cmd.chat_id)
