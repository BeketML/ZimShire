from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import Column, DataTable, DataTableColumn

from mcp_server.core.mcp import mcp


@mcp.tool(name="search_buffett_letters_ui", app=True, tags={"rag", "ui"})
def search_buffett_letters_ui(
    query: str,
    top_k: int = 5,
    letter_years_filter: str | None = None,
) -> PrefabApp:
    """Visual search over Buffett letters. Returns hybrid RAG results as a searchable table.
    letter_years_filter: single year or comma-separated years, e.g. '1988' or '1988,1989'."""
    from mcp_server.rag.tools import search_buffett_letters

    years: list[int] | None = None
    if letter_years_filter:
        years = [int(y.strip()) for y in letter_years_filter.split(",") if y.strip().isdigit()]

    results = search_buffett_letters(query, top_k, years)

    with PrefabApp() as ui:
        with Column():
            DataTable(
                columns=[
                    DataTableColumn(key="letter_year",      header="Year",         sortable=True),
                    DataTableColumn(key="similarity_score", header="Cosine",       sortable=True, format="number:4"),
                    DataTableColumn(key="rerank_score",     header="Rerank",       sortable=True, format="number:2"),
                    DataTableColumn(key="chunk_index",      header="Chunk"),
                    DataTableColumn(key="passage_snippet",  header="Passage"),
                    DataTableColumn(key="source_file",      header="Source"),
                ],
                rows=results,
                search=True,
                paginated=True,
            )
    return ui
