"""Wrap LangGraph node functions to emit Langfuse state spans."""
from __future__ import annotations

from functools import wraps
from typing import Callable

from app.services.langfuse_service import observe_graph_state


def wrap_node(fn: Callable, node_name: str) -> Callable:
    """Return an async wrapper that emits a Langfuse span after the node runs.

    Uses **kwargs (not *args) so functools.partial()-wrapped nodes (e.g. load_memory)
    correctly forward keyword arguments like `store` through the wrapper.
    """
    @wraps(fn)
    async def wrapped(state, config, **kwargs):
        result = await fn(state, config, **kwargs)
        merged = {**state, **(result or {})}
        observe_graph_state(node_name, merged)
        return result

    return wrapped
