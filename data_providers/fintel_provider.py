"""Fintel data provider — short interest, insider trades, institutional ownership.

API docs: https://fintel.io/doc/api
Authentication via X-API-KEY header.
"""
import logging
import time

import pandas as pd
import requests

from data_providers.base import DataProvider

logger = logging.getLogger("fintel")

BASE_URL = "https://api.fintel.io"

REQUEST_TIMEOUT = 10

CACHE_TTL = 1800  # 30 minutes for all endpoints


class FintelProvider(DataProvider):
    """Fintel API provider for short interest, insider trades, and institutional data."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._short_interest_cache: dict[str, tuple[float, dict]] = {}
        self._insider_cache: dict[str, tuple[float, dict]] = {}
        self._institutional_cache: dict[str, tuple[float, dict]] = {}

    @property
    def name(self) -> str:
        return "Fintel"

    @property
    def source_tag(self) -> str:
        return "fintel"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str) -> dict | None:
        """Make an authenticated GET request to the Fintel API."""
        headers = {
            "X-API-KEY": self._api_key,
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
                "Fintel %s returned %d: %s",
                endpoint, resp.status_code, resp.text[:200],
            )
            return None
        except requests.RequestException as exc:
            logger.error("Fintel request failed: %s", exc)
            return None

    def get_short_interest(self, ticker: str) -> dict | None:
        """Get short interest data for a ticker.

        Returns symbol, name, exchange, and historical short volume data
        with marketDate, shortVolume, totalVolume, shortVolumeRatio.
        """
        now = time.time()
        cached = self._short_interest_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"web/v/0.0/ss/us/{ticker}")
        if not data:
            return None

        result = {
            "ticker": ticker,
            "symbol": data.get("symbol", ticker),
            "name": data.get("name"),
            "exchange": data.get("exchange"),
            "data": _extract_short_data(data.get("data", [])),
            "source": self.source_tag,
        }

        self._short_interest_cache[ticker] = (now, result)
        return result

    def get_insider_trades(self, ticker: str) -> dict | None:
        """Get insider trading activity for a ticker.

        Returns insider ownership percentage and list of individual
        insider transactions with name, form type, dates, and values.
        """
        now = time.time()
        cached = self._insider_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"web/v/0.0/n/us/{ticker}")
        if not data:
            return None

        raw_insiders = data.get("insiders", [])
        insiders = []
        for insider in raw_insiders:
            insiders.append({
                "name": insider.get("name"),
                "form_type": insider.get("formType"),
                "file_date": insider.get("fileDate"),
                "transaction_date": insider.get("transactionDate"),
                "code": insider.get("code"),
                "shares": insider.get("shares"),
                "value": insider.get("value"),
            })

        result = {
            "ticker": ticker,
            "insider_ownership_pct_float": data.get("insiderOwnershipPercentFloat"),
            "insiders": insiders,
            "source": self.source_tag,
        }

        self._insider_cache[ticker] = (now, result)
        return result

    def get_institutional_ownership(self, ticker: str) -> dict | None:
        """Get institutional ownership data for a ticker.

        Returns list of institutional owners with holdings details.
        """
        now = time.time()
        cached = self._institutional_cache.get(ticker)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        data = self._get(f"web/v/0.0/so/us/{ticker}")
        if not data:
            return None

        raw_owners = data.get("owners", [])
        owners = []
        for owner in raw_owners:
            owners.append({
                "name": owner.get("name"),
                "shares": owner.get("shares"),
                "value": owner.get("value"),
                "change": owner.get("change"),
                "change_percent": owner.get("changePercent"),
                "date_reported": owner.get("dateReported"),
            })

        result = {
            "ticker": ticker,
            "owners": owners,
            "source": self.source_tag,
        }

        self._institutional_cache[ticker] = (now, result)
        return result

    # -- Standard interface methods: not supported by Fintel --

    def get_quote(self, ticker: str) -> dict | None:
        """Fintel does not provide price quotes."""
        return None

    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        """Fintel does not provide OHLCV history."""
        return None

    def get_fundamentals(self, ticker: str) -> dict | None:
        """Fintel does not provide company fundamentals."""
        return None

    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        """Fintel does not provide news articles."""
        return None

    def get_calendar(self, days: int = 7) -> list | None:
        """Fintel does not provide economic calendar."""
        return None


def _extract_short_data(raw_data: list) -> list[dict]:
    """Extract and normalize short interest data points."""
    entries = []
    for item in raw_data:
        entries.append({
            "market_date": item.get("marketDate"),
            "short_volume": item.get("shortVolume"),
            "total_volume": item.get("totalVolume"),
            "short_volume_ratio": item.get("shortVolumeRatio"),
        })
    return entries
