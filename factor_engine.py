"""
Venture Fund-Grade Multi-Factor Analysis Engine v2.

Computes 9 factor category exposures (each -5 to +5 scale):
  1. Momentum   - Price trend 1m/3m/6m/12m + RSI + MACD
  2. Value      - P/E, P/B, EV/EBITDA, P/S, Dividend Yield (sector-adjusted)
  3. Quality    - ROE, ROA, Gross Margin, Op Margin, Debt/Equity, Current Ratio
  4. Growth     - Revenue growth, EPS growth, Forward EPS, Analyst Rating
  5. Volatility - Beta, 30D Realized Vol, Max Drawdown, ATR (inverted scoring)
  6. Sentiment  - Short Interest, Institutional Hold, Insider Activity, Consensus
  7. Macro      - S&P Correlation, Relative Strength, 52-Week Position
  8. Economic   - CPI, GDP, Consumer Sentiment, Yield Curve, PMI, Housing
  9. Industry   - Sector ETF momentum, relative strength vs market, rotation

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
        "momentum": 0.08, "value": 0.25, "quality": 0.25, "growth": 0.08,
        "volatility": 0.10, "sentiment": 0.06, "macro": 0.08,
        "economic": 0.05, "industry": 0.05,
    },
    "BEAR": {
        "momentum": 0.12, "value": 0.22, "quality": 0.22, "growth": 0.10,
        "volatility": 0.10, "sentiment": 0.08, "macro": 0.08,
        "economic": 0.04, "industry": 0.04,
    },
    "RECOVERY": {
        "momentum": 0.20, "value": 0.18, "quality": 0.18, "growth": 0.18,
        "volatility": 0.08, "sentiment": 0.08, "macro": 0.05,
        "economic": 0.03, "industry": 0.02,
    },
    "BULL": {
        "momentum": 0.25, "value": 0.10, "quality": 0.15, "growth": 0.25,
        "volatility": 0.05, "sentiment": 0.10, "macro": 0.05,
        "economic": 0.03, "industry": 0.02,
    },
    "EUPHORIA": {
        "momentum": 0.15, "value": 0.08, "quality": 0.12, "growth": 0.30,
        "volatility": 0.05, "sentiment": 0.12, "macro": 0.08,
        "economic": 0.05, "industry": 0.05,
    },
}

SHORT_TERM_WEIGHTS = {
    "momentum": 0.30, "value": 0.05, "quality": 0.05, "growth": 0.10,
    "volatility": 0.10, "sentiment": 0.20, "macro": 0.10,
    "economic": 0.05, "industry": 0.05,
}

LONG_TERM_WEIGHTS = {
    "momentum": 0.05, "value": 0.25, "quality": 0.25, "growth": 0.20,
    "volatility": 0.05, "sentiment": 0.02, "macro": 0.03,
    "economic": 0.05, "industry": 0.10,
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
        macro = _compute_macro(hist)
        economic = _compute_economic()
        industry = _compute_industry_outlook(sector)

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
        }

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
    })
    sub.append({
        "name": "3M Momentum", "name_cn": "3月动量",
        "value": _fmt(ret(63), 1),
        "score": score_ret(ret(63), [(-15, -4), (-5, -2), (0, 0), (8, 2), (20, 4), (9999, 5)]),
        "unit": "%",
    })
    sub.append({
        "name": "6M Momentum", "name_cn": "6月动量",
        "value": _fmt(ret(126), 1),
        "score": score_ret(ret(126), [(-20, -4), (-8, -2), (0, 0), (12, 2), (30, 4), (9999, 5)]),
        "unit": "%",
    })
    sub.append({
        "name": "12M Momentum", "name_cn": "12月动量",
        "value": _fmt(ret(252), 1),
        "score": score_ret(ret(252), [(-25, -4), (-10, -2), (0, 0), (15, 2), (40, 4), (9999, 5)]),
        "unit": "%",
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
    })

    macd_score = 0.0
    if n >= 35:
        try:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            macd_vals = ema12 - ema26
            signal_vals = _ema(macd_vals, 9)
            macd_now = float(macd_vals[-1])
            sig_now = float(signal_vals[-1])
            if macd_now > sig_now:
                macd_score = 3.0 if macd_now > 0 else 1.0
            else:
                macd_score = -3.0 if macd_now < 0 else -1.0
        except Exception:
            pass
    sub.append({
        "name": "MACD Signal", "name_cn": "MACD信号",
        "value": None, "score": macd_score, "unit": "",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Momentum", "label_cn": "动量", "factors": sub,
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
    })

    pb_lo, pb_hi = profile["pb_range"]
    pb = info.get("priceToBook")
    pb_score = _score_valuation_ratio(pb, pb_lo, pb_hi)
    sub.append({
        "name": "P/B Ratio", "name_cn": "市净率",
        "value": _fmt(pb, 2), "score": pb_score, "unit": "x",
    })

    ev_lo, ev_hi = profile["ev_ebitda_range"]
    ev_ebitda = info.get("enterpriseToEbitda")
    ev_score = _score_valuation_ratio(ev_ebitda, ev_lo, ev_hi)
    sub.append({
        "name": "EV/EBITDA", "name_cn": "企业价值倍数",
        "value": _fmt(ev_ebitda, 1), "score": ev_score, "unit": "x",
    })

    ps = info.get("priceToSalesTrailing12Months")
    sub.append({
        "name": "P/S Ratio", "name_cn": "市销率",
        "value": _fmt(ps, 2),
        "score": _thresh(ps, [(1, 5), (3, 3), (6, 1), (10, -1), (20, -3), (9999, -5)]),
        "unit": "x",
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
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Value", "label_cn": "估值", "factors": sub,
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
    })

    roa = info.get("returnOnAssets")
    roa_pct = (roa * 100) if roa else None
    sub.append({
        "name": "ROA", "name_cn": "总资产收益率",
        "value": _fmt(roa_pct, 1),
        "score": _thresh(roa_pct, [(-2, -5), (0, -3), (3, -1), (7, 2), (12, 4), (9999, 5)]),
        "unit": "%",
    })

    gm = info.get("grossMargins")
    gm_pct = (gm * 100) if gm else None
    sub.append({
        "name": "Gross Margin", "name_cn": "毛利率",
        "value": _fmt(gm_pct, 1),
        "score": _thresh(gm_pct, [(10, -3), (20, -1), (35, 1), (50, 3), (65, 4), (9999, 5)]),
        "unit": "%",
    })

    om = info.get("operatingMargins")
    om_pct = (om * 100) if om else None
    sub.append({
        "name": "Operating Margin", "name_cn": "营业利润率",
        "value": _fmt(om_pct, 1),
        "score": _thresh(om_pct, [(-5, -5), (0, -3), (5, -1), (12, 1), (20, 3), (9999, 5)]),
        "unit": "%",
    })

    de = info.get("debtToEquity")
    sub.append({
        "name": "Debt/Equity", "name_cn": "负债权益比",
        "value": _fmt(de, 1),
        "score": _thresh(de, [(20, 5), (50, 3), (100, 1), (150, -1), (200, -3), (9999, -5)]),
        "unit": "%",
    })

    cr = info.get("currentRatio")
    sub.append({
        "name": "Current Ratio", "name_cn": "流动比率",
        "value": _fmt(cr, 2),
        "score": _thresh(cr, [(0.5, -5), (1.0, -2), (1.5, 1), (2.5, 4), (9999, 5)]),
        "unit": "x",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Quality", "label_cn": "质量", "factors": sub,
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
    })

    eg = info.get("earningsGrowth")
    eg_pct = (eg * 100) if eg else None
    sub.append({
        "name": "EPS Growth", "name_cn": "每股收益增长",
        "value": _fmt(eg_pct, 1),
        "score": _thresh(eg_pct, [(-20, -5), (-5, -3), (0, -1), (8, 1), (20, 3), (9999, 5)]),
        "unit": "%",
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
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Growth", "label_cn": "成长", "factors": sub,
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
    })

    if n >= 30:
        rets = np.diff(np.log(closes[-31:]))
        rv = float(np.std(rets) * np.sqrt(252) * 100)
        sub.append({
            "name": "30D Realized Vol", "name_cn": "30日波动率",
            "value": _fmt(rv, 1),
            "score": _thresh(rv, [(15, 5), (25, 3), (35, 1), (50, -1), (70, -3), (9999, -5)]),
            "unit": "%",
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
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {
        "composite": round(composite, 2),
        "label": "Volatility", "label_cn": "波动性", "factors": sub,
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
        })

    inst = info.get("heldPercentInstitutions")
    if inst:
        ip = inst * 100
        sub.append({
            "name": "Institutional Hold.", "name_cn": "机构持仓",
            "value": _fmt(ip, 1),
            "score": _thresh(ip, [(20, -3), (40, 0), (60, 2), (80, 4), (9999, 4)]),
            "unit": "%",
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
    })

    rc = info.get("recommendationMean")
    if rc:
        rc_score = _thresh(rc, [(1.5, 5), (2.0, 3), (2.5, 1), (3.0, -1), (9999, -3)])
        sub.append({
            "name": "Analyst Consensus", "name_cn": "分析师共识",
            "value": _fmt(rc, 2), "score": rc_score, "unit": "/5",
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {
        "composite": round(composite, 2),
        "label": "Sentiment", "label_cn": "情绪", "factors": sub,
    }


# ---------------------------------------------------------------------------
# 7. Macro Factors
# ---------------------------------------------------------------------------

def _compute_macro(hist):
    sub = []
    closes = hist["Close"].values.astype(float)
    n = len(closes)

    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")["Close"].values.astype(float)
        min_len = min(n, len(spy_hist))
        if min_len > 60:
            r1 = np.diff(np.log(closes[-min_len:]))
            r2 = np.diff(np.log(spy_hist[-min_len:]))
            corr = float(np.corrcoef(r1, r2)[0, 1])
            sub.append({
                "name": "Market Correlation", "name_cn": "市场相关性",
                "value": _fmt(corr, 2), "score": _clamp(-corr * 3.0), "unit": "",
            })
            if min_len >= 252:
                stock_ret = (closes[-1] / closes[-252] - 1) * 100
                spy_ret = (spy_hist[-1] / spy_hist[-252] - 1) * 100
                rs = stock_ret - spy_ret
                sub.append({
                    "name": "Relative Strength (1Y)", "name_cn": "相对强度",
                    "value": _fmt(rs, 1),
                    "score": _thresh(rs, [(-20, -5), (-10, -3), (-3, -1), (3, 1), (10, 3), (9999, 5)]),
                    "unit": "%",
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
            })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {
        "composite": round(composite, 2),
        "label": "Macro", "label_cn": "宏观", "factors": sub,
    }


# ---------------------------------------------------------------------------
# 8. Economic Cycle Factor
# ---------------------------------------------------------------------------

def _compute_economic():
    """Score economic conditions for equity favorability using FRED macro data."""
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("economic_factor")
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    sub = []

    try:
        macro = get_macro_indicators()
        ind = macro.get("indicators", {})
    except Exception:
        ind = {}

    # Fallback: if FRED data is all nulls, fetch key indicators from yfinance
    all_null = all(v is None for v in ind.values()) if ind else True
    if all_null:
        try:
            # Treasury yields from yfinance
            tnx = yf.Ticker("^TNX").history(period="5d")
            if not tnx.empty:
                ind["treasury_10y"] = round(float(tnx["Close"].iloc[-1]), 2)
            irx = yf.Ticker("^IRX").history(period="5d")
            if not irx.empty:
                ind["treasury_3mo"] = round(float(irx["Close"].iloc[-1]), 2)
            fvx = yf.Ticker("^FVX").history(period="5d")
            if not fvx.empty:
                ind["treasury_2y"] = round(float(fvx["Close"].iloc[-1]), 2)
            # Yield curve from available data
            if ind.get("treasury_10y") and ind.get("treasury_2y"):
                spread = ind["treasury_10y"] - ind["treasury_2y"]
                ind["yield_curve_spread"] = round(spread, 2)
                ind["yield_curve_inverted"] = spread < 0
            # Consumer sentiment proxy from consumer discretionary vs staples
            xly = yf.Ticker("XLY").history(period="1mo")
            xlp = yf.Ticker("XLP").history(period="1mo")
            if not xly.empty and not xlp.empty:
                xly_ret = (float(xly["Close"].iloc[-1]) / float(xly["Close"].iloc[0]) - 1)
                xlp_ret = (float(xlp["Close"].iloc[-1]) / float(xlp["Close"].iloc[0]) - 1)
                # Discretionary outperforming staples = consumer confidence
                consumer_proxy = (xly_ret - xlp_ret) * 100
                ind["_consumer_proxy"] = round(consumer_proxy, 2)
            # Fed funds proxy from 3-month treasury
            if ind.get("treasury_3mo"):
                ind["fed_funds_rate"] = ind["treasury_3mo"]
                if ind.get("treasury_10y"):
                    # Rough CPI proxy: 10Y yield - real rate assumption (~1.5%)
                    ind["_implied_cpi"] = round(ind["treasury_10y"] - 1.5, 1)
        except Exception as exc:
            logger.warning("Economic yfinance fallback failed: %s", exc)

    # CPI trend: rising inflation negative for growth, positive for value
    cpi = ind.get("cpi_yoy") or ind.get("_implied_cpi")
    if cpi is not None:
        cpi_score = _thresh(
            cpi, [(2, 3), (3, 1), (4, -1), (5, -3), (9999, -5)],
        )
        sub.append({
            "name": "CPI Inflation", "name_cn": "消费者物价指数",
            "value": _fmt(cpi, 1), "score": cpi_score, "unit": "%",
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
        })

    # Consumer sentiment (FRED or proxy from XLY/XLP relative performance)
    cs = ind.get("consumer_sentiment")
    if cs is not None:
        cs_score = _thresh(
            cs, [(50, -5), (60, -3), (70, -1), (80, 1), (90, 3), (9999, 5)],
        )
        sub.append({
            "name": "Consumer Sentiment", "name_cn": "消费者信心指数",
            "value": _fmt(cs, 1), "score": cs_score, "unit": "",
        })
    elif ind.get("_consumer_proxy") is not None:
        cp = ind["_consumer_proxy"]
        cp_score = _thresh(
            cp, [(-5, -4), (-2, -2), (0, 0), (2, 2), (5, 4), (9999, 5)],
        )
        sub.append({
            "name": "Consumer Confidence Proxy", "name_cn": "消费信心代理指标",
            "value": _fmt(cp, 1), "score": cp_score, "unit": "%",
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
        })

    # ISM Manufacturing proxy
    ism = ind.get("ism_manufacturing")
    if ism is not None:
        ism_score = _thresh(
            ism, [(45, -5), (48, -3), (50, -1), (52, 1), (55, 3), (9999, 5)],
        )
        sub.append({
            "name": "ISM Manufacturing", "name_cn": "ISM制造业指数",
            "value": _fmt(ism, 1), "score": ism_score, "unit": "",
        })

    # Retail sales
    retail = ind.get("retail_sales")
    if retail is not None:
        # Retail sales reported as level; we score relative to trend
        # A positive value typically means consumer spending OK
        retail_score = 1.0  # Neutral baseline since we only have level
        sub.append({
            "name": "Retail Sales", "name_cn": "零售销售额",
            "value": _fmt(retail, 1), "score": retail_score, "unit": "B$",
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
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    result = {
        "composite": round(composite, 2),
        "label": "Economic", "label_cn": "经济周期", "factors": sub,
    }
    _CACHE["economic_factor"] = {"data": result, "ts": now}
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
                })

            # 1-month return
            if n_etf >= 21:
                month_ret = (etf_closes[-1] / etf_closes[-21] - 1) * 100
                sub.append({
                    "name": "Sector 1M Return", "name_cn": "行业1月回报",
                    "value": _fmt(month_ret, 2),
                    "score": _thresh(month_ret, [(-8, -4), (-3, -2), (0, 0), (3, 2), (8, 4), (9999, 5)]),
                    "unit": "%",
                })

            # 3-month return
            if n_etf >= 63:
                q_ret = (etf_closes[-1] / etf_closes[-63] - 1) * 100
                sub.append({
                    "name": "Sector 3M Return", "name_cn": "行业3月回报",
                    "value": _fmt(q_ret, 2),
                    "score": _thresh(q_ret, [(-12, -4), (-5, -2), (0, 0), (5, 2), (12, 4), (9999, 5)]),
                    "unit": "%",
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
                    })

    except Exception as exc:
        logger.warning("Industry outlook failed for %s (%s): %s", sector, etf_symbol, exc)

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    result = {
        "composite": round(composite, 2),
        "label": "Industry", "label_cn": "行业前景",
        "sector_etf": etf_symbol,
        "factors": sub,
    }
    _CACHE[cache_key] = {"data": result, "ts": now}
    return result


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
