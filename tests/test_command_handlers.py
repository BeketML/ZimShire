"""Unit tests for message persist command handlers."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.modules.messages.commands import (
    CreateAssistantMessageCommand,
    InsertRAGRetrievalsCommand,
    TouchChatCommand,
    WriteSemanticCacheCommand,
)


@pytest.mark.asyncio
async def test_handle_create_assistant_message():
    from app.modules.messages.handlers import handle_create_assistant_message

    mock_session = AsyncMock()
    fake_msg = MagicMock()
    fake_msg.message_id = UUID("00000000-0000-0000-0000-000000000001")

    with patch("app.modules.messages.handlers.create_assistant_message", return_value=fake_msg) as mock_create:
        cmd = CreateAssistantMessageCommand(
            chat_id=UUID("00000000-0000-0000-0000-000000000002"),
            content="Test answer",
            grounded=True,
            langfuse_trace_id="trace-123",
        )
        result = await handle_create_assistant_message(mock_session, cmd)

    mock_create.assert_called_once()
    assert result is fake_msg


@pytest.mark.asyncio
async def test_handle_insert_rag_retrievals_empty_chunks():
    from app.modules.messages.handlers import handle_insert_rag_retrievals

    mock_session = AsyncMock()
    cmd = InsertRAGRetrievalsCommand(
        message_id=UUID("00000000-0000-0000-0000-000000000001"),
        chunks=[],
        used_point_ids=frozenset(),
    )
    with patch("app.modules.messages.handlers.bulk_create_rag") as mock_bulk:
        await handle_insert_rag_retrievals(mock_session, cmd)
        mock_bulk.assert_not_called()


@pytest.mark.asyncio
async def test_handle_write_semantic_cache_skips_empty_embedding():
    from app.modules.messages.handlers import handle_write_semantic_cache

    cmd = WriteSemanticCacheCommand(
        query="test",
        response="answer",
        sources=(),
        embedding=(),  # empty = skip
    )
    with patch("app.modules.messages.handlers.write_semantic") as mock_write:
        await handle_write_semantic_cache(cmd)
        mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_handle_touch_chat():
    from app.modules.messages.handlers import handle_touch_chat

    mock_session = AsyncMock()
    chat_id = UUID("00000000-0000-0000-0000-000000000001")
    cmd = TouchChatCommand(chat_id=chat_id)

    with patch("app.modules.messages.handlers.touch_chat") as mock_touch:
        await handle_touch_chat(mock_session, cmd)
        mock_touch.assert_called_once_with(mock_session, chat_id)
