"""LangGraph → MCP via langchain-mcp-adapters (streamable HTTP).

Three separate clients: one per MCP server (rag/market/web).
"""
from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

_rag_client: MultiServerMCPClient | None = None
_market_client: MultiServerMCPClient | None = None
_web_client: MultiServerMCPClient | None = None

_rag_tools: dict[str, BaseTool] = {}
_market_tools: dict[str, BaseTool] = {}
_web_tools: dict[str, BaseTool] = {}


async def _connect(url: str, name: str, retries: int = 5) -> tuple[MultiServerMCPClient, dict[str, BaseTool]]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            client = MultiServerMCPClient(
                {name: {"url": f"{url.rstrip('/')}/mcp", "transport": "streamable_http"}}
            )
            tool_list = await client.get_tools()
            return client, {t.name: t for t in tool_list}
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                await asyncio.sleep(2)
    raise RuntimeError(f"MCP client failed to connect to {url}") from last_error


async def init_mcp_client(
    rag_url: str = "http://localhost:8001",
    market_url: str = "http://localhost:8002",
    web_url: str = "http://localhost:8003",
    retries: int = 5,
) -> None:
    global _rag_client, _market_client, _web_client
    global _rag_tools, _market_tools, _web_tools

    _rag_client, _rag_tools = await _connect(rag_url, "rag", retries)
    _market_client, _market_tools = await _connect(market_url, "market", retries)
    _web_client, _web_tools = await _connect(web_url, "web", retries)


def get_rag_mcp_tools() -> dict[str, BaseTool]:
    if not _rag_tools:
        raise RuntimeError("RAG MCP client not initialised")
    return _rag_tools


def get_market_mcp_tools() -> dict[str, BaseTool]:
    if not _market_tools:
        raise RuntimeError("Market MCP client not initialised")
    return _market_tools


def get_web_mcp_tools() -> dict[str, BaseTool]:
    if not _web_tools:
        raise RuntimeError("Web MCP client not initialised")
    return _web_tools


def get_mcp_tools() -> dict[str, BaseTool]:
    """Return all tools merged — kept for backward compatibility."""
    return {**_rag_tools, **_market_tools, **_web_tools}


async def close_mcp_client() -> None:
    global _rag_client, _market_client, _web_client
    global _rag_tools, _market_tools, _web_tools

    for client in (_rag_client, _market_client, _web_client):
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass

    _rag_client = _market_client = _web_client = None
    _rag_tools = _market_tools = _web_tools = {}
