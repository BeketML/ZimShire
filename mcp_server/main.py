"""Entry point for the ZimShire MCP microservice.

Run from repo root (required for package imports):

    python -m mcp_server.main
    python -m mcp_server.main --transport streamable-http --port 8001

stdio (Cursor / Claude Code MCP config):
    python -m mcp_server.main

Do NOT run: cd mcp_server && python main.py  (ModuleNotFoundError: mcp_server)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python mcp_server/main.py` from any cwd
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_server.core.mcp import mcp

# Register tools — decorators run on import
import mcp_server.market.tools  # noqa: F401
import mcp_server.search.tools  # noqa: F401
import mcp_server.rag.tools     # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(description="ZimShire MCP Server")
    parser.add_argument(
        "--transport",
        choices=["sse", "stdio", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio for Cursor/Claude Code)",
    )
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
