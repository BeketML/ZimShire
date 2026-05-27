"""Market subagent — live financial data specialist."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.prompts import MARKET_SUBAGENT_PROMPT
from app.modules.agents.mcp_client import get_market_mcp_tools
from app.modules.agents.schemas import SubagentResult
from app.modules.cache.gateways import lookup_market, store_market
from app.services.llm import get_subagent_model

logger = logging.getLogger(__name__)

_MARKET_TOOL_MAP: dict[str, list[str]] = {
    "info": ["get_stock_info"],
    "price": ["get_stock_price"],
    "financials": ["get_income_statement", "get_balance_sheet", "get_cashflow"],
    "history": ["get_stock_history"],
    "news": ["get_stock_news"],
    "earnings": ["get_earnings_estimate"],
    "holders": ["get_institutional_holders"],
    "insider": ["get_insider_transactions"],
}


async def run_market_subagent(
    *,
    sub_query: str,
    tickers: list[str] | None = None,
    data_type: str = "info",
    config: RunnableConfig,
) -> SubagentResult:
    mcp_tools = get_market_mcp_tools()
    fetched_data: dict[str, Any] = {}

    def _make_tool(name: str):
        mcp_fn = mcp_tools.get(name)

        @tool(name=name)
        async def _wrapped(**kwargs) -> Any:
            f"""Call {name} via MCP."""
            if mcp_fn is None:
                return {"error": f"{name} unavailable"}
            try:
                return await mcp_fn.ainvoke(kwargs)
            except Exception as exc:
                logger.warning("%s call failed: %s", name, exc)
                return {"error": str(exc)}

        return _wrapped

    # Build tool list: always include lookup_ticker + the data_type tools
    tool_names = ["lookup_ticker"] + _MARKET_TOOL_MAP.get(data_type, ["get_stock_info"])
    agent_tools = [_make_tool(n) for n in set(tool_names) if n in mcp_tools]

    # Pre-fill cache hits
    if tickers:
        for ticker in tickers:
            cached = await lookup_market(ticker, data_type)
            if cached is not None:
                fetched_data[ticker] = cached

    llm = get_subagent_model(config.get("configurable", {}).get("model"))
    agent = create_react_agent(llm, agent_tools)

    ticker_hint = f" Tickers: {', '.join(tickers)}." if tickers else ""
    try:
        result = await agent.ainvoke(
            {"messages": [SystemMessage(content=MARKET_SUBAGENT_PROMPT), HumanMessage(content=sub_query + ticker_hint)]},
            config=config,
        )
        last = result["messages"][-1]
        formatted = last.content if isinstance(last.content, str) else str(last.content)
    except Exception as exc:
        logger.exception("market_subagent failed: %s", exc)
        formatted = "Market subagent encountered an error."

    # Persist any fetched ticker data to cache
    for ticker, data in fetched_data.items():
        try:
            await store_market(ticker, data_type, data)
        except Exception:
            pass

    return SubagentResult(
        agent_name="market",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts={"tickers": tickers or [], "data_type": data_type},
    )
