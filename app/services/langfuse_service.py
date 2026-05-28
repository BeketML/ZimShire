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

    Passes user_id / session_id directly so Langfuse links the trace to the
    correct user and chat without a separate propagate_attributes context.
    Returns None if Langfuse is not configured.
    """
    if not _check_available():
        return None
    try:
        from langfuse.langchain import CallbackHandler
        kwargs: dict = {}
        if user_id:
            kwargs["user_id"] = user_id
        if session_id:
            kwargs["session_id"] = session_id
        if trace_name:
            kwargs["trace_name"] = trace_name
        return CallbackHandler(**kwargs)
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


def observe_graph_state(node_name: str, state: dict) -> None:
    """Emit a Langfuse score/event capturing state after a node runs."""
    if not _check_available():
        return
    try:
        from langfuse import get_client
        client = get_client()
        payload = sanitize_state(state)
        client.create_event(
            name=f"node:{node_name}",
            input=payload,
        )
    except Exception as exc:
        logger.debug("observe_graph_state(%s) failed: %s", node_name, exc)


def observe_tool_call(name: str, input_data, output_data) -> None:
    """Emit a Langfuse event for a single MCP tool call."""
    if not _check_available():
        return
    try:
        from langfuse import get_client
        client = get_client()
        client.create_event(
            name=f"tool:{name}",
            input=input_data,
            output=str(output_data)[:1000] if output_data is not None else None,
        )
    except Exception as exc:
        logger.debug("observe_tool_call(%s) failed: %s", name, exc)


def log_react_tool_messages(messages: list) -> None:
    """Log AIMessage tool calls + matching ToolMessages as Langfuse events."""
    if not _check_available():
        return
    try:
        from langchain_core.messages import AIMessage, ToolMessage
        tool_outputs: dict[str, str] = {}
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_outputs[msg.tool_call_id] = (
                    msg.content[:500] if isinstance(msg.content, str) else str(msg.content)[:500]
                )
        for msg in messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for call in msg.tool_calls:
                    output = tool_outputs.get(call.get("id", ""))
                    observe_tool_call(call.get("name", "unknown"), call.get("args"), output)
    except Exception as exc:
        logger.debug("log_react_tool_messages failed: %s", exc)


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
