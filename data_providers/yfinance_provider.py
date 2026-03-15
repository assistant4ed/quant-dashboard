"""yfinance data provider — wraps existing yfinance logic as a fallback provider."""
import logging
import time

import pandas as pd
import yfinance as yf

from data_providers.base import DataProvider

logger = logging.getLogger("yfinance_provider")

CACHE_TTL = 300
HISTORY_CACHE_TTL = 1800


class YFinanceProvider(DataProvider):
    """yfinance wrapper — free, no API key, but delayed/unreliable."""

    def __init__(self):
        self._quote_cache: dict[str, tuple[float, dict]] = {}
        self._history_cache: dict[str, tuple[float, pd.DataFrame]] = {}

    @property
    def name(self) -> str:
        return "Yahoo Finance"

    @property
    def source_tag(self) -> str:
        return "yfinance"

    def is_available(self) -> bool:
        return True  # no API key needed

    def get_quote(self, ticker: str) -> dict | None:
        now = time.time()
        cached = self._quote_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if hist.empty:
                return None

            current = hist.iloc[-1]
            prev_close = hist.iloc[-2]["Close"] if len(hist) > 1 else current["Open"]
            change = current["Close"] - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0

            quote = {
                "ticker": ticker,
                "price": round(float(current["Close"]), 2),
                "open": round(float(current["Open"]), 2),
                "high": round(float(current["High"]), 2),
                "low": round(float(current["Low"]), 2),
                "close": round(float(current["Close"]), 2),
                "volume": int(current["Volume"]),
                "change": round(float(change), 2),
                "change_percent": round(float(change_pct), 2),
                "timestamp": str(hist.index[-1]),
                "source": self.source_tag,
            }
            self._quote_cache[ticker] = (now, quote)
            return quote
        except Exception as exc:
            logger.warning("yfinance quote failed for %s: %s", ticker, exc)
            return None

    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        cache_key = f"{ticker}_{period}"
        now = time.time()
        cached = self._history_cache.get(cache_key)
        if cached and now - cached[0] < HISTORY_CACHE_TTL:
            return cached[1]

        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            if df.empty:
                return None
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            self._history_cache[cache_key] = (now, df)
            return df
        except Exception as exc:
            logger.warning("yfinance history failed for %s: %s", ticker, exc)
            return None

    def get_fundamentals(self, ticker: str) -> dict | None:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if not info or "symbol" not in info:
                return None
            return {
                "ticker": ticker,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "dividend_yield": info.get("dividendYield"),
                "market_cap": info.get("marketCap"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "profit_margin": info.get("profitMargins"),
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "beta": info.get("beta"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "name": info.get("longName"),
                "source": self.source_tag,
            }
        except Exception as exc:
            logger.warning("yfinance fundamentals failed for %s: %s", ticker, exc)
            return None

    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        try:
            target = ticker or "SPY"
            stock = yf.Ticker(target)
            raw_news = stock.news
            if not raw_news:
                return None
            articles = []
            for item in raw_news[:limit]:
                articles.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "source": item.get("publisher", "Yahoo Finance"),
                    "datetime": item.get("providerPublishTime"),
                    "summary": "",
                    "sentiment": None,
                })
            return articles
        except Exception as exc:
            logger.warning("yfinance news failed: %s", exc)
            return None

    def get_calendar(self, days: int = 7) -> list | None:
        return None  # yfinance doesn't provide economic calendar

    def get_ticker_info(self, ticker: str) -> dict | None:
        """Get basic company info."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                "ticker": info.get("symbol", ticker),
                "name": info.get("longName"),
                "exchange": info.get("exchange"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": info.get("country"),
                "source": self.source_tag,
            }
        except Exception:
            return None
