"""TurnOrchestrationService — owns the full lifecycle of one research turn."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator
from uuid import UUID

from langchain_core.messages import HumanMessage

from app.core.database import AsyncSessionLocal
from app.modules.messages import repository as msg_repo
from app.modules.messages.service import persist_assistant_turn
from app.services.langfuse_service import (
    flush as langfuse_flush,
    get_trace_id,
    make_callback_handler,
)

logger = logging.getLogger(__name__)

_SUBAGENT_LABELS: dict[str, str] = {
    "rag": "Searching Buffett letters…",
    "market": "Fetching market data…",
    "web": "Searching the web…",
}


def _chunk_text(text: str, words_per_chunk: int = 4) -> list[str]:
    words = text.split(" ")
    return (
        [" ".join(words[i : i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)]
        if words
        else []
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


class TurnOrchestrationService:
    """Owns the full lifecycle of one research turn: graph run → SSE stream → persist."""

    def __init__(self, graph, store) -> None:
        self._graph = graph
        self._store = store

    async def stream_turn(
        self,
        chat_id: UUID,
        user_id: UUID,
        query: str,
    ) -> AsyncIterator[str]:
        async with AsyncSessionLocal() as session:
            human = await msg_repo.create_human_message(
                session, chat_id=chat_id, content=query
            )
            await session.commit()
            human_message_id = human.message_id

        handler = make_callback_handler(
            user_id=str(user_id),
            session_id=str(chat_id),
            trace_name="zimshire_turn",
        )
        config = {
            "configurable": {
                "thread_id": str(chat_id),
                "user_id": str(user_id),
                "chat_id": str(chat_id),
                "human_message_id": str(human_message_id),
                "query": query,
            },
            "callbacks": [handler] if handler is not None else [],
            "metadata": {
                "langfuse_user_id": str(user_id),
                "langfuse_session_id": str(chat_id),
            },
        }
        inputs = {"messages": [HumanMessage(content=query)], "query": query}

        final_state: dict = {}
        synthesis_started = False
        progress_state = {"plan_emitted": False, "context_emitted": False}

        try:
            # stream_mode=["messages", "values"] yields (typ, chunk) tuples:
            #   "messages" → (AIMessageChunk, metadata) — real LLM tokens per node
            #   "values"   → full state dict after each node — used for progress events
            async for typ, chunk in self._graph.astream(
                inputs, config=config, stream_mode=["messages", "values"]
            ):
                if typ == "messages":
                    msg_chunk, metadata = chunk
                    node = metadata.get("langgraph_node", "")
                    content = getattr(msg_chunk, "content", None)
                    if node == "synthesizer" and isinstance(content, str) and content:
                        synthesis_started = True
                        yield _sse({"type": "token", "content": content})

                elif typ == "values":
                    final_state = chunk

                    # Orchestrator plan landed → subagents about to start
                    if chunk.get("subagent_plan") and not progress_state["plan_emitted"]:
                        progress_state["plan_emitted"] = True
                        for item in (chunk["subagent_plan"].get("subagents") or []):
                            if item.get("enabled"):
                                label = _SUBAGENT_LABELS.get(item["name"])
                                if label:
                                    yield _sse({
                                        "type": "progress",
                                        "stage": item["name"],
                                        "message": label,
                                    })

                    # Subagents done → synthesis about to start
                    if chunk.get("collected_context") and not progress_state["context_emitted"]:
                        progress_state["context_emitted"] = True
                        yield _sse({
                            "type": "progress",
                            "stage": "synthesizing",
                            "message": "Composing answer…",
                        })

        except Exception as exc:
            logger.exception("graph run failed: %s", exc)
            trace_id = get_trace_id(handler)
            yield _sse({"type": "error", "detail": str(exc)})
            yield _sse({"type": "done", "message_id": None, "grounded": None, "sources": [], "langfuse_trace_id": trace_id, "cache_hit": False})
            langfuse_flush()
            return

        trace_id = get_trace_id(handler)

        # Input was blocked — no synthesis occurred
        if final_state.get("input_blocked"):
            reason = final_state.get("input_blocked_reason") or "Query rejected by input guardrail."
            yield _sse({"type": "blocked", "reason": reason})
            yield _sse({"type": "done", "message_id": None, "grounded": None, "sources": [], "langfuse_trace_id": trace_id, "cache_hit": False})
            langfuse_flush()
            return

        approved_text = final_state.get("draft_answer") or ""

        # Output guardrail rewrote content that was already streamed to the client
        if synthesis_started and final_state.get("output_rewritten"):
            yield _sse({"type": "replace", "content": approved_text})

        # No synthesis tokens were sent (cache hit or edge case) — stream text now
        if not synthesis_started and approved_text:
            for piece in _chunk_text(approved_text):
                yield _sse({"type": "token", "content": piece + " "})

        async with AsyncSessionLocal() as session:
            assistant_msg = await persist_assistant_turn(
                session,
                chat_id=chat_id,
                user_id=user_id,
                user_query=query,
                final_state=final_state,
                langfuse_trace_id=trace_id,
                store=self._store,
            )
            await session.commit()

        yield _sse(
            {
                "type": "done",
                "message_id": str(assistant_msg.message_id),
                "grounded": final_state.get("grounded"),
                "sources": final_state.get("sources") or [],
                "langfuse_trace_id": trace_id,
                "cache_hit": bool(final_state.get("cache_hit")),
            }
        )
        langfuse_flush()
