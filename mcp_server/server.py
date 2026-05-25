from __future__ import annotations

from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_server.core.config import settings
from mcp_server.routers import rag_api, web_search_api, yfinance_data_api
from mcp_server.services import factory


@asynccontextmanager
async def lifespan(app: FastMCP):
    await factory.init_services(settings)
    yield
    await factory.close_services()


mcp = FastMCP("ZimShire", lifespan=lifespan)


# ------------------------------------------------------------------ #
# RAG                                                                  #
# ------------------------------------------------------------------ #

@mcp.tool(name="search_buffett_letters", tags={"rag", "research", "buffett"})
async def search_buffett_letters(
    query: str,
    top_k: int = 5,
    letter_years_filter: list[int] | None = None,
) -> list[dict]:
    """Search Buffett shareholder letters using hybrid RAG (dense + sparse vectors, RRF fusion, cross-encoder reranker)."""
    return await rag_api.handle_search_buffett_letters(query, top_k, letter_years_filter)


# ------------------------------------------------------------------ #
# Web Search                                                           #
# ------------------------------------------------------------------ #

@mcp.tool(name="web_search", tags={"web", "search", "organic"})
async def web_search(
    query: str,
    max_results: int = 5,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    """Organic web search via DuckDuckGo (SerpApi). Returns title, url, snippet, date.
    date_filter: d (past day), w (past week), m (past month), y (past year),
    or custom range e.g. 2021-06-15..2024-06-16."""
    return await web_search_api.handle_web_search(query, max_results, region, date_filter)


@mcp.tool(name="web_search_news", tags={"web", "news"})
async def web_search_news(
    query: str,
    max_results: int = 10,
    region: str = "us-en",
    date_filter: str | None = None,
) -> list[dict]:
    """News-only search via DuckDuckGo News (SerpApi). Returns title, url, snippet, source, date, thumbnail.
    date_filter: d (past day), w (past week), m (past month)."""
    return await web_search_api.handle_web_search_news(query, max_results, region, date_filter)


@mcp.tool(name="web_search_knowledge", tags={"web", "knowledge"})
async def web_search_knowledge(query: str) -> dict | None:
    """Knowledge Graph card for an entity (company, person, place) via DuckDuckGo (SerpApi).
    Returns title, description, website, facts dict, profiles, related_topics. Returns null if no card found."""
    return await web_search_api.handle_web_search_knowledge(query)


# ------------------------------------------------------------------ #
# Market — Backward compat                                            #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_market_data", tags={"market", "finance", "yfinance"})
async def get_market_data(ticker: str, data_type: str = "info") -> dict:
    """Fetch stock market data via yfinance. data_type: info | financials | history."""
    return await yfinance_data_api.handle_get_market_data(ticker, data_type)


# ------------------------------------------------------------------ #
# Market — Fundamentals                                               #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_stock_info", tags={"market", "finance", "fundamentals"})
async def get_stock_info(ticker: str) -> dict:
    """Full company overview: sector, market cap, P/E, EPS, dividend yield, description, CEO, employees.
    ticker: e.g. AAPL, MSFT, BRK-B"""
    return await yfinance_data_api.handle_get_stock_info(ticker)


@mcp.tool(name="get_stock_price", tags={"market", "finance", "fundamentals"})
async def get_stock_price(ticker: str) -> dict:
    """Fast current price data: last price, previous close, 52-week high/low, market cap, shares outstanding.
    Faster than get_stock_info — use when only price is needed."""
    return await yfinance_data_api.handle_get_stock_price(ticker)


# ------------------------------------------------------------------ #
# Market — Price History                                              #
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
    return await yfinance_data_api.handle_get_stock_history(ticker, period, interval)


# ------------------------------------------------------------------ #
# Market — Financials                                                 #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_income_statement", tags={"market", "finance", "financials"})
async def get_income_statement(ticker: str, quarterly: bool = False) -> dict:
    """Income statement (P&L): revenue, gross profit, EBITDA, net income.
    quarterly=True for last 4 quarters; False for annual (default)."""
    return await yfinance_data_api.handle_get_income_statement(ticker, quarterly)


@mcp.tool(name="get_balance_sheet", tags={"market", "finance", "financials"})
async def get_balance_sheet(ticker: str, quarterly: bool = False) -> dict:
    """Balance sheet: total assets, total debt, cash, stockholders equity.
    quarterly=True for last 4 quarters; False for annual (default)."""
    return await yfinance_data_api.handle_get_balance_sheet(ticker, quarterly)


@mcp.tool(name="get_cashflow", tags={"market", "finance", "financials"})
async def get_cashflow(ticker: str, quarterly: bool = False) -> dict:
    """Cash flow statement: operating cash flow, capital expenditures, free cash flow.
    quarterly=True for last 4 quarters; False for annual (default)."""
    return await yfinance_data_api.handle_get_cashflow(ticker, quarterly)


# ------------------------------------------------------------------ #
# Market — Analysis                                                   #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_analyst_targets", tags={"market", "finance", "analysis"})
async def get_analyst_targets(ticker: str) -> dict:
    """Analyst price targets consensus: current, low, high, mean, median."""
    return await yfinance_data_api.handle_get_analyst_targets(ticker)


@mcp.tool(name="get_recommendations", tags={"market", "finance", "analysis"})
async def get_recommendations(ticker: str) -> list[dict]:
    """Analyst recommendations summary by period: strongBuy, buy, hold, sell, strongSell counts."""
    return await yfinance_data_api.handle_get_recommendations(ticker)


@mcp.tool(name="get_earnings_estimate", tags={"market", "finance", "analysis"})
async def get_earnings_estimate(ticker: str) -> dict:
    """Forward EPS estimates: current quarter (0q), next quarter (+1q), current year (0y), next year (+1y).
    Includes number of analysts, average, low, high, year-ago EPS, growth."""
    return await yfinance_data_api.handle_get_earnings_estimate(ticker)


@mcp.tool(name="get_upgrades_downgrades", tags={"market", "finance", "analysis"})
async def get_upgrades_downgrades(ticker: str) -> list[dict]:
    """History of analyst rating changes: date, firm, from grade, to grade, action."""
    return await yfinance_data_api.handle_get_upgrades_downgrades(ticker)


# ------------------------------------------------------------------ #
# Market — Holders                                                    #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_institutional_holders", tags={"market", "finance", "holders"})
async def get_institutional_holders(ticker: str) -> list[dict]:
    """Top institutional holders: fund name, shares held, % of float, value, date reported."""
    return await yfinance_data_api.handle_get_institutional_holders(ticker)


@mcp.tool(name="get_insider_transactions", tags={"market", "finance", "holders"})
async def get_insider_transactions(ticker: str) -> list[dict]:
    """Recent insider buy/sell transactions: name, title, date, shares, value, transaction type."""
    return await yfinance_data_api.handle_get_insider_transactions(ticker)


# ------------------------------------------------------------------ #
# Market — News                                                       #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_stock_news", tags={"market", "news"})
async def get_stock_news(ticker: str, count: int = 10) -> list[dict]:
    """Latest news articles for a specific ticker from Yahoo Finance."""
    return await yfinance_data_api.handle_get_stock_news(ticker, count)


# ------------------------------------------------------------------ #
# Market — Macro                                                      #
# ------------------------------------------------------------------ #

@mcp.tool(name="get_market_summary", tags={"market", "macro"})
async def get_market_summary(market: str = "US") -> dict:
    """Market-wide summary: major indices, gainers/losers, crypto, commodities, currencies.
    market: US / GB / ASIA / EUROPE / RATES / COMMODITIES / CURRENCIES / CRYPTOCURRENCIES."""
    return await yfinance_data_api.handle_get_market_summary(market)


@mcp.tool(name="get_calendar_events", tags={"market", "macro"})
async def get_calendar_events(days_ahead: int = 7) -> dict:
    """Upcoming market events: earnings releases, IPOs, stock splits.
    days_ahead: number of days to look ahead (default 7)."""
    return await yfinance_data_api.handle_get_calendar_events(days_ahead)


# ------------------------------------------------------------------ #
# Market — Screener / Discovery                                       #
# ------------------------------------------------------------------ #

@mcp.tool(name="lookup_ticker", tags={"market", "screener"})
async def lookup_ticker(query: str) -> list[dict]:
    """Look up ticker symbols by company name or keyword.
    Returns matched stocks, ETFs, mutual funds, indices, futures, currencies."""
    return await yfinance_data_api.handle_lookup_ticker(query)


@mcp.tool(name="screen_stocks", tags={"market", "screener"})
async def screen_stocks(
    sector: str | None = None,
    region: str = "us",
    size: int = 20,
) -> list[dict]:
    """Screen stocks by region and optional sector.
    sector: technology / financial-services / healthcare / consumer-cyclical / ...
    region: us / gb / de / jp / ...
    size: number of results (default 20, max 250)."""
    return await yfinance_data_api.handle_screen_stocks(sector, region, size)
