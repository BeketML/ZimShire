"""Langfuse observability — one trace per user request."""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse = None


def _get_langfuse():
    global _langfuse
    if _langfuse is None and settings.langfuse_public_key:
        try:
            from langfuse import Langfuse

            _langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_base_url or "https://cloud.langfuse.com",
            )
        except Exception as exc:
            logger.warning("Langfuse init failed: %s", exc)
    return _langfuse


def new_trace(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    name: str = "zimshire_turn",
) -> tuple[str, object | None]:
    """Create a Langfuse trace and return (trace_id, handler).

    Returns a UUID-based local trace_id if Langfuse is not configured.
    The handler (langfuse.langchain.CallbackHandler) can be passed to
    LangChain runnables via config["callbacks"].
    """
    lf = _get_langfuse()
    if lf is None:
        import uuid

        return f"local-{uuid.uuid4()}", None

    try:
        from langfuse.langchain import CallbackHandler

        trace = lf.trace(name=name, user_id=user_id, session_id=session_id)
        handler = CallbackHandler(trace_id=trace.id, langfuse_client=lf)
        return trace.id, handler
    except Exception as exc:
        logger.warning("Langfuse trace creation failed: %s", exc)
        import uuid

        return f"local-{uuid.uuid4()}", None


def flush() -> None:
    lf = _get_langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception:
            pass
