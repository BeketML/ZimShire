"""FastAPI dependency factories for service injection."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as _settings
from app.core.dependencies import get_db
from app.core.providers import ConfigProvider, EmbeddingProvider, LLMProvider
from app.services.embedding_provider import LiteLLMEmbedder
from app.services.llm_provider import LiteLLMProvider

__all__ = [
    "get_db",
    "get_config",
    "get_llm_provider",
    "get_embedding_provider",
    "get_turn_service",
    "get_chat_repo",
    "get_message_repo",
    "get_user_repo",
]


def get_config() -> ConfigProvider:
    return _settings


def get_llm_provider(config: ConfigProvider = Depends(get_config)) -> LLMProvider:
    return LiteLLMProvider(config)


def get_embedding_provider(config: ConfigProvider = Depends(get_config)) -> EmbeddingProvider:
    return LiteLLMEmbedder(config)


def get_turn_service():
    from app.modules.agents.service import get_graph, get_store
    from app.modules.messages.turn_service import TurnOrchestrationService

    return TurnOrchestrationService(get_graph(), get_store())


def get_chat_repo(db: AsyncSession = Depends(get_db)):
    from app.modules.chats.repository import SqlChatRepository

    return SqlChatRepository(db)


def get_message_repo(db: AsyncSession = Depends(get_db)):
    from app.modules.messages.repository import SqlMessageRepository

    return SqlMessageRepository(db)


def get_user_repo(db: AsyncSession = Depends(get_db)):
    from app.modules.users.repository import SqlUserRepository

    return SqlUserRepository(db)
