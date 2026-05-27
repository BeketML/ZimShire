"""Compile the ZimShire LangGraph.

Topology:
  START → input_guardrail
  input_guardrail →[blocked]→ END
  input_guardrail →[continue]→ semantic_cache_check
  semantic_cache_check →[hit]→ END
  semantic_cache_check →[miss]→ load_memory
  load_memory → orchestrator (planner)
  orchestrator → run_subagents
  run_subagents → synthesizer
  synthesizer → output_guardrail
  output_guardrail →[retry, retry_count < 3]→ synthesizer
  output_guardrail →[proceed]→ faithfulness_guardrail
  faithfulness_guardrail → END
"""
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
from app.modules.agents.nodes.subagent_runner import run_subagents
from app.modules.agents.nodes.synthesizer import synthesizer
from app.modules.agents.observability import wrap_node
from app.modules.agents.routing import (
    route_after_cache,
    route_after_input,
    route_after_output_guardrail,
)
from app.modules.agents.state import ZimShireState


def build_graph(checkpointer: BaseCheckpointSaver, store: BaseStore):
    builder = StateGraph(ZimShireState)

    builder.add_node("input_guardrail", wrap_node(input_guardrail, "input_guardrail"))
    builder.add_node("semantic_cache_check", wrap_node(semantic_cache_check, "semantic_cache_check"))
    builder.add_node("load_memory", wrap_node(partial(load_memory, store=store), "load_memory"))
    builder.add_node("orchestrator", wrap_node(orchestrator, "orchestrator"))
    builder.add_node("run_subagents", wrap_node(run_subagents, "run_subagents"))
    builder.add_node("synthesizer", wrap_node(synthesizer, "synthesizer"))
    builder.add_node("output_guardrail", wrap_node(output_guardrail, "output_guardrail"))
    builder.add_node("faithfulness_guardrail", wrap_node(faithfulness_guardrail, "faithfulness_guardrail"))

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
    builder.add_edge("orchestrator", "run_subagents")
    builder.add_edge("run_subagents", "synthesizer")
    builder.add_edge("synthesizer", "output_guardrail")
    builder.add_conditional_edges(
        "output_guardrail",
        route_after_output_guardrail,
        {"retry": "synthesizer", "proceed": "faithfulness_guardrail"},
    )
    builder.add_edge("faithfulness_guardrail", END)

    return builder.compile(checkpointer=checkpointer, store=store)
