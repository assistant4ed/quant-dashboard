"""
Venture Fund-Grade Multi-Factor Analysis Engine v3.

Computes 12 factor category exposures (each -5 to +5 scale):
  1. Momentum           - Price trend 1m/3m/6m/12m + RSI + MACD
  2. Value              - P/E, P/B, EV/EBITDA, P/S, Dividend Yield (sector-adjusted)
  3. Quality            - ROE, ROA, Gross Margin, Op Margin, Debt/Equity, Current Ratio
  4. Growth             - Revenue growth, EPS growth, Forward EPS, Analyst Rating
  5. Volatility         - Beta, 30D Realized Vol, Max Drawdown, ATR (inverted scoring)
  6. Sentiment          - Short Interest, Institutional Hold, Insider Activity, Consensus
  7. Macro              - S&P Correlation, Relative Strength, 52-Week Position
  8. Economic           - CPI, GDP, Consumer Sentiment, Yield Curve, PMI, Housing
  9. Industry           - Sector ETF momentum, relative strength vs market, rotation
 10. Risk-Adjusted      - Sharpe, Sortino, Information, Calmar, Treynor, Risk-Reward
 11. Historical Analogy - Macro fingerprint vs historical regimes, forward return est.
 12. ML Adaptive        - Ridge regression meta-factor, factor alignment, signal consistency

Adds market regime detection, dynamic factor weights, industry-specific
thresholds, multi-horizon scoring, risk-to-return, and bottom detection.
"""
import logging
import math
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

from data_sources import get_macro_indicators, get_market_sentiment

logger = logging.getLogger("factors")

_CACHE: dict = {}
_CACHE_TTL = 1800  # 30-minute TTL


# ---------------------------------------------------------------------------
# Constants: Regime-Dependent Factor Weights
# ---------------------------------------------------------------------------

REGIME_WEIGHTS = {
    "PANIC": {
        "momentum": 0.064, "value": 0.200, "quality": 0.200, "growth": 0.064,
        "volatility": 0.080, "sentiment": 0.048, "macro": 0.064,
        "economic": 0.040, "industry": 0.040,
        "risk_adjusted": 0.080, "historical": 0.080, "ml_adaptive": 0.040,
    },
    "BEAR": {
        "momentum": 0.098, "value": 0.180, "quality": 0.180, "growth": 0.082,
        "volatility": 0.082, "sentiment": 0.066, "macro": 0.066,
        "economic": 0.033, "industry": 0.033,
        "risk_adjusted": 0.070, "historical": 0.070, "ml_adaptive": 0.040,
    },
    "RECOVERY": {
        "momentum": 0.167, "value": 0.149, "quality": 0.149, "growth": 0.149,
        "volatility": 0.066, "sentiment": 0.066, "macro": 0.042,
        "economic": 0.025, "industry": 0.017,
        "risk_adjusted": 0.060, "historical": 0.060, "ml_adaptive": 0.050,
    },
    "BULL": {
        "momentum": 0.212, "value": 0.085, "quality": 0.128, "growth": 0.212,
        "volatility": 0.043, "sentiment": 0.085, "macro": 0.043,
        "economic": 0.025, "industry": 0.017,
        "risk_adjusted": 0.050, "historical": 0.050, "ml_adaptive": 0.050,
    },
    "EUPHORIA": {
        "momentum": 0.124, "value": 0.066, "quality": 0.100, "growth": 0.248,
        "volatility": 0.042, "sentiment": 0.100, "macro": 0.066,
        "economic": 0.042, "industry": 0.042,
        "risk_adjusted": 0.060, "historical": 0.060, "ml_adaptive": 0.050,
    },
}

SHORT_TERM_WEIGHTS = {
    "momentum": 0.240, "value": 0.040, "quality": 0.040, "growth": 0.080,
    "volatility": 0.080, "sentiment": 0.160, "macro": 0.080,
    "economic": 0.040, "industry": 0.040,
    "risk_adjusted": 0.050, "historical": 0.050, "ml_adaptive": 0.100,
}

LONG_TERM_WEIGHTS = {
    "momentum": 0.041, "value": 0.205, "quality": 0.205, "growth": 0.164,
    "volatility": 0.041, "sentiment": 0.016, "macro": 0.025,
    "economic": 0.041, "industry": 0.082,
    "risk_adjusted": 0.080, "historical": 0.080, "ml_adaptive": 0.020,
}


# ---------------------------------------------------------------------------
# Constants: Sector Profiles
# ---------------------------------------------------------------------------

SECTOR_PROFILES = {
    "Technology": {
        "pe_range": (25, 35), "pb_range": (4, 10), "ev_ebitda_range": (15, 25),
        "margin_high": True, "growth_expected": True, "dividend_focus": False,
        "etf": "XLK",
    },
    "Financial Services": {
        "pe_range": (10, 15), "pb_range": (1, 2), "ev_ebitda_range": (8, 14),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLF",
    },
    "Healthcare": {
        "pe_range": (20, 30), "pb_range": (3, 8), "ev_ebitda_range": (12, 22),
        "margin_high": True, "growth_expected": True, "dividend_focus": False,
        "etf": "XLV",
    },
    "Energy": {
        "pe_range": (8, 15), "pb_range": (1, 3), "ev_ebitda_range": (5, 10),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLE",
    },
    "Consumer Cyclical": {
        "pe_range": (18, 25), "pb_range": (3, 7), "ev_ebitda_range": (10, 18),
        "margin_high": False, "growth_expected": True, "dividend_focus": False,
        "etf": "XLY",
    },
    "Consumer Defensive": {
        "pe_range": (18, 25), "pb_range": (4, 8), "ev_ebitda_range": (12, 18),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLP",
    },
    "Industrials": {
        "pe_range": (15, 22), "pb_range": (3, 6), "ev_ebitda_range": (10, 16),
        "margin_high": False, "growth_expected": False, "dividend_focus": False,
        "etf": "XLI",
    },
    "Basic Materials": {
        "pe_range": (12, 18), "pb_range": (1.5, 4), "ev_ebitda_range": (6, 12),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLB",
    },
    "Utilities": {
        "pe_range": (15, 20), "pb_range": (1.5, 3), "ev_ebitda_range": (10, 14),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLU",
    },
    "Real Estate": {
        "pe_range": (25, 45), "pb_range": (1.5, 3.5), "ev_ebitda_range": (15, 25),
        "margin_high": False, "growth_expected": False, "dividend_focus": True,
        "etf": "XLRE",
    },
    "Communication Services": {
        "pe_range": (15, 25), "pb_range": (2, 6), "ev_ebitda_range": (8, 16),
        "margin_high": True, "growth_expected": True, "dividend_focus": False,
        "etf": "XLC",
    },
}

DEFAULT_SECTOR_PROFILE = {
    "pe_range": (15, 25), "pb_range": (2, 5), "ev_ebitda_range": (10, 18),
    "margin_high": False, "growth_expected": False, "dividend_focus": False,
    "etf": "SPY",
}

SECTOR_ETF_MAP = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
    "Energy": "XLE", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Industrials": "XLI", "Basic Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_factor_analysis(ticker: str) -> dict:
    """Compute full multi-factor analysis with regime-aware dynamic weights.

    Returns composite score, all factor groups, regime info,
    short/medium/long term ratings, risk-reward, and bottom assessment.
    """
    now = datetime.now(timezone.utc)
    cache_key = f"analysis_{ticker}"
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        hist = stock.history(period="2y")

        if hist.empty:
            return _make_error(ticker, "No price history available")

        sector = info.get("sector", "")
        profile = SECTOR_PROFILES.get(sector, DEFAULT_SECTOR_PROFILE)
        regime_data = detect_market_regime()
        regime = regime_data.get("regime", "BULL")

        momentum = _compute_momentum(hist, info)
        value = _compute_value(info, profile)
        quality = _compute_quality(info)
        growth = _compute_growth(info)
        volatility = _compute_volatility(hist, info)
        sentiment = _compute_sentiment(stock, info)
        macro = _compute_macro(hist, ticker, sector, info)
        country = info.get("country", "United States")
        economic = _compute_economic(ticker, country, info)
        industry = _compute_industry_outlook(sector)
        risk_adjusted = _compute_risk_adjusted_return(hist, info)
        historical = _compute_historical_analogy(hist, info)

        groups = {
            "momentum": momentum,
            "value": value,
            "quality": quality,
            "growth": growth,
            "volatility": volatility,
            "sentiment": sentiment,
            "macro": macro,
            "economic": economic,
            "industry": industry,
            "risk_adjusted": risk_adjusted,
            "historical": historical,
        }

        ml_adaptive = _compute_ml_adaptive(groups, ticker, hist)
        groups["ml_adaptive"] = ml_adaptive

        weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["BULL"])
        composite = _clamp(
            sum(groups[k]["composite"] * weights[k] for k in weights), -5, 5,
        )

        short_term = _compute_horizon_score(groups, SHORT_TERM_WEIGHTS)
        long_term = _compute_horizon_score(groups, LONG_TERM_WEIGHTS)
        medium_term = composite

        risk_reward = _compute_risk_reward(info, hist)
        bottom = assess_market_bottom()

        data = {
            "ticker": ticker,
            "sector": sector,
            "composite": round(composite, 3),
            "signal": _rating(composite),
            "regime": regime_data,
            "weights": weights,
            "group_scores": {
                k: round(groups[k]["composite"], 2) for k in groups
            },
            "groups": groups,
            "ratings": {
                "short_term": {
                    "horizon": "1-4 weeks",
                    "horizon_cn": "1-4周",
                    "score": round(short_term, 3),
                    "signal": _rating(short_term),
                },
                "medium_term": {
                    "horizon": "1-6 months",
                    "horizon_cn": "1-6个月",
                    "score": round(medium_term, 3),
                    "signal": _rating(medium_term),
                },
                "long_term": {
                    "horizon": "6-24 months",
                    "horizon_cn": "6-24个月",
                    "score": round(long_term, 3),
                    "signal": _rating(long_term),
                },
            },
            "risk_reward": risk_reward,
            "market_bottom": bottom,
            "generated_at": now.isoformat(),
        }
        _CACHE[cache_key] = {"data": data, "ts": now}
        return data

    except Exception as exc:
        logger.exception("Factor analysis error for %s", ticker)
        return _make_error(ticker, str(exc))


def detect_market_regime() -> dict:
    """Determine current market state from VIX, S&P 500, breadth, and flows.

    Returns regime label plus all constituent signals.
    """
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("regime")
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    signals = {}

    vix_level = _safe_yf_close("^VIX")
    signals["vix"] = vix_level

    sp_data = _fetch_regime_series("^GSPC")
    signals["sp500_price"] = sp_data.get("price")
    signals["sp500_drawdown_pct"] = sp_data.get("drawdown_pct")
    signals["sp500_above_50ma"] = sp_data.get("above_50ma")
    signals["sp500_above_200ma"] = sp_data.get("above_200ma")
    signals["sp500_50_vs_200"] = sp_data.get("golden_cross")

    nasdaq_data = _fetch_regime_series("^IXIC")
    signals["nasdaq_above_200ma"] = nasdaq_data.get("above_200ma")

    tlt_close = _safe_yf_close("TLT")
    signals["tlt_price"] = tlt_close
    gold_close = _safe_yf_close("GC=F")
    signals["gold_price"] = gold_close

    # Advance-decline proxy: compare S&P 500 and Russell 2000 trends
    rut_data = _fetch_regime_series("^RUT")
    breadth_positive = (
        sp_data.get("above_50ma", False) and rut_data.get("above_50ma", False)
    )
    signals["breadth_positive"] = breadth_positive

    # VIX trend: declining from elevated
    vix_declining = False
    try:
        vix_hist = yf.Ticker("^VIX").history(period="1mo")
        if not vix_hist.empty and len(vix_hist) >= 10:
            vix_closes = vix_hist["Close"].values.astype(float)
            vix_10d_ago = float(vix_closes[-10])
            vix_now = float(vix_closes[-1])
            vix_declining = vix_now < vix_10d_ago and vix_10d_ago > 22
            signals["vix_declining_from_elevated"] = vix_declining
    except Exception:
        pass

    regime = _classify_regime(signals)
    signals["regime"] = regime

    data = {
        "regime": regime,
        "signals": signals,
        "detected_at": now.isoformat(),
    }
    _CACHE["regime"] = {"data": data, "ts": now}
    return data


def assess_market_bottom() -> dict:
    """Score 0-100 for 'is this a buying opportunity' based on contrarian signals.

    High score means conditions historically precede market recoveries.
    """
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("bottom")
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    component_scores = []
    signal_details = []

    # 1. VIX spike score
    vix = _safe_yf_close("^VIX")
    if vix is not None:
        vix_score = _clamp(((vix - 18) / 22) * 100, 0, 100)
        component_scores.append(vix_score)
        signal_details.append({
            "name": "VIX Spike",
            "name_cn": "VIX恐慌指数",
            "value": round(vix, 1),
            "score": round(vix_score, 1),
            "bullish": vix > 30,
        })

    # 2. S&P 500 drawdown from 52-week high
    sp_data = _fetch_regime_series("^GSPC")
    dd = sp_data.get("drawdown_pct")
    if dd is not None:
        dd_score = _clamp((abs(dd) / 25) * 100, 0, 100)
        component_scores.append(dd_score)
        signal_details.append({
            "name": "S&P 500 Drawdown",
            "name_cn": "标普500回撤",
            "value": round(dd, 1),
            "score": round(dd_score, 1),
            "bullish": dd < -15,
        })

    # 3. Breadth washout: percentage of major indices below 200 MA
    indices_below_200 = 0
    total_checked = 0
    for sym in ["^GSPC", "^IXIC", "^RUT", "^DJI"]:
        idx_data = _fetch_regime_series(sym)
        if idx_data.get("above_200ma") is not None:
            total_checked += 1
            if not idx_data["above_200ma"]:
                indices_below_200 += 1
    if total_checked > 0:
        washout_pct = (indices_below_200 / total_checked) * 100
        component_scores.append(washout_pct)
        signal_details.append({
            "name": "Breadth Washout",
            "name_cn": "市场广度崩溃",
            "value": f"{indices_below_200}/{total_checked} below 200MA",
            "score": round(washout_pct, 1),
            "bullish": washout_pct >= 75,
        })

    # 4. Credit spread proxy: HYG vs LQD ratio
    hyg = _safe_yf_close("HYG")
    lqd = _safe_yf_close("LQD")
    if hyg is not None and lqd is not None and lqd > 0:
        spread_ratio = hyg / lqd
        # Lower ratio = wider spreads = more fear = higher bottom score
        spread_score = _clamp(((1.0 - spread_ratio) / 0.15) * 100, 0, 100)
        component_scores.append(spread_score)
        signal_details.append({
            "name": "Credit Spread (HYG/LQD)",
            "name_cn": "信用利差",
            "value": round(spread_ratio, 4),
            "score": round(spread_score, 1),
            "bullish": spread_ratio < 0.90,
        })

    # 5. Fear & Greed proxy from sentiment data
    try:
        sentiment = get_market_sentiment()
        fg = sentiment.get("fear_greed_score")
        if fg is not None:
            # Extreme fear = high bottom score (contrarian)
            fear_score = _clamp(((50 - fg) / 50) * 100, 0, 100)
            component_scores.append(fear_score)
            signal_details.append({
                "name": "Fear & Greed Contrarian",
                "name_cn": "恐惧贪婪反向指标",
                "value": round(fg, 1),
                "score": round(fear_score, 1),
                "bullish": fg < 25,
            })
    except Exception:
        pass

    bottom_score = round(
        sum(component_scores) / len(component_scores), 1,
    ) if component_scores else 0

    bullish_signals = sum(1 for s in signal_details if s.get("bullish"))

    # Risk-reward estimate based on bottom score
    if bottom_score >= 70:
        rr_ratio = "3:1"
        recommendation = "Strong contrarian buy signal. Historically, similar conditions precede major recoveries."
    elif bottom_score >= 50:
        rr_ratio = "2:1"
        recommendation = "Elevated fear. Consider gradual accumulation of quality positions."
    elif bottom_score >= 30:
        rr_ratio = "1:1"
        recommendation = "Market stress moderate. Selective opportunities in oversold names."
    else:
        rr_ratio = "0.5:1"
        recommendation = "No bottom signals. Market conditions normal or elevated."

    data = {
        "bottom_score": bottom_score,
        "signals": signal_details,
        "bullish_signal_count": bullish_signals,
        "total_signals": len(signal_details),
        "risk_reward_ratio": rr_ratio,
        "recommendation": recommendation,
        "assessed_at": now.isoformat(),
    }
    _CACHE["bottom"] = {"data": data, "ts": now}
    return data


# ---------------------------------------------------------------------------
# Helpers (preserved from v1)
# ---------------------------------------------------------------------------

def _clamp(v, lo=-5.0, hi=5.0):
    return float(max(lo, min(hi, v)))


def _make_error(ticker, msg):
    return {"ticker": ticker, "composite": 0.0, "signal": "ERROR", "error": msg}


def _rating(score):
    if score >= 2.5:
        return "STRONG_BUY"
    if score >= 0.8:
        return "BUY"
    if score >= -0.8:
        return "HOLD"
    if score >= -2.5:
        return "SELL"
    return "STRONG_SELL"


def _thresh(value, breaks):
    """Map value to score using [(threshold, score), ...] breakpoints."""
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return 0.0
    for thresh, sc in breaks:
        if value <= thresh:
            return float(sc)
    return float(breaks[-1][1])


def _ema(data, period):
    k = 2.0 / (period + 1)
    result = [float(data[0])]
    for v in data[1:]:
        result.append(float(v) * k + result[-1] * (1 - k))
    return np.array(result)


def _calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    diffs = np.diff(closes.astype(float))
    gains = np.maximum(diffs, 0)
    losses = np.abs(np.minimum(diffs, 0))
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1 + avg_gain / avg_loss))


def _safe_mean(scores):
    valid = [s for s in scores if s is not None]
    return float(np.mean(valid)) if valid else 0.0


def _fmt(v, decimals=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), decimals)


# ---------------------------------------------------------------------------
# Internal: Market Data Fetchers
# ---------------------------------------------------------------------------

def _safe_yf_close(symbol):
    """Fetch latest closing price for a symbol, return None on failure."""
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", symbol, exc)
    return None


def _fetch_regime_series(symbol):
    """Fetch price data and compute regime-relevant indicators for a symbol."""
    result = {
        "price": None, "drawdown_pct": None,
        "above_50ma": None, "above_200ma": None, "golden_cross": None,
    }
    try:
        hist = yf.Ticker(symbol).history(period="2y")
        if hist.empty:
            return result
        closes = hist["Close"].values.astype(float)
        n = len(closes)
        current = float(closes[-1])
        result["price"] = round(current, 2)

        high_52w = float(closes[-min(252, n):].max())
        result["drawdown_pct"] = round((current / high_52w - 1) * 100, 2)

        if n >= 50:
            ma_50 = float(np.mean(closes[-50:]))
            result["above_50ma"] = current > ma_50
        if n >= 200:
            ma_200 = float(np.mean(closes[-200:]))
            result["above_200ma"] = current > ma_200
            if n >= 50:
                result["golden_cross"] = float(np.mean(closes[-50:])) > ma_200
    except Exception as exc:
        logger.warning("Regime series fetch failed for %s: %s", symbol, exc)
    return result


def _classify_regime(signals):
    """Classify market regime based on collected signals."""
    vix = signals.get("vix")
    dd = signals.get("sp500_drawdown_pct")
    above_200 = signals.get("sp500_above_200ma")
    above_50 = signals.get("sp500_above_50ma")
    breadth = signals.get("breadth_positive", False)
    vix_declining = signals.get("vix_declining_from_elevated", False)

    if vix is None:
        return "BULL"

    if vix > 30 and dd is not None and dd < -15:
        return "PANIC"

    if vix > 22 and not above_200:
        return "BEAR"

    if vix_declining and above_50 and dd is not None and dd < -5:
        return "RECOVERY"

    if vix < 13 and above_200 and breadth:
        return "EUPHORIA"

    if vix < 20 and above_200 and above_50:
        return "BULL"

    # Edge cases: default based on VIX level and trend
    if vix >= 20:
        return "BEAR"
    return "BULL"


def _compute_horizon_score(groups, weights):
    """Compute weighted composite for a specific time horizon."""
    return _clamp(
        sum(groups[k]["composite"] * weights.get(k, 0) for k in groups),
        -5, 5,
    )


# ---------------------------------------------------------------------------
# 1. Momentum Factors
# ---------------------------------------------------------------------------

def _compute_momentum(hist, info):
    closes = hist["Close"].values.astype(float)
    n = len(closes)
    sub = []

    def ret(days):
        return (closes[-1] / closes[-days] - 1) * 100 if n > days else None

    def score_ret(r, thresholds):
        return _thresh(r, thresholds) if r is not None else 0.0

    sub.append({
        "name": "1M Momentum", "name_cn": "1月动量",
        "value": _fmt(ret(21), 1),
        "score": score_ret(ret(21), [(-8, -4), (-3, -2), (0, 0), (5, 2), (10, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance history(2y) Close",
    })
    sub.append({
        "name": "3M Momentum", "name_cn": "3月动量",
        "value": _fmt(ret(63), 1),
        "score": score_ret(ret(63), [(-15, -4), (-5, -2), (0, 0), (8, 2), (20, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance history(2y) Close",
    })
    sub.append({
        "name": "6M Momentum", "name_cn": "6月动量",
        "value": _fmt(ret(126), 1),
        "score": score_ret(ret(126), [(-20, -4), (-8, -2), (0, 0), (12, 2), (30, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance history(2y) Close",
    })
    sub.append({
        "name": "12M Momentum", "name_cn": "12月动量",
        "value": _fmt(ret(252), 1),
        "score": score_ret(ret(252), [(-25, -4), (-10, -2), (0, 0), (15, 2), (40, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance history(2y) Close",
    })

    rsi = _calc_rsi(closes, 14)
    rsi_score = 0.0
    if rsi is not None:
        if rsi > 75:
            rsi_score = -3.0
        elif rsi > 60:
            rsi_score = 2.0
        elif rsi > 40:
            rsi_score = 0.0
        elif rsi > 25:
            rsi_score = -2.0
        else:
            rsi_score = -4.0
    sub.append({
        "name": "RSI (14)", "name_cn": "RSI指标",
        "value": _fmt(rsi, 1), "score": rsi_score, "unit": "",
        "source": "yfinance history(2y) Close, RSI-14",
    })

    macd_score = 0.0
    macd_histogram_value = None
    if n >= 35:
        try:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            macd_vals = ema12 - ema26
            signal_vals = _ema(macd_vals, 9)
            macd_now = float(macd_vals[-1])
            sig_now = float(signal_vals[-1])
            macd_histogram_value = round(macd_now - sig_now, 4)
            if macd_now > sig_now:
                macd_score = 3.0 if macd_now > 0 else 1.0
            else:
                macd_score = -3.0 if macd_now < 0 else -1.0
        except Exception:
            pass
    sub.append({
        "name": "MACD Signal", "name_cn": "MACD信号",
        "value": _fmt(macd_histogram_value, 2) if macd_histogram_value is not None else None,
        "score": macd_score, "unit": "",
        "source": "yfinance history(2y) Close, EMA12/26",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Momentum", "label_cn": "动量", "factors": sub,
        "data_source_summary": "yfinance 2-year price history",
    }


# ---------------------------------------------------------------------------
# 2. Value Factors (sector-adjusted)
# ---------------------------------------------------------------------------

def _compute_value(info, profile=None):
    if profile is None:
        profile = DEFAULT_SECTOR_PROFILE
    sub = []

    pe_lo, pe_hi = profile["pe_range"]
    pe = info.get("trailingPE") or info.get("forwardPE")
    pe_score = _score_valuation_ratio(pe, pe_lo, pe_hi)
    sub.append({
        "name": "P/E Ratio", "name_cn": "市盈率",
        "value": _fmt(pe, 1), "score": pe_score, "unit": "x",
        "source": "yfinance info.trailingPE",
    })

    pb_lo, pb_hi = profile["pb_range"]
    pb = info.get("priceToBook")
    pb_score = _score_valuation_ratio(pb, pb_lo, pb_hi)
    sub.append({
        "name": "P/B Ratio", "name_cn": "市净率",
        "value": _fmt(pb, 2), "score": pb_score, "unit": "x",
        "source": "yfinance info.priceToBook",
    })

    ev_lo, ev_hi = profile["ev_ebitda_range"]
    ev_ebitda = info.get("enterpriseToEbitda")
    ev_score = _score_valuation_ratio(ev_ebitda, ev_lo, ev_hi)
    sub.append({
        "name": "EV/EBITDA", "name_cn": "企业价值倍数",
        "value": _fmt(ev_ebitda, 1), "score": ev_score, "unit": "x",
        "source": "yfinance info.enterpriseToEbitda",
    })

    ps = info.get("priceToSalesTrailing12Months")
    sub.append({
        "name": "P/S Ratio", "name_cn": "市销率",
        "value": _fmt(ps, 2),
        "score": _thresh(ps, [(1, 5), (3, 3), (6, 1), (10, -1), (20, -3), (9999, -5)]),
        "unit": "x",
        "source": "yfinance info.priceToSalesTrailing12Months",
    })

    dy = info.get("dividendYield")
    dy_pct = (dy * 100) if dy else None
    if profile.get("dividend_focus"):
        dy_score = _thresh(
            dy_pct, [(0, -2), (1, 0), (2, 2), (3, 3), (4, 4), (9999, 5)],
        ) if dy_pct is not None else -1.0
    else:
        dy_score = (
            4.0 if dy_pct and dy_pct > 4
            else (2.0 if dy_pct and dy_pct > 2
                  else (1.0 if dy_pct and dy_pct > 0 else 0.0))
        )
    sub.append({
        "name": "Dividend Yield", "name_cn": "股息率",
        "value": _fmt(dy_pct, 2), "score": dy_score, "unit": "%",
        "source": "yfinance info.dividendYield",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Value", "label_cn": "估值", "factors": sub,
        "data_source_summary": "yfinance real-time fundamentals (quarterly reported)",
    }


def _score_valuation_ratio(value, sector_low, sector_high):
    """Score a valuation ratio against its sector-specific normal range.

    Below range = cheap (positive score). Above range = expensive (negative).
    """
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return 0.0
    if value < 0:
        return -3.0  # Negative P/E means losses
    mid = (sector_low + sector_high) / 2
    half_range = (sector_high - sector_low) / 2
    if half_range == 0:
        half_range = 1.0
    # Normalize: how many half-ranges below the midpoint
    z = (mid - value) / half_range
    return _clamp(z * 2.5, -5, 5)


# ---------------------------------------------------------------------------
# 3. Quality Factors
# ---------------------------------------------------------------------------

def _compute_quality(info):
    sub = []

    roe = info.get("returnOnEquity")
    roe_pct = (roe * 100) if roe else None
    sub.append({
        "name": "ROE", "name_cn": "净资产收益率",
        "value": _fmt(roe_pct, 1),
        "score": _thresh(roe_pct, [(-5, -5), (0, -3), (8, -1), (15, 2), (25, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.returnOnEquity",
    })

    roa = info.get("returnOnAssets")
    roa_pct = (roa * 100) if roa else None
    sub.append({
        "name": "ROA", "name_cn": "总资产收益率",
        "value": _fmt(roa_pct, 1),
        "score": _thresh(roa_pct, [(-2, -5), (0, -3), (3, -1), (7, 2), (12, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.returnOnAssets",
    })

    gm = info.get("grossMargins")
    gm_pct = (gm * 100) if gm else None
    sub.append({
        "name": "Gross Margin", "name_cn": "毛利率",
        "value": _fmt(gm_pct, 1),
        "score": _thresh(gm_pct, [(10, -3), (20, -1), (35, 1), (50, 3), (65, 4), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.grossMargins",
    })

    om = info.get("operatingMargins")
    om_pct = (om * 100) if om else None
    sub.append({
        "name": "Operating Margin", "name_cn": "营业利润率",
        "value": _fmt(om_pct, 1),
        "score": _thresh(om_pct, [(-5, -5), (0, -3), (5, -1), (12, 1), (20, 3), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.operatingMargins",
    })

    de = info.get("debtToEquity")
    sub.append({
        "name": "Debt/Equity", "name_cn": "负债权益比",
        "value": _fmt(de, 1),
        "score": _thresh(de, [(20, 5), (50, 3), (100, 1), (150, -1), (200, -3), (9999, -5)]),
        "unit": "%",
        "source": "yfinance info.debtToEquity",
    })

    cr = info.get("currentRatio")
    sub.append({
        "name": "Current Ratio", "name_cn": "流动比率",
        "value": _fmt(cr, 2),
        "score": _thresh(cr, [(0.5, -5), (1.0, -2), (1.5, 1), (2.5, 4), (9999, 5)]),
        "unit": "x",
        "source": "yfinance info.currentRatio",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Quality", "label_cn": "质量", "factors": sub,
        "data_source_summary": "yfinance real-time fundamentals (quarterly reported)",
    }


# ---------------------------------------------------------------------------
# 4. Growth Factors
# ---------------------------------------------------------------------------

def _compute_growth(info):
    sub = []

    rg = info.get("revenueGrowth")
    rg_pct = (rg * 100) if rg else None
    sub.append({
        "name": "Revenue Growth", "name_cn": "营收增长率",
        "value": _fmt(rg_pct, 1),
        "score": _thresh(rg_pct, [(-10, -5), (-3, -3), (0, -1), (5, 1), (15, 3), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.revenueGrowth",
    })

    eg = info.get("earningsGrowth")
    eg_pct = (eg * 100) if eg else None
    sub.append({
        "name": "EPS Growth", "name_cn": "每股收益增长",
        "value": _fmt(eg_pct, 1),
        "score": _thresh(eg_pct, [(-20, -5), (-5, -3), (0, -1), (8, 1), (20, 3), (9999, 5)]),
        "unit": "%",
        "source": "yfinance info.earningsGrowth",
    })

    fwd_eps = info.get("forwardEps")
    ttm_eps = info.get("trailingEps")
    fwd_growth = None
    fwd_score = 0.0
    if fwd_eps and ttm_eps and ttm_eps != 0:
        fwd_growth = (fwd_eps / ttm_eps - 1) * 100
        fwd_score = _thresh(
            fwd_growth, [(-15, -5), (-5, -3), (0, -1), (5, 1), (15, 3), (9999, 5)],
        )
    sub.append({
        "name": "Fwd EPS Growth", "name_cn": "预期EPS增长",
        "value": _fmt(fwd_growth, 1), "score": fwd_score, "unit": "%",
        "source": "yfinance info.forwardEps / trailingEps",
    })

    rc = info.get("recommendationMean")
    rc_score = 0.0
    if rc:
        if rc <= 1.5:
            rc_score = 5.0
        elif rc <= 2.0:
            rc_score = 3.0
        elif rc <= 2.5:
            rc_score = 1.0
        elif rc <= 3.5:
            rc_score = -2.0
        else:
            rc_score = -4.0
    sub.append({
        "name": "Analyst Rating", "name_cn": "分析师评级",
        "value": _fmt(rc, 2), "score": rc_score, "unit": "/5",
        "source": "yfinance info.recommendationMean",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Growth", "label_cn": "成长", "factors": sub,
        "data_source_summary": "yfinance real-time fundamentals + analyst estimates",
    }


# ---------------------------------------------------------------------------
# 5. Volatility Factors (lower risk = higher score)
# ---------------------------------------------------------------------------

def _compute_volatility(hist, info):
    sub = []
    closes = hist["Close"].values.astype(float)
    n = len(closes)

    beta = info.get("beta")
    beta_score = 0.0
    if beta:
        if beta < 0.5:
            beta_score = 4.0
        elif beta < 0.8:
            beta_score = 3.0
        elif beta < 1.0:
            beta_score = 2.0
        elif beta < 1.2:
            beta_score = 0.0
        elif beta < 1.5:
            beta_score = -2.0
        else:
            beta_score = -4.0
    sub.append({
        "name": "Beta", "name_cn": "贝塔系数",
        "value": _fmt(beta, 2), "score": beta_score, "unit": "",
        "source": "yfinance info.beta",
    })

    if n >= 30:
        rets = np.diff(np.log(closes[-31:]))
        rv = float(np.std(rets) * np.sqrt(252) * 100)
        sub.append({
            "name": "30D Realized Vol", "name_cn": "30日波动率",
            "value": _fmt(rv, 1),
            "score": _thresh(rv, [(15, 5), (25, 3), (35, 1), (50, -1), (70, -3), (9999, -5)]),
            "unit": "%",
            "source": "yfinance history(2y) Close, 30d log returns",
        })

    if n >= 50:
        window = closes[-min(252, n):]
        rolling_max = np.maximum.accumulate(window)
        dd = (window / rolling_max - 1) * 100
        max_dd = float(dd.min())
        sub.append({
            "name": "Max Drawdown (1Y)", "name_cn": "最大回撤",
            "value": _fmt(max_dd, 1),
            "score": _thresh(max_dd, [(-50, -5), (-30, -3), (-20, -1), (-10, 1), (-5, 3), (0, 4)]),
            "unit": "%",
            "source": "yfinance history(2y) Close, rolling max",
        })

    if n >= 15:
        hi = hist["High"].values[-15:].astype(float)
        lo = hist["Low"].values[-15:].astype(float)
        cl = hist["Close"].values[-15:].astype(float)
        tr_vals = [
            max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
            for i in range(1, 15)
        ]
        atr_pct = float(np.mean(tr_vals)) / closes[-1] * 100
        sub.append({
            "name": "ATR % of Price", "name_cn": "真实波幅占比",
            "value": _fmt(atr_pct, 2),
            "score": _thresh(atr_pct, [(0.5, 5), (1.0, 3), (2.0, 1), (3.5, -1), (5.0, -3), (9999, -5)]),
            "unit": "%",
            "source": "yfinance history(2y) High/Low/Close",
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Volatility", "label_cn": "波动性", "factors": sub,
        "data_source_summary": "yfinance price history + fundamentals",
    }


# ---------------------------------------------------------------------------
# 6. Sentiment Factors
# ---------------------------------------------------------------------------

def _compute_sentiment(stock, info):
    sub = []

    sp = info.get("shortPercentOfFloat")
    if sp:
        sp_pct = sp * 100
        sub.append({
            "name": "Short Interest", "name_cn": "空头仓位",
            "value": _fmt(sp_pct, 1),
            "score": _thresh(sp_pct, [(2, 4), (5, 2), (10, -1), (20, -3), (9999, -5)]),
            "unit": "%",
            "source": "yfinance info.shortPercentOfFloat",
        })

    inst = info.get("heldPercentInstitutions")
    if inst:
        ip = inst * 100
        sub.append({
            "name": "Institutional Hold.", "name_cn": "机构持仓",
            "value": _fmt(ip, 1),
            "score": _thresh(ip, [(20, -3), (40, 0), (60, 2), (80, 4), (9999, 4)]),
            "unit": "%",
            "source": "yfinance info.heldPercentInstitutions",
        })

    ins_score = 0.0
    try:
        import pandas as pd
        txns = stock.insider_transactions
        if txns is not None and not txns.empty:
            recent = txns.head(20)
            if "Shares" in recent.columns:
                txn_col = None
                for col in ("Transaction", "transaction"):
                    if col in recent.columns:
                        txn_col = col
                        break
                if txn_col:
                    buys = recent[
                        recent[txn_col].astype(str).str.contains(
                            "Buy|Purchase", case=False, na=False,
                        )
                    ]["Shares"].sum()
                    sells = recent[
                        recent[txn_col].astype(str).str.contains(
                            "Sell|Sale", case=False, na=False,
                        )
                    ]["Shares"].sum()
                    ins_score = 2.0 if buys > sells else (-2.0 if sells > buys else 0.0)
    except Exception:
        pass
    sub.append({
        "name": "Insider Activity", "name_cn": "内部人员活动",
        "value": None, "score": ins_score, "unit": "",
        "source": "yfinance insider_transactions",
    })

    rc = info.get("recommendationMean")
    if rc:
        rc_score = _thresh(rc, [(1.5, 5), (2.0, 3), (2.5, 1), (3.0, -1), (9999, -3)])
        sub.append({
            "name": "Analyst Consensus", "name_cn": "分析师共识",
            "value": _fmt(rc, 2), "score": rc_score, "unit": "/5",
            "source": "yfinance info.recommendationMean",
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {
        "composite": round(composite, 2),
        "label": "Sentiment", "label_cn": "情绪", "factors": sub,
        "data_source_summary": "yfinance fundamentals + insider transactions",
    }


# ---------------------------------------------------------------------------
# 7. Macro Factors
# ---------------------------------------------------------------------------

def _compute_macro(hist, ticker="", sector="", info=None):
    sub = []
    closes = hist["Close"].values.astype(float)
    n = len(closes)

    spy_hist_data = None
    try:
        spy_hist_data = yf.Ticker("SPY").history(period="1y")["Close"].values.astype(float)
        min_len = min(n, len(spy_hist_data))
        if min_len > 60:
            r1 = np.diff(np.log(closes[-min_len:]))
            r2 = np.diff(np.log(spy_hist_data[-min_len:]))
            corr = float(np.corrcoef(r1, r2)[0, 1])
            sub.append({
                "name": "Market Correlation", "name_cn": "市场相关性",
                "value": _fmt(corr, 2), "score": _clamp(-corr * 3.0), "unit": "",
                "source": "yfinance SPY + stock history(1y)",
            })
            if min_len >= 252:
                stock_ret = (closes[-1] / closes[-252] - 1) * 100
                spy_ret = (spy_hist_data[-1] / spy_hist_data[-252] - 1) * 100
                rs = stock_ret - spy_ret
                sub.append({
                    "name": "Relative Strength (1Y)", "name_cn": "相对强度",
                    "value": _fmt(rs, 1),
                    "score": _thresh(rs, [(-20, -5), (-10, -3), (-3, -1), (3, 1), (10, 3), (9999, 5)]),
                    "unit": "%",
                    "source": "yfinance SPY + stock history(1y)",
                })
    except Exception:
        pass

    if n >= 52:
        window = closes[-min(252, n):]
        hi_52 = float(window.max())
        lo_52 = float(window.min())
        if hi_52 != lo_52:
            pos = (closes[-1] - lo_52) / (hi_52 - lo_52) * 100
            sub.append({
                "name": "52W Range Position", "name_cn": "52周位置",
                "value": _fmt(pos, 1),
                "score": _thresh(pos, [(10, -4), (25, -2), (40, 0), (60, 1), (75, 3), (9999, 4)]),
                "unit": "%",
                "source": "yfinance stock history(1y)",
            })

    # Sector Momentum vs Market: compare sector ETF 3M return vs SPY 3M return
    etf_symbol = SECTOR_ETF_MAP.get(sector, "SPY")
    if etf_symbol != "SPY":
        try:
            etf_hist = yf.Ticker(etf_symbol).history(period="6mo")["Close"].values.astype(float)
            if len(etf_hist) >= 63 and spy_hist_data is not None and len(spy_hist_data) >= 63:
                etf_3m = (etf_hist[-1] / etf_hist[-63] - 1) * 100
                spy_3m = (spy_hist_data[-1] / spy_hist_data[-63] - 1) * 100
                sector_vs_mkt = etf_3m - spy_3m
                sub.append({
                    "name": "Sector vs Market (3M)", "name_cn": "板块相对大盘(3月)",
                    "value": _fmt(sector_vs_mkt, 1),
                    "score": _thresh(sector_vs_mkt, [(-8, -4), (-3, -2), (0, 0), (3, 2), (8, 4), (9999, 5)]),
                    "unit": "%",
                    "source": f"yfinance {etf_symbol} vs SPY 3M return",
                })
        except Exception:
            pass

    # Dollar Impact: USD strength via DXY proxy (DX-Y.NYB)
    # Strong dollar is typically negative for international revenue companies
    try:
        dxy_hist = yf.Ticker("DX-Y.NYB").history(period="3mo")["Close"].values.astype(float)
        if len(dxy_hist) >= 21:
            dxy_1m_change = (dxy_hist[-1] / dxy_hist[-21] - 1) * 100
            # Strong USD = negative for most equities (especially multinationals)
            dxy_score = _thresh(
                dxy_1m_change,
                [(-3, 4), (-1, 2), (0, 1), (1, -1), (3, -3), (9999, -4)],
            )
            sub.append({
                "name": "Dollar Impact (DXY 1M)", "name_cn": "美元影响(1月)",
                "value": _fmt(dxy_1m_change, 1),
                "score": dxy_score, "unit": "%",
                "source": "yfinance DX-Y.NYB 1-month change",
            })
    except Exception:
        pass

    # Interest Rate Sensitivity: correlation of stock returns with 10Y yield changes
    try:
        tnx_hist = yf.Ticker("^TNX").history(period="1y")["Close"].values.astype(float)
        min_ir_len = min(n, len(tnx_hist))
        if min_ir_len > 60:
            stock_rets = np.diff(np.log(closes[-min_ir_len:]))
            yield_changes = np.diff(tnx_hist[-min_ir_len:])
            ir_corr = float(np.corrcoef(stock_rets, yield_changes)[0, 1])
            # Positive correlation with rising yields = rate-sensitive (negative score)
            # Negative correlation = benefits from lower rates
            ir_score = _thresh(
                ir_corr,
                [(-0.3, 3), (-0.1, 1), (0.1, 0), (0.3, -2), (9999, -4)],
            )
            sub.append({
                "name": "Rate Sensitivity", "name_cn": "利率敏感度",
                "value": _fmt(ir_corr, 2),
                "score": ir_score, "unit": "",
                "source": "yfinance stock vs ^TNX correlation (1Y)",
            })
    except Exception:
        pass

    # Gold/Risk Correlation: stock correlation with gold (GC=F)
    try:
        gold_hist = yf.Ticker("GC=F").history(period="1y")["Close"].values.astype(float)
        min_gold_len = min(n, len(gold_hist))
        if min_gold_len > 60:
            stock_rets = np.diff(np.log(closes[-min_gold_len:]))
            gold_rets = np.diff(np.log(gold_hist[-min_gold_len:]))
            gold_corr = float(np.corrcoef(stock_rets, gold_rets)[0, 1])
            # High gold correlation = safe-haven behavior = defensive
            # Mildly positive = neutral, strongly negative = risk-on
            gold_score = _thresh(
                gold_corr,
                [(-0.3, 2), (-0.1, 1), (0.1, 0), (0.3, -1), (9999, -3)],
            )
            sub.append({
                "name": "Gold/Risk Correlation", "name_cn": "黄金避险相关性",
                "value": _fmt(gold_corr, 2),
                "score": gold_score, "unit": "",
                "source": "yfinance stock vs GC=F correlation (1Y)",
            })
    except Exception:
        pass

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {
        "composite": round(composite, 2),
        "label": "Macro", "label_cn": "宏观", "factors": sub,
        "data_source_summary": "yfinance SPY benchmark + stock price history + DXY + ^TNX + GC=F",
    }


# ---------------------------------------------------------------------------
# 8. Economic Cycle Factor
# ---------------------------------------------------------------------------

# Geographic revenue weights for major tickers (approximate annual report data)
GEOGRAPHIC_REVENUE_WEIGHTS = {
    "AAPL": {"US": 0.42, "Europe": 0.25, "China": 0.19, "Japan": 0.07, "Other": 0.07},
    "MSFT": {"US": 0.50, "Europe": 0.25, "Other": 0.25},
    "NVDA": {"US": 0.27, "China": 0.25, "Other": 0.48},
    "AMZN": {"US": 0.60, "Europe": 0.25, "Other": 0.15},
    "GOOGL": {"US": 0.47, "Europe": 0.30, "Other": 0.23},
    "META": {"US": 0.42, "Europe": 0.24, "Other": 0.34},
    "TSLA": {"US": 0.47, "China": 0.22, "Europe": 0.20, "Other": 0.11},
    "AVGO": {"US": 0.35, "China": 0.30, "Other": 0.35},
    "JPM": {"US": 0.75, "Europe": 0.15, "Other": 0.10},
    "V": {"US": 0.45, "Europe": 0.25, "Other": 0.30},
    "QCOM": {"US": 0.25, "China": 0.65, "Other": 0.10},
    "AMD": {"US": 0.30, "China": 0.25, "Other": 0.45},
    "INTC": {"US": 0.35, "China": 0.27, "Other": 0.38},
    "NFLX": {"US": 0.45, "Europe": 0.30, "Other": 0.25},
    "CRM": {"US": 0.65, "Europe": 0.20, "Other": 0.15},
    "ADBE": {"US": 0.55, "Europe": 0.25, "Other": 0.20},
    "ORCL": {"US": 0.55, "Europe": 0.25, "Other": 0.20},
    "TXN": {"US": 0.30, "China": 0.35, "Other": 0.35},
    "AMAT": {"US": 0.20, "China": 0.30, "Other": 0.50},
    "CAT": {"US": 0.45, "Europe": 0.20, "China": 0.10, "Other": 0.25},
}


def _get_geographic_weights(ticker, country, info=None):
    """Determine economic region weights for a stock.

    Returns a dict like {"US": 0.42, "China": 0.19, "Europe": 0.25, ...}.
    Falls back to single-country allocation when no data is available.
    """
    # Check hardcoded weights first
    if ticker in GEOGRAPHIC_REVENUE_WEIGHTS:
        return GEOGRAPHIC_REVENUE_WEIGHTS[ticker]

    # Determine primary country/region
    country = (country or "").strip()
    exchange = ""
    if info:
        exchange = (info.get("exchange", "") or "").upper()

    is_chinese = (
        country in ("China", "Hong Kong")
        or any(x in exchange for x in ("HK", "HKSE", "SHG", "SHE", "SZ"))
        or ticker.endswith(".HK") or ticker.endswith(".SS") or ticker.endswith(".SZ")
    )

    is_european = country in (
        "United Kingdom", "Germany", "France", "Switzerland", "Netherlands",
        "Spain", "Italy", "Sweden", "Denmark", "Norway", "Finland",
        "Belgium", "Ireland", "Austria", "Luxembourg", "Portugal",
    )

    if is_chinese:
        return {"China": 0.80, "US": 0.10, "Other": 0.10}
    if is_european:
        return {"Europe": 0.70, "US": 0.20, "Other": 0.10}

    # Default: US-dominant company
    return {"US": 1.0}


def _get_us_economic_factors(ind):
    """Compute US economic factors from FRED macro indicator data."""
    sub = []

    # CPI trend: rising inflation negative for growth
    cpi = ind.get("cpi_yoy") or ind.get("_implied_cpi")
    if cpi is not None:
        cpi_score = _thresh(
            cpi, [(2, 3), (3, 1), (4, -1), (5, -3), (9999, -5)],
        )
        sub.append({
            "name": "CPI Inflation", "name_cn": "消费者物价指数",
            "value": _fmt(cpi, 1), "score": cpi_score, "unit": "%",
            "source": "FRED CPI YoY% change",
        })

    # GDP growth direction
    gdp = ind.get("gdp_growth")
    if gdp is not None:
        gdp_score = _thresh(
            gdp, [(-2, -5), (0, -3), (1, -1), (2, 1), (3, 3), (9999, 5)],
        )
        sub.append({
            "name": "GDP Growth", "name_cn": "GDP增长率",
            "value": _fmt(gdp, 1), "score": gdp_score, "unit": "%",
            "source": "FRED GDP growth rate",
        })

    # Consumer sentiment (FRED or proxy)
    cs = ind.get("consumer_sentiment")
    if cs is not None:
        cs_score = _thresh(
            cs, [(50, -5), (60, -3), (70, -1), (80, 1), (90, 3), (9999, 5)],
        )
        sub.append({
            "name": "Consumer Sentiment", "name_cn": "消费者信心指数",
            "value": _fmt(cs, 1), "score": cs_score, "unit": "",
            "source": "FRED consumer sentiment index",
        })
    elif ind.get("_consumer_proxy") is not None:
        cp = ind["_consumer_proxy"]
        cp_score = _thresh(
            cp, [(-5, -4), (-2, -2), (0, 0), (2, 2), (5, 4), (9999, 5)],
        )
        sub.append({
            "name": "Consumer Confidence Proxy", "name_cn": "消费信心代理指标",
            "value": _fmt(cp, 1), "score": cp_score, "unit": "%",
            "source": "yfinance XLY/XLP relative performance",
        })

    # Unemployment rate
    unemp = ind.get("unemployment")
    if unemp is not None:
        unemp_score = _thresh(
            unemp, [(3.5, 5), (4.0, 3), (5.0, 1), (6.0, -1), (7.0, -3), (9999, -5)],
        )
        sub.append({
            "name": "Unemployment Rate", "name_cn": "失业率",
            "value": _fmt(unemp, 1), "score": unemp_score, "unit": "%",
            "source": "FRED unemployment rate",
        })

    # Yield curve shape
    yc_inverted = ind.get("yield_curve_inverted")
    yc_spread = ind.get("yield_curve_spread")
    if yc_spread is not None:
        if yc_inverted:
            yc_score = _thresh(
                yc_spread, [(-1.0, -5), (-0.5, -4), (-0.1, -2), (9999, -1)],
            )
        else:
            yc_score = _thresh(
                yc_spread, [(0.2, 0), (0.5, 1), (1.0, 2), (1.5, 3), (9999, 4)],
            )
        sub.append({
            "name": "Yield Curve Spread", "name_cn": "收益率曲线利差",
            "value": _fmt(yc_spread, 2), "score": yc_score,
            "unit": "bps" if abs(yc_spread) < 1 else "%",
            "source": "FRED / yfinance ^TNX, ^FVX",
        })

    # Industrial Production YoY% (manufacturing activity proxy for ISM PMI)
    ip_yoy = ind.get("industrial_production_yoy")
    if ip_yoy is not None:
        ip_score = _thresh(
            ip_yoy, [(-5, -5), (-2, -3), (0, -1), (2, 1), (4, 3), (9999, 5)],
        )
        sub.append({
            "name": "Industrial Production YoY", "name_cn": "工业生产同比",
            "value": _fmt(ip_yoy, 1), "score": ip_score, "unit": "% YoY",
            "source": "FRED INDPRO YoY% change",
        })

    # Retail sales YoY growth
    retail = ind.get("retail_sales")
    if retail is not None:
        retail_score = _thresh(
            retail, [(-5, -5), (-2, -3), (0, -1), (3, 1), (6, 3), (9999, 5)],
        )
        sub.append({
            "name": "Retail Sales Growth", "name_cn": "零售销售增长",
            "value": _fmt(retail, 1), "score": retail_score, "unit": "% YoY",
            "source": "FRED retail sales YoY% change",
        })

    # Real interest rate
    real_rate = ind.get("real_interest_rate")
    if real_rate is not None:
        rr_score = _thresh(
            real_rate, [(-2, 4), (-1, 3), (0, 1), (1, -1), (2, -3), (9999, -5)],
        )
        sub.append({
            "name": "Real Interest Rate", "name_cn": "实际利率",
            "value": _fmt(real_rate, 2), "score": rr_score, "unit": "%",
            "source": "FRED (fed funds rate - CPI YoY)",
        })

    # Housing starts
    housing = ind.get("housing_starts")
    if housing is not None:
        hs_score = _thresh(
            housing, [(1000, -3), (1200, -1), (1400, 1), (1600, 3), (9999, 5)],
        )
        sub.append({
            "name": "Housing Starts", "name_cn": "新屋开工数",
            "value": _fmt(housing, 0), "score": hs_score, "unit": "K",
            "source": "FRED housing starts",
        })

    return sub


def _get_china_economic_factors():
    """Compute Chinese economy factors using yfinance-accessible proxies.

    Uses Hang Seng Index, USD/CNY exchange rate, and China Large-Cap ETF
    as proxies for Chinese economic conditions.
    """
    sub = []

    # Hang Seng Index 3M return (China/HK market momentum)
    try:
        hsi_hist = yf.Ticker("^HSI").history(period="6mo")["Close"].values.astype(float)
        if len(hsi_hist) >= 63:
            hsi_3m = (hsi_hist[-1] / hsi_hist[-63] - 1) * 100
            hsi_score = _thresh(
                hsi_3m, [(-15, -5), (-8, -3), (-2, -1), (2, 1), (8, 3), (9999, 5)],
            )
            sub.append({
                "name": "HSI Momentum (3M)", "name_cn": "恒生指数动量(3月)",
                "value": _fmt(hsi_3m, 1), "score": hsi_score, "unit": "%",
                "source": "yfinance ^HSI 3-month return",
            })
    except Exception:
        pass

    # USD/CNY exchange rate trend (strong yuan = positive for Chinese economy)
    try:
        cny_hist = yf.Ticker("CNY=X").history(period="3mo")["Close"].values.astype(float)
        if len(cny_hist) >= 21:
            # CNY=X is USD/CNY: lower = stronger yuan
            cny_1m_change = (cny_hist[-1] / cny_hist[-21] - 1) * 100
            # Negative change (yuan strengthening) is positive
            cny_score = _thresh(
                cny_1m_change,
                [(-2, 4), (-1, 2), (0, 0), (1, -2), (2, -4), (9999, -5)],
            )
            sub.append({
                "name": "Yuan Strength (1M)", "name_cn": "人民币走势(1月)",
                "value": _fmt(-cny_1m_change, 1),
                "score": cny_score, "unit": "%",
                "source": "yfinance CNY=X 1-month change (inverted)",
            })
    except Exception:
        pass

    # FXI (iShares China Large-Cap ETF) momentum
    try:
        fxi_hist = yf.Ticker("FXI").history(period="6mo")["Close"].values.astype(float)
        if len(fxi_hist) >= 63:
            fxi_3m = (fxi_hist[-1] / fxi_hist[-63] - 1) * 100
            fxi_score = _thresh(
                fxi_3m, [(-15, -5), (-8, -3), (-2, -1), (2, 1), (8, 3), (9999, 5)],
            )
            sub.append({
                "name": "China ETF Momentum (3M)", "name_cn": "中国ETF动量(3月)",
                "value": _fmt(fxi_3m, 1), "score": fxi_score, "unit": "%",
                "source": "yfinance FXI (iShares China Large-Cap) 3-month return",
            })
    except Exception:
        pass

    # China vs US relative performance (FXI vs SPY)
    try:
        spy_hist = yf.Ticker("SPY").history(period="3mo")["Close"].values.astype(float)
        fxi_hist_short = yf.Ticker("FXI").history(period="3mo")["Close"].values.astype(float)
        min_len = min(len(spy_hist), len(fxi_hist_short))
        if min_len >= 21:
            fxi_ret = (fxi_hist_short[-1] / fxi_hist_short[-21] - 1) * 100
            spy_ret = (spy_hist[-1] / spy_hist[-21] - 1) * 100
            cn_vs_us = fxi_ret - spy_ret
            cn_vs_score = _thresh(
                cn_vs_us, [(-10, -4), (-5, -2), (0, 0), (5, 2), (10, 4), (9999, 5)],
            )
            sub.append({
                "name": "China vs US (1M)", "name_cn": "中美市场对比(1月)",
                "value": _fmt(cn_vs_us, 1), "score": cn_vs_score, "unit": "%",
                "source": "yfinance FXI vs SPY 1-month relative return",
            })
    except Exception:
        pass

    return sub


def _get_europe_economic_factors():
    """Compute European economy factors using yfinance-accessible proxies.

    Uses Euro Stoxx 50, EUR/USD exchange rate, and Eurozone ETF.
    """
    sub = []

    # Euro Stoxx 50 3M return
    try:
        stoxx_hist = yf.Ticker("^STOXX50E").history(period="6mo")["Close"].values.astype(float)
        if len(stoxx_hist) >= 63:
            stoxx_3m = (stoxx_hist[-1] / stoxx_hist[-63] - 1) * 100
            stoxx_score = _thresh(
                stoxx_3m, [(-12, -5), (-6, -3), (-2, -1), (2, 1), (6, 3), (9999, 5)],
            )
            sub.append({
                "name": "Euro Stoxx 50 (3M)", "name_cn": "欧洲斯托克50(3月)",
                "value": _fmt(stoxx_3m, 1), "score": stoxx_score, "unit": "%",
                "source": "yfinance ^STOXX50E 3-month return",
            })
    except Exception:
        pass

    # EUR/USD trend (strong euro = positive for European economy)
    try:
        eur_hist = yf.Ticker("EURUSD=X").history(period="3mo")["Close"].values.astype(float)
        if len(eur_hist) >= 21:
            eur_1m_change = (eur_hist[-1] / eur_hist[-21] - 1) * 100
            eur_score = _thresh(
                eur_1m_change,
                [(-3, -4), (-1, -2), (0, 0), (1, 2), (3, 4), (9999, 5)],
            )
            sub.append({
                "name": "EUR/USD Trend (1M)", "name_cn": "欧元走势(1月)",
                "value": _fmt(eur_1m_change, 1),
                "score": eur_score, "unit": "%",
                "source": "yfinance EURUSD=X 1-month change",
            })
    except Exception:
        pass

    # EZU (iShares MSCI Eurozone ETF) vs SPY relative performance
    try:
        ezu_hist = yf.Ticker("EZU").history(period="3mo")["Close"].values.astype(float)
        spy_hist = yf.Ticker("SPY").history(period="3mo")["Close"].values.astype(float)
        min_len = min(len(ezu_hist), len(spy_hist))
        if min_len >= 21:
            ezu_ret = (ezu_hist[-1] / ezu_hist[-21] - 1) * 100
            spy_ret = (spy_hist[-1] / spy_hist[-21] - 1) * 100
            eu_vs_us = ezu_ret - spy_ret
            eu_vs_score = _thresh(
                eu_vs_us, [(-8, -4), (-3, -2), (0, 0), (3, 2), (8, 4), (9999, 5)],
            )
            sub.append({
                "name": "Europe vs US (1M)", "name_cn": "欧美市场对比(1月)",
                "value": _fmt(eu_vs_us, 1), "score": eu_vs_score, "unit": "%",
                "source": "yfinance EZU vs SPY 1-month relative return",
            })
    except Exception:
        pass

    return sub


def _compute_economic(ticker="", country="", info=None):
    """Score economic conditions for equity favorability.

    Country-aware: uses geographic revenue weights to blend US, China,
    and Europe economic indicators for multinational companies.
    For single-region companies, uses only that region's indicators.
    """
    now = datetime.now(timezone.utc)
    cache_key = f"economic_{ticker or 'global'}"
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    # Determine geographic weights for this stock
    geo_weights = _get_geographic_weights(ticker, country, info)

    # Fetch US FRED data (shared across all computations)
    ind = {}
    try:
        macro = get_macro_indicators()
        ind = macro.get("indicators", {})
    except Exception:
        pass

    # Fallback: if FRED data is all nulls, fetch key indicators from yfinance
    all_null = all(v is None for v in ind.values()) if ind else True
    if all_null:
        try:
            tnx = yf.Ticker("^TNX").history(period="5d")
            if not tnx.empty:
                ind["treasury_10y"] = round(float(tnx["Close"].iloc[-1]), 2)
            irx = yf.Ticker("^IRX").history(period="5d")
            if not irx.empty:
                ind["treasury_3mo"] = round(float(irx["Close"].iloc[-1]), 2)
            fvx = yf.Ticker("^FVX").history(period="5d")
            if not fvx.empty:
                ind["treasury_2y"] = round(float(fvx["Close"].iloc[-1]), 2)
            if ind.get("treasury_10y") and ind.get("treasury_2y"):
                spread = ind["treasury_10y"] - ind["treasury_2y"]
                ind["yield_curve_spread"] = round(spread, 2)
                ind["yield_curve_inverted"] = spread < 0
            xly = yf.Ticker("XLY").history(period="1mo")
            xlp = yf.Ticker("XLP").history(period="1mo")
            if not xly.empty and not xlp.empty:
                xly_ret = (float(xly["Close"].iloc[-1]) / float(xly["Close"].iloc[0]) - 1)
                xlp_ret = (float(xlp["Close"].iloc[-1]) / float(xlp["Close"].iloc[0]) - 1)
                consumer_proxy = (xly_ret - xlp_ret) * 100
                ind["_consumer_proxy"] = round(consumer_proxy, 2)
            if ind.get("treasury_3mo"):
                ind["fed_funds_rate"] = ind["treasury_3mo"]
                if ind.get("treasury_10y"):
                    ind["_implied_cpi"] = round(ind["treasury_10y"] - 1.5, 1)
        except Exception as exc:
            logger.warning("Economic yfinance fallback failed: %s", exc)

    # Compute factors for each region and blend by weight
    all_factors = []
    weighted_scores = []
    is_multi_region = len(geo_weights) > 1

    for region, weight in geo_weights.items():
        if region == "US":
            region_factors = _get_us_economic_factors(ind)
        elif region == "China":
            region_factors = _get_china_economic_factors()
        elif region == "Europe":
            region_factors = _get_europe_economic_factors()
        else:
            # "Other" or unknown regions: skip (no reliable data source)
            continue

        # Label factors with region tag when multi-region
        if is_multi_region and region_factors:
            weight_pct = round(weight * 100)
            for factor in region_factors:
                factor["name"] = f"{factor['name']} ({region} {weight_pct}%)"
                factor["name_cn"] = f"{factor['name_cn']}({region} {weight_pct}%)"

        all_factors.extend(region_factors)

        if region_factors:
            region_score = _safe_mean([f["score"] for f in region_factors])
            weighted_scores.append(region_score * weight)

    composite = _clamp(sum(weighted_scores)) if weighted_scores else 0.0

    # Build region summary for data source description
    region_labels = [f"{r} {round(w * 100)}%" for r, w in geo_weights.items()]
    region_summary = ", ".join(region_labels)

    result = {
        "composite": round(composite, 2),
        "label": "Economic", "label_cn": "经济周期",
        "factors": all_factors,
        "geographic_weights": geo_weights,
        "data_source_summary": f"FRED + yfinance regional proxies ({region_summary})",
    }
    _CACHE[cache_key] = {"data": result, "ts": now}
    return result


# ---------------------------------------------------------------------------
# 9. Industry Outlook Factor
# ---------------------------------------------------------------------------

def _compute_industry_outlook(sector):
    """Score sector ETF momentum and relative strength vs S&P 500."""
    now = datetime.now(timezone.utc)
    cache_key = f"industry_{sector}"
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    sub = []
    etf_symbol = SECTOR_ETF_MAP.get(sector, "SPY")

    try:
        etf_hist = yf.Ticker(etf_symbol).history(period="6mo")
        spy_hist = yf.Ticker("SPY").history(period="6mo")

        if not etf_hist.empty and not spy_hist.empty:
            etf_closes = etf_hist["Close"].values.astype(float)
            spy_closes = spy_hist["Close"].values.astype(float)
            n_etf = len(etf_closes)
            n_spy = len(spy_closes)

            # 1-week return
            if n_etf >= 5:
                week_ret = (etf_closes[-1] / etf_closes[-5] - 1) * 100
                sub.append({
                    "name": "Sector 1W Return", "name_cn": "行业1周回报",
                    "value": _fmt(week_ret, 2),
                    "score": _thresh(week_ret, [(-5, -4), (-2, -2), (0, 0), (2, 2), (5, 4), (9999, 5)]),
                    "unit": "%",
                    "source": f"yfinance {etf_symbol} history(6mo)",
                })

            # 1-month return
            if n_etf >= 21:
                month_ret = (etf_closes[-1] / etf_closes[-21] - 1) * 100
                sub.append({
                    "name": "Sector 1M Return", "name_cn": "行业1月回报",
                    "value": _fmt(month_ret, 2),
                    "score": _thresh(month_ret, [(-8, -4), (-3, -2), (0, 0), (3, 2), (8, 4), (9999, 5)]),
                    "unit": "%",
                    "source": f"yfinance {etf_symbol} history(6mo)",
                })

            # 3-month return
            if n_etf >= 63:
                q_ret = (etf_closes[-1] / etf_closes[-63] - 1) * 100
                sub.append({
                    "name": "Sector 3M Return", "name_cn": "行业3月回报",
                    "value": _fmt(q_ret, 2),
                    "score": _thresh(q_ret, [(-12, -4), (-5, -2), (0, 0), (5, 2), (12, 4), (9999, 5)]),
                    "unit": "%",
                    "source": f"yfinance {etf_symbol} history(6mo)",
                })

            # Relative strength vs S&P 500 (1 month)
            min_len = min(n_etf, n_spy)
            if min_len >= 21:
                etf_1m = (etf_closes[-1] / etf_closes[-21] - 1) * 100
                spy_1m = (spy_closes[-1] / spy_closes[-21] - 1) * 100
                rel_str = etf_1m - spy_1m
                sub.append({
                    "name": "Sector Rel. Strength", "name_cn": "行业相对强度",
                    "value": _fmt(rel_str, 2),
                    "score": _thresh(rel_str, [(-5, -4), (-2, -2), (0, 0), (2, 2), (5, 4), (9999, 5)]),
                    "unit": "%",
                    "source": f"yfinance {etf_symbol} vs SPY history(6mo)",
                })

            # Sector rotation signal: compare recent volume trend
            if n_etf >= 21 and "Volume" in etf_hist.columns:
                vol_recent = float(np.mean(etf_hist["Volume"].values[-5:]))
                vol_prior = float(np.mean(etf_hist["Volume"].values[-21:-5]))
                if vol_prior > 0:
                    vol_ratio = vol_recent / vol_prior
                    # Rising volume with rising price = money flowing in
                    price_up = etf_closes[-1] > etf_closes[-21]
                    if price_up and vol_ratio > 1.1:
                        rotation_score = 3.0
                        rotation_label = "inflow"
                    elif not price_up and vol_ratio > 1.1:
                        rotation_score = -3.0
                        rotation_label = "outflow"
                    elif price_up:
                        rotation_score = 1.0
                        rotation_label = "mild_inflow"
                    else:
                        rotation_score = -1.0
                        rotation_label = "mild_outflow"
                    sub.append({
                        "name": "Rotation Signal", "name_cn": "板块轮动信号",
                        "value": rotation_label, "score": rotation_score, "unit": "",
                        "source": f"yfinance {etf_symbol} volume + price history",
                    })

    except Exception as exc:
        logger.warning("Industry outlook failed for %s (%s): %s", sector, etf_symbol, exc)

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    result = {
        "composite": round(composite, 2),
        "label": "Industry", "label_cn": "行业前景",
        "data_source_summary": f"yfinance sector ETF ({etf_symbol}) + SPY",
        "sector_etf": etf_symbol,
        "factors": sub,
    }
    _CACHE[cache_key] = {"data": result, "ts": now}
    return result


# ---------------------------------------------------------------------------
# 10. Risk-Adjusted Return Factor
# ---------------------------------------------------------------------------

def _get_risk_free_rate():
    """Fetch annualized risk-free rate from ^TNX (10Y Treasury), cached."""
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("risk_free_rate")
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]
    rate = 0.04  # fallback 4%
    try:
        tnx = _safe_yf_close("^TNX")
        if tnx is not None:
            rate = tnx / 100.0  # ^TNX reports yield as percentage
    except Exception:
        pass
    _CACHE["risk_free_rate"] = {"data": rate, "ts": now}
    return rate


def _get_spy_returns(period_days):
    """Fetch SPY daily log returns for the given lookback period."""
    cache_key = f"spy_returns_{period_days}"
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]
    result = None
    try:
        spy_hist = yf.Ticker("SPY").history(period="2y")
        if not spy_hist.empty:
            spy_closes = spy_hist["Close"].values.astype(float)
            n = min(len(spy_closes), period_days + 1)
            if n > 20:
                result = np.diff(np.log(spy_closes[-n:]))
    except Exception:
        pass
    _CACHE[cache_key] = {"data": result, "ts": now}
    return result


def _compute_risk_adjusted_return(hist, info):
    """Score risk-adjusted return metrics as a factor (-5 to +5)."""
    try:
        closes = hist["Close"].values.astype(float)
        n = len(closes)
        if n < 60:
            return {
                "composite": 0.0, "label": "Risk-Adjusted",
                "label_cn": "风险调整回报", "factors": [],
                "data_source_summary": "yfinance price history + ^TNX + SPY benchmark",
            }

        sub = []
        rf = _get_risk_free_rate()
        daily_rf = rf / 252.0

        # Daily log returns for the stock
        daily_returns = np.diff(np.log(closes))
        ann_return = float(np.mean(daily_returns) * 252)
        ann_std = float(np.std(daily_returns) * np.sqrt(252))

        # 1. Sharpe Ratio
        sharpe = (ann_return - rf) / ann_std if ann_std > 0 else 0.0
        sharpe_score = _thresh(
            sharpe,
            [(0, -5), (0.5, -2), (1.0, 0), (1.5, 2), (2.0, 3), (9999, 5)],
        )
        sub.append({
            "name": "Sharpe Ratio", "name_cn": "夏普比率",
            "value": _fmt(sharpe, 2), "score": sharpe_score, "unit": "",
            "source": "yfinance stock history + ^TNX risk-free rate",
        })

        # 2. Sortino Ratio (downside deviation only)
        downside_returns = daily_returns[daily_returns < daily_rf]
        if len(downside_returns) > 5:
            downside_std = float(np.std(downside_returns) * np.sqrt(252))
            sortino = (ann_return - rf) / downside_std if downside_std > 0 else 0.0
        else:
            sortino = sharpe * 1.4  # approximate if insufficient downside data
        sortino_score = _thresh(
            sortino,
            [(0, -5), (0.5, -2), (1.0, 1), (1.5, 2), (2.0, 3), (9999, 5)],
        )
        sub.append({
            "name": "Sortino Ratio", "name_cn": "索提诺比率",
            "value": _fmt(sortino, 2), "score": sortino_score, "unit": "",
            "source": "yfinance stock history + ^TNX risk-free rate",
        })

        # 3. Information Ratio vs SPY
        spy_returns = _get_spy_returns(n)
        ir_score = 0.0
        ir_val = None
        if spy_returns is not None:
            min_len = min(len(daily_returns), len(spy_returns))
            if min_len > 30:
                excess = daily_returns[-min_len:] - spy_returns[-min_len:]
                tracking_error = float(np.std(excess) * np.sqrt(252))
                if tracking_error > 0:
                    ir_val = float(np.mean(excess) * 252) / tracking_error
                    ir_score = _thresh(
                        ir_val,
                        [(-0.5, -4), (0, -2), (0.5, 1), (1.0, 3), (9999, 5)],
                    )
        sub.append({
            "name": "Information Ratio", "name_cn": "信息比率",
            "value": _fmt(ir_val, 2), "score": ir_score, "unit": "",
            "source": "yfinance stock + SPY history",
        })

        # 4. Calmar Ratio: annualized return / max drawdown
        rolling_max = np.maximum.accumulate(closes)
        drawdowns = (closes / rolling_max - 1)
        max_dd = abs(float(drawdowns.min()))
        calmar = ann_return / max_dd if max_dd > 0.001 else 0.0
        calmar_score = _thresh(
            calmar,
            [(0.5, -3), (1.0, 0), (2.0, 2), (9999, 4)],
        )
        sub.append({
            "name": "Calmar Ratio", "name_cn": "卡玛比率",
            "value": _fmt(calmar, 2), "score": calmar_score, "unit": "",
            "source": "yfinance stock history, max drawdown",
        })

        # 5. Treynor Ratio: (return - rf) / beta
        beta = info.get("beta")
        treynor_val = None
        treynor_score = 0.0
        if beta and abs(beta) > 0.01:
            treynor_val = (ann_return - rf) / beta
            # Market Treynor is roughly (market_return - rf), ~7-10% range
            treynor_score = _thresh(
                treynor_val,
                [(-0.05, -4), (0, -2), (0.05, 0), (0.10, 2), (0.15, 4), (9999, 5)],
            )
        sub.append({
            "name": "Treynor Ratio", "name_cn": "特雷诺比率",
            "value": _fmt(treynor_val, 4), "score": treynor_score, "unit": "",
            "source": "yfinance stock history + info.beta + ^TNX",
        })

        # 6. Risk-Reward Scoring: upside potential vs realized downside
        target_price = info.get("targetMeanPrice")
        current_price = float(closes[-1])
        rr_val = None
        rr_score = 0.0
        if target_price and target_price > 0 and max_dd > 0.001:
            upside = (target_price / current_price - 1)
            rr_val = upside / max_dd
            rr_score = _thresh(
                rr_val,
                [(0.5, -4), (1.0, -1), (1.5, 1), (2.0, 3), (3.0, 4), (9999, 5)],
            )
        sub.append({
            "name": "Risk-Reward Score", "name_cn": "风险回报评分",
            "value": _fmt(rr_val, 2), "score": rr_score, "unit": "x",
            "source": "yfinance info.targetMeanPrice + history",
        })

        composite = _clamp(_safe_mean([s["score"] for s in sub]))
        return {
            "composite": round(composite, 2),
            "label": "Risk-Adjusted", "label_cn": "风险调整回报", "factors": sub,
            "data_source_summary": "yfinance price history + ^TNX + SPY benchmark",
        }

    except Exception as exc:
        logger.warning("Risk-adjusted factor failed: %s", exc)
        return {
            "composite": 0.0, "label": "Risk-Adjusted",
            "label_cn": "风险调整回报", "factors": [],
            "data_source_summary": "yfinance price history + ^TNX + SPY benchmark",
        }


# ---------------------------------------------------------------------------
# 11. Historical Regime Analogy Factor
# ---------------------------------------------------------------------------

# Reference periods: (name, name_cn, vix, pe, yield_curve, dd_pct, fwd_12m_return)
_HISTORICAL_REGIMES = [
    ("Dot-com Bottom (2002-10)", "互联网泡沫底部",
     35.0, 18.0, 2.5, -49.0, 28.0),
    ("Pre-GFC Peak (2007-10)", "金融危机前高点",
     16.0, 17.0, -0.1, 0.0, -38.0),
    ("GFC Bottom (2009-03)", "金融危机底部",
     46.0, 12.0, 2.5, -57.0, 65.0),
    ("EU Crisis (2011-10)", "欧债危机",
     30.0, 13.0, 1.8, -19.0, 20.0),
    ("Pre-COVID Peak (2020-02)", "新冠前高点",
     14.0, 22.0, 0.1, 0.0, 17.0),
    ("COVID Bottom (2020-03)", "新冠底部",
     66.0, 18.0, 0.5, -34.0, 75.0),
    ("2022 Bear (2022-10)", "2022年熊市",
     31.0, 17.0, -0.5, -25.0, 22.0),
    ("AI Bull (2024-07)", "AI牛市",
     12.0, 23.0, -0.3, 0.0, 10.0),
]

# Normalization ranges for each dimension (for Euclidean distance)
_FINGERPRINT_RANGES = {
    "vix": (10.0, 70.0),
    "pe": (10.0, 30.0),
    "yield_curve": (-1.0, 3.0),
    "drawdown": (-60.0, 0.0),
    "momentum_12m": (-50.0, 50.0),
}


def _compute_historical_analogy(hist, info):
    """Compare current macro fingerprint to historical regimes."""
    try:
        sub = []

        # Build current fingerprint
        vix_now = _safe_yf_close("^VIX")
        if vix_now is None:
            vix_now = 20.0

        # SPY P/E from info or fallback
        pe_now = info.get("trailingPE") or info.get("forwardPE")
        if pe_now is None or (isinstance(pe_now, float) and np.isnan(pe_now)):
            # Try SPY P/E as market proxy
            try:
                spy_info = yf.Ticker("SPY").info
                pe_now = spy_info.get("trailingPE", 20.0)
            except Exception:
                pe_now = 20.0

        # Yield curve from economic cache or live fetch
        yc_spread = None
        eco_cached = _CACHE.get("economic_factor")
        if eco_cached:
            for f in eco_cached["data"].get("factors", []):
                if f.get("name") == "Yield Curve Spread":
                    yc_spread = f.get("value")
                    break
        if yc_spread is None:
            tnx = _safe_yf_close("^TNX")
            fvx = _safe_yf_close("^FVX")
            if tnx is not None and fvx is not None:
                yc_spread = tnx - fvx
            else:
                yc_spread = 0.0

        # S&P 500 drawdown from high
        sp_data = _fetch_regime_series("^GSPC")
        dd_now = sp_data.get("drawdown_pct", 0.0) or 0.0

        # 12-month momentum of the stock
        closes = hist["Close"].values.astype(float)
        n = len(closes)
        mom_12m = 0.0
        if n >= 252:
            mom_12m = (closes[-1] / closes[-252] - 1) * 100

        current_fp = [vix_now, pe_now, yc_spread, dd_now, mom_12m]

        # Normalize current fingerprint
        dims = ["vix", "pe", "yield_curve", "drawdown", "momentum_12m"]
        ranges = [_FINGERPRINT_RANGES[d] for d in dims]

        def normalize(val, rng):
            lo, hi = rng
            span = hi - lo
            if span == 0:
                return 0.0
            return (val - lo) / span

        current_norm = [normalize(v, r) for v, r in zip(current_fp, ranges)]

        # Compute distance to each historical regime
        distances = []
        for name, name_cn, h_vix, h_pe, h_yc, h_dd, h_fwd in _HISTORICAL_REGIMES:
            hist_norm = [
                normalize(h_vix, _FINGERPRINT_RANGES["vix"]),
                normalize(h_pe, _FINGERPRINT_RANGES["pe"]),
                normalize(h_yc, _FINGERPRINT_RANGES["yield_curve"]),
                normalize(h_dd, _FINGERPRINT_RANGES["drawdown"]),
                normalize(mom_12m, _FINGERPRINT_RANGES["momentum_12m"]),
            ]
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(current_norm, hist_norm)))
            distances.append((dist, name, name_cn, h_fwd))

        distances.sort(key=lambda x: x[0])

        # Top-3 closest analogues, weighted by inverse distance
        top_3 = distances[:3]
        inv_weights = []
        for dist, _, _, _ in top_3:
            inv_weights.append(1.0 / (dist + 0.01))  # avoid div by zero
        weight_sum = sum(inv_weights)
        norm_weights = [w / weight_sum for w in inv_weights]

        predicted_return = sum(w * fwd for w, (_, _, _, fwd) in zip(norm_weights, top_3))

        # Closest analogue similarity percentage
        max_possible_dist = math.sqrt(len(dims))  # max Euclidean distance in unit cube
        closest_similarity = max(0.0, (1.0 - top_3[0][0] / max_possible_dist) * 100)

        sub.append({
            "name": "Closest Historical Analogue",
            "name_cn": "最近历史类比",
            "value": f"{top_3[0][1]} ({closest_similarity:.0f}%)",
            "score": _thresh(
                predicted_return,
                [(-15, -5), (-5, -3), (0, -1), (5, 1), (15, 3), (9999, 5)],
            ),
            "unit": "",
            "source": "^VIX, info.trailingPE, ^TNX/^FVX, ^GSPC, stock history",
        })

        sub.append({
            "name": "Predicted Forward Return",
            "name_cn": "预测远期回报",
            "value": _fmt(predicted_return, 1),
            "score": _thresh(
                predicted_return,
                [(-15, -5), (-5, -3), (0, -1), (5, 1), (15, 3), (9999, 5)],
            ),
            "unit": "%",
            "source": "weighted historical regime forward returns",
        })

        # VIX percentile in historical distribution
        hist_vix_vals = [r[2] for r in _HISTORICAL_REGIMES]
        vix_below = sum(1 for v in hist_vix_vals if v <= vix_now)
        vix_pctile = (vix_below / len(hist_vix_vals)) * 100
        vix_pctile_score = _thresh(
            vix_pctile,
            [(20, 3), (40, 1), (60, 0), (80, -2), (9999, -4)],
        )
        sub.append({
            "name": "VIX Percentile vs History",
            "name_cn": "VIX历史百分位",
            "value": _fmt(vix_pctile, 0),
            "score": vix_pctile_score,
            "unit": "%ile",
            "source": "yfinance ^VIX vs 8 reference periods",
        })

        # Valuation percentile
        hist_pe_vals = [r[3] for r in _HISTORICAL_REGIMES]
        pe_below = sum(1 for v in hist_pe_vals if v <= pe_now)
        pe_pctile = (pe_below / len(hist_pe_vals)) * 100
        pe_pctile_score = _thresh(
            pe_pctile,
            [(20, 4), (40, 2), (60, 0), (80, -2), (9999, -4)],
        )
        sub.append({
            "name": "Valuation Percentile vs History",
            "name_cn": "估值历史百分位",
            "value": _fmt(pe_pctile, 0),
            "score": pe_pctile_score,
            "unit": "%ile",
            "source": "yfinance info.trailingPE vs 8 reference periods",
        })

        composite = _clamp(_safe_mean([s["score"] for s in sub]))
        return {
            "composite": round(composite, 2),
            "label": "Historical Analogy", "label_cn": "历史周期类比",
            "factors": sub,
            "data_source_summary": "yfinance ^VIX, ^GSPC, ^TNX + 8 historical reference periods",
        }

    except Exception as exc:
        logger.warning("Historical analogy factor failed: %s", exc)
        return {
            "composite": 0.0, "label": "Historical Analogy",
            "label_cn": "历史周期类比", "factors": [],
            "data_source_summary": "yfinance ^VIX, ^GSPC, ^TNX + 8 historical reference periods",
        }


# ---------------------------------------------------------------------------
# 12. ML Adaptive Meta-Factor
# ---------------------------------------------------------------------------

def _compute_ml_adaptive(groups, ticker, hist):
    """Ridge regression meta-factor using rolling features and factor alignment."""
    try:
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import TimeSeriesSplit

        closes = hist["Close"].values.astype(float)
        volumes = hist["Volume"].values.astype(float)
        n = len(closes)

        if n < 120:
            return {
                "composite": 0.0, "label": "ML Adaptive",
                "label_cn": "机器学习自适应", "factors": [],
                "data_source_summary": "sklearn Ridge regression on yfinance 2Y features",
            }

        sub = []

        # Build rolling features at each historical point
        features = []
        targets = []
        target_horizon = 20  # 20-day forward return

        for i in range(60, n - target_horizon):
            window = closes[:i + 1]
            vol_window = volumes[:i + 1]

            # Feature 1: 20-day momentum
            mom_20 = (window[-1] / window[-20] - 1) * 100 if len(window) >= 20 else 0.0

            # Feature 2: 60-day momentum
            mom_60 = (window[-1] / window[-60] - 1) * 100 if len(window) >= 60 else 0.0

            # Feature 3: RSI
            rsi = _calc_rsi(np.array(window[-30:]), 14)
            if rsi is None:
                rsi = 50.0

            # Feature 4: Realized volatility (20-day)
            if len(window) >= 21:
                rets_20 = np.diff(np.log(window[-21:]))
                vol_20 = float(np.std(rets_20) * np.sqrt(252) * 100)
            else:
                vol_20 = 20.0

            # Feature 5: Volume ratio (5-day vs 20-day average)
            if len(vol_window) >= 20:
                vol_5 = float(np.mean(vol_window[-5:]))
                vol_20_avg = float(np.mean(vol_window[-20:]))
                vol_ratio = vol_5 / vol_20_avg if vol_20_avg > 0 else 1.0
            else:
                vol_ratio = 1.0

            features.append([mom_20, mom_60, rsi, vol_20, vol_ratio])

            # Target: 20-day forward return
            fwd_ret = (closes[i + target_horizon] / closes[i] - 1) * 100
            targets.append(fwd_ret)

        if len(features) < 40:
            return {
                "composite": 0.0, "label": "ML Adaptive",
                "label_cn": "机器学习自适应", "factors": [],
                "data_source_summary": "sklearn Ridge regression on yfinance 2Y features",
            }

        x_arr = np.array(features)
        y_arr = np.array(targets)

        # Train/validation split using time series split
        split_idx = int(len(x_arr) * 0.8)
        x_train, x_val = x_arr[:split_idx], x_arr[split_idx:]
        y_train, y_val = y_arr[:split_idx], y_arr[split_idx:]

        # Standardize features
        x_mean = x_train.mean(axis=0)
        x_std = x_train.std(axis=0)
        x_std[x_std == 0] = 1.0
        x_train_norm = (x_train - x_mean) / x_std
        x_val_norm = (x_val - x_mean) / x_std

        model = Ridge(alpha=1.0)
        model.fit(x_train_norm, y_train)

        # Validation R-squared
        r2 = model.score(x_val_norm, y_val)
        r2 = max(0.0, min(1.0, r2))  # clamp to [0, 1]

        # Current prediction
        current_window = closes
        current_vol_window = volumes
        mom_20_now = (current_window[-1] / current_window[-20] - 1) * 100
        mom_60_now = (current_window[-1] / current_window[-60] - 1) * 100
        rsi_now = _calc_rsi(np.array(current_window[-30:]), 14) or 50.0
        rets_20_now = np.diff(np.log(current_window[-21:]))
        vol_20_now = float(np.std(rets_20_now) * np.sqrt(252) * 100)
        vol_5_now = float(np.mean(current_vol_window[-5:]))
        vol_20_avg_now = float(np.mean(current_vol_window[-20:]))
        vol_ratio_now = vol_5_now / vol_20_avg_now if vol_20_avg_now > 0 else 1.0

        current_features = np.array([[mom_20_now, mom_60_now, rsi_now, vol_20_now, vol_ratio_now]])
        current_norm = (current_features - x_mean) / x_std
        predicted_return = float(model.predict(current_norm)[0])

        # Confidence-weighted prediction score
        confidence_weight = 0.3 + 0.7 * r2  # minimum 30% weight even with low R2
        pred_score = _thresh(
            predicted_return,
            [(-10, -5), (-5, -3), (-2, -1), (2, 1), (5, 3), (9999, 5)],
        )
        weighted_pred_score = pred_score * confidence_weight

        sub.append({
            "name": "ML Predicted Return",
            "name_cn": "ML预测回报",
            "value": _fmt(predicted_return, 2),
            "score": weighted_pred_score,
            "unit": "%",
            "source": "sklearn Ridge on yfinance 2Y price/volume features",
        })

        # Model confidence
        confidence_score = _thresh(
            r2 * 100,
            [(5, -3), (10, -1), (20, 1), (30, 3), (9999, 5)],
        )
        sub.append({
            "name": "Model Confidence",
            "name_cn": "模型置信度",
            "value": _fmt(r2 * 100, 1),
            "score": confidence_score,
            "unit": "%",
            "source": "sklearn Ridge R² on time-series validation split",
        })

        # Factor alignment: how many of the other factors agree in direction
        # Exclude ml_adaptive itself (it's not in groups yet when called)
        factor_directions = []
        for k, g in groups.items():
            comp = g.get("composite", 0)
            if comp > 0.5:
                factor_directions.append(1)
            elif comp < -0.5:
                factor_directions.append(-1)
            else:
                factor_directions.append(0)

        if factor_directions:
            bullish_count = sum(1 for d in factor_directions if d == 1)
            bearish_count = sum(1 for d in factor_directions if d == -1)
            total_factors = len(factor_directions)
            dominant = max(bullish_count, bearish_count)
            alignment_pct = (dominant / total_factors) * 100

            if bullish_count > bearish_count:
                alignment_score = _thresh(
                    alignment_pct,
                    [(30, -1), (50, 1), (70, 3), (9999, 5)],
                )
            elif bearish_count > bullish_count:
                alignment_score = _thresh(
                    alignment_pct,
                    [(30, 1), (50, -1), (70, -3), (9999, -5)],
                )
            else:
                alignment_score = 0.0

            sub.append({
                "name": "Factor Alignment",
                "name_cn": "因子一致性",
                "value": f"{dominant}/{total_factors} ({alignment_pct:.0f}%)",
                "score": alignment_score,
                "unit": "",
                "source": "computed from factors 1-11 composite scores",
            })

        # Signal consistency: current vs 5-day average signal direction
        # Compare current 20-day momentum direction vs 5-day rolling average
        if n >= 25:
            signals_5d = []
            for offset in range(5):
                idx = -(offset + 1)
                if abs(idx) + 20 <= n:
                    m20 = (closes[idx] / closes[idx - 20] - 1) * 100
                    signals_5d.append(1 if m20 > 0 else -1)
            current_signal = 1 if mom_20_now > 0 else -1
            if signals_5d:
                avg_signal = np.mean(signals_5d)
                consistent = (current_signal > 0 and avg_signal > 0) or \
                             (current_signal < 0 and avg_signal < 0)
                consistency_score = 3.0 if consistent else -2.0
            else:
                consistency_score = 0.0
        else:
            consistency_score = 0.0

        sub.append({
            "name": "Signal Consistency",
            "name_cn": "信号一致性",
            "value": "Consistent" if consistency_score > 0 else "Divergent",
            "score": consistency_score,
            "unit": "",
            "source": "yfinance history, 5-day rolling 20D momentum",
        })

        composite = _clamp(_safe_mean([s["score"] for s in sub]))
        return {
            "composite": round(composite, 2),
            "label": "ML Adaptive", "label_cn": "机器学习自适应", "factors": sub,
            "data_source_summary": "sklearn Ridge regression on yfinance 2Y features",
        }

    except Exception as exc:
        logger.warning("ML adaptive factor failed: %s", exc)
        return {
            "composite": 0.0, "label": "ML Adaptive",
            "label_cn": "机器学习自适应", "factors": [],
            "data_source_summary": "sklearn Ridge regression on yfinance 2Y features",
        }


# ---------------------------------------------------------------------------
# Risk-to-Return Ratio
# ---------------------------------------------------------------------------

def _compute_risk_reward(info, hist):
    """Calculate expected risk-to-return with position sizing guidance."""
    closes = hist["Close"].values.astype(float)
    n = len(closes)
    current = float(closes[-1])

    # Upside: distance to analyst target
    target = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    upside_pct = None
    if target and target > 0:
        upside_pct = ((target / current) - 1) * 100

    # Downside: based on recent volatility and drawdown
    downside_pct = None
    if n >= 60:
        # 30-day realized vol annualized, then scale to ~3-month risk
        rets_30d = np.diff(np.log(closes[-31:]))
        monthly_vol = float(np.std(rets_30d) * np.sqrt(21) * 100)
        # Expected 3-month downside: ~1.5x monthly vol
        downside_pct = monthly_vol * 1.5

        # Floor at recent max drawdown (3 months)
        window_3m = closes[-min(63, n):]
        rolling_max = np.maximum.accumulate(window_3m)
        dd = (window_3m / rolling_max - 1) * 100
        recent_max_dd = abs(float(dd.min()))
        downside_pct = max(downside_pct, recent_max_dd)

        # Cap at 30% — beyond that the model is unreliable
        downside_pct = min(downside_pct, 30.0)

    # Risk-to-return ratio
    rr_ratio = None
    if upside_pct is not None and downside_pct is not None and downside_pct > 0:
        rr_ratio = round(upside_pct / downside_pct, 2)

    # Kelly criterion position sizing: f = (p * b - q) / b
    # p = win probability estimate, b = win/loss ratio, q = 1 - p
    kelly_fraction = None
    if rr_ratio is not None:
        # Estimate win probability from analyst consensus
        rec_mean = info.get("recommendationMean")
        if rec_mean:
            # Scale 1-5 recommendation to win probability 0.3-0.7
            win_prob = _clamp(1.0 - (rec_mean - 1) / 4, 0.3, 0.7)
        else:
            win_prob = 0.5

        b = rr_ratio if rr_ratio > 0 else 0.01
        q = 1 - win_prob
        kelly_raw = (win_prob * b - q) / b
        # Half-Kelly for safety
        kelly_fraction = round(max(0, kelly_raw * 0.5) * 100, 1)

    return {
        "current_price": round(current, 2),
        "analyst_target": _fmt(target, 2),
        "analyst_target_high": _fmt(target_high, 2),
        "upside_pct": _fmt(upside_pct, 1),
        "downside_pct": _fmt(downside_pct, 1),
        "risk_reward_ratio": rr_ratio,
        "kelly_position_pct": kelly_fraction,
        "position_sizing": _position_size_label(kelly_fraction),
    }


def _position_size_label(kelly_pct):
    """Translate Kelly fraction into human-readable position sizing."""
    if kelly_pct is None:
        return "Insufficient data"
    if kelly_pct <= 0:
        return "No position recommended"
    if kelly_pct < 3:
        return "Small position (1-2% of portfolio)"
    if kelly_pct < 8:
        return "Moderate position (3-5% of portfolio)"
    if kelly_pct < 15:
        return "Standard position (5-8% of portfolio)"
    return "Conviction position (8-12% of portfolio)"
