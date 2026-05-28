"""LangGraph lifecycle — checkpointer + store + compiled graph."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_state: dict[str, Any] = {
    "graph": None,
    "store": None,
    "_cm_checkpointer": None,
    "_cm_store": None,
}


def _to_psycopg_dsn(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    return url


async def init_graph(database_url: str) -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from app.modules.agents.builder import build_graph
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

    graph = build_graph(checkpointer, store)

    _state["graph"] = graph
    _state["store"] = store
    _state["_cm_checkpointer"] = cm_checkpointer
    _state["_cm_store"] = cm_store
    logger.info("LangGraph compiled and checkpointer/store ready")


async def close_graph() -> None:
    cm_store = _state.get("_cm_store")
    if cm_store is not None:
        await cm_store.__aexit__(None, None, None)
    cm_checkpointer = _state.get("_cm_checkpointer")
    if cm_checkpointer is not None:
        await cm_checkpointer.__aexit__(None, None, None)
    for key in list(_state.keys()):
        _state[key] = None


def get_graph():
    g = _state["graph"]
    if g is None:
        raise RuntimeError("Graph not initialised — call init_graph() in lifespan")
    return g


def get_store():
    s = _state["store"]
    if s is None:
        raise RuntimeError("Store not initialised — call init_graph() in lifespan")
    return s
