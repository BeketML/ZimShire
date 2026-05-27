"""Subagent tools for the ReAct orchestrator.

Each tool calls MCP via get_mcp_tools() and writes results into a shared
`accumulated` dict (closure). The orchestrator node returns the dict into
LangGraph state in one shot.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.modules.agents.mcp_client import get_mcp_tools
from app.modules.cache.gateways import lookup_market, store_market

logger = logging.getLogger(__name__)

RAG_TOP_K = 5
WEB_MAX_RESULTS = 5

# MCP tool names that map to each data_type
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


def build_tools_with_accumulator(
    accumulated: dict[str, Any],
) -> list[BaseTool]:
    """Return [rag_agent, market_agent, web_agent] wired to the shared accumulator."""
    mcp_tools = get_mcp_tools()

    @tool
    async def rag_agent(query: str, years: list[int] | None = None) -> str:
        """Search Warren Buffett shareholder letters for investment philosophy,
        moats, intrinsic value, margin of safety, and management quality.

        Args:
            query: Natural-language research question.
            years: Optional list of letter years to filter on, e.g. [1988, 1989].
        """
        tool_fn = mcp_tools.get("search_buffett_letters")
        if tool_fn is None:
            return "search_buffett_letters tool unavailable."
        try:
            hits: list[dict] = await tool_fn.ainvoke(
                {"query": query, "top_k": RAG_TOP_K, "letter_years_filter": years}
            )
        except Exception as exc:
            logger.exception("rag_agent MCP call failed: %s", exc)
            hits = []

        if hits:
            accumulated["rag_chunks"].extend(hits)
            formatted = "\n\n".join(
                f"[{h.get('letter_year')}] score={h.get('similarity_score', 0):.3f}\n"
                f"{h.get('passage_snippet', '')}"
                for h in hits
            )
        else:
            formatted = "No relevant Buffett letter passages found."

        accumulated["collected_context"]["rag"] = formatted
        return formatted

    @tool
    async def market_agent(tickers: list[str], data_type: str = "info") -> str:
        """Get live market data for one or more ticker symbols.

        Args:
            tickers: Ticker symbols, e.g. ["AAPL", "KO"]. Call lookup_ticker first if uncertain.
            data_type: One of "info" (default), "price", "financials", "history",
                       "news", "earnings", "holders", "insider".
        """
        if not tickers:
            return "No tickers provided."

        tool_names = _MARKET_TOOL_MAP.get(data_type, ["get_stock_info"])
        result: dict[str, Any] = {}

        for ticker in tickers:
            # Cache-first
            cached = await lookup_market(ticker, data_type)
            if cached is not None:
                result[ticker] = cached
                continue

            ticker_data: dict[str, Any] = {}
            for tool_name in tool_names:
                tool_fn = mcp_tools.get(tool_name)
                if tool_fn is None:
                    logger.warning("MCP tool %s unavailable", tool_name)
                    continue
                try:
                    payload = await tool_fn.ainvoke({"ticker": ticker})
                    if isinstance(payload, dict):
                        ticker_data.update(payload)
                    else:
                        ticker_data[tool_name] = payload
                except Exception as exc:
                    logger.exception("market_agent %s(%s) failed: %s", tool_name, ticker, exc)

            if ticker_data:
                await store_market(ticker, data_type, ticker_data)
            result[ticker] = ticker_data

        text = json.dumps(result, default=str)[:6000]
        accumulated["collected_context"]["market"] = text
        return text

    @tool
    async def web_agent(query: str) -> str:
        """Search the web for current news, events, and facts not in Buffett letters.

        Args:
            query: Search query string.
        """
        tool_fn = mcp_tools.get("web_search")
        if tool_fn is None:
            return "web_search tool unavailable."
        try:
            results: list[dict] = await tool_fn.ainvoke(
                {"query": query, "max_results": WEB_MAX_RESULTS}
            )
        except Exception as exc:
            logger.exception("web_agent MCP call failed: %s", exc)
            results = []

        accumulated["web_sources"].extend(results)
        if results:
            formatted = "\n".join(
                f"- {r.get('title', '')[:120]}: {r.get('snippet', '')[:200]}"
                for r in results
            )
        else:
            formatted = "No web results found."

        accumulated["collected_context"]["web"] = formatted
        return formatted

    return [rag_agent, market_agent, web_agent]
