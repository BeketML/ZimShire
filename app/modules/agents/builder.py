"""Compile the ZimShire LangGraph (with output_guardrail retry loop)."""
from __future__ import annotations

from functools import partial

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.modules.agents.nodes.cache import semantic_cache_check
from app.modules.agents.nodes.guardrails import (
    faithfulness_guardrail,
    input_guardrail,
    output_guardrail,
)
from app.modules.agents.nodes.memory import load_memory
from app.modules.agents.nodes.orchestrator import orchestrator
from app.modules.agents.routing import (
    route_after_cache,
    route_after_input,
    route_after_output_guardrail,
)
from app.modules.agents.state import ZimShireState


def build_graph(checkpointer: BaseCheckpointSaver, store: BaseStore):
    builder = StateGraph(ZimShireState)

    builder.add_node("input_guardrail", input_guardrail)
    builder.add_node("semantic_cache_check", semantic_cache_check)
    builder.add_node("load_memory", partial(load_memory, store=store))
    builder.add_node("orchestrator", orchestrator)
    builder.add_node("output_guardrail", output_guardrail)
    builder.add_node("faithfulness_guardrail", faithfulness_guardrail)

    builder.add_edge(START, "input_guardrail")
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input,
        {"blocked": END, "continue": "semantic_cache_check"},
    )
    builder.add_conditional_edges(
        "semantic_cache_check",
        route_after_cache,
        {"hit": END, "miss": "load_memory"},
    )
    builder.add_edge("load_memory", "orchestrator")
    builder.add_edge("orchestrator", "output_guardrail")
    builder.add_conditional_edges(
        "output_guardrail",
        route_after_output_guardrail,
        {"retry": "orchestrator", "proceed": "faithfulness_guardrail"},
    )
    builder.add_edge("faithfulness_guardrail", END)

    return builder.compile(checkpointer=checkpointer, store=store)
