"""
Test runner for mcp_server/market/tools.py
Calls each tool directly (bypassing FastMCP), prints a summary, and flags empty/broken responses.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import yfinance as yf

TICKER = "NVDA"
SEP = "-" * 60


def _to_json(raw):
    return json.loads(json.dumps(raw, default=str))


def _df_to_records(df):
    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    return _to_json(df.reset_index().to_dict(orient="records"))


def _df_to_dict(df):
    if df is None or (hasattr(df, "empty") and df.empty):
        return {}
    df = df.copy()
    df.columns = df.columns.astype(str)
    return _to_json(df.to_dict())


def _print_dict(name: str, data: dict, key_hints: list[str]) -> None:
    if not data:
        print(f"[FAIL] {name}: empty response {{}}")
        return
    print(f"[OK]   {name} — {len(data)} keys")
    for k in key_hints:
        val = data.get(k, "<missing>")
        if isinstance(val, str) and len(val) > 120:
            val = val[:120] + "..."
        print(f"       {k}: {val}")


def _print_list(name: str, data: list, row_keys: list[str], max_rows: int = 3) -> None:
    if not data:
        print(f"[FAIL] {name}: empty response []")
        return
    print(f"[OK]   {name} — {len(data)} rows")
    for row in data[:max_rows]:
        parts = []
        for k in row_keys:
            val = row.get(k, "<missing>")
            if isinstance(val, str) and len(val) > 80:
                val = val[:80] + "..."
            parts.append(f"{k}: {val}")
        print("       " + " | ".join(parts))


async def run_all():
    print(f"Ticker: {TICKER}\n{SEP}")

    # 1. get_stock_info
    print(f"\n{SEP}\n[1] get_stock_info")
    try:
        data = _to_json(dict(yf.Ticker(TICKER).info))
        _print_dict("get_stock_info", data, [
            "sector", "industry", "marketCap", "trailingPE",
            "dividendYield", "fullTimeEmployees", "longBusinessSummary",
        ])
    except Exception as e:
        print(f"[FAIL] get_stock_info: {e}")

    # 2. get_stock_price
    print(f"\n{SEP}\n[2] get_stock_price")
    try:
        fi = yf.Ticker(TICKER).fast_info
        keys = list(fi.keys()) if hasattr(fi, "keys") else []
        result = {}
        for k in keys:
            try:
                result[k] = fi[k]
            except Exception:
                pass
        data = _to_json(result)
        _print_dict("get_stock_price", data, [
            "lastPrice", "previousClose", "yearHigh",
            "yearLow", "marketCap", "shares",
        ])
    except Exception as e:
        print(f"[FAIL] get_stock_price: {e}")

    # 3. get_stock_history
    print(f"\n{SEP}\n[3] get_stock_history (period=1mo)")
    try:
        data = _df_to_records(yf.Ticker(TICKER).history(period="1mo", interval="1d"))
        _print_list("get_stock_history", data, ["Date", "Open", "High", "Low", "Close", "Volume"])
    except Exception as e:
        print(f"[FAIL] get_stock_history: {e}")

    # 4. get_income_statement
    print(f"\n{SEP}\n[4] get_income_statement (annual)")
    try:
        data = _df_to_dict(yf.Ticker(TICKER).income_stmt)
        if not data:
            print("[FAIL] get_income_statement: empty response {}")
        else:
            dates = list(data.keys())
            print(f"[OK]   get_income_statement — {len(dates)} periods: {dates[:2]}")
            first = data[dates[0]]
            for metric in ["Total Revenue", "Gross Profit", "EBITDA", "Net Income"]:
                print(f"       {metric}: {first.get(metric, '<missing>')}")
    except Exception as e:
        print(f"[FAIL] get_income_statement: {e}")

    # 5. get_balance_sheet
    print(f"\n{SEP}\n[5] get_balance_sheet (annual)")
    try:
        data = _df_to_dict(yf.Ticker(TICKER).balance_sheet)
        if not data:
            print("[FAIL] get_balance_sheet: empty response {}")
        else:
            dates = list(data.keys())
            print(f"[OK]   get_balance_sheet — {len(dates)} periods: {dates[:2]}")
            first = data[dates[0]]
            for metric in ["Total Assets", "Total Debt", "Cash And Cash Equivalents", "Stockholders Equity"]:
                print(f"       {metric}: {first.get(metric, '<missing>')}")
    except Exception as e:
        print(f"[FAIL] get_balance_sheet: {e}")

    # 6. get_cashflow
    print(f"\n{SEP}\n[6] get_cashflow (annual)")
    try:
        data = _df_to_dict(yf.Ticker(TICKER).cashflow)
        if not data:
            print("[FAIL] get_cashflow: empty response {}")
        else:
            dates = list(data.keys())
            print(f"[OK]   get_cashflow — {len(dates)} periods: {dates[:2]}")
            first = data[dates[0]]
            for metric in ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"]:
                print(f"       {metric}: {first.get(metric, '<missing>')}")
    except Exception as e:
        print(f"[FAIL] get_cashflow: {e}")

    # 7. get_earnings_estimate
    print(f"\n{SEP}\n[7] get_earnings_estimate")
    try:
        data = _df_to_dict(yf.Ticker(TICKER).earnings_estimate)
        _print_dict("get_earnings_estimate", data, [
            "avg", "low", "high", "numberOfAnalysts", "growth",
        ])
    except Exception as e:
        print(f"[FAIL] get_earnings_estimate: {e}")

    # 8. get_institutional_holders
    print(f"\n{SEP}\n[8] get_institutional_holders")
    try:
        data = _df_to_records(yf.Ticker(TICKER).institutional_holders)
        _print_list("get_institutional_holders", data, ["Holder", "Shares", "pctHeld", "Value"])
    except Exception as e:
        print(f"[FAIL] get_institutional_holders: {e}")

    # 9. get_insider_transactions
    print(f"\n{SEP}\n[9] get_insider_transactions")
    try:
        data = _df_to_records(yf.Ticker(TICKER).insider_transactions)
        _print_list("get_insider_transactions", data, ["Insider", "Position", "Transaction", "Shares", "Value"])
    except Exception as e:
        print(f"[FAIL] get_insider_transactions: {e}")

    # 10. get_stock_news
    print(f"\n{SEP}\n[10] get_stock_news (count=3)")
    try:
        raw = yf.Ticker(TICKER).get_news(count=3) or []
        data = _to_json(raw)
        if not data:
            print(f"[FAIL] get_stock_news: empty response []")
        else:
            print(f"[OK]   get_stock_news — {len(data)} articles")
            for article in data[:3]:
                content = article.get("content", {})
                title = content.get("title") or article.get("title", "<missing>")
                provider = (content.get("provider") or {}).get("displayName") or article.get("publisher", "<missing>")
                link = (content.get("canonicalUrl") or {}).get("url") or article.get("link", "<missing>")
                print(f"       title: {str(title)[:80]} | provider: {provider}")
                print(f"       link:  {str(link)[:100]}")
    except Exception as e:
        print(f"[FAIL] get_stock_news: {e}")

    # 11. lookup_ticker
    print(f"\n{SEP}\n[11] lookup_ticker('Berkshire')")
    try:
        results = yf.Lookup("Berkshire").get_all(count=5)
        if results is None:
            data = []
        elif hasattr(results, "to_dict"):
            data = _df_to_records(results)
        else:
            data = _to_json(list(results))
        _print_list("lookup_ticker", data, ["symbol", "shortName", "quoteType", "regularMarketPrice"], max_rows=5)
    except Exception as e:
        print(f"[FAIL] lookup_ticker: {e}")

    print(f"\n{SEP}\nDone.")


if __name__ == "__main__":
    asyncio.run(run_all())
