"""Entry point for the ZimShire RAG MCP server (port 8001).

Run from repo root:
    python -m mcp_server.rag_main --transport streamable-http --port 8001
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

# Replace the shared mcp instance BEFORE importing tool modules
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


_mcp_module.mcp = FastMCP("ZimShire RAG", lifespan=_lifespan)

# Now import — tools register to the new instance via `from mcp_server.core.mcp import mcp`
import mcp_server.rag.tools      # noqa: F401, E402
import mcp_server.ui.rag_ui      # noqa: F401, E402

mcp = _mcp_module.mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="ZimShire RAG MCP Server")
    parser.add_argument("--transport", choices=["sse", "stdio", "streamable-http"], default="streamable-http")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
