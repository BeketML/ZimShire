from __future__ import annotations

import asyncio
import json
from typing import Any

import yfinance as yf

from mcp_server.core.mcp import mcp

# ------------------------------------------------------------------ #
# Serialisation helpers                                                #
# ------------------------------------------------------------------ #

def _to_json(raw: Any) -> Any:
    return json.loads(json.dumps(raw, default=str))


def _df_to_records(df: Any) -> list[dict]:
    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    return _to_json(df.reset_index().to_dict(orient="records"))


def _df_to_dict(df: Any) -> dict:
    if df is None or (hasattr(df, "empty") and df.empty):
        return {}
    df = df.copy()
    df.columns = df.columns.astype(str)
    return _to_json(df.to_dict())


async def _run(fn, *args) -> Any:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ------------------------------------------------------------------ #
# Fundamentals                                                         #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_stock_info", tags={"market", "finance", "fundamentals"})
async def get_stock_info(ticker: str) -> dict:
    """Full company overview: sector, market cap, P/E, EPS, dividend yield, description, CEO, employees.
    ticker: e.g. AAPL, MSFT, BRK-B"""
    return await _run(lambda: _to_json(dict(yf.Ticker(ticker).info)))


@mcp.tool(name="get_stock_price", tags={"market", "finance", "fundamentals"})
async def get_stock_price(ticker: str) -> dict:
    """Fast current price data: lastPrice, previousClose, yearHigh, yearLow, marketCap, shares, dayHigh, dayLow.
    Faster than get_stock_info — use when only price is needed."""
    def _fetch():
        fi = yf.Ticker(ticker).fast_info
        keys = list(fi.keys()) if hasattr(fi, "keys") else []
        result = {}
        for k in keys:
            try:
                result[k] = fi[k]
            except Exception:
                pass
        return _to_json(result)
    return await _run(_fetch)


# ------------------------------------------------------------------ #
# Price history                                                        #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_stock_history", tags={"market", "finance", "price"})
async def get_stock_history(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
) -> list[dict]:
    """OHLCV price history for a ticker.
    period: 1d / 5d / 1mo / 3mo / 6mo / 1y / 2y / 5y / 10y / ytd / max.
    interval: 1m / 5m / 15m / 1h / 1d / 1wk / 1mo."""
    return await _run(
        lambda: _df_to_records(yf.Ticker(ticker).history(period=period, interval=interval))
    )


# ------------------------------------------------------------------ #
# Financials                                                           #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_income_statement", tags={"market", "finance", "financials"})
async def get_income_statement(ticker: str, quarterly: bool = False) -> dict:
    """Income statement (P&L): revenue, gross profit, EBITDA, net income.
    quarterly=True for last 4 quarters; False for annual (default)."""
    def _fetch():
        t = yf.Ticker(ticker)
        return _df_to_dict(t.quarterly_income_stmt if quarterly else t.income_stmt)
    return await _run(_fetch)


@mcp.tool(name="get_balance_sheet", tags={"market", "finance", "financials"})
async def get_balance_sheet(ticker: str, quarterly: bool = False) -> dict:
    """Balance sheet: total assets, total debt, cash, stockholders equity.
    quarterly=True for last 4 quarters; False for annual (default)."""
    def _fetch():
        t = yf.Ticker(ticker)
        return _df_to_dict(t.quarterly_balance_sheet if quarterly else t.balance_sheet)
    return await _run(_fetch)


@mcp.tool(name="get_cashflow", tags={"market", "finance", "financials"})
async def get_cashflow(ticker: str, quarterly: bool = False) -> dict:
    """Cash flow statement: operating cash flow, capital expenditures, free cash flow.
    quarterly=True for last 4 quarters; False for annual (default)."""
    def _fetch():
        t = yf.Ticker(ticker)
        return _df_to_dict(t.quarterly_cashflow if quarterly else t.cashflow)
    return await _run(_fetch)


# ------------------------------------------------------------------ #
# Analysis                                                             #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_earnings_estimate", tags={"market", "finance", "analysis"})
async def get_earnings_estimate(ticker: str) -> dict:
    """Forward EPS estimates: current quarter (0q), next quarter (+1q), current year (0y), next year (+1y).
    Includes number of analysts, average, low, high, year-ago EPS, growth."""
    return await _run(
        lambda: _df_to_dict(yf.Ticker(ticker).earnings_estimate)
    )


# ------------------------------------------------------------------ #
# Holders                                                              #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_institutional_holders", tags={"market", "finance", "holders"})
async def get_institutional_holders(ticker: str) -> list[dict]:
    """Top institutional holders: fund name, shares held, % of float, value, date reported."""
    return await _run(
        lambda: _df_to_records(yf.Ticker(ticker).institutional_holders)
    )


@mcp.tool(name="get_insider_transactions", tags={"market", "finance", "holders"})
async def get_insider_transactions(ticker: str) -> list[dict]:
    """Recent insider buy/sell transactions: name, title, date, shares, value, transaction type."""
    return await _run(
        lambda: _df_to_records(yf.Ticker(ticker).insider_transactions)
    )


# ------------------------------------------------------------------ #
# News                                                                 #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_stock_news", tags={"market", "news"})
async def get_stock_news(ticker: str, count: int = 10) -> list[dict]:
    """Latest news articles for a specific ticker from Yahoo Finance."""
    return await _run(
        lambda: _to_json(yf.Ticker(ticker).get_news(count=count) or [])
    )


# ------------------------------------------------------------------ #
# Screener / discovery                                                 #
# ------------------------------------------------------------------ #

@mcp.tool(name="lookup_ticker", tags={"market", "screener"})
async def lookup_ticker(query: str) -> list[dict]:
    """Look up ticker symbols by company name or keyword.
    Returns matched stocks, ETFs, mutual funds, indices, futures, currencies."""
    def _fetch():
        results = yf.Lookup(query).get_all(count=20)
        if results is None:
            return []
        if hasattr(results, "to_dict"):
            return _df_to_records(results)
        return _to_json(list(results))
    return await _run(_fetch)


