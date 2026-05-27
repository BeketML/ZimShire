"""Long-term memory node — loads user profile from LangGraph store."""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.modules.agents.state import ZimShireState

logger = logging.getLogger(__name__)


async def load_memory(state: ZimShireState, config: RunnableConfig, *, store: BaseStore) -> dict:
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return {"user_profile": {}}

    query = state.get("query") or ""
    profile: dict = {"tracked_companies": [], "research_interests": []}

    try:
        namespace = ("users", str(user_id), "interests")
        items = await store.asearch(namespace, query=query, limit=5)
        for it in items:
            val = it.value or {}
            company = val.get("company") or val.get("ticker") or ""
            interest = val.get("interest") or ""
            if company and company not in profile["tracked_companies"]:
                profile["tracked_companies"].append(company)
            if interest and interest not in profile["research_interests"]:
                profile["research_interests"].append(interest)
    except Exception as exc:
        logger.warning("load_memory store.asearch failed: %s", exc)

    return {"user_profile": profile}
