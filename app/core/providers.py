"""Provider protocols — abstract interfaces for config, LLM, and embedding."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel


@runtime_checkable
class ConfigProvider(Protocol):
    database_url: str
    qdrant_url: str
    mcp_base_url: str
    mcp_port: int
    default_chat_model: str
    default_provider: str
    orchestrator_model: str
    subagent_model: str
    guardrail_model: str
    memory_model: str
    embedding_model: str
    litellm_base_url: str
    litellm_api_key: str
    litellm_end_user_id: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str
    fail_open_on_guardrail_error: bool
    semantic_similarity_threshold: float
    semantic_cache_ttl_days: int
    market_cache_ttl_hours: int
    faithfulness_score_threshold: float
    faithfulness_min_strong_hits: int
    output_guardrail_max_retries: int
    short_term_turn_pairs: int


@runtime_checkable
class LLMProvider(Protocol):
    def get_orchestrator_model(self) -> BaseChatModel: ...
    def get_subagent_model(self) -> BaseChatModel: ...
    def get_guardrail_model(self) -> BaseChatModel: ...
    def get_memory_model(self) -> BaseChatModel: ...


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
