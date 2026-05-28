from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("app.modules.agents.mcp_registry").setLevel(logging.DEBUG)


_configure_logging()
from app.api.health import check_mcp, check_postgres, check_qdrant
from app.modules.agents import close_graph, close_mcp_client, get_graph, get_registry, get_store, init_graph, init_mcp_client
from app.modules.chat_history.router import router as chat_history_router
from app.modules.chats.router import router as chats_router
from app.modules.inspect.router import router as inspect_router
from app.modules.messages.router import router as messages_router
from app.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mcp_client(base_url=settings.mcp_base_url)
    await init_graph(database_url=settings.database_url)
    # Expose lifespan-scoped singletons on app.state for deps injection
    app.state.graph = get_graph()
    app.state.store = get_store()
    app.state.tool_registry = get_registry()
    yield
    await close_graph()
    await close_mcp_client()


app = FastAPI(title="ZimShire", version="0.1.0", lifespan=lifespan)

app.include_router(users_router)
app.include_router(chats_router)
app.include_router(messages_router)
app.include_router(chat_history_router)
app.include_router(inspect_router)


@app.get("/health")
async def health(response: Response) -> dict[str, str]:
    postgres = await check_postgres()
    qdrant = await check_qdrant()
    mcp_status = await check_mcp()
    all_ok = all(s == "ok" for s in (postgres, qdrant, mcp_status))
    if not all_ok:
        response.status_code = 503
    return {
        "status": "ok" if all_ok else "degraded",
        "postgres": postgres,
        "qdrant": qdrant,
        "mcp": mcp_status,
    }
