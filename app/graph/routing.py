from __future__ import annotations

from app.graph.state import ZimShireState


def route_after_input(state: ZimShireState) -> str:
    return "blocked" if state.get("input_blocked") else "continue"


def route_after_cache(state: ZimShireState) -> str:
    return "hit" if state.get("cache_hit") else "miss"
