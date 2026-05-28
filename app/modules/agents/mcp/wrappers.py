"""Tool wrappers — cache-first market wrapper + Langfuse tracing wrapper."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from app.modules.agents.mcp.allowlists import MARKET_TOOL_MAP, AgentName
from app.modules.agents.mcp.registry import get_all_tools, matches_agent
from app.modules.cache.gateways import lookup_market, store_market
from app.services.langfuse_service import observe_tool_call

logger = logging.getLogger(__name__)


def _filter_market_by_data_type(names: set[str], data_type: str | None) -> set[str]:
    if not data_type:
        return names
    allowed = set(MARKET_TOOL_MAP.get(data_type, ["get_stock_info"]))
    allowed.add("lookup_ticker")
    return names & allowed


def _wrap_market_tool(tool: BaseTool, data_type: str) -> BaseTool:
    async def _cached_invoke(**kwargs: Any) -> Any:
        ticker = kwargs.get("ticker")
        if isinstance(ticker, str) and ticker:
            cached = await lookup_market(ticker, data_type)
            if cached is not None:
                return cached
        result = await tool.ainvoke(kwargs)
        parsed = result
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        elif isinstance(result, list):
            for block in result:
                if isinstance(block, dict) and block.get("type") == "text":
                    try:
                        parsed = json.loads(block["text"])
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break
        if isinstance(ticker, str) and ticker and isinstance(parsed, dict) and parsed:
            try:
                await store_market(ticker, data_type, parsed)
                logger.info("store_market(%s, %s) OK", ticker, data_type)
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
    matched = [t for name, t in tools.items() if matches_agent(name, t, agent)]

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
