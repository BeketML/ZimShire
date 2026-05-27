"""Entry point for the ZimShire Web/Search MCP server (port 8003).

Run from repo root:
    python -m mcp_server.web_main --transport streamable-http --port 8003
"""
from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx
from fastmcp import FastMCP

import mcp_server.core.mcp as _mcp_module

_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(app: FastMCP):
    global _http_client
    _http_client = httpx.AsyncClient(timeout=30.0)
    _mcp_module._http_client = _http_client
    yield
    await _http_client.aclose()
    _mcp_module._http_client = None


_mcp_module.mcp = FastMCP("ZimShire Web", lifespan=_lifespan)

import mcp_server.search.tools    # noqa: F401, E402
import mcp_server.ui.search_ui    # noqa: F401, E402

mcp = _mcp_module.mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="ZimShire Web MCP Server")
    parser.add_argument("--transport", choices=["sse", "stdio", "streamable-http"], default="streamable-http")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
