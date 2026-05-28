"""Health check helpers — one async function per backend."""
from __future__ import annotations

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine


async def check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def check_qdrant() -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.qdrant_url.rstrip('/')}/healthz")
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def check_mcp() -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.mcp_base_url.rstrip('/')}/mcp")
            if resp.status_code >= 500:
                return f"error: MCP returned {resp.status_code}"
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
