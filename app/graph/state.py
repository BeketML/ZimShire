"""LangGraph state for ZimShire. See docs/agent_architecture.md §3."""
from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ZimShireState(TypedDict):
    # Core
    messages: Annotated[list[BaseMessage], add_messages]
    query: NotRequired[str]

    # Memory
    user_preferences: NotRequired[list[str]]

    # Sub-agent results (orchestrator closure accumulator)
    rag_agent_chunks: NotRequired[list[dict]]
    rag_agent_result: NotRequired[str]
    rag_invoked: NotRequired[bool]
    web_agent_sources: NotRequired[list[dict]]
    web_agent_result: NotRequired[str]
    market_agent_result: NotRequired[str]

    # Orchestrator result
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]
    sources: NotRequired[list[dict]]

    # Guardrail / cache flags
    cache_hit: NotRequired[bool]
    input_blocked: NotRequired[bool]
    input_blocked_reason: NotRequired[str | None]
    output_blocked: NotRequired[bool]
    output_blocked_reason: NotRequired[str | None]
    output_rewritten: NotRequired[bool]
