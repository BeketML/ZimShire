"""Langfuse v4 observability — one trace per user request.

Usage:
    handler = make_callback_handler()
    with trace_context(user_id=..., session_id=..., name=...):
        result = await agent.ainvoke(..., config={"callbacks": [handler]})
    trace_id = handler.last_trace_id or f"local-{uuid4()}"
    flush()
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

_LANGFUSE_AVAILABLE: bool | None = None


def _check_available() -> bool:
    global _LANGFUSE_AVAILABLE
    if _LANGFUSE_AVAILABLE is None:
        try:
            import os
            from langfuse import get_client  # noqa: F401
            pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
            _LANGFUSE_AVAILABLE = bool(pk and sk)
        except Exception:
            _LANGFUSE_AVAILABLE = False
    return _LANGFUSE_AVAILABLE


def make_callback_handler(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_name: str = "zimshire_turn",
):
    """Return a LangChain CallbackHandler for the current request.

    In Langfuse v4, user/session metadata is passed via TraceContext on the
    handler constructor. The same metadata is also set in config["metadata"]
    by the caller (belt-and-suspenders for LangGraph compatibility).
    Returns None if Langfuse is not configured.
    """
    if not _check_available():
        return None
    try:
        from langfuse.langchain import CallbackHandler
        from langfuse.types import TraceContext
        tc: TraceContext = {}
        if user_id:
            tc["user_id"] = user_id
        if session_id:
            tc["session_id"] = session_id
        if trace_name:
            tc["trace_name"] = trace_name
        return CallbackHandler(trace_context=tc if tc else None)
    except Exception as exc:
        logger.warning("Langfuse CallbackHandler creation failed: %s", exc)
        return None


def get_trace_id(handler) -> str:
    """Extract trace_id from handler after a run, or return a local fallback UUID."""
    if handler is not None:
        try:
            tid = handler.last_trace_id
            if tid:
                return tid
        except Exception:
            pass
    return f"local-{uuid.uuid4()}"


def flush() -> None:
    """Flush pending Langfuse events. Call after each SSE turn completes."""
    if not _check_available():
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception as exc:
        logger.warning("Langfuse flush failed: %s", exc)


def sanitize_state(state: dict) -> dict:
    """Truncate large list fields so the Langfuse payload stays small."""
    out = {}
    for k, v in state.items():
        if k == "messages":
            out[k] = f"[{len(v)} messages]" if isinstance(v, list) else v
        elif k == "rag_agent_chunks":
            out[k] = f"[{len(v)} chunks]" if isinstance(v, list) else v
        elif isinstance(v, str) and len(v) > 800:
            out[k] = v[:800] + "…"
        else:
            out[k] = v
    return out


# Keep for backward compat (called by guardrail nodes)
def new_trace(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    name: str = "zimshire_turn",
) -> tuple[str, object | None]:
    """Legacy helper — returns (placeholder_id, handler).

    The real trace_id is only known after the run; use get_trace_id(handler).
    """
    handler = make_callback_handler()
    return f"local-{uuid.uuid4()}", handler
