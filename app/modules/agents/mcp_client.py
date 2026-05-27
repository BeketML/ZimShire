"""LangGraph → MCP via langchain-mcp-adapters (streamable HTTP)."""
from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

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


async def close_mcp_client() -> None:
    global _client, _tools
    if _client is not None:
        try:
            await _client.__aexit__(None, None, None)
        except Exception:
            pass
        _client = None
    _tools = {}
