"""Abstract base class for all data providers."""
from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class DataProvider(ABC):
    """Standard interface for market data providers.

    Each provider implements the methods it supports and returns None
    for capabilities it lacks. The facade layer handles fallback logic.
    """

    @abstractmethod
    def get_quote(self, ticker: str) -> dict | None:
        """Current price quote.

        Returns dict with keys:
            ticker, price, change, change_percent, volume,
            open, high, low, close, timestamp, source
        """

    @abstractmethod
    def get_history(
        self, ticker: str, period: str = "1y"
    ) -> pd.DataFrame | None:
        """OHLCV history as a DataFrame.

        Columns: Date, Open, High, Low, Close, Volume
        Period values: 1mo, 3mo, 6mo, 1y, 5y
        """

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict | None:
        """Company fundamentals: P/E, margins, growth, etc."""

    @abstractmethod
    def get_news(self, ticker: str | None = None, limit: int = 20) -> list | None:
        """News articles. Each item has: title, url, source, datetime, summary, sentiment."""

    @abstractmethod
    def get_calendar(self, days: int = 7) -> list | None:
        """Upcoming economic events / earnings."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if the provider's API key is configured and reachable."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. 'MarketStack')."""

    @property
    @abstractmethod
    def source_tag(self) -> str:
        """Short tag for data attribution (e.g. 'marketstack')."""
