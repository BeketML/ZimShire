"""Integration tests — httpx AsyncClient with dependency overrides (no real DB/LLM)."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── fixtures ────────────────────────────────────────────────────────────────


def _fake_db():
    """AsyncSession stub."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _patched_app():
    """Return the FastAPI app with app.state pre-set for tests."""
    from app.main import app
    app.state.graph = MagicMock()
    app.state.store = MagicMock()
    app.state.tool_registry = MagicMock()
    return app


# ── users ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_user_empty_body():
    """POST /users with empty body returns 201 with a UUID."""
    from app.core.dependencies import get_db

    fake_user = MagicMock()
    fake_user.user_id = uuid4()
    fake_user.name = None
    fake_user.surname = None
    fake_user.created_at = _NOW

    app = _patched_app()
    app.dependency_overrides[get_db] = lambda: _fake_db()

    try:
        with MagicMock() as _:
            import app.modules.users.service as user_service
            orig = user_service.create_user

            async def _fake_create(session, *, name, surname):
                return fake_user

            user_service.create_user = _fake_create

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/users", content=b"{}", headers={"Content-Type": "application/json"}
                )
            user_service.create_user = orig
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert "user_id" in data


@pytest.mark.asyncio
async def test_get_user_not_found():
    """GET /users/{id} returns 404 for unknown UUID."""
    from app.core.dependencies import get_db
    from app.core.exceptions import NotFoundError

    app = _patched_app()
    app.dependency_overrides[get_db] = lambda: _fake_db()

    try:
        import app.modules.users.service as user_service
        orig = user_service.get_user

        async def _fake_get(session, user_id):
            raise NotFoundError("not found")

        user_service.get_user = _fake_get

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/users/{uuid4()}")
        user_service.get_user = orig
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


# ── chats ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_chat_returns_201():
    from app.core.dependencies import get_db

    user_id = uuid4()
    fake_chat = MagicMock()
    fake_chat.chat_id = uuid4()
    fake_chat.user_id = user_id
    fake_chat.chat_title = "Test"
    fake_chat.model = "gpt-4o-mini"
    fake_chat.provider = "openai"
    fake_chat.created_at = _NOW
    fake_chat.updated_at = _NOW

    app = _patched_app()
    app.dependency_overrides[get_db] = lambda: _fake_db()

    try:
        import app.modules.chats.service as chat_service
        orig = chat_service.create_chat

        async def _fake_create(session, *, user_id, chat_title, model, provider):
            return fake_chat

        chat_service.create_chat = _fake_create

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/chats", json={"user_id": str(user_id), "chat_title": "Test"}
            )
        chat_service.create_chat = orig
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert "chat_id" in data


# ── messages history ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_messages_wrong_user_403():
    """GET /chats/{id}/messages with wrong user_id returns 403."""
    from app.core.dependencies import get_db

    chat_id = uuid4()
    real_user_id = uuid4()
    other_user_id = uuid4()

    fake_chat = MagicMock()
    fake_chat.chat_id = chat_id
    fake_chat.user_id = real_user_id

    app = _patched_app()
    app.dependency_overrides[get_db] = lambda: _fake_db()

    try:
        import app.modules.messages.router as msg_router
        orig = msg_router.get_chat

        async def _fake_get_chat(session, chat_id):
            return fake_chat

        msg_router.get_chat = _fake_get_chat

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/chats/{chat_id}/messages", params={"user_id": str(other_user_id)}
            )
        msg_router.get_chat = orig
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_messages_chat_not_found():
    from app.core.dependencies import get_db

    app = _patched_app()
    app.dependency_overrides[get_db] = lambda: _fake_db()

    try:
        import app.modules.messages.router as msg_router
        orig = msg_router.get_chat

        async def _fake_get_chat(session, chat_id):
            return None

        msg_router.get_chat = _fake_get_chat

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/chats/{uuid4()}/messages", params={"user_id": str(uuid4())}
            )
        msg_router.get_chat = orig
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


# ── providers ──────────────────────────────────────────────────────────────


def test_litellm_provider_returns_chat_models():
    from app.core.config import settings
    from app.services.llm_provider import LiteLLMProvider

    provider = LiteLLMProvider(settings)
    assert provider.get_orchestrator_model() is not None
    assert provider.get_guardrail_model() is not None
    assert provider.get_subagent_model() is not None
    assert provider.get_memory_model() is not None


def test_config_provider_satisfies_protocol():
    from app.core.config import settings
    from app.core.providers import ConfigProvider

    assert isinstance(settings, ConfigProvider)
