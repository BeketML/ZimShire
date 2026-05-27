"""RAG subagent — Buffett letters specialist."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.prompts import RAG_SUBAGENT_PROMPT
from app.modules.agents.mcp_client import get_rag_mcp_tools
from app.modules.agents.schemas import SubagentResult
from app.services.llm import get_subagent_model

logger = logging.getLogger(__name__)

RAG_TOP_K = 5


async def run_rag_subagent(
    *,
    sub_query: str,
    years: list[int] | None = None,
    config: RunnableConfig,
) -> SubagentResult:
    rag_chunks: list[dict] = []
    mcp_tools = get_rag_mcp_tools()

    @tool
    async def search_buffett_letters(query: str, top_k: int = RAG_TOP_K, letter_years_filter: list[int] | None = None) -> list[dict]:
        """Search Warren Buffett annual shareholder letters for investment philosophy and insights."""
        tool_fn = mcp_tools.get("search_buffett_letters")
        if tool_fn is None:
            return []
        hits: list[Any] = await tool_fn.ainvoke(
            {"query": query, "top_k": top_k, "letter_years_filter": letter_years_filter}
        )
        if isinstance(hits, list):
            rag_chunks.extend(hits)
        return hits or []

    llm = get_subagent_model(config.get("configurable", {}).get("model"))
    agent = create_react_agent(llm, [search_buffett_letters])

    query_with_years = sub_query
    if years:
        query_with_years = f"{sub_query} (focus on letters from years: {years})"

    try:
        result = await agent.ainvoke(
            {"messages": [SystemMessage(content=RAG_SUBAGENT_PROMPT), HumanMessage(content=query_with_years)]},
            config=config,
        )
        last = result["messages"][-1]
        formatted = last.content if isinstance(last.content, str) else str(last.content)
    except Exception as exc:
        logger.exception("rag_subagent failed: %s", exc)
        formatted = "RAG subagent encountered an error."

    return SubagentResult(
        agent_name="rag",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts={"rag_chunks": rag_chunks},
    )
