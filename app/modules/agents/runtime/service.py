"""LangGraph lifecycle — init, close, get_graph, get_store."""
from __future__ import annotations

import logging
from typing import Any

from app.modules.agents.runtime.graph_factory import build_checkpointer_and_store

logger = logging.getLogger(__name__)

_state: dict[str, Any] = {
    "graph": None,
    "store": None,
    "_cm_checkpointer": None,
    "_cm_store": None,
}


async def init_graph(database_url: str) -> None:
    from app.modules.agents.graph.builder import build_graph

    checkpointer, store, cm_checkpointer, cm_store = await build_checkpointer_and_store(database_url)
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
