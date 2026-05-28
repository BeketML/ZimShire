"""Orchestrator planner node — structured output, no tool calls."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.exceptions import AgentPlanError
from app.core.prompts import ORCHESTRATOR_PLANNER_PROMPT
from app.modules.agents.graph.schemas import OrchestratorPlan
from app.modules.agents.graph.state import ZimShireState
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.services.llm import get_orchestrator_model

logger = logging.getLogger(__name__)

_short_term_svc = ShortTermMemoryService()


def _build_planner_user_message(state: ZimShireState) -> str:
    profile = state.get("user_profile") or {}
    companies = ", ".join(profile.get("tracked_companies", [])) or "(none)"
    interests = ", ".join(profile.get("research_interests", [])) or "(none)"
    history_text = _short_term_svc.format_recent_turns(
        state.get("messages", []), limit_turn_pairs=5
    )
    query = state.get("query") or ""

    return (
        f"USER QUERY: {query}\n\n"
        f"USER PROFILE:\n"
        f"- Tracked companies: {companies}\n"
        f"- Research interests: {interests}\n\n"
        f"RECENT CONVERSATION (last 5 turns):\n{history_text}"
    )


async def orchestrator(state: ZimShireState, config: RunnableConfig) -> dict:
    llm = get_orchestrator_model()

    user_msg = _build_planner_user_message(state)

    # Use structured output for deterministic plan
    structured_llm = llm.with_structured_output(OrchestratorPlan)
    try:
        plan: OrchestratorPlan = await structured_llm.ainvoke(
            [SystemMessage(content=ORCHESTRATOR_PLANNER_PROMPT), HumanMessage(content=user_msg)]
        )
    except Exception as exc:
        logger.error("orchestrator planner failed: %s", exc, exc_info=True)
        raise AgentPlanError(f"orchestrator planner failed: {exc}") from exc

    enabled = [s for s in plan.subagents if s.enabled]
    logger.info(
        "orchestrator plan: enabled=%s direct=%s",
        [s.name for s in enabled],
        plan.direct_answer_possible,
    )

    return {
        "subagent_plan": plan.model_dump(),
        "direct_answer_possible": plan.direct_answer_possible,
    }
