from __future__ import annotations

import httpx
from fastembed import SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from mcp_server.core.config import Settings


class DenseEmbedder:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        headers = {
            "Authorization": f"Bearer {self._settings.litellm_api_key}",
            "x-litellm-end-user-id": self._settings.litellm_end_user_id,
            "Content-Type": "application/json",
        }
        payload = {"model": self._settings.embedding_model, "input": text}

        resp = await self._http.post(
            self._settings.embeddings_url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


class SparseEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model = SparseTextEmbedding(model_name=model_name)

    def embed(self, text: str) -> dict[int, float]:
        result = next(self._model.embed([text]))
        return dict(zip(result.indices.tolist(), result.values.tolist()))


class Reranker:
    def __init__(self, model_name: str) -> None:
        self._model = TextCrossEncoder(model_name=model_name)

    def rerank(self, query: str, hits: list[dict], top_k: int) -> list[dict]:
        if not hits:
            return hits
        passages = [h["passage_snippet"] for h in hits]
        scores = list(self._model.rerank(query, passages))
        ranked = sorted(zip(hits, scores), key=lambda pair: pair[1], reverse=True)[:top_k]
        result = []
        for hit, score in ranked:
            hit["similarity_score"] = float(score)
            result.append(hit)
        return result
