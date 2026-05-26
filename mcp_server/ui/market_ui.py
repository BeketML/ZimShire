from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import (
    Column,
    DataTable,
    DataTableColumn,
    Metric,
    Row,
)
from prefab_ui.components.charts import ChartSeries, LineChart

from mcp_server.core.mcp import mcp


# ── Helpers ────────────────────────────────────────────────────────────────

def _kv_rows(d: dict) -> list[dict]:
    """Flatten a dict into [{field, value}] rows, skipping None values."""
    return [{"field": str(k), "value": str(v)} for k, v in d.items() if v is not None]


def _kv_table(rows: list[dict]) -> DataTable:
    return DataTable(
        columns=[
            DataTableColumn(key="field", header="Field", sortable=True),
            DataTableColumn(key="value", header="Value"),
        ],
        rows=rows,
        search=True,
    )


def _financials_to_rows(raw: dict) -> tuple[list[dict], list[DataTableColumn]]:
    """Transform {metric: {date: value}} → (rows, columns) for DataTable."""
    rows: list[dict] = []
    for metric, date_vals in raw.items():
        row: dict = {"metric": str(metric)}
        if isinstance(date_vals, dict):
            for date_str, val in date_vals.items():
                col_key = str(date_str)[:10]
                row[col_key] = str(val) if val is not None else ""
        rows.append(row)

    col_keys: list[str] = list(rows[0].keys()) if rows else ["metric"]
    columns = [
        DataTableColumn(key=k, header=k, sortable=(k == "metric"))
        for k in col_keys
    ]
    return rows, columns


def _auto_table(items: list[dict], *, search: bool = True, paginated: bool = False) -> DataTable:
    """Build DataTable auto-generating columns from first row keys."""
    if not items:
        return DataTable(
            columns=[DataTableColumn(key="result", header="No data")],
            rows=[],
        )
    keys = list(items[0].keys())
    columns = [DataTableColumn(key=k, header=k) for k in keys]
    return DataTable(columns=columns, rows=items, search=search, paginated=paginated)


# ── Stock info ─────────────────────────────────────────────────────────────

@mcp.tool(name="get_stock_info_ui", app=True, tags={"market", "fundamentals", "ui"})
async def get_stock_info_ui(ticker: str) -> PrefabApp:
    """Full company overview: sector, market cap, P/E, EPS, dividend yield, description, CEO."""
    from mcp_server.market.tools import get_stock_info

    raw = await get_stock_info(ticker)
    rows = _kv_rows(raw)

    with PrefabApp() as ui:
        with Column():
            _kv_table(rows)
    return ui


# ── Stock price ────────────────────────────────────────────────────────────

@mcp.tool(name="get_stock_price_ui", app=True, tags={"market", "price", "ui"})
async def get_stock_price_ui(ticker: str) -> PrefabApp:
    """Current price snapshot: last price, previous close, 52-week high/low, market cap."""
    from mcp_server.market.tools import get_stock_price

    d = await get_stock_price(ticker)

    def _fmt(v: object) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):,.2f}"
        except (TypeError, ValueError):
            return str(v)

    price_fields = [
        ("Last Price",    d.get("last_price") or d.get("lastPrice")),
        ("Prev Close",    d.get("previous_close") or d.get("previousClose")),
        ("52W High",      d.get("year_high") or d.get("fiftyTwoWeekHigh")),
        ("52W Low",       d.get("year_low") or d.get("fiftyTwoWeekLow")),
        ("Market Cap",    d.get("market_cap") or d.get("marketCap")),
        ("Shares Out",    d.get("shares") or d.get("sharesOutstanding")),
    ]

    with PrefabApp() as ui:
        with Column():
            with Row():
                for label, value in price_fields:
                    Metric(label=label, value=_fmt(value))
            _kv_table(_kv_rows(d))
    return ui


# ── Stock history ──────────────────────────────────────────────────────────

@mcp.tool(name="get_stock_history_ui", app=True, tags={"market", "price", "ui"})
async def get_stock_history_ui(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
) -> PrefabApp:
    """OHLCV price history as a line chart. period: 1d/5d/1mo/3mo/6mo/1y/2y/5y/max."""
    from mcp_server.market.tools import get_stock_history

    data = await get_stock_history(ticker, period, interval)
    chart_data = []
    for row in data:
        date_str = str(row.get("Date", ""))[:10]
        close = row.get("Close")
        if close is not None:
            chart_data.append({"date": date_str, "close": round(float(close), 2)})

    with PrefabApp() as ui:
        with Column():
            LineChart(
                data=chart_data,
                series=[ChartSeries(data_key="close", label=f"{ticker} Close")],
                x_axis="date",
                height=350,
            )
            _auto_table(data)
    return ui


# ── Income statement ───────────────────────────────────────────────────────

@mcp.tool(name="get_income_statement_ui", app=True, tags={"market", "financials", "ui"})
async def get_income_statement_ui(ticker: str, quarterly: bool = False) -> PrefabApp:
    """Income statement (revenue, gross profit, EBITDA, net income) by period."""
    from mcp_server.market.tools import get_income_statement

    raw = await get_income_statement(ticker, quarterly)
    rows, columns = _financials_to_rows(raw)

    with PrefabApp() as ui:
        with Column():
            DataTable(columns=columns, rows=rows, search=True)
    return ui


# ── Balance sheet ──────────────────────────────────────────────────────────

@mcp.tool(name="get_balance_sheet_ui", app=True, tags={"market", "financials", "ui"})
async def get_balance_sheet_ui(ticker: str, quarterly: bool = False) -> PrefabApp:
    """Balance sheet (total assets, total debt, cash, equity) by period."""
    from mcp_server.market.tools import get_balance_sheet

    raw = await get_balance_sheet(ticker, quarterly)
    rows, columns = _financials_to_rows(raw)

    with PrefabApp() as ui:
        with Column():
            DataTable(columns=columns, rows=rows, search=True)
    return ui


# ── Cash flow ──────────────────────────────────────────────────────────────

@mcp.tool(name="get_cashflow_ui", app=True, tags={"market", "financials", "ui"})
async def get_cashflow_ui(ticker: str, quarterly: bool = False) -> PrefabApp:
    """Cash flow statement (operating, capex, free cash flow) by period."""
    from mcp_server.market.tools import get_cashflow

    raw = await get_cashflow(ticker, quarterly)
    rows, columns = _financials_to_rows(raw)

    with PrefabApp() as ui:
        with Column():
            DataTable(columns=columns, rows=rows, search=True)
    return ui


# ── Earnings estimate ──────────────────────────────────────────────────────

@mcp.tool(name="get_earnings_estimate_ui", app=True, tags={"market", "analysis", "ui"})
async def get_earnings_estimate_ui(ticker: str) -> PrefabApp:
    """Forward EPS estimates (current/next quarter, current/next year)."""
    from mcp_server.market.tools import get_earnings_estimate

    raw = await get_earnings_estimate(ticker)
    rows, columns = _financials_to_rows(raw)

    with PrefabApp() as ui:
        with Column():
            DataTable(columns=columns, rows=rows, search=True)
    return ui


# ── Institutional holders ──────────────────────────────────────────────────

@mcp.tool(name="get_institutional_holders_ui", app=True, tags={"market", "holders", "ui"})
async def get_institutional_holders_ui(ticker: str) -> PrefabApp:
    """Top institutional holders: fund name, shares, % of float, value, date reported."""
    from mcp_server.market.tools import get_institutional_holders

    data = await get_institutional_holders(ticker)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True, paginated=True)
    return ui


# ── Insider transactions ───────────────────────────────────────────────────

@mcp.tool(name="get_insider_transactions_ui", app=True, tags={"market", "holders", "ui"})
async def get_insider_transactions_ui(ticker: str) -> PrefabApp:
    """Recent insider buy/sell transactions: name, title, date, shares, value, type."""
    from mcp_server.market.tools import get_insider_transactions

    data = await get_insider_transactions(ticker)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True, paginated=True)
    return ui


# ── Stock news ─────────────────────────────────────────────────────────────

@mcp.tool(name="get_stock_news_ui", app=True, tags={"market", "news", "ui"})
async def get_stock_news_ui(ticker: str, count: int = 10) -> PrefabApp:
    """Latest news articles for a ticker from Yahoo Finance."""
    from mcp_server.market.tools import get_stock_news

    data = await get_stock_news(ticker, count)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True, paginated=True)
    return ui


# ── Lookup ticker ──────────────────────────────────────────────────────────

@mcp.tool(name="lookup_ticker_ui", app=True, tags={"market", "screener", "ui"})
async def lookup_ticker_ui(query: str) -> PrefabApp:
    """Look up ticker symbols by company name or keyword."""
    from mcp_server.market.tools import lookup_ticker

    data = await lookup_ticker(query)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True)
    return ui


