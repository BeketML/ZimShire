from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.modules.agents.mcp_client import close_mcp_client, init_mcp_client
from app.modules.agents.service import close_graph, init_graph
from app.modules.users.router import router as users_router
from app.modules.chats.router import router as chats_router
from app.modules.messages.router import router as messages_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mcp_client(settings.mcp_base_url)
    await init_graph()
    yield
    await close_graph()
    await close_mcp_client()


app = FastAPI(title="ZimShire", version="0.1.0", lifespan=lifespan)

app.include_router(users_router)
app.include_router(chats_router)
app.include_router(messages_router)


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_qdrant() -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.qdrant_url.rstrip('/')}/healthz")
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_mcp() -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # FastMCP streamable-http serves at /mcp; any sub-5xx response means up
            resp = await client.get(f"{settings.mcp_base_url.rstrip('/')}/mcp")
            if resp.status_code >= 500:
                return f"error: MCP returned {resp.status_code}"
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


@app.get("/health")
async def health(response: Response) -> dict[str, str]:
    postgres = await _check_postgres()
    qdrant = await _check_qdrant()
    mcp_status = await _check_mcp()
    all_ok = all(s == "ok" for s in (postgres, qdrant, mcp_status))
    if not all_ok:
        response.status_code = 503
    return {
        "status": "ok" if all_ok else "degraded",
        "postgres": postgres,
        "qdrant": qdrant,
        "mcp": mcp_status,
    }
