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


def make_callback_handler():
    """Return a LangChain CallbackHandler for the current request.

    Returns None if Langfuse is not configured — callers must handle None.
    """
    if not _check_available():
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception as exc:
        logger.warning("Langfuse CallbackHandler creation failed: %s", exc)
        return None


def trace_context(*, user_id: str, session_id: str, name: str = "zimshire_turn"):
    """Context manager that attaches trace metadata to all LLM calls within it.

    Use as:
        with trace_context(user_id=..., session_id=...):
            await agent.ainvoke(...)
    """
    if not _check_available():
        from contextlib import nullcontext
        return nullcontext()
    try:
        from langfuse import propagate_attributes
        return propagate_attributes(
            trace_name=name,
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning("Langfuse propagate_attributes failed: %s", exc)
        from contextlib import nullcontext
        return nullcontext()


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
