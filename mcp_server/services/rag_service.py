from __future__ import annotations

from mcp_server.services.protocols import (
    EmbeddingServiceInterface,
    RAGServiceInterface,
    RerankerInterface,
    SearchHit,
    SparseEmbeddingServiceInterface,
    VectorStoreInterface,
)


class RAGService(RAGServiceInterface):
    def __init__(
        self,
        embedding_service: EmbeddingServiceInterface,
        sparse_embedding_service: SparseEmbeddingServiceInterface,
        vector_store: VectorStoreInterface,
        reranker: RerankerInterface,
    ) -> None:
        self._embedding_service = embedding_service
        self._sparse_embedding_service = sparse_embedding_service
        self._vector_store = vector_store
        self._reranker = reranker

    async def search(
        self,
        query: str,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[SearchHit]:
        dense_vec = await self._embedding_service.embed_query(query)
        sparse_vec = self._sparse_embedding_service.embed_query_sparse(query)
        candidates = await self._vector_store.search(
            dense_vec,
            sparse_vector=sparse_vec,
            top_k=top_k,
            letter_years_filter=letter_years_filter,
        )
        return self._reranker.rerank(query, candidates, top_k)
