from __future__ import annotations

from app.core.config import settings
from app.modules.agents.graph.state import ZimShireState


def route_after_input(state: ZimShireState) -> str:
    return "blocked" if state.get("input_blocked") else "continue"


def route_after_cache(state: ZimShireState) -> str:
    return "hit" if state.get("cache_hit") else "miss"


def route_after_output_guardrail(state: ZimShireState) -> str:
    if state.get("output_blocked") and state.get("retry_count", 0) < settings.output_guardrail_max_retries:
        return "retry"
    return "proceed"
