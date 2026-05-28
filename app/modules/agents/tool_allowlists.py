"""Static allowlist data for MCP tool filtering — no logic, no imports."""
from __future__ import annotations

from typing import Literal

AgentName = Literal["rag", "market", "web"]

AGENT_PRIMARY_TAG: dict[AgentName, str] = {
    "rag": "rag",
    "market": "market",
    "web": "web",
}

EXCLUDE_TAGS = frozenset({"ui"})

AGENT_TOOL_ALLOWLIST: dict[AgentName, frozenset[str]] = {
    "rag": frozenset({"search_buffett_letters"}),
    "market": frozenset(
        {
            "lookup_ticker",
            "get_stock_info",
            "get_stock_price",
            "get_stock_history",
            "get_income_statement",
            "get_balance_sheet",
            "get_cashflow",
            "get_earnings_estimate",
            "get_institutional_holders",
            "get_insider_transactions",
            "get_stock_news",
        }
    ),
    "web": frozenset({"web_search", "web_search_news", "web_search_knowledge"}),
}

MARKET_TOOL_MAP: dict[str, list[str]] = {
    "info": ["get_stock_info"],
    "price": ["get_stock_price"],
    "financials": ["get_income_statement", "get_balance_sheet", "get_cashflow"],
    "history": ["get_stock_history"],
    "news": ["get_stock_news"],
    "earnings": ["get_earnings_estimate"],
    "holders": ["get_institutional_holders"],
    "insider": ["get_insider_transactions"],
}
