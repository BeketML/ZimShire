"""LangGraph → MCP via langchain-mcp-adapters (streamable HTTP).

Single MCP server (mcp_server.main) — tools filtered by tag in mcp/registry.
"""
from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.modules.agents.mcp import get_agent_tools, set_all_tools

_client: MultiServerMCPClient | None = None
_tools: dict[str, BaseTool] = {}


async def init_mcp_client(base_url: str = "http://localhost:8001", retries: int = 5) -> None:
    global _client, _tools
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            _client = MultiServerMCPClient(
                {
                    "zimshire": {
                        "url": f"{base_url.rstrip('/')}/mcp",
                        "transport": "streamable_http",
                    }
                }
            )
            tool_list = await _client.get_tools()
            _tools = {t.name: t for t in tool_list}
            set_all_tools(_tools)
            return
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                await asyncio.sleep(2)
    raise RuntimeError(f"MCP client failed to connect to {base_url}") from last_error


def get_mcp_tools() -> dict[str, BaseTool]:
    if not _tools:
        raise RuntimeError("MCP client not initialised — call init_mcp_client() in lifespan")
    return _tools


def get_rag_mcp_tools() -> dict[str, BaseTool]:
    return {t.name: t for t in get_agent_tools("rag", wrap_market_cache=False)}


def get_market_mcp_tools() -> dict[str, BaseTool]:
    return {t.name: t for t in get_agent_tools("market", wrap_market_cache=False)}


def get_web_mcp_tools() -> dict[str, BaseTool]:
    return {t.name: t for t in get_agent_tools("web", wrap_market_cache=False)}


async def close_mcp_client() -> None:
    global _client, _tools
    if _client is not None:
        try:
            await _client.__aexit__(None, None, None)
        except Exception:
            pass
        _client = None
    _tools = {}
    set_all_tools({})
