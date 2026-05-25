"""Subagent tools used inside the ReAct orchestrator.

Each tool calls the MCP server via `app.graph.mcp_client` and writes its raw
results into a shared `accumulated` dict (closure). The orchestrator node then
returns everything from this dict into LangGraph state on completion.

`market_agent` is special: it consults `market_data_cache` (Postgres) before
asking MCP, so a fresh TTL hit avoids both an MCP roundtrip and a yfinance call.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.mcp_client import get_mcp_tools
from app.repositories import cache_repo

logger = logging.getLogger(__name__)


RAG_TOP_K = 5
WEB_MAX_RESULTS = 5


def build_tools_with_accumulator(
    accumulated: dict[str, Any],
    *,
    db_session_factory,
) -> list[BaseTool]:
    """Return [rag_agent, market_agent, web_agent] wired to the shared accumulator.

    `db_session_factory` is an async context manager factory (e.g. AsyncSessionLocal)
    used by `market_agent` to read/write market_data_cache.
    """
    mcp_tools = get_mcp_tools()

    @tool
    async def rag_agent(query: str, years: list[int] | None = None) -> str:
        """Search Warren Buffett shareholder letters for investment philosophy,
        moats, intrinsic value, margin of safety, management quality.

        Args:
            query: Natural-language research question.
            years: Optional list of letter years to filter on.
        """
        try:
            hits: list[dict] = await mcp_tools["search_buffett_letters"].ainvoke(
                {"query": query, "top_k": RAG_TOP_K, "letter_years_filter": years}
            )
        except Exception as e:
            logger.exception("rag_agent MCP call failed: %s", e)
            hits = []

        if hits:
            accumulated["rag_agent_chunks"].extend(hits)
            formatted = "\n\n".join(
                f"[{h.get('letter_year')}] score={h.get('similarity_score', 0):.3f}\n"
                f"{h.get('passage_snippet', '')}"
                for h in hits
            )
        else:
            formatted = "No relevant Buffett letter passages found."
        accumulated["rag_agent_result"] = formatted
        return formatted

    @tool
    async def market_agent(tickers: list[str], data_type: str = "info") -> str:
        """Get live market data for one or more ticker symbols.

        Args:
            tickers: List like ["AAPL", "KO"].
            data_type: One of "info" (default), "financials", "history".
        """
        if not tickers:
            return "No tickers provided."
        result: dict[str, Any] = {}
        async with db_session_factory() as session:  # type: AsyncSession
            for ticker in tickers:
                cached = await cache_repo.get_valid_market(
                    session, ticker=ticker, data_type=data_type
                )
                if cached is not None:
                    result[ticker] = cached.payload
                    continue
                try:
                    payload = await mcp_tools["get_market_data"].ainvoke(
                        {"ticker": ticker, "data_type": data_type}
                    )
                except Exception as e:
                    logger.exception("market_agent MCP call failed for %s: %s", ticker, e)
                    payload = {"error": str(e), "ticker": ticker}
                if "error" not in payload:
                    try:
                        await cache_repo.upsert_market(
                            session,
                            ticker=ticker,
                            data_type=data_type,
                            payload=payload,
                        )
                    except Exception as e:
                        logger.warning("market_data_cache upsert failed: %s", e)
                result[ticker] = payload
            await session.commit()
        text = json.dumps(result, default=str)[:6000]
        accumulated["market_agent_result"] = text
        return text

    @tool
    async def web_agent(query: str) -> str:
        """Web search for current news/events not covered in Buffett letters."""
        try:
            results: list[dict] = await mcp_tools["web_search"].ainvoke(
                {"query": query, "max_results": WEB_MAX_RESULTS}
            )
        except Exception as e:
            logger.exception("web_agent MCP call failed: %s", e)
            results = []
        accumulated["web_agent_sources"].extend(results)
        if results:
            formatted = "\n".join(
                f"- {r.get('title', '')[:120]}: {r.get('snippet', '')[:200]}"
                for r in results
            )
        else:
            formatted = "No web results."
        accumulated["web_agent_result"] = formatted
        return formatted

    return [rag_agent, market_agent, web_agent]
