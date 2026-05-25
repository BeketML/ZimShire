from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from mcp_server.services.protocols import MarketDataServiceInterface

_LEGACY_DATA_TYPES = ("info", "financials", "history")


def _to_json(raw: Any) -> Any:
    """Sanitise non-JSON-serialisable types from yfinance (numpy scalars, Timestamps)."""
    return json.loads(json.dumps(raw, default=str))


def _df_to_records(df: Any) -> list[dict]:
    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    return _to_json(df.reset_index().to_dict(orient="records"))


def _df_to_dict(df: Any) -> dict:
    if df is None or (hasattr(df, "empty") and df.empty):
        return {}
    return _to_json(df.to_dict())


class YFinanceDataService(MarketDataServiceInterface):

    async def _run(self, fn, *args) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ------------------------------------------------------------------ #
    # Fundamentals                                                         #
    # ------------------------------------------------------------------ #

    async def get_stock_info(self, ticker: str) -> dict:
        return await self._run(self._fetch_info, ticker)

    def _fetch_info(self, ticker: str) -> dict:
        return _to_json(dict(yf.Ticker(ticker).info))

    async def get_stock_price(self, ticker: str) -> dict:
        return await self._run(self._fetch_price, ticker)

    def _fetch_price(self, ticker: str) -> dict:
        fi = yf.Ticker(ticker).fast_info
        return _to_json({k: getattr(fi, k, None) for k in fi.__dict__})

    # ------------------------------------------------------------------ #
    # Price history                                                        #
    # ------------------------------------------------------------------ #

    async def get_stock_history(
        self, ticker: str, period: str, interval: str
    ) -> list[dict]:
        return await self._run(self._fetch_history, ticker, period, interval)

    def _fetch_history(self, ticker: str, period: str, interval: str) -> list[dict]:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        return _df_to_records(df)

    # ------------------------------------------------------------------ #
    # Financials                                                           #
    # ------------------------------------------------------------------ #

    async def get_income_statement(self, ticker: str, quarterly: bool) -> dict:
        return await self._run(self._fetch_income_stmt, ticker, quarterly)

    def _fetch_income_stmt(self, ticker: str, quarterly: bool) -> dict:
        t = yf.Ticker(ticker)
        df = t.quarterly_income_stmt if quarterly else t.income_stmt
        return _df_to_dict(df)

    async def get_balance_sheet(self, ticker: str, quarterly: bool) -> dict:
        return await self._run(self._fetch_balance_sheet, ticker, quarterly)

    def _fetch_balance_sheet(self, ticker: str, quarterly: bool) -> dict:
        t = yf.Ticker(ticker)
        df = t.quarterly_balance_sheet if quarterly else t.balance_sheet
        return _df_to_dict(df)

    async def get_cashflow(self, ticker: str, quarterly: bool) -> dict:
        return await self._run(self._fetch_cashflow, ticker, quarterly)

    def _fetch_cashflow(self, ticker: str, quarterly: bool) -> dict:
        t = yf.Ticker(ticker)
        df = t.quarterly_cashflow if quarterly else t.cashflow
        return _df_to_dict(df)

    # ------------------------------------------------------------------ #
    # Analysis                                                             #
    # ------------------------------------------------------------------ #

    async def get_analyst_targets(self, ticker: str) -> dict:
        return await self._run(self._fetch_analyst_targets, ticker)

    def _fetch_analyst_targets(self, ticker: str) -> dict:
        targets = yf.Ticker(ticker).analyst_price_targets
        if targets is None:
            return {}
        return _to_json(dict(targets))

    async def get_recommendations(self, ticker: str) -> list[dict]:
        return await self._run(self._fetch_recommendations, ticker)

    def _fetch_recommendations(self, ticker: str) -> list[dict]:
        df = yf.Ticker(ticker).recommendations_summary
        return _df_to_records(df)

    async def get_earnings_estimate(self, ticker: str) -> dict:
        return await self._run(self._fetch_earnings_estimate, ticker)

    def _fetch_earnings_estimate(self, ticker: str) -> dict:
        df = yf.Ticker(ticker).earnings_estimate
        return _df_to_dict(df)

    async def get_upgrades_downgrades(self, ticker: str) -> list[dict]:
        return await self._run(self._fetch_upgrades_downgrades, ticker)

    def _fetch_upgrades_downgrades(self, ticker: str) -> list[dict]:
        df = yf.Ticker(ticker).upgrades_downgrades
        return _df_to_records(df)

    # ------------------------------------------------------------------ #
    # Holders                                                              #
    # ------------------------------------------------------------------ #

    async def get_institutional_holders(self, ticker: str) -> list[dict]:
        return await self._run(self._fetch_institutional_holders, ticker)

    def _fetch_institutional_holders(self, ticker: str) -> list[dict]:
        df = yf.Ticker(ticker).institutional_holders
        return _df_to_records(df)

    async def get_insider_transactions(self, ticker: str) -> list[dict]:
        return await self._run(self._fetch_insider_transactions, ticker)

    def _fetch_insider_transactions(self, ticker: str) -> list[dict]:
        df = yf.Ticker(ticker).insider_transactions
        return _df_to_records(df)

    # ------------------------------------------------------------------ #
    # News                                                                 #
    # ------------------------------------------------------------------ #

    async def get_stock_news(self, ticker: str, count: int) -> list[dict]:
        return await self._run(self._fetch_stock_news, ticker, count)

    def _fetch_stock_news(self, ticker: str, count: int) -> list[dict]:
        news = yf.Ticker(ticker).get_news(count=count)
        return _to_json(news or [])

    # ------------------------------------------------------------------ #
    # Macro                                                                #
    # ------------------------------------------------------------------ #

    async def get_market_summary(self, market: str) -> dict:
        return await self._run(self._fetch_market_summary, market)

    def _fetch_market_summary(self, market: str) -> dict:
        summary = yf.Market(market).summary
        return _to_json(summary or {})

    async def get_calendar_events(self, days_ahead: int) -> dict:
        return await self._run(self._fetch_calendar_events, days_ahead)

    def _fetch_calendar_events(self, days_ahead: int) -> dict:
        end = datetime.now() + timedelta(days=days_ahead)
        cal = yf.Calendars(end=end)
        result: dict = {}
        try:
            df = cal.get_earnings_calendar()
            result["earnings"] = _df_to_records(df)
        except Exception:
            result["earnings"] = []
        try:
            df = cal.get_ipo_info_calendar()
            result["ipo"] = _df_to_records(df)
        except Exception:
            result["ipo"] = []
        try:
            df = cal.get_splits_calendar()
            result["splits"] = _df_to_records(df)
        except Exception:
            result["splits"] = []
        return result

    # ------------------------------------------------------------------ #
    # Screener / discovery                                                 #
    # ------------------------------------------------------------------ #

    async def lookup_ticker(self, query: str) -> list[dict]:
        return await self._run(self._fetch_lookup, query)

    def _fetch_lookup(self, query: str) -> list[dict]:
        results = yf.Lookup(query).get_all(count=20)
        if results is None:
            return []
        if hasattr(results, "to_dict"):
            return _df_to_records(results)
        return _to_json(list(results))

    async def screen_stocks(
        self, sector: str | None, region: str, size: int
    ) -> list[dict]:
        return await self._run(self._fetch_screen, sector, region, size)

    def _fetch_screen(
        self, sector: str | None, region: str, size: int
    ) -> list[dict]:
        query = yf.EquityQuery("eq", ["region", region])
        if sector:
            sector_q = yf.EquityQuery("eq", ["sector", sector])
            query = yf.EquityQuery("and", [query, sector_q])
        result = yf.screen(query, size=size)
        quotes = (result or {}).get("quotes", [])
        return _to_json(quotes)

    # ------------------------------------------------------------------ #
    # Backward compat                                                      #
    # ------------------------------------------------------------------ #

    async def get_data(self, ticker: str, data_type: str) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_legacy, ticker, data_type)

    def _fetch_legacy(self, ticker: str, data_type: str) -> dict:
        if data_type not in _LEGACY_DATA_TYPES:
            raise ValueError(
                f"Unsupported data_type {data_type!r}. Choose from: {_LEGACY_DATA_TYPES}"
            )
        t = yf.Ticker(ticker)
        if data_type == "info":
            return _to_json(dict(t.info))
        if data_type == "financials":
            df = t.financials
            return _df_to_dict(df)
        df = t.history(period="1mo")
        return _to_json(df.reset_index().to_dict(orient="records"))
