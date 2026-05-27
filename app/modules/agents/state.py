"""ZimShireState — canonical source: docs/agent_architecture.md §3."""
from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ZimShireState(TypedDict):
    # Core
    messages: Annotated[list[BaseMessage], add_messages]
    query: NotRequired[str]

    # Long-term memory
    user_profile: NotRequired[dict]

    # Collected context from subagent tools (closure accumulator)
    collected_context: NotRequired[dict]
    # Keys: "rag" | "market" | "web" — each a formatted string

    # Raw artifacts for faithfulness + audit
    rag_agent_chunks: NotRequired[list[dict]]
    rag_invoked: NotRequired[bool]
    web_agent_sources: NotRequired[list[dict]]

    # Orchestrator result
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]
    sources: NotRequired[list[dict]]

    # Output guardrail feedback loop
    feedback_message: NotRequired[str | None]
    retry_count: NotRequired[int]

    # Orchestrator planner output (Etap C)
    subagent_plan: NotRequired[dict]            # serialised OrchestratorPlan
    subagent_results: NotRequired[list[dict]]   # serialised SubagentResult[]
    direct_answer_possible: NotRequired[bool]

    # Guardrail / cache flags
    cache_hit: NotRequired[bool]
    input_blocked: NotRequired[bool]
    input_blocked_reason: NotRequired[str | None]
    output_blocked: NotRequired[bool]
    output_blocked_reason: NotRequired[str | None]
    output_rewritten: NotRequired[bool]
