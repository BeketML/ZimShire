"""LiteLLMEmbedder — concrete EmbeddingProvider backed by the LiteLLM gateway."""
from __future__ import annotations

from app.core.providers import ConfigProvider
from app.services.embedding import embed_text


class LiteLLMEmbedder:
    def __init__(self, config: ConfigProvider) -> None:
        self._config = config

    async def embed(self, text: str) -> list[float]:
        return await embed_text(text)
