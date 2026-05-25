from __future__ import annotations

from fastembed import SparseTextEmbedding

from mcp_server.services.protocols import SparseEmbeddingServiceInterface


class FastEmbedSparseEmbeddingService(SparseEmbeddingServiceInterface):
    def __init__(self, model_name: str) -> None:
        self._model = SparseTextEmbedding(model_name=model_name)

    def embed_query_sparse(self, text: str) -> dict[int, float]:
        result = next(self._model.embed([text]))
        return dict(zip(result.indices.tolist(), result.values.tolist()))
