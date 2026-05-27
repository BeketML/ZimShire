"""Tests for orchestrator plan schema and subagent routing logic."""
import pytest

from app.modules.agents.schemas import OrchestratorPlan, SubagentPlanItem, SubagentResult


def _plan(rag=False, market=False, web=False, direct=False) -> OrchestratorPlan:
    return OrchestratorPlan(
        subagents=[
            SubagentPlanItem(name="rag", enabled=rag, query="q" if rag else "", reason="test"),
            SubagentPlanItem(name="market", enabled=market, query="q" if market else "", reason="test"),
            SubagentPlanItem(name="web", enabled=web, query="q" if web else "", reason="test"),
        ],
        direct_answer_possible=direct,
    )


def test_plan_serialization_roundtrip():
    plan = _plan(rag=True, market=False, web=False)
    data = plan.model_dump()
    restored = OrchestratorPlan(**data)
    enabled = [s for s in restored.subagents if s.enabled]
    assert len(enabled) == 1
    assert enabled[0].name == "rag"


def test_direct_answer_no_subagents():
    plan = _plan(direct=True)
    enabled = [s for s in plan.subagents if s.enabled]
    assert len(enabled) == 0
    assert plan.direct_answer_possible is True


def test_all_three_enabled():
    plan = _plan(rag=True, market=True, web=True)
    enabled = [s for s in plan.subagents if s.enabled]
    assert {s.name for s in enabled} == {"rag", "market", "web"}


def test_subagent_result_model():
    result = SubagentResult(
        agent_name="rag",
        sub_query="what is a moat?",
        formatted_context="A moat is a competitive advantage.",
        raw_artifacts={"rag_chunks": [{"letter_year": 1988, "similarity_score": 0.9}]},
    )
    assert result.agent_name == "rag"
    assert len(result.raw_artifacts["rag_chunks"]) == 1


def test_short_term_memory_service():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from app.modules.chat_history.short_term.service import ShortTermMemoryService

    svc = ShortTermMemoryService()
    msgs = [
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
        HumanMessage(content="Q2"),
        ToolMessage(content="tool result", tool_call_id="x"),
        AIMessage(content="A2"),
    ]
    result = svc.format_recent_turns(msgs, limit_turn_pairs=5)
    assert "Q1" in result
    assert "A1" in result
    assert "Q2" in result
    assert "A2" in result
    assert "tool result" not in result


def test_short_term_limit():
    from langchain_core.messages import AIMessage, HumanMessage
    from app.modules.chat_history.short_term.service import ShortTermMemoryService

    svc = ShortTermMemoryService()
    msgs = []
    for i in range(8):
        msgs.append(HumanMessage(content=f"Q{i}"))
        msgs.append(AIMessage(content=f"A{i}"))

    result = svc.format_recent_turns(msgs, limit_turn_pairs=5)
    # Q0-Q2 should not be included (only last 5 pairs = Q3-Q7)
    assert "Q0" not in result
    assert "Q7" in result
