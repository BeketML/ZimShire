"""LiteLLM gateway wrapper — ChatOpenAI pointed at the Zimran proxy."""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


@lru_cache(maxsize=16)
def get_chat_model(model: str | None = None, temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.default_chat_model,
        temperature=temperature,
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_base_url,
        default_headers={"x-litellm-end-user-id": settings.litellm_end_user_id},
    )
