from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastmcp import FastMCP

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialised — lifespan has not started")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastMCP):
    global _http_client
    _http_client = httpx.AsyncClient(timeout=30.0)

    yield

    await _http_client.aclose()
    _http_client = None


mcp = FastMCP("ZimShire", lifespan=lifespan)
