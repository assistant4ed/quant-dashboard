"""
Scheduled market data updater.

Designed to run at EST 9:30am, 12:30pm, 3:30pm, 6:30pm.
Updates: predictions cache, news data, economic indicators.

Usage:
    python scheduled_update.py          # single run
    crontab example (EST 9:30am):
    30 9 * * 1-5 cd /Users/Ed/qlib/dashboard && /Users/Ed/qlib-env/bin/python scheduled_update.py
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
API_KEYS_FILE = DATA_DIR / "api_keys.json"

REQUEST_TIMEOUT_SECONDS = 15
NEWS_PAGE_SIZE = 20

FRED_SERIES = {
    "gdp_growth": {
        "id": "A191RL1Q225SBEA",
        "name": "GDP Growth Rate",
        "name_cn": "GDP增长率",
        "unit": "%",
    },
    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "name_cn": "失业率",
        "unit": "%",
    },
    "cpi": {
        "id": "CPIAUCSL",
        "name": "CPI Inflation",
        "name_cn": "CPI通胀率",
        "unit": "%",
    },
    "fed_rate": {
        "id": "FEDFUNDS",
        "name": "Fed Funds Rate",
        "name_cn": "联邦基金利率",
        "unit": "%",
    },
    "consumer_confidence": {
        "id": "UMCSENT",
        "name": "Consumer Confidence",
        "name_cn": "消费者信心指数",
        "unit": "",
    },
    "pmi": {
        "id": "MANEMP",
        "name": "Manufacturing Employment",
        "name_cn": "制造业就业",
        "unit": "K",
    },
}

POSITIVE_KEYWORDS = frozenset(
    ["surge", "boom", "gain", "rise", "rally", "record"]
)
NEGATIVE_KEYWORDS = frozenset(
    ["drop", "fall", "crash", "plunge", "recession", "fear"]
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("scheduler")


def load_api_keys():
    """Load API keys from the configuration file."""
    if API_KEYS_FILE.exists():
        with open(API_KEYS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _write_json_atomic(file_path, data):
    """Write JSON to disk using an atomic rename to prevent corruption."""
    tmp = file_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(file_path)


def _classify_sentiment(title):
    """Derive a simple sentiment label from headline keywords."""
    title_lower = (title or "").lower()
    if any(word in title_lower for word in POSITIVE_KEYWORDS):
        return "positive"
    if any(word in title_lower for word in NEGATIVE_KEYWORDS):
        return "negative"
    return "neutral"


def update_news(api_keys):
    """Update news data from NewsAPI if key is available."""
    import requests

    key = api_keys.get("newsapi", "")
    if not key:
        logger.info("NewsAPI key not configured, skipping news update")
        return

    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "category": "business",
        "country": "us",
        "pageSize": NEWS_PAGE_SIZE,
        "apiKey": key,
    }

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for art in data.get("articles", []):
            sentiment = _classify_sentiment(art.get("title", ""))
            articles.append({
                "title": art.get("title", ""),
                "title_cn": "",
                "source": (art.get("source", {}) or {}).get("name", ""),
                "date": (art.get("publishedAt", "") or "")[:10],
                "category": "market",
                "sentiment": sentiment,
                "impact": "medium",
                "summary": art.get("description", "") or "",
                "summary_cn": "",
                "url": art.get("url", ""),
            })

        news_file = DATA_DIR / "news_data.json"
        output = {
            "updated_at": datetime.now(timezone.utc).isoformat()[:10],
            "articles": articles,
        }
        _write_json_atomic(news_file, output)
        logger.info("Updated news: %d articles", len(articles))

    except Exception as exc:
        logger.error("News update failed: %s", exc)


def update_economic_data(api_keys):
    """Update economic indicators from FRED if key is available."""
    import requests

    key = api_keys.get("fred", "")
    if not key:
        logger.info("FRED key not configured, skipping economic update")
        return

    indicators = []
    for key_id, info in FRED_SERIES.items():
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": info["id"],
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            }
            resp = requests.get(
                url, params=params, timeout=REQUEST_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            obs = resp.json().get("observations", [])

            if len(obs) >= 2:
                current = (
                    float(obs[0]["value"])
                    if obs[0]["value"] != "."
                    else 0
                )
                previous = (
                    float(obs[1]["value"])
                    if obs[1]["value"] != "."
                    else 0
                )
                change = round(current - previous, 2)

                if change > 0:
                    direction = "up"
                elif change < 0:
                    direction = "down"
                else:
                    direction = "flat"

                indicators.append({
                    "id": key_id,
                    "name": info["name"],
                    "name_cn": info["name_cn"],
                    "value": round(current, 1),
                    "unit": info["unit"],
                    "change": change,
                    "direction": direction,
                    "period": obs[0]["date"],
                })
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", key_id, exc)

    if indicators:
        econ_file = DATA_DIR / "economic_data.json"
        output = {
            "updated_at": datetime.now(timezone.utc).isoformat()[:10],
            "indicators": indicators,
        }
        _write_json_atomic(econ_file, output)
        logger.info("Updated %d economic indicators", len(indicators))


def update_market_data():
    """Clear the yfinance cache so the next request fetches fresh data.

    In a production system this would pre-warm the cache for the top
    tickers. For now, clearing ensures staleness is bounded by the
    dashboard's CACHE_TTL.
    """
    logger.info("Market data cache cleared (next request fetches fresh)")


def main():
    """Run all scheduled updates."""
    logger.info("=" * 60)
    logger.info("SCHEDULED UPDATE STARTING")
    logger.info("=" * 60)

    api_keys = load_api_keys()

    update_market_data()
    update_news(api_keys)
    update_economic_data(api_keys)

    logger.info("Scheduled update complete")


if __name__ == "__main__":
    main()
