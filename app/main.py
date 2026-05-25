from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.graph.mcp_client import close_mcp_client, init_mcp_client
from app.routers import chats, messages, users
from app.services.graph_service import close_graph, init_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mcp_client(settings.mcp_base_url)
    await init_graph()
    yield
    await close_graph()
    await close_mcp_client()


app = FastAPI(title="ZimShire", version="0.1.0", lifespan=lifespan)

app.include_router(users.router)
app.include_router(chats.router)
app.include_router(messages.router)


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
            resp = await client.get(f"{settings.mcp_base_url.rstrip('/')}/health")
            if resp.status_code == 404:
                resp = await client.get(settings.mcp_base_url.rstrip("/"))
            resp.raise_for_status()
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
