from __future__ import annotations

from mcp_server.services import factory


async def handle_search_buffett_letters(
    query: str,
    top_k: int,
    letter_years_filter: list[int] | None,
) -> list[dict]:
    hits = await factory.get_rag_service().search(query, top_k, letter_years_filter)
    return [dict(h) for h in hits]
