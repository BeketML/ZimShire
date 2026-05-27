"""RAG subagent — Buffett letters specialist."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.prompts import RAG_SUBAGENT_PROMPT
from app.modules.agents.mcp_registry import format_tool_names_for_prompt, get_agent_tools
from app.modules.agents.schemas import SubagentResult
from app.modules.agents.subagents.base import run_react_subagent


async def run_rag_subagent(
    *,
    sub_query: str,
    years: list[int] | None = None,
    config: RunnableConfig,
) -> SubagentResult:
    tools = get_agent_tools("rag", wrap_market_cache=False)
    tool_block = format_tool_names_for_prompt(tools)
    system_prompt = (
        f"{RAG_SUBAGENT_PROMPT}\n\n## Tools available for this run\n{tool_block}"
    )

    query_with_years = sub_query
    if years:
        query_with_years = f"{sub_query} (focus on letters from years: {years})"

    formatted, artifacts = await run_react_subagent(
        agent="rag",
        system_prompt=system_prompt,
        human_message=query_with_years,
        config=config,
        tools=tools,
        error_label="RAG subagent",
    )

    return SubagentResult(
        agent_name="rag",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts=artifacts,
    )
