"""Unit tests for guardrail nodes (no live infra needed — LLM is mocked)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ── helpers ────────────────────────────────────────────────────────────────


def _make_config(model="gpt-4o-mini", human_message_id="00000000-0000-0000-0000-000000000001"):
    return {
        "configurable": {
            "thread_id": "chat-1",
            "user_id": "user-1",
            "model": model,
            "human_message_id": human_message_id,
        }
    }


def _make_llm_resp(content: str):
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content=content))
    return mock


# ── input_guardrail ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_input_guardrail_passes_research_question():
    from app.modules.agents.nodes.guardrails import input_guardrail

    state = {"messages": [HumanMessage(content="How would Buffett evaluate Apple's moat?")]}
    resp_json = json.dumps({"blocked": False, "reason": None})

    with (
        patch("app.modules.agents.nodes.input_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.input_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await input_guardrail(state, _make_config())

    assert result["input_blocked"] is False
    assert result["query"] == "How would Buffett evaluate Apple's moat?"


@pytest.mark.asyncio
async def test_input_guardrail_blocks_off_topic():
    from app.modules.agents.nodes.guardrails import input_guardrail

    state = {"messages": [HumanMessage(content="What's the best recipe for pasta?")]}
    resp_json = json.dumps({"blocked": True, "reason": "off-topic: cooking"})

    with (
        patch("app.modules.agents.nodes.input_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.input_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await input_guardrail(state, _make_config())

    assert result["input_blocked"] is True
    assert result["input_blocked_reason"] == "off-topic: cooking"
    assert any(isinstance(m, AIMessage) for m in result.get("messages", []))


@pytest.mark.asyncio
async def test_input_guardrail_blocks_personal_advice():
    from app.modules.agents.nodes.guardrails import input_guardrail

    state = {"messages": [HumanMessage(content="Should I buy Apple stock right now?")]}
    resp_json = json.dumps({"blocked": True, "reason": "personal investment advice"})

    with (
        patch("app.modules.agents.nodes.input_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.input_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await input_guardrail(state, _make_config())

    assert result["input_blocked"] is True


@pytest.mark.asyncio
async def test_input_guardrail_allows_on_llm_failure():
    """If LLM call throws, guardrail fails open (allow through)."""
    from app.modules.agents.nodes.guardrails import input_guardrail

    state = {"messages": [HumanMessage(content="Tell me about Berkshire Hathaway")]}

    with (
        patch("app.modules.agents.nodes.input_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.input_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        failing_llm = MagicMock()
        failing_llm.ainvoke = AsyncMock(side_effect=Exception("network error"))
        mock_model.return_value = failing_llm
        result = await input_guardrail(state, _make_config())

    assert result["input_blocked"] is False


# ── output_guardrail ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_output_guardrail_passes_clean_answer():
    from app.modules.agents.nodes.guardrails import output_guardrail

    state = {
        "messages": [],
        "draft_answer": "Buffett wrote in 1988 that Coca-Cola's brand is a durable moat.",
        "collected_context": {"rag": "[1988] score=0.87\nBuffett letter passage..."},
        "user_profile": {},
        "retry_count": 0,
    }
    resp_json = json.dumps({
        "factual_consistent": True,
        "unsupported_claims": [],
        "safety_violation": False,
        "safety_category": None,
        "safety_reason": None,
        "feedback": None,
    })
    with (
        patch("app.modules.agents.nodes.output_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.output_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await output_guardrail(state, _make_config())

    assert result["output_blocked"] is False
    assert result["feedback_message"] is None


@pytest.mark.asyncio
async def test_output_guardrail_catches_buy_sell():
    from app.modules.agents.nodes.guardrails import output_guardrail

    state = {
        "messages": [],
        "draft_answer": "You should buy Apple stock immediately.",
        "collected_context": {},
        "user_profile": {},
        "retry_count": 0,
    }
    resp_json = json.dumps({
        "factual_consistent": True,
        "unsupported_claims": [],
        "safety_violation": True,
        "safety_category": "buy_sell",
        "safety_reason": "direct buy recommendation",
        "feedback": "Remove the buy recommendation and reframe as analysis.",
    })
    with (
        patch("app.modules.agents.nodes.output_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.output_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await output_guardrail(state, _make_config())

    assert result["output_blocked"] is True
    assert result.get("retry_count") == 1
    assert result.get("feedback_message") is not None
    # draft_answer NOT replaced on first retry
    assert "draft_answer" not in result


@pytest.mark.asyncio
async def test_output_guardrail_fallback_after_max_retries():
    from app.modules.agents.nodes.guardrails import output_guardrail

    state = {
        "messages": [],
        "draft_answer": "Still bad answer.",
        "collected_context": {},
        "user_profile": {},
        "retry_count": 2,  # already at max
    }
    resp_json = json.dumps({
        "factual_consistent": True,
        "unsupported_claims": [],
        "safety_violation": True,
        "safety_category": "price_target",
        "safety_reason": "explicit price target",
        "feedback": "Remove price target.",
    })
    with (
        patch("app.modules.agents.nodes.output_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.output_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await output_guardrail(state, _make_config())

    assert result["output_rewritten"] is True
    assert "ZimShire can help" in result["draft_answer"]


# ── faithfulness_guardrail ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_faithfulness_grounded_none_when_rag_not_invoked():
    from app.modules.agents.nodes.guardrails import faithfulness_guardrail

    state = {"rag_invoked": False, "rag_agent_chunks": [], "collected_context": {}, "query": ""}
    with patch("app.modules.agents.nodes.faithfulness_guardrail.write_guardrail_log", new_callable=AsyncMock):
        result = await faithfulness_guardrail(state, _make_config())

    assert result["grounded"] is None
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_faithfulness_grounded_true():
    from app.modules.agents.nodes.guardrails import faithfulness_guardrail

    chunks = [
        {"letter_year": 1988, "passage_snippet": "moats are durable", "similarity_score": 0.91, "qdrant_point_id": "abc"},
        {"letter_year": 1989, "passage_snippet": "brand loyalty is key", "similarity_score": 0.88, "qdrant_point_id": "def"},
    ]
    state = {
        "rag_invoked": True,
        "rag_agent_chunks": chunks,
        "collected_context": {"rag": "moats are durable"},
        "query": "What did Buffett say about moats?",
        "messages": [],
    }
    resp_json = json.dumps({"grounded": True, "score": 0.90, "unsupported_claims": []})
    with (
        patch("app.modules.agents.nodes.faithfulness_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.faithfulness_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await faithfulness_guardrail(state, _make_config())

    assert result["grounded"] is True
    assert len(result["sources"]) > 0


@pytest.mark.asyncio
async def test_faithfulness_grounded_false_low_score():
    from app.modules.agents.nodes.guardrails import faithfulness_guardrail

    chunks = [
        {"letter_year": 1988, "passage_snippet": "a short passage", "similarity_score": 0.80, "qdrant_point_id": "abc"},
    ]
    state = {
        "rag_invoked": True,
        "rag_agent_chunks": chunks,
        "collected_context": {"rag": "answer with many invented claims"},
        "query": "test",
        "messages": [],
    }
    resp_json = json.dumps({"grounded": False, "score": 0.30, "unsupported_claims": ["claim1"]})
    with (
        patch("app.modules.agents.nodes.faithfulness_guardrail.get_guardrail_model") as mock_model,
        patch("app.modules.agents.nodes.faithfulness_guardrail.write_guardrail_log", new_callable=AsyncMock),
    ):
        mock_model.return_value = _make_llm_resp(resp_json)
        result = await faithfulness_guardrail(state, _make_config())

    assert result["grounded"] is False
    assert result["sources"] == []
