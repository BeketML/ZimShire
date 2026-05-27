"""load_context node — thin wrapper over LongTermMemoryService."""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.modules.agents.state import ZimShireState
from app.modules.chat_history.long_term.service import LongTermMemoryService

logger = logging.getLogger(__name__)


async def load_memory(state: ZimShireState, config: RunnableConfig, *, store: BaseStore) -> dict:
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return {"user_profile": {}}

    query = state.get("query") or ""
    svc = LongTermMemoryService(store)
    profile = await svc.load_profile(str(user_id), query)
    return {"user_profile": profile.model_dump()}
