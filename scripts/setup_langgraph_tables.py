"""
Create LangGraph Postgres tables for short-term and long-term memory.

Short-term (checkpointer / thread state):
  - checkpoints
  - checkpoint_blobs
  - checkpoint_writes

Long-term (AsyncPostgresStore):
  - store
  - store_vectors  (requires pgvector)

Uses official LangGraph setup() migrations — do not create these tables via raw SQL.

Docs:
  - docs/db_schema_reference.md (LangGraph Built-in Tables)
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/concepts/memory

Usage (from repo root):
  python scripts/setup_langgraph_tables.py
  python scripts/setup_langgraph_tables.py --database-url "postgresql+asyncpg://zimshire:zimshire@localhost:5432/zimshire"
  python scripts/setup_langgraph_tables.py --verify-only

Requires: Postgres running, pgvector extension (see init.sql).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    # psycopg async requires SelectorEventLoop on Windows (not ProactorEventLoop).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

# Tables created by LangGraph (information_schema check after setup)
CHECKPOINTER_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
STORE_TABLES = ("store", "store_vectors")
ALL_LANGGRAPH_TABLES = CHECKPOINTER_TABLES + STORE_TABLES

VECTOR_DIMS = 1536
STORE_INDEX_FIELDS = ("interest", "company")


def to_psycopg_dsn(database_url: str) -> str:
    """Convert SQLAlchemy async URL to psycopg-compatible postgresql:// DSN."""
    url = database_url.strip()
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
    ):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def resolve_database_url(cli_url: str | None) -> str:
    if cli_url:
        return cli_url
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    try:
        from app.core.config import settings

        return settings.database_url
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "DATABASE_URL not set. Pass --database-url or define it in .env "
            f"(app.core.config failed: {exc})"
        ) from exc


async def _embed_for_store(texts: list[str]) -> list[list[float]]:
    """Embedding fn for store vector index (used at runtime, not during setup)."""
    try:
        from app.services.embedding import embed_text

        out: list[list[float]] = []
        for text in texts:
            out.append(await embed_text(text))
        return out
    except Exception:
        return [[0.0] * VECTOR_DIMS for _ in texts]


async def ensure_vector_extension(dsn: str) -> None:
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")


async def list_public_tables(dsn: str) -> set[str]:
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            rows = await cur.fetchall()
    return {r[0] for r in rows}


async def setup_langgraph(dsn: str) -> None:
    print(f"Target database: {dsn.split('@')[-1] if '@' in dsn else dsn}")

    print("Ensuring pgvector extension...")
    await ensure_vector_extension(dsn)

    print("Setting up short-term memory (AsyncPostgresSaver / checkpointer)...")
    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        await checkpointer.setup()
    print("  OK: checkpoints, checkpoint_blobs, checkpoint_writes")

    print("Setting up long-term memory (AsyncPostgresStore)...")
    async with AsyncPostgresStore.from_conn_string(
        dsn,
        index={
            "dims": VECTOR_DIMS,
            "embed": _embed_for_store,
            "fields": list(STORE_INDEX_FIELDS),
        },
    ) as store:
        await store.setup()
    print("  OK: store, store_vectors")


async def verify_tables(dsn: str) -> None:
    tables = await list_public_tables(dsn)
    missing = [t for t in ALL_LANGGRAPH_TABLES if t not in tables]
    if missing:
        raise RuntimeError(f"Missing LangGraph tables: {', '.join(missing)}")
    print("Verified tables present:")
    for name in ALL_LANGGRAPH_TABLES:
        print(f"  - {name}")


async def async_main(database_url: str, verify_only: bool) -> None:
    dsn = to_psycopg_dsn(database_url)

    if verify_only:
        await verify_tables(dsn)
        print("Verify-only: all LangGraph tables exist.")
        return

    await setup_langgraph(dsn)
    await verify_tables(dsn)
    print("\nLangGraph Postgres setup complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create LangGraph checkpointer + store tables in Postgres.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "SQLAlchemy or psycopg URL. "
            "Default: DATABASE_URL env or app.core.config.settings."
        ),
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only check that LangGraph tables exist (no setup).",
    )
    args = parser.parse_args()

    database_url = resolve_database_url(args.database_url)
    try:
        asyncio.run(async_main(database_url, args.verify_only))
    except psycopg.OperationalError as exc:
        raise SystemExit(
            f"Cannot connect to Postgres: {exc}\n"
            "Start infra: docker compose up -d postgres"
        ) from exc


if __name__ == "__main__":
    main()
