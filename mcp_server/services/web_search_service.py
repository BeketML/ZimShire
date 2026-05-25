from __future__ import annotations

import httpx

from mcp_server.services.protocols import (
    WebKnowledgeGraph,
    WebNewsResult,
    WebOrganicResult,
    WebSearchServiceInterface,
)

SERPAPI_BASE = "https://serpapi.com/search"


class SerpApiWebSearchService(WebSearchServiceInterface):
    def __init__(self, api_key: str, http_client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http_client

    def _base_params(self, query: str, region: str, date_filter: str | None) -> dict:
        params: dict = {
            "api_key": self._api_key,
            "q": query,
            "kl": region,
        }
        if date_filter:
            params["df"] = date_filter
        return params

    async def search_organic(
        self,
        query: str,
        max_results: int = 5,
        region: str = "us-en",
        date_filter: str | None = None,
    ) -> list[WebOrganicResult]:
        params = self._base_params(query, region, date_filter)
        params["engine"] = "duckduckgo"
        params["m"] = min(max_results, 50)

        resp = await self._http.get(SERPAPI_BASE, params=params, timeout=30.0)
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
        return results

    async def search_news(
        self,
        query: str,
        max_results: int = 10,
        region: str = "us-en",
        date_filter: str | None = None,
    ) -> list[WebNewsResult]:
        params = self._base_params(query, region, date_filter)
        params["engine"] = "duckduckgo_news"
        params["m"] = min(max_results, 100)

        resp = await self._http.get(SERPAPI_BASE, params=params, timeout=30.0)
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
        return results

    async def search_knowledge(
        self,
        query: str,
    ) -> WebKnowledgeGraph | None:
        params = {
            "api_key": self._api_key,
            "engine": "duckduckgo",
            "q": query,
            "kl": "us-en",
        }

        resp = await self._http.get(SERPAPI_BASE, params=params, timeout=30.0)
        if resp.status_code >= 400:
            raise RuntimeError(f"SerpApi knowledge error {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()

        kg = data.get("knowledge_graph")
        if not kg:
            return None

        return {
            "title": kg.get("title", ""),
            "description": kg.get("description", ""),
            "website": kg.get("website"),
            "facts": {k: str(v) for k, v in (kg.get("facts") or {}).items()},
            "profiles": kg.get("profiles") or [],
            "related_topics": kg.get("related_topics") or [],
        }
