from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from mcp_server.core.config import Settings
from mcp_server.services.protocols import SearchHit, VectorStoreInterface


class QdrantVectorStore(VectorStoreInterface):
    def __init__(
        self,
        settings: Settings,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or AsyncQdrantClient(
            url=settings.qdrant_url,
            check_compatibility=False,
        )
        self._hybrid_capable: bool | None = None  # cached after first collection check

    def _build_filter(
        self,
        letter_years_filter: list[int] | None,
    ) -> qm.Filter | None:
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

    def _to_hit(self, point: qm.ScoredPoint) -> SearchHit:
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

    async def _has_named_vectors(self) -> bool:
        if self._hybrid_capable is None:
            info = await self._client.get_collection(self._settings.qdrant_collection)
            cfg = info.config.params.vectors
            # Named-vector collections expose a dict; unnamed expose a single VectorParams
            self._hybrid_capable = isinstance(cfg, dict) and "dense" in cfg
        return self._hybrid_capable

    async def search(
        self,
        query_vector: list[float],
        *,
        sparse_vector: dict[int, float] | None = None,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[SearchHit]:
        f = self._build_filter(letter_years_filter)

        if sparse_vector and await self._has_named_vectors():
            return await self._hybrid_search(query_vector, sparse_vector, top_k, f)
        return await self._dense_search(query_vector, top_k, f)

    async def _hybrid_search(
        self,
        dense_vec: list[float],
        sparse_vec: dict[int, float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[SearchHit]:
        qdrant_sparse = qm.SparseVector(
            indices=list(sparse_vec.keys()),
            values=list(sparse_vec.values()),
        )
        prefetch = [
            qm.Prefetch(
                query=dense_vec,
                using="dense",
                limit=top_k * 3,
                filter=f,
            ),
            qm.Prefetch(
                query=qdrant_sparse,
                using="sparse",
                limit=top_k * 3,
                filter=f,
            ),
        ]
        result = await self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            prefetch=prefetch,
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k * 2,  # over-fetch for cross-encoder reranker
            with_payload=True,
        )
        return [self._to_hit(p) for p in result.points]

    async def _dense_search(
        self,
        query_vector: list[float],
        top_k: int,
        f: qm.Filter | None,
    ) -> list[SearchHit]:
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
