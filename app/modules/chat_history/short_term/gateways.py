"""Read short-term memory from LangGraph checkpointer."""
from __future__ import annotations

from langchain_core.messages import BaseMessage


async def load_messages_from_checkpointer(graph, *, thread_id: str) -> list[BaseMessage]:
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if snapshot is None or not snapshot.values:
        return []
    messages = snapshot.values.get("messages") or []
    return list(messages)
