"""
Unified broker interface that abstracts over IBKR and Alpaca.

Tries IBKR Client Portal first (if the gateway is reachable and
authenticated), then falls back to Alpaca Markets (if API keys are
configured). This lets the dashboard work seamlessly regardless of
which broker connection is available.

Usage:
    broker = Broker()
    if broker.is_connected():
        account = broker.get_account()
        positions = broker.get_positions()
        broker.place_order("AAPL", 10, "buy", "market")
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("broker")


class BrokerError(Exception):
    """Raised when no broker is available or an operation fails."""


class Broker:
    """Unified broker interface -- tries IBKR first, falls back to Alpaca.

    The broker selection happens once during __init__ and can be
    refreshed by calling refresh(). All trading methods delegate
    to whichever broker is currently active.
    """

    def __init__(self):
        self._ibkr_available = False
        self._alpaca_available = False
        self._alpaca_client = None
        self._ibkr_account_id = None
        self._check_brokers()

    # ------------------------------------------------------------------
    # Broker discovery
    # ------------------------------------------------------------------

    def _check_brokers(self):
        """Probe both brokers and record which ones are reachable."""
        self._ibkr_available = False
        self._alpaca_available = False

        # Try IBKR first
        try:
            from ibkr_client import check_auth_status, get_accounts

            status = check_auth_status()
            if status.get("authenticated") and status.get("connected"):
                accounts = get_accounts()
                if accounts and isinstance(accounts, list) and len(accounts) > 0:
                    self._ibkr_account_id = accounts[0].get("id")
                self._ibkr_available = True
                logger.info("IBKR gateway is connected and authenticated")
        except Exception as exc:
            logger.debug("IBKR not available: %s", exc)

        # Try Alpaca as fallback
        try:
            from alpaca_client import AlpacaClient, AlpacaConfigError

            client = AlpacaClient()
            conn = client.check_connection()
            if conn.get("connected"):
                self._alpaca_client = client
                self._alpaca_available = True
                logger.info(
                    "Alpaca connected (paper=%s)", client.is_paper,
                )
        except Exception as exc:
            logger.debug("Alpaca not available: %s", exc)

        if not self._ibkr_available and not self._alpaca_available:
            logger.warning("No broker connection available")

    def refresh(self):
        """Re-probe broker connections. Call after configuration changes."""
        self._check_brokers()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_connected(self):
        """Return True if at least one broker is reachable."""
        return self._ibkr_available or self._alpaca_available

    def get_broker_name(self):
        """Return the name of the currently active broker.

        Returns "IBKR" if the gateway is connected, "Alpaca" if
        Alpaca keys are configured and valid, or "None" if neither
        is available.
        """
        if self._ibkr_available:
            return "IBKR"
        if self._alpaca_available:
            return "Alpaca"
        return "None"

    def get_status(self):
        """Return a detailed status dict for the /api/broker/status endpoint."""
        return {
            "active_broker": self.get_broker_name(),
            "ibkr_available": self._ibkr_available,
            "alpaca_available": self._alpaca_available,
            "alpaca_paper": (
                self._alpaca_client.is_paper
                if self._alpaca_client else None
            ),
            "connected": self.is_connected(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Account and portfolio
    # ------------------------------------------------------------------

    def get_account(self):
        """Get account information from the active broker.

        Returns a normalised dict with common fields regardless of
        which broker is serving the data.
        """
        if self._ibkr_available:
            return self._ibkr_get_account()
        if self._alpaca_available:
            return self._alpaca_get_account()
        raise BrokerError("No broker connection available")

    def get_positions(self):
        """Get open positions from the active broker."""
        if self._ibkr_available:
            return self._ibkr_get_positions()
        if self._alpaca_available:
            return self._alpaca_get_positions()
        raise BrokerError("No broker connection available")

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(self, symbol, qty, side, order_type, **kwargs):
        """Place an order through the active broker.

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            side: "buy" or "sell"
            order_type: "market", "limit", "stop", "stop_limit"
            **kwargs: Additional order parameters (limit_price,
                      stop_price, time_in_force)
        """
        if self._ibkr_available:
            return self._ibkr_place_order(
                symbol, qty, side, order_type, **kwargs,
            )
        if self._alpaca_available:
            return self._alpaca_place_order(
                symbol, qty, side, order_type, **kwargs,
            )
        raise BrokerError("No broker connection available")

    def get_orders(self, status="open"):
        """List orders from the active broker."""
        if self._ibkr_available:
            return self._ibkr_get_orders(status)
        if self._alpaca_available:
            return self._alpaca_get_orders(status)
        raise BrokerError("No broker connection available")

    def cancel_order(self, order_id):
        """Cancel a specific order by ID."""
        if self._ibkr_available:
            return self._ibkr_cancel_order(order_id)
        if self._alpaca_available:
            return self._alpaca_cancel_order(order_id)
        raise BrokerError("No broker connection available")

    # ------------------------------------------------------------------
    # IBKR backend
    # ------------------------------------------------------------------

    def _ibkr_get_account(self):
        from ibkr_client import get_account_summary, get_accounts

        if not self._ibkr_account_id:
            accounts = get_accounts()
            if accounts and isinstance(accounts, list) and len(accounts) > 0:
                self._ibkr_account_id = accounts[0].get("id")
            else:
                raise BrokerError("No IBKR accounts found")

        summary = get_account_summary(self._ibkr_account_id)
        if not summary:
            raise BrokerError("Failed to fetch IBKR account summary")

        return {
            "broker": "IBKR",
            "account_id": self._ibkr_account_id,
            "equity": _extract_ibkr_value(summary, "netliquidationvalue"),
            "buying_power": _extract_ibkr_value(summary, "buyingpower"),
            "cash": _extract_ibkr_value(summary, "totalcashvalue"),
            "portfolio_value": _extract_ibkr_value(summary, "netliquidationvalue"),
            "raw": summary,
        }

    def _ibkr_get_positions(self):
        from ibkr_client import get_positions

        if not self._ibkr_account_id:
            raise BrokerError("No IBKR account ID available")

        raw_positions = get_positions(self._ibkr_account_id)
        if raw_positions is None:
            raise BrokerError("Failed to fetch IBKR positions")

        positions = []
        for pos in raw_positions:
            positions.append({
                "broker": "IBKR",
                "symbol": pos.get("ticker", pos.get("contractDesc", "")),
                "qty": pos.get("position", 0),
                "market_value": pos.get("mktValue", 0),
                "avg_entry_price": pos.get("avgCost", 0),
                "current_price": pos.get("mktPrice", 0),
                "unrealized_pl": pos.get("unrealizedPnl", 0),
            })
        return positions

    def _ibkr_place_order(self, symbol, qty, side, order_type, **kwargs):
        from ibkr_client import search_contract
        from trading import place_order as ibkr_place

        conid = search_contract(symbol)
        if not conid:
            raise BrokerError(f"Cannot resolve IBKR contract for {symbol}")

        ibkr_type_map = {
            "market": "MKT",
            "limit": "LMT",
            "stop": "STP",
            "stop_limit": "STP_LIMIT",
        }
        mapped_type = ibkr_type_map.get(order_type.lower(), order_type.upper())
        mapped_side = side.upper()
        tif = kwargs.get("time_in_force", "DAY").upper()
        price = kwargs.get("limit_price")

        result = ibkr_place(
            self._ibkr_account_id, conid, mapped_side, int(qty),
            mapped_type, price, tif,
        )
        return {"broker": "IBKR", "order": result}

    def _ibkr_get_orders(self, status):
        from ibkr_client import _get

        result = _get("/iserver/account/orders")
        if result is None:
            return []
        orders = result.get("orders", result) if isinstance(result, dict) else result
        return [
            {"broker": "IBKR", **order}
            for order in (orders if isinstance(orders, list) else [])
        ]

    def _ibkr_cancel_order(self, order_id):
        from ibkr_client import _session, IBKR_BASE_URL, REQUEST_TIMEOUT

        url = (
            f"{IBKR_BASE_URL}/iserver/account"
            f"/{self._ibkr_account_id}/order/{order_id}"
        )
        try:
            resp = _session.delete(url, timeout=REQUEST_TIMEOUT, verify=False)
            resp.raise_for_status()
            return {"broker": "IBKR", "cancelled": True, "order_id": order_id}
        except Exception as exc:
            raise BrokerError(f"IBKR cancel failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Alpaca backend
    # ------------------------------------------------------------------

    def _alpaca_get_account(self):
        account = self._alpaca_client.get_account()
        account["broker"] = "Alpaca"
        return account

    def _alpaca_get_positions(self):
        positions = self._alpaca_client.get_positions()
        for pos in positions:
            pos["broker"] = "Alpaca"
        return positions

    def _alpaca_place_order(self, symbol, qty, side, order_type, **kwargs):
        result = self._alpaca_client.place_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            limit_price=kwargs.get("limit_price"),
            stop_price=kwargs.get("stop_price"),
            time_in_force=kwargs.get("time_in_force", "day"),
        )
        return {"broker": "Alpaca", "order": result}

    def _alpaca_get_orders(self, status):
        orders = self._alpaca_client.get_orders(status=status)
        if isinstance(orders, list):
            for order in orders:
                order["broker"] = "Alpaca"
        return orders

    def _alpaca_cancel_order(self, order_id):
        self._alpaca_client.cancel_order(order_id)
        return {"broker": "Alpaca", "cancelled": True, "order_id": order_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_ibkr_value(summary, key):
    """Extract a numeric value from an IBKR account summary dict.

    IBKR returns summary values as nested dicts like:
    {"netliquidationvalue": {"amount": 12345.67, "currency": "USD"}}
    """
    entry = summary.get(key, {})
    if isinstance(entry, dict):
        return entry.get("amount")
    return entry
