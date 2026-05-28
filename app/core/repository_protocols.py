"""Repository Protocol interfaces — one per domain (chat, message, user)."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.models.models import Chat, Message, User


class ChatRepositoryProtocol(Protocol):
    async def get(self, chat_id: UUID) -> Chat | None: ...
    async def create(
        self, *, user_id: UUID, chat_title: str | None, model: str, provider: str
    ) -> Chat: ...
    async def touch(self, chat_id: UUID) -> None: ...


class MessageRepositoryProtocol(Protocol):
    async def list(self, chat_id: UUID) -> list[Message]: ...
    async def create_human(self, *, chat_id: UUID, content: str) -> Message: ...
    async def create_assistant(
        self,
        *,
        chat_id: UUID,
        content: str,
        grounded: bool | None,
        langfuse_trace_id: str | None,
    ) -> Message: ...


class UserRepositoryProtocol(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...
    async def create(self, *, name: str | None, surname: str | None) -> User: ...
