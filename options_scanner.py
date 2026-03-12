"""
Options scanner with real-time data and second-level timestamp accuracy.

Provides options chain analysis, unusual activity detection, Black-Scholes
pricing, options flow tracking, and multi-leg strategy construction using
the IBKR Client Portal API gateway.
"""
import logging
import math
from datetime import datetime, timezone, timedelta

import numpy as np

from ibkr_client import (
    TOP_30_OPTIONS,
    get_market_snapshot,
    get_options_info,
    get_options_chain,
    get_option_strikes,
    get_option_contracts,
    search_contract,
)

logger = logging.getLogger("options_scanner")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.045
TRADING_DAYS_PER_YEAR = 252
UNUSUAL_VOLUME_MULTIPLIER = 2.0
LARGE_TRADE_THRESHOLD = 100
DEFAULT_AVG_VOLUME = 500

# Snapshot field IDs for options data
# 31=Last, 84=Bid, 86=Ask, 87=Volume, 7282=OpenInterest
# 7219=Symbol, 7633=ImpliedVol, 7635=Delta, 7636=Gamma, 7637=Theta, 7638=Vega
OPTIONS_SNAPSHOT_FIELDS = (
    "31,84,86,87,88,"
    "7282,7219,"
    "7633,7635,7636,7637,7638"
)


def _now_iso():
    """Return current UTC timestamp with second precision in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Options Overview
# ---------------------------------------------------------------------------

def get_options_overview(symbol):
    """Return available expirations, strike range, and ATM strike for a symbol.

    Resolves the underlying contract, fetches the current price via a market
    snapshot, and queries the IBKR options info endpoint for available
    expirations and strikes.

    Args:
        symbol: Ticker symbol (e.g. "AAPL").

    Returns:
        dict with expirations, strike_min, strike_max, atm_strike,
        underlying_price, and a second-precision timestamp.
    """
    timestamp = _now_iso()

    conid = search_contract(symbol)
    if not conid:
        return {"error": f"Could not resolve symbol {symbol}", "timestamp": timestamp}

    # Current underlying price
    snapshots = get_market_snapshot([conid])
    underlying_price = None
    if snapshots and len(snapshots) > 0:
        raw = snapshots[0].get("31")
        if raw is not None:
            try:
                underlying_price = float(raw)
            except (ValueError, TypeError):
                underlying_price = None

    # Options metadata
    info = get_options_info(conid)
    if not info:
        return {
            "symbol": symbol,
            "conid": conid,
            "underlying_price": underlying_price,
            "error": "No options information available",
            "timestamp": timestamp,
        }

    # Parse expirations and strikes from the info response
    expirations = []
    all_strikes = []

    if isinstance(info, dict):
        expirations = info.get("expirations", [])
        months = info.get("months", [])
        if not expirations and months:
            expirations = months

        # Fetch strikes for the nearest month if available
        first_month = months[0] if months else None
        if first_month:
            strikes_data = get_option_strikes(conid, month=first_month)
            if strikes_data and isinstance(strikes_data, dict):
                call_strikes = strikes_data.get("call", [])
                put_strikes = strikes_data.get("put", [])
                all_strikes = sorted(set(call_strikes + put_strikes))
    elif isinstance(info, list):
        for entry in info:
            exp = entry.get("expiration") or entry.get("month")
            if exp and exp not in expirations:
                expirations.append(exp)
            strike = entry.get("strike")
            if strike is not None:
                all_strikes.append(float(strike))
        all_strikes = sorted(set(all_strikes))

    # Determine ATM strike
    atm_strike = None
    if underlying_price and all_strikes:
        atm_strike = min(all_strikes, key=lambda s: abs(s - underlying_price))

    strike_min = min(all_strikes) if all_strikes else None
    strike_max = max(all_strikes) if all_strikes else None

    return {
        "symbol": symbol,
        "conid": conid,
        "underlying_price": underlying_price,
        "expirations": expirations,
        "strike_min": strike_min,
        "strike_max": strike_max,
        "total_strikes": len(all_strikes),
        "atm_strike": atm_strike,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 2. Options Chain Data
# ---------------------------------------------------------------------------

def get_options_chain_data(symbol, expiration=None, right=None, strike_range=None):
    """Fetch the full options chain with Greeks for a symbol.

    Args:
        symbol: Ticker symbol.
        expiration: Expiration month filter (e.g. "MAR26"). None for all.
        right: "C" for calls, "P" for puts, None for both.
        strike_range: Tuple of (min_strike, max_strike) to filter. None for all.

    Returns:
        dict with chain rows, each containing bid, ask, last, volume,
        open_interest, implied_vol, delta, gamma, theta, vega, and a
        per-row second-precision timestamp.
    """
    timestamp = _now_iso()

    conid = search_contract(symbol)
    if not conid:
        return {"error": f"Could not resolve symbol {symbol}", "timestamp": timestamp}

    # Determine which rights to fetch
    rights_to_fetch = []
    if right:
        rights_to_fetch.append(right.upper())
    else:
        rights_to_fetch = ["C", "P"]

    chain_rows = []

    for r in rights_to_fetch:
        contracts = get_option_contracts(
            conid,
            month=expiration,
            right=r,
        )
        if not contracts or not isinstance(contracts, list):
            continue

        # Collect conids for snapshot batch
        option_conids = []
        contract_meta = []
        for contract in contracts:
            opt_conid = contract.get("conid")
            if opt_conid is None:
                continue

            contract_strike = contract.get("strike")
            if contract_strike is not None:
                contract_strike = float(contract_strike)

            # Apply strike range filter
            if strike_range and contract_strike is not None:
                if contract_strike < strike_range[0] or contract_strike > strike_range[1]:
                    continue

            option_conids.append(opt_conid)
            contract_meta.append({
                "conid": opt_conid,
                "strike": contract_strike,
                "right": r,
                "expiration": contract.get("maturityDate") or contract.get("expiry") or expiration,
                "symbol": contract.get("symbol", symbol),
            })

        # Fetch market data in batches of 50
        batch_size = 50
        for i in range(0, len(option_conids), batch_size):
            batch_conids = option_conids[i:i + batch_size]
            batch_meta = contract_meta[i:i + batch_size]

            snapshots = get_market_snapshot(batch_conids)
            if not snapshots:
                continue

            # Index snapshots by conid for lookup
            snap_map = {}
            for snap in snapshots:
                snap_conid = snap.get("conid") or snap.get("conidEx")
                if snap_conid is not None:
                    snap_map[int(snap_conid)] = snap

            for meta in batch_meta:
                snap = snap_map.get(int(meta["conid"]), {})
                row_timestamp = _now_iso()

                chain_rows.append({
                    "conid": meta["conid"],
                    "symbol": meta["symbol"],
                    "strike": meta["strike"],
                    "right": meta["right"],
                    "expiration": meta["expiration"],
                    "bid": _safe_float(snap.get("84")),
                    "ask": _safe_float(snap.get("86")),
                    "last": _safe_float(snap.get("31")),
                    "volume": _safe_int(snap.get("87")),
                    "open_interest": _safe_int(snap.get("7282")),
                    "implied_vol": _safe_float(snap.get("7633")),
                    "delta": _safe_float(snap.get("7635")),
                    "gamma": _safe_float(snap.get("7636")),
                    "theta": _safe_float(snap.get("7637")),
                    "vega": _safe_float(snap.get("7638")),
                    "timestamp": row_timestamp,
                })

    return {
        "symbol": symbol,
        "conid": conid,
        "total_contracts": len(chain_rows),
        "filters": {
            "expiration": expiration,
            "right": right,
            "strike_range": strike_range,
        },
        "chain": chain_rows,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 3. Unusual Activity Scanner
# ---------------------------------------------------------------------------

def scan_unusual_activity(symbols=None):
    """Scan for unusual options volume across a set of symbols.

    Flags contracts where current volume exceeds 2x the average daily
    volume or where a single trade size exceeds LARGE_TRADE_THRESHOLD.

    Args:
        symbols: List of ticker symbols to scan. Defaults to TOP_30_OPTIONS.

    Returns:
        dict with alerts sorted by volume ratio (highest first) and a
        second-precision timestamp.
    """
    timestamp = _now_iso()

    if symbols is None:
        symbols = TOP_30_OPTIONS

    alerts = []

    for symbol in symbols:
        conid = search_contract(symbol)
        if not conid:
            continue

        # Get nearby options contracts
        info = get_options_info(conid)
        if not info:
            continue

        # Find the nearest expiration month
        nearest_month = None
        if isinstance(info, dict):
            months = info.get("months", [])
            if months:
                nearest_month = months[0]
        elif isinstance(info, list) and len(info) > 0:
            nearest_month = info[0].get("month")

        if not nearest_month:
            continue

        # Fetch contracts for both calls and puts
        for r in ["C", "P"]:
            contracts = get_option_contracts(conid, month=nearest_month, right=r)
            if not contracts or not isinstance(contracts, list):
                continue

            option_conids = []
            meta_map = {}
            for contract in contracts:
                opt_conid = contract.get("conid")
                if opt_conid is None:
                    continue
                option_conids.append(opt_conid)
                meta_map[int(opt_conid)] = {
                    "strike": _safe_float(contract.get("strike")),
                    "expiration": contract.get("maturityDate") or nearest_month,
                    "right": r,
                }

            # Batch snapshot
            batch_size = 50
            for i in range(0, len(option_conids), batch_size):
                batch = option_conids[i:i + batch_size]
                snapshots = get_market_snapshot(batch)
                if not snapshots:
                    continue

                for snap in snapshots:
                    snap_conid = snap.get("conid") or snap.get("conidEx")
                    if snap_conid is None:
                        continue

                    volume = _safe_int(snap.get("87"))
                    open_interest = _safe_int(snap.get("7282"))
                    last_price = _safe_float(snap.get("31"))

                    if volume is None or volume == 0:
                        continue

                    avg_volume = open_interest if open_interest and open_interest > 0 else DEFAULT_AVG_VOLUME
                    volume_ratio = volume / avg_volume

                    meta = meta_map.get(int(snap_conid), {})
                    is_unusual_volume = volume_ratio >= UNUSUAL_VOLUME_MULTIPLIER
                    is_large_trade = volume >= LARGE_TRADE_THRESHOLD

                    if is_unusual_volume or is_large_trade:
                        alerts.append({
                            "symbol": symbol,
                            "conid": snap_conid,
                            "strike": meta.get("strike"),
                            "right": meta.get("right"),
                            "expiration": meta.get("expiration"),
                            "volume": volume,
                            "open_interest": open_interest,
                            "volume_ratio": round(volume_ratio, 2),
                            "last_price": last_price,
                            "is_unusual_volume": is_unusual_volume,
                            "is_large_trade": is_large_trade,
                            "timestamp": _now_iso(),
                        })

    # Sort by volume ratio descending
    alerts.sort(key=lambda a: a.get("volume_ratio", 0), reverse=True)

    return {
        "total_alerts": len(alerts),
        "symbols_scanned": len(symbols),
        "alerts": alerts,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 4. Black-Scholes Options Metrics
# ---------------------------------------------------------------------------

def calculate_options_metrics(symbol, current_price, strike, expiration_date, right, implied_vol):
    """Calculate Black-Scholes price, Greeks, and position analytics.

    Args:
        symbol: Ticker symbol (for labeling).
        current_price: Current underlying price.
        strike: Option strike price.
        expiration_date: Expiration as ISO date string "YYYY-MM-DD" or datetime.
        right: "C" for call, "P" for put.
        implied_vol: Annualized implied volatility as a decimal (e.g. 0.30).

    Returns:
        dict with theoretical_price, delta, gamma, theta, vega, rho,
        probability_of_profit, max_profit, max_loss, break_even, and a
        second-precision timestamp.
    """
    timestamp = _now_iso()

    if isinstance(expiration_date, str):
        exp_dt = datetime.strptime(expiration_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        exp_dt = expiration_date

    now = datetime.now(timezone.utc)
    days_to_expiry = max((exp_dt - now).total_seconds() / 86400, 0.001)
    t = days_to_expiry / 365.0
    is_call = right.upper() == "C"

    s = float(current_price)
    k = float(strike)
    sigma = float(implied_vol)
    r = RISK_FREE_RATE

    # Black-Scholes core
    d1 = _bs_d1(s, k, t, r, sigma)
    d2 = d1 - sigma * math.sqrt(t)

    nd1 = _norm_cdf(d1)
    nd2 = _norm_cdf(d2)
    n_neg_d1 = _norm_cdf(-d1)
    n_neg_d2 = _norm_cdf(-d2)
    nprime_d1 = _norm_pdf(d1)

    discount = math.exp(-r * t)

    # Theoretical price
    if is_call:
        price = s * nd1 - k * discount * nd2
    else:
        price = k * discount * n_neg_d2 - s * n_neg_d1

    # Greeks
    sqrt_t = math.sqrt(t)

    if is_call:
        delta = nd1
        rho = k * t * discount * nd2 / 100.0
    else:
        delta = nd1 - 1.0
        rho = -k * t * discount * n_neg_d2 / 100.0

    gamma = nprime_d1 / (s * sigma * sqrt_t)
    theta = (-(s * nprime_d1 * sigma) / (2.0 * sqrt_t)
             - r * k * discount * (nd2 if is_call else -n_neg_d2)) / 365.0
    vega = s * nprime_d1 * sqrt_t / 100.0

    # Probability of profit (probability of finishing ITM minus premium)
    if is_call:
        break_even = k + price
        prob_itm = nd2
    else:
        break_even = k - price
        prob_itm = n_neg_d2

    # Probability of profit accounts for premium paid
    if is_call:
        d2_be = _bs_d1(s, break_even, t, r, sigma) - sigma * sqrt_t
        probability_of_profit = _norm_cdf(d2_be)
    else:
        d2_be = _bs_d1(s, break_even, t, r, sigma) - sigma * sqrt_t
        probability_of_profit = _norm_cdf(-d2_be)

    # Max profit / max loss for a long position (1 contract = 100 shares)
    premium_per_share = price
    if is_call:
        max_profit = None  # Unlimited for long call
        max_loss = round(premium_per_share * 100, 2)
    else:
        max_profit = round((k - premium_per_share) * 100, 2)
        max_loss = round(premium_per_share * 100, 2)

    return {
        "symbol": symbol,
        "current_price": s,
        "strike": k,
        "right": right.upper(),
        "expiration_date": exp_dt.strftime("%Y-%m-%d"),
        "days_to_expiry": round(days_to_expiry, 1),
        "implied_vol": sigma,
        "theoretical_price": round(price, 4),
        "greeks": {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta, 6),
            "vega": round(vega, 6),
            "rho": round(rho, 6),
        },
        "probability_of_profit": round(probability_of_profit, 4),
        "probability_itm": round(prob_itm, 4),
        "break_even": round(break_even, 2),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 5. Options Flow
# ---------------------------------------------------------------------------

def get_options_flow(symbol):
    """Aggregate real-time options flow for a symbol.

    Fetches the nearest-expiration chain for both calls and puts and
    computes put/call ratio, net premium, and implied move.

    Args:
        symbol: Ticker symbol.

    Returns:
        dict with call_volume, put_volume, put_call_ratio, net_premium,
        implied_move_pct, flow details, and a second-precision timestamp.
    """
    timestamp = _now_iso()

    conid = search_contract(symbol)
    if not conid:
        return {"error": f"Could not resolve symbol {symbol}", "timestamp": timestamp}

    # Current underlying price
    snapshots = get_market_snapshot([conid])
    underlying_price = None
    if snapshots and len(snapshots) > 0:
        underlying_price = _safe_float(snapshots[0].get("31"))

    # Get nearest expiration
    info = get_options_info(conid)
    if not info:
        return {
            "symbol": symbol,
            "conid": conid,
            "underlying_price": underlying_price,
            "error": "No options data available",
            "timestamp": timestamp,
        }

    nearest_month = None
    if isinstance(info, dict):
        months = info.get("months", [])
        if months:
            nearest_month = months[0]
    elif isinstance(info, list) and len(info) > 0:
        nearest_month = info[0].get("month")

    if not nearest_month:
        return {
            "symbol": symbol,
            "conid": conid,
            "underlying_price": underlying_price,
            "error": "No expiration months found",
            "timestamp": timestamp,
        }

    call_volume = 0
    put_volume = 0
    call_premium = 0.0
    put_premium = 0.0
    flow_details = []

    for r in ["C", "P"]:
        contracts = get_option_contracts(conid, month=nearest_month, right=r)
        if not contracts or not isinstance(contracts, list):
            continue

        option_conids = []
        meta_map = {}
        for contract in contracts:
            opt_conid = contract.get("conid")
            if opt_conid is None:
                continue
            option_conids.append(opt_conid)
            meta_map[int(opt_conid)] = {
                "strike": _safe_float(contract.get("strike")),
                "expiration": contract.get("maturityDate") or nearest_month,
            }

        batch_size = 50
        for i in range(0, len(option_conids), batch_size):
            batch = option_conids[i:i + batch_size]
            snaps = get_market_snapshot(batch)
            if not snaps:
                continue

            for snap in snaps:
                snap_conid = snap.get("conid") or snap.get("conidEx")
                if snap_conid is None:
                    continue

                vol = _safe_int(snap.get("87")) or 0
                last = _safe_float(snap.get("31")) or 0.0
                meta = meta_map.get(int(snap_conid), {})

                premium = vol * last * 100  # per-contract multiplier

                if r == "C":
                    call_volume += vol
                    call_premium += premium
                else:
                    put_volume += vol
                    put_premium += premium

                if vol > 0:
                    flow_details.append({
                        "conid": snap_conid,
                        "right": r,
                        "strike": meta.get("strike"),
                        "expiration": meta.get("expiration"),
                        "volume": vol,
                        "last_price": last,
                        "premium": round(premium, 2),
                        "timestamp": _now_iso(),
                    })

    total_volume = call_volume + put_volume
    put_call_ratio = round(put_volume / call_volume, 4) if call_volume > 0 else None
    net_premium = round(call_premium - put_premium, 2)

    # Implied move: use ATM straddle price as a proxy
    implied_move_pct = None
    if underlying_price and underlying_price > 0:
        atm_call_premium = _find_atm_premium(flow_details, "C", underlying_price)
        atm_put_premium = _find_atm_premium(flow_details, "P", underlying_price)
        straddle_price = (atm_call_premium or 0.0) + (atm_put_premium or 0.0)
        if straddle_price > 0:
            implied_move_pct = round((straddle_price / underlying_price) * 100, 2)

    # Sort flow by volume descending
    flow_details.sort(key=lambda f: f.get("volume", 0), reverse=True)

    return {
        "symbol": symbol,
        "conid": conid,
        "underlying_price": underlying_price,
        "expiration": nearest_month,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_volume": total_volume,
        "put_call_ratio": put_call_ratio,
        "call_premium": round(call_premium, 2),
        "put_premium": round(put_premium, 2),
        "net_premium": net_premium,
        "implied_move_pct": implied_move_pct,
        "flow": flow_details[:50],  # Top 50 by volume
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 6. Strategy Builder
# ---------------------------------------------------------------------------

SUPPORTED_STRATEGIES = [
    "covered_call",
    "protective_put",
    "iron_condor",
    "bull_call_spread",
    "bear_put_spread",
    "straddle",
    "strangle",
]


def build_strategy(symbol, strategy_type, params):
    """Construct a multi-leg options strategy with P/L analytics.

    Args:
        symbol: Ticker symbol.
        strategy_type: One of SUPPORTED_STRATEGIES.
        params: dict with strategy-specific keys:
            - expiration: Expiration date "YYYY-MM-DD" (required for all).
            - implied_vol: Annualized IV as decimal (required for all).
            - strike / strike_call / strike_put: Strike prices.
            - strike_long_put / strike_short_put / strike_short_call /
              strike_long_call: For iron condor.
            - current_price: Override underlying price. If omitted, fetched live.

    Returns:
        dict with legs, max_profit, max_loss, break_even (list), pop
        (probability of profit), and a second-precision timestamp.
    """
    timestamp = _now_iso()

    if strategy_type not in SUPPORTED_STRATEGIES:
        return {
            "error": f"Unsupported strategy: {strategy_type}",
            "supported": SUPPORTED_STRATEGIES,
            "timestamp": timestamp,
        }

    # Resolve underlying price
    current_price = params.get("current_price")
    if current_price is None:
        conid = search_contract(symbol)
        if conid:
            snaps = get_market_snapshot([conid])
            if snaps and len(snaps) > 0:
                current_price = _safe_float(snaps[0].get("31"))
    if current_price is None:
        return {"error": "Cannot determine underlying price", "timestamp": timestamp}

    s = float(current_price)
    expiration = params.get("expiration")
    iv = float(params.get("implied_vol", 0.30))

    if not expiration:
        return {"error": "expiration is required in params", "timestamp": timestamp}

    builder = _STRATEGY_BUILDERS.get(strategy_type)
    if builder is None:
        return {"error": f"No builder for {strategy_type}", "timestamp": timestamp}

    result = builder(symbol, s, expiration, iv, params)
    result["symbol"] = symbol
    result["strategy_type"] = strategy_type
    result["underlying_price"] = s
    result["timestamp"] = timestamp
    return result


# ---------------------------------------------------------------------------
# Strategy builders (private)
# ---------------------------------------------------------------------------

def _build_covered_call(symbol, s, expiration, iv, params):
    """Long 100 shares + short 1 call."""
    strike = float(params.get("strike", round(s * 1.05, 2)))
    call = _price_option(s, strike, expiration, "C", iv)

    max_profit = round((strike - s + call["price"]) * 100, 2)
    max_loss = round((s - call["price"]) * 100, 2)
    break_even = round(s - call["price"], 2)

    return {
        "legs": [
            {"type": "stock", "action": "BUY", "quantity": 100, "price": s},
            {"type": "option", "action": "SELL", "right": "C", "strike": strike,
             "expiration": expiration, "price": call["price"], "greeks": call["greeks"]},
        ],
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even],
        "probability_of_profit": call["prob_otm"],
    }


def _build_protective_put(symbol, s, expiration, iv, params):
    """Long 100 shares + long 1 put."""
    strike = float(params.get("strike", round(s * 0.95, 2)))
    put = _price_option(s, strike, expiration, "P", iv)

    max_profit = None  # Unlimited upside
    max_loss = round((s - strike + put["price"]) * 100, 2)
    break_even = round(s + put["price"], 2)

    return {
        "legs": [
            {"type": "stock", "action": "BUY", "quantity": 100, "price": s},
            {"type": "option", "action": "BUY", "right": "P", "strike": strike,
             "expiration": expiration, "price": put["price"], "greeks": put["greeks"]},
        ],
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even],
        "probability_of_profit": put["prob_otm"],
    }


def _build_iron_condor(symbol, s, expiration, iv, params):
    """Short put spread + short call spread (4 legs)."""
    long_put = float(params.get("strike_long_put", round(s * 0.90, 2)))
    short_put = float(params.get("strike_short_put", round(s * 0.95, 2)))
    short_call = float(params.get("strike_short_call", round(s * 1.05, 2)))
    long_call = float(params.get("strike_long_call", round(s * 1.10, 2)))

    lp = _price_option(s, long_put, expiration, "P", iv)
    sp = _price_option(s, short_put, expiration, "P", iv)
    sc = _price_option(s, short_call, expiration, "C", iv)
    lc = _price_option(s, long_call, expiration, "C", iv)

    net_credit = round(sp["price"] - lp["price"] + sc["price"] - lc["price"], 4)
    put_spread_width = short_put - long_put
    call_spread_width = long_call - short_call
    max_spread_width = max(put_spread_width, call_spread_width)

    max_profit = round(net_credit * 100, 2)
    max_loss = round((max_spread_width - net_credit) * 100, 2)
    break_even_lower = round(short_put - net_credit, 2)
    break_even_upper = round(short_call + net_credit, 2)

    # Probability of profit: probability price stays between the break-evens
    # N(d2) gives P(S_T > K), so P(lower < S_T < upper) = N(d2_lower) - N(d2_upper)
    t = _years_to_expiry(expiration)
    d2_lower = _bs_d1(s, break_even_lower, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    d2_upper = _bs_d1(s, break_even_upper, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    pop = round(_norm_cdf(d2_lower) - _norm_cdf(d2_upper), 4)

    return {
        "legs": [
            {"type": "option", "action": "BUY", "right": "P", "strike": long_put,
             "expiration": expiration, "price": lp["price"], "greeks": lp["greeks"]},
            {"type": "option", "action": "SELL", "right": "P", "strike": short_put,
             "expiration": expiration, "price": sp["price"], "greeks": sp["greeks"]},
            {"type": "option", "action": "SELL", "right": "C", "strike": short_call,
             "expiration": expiration, "price": sc["price"], "greeks": sc["greeks"]},
            {"type": "option", "action": "BUY", "right": "C", "strike": long_call,
             "expiration": expiration, "price": lc["price"], "greeks": lc["greeks"]},
        ],
        "net_credit": round(net_credit, 4),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even_lower, break_even_upper],
        "probability_of_profit": pop,
    }


def _build_bull_call_spread(symbol, s, expiration, iv, params):
    """Buy lower-strike call, sell higher-strike call."""
    strike_buy = float(params.get("strike", round(s, 2)))
    strike_sell = float(params.get("strike_call", round(s * 1.05, 2)))

    long_call = _price_option(s, strike_buy, expiration, "C", iv)
    short_call = _price_option(s, strike_sell, expiration, "C", iv)

    net_debit = round(long_call["price"] - short_call["price"], 4)
    max_profit = round((strike_sell - strike_buy - net_debit) * 100, 2)
    max_loss = round(net_debit * 100, 2)
    break_even = round(strike_buy + net_debit, 2)

    t = _years_to_expiry(expiration)
    d2_be = _bs_d1(s, break_even, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    pop = round(_norm_cdf(d2_be), 4)

    return {
        "legs": [
            {"type": "option", "action": "BUY", "right": "C", "strike": strike_buy,
             "expiration": expiration, "price": long_call["price"], "greeks": long_call["greeks"]},
            {"type": "option", "action": "SELL", "right": "C", "strike": strike_sell,
             "expiration": expiration, "price": short_call["price"], "greeks": short_call["greeks"]},
        ],
        "net_debit": round(net_debit, 4),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even],
        "probability_of_profit": pop,
    }


def _build_bear_put_spread(symbol, s, expiration, iv, params):
    """Buy higher-strike put, sell lower-strike put."""
    strike_buy = float(params.get("strike", round(s, 2)))
    strike_sell = float(params.get("strike_put", round(s * 0.95, 2)))

    long_put = _price_option(s, strike_buy, expiration, "P", iv)
    short_put = _price_option(s, strike_sell, expiration, "P", iv)

    net_debit = round(long_put["price"] - short_put["price"], 4)
    max_profit = round((strike_buy - strike_sell - net_debit) * 100, 2)
    max_loss = round(net_debit * 100, 2)
    break_even = round(strike_buy - net_debit, 2)

    t = _years_to_expiry(expiration)
    d2_be = _bs_d1(s, break_even, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    pop = round(_norm_cdf(-d2_be), 4)

    return {
        "legs": [
            {"type": "option", "action": "BUY", "right": "P", "strike": strike_buy,
             "expiration": expiration, "price": long_put["price"], "greeks": long_put["greeks"]},
            {"type": "option", "action": "SELL", "right": "P", "strike": strike_sell,
             "expiration": expiration, "price": short_put["price"], "greeks": short_put["greeks"]},
        ],
        "net_debit": round(net_debit, 4),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even],
        "probability_of_profit": pop,
    }


def _build_straddle(symbol, s, expiration, iv, params):
    """Long call + long put at the same ATM strike."""
    strike = float(params.get("strike", round(s, 2)))

    call = _price_option(s, strike, expiration, "C", iv)
    put = _price_option(s, strike, expiration, "P", iv)

    total_premium = round(call["price"] + put["price"], 4)
    max_profit = None  # Unlimited
    max_loss = round(total_premium * 100, 2)
    break_even_lower = round(strike - total_premium, 2)
    break_even_upper = round(strike + total_premium, 2)

    # Probability price moves outside the break-even range
    # P(between) = N(d2_lower) - N(d2_upper), so P(outside) = 1 - P(between)
    t = _years_to_expiry(expiration)
    d2_lower = _bs_d1(s, break_even_lower, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    d2_upper = _bs_d1(s, break_even_upper, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    pop = round(1.0 - (_norm_cdf(d2_lower) - _norm_cdf(d2_upper)), 4)

    return {
        "legs": [
            {"type": "option", "action": "BUY", "right": "C", "strike": strike,
             "expiration": expiration, "price": call["price"], "greeks": call["greeks"]},
            {"type": "option", "action": "BUY", "right": "P", "strike": strike,
             "expiration": expiration, "price": put["price"], "greeks": put["greeks"]},
        ],
        "total_premium": round(total_premium, 4),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even_lower, break_even_upper],
        "probability_of_profit": pop,
    }


def _build_strangle(symbol, s, expiration, iv, params):
    """Long OTM call + long OTM put at different strikes."""
    strike_call = float(params.get("strike_call", round(s * 1.05, 2)))
    strike_put = float(params.get("strike_put", round(s * 0.95, 2)))

    call = _price_option(s, strike_call, expiration, "C", iv)
    put = _price_option(s, strike_put, expiration, "P", iv)

    total_premium = round(call["price"] + put["price"], 4)
    max_profit = None  # Unlimited
    max_loss = round(total_premium * 100, 2)
    break_even_lower = round(strike_put - total_premium, 2)
    break_even_upper = round(strike_call + total_premium, 2)

    # Probability price moves outside the break-even range
    t = _years_to_expiry(expiration)
    d2_lower = _bs_d1(s, break_even_lower, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    d2_upper = _bs_d1(s, break_even_upper, t, RISK_FREE_RATE, iv) - iv * math.sqrt(t)
    pop = round(1.0 - (_norm_cdf(d2_lower) - _norm_cdf(d2_upper)), 4)

    return {
        "legs": [
            {"type": "option", "action": "BUY", "right": "C", "strike": strike_call,
             "expiration": expiration, "price": call["price"], "greeks": call["greeks"]},
            {"type": "option", "action": "BUY", "right": "P", "strike": strike_put,
             "expiration": expiration, "price": put["price"], "greeks": put["greeks"]},
        ],
        "total_premium": round(total_premium, 4),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "break_even": [break_even_lower, break_even_upper],
        "probability_of_profit": pop,
    }


_STRATEGY_BUILDERS = {
    "covered_call": _build_covered_call,
    "protective_put": _build_protective_put,
    "iron_condor": _build_iron_condor,
    "bull_call_spread": _build_bull_call_spread,
    "bear_put_spread": _build_bear_put_spread,
    "straddle": _build_straddle,
    "strangle": _build_strangle,
}


# ---------------------------------------------------------------------------
# Black-Scholes helpers
# ---------------------------------------------------------------------------

def _bs_d1(s, k, t, r, sigma):
    """Compute Black-Scholes d1 parameter."""
    if k <= 0 or t <= 0 or sigma <= 0:
        return 0.0
    return (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))


def _norm_cdf(x):
    """Standard normal cumulative distribution function.

    Uses the math.erf implementation for accuracy without scipy.
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _price_option(s, k, expiration, right, iv):
    """Price a single option leg and return price + Greeks.

    Args:
        s: Current underlying price.
        k: Strike price.
        expiration: Expiration date as "YYYY-MM-DD".
        right: "C" or "P".
        iv: Implied volatility (annualized decimal).

    Returns:
        dict with price, greeks, prob_itm, prob_otm.
    """
    t = _years_to_expiry(expiration)
    r = RISK_FREE_RATE
    is_call = right.upper() == "C"

    d1 = _bs_d1(s, k, t, r, iv)
    d2 = d1 - iv * math.sqrt(t)
    sqrt_t = math.sqrt(t)
    discount = math.exp(-r * t)

    nd1 = _norm_cdf(d1)
    nd2 = _norm_cdf(d2)
    nprime_d1 = _norm_pdf(d1)

    if is_call:
        price = s * nd1 - k * discount * nd2
        delta = nd1
        prob_itm = nd2
    else:
        price = k * discount * _norm_cdf(-d2) - s * _norm_cdf(-d1)
        delta = nd1 - 1.0
        prob_itm = _norm_cdf(-d2)

    gamma = nprime_d1 / (s * iv * sqrt_t) if (s * iv * sqrt_t) > 0 else 0.0
    theta = (-(s * nprime_d1 * iv) / (2.0 * sqrt_t)
             - r * k * discount * (nd2 if is_call else -_norm_cdf(-d2))) / 365.0
    vega = s * nprime_d1 * sqrt_t / 100.0

    return {
        "price": round(price, 4),
        "greeks": {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta, 6),
            "vega": round(vega, 6),
        },
        "prob_itm": round(prob_itm, 4),
        "prob_otm": round(1.0 - prob_itm, 4),
    }


def _years_to_expiry(expiration):
    """Convert an expiration date string to fractional years from now."""
    if isinstance(expiration, str):
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        exp_dt = expiration
    now = datetime.now(timezone.utc)
    days = max((exp_dt - now).total_seconds() / 86400, 0.001)
    return days / 365.0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _safe_float(value):
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _find_atm_premium(flow_details, right, underlying_price):
    """Find the premium of the ATM option from flow details.

    Selects the contract whose strike is closest to the underlying price.
    """
    candidates = [f for f in flow_details if f.get("right") == right and f.get("strike") is not None]
    if not candidates:
        return None

    atm = min(candidates, key=lambda f: abs(f["strike"] - underlying_price))
    return atm.get("last_price")
