"""Async text embeddings via LiteLLM gateway (text-embedding-3-small)."""
from __future__ import annotations

import httpx

from app.core.config import settings


async def embed_text(text: str) -> list[float]:
    if not text.strip():
        raise ValueError("Cannot embed empty text")
    base = settings.litellm_base_url.rstrip("/")
    url = (base if base.endswith("/v1") else base + "/v1") + "/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.litellm_api_key}",
        "x-litellm-end-user-id": settings.litellm_end_user_id,
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embedding_model, "input": text}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["data"][0]["embedding"]
