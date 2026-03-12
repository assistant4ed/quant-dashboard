"""
Persistent IBKR session manager for day trading.

Runs a background daemon thread that maintains the IBKR Client Portal
gateway connection by periodically tickling the session, validating
SSO tokens, and checking authentication status. Automatically
reconnects when the session drops.

Usage:
    from ibkr_session import session_manager

    session_manager.start()      # begin keepalive loop
    session_manager.get_status()  # inspect connection health
    session_manager.stop()        # graceful shutdown
"""

import logging
import threading
import time
from datetime import datetime, timezone

from ibkr_client import (
    _get,
    _post,
    auto_reconnect,
    check_auth_status,
    get_account_summary,
    get_accounts,
    tickle,
)

logger = logging.getLogger("ibkr.session")

# ---------------------------------------------------------------------------
# Timing constants (seconds)
# ---------------------------------------------------------------------------
TICKLE_INTERVAL = 55         # IBKR timeout is 5 min; tickle well under that
AUTH_CHECK_INTERVAL = 120    # verify auth every 2 minutes
SSO_VALIDATE_INTERVAL = 300  # validate SSO token every 5 minutes
LOOP_SLEEP = 1               # main-loop resolution

# Error log cap to prevent unbounded memory growth
MAX_ERROR_LOG_ENTRIES = 500


class IbkrSessionManager:
    """Singleton-style persistent session manager for IBKR gateway.

    Spawns a daemon thread that keeps the IBKR Client Portal session
    alive and automatically reconnects on authentication failures.
    """

    def __init__(self):
        self._running = False
        self._thread = None
        self._status = "disconnected"
        self._is_authenticated = False
        self._last_tickle = None
        self._last_auth_check = None
        self._last_sso_validate = None
        self._reconnect_count = 0
        self._error_log = []
        self._session_started = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the keepalive daemon thread.

        Safe to call multiple times; subsequent calls are no-ops while
        the thread is already running.
        """
        with self._lock:
            if self._running:
                logger.info("Session manager already running")
                return

            self._running = True
            self._session_started = datetime.now(timezone.utc)
            self._status = "connecting"
            self._thread = threading.Thread(
                target=self._keepalive_loop,
                name="ibkr-session-keepalive",
                daemon=True,
            )
            self._thread.start()
            logger.info("IBKR session manager started")

    def stop(self):
        """Gracefully stop the keepalive thread."""
        with self._lock:
            if not self._running:
                logger.info("Session manager is not running")
                return

            self._running = False

        # Wait for the thread outside the lock to avoid deadlock
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

        with self._lock:
            self._status = "disconnected"
            self._is_authenticated = False

        logger.info("IBKR session manager stopped")

    def get_status(self):
        """Return a snapshot of current session health.

        Returns:
            dict with connection status, uptime, timestamps, and errors.
        """
        with self._lock:
            uptime = 0.0
            if self._session_started is not None:
                delta = datetime.now(timezone.utc) - self._session_started
                uptime = delta.total_seconds()

            is_day_trading_ready = (
                self._status == "connected"
                and self._is_authenticated
                and self._running
            )

            return {
                "status": self._status,
                "authenticated": self._is_authenticated,
                "uptime_seconds": round(uptime, 1),
                "last_tickle": (
                    self._last_tickle.isoformat()
                    if self._last_tickle else None
                ),
                "last_auth_check": (
                    self._last_auth_check.isoformat()
                    if self._last_auth_check else None
                ),
                "last_sso_validate": (
                    self._last_sso_validate.isoformat()
                    if self._last_sso_validate else None
                ),
                "reconnect_count": self._reconnect_count,
                "error_log": list(self._error_log),
                "session_started": (
                    self._session_started.isoformat()
                    if self._session_started else None
                ),
                "is_running": self._running,
                "is_day_trading_ready": is_day_trading_ready,
            }

    def ensure_connected(self):
        """Quick connectivity check with automatic reconnect.

        Designed to be called before any API request to guarantee
        the session is alive. Returns True when the session is usable.
        """
        auth = check_auth_status()
        if auth.get("authenticated") and auth.get("connected"):
            with self._lock:
                self._status = "connected"
                self._is_authenticated = True
            return True

        logger.warning("ensure_connected: session is down, reconnecting")
        return self._attempt_reconnect()

    def configure_day_trading(self):
        """Validate that the account is ready for day trading.

        Checks:
            - Session is authenticated
            - Account exists and is accessible
            - Account buying power is available
            - Market data subscriptions are reachable

        Returns:
            dict describing readiness and any blocking issues.
        """
        issues = []
        result = {
            "is_ready": False,
            "account_id": None,
            "account_type": None,
            "buying_power": None,
            "market_data_ok": False,
            "issues": issues,
        }

        # 1. Session authentication
        if not self.ensure_connected():
            issues.append("IBKR gateway is not authenticated")
            return result

        # 2. Account lookup
        accounts = get_accounts()
        if not accounts or not isinstance(accounts, list):
            issues.append("No accounts found on IBKR gateway")
            return result

        account = accounts[0]
        account_id = account.get("accountId") or account.get("id")
        if not account_id:
            issues.append("Could not determine account ID")
            return result

        result["account_id"] = account_id
        result["account_type"] = account.get("type", "unknown")

        # 3. Account summary / buying power
        summary = get_account_summary(account_id)
        if summary:
            buying_power = _extract_buying_power(summary)
            result["buying_power"] = buying_power
            if buying_power is not None and buying_power <= 0:
                issues.append(
                    f"Insufficient buying power: ${buying_power:,.2f}"
                )
        else:
            issues.append("Could not retrieve account summary")

        # 4. Market data probe -- tickle returns session metadata
        #    including 'isFT' (is paper/funded) and 'ssoExpires'
        tickle_result = tickle()
        if tickle_result is None:
            issues.append("Market data session unreachable (tickle failed)")
        else:
            result["market_data_ok"] = True

        # 5. Validate SSO token
        sso_result = _post("/sso/validate")
        if not sso_result:
            issues.append("SSO validation failed")

        result["is_ready"] = len(issues) == 0
        return result

    # ------------------------------------------------------------------
    # Internal keepalive loop
    # ------------------------------------------------------------------

    def _keepalive_loop(self):
        """Background loop that maintains the IBKR session.

        Runs on a daemon thread and exits when ``self._running`` is
        set to False.
        """
        logger.info("Keepalive loop started")
        last_tickle_time = 0.0
        last_auth_time = 0.0
        last_sso_time = 0.0

        # Initial connectivity check
        self._run_auth_check()

        while self._running:
            now = time.monotonic()

            try:
                # --- Tickle every TICKLE_INTERVAL seconds ---
                if now - last_tickle_time >= TICKLE_INTERVAL:
                    self._run_tickle()
                    last_tickle_time = now

                # --- Auth check every AUTH_CHECK_INTERVAL seconds ---
                if now - last_auth_time >= AUTH_CHECK_INTERVAL:
                    self._run_auth_check()
                    last_auth_time = now

                # --- SSO validate every SSO_VALIDATE_INTERVAL seconds ---
                if now - last_sso_time >= SSO_VALIDATE_INTERVAL:
                    self._run_sso_validate()
                    last_sso_time = now

            except Exception as exc:
                self._record_error(f"Keepalive loop error: {exc}")
                logger.exception("Unexpected error in keepalive loop")

            # Sleep in small increments so stop() is responsive
            self._interruptible_sleep(LOOP_SLEEP)

        logger.info("Keepalive loop exited")

    # ------------------------------------------------------------------
    # Keepalive sub-tasks
    # ------------------------------------------------------------------

    def _run_tickle(self):
        """Send a tickle to keep the session alive."""
        result = tickle()
        now = datetime.now(timezone.utc)

        with self._lock:
            self._last_tickle = now

        if result is None:
            self._record_error("Tickle failed")
            logger.warning("Tickle failed")
        else:
            logger.debug("Tickle OK")

    def _run_auth_check(self):
        """Verify authentication and reconnect if necessary."""
        auth = check_auth_status()
        now = datetime.now(timezone.utc)

        with self._lock:
            self._last_auth_check = now

        is_authenticated = auth.get("authenticated", False)
        is_connected = auth.get("connected", False)

        if is_authenticated and is_connected:
            with self._lock:
                self._status = "connected"
                self._is_authenticated = True
            logger.debug("Auth check OK: authenticated and connected")
            return

        logger.warning(
            "Auth check failed: authenticated=%s connected=%s",
            is_authenticated,
            is_connected,
        )

        # Session dropped -- attempt reconnect
        self._attempt_reconnect()

    def _run_sso_validate(self):
        """Validate the SSO token."""
        result = _post("/sso/validate")
        now = datetime.now(timezone.utc)

        with self._lock:
            self._last_sso_validate = now

        if result is None:
            self._record_error("SSO validation failed")
            logger.warning("SSO validation failed")
        else:
            logger.debug("SSO validate OK")

    # ------------------------------------------------------------------
    # Reconnect logic
    # ------------------------------------------------------------------

    def _attempt_reconnect(self):
        """Run the auto-reconnect sequence from ibkr_client.

        Returns True on success, False on failure.
        """
        with self._lock:
            self._status = "reconnecting"
            self._is_authenticated = False

        logger.info("Attempting auto-reconnect")
        reconnect_result = auto_reconnect()

        if reconnect_result.get("success"):
            with self._lock:
                self._status = "connected"
                self._is_authenticated = True
                self._reconnect_count += 1
            logger.info(
                "Reconnect succeeded (total reconnects: %d)",
                self._reconnect_count,
            )
            return True

        with self._lock:
            self._status = "error"
            self._is_authenticated = False
            self._reconnect_count += 1

        msg = reconnect_result.get("message", "Unknown reconnect failure")
        self._record_error(f"Reconnect failed: {msg}")
        logger.error("Reconnect failed: %s", msg)
        return False

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _record_error(self, message):
        """Append a timestamped error to the log (capped)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }
        with self._lock:
            self._error_log.append(entry)
            if len(self._error_log) > MAX_ERROR_LOG_ENTRIES:
                self._error_log = self._error_log[-MAX_ERROR_LOG_ENTRIES:]

    def _interruptible_sleep(self, seconds):
        """Sleep in small increments so the loop responds to stop()."""
        increment = 0.25
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(increment)
            elapsed += increment


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_buying_power(summary):
    """Pull buying power from an IBKR account summary dict.

    The shape of the summary varies by account type, so this
    handles several known key paths.
    """
    for key in ("buyingPower", "BuyingPower", "DayTradesRemaining"):
        if key in summary:
            raw = summary[key]
            if isinstance(raw, dict):
                raw = raw.get("amount", raw.get("value"))
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue

    # Fallback: look inside nested accountSummary
    nested = summary.get("accountSummary", {})
    for key in ("buyingPower", "BuyingPower"):
        if key in nested:
            try:
                return float(nested[key])
            except (TypeError, ValueError):
                continue

    return None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
session_manager = IbkrSessionManager()
