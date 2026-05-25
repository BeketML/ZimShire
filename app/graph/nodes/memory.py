"""Long-term user memory: pull tracked-company interests from the LangGraph store.

Short-term history lives in `state['messages']` (restored by the checkpointer).
We do not duplicate it as a string list; the orchestrator's system prompt formats
the last few turns inline.
"""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.graph.state import ZimShireState

logger = logging.getLogger(__name__)


async def load_memory(state: ZimShireState, config: RunnableConfig, *, store: BaseStore) -> dict:
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return {"user_preferences": []}

    query = state.get("query") or ""
    prefs: list[str] = []
    try:
        namespace = ("users", str(user_id), "interests")
        items = await store.asearch(namespace, query=query, limit=5)
        for it in items:
            val = it.value or {}
            company = val.get("company") or val.get("ticker") or ""
            interest = val.get("interest") or ""
            label = f"{company}: {interest}" if company else interest
            if label:
                prefs.append(label)
    except Exception as e:
        logger.warning("load_memory store.asearch failed: %s", e)

    return {"user_preferences": prefs}
