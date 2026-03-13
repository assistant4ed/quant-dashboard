"""Real-time stock monitoring engine for quantitative traders.

Runs a background daemon thread that:
  1. Polls 9 default stocks via yfinance every 2 seconds (30s when market closed)
  2. Recalculates technical signals every 30 seconds
  3. Refreshes factor-engine scores every 60 seconds
  4. Generates SSE-formatted events for browser streaming
  5. Tracks positions, alerts, and price levels
"""
import json
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Generator

import numpy as np
import yfinance as yf

from factor_engine import get_factor_analysis, detect_market_regime, assess_market_bottom

logger = logging.getLogger("monitor")

DEFAULT_WATCHLIST = [
    "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
    "META", "GOOGL", "JPM", "SPY",
]

MAX_WATCHLIST_SIZE = 12
MAX_ALERT_HISTORY = 20

POLL_INTERVAL_MARKET_OPEN = 2
POLL_INTERVAL_MARKET_CLOSED = 30
SIGNAL_REFRESH_INTERVAL = 30
FACTOR_REFRESH_INTERVAL = 60
ML_RETRAIN_INTERVAL = 1800  # 30 minutes
SSE_YIELD_INTERVAL = 1

MIN_STOP_LOSS_PCT = 0.015  # 1.5% minimum below entry
DEFAULT_ATR_TARGET_MULTIPLIER = 2.5
DEFAULT_ATR_STOP_MULTIPLIER = 2.0
GAP_ALERT_THRESHOLD = 0.02  # 2%
VOLUME_SPIKE_ALERT_THRESHOLD = 2.0
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_EXTREME_OVERBOUGHT = 80
STRONG_BUY_VOLUME_SURGE = 1.5
CUT_LOSS_GAP_PCT = 0.03  # 3%


# ---------------------------------------------------------------------------
# Technical indicator calculations
# ---------------------------------------------------------------------------

def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    """Compute RSI from an array of closing prices."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                 period: int = 14) -> float:
    """Compute Average True Range from OHLC data."""
    if len(closes) < period + 1:
        return 0.0
    prev_closes = closes[:-1]
    curr_highs = highs[1:]
    curr_lows = lows[1:]
    tr = np.maximum(
        curr_highs - curr_lows,
        np.maximum(
            np.abs(curr_highs - prev_closes),
            np.abs(curr_lows - prev_closes),
        ),
    )
    return float(np.mean(tr[-period:]))


def _compute_sma(closes: np.ndarray, period: int) -> float:
    """Compute Simple Moving Average for the given period."""
    if len(closes) < period:
        return float(closes[-1]) if len(closes) > 0 else 0.0
    return float(np.mean(closes[-period:]))


def _compute_macd(closes: np.ndarray) -> str:
    """Compute MACD signal: 'bullish' or 'bearish'.

    Uses EMA-12 vs EMA-26 with a 9-period signal line.
    """
    if len(closes) < 35:
        return "bearish"
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd_line = ema_12 - ema_26
    signal_line = _ema(macd_line[-18:], 9)
    if len(signal_line) < 2:
        return "bearish"
    return "bullish" if macd_line[-1] > signal_line[-1] else "bearish"


def _ema(data: np.ndarray, span: int) -> np.ndarray:
    """Compute Exponential Moving Average."""
    if len(data) < span:
        return data.copy()
    alpha = 2.0 / (span + 1)
    result = np.empty_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _compute_bollinger(closes: np.ndarray, period: int = 20,
                       num_std: float = 2.0) -> dict:
    """Compute Bollinger Bands and return position relative to them."""
    if len(closes) < period:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "position": "middle"}
    window = closes[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window))
    upper = middle + num_std * std
    lower = middle - num_std * std
    price = float(closes[-1])

    if price >= upper:
        position = "upper"
    elif price <= lower:
        position = "lower"
    else:
        position = "middle"

    return {"upper": upper, "middle": middle, "lower": lower, "position": position}


def _compute_vwap_estimate(closes: np.ndarray, volumes: np.ndarray) -> float:
    """Estimate VWAP from intraday or recent close/volume data."""
    if len(closes) == 0 or len(volumes) == 0:
        return 0.0
    total_vol = np.sum(volumes[-20:])
    if total_vol == 0:
        return float(closes[-1])
    return float(np.sum(closes[-20:] * volumes[-20:]) / total_vol)


# ---------------------------------------------------------------------------
# Trading decision logic
# ---------------------------------------------------------------------------

def compute_trading_decision(state: dict) -> dict:
    """12-factor quantitative trading decision engine.

    Combines technical signals, 12-factor composite scores, risk-adjusted
    returns, historical regime analogy, and ML predictions to produce
    institutional-grade trading decisions with confidence scoring.
    """
    price = state.get("price", 0)
    if price <= 0:
        return {
            "action": "HOLD",
            "confidence": 1,
            "reason": "No valid price data available",
            "entry_price": None,
            "target_price": None,
            "stop_loss": None,
            "risk_reward": 0.0,
        }

    # --- Extract state variables ---
    rsi = state.get("rsi", 50)
    atr = state.get("atr", 0)
    sma_20 = state.get("sma_20", price)
    sma_50 = state.get("sma_50", price)
    sma_200 = state.get("sma_200", price)
    above_sma20 = state.get("above_sma20", False)
    above_sma50 = state.get("above_sma50", False)
    above_sma200 = state.get("above_sma200", False)
    macd_signal = state.get("macd_signal", "bearish")
    bollinger_position = state.get("bollinger_position", "middle")
    bollinger = state.get("_bollinger", {})
    volume = state.get("volume", 0)
    avg_volume = state.get("avg_volume", 1)
    prev_close = state.get("prev_close", price)
    factor_signal = state.get("factor_signal", "HOLD")
    factor_composite = state.get("factor_composite", 0.0)
    regime = state.get("regime", "BULL")

    # 12-factor group scores
    factor_scores = state.get("factor_scores", {})
    risk_adj_score = factor_scores.get("risk_adjusted", 0.0)
    historical_score = factor_scores.get("historical", 0.0)
    ml_score = factor_scores.get("ml_adaptive", 0.0)
    momentum_score = factor_scores.get("momentum", 0.0)
    value_score = factor_scores.get("value", 0.0)
    quality_score = factor_scores.get("quality", 0.0)
    growth_score = factor_scores.get("growth", 0.0)

    # Risk-reward detail from factor engine
    rr_detail = state.get("risk_reward_detail", {})
    rr_ratio_factor = rr_detail.get("risk_reward_ratio", 0)
    kelly_pct = rr_detail.get("kelly_position_pct", 0)

    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
    is_volume_surge = volume_ratio > STRONG_BUY_VOLUME_SURGE
    gap_pct = (price - prev_close) / prev_close if prev_close > 0 else 0
    price_distance_sma20 = (price - sma_20) / sma_20 if sma_20 > 0 else 0

    # --- Multi-layer signal scoring ---
    # Layer 1: Technical signals (weight 0.30)
    tech_score = 0.0
    tech_reasons = []

    if rsi < RSI_OVERSOLD:
        tech_score += 3.0
        tech_reasons.append(f"RSI oversold {rsi:.0f}")
    elif rsi < 40:
        tech_score += 1.0
    elif rsi > RSI_EXTREME_OVERBOUGHT:
        tech_score -= 3.0
        tech_reasons.append(f"RSI extreme {rsi:.0f}")
    elif rsi > RSI_OVERBOUGHT:
        tech_score -= 2.0

    if macd_signal == "bullish":
        tech_score += 1.5
    else:
        tech_score -= 1.0

    sma_alignment = sum([above_sma20, above_sma50, above_sma200])
    if sma_alignment == 3:
        tech_score += 2.0
        tech_reasons.append("Above all SMAs")
    elif sma_alignment == 0:
        tech_score -= 2.0
        tech_reasons.append("Below all SMAs")
    else:
        tech_score += (sma_alignment - 1.5) * 0.8

    if bollinger_position == "lower":
        tech_score += 1.5
    elif bollinger_position == "upper":
        tech_score -= 1.0

    if is_volume_surge:
        if tech_score > 0:
            tech_score += 1.5
            tech_reasons.append(f"Volume surge {volume_ratio:.1f}x")
        else:
            tech_score -= 1.0

    # Layer 2: Factor engine composite (weight 0.35)
    factor_score_normalized = factor_composite * 2  # scale -5..+5 to -10..+10

    # Layer 3: Risk-adjusted quality (weight 0.15)
    risk_quality = (risk_adj_score + quality_score + value_score) / 3 * 2

    # Layer 4: Forward-looking signals (weight 0.20)
    forward_score = 0.0
    if historical_score > 1:
        forward_score += 2.0
        tech_reasons.append("Historical analogue bullish")
    elif historical_score < -1:
        forward_score -= 2.0
        tech_reasons.append("Historical analogue bearish")

    if ml_score > 1:
        forward_score += 1.5
    elif ml_score < -1:
        forward_score -= 1.5

    if growth_score > 2:
        forward_score += 1.5
    elif growth_score < -2:
        forward_score -= 1.5

    if rr_ratio_factor and rr_ratio_factor > 2:
        forward_score += 1.5
        tech_reasons.append(f"R:R {rr_ratio_factor:.1f}:1")
    elif rr_ratio_factor and rr_ratio_factor < 0.5:
        forward_score -= 1.5

    # --- Weighted composite decision score ---
    decision_score = (
        tech_score * 0.30
        + factor_score_normalized * 0.35
        + risk_quality * 0.15
        + forward_score * 0.20
    )

    # --- Regime adjustment ---
    if regime == "PANIC":
        decision_score *= 0.5  # Dampen in panic — don't chase
        if decision_score > 0 and rsi < RSI_OVERSOLD:
            decision_score *= 1.8  # But amplify contrarian oversold
    elif regime == "EUPHORIA":
        if decision_score > 0:
            decision_score *= 0.7  # Cautious in euphoria

    # --- CUT_LOSS override: immediate danger ---
    action = "HOLD"
    reason_parts = []

    existing_stop = state.get("stop_loss")
    if existing_stop and price < existing_stop:
        action = "CUT_LOSS"
        reason_parts.append(f"Price {price:.2f} below stop {existing_stop:.2f}")
    elif gap_pct < -CUT_LOSS_GAP_PCT and not above_sma200:
        action = "CUT_LOSS"
        reason_parts.append(f"Gap down {gap_pct * 100:.1f}% below SMA200")
    elif not above_sma200 and is_volume_surge and decision_score < -3:
        action = "CUT_LOSS"
        reason_parts.append(
            f"SMA200 break with volume surge, score {decision_score:.1f}"
        )
    else:
        # Score-based decision thresholds
        if decision_score >= 5.0:
            action = "STRONG_BUY"
        elif decision_score >= 2.5:
            action = "BUY"
        elif decision_score <= -5.0:
            action = "STRONG_SELL"
        elif decision_score <= -2.5:
            action = "SELL"
        else:
            action = "HOLD"

        # Build reason from strongest signals
        if tech_reasons:
            reason_parts.extend(tech_reasons[:3])
        if factor_signal != "HOLD":
            reason_parts.append(f"12F: {factor_signal}")
        if regime != "BULL":
            reason_parts.append(f"Regime: {regime}")
        if not reason_parts:
            if decision_score > 0.5:
                reason_parts.append("Lean bullish, awaiting confirmation")
            elif decision_score < -0.5:
                reason_parts.append("Lean bearish, monitoring closely")
            else:
                reason_parts.append("Neutral signals across 12 factors")

    # --- Confidence 1-10 ---
    abs_score = abs(decision_score)
    confidence = min(10, max(1, round(abs_score * 1.2)))

    # Boost for extreme actions
    if action in ("STRONG_BUY", "STRONG_SELL", "CUT_LOSS"):
        confidence = max(confidence, 7)

    # --- Price levels ---
    entry_price = _compute_entry_price(
        price, sma_20, sma_50, sma_200, bollinger, action,
    )
    target_price = _compute_target_price(
        entry_price, atr, sma_20, sma_50, bollinger,
    )
    stop_loss = _compute_stop_loss(entry_price, atr, sma_200, sma_50)

    risk_reward = 0.0
    if entry_price and stop_loss and target_price:
        risk = entry_price - stop_loss
        reward = target_price - entry_price
        if risk > 0:
            risk_reward = round(reward / risk, 2)

    reason = "; ".join(reason_parts) if reason_parts else "No signal"

    return {
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "entry_price": round(entry_price, 2) if entry_price else None,
        "target_price": round(target_price, 2) if target_price else None,
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "risk_reward": risk_reward,
        "decision_score": round(decision_score, 2),
        "kelly_pct": kelly_pct,
    }


def _near_level(price: float, level: float, tolerance_pct: float = 0.02) -> bool:
    """Check if price is within tolerance of a support/resistance level."""
    if level <= 0:
        return False
    return abs(price - level) / level <= tolerance_pct


def _compute_entry_price(price: float, sma_20: float, sma_50: float,
                         sma_200: float, bollinger: dict, action: str) -> float:
    """Determine suggested entry price based on action and nearby support."""
    if action in ("BUY", "STRONG_BUY"):
        # Nearest support below price
        supports = [
            v for v in [bollinger.get("lower", 0), sma_200, sma_50, sma_20]
            if 0 < v < price
        ]
        if supports:
            return max(supports)  # closest support below price
        return price
    return price


def _compute_target_price(entry: float, atr: float, sma_20: float,
                          sma_50: float, bollinger: dict) -> float:
    """Determine take-profit target from resistance levels or ATR."""
    if entry <= 0:
        return 0.0
    resistances = [
        v for v in [bollinger.get("upper", 0), sma_50, sma_20]
        if v > entry
    ]
    if resistances:
        return min(resistances)  # nearest resistance above entry
    # Fallback: entry + 2.5 * ATR
    if atr > 0:
        return entry + DEFAULT_ATR_TARGET_MULTIPLIER * atr
    return entry * 1.05  # 5% default target


def _compute_stop_loss(entry: float, atr: float, sma_200: float,
                       sma_50: float) -> float:
    """Determine stop-loss level from ATR or nearest SMA support."""
    if entry <= 0:
        return 0.0
    # ATR-based stop
    atr_stop = entry - DEFAULT_ATR_STOP_MULTIPLIER * atr if atr > 0 else 0

    # SMA-based stop: below nearest SMA support
    sma_stops = [v * 0.99 for v in [sma_200, sma_50] if 0 < v < entry]

    candidates = [s for s in [atr_stop] + sma_stops if s > 0]
    if candidates:
        stop = max(candidates)  # highest stop that is still below entry
    else:
        stop = entry * (1 - MIN_STOP_LOSS_PCT)

    # Enforce minimum distance
    min_stop = entry * (1 - MIN_STOP_LOSS_PCT)
    if stop > min_stop:
        stop = min_stop

    return stop


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------

def _check_alerts(state: dict, prev_state: dict | None) -> list[dict]:
    """Generate alerts by comparing current state to previous state."""
    alerts = []
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = state.get("ticker", "???")
    rsi = state.get("rsi", 50)
    price = state.get("price", 0)
    prev_close = state.get("prev_close", price)
    volume = state.get("volume", 0)
    avg_volume = state.get("avg_volume", 1)
    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

    prev_rsi = prev_state.get("rsi", 50) if prev_state else 50
    prev_above_sma20 = prev_state.get("above_sma20") if prev_state else None
    prev_above_sma50 = prev_state.get("above_sma50") if prev_state else None
    prev_above_sma200 = prev_state.get("above_sma200") if prev_state else None
    prev_macd = prev_state.get("macd_signal") if prev_state else None

    bollinger = state.get("_bollinger", {})

    def _add(alert_type: str, message: str, severity: str):
        alerts.append({
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": now_iso,
        })

    # RSI crosses
    if prev_rsi >= RSI_OVERSOLD > rsi:
        _add("OPPORTUNITY",
             f"{ticker} RSI crossed below {RSI_OVERSOLD} ({rsi:.1f}) -- oversold bounce setup",
             "high")
    if prev_rsi <= RSI_OVERBOUGHT < rsi:
        _add("WARNING",
             f"{ticker} RSI crossed above {RSI_OVERBOUGHT} ({rsi:.1f}) -- overbought",
             "medium")

    # SMA crosses
    if prev_above_sma20 is not None and prev_above_sma20 != state.get("above_sma20"):
        direction = "above" if state.get("above_sma20") else "below"
        sev = "medium" if direction == "above" else "high"
        _add("BREAKOUT",
             f"{ticker} price crossed {direction} SMA20 ({state.get('sma_20', 0):.2f})",
             sev)

    if prev_above_sma50 is not None and prev_above_sma50 != state.get("above_sma50"):
        direction = "above" if state.get("above_sma50") else "below"
        sev = "high"
        _add("BREAKOUT",
             f"{ticker} price crossed {direction} SMA50 ({state.get('sma_50', 0):.2f})",
             sev)

    if prev_above_sma200 is not None and prev_above_sma200 != state.get("above_sma200"):
        direction = "above" if state.get("above_sma200") else "below"
        sev = "critical" if direction == "below" else "high"
        _add("BREAKOUT",
             f"{ticker} price crossed {direction} SMA200 ({state.get('sma_200', 0):.2f})",
             sev)

    # Volume spike
    if volume_ratio > VOLUME_SPIKE_ALERT_THRESHOLD:
        _add("WARNING",
             f"{ticker} volume spike {volume_ratio:.1f}x average",
             "high")

    # Stop loss hit
    stop_loss = state.get("stop_loss")
    if stop_loss and price > 0 and price <= stop_loss:
        _add("CUT_LOSS",
             f"{ticker} hit stop loss at {stop_loss:.2f} (price {price:.2f})",
             "critical")

    # MACD crossover
    if prev_macd and prev_macd != state.get("macd_signal"):
        direction = state.get("macd_signal", "bearish")
        sev = "medium"
        _add("BREAKOUT",
             f"{ticker} MACD crossover to {direction}",
             sev)

    # Bollinger breakout
    bb_upper = bollinger.get("upper", 0)
    bb_lower = bollinger.get("lower", 0)
    if bb_upper > 0 and price > bb_upper:
        _add("BREAKOUT",
             f"{ticker} broke above upper Bollinger Band ({bb_upper:.2f})",
             "medium")
    if bb_lower > 0 and price < bb_lower:
        _add("OPPORTUNITY",
             f"{ticker} broke below lower Bollinger Band ({bb_lower:.2f})",
             "high")

    # Gap detection
    gap_pct = (price - prev_close) / prev_close if prev_close > 0 else 0
    if abs(gap_pct) > GAP_ALERT_THRESHOLD:
        direction = "up" if gap_pct > 0 else "down"
        sev = "high" if abs(gap_pct) > CUT_LOSS_GAP_PCT else "medium"
        alert_type = "BREAKOUT" if gap_pct > 0 else "WARNING"
        _add(alert_type,
             f"{ticker} gap {direction} {abs(gap_pct) * 100:.1f}% from previous close",
             sev)

    # Favorable risk-reward
    risk_reward = state.get("risk_reward", 0)
    if risk_reward > 3.0:
        _add("OPPORTUNITY",
             f"{ticker} risk/reward ratio very favorable at {risk_reward:.1f}:1",
             "high")

    return alerts


# ---------------------------------------------------------------------------
# Market hours detection
# ---------------------------------------------------------------------------

def _is_market_open() -> bool:
    """Check if US stock market is approximately open (ET 9:30-16:00 weekdays).

    Uses a simplified heuristic; does not account for holidays.
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    if weekday >= 5:  # Saturday or Sunday
        return False
    # ET = UTC-5 (EST) or UTC-4 (EDT). Use UTC-4 for conservative estimate.
    et_hour = (now_utc.hour - 4) % 24
    et_minute = now_utc.minute
    # Market open 9:30 ET to 16:00 ET
    if et_hour < 9 or (et_hour == 9 and et_minute < 30):
        return False
    if et_hour >= 16:
        return False
    return True


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def _batch_fetch_prices(tickers: list[str]) -> dict:
    """Fetch current price data for all tickers in a single yfinance call.

    Returns a dict of ticker -> {price, open, high, low, volume, prev_close,
    bid, ask, avg_volume}.
    """
    result = {}
    if not tickers:
        return result

    try:
        ticker_str = " ".join(tickers)
        data = yf.download(
            ticker_str,
            period="1d",
            interval="1m",
            group_by="ticker",
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            return result

        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = data
                else:
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    df = data[ticker]

                if df.empty:
                    continue

                last_row = df.iloc[-1]
                first_row = df.iloc[0]
                price = float(last_row["Close"])
                if np.isnan(price) or price <= 0:
                    continue

                result[ticker] = {
                    "price": price,
                    "open": _safe_float(first_row.get("Open", price)),
                    "high": _safe_float(df["High"].max()),
                    "low": _safe_float(df["Low"].min()),
                    "volume": int(_safe_float(df["Volume"].sum())),
                }
            except Exception:
                logger.debug("Failed to parse price for %s", ticker, exc_info=True)
    except Exception:
        logger.warning("Batch price fetch failed", exc_info=True)

    # Supplement with individual ticker info for bid/ask/prev_close/avg_volume
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
            entry = result.get(ticker, {})
            entry.setdefault("price", _safe_float(info.get("regularMarketPrice", 0)))
            entry["prev_close"] = _safe_float(
                info.get("regularMarketPreviousClose",
                         info.get("previousClose", entry.get("price", 0)))
            )
            entry["bid"] = _safe_float(info.get("bid", 0))
            entry["ask"] = _safe_float(info.get("ask", 0))
            entry["avg_volume"] = int(_safe_float(
                info.get("averageDailyVolume10Day",
                         info.get("averageVolume", 0))
            ))
            if entry.get("price", 0) > 0:
                result[ticker] = entry
        except Exception:
            logger.debug("Failed to fetch info for %s", ticker, exc_info=True)

    return result


def _fetch_history(ticker: str, period: str = "3mo") -> dict | None:
    """Fetch historical OHLCV data for technical indicator calculation.

    Returns dict with numpy arrays: closes, highs, lows, volumes.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist is None or hist.empty or len(hist) < 5:
            return None
        return {
            "closes": hist["Close"].values.astype(float),
            "highs": hist["High"].values.astype(float),
            "lows": hist["Low"].values.astype(float),
            "volumes": hist["Volume"].values.astype(float),
        }
    except Exception:
        logger.debug("Failed to fetch history for %s", ticker, exc_info=True)
        return None


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# MonitorEngine
# ---------------------------------------------------------------------------

class MonitorEngine:
    """Background engine that polls stocks, computes signals, and streams SSE."""

    def __init__(self, watchlist: list[str] | None = None):
        self._watchlist = list(watchlist or DEFAULT_WATCHLIST)[:MAX_WATCHLIST_SIZE]
        self._states: dict[str, dict] = {}
        self._prev_states: dict[str, dict] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._regime: dict | None = None
        self._regime_updated: float = 0
        self._signals_updated: dict[str, float] = {}
        self._factors_updated: dict[str, float] = {}
        self._history_cache: dict[str, dict] = {}
        self._history_cache_ts: dict[str, float] = {}
        self._pending_alerts: list[dict] = []
        self._ml_training_data: dict[str, list] = {}  # ticker → [(timestamp, factors, price)]
        self._ml_last_retrain: float = 0
        self._ml_model: object = None  # sklearn model
        self._ml_r2: float = 0.0

    # --- Public API ---

    def start(self):
        """Start the background polling thread."""
        if self._running:
            logger.warning("MonitorEngine already running")
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="monitor-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("MonitorEngine started with watchlist: %s", self._watchlist)

    def stop(self):
        """Stop the background polling thread gracefully."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("MonitorEngine stopped")

    def get_states(self) -> dict:
        """Return a copy of all current stock states."""
        with self._lock:
            return {
                ticker: self._sanitize_state(state)
                for ticker, state in self._states.items()
            }

    def get_state(self, ticker: str) -> dict | None:
        """Return a copy of a single stock's state."""
        with self._lock:
            state = self._states.get(ticker.upper())
            if state is None:
                return None
            return self._sanitize_state(state)

    def set_watchlist(self, tickers: list[str]):
        """Update the watchlist (max 12 stocks)."""
        cleaned = [t.upper().strip() for t in tickers if t.strip()]
        cleaned = list(dict.fromkeys(cleaned))[:MAX_WATCHLIST_SIZE]
        with self._lock:
            removed = set(self._watchlist) - set(cleaned)
            self._watchlist = cleaned
            for t in removed:
                self._states.pop(t, None)
                self._prev_states.pop(t, None)
                self._signals_updated.pop(t, None)
                self._factors_updated.pop(t, None)
                self._history_cache.pop(t, None)
                self._history_cache_ts.pop(t, None)
        logger.info("Watchlist updated to: %s", cleaned)

    @property
    def watchlist(self) -> list[str]:
        """Current watchlist."""
        with self._lock:
            return list(self._watchlist)

    def stream_updates(self) -> Generator[str, None, None]:
        """Generator yielding SSE-formatted events.

        Yields initial full state, then incremental updates every second
        and alert events as they occur.
        """
        # Yield initial full state
        with self._lock:
            initial_data = {
                "type": "snapshot",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "regime": self._regime.get("regime") if self._regime else None,
                "bottom_score": self._get_bottom_score(),
                "ml_r2": self._ml_r2,
                "factor_count": 12,
                "stocks": {
                    t: self._sanitize_state(s)
                    for t, s in self._states.items()
                },
            }
        yield f"data: {json.dumps(initial_data, default=str)}\n\n"

        # Continuous update stream
        while self._running:
            time.sleep(SSE_YIELD_INTERVAL)

            # Collect any pending alerts
            alerts_to_send = []
            with self._lock:
                if self._pending_alerts:
                    alerts_to_send = list(self._pending_alerts)
                    self._pending_alerts.clear()

                update_data = {
                    "type": "update",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "regime": self._regime.get("regime") if self._regime else None,
                    "bottom_score": self._get_bottom_score(),
                    "ml_r2": self._ml_r2,
                    "factor_count": 12,
                    "stocks": {
                        t: self._sanitize_state(s)
                        for t, s in self._states.items()
                    },
                }

            yield f"data: {json.dumps(update_data, default=str)}\n\n"

            # Yield individual alert events
            for alert_event in alerts_to_send:
                alert_sse = {
                    "type": "alert",
                    "ticker": alert_event.get("ticker"),
                    "alert": alert_event.get("alert"),
                }
                yield f"data: {json.dumps(alert_sse, default=str)}\n\n"

    # --- Internal polling loop ---

    def _poll_loop(self):
        """Main background loop: fetch prices, compute signals, generate alerts."""
        logger.info("Poll loop started")
        while not self._stop_event.is_set():
            try:
                now = time.time()
                market_open = _is_market_open()
                interval = (
                    POLL_INTERVAL_MARKET_OPEN if market_open
                    else POLL_INTERVAL_MARKET_CLOSED
                )

                with self._lock:
                    current_watchlist = list(self._watchlist)

                # Step 1: Batch fetch prices (every poll)
                self._update_prices(current_watchlist)

                # Step 2: Recalculate technicals (every 30s)
                self._update_signals(current_watchlist, now)

                # Step 3: Refresh factor engine scores (every 60s)
                self._update_factors(current_watchlist, now)

                # Step 4: Refresh market regime (every 60s)
                self._update_regime(now)

                # Step 5: Compute trading decisions and check alerts
                self._compute_decisions_and_alerts(current_watchlist)

                # Step 6: ML model retraining (every 30 min)
                self._retrain_ml_model(now)

            except Exception:
                logger.error("Poll loop error", exc_info=True)

            # Wait for next poll or stop signal
            self._stop_event.wait(timeout=interval)

        logger.info("Poll loop exited")

    def _update_prices(self, tickers: list[str]):
        """Fetch and update price data for all tickers."""
        price_data = _batch_fetch_prices(tickers)
        with self._lock:
            for ticker in tickers:
                data = price_data.get(ticker)
                if data is None:
                    continue
                state = self._states.setdefault(ticker, {"ticker": ticker})
                prev_close = data.get("prev_close", state.get("prev_close", 0))
                price = data["price"]
                change_pct = (
                    ((price - prev_close) / prev_close * 100) if prev_close > 0
                    else 0.0
                )
                state.update({
                    "price": price,
                    "prev_close": prev_close,
                    "open": data.get("open", state.get("open", price)),
                    "high": data.get("high", state.get("high", price)),
                    "low": data.get("low", state.get("low", price)),
                    "volume": data.get("volume", state.get("volume", 0)),
                    "avg_volume": data.get("avg_volume", state.get("avg_volume", 0)),
                    "change_pct": round(change_pct, 2),
                    "bid": data.get("bid", state.get("bid", 0)),
                    "ask": data.get("ask", state.get("ask", 0)),
                    "last_price_update": datetime.now(timezone.utc).isoformat(),
                })

    def _update_signals(self, tickers: list[str], now: float):
        """Recalculate technical indicators for tickers due for refresh."""
        for ticker in tickers:
            last_update = self._signals_updated.get(ticker, 0)
            if now - last_update < SIGNAL_REFRESH_INTERVAL:
                continue

            hist = self._get_cached_history(ticker, now)
            if hist is None:
                continue

            closes = hist["closes"]
            highs = hist["highs"]
            lows = hist["lows"]
            volumes = hist["volumes"]

            rsi = _compute_rsi(closes)
            atr = _compute_atr(highs, lows, closes)
            sma_20 = _compute_sma(closes, 20)
            sma_50 = _compute_sma(closes, 50)
            sma_200 = _compute_sma(closes, 200)
            macd_signal = _compute_macd(closes)
            bollinger = _compute_bollinger(closes)
            vwap_estimate = _compute_vwap_estimate(closes, volumes)

            with self._lock:
                state = self._states.get(ticker)
                if state is None:
                    continue
                price = state.get("price", 0)
                atr_pct = (atr / price * 100) if price > 0 else 0

                # Save previous SMA states for crossover detection
                state["_prev_above_sma20"] = state.get("above_sma20")
                state["_prev_above_sma50"] = state.get("above_sma50")
                state["_prev_above_sma200"] = state.get("above_sma200")

                state.update({
                    "rsi": round(rsi, 1),
                    "atr": round(atr, 2),
                    "atr_pct": round(atr_pct, 2),
                    "sma_20": round(sma_20, 2),
                    "sma_50": round(sma_50, 2),
                    "sma_200": round(sma_200, 2),
                    "vwap_estimate": round(vwap_estimate, 2),
                    "above_sma20": price > sma_20 if sma_20 > 0 else False,
                    "above_sma50": price > sma_50 if sma_50 > 0 else False,
                    "above_sma200": price > sma_200 if sma_200 > 0 else False,
                    "macd_signal": macd_signal,
                    "bollinger_position": bollinger["position"],
                    "_bollinger": bollinger,
                    "last_signal_update": datetime.now(timezone.utc).isoformat(),
                })

            self._signals_updated[ticker] = now

    def _update_factors(self, tickers: list[str], now: float):
        """Refresh 12-factor engine scores for tickers due for refresh."""
        for ticker in tickers:
            last_update = self._factors_updated.get(ticker, 0)
            if now - last_update < FACTOR_REFRESH_INTERVAL:
                continue

            try:
                analysis = get_factor_analysis(ticker)
                composite = analysis.get("composite", 0.0)
                signal = analysis.get("signal", "HOLD")
                regime_data = analysis.get("regime", {})
                regime_label = regime_data.get("regime", "BULL") if regime_data else "BULL"
                group_scores = analysis.get("group_scores", {})
                ratings = analysis.get("ratings", {})
                risk_reward = analysis.get("risk_reward", {})

                with self._lock:
                    state = self._states.get(ticker)
                    if state is not None:
                        state["factor_composite"] = composite
                        state["factor_signal"] = signal
                        state["regime"] = regime_label
                        state["factor_scores"] = group_scores
                        state["ratings"] = ratings
                        state["risk_reward_detail"] = risk_reward

                # Accumulate ML training data point
                price = 0
                with self._lock:
                    s = self._states.get(ticker)
                    if s:
                        price = s.get("price", 0)
                if group_scores and price > 0:
                    entry = self._ml_training_data.setdefault(ticker, [])
                    entry.append({
                        "ts": now,
                        "scores": group_scores,
                        "price": price,
                    })
                    # Keep last 500 data points per ticker
                    if len(entry) > 500:
                        self._ml_training_data[ticker] = entry[-500:]

            except Exception:
                logger.debug("Factor refresh failed for %s", ticker, exc_info=True)

            self._factors_updated[ticker] = now

    def _update_regime(self, now: float):
        """Refresh market regime detection."""
        if now - self._regime_updated < FACTOR_REFRESH_INTERVAL:
            return
        try:
            regime_data = detect_market_regime()
            with self._lock:
                self._regime = regime_data
            self._regime_updated = now
        except Exception:
            logger.debug("Regime detection failed", exc_info=True)

    def _retrain_ml_model(self, now: float):
        """Retrain the cross-sectional ML model on accumulated factor→return data.

        Uses Ridge regression to learn which factor score combinations
        predict forward price changes. Retrains every ML_RETRAIN_INTERVAL.
        """
        if now - self._ml_last_retrain < ML_RETRAIN_INTERVAL:
            return

        try:
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import StandardScaler

            factor_names = [
                "momentum", "value", "quality", "growth", "volatility",
                "sentiment", "macro", "economic", "industry",
                "risk_adjusted", "historical", "ml_adaptive",
            ]

            features = []
            targets = []

            for ticker, data_points in self._ml_training_data.items():
                if len(data_points) < 3:
                    continue
                for i in range(len(data_points) - 1):
                    curr = data_points[i]
                    nxt = data_points[i + 1]
                    scores = curr["scores"]
                    price_now = curr["price"]
                    price_next = nxt["price"]
                    if price_now <= 0:
                        continue

                    fwd_return = (price_next / price_now - 1) * 100
                    row = [scores.get(f, 0.0) for f in factor_names]
                    features.append(row)
                    targets.append(fwd_return)

            if len(features) < 10:
                self._ml_last_retrain = now
                return

            x = np.array(features)
            y = np.array(targets)

            scaler = StandardScaler()
            x_scaled = scaler.fit_transform(x)

            model = Ridge(alpha=1.0)
            model.fit(x_scaled, y)

            # Compute R² on training data (simple validation)
            y_pred = model.predict(x_scaled)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            with self._lock:
                self._ml_model = {"model": model, "scaler": scaler, "factor_names": factor_names}
                self._ml_r2 = round(max(0, r2), 3)

            logger.info(
                "ML model retrained: %d samples, R²=%.3f, coefficients=%s",
                len(features), r2,
                {f: round(c, 3) for f, c in zip(factor_names, model.coef_)},
            )
        except Exception:
            logger.debug("ML retrain failed", exc_info=True)

        self._ml_last_retrain = now

    def _compute_decisions_and_alerts(self, tickers: list[str]):
        """Compute trading decisions and check for alert conditions."""
        with self._lock:
            for ticker in tickers:
                state = self._states.get(ticker)
                if state is None or state.get("price", 0) <= 0:
                    continue

                prev_state = self._prev_states.get(ticker)

                # Compute trading decision using 12-factor engine
                decision = compute_trading_decision(state)
                state.update({
                    "action": decision["action"],
                    "confidence": decision["confidence"],
                    "reason": decision["reason"],
                    "entry_price": decision["entry_price"],
                    "target_price": decision["target_price"],
                    "stop_loss": decision["stop_loss"],
                    "risk_reward": decision["risk_reward"],
                    "decision_score": decision.get("decision_score", 0),
                    "kelly_pct": decision.get("kelly_pct", 0),
                })

                # Check alerts
                new_alerts = _check_alerts(state, prev_state)
                if new_alerts:
                    alert_history = state.get("alert_history", [])
                    for alert in new_alerts:
                        alert_history.append(alert)
                        self._pending_alerts.append({
                            "ticker": ticker,
                            "alert": alert,
                        })
                    # Keep only last N alerts
                    state["alert_history"] = alert_history[-MAX_ALERT_HISTORY:]
                    state["alert"] = new_alerts[-1]  # most recent
                else:
                    state.setdefault("alert", None)
                    state.setdefault("alert_history", [])

                # Snapshot current state for next comparison
                self._prev_states[ticker] = {
                    k: v for k, v in state.items()
                    if not k.startswith("_")
                }

    # --- Helpers ---

    def _get_cached_history(self, ticker: str, now: float) -> dict | None:
        """Return cached history or fetch fresh if stale."""
        cache_ts = self._history_cache_ts.get(ticker, 0)
        if now - cache_ts < SIGNAL_REFRESH_INTERVAL:
            return self._history_cache.get(ticker)
        hist = _fetch_history(ticker)
        if hist is not None:
            self._history_cache[ticker] = hist
            self._history_cache_ts[ticker] = now
        return hist

    def _get_bottom_score(self) -> float | None:
        """Extract bottom score from regime data or return None."""
        if self._regime is None:
            return None
        try:
            bottom = assess_market_bottom()
            return bottom.get("bottom_score")
        except Exception:
            return None

    @staticmethod
    def _sanitize_state(state: dict) -> dict:
        """Return a copy of state without internal keys (prefixed with _)."""
        return {k: v for k, v in state.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_engine: MonitorEngine | None = None


def get_engine() -> MonitorEngine:
    """Get or create the default singleton MonitorEngine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = MonitorEngine()
    return _default_engine


def start():
    """Start the default monitor engine."""
    engine = get_engine()
    engine.start()
    return engine


def stop():
    """Stop the default monitor engine."""
    if _default_engine is not None:
        _default_engine.stop()
