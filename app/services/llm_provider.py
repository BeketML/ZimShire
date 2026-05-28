"""LiteLLMProvider — concrete LLMProvider backed by the LiteLLM gateway."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.core.providers import ConfigProvider
from app.services.llm import get_chat_model


class LiteLLMProvider:
    """Wraps the cached llm.py factory functions behind an LLMProvider interface."""

    def __init__(self, config: ConfigProvider) -> None:
        self._config = config

    def get_orchestrator_model(self) -> BaseChatModel:
        return get_chat_model(self._config.orchestrator_model, temperature=0.2, max_tokens=1500)

    def get_subagent_model(self) -> BaseChatModel:
        return get_chat_model(self._config.subagent_model, temperature=0.1)

    def get_guardrail_model(self) -> BaseChatModel:
        return get_chat_model(self._config.guardrail_model, temperature=0.0)

    def get_memory_model(self) -> BaseChatModel:
        return get_chat_model(self._config.memory_model, temperature=0.0)
