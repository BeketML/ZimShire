"""MCP tool registry — filter tools by FastMCP tags for each subagent."""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool

from app.modules.cache.gateways import lookup_market, store_market
from app.services.langfuse_service import observe_tool_call

logger = logging.getLogger(__name__)

AgentName = Literal["rag", "market", "web"]

AGENT_PRIMARY_TAG: dict[AgentName, str] = {
    "rag": "rag",
    "market": "market",
    "web": "web",
}

EXCLUDE_TAGS = frozenset({"ui"})

# Fallback when MCP tags are not present in BaseTool.metadata (HTTP transport).
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

_all_tools: dict[str, BaseTool] = {}


def set_all_tools(tools: dict[str, BaseTool]) -> None:
    global _all_tools
    _all_tools = dict(tools)
    tag_index = {name: sorted(tool_tags(t)) for name, t in tools.items()}
    logger.info("MCP registry loaded %d tools: %s", len(tools), tag_index)


def get_all_tools() -> dict[str, BaseTool]:
    if not _all_tools:
        raise RuntimeError("MCP tools not initialised — call init_mcp_client() first")
    return _all_tools


def tool_tags(tool: BaseTool) -> set[str]:
    tags: set[str] = set()
    meta = getattr(tool, "metadata", None) or {}
    if isinstance(meta, dict):
        for key in ("tags", "tag"):
            val = meta.get(key)
            if isinstance(val, (list, tuple, set, frozenset)):
                tags.update(str(t) for t in val)
            elif isinstance(val, str):
                tags.add(val)
        nested = meta.get("_meta")
        if isinstance(nested, dict):
            for key in ("tags", "tag", "fastmcp_tags"):
                val = nested.get(key)
                if isinstance(val, (list, tuple, set, frozenset)):
                    tags.update(str(t) for t in val)
                elif isinstance(val, str):
                    tags.add(val)
    return tags


def _is_ui_tool(name: str, tool: BaseTool) -> bool:
    if name.endswith("_ui"):
        return True
    return "ui" in tool_tags(tool)


def _matches_agent(name: str, tool: BaseTool, agent: AgentName) -> bool:
    if _is_ui_tool(name, tool):
        return False
    tags = tool_tags(tool)
    primary = AGENT_PRIMARY_TAG[agent]
    if tags:
        return primary in tags and not (tags & EXCLUDE_TAGS)
    return name in AGENT_TOOL_ALLOWLIST[agent]


def _filter_market_by_data_type(names: set[str], data_type: str | None) -> set[str]:
    if not data_type:
        return names
    allowed = set(MARKET_TOOL_MAP.get(data_type, ["get_stock_info"]))
    allowed.add("lookup_ticker")
    return names & allowed


def _wrap_market_tool(tool: BaseTool, data_type: str) -> BaseTool:
    """Cache-first wrapper for market MCP tools keyed by ticker."""

    async def _cached_invoke(**kwargs: Any) -> Any:
        ticker = kwargs.get("ticker")
        if isinstance(ticker, str) and ticker:
            cached = await lookup_market(ticker, data_type)
            if cached is not None:
                return cached
        result = await tool.ainvoke(kwargs)
        if isinstance(ticker, str) and ticker and isinstance(result, dict) and result:
            try:
                await store_market(ticker, data_type, result)
            except Exception as exc:
                logger.warning("store_market(%s) failed: %s", ticker, exc)
        return result

    if isinstance(tool, StructuredTool):
        return StructuredTool(
            name=tool.name,
            description=tool.description or "",
            args_schema=tool.args_schema,
            coroutine=_cached_invoke,
            metadata=getattr(tool, "metadata", None),
        )
    return tool


def _wrap_traced_tool(tool: BaseTool) -> BaseTool:
    """Emit a Langfuse event for each MCP tool invocation."""
    tool_name = tool.name

    async def _traced_invoke(**kwargs: Any) -> Any:
        result = await tool.ainvoke(kwargs)
        observe_tool_call(tool_name, kwargs, result)
        return result

    if isinstance(tool, StructuredTool):
        return StructuredTool(
            name=tool.name,
            description=tool.description or "",
            args_schema=tool.args_schema,
            coroutine=_traced_invoke,
            metadata=getattr(tool, "metadata", None),
        )
    return tool


def get_agent_tools(
    agent: AgentName,
    *,
    data_type: str | None = None,
    wrap_market_cache: bool = True,
) -> list[BaseTool]:
    tools = get_all_tools()
    matched = [t for name, t in tools.items() if _matches_agent(name, t, agent)]

    if agent == "market":
        allowed_names = _filter_market_by_data_type({t.name for t in matched}, data_type)
        matched = [t for t in matched if t.name in allowed_names]
        if wrap_market_cache and data_type:
            dt = data_type
            matched = [_wrap_market_tool(t, dt) for t in matched]

    if not matched:
        logger.warning("No MCP tools matched agent=%s data_type=%s", agent, data_type)

    return [_wrap_traced_tool(t) for t in matched]


def format_tool_names_for_prompt(tools: list[BaseTool]) -> str:
    lines = []
    for t in tools:
        desc = (t.description or "").split("\n")[0].strip()
        lines.append(f"- {t.name}: {desc}" if desc else f"- {t.name}")
    return "\n".join(lines) if lines else "(no tools available)"
