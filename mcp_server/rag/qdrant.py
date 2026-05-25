from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from mcp_server.core.config import Settings

logger = logging.getLogger(__name__)


class QdrantStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = QdrantClient(
            url=settings.qdrant_url,
            check_compatibility=False,
        )
        self._collection_mode: str | None = None  # "full" | "hybrid" | "dense"

    def _build_filter(self, letter_years_filter: list[int] | None) -> qm.Filter | None:
        if not letter_years_filter:
            return None
        return qm.Filter(
            must=[
                qm.FieldCondition(
                    key="letter_year",
                    match=qm.MatchAny(any=letter_years_filter),
                )
            ]
        )

    def _to_hit(self, point: qm.ScoredPoint) -> dict:
        payload = point.payload or {}
        text = str(payload.get("text") or "")
        return {
            "letter_year": int(payload.get("letter_year") or payload.get("year") or 0),
            "passage_snippet": text[: self._settings.passage_snippet_max],
            "similarity_score": float(point.score),
            "qdrant_point_id": str(point.id),
            "chunk_index": payload.get("chunk_index"),
            "source_file": payload.get("source_file"),
        }

    def _detect_mode(self) -> str:
        if self._collection_mode is not None:
            return self._collection_mode

        info = self._client.get_collection(self._settings.qdrant_collection)
        cfg = info.config.params.vectors
        sparse_cfg = info.config.params.sparse_vectors or {}

        if isinstance(cfg, dict):
            has_dense = "dense" in cfg
            has_multi = "multi" in cfg
            has_sparse = "sparse" in sparse_cfg
            if has_dense and has_multi and has_sparse:
                self._collection_mode = "full"
            elif has_dense and has_sparse:
                self._collection_mode = "hybrid"
            else:
                self._collection_mode = "dense"
        else:
            self._collection_mode = "dense"

        logger.info("Qdrant collection mode: %s", self._collection_mode)
        return self._collection_mode

    def search(
        self,
        dense_vec: list[float],
        *,
        sparse_vec: dict[int, float] | None = None,
        colbert_query_vec: list[list[float]] | None = None,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[dict]:
        f = self._build_filter(letter_years_filter)
        mode = self._detect_mode()

        if mode == "full" and sparse_vec and colbert_query_vec:
            return self._full_search(dense_vec, sparse_vec, colbert_query_vec, top_k, f)
        if mode in ("full", "hybrid") and sparse_vec:
            logger.warning("Collection has 'multi' but no ColBERT query vec provided — falling back to RRF")
            return self._hybrid_rrf(dense_vec, sparse_vec, top_k, f)
        return self._dense_search(dense_vec, top_k, f)

    def _full_search(
        self,
        dense_vec: list[float],
        sparse_vec: dict[int, float],
        colbert_query_vec: list[list[float]],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[dict]:
        limit = self._settings.hybrid_prefetch_limit
        qdrant_sparse = qm.SparseVector(
            indices=list(sparse_vec.keys()),
            values=list(sparse_vec.values()),
        )
        prefetch = [
            qm.Prefetch(query=dense_vec, using="dense", limit=limit, filter=f),
            qm.Prefetch(query=qdrant_sparse, using="sparse", limit=limit, filter=f),
        ]
        result = self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            prefetch=prefetch,
            query=colbert_query_vec,
            using=self._settings.late_interaction_vector_name,
            limit=top_k,
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]

    def _hybrid_rrf(
        self,
        dense_vec: list[float],
        sparse_vec: dict[int, float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[dict]:
        limit = self._settings.hybrid_prefetch_limit
        qdrant_sparse = qm.SparseVector(
            indices=list(sparse_vec.keys()),
            values=list(sparse_vec.values()),
        )
        prefetch = [
            qm.Prefetch(query=dense_vec, using="dense", limit=limit, filter=f),
            qm.Prefetch(query=qdrant_sparse, using="sparse", limit=limit, filter=f),
        ]
        result = self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            prefetch=prefetch,
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]

    def _dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[dict]:
        result = self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=query_vector,
            using="dense",
            limit=top_k,
            query_filter=f,
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]
