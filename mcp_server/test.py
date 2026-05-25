"""Quick RAG smoke test. Run from repo root:

    python -m mcp_server.test
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx

from mcp_server.core.config import settings
from mcp_server.rag.embeddings import DenseEmbedder, LateInteractionEmbedder, SparseEmbedder
from mcp_server.rag.qdrant import QdrantStore


def run_search(query: str, top_k: int = 3) -> list[dict]:
    with httpx.Client(timeout=60.0) as http:
        dense = DenseEmbedder(settings, http)
        sparse = SparseEmbedder(settings.sparse_embedding_model)
        colbert = LateInteractionEmbedder(settings.reranker_model)
        store = QdrantStore(settings)

        dense_vec = dense.embed(query)
        sparse_vec = sparse.embed_query(query)
        colbert_vec = colbert.embed_query(query)

        return store.search(
            dense_vec,
            sparse_vec=sparse_vec,
            colbert_query_vec=colbert_vec,
            top_k=top_k,
        )


def main() -> None:
    query = "margin of safety long-term investing"
    hits = run_search(query)
    print(f"Query: {query}\nHits: {len(hits)}\n")
    for i, h in enumerate(hits, 1):
        print(f"--- {i} year={h.get('letter_year')} score={h.get('similarity_score', 0):.4f} ---")
        print(h.get("passage_snippet", "")[:400])
        print()


if __name__ == "__main__":
    main()
