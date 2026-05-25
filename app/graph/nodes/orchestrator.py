"""ReAct orchestrator with closure-accumulator tool wiring.

The orchestrator calls subagent tools (`rag_agent`, `market_agent`, `web_agent`)
to decide whether to ground in Buffett letters, fetch live market data, or pull
recent web context. Tools write raw outputs into a shared `accumulated` dict via
closure; on return we surface them into LangGraph state in one shot.

Synthesizer uses `ainvoke` (not `astream`) — guardrails downstream need the
complete draft. SSE streaming happens in FastAPI after the graph completes.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from app.core.prompts import SYSTEM_BUFFETT
from app.db.database import AsyncSessionLocal
from app.graph.state import ZimShireState
from app.graph.tools.subagents import build_tools_with_accumulator
from app.services.llm import get_chat_model

logger = logging.getLogger(__name__)


def _build_system_prompt(state: ZimShireState) -> str:
    prefs = state.get("user_preferences") or []
    history_lines: list[str] = []
    for m in state.get("messages", [])[-20:]:
        role = "User" if getattr(m, "type", None) == "human" else "Assistant"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_lines.append(f"{role}: {content}")

    parts = [SYSTEM_BUFFETT, "", "## User long-term interests"]
    parts.append("\n".join(f"- {p}" for p in prefs) if prefs else "(none yet)")
    parts.append("\n## Recent conversation")
    parts.append("\n".join(history_lines) if history_lines else "(none)")
    return "\n".join(parts)


async def orchestrator(state: ZimShireState, config: RunnableConfig) -> dict:
    accumulated: dict[str, Any] = {
        "rag_agent_chunks": [],
        "rag_agent_result": "",
        "web_agent_sources": [],
        "web_agent_result": "",
        "market_agent_result": "",
    }
    tools = build_tools_with_accumulator(accumulated, db_session_factory=AsyncSessionLocal)

    model_name = config.get("configurable", {}).get("model")
    llm = get_chat_model(model_name)
    agent = create_react_agent(llm, tools)

    system_prompt = _build_system_prompt(state)
    inputs = {"messages": [SystemMessage(content=system_prompt), *state.get("messages", [])]}
    try:
        result = await agent.ainvoke(inputs)
    except Exception as e:
        logger.exception("orchestrator ainvoke failed: %s", e)
        draft = (
            "I ran into a problem while researching this question. Please try again, "
            "or rephrase. (Note: I am a research companion, not a financial advisor.)"
        )
        return {
            "draft_answer": draft,
            "rag_invoked": False,
            "messages": [AIMessage(content=draft)],
        }

    last = result["messages"][-1]
    draft = last.content if isinstance(last.content, str) else str(last.content)

    return {
        "draft_answer": draft,
        "rag_agent_chunks": accumulated["rag_agent_chunks"],
        "rag_agent_result": accumulated["rag_agent_result"],
        "rag_invoked": len(accumulated["rag_agent_chunks"]) > 0,
        "web_agent_sources": accumulated["web_agent_sources"],
        "web_agent_result": accumulated["web_agent_result"],
        "market_agent_result": accumulated["market_agent_result"],
        "messages": [AIMessage(content=draft)],
    }
