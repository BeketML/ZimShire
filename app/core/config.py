from datetime import timedelta
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str
    qdrant_url: str = "http://localhost:6333"
    mcp_base_url: str = "http://localhost:8001"
    mcp_port: int = 8001
    litellm_base_url: str = ""
    litellm_api_key: str = ""
    litellm_end_user_id: str = ""
    # Per-role model config (all via LiteLLM gateway)
    default_chat_model: str = "gpt-4o-mini"
    default_provider: str = "openai"
    orchestrator_model: str = "claude-sonnet-4-6"
    subagent_model: str = "claude-haiku-4-5"
    guardrail_model: str = "gpt-4o-mini"
    memory_model: str = "claude-haiku-4-5"
    embedding_model: str = "text-embedding-3-small"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""
    fail_open_on_guardrail_error: bool = True

    # --- Thresholds & TTLs ---
    semantic_similarity_threshold: float = 0.92
    semantic_cache_ttl_days: int = 7
    market_cache_ttl_hours: int = 1
    faithfulness_score_threshold: float = 0.40
    faithfulness_min_strong_hits: int = 2
    output_guardrail_max_retries: int = 2
    short_term_turn_pairs: int = 5

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def semantic_cache_ttl(self) -> timedelta:
        return timedelta(days=self.semantic_cache_ttl_days)

    @property
    def market_cache_ttl(self) -> timedelta:
        return timedelta(hours=self.market_cache_ttl_hours)


settings = Settings()
