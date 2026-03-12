"""
Automated day trading engine combining AI analysis with LightGBM model signals.

Runs a background scan loop that identifies trade candidates from model
predictions and real-time technical indicators, applies risk management
controls, and places orders through the IBKR gateway (or logs them in
paper mode).

Safety defaults:
- paper_mode is True -- live trading must be explicitly enabled
- Daily loss limits enforced on every scan cycle
- Position size capped as a percentage of portfolio
- Full audit trail of every trade decision
"""
import copy
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ibkr_client import (
    check_auth_status,
    get_account_summary,
    get_accounts,
    get_market_snapshot_by_symbols,
    get_positions,
    search_contract,
)
from trading import (
    ai_trade_recommendation,
    execute_ai_trade,
    place_order,
)

logger = logging.getLogger("auto_trader")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"

ET_TIMEZONE = ZoneInfo("America/New_York")
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
EOD_CLOSE_HOUR = 15
EOD_CLOSE_MINUTE = 55
MAX_CANDIDATES = 5
MIN_CANDIDATES = 3

DEFAULT_CONFIG = {
    "max_trades_per_day": 10,
    "max_position_size_pct": 5.0,
    "max_daily_loss_pct": 2.0,
    "max_daily_loss_dollars": 1000,
    "min_confidence": 7,
    "allowed_tickers": [],
    "trading_hours_only": True,
    "use_ai_analysis": True,
    "use_model_signals": True,
    "order_type": "LMT",
    "time_in_force": "DAY",
    "scan_interval_seconds": 300,
    "enable_stop_loss": True,
    "stop_loss_pct": 2.0,
    "enable_take_profit": True,
    "take_profit_pct": 5.0,
    "paper_mode": True,
    "auto_close_eod": True,
}

# Technical indicator thresholds for signal scoring
RSI_OVERSOLD_THRESHOLD = 30
RSI_OVERBOUGHT_THRESHOLD = 70
VOLUME_SPIKE_MULTIPLIER = 1.5
SIGNAL_SCORE_MODEL_WEIGHT = 40
SIGNAL_SCORE_RSI_WEIGHT = 20
SIGNAL_SCORE_MACD_WEIGHT = 15
SIGNAL_SCORE_VOLUME_WEIGHT = 15
SIGNAL_SCORE_PRICE_ACTION_WEIGHT = 10


# ---------------------------------------------------------------------------
# AutoTrader
# ---------------------------------------------------------------------------


class AutoTrader:
    """Automated day trading engine with risk management controls.

    Combines LightGBM model predictions with real-time technical analysis
    to identify and execute intraday trades. All operations are logged
    and constrained by configurable risk limits.
    """

    def __init__(self, config=None):
        self._running = False
        self._thread = None
        self._config = _merge_config(config)
        self._trade_log = []
        self._daily_pnl = 0.0
        self._trades_today = 0
        self._lock = threading.Lock()
        self._next_scan = None
        self._alerts = []
        self._account_id = None
        self._start_time = None
        self._portfolio_value = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the auto-trading loop in a daemon thread.

        Validates IBKR connectivity before launching the scan loop.
        Returns a dict describing the outcome.
        """
        with self._lock:
            if self._running:
                return {"success": False, "error": "Auto-trader is already running"}

            auth = check_auth_status()
            if not auth.get("authenticated"):
                logger.error("IBKR gateway not authenticated -- cannot start")
                return {
                    "success": False,
                    "error": "IBKR gateway not authenticated",
                    "auth_status": auth,
                }

            account_id = self._resolve_account_id()
            if not account_id:
                return {
                    "success": False,
                    "error": "No IBKR account found",
                }

            self._account_id = account_id
            self._running = True
            self._start_time = datetime.now(timezone.utc)
            self._daily_pnl = 0.0
            self._trades_today = 0
            self._alerts = []

            self._thread = threading.Thread(
                target=self._run_loop,
                name="auto-trader-loop",
                daemon=True,
            )
            self._thread.start()

            logger.info(
                "Auto-trader started: paper_mode=%s account=%s",
                self._config["paper_mode"],
                self._account_id,
            )
            return {
                "success": True,
                "paper_mode": self._config["paper_mode"],
                "account_id": self._account_id,
                "config": self._config,
            }

    def stop(self, close_positions=False):
        """Stop the trading loop.

        Args:
            close_positions: If True, close all open day-trade
                positions before stopping.

        Returns a dict describing the outcome.
        """
        with self._lock:
            if not self._running:
                return {"success": False, "error": "Auto-trader is not running"}
            self._running = False

        if close_positions:
            self._close_all_positions()

        logger.info("Auto-trader stopped (close_positions=%s)", close_positions)
        return {
            "success": True,
            "trades_today": self._trades_today,
            "daily_pnl": self._daily_pnl,
        }

    def get_status(self):
        """Return the current operational status of the auto-trader."""
        open_positions = self._get_open_positions()
        portfolio_pnl_pct = 0.0
        if self._portfolio_value and self._portfolio_value > 0:
            portfolio_pnl_pct = round(
                (self._daily_pnl / self._portfolio_value) * 100, 4,
            )

        return {
            "running": self._running,
            "paper_mode": self._config["paper_mode"],
            "trades_today": self._trades_today,
            "daily_pnl": round(self._daily_pnl, 2),
            "daily_pnl_pct": portfolio_pnl_pct,
            "open_positions": open_positions,
            "trade_log": list(self._trade_log),
            "next_scan": (
                self._next_scan.isoformat() if self._next_scan else None
            ),
            "config": dict(self._config),
            "alerts": list(self._alerts),
            "account_id": self._account_id,
            "started_at": (
                self._start_time.isoformat() if self._start_time else None
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def update_config(self, new_config):
        """Update configuration while the engine is running.

        Only known keys from DEFAULT_CONFIG are accepted.

        Args:
            new_config: Dict with configuration overrides.

        Returns the merged configuration.
        """
        if not isinstance(new_config, dict):
            return {"error": "new_config must be a dict"}

        with self._lock:
            for key, value in new_config.items():
                if key in DEFAULT_CONFIG:
                    self._config[key] = value
                    logger.info("Config updated: %s = %s", key, value)
                else:
                    logger.warning("Unknown config key ignored: %s", key)

        return {"success": True, "config": dict(self._config)}

    def get_trade_log(self):
        """Return the full trade audit log."""
        return list(self._trade_log)

    # ------------------------------------------------------------------
    # Main scan loop
    # ------------------------------------------------------------------

    def _run_loop(self):
        """Background loop that scans for opportunities on each interval."""
        logger.info("Scan loop started (interval=%ds)", self._config["scan_interval_seconds"])

        while self._running:
            try:
                self._execute_scan_cycle()
            except Exception as exc:
                logger.error("Scan cycle failed: %s", exc, exc_info=True)
                self._add_alert(f"Scan cycle error: {exc}")

            interval = self._config["scan_interval_seconds"]
            self._next_scan = datetime.now(timezone.utc).replace(
                microsecond=0,
            )
            self._next_scan = _add_seconds(self._next_scan, interval)

            # Sleep in 1-second increments so we can exit quickly on stop()
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Scan loop exited")

    def _execute_scan_cycle(self):
        """Run a single scan cycle: check limits, find candidates, trade."""
        now_et = datetime.now(ET_TIMEZONE)

        # Trading hours gate
        if self._config["trading_hours_only"] and not _is_trading_hours(now_et):
            logger.debug("Outside trading hours -- skipping scan")
            return

        # EOD auto-close
        if (
            self._config["auto_close_eod"]
            and now_et.hour == EOD_CLOSE_HOUR
            and now_et.minute >= EOD_CLOSE_MINUTE
        ):
            logger.info("EOD auto-close triggered at %s", now_et.strftime("%H:%M ET"))
            self._close_all_positions()
            return

        # Refresh portfolio value
        self._refresh_portfolio_value()

        # Daily loss limit check
        if self._is_daily_loss_exceeded():
            logger.warning(
                "Daily loss limit exceeded (pnl=%.2f) -- pausing trading",
                self._daily_pnl,
            )
            self._add_alert(
                f"Daily loss limit exceeded: ${self._daily_pnl:.2f}",
            )
            return

        # Trade count limit
        if self._trades_today >= self._config["max_trades_per_day"]:
            logger.info("Max trades per day reached (%d)", self._trades_today)
            return

        # IBKR connection health
        auth = check_auth_status()
        if not auth.get("authenticated"):
            self._add_alert("IBKR connection lost")
            logger.error("IBKR authentication lost during scan")
            return

        # Generate signals and find candidates
        candidates = self._generate_day_trade_signals()
        if not candidates:
            logger.info("No trade candidates found this cycle")
            return

        # Evaluate top candidates
        for candidate in candidates[:MAX_CANDIDATES]:
            if self._trades_today >= self._config["max_trades_per_day"]:
                break
            if self._is_daily_loss_exceeded():
                break

            self._evaluate_and_trade(candidate)

        # Monitor existing positions for stop-loss / take-profit
        self._monitor_positions()

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def _generate_day_trade_signals(self):
        """Combine model predictions with real-time technical analysis.

        Signal sources:
        1. LightGBM model signal (from predictions.json)
        2. RSI overbought/oversold
        3. MACD crossover
        4. Volume spike detection
        5. Price action (support/resistance proximity)

        Returns a scored list of trade candidates sorted by strength.
        """
        candidates = []

        # Source 1: Model predictions
        model_signals = {}
        if self._config["use_model_signals"]:
            model_signals = self._load_model_predictions()

        # Determine ticker universe
        tickers = self._config["allowed_tickers"]
        if not tickers:
            tickers = [s["ticker"] for s in model_signals.values()]

        if not tickers:
            logger.info("No tickers in universe -- skipping signal generation")
            return []

        # Fetch real-time snapshots for scoring
        snapshots = self._fetch_realtime_data(tickers)

        for ticker in tickers:
            score = 0.0
            signal_details = {}

            # Model signal component
            model_entry = model_signals.get(ticker, {})
            model_signal = model_entry.get("signal", 0)
            if model_signal > 0:
                score += SIGNAL_SCORE_MODEL_WEIGHT * min(model_signal / 0.03, 1.0)
                signal_details["model_signal"] = round(model_signal, 5)
                signal_details["model_rank"] = model_entry.get("rank")

            # Technical components from snapshot
            snap = snapshots.get(ticker, {})
            technical_scores = self._score_technicals(snap)
            score += technical_scores.get("rsi_score", 0)
            score += technical_scores.get("macd_score", 0)
            score += technical_scores.get("volume_score", 0)
            score += technical_scores.get("price_action_score", 0)
            signal_details.update(technical_scores)

            if score > 0:
                candidates.append({
                    "ticker": ticker,
                    "score": round(score, 2),
                    "model_signal": model_signal,
                    "details": signal_details,
                    "side": "BUY" if model_signal > 0 else "SELL",
                    "current_price": snap.get("last"),
                })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        logger.info(
            "Generated %d candidates (top: %s)",
            len(candidates),
            candidates[0]["ticker"] if candidates else "none",
        )
        return candidates

    def _score_technicals(self, snapshot):
        """Score a stock's technical indicators from a market snapshot.

        Returns dict of individual scores and raw indicator values.
        """
        scores = {
            "rsi_score": 0.0,
            "macd_score": 0.0,
            "volume_score": 0.0,
            "price_action_score": 0.0,
        }

        if not snapshot:
            return scores

        # RSI scoring -- oversold conditions favor buy signals
        last_price = snapshot.get("last")
        change_pct = snapshot.get("change_pct")

        if change_pct is not None:
            try:
                pct = float(str(change_pct).replace("%", ""))
                if pct < -2.0:
                    # Significant drop may indicate oversold bounce candidate
                    scores["rsi_score"] = SIGNAL_SCORE_RSI_WEIGHT * 0.7
                elif pct < -1.0:
                    scores["rsi_score"] = SIGNAL_SCORE_RSI_WEIGHT * 0.4
            except (ValueError, TypeError):
                pass
            scores["change_pct"] = change_pct

        # Volume spike scoring
        volume = snapshot.get("volume")
        if volume is not None:
            try:
                vol = float(str(volume).replace(",", ""))
                if vol > 0:
                    scores["volume_score"] = SIGNAL_SCORE_VOLUME_WEIGHT * 0.5
                    scores["volume"] = vol
            except (ValueError, TypeError):
                pass

        # Price action -- proximity to support/resistance
        if last_price is not None:
            try:
                price = float(str(last_price).replace(",", ""))
                low = snapshot.get("low")
                high = snapshot.get("high")
                if low and high:
                    low_f = float(str(low).replace(",", ""))
                    high_f = float(str(high).replace(",", ""))
                    day_range = high_f - low_f
                    if day_range > 0:
                        position_in_range = (price - low_f) / day_range
                        # Price near day low = potential support bounce
                        if position_in_range < 0.3:
                            scores["price_action_score"] = (
                                SIGNAL_SCORE_PRICE_ACTION_WEIGHT * 0.8
                            )
                        elif position_in_range < 0.5:
                            scores["price_action_score"] = (
                                SIGNAL_SCORE_PRICE_ACTION_WEIGHT * 0.4
                            )
            except (ValueError, TypeError):
                pass

        # MACD proxy -- use intraday change direction as a momentum proxy
        if change_pct is not None:
            try:
                pct = float(str(change_pct).replace("%", ""))
                # Positive momentum after a dip = bullish MACD-like signal
                if 0 < pct < 1.0:
                    scores["macd_score"] = SIGNAL_SCORE_MACD_WEIGHT * 0.6
                elif pct >= 1.0:
                    scores["macd_score"] = SIGNAL_SCORE_MACD_WEIGHT * 0.3
            except (ValueError, TypeError):
                pass

        return scores

    # ------------------------------------------------------------------
    # AI-enhanced evaluation
    # ------------------------------------------------------------------

    def _evaluate_and_trade(self, candidate):
        """Evaluate a candidate with optional AI analysis, then trade.

        Args:
            candidate: Dict from _generate_day_trade_signals().
        """
        ticker = candidate["ticker"]
        logger.info(
            "Evaluating candidate: %s (score=%.2f)",
            ticker,
            candidate["score"],
        )

        confidence = self._estimate_confidence(candidate)

        # Optional deep AI analysis
        if self._config["use_ai_analysis"]:
            confidence = self._run_ai_analysis(ticker, candidate, confidence)

        min_confidence = self._config["min_confidence"]
        if confidence < min_confidence:
            logger.info(
                "Skipping %s: confidence %d < min %d",
                ticker,
                confidence,
                min_confidence,
            )
            self._log_trade(
                ticker,
                "SKIP",
                reason=f"confidence {confidence} < min {min_confidence}",
                candidate=candidate,
            )
            return

        # Calculate position size
        quantity, price = self._calculate_position(ticker, candidate)
        if quantity < 1:
            logger.info("Skipping %s: calculated quantity < 1", ticker)
            return

        side = candidate.get("side", "BUY")

        # Execute or paper-log
        if self._config["paper_mode"]:
            self._paper_trade(ticker, side, quantity, price, candidate, confidence)
        else:
            self._live_trade(ticker, side, quantity, price, candidate, confidence)

    def _estimate_confidence(self, candidate):
        """Estimate a confidence score (1-10) from signal components."""
        score = candidate["score"]
        # Map the 0-100 composite score to a 1-10 confidence scale
        max_possible = (
            SIGNAL_SCORE_MODEL_WEIGHT
            + SIGNAL_SCORE_RSI_WEIGHT
            + SIGNAL_SCORE_MACD_WEIGHT
            + SIGNAL_SCORE_VOLUME_WEIGHT
            + SIGNAL_SCORE_PRICE_ACTION_WEIGHT
        )
        normalized = min(score / max_possible, 1.0)
        confidence = max(1, round(normalized * 10))
        return confidence

    def _run_ai_analysis(self, ticker, candidate, base_confidence):
        """Run quick AI analysis and adjust confidence.

        Returns an updated confidence score.
        """
        try:
            from ai_analyst import quick_analyze
            from data_sources import get_full_stock_profile

            stock_data = get_full_stock_profile(ticker)
            ai_result = quick_analyze(ticker, stock_data)

            quick_text = ai_result.get("quick_analysis", "")
            if not quick_text:
                return base_confidence

            # Parse AI sentiment from the quick analysis text
            text_upper = quick_text.upper()
            if "STRONG_BUY" in text_upper or "STRONG BUY" in text_upper:
                return min(base_confidence + 2, 10)
            if "BUY" in text_upper and "SELL" not in text_upper:
                return min(base_confidence + 1, 10)
            if "SELL" in text_upper:
                return max(base_confidence - 2, 1)

            return base_confidence
        except Exception as exc:
            logger.warning("AI analysis failed for %s: %s", ticker, exc)
            return base_confidence

    # ------------------------------------------------------------------
    # Position sizing and execution
    # ------------------------------------------------------------------

    def _calculate_position(self, ticker, candidate):
        """Calculate the number of shares and limit price for a trade.

        Respects the max_position_size_pct configuration.

        Returns (quantity, price).
        """
        price = candidate.get("current_price")
        if price is None:
            return 0, None

        try:
            price = float(str(price).replace(",", ""))
        except (ValueError, TypeError):
            return 0, None

        if price <= 0:
            return 0, None

        portfolio_value = self._portfolio_value or 0
        if portfolio_value <= 0:
            # Conservative fallback
            return 1, round(price, 2)

        max_dollars = portfolio_value * (
            self._config["max_position_size_pct"] / 100.0
        )
        quantity = int(max_dollars / price)
        quantity = max(quantity, 1)

        return quantity, round(price, 2)

    def _paper_trade(self, ticker, side, quantity, price, candidate, confidence):
        """Log a simulated trade in paper mode."""
        trade_record = {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "confidence": confidence,
            "mode": "paper",
            "status": "filled",
            "order_type": self._config["order_type"],
            "score": candidate["score"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_log.append(trade_record)
        self._trades_today += 1

        logger.info(
            "PAPER TRADE: %s %d %s @ $%.2f (confidence=%d, score=%.1f)",
            side,
            quantity,
            ticker,
            price,
            confidence,
            candidate["score"],
        )

    def _live_trade(self, ticker, side, quantity, price, candidate, confidence):
        """Place a real order through the IBKR gateway."""
        # Final IBKR connection check before every live trade
        auth = check_auth_status()
        if not auth.get("authenticated"):
            self._add_alert(f"IBKR disconnected before trading {ticker}")
            logger.error("IBKR auth lost before placing order for %s", ticker)
            return

        conid = search_contract(ticker)
        if not conid:
            logger.error("Could not resolve contract for %s", ticker)
            self._log_trade(ticker, side, reason="conid resolution failed")
            return

        order_type = self._config["order_type"]
        tif = self._config["time_in_force"]
        order_price = price if order_type == "LMT" else None

        logger.info(
            "LIVE TRADE: %s %d %s @ $%s type=%s tif=%s",
            side,
            quantity,
            ticker,
            order_price,
            order_type,
            tif,
        )

        result = place_order(
            account_id=self._account_id,
            conid=conid,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=order_price,
            tif=tif,
        )

        is_success = result.get("success", False)

        trade_record = {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "confidence": confidence,
            "mode": "live",
            "status": "submitted" if is_success else "failed",
            "order_id": result.get("order_id"),
            "order_type": order_type,
            "score": candidate["score"],
            "error": result.get("error"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_log.append(trade_record)

        if is_success:
            self._trades_today += 1
            logger.info(
                "Order submitted: %s %s order_id=%s",
                side,
                ticker,
                result.get("order_id"),
            )
        else:
            self._add_alert(
                f"Order failed for {ticker}: {result.get('error')}",
            )
            logger.error(
                "Order failed for %s: %s", ticker, result.get("error"),
            )

    # ------------------------------------------------------------------
    # Position monitoring
    # ------------------------------------------------------------------

    def _monitor_positions(self):
        """Check all open positions against stop-loss and take-profit."""
        if not self._account_id:
            return

        positions = self._get_open_positions()
        if not positions:
            return

        for pos in positions:
            ticker = pos.get("ticker", "")
            unrealized_pnl = pos.get("unrealized_pnl", 0)
            avg_cost = pos.get("avg_cost", 0)
            quantity = pos.get("quantity", 0)

            if avg_cost <= 0 or quantity == 0:
                continue

            pnl_pct = (unrealized_pnl / (avg_cost * abs(quantity))) * 100

            # Stop-loss check
            if (
                self._config["enable_stop_loss"]
                and pnl_pct <= -self._config["stop_loss_pct"]
            ):
                logger.warning(
                    "STOP-LOSS triggered for %s: pnl=%.2f%%",
                    ticker,
                    pnl_pct,
                )
                self._close_position(pos, reason="stop_loss")

            # Take-profit check
            elif (
                self._config["enable_take_profit"]
                and pnl_pct >= self._config["take_profit_pct"]
            ):
                logger.info(
                    "TAKE-PROFIT triggered for %s: pnl=%.2f%%",
                    ticker,
                    pnl_pct,
                )
                self._close_position(pos, reason="take_profit")

    def _close_position(self, position, reason="manual"):
        """Close a single position by placing an opposing order."""
        ticker = position.get("ticker", "")
        quantity = abs(position.get("quantity", 0))
        conid = position.get("conid")

        if quantity <= 0:
            return

        # Determine the closing side
        is_long = position.get("quantity", 0) > 0
        close_side = "SELL" if is_long else "BUY"

        logger.info(
            "Closing position: %s %d %s (reason=%s)",
            close_side,
            quantity,
            ticker,
            reason,
        )

        if self._config["paper_mode"]:
            trade_record = {
                "ticker": ticker,
                "side": close_side,
                "quantity": quantity,
                "mode": "paper",
                "status": "closed",
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._trade_log.append(trade_record)
            unrealized = position.get("unrealized_pnl", 0)
            self._daily_pnl += unrealized
            return

        if not conid:
            conid = search_contract(ticker)
        if not conid:
            logger.error("Cannot close %s: conid not found", ticker)
            return

        result = place_order(
            account_id=self._account_id,
            conid=conid,
            side=close_side,
            quantity=int(quantity),
            order_type="MKT",
            tif="IOC",
        )

        trade_record = {
            "ticker": ticker,
            "side": close_side,
            "quantity": int(quantity),
            "mode": "live",
            "status": "submitted" if result.get("success") else "failed",
            "reason": reason,
            "order_id": result.get("order_id"),
            "error": result.get("error"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_log.append(trade_record)

    def _close_all_positions(self):
        """Close all open positions (end of day or manual stop)."""
        positions = self._get_open_positions()
        if not positions:
            logger.info("No positions to close")
            return

        logger.info("Closing all %d positions", len(positions))
        for pos in positions:
            self._close_position(pos, reason="eod_close")

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _load_model_predictions(self):
        """Load the latest model predictions from predictions.json.

        Returns a dict keyed by ticker with signal data.
        """
        if not PREDICTIONS_FILE.exists():
            logger.warning("Predictions file not found: %s", PREDICTIONS_FILE)
            return {}

        try:
            with open(PREDICTIONS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load predictions: %s", exc)
            return {}

        signals = {}

        # Consensus top stocks (20-day averaged)
        for stock in data.get("top_stocks", []):
            ticker = stock.get("ticker", "")
            if ticker and stock.get("trend") == "up":
                signals[ticker] = {
                    "ticker": ticker,
                    "signal": stock.get("signal", 0),
                    "consistency": stock.get("consistency", 0),
                    "combined_score": stock.get("combined_score", 0),
                    "rank": stock.get("rank"),
                    "source": "consensus",
                }

        # Single-day top picks (stronger short-term signal)
        for stock in data.get("single_day_top", []):
            ticker = stock.get("ticker", "")
            if ticker:
                existing = signals.get(ticker, {})
                single_signal = stock.get("signal", 0)
                # Use the stronger of consensus vs single-day signal
                if single_signal > existing.get("signal", 0):
                    signals[ticker] = {
                        "ticker": ticker,
                        "signal": single_signal,
                        "consistency": existing.get("consistency", 0),
                        "combined_score": existing.get("combined_score", 0),
                        "rank": stock.get("rank"),
                        "source": "single_day",
                    }

        return signals

    def _fetch_realtime_data(self, tickers):
        """Fetch real-time market snapshots for a list of tickers.

        Returns dict keyed by ticker.
        """
        if not tickers:
            return {}

        try:
            snapshots = get_market_snapshot_by_symbols(tickers)
            if not snapshots:
                return {}
            return {s["symbol"]: s for s in snapshots if s.get("symbol")}
        except Exception as exc:
            logger.error("Real-time data fetch failed: %s", exc)
            return {}

    def _get_open_positions(self):
        """Retrieve current open positions from IBKR."""
        if not self._account_id:
            return []

        try:
            positions = get_positions(self._account_id)
            if not positions or not isinstance(positions, list):
                return []

            result = []
            for pos in positions:
                quantity = pos.get("position", 0)
                if quantity == 0:
                    continue
                result.append({
                    "conid": pos.get("conid"),
                    "ticker": pos.get(
                        "contractDesc",
                        pos.get("ticker", "Unknown"),
                    ),
                    "quantity": quantity,
                    "avg_cost": pos.get("avgCost", 0),
                    "market_value": pos.get("mktValue", 0),
                    "unrealized_pnl": pos.get("unrealizedPnl", 0),
                    "currency": pos.get("currency", "USD"),
                })
            return result
        except Exception as exc:
            logger.error("Failed to get positions: %s", exc)
            return []

    def _refresh_portfolio_value(self):
        """Update the cached portfolio net liquidation value."""
        if not self._account_id:
            return

        try:
            summary = get_account_summary(self._account_id)
            if not summary:
                return

            net_liq = self._extract_net_liquidation(summary)
            if net_liq and net_liq > 0:
                self._portfolio_value = net_liq
        except Exception as exc:
            logger.warning("Portfolio value refresh failed: %s", exc)

    def _resolve_account_id(self):
        """Resolve the IBKR account ID."""
        try:
            accounts = get_accounts()
            if accounts and isinstance(accounts, list) and len(accounts) > 0:
                return (
                    accounts[0].get("accountId")
                    or accounts[0].get("id")
                )
        except Exception as exc:
            logger.error("Account resolution failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Risk management
    # ------------------------------------------------------------------

    def _is_daily_loss_exceeded(self):
        """Check whether the daily loss limit has been breached."""
        # Absolute dollar limit
        if self._daily_pnl <= -abs(self._config["max_daily_loss_dollars"]):
            return True

        # Percentage-of-portfolio limit
        if self._portfolio_value and self._portfolio_value > 0:
            loss_pct = abs(self._daily_pnl) / self._portfolio_value * 100
            if (
                self._daily_pnl < 0
                and loss_pct >= self._config["max_daily_loss_pct"]
            ):
                return True

        return False

    # ------------------------------------------------------------------
    # Logging and alerts
    # ------------------------------------------------------------------

    def _log_trade(self, ticker, side, reason=None, candidate=None):
        """Append an informational entry to the trade log."""
        entry = {
            "ticker": ticker,
            "side": side,
            "reason": reason,
            "score": candidate.get("score") if candidate else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_log.append(entry)

    def _add_alert(self, message):
        """Add a timestamped alert message."""
        self._alerts.append({
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Cap alerts list
        max_alerts = 50
        if len(self._alerts) > max_alerts:
            self._alerts = self._alerts[-max_alerts:]

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_net_liquidation(summary):
        """Extract net liquidation value from an IBKR account summary."""
        if not summary or not isinstance(summary, dict):
            return None

        for key in (
            "netliquidation",
            "netLiquidation",
            "NetLiquidation",
            "totalcashvalue",
        ):
            val = summary.get(key)
            if isinstance(val, dict):
                amount = val.get("amount")
                if amount is not None:
                    try:
                        return float(amount)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(val, (int, float)):
                return float(val)
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _merge_config(user_config):
    """Merge user-supplied config over DEFAULT_CONFIG."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if user_config and isinstance(user_config, dict):
        for key, value in user_config.items():
            if key in DEFAULT_CONFIG:
                merged[key] = value
    return merged


def _is_trading_hours(now_et):
    """Return True if the current ET time is within market hours."""
    if now_et.weekday() >= 5:
        return False

    market_open = now_et.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    market_close = now_et.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )
    return market_open <= now_et <= market_close


def _add_seconds(dt, seconds):
    """Add seconds to a datetime without importing timedelta at the top."""
    from datetime import timedelta
    return dt + timedelta(seconds=seconds)
