from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import Column, DataTable, DataTableColumn

from mcp_server.core.mcp import mcp


# ── RAG ────────────────────────────────────────────────────────────────────

@mcp.tool(name="search_buffett_letters_ui", app=True, tags={"rag", "ui"})
def search_buffett_letters_ui(
    query: str,
    top_k: int = 5,
    letter_years_filter: list[int] | None = None,
) -> PrefabApp:
    """Visual search over Buffett letters. Returns hybrid RAG results as a searchable table."""
    from mcp_server.rag.tools import search_buffett_letters

    results = search_buffett_letters(query, top_k, letter_years_filter)

    with PrefabApp() as ui:
        with Column():
            DataTable(
                columns=[
                    DataTableColumn(key="letter_year",      header="Year",   sortable=True),
                    DataTableColumn(key="similarity_score", header="Score",  sortable=True, format="number:4"),
                    DataTableColumn(key="chunk_index",      header="Chunk"),
                    DataTableColumn(key="passage_snippet",  header="Passage"),
                    DataTableColumn(key="source_file",      header="Source"),
                ],
                rows=results,
                search=True,
                paginated=True,
            )
    return ui


# ── Market ─────────────────────────────────────────────────────────────────

@mcp.tool(name="get_market_data_ui", app=True, tags={"market", "ui"})
async def get_market_data_ui(ticker: str, data_type: str = "info") -> PrefabApp:
    """Visual market data for a ticker. data_type: info | financials | history."""
    from mcp_server.market.tools import get_market_data

    raw = await get_market_data(ticker, data_type)

    if isinstance(raw, dict):
        rows = [{"field": k, "value": str(v)} for k, v in raw.items() if v is not None]
        columns = [
            DataTableColumn(key="field", header="Field", sortable=True),
            DataTableColumn(key="value", header="Value"),
        ]
    elif isinstance(raw, list):
        rows = raw
        columns = [DataTableColumn(key=k, header=k) for k in (rows[0].keys() if rows else [])]
    else:
        rows = [{"result": str(raw)}]
        columns = [DataTableColumn(key="result", header="Result")]

    with PrefabApp() as ui:
        with Column():
            DataTable(columns=columns, rows=rows, search=True, paginated=True)
    return ui


# ── Web Search ─────────────────────────────────────────────────────────────

@mcp.tool(name="web_search_ui", app=True, tags={"web", "ui"})
async def web_search_ui(query: str, max_results: int = 5) -> PrefabApp:
    """Visual web search results via DuckDuckGo (SerpApi). Returns title, url, snippet."""
    from mcp_server.search.tools import web_search

    results = await web_search(query, max_results)

    with PrefabApp() as ui:
        with Column():
            DataTable(
                columns=[
                    DataTableColumn(key="title",   header="Title"),
                    DataTableColumn(key="url",     header="URL"),
                    DataTableColumn(key="snippet", header="Snippet"),
                    DataTableColumn(key="date",    header="Date", sortable=True),
                ],
                rows=results,
                search=True,
            )
    return ui
