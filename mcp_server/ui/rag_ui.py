from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import Column, DataTable, DataTableColumn

from mcp_server.core.mcp import mcp


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
                    DataTableColumn(key="letter_year",      header="Year",    sortable=True),
                    DataTableColumn(key="similarity_score", header="Score",   sortable=True, format="number:4"),
                    DataTableColumn(key="chunk_index",      header="Chunk"),
                    DataTableColumn(key="passage_snippet",  header="Passage"),
                    DataTableColumn(key="source_file",      header="Source"),
                ],
                rows=results,
                search=True,
                paginated=True,
            )
    return ui
