"""Market subagent — live financial data specialist."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.prompts import MARKET_SUBAGENT_PROMPT
from app.modules.agents.mcp_registry import format_tool_names_for_prompt, get_agent_tools
from app.modules.agents.schemas import SubagentResult
from app.modules.agents.subagents.base import run_react_subagent


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
