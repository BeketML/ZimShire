from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import (
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Text,
)

from mcp_server.core.mcp import mcp


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


@mcp.tool(name="web_search_news_ui", app=True, tags={"web", "news", "ui"})
async def web_search_news_ui(
    query: str,
    max_results: int = 10,
    region: str = "us-en",
    date_filter: str | None = None,
) -> PrefabApp:
    """Visual news search results via DuckDuckGo (SerpApi)."""
    from mcp_server.search.tools import web_search_news

    results = await web_search_news(query, max_results, region, date_filter)

    with PrefabApp() as ui:
        with Column():
            DataTable(
                columns=[
                    DataTableColumn(key="title",   header="Title"),
                    DataTableColumn(key="source",  header="Source",  sortable=True),
                    DataTableColumn(key="date",    header="Date",    sortable=True),
                    DataTableColumn(key="snippet", header="Snippet"),
                    DataTableColumn(key="url",     header="URL"),
                ],
                rows=results,
                search=True,
                paginated=True,
            )
    return ui


@mcp.tool(name="web_search_knowledge_ui", app=True, tags={"web", "knowledge", "ui"})
async def web_search_knowledge_ui(query: str) -> PrefabApp:
    """Visual knowledge graph card for an entity via DuckDuckGo (SerpApi)."""
    from mcp_server.search.tools import web_search_knowledge

    result = await web_search_knowledge(query)

    with PrefabApp() as ui:
        with Column():
            if not result:
                Text("No knowledge card found for this query.")
            else:
                with Card():
                    with CardHeader():
                        CardTitle(result.get("title", ""))
                        CardDescription(result.get("description", ""))
                    with CardContent():
                        facts = result.get("facts") or {}
                        fact_rows = [{"key": k, "value": str(v)} for k, v in facts.items()]
                        if fact_rows:
                            DataTable(
                                columns=[
                                    DataTableColumn(key="key",   header="Fact"),
                                    DataTableColumn(key="value", header="Value"),
                                ],
                                rows=fact_rows,
                                search=True,
                            )
    return ui
