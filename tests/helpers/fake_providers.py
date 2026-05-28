"""Fake providers and models for unit / integration tests — no real LLM calls."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage


class FakeChatModel:
    """Returns a canned AIMessage for any ainvoke call."""

    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, messages, **kwargs) -> AIMessage:
        return AIMessage(content=self._content)

    def with_structured_output(self, schema):
        content = self._content
        model = self

        class _StructuredModel:
            async def ainvoke(self, messages, **kwargs):
                try:
                    data = json.loads(content)
                    return schema(**data)
                except Exception:
                    return schema()

        return _StructuredModel()


GUARDRAIL_PASS_JSON = json.dumps({
    "blocked": False,
    "reason": None,
    "factual_consistent": True,
    "unsupported_claims": [],
    "safety_violation": False,
    "safety_category": None,
    "safety_reason": None,
    "feedback": None,
    "grounded": True,
    "score": 0.9,
})

GUARDRAIL_BLOCK_JSON = json.dumps({
    "blocked": True,
    "reason": "personal investment advice",
})


class FakeLLMProvider:
    """LLMProvider that returns FakeChatModel for all roles."""

    def __init__(self, content: str = GUARDRAIL_PASS_JSON) -> None:
        self._content = content

    def get_orchestrator_model(self):
        return FakeChatModel(self._content)

    def get_subagent_model(self):
        return FakeChatModel(self._content)

    def get_guardrail_model(self):
        return FakeChatModel(self._content)

    def get_memory_model(self):
        return FakeChatModel(self._content)
