"""Integration tests for SSE streaming endpoint — mocks TurnOrchestrationService."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

import httpx

from tests.helpers.sse_parser import find_event, parse_sse_lines

_CHAT_ID = uuid4()
_USER_ID = uuid4()

_DONE_EVENT = (
    f'{{"type": "done", "message_id": "{uuid4()}", '
    f'"grounded": true, "sources": [], '
    f'"langfuse_trace_id": "trace-test", "cache_hit": false}}'
)


# ── helpers ─────────────────────────────────────────────────────────────────


def _patched_app():
    from app.main import app
    app.state.graph = MagicMock()
    app.state.store = MagicMock()
    app.state.tool_registry = MagicMock()
    return app


def _make_turn_svc(sse_lines: list[str]):
    """Return a get_turn_service override that yields the given SSE lines."""
    async def _stream(*args, **kwargs):
        for line in sse_lines:
            yield line

    svc = MagicMock()
    svc.stream_turn = _stream
    return lambda: svc


async def _post_message(app, sse_lines: list[str]) -> list[dict]:
    from app.api.deps import get_turn_service
    from app.core.dependencies import get_db

    db = MagicMock()
    db.__aenter__ = MagicMock(return_value=db)
    db.__aexit__ = MagicMock(return_value=None)

    fake_chat = MagicMock()
    fake_chat.chat_id = _CHAT_ID
    fake_chat.user_id = _USER_ID

    async def _fake_get_chat(session, chat_id):
        return fake_chat

    # Patch get_chat where the router imports it (not in the repository module)
    import app.modules.messages.router as msg_router
    orig_get_chat = msg_router.get_chat
    msg_router.get_chat = _fake_get_chat

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_turn_service] = _make_turn_svc(sse_lines)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/chats/{_CHAT_ID}/messages",
                json={"user_id": str(_USER_ID), "query": "test query"},
            )
        return parse_sse_lines(resp.text)
    finally:
        msg_router.get_chat = orig_get_chat
        app.dependency_overrides.clear()


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_progress_events_appear_before_tokens():
    """Progress events must arrive before the first token."""
    lines = [
        f'data: {{"type": "progress", "stage": "rag", "message": "Searching Buffett letters…"}}\n\n',
        f'data: {{"type": "progress", "stage": "synthesizing", "message": "Composing answer…"}}\n\n',
        f'data: {{"type": "token", "content": "Warren"}}\n\n',
        f'data: {{"type": "token", "content": " Buffett"}}\n\n',
        f'data: {_DONE_EVENT}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    types = [e["type"] for e in events]
    first_token_idx = types.index("token")
    progress_indices = [i for i, t in enumerate(types) if t == "progress"]

    assert progress_indices, "expected at least one progress event"
    assert all(i < first_token_idx for i in progress_indices), (
        "all progress events must come before the first token"
    )


@pytest.mark.asyncio
async def test_token_content_is_non_empty():
    """All token events must have non-empty content."""
    lines = [
        f'data: {{"type": "token", "content": "Warren"}}\n\n',
        f'data: {{"type": "token", "content": " Buffett consistently"}}\n\n',
        f'data: {_DONE_EVENT}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 2
    for evt in token_events:
        assert isinstance(evt["content"], str) and evt["content"], (
            f"token content must be non-empty: {evt}"
        )


@pytest.mark.asyncio
async def test_input_blocked_no_tokens():
    """Blocked queries emit 'blocked' + 'done' with no token events."""
    lines = [
        f'data: {{"type": "blocked", "reason": "off-topic"}}\n\n',
        f'data: {{"type": "done", "message_id": null, "grounded": null, '
        f'"sources": [], "langfuse_trace_id": "t1", "cache_hit": false}}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    types = [e["type"] for e in events]
    assert "token" not in types
    assert "blocked" in types
    done = find_event(events, "done")
    assert done is not None
    assert done["message_id"] is None


@pytest.mark.asyncio
async def test_cache_hit_has_tokens_no_progress():
    """Cache hits stream tokens but emit no progress events."""
    lines = [
        f'data: {{"type": "token", "content": "Based on Buffett\'s 1988"}}\n\n',
        f'data: {{"type": "token", "content": " letter..."}}\n\n',
        f'data: {{"type": "done", "message_id": "{uuid4()}", "grounded": true, '
        f'"sources": [], "langfuse_trace_id": "t2", "cache_hit": true}}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    assert any(e["type"] == "token" for e in events)
    assert not any(e["type"] == "progress" for e in events)
    done = find_event(events, "done")
    assert done is not None and done["cache_hit"] is True


@pytest.mark.asyncio
async def test_output_rewritten_sends_replace():
    """When output guardrail rewrites, client receives 'replace' event before 'done'."""
    safe_text = "ZimShire can help you research companies through Buffett's philosophy."
    lines = [
        f'data: {{"type": "token", "content": "Buy Apple now!"}}\n\n',
        f'data: {{"type": "replace", "content": "{safe_text}"}}\n\n',
        f'data: {{"type": "done", "message_id": "{uuid4()}", "grounded": false, '
        f'"sources": [], "langfuse_trace_id": "t3", "cache_hit": false}}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    types = [e["type"] for e in events]
    assert "replace" in types
    replace_evt = find_event(events, "replace")
    assert replace_evt is not None
    assert "ZimShire" in replace_evt["content"]

    # replace must appear before done
    assert types.index("replace") < types.index("done")


@pytest.mark.asyncio
async def test_done_event_has_required_fields():
    """Done event must contain all required fields."""
    msg_id = str(uuid4())
    lines = [
        f'data: {{"type": "token", "content": "Hello"}}\n\n',
        f'data: {{"type": "done", "message_id": "{msg_id}", "grounded": true, '
        f'"sources": [{{"letter_year": 1988, "passage": "moats", "similarity_score": 0.5, "qdrant_point_id": "abc"}}], '
        f'"langfuse_trace_id": "trace-xyz", "cache_hit": false}}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    done = find_event(events, "done")
    assert done is not None
    assert done["message_id"] == msg_id
    assert done["grounded"] is True
    assert isinstance(done["sources"], list) and len(done["sources"]) == 1
    assert done["langfuse_trace_id"] == "trace-xyz"
    assert done["cache_hit"] is False


@pytest.mark.asyncio
async def test_done_is_always_last_event():
    """'done' must always be the final event in the stream."""
    for lines in [
        # Normal path
        [
            f'data: {{"type": "token", "content": "Hello"}}\n\n',
            f'data: {_DONE_EVENT}\n\n',
        ],
        # Blocked path
        [
            f'data: {{"type": "blocked", "reason": "off-topic"}}\n\n',
            f'data: {{"type": "done", "message_id": null, "grounded": null, '
            f'"sources": [], "langfuse_trace_id": "t1", "cache_hit": false}}\n\n',
        ],
        # Replace path
        [
            f'data: {{"type": "token", "content": "bad"}}\n\n',
            f'data: {{"type": "replace", "content": "safe"}}\n\n',
            f'data: {_DONE_EVENT}\n\n',
        ],
    ]:
        events = await _post_message(_patched_app(), lines)
        assert events, "stream must not be empty"
        assert events[-1]["type"] == "done", (
            f"last event must be 'done', got: {events[-1]}"
        )


@pytest.mark.asyncio
async def test_multiple_progress_stages_ordered():
    """Progress events for different stages arrive in pipeline order."""
    lines = [
        f'data: {{"type": "progress", "stage": "rag", "message": "Searching Buffett letters…"}}\n\n',
        f'data: {{"type": "progress", "stage": "market", "message": "Fetching market data…"}}\n\n',
        f'data: {{"type": "progress", "stage": "synthesizing", "message": "Composing answer…"}}\n\n',
        f'data: {{"type": "token", "content": "Analysis:"}}\n\n',
        f'data: {_DONE_EVENT}\n\n',
    ]
    events = await _post_message(_patched_app(), lines)

    types = [e["type"] for e in events]
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["rag", "market", "synthesizing"]
    assert types.index("token") > types.index("progress")
