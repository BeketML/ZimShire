"""run_subagents node — runs 0..3 enabled subagents in parallel."""
from __future__ import annotations

import asyncio
import logging

from langchain_core.runnables import RunnableConfig

from app.modules.agents.schemas import OrchestratorPlan, SubagentResult
from app.modules.agents.state import ZimShireState
from app.modules.agents.subagents.market_subagent import run_market_subagent
from app.modules.agents.subagents.rag_subagent import run_rag_subagent
from app.modules.agents.subagents.web_subagent import run_web_subagent

logger = logging.getLogger(__name__)


async def run_subagents(state: ZimShireState, config: RunnableConfig) -> dict:
    plan_dict = state.get("subagent_plan") or {}
    if not plan_dict:
        return {"subagent_results": [], "collected_context": {}, "rag_agent_chunks": [], "web_agent_sources": [], "rag_invoked": False}

    plan = OrchestratorPlan(**plan_dict)
    enabled = [item for item in plan.subagents if item.enabled]

    if not enabled:
        return {"subagent_results": [], "collected_context": {}, "rag_agent_chunks": [], "web_agent_sources": [], "rag_invoked": False}

    async def _run_one(item) -> SubagentResult:
        if item.name == "rag":
            return await run_rag_subagent(sub_query=item.query, years=item.years, config=config)
        elif item.name == "market":
            return await run_market_subagent(
                sub_query=item.query, tickers=item.tickers, data_type=item.data_type or "info", config=config
            )
        else:
            return await run_web_subagent(sub_query=item.query, config=config)

    results: list[SubagentResult] = await asyncio.gather(*(_run_one(item) for item in enabled))

    collected_context: dict = {}
    rag_chunks: list[dict] = []
    web_sources: list[dict] = []

    for result in results:
        collected_context[result.agent_name] = result.formatted_context
        if result.agent_name == "rag":
            rag_chunks.extend(result.raw_artifacts.get("rag_chunks", []))
        elif result.agent_name == "web":
            web_sources.extend(result.raw_artifacts.get("web_sources", []))

    logger.info("run_subagents: completed %d subagents", len(results))

    return {
        "subagent_results": [r.model_dump() for r in results],
        "collected_context": collected_context,
        "rag_agent_chunks": rag_chunks,
        "web_agent_sources": web_sources,
        "rag_invoked": len(rag_chunks) > 0,
    }
