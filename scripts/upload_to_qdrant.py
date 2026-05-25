"""Upload letter_chunks.json to Qdrant with named dense + sparse (BM42) vectors.

Creates a hybrid-search-ready collection with:
  "dense"  — LiteLLM text-embedding-3-small (1536-dim, cosine)
  "sparse" — fastembed BM42 (Qdrant/bm42-all-minilm-l6-v2-attentions)

Point IDs are deterministic: uuid5(NAMESPACE, "{year}:{chunk_index}"), so
re-running is safe (same chunk overwrites itself, no duplicates).

Usage:
    python scripts/upload_to_qdrant.py
    python scripts/upload_to_qdrant.py --chunks-json data/letter_chunks.json
    python scripts/upload_to_qdrant.py --batch-size 32
    python scripts/upload_to_qdrant.py --dry-run
    python scripts/upload_to_qdrant.py --no-sparse          # dense-only (legacy)
    python scripts/upload_to_qdrant.py --recreate-collection
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastembed import SparseTextEmbedding
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

REPO_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("upload_to_qdrant")


class Settings(BaseSettings):
    litellm_base_url: str
    litellm_api_key: str
    litellm_end_user_id: str
    embedding_model: str = "text-embedding-3-small"
    sparse_embedding_model: str = "Qdrant/bm42-all-minilm-l6-v2-attentions"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "buffett_letters"

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def embeddings_url(self) -> str:
        base = self.litellm_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        return base + "/embeddings"


EMBEDDING_DIM_BY_MODEL: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
MIN_CHUNK_CHARS = 100
DISCLAIMER_PREFIX = "IMPORTANT NOTE The"


def point_id(year: int, chunk_index: int) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{year}:{chunk_index}"))


def load_and_validate(path: Path) -> tuple[list[dict[str, Any]], int]:
    raw_chunks: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_chunks, list):
        raise ValueError(f"Expected JSON array in {path}")

    records: list[dict[str, Any]] = []
    skipped = 0

    for item in raw_chunks:
        text = (item.get("text") or "").strip()

        if len(text) < MIN_CHUNK_CHARS or text.startswith(DISCLAIMER_PREFIX):
            skipped += 1
            continue

        meta = item.get("metadata") or {}
        year = meta.get("year") or meta.get("letter_year")
        chunk_index = meta.get("chunk_index")

        if year is None or chunk_index is None:
            logger.warning("Skipping chunk without year or chunk_index: %s", str(item)[:80])
            skipped += 1
            continue

        records.append({
            "text": text,
            "year": int(year),
            "chunk_index": int(chunk_index),
            "total_chunks": meta.get("total_chunks"),
            "source_file": meta.get("source_file"),
        })

    return records, skipped


async def embed_dense_batch(
    http: httpx.AsyncClient,
    texts: list[str],
    settings: Settings,
    embed_dim: int,
) -> list[list[float]]:
    resp = await http.post(
        settings.embeddings_url,
        headers={
            "Authorization": f"Bearer {settings.litellm_api_key}",
            "x-litellm-end-user-id": settings.litellm_end_user_id,
            "Content-Type": "application/json",
        },
        json={"model": settings.embedding_model, "input": texts},
        timeout=120.0,
    )
    if resp.status_code >= 400:
        logger.error("LiteLLM error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    vectors = [row["embedding"] for row in resp.json()["data"]]

    if vectors and len(vectors[0]) != embed_dim:
        raise ValueError(
            f"API returned dim={len(vectors[0])}, expected {embed_dim} "
            f"for model '{settings.embedding_model}'. Check EMBEDDING_MODEL in .env."
        )
    return vectors


def encode_sparse_batch(
    encoder: SparseTextEmbedding,
    texts: list[str],
) -> list[qm.SparseVector]:
    results = list(encoder.embed(texts))
    return [
        qm.SparseVector(
            indices=r.indices.tolist(),
            values=r.values.tolist(),
        )
        for r in results
    ]


async def ensure_collection(
    qdrant: AsyncQdrantClient,
    collection: str,
    embed_dim: int,
    recreate: bool,
    with_sparse: bool,
) -> None:
    existing = {c.name for c in (await qdrant.get_collections()).collections}

    if collection in existing:
        info = await qdrant.get_collection(collection)
        cfg = info.config.params.vectors

        if isinstance(cfg, dict):
            # Already a named-vector collection
            dense_ok = "dense" in cfg and cfg["dense"].size == embed_dim
            sparse_ok = not with_sparse or (
                info.config.params.sparse_vectors is not None
                and "sparse" in info.config.params.sparse_vectors
            )
            if dense_ok and sparse_ok:
                logger.info(
                    "Collection '%s' already has correct config (named dense=%d%s)",
                    collection, embed_dim, " + sparse" if with_sparse else "",
                )
                return
            if not recreate:
                raise RuntimeError(
                    f"Collection '{collection}' config mismatch. "
                    "Use --recreate-collection to drop and recreate."
                )
            logger.warning("Recreating '%s': vector config mismatch", collection)
        else:
            # Old unnamed dense-only collection
            current_dim = cfg.size
            if current_dim == embed_dim and not with_sparse:
                logger.info("Collection '%s' exists (dim=%d, dense-only)", collection, embed_dim)
                return
            if not recreate:
                raise RuntimeError(
                    f"Collection '{collection}' uses unnamed dense vectors (dim={current_dim}). "
                    "Use --recreate-collection to upgrade to named dense+sparse format."
                )
            logger.warning(
                "Recreating '%s': upgrading from unnamed dense (dim=%d) to named dense+sparse",
                collection, current_dim,
            )

        await qdrant.delete_collection(collection)

    if with_sparse:
        logger.info(
            "Creating collection '%s' (named dense=%d cosine + sparse BM42)",
            collection, embed_dim,
        )
        await qdrant.create_collection(
            collection_name=collection,
            vectors_config={
                "dense": qm.VectorParams(size=embed_dim, distance=qm.Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": qm.SparseVectorParams(),
            },
        )
    else:
        logger.info("Creating collection '%s' (unnamed dense=%d, cosine)", collection, embed_dim)
        await qdrant.create_collection(
            collection_name=collection,
            vectors_config=qm.VectorParams(size=embed_dim, distance=qm.Distance.COSINE),
        )

    await qdrant.create_payload_index(
        collection_name=collection,
        field_name="letter_year",
        field_schema=qm.PayloadSchemaType.INTEGER,
    )


async def run(
    chunks_json: Path,
    batch_size: int,
    dry_run: bool,
    recreate_collection: bool,
    with_sparse: bool,
) -> None:
    settings = Settings()
    embed_dim = EMBEDDING_DIM_BY_MODEL.get(settings.embedding_model, 1536)

    logger.info("LiteLLM  : %s", settings.litellm_base_url)
    logger.info("Model    : %s  dim=%d", settings.embedding_model, embed_dim)
    logger.info("Sparse   : %s", settings.sparse_embedding_model if with_sparse else "disabled")
    logger.info("Qdrant   : %s  collection=%s", settings.qdrant_url, settings.qdrant_collection)
    logger.info("JSON     : %s", chunks_json)

    records, skipped = load_and_validate(chunks_json)
    if not records:
        logger.error("No valid chunks found in %s", chunks_json)
        sys.exit(1)

    years = sorted({r["year"] for r in records})
    logger.info(
        "Loaded %d chunks  skipped=%d  years=%d-%d",
        len(records), skipped, years[0], years[-1],
    )

    if dry_run:
        by_year: dict[int, int] = {}
        for r in records:
            by_year[r["year"]] = by_year.get(r["year"], 0) + 1
        for y in years:
            logger.info("  %d -> %d chunks", y, by_year[y])
        logger.info("Dry run: no writes to Qdrant")
        return

    # Initialise sparse encoder once (downloads model on first run, cached after)
    sparse_encoder: SparseTextEmbedding | None = None
    if with_sparse:
        logger.info("Loading sparse encoder '%s' (downloads on first run)…", settings.sparse_embedding_model)
        sparse_encoder = SparseTextEmbedding(model_name=settings.sparse_embedding_model)
        logger.info("Sparse encoder ready")

    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    await ensure_collection(qdrant, settings.qdrant_collection, embed_dim, recreate_collection, with_sparse)

    total = len(records)
    started = time.time()

    async with httpx.AsyncClient() as http:
        for i in range(0, total, batch_size):
            batch = records[i : i + batch_size]
            texts = [r["text"] for r in batch]

            dense_vectors = await embed_dense_batch(http, texts, settings, embed_dim)

            if with_sparse and sparse_encoder is not None:
                sparse_vectors = encode_sparse_batch(sparse_encoder, texts)
                points = [
                    qm.PointStruct(
                        id=point_id(r["year"], r["chunk_index"]),
                        vector={
                            "dense": dense_vec,
                            "sparse": sparse_vec,
                        },
                        payload={
                            "letter_year": r["year"],
                            "year": r["year"],
                            "chunk_index": r["chunk_index"],
                            "total_chunks": r.get("total_chunks"),
                            "source_file": r.get("source_file"),
                            "text": r["text"],
                        },
                    )
                    for r, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors)
                ]
            else:
                points = [
                    qm.PointStruct(
                        id=point_id(r["year"], r["chunk_index"]),
                        vector=dense_vec,
                        payload={
                            "letter_year": r["year"],
                            "year": r["year"],
                            "chunk_index": r["chunk_index"],
                            "total_chunks": r.get("total_chunks"),
                            "source_file": r.get("source_file"),
                            "text": r["text"],
                        },
                    )
                    for r, dense_vec in zip(batch, dense_vectors)
                ]

            await qdrant.upsert(collection_name=settings.qdrant_collection, points=points)
            logger.info(
                "Upserted %d/%d (batch %d–%d)",
                i + len(batch), total, i, i + len(batch) - 1,
            )

    logger.info(
        "Done: %d points -> '%s'  %.1fs",
        total, settings.qdrant_collection, time.time() - started,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload letter chunks JSON to Qdrant")
    parser.add_argument(
        "--chunks-json",
        type=Path,
        default=REPO_ROOT / "data" / "letter_chunks.json",
        help="Path to letter_chunks.json (default: data/letter_chunks.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Number of chunks per embedding API call (default: 64)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count only — no embedding calls, no Qdrant writes",
    )
    parser.add_argument(
        "--recreate-collection",
        action="store_true",
        help="Drop and recreate the Qdrant collection if config mismatches",
    )
    parser.add_argument(
        "--no-sparse",
        action="store_true",
        help="Skip BM42 sparse vectors (creates dense-only unnamed collection)",
    )
    args = parser.parse_args()

    if not args.chunks_json.is_file():
        parser.error(f"File not found: {args.chunks_json}")

    asyncio.run(
        run(
            chunks_json=args.chunks_json,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            recreate_collection=args.recreate_collection,
            with_sparse=not args.no_sparse,
        )
    )


if __name__ == "__main__":
    main()
