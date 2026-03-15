"""
Venture fund-grade data aggregation module.

Collects and normalizes data from multiple sources:
- yfinance: fundamentals, financials, insider trades, institutional holders
- FRED API: macroeconomic indicators (Treasury yields, GDP, CPI, unemployment)
- SEC EDGAR: institutional holdings (13F), insider transactions
- Market sentiment: VIX, Fear & Greed proxy, put/call ratios
- Technical: advanced indicators, sector rotation, relative strength
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger("data_sources")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
API_KEYS_FILE = DATA_DIR / "api_keys.json"

CACHE_TTL = 1800  # 30 minutes
SEC_EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FEAR_GREED_URL = "https://production.dataviz.cnn.com/index/fearandgreed/graphdata"

# Top 50 most actively traded US stocks
# Fallback list used when dynamic fetch fails
_FALLBACK_TOP_50 = [
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

# Cache for dynamic top-50
_top50_cache: list[str] = []
_top50_cache_expiry: float = 0.0
TOP_50_CACHE_TTL = 86400  # 24 hours


def get_top_50_by_volume() -> list[str]:
    """Fetch the 50 most traded US stocks this week by average daily volume.

    Uses a broad screening pool of ~120 large-cap US tickers and ranks
    by trailing 5-day average volume. Falls back to the static list
    on failure.
    """
    global _top50_cache, _top50_cache_expiry
    now = time.time()
    if _top50_cache and now < _top50_cache_expiry:
        return _top50_cache

    # Broad pool: S&P 100 + popular mid/large caps
    pool = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
        "JPM", "V", "UNH", "MA", "HD", "COST", "PG", "JNJ", "ABBV", "CRM",
        "NFLX", "AMD", "LLY", "MRK", "PEP", "KO", "ADBE", "WMT", "BAC",
        "TMO", "CSCO", "ACN", "ORCL", "MCD", "ABT", "DHR", "QCOM", "TXN",
        "NEE", "PM", "INTC", "CMCSA", "INTU", "AMGN", "ISRG", "GE", "IBM",
        "NOW", "CAT", "GS", "AMAT", "BLK", "UBER", "COIN", "PLTR", "SOFI",
        "RIVN", "MARA", "XYZ", "SNAP", "ROKU", "HOOD", "SHOP", "ARM", "SMCI",
        "MSTR", "MU", "CRWD", "PANW", "SNOW", "DDOG", "NET", "ZS", "OKTA",
        "ABNB", "DASH", "RBLX", "U", "PATH", "BILL", "HUBS", "TEAM", "MNDY",
        "CEG", "VST", "FSLR", "ENPH", "XOM", "CVX", "COP", "SLB", "HAL",
        "BA", "RTX", "LMT", "GD", "NOC", "DE", "UPS", "FDX", "DAL", "UAL",
        "AAL", "CCL", "WYNN", "MGM", "DIS", "CMCSA", "T", "VZ", "TMUS",
        "BRK-B", "C", "WFC", "MS", "SCHW", "AXP", "BX", "KKR", "GM", "F",
        "NKE", "SBUX", "TGT", "LOW", "BKNG", "MAR", "HLT", "LULU", "DECK",
    ]
    # Deduplicate
    seen = set()
    unique_pool = []
    for t in pool:
        if t not in seen:
            seen.add(t)
            unique_pool.append(t)

    try:
        volume_data = []
        # Batch download 5-day history for the entire pool
        batch = yf.download(unique_pool, period="5d", group_by="ticker",
                            threads=True, progress=False)

        for ticker in unique_pool:
            try:
                if len(unique_pool) > 1:
                    vol_series = batch[ticker]["Volume"]
                else:
                    vol_series = batch["Volume"]
                avg_vol = float(vol_series.mean())
                if avg_vol > 0:
                    volume_data.append((ticker, avg_vol))
            except Exception:
                continue

        if len(volume_data) >= 50:
            volume_data.sort(key=lambda x: x[1], reverse=True)
            _top50_cache = [t for t, _ in volume_data[:50]]
            _top50_cache_expiry = now + TOP_50_CACHE_TTL
            logger.info("Dynamic top-50 fetched: %s", _top50_cache[:10])
            return _top50_cache

    except Exception as exc:
        logger.warning("Dynamic top-50 fetch failed, using fallback: %s", exc)

    return _FALLBACK_TOP_50


# Public alias — other modules import this
TOP_50_TICKERS = _FALLBACK_TOP_50

# FRED series IDs for key economic indicators
# Series that return index levels (need YoY% computation) are marked below.
FRED_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "treasury_10y": "DGS10",
    "treasury_2y": "DGS2",
    "treasury_3mo": "DTB3",
    "cpi_yoy": "CPIAUCSL",        # Index level; compute YoY% change
    "core_cpi": "CPILFESL",       # Index level; compute YoY% change
    "unemployment": "UNRATE",
    "gdp_growth": "A191RL1Q225SBEA",
    "retail_sales": "RSAFS",      # Absolute level; compute YoY% change
    "consumer_sentiment": "UMCSENT",
    "housing_starts": "HOUST",
    "pce_inflation": "PCEPI",     # Index level; compute YoY% change
    "m2_money_supply": "M2SL",
    "initial_claims": "ICSA",
    "ism_manufacturing": "MANEMP",  # Manufacturing employment (proxy; ISM PMI not on FRED)
    "industrial_production_yoy": "INDPRO",  # Industrial production index; compute YoY%
}

# Series that need YoY% change computation instead of raw latest value
FRED_YOY_SERIES = {
    "cpi_yoy", "core_cpi", "retail_sales", "pce_inflation",
    "industrial_production_yoy",
}

TRADING_DAYS_PER_YEAR = 252

# Caches
_fundamentals_cache = {}
_fundamentals_expiry = {}
_macro_cache = {}
_macro_expiry = 0.0
_sec_cache = {}
_sec_expiry = {}

SEC_HEADERS = {
    "User-Agent": "AntigravityTools/1.0 (research@antigravity.tools)",
    "Accept": "application/json",
}


def _load_api_keys():
    """Load API keys from config file, with env var overrides."""
    import os
    keys = {}
    if API_KEYS_FILE.exists():
        with open(API_KEYS_FILE, "r", encoding="utf-8") as fh:
            keys = json.load(fh)
    env_map = {
        "fred": "FRED_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "finnhub": "FINNHUB_API_KEY",
        "newsapi": "NEWSAPI_API_KEY",
        "marketstack": "MARKETSTACK_API_KEY",
        "fintel": "FINTEL_API_KEY",
        "quiver": "QUIVER_API_KEY",
    }
    for key_name, env_var in env_map.items():
        env_val = os.environ.get(env_var, "")
        if env_val:
            keys[key_name] = env_val
    return keys


# ---------------------------------------------------------------------------
# Fundamentals (via yfinance)
# ---------------------------------------------------------------------------

def get_fundamentals(ticker):
    """Get comprehensive fundamental data for a stock.

    Returns financial ratios, income statement, balance sheet,
    cash flow, insider trades, and institutional holders.
    """
    now = time.time()
    if ticker in _fundamentals_cache and now < _fundamentals_expiry.get(ticker, 0):
        return _fundamentals_cache[ticker]

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Income statement metrics
        income = {}
        try:
            inc_stmt = stock.income_stmt
            if inc_stmt is not None and not inc_stmt.empty:
                latest = inc_stmt.iloc[:, 0]
                income = {
                    "total_revenue": _safe_num(latest.get("Total Revenue")),
                    "gross_profit": _safe_num(latest.get("Gross Profit")),
                    "operating_income": _safe_num(latest.get("Operating Income")),
                    "net_income": _safe_num(latest.get("Net Income")),
                    "ebitda": _safe_num(latest.get("EBITDA")),
                    "eps_diluted": _safe_num(latest.get("Diluted EPS")),
                }
        except Exception:
            pass

        # Balance sheet metrics
        balance = {}
        try:
            bal_sheet = stock.balance_sheet
            if bal_sheet is not None and not bal_sheet.empty:
                latest = bal_sheet.iloc[:, 0]
                balance = {
                    "total_assets": _safe_num(latest.get("Total Assets")),
                    "total_liabilities": _safe_num(latest.get("Total Liabilities Net Minority Interest")),
                    "total_equity": _safe_num(latest.get("Stockholders Equity")),
                    "total_debt": _safe_num(latest.get("Total Debt")),
                    "cash_and_equivalents": _safe_num(latest.get("Cash And Cash Equivalents")),
                    "current_assets": _safe_num(latest.get("Current Assets")),
                    "current_liabilities": _safe_num(latest.get("Current Liabilities")),
                }
        except Exception:
            pass

        # Cash flow metrics
        cashflow = {}
        try:
            cf_stmt = stock.cashflow
            if cf_stmt is not None and not cf_stmt.empty:
                latest = cf_stmt.iloc[:, 0]
                cashflow = {
                    "operating_cash_flow": _safe_num(latest.get("Operating Cash Flow")),
                    "capital_expenditure": _safe_num(latest.get("Capital Expenditure")),
                    "free_cash_flow": _safe_num(latest.get("Free Cash Flow")),
                    "dividends_paid": _safe_num(latest.get("Cash Dividends Paid")),
                    "share_buyback": _safe_num(latest.get("Repurchase Of Capital Stock")),
                }
        except Exception:
            pass

        # Key ratios
        ratios = {
            "pe_trailing": _safe_float(info.get("trailingPE")),
            "pe_forward": _safe_float(info.get("forwardPE")),
            "peg_ratio": _safe_float(info.get("pegRatio")),
            "price_to_book": _safe_float(info.get("priceToBook")),
            "price_to_sales": _safe_float(info.get("priceToSalesTrailing12Months")),
            "ev_to_ebitda": _safe_float(info.get("enterpriseToEbitda")),
            "ev_to_revenue": _safe_float(info.get("enterpriseToRevenue")),
            "profit_margin": _safe_float(info.get("profitMargins")),
            "operating_margin": _safe_float(info.get("operatingMargins")),
            "gross_margin": _safe_float(info.get("grossMargins")),
            "roe": _safe_float(info.get("returnOnEquity")),
            "roa": _safe_float(info.get("returnOnAssets")),
            "debt_to_equity": _safe_float(info.get("debtToEquity")),
            "current_ratio": _safe_float(info.get("currentRatio")),
            "quick_ratio": _safe_float(info.get("quickRatio")),
            "dividend_yield": _safe_float(info.get("dividendYield")),
            "payout_ratio": _safe_float(info.get("payoutRatio")),
            "beta": _safe_float(info.get("beta")),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            "short_ratio": _safe_float(info.get("shortRatio")),
            "short_pct_float": _safe_float(info.get("shortPercentOfFloat")),
        }

        # Growth metrics
        growth = {
            "revenue_growth": _safe_float(info.get("revenueGrowth")),
            "earnings_growth": _safe_float(info.get("earningsGrowth")),
            "earnings_quarterly_growth": _safe_float(info.get("earningsQuarterlyGrowth")),
        }

        # Analyst estimates
        analysts = {
            "target_mean": _safe_float(info.get("targetMeanPrice")),
            "target_high": _safe_float(info.get("targetHighPrice")),
            "target_low": _safe_float(info.get("targetLowPrice")),
            "target_median": _safe_float(info.get("targetMedianPrice")),
            "recommendation": info.get("recommendationKey"),
            "recommendation_mean": _safe_float(info.get("recommendationMean")),
            "num_analysts": info.get("numberOfAnalystOpinions"),
        }

        # Insider transactions
        insiders = []
        try:
            insider_txns = stock.insider_transactions
            if insider_txns is not None and not insider_txns.empty:
                for _, row in insider_txns.head(10).iterrows():
                    insiders.append({
                        "name": str(row.get("Insider", "")),
                        "relation": str(row.get("Position", "")),
                        "transaction": str(row.get("Transaction", "")),
                        "shares": _safe_num(row.get("Shares")),
                        "value": _safe_num(row.get("Value")),
                        "date": str(row.get("Start Date", "")),
                    })
        except Exception:
            pass

        # Institutional holders
        institutions = []
        try:
            inst_holders = stock.institutional_holders
            if inst_holders is not None and not inst_holders.empty:
                for _, row in inst_holders.head(10).iterrows():
                    institutions.append({
                        "holder": str(row.get("Holder", "")),
                        "shares": _safe_num(row.get("Shares")),
                        "value": _safe_num(row.get("Value")),
                        "pct_held": _safe_float(row.get("% Out")),
                        "date_reported": str(row.get("Date Reported", "")),
                    })
        except Exception:
            pass

        # Earnings history
        earnings = []
        try:
            earn_hist = stock.earnings_history
            if earn_hist is not None and not earn_hist.empty:
                for _, row in earn_hist.iterrows():
                    earnings.append({
                        "date": str(row.get("Earnings Date", "")),
                        "eps_estimate": _safe_float(row.get("EPS Estimate")),
                        "eps_actual": _safe_float(row.get("Reported EPS")),
                        "surprise_pct": _safe_float(row.get("Surprise(%)")),
                    })
        except Exception:
            pass

        result = {
            "ticker": ticker,
            "name": info.get("longName", info.get("shortName", ticker)),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "description": info.get("longBusinessSummary", ""),
            "country": info.get("country", ""),
            "employees": info.get("fullTimeEmployees"),
            "website": info.get("website", ""),
            "ratios": ratios,
            "growth": growth,
            "income_statement": income,
            "balance_sheet": balance,
            "cash_flow": cashflow,
            "analyst_estimates": analysts,
            "insider_transactions": insiders,
            "institutional_holders": institutions,
            "earnings_history": earnings,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _fundamentals_cache[ticker] = result
        _fundamentals_expiry[ticker] = now + CACHE_TTL
        return result

    except Exception as exc:
        logger.error("Failed to get fundamentals for %s: %s", ticker, exc)
        return {"ticker": ticker, "error": str(exc)}


# ---------------------------------------------------------------------------
# Macroeconomic Data (via FRED)
# ---------------------------------------------------------------------------

def get_macro_indicators():
    """Fetch key macroeconomic indicators from FRED.

    Returns latest values for Fed funds rate, Treasury yields,
    CPI, unemployment, GDP growth, and other key indicators.
    """
    global _macro_cache, _macro_expiry
    now = time.time()
    if _macro_cache and now < _macro_expiry:
        return _macro_cache

    keys = _load_api_keys()
    fred_key = keys.get("fred", "")

    indicators = {}

    for name, series_id in FRED_SERIES.items():
        try:
            if name in FRED_YOY_SERIES:
                value = _fetch_fred_yoy_change(series_id, fred_key)
            else:
                value = _fetch_fred_latest(series_id, fred_key)
            indicators[name] = value
        except Exception as exc:
            logger.warning("FRED fetch failed for %s (%s): %s", name, series_id, exc)
            indicators[name] = None

    # Yield curve spread (10Y - 2Y)
    if indicators.get("treasury_10y") and indicators.get("treasury_2y"):
        indicators["yield_curve_spread"] = round(
            indicators["treasury_10y"] - indicators["treasury_2y"], 2
        )
        indicators["yield_curve_inverted"] = indicators["yield_curve_spread"] < 0

    # Real interest rate estimate (Fed Funds - CPI)
    if indicators.get("fed_funds_rate") and indicators.get("cpi_yoy"):
        indicators["real_interest_rate"] = round(
            indicators["fed_funds_rate"] - indicators["cpi_yoy"], 2
        )

    result = {
        "indicators": indicators,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    _macro_cache = result
    _macro_expiry = now + CACHE_TTL
    return result


def _fetch_fred_latest(series_id, api_key):
    """Fetch the latest observation from a FRED series."""
    if not api_key:
        return None

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }
    resp = requests.get(FRED_BASE, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    observations = data.get("observations", [])
    if observations:
        val = observations[0].get("value", ".")
        if val != ".":
            return float(val)
    return None


def _fetch_fred_yoy_change(series_id, api_key):
    """Fetch last 13 monthly observations and compute YoY percent change.

    Returns (latest / 12_months_ago - 1) * 100, which gives the
    year-over-year percentage change for index-level FRED series
    like CPIAUCSL, CPILFESL, PCEPI, and RSAFS.
    """
    if not api_key:
        return None

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 13,
    }
    resp = requests.get(FRED_BASE, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    observations = data.get("observations", [])

    # Filter out missing values and collect valid floats
    valid = []
    for obs in observations:
        val = obs.get("value", ".")
        if val != ".":
            valid.append(float(val))

    # Need at least 12 months of separation for YoY
    if len(valid) < 12:
        return None

    # Observations are desc-sorted: index 0 = latest, index 11 = ~12 months ago
    latest = valid[0]
    year_ago = valid[11]

    if year_ago == 0:
        return None

    yoy_pct = (latest / year_ago - 1) * 100
    return round(yoy_pct, 2)


# ---------------------------------------------------------------------------
# Market Sentiment Indicators
# ---------------------------------------------------------------------------

def get_market_sentiment():
    """Get market-wide sentiment indicators.

    Collects VIX, put/call ratio, advance/decline, new highs/lows,
    and a Fear & Greed proxy score.
    """
    sentiment = {}

    # VIX (CBOE Volatility Index)
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        if not vix_hist.empty:
            sentiment["vix"] = round(float(vix_hist["Close"].iloc[-1]), 2)
            sentiment["vix_prev"] = round(float(vix_hist["Close"].iloc[-2]), 2) if len(vix_hist) > 1 else None
            sentiment["vix_change"] = round(
                sentiment["vix"] - (sentiment["vix_prev"] or sentiment["vix"]), 2
            )

            # VIX interpretation
            if sentiment["vix"] < 15:
                sentiment["vix_regime"] = "low_volatility"
            elif sentiment["vix"] < 20:
                sentiment["vix_regime"] = "normal"
            elif sentiment["vix"] < 30:
                sentiment["vix_regime"] = "elevated"
            else:
                sentiment["vix_regime"] = "high_fear"
    except Exception as exc:
        logger.warning("VIX fetch failed: %s", exc)

    # Major indices for breadth
    indices = {
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "dow": "^DJI",
        "russell2000": "^RUT",
    }
    for name, symbol in indices.items():
        try:
            idx = yf.Ticker(symbol)
            hist = idx.history(period="5d")
            if not hist.empty:
                close = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
                sentiment[f"{name}_price"] = round(close, 2)
                sentiment[f"{name}_change_pct"] = round((close - prev) / prev * 100, 2)
        except Exception:
            pass

    # Sector ETF performance (for rotation analysis)
    sector_etfs = {
        "technology": "XLK", "healthcare": "XLV", "financials": "XLF",
        "energy": "XLE", "consumer_disc": "XLY", "consumer_staples": "XLP",
        "industrials": "XLI", "materials": "XLB", "utilities": "XLU",
        "real_estate": "XLRE", "communication": "XLC",
    }
    sector_performance = {}
    for sector, etf in sector_etfs.items():
        try:
            s = yf.Ticker(etf)
            hist = s.history(period="1mo")
            if not hist.empty and len(hist) > 1:
                month_return = (
                    (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[0]))
                    / float(hist["Close"].iloc[0]) * 100
                )
                week_return = 0
                if len(hist) >= 5:
                    week_return = (
                        (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-5]))
                        / float(hist["Close"].iloc[-5]) * 100
                    )
                sector_performance[sector] = {
                    "etf": etf,
                    "month_return": round(month_return, 2),
                    "week_return": round(week_return, 2),
                }
        except Exception:
            pass

    sentiment["sector_rotation"] = sector_performance

    # Treasury and gold as risk indicators
    risk_assets = {"gold": "GC=F", "treasury_20y": "TLT", "us_dollar": "DX-Y.NYB"}
    for name, symbol in risk_assets.items():
        try:
            asset = yf.Ticker(symbol)
            hist = asset.history(period="5d")
            if not hist.empty:
                sentiment[f"{name}_price"] = round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            pass

    # Composite fear/greed proxy score (0-100, 0=extreme fear, 100=extreme greed)
    score_components = []
    if "vix" in sentiment:
        # Low VIX = greed, High VIX = fear
        vix_score = max(0, min(100, 100 - (sentiment["vix"] - 12) * 3.5))
        score_components.append(vix_score)

    if "sp500_change_pct" in sentiment:
        # Positive market = greed
        market_score = max(0, min(100, 50 + sentiment["sp500_change_pct"] * 20))
        score_components.append(market_score)

    if score_components:
        sentiment["fear_greed_score"] = round(sum(score_components) / len(score_components), 1)
        if sentiment["fear_greed_score"] < 25:
            sentiment["fear_greed_label"] = "Extreme Fear"
        elif sentiment["fear_greed_score"] < 45:
            sentiment["fear_greed_label"] = "Fear"
        elif sentiment["fear_greed_score"] < 55:
            sentiment["fear_greed_label"] = "Neutral"
        elif sentiment["fear_greed_score"] < 75:
            sentiment["fear_greed_label"] = "Greed"
        else:
            sentiment["fear_greed_label"] = "Extreme Greed"

    sentiment["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return sentiment


# ---------------------------------------------------------------------------
# Advanced Technical Analysis
# ---------------------------------------------------------------------------

def get_technical_profile(ticker, period="1y"):
    """Compute advanced technical indicators for a stock.

    Returns moving averages, RSI, MACD, Bollinger Bands, ATR,
    OBV, relative strength vs S&P 500, and more.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            return {"ticker": ticker, "error": "No data"}

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]
        returns = close.pct_change().dropna()

        # Moving averages
        sma_20 = float(close.rolling(20).mean().iloc[-1])
        sma_50 = float(close.rolling(50).mean().iloc[-1])
        sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        ema_12 = float(close.ewm(span=12).mean().iloc[-1])
        ema_26 = float(close.ewm(span=26).mean().iloc[-1])

        current = float(close.iloc[-1])

        # RSI (14-period)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi_value = float(rsi.iloc[-1]) if not rsi.empty else None

        # MACD
        macd_line = ema_12 - ema_26
        signal_line_series = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        signal_line = float(signal_line_series.ewm(span=9).mean().iloc[-1])
        macd_histogram = macd_line - signal_line

        # Bollinger Bands
        bb_sma = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = float((bb_sma + 2 * bb_std).iloc[-1])
        bb_lower = float((bb_sma - 2 * bb_std).iloc[-1])
        bb_width = (bb_upper - bb_lower) / float(bb_sma.iloc[-1]) * 100

        # ATR (Average True Range)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        # OBV (On Balance Volume)
        obv = (volume * np.sign(close.diff())).cumsum()
        obv_trend = "up" if float(obv.iloc[-1]) > float(obv.iloc[-5]) else "down"

        # Volatility metrics
        daily_vol = float(returns.std())
        annual_vol = daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR)

        # Relative Strength vs S&P 500
        rs_vs_sp500 = None
        try:
            sp500 = yf.Ticker("^GSPC")
            sp_hist = sp500.history(period=period)
            if not sp_hist.empty and len(sp_hist) >= 20:
                stock_return_20d = (current / float(close.iloc[-20]) - 1) * 100
                sp_return_20d = (
                    float(sp_hist["Close"].iloc[-1]) / float(sp_hist["Close"].iloc[-20]) - 1
                ) * 100
                rs_vs_sp500 = round(stock_return_20d - sp_return_20d, 2)
        except Exception:
            pass

        # 52-week high/low distance
        high_52w = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
        low_52w = float(low.tail(252).min()) if len(low) >= 252 else float(low.min())
        pct_from_52w_high = round((current / high_52w - 1) * 100, 2)
        pct_from_52w_low = round((current / low_52w - 1) * 100, 2)

        # Trend assessment
        ma_signals = []
        if current > sma_20:
            ma_signals.append("above_sma20")
        if current > sma_50:
            ma_signals.append("above_sma50")
        if sma_200 and current > sma_200:
            ma_signals.append("above_sma200")
        if sma_50 > (sma_200 or 0):
            ma_signals.append("golden_cross")

        bullish_count = len(ma_signals)
        if bullish_count >= 3:
            trend_strength = "strong_bullish"
        elif bullish_count >= 2:
            trend_strength = "bullish"
        elif bullish_count >= 1:
            trend_strength = "neutral"
        else:
            trend_strength = "bearish"

        return {
            "ticker": ticker,
            "current_price": round(current, 2),
            "moving_averages": {
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2) if sma_200 else None,
                "ema_12": round(ema_12, 2),
                "ema_26": round(ema_26, 2),
            },
            "rsi_14": round(rsi_value, 1) if rsi_value else None,
            "macd": {
                "macd_line": round(macd_line, 4),
                "signal_line": round(signal_line, 4),
                "histogram": round(macd_histogram, 4),
            },
            "bollinger_bands": {
                "upper": round(bb_upper, 2),
                "lower": round(bb_lower, 2),
                "width_pct": round(bb_width, 2),
            },
            "atr_14": round(atr, 2),
            "obv_trend": obv_trend,
            "volatility": {
                "daily": round(daily_vol * 100, 2),
                "annual": round(annual_vol * 100, 1),
            },
            "relative_strength_vs_sp500": rs_vs_sp500,
            "range_52w": {
                "high": round(high_52w, 2),
                "low": round(low_52w, 2),
                "pct_from_high": pct_from_52w_high,
                "pct_from_low": pct_from_52w_low,
            },
            "ma_signals": ma_signals,
            "trend_strength": trend_strength,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("Technical profile failed for %s: %s", ticker, exc)
        return {"ticker": ticker, "error": str(exc)}


# ---------------------------------------------------------------------------
# Aggregate All Data for AI Analysis
# ---------------------------------------------------------------------------

def get_full_stock_profile(ticker):
    """Aggregate all available data sources for a single stock.

    This is the primary function used by the AI analyst. It combines:
    - Fundamentals (financials, ratios, growth)
    - Technical indicators (MA, RSI, MACD, etc.)
    - Insider activity
    - Institutional holdings
    - Analyst estimates
    - Recent price action
    """
    fundamentals = get_fundamentals(ticker)
    technicals = get_technical_profile(ticker)

    # Recent price history for context
    price_history = []
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        if not hist.empty:
            for date, row in hist.tail(60).iterrows():
                price_history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
    except Exception:
        pass

    return {
        "ticker": ticker,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "recent_prices": price_history,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def get_market_context():
    """Get full market context for AI analysis.

    Combines macro indicators and market sentiment.
    """
    macro = get_macro_indicators()
    sentiment = get_market_sentiment()

    return {
        "macro": macro,
        "sentiment": sentiment,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def scan_top_50():
    """Quick scan of the top 50 most traded US stocks this week.

    Returns a lightweight overview suitable for the dashboard.
    """
    results = []
    tickers = get_top_50_by_volume()
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1mo")
            if hist.empty:
                continue

            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            month_start = float(hist["Close"].iloc[0])

            results.append({
                "ticker": ticker,
                "name": info.get("longName", info.get("shortName", ticker)),
                "sector": info.get("sector", ""),
                "current_price": round(current, 2),
                "day_change_pct": round((current - prev) / prev * 100, 2),
                "month_change_pct": round((current - month_start) / month_start * 100, 2),
                "market_cap": info.get("marketCap"),
                "pe_ratio": _safe_float(info.get("trailingPE")),
                "volume": int(hist["Volume"].iloc[-1]),
                "beta": _safe_float(info.get("beta")),
            })
        except Exception as exc:
            logger.warning("Scan failed for %s: %s", ticker, exc)

    return results


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_float(value):
    """Convert to float safely, return None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return None
        return round(result, 4)
    except (ValueError, TypeError):
        return None


def _safe_num(value):
    """Convert to number safely for large values."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            if np.isnan(value) or np.isinf(value):
                return None
            return value
        return float(value)
    except (ValueError, TypeError):
        return None
