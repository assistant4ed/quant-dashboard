"""
Flask backend for the qlib stock prediction dashboard.

Serves prediction data from a pre-trained LightGBM + Alpha158 model
and provides API endpoints for the frontend dashboard.
"""
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"
ECONOMIC_FILE = DATA_DIR / "economic_data.json"
NEWS_FILE = DATA_DIR / "news_data.json"
IMPROVEMENT_STATUS_FILE = DATA_DIR / "improvement_status.json"
PYTHON_BIN = Path(os.environ.get("PYTHON_BIN", "/Users/Ed/qlib-env/bin/python"))
GENERATE_SCRIPT = BASE_DIR / "generate_data.py"
IMPROVE_SCRIPT = BASE_DIR / "improve_model.py"

BACKTEST_FILE = DATA_DIR / "backtest_results.json"
QUALITY_FILE = DATA_DIR / "quality_report.json"
QUALITY_SCRIPT = BASE_DIR / "quality_check.py"
API_KEYS_FILE = DATA_DIR / "api_keys.json"
MODEL_EVOLUTION_FILE = DATA_DIR / "model_evolution.json"

DEFAULT_PORT = 5001
DEFAULT_TOP_N = 10
MAX_TOP_N = 100

# Historical data cache (ticker_period -> list of OHLCV dicts)
CACHE_TTL = 3600  # 1 hour in seconds
ALLOWED_PERIODS = {"1mo", "3mo", "6mo", "1y", "5y"}
TICKER_PATTERN = re.compile(r"^[A-Za-z0-9]{1,10}$")
TRADING_DAYS_PER_YEAR = 252
MAX_SIGNAL_BOOST = 15
MAX_PROBABILITY = 95
GROWTH_SCALE = 500
MONTHS_IN_YEAR = 12
PREDICTION_MONTHS = 6
PERCENTILE_90_Z = 1.645  # z-score for 90th percentile confidence band
MOMENTUM_WEIGHT = 0.5
VOLATILITY_WEIGHT = 0.3
TREND_WEIGHT = 0.2
SMA_SHORT_PERIOD = 20
SMA_LONG_PERIOD = 50

_history_cache: dict[str, list[dict]] = {}
_cache_expiry: dict[str, float] = {}
_company_cache: dict[str, dict] = {}
_company_cache_expiry: dict[str, float] = {}

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        template_folder=str(BASE_DIR / "templates"),
    )
    CORS(app)

    # Structured logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger("dashboard")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_predictions():
        """Load predictions.json from disk and return the parsed dict.

        Raises FileNotFoundError when the data file does not exist.
        """
        if not PREDICTIONS_FILE.exists():
            raise FileNotFoundError(
                f"Predictions file not found at {PREDICTIONS_FILE}. "
                "Run generate_data.py first."
            )
        with open(PREDICTIONS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _error_response(message, code, status_code):
        """Return a consistent JSON error envelope."""
        return (
            jsonify({
                "error": {
                    "code": code,
                    "message": message,
                },
                "data": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            }),
            status_code,
        )

    def _load_json_file(file_path, description):
        """Load a JSON data file from disk.

        Raises FileNotFoundError when the file does not exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(
                f"{description} not found at {file_path}."
            )
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _get_history(ticker, period="1y"):
        """Fetch historical OHLCV data via yfinance with TTL cache."""
        cache_key = f"{ticker}_{period}"
        now = time.time()
        if cache_key in _history_cache and now < _cache_expiry.get(cache_key, 0):
            return _history_cache[cache_key]

        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        data = []
        for date, row in hist.iterrows():
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"]),
            })

        _history_cache[cache_key] = data
        _cache_expiry[cache_key] = now + CACHE_TTL
        return data

    def _get_company_info(ticker):
        """Fetch company info via yfinance with TTL cache."""
        now = time.time()
        if ticker in _company_cache and now < _company_cache_expiry.get(ticker, 0):
            return _company_cache[ticker]

        stock = yf.Ticker(ticker)
        info = stock.info

        _company_cache[ticker] = info
        _company_cache_expiry[ticker] = now + CACHE_TTL
        return info

    def _format_market_cap(value):
        """Format market cap to human readable string."""
        if not value:
            return None
        trillion_threshold = 1e12
        billion_threshold = 1e9
        million_threshold = 1e6
        if value >= trillion_threshold:
            return f"${value / trillion_threshold:.2f}T"
        if value >= billion_threshold:
            return f"${value / billion_threshold:.2f}B"
        if value >= million_threshold:
            return f"${value / million_threshold:.0f}M"
        return f"${value:,.0f}"

    def _safe_round(value, decimals=2):
        """Round a value if it is not None, otherwise return None."""
        if value is None:
            return None
        return round(value, decimals)

    def _enrich_stock(stock):
        """Add live price data to a stock dict for trader display."""
        try:
            ticker = stock["ticker"]
            hist = _get_history(ticker, "1mo")
            if hist and len(hist) >= 2:
                stock["current_price"] = hist[-1]["close"]
                stock["prev_close"] = hist[-2]["close"]
                stock["day_change_pct"] = round(
                    (hist[-1]["close"] - hist[-2]["close"])
                    / hist[-2]["close"]
                    * 100,
                    2,
                )
                stock["volume"] = hist[-1]["volume"]
        except Exception:
            pass
        return stock

    def _calculate_rsi(prices, period=14):
        """Calculate RSI from a pandas Series of prices."""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else None

    # ------------------------------------------------------------------
    # Page routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        """Serve the main dashboard page."""
        return render_template("index.html")

    # ------------------------------------------------------------------
    # API routes
    # ------------------------------------------------------------------

    @app.route("/api/predictions")
    def api_predictions():
        """Return the full predictions.json payload."""
        try:
            data = _load_predictions()
        except FileNotFoundError as exc:
            logger.warning("Predictions file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/top-stocks")
    def api_top_stocks():
        """Return the top N stocks.

        Query parameters
        ----------------
        n : int, default 10
            Number of stocks to return (capped at MAX_TOP_N).
        view : str, default "consensus"
            "consensus" for 20-day combined ranking,
            "single_day" for the latest single-day signal ranking.
        """
        try:
            data = _load_predictions()
        except FileNotFoundError as exc:
            logger.warning("Predictions file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        n_param = request.args.get("n", str(DEFAULT_TOP_N))
        view = request.args.get("view", "consensus")

        try:
            n = int(n_param)
        except ValueError:
            return _error_response(
                f"Parameter 'n' must be an integer, got '{n_param}'",
                "VALIDATION_FAILED",
                400,
            )

        n = max(1, min(n, MAX_TOP_N))

        if view == "single_day":
            stocks = data.get("single_day_top", [])[:n]
        elif view == "consensus":
            stocks = data.get("top_stocks", [])[:n]
        else:
            return _error_response(
                f"Invalid view '{view}'. Use 'consensus' or 'single_day'.",
                "VALIDATION_FAILED",
                400,
            )

        stocks = [_enrich_stock(dict(s)) for s in stocks]

        return jsonify({
            "data": {
                "view": view,
                "count": len(stocks),
                "stocks": stocks,
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/sectors")
    def api_sectors():
        """Return sector breakdown data."""
        try:
            data = _load_predictions()
        except FileNotFoundError as exc:
            logger.warning("Predictions file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        sectors = data.get("sector_breakdown", [])

        return jsonify({
            "data": {
                "count": len(sectors),
                "sectors": sectors,
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/methodology")
    def api_methodology():
        """Return methodology and quant research content."""
        try:
            data = _load_predictions()
        except FileNotFoundError as exc:
            logger.warning("Predictions file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        methodology = data.get("methodology", {})

        return jsonify({
            "data": methodology,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/refresh", methods=["GET", "POST"])
    def api_refresh():
        """Trigger prediction regeneration by running generate_data.py.

        This is a long-running operation. The endpoint returns immediately
        with the subprocess result once complete.  In a production system
        this should be an async task, but for a local dashboard a synchronous
        call is acceptable.
        """
        if not GENERATE_SCRIPT.exists():
            return _error_response(
                f"Generate script not found at {GENERATE_SCRIPT}",
                "SCRIPT_NOT_FOUND",
                404,
            )

        if not PYTHON_BIN.exists():
            return _error_response(
                f"Python interpreter not found at {PYTHON_BIN}",
                "INTERPRETER_NOT_FOUND",
                500,
            )

        logger.info("Starting prediction regeneration via %s", GENERATE_SCRIPT)

        try:
            result = subprocess.run(
                [str(PYTHON_BIN), str(GENERATE_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=1800,
                cwd=str(BASE_DIR),
            )
        except subprocess.TimeoutExpired:
            logger.error("generate_data.py timed out after 30 minutes")
            return _error_response(
                "Prediction regeneration timed out after 30 minutes",
                "TIMEOUT",
                504,
            )

        is_success = result.returncode == 0

        if not is_success:
            logger.error(
                "generate_data.py failed (exit %d): %s",
                result.returncode,
                result.stderr[-500:] if result.stderr else "no stderr",
            )

        return jsonify({
            "data": {
                "success": is_success,
                "return_code": result.returncode,
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                "stderr_tail": result.stderr[-2000:] if result.stderr else "",
            },
            "error": None if is_success else {
                "code": "GENERATION_FAILED",
                "message": "Prediction regeneration failed. Check stderr_tail for details.",
            },
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        }), 200 if is_success else 500

    # ------------------------------------------------------------------
    # Task 1: Historical data API
    # ------------------------------------------------------------------

    @app.route("/api/history/<ticker>")
    def api_history(ticker):
        """Return historical OHLCV data for a ticker via yfinance.

        Query parameters
        ----------------
        period : str, default "1y"
            One of "1mo", "3mo", "6mo", "1y", "5y".
        """
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Ticker must be alphanumeric and at most 10 characters",
                "VALIDATION_FAILED",
                400,
            )

        period = request.args.get("period", "1y")
        if period not in ALLOWED_PERIODS:
            return _error_response(
                f"Invalid period '{period}'. "
                f"Allowed values: {', '.join(sorted(ALLOWED_PERIODS))}",
                "VALIDATION_FAILED",
                400,
            )

        ticker_upper = ticker.upper()

        try:
            history = _get_history(ticker_upper, period)
        except Exception as exc:
            logger.error(
                "Failed to fetch history for %s (period=%s): %s",
                ticker_upper,
                period,
                exc,
            )
            return _error_response(
                f"Failed to fetch historical data for {ticker_upper}",
                "FETCH_FAILED",
                502,
            )

        if not history:
            return _error_response(
                f"No historical data found for ticker '{ticker_upper}'",
                "DATA_NOT_FOUND",
                404,
            )

        return jsonify({
            "data": {
                "ticker": ticker_upper,
                "period": period,
                "count": len(history),
                "history": history,
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Task 2: Growth predictions API
    # ------------------------------------------------------------------

    @app.route("/api/growth")
    def api_growth():
        """Return predicted growth percentages and probabilities.

        Converts raw model signals into annualized growth estimates
        with confidence levels derived from consistency scores.
        """
        try:
            data = _load_predictions()
        except FileNotFoundError as exc:
            logger.warning("Predictions file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        top_stocks = data.get("top_stocks", [])
        growth_predictions = []

        for stock in top_stocks:
            signal = stock.get("signal", 0)
            consistency = stock.get("consistency", 0)

            # Signal is a relative ranking score, not a literal daily return.
            # Scale to a realistic growth range: top signal (~0.03) -> ~15-25%
            # Using a log-like scaling to compress extreme values.
            growth_scale = 500  # maps signal 0.03 -> ~15%
            predicted_growth = signal * growth_scale

            # Probability: weighted blend of consistency and signal rank
            base_prob = consistency * 70  # consistency 0.9 -> 63%
            signal_boost = min(signal / 0.03 * 20, 25)  # cap +25%
            probability = min(base_prob + signal_boost, MAX_PROBABILITY)

            if probability >= 70:
                confidence = "high"
            elif probability >= 50:
                confidence = "medium"
            else:
                confidence = "low"

            growth_predictions.append({
                "ticker": stock["ticker"],
                "name": stock.get("name", ""),
                "name_cn": stock.get("name_cn", ""),
                "predicted_growth_pct": round(predicted_growth, 2),
                "probability": round(probability, 1),
                "confidence_level": confidence,
                "signal": signal,
                "consistency": consistency,
                "timeframe": "annual",
            })

        return jsonify({
            "data": {
                "predictions": growth_predictions,
                "count": len(growth_predictions),
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Task 3: Economic indicators API
    # ------------------------------------------------------------------

    @app.route("/api/economic")
    def api_economic():
        """Return current economic indicators."""
        try:
            data = _load_json_file(ECONOMIC_FILE, "Economic data file")
        except FileNotFoundError as exc:
            logger.warning("Economic data file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Task 4: News feed API
    # ------------------------------------------------------------------

    @app.route("/api/news")
    def api_news():
        """Return financial news from the last 7 days (Finnhub primary, yfinance fallback)."""
        from datetime import timedelta
        import yfinance as yf

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        articles = []
        news_source = "yfinance"

        # Try Finnhub first as primary news source
        try:
            from data_providers import get_provider
            finnhub = get_provider('finnhub')
            if finnhub and finnhub.is_available():
                finnhub_articles = finnhub.get_news("", 30) or []
                sentiment_cache = {}
                for fa in finnhub_articles:
                    ticker_tag = fa.get("related", "") or fa.get("ticker", "")
                    sentiment = None
                    if ticker_tag and ticker_tag not in sentiment_cache:
                        try:
                            sentiment_cache[ticker_tag] = finnhub.get_sentiment(ticker_tag)
                        except Exception:
                            sentiment_cache[ticker_tag] = None
                    if ticker_tag:
                        sentiment = sentiment_cache.get(ticker_tag)
                    articles.append({
                        "title": fa.get("headline", fa.get("title", "")),
                        "summary": fa.get("summary", ""),
                        "url": fa.get("url", ""),
                        "publishedAt": fa.get("datetime", fa.get("publishedAt", "")),
                        "source": fa.get("source", "finnhub"),
                        "sentiment": sentiment,
                        "affected_sectors": [],
                    })
                if articles:
                    news_source = "finnhub"
        except Exception as exc:
            logger.warning("Finnhub news fetch failed, falling back to yfinance: %s", exc)

        # Fall back to yfinance if Finnhub returned nothing
        if not articles:
            try:
                for ticker_sym in ["SPY", "QQQ", "^VIX"]:
                    stock = yf.Ticker(ticker_sym)
                    news_items = stock.news or []
                    for item in news_items[:10]:
                        pub_ts = item.get("providerPublishTime") or item.get("publishTime") or 0
                        pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc) if pub_ts else None
                        if pub_dt and pub_dt < seven_days_ago:
                            continue
                        content = item.get("content") or {}
                        title = content.get("title") or item.get("title", "")
                        link = ""
                        clickthrough = content.get("clickThroughUrl") or {}
                        if isinstance(clickthrough, dict):
                            link = clickthrough.get("url", "")
                        if not link:
                            link = item.get("link", "")
                        summary = content.get("summary") or item.get("summary", "")
                        articles.append({
                            "title": title,
                            "summary": summary,
                            "url": link,
                            "publishedAt": pub_dt.isoformat() if pub_dt else "",
                            "source": item.get("publisher", ""),
                            "sentiment": None,
                            "affected_sectors": [],
                        })
            except Exception as exc:
                logger.warning("Live news fetch failed: %s", exc)

        # Deduplicate by title
        seen_titles = set()
        unique_articles = []
        for a in articles:
            t = a.get("title", "")
            if t and t not in seen_titles:
                seen_titles.add(t)
                unique_articles.append(a)

        # Fall back to cached file articles if we have fewer than 5
        if len(unique_articles) < 5:
            try:
                cached = _load_json_file(NEWS_FILE, "News data file")
                for a in (cached.get("articles") or []):
                    pub_str = a.get("publishedAt", "")
                    try:
                        pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        if pub_dt < seven_days_ago:
                            continue
                    except Exception:
                        pass
                    t = a.get("title", "")
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        a["source"] = a.get("source", "cache")
                        a["sentiment"] = None
                        unique_articles.append(a)
            except FileNotFoundError:
                pass

        # Sort newest first
        def _pub_sort(a):
            try:
                return datetime.fromisoformat(a.get("publishedAt", "").replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        unique_articles.sort(key=_pub_sort, reverse=True)

        return jsonify({
            "data": {"articles": unique_articles[:30]},
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "days_filter": 7,
                "source": news_source,
            },
        })

    @app.route("/api/market-live")
    def api_market_live():
        """Real-time market overview: indices, VIX, commodities, crypto, rates."""
        import yfinance as yf

        symbols = {
            "SP500": "^GSPC",
            "NASDAQ": "^IXIC",
            "DOW": "^DJI",
            "RUSSELL2000": "^RUT",
            "VIX": "^VIX",
            "GOLD": "GC=F",
            "OIL": "CL=F",
            "TREASURY10Y": "^TNX",
            "DOLLAR": "DX-Y.NYB",
            "BTC": "BTC-USD",
        }

        result = {}
        tickers_batch = yf.Tickers(" ".join(symbols.values()))

        for name, sym in symbols.items():
            try:
                info = tickers_batch.tickers[sym].fast_info
                price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                prev = getattr(info, "previous_close", None)
                change = round(price - prev, 2) if price and prev else None
                change_pct = round((price / prev - 1) * 100, 2) if price and prev and prev != 0 else None
                result[name] = {
                    "symbol": sym,
                    "price": round(price, 2) if price else None,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": "up" if (change_pct or 0) >= 0 else "down",
                }
            except Exception as exc:
                logger.warning("market-live failed for %s: %s", sym, exc)
                result[name] = {"symbol": sym, "price": None, "change": None, "change_pct": None}

        return jsonify({
            "data": result,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Task 5: Model improvement status API
    # ------------------------------------------------------------------

    @app.route("/api/improvement-status")
    def api_improvement_status():
        """Return the current status of the self-improving model agent."""
        try:
            data = _load_json_file(
                IMPROVEMENT_STATUS_FILE,
                "Improvement status file",
            )
        except FileNotFoundError as exc:
            logger.warning("Improvement status file missing: %s", exc)
            return _error_response(str(exc), "DATA_NOT_FOUND", 404)

        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/improve", methods=["POST"])
    def api_improve():
        """Trigger the model improvement agent via improve_model.py.

        Runs the improvement script as a subprocess.  Follows the same
        pattern as the /api/refresh endpoint.
        """
        if not IMPROVE_SCRIPT.exists():
            return _error_response(
                f"Improvement script not found at {IMPROVE_SCRIPT}",
                "SCRIPT_NOT_FOUND",
                404,
            )

        if not PYTHON_BIN.exists():
            return _error_response(
                f"Python interpreter not found at {PYTHON_BIN}",
                "INTERPRETER_NOT_FOUND",
                500,
            )

        logger.info(
            "Starting model improvement via %s",
            IMPROVE_SCRIPT,
        )

        try:
            result = subprocess.run(
                [str(PYTHON_BIN), str(IMPROVE_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=3600,
                cwd=str(BASE_DIR),
            )
        except subprocess.TimeoutExpired:
            logger.error("improve_model.py timed out after 60 minutes")
            return _error_response(
                "Model improvement timed out after 60 minutes",
                "TIMEOUT",
                504,
            )

        is_success = result.returncode == 0

        if not is_success:
            logger.error(
                "improve_model.py failed (exit %d): %s",
                result.returncode,
                result.stderr[-500:] if result.stderr else "no stderr",
            )

        return jsonify({
            "data": {
                "success": is_success,
                "return_code": result.returncode,
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                "stderr_tail": result.stderr[-2000:] if result.stderr else "",
            },
            "error": None if is_success else {
                "code": "IMPROVEMENT_FAILED",
                "message": "Model improvement failed. Check stderr_tail for details.",
            },
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        }), 200 if is_success else 500

    # ------------------------------------------------------------------
    # Task 6: Forward prediction API
    # ------------------------------------------------------------------

    @app.route("/api/predict-forward/<ticker>")
    def api_predict_forward(ticker):
        """Generate 6-month forward price prediction with confidence bands.

        Uses historical volatility and model signal to project monthly prices
        with upper/lower confidence intervals at the 90th percentile.
        """
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Ticker must be alphanumeric and at most 10 characters",
                "VALIDATION_FAILED",
                400,
            )

        ticker_upper = ticker.upper()

        try:
            stock = yf.Ticker(ticker_upper)
            hist = stock.history(period="1y")
            if hist.empty:
                return _error_response(
                    f"No data for {ticker_upper}",
                    "DATA_NOT_FOUND",
                    404,
                )

            current_price = float(hist["Close"].iloc[-1])

            # Calculate annualized historical volatility
            returns = hist["Close"].pct_change().dropna()
            daily_vol = float(returns.std())
            annual_vol = daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR)

            # Look up model signal and consistency from predictions
            signal = 0
            consistency = 0
            try:
                data = _load_predictions()
                for s in data.get("top_stocks", []):
                    if s["ticker"] == ticker_upper:
                        signal = s.get("signal", 0)
                        consistency = s.get("consistency", 0)
                        break
            except FileNotFoundError:
                pass

            # Expected annual return derived from signal strength
            expected_annual_return = signal * GROWTH_SCALE
            monthly_return = expected_annual_return / 12 / 100

            dates = []
            predicted = []
            upper = []
            lower = []

            base_date = hist.index[-1]

            for month in range(1, 7):
                future_date = base_date + pd.DateOffset(months=month)
                dates.append(future_date.strftime("%Y-%m-%d"))

                price_expected = current_price * (1 + monthly_return) ** month
                predicted.append(round(price_expected, 2))

                # Confidence bands widen with the square root of time
                time_factor = np.sqrt(month / 6)
                upper_price = price_expected * (
                    1 + PERCENTILE_90_Z * annual_vol * time_factor
                )
                lower_price = price_expected * (
                    1 - PERCENTILE_90_Z * annual_vol * time_factor
                )
                upper.append(round(upper_price, 2))
                lower.append(round(max(lower_price, 0), 2))

            target_price = predicted[5]
            growth_pct = (
                (target_price - current_price) / current_price * 100
            )

            # Probability blend of consistency score and signal strength
            base_prob = consistency * 70
            signal_boost = min(signal / 0.03 * 20, 25)
            probability = min(base_prob + signal_boost, MAX_PROBABILITY)

            # Trader-essential risk metrics
            sharpe_estimate = (
                round((expected_annual_return / 100 - 0.05) / annual_vol, 2)
                if annual_vol > 0
                else 0
            )
            max_drawdown_estimate = round(annual_vol * 100 * 1.5, 1)
            risk_reward_ratio = (
                round(abs(growth_pct) / (annual_vol * 100), 2)
                if annual_vol > 0
                else 0
            )

            return jsonify({
                "data": {
                    "ticker": ticker_upper,
                    "base_price": round(current_price, 2),
                    "target_price": round(target_price, 2),
                    "growth_pct": round(growth_pct, 1),
                    "probability": round(probability, 1),
                    "annual_volatility": round(annual_vol * 100, 1),
                    "months": 6,
                    "daily_volatility": round(daily_vol * 100, 2),
                    "sharpe_estimate": sharpe_estimate,
                    "max_drawdown_estimate": max_drawdown_estimate,
                    "risk_reward_ratio": risk_reward_ratio,
                    "dates": dates,
                    "predicted_prices": predicted,
                    "upper_band": upper,
                    "lower_band": lower,
                },
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as exc:
            logger.error(
                "Forward prediction failed for %s: %s",
                ticker_upper,
                exc,
            )
            return _error_response(
                str(exc),
                "PREDICTION_FAILED",
                502,
            )

    # ------------------------------------------------------------------
    # Task 7: Company info API
    # ------------------------------------------------------------------

    @app.route("/api/company/<ticker>")
    def api_company(ticker):
        """Return company profile and key financial stats."""
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Ticker must be alphanumeric and at most 10 characters",
                "VALIDATION_FAILED",
                400,
            )

        ticker_upper = ticker.upper()

        try:
            info = _get_company_info(ticker_upper)

            # Fetch recent price history for live trading data
            stock = yf.Ticker(ticker_upper)
            hist = stock.history(period="1mo")
            if not hist.empty:
                current_price = round(float(hist["Close"].iloc[-1]), 2)
                prev_close = (
                    round(float(hist["Close"].iloc[-2]), 2)
                    if len(hist) > 1
                    else current_price
                )
                day_change_pct = round(
                    (current_price - prev_close) / prev_close * 100, 2
                )
                volume = int(hist["Volume"].iloc[-1])
                avg_vol_10d = (
                    int(hist["Volume"].tail(10).mean())
                    if len(hist) >= 10
                    else int(hist["Volume"].mean())
                )
                rsi = _calculate_rsi(hist["Close"])
            else:
                current_price = None
                prev_close = None
                day_change_pct = None
                volume = None
                avg_vol_10d = None
                rsi = None

            company = {
                "ticker": ticker_upper,
                "name": info.get(
                    "longName", info.get("shortName", ticker_upper)
                ),
                "description": info.get("longBusinessSummary", ""),
                "description_cn": "",
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": _format_market_cap(info.get("marketCap")),
                "pe_ratio": _safe_round(info.get("trailingPE")),
                "forward_pe": _safe_round(info.get("forwardPE")),
                "dividend_yield": _safe_round(
                    info.get("dividendYield", 0) * 100
                    if info.get("dividendYield")
                    else None,
                ),
                "beta": _safe_round(info.get("beta")),
                "high_52w": _safe_round(info.get("fiftyTwoWeekHigh")),
                "low_52w": _safe_round(info.get("fiftyTwoWeekLow")),
                "avg_volume": info.get("averageVolume"),
                "employees": info.get("fullTimeEmployees"),
                "website": info.get("website", ""),
                "country": info.get("country", ""),
                "current_price": current_price,
                "prev_close": prev_close,
                "day_change_pct": day_change_pct,
                "volume": volume,
                "avg_volume_10d": avg_vol_10d,
                "rsi_14": _safe_round(rsi),
                "revenue": info.get("totalRevenue"),
                "profit_margin": _safe_round(info.get("profitMargins")),
                "debt_to_equity": _safe_round(info.get("debtToEquity")),
                "free_cash_flow": info.get("freeCashflow"),
                "earnings_growth": _safe_round(info.get("earningsGrowth")),
                "revenue_growth": _safe_round(info.get("revenueGrowth")),
            }

            return jsonify({
                "data": company,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as exc:
            logger.error(
                "Company info failed for %s: %s", ticker_upper, exc
            )
            return _error_response(
                f"Failed to get company info for {ticker_upper}",
                "COMPANY_INFO_FAILED",
                502,
            )

    # ------------------------------------------------------------------
    # Task 8: Stock-specific news API
    # ------------------------------------------------------------------

    @app.route("/api/stock-news/<ticker>")
    def api_stock_news(ticker):
        """Return news articles relevant to a specific stock.

        Filters the existing news feed by sector. Falls back to general
        market news when no sector-specific articles are found.
        """
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Ticker must be alphanumeric and at most 10 characters",
                "VALIDATION_FAILED",
                400,
            )

        ticker_upper = ticker.upper()

        # Determine the stock's sector from predictions
        stock_sector = None
        try:
            data = _load_predictions()
            for s in data.get("top_stocks", []):
                if s["ticker"] == ticker_upper:
                    stock_sector = s.get("sector", "")
                    break
        except FileNotFoundError:
            pass

        # Load the news feed
        try:
            news_data = _load_json_file(NEWS_FILE, "News data")
        except FileNotFoundError:
            return jsonify({
                "data": {"ticker": ticker_upper, "articles": []},
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        articles = news_data.get("articles", [])
        relevant = []
        general_fallback_limit = 5

        for article in articles:
            affected = article.get("affected_sectors", [])
            if stock_sector and stock_sector in affected:
                relevant.append(article)
            elif not affected:
                relevant.append(article)

        # Fall back to the top general articles if no sector match
        if not relevant:
            relevant = articles[:general_fallback_limit]

        return jsonify({
            "data": {"ticker": ticker_upper, "articles": relevant},
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    # ------------------------------------------------------------------
    # Task 9: On-demand stock analysis API
    # ------------------------------------------------------------------

    @app.route("/api/analyze/<ticker>", methods=["POST"])
    def api_analyze(ticker):
        """Analyze any stock on demand using technical indicators.

        If the ticker already exists in the predictions file, returns
        the cached result. Otherwise, fetches 6 months of history from
        yfinance and computes momentum, volatility, and trend signals.
        """
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Ticker must be alphanumeric and at most 10 characters",
                "VALIDATION_FAILED",
                400,
            )

        ticker_upper = ticker.upper()

        # Return cached prediction if available
        try:
            data = _load_predictions()
            all_stocks = (
                data.get("top_stocks", [])
                + data.get("single_day_top", [])
            )
            for s in all_stocks:
                if s["ticker"] == ticker_upper:
                    return jsonify({
                        "data": {
                            "ticker": ticker_upper,
                            "status": "already_analyzed",
                            "stock": s,
                        },
                        "error": None,
                        "meta": {
                            "timestamp": datetime.now(
                                timezone.utc
                            ).isoformat(),
                        },
                    })
        except FileNotFoundError:
            pass

        # Perform fresh analysis
        try:
            stock = yf.Ticker(ticker_upper)
            hist = stock.history(period="6mo")
            if hist.empty:
                return _error_response(
                    f"No data for {ticker_upper}",
                    "DATA_NOT_FOUND",
                    404,
                )

            close = hist["Close"]
            returns = close.pct_change().dropna()

            sma_short = float(close.rolling(SMA_SHORT_PERIOD).mean().iloc[-1])
            sma_long = float(close.rolling(SMA_LONG_PERIOD).mean().iloc[-1])
            current = float(close.iloc[-1])

            # Momentum: distance from long-term moving average
            momentum = (
                (current - sma_long) / sma_long if sma_long > 0 else 0
            )

            # Annualized volatility
            vol = float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

            # Composite signal
            short_term_momentum = (
                (current - sma_short) / sma_short if sma_short > 0 else 0
            )
            signal = (
                momentum * MOMENTUM_WEIGHT
                + (1 - vol) * VOLATILITY_WEIGHT
                + short_term_momentum * TREND_WEIGHT
            )

            trend = "up" if current > sma_short else "down"

            info = _get_company_info(ticker_upper)

            analysis = {
                "ticker": ticker_upper,
                "name": info.get(
                    "longName", info.get("shortName", ticker_upper)
                ),
                "current_price": round(current, 2),
                "signal": round(signal, 5),
                "trend": trend,
                "sma_20": round(sma_short, 2),
                "sma_50": round(sma_long, 2),
                "volatility": round(vol * 100, 1),
                "momentum": round(momentum * 100, 1),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "status": "analyzed",
            }

            return jsonify({
                "data": analysis,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as exc:
            logger.error(
                "Analysis failed for %s: %s", ticker_upper, exc
            )
            return _error_response(
                str(exc),
                "ANALYSIS_FAILED",
                502,
            )

    # ------------------------------------------------------------------
    # Task 10: Backtest results API
    # ------------------------------------------------------------------

    @app.route("/api/backtest")
    def api_backtest():
        """Return backtest validation results."""
        try:
            data = _load_json_file(
                BACKTEST_FILE, "Backtest results"
            )
        except FileNotFoundError:
            return jsonify({
                "data": {"status": "not_run", "rounds": []},
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        return jsonify({
            "data": data,
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    # ------------------------------------------------------------------
    # Quality check sub-agent API
    # ------------------------------------------------------------------

    @app.route("/api/quality")
    def api_quality():
        """Return the latest quality check report."""
        try:
            data = _load_json_file(QUALITY_FILE, "Quality report")
        except FileNotFoundError:
            return jsonify({
                "data": {"status": "not_run", "overall_accuracy": 0},
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        return jsonify({
            "data": data,
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    @app.route("/api/quality/run", methods=["POST"])
    def api_quality_run():
        """Trigger quality check sub-agent."""
        if not QUALITY_SCRIPT.exists():
            return _error_response(
                "Quality check script not found",
                "SCRIPT_NOT_FOUND",
                404,
            )

        if not PYTHON_BIN.exists():
            return _error_response(
                f"Python interpreter not found at {PYTHON_BIN}",
                "INTERPRETER_NOT_FOUND",
                500,
            )

        logger.info(
            "Starting quality check via %s", QUALITY_SCRIPT
        )

        try:
            result = subprocess.run(
                [str(PYTHON_BIN), str(QUALITY_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(BASE_DIR),
            )
        except subprocess.TimeoutExpired:
            logger.error("quality_check.py timed out after 5 minutes")
            return _error_response(
                "Quality check timed out",
                "TIMEOUT",
                504,
            )

        is_success = result.returncode == 0

        if not is_success:
            logger.error(
                "quality_check.py failed (exit %d): %s",
                result.returncode,
                result.stderr[-500:] if result.stderr else "no stderr",
            )

        return jsonify({
            "data": {
                "success": is_success,
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            },
            "error": None if is_success else {
                "code": "CHECK_FAILED",
                "message": "Quality check failed",
            },
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }), 200 if is_success else 500

    # ------------------------------------------------------------------
    # Task 11: API configuration status
    # ------------------------------------------------------------------

    @app.route("/api/config/status")
    def api_config_status():
        """Check which external API keys are configured.

        Reads api_keys.json to determine which third-party data sources
        are available. Never exposes the actual key values.
        """
        keys = {}
        if API_KEYS_FILE.exists():
            with open(API_KEYS_FILE, "r", encoding="utf-8") as fh:
                keys = json.load(fh)

        return jsonify({
            "data": {
                "anthropic": bool(keys.get("anthropic")) or bool(os.environ.get("ANTHROPIC_API_KEY")),
                "finnhub": bool(keys.get("finnhub")),
                "fred": bool(keys.get("fred")),
                "newsapi": bool(keys.get("newsapi")),
                "yfinance": True,
            },
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    # ------------------------------------------------------------------
    # Model evolution API
    # ------------------------------------------------------------------

    @app.route("/api/model-evolution")
    def api_model_evolution():
        """Return model evolution history with formulas and testing data."""
        evolution_file = DATA_DIR / "model_evolution.json"
        try:
            data = _load_json_file(evolution_file, "Model evolution data")
        except FileNotFoundError:
            return jsonify({
                "data": {"evolution": [], "formulas": {}},
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        return jsonify({
            "data": data,
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    # ------------------------------------------------------------------
    # Venture Fund Data Sources
    # ------------------------------------------------------------------

    @app.route("/api/fundamentals/<ticker>")
    def api_fundamentals(ticker):
        """Get comprehensive fundamental data for a stock."""
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Invalid ticker", "VALIDATION_FAILED", 400,
            )
        try:
            from data_sources import get_fundamentals
            data = get_fundamentals(ticker.upper())
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Fundamentals failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "FUNDAMENTALS_FAILED", 502)

    @app.route("/api/technicals/<ticker>")
    def api_technicals(ticker):
        """Get advanced technical analysis for a stock."""
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Invalid ticker", "VALIDATION_FAILED", 400,
            )
        period = request.args.get("period", "1y")
        try:
            from data_sources import get_technical_profile
            data = get_technical_profile(ticker.upper(), period)
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Technicals failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "TECHNICALS_FAILED", 502)

    @app.route("/api/market-sentiment")
    def api_market_sentiment():
        """Get market-wide sentiment indicators (VIX, indices, sector rotation)."""
        try:
            from data_sources import get_market_sentiment
            data = get_market_sentiment()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Market sentiment failed: %s", exc)
            return _error_response(str(exc), "SENTIMENT_FAILED", 502)

    @app.route("/api/macro")
    def api_macro():
        """Get macroeconomic indicators from FRED."""
        try:
            from data_sources import get_macro_indicators
            data = get_macro_indicators()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Macro indicators failed: %s", exc)
            return _error_response(str(exc), "MACRO_FAILED", 502)

    @app.route("/api/scan-top50")
    def api_scan_top50():
        """Quick scan of top 50 US stocks with key metrics."""
        try:
            from data_sources import scan_top_50
            stocks = scan_top_50()
            return jsonify({
                "data": {
                    "stocks": stocks,
                    "count": len(stocks),
                },
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Top 50 scan failed: %s", exc)
            return _error_response(str(exc), "SCAN_FAILED", 502)

    @app.route("/api/market-context")
    def api_market_context():
        """Get full market context (macro + sentiment combined)."""
        try:
            from data_sources import get_market_context
            data = get_market_context()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Market context failed: %s", exc)
            return _error_response(str(exc), "CONTEXT_FAILED", 502)

    # ------------------------------------------------------------------
    # AI Analysis (Claude Opus 4.6)
    # ------------------------------------------------------------------

    @app.route("/api/ai-analyze/<ticker>", methods=["POST"])
    def api_ai_analyze(ticker):
        """Run comprehensive AI analysis on a stock using Claude Opus 4.6.

        Aggregates all data sources and sends to Claude for
        venture fund-grade analysis with price targets and recommendations.
        """
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Invalid ticker", "VALIDATION_FAILED", 400,
            )

        ticker_upper = ticker.upper()

        try:
            from data_sources import get_full_stock_profile, get_market_context
            from ai_analyst import analyze_stock

            logger.info("Starting AI analysis for %s", ticker_upper)

            # Gather all data
            stock_data = get_full_stock_profile(ticker_upper)
            market_context = get_market_context()

            # Run AI analysis (language-aware)
            language = request.args.get("lang", "en").lower()
            if language not in ("en", "cn"):
                language = "en"
            analysis = analyze_stock(ticker_upper, stock_data, market_context, language=language)

            return jsonify({
                "data": analysis,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except ValueError as exc:
            # Missing API key
            return _error_response(str(exc), "CONFIG_ERROR", 400)
        except Exception as exc:
            logger.error("AI analysis failed for %s: %s", ticker_upper, exc)
            return _error_response(str(exc), "AI_ANALYSIS_FAILED", 502)

    @app.route("/api/ai-quick/<ticker>", methods=["POST"])
    def api_ai_quick(ticker):
        """Run a quick AI analysis on a stock (lighter, faster)."""
        if not TICKER_PATTERN.match(ticker):
            return _error_response(
                "Invalid ticker", "VALIDATION_FAILED", 400,
            )

        ticker_upper = ticker.upper()

        try:
            from data_sources import get_full_stock_profile
            from ai_analyst import quick_analyze

            stock_data = get_full_stock_profile(ticker_upper)
            language = request.args.get("lang", "en").lower()
            if language not in ("en", "cn"):
                language = "en"
            analysis = quick_analyze(ticker_upper, stock_data, language=language)

            return jsonify({
                "data": analysis,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except ValueError as exc:
            return _error_response(str(exc), "CONFIG_ERROR", 400)
        except Exception as exc:
            logger.error("Quick AI analysis failed for %s: %s", ticker_upper, exc)
            return _error_response(str(exc), "AI_ANALYSIS_FAILED", 502)

    # ------------------------------------------------------------------
    # Options endpoints
    # ------------------------------------------------------------------

    @app.route("/api/options/overview/<ticker>")
    def api_options_overview(ticker):
        """Get options overview with available expirations."""
        try:
            from options_scanner import get_options_overview
            data = get_options_overview(ticker.upper())
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Options scanner not available: %s", exc)
            return _error_response(
                "Options scanner not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Options overview failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "OPTIONS_ERROR", 502)

    @app.route("/api/options/chain/<ticker>")
    def api_options_chain(ticker):
        """Get options chain data."""
        try:
            from options_scanner import get_options_chain_data
            expiration = request.args.get("expiration")
            right = request.args.get("right")  # C or P
            data = get_options_chain_data(
                ticker.upper(), expiration=expiration, right=right,
            )
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Options scanner not available: %s", exc)
            return _error_response(
                "Options scanner not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Options chain failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "OPTIONS_ERROR", 502)

    @app.route("/api/options/flow/<ticker>")
    def api_options_flow(ticker):
        """Get options flow with second-precision timestamps."""
        try:
            from options_scanner import get_options_flow
            data = get_options_flow(ticker.upper())
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Options scanner not available: %s", exc)
            return _error_response(
                "Options scanner not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Options flow failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "OPTIONS_ERROR", 502)

    @app.route("/api/options/strategy", methods=["POST"])
    def api_options_strategy():
        """Build an options strategy."""
        try:
            from options_scanner import build_strategy
            body = request.get_json()
            if not body:
                return _error_response(
                    "Request body required", "VALIDATION_FAILED", 400,
                )
            symbol = body.get("symbol", "").upper()
            strategy_type = body.get("strategy_type", "")
            params = body.get("params", {})
            data = build_strategy(symbol, strategy_type, params)
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Options scanner not available: %s", exc)
            return _error_response(
                "Options scanner not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Options strategy build failed: %s", exc)
            return _error_response(str(exc), "OPTIONS_ERROR", 502)

    @app.route("/api/options/unusual")
    def api_options_unusual():
        """Get unusual options activity across watchlist."""
        try:
            from options_scanner import get_unusual_options
            data = get_unusual_options()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Options scanner not available: %s", exc)
            return _error_response(
                "Options scanner not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Unusual options failed: %s", exc)
            return _error_response(str(exc), "OPTIONS_ERROR", 502)

    # ------------------------------------------------------------------
    # AI analysis with full data transparency
    # ------------------------------------------------------------------

    @app.route("/api/economic-calendar")
    def api_economic_calendar():
        """Get upcoming economic data release dates and events."""
        try:
            from economic_calendar import get_economic_calendar
            days = request.args.get("days", 30, type=int)
            data = get_economic_calendar(days_ahead=days)
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError:
            logger.warning("economic_calendar module not available")
            return _error_response(
                "Economic calendar not available",
                "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Economic calendar failed: %s", exc)
            return _error_response(str(exc), "CALENDAR_ERROR", 502)

    @app.route("/api/stock-events/<ticker>")
    def api_stock_events(ticker):
        """Get upcoming events for a specific stock."""
        try:
            from economic_calendar import get_stock_events
            days = request.args.get("days", 90, type=int)
            data = get_stock_events(ticker.upper(), days_ahead=days)
            return jsonify({
                "data": data,
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError:
            logger.warning("economic_calendar module not available")
            return _error_response(
                "Economic calendar not available",
                "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error("Stock events failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "EVENTS_ERROR", 502)

    @app.route("/api/ai-analyze-full/<ticker>", methods=["POST"])
    def api_ai_analyze_full(ticker):
        """Full AI analysis WITH all input data shown to user."""
        try:
            from data_sources import get_full_stock_profile, get_market_context
            from ai_analyst import analyze_stock

            ticker_upper = ticker.upper()
            stock_data = get_full_stock_profile(ticker_upper)
            market_context = get_market_context()

            # Add upcoming events to context for AI analysis
            try:
                from economic_calendar import (
                    get_economic_calendar,
                    get_stock_events,
                )
                stock_events = get_stock_events(ticker_upper)
                econ_calendar = get_economic_calendar(days_ahead=14)
                stock_data["upcoming_events"] = stock_events
                market_context["upcoming_releases"] = econ_calendar
            except Exception:
                pass

            analysis = analyze_stock(
                ticker_upper, stock_data, market_context,
            )

            # Include the LightGBM model prediction if available
            model_prediction = None
            try:
                predictions = _load_predictions()
                for s in predictions.get("top_stocks", []):
                    if s["ticker"] == ticker_upper:
                        model_prediction = {
                            "signal": s.get("signal"),
                            "consistency": s.get("consistency"),
                            "combined_score": s.get("combined_score"),
                            "rank": s.get("rank"),
                            "trend": s.get("trend"),
                        }
                        break
                if not model_prediction:
                    for s in predictions.get("single_day_top", []):
                        if s["ticker"] == ticker_upper:
                            model_prediction = {
                                "signal": s.get("signal"),
                                "rank": s.get("rank"),
                            }
                            break
            except Exception:
                pass

            return jsonify({
                "data": {
                    "analysis": analysis,
                    "model_prediction": model_prediction,
                    "input_data": {
                        "fundamentals": stock_data.get(
                            "fundamentals", {},
                        ),
                        "technicals": stock_data.get("technicals", {}),
                        "recent_prices": stock_data.get(
                            "recent_prices", [],
                        )[-10:],
                        "macro": market_context.get("macro", {}),
                        "sentiment": market_context.get("sentiment", {}),
                    },
                    "data_sources_used": [
                        {
                            "name": "Yahoo Finance",
                            "type": "fundamentals",
                            "fields": [
                                "income_statement",
                                "balance_sheet",
                                "cash_flow",
                                "ratios",
                                "growth",
                                "analyst_estimates",
                                "insider_transactions",
                                "institutional_holders",
                            ],
                        },
                        {
                            "name": "Yahoo Finance",
                            "type": "technicals",
                            "fields": [
                                "RSI",
                                "MACD",
                                "Bollinger",
                                "ATR",
                                "OBV",
                                "moving_averages",
                                "relative_strength",
                            ],
                        },
                        {
                            "name": "Yahoo Finance",
                            "type": "price_history",
                            "fields": ["OHLCV", "3 months daily"],
                        },
                        {
                            "name": "FRED API",
                            "type": "macro",
                            "fields": [
                                "fed_funds",
                                "treasury_yields",
                                "CPI",
                                "unemployment",
                                "GDP",
                            ],
                        },
                        {
                            "name": "Market Indices",
                            "type": "sentiment",
                            "fields": [
                                "VIX",
                                "S&P500",
                                "NASDAQ",
                                "sector_rotation",
                                "fear_greed",
                            ],
                        },
                        {
                            "name": "LightGBM Alpha158",
                            "type": "model",
                            "fields": (
                                [
                                    "signal",
                                    "consistency",
                                    "combined_score",
                                ]
                                if model_prediction
                                else []
                            ),
                        },
                    ],
                    "upcoming_events": stock_data.get(
                        "upcoming_events", {},
                    ),
                    "historical_data_range": {
                        "fundamentals": "Latest quarterly/annual",
                        "technicals": "1 year daily",
                        "price_history": "3 months daily",
                        "macro": "Latest available",
                    },
                },
                "error": None,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except ImportError as exc:
            logger.error("Analysis module not available: %s", exc)
            return _error_response(
                "Analysis module not available", "MODULE_NOT_FOUND", 500,
            )
        except Exception as exc:
            logger.error(
                "Full AI analysis failed for %s: %s", ticker, exc,
            )
            return _error_response(str(exc), "AI_ANALYSIS_FAILED", 502)

    # ------------------------------------------------------------------
    # Study Cards & Quiz
    # ------------------------------------------------------------------

    @app.route("/api/study/decks")
    def api_study_decks():
        """List available study decks with metadata."""
        try:
            from study_cards import get_decks
            decks = get_decks()
            return jsonify({
                "data": decks,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Failed to load study decks: %s", exc)
            return _error_response(str(exc), "STUDY_ERROR", 500)

    @app.route("/api/study/cards/<deck_id>")
    def api_study_cards(deck_id):
        """Get study cards for a specific deck."""
        try:
            from study_cards import get_cards
            cards = get_cards(deck_id)
            if cards is None:
                return _error_response(
                    f"Deck '{deck_id}' not found",
                    "DECK_NOT_FOUND",
                    404,
                )
            return jsonify({
                "data": {"deck": deck_id, "cards": cards},
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Failed to load study cards: %s", exc)
            return _error_response(str(exc), "STUDY_ERROR", 500)

    @app.route("/api/study/quiz", methods=["POST"])
    def api_study_quiz():
        """Generate a quiz with live stock data questions."""
        try:
            from study_cards import generate_quiz
            body = request.get_json(force=True) or {}
            deck_id = body.get("deck", "technical_analysis")
            num_questions = min(int(body.get("num_questions", 5)), 10)
            quiz = generate_quiz(deck_id, num_questions)
            return jsonify({
                "data": quiz,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Failed to generate quiz: %s", exc)
            return _error_response(str(exc), "QUIZ_ERROR", 500)

    @app.route("/api/study/score", methods=["POST"])
    def api_study_score():
        """Score a completed quiz and update progress."""
        try:
            from study_cards import score_quiz
            body = request.get_json(force=True) or {}
            quiz_id = body.get("quiz_id", "")
            answers = body.get("answers", [])
            result = score_quiz(quiz_id, answers)
            if result is None:
                return _error_response(
                    "Quiz not found or expired",
                    "QUIZ_NOT_FOUND",
                    404,
                )
            return jsonify({
                "data": result,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Failed to score quiz: %s", exc)
            return _error_response(str(exc), "QUIZ_ERROR", 500)

    @app.route("/api/study/progress")
    def api_study_progress():
        """Get cumulative study progress and skill levels."""
        try:
            from study_cards import get_user_progress
            progress = get_user_progress()
            return jsonify({
                "data": progress,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Failed to load study progress: %s", exc)
            return _error_response(str(exc), "STUDY_ERROR", 500)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.route("/health")
    def health():
        """Basic health check for load balancer probes."""
        has_data = PREDICTIONS_FILE.exists()
        return jsonify({
            "status": "healthy" if has_data else "degraded",
            "checks": {
                "predictions_file": "ok" if has_data else "missing",
            },
        })

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    @app.errorhandler(404)
    def handle_not_found(_error):
        return _error_response("Resource not found", "NOT_FOUND", 404)

    @app.errorhandler(500)
    def handle_internal_error(_error):
        logger.exception("Unhandled server error")
        return _error_response(
            "Internal server error",
            "INTERNAL_ERROR",
            500,
        )

    # ---------------------------------------------------------------------------
    # Factor Analysis (Venture Fund Multi-Factor Engine)
    # ---------------------------------------------------------------------------

    @app.route("/api/factors/<ticker>")
    def api_factor_analysis(ticker):
        """Return multi-factor analysis for a ticker (9 factor groups, venture fund grade).

        Includes dynamic regime-adjusted weights, short/medium/long term ratings,
        risk-reward ratio, and market bottom assessment.
        """
        try:
            from factor_engine import get_factor_analysis
            data = get_factor_analysis(ticker.upper().strip())
            return jsonify(data)
        except Exception as exc:
            logger.error("Factor analysis failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "FACTOR_ERROR", 500)

    @app.route("/api/market-regime")
    def api_market_regime():
        """Return current market regime (PANIC/BEAR/RECOVERY/BULL/EUPHORIA)."""
        try:
            from factor_engine import detect_market_regime
            data = detect_market_regime()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Market regime detection failed: %s", exc)
            return _error_response(str(exc), "REGIME_ERROR", 500)

    @app.route("/api/market-bottom")
    def api_market_bottom():
        """Assess whether the market is near a bottom (buying opportunity score 0-100)."""
        try:
            from factor_engine import assess_market_bottom
            data = assess_market_bottom()
            return jsonify({
                "data": data,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Market bottom assessment failed: %s", exc)
            return _error_response(str(exc), "BOTTOM_ERROR", 500)

    @app.route("/api/predict-chart/<ticker>")
    def api_predict_chart(ticker):
        """
        Return historical OHLCV + multi-scenario future price prediction.

        Response:
          historical: list of {time, open, high, low, close, volume}
          prediction: {base, bull, bear} — each list of {time, value}
          levels: {support, resistance, current_price, target_30d, target_60d, target_90d}
          model_signal: float from predictions.json (if available)
          factors: composite factor score
        """
        import datetime as _dt

        try:
            clean_ticker = ticker.upper().strip()

            # --- Historical OHLCV (1 year) ---
            stock = yf.Ticker(clean_ticker)
            hist = stock.history(period="1y")
            if hist.empty:
                return _error_response("No data", "NO_DATA", 404)

            closes = hist["Close"].values.astype(float)
            historical = []
            for idx, row in hist.iterrows():
                dt_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                historical.append({
                    "time": dt_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })

            # --- Trend (linear regression on log prices, last 60 days) ---
            n = min(60, len(closes))
            log_prices = np.log(closes[-n:])
            x = np.arange(n)
            slope, intercept = np.polyfit(x, log_prices, 1)
            daily_trend = float(slope)  # daily log return from trend

            # --- Model signal ---
            model_signal = 0.0
            try:
                pred_path = Path(__file__).parent / "data" / "predictions.json"
                with open(pred_path) as f:
                    preds = json.load(f)
                for s in preds.get("top_stocks", []):
                    if s.get("ticker") == clean_ticker:
                        model_signal = float(s.get("signal", 0))
                        break
            except Exception:
                pass

            # --- Factor composite score ---
            factor_composite = 0.0
            try:
                from factor_engine import get_factor_analysis
                fdata = get_factor_analysis(clean_ticker)
                factor_composite = fdata.get("composite", 0.0)
            except Exception:
                pass

            # --- Future prediction ---
            current_price = float(closes[-1])
            realized_vol = (
                float(np.std(np.diff(np.log(closes[-60:]))) * np.sqrt(252))
                if len(closes) >= 61
                else 0.20
            )

            # Blend: trend + model signal influence + factor boost
            signal_daily_boost = model_signal * 0.002  # scale signal to ~0.2% per day max
            factor_daily_boost = factor_composite * 0.0003
            base_daily_return = daily_trend + signal_daily_boost + factor_daily_boost

            prediction_days = 90
            base = []
            bull = []
            bear = []

            # Get last date of historical data
            last_hist_date = hist.index[-1]
            if hasattr(last_hist_date, "date"):
                last_hist_date = last_hist_date.date()
            else:
                last_hist_date = _dt.date.fromisoformat(str(last_hist_date)[:10])

            for i in range(1, prediction_days + 1):
                future_date = last_hist_date + _dt.timedelta(days=i)
                # Skip weekends
                if future_date.weekday() >= 5:
                    continue
                date_str = future_date.strftime("%Y-%m-%d")
                trading_days = i * (5 / 7)  # approx trading days
                base_price = current_price * np.exp(base_daily_return * trading_days)
                std_band = realized_vol * np.sqrt(trading_days / 252) * current_price
                bull_price = base_price + 1.5 * std_band
                bear_price = base_price - 1.5 * std_band

                base.append({"time": date_str, "value": round(float(base_price), 2)})
                bull.append({"time": date_str, "value": round(float(bull_price), 2)})
                bear.append({"time": date_str, "value": round(float(bear_price), 2)})

            # --- Support / Resistance ---
            window = closes[-min(60, len(closes)):]
            support = round(float(np.percentile(window, 10)), 2)
            resistance = round(float(np.percentile(window, 90)), 2)
            target_30d = round(base[min(21, len(base) - 1)]["value"], 2) if base else current_price
            target_60d = round(base[min(42, len(base) - 1)]["value"], 2) if base else current_price
            target_90d = round(base[-1]["value"], 2) if base else current_price

            return jsonify({
                "ticker": clean_ticker,
                "historical": historical,
                "prediction": {"base": base, "bull": bull, "bear": bear},
                "levels": {
                    "current_price": round(current_price, 2),
                    "support": support,
                    "resistance": resistance,
                    "target_30d": target_30d,
                    "target_60d": target_60d,
                    "target_90d": target_90d,
                    "change_30d_pct": round((target_30d / current_price - 1) * 100, 2),
                    "change_60d_pct": round((target_60d / current_price - 1) * 100, 2),
                    "change_90d_pct": round((target_90d / current_price - 1) * 100, 2),
                },
                "model_signal": model_signal,
                "factor_composite": factor_composite,
                "realized_vol_annual": round(realized_vol * 100, 1),
            })

        except Exception as exc:
            logger.error("predict-chart failed for %s: %s", ticker, exc)
            return _error_response(str(exc), "PREDICT_ERROR", 500)

    # ------------------------------------------------------------------
    # Model 2: Sentiment & Market Agent Predictions
    # ------------------------------------------------------------------

    SENTIMENT_PREDICTIONS_FILE = DATA_DIR / "sentiment_predictions.json"
    _sentiment_cache = {}
    _sentiment_cache_expiry = 0.0
    SENTIMENT_CACHE_TTL = 1800  # 30 minutes

    @app.route("/api/model2/predictions")
    def api_model2_predictions():
        """Return Model 2 (Sentiment Agent) predictions.

        Loads cached results from sentiment_predictions.json.
        If no cached data exists, returns empty predictions.
        """
        nonlocal _sentiment_cache, _sentiment_cache_expiry
        now = time.time()
        if _sentiment_cache and now < _sentiment_cache_expiry:
            return jsonify({
                "data": _sentiment_cache,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })

        try:
            if SENTIMENT_PREDICTIONS_FILE.exists():
                with open(SENTIMENT_PREDICTIONS_FILE, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                # Return the latest run results
                if isinstance(raw, dict) and "predictions" in raw:
                    _sentiment_cache = raw
                    _sentiment_cache_expiry = now + SENTIMENT_CACHE_TTL
                    return jsonify({
                        "data": raw,
                        "error": None,
                        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
                    })
                # Legacy format: list of past predictions
                return jsonify({
                    "data": {
                        "model_name": "Sentiment & Market Agent",
                        "predictions": [],
                        "post_mortem": raw if isinstance(raw, list) else [],
                    },
                    "error": None,
                    "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
                })
        except Exception as exc:
            logger.error("Model 2 predictions load failed: %s", exc)

        return jsonify({
            "data": {
                "model_name": "Sentiment & Market Agent",
                "predictions": [],
                "scan_results": {"total_scanned": 0, "shortlisted": 0},
                "post_mortem": {"total_past": 0, "hit_rate": 0, "avg_return": 0},
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/model2/scan", methods=["POST"])
    def api_model2_scan():
        """Run the full Model 2 sentiment scan pipeline.

        This triggers the 5-step pipeline:
        1. Scan for anomalies
        2. Research shortlisted tickers
        3. Predict edge
        4. Size positions
        5. Record post-mortem
        """
        try:
            from sentiment_predictor import run_sentiment_scan
            results = run_sentiment_scan()
            # Clear cache to force reload
            nonlocal _sentiment_cache, _sentiment_cache_expiry
            _sentiment_cache = results
            _sentiment_cache_expiry = time.time() + SENTIMENT_CACHE_TTL
            return jsonify({
                "data": results,
                "error": None,
                "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as exc:
            logger.error("Model 2 scan failed: %s", exc)
            return _error_response(str(exc), "MODEL2_SCAN_FAILED", 502)

    @app.route("/api/models/compare")
    def api_models_compare():
        """Compare predictions from both models side-by-side.

        Returns Model 1 (LightGBM) and Model 2 (Sentiment Agent)
        predictions merged by ticker for easy comparison.
        """
        model1 = {}
        model2 = {}

        # Load Model 1
        try:
            data = _load_predictions()
            for stock in data.get("top_stocks", []):
                model1[stock["ticker"]] = {
                    "signal": stock.get("signal", 0),
                    "consistency": stock.get("consistency", 0),
                    "trend": stock.get("trend", ""),
                    "combined_score": stock.get("combined_score", 0),
                }
        except FileNotFoundError:
            pass

        # Load Model 2
        try:
            if SENTIMENT_PREDICTIONS_FILE.exists():
                with open(SENTIMENT_PREDICTIONS_FILE, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                for pred in (raw.get("predictions") or []):
                    model2[pred["ticker"]] = {
                        "direction": pred.get("direction", ""),
                        "edge_pct": pred.get("edge_pct", 0),
                        "confidence": pred.get("confidence", 0),
                        "sentiment_score": pred.get("sentiment_score", 0),
                        "risk_reward": pred.get("risk_reward", 0),
                    }
        except Exception:
            pass

        # Merge
        all_tickers = sorted(set(list(model1.keys()) + list(model2.keys())))
        comparison = []
        for ticker in all_tickers:
            entry = {"ticker": ticker}
            if ticker in model1:
                entry["model1"] = model1[ticker]
            if ticker in model2:
                entry["model2"] = model2[ticker]
            # Agreement check
            if ticker in model1 and ticker in model2:
                m1_bullish = model1[ticker].get("trend") == "up"
                m2_bullish = model2[ticker].get("direction") == "LONG"
                entry["models_agree"] = m1_bullish == m2_bullish
            comparison.append(entry)

        return jsonify({
            "data": {
                "comparison": comparison,
                "model1_count": len(model1),
                "model2_count": len(model2),
                "both_models": len([c for c in comparison if "model1" in c and "model2" in c]),
            },
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Live Trading Monitor
    # ------------------------------------------------------------------

    _monitor_engine = None

    def _get_monitor():
        nonlocal _monitor_engine
        if _monitor_engine is None:
            from monitor import MonitorEngine
            _monitor_engine = MonitorEngine()
            _monitor_engine.start()
            logger.info("Monitor engine started")
        return _monitor_engine

    @app.route("/monitor")
    def monitor_page():
        """Serve the live trading monitor page."""
        return render_template("monitor.html")

    @app.route("/api/monitor/stream")
    def monitor_stream():
        """SSE stream of real-time stock updates."""
        engine = _get_monitor()

        def generate():
            for event in engine.stream_updates():
                yield event

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.route("/api/monitor/states")
    def monitor_states():
        """Return current state of all monitored stocks."""
        engine = _get_monitor()
        return jsonify({
            "data": engine.get_states(),
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/monitor/config", methods=["GET", "POST"])
    def monitor_config():
        """Get or update the watchlist."""
        engine = _get_monitor()
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            tickers = body.get("tickers", [])
            if tickers and isinstance(tickers, list):
                engine.set_watchlist([t.upper().strip() for t in tickers[:12]])
            return jsonify({
                "data": {"watchlist": engine.watchlist},
                "error": None,
            })
        return jsonify({
            "data": {"watchlist": engine.watchlist},
            "error": None,
        })

    # ------------------------------------------------------------------
    # Alt Data Routes (Fintel + Quiver + Finnhub)
    # ------------------------------------------------------------------

    @app.route("/api/alt-data/<ticker>")
    def api_alt_data(ticker):
        """Aggregated alternative data: short interest, insider, congressional, dark pool."""
        from data_providers import get_alt_data
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        alt = get_alt_data(ticker)
        if not alt:
            return _error_response(f"No alt data for {ticker}", "DATA_NOT_FOUND", 404)
        return jsonify({
            "data": alt,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/short-interest/<ticker>")
    def api_short_interest(ticker):
        """Short interest data from Fintel."""
        from data_providers import get_short_interest
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        data = get_short_interest(ticker)
        if not data:
            return _error_response(f"No short interest data for {ticker}", "DATA_NOT_FOUND", 404)
        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/insider-trades/<ticker>")
    def api_insider_trades(ticker):
        """Insider trading data from Fintel."""
        from data_providers import get_insider_trades
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        data = get_insider_trades(ticker)
        if not data:
            return _error_response(f"No insider data for {ticker}", "DATA_NOT_FOUND", 404)
        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/congressional/<ticker>")
    def api_congressional(ticker):
        """Congressional trading data from Quiver Quant."""
        from data_providers import get_congressional_trades
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        data = get_congressional_trades(ticker)
        if not data:
            return _error_response(f"No congressional data for {ticker}", "DATA_NOT_FOUND", 404)
        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/dark-pool/<ticker>")
    def api_dark_pool(ticker):
        """Dark pool volume data from Quiver Quant."""
        from data_providers import get_dark_pool
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        data = get_dark_pool(ticker)
        if not data:
            return _error_response(f"No dark pool data for {ticker}", "DATA_NOT_FOUND", 404)
        return jsonify({
            "data": data,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/news-enhanced")
    def api_news_enhanced():
        """Enhanced news with Finnhub sentiment scores."""
        from data_providers import get_provider
        ticker = request.args.get('ticker', 'AAPL').upper().strip()
        limit = min(int(request.args.get('limit', 30)), 100)

        finnhub = get_provider('finnhub')
        articles = []
        if finnhub and finnhub.is_available():
            articles = finnhub.get_news(ticker, limit) or []

        # Get sentiment scores
        sentiment_data = None
        if finnhub and finnhub.is_available():
            sentiment_data = finnhub.get_sentiment(ticker)

        return jsonify({
            "data": {
                "articles": articles,
                "sentiment": sentiment_data,
                "ticker": ticker,
            },
            "error": None,
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "finnhub",
                "count": len(articles),
            },
        })

    @app.route("/api/economic-calendar-enhanced")
    def api_economic_calendar_enhanced():
        """Economic calendar from Finnhub (enhanced provider)."""
        from data_providers import get_calendar
        days = min(int(request.args.get('days', 7)), 30)
        data = get_calendar(days)
        return jsonify({
            "data": data or [],
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ------------------------------------------------------------------
    # Data Provider Status
    # ------------------------------------------------------------------

    @app.route("/api/providers")
    def api_providers():
        """Health check for all configured data providers."""
        from data_providers import provider_status
        return jsonify({
            "data": provider_status(),
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    @app.route("/api/quote/<ticker>")
    def api_quote(ticker):
        """Get latest quote from best available provider."""
        from data_providers import get_quote
        ticker = ticker.upper().strip()
        if not TICKER_PATTERN.match(ticker):
            return _error_response("Invalid ticker", "INVALID_TICKER", 400)
        quote = get_quote(ticker)
        if not quote:
            return _error_response(
                f"No quote data for {ticker}", "DATA_NOT_FOUND", 404,
            )
        return jsonify({
            "data": quote,
            "error": None,
            "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })

    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)
