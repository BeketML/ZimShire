from __future__ import annotations

import httpx
from mcp_server.core.config import Settings
from mcp_server.services.protocols import EmbeddingServiceInterface

class LiteLLMEmbeddingService(EmbeddingServiceInterface):
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        headers = {
            "Authorization": f"Bearer {self._settings.litellm_api_key}",
            "x-litellm-end-user-id": self._settings.litellm_end_user_id,
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.embedding_model,
            "input": text,
        }

        if self._http is not None:
            resp = await self._http.post(
                self._settings.embeddings_url,
                headers=headers,
                json=payload,
                timeout=30.0,
            )
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self._settings.embeddings_url,
                    headers=headers,
                    json=payload,
                )

        if resp.status_code >= 400:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
