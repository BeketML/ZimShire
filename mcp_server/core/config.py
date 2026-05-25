from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "buffett_letters"
    litellm_base_url: str = ""
    litellm_api_key: str = ""
    litellm_end_user_id: str = ""
    embedding_model: str = "text-embedding-3-small"
    passage_snippet_max: int = 800
    sparse_embedding_model: str = "qdrant/bm25"
    reranker_model: str = "answerdotai/answerai-colbert-small-v1"
    duckduckgo_api_key: str = ""
    # ColBERT / hybrid search constants — not in .env, stable values
    late_interaction_vector_name: str = "multi"
    colbert_embedding_dim: int = 96
    hybrid_prefetch_limit: int = 20

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def embeddings_url(self) -> str:
        base = self.litellm_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        return base + "/embeddings"


settings = Settings()
