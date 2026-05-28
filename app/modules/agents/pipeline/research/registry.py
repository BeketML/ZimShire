"""Strategy registry for subagent dispatch — add new subagents here only."""
from __future__ import annotations

from typing import Protocol

from langchain_core.runnables import RunnableConfig

from app.modules.agents.graph.schemas import SubagentPlanItem, SubagentResult


class SubagentStrategy(Protocol):
    async def run(self, item: SubagentPlanItem, config: RunnableConfig) -> SubagentResult: ...


class _RAGStrategy:
    async def run(self, item: SubagentPlanItem, config: RunnableConfig) -> SubagentResult:
        from app.modules.agents.pipeline.research.subagents import run_rag_subagent

        return await run_rag_subagent(sub_query=item.query, years=item.years, config=config)


class _MarketStrategy:
    async def run(self, item: SubagentPlanItem, config: RunnableConfig) -> SubagentResult:
        from app.modules.agents.pipeline.research.subagents import run_market_subagent

        return await run_market_subagent(
            sub_query=item.query,
            tickers=item.tickers,
            data_type=item.data_type or "info",
            config=config,
        )


class _WebStrategy:
    async def run(self, item: SubagentPlanItem, config: RunnableConfig) -> SubagentResult:
        from app.modules.agents.pipeline.research.subagents import run_web_subagent

        return await run_web_subagent(sub_query=item.query, config=config)


SUBAGENT_REGISTRY: dict[str, SubagentStrategy] = {
    "rag": _RAGStrategy(),
    "market": _MarketStrategy(),
    "web": _WebStrategy(),
}
