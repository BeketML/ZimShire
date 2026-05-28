"""RAG, market, and web subagent implementations."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.prompts import MARKET_SUBAGENT_PROMPT, RAG_SUBAGENT_PROMPT, WEB_SUBAGENT_PROMPT
from app.modules.agents.graph.schemas import SubagentResult
from app.modules.agents.mcp import format_tool_names_for_prompt, get_agent_tools
from app.modules.agents.pipeline.research.react import run_react_subagent


# ── RAG subagent ─────────────────────────────────────────────────────────────

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


# ── Market subagent ───────────────────────────────────────────────────────────

async def run_market_subagent(
    *,
    sub_query: str,
    tickers: list[str] | None = None,
    data_type: str = "info",
    config: RunnableConfig,
) -> SubagentResult:
    tools = get_agent_tools("market", data_type=data_type, wrap_market_cache=True)
    tool_block = format_tool_names_for_prompt(tools)
    system_prompt = (
        f"{MARKET_SUBAGENT_PROMPT}\n\n## Tools available for this run\n{tool_block}"
    )

    ticker_hint = f" Tickers: {', '.join(tickers)}." if tickers else ""
    formatted, artifacts = await run_react_subagent(
        agent="market",
        system_prompt=system_prompt,
        human_message=sub_query + ticker_hint,
        config=config,
        tools=tools,
        error_label="Market subagent",
    )

    raw = {
        "tickers": tickers or [],
        "data_type": data_type,
        **artifacts,
    }
    return SubagentResult(
        agent_name="market",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts=raw,
    )


# ── Web subagent ──────────────────────────────────────────────────────────────

async def run_web_subagent(
    *,
    sub_query: str,
    config: RunnableConfig,
) -> SubagentResult:
    tools = get_agent_tools("web", wrap_market_cache=False)
    tool_block = format_tool_names_for_prompt(tools)
    system_prompt = (
        f"{WEB_SUBAGENT_PROMPT}\n\n## Tools available for this run\n{tool_block}"
    )

    formatted, artifacts = await run_react_subagent(
        agent="web",
        system_prompt=system_prompt,
        human_message=sub_query,
        config=config,
        tools=tools,
        error_label="Web subagent",
    )

    return SubagentResult(
        agent_name="web",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts=artifacts,
    )
