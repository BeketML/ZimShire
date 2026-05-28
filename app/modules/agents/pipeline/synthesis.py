"""Synthesizer node — final answer from collected_context + profile + history."""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.prompts import ORCHESTRATOR_SYNTH_PROMPT
from app.modules.agents.graph.state import ZimShireState
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.services.llm import get_orchestrator_model

logger = logging.getLogger(__name__)

_short_term_svc = ShortTermMemoryService()


def _build_synth_prompt(state: ZimShireState) -> str:
    profile = state.get("user_profile") or {}
    companies = ", ".join(profile.get("tracked_companies", [])) or "(none)"
    interests = ", ".join(profile.get("research_interests", [])) or "(none)"
    history_text = _short_term_svc.format_recent_turns(
        state.get("messages", []), limit_turn_pairs=5
    )

    ctx = state.get("collected_context") or {}
    rag_ctx = ctx.get("rag", "(not used)")
    market_ctx = ctx.get("market", "(not used)")
    web_ctx = ctx.get("web", "(not used)")

    feedback = state.get("feedback_message")
    feedback_section = (
        f"\n\n## Guardrail feedback — rewrite required\n{feedback}" if feedback else ""
    )

    return (
        f"{ORCHESTRATOR_SYNTH_PROMPT}\n\n"
        f"## User profile\n"
        f"- Tracked companies: {companies}\n"
        f"- Research interests: {interests}\n\n"
        f"## Recent conversation (last 5 turns)\n{history_text}\n\n"
        f"## Collected context\n"
        f"### RAG (Buffett letters)\n{rag_ctx}\n\n"
        f"### Market data\n{market_ctx}\n\n"
        f"### Web search\n{web_ctx}"
        + feedback_section
    )


async def synthesizer(state: ZimShireState, config: RunnableConfig) -> dict:
    llm = get_orchestrator_model()

    query = state.get("query") or ""
    system_prompt = _build_synth_prompt(state)

    try:
        resp = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=f"QUERY: {query}")],
            config=config,
        )
        draft = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as exc:
        logger.exception("synthesizer failed: %s", exc)
        draft = (
            "I ran into a problem synthesizing the research. "
            "Please try again or rephrase. "
            "(ZimShire is a research companion, not a financial advisor.)"
        )

    return {
        "draft_answer": draft,
        "messages": [AIMessage(content=draft)],
        "feedback_message": None,
    }
