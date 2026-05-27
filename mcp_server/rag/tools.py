from __future__ import annotations

import httpx

from mcp_server.core.config import settings
from mcp_server.core.mcp import mcp
from mcp_server.rag.embeddings import DenseEmbedder, LateInteractionEmbedder, SparseEmbedder
from mcp_server.rag.qdrant import QdrantStore

_dense: DenseEmbedder | None = None
_sparse: SparseEmbedder | None = None
_colbert: LateInteractionEmbedder | None = None
_store: QdrantStore | None = None
_http_client: httpx.Client | None = None
_rag_ready = False


def _ensure_rag() -> None:
    global _dense, _sparse, _colbert, _store, _http_client, _rag_ready
    if _rag_ready:
        return
    _http_client = httpx.Client(timeout=30.0)
    _dense = DenseEmbedder(settings, _http_client)
    _sparse = SparseEmbedder(settings.sparse_embedding_model)
    _colbert = LateInteractionEmbedder(settings.reranker_model)
    _store = QdrantStore(settings)
    _rag_ready = True


@mcp.tool(name="search_buffett_letters", tags={"rag"})
def search_buffett_letters(
    query: str,
    top_k: int = 5,
    letter_years_filter: list[int] | None = None,
) -> list[dict]:
    """Search Buffett shareholder letters using hybrid RAG.

    Retrieval: dense (text-embedding-3-small) + sparse (BM25) prefetch with RRF.
    Reranking: ColBERT late interaction multivector (answerdotai/answerai-colbert-small-v1) inside Qdrant.
    """
    _ensure_rag()
    dense_vec = _dense.embed(query)  # type: ignore[union-attr]
    sparse_vec = _sparse.embed_query(query)  # type: ignore[union-attr]
    colbert_vec = _colbert.embed_query(query)  # type: ignore[union-attr]
    return _store.search(  # type: ignore[union-attr]
        dense_vec,
        sparse_vec=sparse_vec,
        colbert_query_vec=colbert_vec,
        top_k=top_k,
        letter_years_filter=letter_years_filter,
    )
