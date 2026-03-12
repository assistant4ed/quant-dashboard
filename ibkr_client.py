"""
Interactive Brokers Client Portal API client.

Provides real-time market data, options chains, and historical candles
from the IBKR gateway running at localhost:5055.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import requests
import urllib3

# Suppress SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("ibkr")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IBKR_BASE_URL = "https://localhost:5055/v1/api"
REQUEST_TIMEOUT = 10
CONID_CACHE_FILE = Path(__file__).parent / "data" / "conid_cache.json"
SNAPSHOT_FIELDS = (
    "31,70,71,82,83,84,85,86,87,88,"
    "7219,7220,7221,7222,"
    "7282,7283,7284,7285,7286,7287,7288,7289,7290,7291,7292,7293,"
    "7674,7675,7676,7677,7678,7679,7680,7681"
)
# Field IDs:
# 31=Last, 70=High, 71=Low, 82=Change, 83=%Change, 84=Bid, 86=Ask, 87=Volume
# 88=Close, 7219=Symbol, 7221=Exchange, 7282=Market Cap
# 7675=PE, 7676=Div Yield, 7293=52W High
# See: https://www.interactivebrokers.com/api/doc.html
#   #tag/Market-Data/paths/~1iserver~1marketdata~1snapshot/get

# Top 20 most actively traded US stocks (by volume/market cap)
TOP_20_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AVGO", "JPM", "V",
    "UNH", "MA", "HD", "COST", "PG",
    "JNJ", "ABBV", "CRM", "NFLX", "AMD",
]

# Top 50 most actively traded US stocks (expanded for venture fund coverage)
TOP_50_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "TSLA", "AVGO", "JPM", "V",
    "UNH", "MA", "HD", "COST", "PG",
    "JNJ", "ABBV", "CRM", "NFLX", "AMD",
    "LLY", "MRK", "PEP", "KO", "ADBE",
    "WMT", "BAC", "TMO", "CSCO", "ACN",
    "ORCL", "MCD", "ABT", "DHR", "QCOM",
    "TXN", "NEE", "PM", "INTC", "CMCSA",
    "INTU", "AMGN", "ISRG", "GE", "IBM",
    "NOW", "CAT", "GS", "AMAT", "BLK",
]

# Auto-reconnect settings
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY = 2  # seconds

# Top 30 most-traded options (stocks/ETFs/indices)
TOP_30_OPTIONS = [
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
    "AMZN", "META", "MSFT", "AMD", "GOOGL",
    "IWM", "SPX", "NFLX", "BABA", "COIN",
    "SQ", "PLTR", "SOFI", "MARA", "RIOT",
    "XSP", "MSTR", "SMCI", "INTC", "BAC",
    "F", "UBER", "DIS", "PYPL", "MU",
]

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
LOOKBACK_BARS = 20
MARKET_DAY_5M_BARS = 78  # ~6.5 hours of 5-min bars

# Session for connection reuse
_session = requests.Session()
_session.verify = False

# Conid cache: ticker -> conid mapping (loaded from disk if available)
_conid_cache = {}


def _load_conid_cache():
    """Load conid cache from disk."""
    global _conid_cache
    try:
        if CONID_CACHE_FILE.exists():
            with open(CONID_CACHE_FILE) as f:
                _conid_cache = json.load(f)
            logger.info("Loaded %d conids from cache", len(_conid_cache))
    except Exception as exc:
        logger.warning("Failed to load conid cache: %s", exc)


def _save_conid_cache():
    """Save conid cache to disk."""
    try:
        CONID_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONID_CACHE_FILE, "w") as f:
            json.dump(_conid_cache, f, indent=2)
    except Exception as exc:
        logger.warning("Failed to save conid cache: %s", exc)


_load_conid_cache()


# ---------------------------------------------------------------------------
# Core API Methods
# ---------------------------------------------------------------------------

def _get(endpoint, params=None):
    """Make a GET request to the IBKR gateway."""
    url = f"{IBKR_BASE_URL}{endpoint}"
    try:
        resp = _session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        logger.error("IBKR gateway not running at %s", IBKR_BASE_URL)
        return None
    except requests.exceptions.HTTPError as exc:
        logger.error("IBKR API error %s: %s", endpoint, exc)
        return None
    except Exception as exc:
        logger.error("IBKR request failed %s: %s", endpoint, exc)
        return None


def _post(endpoint, data=None):
    """Make a POST request to the IBKR gateway."""
    url = f"{IBKR_BASE_URL}{endpoint}"
    try:
        resp = _session.post(url, json=data, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        logger.error("IBKR gateway not running at %s", IBKR_BASE_URL)
        return None
    except Exception as exc:
        logger.error("IBKR request failed %s: %s", endpoint, exc)
        return None


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def check_auth_status():
    """Check if the IBKR gateway is authenticated.

    Returns dict with 'authenticated' bool and 'connected' bool.
    """
    result = _get("/iserver/auth/status")
    if result is None:
        return {
            "authenticated": False,
            "connected": False,
            "error": "Gateway not reachable",
        }
    return {
        "authenticated": result.get("authenticated", False),
        "connected": result.get("connected", False),
        "competing": result.get("competing", False),
        "message": result.get("message", ""),
    }


def reauthenticate():
    """Send a reauthenticate request to keep the session alive."""
    return _post("/iserver/reauthenticate")


def tickle():
    """Keep the session alive (must be called every few minutes)."""
    return _post("/tickle")


# ---------------------------------------------------------------------------
# Contract Search (resolve ticker -> conid)
# ---------------------------------------------------------------------------

def search_contract(symbol):
    """Search for a contract by symbol. Returns the conid (contract ID).

    The conid is required for most IBKR API calls.
    """
    if symbol in _conid_cache:
        return _conid_cache[symbol]

    result = _get(
        "/iserver/secdef/search",
        params={"symbol": symbol, "name": "true"},
    )
    if not result or not isinstance(result, list) or len(result) == 0:
        return None

    # Find US stock match — exchange info is in companyHeader, not description
    for item in result:
        header = (item.get("companyHeader") or item.get("description") or "").upper()
        if "NASDAQ" in header or "NYSE" in header or "ARCA" in header:
            _conid_cache[symbol] = item["conid"]
            _save_conid_cache()
            return item["conid"]

    # Fallback to first result
    conid = result[0].get("conid")
    if conid:
        _conid_cache[symbol] = conid
        _save_conid_cache()
    return conid


def resolve_conids(symbols):
    """Resolve multiple symbols to conids. Returns dict of symbol->conid."""
    resolved = {}
    for sym in symbols:
        conid = search_contract(sym)
        if conid:
            resolved[sym] = conid
    return resolved


# ---------------------------------------------------------------------------
# Market Data Snapshots
# ---------------------------------------------------------------------------

def get_market_snapshot(conids):
    """Get real-time market data snapshot for a list of conids.

    IBKR requires the first snapshot call to "subscribe" the conid.
    The second call returns actual data. This method handles that
    automatically by retrying once if the first call returns empty prices.

    Args:
        conids: list of conid integers or comma-separated string

    Returns list of dicts with price/volume data.
    """
    if isinstance(conids, list):
        conids_str = ",".join(str(c) for c in conids)
    else:
        conids_str = str(conids)

    params = {"conids": conids_str, "fields": SNAPSHOT_FIELDS}

    # First call subscribes the conids
    result = _get("/iserver/marketdata/snapshot", params=params)

    # Check if we got empty/stale data (no "31" last price field)
    if result and isinstance(result, list):
        has_prices = any(snap.get("31") for snap in result)
        if not has_prices:
            # Wait briefly and retry — second call gets real data
            time.sleep(1)
            result = _get("/iserver/marketdata/snapshot", params=params)

    return result


def get_market_snapshot_by_symbols(symbols):
    """Get market snapshots for a list of ticker symbols.

    Resolves symbols to conids first, then fetches snapshots.
    Returns list of enriched dicts with symbol names.
    """
    conid_map = resolve_conids(symbols)
    if not conid_map:
        return []

    conids = list(conid_map.values())
    snapshots = get_market_snapshot(conids)
    if not snapshots:
        return []

    # Map conids back to symbols (handle string/int mismatch)
    conid_to_sym = {}
    for sym, cid in conid_map.items():
        conid_to_sym[int(cid)] = sym
        conid_to_sym[str(cid)] = sym

    results = []
    for snap in snapshots:
        conid = snap.get("conid") or snap.get("conidEx")
        symbol = conid_to_sym.get(conid, "")
        results.append({
            "symbol": symbol,
            "conid": conid,
            "last": snap.get("31"),
            "high": snap.get("70"),
            "low": snap.get("71"),
            "change": snap.get("82"),
            "change_pct": snap.get("83"),
            "bid": snap.get("84"),
            "ask": snap.get("86"),
            "volume": snap.get("87"),
            "avg_volume": snap.get("87_raw"),
            "close": snap.get("88"),
            "open": snap.get("7295"),
            "market_cap": snap.get("7282"),
            "pe": snap.get("7675"),
            "div_yield": snap.get("7676"),
        })

    return results


# ---------------------------------------------------------------------------
# Historical Data (Candles)
# ---------------------------------------------------------------------------

def get_historical_data(conid, period="1d", bar_size="1min"):
    """Get historical market data (candles).

    Args:
        conid: Contract ID
        period: Time period - "1d", "1w", "1m", "3m", "6m", "1y"
        bar_size: Bar size - "1secs", "5secs", "10secs", "30secs",
                  "1min", "2min", "3min", "5min", "10min", "15min",
                  "30min", "1h", "2h", "4h", "8h", "1d", "1w", "1m"

    Returns list of OHLCV candle dicts.
    """
    result = _get("/iserver/marketdata/history", params={
        "conid": conid,
        "period": period,
        "bar": bar_size,
    })

    if not result or "data" not in result:
        return []

    candles = []
    for bar in result["data"]:
        candles.append({
            "time": bar.get("t"),  # epoch ms
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
        })

    return candles


def get_intraday_candles(symbol, bar_size="1min", period="1d"):
    """Get intraday candles for a symbol.

    Convenience wrapper that resolves symbol to conid.
    """
    conid = search_contract(symbol)
    if not conid:
        return []
    return get_historical_data(conid, period=period, bar_size=bar_size)


# ---------------------------------------------------------------------------
# Options Chain
# ---------------------------------------------------------------------------

def get_options_info(conid):
    """Get available options expirations and strikes for a contract.

    Returns dict with months, expirations, and strikes.
    """
    result = _get("/iserver/secdef/info", params={
        "conid": conid,
        "secType": "OPT",
    })
    return result


def get_options_chain(symbol, month=None, right=None, strike=None):
    """Get options chain for a symbol.

    Args:
        symbol: Ticker symbol
        month: Expiry month in format "MAR26" (optional)
        right: "C" for calls, "P" for puts (optional)
        strike: Strike price (optional)

    Returns list of option contracts with Greeks.
    """
    conid = search_contract(symbol)
    if not conid:
        return {"error": f"Could not find contract for {symbol}"}

    # Get available strikes/expirations
    info = _get("/iserver/secdef/info", params={
        "conid": conid,
        "secType": "OPT",
    })

    if not info:
        return {"error": "No options data available", "symbol": symbol}

    return {
        "symbol": symbol,
        "conid": conid,
        "options_info": info,
    }


def get_option_strikes(conid, sectype="OPT", month=None, exchange=None):
    """Get strikes for a given contract and month."""
    params = {"conid": conid, "sectype": sectype}
    if month:
        params["month"] = month
    if exchange:
        params["exchange"] = exchange

    result = _get("/iserver/secdef/strikes", params=params)
    return result


def get_option_contracts(conid, sectype="OPT", month=None, right=None, strike=None):
    """Get specific option contracts matching filters."""
    body = {
        "conid": conid,
        "sectype": sectype,
    }
    if month:
        body["month"] = month
    if right:
        body["right"] = right
    if strike:
        body["strike"] = str(strike)

    result = _post("/iserver/secdef/info", data=body)
    return result


# ---------------------------------------------------------------------------
# Short-Term Trading Analysis
# ---------------------------------------------------------------------------

def get_short_term_analysis(symbol):
    """Generate short-term trading analysis for a symbol.

    Uses 1-minute and 5-minute candles to compute:
    - VWAP
    - RSI (14-period on 5-min bars)
    - MACD (12, 26, 9)
    - Stochastic (14, 3, 3)
    - Support/Resistance levels
    - Entry/Exit signals with rationale
    """
    conid = search_contract(symbol)
    if not conid:
        return {"error": f"Could not resolve {symbol}"}

    # Fetch 1-day of 5-minute bars
    candles_5m = get_historical_data(conid, period="1d", bar_size="5min")
    # Fetch 5-day of 1-hour bars for context
    candles_1h = get_historical_data(conid, period="5d", bar_size="1h")

    if not candles_5m:
        return {"error": "No intraday data available", "symbol": symbol}

    closes_5m = [c["close"] for c in candles_5m if c.get("close")]
    highs_5m = [c["high"] for c in candles_5m if c.get("high")]
    lows_5m = [c["low"] for c in candles_5m if c.get("low")]
    volumes_5m = [c["volume"] for c in candles_5m if c.get("volume")]

    analysis = {
        "symbol": symbol,
        "conid": conid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candles_5m": candles_5m[-MARKET_DAY_5M_BARS:],
        "candles_1h": candles_1h,
    }

    if len(closes_5m) < RSI_PERIOD:
        analysis["indicators"] = {"error": "Insufficient data"}
        return analysis

    # VWAP
    vwap_values = _calc_vwap(candles_5m)

    current_price = closes_5m[-1]
    current_vwap = vwap_values[-1] if vwap_values else current_price

    # RSI (14-period)
    rsi = _calc_rsi(closes_5m, RSI_PERIOD)

    # MACD (12, 26, 9)
    macd_line, signal_line, histogram = _calc_macd(
        closes_5m, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    )

    # Stochastic (14, 3, 3)
    stoch_k, stoch_d = _calc_stochastic(
        highs_5m, lows_5m, closes_5m, STOCH_K_PERIOD, STOCH_D_PERIOD,
    )

    # Support/Resistance
    lookback = min(LOOKBACK_BARS, len(lows_5m))
    support = min(lows_5m[-lookback:])
    resistance = max(highs_5m[-lookback:])

    # Generate signals with rationale
    signals, rationale = _generate_signals(
        current_price, current_vwap, rsi,
        macd_line, signal_line, histogram,
        stoch_k, stoch_d,
    )

    # Overall recommendation
    recommendation, rec_rationale = _derive_recommendation(signals)

    analysis["indicators"] = {
        "vwap": current_vwap,
        "rsi": round(rsi, 1),
        "macd": round(macd_line, 4),
        "macd_signal": round(signal_line, 4),
        "macd_histogram": round(histogram, 4),
        "stochastic_k": round(stoch_k, 1),
        "stochastic_d": round(stoch_d, 1),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
    }
    analysis["signals"] = signals
    analysis["rationale"] = rationale
    analysis["recommendation"] = recommendation
    analysis["recommendation_rationale"] = rec_rationale
    analysis["vwap_series"] = vwap_values[-MARKET_DAY_5M_BARS:]

    return analysis


# ---------------------------------------------------------------------------
# Signal Generation Helpers
# ---------------------------------------------------------------------------

def _generate_signals(
    current_price,
    current_vwap,
    rsi,
    macd_line,
    signal_line,
    histogram,
    stoch_k,
    stoch_d,
):
    """Evaluate indicators and produce signal labels with rationale."""
    signals = []
    rationale = []

    # VWAP signal
    if current_price > current_vwap:
        signals.append("BULLISH")
        rationale.append(
            f"Price ${current_price:.2f} above VWAP "
            f"${current_vwap:.2f} -- buyers in control"
        )
    else:
        signals.append("BEARISH")
        rationale.append(
            f"Price ${current_price:.2f} below VWAP "
            f"${current_vwap:.2f} -- sellers in control"
        )

    # RSI signal
    rsi_overbought_threshold = 70
    rsi_oversold_threshold = 30
    if rsi > rsi_overbought_threshold:
        signals.append("OVERBOUGHT")
        rationale.append(
            f"RSI at {rsi:.1f} -- overbought territory, potential reversal down"
        )
    elif rsi < rsi_oversold_threshold:
        signals.append("OVERSOLD")
        rationale.append(
            f"RSI at {rsi:.1f} -- oversold territory, potential bounce"
        )
    else:
        rationale.append(f"RSI at {rsi:.1f} -- neutral momentum zone")

    # MACD signal
    if macd_line > signal_line and histogram > 0:
        signals.append("MACD_BULLISH")
        rationale.append(
            "MACD crossed above signal line -- bullish momentum building"
        )
    elif macd_line < signal_line and histogram < 0:
        signals.append("MACD_BEARISH")
        rationale.append(
            "MACD crossed below signal line -- bearish momentum building"
        )

    # Stochastic
    stoch_overbought = 80
    stoch_oversold = 20
    if stoch_k > stoch_overbought and stoch_d > stoch_overbought:
        signals.append("STOCH_OVERBOUGHT")
        rationale.append(
            f"Stochastic K={stoch_k:.0f} D={stoch_d:.0f} -- "
            "overbought, watch for crossover"
        )
    elif stoch_k < stoch_oversold and stoch_d < stoch_oversold:
        signals.append("STOCH_OVERSOLD")
        rationale.append(
            f"Stochastic K={stoch_k:.0f} D={stoch_d:.0f} -- "
            "oversold, potential reversal up"
        )

    return signals, rationale


def _derive_recommendation(signals):
    """Count bullish vs bearish signals and return a recommendation."""
    bullish_count = sum(
        1 for s in signals if "BULLISH" in s or "OVERSOLD" in s
    )
    bearish_count = sum(
        1 for s in signals if "BEARISH" in s or "OVERBOUGHT" in s
    )

    if bullish_count > bearish_count:
        return "BUY", f"{bullish_count} bullish vs {bearish_count} bearish signals"
    if bearish_count > bullish_count:
        return "SELL", f"{bearish_count} bearish vs {bullish_count} bullish signals"
    return "HOLD", "Mixed signals -- wait for clearer direction"


# ---------------------------------------------------------------------------
# Technical Indicator Helpers
# ---------------------------------------------------------------------------

def _calc_vwap(candles):
    """Calculate cumulative VWAP from a list of candle dicts."""
    cum_vol = 0
    cum_vwap = 0
    vwap_values = []

    for candle in candles:
        if candle.get("close") and candle.get("volume"):
            typical = (candle["high"] + candle["low"] + candle["close"]) / 3
            cum_vol += candle["volume"]
            cum_vwap += typical * candle["volume"]
            vwap_values.append(
                round(cum_vwap / cum_vol, 2) if cum_vol > 0 else 0
            )
        else:
            vwap_values.append(vwap_values[-1] if vwap_values else 0)

    return vwap_values


def _calc_rsi(closes, period=14):
    """Calculate RSI from a list of close prices."""
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_ema(data, period):
    """Calculate exponential moving average."""
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


def _calc_macd(closes, fast=12, slow=26, signal_period=9):
    """Calculate MACD line, signal line, and histogram."""
    if len(closes) < slow:
        return 0, 0, 0

    ema_fast = _calc_ema(closes, fast)
    ema_slow = _calc_ema(closes, slow)

    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_ema = _calc_ema(macd_line[slow - 1:], signal_period)

    current_macd = macd_line[-1]
    current_signal = signal_ema[-1] if signal_ema else 0
    histogram = current_macd - current_signal

    return current_macd, current_signal, histogram


def _calc_stochastic(highs, lows, closes, k_period=14, d_period=3):
    """Calculate Stochastic K and D values."""
    if len(closes) < k_period:
        return 50.0, 50.0

    k_values = []
    for i in range(k_period - 1, len(closes)):
        h = max(highs[i - k_period + 1:i + 1])
        l = min(lows[i - k_period + 1:i + 1])
        if h == l:
            k_values.append(50.0)
        else:
            k_values.append((closes[i] - l) / (h - l) * 100)

    # D is SMA of K
    if len(k_values) >= d_period:
        d_value = sum(k_values[-d_period:]) / d_period
    else:
        d_value = k_values[-1] if k_values else 50.0

    return k_values[-1] if k_values else 50.0, d_value


# ---------------------------------------------------------------------------
# Portfolio & Account
# ---------------------------------------------------------------------------

def get_accounts():
    """Get list of accounts."""
    return _get("/portfolio/accounts")


def get_account_summary(account_id):
    """Get account summary/balances."""
    return _get(f"/portfolio/{account_id}/summary")


def get_positions(account_id):
    """Get current positions."""
    return _get(f"/portfolio/{account_id}/positions")


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------

def keep_session_alive():
    """Call tickle endpoint to prevent session timeout.

    Should be called every 1-2 minutes.
    """
    result = tickle()
    if result:
        # Also validate SSO
        _post("/sso/validate")
    return result


# ---------------------------------------------------------------------------
# Auto-Reconnect
# ---------------------------------------------------------------------------

def auto_reconnect():
    """Attempt to re-establish IBKR gateway connection.

    Tries reauthentication up to MAX_RECONNECT_ATTEMPTS times
    with exponential backoff.

    Returns dict with connection status and attempt details.
    """
    attempts = []

    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        logger.info("Reconnect attempt %d/%d", attempt, MAX_RECONNECT_ATTEMPTS)

        # Step 1: Tickle to wake the session
        tickle_result = tickle()
        if tickle_result:
            logger.info("Tickle succeeded on attempt %d", attempt)

        # Step 2: Reauthenticate
        reauth_result = reauthenticate()

        # Step 3: Check status
        time.sleep(RECONNECT_DELAY)
        status = check_auth_status()

        attempt_info = {
            "attempt": attempt,
            "tickle": tickle_result is not None,
            "reauth": reauth_result is not None,
            "authenticated": status.get("authenticated", False),
            "connected": status.get("connected", False),
        }
        attempts.append(attempt_info)

        if status.get("authenticated") and status.get("connected"):
            logger.info("Reconnected successfully on attempt %d", attempt)
            return {
                "success": True,
                "attempts": attempts,
                "status": status,
            }

        # Exponential backoff
        if attempt < MAX_RECONNECT_ATTEMPTS:
            backoff = RECONNECT_DELAY * (2 ** (attempt - 1))
            logger.info("Waiting %ds before next attempt", backoff)
            time.sleep(backoff)

    logger.warning("Failed to reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS)
    return {
        "success": False,
        "attempts": attempts,
        "status": check_auth_status(),
        "message": "Failed to reconnect. Ensure IBKR gateway is running at "
                   f"{IBKR_BASE_URL} and you are logged in.",
    }


def get_top50_snapshots():
    """Get market snapshots for all top 50 stocks.

    Fetches in batches to avoid overwhelming the IBKR gateway.
    """
    batch_size = 10
    all_results = []

    for i in range(0, len(TOP_50_TICKERS), batch_size):
        batch = TOP_50_TICKERS[i:i + batch_size]
        snapshots = get_market_snapshot_by_symbols(batch)
        if snapshots:
            all_results.extend(snapshots)
        # Small delay between batches
        if i + batch_size < len(TOP_50_TICKERS):
            time.sleep(0.5)

    return all_results
