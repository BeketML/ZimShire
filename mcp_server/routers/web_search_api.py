from __future__ import annotations

from mcp_server.services import factory


async def handle_web_search(
    query: str,
    max_results: int,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    results = await factory.get_web_search_service().search_organic(
        query, max_results, region, date_filter
    )
    return [dict(r) for r in results]


async def handle_web_search_news(
    query: str,
    max_results: int,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    results = await factory.get_web_search_service().search_news(
        query, max_results, region, date_filter
    )
    return [dict(r) for r in results]


async def handle_web_search_knowledge(query: str) -> dict | None:
    result = await factory.get_web_search_service().search_knowledge(query)
    return dict(result) if result is not None else None
