"""LiteLLM gateway wrapper — per-role ChatOpenAI factories."""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


@lru_cache(maxsize=32)
def get_chat_model(model: str | None = None, temperature: float = 0.2) -> ChatOpenAI:
    """Generic model factory — cached by (model, temperature)."""
    return ChatOpenAI(
        model=model or settings.default_chat_model,
        temperature=temperature,
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_base_url,
        default_headers={"x-litellm-end-user-id": settings.litellm_end_user_id},
    )


def get_orchestrator_model(model_override: str | None = None) -> ChatOpenAI:
    """Planner + synthesizer — Claude via LiteLLM."""
    return get_chat_model(model_override or settings.orchestrator_model, temperature=0.2)


def get_subagent_model(model_override: str | None = None) -> ChatOpenAI:
    """RAG / Market / Web subagents — Claude via LiteLLM."""
    return get_chat_model(model_override or settings.subagent_model, temperature=0.1)


def get_guardrail_model(model_override: str | None = None) -> ChatOpenAI:
    """Guardrail classifiers — fast cheap model (gpt-4o-mini by default)."""
    return get_chat_model(model_override or settings.guardrail_model, temperature=0.0)


def get_memory_model() -> ChatOpenAI:
    """Memory extraction — lightweight model."""
    return get_chat_model(settings.memory_model, temperature=0.0)
