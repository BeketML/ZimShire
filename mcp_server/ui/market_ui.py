from __future__ import annotations

from prefab_ui import PrefabApp
from prefab_ui.components import (
    Column,
    DataTable,
    DataTableColumn,
    Metric,
    Row,
)
from prefab_ui.components.charts import BarChart, ChartSeries, LineChart

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


# ── Analyst targets ────────────────────────────────────────────────────────

@mcp.tool(name="get_analyst_targets_ui", app=True, tags={"market", "analysis", "ui"})
async def get_analyst_targets_ui(ticker: str) -> PrefabApp:
    """Analyst price targets consensus as metric cards: current, low, high, mean, median."""
    from mcp_server.market.tools import get_analyst_targets

    d = await get_analyst_targets(ticker)

    def _fmt(v: object) -> str:
        if v is None:
            return "—"
        try:
            return f"${float(v):,.2f}"
        except (TypeError, ValueError):
            return str(v)

    target_fields = [
        ("Current",  d.get("current")),
        ("Low",      d.get("low")),
        ("High",     d.get("high")),
        ("Mean",     d.get("mean")),
        ("Median",   d.get("median")),
    ]

    with PrefabApp() as ui:
        with Column():
            with Row():
                for label, value in target_fields:
                    Metric(label=label, value=_fmt(value))
            _kv_table(_kv_rows(d))
    return ui


# ── Recommendations ────────────────────────────────────────────────────────

@mcp.tool(name="get_recommendations_ui", app=True, tags={"market", "analysis", "ui"})
async def get_recommendations_ui(ticker: str) -> PrefabApp:
    """Analyst recommendations by period as a stacked bar chart."""
    from mcp_server.market.tools import get_recommendations

    data = await get_recommendations(ticker)

    with PrefabApp() as ui:
        with Column():
            if data:
                BarChart(
                    data=data,
                    series=[
                        ChartSeries(data_key="strongBuy",  label="Strong Buy"),
                        ChartSeries(data_key="buy",        label="Buy"),
                        ChartSeries(data_key="hold",       label="Hold"),
                        ChartSeries(data_key="sell",       label="Sell"),
                        ChartSeries(data_key="strongSell", label="Strong Sell"),
                    ],
                    x_axis="period",
                    stacked=True,
                    height=300,
                )
            _auto_table(data)
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


# ── Upgrades / downgrades ──────────────────────────────────────────────────

@mcp.tool(name="get_upgrades_downgrades_ui", app=True, tags={"market", "analysis", "ui"})
async def get_upgrades_downgrades_ui(ticker: str) -> PrefabApp:
    """Analyst rating changes: date, firm, from grade, to grade, action."""
    from mcp_server.market.tools import get_upgrades_downgrades

    data = await get_upgrades_downgrades(ticker)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True, paginated=True)
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


# ── Market summary ─────────────────────────────────────────────────────────

@mcp.tool(name="get_market_summary_ui", app=True, tags={"market", "macro", "ui"})
async def get_market_summary_ui(market: str = "US") -> PrefabApp:
    """Market-wide summary: indices, gainers/losers, crypto, commodities, currencies."""
    from mcp_server.market.tools import get_market_summary

    raw = await get_market_summary(market)
    rows = _kv_rows(raw)

    with PrefabApp() as ui:
        with Column():
            _kv_table(rows)
    return ui


# ── Calendar events ────────────────────────────────────────────────────────

@mcp.tool(name="get_calendar_events_ui", app=True, tags={"market", "macro", "ui"})
async def get_calendar_events_ui(days_ahead: int = 7) -> PrefabApp:
    """Upcoming market events: earnings releases, IPOs, stock splits."""
    from mcp_server.market.tools import get_calendar_events

    data = await get_calendar_events(days_ahead)
    rows: list[dict] = []
    for event_type, events in data.items():
        for event in events or []:
            row: dict = {"type": event_type}
            row.update({k: str(v)[:120] if v is not None else "" for k, v in event.items()})
            rows.append(row)

    with PrefabApp() as ui:
        with Column():
            _auto_table(rows, search=True, paginated=True)
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


# ── Screen stocks ──────────────────────────────────────────────────────────

@mcp.tool(name="screen_stocks_ui", app=True, tags={"market", "screener", "ui"})
async def screen_stocks_ui(
    sector: str | None = None,
    region: str = "us",
    size: int = 20,
) -> PrefabApp:
    """Screen stocks by region and optional sector."""
    from mcp_server.market.tools import screen_stocks

    data = await screen_stocks(sector, region, size)

    with PrefabApp() as ui:
        with Column():
            _auto_table(data, search=True, paginated=True)
    return ui


# ── Legacy get_market_data ─────────────────────────────────────────────────

@mcp.tool(name="get_market_data_ui", app=True, tags={"market", "ui"})
async def get_market_data_ui(ticker: str, data_type: str = "info") -> PrefabApp:
    """Visual market data for a ticker. data_type: info | financials | history."""
    from mcp_server.market.tools import get_market_data

    raw = await get_market_data(ticker, data_type)

    if isinstance(raw, dict):
        rows = _kv_rows(raw)
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
