"""MarketStack data provider — EOD, intraday, splits, dividends.

API docs: https://marketstack.com/documentation
Free tier: 100 req/mo, EOD only, HTTP (no HTTPS), 12 months history.
Paid tiers: HTTPS, intraday, real-time, 30+ years history.
"""
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from data_providers.base import DataProvider

logger = logging.getLogger("marketstack")

BASE_URL = "http://api.marketstack.com/v1"
HTTPS_URL = "https://api.marketstack.com/v1"

CACHE_TTL = 300  # 5 minutes for quotes
HISTORY_CACHE_TTL = 1800  # 30 minutes for history

PERIOD_TO_DAYS = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "5y": 1825,
}


class MarketStackProvider(DataProvider):
    """MarketStack API provider for EOD/intraday stock data."""

    def __init__(self, api_key: str, use_https: bool = True):
        self._api_key = api_key
        self._base = HTTPS_URL if use_https else BASE_URL
        self._quote_cache: dict[str, tuple[float, dict]] = {}
        self._history_cache: dict[str, tuple[float, pd.DataFrame]] = {}

    @property
    def name(self) -> str:
        return "MarketStack"

    @property
    def source_tag(self) -> str:
        return "marketstack"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make an authenticated GET request."""
        req_params = {"access_key": self._api_key}
        if params:
            req_params.update(params)
        try:
            resp = requests.get(
                f"{self._base}/{endpoint}",
                params=req_params,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "MarketStack %s returned %d: %s",
                endpoint, resp.status_code, resp.text[:200],
            )
            return None
        except requests.RequestException as exc:
            logger.error("MarketStack request failed: %s", exc)
            return None

    def get_quote(self, ticker: str) -> dict | None:
        """Get latest EOD quote for a ticker."""
        now = time.time()
        cached = self._quote_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get("eod/latest", {"symbols": ticker, "limit": 1})
        if not data or "data" not in data or not data["data"]:
            return None

        item = data["data"][0]
        quote = {
            "ticker": ticker,
            "price": item.get("close"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
            "change": _safe_float(item.get("close", 0) - item.get("open", 0)),
            "change_percent": _calc_change_pct(item.get("open"), item.get("close")),
            "timestamp": item.get("date"),
            "exchange": item.get("exchange"),
            "source": self.source_tag,
        }
        self._quote_cache[ticker] = (now, quote)
        return quote

    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        """Get EOD OHLCV history."""
        cache_key = f"{ticker}_{period}"
        now = time.time()
        cached = self._history_cache.get(cache_key)
        if cached and now - cached[0] < HISTORY_CACHE_TTL:
            return cached[1]

        days = PERIOD_TO_DAYS.get(period, 365)
        date_from = pd.Timestamp.now() - pd.Timedelta(days=days)
        date_to = pd.Timestamp.now()

        data = self._get("eod", {
            "symbols": ticker,
            "date_from": date_from.strftime("%Y-%m-%d"),
            "date_to": date_to.strftime("%Y-%m-%d"),
            "limit": 1000,
            "sort": "ASC",
        })
        if not data or "data" not in data or not data["data"]:
            return None

        records = data["data"]
        df = pd.DataFrame(records)
        df = df.rename(columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df = df.sort_index()

        self._history_cache[cache_key] = (now, df)
        return df

    def get_splits(self, ticker: str) -> list | None:
        """Get stock split history."""
        data = self._get(f"tickers/{ticker}/splits")
        if not data or "data" not in data:
            return None
        return [
            {
                "date": s.get("date"),
                "factor": s.get("split_factor"),
                "source": self.source_tag,
            }
            for s in data["data"]
        ]

    def get_dividends(self, ticker: str) -> list | None:
        """Get dividend history."""
        data = self._get(f"tickers/{ticker}/dividends")
        if not data or "data" not in data:
            return None
        return [
            {
                "date": d.get("date"),
                "amount": d.get("dividend"),
                "source": self.source_tag,
            }
            for d in data["data"]
        ]

    def get_ticker_info(self, ticker: str) -> dict | None:
        """Get ticker reference data (name, exchange, etc.)."""
        data = self._get(f"tickers/{ticker}")
        if not data:
            return None
        return {
            "ticker": data.get("symbol"),
            "name": data.get("name"),
            "exchange": data.get("stock_exchange", {}).get("name"),
            "mic": data.get("stock_exchange", {}).get("mic"),
            "country": data.get("stock_exchange", {}).get("country"),
            "source": self.source_tag,
        }

    def get_fundamentals(self, ticker: str) -> dict | None:
        """MarketStack doesn't provide fundamentals — return None for fallback."""
        return None

    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        """MarketStack doesn't provide news — return None for fallback."""
        return None

    def get_calendar(self, days: int = 7) -> list | None:
        """MarketStack doesn't provide economic calendar — return None for fallback."""
        return None

    def get_exchanges(self) -> list | None:
        """List all available exchanges."""
        data = self._get("exchanges")
        if not data or "data" not in data:
            return None
        return [
            {
                "name": ex.get("name"),
                "mic": ex.get("mic"),
                "country": ex.get("country"),
                "city": ex.get("city"),
                "timezone": ex.get("timezone", {}).get("timezone"),
            }
            for ex in data["data"]
        ]


def _safe_float(value) -> float | None:
    """Convert to float, returning None for invalid values."""
    if value is None:
        return None
    try:
        f = float(value)
        if pd.isna(f) or not np.isfinite(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None


def _calc_change_pct(open_price, close_price) -> float | None:
    """Calculate percentage change from open to close."""
    if not open_price or not close_price or open_price == 0:
        return None
    return round(((close_price - open_price) / open_price) * 100, 2)
