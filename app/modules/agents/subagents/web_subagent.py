"""Web subagent — recent news and events specialist."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.prompts import WEB_SUBAGENT_PROMPT
from app.modules.agents.mcp_client import get_web_mcp_tools
from app.modules.agents.schemas import SubagentResult
from app.services.llm import get_subagent_model

logger = logging.getLogger(__name__)

WEB_MAX_RESULTS = 5


async def run_web_subagent(
    *,
    sub_query: str,
    config: RunnableConfig,
) -> SubagentResult:
    web_sources: list[dict] = []
    mcp_tools = get_web_mcp_tools()

    @tool
    async def web_search(query: str, max_results: int = WEB_MAX_RESULTS, region: str = "us", date_filter: str | None = None) -> list[dict]:
        """Search the web for current news and events."""
        tool_fn = mcp_tools.get("web_search")
        if tool_fn is None:
            return []
        try:
            results: Any = await tool_fn.ainvoke({"query": query, "max_results": max_results, "region": region, "date_filter": date_filter})
            if isinstance(results, list):
                web_sources.extend(results)
            return results or []
        except Exception as exc:
            logger.warning("web_search failed: %s", exc)
            return []

    @tool
    async def web_search_news(query: str, max_results: int = WEB_MAX_RESULTS, region: str = "us", date_filter: str | None = None) -> list[dict]:
        """Search for recent news articles."""
        tool_fn = mcp_tools.get("web_search_news")
        if tool_fn is None:
            return []
        try:
            results: Any = await tool_fn.ainvoke({"query": query, "max_results": max_results, "region": region, "date_filter": date_filter})
            if isinstance(results, list):
                web_sources.extend(results)
            return results or []
        except Exception as exc:
            logger.warning("web_search_news failed: %s", exc)
            return []

    llm = get_subagent_model(config.get("configurable", {}).get("model"))
    agent = create_react_agent(llm, [web_search, web_search_news])

    try:
        result = await agent.ainvoke(
            {"messages": [SystemMessage(content=WEB_SUBAGENT_PROMPT), HumanMessage(content=sub_query)]},
            config=config,
        )
        last = result["messages"][-1]
        formatted = last.content if isinstance(last.content, str) else str(last.content)
    except Exception as exc:
        logger.exception("web_subagent failed: %s", exc)
        formatted = "Web subagent encountered an error."

    return SubagentResult(
        agent_name="web",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts={"web_sources": web_sources},
    )
