"""Data provider factory with automatic fallback cascading.

Usage:
    from data_providers import get_provider, get_quote, get_history

    # Direct provider access
    ms = get_provider("marketstack")
    quote = ms.get_quote("AAPL")

    # Cascading fallback (tries providers in priority order)
    quote = get_quote("AAPL")        # Finnhub -> MarketStack -> yfinance
    hist = get_history("AAPL", "1y") # Finnhub -> MarketStack -> yfinance

    # Alternative data
    short = get_short_interest("AAPL")       # Fintel
    congress = get_congressional_trades("AAPL")  # Quiver
    alt = get_alt_data("AAPL")               # Aggregated alt data
"""
import json
import logging
from pathlib import Path

import pandas as pd

from data_providers.base import DataProvider
from data_providers.finnhub_provider import FinnhubProvider
from data_providers.fintel_provider import FintelProvider
from data_providers.marketstack_provider import MarketStackProvider
from data_providers.quiver_provider import QuiverProvider
from data_providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger("data_providers")

BASE_DIR = Path(__file__).resolve().parent.parent
API_KEYS_FILE = BASE_DIR / "data" / "api_keys.json"

_providers: dict[str, DataProvider] = {}
_initialized = False

# Priority order for fallback cascading (core market data)
PROVIDER_PRIORITY = ["finnhub", "marketstack", "yfinance"]


def _load_api_keys() -> dict:
    """Load API keys from config file."""
    try:
        with open(API_KEYS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load API keys: %s", exc)
        return {}


def _init_providers():
    """Initialize all providers once."""
    global _initialized
    if _initialized:
        return

    keys = _load_api_keys()

    finnhub_key = keys.get("finnhub", "")
    if finnhub_key:
        _providers["finnhub"] = FinnhubProvider(finnhub_key)
        logger.info("Finnhub provider initialized")

    ms_key = keys.get("marketstack", "")
    if ms_key:
        _providers["marketstack"] = MarketStackProvider(ms_key)
        logger.info("MarketStack provider initialized")

    _providers["yfinance"] = YFinanceProvider()
    logger.info("yfinance provider initialized (fallback)")

    fintel_key = keys.get("fintel", "")
    if fintel_key:
        _providers["fintel"] = FintelProvider(fintel_key)
        logger.info("Fintel provider initialized")

    quiver_key = keys.get("quiver", "")
    if quiver_key:
        _providers["quiver"] = QuiverProvider(quiver_key)
        logger.info("Quiver Quant provider initialized")

    _initialized = True


def get_provider(name: str) -> DataProvider | None:
    """Get a specific provider by name."""
    _init_providers()
    return _providers.get(name)


def get_all_providers() -> dict[str, DataProvider]:
    """Get all initialized providers."""
    _init_providers()
    return dict(_providers)


def get_available_providers() -> list[str]:
    """List names of providers with valid API keys."""
    _init_providers()
    return [name for name, p in _providers.items() if p.is_available()]


def provider_status() -> list[dict]:
    """Health check for all providers."""
    _init_providers()
    return [
        {
            "name": p.name,
            "tag": p.source_tag,
            "available": p.is_available(),
        }
        for p in _providers.values()
    ]


# ---------------------------------------------------------------------------
# Cascading data access functions — try providers in priority order
# ---------------------------------------------------------------------------

def get_quote(ticker: str) -> dict | None:
    """Get quote, trying providers in priority order."""
    _init_providers()
    for name in PROVIDER_PRIORITY:
        provider = _providers.get(name)
        if not provider or not provider.is_available():
            continue
        result = provider.get_quote(ticker)
        if result:
            return result
        logger.debug("%s returned no quote for %s, trying next", name, ticker)
    return None


def get_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """Get OHLCV history, trying providers in priority order."""
    _init_providers()
    for name in PROVIDER_PRIORITY:
        provider = _providers.get(name)
        if not provider or not provider.is_available():
            continue
        result = provider.get_history(ticker, period)
        if result is not None and not result.empty:
            return result
        logger.debug("%s returned no history for %s, trying next", name, ticker)
    return None


def get_fundamentals(ticker: str) -> dict | None:
    """Get fundamentals, trying providers in priority order."""
    _init_providers()
    for name in PROVIDER_PRIORITY:
        provider = _providers.get(name)
        if not provider or not provider.is_available():
            continue
        result = provider.get_fundamentals(ticker)
        if result:
            return result
    return None


def get_news(ticker: str | None = None, limit: int = 20) -> list | None:
    """Get news, trying providers in priority order."""
    _init_providers()
    for name in PROVIDER_PRIORITY:
        provider = _providers.get(name)
        if not provider or not provider.is_available():
            continue
        result = provider.get_news(ticker, limit)
        if result:
            return result
    return None


def get_calendar(days: int = 7) -> list | None:
    """Get economic calendar."""
    _init_providers()
    for name in PROVIDER_PRIORITY:
        provider = _providers.get(name)
        if not provider or not provider.is_available():
            continue
        result = provider.get_calendar(days)
        if result:
            return result
    return None


# ---------------------------------------------------------------------------
# Alternative data access functions — specialized providers
# ---------------------------------------------------------------------------

def get_sentiment(ticker: str) -> dict | None:
    """Get news sentiment scores from Finnhub."""
    _init_providers()
    finnhub = _providers.get("finnhub")
    if not finnhub or not finnhub.is_available():
        return None
    return finnhub.get_sentiment(ticker)


def get_short_interest(ticker: str) -> dict | None:
    """Get short interest data from Fintel."""
    _init_providers()
    fintel = _providers.get("fintel")
    if not fintel or not fintel.is_available():
        return None
    return fintel.get_short_interest(ticker)


def get_insider_trades(ticker: str) -> dict | None:
    """Get insider trading activity from Fintel."""
    _init_providers()
    fintel = _providers.get("fintel")
    if not fintel or not fintel.is_available():
        return None
    return fintel.get_insider_trades(ticker)


def get_institutional_ownership(ticker: str) -> dict | None:
    """Get institutional ownership data from Fintel."""
    _init_providers()
    fintel = _providers.get("fintel")
    if not fintel or not fintel.is_available():
        return None
    return fintel.get_institutional_ownership(ticker)


def get_congressional_trades(ticker: str | None = None) -> list | None:
    """Get congressional trading data from Quiver Quant."""
    _init_providers()
    quiver = _providers.get("quiver")
    if not quiver or not quiver.is_available():
        return None
    return quiver.get_congressional_trades(ticker)


def get_dark_pool(ticker: str) -> list | None:
    """Get dark pool volume data from Quiver Quant."""
    _init_providers()
    quiver = _providers.get("quiver")
    if not quiver or not quiver.is_available():
        return None
    return quiver.get_dark_pool(ticker)


def get_alt_data(ticker: str) -> dict:
    """Aggregate all alternative data for a ticker into one dict.

    Combines short interest, insider trades, congressional trades,
    dark pool data, and sentiment into a single response. Each key
    will be None if the corresponding provider is unavailable.
    """
    _init_providers()
    return {
        "ticker": ticker,
        "short_interest": get_short_interest(ticker),
        "insider_trades": get_insider_trades(ticker),
        "institutional_ownership": get_institutional_ownership(ticker),
        "congressional_trades": get_congressional_trades(ticker),
        "dark_pool": get_dark_pool(ticker),
        "sentiment": get_sentiment(ticker),
    }
