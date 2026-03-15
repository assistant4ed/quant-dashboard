"""Finnhub data provider — real-time quotes, candles, news, fundamentals, sentiment.

API docs: https://finnhub.io/docs/api
Free tier: 60 calls/min, real-time US quotes, 1 year candle history.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from data_providers.base import DataProvider

logger = logging.getLogger("finnhub")

BASE_URL = "https://finnhub.io/api/v1"

REQUEST_TIMEOUT = 10

QUOTE_CACHE_TTL = 300  # 5 minutes
HISTORY_CACHE_TTL = 1800  # 30 minutes
NEWS_CACHE_TTL = 600  # 10 minutes
FUNDAMENTALS_CACHE_TTL = 1800  # 30 minutes
SENTIMENT_CACHE_TTL = 600  # 10 minutes
CALENDAR_CACHE_TTL = 1800  # 30 minutes

NEWS_LOOKBACK_DAYS = 7

PERIOD_TO_DAYS = {
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "5y": 1825,
}


class FinnhubProvider(DataProvider):
    """Finnhub API provider for real-time quotes, candles, news, and sentiment."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._quote_cache: dict[str, tuple[float, dict]] = {}
        self._history_cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._news_cache: dict[str, tuple[float, list]] = {}
        self._fundamentals_cache: dict[str, tuple[float, dict]] = {}
        self._sentiment_cache: dict[str, tuple[float, dict]] = {}
        self._calendar_cache: dict[str, tuple[float, list]] = {}

    @property
    def name(self) -> str:
        return "Finnhub"

    @property
    def source_tag(self) -> str:
        return "finnhub"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make an authenticated GET request to the Finnhub API."""
        req_params = {"token": self._api_key}
        if params:
            req_params.update(params)
        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}",
                params=req_params,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "Finnhub %s returned %d: %s",
                endpoint, resp.status_code, resp.text[:200],
            )
            return None
        except requests.RequestException as exc:
            logger.error("Finnhub request failed: %s", exc)
            return None

    def get_quote(self, ticker: str) -> dict | None:
        """Get real-time quote for a ticker.

        Finnhub returns: c (current), d (change), dp (change%),
        h (high), l (low), o (open), pc (prev close), t (timestamp).
        """
        now = time.time()
        cached = self._quote_cache.get(ticker)
        if cached and now - cached[0] < QUOTE_CACHE_TTL:
            return cached[1]

        data = self._get("quote", {"symbol": ticker})
        if not data or data.get("c") is None or data.get("c") == 0:
            return None

        quote = {
            "ticker": ticker,
            "price": data.get("c"),
            "open": data.get("o"),
            "high": data.get("h"),
            "low": data.get("l"),
            "close": data.get("c"),
            "volume": None,
            "change": data.get("d"),
            "change_percent": data.get("dp"),
            "prev_close": data.get("pc"),
            "timestamp": _unix_to_iso(data.get("t")),
            "source": self.source_tag,
        }
        self._quote_cache[ticker] = (now, quote)
        return quote

    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        """Get daily OHLCV candle history.

        Uses resolution=D for daily candles with from/to as unix timestamps.
        """
        cache_key = f"{ticker}_{period}"
        now = time.time()
        cached = self._history_cache.get(cache_key)
        if cached and now - cached[0] < HISTORY_CACHE_TTL:
            return cached[1]

        days = PERIOD_TO_DAYS.get(period, 365)
        unix_now = int(now)
        unix_start = int(now - days * 86400)

        data = self._get("stock/candle", {
            "symbol": ticker,
            "resolution": "D",
            "from": unix_start,
            "to": unix_now,
        })
        if not data or data.get("s") != "ok":
            return None

        timestamps = data.get("t", [])
        if not timestamps:
            return None

        df = pd.DataFrame({
            "Date": pd.to_datetime(timestamps, unit="s", utc=True),
            "Open": data.get("o", []),
            "High": data.get("h", []),
            "Low": data.get("l", []),
            "Close": data.get("c", []),
            "Volume": data.get("v", []),
        })
        df = df.set_index("Date")
        df = df.sort_index()

        self._history_cache[cache_key] = (now, df)
        return df

    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        """Get company news for the last 7 days.

        Returns articles with headline, source, datetime, url, summary, image, sentiment.
        """
        target = ticker or "AAPL"
        cache_key = f"{target}_{limit}"
        now = time.time()
        cached = self._news_cache.get(cache_key)
        if cached and now - cached[0] < NEWS_CACHE_TTL:
            return cached[1]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week_ago = (datetime.now(timezone.utc) - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        data = self._get("company-news", {
            "symbol": target,
            "from": week_ago,
            "to": today,
        })
        if not data or not isinstance(data, list):
            return None

        articles = []
        for item in data[:limit]:
            articles.append({
                "title": item.get("headline", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "datetime": _unix_to_iso(item.get("datetime")),
                "summary": item.get("summary", ""),
                "image": item.get("image", ""),
                "sentiment": item.get("sentiment"),
                "source_provider": self.source_tag,
            })

        self._news_cache[cache_key] = (now, articles)
        return articles

    def get_fundamentals(self, ticker: str) -> dict | None:
        """Get company fundamentals (basic financials / metrics).

        Uses the /stock/metric endpoint with metric=all.
        """
        now = time.time()
        cached = self._fundamentals_cache.get(ticker)
        if cached and now - cached[0] < FUNDAMENTALS_CACHE_TTL:
            return cached[1]

        data = self._get("stock/metric", {
            "symbol": ticker,
            "metric": "all",
        })
        if not data or "metric" not in data:
            return None

        metrics = data["metric"]
        fundamentals = {
            "ticker": ticker,
            "pe_ratio": metrics.get("peBasicExclExtraTTM"),
            "forward_pe": metrics.get("peFwdTTM"),
            "pb_ratio": metrics.get("pbAnnual"),
            "ps_ratio": metrics.get("psAnnual"),
            "ev_ebitda": metrics.get("currentEv/ebitdaAnnual"),
            "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
            "market_cap": metrics.get("marketCapitalization"),
            "revenue_growth": metrics.get("revenueGrowthQuarterlyYoy"),
            "earnings_growth": metrics.get("epsGrowthQuarterlyYoy"),
            "profit_margin": metrics.get("netProfitMarginTTM"),
            "gross_margin": metrics.get("grossMarginTTM"),
            "operating_margin": metrics.get("operatingMarginTTM"),
            "roe": metrics.get("roeTTM"),
            "roa": metrics.get("roaTTM"),
            "debt_to_equity": metrics.get("totalDebt/totalEquityAnnual"),
            "current_ratio": metrics.get("currentRatioAnnual"),
            "beta": metrics.get("beta"),
            "week_52_high": metrics.get("52WeekHigh"),
            "week_52_low": metrics.get("52WeekLow"),
            "sma_10": metrics.get("10DayAverageTradingVolume"),
            "source": self.source_tag,
        }

        self._fundamentals_cache[ticker] = (now, fundamentals)
        return fundamentals

    def get_calendar(self, days: int = 7) -> list | None:
        """Get upcoming economic calendar events."""
        cache_key = str(days)
        now = time.time()
        cached = self._calendar_cache.get(cache_key)
        if cached and now - cached[0] < CALENDAR_CACHE_TTL:
            return cached[1]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

        data = self._get("calendar/economic", {
            "from": today,
            "to": end_date,
        })
        if not data:
            return None

        raw_events = data.get("economicCalendar", {}).get("result", [])
        if not raw_events:
            return None

        events = []
        for item in raw_events:
            events.append({
                "event": item.get("event", ""),
                "country": item.get("country", ""),
                "date": item.get("time", ""),
                "impact": item.get("impact", ""),
                "actual": item.get("actual"),
                "previous": item.get("prev"),
                "estimate": item.get("estimate"),
                "unit": item.get("unit", ""),
                "source": self.source_tag,
            })

        self._calendar_cache[cache_key] = (now, events)
        return events

    def get_sentiment(self, ticker: str) -> dict | None:
        """Get news sentiment scores for a ticker.

        Returns buzz metrics, sentiment scores, and sector averages.
        """
        now = time.time()
        cached = self._sentiment_cache.get(ticker)
        if cached and now - cached[0] < SENTIMENT_CACHE_TTL:
            return cached[1]

        data = self._get("news-sentiment", {"symbol": ticker})
        if not data or "sentiment" not in data:
            return None

        buzz = data.get("buzz", {})
        sentiment_data = data.get("sentiment", {})

        result = {
            "ticker": ticker,
            "buzz_articles_in_last_week": buzz.get("articlesInLastWeek"),
            "buzz_weekly_average": buzz.get("weeklyAverage"),
            "buzz_ratio": buzz.get("buzz"),
            "company_news_score": data.get("companyNewsScore"),
            "sector_average_bullish_percent": data.get("sectorAverageBullishPercent"),
            "sector_average_news_score": data.get("sectorAverageNewsScore"),
            "bearish_percent": sentiment_data.get("bearishPercent"),
            "bullish_percent": sentiment_data.get("bullishPercent"),
            "source": self.source_tag,
        }

        self._sentiment_cache[ticker] = (now, result)
        return result


def _unix_to_iso(unix_ts: int | float | None) -> str | None:
    """Convert a unix timestamp to ISO 8601 string."""
    if unix_ts is None:
        return None
    try:
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None
