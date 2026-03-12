"""
Venture Fund-Grade Multi-Factor Analysis Engine.

Computes 7 factor category exposures (each -5 to +5 scale):
  1. Momentum   – Price trend 1m/3m/6m/12m + RSI + MACD
  2. Value      – P/E, P/B, EV/EBITDA, P/S, Dividend Yield
  3. Quality    – ROE, ROA, Gross Margin, Op Margin, Debt/Equity, Current Ratio
  4. Growth     – Revenue growth, EPS growth, Forward EPS, Analyst Rating
  5. Volatility – Beta, 30D Realized Vol, Max Drawdown, ATR (inverted scoring)
  6. Sentiment  – Short Interest, Institutional Hold, Insider Activity, Analyst Consensus
  7. Macro      – S&P Correlation, Relative Strength, 52-Week Position

Composite = venture-fund weighted average of all group scores.
"""
import logging
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

logger = logging.getLogger("factors")

_CACHE: dict = {}
_CACHE_TTL = 1800  # 30-minute TTL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_factor_analysis(ticker: str) -> dict:
    """Compute full multi-factor analysis. Returns dict with composite score and all factor groups."""
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(ticker)
    if cached and (now - cached["ts"]).seconds < _CACHE_TTL:
        return cached["data"]

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        hist = stock.history(period="2y")

        if hist.empty:
            return _make_error(ticker, "No price history available")

        momentum = _compute_momentum(hist, info)
        value = _compute_value(info)
        quality = _compute_quality(info)
        growth = _compute_growth(info)
        volatility = _compute_volatility(hist, info)
        sentiment = _compute_sentiment(stock, info)
        macro = _compute_macro(hist)

        groups = {
            "momentum": momentum,
            "value": value,
            "quality": quality,
            "growth": growth,
            "volatility": volatility,
            "sentiment": sentiment,
            "macro": macro,
        }

        weights = {
            "momentum": 0.22,
            "value": 0.13,
            "quality": 0.20,
            "growth": 0.22,
            "volatility": 0.08,
            "sentiment": 0.09,
            "macro": 0.06,
        }

        composite = _clamp(
            sum(groups[k]["composite"] * weights[k] for k in weights), -5, 5
        )

        data = {
            "ticker": ticker,
            "composite": round(composite, 3),
            "signal": _rating(composite),
            "weights": weights,
            "group_scores": {k: round(groups[k]["composite"], 2) for k in groups},
            "groups": groups,
            "generated_at": now.isoformat(),
        }
        _CACHE[ticker] = {"data": data, "ts": now}
        return data

    except Exception as exc:
        logger.exception("Factor analysis error for %s", ticker)
        return _make_error(ticker, str(exc))


# ---------------------------------------------------------------------------
# Helpers
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
    """Map value to score using [(threshold, score), ...] breakpoints (ascending thresholds)."""
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
        "name": "1M Momentum",
        "name_cn": "1月动量",
        "value": _fmt(ret(21), 1),
        "score": score_ret(ret(21), [(-8, -4), (-3, -2), (0, 0), (5, 2), (10, 4), (9999, 5)]),
        "unit": "%",
    })
    sub.append({
        "name": "3M Momentum",
        "name_cn": "3月动量",
        "value": _fmt(ret(63), 1),
        "score": score_ret(ret(63), [(-15, -4), (-5, -2), (0, 0), (8, 2), (20, 4), (9999, 5)]),
        "unit": "%",
    })
    sub.append({
        "name": "6M Momentum",
        "name_cn": "6月动量",
        "value": _fmt(ret(126), 1),
        "score": score_ret(ret(126), [(-20, -4), (-8, -2), (0, 0), (12, 2), (30, 4), (9999, 5)]),
        "unit": "%",
    })
    sub.append({
        "name": "12M Momentum",
        "name_cn": "12月动量",
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
    sub.append({"name": "RSI (14)", "name_cn": "RSI指标", "value": _fmt(rsi, 1), "score": rsi_score, "unit": ""})

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
    sub.append({"name": "MACD Signal", "name_cn": "MACD信号", "value": None, "score": macd_score, "unit": ""})

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {"composite": round(composite, 2), "label": "Momentum", "label_cn": "动量", "factors": sub}


# ---------------------------------------------------------------------------
# 2. Value Factors
# ---------------------------------------------------------------------------

def _compute_value(info):
    sub = []

    pe = info.get("trailingPE") or info.get("forwardPE")
    sub.append({
        "name": "P/E Ratio",
        "name_cn": "市盈率",
        "value": _fmt(pe, 1),
        "score": _thresh(pe, [(10, 5), (15, 3), (20, 1), (25, -1), (35, -3), (9999, -5)]),
        "unit": "x",
    })

    pb = info.get("priceToBook")
    sub.append({
        "name": "P/B Ratio",
        "name_cn": "市净率",
        "value": _fmt(pb, 2),
        "score": _thresh(pb, [(1, 5), (2, 3), (3, 1), (5, -1), (8, -3), (9999, -5)]),
        "unit": "x",
    })

    ev_ebitda = info.get("enterpriseToEbitda")
    sub.append({
        "name": "EV/EBITDA",
        "name_cn": "企业价值倍数",
        "value": _fmt(ev_ebitda, 1),
        "score": _thresh(ev_ebitda, [(8, 5), (12, 3), (18, 1), (25, -1), (40, -3), (9999, -5)]),
        "unit": "x",
    })

    ps = info.get("priceToSalesTrailing12Months")
    sub.append({
        "name": "P/S Ratio",
        "name_cn": "市销率",
        "value": _fmt(ps, 2),
        "score": _thresh(ps, [(1, 5), (3, 3), (6, 1), (10, -1), (20, -3), (9999, -5)]),
        "unit": "x",
    })

    dy = info.get("dividendYield")
    dy_pct = (dy * 100) if dy else None
    dy_score = 4.0 if dy_pct and dy_pct > 4 else (2.0 if dy_pct and dy_pct > 2 else (1.0 if dy_pct and dy_pct > 0 else 0.0))
    sub.append({
        "name": "Dividend Yield",
        "name_cn": "股息率",
        "value": _fmt(dy_pct, 2),
        "score": dy_score,
        "unit": "%",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {"composite": round(composite, 2), "label": "Value", "label_cn": "估值", "factors": sub}


# ---------------------------------------------------------------------------
# 3. Quality Factors
# ---------------------------------------------------------------------------

def _compute_quality(info):
    sub = []

    roe = info.get("returnOnEquity")
    roe_pct = (roe * 100) if roe else None
    sub.append({
        "name": "ROE",
        "name_cn": "净资产收益率",
        "value": _fmt(roe_pct, 1),
        "score": _thresh(roe_pct, [(-5, -5), (0, -3), (8, -1), (15, 2), (25, 4), (9999, 5)]),
        "unit": "%",
    })

    roa = info.get("returnOnAssets")
    roa_pct = (roa * 100) if roa else None
    sub.append({
        "name": "ROA",
        "name_cn": "总资产收益率",
        "value": _fmt(roa_pct, 1),
        "score": _thresh(roa_pct, [(-2, -5), (0, -3), (3, -1), (7, 2), (12, 4), (9999, 5)]),
        "unit": "%",
    })

    gm = info.get("grossMargins")
    gm_pct = (gm * 100) if gm else None
    sub.append({
        "name": "Gross Margin",
        "name_cn": "毛利率",
        "value": _fmt(gm_pct, 1),
        "score": _thresh(gm_pct, [(10, -3), (20, -1), (35, 1), (50, 3), (65, 4), (9999, 5)]),
        "unit": "%",
    })

    om = info.get("operatingMargins")
    om_pct = (om * 100) if om else None
    sub.append({
        "name": "Operating Margin",
        "name_cn": "营业利润率",
        "value": _fmt(om_pct, 1),
        "score": _thresh(om_pct, [(-5, -5), (0, -3), (5, -1), (12, 1), (20, 3), (9999, 5)]),
        "unit": "%",
    })

    de = info.get("debtToEquity")
    sub.append({
        "name": "Debt/Equity",
        "name_cn": "负债权益比",
        "value": _fmt(de, 1),
        "score": _thresh(de, [(20, 5), (50, 3), (100, 1), (150, -1), (200, -3), (9999, -5)]),
        "unit": "%",
    })

    cr = info.get("currentRatio")
    sub.append({
        "name": "Current Ratio",
        "name_cn": "流动比率",
        "value": _fmt(cr, 2),
        "score": _thresh(cr, [(0.5, -5), (1.0, -2), (1.5, 1), (2.5, 4), (9999, 5)]),
        "unit": "x",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {"composite": round(composite, 2), "label": "Quality", "label_cn": "质量", "factors": sub}


# ---------------------------------------------------------------------------
# 4. Growth Factors
# ---------------------------------------------------------------------------

def _compute_growth(info):
    sub = []

    rg = info.get("revenueGrowth")
    rg_pct = (rg * 100) if rg else None
    sub.append({
        "name": "Revenue Growth",
        "name_cn": "营收增长率",
        "value": _fmt(rg_pct, 1),
        "score": _thresh(rg_pct, [(-10, -5), (-3, -3), (0, -1), (5, 1), (15, 3), (9999, 5)]),
        "unit": "%",
    })

    eg = info.get("earningsGrowth")
    eg_pct = (eg * 100) if eg else None
    sub.append({
        "name": "EPS Growth",
        "name_cn": "每股收益增长",
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
        fwd_score = _thresh(fwd_growth, [(-15, -5), (-5, -3), (0, -1), (5, 1), (15, 3), (9999, 5)])
    sub.append({
        "name": "Fwd EPS Growth",
        "name_cn": "预期EPS增长",
        "value": _fmt(fwd_growth, 1),
        "score": fwd_score,
        "unit": "%",
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
        "name": "Analyst Rating",
        "name_cn": "分析师评级",
        "value": _fmt(rc, 2),
        "score": rc_score,
        "unit": "/5",
    })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {"composite": round(composite, 2), "label": "Growth", "label_cn": "成长", "factors": sub}


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
    sub.append({"name": "Beta", "name_cn": "贝塔系数", "value": _fmt(beta, 2), "score": beta_score, "unit": ""})

    if n >= 30:
        rets = np.diff(np.log(closes[-31:]))
        rv = float(np.std(rets) * np.sqrt(252) * 100)
        sub.append({
            "name": "30D Realized Vol",
            "name_cn": "30日波动率",
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
            "name": "Max Drawdown (1Y)",
            "name_cn": "最大回撤",
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
            "name": "ATR % of Price",
            "name_cn": "真实波幅占比",
            "value": _fmt(atr_pct, 2),
            "score": _thresh(atr_pct, [(0.5, 5), (1.0, 3), (2.0, 1), (3.5, -1), (5.0, -3), (9999, -5)]),
            "unit": "%",
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]))
    return {"composite": round(composite, 2), "label": "Volatility", "label_cn": "波动性", "factors": sub}


# ---------------------------------------------------------------------------
# 6. Sentiment Factors
# ---------------------------------------------------------------------------

def _compute_sentiment(stock, info):
    sub = []

    sp = info.get("shortPercentOfFloat")
    if sp:
        sp_pct = sp * 100
        sub.append({
            "name": "Short Interest",
            "name_cn": "空头仓位",
            "value": _fmt(sp_pct, 1),
            "score": _thresh(sp_pct, [(2, 4), (5, 2), (10, -1), (20, -3), (9999, -5)]),
            "unit": "%",
        })

    inst = info.get("heldPercentInstitutions")
    if inst:
        ip = inst * 100
        sub.append({
            "name": "Institutional Hold.",
            "name_cn": "机构持仓",
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
                        recent[txn_col].astype(str).str.contains("Buy|Purchase", case=False, na=False)
                    ]["Shares"].sum()
                    sells = recent[
                        recent[txn_col].astype(str).str.contains("Sell|Sale", case=False, na=False)
                    ]["Shares"].sum()
                    ins_score = 2.0 if buys > sells else (-2.0 if sells > buys else 0.0)
    except Exception:
        pass
    sub.append({"name": "Insider Activity", "name_cn": "内部人员活动", "value": None, "score": ins_score, "unit": ""})

    rc = info.get("recommendationMean")
    if rc:
        rc_score = _thresh(rc, [(1.5, 5), (2.0, 3), (2.5, 1), (3.0, -1), (9999, -3)])
        sub.append({
            "name": "Analyst Consensus",
            "name_cn": "分析师共识",
            "value": _fmt(rc, 2),
            "score": rc_score,
            "unit": "/5",
        })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {"composite": round(composite, 2), "label": "Sentiment", "label_cn": "情绪", "factors": sub}


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
                "name": "Market Correlation",
                "name_cn": "市场相关性",
                "value": _fmt(corr, 2),
                "score": _clamp(-corr * 3.0),
                "unit": "",
            })
            if min_len >= 252:
                stock_ret = (closes[-1] / closes[-252] - 1) * 100
                spy_ret = (spy_hist[-1] / spy_hist[-252] - 1) * 100
                rs = stock_ret - spy_ret
                sub.append({
                    "name": "Relative Strength (1Y)",
                    "name_cn": "相对强度",
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
                "name": "52W Range Position",
                "name_cn": "52周位置",
                "value": _fmt(pos, 1),
                "score": _thresh(pos, [(10, -4), (25, -2), (40, 0), (60, 1), (75, 3), (9999, 4)]),
                "unit": "%",
            })

    composite = _clamp(_safe_mean([s["score"] for s in sub]) if sub else 0.0)
    return {"composite": round(composite, 2), "label": "Macro", "label_cn": "宏观", "factors": sub}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt(v, decimals=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), decimals)
