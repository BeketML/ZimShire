"""Unit tests for the subagent strategy registry."""
from __future__ import annotations

import pytest

from app.modules.agents.subagents.registry import SUBAGENT_REGISTRY


def test_registry_has_all_three_agents():
    assert "rag" in SUBAGENT_REGISTRY
    assert "market" in SUBAGENT_REGISTRY
    assert "web" in SUBAGENT_REGISTRY


def test_registry_strategies_have_run_method():
    for name, strategy in SUBAGENT_REGISTRY.items():
        assert callable(getattr(strategy, "run", None)), f"{name} strategy missing .run()"


def test_unknown_agent_not_in_registry():
    assert SUBAGENT_REGISTRY.get("unknown") is None


@pytest.mark.asyncio
async def test_subagent_runner_empty_plan_returns_empty():
    """An empty subagent plan returns the empty-result dict."""
    from app.modules.agents.nodes.subagent_runner import run_subagents

    state = {"subagent_plan": {"subagents": [], "direct_answer_possible": True}}
    result = await run_subagents(state, {"configurable": {}})
    assert result["subagent_results"] == []
    assert result["rag_invoked"] is False
    assert result["collected_context"] == {}
