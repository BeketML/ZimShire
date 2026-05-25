from __future__ import annotations

import httpx
from fastembed import LateInteractionTextEmbedding, SparseTextEmbedding

from mcp_server.core.config import Settings


class DenseEmbedder:
    def __init__(self, settings: Settings, http_client: httpx.Client) -> None:
        self._settings = settings
        self._http = http_client

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        resp = self._http.post(
            self._settings.embeddings_url,
            headers={
                "Authorization": f"Bearer {self._settings.litellm_api_key}",
                "x-litellm-end-user-id": self._settings.litellm_end_user_id,
                "Content-Type": "application/json",
            },
            json={"model": self._settings.embedding_model, "input": text},
            timeout=30.0,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


class SparseEmbedder:
    """BM25 sparse embedder. Uses query_embed() for queries, embed() for documents."""

    def __init__(self, model_name: str) -> None:
        self._model = SparseTextEmbedding(model_name=model_name)

    def embed_query(self, text: str) -> dict[int, float]:
        result = next(self._model.query_embed(text))
        return dict(zip(result.indices.tolist(), result.values.tolist()))


class LateInteractionEmbedder:
    """ColBERT late interaction embedder for query-time reranking inside Qdrant."""

    def __init__(self, model_name: str) -> None:
        self._model = LateInteractionTextEmbedding(model_name=model_name)

    def embed_query(self, text: str) -> list[list[float]]:
        import numpy as np
        result = next(self._model.query_embed(text))
        if isinstance(result, np.ndarray):
            return result.tolist()
        return [v.tolist() if isinstance(v, np.ndarray) else list(v) for v in result]
