"""
Alpaca Markets API client for stock and ETF trading.

A simpler alternative to IBKR that provides:
- Free stock/ETF trading ($0 commissions)
- Built-in paper trading (no gateway process needed)
- Simple REST API with key-based authentication
- No minimum account balance
- WebSocket support for real-time data

Setup:
    1. Create a free account at https://alpaca.markets
    2. Go to https://app.alpaca.markets/paper/dashboard/overview
    3. Click "API Keys" in the sidebar and generate a new key pair
    4. Add keys to dashboard/data/api_keys.json:
       {
           "alpaca_key": "your-api-key-id",
           "alpaca_secret": "your-api-secret-key",
           "alpaca_paper": true
       }
    5. Set alpaca_paper to false only when ready for live trading

API Documentation: https://docs.alpaca.markets/reference
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger("alpaca")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_URL = "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"

API_KEYS_FILE = Path(__file__).resolve().parent / "data" / "api_keys.json"
REQUEST_TIMEOUT = 15
SCREENER_LIMIT = 20
DEFAULT_BAR_LIMIT = 100
MAX_BAR_LIMIT = 10000


class AlpacaConfigError(Exception):
    """Raised when Alpaca API keys are missing or invalid."""


class AlpacaApiError(Exception):
    """Raised when the Alpaca API returns an error response."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AlpacaClient:
    """REST client for the Alpaca Markets trading API.

    Reads credentials from api_keys.json and configures the session
    with the appropriate base URL (paper or live) and auth headers.

    All methods return plain dicts parsed from JSON responses.
    Errors are raised as AlpacaApiError with status code context.
    """

    def __init__(self):
        self._api_key, self._api_secret, self._is_paper = _load_keys()
        self._base_url = ALPACA_PAPER_URL if self._is_paper else ALPACA_LIVE_URL
        self._data_url = ALPACA_DATA_URL
        self._session = requests.Session()
        self._session.headers.update({
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Accept": "application/json",
        })
        logger.info(
            "Alpaca client initialized (paper=%s, base=%s)",
            self._is_paper,
            self._base_url,
        )

    @property
    def is_paper(self):
        """Whether the client is using the paper trading environment."""
        return self._is_paper

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url, params=None):
        """Send a GET request and return parsed JSON."""
        try:
            resp = self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            body = _safe_json(exc.response)
            status = exc.response.status_code if exc.response is not None else None
            message = body.get("message", str(exc)) if isinstance(body, dict) else str(exc)
            logger.error("Alpaca GET %s -> %s: %s", url, status, message)
            raise AlpacaApiError(message, status_code=status, response_body=body) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Alpaca connection failed: %s", exc)
            raise AlpacaApiError("Cannot reach Alpaca API") from exc
        except requests.exceptions.Timeout as exc:
            logger.error("Alpaca request timed out: %s", exc)
            raise AlpacaApiError("Alpaca API request timed out") from exc

    def _post(self, url, payload=None):
        """Send a POST request and return parsed JSON."""
        try:
            resp = self._session.post(
                url, json=payload, timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            body = _safe_json(exc.response)
            status = exc.response.status_code if exc.response is not None else None
            message = body.get("message", str(exc)) if isinstance(body, dict) else str(exc)
            logger.error("Alpaca POST %s -> %s: %s", url, status, message)
            raise AlpacaApiError(message, status_code=status, response_body=body) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Alpaca connection failed: %s", exc)
            raise AlpacaApiError("Cannot reach Alpaca API") from exc

    def _delete(self, url, params=None):
        """Send a DELETE request and return parsed JSON or empty dict."""
        try:
            resp = self._session.delete(
                url, params=params, timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            body = _safe_json(exc.response)
            status = exc.response.status_code if exc.response is not None else None
            message = body.get("message", str(exc)) if isinstance(body, dict) else str(exc)
            logger.error("Alpaca DELETE %s -> %s: %s", url, status, message)
            raise AlpacaApiError(message, status_code=status, response_body=body) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Alpaca connection failed: %s", exc)
            raise AlpacaApiError("Cannot reach Alpaca API") from exc

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def check_connection(self):
        """Verify that API keys are valid and return account status.

        Returns a dict with connection info. No gateway process needed --
        Alpaca uses direct REST calls authenticated by API key headers.
        """
        try:
            account = self.get_account()
            return {
                "connected": True,
                "broker": "Alpaca",
                "paper": self._is_paper,
                "account_id": account.get("id"),
                "status": account.get("status"),
                "currency": account.get("currency"),
            }
        except AlpacaApiError as exc:
            return {
                "connected": False,
                "broker": "Alpaca",
                "paper": self._is_paper,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Account and portfolio
    # ------------------------------------------------------------------

    def get_account(self):
        """Get account information.

        Returns buying power, equity, cash, day trade count, and more.
        See: https://docs.alpaca.markets/reference/getaccount
        """
        raw = self._get(f"{self._base_url}/v2/account")
        return {
            "id": raw.get("id"),
            "status": raw.get("status"),
            "currency": raw.get("currency", "USD"),
            "buying_power": _to_float(raw.get("buying_power")),
            "cash": _to_float(raw.get("cash")),
            "portfolio_value": _to_float(raw.get("portfolio_value")),
            "equity": _to_float(raw.get("equity")),
            "long_market_value": _to_float(raw.get("long_market_value")),
            "short_market_value": _to_float(raw.get("short_market_value")),
            "initial_margin": _to_float(raw.get("initial_margin")),
            "maintenance_margin": _to_float(raw.get("maintenance_margin")),
            "daytrade_count": int(raw.get("daytrade_count", 0)),
            "pattern_day_trader": raw.get("pattern_day_trader", False),
            "trading_blocked": raw.get("trading_blocked", False),
            "account_blocked": raw.get("account_blocked", False),
            "created_at": raw.get("created_at"),
        }

    def get_positions(self):
        """Get all open positions with P&L.

        See: https://docs.alpaca.markets/reference/getallopenpositions
        """
        raw_positions = self._get(f"{self._base_url}/v2/positions")
        positions = []
        for pos in raw_positions:
            positions.append({
                "symbol": pos.get("symbol"),
                "qty": _to_float(pos.get("qty")),
                "side": pos.get("side"),
                "market_value": _to_float(pos.get("market_value")),
                "cost_basis": _to_float(pos.get("cost_basis")),
                "avg_entry_price": _to_float(pos.get("avg_entry_price")),
                "current_price": _to_float(pos.get("current_price")),
                "unrealized_pl": _to_float(pos.get("unrealized_pl")),
                "unrealized_plpc": _to_float(pos.get("unrealized_plpc")),
                "change_today": _to_float(pos.get("change_today")),
                "asset_class": pos.get("asset_class"),
            })
        return positions

    def get_portfolio_history(self, period="1M", timeframe="1D"):
        """Get portfolio value history for charting.

        Args:
            period: "1D", "1W", "1M", "3M", "1A" (1 year), "all"
            timeframe: "1Min", "5Min", "15Min", "1H", "1D"

        See: https://docs.alpaca.markets/reference/getportfoliohistory
        """
        return self._get(
            f"{self._base_url}/v2/account/portfolio/history",
            params={"period": period, "timeframe": timeframe},
        )

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol,
        qty,
        side,
        order_type="market",
        limit_price=None,
        stop_price=None,
        time_in_force="day",
    ):
        """Place a new order.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")
            qty: Number of shares (integer or float for fractional)
            side: "buy" or "sell"
            order_type: "market", "limit", "stop", "stop_limit",
                        "trailing_stop"
            limit_price: Required for limit and stop_limit orders
            stop_price: Required for stop and stop_limit orders
            time_in_force: "day", "gtc", "opg", "cls", "ioc", "fok"

        Returns the created order dict.
        See: https://docs.alpaca.markets/reference/postorder
        """
        payload = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": time_in_force.lower(),
        }
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)

        logger.info(
            "Placing %s %s order: %s x%s (type=%s, tif=%s)",
            side, symbol, order_type, qty, limit_price, time_in_force,
        )
        return self._post(f"{self._base_url}/v2/orders", payload=payload)

    def get_orders(self, status="open", limit=50):
        """List orders filtered by status.

        Args:
            status: "open", "closed", "all"
            limit: Maximum number of orders to return (default 50)

        See: https://docs.alpaca.markets/reference/getallorders
        """
        return self._get(
            f"{self._base_url}/v2/orders",
            params={"status": status, "limit": limit, "direction": "desc"},
        )

    def cancel_order(self, order_id):
        """Cancel a specific order by ID.

        See: https://docs.alpaca.markets/reference/deleteorderbyorderid
        """
        logger.info("Cancelling order %s", order_id)
        return self._delete(f"{self._base_url}/v2/orders/{order_id}")

    def cancel_all_orders(self):
        """Cancel all open orders.

        See: https://docs.alpaca.markets/reference/deleteallorders
        """
        logger.info("Cancelling all open orders")
        return self._delete(f"{self._base_url}/v2/orders")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_quote(self, symbol):
        """Get the latest quote (bid/ask/last) for a symbol.

        See: https://docs.alpaca.markets/reference/stocklatestquote
        """
        raw = self._get(
            f"{self._data_url}/v2/stocks/{symbol.upper()}/quotes/latest",
        )
        quote = raw.get("quote", {})
        return {
            "symbol": raw.get("symbol", symbol.upper()),
            "bid": quote.get("bp"),
            "bid_size": quote.get("bs"),
            "ask": quote.get("ap"),
            "ask_size": quote.get("as"),
            "timestamp": quote.get("t"),
        }

    def get_bars(self, symbol, timeframe="1Day", limit=DEFAULT_BAR_LIMIT):
        """Get historical price bars (OHLCV).

        Args:
            symbol: Ticker symbol
            timeframe: "1Min", "5Min", "15Min", "1Hour", "1Day",
                       "1Week", "1Month"
            limit: Number of bars to return (max 10000)

        See: https://docs.alpaca.markets/reference/stockbars
        """
        clamped_limit = min(limit, MAX_BAR_LIMIT)
        raw = self._get(
            f"{self._data_url}/v2/stocks/{symbol.upper()}/bars",
            params={"timeframe": timeframe, "limit": clamped_limit},
        )
        bars = raw.get("bars", [])
        return [
            {
                "timestamp": bar.get("t"),
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v"),
                "vwap": bar.get("vw"),
                "trade_count": bar.get("n"),
            }
            for bar in bars
        ]

    def get_snapshot(self, symbol):
        """Get a full market snapshot (latest trade, quote, and bar).

        See: https://docs.alpaca.markets/reference/stocksnapshot
        """
        raw = self._get(
            f"{self._data_url}/v2/stocks/{symbol.upper()}/snapshot",
        )
        latest_trade = raw.get("latestTrade", {})
        latest_quote = raw.get("latestQuote", {})
        minute_bar = raw.get("minuteBar", {})
        daily_bar = raw.get("dailyBar", {})
        prev_daily_bar = raw.get("prevDailyBar", {})

        return {
            "symbol": raw.get("symbol", symbol.upper()),
            "latest_trade": {
                "price": latest_trade.get("p"),
                "size": latest_trade.get("s"),
                "timestamp": latest_trade.get("t"),
            },
            "latest_quote": {
                "bid": latest_quote.get("bp"),
                "ask": latest_quote.get("ap"),
                "bid_size": latest_quote.get("bs"),
                "ask_size": latest_quote.get("as"),
            },
            "minute_bar": {
                "open": minute_bar.get("o"),
                "high": minute_bar.get("h"),
                "low": minute_bar.get("l"),
                "close": minute_bar.get("c"),
                "volume": minute_bar.get("v"),
            },
            "daily_bar": {
                "open": daily_bar.get("o"),
                "high": daily_bar.get("h"),
                "low": daily_bar.get("l"),
                "close": daily_bar.get("c"),
                "volume": daily_bar.get("v"),
            },
            "prev_daily_bar": {
                "open": prev_daily_bar.get("o"),
                "high": prev_daily_bar.get("h"),
                "low": prev_daily_bar.get("l"),
                "close": prev_daily_bar.get("c"),
                "volume": prev_daily_bar.get("v"),
            },
        }

    def get_top_movers(self, market_type="stocks"):
        """Get the most active stocks by volume using the screener.

        Args:
            market_type: "stocks" or "etfs" (not yet supported by Alpaca)

        See: https://docs.alpaca.markets/reference/getmovers
        """
        try:
            return self._get(
                f"{self._data_url}/v1beta1/screener/{market_type}/movers",
                params={"top": SCREENER_LIMIT},
            )
        except AlpacaApiError:
            logger.warning("Screener endpoint not available, returning empty")
            return {"gainers": [], "losers": []}

    # ------------------------------------------------------------------
    # Day trading support
    # ------------------------------------------------------------------

    def is_market_open(self):
        """Check whether the US stock market is currently open."""
        clock = self.get_clock()
        return clock.get("is_open", False)

    def get_clock(self):
        """Get the current market clock.

        Returns whether the market is open and the next open/close times.
        See: https://docs.alpaca.markets/reference/getclock
        """
        raw = self._get(f"{self._base_url}/v2/clock")
        return {
            "is_open": raw.get("is_open", False),
            "timestamp": raw.get("timestamp"),
            "next_open": raw.get("next_open"),
            "next_close": raw.get("next_close"),
        }

    def get_calendar(self, start, end):
        """Get the trading calendar between two dates.

        Args:
            start: Start date string "YYYY-MM-DD"
            end: End date string "YYYY-MM-DD"

        See: https://docs.alpaca.markets/reference/getcalendar
        """
        return self._get(
            f"{self._base_url}/v2/calendar",
            params={"start": start, "end": end},
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_keys():
    """Load Alpaca API keys from api_keys.json.

    Returns (api_key, api_secret, is_paper) tuple.
    Raises AlpacaConfigError with setup instructions if keys are missing.
    """
    if not API_KEYS_FILE.exists():
        raise AlpacaConfigError(
            f"API keys file not found at {API_KEYS_FILE}. "
            "Create it with alpaca_key, alpaca_secret, and alpaca_paper fields."
        )

    with open(API_KEYS_FILE, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    api_key = config.get("alpaca_key", "")
    api_secret = config.get("alpaca_secret", "")
    is_paper = config.get("alpaca_paper", True)

    if not api_key or not api_secret:
        raise AlpacaConfigError(
            "Alpaca API keys are not configured. To set up:\n"
            "  1. Create a free account at https://alpaca.markets\n"
            "  2. Go to https://app.alpaca.markets/paper/dashboard/overview\n"
            "  3. Click 'API Keys' in the sidebar\n"
            "  4. Generate a new key pair\n"
            f"  5. Add them to {API_KEYS_FILE}:\n"
            '     {\n'
            '         "alpaca_key": "your-api-key-id",\n'
            '         "alpaca_secret": "your-api-secret-key",\n'
            '         "alpaca_paper": true\n'
            '     }\n'
            "  Set alpaca_paper to false only for live trading."
        )

    return api_key, api_secret, is_paper


def _to_float(value):
    """Safely convert a string or number to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_json(response):
    """Extract JSON body from a response, returning empty dict on failure."""
    if response is None:
        return {}
    try:
        return response.json()
    except (ValueError, AttributeError):
        return {}
