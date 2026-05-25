from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from mcp_server.core.config import Settings


class QdrantStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            check_compatibility=False,
        )
        self._hybrid_capable: bool | None = None

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

    async def _is_hybrid(self) -> bool:
        if self._hybrid_capable is None:
            info = await self._client.get_collection(self._settings.qdrant_collection)
            cfg = info.config.params.vectors
            self._hybrid_capable = isinstance(cfg, dict) and "dense" in cfg
        return self._hybrid_capable

    async def search(
        self,
        dense_vec: list[float],
        *,
        sparse_vec: dict[int, float] | None = None,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[dict]:
        f = self._build_filter(letter_years_filter)

        if sparse_vec and await self._is_hybrid():
            return await self._hybrid_search(dense_vec, sparse_vec, top_k, f)
        return await self._dense_search(dense_vec, top_k, f)

    async def _hybrid_search(
        self,
        dense_vec: list[float],
        sparse_vec: dict[int, float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[dict]:
        qdrant_sparse = qm.SparseVector(
            indices=list(sparse_vec.keys()),
            values=list(sparse_vec.values()),
        )
        prefetch = [
            qm.Prefetch(query=dense_vec, using="dense", limit=top_k * 3, filter=f),
            qm.Prefetch(query=qdrant_sparse, using="sparse", limit=top_k * 3, filter=f),
        ]
        result = await self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            prefetch=prefetch,
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k * 2,
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]

    async def _dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[dict]:
        result = await self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=query_vector,
            limit=top_k,
            query_filter=f,
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]

    async def get_letter_years(self) -> list[int]:
        years: set[int] = set()
        offset = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self._settings.qdrant_collection,
                limit=256,
                offset=offset,
                with_payload=["letter_year"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                year = payload.get("letter_year") or payload.get("year")
                if year is not None:
                    years.add(int(year))
            if offset is None:
                break
        return sorted(years)
