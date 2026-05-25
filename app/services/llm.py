"""LiteLLM gateway wrapper — produces langchain ChatOpenAI compatibility.

All LLM calls in the graph go through here, routed via the Zimran gateway
(`LITELLM_BASE_URL`) with the `x-litellm-end-user-id` header for budget tracking.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


@lru_cache(maxsize=16)
def get_chat_model(model: str | None = None, temperature: float = 0.2) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointed at the LiteLLM gateway.

    Cached so we reuse the same client across requests for a given model slug.
    """
    return ChatOpenAI(
        model=model or settings.default_chat_model,
        temperature=temperature,
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_base_url,
        default_headers={"x-litellm-end-user-id": settings.litellm_end_user_id},
    )
