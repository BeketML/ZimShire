"""LangGraph observability — no-op stubs kept for import compatibility."""
from __future__ import annotations

from typing import Callable


def wrap_node(fn: Callable, node_name: str) -> Callable:
    """No-op — the Langfuse CallbackHandler in config['callbacks'] already
    captures every node as a CHAIN span with nested LLM/TOOL children."""
    return fn
