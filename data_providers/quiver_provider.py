"""Quiver Quant data provider — congressional trades, dark pool, lobbying, gov contracts.

API docs: https://www.quiverquant.com/api
Authentication via Bearer token in Authorization header.
"""
import logging
import time

import pandas as pd
import requests

from data_providers.base import DataProvider

logger = logging.getLogger("quiver")

BASE_URL = "https://api.quiverquant.com/beta"

REQUEST_TIMEOUT = 10

CACHE_TTL = 1800  # 30 minutes for all endpoints


class QuiverProvider(DataProvider):
    """Quiver Quant API provider for alternative / political data."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._congress_cache: dict[str, tuple[float, list]] = {}
        self._dark_pool_cache: dict[str, tuple[float, list]] = {}
        self._lobbying_cache: dict[str, tuple[float, list]] = {}
        self._gov_contracts_cache: dict[str, tuple[float, list]] = {}

    @property
    def name(self) -> str:
        return "Quiver Quant"

    @property
    def source_tag(self) -> str:
        return "quiver"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str) -> list | dict | None:
        """Make an authenticated GET request to the Quiver Quant API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "Quiver %s returned %d: %s",
                endpoint, resp.status_code, resp.text[:200],
            )
            return None
        except requests.RequestException as exc:
            logger.error("Quiver request failed: %s", exc)
            return None

    def get_congressional_trades(self, ticker: str | None = None) -> list | None:
        """Get congressional trading data.

        If ticker is provided, returns trades for that ticker.
        Otherwise returns bulk congressional trading data.

        Each trade includes: Representative, Party, Transaction, Range,
        ReportDate, TransactionDate, etc.
        """
        cache_key = ticker or "__bulk__"
        now = time.time()
        cached = self._congress_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        if ticker:
            endpoint = f"historical/congresstrading/{ticker}"
        else:
            endpoint = "bulk/congresstrading"

        data = self._get(endpoint)
        if not data or not isinstance(data, list):
            return None

        # Keep PascalCase keys from the API for frontend compatibility
        trades = []
        for item in data:
            trades.append({
                "Representative": item.get("Representative"),
                "Party": item.get("Party"),
                "Transaction": item.get("Transaction"),
                "Range": item.get("Range"),
                "ReportDate": item.get("ReportDate"),
                "TransactionDate": item.get("TransactionDate"),
                "Ticker": item.get("Ticker", ticker),
                "House": item.get("House"),
                "Amount": item.get("Amount"),
                "ExcessReturn": item.get("ExcessReturn"),
                "source": self.source_tag,
            })

        self._congress_cache[cache_key] = (now, trades)
        return trades

    def get_dark_pool(self, ticker: str) -> list | None:
        """Get dark pool volume data for a ticker."""
        now = time.time()
        cached = self._dark_pool_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"historical/offexchange/{ticker}")
        if not data or not isinstance(data, list):
            return None

        # Limit to last 90 days to avoid huge payloads
        entries = []
        for item in data[-90:]:
            entries.append({
                "date": item.get("Date"),
                "otc_short": item.get("OTC_Short"),
                "otc_total": item.get("OTC_Total"),
                "dpi": item.get("DPI"),
                "ticker": ticker,
                "source": self.source_tag,
            })

        self._dark_pool_cache[ticker] = (now, entries)
        return entries

    def get_lobbying(self, ticker: str) -> list | None:
        """Get lobbying data for a ticker."""
        now = time.time()
        cached = self._lobbying_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"historical/lobbying/{ticker}")
        if not data or not isinstance(data, list):
            return None

        entries = []
        for item in data:
            entries.append({
                "date": item.get("Date"),
                "client": item.get("Client"),
                "amount": item.get("Amount"),
                "issue": item.get("Issue"),
                "specific_issue": item.get("SpecificIssue"),
                "ticker": ticker,
                "source": self.source_tag,
            })

        self._lobbying_cache[ticker] = (now, entries)
        return entries

    def get_gov_contracts(self, ticker: str) -> list | None:
        """Get government contract data for a ticker."""
        now = time.time()
        cached = self._gov_contracts_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"historical/govcontracts/{ticker}")
        if not data or not isinstance(data, list):
            return None

        entries = []
        for item in data:
            entries.append({
                "date": item.get("Date"),
                "amount": item.get("Amount"),
                "agency": item.get("Agency"),
                "description": item.get("Description"),
                "ticker": ticker,
                "source": self.source_tag,
            })

        self._gov_contracts_cache[ticker] = (now, entries)
        return entries

    # -- Standard interface methods: not supported by Quiver --

    def get_quote(self, ticker: str) -> dict | None:
        """Quiver does not provide price quotes."""
        return None

    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        """Quiver does not provide OHLCV history."""
        return None

    def get_fundamentals(self, ticker: str) -> dict | None:
        """Quiver does not provide company fundamentals."""
        return None

    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        """Quiver does not provide news articles."""
        return None

    def get_calendar(self, days: int = 7) -> list | None:
        """Quiver does not provide economic calendar."""
        return None
