"""ReAct orchestrator node with closure-accumulator tool wiring."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from app.core.prompts import SYSTEM_BUFFETT
from app.modules.agents.state import ZimShireState
from app.modules.agents.tools.subagents import build_tools_with_accumulator
from app.services.llm import get_orchestrator_model

logger = logging.getLogger(__name__)


def _build_system_prompt(state: ZimShireState) -> str:
    profile = state.get("user_profile") or {}
    companies = ", ".join(profile.get("tracked_companies", [])) or "(none)"
    interests = ", ".join(profile.get("research_interests", [])) or "(none)"

    history_lines: list[str] = []
    for m in state.get("messages", [])[-20:]:
        role = "User" if getattr(m, "type", None) == "human" else "Assistant"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_lines.append(f"{role}: {content}")

    feedback = state.get("feedback_message")
    feedback_section = (
        f"\n\n## Guardrail feedback — rewrite required\n{feedback}" if feedback else ""
    )

    return (
        f"{SYSTEM_BUFFETT}\n\n"
        f"## User profile (long-term)\n"
        f"- Tracked companies: {companies}\n"
        f"- Research interests: {interests}\n\n"
        f"## Recent conversation\n"
        + "\n".join(history_lines)
        + feedback_section
    )


async def orchestrator(state: ZimShireState, config: RunnableConfig) -> dict:
    existing_context = state.get("collected_context") or {}
    accumulated: dict[str, Any] = {
        "rag_chunks": list(state.get("rag_agent_chunks") or []),
        "web_sources": list(state.get("web_agent_sources") or []),
        "collected_context": dict(existing_context),
    }

    tools = build_tools_with_accumulator(accumulated)
    # Per-chat model override applies to orchestrator; subagents use their own model
    model_override = config.get("configurable", {}).get("model")
    llm = get_orchestrator_model(model_override)

    agent = create_react_agent(llm, tools)
    system_prompt = _build_system_prompt(state)
    inputs = {"messages": [SystemMessage(content=system_prompt), *state.get("messages", [])]}

    try:
        result = await agent.ainvoke(inputs)
    except Exception as exc:
        logger.exception("orchestrator ainvoke failed: %s", exc)
        draft = (
            "I ran into a problem while researching this question. "
            "Please try again or rephrase. "
            "(Note: ZimShire is a research companion, not a financial advisor.)"
        )
        return {
            "draft_answer": draft,
            "rag_invoked": False,
            "messages": [AIMessage(content=draft)],
            "feedback_message": None,
        }

    last = result["messages"][-1]
    draft = last.content if isinstance(last.content, str) else str(last.content)

    return {
        "draft_answer": draft,
        "collected_context": accumulated["collected_context"],
        "rag_agent_chunks": accumulated["rag_chunks"],
        "rag_invoked": len(accumulated["rag_chunks"]) > 0,
        "web_agent_sources": accumulated["web_sources"],
        "messages": [AIMessage(content=draft)],
        "feedback_message": None,
    }
