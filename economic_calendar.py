"""
Economic calendar and stock event tracking module.

Provides upcoming economic data release dates (FOMC, CPI, NFP, GDP, etc.)
and stock-specific event dates (earnings, dividends, options expirations).
Uses hardcoded 2026 schedules supplemented by live data from FRED and
yfinance where available.
"""
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf

logger = logging.getLogger("calendar")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
API_KEYS_FILE = DATA_DIR / "api_keys.json"

CACHE_TTL = 3600  # 1 hour
FRED_BASE = "https://api.stlouisfed.org/fred"
FRED_RELEASE_DATES = f"{FRED_BASE}/release/dates"

REQUEST_TIMEOUT = 10

# Importance levels
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Event categories
CATEGORY_MONETARY_POLICY = "monetary_policy"
CATEGORY_INFLATION = "inflation"
CATEGORY_EMPLOYMENT = "employment"
CATEGORY_GDP = "gdp"
CATEGORY_CONSUMER = "consumer"
CATEGORY_MANUFACTURING = "manufacturing"
CATEGORY_HOUSING = "housing"
CATEGORY_EARNINGS = "earnings"
CATEGORY_DIVIDEND = "dividend"
CATEGORY_OPTIONS = "options"
CATEGORY_SPLIT = "split"

# ---------------------------------------------------------------------------
# 2026 FOMC Meeting Schedule
# ---------------------------------------------------------------------------
FOMC_MEETINGS_2026 = [
    (date(2026, 1, 28), date(2026, 1, 29)),
    (date(2026, 3, 17), date(2026, 3, 18)),
    (date(2026, 4, 28), date(2026, 4, 29)),
    (date(2026, 6, 16), date(2026, 6, 17)),
    (date(2026, 7, 28), date(2026, 7, 29)),
    (date(2026, 9, 15), date(2026, 9, 16)),
    (date(2026, 10, 27), date(2026, 10, 28)),
    (date(2026, 12, 8), date(2026, 12, 9)),
]

# ---------------------------------------------------------------------------
# 2026 CPI Release Dates (typically around the 13th of each month)
# These are the BLS schedule for CPI-U monthly releases.
# ---------------------------------------------------------------------------
CPI_RELEASES_2026 = [
    date(2026, 1, 14),   # Dec 2025 CPI
    date(2026, 2, 11),   # Jan CPI
    date(2026, 3, 12),   # Feb CPI
    date(2026, 4, 14),   # Mar CPI
    date(2026, 5, 13),   # Apr CPI
    date(2026, 6, 10),   # May CPI
    date(2026, 7, 14),   # Jun CPI
    date(2026, 8, 12),   # Jul CPI
    date(2026, 9, 15),   # Aug CPI
    date(2026, 10, 14),  # Sep CPI
    date(2026, 11, 12),  # Oct CPI
    date(2026, 12, 10),  # Nov CPI
]

# ---------------------------------------------------------------------------
# 2026 GDP Release Dates (advance, second, third estimates each quarter)
# ---------------------------------------------------------------------------
GDP_RELEASES_2026 = [
    (date(2026, 1, 29), "Q4 2025 Advance"),
    (date(2026, 2, 26), "Q4 2025 Second"),
    (date(2026, 3, 26), "Q4 2025 Third"),
    (date(2026, 4, 29), "Q1 2026 Advance"),
    (date(2026, 5, 28), "Q1 2026 Second"),
    (date(2026, 6, 25), "Q1 2026 Third"),
    (date(2026, 7, 29), "Q2 2026 Advance"),
    (date(2026, 8, 27), "Q2 2026 Second"),
    (date(2026, 9, 24), "Q2 2026 Third"),
    (date(2026, 10, 29), "Q3 2026 Advance"),
    (date(2026, 11, 25), "Q3 2026 Second"),
    (date(2026, 12, 23), "Q3 2026 Third"),
]

# ---------------------------------------------------------------------------
# 2026 PCE (Personal Consumption Expenditures) Release Dates
# Typically released ~last Friday of the month by BEA.
# ---------------------------------------------------------------------------
PCE_RELEASES_2026 = [
    (date(2026, 1, 30), "Dec 2025"),
    (date(2026, 2, 27), "Jan"),
    (date(2026, 3, 27), "Feb"),
    (date(2026, 4, 30), "Mar"),
    (date(2026, 5, 29), "Apr"),
    (date(2026, 6, 26), "May"),
    (date(2026, 7, 31), "Jun"),
    (date(2026, 8, 28), "Jul"),
    (date(2026, 9, 25), "Aug"),
    (date(2026, 10, 30), "Sep"),
    (date(2026, 11, 25), "Oct"),
    (date(2026, 12, 23), "Nov"),
]

# ---------------------------------------------------------------------------
# 2026 PPI Release Dates (Producer Price Index)
# Typically released ~14th-15th of each month.
# ---------------------------------------------------------------------------
PPI_RELEASES_2026 = [
    date(2026, 1, 15),
    date(2026, 2, 13),
    date(2026, 3, 13),
    date(2026, 4, 15),
    date(2026, 5, 14),
    date(2026, 6, 12),
    date(2026, 7, 15),
    date(2026, 8, 13),
    date(2026, 9, 15),
    date(2026, 10, 15),
    date(2026, 11, 13),
    date(2026, 12, 11),
]

# ---------------------------------------------------------------------------
# 2026 Retail Sales Release Dates
# Typically released ~16th of each month.
# ---------------------------------------------------------------------------
RETAIL_SALES_RELEASES_2026 = [
    date(2026, 1, 16),
    date(2026, 2, 14),
    date(2026, 3, 17),
    date(2026, 4, 16),
    date(2026, 5, 15),
    date(2026, 6, 16),
    date(2026, 7, 16),
    date(2026, 8, 14),
    date(2026, 9, 16),
    date(2026, 10, 16),
    date(2026, 11, 17),
    date(2026, 12, 15),
]

# ---------------------------------------------------------------------------
# 2026 UMich Consumer Sentiment (preliminary ~mid-month, final ~end-month)
# ---------------------------------------------------------------------------
CONSUMER_SENTIMENT_RELEASES_2026 = [
    (date(2026, 1, 16), "Jan Prelim"),
    (date(2026, 1, 30), "Jan Final"),
    (date(2026, 2, 13), "Feb Prelim"),
    (date(2026, 2, 27), "Feb Final"),
    (date(2026, 3, 13), "Mar Prelim"),
    (date(2026, 3, 27), "Mar Final"),
    (date(2026, 4, 10), "Apr Prelim"),
    (date(2026, 4, 24), "Apr Final"),
    (date(2026, 5, 15), "May Prelim"),
    (date(2026, 5, 29), "May Final"),
    (date(2026, 6, 12), "Jun Prelim"),
    (date(2026, 6, 26), "Jun Final"),
    (date(2026, 7, 10), "Jul Prelim"),
    (date(2026, 7, 31), "Jul Final"),
    (date(2026, 8, 14), "Aug Prelim"),
    (date(2026, 8, 28), "Aug Final"),
    (date(2026, 9, 11), "Sep Prelim"),
    (date(2026, 9, 25), "Sep Final"),
    (date(2026, 10, 16), "Oct Prelim"),
    (date(2026, 10, 30), "Oct Final"),
    (date(2026, 11, 13), "Nov Prelim"),
    (date(2026, 11, 25), "Nov Final"),
    (date(2026, 12, 11), "Dec Prelim"),
    (date(2026, 12, 23), "Dec Final"),
]

# ---------------------------------------------------------------------------
# 2026 ISM Manufacturing PMI (first business day of the month)
# ---------------------------------------------------------------------------
ISM_MANUFACTURING_RELEASES_2026 = [
    date(2026, 1, 5),
    date(2026, 2, 2),
    date(2026, 3, 2),
    date(2026, 4, 1),
    date(2026, 5, 1),
    date(2026, 6, 1),
    date(2026, 7, 1),
    date(2026, 8, 3),
    date(2026, 9, 1),
    date(2026, 10, 1),
    date(2026, 11, 2),
    date(2026, 12, 1),
]

# Month names for labeling NFP reports
_MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------
_calendar_cache = {}
_calendar_expiry = 0.0
_stock_events_cache = {}
_stock_events_expiry = {}
_impact_cache = {}
_impact_expiry = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso():
    """Return current UTC timestamp in ISO 8601 with second precision."""
    return datetime.now(timezone.utc).isoformat()


def _load_api_keys():
    """Load API keys from config file."""
    if API_KEYS_FILE.exists():
        with open(API_KEYS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _first_friday(year, month):
    """Return the first Friday of the given month and year."""
    first_day = date(year, month, 1)
    day_of_week = first_day.weekday()  # 0=Mon, 4=Fri
    days_until_friday = (4 - day_of_week) % 7
    return first_day + timedelta(days=days_until_friday)


def _generate_nfp_dates_2026():
    """Generate Non-Farm Payrolls release dates for 2026.

    NFP is released on the first Friday of each month, reporting
    the previous month's data.
    """
    events = []
    for month in range(1, 13):
        release_date = _first_friday(2026, month)
        reported_month = month - 1 if month > 1 else 12
        label = _MONTH_NAMES[reported_month]
        events.append((release_date, f"NFP ({label})"))
    return events


def _generate_jobless_claims_dates(start_date, days_ahead):
    """Generate weekly Initial Jobless Claims dates (Thursdays)."""
    events = []
    current = start_date
    # Find next Thursday
    days_until_thursday = (3 - current.weekday()) % 7
    if days_until_thursday == 0 and current == start_date:
        next_thursday = current
    else:
        next_thursday = current + timedelta(days=days_until_thursday or 7)

    end_date = start_date + timedelta(days=days_ahead)
    while next_thursday <= end_date:
        events.append(next_thursday)
        next_thursday += timedelta(days=7)
    return events


def _generate_options_expirations(start_date, days_ahead):
    """Generate options expiration dates within the lookahead window.

    Monthly expirations fall on the third Friday of each month.
    Weekly expirations fall on every Friday.
    """
    events = []
    end_date = start_date + timedelta(days=days_ahead)
    current = start_date

    # Find next Friday
    days_until_friday = (4 - current.weekday()) % 7
    next_friday = current + timedelta(days=days_until_friday or 7)

    while next_friday <= end_date:
        is_monthly = _is_third_friday(next_friday)
        exp_type = "monthly" if is_monthly else "weekly"
        events.append({
            "date": next_friday.isoformat(),
            "event": f"Options Expiration ({exp_type.title()})",
            "importance": MEDIUM if is_monthly else LOW,
            "type": CATEGORY_OPTIONS,
            "expiration_type": exp_type,
        })
        next_friday += timedelta(days=7)
    return events


def _is_third_friday(d):
    """Check whether a date is the third Friday of its month."""
    if d.weekday() != 4:
        return False
    # Third Friday falls between the 15th and 21st
    return 15 <= d.day <= 21


def _filter_upcoming(dates, start_date, days_ahead):
    """Filter a list of dates to those within [start_date, start_date + days_ahead]."""
    end_date = start_date + timedelta(days=days_ahead)
    return [d for d in dates if start_date <= d <= end_date]


def _try_fetch_fred_release_dates(release_id, api_key, days_ahead=90):
    """Attempt to fetch upcoming release dates from the FRED API.

    Args:
        release_id: FRED release ID (e.g. 10 for CPI, 46 for GDP).
        api_key: FRED API key.
        days_ahead: Number of days to look ahead.

    Returns:
        List of date objects, or empty list on failure.
    """
    if not api_key:
        return []

    today = date.today()
    end = today + timedelta(days=days_ahead)

    params = {
        "release_id": release_id,
        "api_key": api_key,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
        "realtime_start": today.isoformat(),
        "realtime_end": end.isoformat(),
    }

    try:
        resp = requests.get(
            FRED_RELEASE_DATES,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        release_dates = []
        for entry in data.get("release_dates", []):
            raw_date = entry.get("date", "")
            if raw_date:
                release_dates.append(date.fromisoformat(raw_date))
        return release_dates
    except Exception as exc:
        logger.warning(
            "Failed to fetch FRED release dates for release_id=%s: %s",
            release_id, exc,
        )
        return []


# ---------------------------------------------------------------------------
# FRED release IDs for key economic reports
# ---------------------------------------------------------------------------
FRED_RELEASE_IDS = {
    "cpi": 10,
    "ppi": 61,
    "employment_situation": 50,
    "gdp": 53,
    "retail_sales": 28,
    "consumer_sentiment": 29,
    "pce": 54,
    "ism_manufacturing": 32,
    "initial_claims": 39,
}


# ---------------------------------------------------------------------------
# 1. Economic Calendar
# ---------------------------------------------------------------------------

def get_economic_calendar(days_ahead=30):
    """Return upcoming major economic events within the lookahead window.

    Combines hardcoded 2026 schedule data with optional FRED API lookups.
    Results are cached for one hour.

    Args:
        days_ahead: Number of calendar days to look ahead. Defaults to 30.

    Returns:
        Dict with keys: events (sorted list), next_major (next high-importance
        event), this_week (events in current week), timestamp.
    """
    global _calendar_cache, _calendar_expiry
    cache_key = days_ahead
    now = time.time()
    if cache_key in _calendar_cache and now < _calendar_expiry:
        return _calendar_cache[cache_key]

    today = date.today()
    events = []

    # Attempt FRED lookups for supplemental data
    keys = _load_api_keys()
    fred_key = keys.get("fred", "")

    # ---- FOMC Meetings ----
    for start_day, end_day in FOMC_MEETINGS_2026:
        if today <= end_day <= today + timedelta(days=days_ahead):
            events.append({
                "date": end_day.isoformat(),
                "time": "14:00 ET",
                "event": "FOMC Rate Decision",
                "importance": HIGH,
                "previous": None,
                "forecast": None,
                "category": CATEGORY_MONETARY_POLICY,
                "meeting_start": start_day.isoformat(),
            })

    # ---- CPI ----
    cpi_dates = _filter_upcoming(CPI_RELEASES_2026, today, days_ahead)
    fred_cpi = _try_fetch_fred_release_dates(
        FRED_RELEASE_IDS["cpi"], fred_key, days_ahead,
    )
    all_cpi = _merge_date_lists(cpi_dates, fred_cpi)
    for d in all_cpi:
        month_idx = d.month - 1 if d.month > 1 else 12
        label = _MONTH_NAMES[month_idx]
        events.append({
            "date": d.isoformat(),
            "time": "08:30 ET",
            "event": f"CPI ({label})",
            "importance": HIGH,
            "previous": None,
            "forecast": None,
            "category": CATEGORY_INFLATION,
        })

    # ---- NFP / Employment Situation ----
    nfp_dates = _generate_nfp_dates_2026()
    for release_date, label in nfp_dates:
        if today <= release_date <= today + timedelta(days=days_ahead):
            events.append({
                "date": release_date.isoformat(),
                "time": "08:30 ET",
                "event": f"Non-Farm Payrolls {label}",
                "importance": HIGH,
                "previous": None,
                "forecast": None,
                "category": CATEGORY_EMPLOYMENT,
            })

    # ---- GDP ----
    for release_date, label in GDP_RELEASES_2026:
        if today <= release_date <= today + timedelta(days=days_ahead):
            is_advance = "Advance" in label
            events.append({
                "date": release_date.isoformat(),
                "time": "08:30 ET",
                "event": f"GDP {label}",
                "importance": HIGH if is_advance else MEDIUM,
                "previous": None,
                "forecast": None,
                "category": CATEGORY_GDP,
            })

    # ---- PPI ----
    ppi_dates = _filter_upcoming(PPI_RELEASES_2026, today, days_ahead)
    for d in ppi_dates:
        month_idx = d.month - 1 if d.month > 1 else 12
        label = _MONTH_NAMES[month_idx]
        events.append({
            "date": d.isoformat(),
            "time": "08:30 ET",
            "event": f"PPI ({label})",
            "importance": MEDIUM,
            "previous": None,
            "forecast": None,
            "category": CATEGORY_INFLATION,
        })

    # ---- Retail Sales ----
    retail_dates = _filter_upcoming(RETAIL_SALES_RELEASES_2026, today, days_ahead)
    for d in retail_dates:
        month_idx = d.month - 1 if d.month > 1 else 12
        label = _MONTH_NAMES[month_idx]
        events.append({
            "date": d.isoformat(),
            "time": "08:30 ET",
            "event": f"Retail Sales ({label})",
            "importance": MEDIUM,
            "previous": None,
            "forecast": None,
            "category": CATEGORY_CONSUMER,
        })

    # ---- Consumer Sentiment (UMich) ----
    for release_date, label in CONSUMER_SENTIMENT_RELEASES_2026:
        if today <= release_date <= today + timedelta(days=days_ahead):
            is_prelim = "Prelim" in label
            events.append({
                "date": release_date.isoformat(),
                "time": "10:00 ET",
                "event": f"Consumer Sentiment ({label})",
                "importance": MEDIUM if is_prelim else LOW,
                "previous": None,
                "forecast": None,
                "category": CATEGORY_CONSUMER,
            })

    # ---- PCE ----
    for release_date, label in PCE_RELEASES_2026:
        if today <= release_date <= today + timedelta(days=days_ahead):
            events.append({
                "date": release_date.isoformat(),
                "time": "08:30 ET",
                "event": f"PCE Price Index ({label})",
                "importance": HIGH,
                "previous": None,
                "forecast": None,
                "category": CATEGORY_INFLATION,
            })

    # ---- ISM Manufacturing ----
    ism_dates = _filter_upcoming(
        ISM_MANUFACTURING_RELEASES_2026, today, days_ahead,
    )
    for d in ism_dates:
        events.append({
            "date": d.isoformat(),
            "time": "10:00 ET",
            "event": "ISM Manufacturing PMI",
            "importance": MEDIUM,
            "previous": None,
            "forecast": None,
            "category": CATEGORY_MANUFACTURING,
        })

    # ---- Initial Jobless Claims (weekly, Thursdays) ----
    claims_dates = _generate_jobless_claims_dates(today, days_ahead)
    for d in claims_dates:
        events.append({
            "date": d.isoformat(),
            "time": "08:30 ET",
            "event": "Initial Jobless Claims",
            "importance": LOW,
            "previous": None,
            "forecast": None,
            "category": CATEGORY_EMPLOYMENT,
        })

    # Sort by date, then by importance (high first for same-day ties)
    importance_order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    events.sort(
        key=lambda e: (e["date"], importance_order.get(e["importance"], 3)),
    )

    # Deduplicate events with same date and event name
    events = _deduplicate_events(events)

    # Derive convenience fields
    next_major = _find_next_major(events)
    this_week = _find_this_week_events(events, today)

    result = {
        "events": events,
        "next_major": next_major,
        "this_week": this_week,
        "timestamp": _now_iso(),
    }

    _calendar_cache[cache_key] = result
    _calendar_expiry = now + CACHE_TTL
    return result


def _merge_date_lists(hardcoded, fetched):
    """Merge hardcoded and FRED-fetched date lists, removing duplicates."""
    combined = set(hardcoded)
    for d in fetched:
        combined.add(d)
    return sorted(combined)


def _deduplicate_events(events):
    """Remove duplicate events sharing the same date and event name."""
    seen = set()
    unique = []
    for event in events:
        key = (event["date"], event["event"])
        if key not in seen:
            seen.add(key)
            unique.append(event)
    return unique


def _find_next_major(events):
    """Return the next high-importance event from the list, or None."""
    for event in events:
        if event["importance"] == HIGH:
            return event
    return None


def _find_this_week_events(events, today):
    """Return events occurring within the current calendar week (Mon-Sun)."""
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return [
        e for e in events
        if week_start.isoformat() <= e["date"] <= week_end.isoformat()
    ]


# ---------------------------------------------------------------------------
# 2. Stock-Specific Events
# ---------------------------------------------------------------------------

def get_stock_events(ticker, days_ahead=90):
    """Return upcoming events for a specific stock.

    Fetches earnings dates, ex-dividend dates, and options expirations
    from yfinance. Handles missing or incomplete data gracefully.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        days_ahead: Number of calendar days to look ahead. Defaults to 90.

    Returns:
        Dict with keys: ticker, events (sorted list), next_earnings,
        days_to_earnings, ex_dividend_date, timestamp.
    """
    global _stock_events_cache, _stock_events_expiry
    now = time.time()
    cache_key = f"{ticker}_{days_ahead}"
    if cache_key in _stock_events_cache and now < _stock_events_expiry.get(cache_key, 0):
        return _stock_events_cache[cache_key]

    today = date.today()
    end_date = today + timedelta(days=days_ahead)
    events = []
    next_earnings = None
    days_to_earnings = None
    ex_dividend_date = None

    try:
        stock = yf.Ticker(ticker)

        # ---- Earnings dates ----
        earnings_event = _extract_earnings(stock, today, end_date)
        if earnings_event:
            events.append(earnings_event)
            next_earnings = earnings_event
            earnings_date = date.fromisoformat(earnings_event["date"])
            days_to_earnings = (earnings_date - today).days

        # ---- Ex-dividend date ----
        ex_div_event = _extract_ex_dividend(stock, today, end_date)
        if ex_div_event:
            events.append(ex_div_event)
            ex_dividend_date = ex_div_event["date"]

        # ---- Stock splits ----
        split_event = _extract_stock_split(stock, today, end_date)
        if split_event:
            events.append(split_event)

    except Exception as exc:
        logger.warning("Failed to fetch yfinance data for %s: %s", ticker, exc)

    # ---- Options expirations ----
    options_events = _generate_options_expirations(today, days_ahead)
    events.extend(options_events)

    # Sort by date, then importance
    importance_order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    events.sort(
        key=lambda e: (e["date"], importance_order.get(e["importance"], 3)),
    )

    result = {
        "ticker": ticker,
        "events": events,
        "next_earnings": next_earnings,
        "days_to_earnings": days_to_earnings,
        "ex_dividend_date": ex_dividend_date,
        "timestamp": _now_iso(),
    }

    _stock_events_cache[cache_key] = result
    _stock_events_expiry[cache_key] = now + CACHE_TTL
    return result


def _extract_earnings(stock, today, end_date):
    """Extract the next earnings date from a yfinance Ticker object.

    Tries the calendar attribute first, then falls back to the
    earnings_dates attribute.

    Returns:
        Event dict, or None if no upcoming earnings found.
    """
    # Try stock.calendar first (structured dict)
    try:
        cal = stock.calendar
        if cal and isinstance(cal, dict):
            earnings_date_raw = cal.get("Earnings Date")
            if earnings_date_raw:
                if isinstance(earnings_date_raw, list) and len(earnings_date_raw) > 0:
                    earnings_date_raw = earnings_date_raw[0]
                earnings_date = _coerce_to_date(earnings_date_raw)
                if earnings_date and today <= earnings_date <= end_date:
                    return _build_earnings_event(earnings_date)
    except Exception:
        pass

    # Fallback: stock.earnings_dates
    try:
        earnings_dates = stock.earnings_dates
        if earnings_dates is not None and not earnings_dates.empty:
            for ts in earnings_dates.index:
                d = _coerce_to_date(ts)
                if d and today <= d <= end_date:
                    return _build_earnings_event(d)
    except Exception:
        pass

    return None


def _build_earnings_event(earnings_date):
    """Build a standardized earnings event dict."""
    quarter = _quarter_label(earnings_date)
    return {
        "date": earnings_date.isoformat(),
        "event": f"{quarter} Earnings Report",
        "importance": HIGH,
        "type": CATEGORY_EARNINGS,
    }


def _quarter_label(d):
    """Return a fiscal quarter label like 'Q1' based on the month."""
    quarter_num = (d.month - 1) // 3 + 1
    return f"Q{quarter_num}"


def _extract_ex_dividend(stock, today, end_date):
    """Extract the next ex-dividend date from a yfinance Ticker.

    Returns:
        Event dict, or None if no upcoming ex-dividend found.
    """
    try:
        info = stock.info
        ex_div_raw = info.get("exDividendDate")
        if ex_div_raw:
            ex_div_date = _coerce_to_date(ex_div_raw)
            if ex_div_date and today <= ex_div_date <= end_date:
                dividend_rate = info.get("dividendRate")
                label = "Ex-Dividend Date"
                if dividend_rate:
                    label += f" (${dividend_rate:.2f}/share)"
                return {
                    "date": ex_div_date.isoformat(),
                    "event": label,
                    "importance": MEDIUM,
                    "type": CATEGORY_DIVIDEND,
                }
    except Exception:
        pass
    return None


def _extract_stock_split(stock, today, end_date):
    """Check for any announced upcoming stock splits.

    yfinance does not reliably expose future splits, so this inspects
    the info dict for any announcements.

    Returns:
        Event dict, or None if no upcoming split found.
    """
    try:
        info = stock.info
        # yfinance stores lastSplitDate and lastSplitFactor but not future
        # splits reliably. We check for any forward-looking hints.
        last_split_date = info.get("lastSplitDate")
        last_split_factor = info.get("lastSplitFactor")
        if last_split_date:
            split_date = _coerce_to_date(last_split_date)
            if split_date and today <= split_date <= end_date:
                factor_label = last_split_factor or "TBD"
                return {
                    "date": split_date.isoformat(),
                    "event": f"Stock Split ({factor_label})",
                    "importance": HIGH,
                    "type": CATEGORY_SPLIT,
                }
    except Exception:
        pass
    return None


def _coerce_to_date(value):
    """Coerce various date-like values to a date object.

    Handles datetime, Timestamp, date, epoch integers, and ISO strings.

    Returns:
        date object, or None if coercion fails.
    """
    if value is None:
        return None

    # Already a date
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    # datetime or pandas Timestamp
    if isinstance(value, datetime):
        return value.date()

    # Integer epoch (seconds)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        except (OSError, ValueError, OverflowError):
            return None

    # String
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass

    # pandas Timestamp-like with .date() method
    if hasattr(value, "date") and callable(value.date):
        try:
            return value.date()
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# 3. Market Events Impact Analysis
# ---------------------------------------------------------------------------

def get_market_events_impact():
    """Analyze how upcoming economic events may affect markets.

    Returns:
        Dict with days until next FOMC, CPI, and NFP, plus a summary
        of the upcoming event density.
    """
    global _impact_cache, _impact_expiry
    now = time.time()
    if _impact_cache and now < _impact_expiry:
        return _impact_cache

    today = date.today()
    calendar = get_economic_calendar(days_ahead=90)
    events = calendar.get("events", [])

    days_to_fomc = _days_until_event(events, "FOMC", today)
    days_to_cpi = _days_until_event(events, "CPI", today)
    days_to_nfp = _days_until_event(events, "Non-Farm Payrolls", today)
    days_to_pce = _days_until_event(events, "PCE", today)
    days_to_gdp = _days_until_event(events, "GDP", today)

    # Count high-importance events in the next 7 and 30 days
    high_events_7d = _count_events_by_importance(
        events, today, days_window=7, importance=HIGH,
    )
    high_events_30d = _count_events_by_importance(
        events, today, days_window=30, importance=HIGH,
    )

    # Risk assessment based on event density
    risk_level = _assess_event_risk(high_events_7d)

    # Pre-event windows (commonly cited as high-volatility periods)
    pre_event_windows = _build_pre_event_windows(events, today)

    result = {
        "days_to_fomc": days_to_fomc,
        "days_to_cpi": days_to_cpi,
        "days_to_nfp": days_to_nfp,
        "days_to_pce": days_to_pce,
        "days_to_gdp": days_to_gdp,
        "high_importance_events_7d": high_events_7d,
        "high_importance_events_30d": high_events_30d,
        "event_risk_level": risk_level,
        "pre_event_windows": pre_event_windows,
        "guidance": _generate_impact_guidance(
            days_to_fomc, days_to_cpi, days_to_nfp, risk_level,
        ),
        "timestamp": _now_iso(),
    }

    _impact_cache = result
    _impact_expiry = now + CACHE_TTL
    return result


def _days_until_event(events, event_keyword, today):
    """Return the number of days until the next event matching the keyword.

    Args:
        events: List of event dicts from the calendar.
        event_keyword: Substring to match against the event name.
        today: Current date.

    Returns:
        Integer days, or None if no matching event found.
    """
    for event in events:
        if event_keyword in event.get("event", ""):
            event_date = date.fromisoformat(event["date"])
            delta = (event_date - today).days
            if delta >= 0:
                return delta
    return None


def _count_events_by_importance(events, today, days_window, importance):
    """Count events of a given importance level within a date window."""
    end = today + timedelta(days=days_window)
    count = 0
    for event in events:
        event_date = date.fromisoformat(event["date"])
        if today <= event_date <= end and event["importance"] == importance:
            count += 1
    return count


def _assess_event_risk(high_events_7d):
    """Assess near-term event risk based on upcoming high-importance events.

    Returns:
        Risk level string: "high", "medium", or "low".
    """
    if high_events_7d >= 3:
        return HIGH
    if high_events_7d >= 1:
        return MEDIUM
    return LOW


def _build_pre_event_windows(events, today):
    """Identify upcoming pre-event windows for high-importance events.

    Market volatility often increases 1-2 days before major releases.
    Returns a list of date ranges representing these windows.
    """
    windows = []
    seen_dates = set()
    for event in events:
        if event["importance"] != HIGH:
            continue
        event_date = date.fromisoformat(event["date"])
        delta = (event_date - today).days
        if delta < 0 or delta > 14:
            continue
        if event_date in seen_dates:
            continue
        seen_dates.add(event_date)

        window_start = event_date - timedelta(days=2)
        if window_start < today:
            window_start = today

        windows.append({
            "event": event["event"],
            "event_date": event_date.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": event_date.isoformat(),
            "days_away": delta,
        })

    return windows


def _generate_impact_guidance(days_to_fomc, days_to_cpi, days_to_nfp, risk_level):
    """Generate a plain-text summary of upcoming event risk.

    Args:
        days_to_fomc: Days until next FOMC decision (or None).
        days_to_cpi: Days until next CPI release (or None).
        days_to_nfp: Days until next NFP release (or None).
        risk_level: Overall risk level string.

    Returns:
        List of guidance strings.
    """
    guidance = []

    if days_to_fomc is not None and days_to_fomc <= 7:
        guidance.append(
            f"FOMC rate decision in {days_to_fomc} day(s). "
            "Expect elevated volatility in rate-sensitive sectors."
        )
    if days_to_cpi is not None and days_to_cpi <= 3:
        guidance.append(
            f"CPI release in {days_to_cpi} day(s). "
            "Inflation data may drive significant intraday moves."
        )
    if days_to_nfp is not None and days_to_nfp <= 3:
        guidance.append(
            f"NFP report in {days_to_nfp} day(s). "
            "Labor market data often causes broad market moves."
        )

    if risk_level == HIGH:
        guidance.append(
            "Multiple high-importance events this week. "
            "Consider reducing position sizes or hedging."
        )
    elif risk_level == MEDIUM:
        guidance.append(
            "Moderate event risk this week. "
            "Monitor positions through key releases."
        )
    else:
        guidance.append(
            "Low event risk in the near term. "
            "Calendar is relatively clear for directional trades."
        )

    return guidance
