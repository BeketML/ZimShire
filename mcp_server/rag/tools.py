from __future__ import annotations

from mcp_server.core.config import settings
from mcp_server.core.mcp import get_http_client, mcp
from mcp_server.rag.embeddings import DenseEmbedder, Reranker, SparseEmbedder
from mcp_server.rag.qdrant import QdrantStore

_dense: DenseEmbedder | None = None
_sparse: SparseEmbedder | None = None
_reranker: Reranker | None = None
_store: QdrantStore | None = None


def _ensure_rag() -> None:
    """Lazy-init RAG stack on first use (avoids blocking server startup)."""
    global _dense, _sparse, _reranker, _store
    if _dense is not None:
        return
    _dense = DenseEmbedder(settings, get_http_client())
    _sparse = SparseEmbedder(settings.sparse_embedding_model)
    _reranker = Reranker(settings.reranker_model)
    _store = QdrantStore(settings)


@mcp.tool(name="search_buffett_letters", tags={"rag", "research", "buffett"})
async def search_buffett_letters(
    query: str,
    top_k: int = 5,
    letter_years_filter: list[int] | None = None,
) -> list[dict]:
    """Search Buffett shareholder letters using hybrid RAG (dense + sparse vectors, RRF fusion, cross-encoder reranker)."""
    _ensure_rag()

    dense_vec = await _dense.embed(query)  # type: ignore[union-attr]
    sparse_vec = _sparse.embed(query)  # type: ignore[union-attr]
    candidates = await _store.search(  # type: ignore[union-attr]
        dense_vec,
        sparse_vec=sparse_vec,
        top_k=top_k,
        letter_years_filter=letter_years_filter,
    )
    return _reranker.rerank(query, candidates, top_k)  # type: ignore[union-attr]
