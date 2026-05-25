from __future__ import annotations

import httpx

from mcp_server.core.config import settings
from mcp_server.core.mcp import get_http_client, mcp
from mcp_server.search.models import WebKnowledgeGraph, WebNewsResult, WebOrganicResult

SERPAPI_BASE = "https://serpapi.com/search"


def _http() -> httpx.AsyncClient:
    return get_http_client()


def _base_params(query: str, region: str, date_filter: str | None) -> dict:
    params: dict = {
        "api_key": settings.duckduckgo_api_key,
        "q": query,
        "kl": region,
    }
    if date_filter:
        params["df"] = date_filter
    return params


# ------------------------------------------------------------------ #
# Organic search                                                       #
# ------------------------------------------------------------------ #

@mcp.tool(name="web_search", tags={"web", "search", "organic"})
async def web_search(
    query: str,
    max_results: int = 5,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    """Organic web search via DuckDuckGo (SerpApi). Returns title, url, snippet, date.
    date_filter: d (past day), w (past week), m (past month), y (past year),
    or custom range e.g. 2021-06-15..2024-06-16."""
    params = _base_params(query, region, date_filter)
    params["engine"] = "duckduckgo"
    params["m"] = min(max_results, 50)

    resp = await _http().get(SERPAPI_BASE, params=params, timeout=30.0)
    if resp.status_code >= 400:
        raise RuntimeError(f"SerpApi organic error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    data = resp.json()

    results: list[WebOrganicResult] = []
    for item in data.get("organic_results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "date": item.get("date"),
            "favicon": item.get("favicon"),
        })
    return [dict(r) for r in results]


# ------------------------------------------------------------------ #
# News search                                                          #
# ------------------------------------------------------------------ #

@mcp.tool(name="web_search_news", tags={"web", "news"})
async def web_search_news(
    query: str,
    max_results: int = 10,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    """News-only search via DuckDuckGo News (SerpApi). Returns title, url, snippet, source, date, thumbnail.
    date_filter: d (past day), w (past week), m (past month)."""
    params = _base_params(query, region, date_filter)
    params["engine"] = "duckduckgo_news"
    params["m"] = min(max_results, 100)

    resp = await _http().get(SERPAPI_BASE, params=params, timeout=30.0)
    if resp.status_code >= 400:
        raise RuntimeError(f"SerpApi news error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    data = resp.json()

    results: list[WebNewsResult] = []
    for item in data.get("news_results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source": item.get("source", ""),
            "date": item.get("date", ""),
            "thumbnail": item.get("thumbnail"),
        })
    return [dict(r) for r in results]


# ------------------------------------------------------------------ #
# Knowledge graph                                                      #
# ------------------------------------------------------------------ #

@mcp.tool(name="web_search_knowledge", tags={"web", "knowledge"})
async def web_search_knowledge(query: str) -> dict | None:
    """Knowledge Graph card for an entity (company, person, place) via DuckDuckGo (SerpApi).
    Returns title, description, website, facts dict, profiles, related_topics. Returns null if no card found."""
    params = {
        "api_key": settings.duckduckgo_api_key,
        "engine": "duckduckgo",
        "q": query,
        "kl": "us-en",
    }

    resp = await _http().get(SERPAPI_BASE, params=params, timeout=30.0)
    if resp.status_code >= 400:
        raise RuntimeError(f"SerpApi knowledge error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    data = resp.json()

    kg = data.get("knowledge_graph")
    if not kg:
        return None

    result: WebKnowledgeGraph = {
        "title": kg.get("title", ""),
        "description": kg.get("description", ""),
        "website": kg.get("website"),
        "facts": {k: str(v) for k, v in (kg.get("facts") or {}).items()},
        "profiles": kg.get("profiles") or [],
        "related_topics": kg.get("related_topics") or [],
    }
    return dict(result)
