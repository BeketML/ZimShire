from __future__ import annotations

import json

from mcp_server.services import factory


def _sanitise(raw):
    return json.loads(json.dumps(raw, default=str))


async def handle_get_market_data(ticker: str, data_type: str) -> dict:
    raw = await factory.get_market_data_service().get_data(ticker, data_type)
    return _sanitise(raw)


async def handle_get_stock_info(ticker: str) -> dict:
    raw = await factory.get_market_data_service().get_stock_info(ticker)
    return _sanitise(raw)


async def handle_get_stock_price(ticker: str) -> dict:
    raw = await factory.get_market_data_service().get_stock_price(ticker)
    return _sanitise(raw)


async def handle_get_stock_history(
    ticker: str, period: str, interval: str
) -> list[dict]:
    raw = await factory.get_market_data_service().get_stock_history(
        ticker, period, interval
    )
    return _sanitise(raw)


async def handle_get_income_statement(ticker: str, quarterly: bool) -> dict:
    raw = await factory.get_market_data_service().get_income_statement(
        ticker, quarterly
    )
    return _sanitise(raw)


async def handle_get_balance_sheet(ticker: str, quarterly: bool) -> dict:
    raw = await factory.get_market_data_service().get_balance_sheet(ticker, quarterly)
    return _sanitise(raw)


async def handle_get_cashflow(ticker: str, quarterly: bool) -> dict:
    raw = await factory.get_market_data_service().get_cashflow(ticker, quarterly)
    return _sanitise(raw)


async def handle_get_analyst_targets(ticker: str) -> dict:
    raw = await factory.get_market_data_service().get_analyst_targets(ticker)
    return _sanitise(raw)


async def handle_get_recommendations(ticker: str) -> list[dict]:
    raw = await factory.get_market_data_service().get_recommendations(ticker)
    return _sanitise(raw)


async def handle_get_earnings_estimate(ticker: str) -> dict:
    raw = await factory.get_market_data_service().get_earnings_estimate(ticker)
    return _sanitise(raw)


async def handle_get_upgrades_downgrades(ticker: str) -> list[dict]:
    raw = await factory.get_market_data_service().get_upgrades_downgrades(ticker)
    return _sanitise(raw)


async def handle_get_institutional_holders(ticker: str) -> list[dict]:
    raw = await factory.get_market_data_service().get_institutional_holders(ticker)
    return _sanitise(raw)


async def handle_get_insider_transactions(ticker: str) -> list[dict]:
    raw = await factory.get_market_data_service().get_insider_transactions(ticker)
    return _sanitise(raw)


async def handle_get_stock_news(ticker: str, count: int) -> list[dict]:
    raw = await factory.get_market_data_service().get_stock_news(ticker, count)
    return _sanitise(raw)


async def handle_get_market_summary(market: str) -> dict:
    raw = await factory.get_market_data_service().get_market_summary(market)
    return _sanitise(raw)


async def handle_get_calendar_events(days_ahead: int) -> dict:
    raw = await factory.get_market_data_service().get_calendar_events(days_ahead)
    return _sanitise(raw)


async def handle_lookup_ticker(query: str) -> list[dict]:
    raw = await factory.get_market_data_service().lookup_ticker(query)
    return _sanitise(raw)


async def handle_screen_stocks(
    sector: str | None, region: str, size: int
) -> list[dict]:
    raw = await factory.get_market_data_service().screen_stocks(sector, region, size)
    return _sanitise(raw)
