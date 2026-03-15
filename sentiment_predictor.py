"""
Model 2: Sentiment & Market Agent -- prediction market trading bot.

Five-step pipeline that scans the top 50 US stocks for anomalies,
researches shortlisted tickers via news sentiment and technicals,
calibrates predicted edge, sizes positions with Kelly criterion,
and tracks predictions for post-mortem analysis.

All data comes from Yahoo Finance (yfinance). No paid APIs required.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("sentiment_predictor")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PREDICTIONS_FILE = DATA_DIR / "sentiment_predictions.json"

# ---------------------------------------------------------------------------
# Keyword lists for basic headline sentiment scoring
# ---------------------------------------------------------------------------
POSITIVE_KEYWORDS = [
    "surge", "rally", "beat", "upgrade", "growth", "strong", "record",
    "bullish", "soar", "jump", "profit", "gain", "outperform", "buy",
    "boost",
]
NEGATIVE_KEYWORDS = [
    "crash", "fall", "miss", "downgrade", "weak", "loss", "bearish",
    "plunge", "drop", "cut", "decline", "sell", "warning", "risk",
    "recession",
]

# Dynamic top 50 — fetched from data_sources at scan time
from data_sources import get_top_50_by_volume

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
MIN_AVG_VOLUME = 1_000_000
ATR_JUMP_THRESHOLD = 1.5
UNUSUAL_VOLUME_MULTIPLIER = 2.0
CACHE_TTL = 1800  # 30 minutes

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

EDGE_THRESHOLD_PCT = 2.0
MAX_POSITION_PCT = 5.0
MIN_RISK_REWARD = 1.5
ATR_STOP_MULTIPLIER = 2.0
ATR_PROFIT_MULTIPLIER = 3.0

RESEARCH_WORKERS = 6
HISTORY_PERIOD = "3mo"

# In-memory cache shared across a single process lifetime
_scan_cache: dict = {}
_scan_cache_expiry: float = 0.0


# =========================================================================
# Step 1 -- Scan Agent
# =========================================================================

def _compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> float | None:
    """Compute RSI for the last bar of *close*."""
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    value = rsi.iloc[-1]
    if pd.isna(value):
        return None
    return round(float(value), 1)


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                 period: int = 14) -> pd.Series:
    """Return a Series of Average True Range values."""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def scan_for_anomalies() -> list[dict]:
    """Scan the top 50 US stocks and return tickers with anomalies.

    Filters applied:
    - Average daily volume over the last 20 days > 1 M shares
    - Recent ATR jump > 1.5x (last 5-day ATR vs 20-day ATR)
    - Latest volume > 2x the 20-day average volume

    A ticker must pass the liquidity filter AND at least one of the
    volatility / volume filters.
    """
    global _scan_cache, _scan_cache_expiry
    now = time.time()
    if _scan_cache and now < _scan_cache_expiry:
        logger.info("Returning cached scan results (%d tickers)", len(_scan_cache))
        return _scan_cache

    shortlist: list[dict] = []

    for ticker in get_top_50_by_volume():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=HISTORY_PERIOD)
            if hist.empty or len(hist) < 25:
                continue

            close = hist["Close"]
            high = hist["High"]
            low = hist["Low"]
            volume = hist["Volume"]

            avg_volume_20d = float(volume.tail(20).mean())
            if avg_volume_20d < MIN_AVG_VOLUME:
                continue

            atr_full = _compute_atr(high, low, close)
            atr_20d = float(atr_full.tail(20).mean()) if len(atr_full) >= 20 else None
            atr_5d = float(atr_full.tail(5).mean()) if len(atr_full) >= 5 else None

            is_atr_spike = False
            if atr_20d and atr_5d and atr_20d > 0:
                is_atr_spike = (atr_5d / atr_20d) > ATR_JUMP_THRESHOLD

            latest_volume = float(volume.iloc[-1])
            is_volume_spike = latest_volume > (UNUSUAL_VOLUME_MULTIPLIER * avg_volume_20d)

            if not (is_atr_spike or is_volume_spike):
                continue

            info = stock.info
            shortlist.append({
                "ticker": ticker,
                "name": info.get("longName", info.get("shortName", ticker)),
                "sector": info.get("sector", ""),
                "current_price": round(float(close.iloc[-1]), 2),
                "avg_volume_20d": int(avg_volume_20d),
                "latest_volume": int(latest_volume),
                "volume_ratio": round(latest_volume / avg_volume_20d, 2),
                "atr_5d": round(atr_5d, 4) if atr_5d else None,
                "atr_20d": round(atr_20d, 4) if atr_20d else None,
                "atr_ratio": round(atr_5d / atr_20d, 2) if (atr_5d and atr_20d and atr_20d > 0) else None,
                "is_atr_spike": is_atr_spike,
                "is_volume_spike": is_volume_spike,
            })

        except Exception as exc:
            logger.warning("Scan failed for %s: %s", ticker, exc)

    _scan_cache = shortlist
    _scan_cache_expiry = now + CACHE_TTL
    logger.info("Scan complete: %d / %d tickers shortlisted",
                len(shortlist), len(get_top_50_by_volume()))
    return shortlist


# =========================================================================
# Step 2 -- Research Agent
# =========================================================================

def _score_text_sentiment(text: str) -> int:
    """Return +1 for each positive keyword and -1 for each negative keyword."""
    lower = text.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in lower)
    return pos - neg


def research_ticker(scan_item: dict) -> dict:
    """Gather sentiment, analyst gap, and RSI for one ticker.

    Returns a dict that extends *scan_item* with research fields.
    """
    ticker = scan_item["ticker"]
    result = {**scan_item}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period=HISTORY_PERIOD)
        if hist.empty:
            result["research_error"] = "No price history"
            return result

        close = hist["Close"]
        current_price = float(close.iloc[-1])

        # -- News sentiment --------------------------------------------------
        raw_sentiment = 0
        news_count = 0
        try:
            news_items = stock.news or []
            news_count = len(news_items)
            for article in news_items:
                title = article.get("title", "")
                summary = article.get("summary", article.get("description", ""))
                raw_sentiment += _score_text_sentiment(title)
                raw_sentiment += _score_text_sentiment(summary)
        except Exception as exc:
            logger.debug("News fetch failed for %s: %s", ticker, exc)

        # Normalize to -100..+100
        if news_count > 0:
            max_possible = news_count * (len(POSITIVE_KEYWORDS) + len(NEGATIVE_KEYWORDS))
            sentiment_score = int(np.clip(
                (raw_sentiment / max(max_possible * 0.1, 1)) * 100, -100, 100
            ))
        else:
            sentiment_score = 0

        # -- Analyst target gap -----------------------------------------------
        target_mean = info.get("targetMeanPrice")
        analyst_gap_pct = None
        if target_mean and current_price > 0:
            analyst_gap_pct = round(
                ((target_mean - current_price) / current_price) * 100, 2
            )

        # -- RSI ---------------------------------------------------------------
        rsi = _compute_rsi(close)

        # -- Moving-average trend signals -------------------------------------
        sma_20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        ma_signals: list[str] = []
        if sma_20 and current_price > sma_20:
            ma_signals.append("above_sma20")
        if sma_50 and current_price > sma_50:
            ma_signals.append("above_sma50")
        if sma_20 and sma_50 and sma_20 > sma_50:
            ma_signals.append("golden_cross")

        result.update({
            "sentiment_score": sentiment_score,
            "news_count": news_count,
            "analyst_target_mean": target_mean,
            "analyst_gap_pct": analyst_gap_pct,
            "rsi": rsi,
            "sma_20": round(sma_20, 2) if sma_20 else None,
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "ma_signals": ma_signals,
            "recommendation": info.get("recommendationKey"),
        })

    except Exception as exc:
        logger.error("Research failed for %s: %s", ticker, exc)
        result["research_error"] = str(exc)

    return result


def research_batch(shortlist: list[dict]) -> list[dict]:
    """Run research agents in parallel for all shortlisted tickers."""
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=RESEARCH_WORKERS) as pool:
        futures = {pool.submit(research_ticker, item): item for item in shortlist}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ticker = futures[future].get("ticker", "?")
                logger.error("Research thread failed for %s: %s", ticker, exc)
    return results


# =========================================================================
# Step 3 -- Prediction Agent
# =========================================================================

def _technical_score(item: dict) -> float:
    """Compute a technical score from 0 to 100.

    Components:
    - RSI extremes contribute up to 40 points (oversold = bullish)
    - MA alignment contributes up to 30 points
    - Volume spike contributes up to 15 points
    - ATR spike contributes up to 15 points (higher volatility = opportunity)
    """
    score = 50.0  # neutral baseline

    rsi = item.get("rsi")
    if rsi is not None:
        if rsi < RSI_OVERSOLD:
            score += 30.0 + (RSI_OVERSOLD - rsi)
        elif rsi > RSI_OVERBOUGHT:
            score -= 30.0 + (rsi - RSI_OVERBOUGHT)
        elif rsi < 45:
            score += 10.0
        elif rsi > 55:
            score -= 10.0

    ma_signals = item.get("ma_signals", [])
    score += len(ma_signals) * 10.0

    if item.get("is_volume_spike"):
        score += 10.0

    if item.get("is_atr_spike"):
        score += 5.0

    return round(float(np.clip(score, 0, 100)), 1)


def predict_edge(item: dict) -> dict:
    """Combine technical, sentiment, and analyst signals into a prediction.

    Returns a dict with direction, edge_pct, confidence, entry_reason.
    """
    tech = _technical_score(item)
    sentiment = item.get("sentiment_score", 0)
    analyst_gap = item.get("analyst_gap_pct")

    # Weighted composite (all normalized to roughly -50..+50 contribution)
    tech_contrib = (tech - 50.0) * 0.40
    sent_contrib = (sentiment / 100.0) * 50.0 * 0.30
    analyst_contrib = 0.0
    if analyst_gap is not None:
        analyst_contrib = float(np.clip(analyst_gap, -30, 30)) * 0.30

    composite = tech_contrib + sent_contrib + analyst_contrib
    edge_pct = round(float(np.clip(abs(composite), 0, 25)), 2)
    direction = "LONG" if composite >= 0 else "SHORT"

    # Confidence 1-10 based on signal alignment
    alignment_count = 0
    if direction == "LONG":
        if tech > 55:
            alignment_count += 1
        if sentiment > 10:
            alignment_count += 1
        if analyst_gap and analyst_gap > 3:
            alignment_count += 1
        rsi = item.get("rsi")
        if rsi and rsi < 45:
            alignment_count += 1
    else:
        if tech < 45:
            alignment_count += 1
        if sentiment < -10:
            alignment_count += 1
        if analyst_gap and analyst_gap < -3:
            alignment_count += 1
        rsi = item.get("rsi")
        if rsi and rsi > 55:
            alignment_count += 1

    base_confidence = 3 + alignment_count * 2
    if edge_pct > EDGE_THRESHOLD_PCT:
        base_confidence += 1
    confidence = int(np.clip(base_confidence, 1, 10))

    # Build human-readable entry reason
    reasons: list[str] = []
    if sentiment > 20:
        reasons.append("Strong positive sentiment")
    elif sentiment < -20:
        reasons.append("Strong negative sentiment")

    rsi_val = item.get("rsi")
    if rsi_val and rsi_val < RSI_OVERSOLD:
        reasons.append(f"Oversold RSI ({rsi_val})")
    elif rsi_val and rsi_val > RSI_OVERBOUGHT:
        reasons.append(f"Overbought RSI ({rsi_val})")

    if analyst_gap and abs(analyst_gap) > 5:
        reasons.append(f"{abs(analyst_gap):.1f}% {'below' if analyst_gap > 0 else 'above'} analyst target")

    if item.get("is_volume_spike"):
        reasons.append(f"Volume spike ({item.get('volume_ratio', 0):.1f}x avg)")

    entry_reason = " + ".join(reasons) if reasons else "Moderate signal alignment"

    return {
        "direction": direction,
        "edge_pct": edge_pct,
        "confidence": confidence,
        "technical_score": tech,
        "entry_reason": entry_reason,
    }


# =========================================================================
# Step 4 -- Risk Agent
# =========================================================================

def size_position(item: dict, prediction: dict) -> dict:
    """Compute position size, stop loss, and take profit using Kelly criterion.

    Kelly fraction = edge / odds (simplified).
    Position capped at MAX_POSITION_PCT of portfolio.
    Trades with risk/reward < MIN_RISK_REWARD are rejected.
    """
    current_price = item.get("current_price", 0)
    atr = item.get("atr_5d") or item.get("atr_20d") or 0
    edge_pct = prediction.get("edge_pct", 0)
    direction = prediction.get("direction", "LONG")

    if current_price <= 0 or atr <= 0:
        return {
            "position_size_pct": 0,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": 0,
            "rejected": True,
            "reject_reason": "Insufficient price or ATR data",
        }

    stop_distance = atr * ATR_STOP_MULTIPLIER
    profit_distance = atr * ATR_PROFIT_MULTIPLIER

    if direction == "LONG":
        stop_loss = round(current_price - stop_distance, 2)
        take_profit = round(current_price + profit_distance, 2)
    else:
        stop_loss = round(current_price + stop_distance, 2)
        take_profit = round(current_price - profit_distance, 2)

    risk_reward = profit_distance / stop_distance if stop_distance > 0 else 0

    if risk_reward < MIN_RISK_REWARD:
        return {
            "position_size_pct": 0,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "risk_reward": round(risk_reward, 2),
            "rejected": True,
            "reject_reason": f"Risk/reward {risk_reward:.2f} below minimum {MIN_RISK_REWARD}",
        }

    # Simplified Kelly: fraction = edge / odds
    odds = profit_distance / stop_distance if stop_distance > 0 else 1
    kelly_fraction = (edge_pct / 100.0) / odds if odds > 0 else 0
    position_pct = round(
        float(np.clip(kelly_fraction * 100, 0.5, MAX_POSITION_PCT)), 2
    )

    return {
        "position_size_pct": position_pct,
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk_reward": round(risk_reward, 2),
        "rejected": False,
        "reject_reason": None,
    }


# =========================================================================
# Step 5 -- Post-Mortem Tracker
# =========================================================================

def _load_past_predictions() -> list[dict]:
    """Load previous predictions from disk."""
    if PREDICTIONS_FILE.exists():
        try:
            with open(PREDICTIONS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load past predictions: %s", exc)
    return []


def _save_predictions(records: list[dict]) -> None:
    """Persist prediction records to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, default=str)
    logger.info("Saved %d prediction records to %s", len(records), PREDICTIONS_FILE)


def _evaluate_past_predictions(records: list[dict]) -> dict:
    """Check past predictions against actual prices and compute hit rate.

    A prediction is a 'hit' when the price moved in the predicted direction
    by at least half the predicted edge within 20 trading days.
    """
    evaluated = 0
    hits = 0
    total_return_pct = 0.0

    for record in records:
        if record.get("outcome") is not None:
            evaluated += 1
            if record["outcome"] == "hit":
                hits += 1
            total_return_pct += record.get("actual_return_pct", 0)
            continue

        entry_price = record.get("entry_price")
        ticker = record.get("ticker")
        if not entry_price or not ticker:
            continue

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            if hist.empty:
                continue

            latest_price = float(hist["Close"].iloc[-1])
            actual_return_pct = ((latest_price - entry_price) / entry_price) * 100

            if record.get("direction") == "SHORT":
                actual_return_pct = -actual_return_pct

            half_edge = record.get("edge_pct", 0) / 2
            is_hit = actual_return_pct >= half_edge

            record["latest_price"] = round(latest_price, 2)
            record["actual_return_pct"] = round(actual_return_pct, 2)
            record["outcome"] = "hit" if is_hit else "miss"
            record["evaluated_at"] = datetime.now(timezone.utc).isoformat()

            evaluated += 1
            if is_hit:
                hits += 1
            total_return_pct += actual_return_pct

        except Exception as exc:
            logger.debug("Post-mortem eval failed for %s: %s", ticker, exc)

    hit_rate = round(hits / evaluated, 4) if evaluated > 0 else 0
    avg_return = round(total_return_pct / evaluated, 2) if evaluated > 0 else 0

    return {
        "total_past": len(records),
        "evaluated": evaluated,
        "hits": hits,
        "hit_rate": hit_rate,
        "avg_return_pct": avg_return,
    }


def _record_new_predictions(predictions: list[dict]) -> None:
    """Append new predictions to the persistent file."""
    past = _load_past_predictions()
    timestamp = datetime.now(timezone.utc).isoformat()

    for pred in predictions:
        past.append({
            "timestamp": timestamp,
            "ticker": pred.get("ticker"),
            "name": pred.get("name"),
            "direction": pred.get("direction"),
            "entry_price": pred.get("current_price"),
            "edge_pct": pred.get("edge_pct"),
            "confidence": pred.get("confidence"),
            "stop_loss": pred.get("stop_loss"),
            "take_profit": pred.get("take_profit"),
            "sentiment_score": pred.get("sentiment_score"),
            "technical_score": pred.get("technical_score"),
            "outcome": None,
            "latest_price": None,
            "actual_return_pct": None,
            "evaluated_at": None,
        })

    _save_predictions(past)


# =========================================================================
# Main entry point
# =========================================================================

def run_sentiment_scan() -> dict:
    """Run the full 5-step pipeline and return predictions.

    Returns a dict matching the dashboard API contract:
    {
        "model_name": "Sentiment & Market Agent",
        "generated_at": <ISO timestamp>,
        "scan_results": {"total_scanned": N, "shortlisted": N},
        "predictions": [ ... ],
        "post_mortem": {"total_past": N, "hit_rate": 0.68, "avg_return_pct": 1.2},
    }
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    logger.info("=== Sentiment scan started at %s ===", generated_at)

    # Step 1 -- Scan
    shortlist = scan_for_anomalies()
    scan_results = {
        "total_scanned": len(get_top_50_by_volume()),
        "shortlisted": len(shortlist),
    }

    if not shortlist:
        logger.info("No anomalies detected. Returning empty predictions.")
        past = _load_past_predictions()
        post_mortem = _evaluate_past_predictions(past)
        _save_predictions(past)
        return {
            "model_name": "Sentiment & Market Agent",
            "generated_at": generated_at,
            "scan_results": scan_results,
            "predictions": [],
            "post_mortem": post_mortem,
        }

    # Step 2 -- Research (parallel)
    researched = research_batch(shortlist)

    # Step 3 + 4 -- Predict + Size
    predictions: list[dict] = []
    for item in researched:
        if item.get("research_error"):
            continue

        prediction = predict_edge(item)
        risk = size_position(item, prediction)

        if risk.get("rejected"):
            logger.debug(
                "Rejected %s: %s", item["ticker"], risk.get("reject_reason")
            )
            continue

        predictions.append({
            "ticker": item["ticker"],
            "name": item.get("name", item["ticker"]),
            "sector": item.get("sector", ""),
            "direction": prediction["direction"],
            "edge_pct": prediction["edge_pct"],
            "confidence": prediction["confidence"],
            "sentiment_score": item.get("sentiment_score", 0),
            "news_count": item.get("news_count", 0),
            "technical_score": prediction["technical_score"],
            "analyst_gap_pct": item.get("analyst_gap_pct"),
            "rsi": item.get("rsi"),
            "position_size_pct": risk["position_size_pct"],
            "stop_loss": risk["stop_loss"],
            "take_profit": risk["take_profit"],
            "risk_reward": risk["risk_reward"],
            "current_price": item.get("current_price"),
            "entry_reason": prediction["entry_reason"],
        })

    # Sort by confidence desc, then edge desc
    predictions.sort(key=lambda p: (-p["confidence"], -p["edge_pct"]))

    # Step 5 -- Post-mortem
    past = _load_past_predictions()
    post_mortem = _evaluate_past_predictions(past)
    _save_predictions(past)

    if predictions:
        _record_new_predictions(predictions)

    logger.info(
        "Scan complete: %d predictions generated, post-mortem hit rate %.1f%%",
        len(predictions),
        post_mortem.get("hit_rate", 0) * 100,
    )

    return {
        "model_name": "Sentiment & Market Agent",
        "generated_at": generated_at,
        "scan_results": scan_results,
        "predictions": predictions,
        "post_mortem": post_mortem,
    }


# =========================================================================
# Dashboard integration helper
# =========================================================================

def get_sentiment_predictions_for_dashboard() -> dict:
    """Format sentiment predictions so they merge with Model 1 (LightGBM).

    Returns a dict that the dashboard API can combine with predictions.json:
    {
        "model_2": {
            "name": "Sentiment & Market Agent",
            "generated_at": <ISO>,
            "total_predictions": N,
            "hit_rate": 0.68,
            "predictions": [
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "direction": "LONG",
                    "signal": 0.035,       # edge_pct / 100 to match Model 1 scale
                    "confidence": 8,
                    "sentiment_score": 65,
                    "technical_score": 72,
                    "position_size_pct": 3.0,
                    "stop_loss": 172.50,
                    "take_profit": 195.00,
                    "risk_reward": 2.1,
                    "current_price": 180.00,
                    "entry_reason": "..."
                }
            ]
        }
    }
    """
    scan = run_sentiment_scan()

    dashboard_predictions = []
    for pred in scan.get("predictions", []):
        dashboard_predictions.append({
            "ticker": pred["ticker"],
            "name": pred["name"],
            "sector": pred.get("sector", ""),
            "direction": pred["direction"],
            "signal": round(pred["edge_pct"] / 100.0, 5),
            "confidence": pred["confidence"],
            "sentiment_score": pred["sentiment_score"],
            "news_count": pred.get("news_count", 0),
            "technical_score": pred["technical_score"],
            "analyst_gap_pct": pred.get("analyst_gap_pct"),
            "rsi": pred.get("rsi"),
            "position_size_pct": pred["position_size_pct"],
            "stop_loss": pred["stop_loss"],
            "take_profit": pred["take_profit"],
            "risk_reward": pred["risk_reward"],
            "current_price": pred["current_price"],
            "entry_reason": pred["entry_reason"],
        })

    post_mortem = scan.get("post_mortem", {})

    return {
        "model_2": {
            "name": "Sentiment & Market Agent",
            "generated_at": scan["generated_at"],
            "total_predictions": len(dashboard_predictions),
            "hit_rate": post_mortem.get("hit_rate", 0),
            "avg_return_pct": post_mortem.get("avg_return_pct", 0),
            "predictions": dashboard_predictions,
        },
    }


# =========================================================================
# CLI entry point
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    result = run_sentiment_scan()
    print(json.dumps(result, indent=2, default=str))
