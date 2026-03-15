"""Options scanner using yfinance for free options chain data.

Provides options overview, chain data, flow metrics, and unusual activity.
"""
import logging
import time
from datetime import datetime, timezone

import yfinance as yf

logger = logging.getLogger("options_scanner")

CACHE_TTL = 300  # 5 minutes
_cache: dict[str, tuple[float, object]] = {}


def _get_cached(key: str):
    """Return cached value if still valid."""
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    return None


def _set_cached(key: str, value):
    _cache[key] = (time.time(), value)


def _get_ticker_options(ticker: str):
    """Get yfinance Ticker and its options data."""
    t = yf.Ticker(ticker)
    info = t.info or {}
    price = info.get("regularMarketPrice") or info.get("currentPrice") or 0
    expirations = list(t.options) if t.options else []
    return t, price, expirations


def get_options_overview(ticker: str) -> dict:
    """Get options overview: underlying price and available expirations."""
    cache_key = f"overview:{ticker}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    _, price, expirations = _get_ticker_options(ticker)
    result = {
        "underlying_price": round(price, 2) if price else None,
        "expirations": expirations,
        "source": "yfinance",
    }
    _set_cached(cache_key, result)
    return result


def get_options_chain_data(
    ticker: str,
    expiration: str | None = None,
    right: str | None = None,
) -> dict:
    """Get options chain for a ticker and expiration.

    Returns calls and puts with strike, bid, ask, last, volume, OI, IV.
    """
    t, price, expirations = _get_ticker_options(ticker)
    if not expirations:
        return {"chain": [], "expiration": None}

    exp = expiration if expiration in expirations else expirations[0]

    cache_key = f"chain:{ticker}:{exp}:{right}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    opt = t.option_chain(exp)
    chain = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if right != "P":
        for _, row in opt.calls.iterrows():
            chain.append(_row_to_dict(row, "C", now_str))

    if right != "C":
        for _, row in opt.puts.iterrows():
            chain.append(_row_to_dict(row, "P", now_str))

    chain.sort(key=lambda x: (x["right"], x["strike"]))

    result = {
        "chain": chain,
        "expiration": exp,
        "underlying_price": round(price, 2) if price else None,
        "source": "yfinance",
    }
    _set_cached(cache_key, result)
    return result


def _row_to_dict(row, right: str, timestamp: str) -> dict:
    """Convert a pandas row to option dict."""
    return {
        "right": right,
        "strike": _safe_num(row.get("strike")),
        "bid": _safe_num(row.get("bid")),
        "ask": _safe_num(row.get("ask")),
        "last": _safe_num(row.get("lastPrice")),
        "volume": _safe_int(row.get("volume")),
        "open_interest": _safe_int(row.get("openInterest")),
        "implied_vol": _safe_num(row.get("impliedVolatility")),
        "delta": None,
        "theta": None,
        "timestamp": timestamp,
    }


def get_options_flow(ticker: str) -> dict:
    """Compute put/call ratio and volume metrics."""
    cache_key = f"flow:{ticker}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    t, price, expirations = _get_ticker_options(ticker)
    if not expirations:
        return {
            "put_call_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "implied_move": None,
        }

    exp = expirations[0]
    opt = t.option_chain(exp)

    call_vol = int(opt.calls["volume"].sum()) if "volume" in opt.calls else 0
    put_vol = int(opt.puts["volume"].sum()) if "volume" in opt.puts else 0

    pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else None

    # Estimate implied move from ATM straddle
    implied_move = _calc_implied_move(opt, price)

    result = {
        "put_call_ratio": pc_ratio,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "implied_move": implied_move,
        "source": "yfinance",
    }
    _set_cached(cache_key, result)
    return result


def get_unusual_options() -> dict:
    """Scan watchlist for unusual options activity (volume >> open interest)."""
    cache_key = "unusual:scan"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    watchlist = ["AAPL", "TSLA", "NVDA", "SPY", "QQQ", "AMZN", "META", "MSFT"]
    unusual = []

    for sym in watchlist:
        try:
            t = yf.Ticker(sym)
            if not t.options:
                continue
            exp = t.options[0]
            opt = t.option_chain(exp)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

            for df, right in [(opt.calls, "C"), (opt.puts, "P")]:
                for _, row in df.iterrows():
                    vol = _safe_int(row.get("volume")) or 0
                    oi = _safe_int(row.get("openInterest")) or 1
                    if vol > 0 and oi > 0 and vol / oi > 3.0:
                        unusual.append({
                            "symbol": sym,
                            "right": right,
                            "strike": _safe_num(row.get("strike")),
                            "volume": vol,
                            "open_interest": oi,
                            "volume_ratio": round(vol / oi, 1),
                            "timestamp": now_str,
                        })
        except Exception as exc:
            logger.debug("Unusual scan skip %s: %s", sym, exc)

    unusual.sort(key=lambda x: x.get("volume_ratio", 0), reverse=True)
    result = {"unusual": unusual[:20]}
    _set_cached(cache_key, result)
    return result


def _calc_implied_move(opt, price: float) -> str | None:
    """Estimate implied move from ATM straddle."""
    if not price or price <= 0:
        return None
    try:
        calls = opt.calls
        puts = opt.puts
        atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts["strike"] - price).abs().argsort()[:1]]
        call_mid = (atm_call["bid"].values[0] + atm_call["ask"].values[0]) / 2
        put_mid = (atm_put["bid"].values[0] + atm_put["ask"].values[0]) / 2
        straddle = call_mid + put_mid
        pct = (straddle / price) * 100
        return f"{pct:.1f}%"
    except Exception:
        return None


def _safe_num(val) -> float | None:
    """Convert to float, return None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    """Convert to int, return None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:
            return None
        return int(f)
    except (TypeError, ValueError):
        return None
