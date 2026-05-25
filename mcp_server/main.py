"""Entry point for the ZimShire MCP microservice.

SSE / streamable-HTTP (for LangGraph graph nodes and Docker):
    python -m mcp_server.main --transport sse --port 8001
    python -m mcp_server.main --transport streamable-http --port 8001

stdio (for Cursor / Claude Code MCP client):
    python -m mcp_server.main
"""

from __future__ import annotations

import argparse

from mcp_server.server import mcp


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
