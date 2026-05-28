"""Build LangGraph checkpointer and store from a Postgres DSN."""
from __future__ import annotations


def _to_psycopg_dsn(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    return url


async def build_checkpointer_and_store(database_url: str):
    """Return (checkpointer, store, cm_checkpointer, cm_store) context managers."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from app.services.embedding import embed_text

    dsn = _to_psycopg_dsn(database_url)

    cm_checkpointer = AsyncPostgresSaver.from_conn_string(dsn)
    checkpointer = await cm_checkpointer.__aenter__()
    await checkpointer.setup()

    async def _embed_for_store(texts: list[str]) -> list[list[float]]:
        return [await embed_text(t) for t in texts]

    cm_store = AsyncPostgresStore.from_conn_string(
        dsn,
        index={"dims": 1536, "embed": _embed_for_store, "fields": ["interest", "company"]},
    )
    store = await cm_store.__aenter__()
    await store.setup()

    return checkpointer, store, cm_checkpointer, cm_store
