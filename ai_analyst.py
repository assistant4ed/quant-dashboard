"""
AI Stock Analyst powered by Claude Opus 4.6 via OpenRouter.

Provides deep, venture fund-grade stock analysis by combining
all available data sources and sending them to Claude for
comprehensive evaluation and price prediction.

Supports two backends:
1. OpenRouter (preferred) - access to Claude and other models
2. Anthropic direct API (fallback)
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

import requests as http_requests

logger = logging.getLogger("ai_analyst")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "anthropic/claude-opus-4"
MAX_TOKENS = 4096
CACHE_TTL = 900  # 15 minutes
TEMPERATURE = 0.3

_analysis_cache = {}
_cache_expiry = {}


def _load_api_keys():
    """Load API keys from config file."""
    keys_file = os.path.join(os.path.dirname(__file__), "data", "api_keys.json")
    if os.path.exists(keys_file):
        with open(keys_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _get_openrouter_key():
    """Get OpenRouter API key from env or config."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        keys = _load_api_keys()
        key = keys.get("openrouter", "")
    return key


def _get_anthropic_key():
    """Get Anthropic API key from env or config."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        keys = _load_api_keys()
        key = keys.get("anthropic", "")
    return key


def _call_ai(system_prompt, user_prompt, max_tokens=MAX_TOKENS):
    """Call AI model via OpenRouter (preferred) or Anthropic direct.

    Returns (response_text, model_used, usage_dict).
    """
    errors = []

    # Try OpenRouter first
    or_key = _get_openrouter_key()
    if or_key:
        try:
            return _call_openrouter(or_key, system_prompt, user_prompt, max_tokens)
        except Exception as exc:
            logger.warning("OpenRouter failed, falling back to Anthropic: %s", exc)
            errors.append(f"OpenRouter: {exc}")

    # Fallback to Anthropic direct
    anthropic_key = _get_anthropic_key()
    if anthropic_key:
        try:
            return _call_anthropic(anthropic_key, system_prompt, user_prompt, max_tokens)
        except Exception as exc:
            logger.error("Anthropic direct API also failed: %s", exc)
            errors.append(f"Anthropic: {exc}")

    if errors:
        raise ValueError(f"All AI backends failed: {'; '.join(errors)}")

    raise ValueError(
        "No AI API key found. Add 'openrouter' or 'anthropic' key to "
        "data/api_keys.json, or set OPENROUTER_API_KEY / ANTHROPIC_API_KEY env var."
    )


def _call_openrouter(api_key, system_prompt, user_prompt, max_tokens):
    """Call Claude via OpenRouter API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5001",
        "X-Title": "Quant Stock Predictor",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    resp = http_requests.post(
        OPENROUTER_BASE_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"OpenRouter error: {data['error']}")

    text = data["choices"][0]["message"]["content"]
    model_used = data.get("model", OPENROUTER_MODEL)
    usage = data.get("usage", {})

    return text, model_used, {
        "input": usage.get("prompt_tokens", 0),
        "output": usage.get("completion_tokens", 0),
    }


def _call_anthropic(api_key, system_prompt, user_prompt, max_tokens):
    """Call Claude via Anthropic direct API."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = response.content[0].text
    return text, "claude-opus-4-6", {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }


# ---------------------------------------------------------------------------
# Core Analysis Function
# ---------------------------------------------------------------------------

def analyze_stock(ticker, stock_data, market_context, language="en"):
    """Run comprehensive AI analysis on a stock using Claude Opus 4.6.

    Args:
        ticker: Stock ticker symbol
        stock_data: Full stock profile from data_sources.get_full_stock_profile()
        market_context: Market context from data_sources.get_market_context()
        language: Output language — 'en' (default) or 'cn' (Simplified Chinese)

    Returns:
        Dict with AI analysis including outlook, risks, price targets, etc.
    """
    now = time.time()
    cache_key = f"{ticker.upper()}:{language}"
    if cache_key in _analysis_cache and now < _cache_expiry.get(cache_key, 0):
        return _analysis_cache[cache_key]

    prompt = _build_analysis_prompt(ticker, stock_data, market_context)
    system = _build_system_prompt(language)

    try:
        raw_text, model_used, usage = _call_ai(system, prompt)

        analysis = _parse_analysis(raw_text, ticker)
        analysis["raw_analysis"] = raw_text
        analysis["model"] = model_used
        analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        analysis["tokens_used"] = usage

        _analysis_cache[cache_key] = analysis
        _cache_expiry[cache_key] = now + CACHE_TTL

        return analysis

    except Exception as exc:
        logger.error("Analysis failed for %s: %s", ticker, exc)
        return {
            "ticker": ticker,
            "error": str(exc),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Quick Analysis (lighter, faster)
# ---------------------------------------------------------------------------

def quick_analyze(ticker, stock_data, language="en"):
    """Run a faster, lighter AI analysis without full market context."""
    fundamentals = stock_data.get("fundamentals", {})
    technicals = stock_data.get("technicals", {})

    prompt = f"""Analyze {ticker} quickly based on this data:

**Key Ratios:** PE={fundamentals.get('ratios', {}).get('pe_trailing')}, \
PEG={fundamentals.get('ratios', {}).get('peg_ratio')}, \
P/B={fundamentals.get('ratios', {}).get('price_to_book')}, \
EV/EBITDA={fundamentals.get('ratios', {}).get('ev_to_ebitda')}, \
Debt/Equity={fundamentals.get('ratios', {}).get('debt_to_equity')}

**Growth:** Rev Growth={fundamentals.get('growth', {}).get('revenue_growth')}, \
Earnings Growth={fundamentals.get('growth', {}).get('earnings_growth')}

**Technical:** Price=${technicals.get('current_price')}, \
RSI={technicals.get('rsi_14')}, Trend={technicals.get('trend_strength')}, \
RS vs SP500={technicals.get('relative_strength_vs_sp500')}

**Analyst Targets:** Mean=${fundamentals.get('analyst_estimates', {}).get('target_mean')}, \
Recommendation={fundamentals.get('analyst_estimates', {}).get('recommendation')}

Give a concise 3-sentence outlook with a BUY/HOLD/SELL rating and confidence (1-10)."""

    lang_note = "用中文（简体）回答所有内容。" if language == "cn" else ""
    system = f"You are a senior quantitative analyst. Be concise and data-driven. {lang_note}".strip()

    try:
        text, model_used, _ = _call_ai(
            system,
            prompt,
            max_tokens=500,
        )
        return {
            "ticker": ticker,
            "quick_analysis": text,
            "model": model_used,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Quick analysis failed for %s: %s", ticker, exc)
        return {"ticker": ticker, "error": str(exc)}


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(language="en"):
    """Return the system prompt, optionally with a Chinese language instruction."""
    lang_suffix = (
        "\n\n重要提示：请用中文（简体）回答所有文本字段，包括summary、key_catalysts、"
        "key_risks、sector_outlook、entry_strategy、exit_strategy、position_sizing、"
        "growth_assessment和detailed_analysis中的所有内容。JSON结构保持不变，"
        "但所有描述性文字必须使用中文。"
        if language == "cn"
        else ""
    )
    return SYSTEM_PROMPT + lang_suffix


SYSTEM_PROMPT = """You are a senior quantitative analyst at a top-tier venture fund. \
You analyze stocks using the same rigor and data sources as Renaissance Technologies, \
Two Sigma, and Bridgewater Associates.

Your analysis framework covers:
1. **Fundamental Analysis**: Valuation ratios, growth metrics, profitability, balance sheet health
2. **Technical Analysis**: Trend, momentum, volatility, support/resistance levels
3. **Macro Environment**: Interest rates, inflation, economic cycle impact on the sector
4. **Sentiment & Flow**: Insider activity, institutional holdings, analyst consensus
5. **Risk Assessment**: Downside scenarios, key risks, position sizing guidance

You MUST respond in this exact JSON structure:
{
  "rating": "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL",
  "confidence": <1-10>,
  "summary": "<2-3 sentence executive summary with specific price levels and % targets>",
  "price_targets": {
    "bull_case": <price>,
    "base_case": <price>,
    "bear_case": <price>,
    "timeframe": "6 months"
  },
  "fundamental_score": <1-10>,
  "technical_score": <1-10>,
  "sentiment_score": <1-10>,
  "risk_score": <1-10 where 10 is highest risk>,
  "key_catalysts": ["<catalyst 1 with specific data>", "<catalyst 2>", "<catalyst 3>"],
  "key_risks": ["<risk 1 with specific data>", "<risk 2>", "<risk 3>"],
  "sector_outlook": "<bullish/neutral/bearish with reasoning>",
  "entry_strategy": "<specific price levels, when and how to enter>",
  "exit_strategy": "<specific stop loss price and take profit price levels>",
  "position_sizing": "<recommended allocation as % of portfolio>",
  "growth_assessment": {
    "historical_revenue_growth": "<e.g. 15% YoY based on last 4 quarters>",
    "historical_earnings_growth": "<e.g. 22% YoY>",
    "predicted_growth_next_12m": "<e.g. 12-18% based on analyst consensus and model>",
    "growth_rationale": "<2-3 sentences explaining WHY growth will accelerate/decelerate, referencing specific data points like revenue trends, margin expansion, new products, market share>",
    "model_signal_interpretation": "<explain what the LightGBM model signal means for this stock - whether the quantitative model agrees with fundamental analysis and why>"
  },
  "detailed_analysis": {
    "fundamentals": "<paragraph explaining valuation rationale - reference specific P/E, PEG, margins, compare to sector averages, explain whether premium is justified by growth>",
    "technicals": "<paragraph explaining chart setup - reference specific RSI value, MACD crossover status, support/resistance levels from moving averages, Bollinger band position>",
    "macro_impact": "<paragraph explaining how current interest rates, inflation, GDP affect THIS specific stock's business model and valuation>",
    "insider_institutional": "<paragraph on what insider buys/sells and institutional changes signal about the stock>"
  }
}

Rules:
- ALWAYS cite specific numbers from the data. Say "$245.50 P/E of 32.1x" not just "high valuation".
- Explain the RATIONALE behind each score. Why is fundamental score 7/10? What specific data drives it?
- Compare current metrics to historical averages to show trajectory.
- Reference the LightGBM model signal and explain whether quantitative model agrees with your assessment.
- Factor in upcoming events (earnings dates, FOMC, CPI) in your entry timing.
- Show how current data compares to historical patterns to predict growth.
- Provide actionable entry/exit levels based on technical analysis with specific price levels.
- Never recommend more than 5% portfolio allocation for a single stock.
- This is NOT financial advice - it is quantitative analysis for research purposes."""


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def _build_analysis_prompt(ticker, stock_data, market_context):
    """Build the full analysis prompt with all available data."""
    fundamentals = stock_data.get("fundamentals", {})
    technicals = stock_data.get("technicals", {})
    prices = stock_data.get("recent_prices", [])
    macro = market_context.get("macro", {})
    sentiment = market_context.get("sentiment", {})

    sections = []

    sections.append(f"# Full Analysis Request: {ticker}")
    sections.append(f"\n## Company: {fundamentals.get('name', ticker)}")
    sections.append(f"Sector: {fundamentals.get('sector', 'N/A')} | "
                    f"Industry: {fundamentals.get('industry', 'N/A')}")

    ratios = fundamentals.get("ratios", {})
    growth = fundamentals.get("growth", {})
    income = fundamentals.get("income_statement", {})
    balance = fundamentals.get("balance_sheet", {})
    cashflow = fundamentals.get("cash_flow", {})

    sections.append(f"""
## Fundamental Data

**Valuation Ratios:**
- P/E (TTM): {ratios.get('pe_trailing')}
- P/E (Forward): {ratios.get('pe_forward')}
- PEG Ratio: {ratios.get('peg_ratio')}
- Price/Book: {ratios.get('price_to_book')}
- Price/Sales: {ratios.get('price_to_sales')}
- EV/EBITDA: {ratios.get('ev_to_ebitda')}
- EV/Revenue: {ratios.get('ev_to_revenue')}
- Market Cap: {ratios.get('market_cap')}
- Enterprise Value: {ratios.get('enterprise_value')}

**Profitability:**
- Gross Margin: {ratios.get('gross_margin')}
- Operating Margin: {ratios.get('operating_margin')}
- Profit Margin: {ratios.get('profit_margin')}
- ROE: {ratios.get('roe')}
- ROA: {ratios.get('roa')}

**Growth:**
- Revenue Growth: {growth.get('revenue_growth')}
- Earnings Growth: {growth.get('earnings_growth')}
- Quarterly Earnings Growth: {growth.get('earnings_quarterly_growth')}

**Balance Sheet Health:**
- Debt/Equity: {ratios.get('debt_to_equity')}
- Current Ratio: {ratios.get('current_ratio')}
- Quick Ratio: {ratios.get('quick_ratio')}
- Total Debt: {balance.get('total_debt')}
- Cash: {balance.get('cash_and_equivalents')}
- Total Equity: {balance.get('total_equity')}

**Cash Flow:**
- Operating CF: {cashflow.get('operating_cash_flow')}
- Free CF: {cashflow.get('free_cash_flow')}
- CapEx: {cashflow.get('capital_expenditure')}
- Buybacks: {cashflow.get('share_buyback')}
- Dividends: {cashflow.get('dividends_paid')}

**Income Statement:**
- Revenue: {income.get('total_revenue')}
- Net Income: {income.get('net_income')}
- EBITDA: {income.get('ebitda')}
- EPS: {income.get('eps_diluted')}

**Short Interest:**
- Short Ratio: {ratios.get('short_ratio')}
- Short % Float: {ratios.get('short_pct_float')}
- Beta: {ratios.get('beta')}
""")

    analysts = fundamentals.get("analyst_estimates", {})
    sections.append(f"""
## Analyst Estimates
- Target Mean: ${analysts.get('target_mean')}
- Target High: ${analysts.get('target_high')}
- Target Low: ${analysts.get('target_low')}
- Recommendation: {analysts.get('recommendation')}
- Recommendation Score: {analysts.get('recommendation_mean')} (1=Strong Buy, 5=Sell)
- Number of Analysts: {analysts.get('num_analysts')}
""")

    insiders = fundamentals.get("insider_transactions", [])
    if insiders:
        sections.append("\n## Recent Insider Transactions")
        for txn in insiders[:5]:
            sections.append(
                f"- {txn.get('name', 'Unknown')} ({txn.get('relation', '')}): "
                f"{txn.get('transaction', '')} {txn.get('shares', '')} shares "
                f"(${txn.get('value', 'N/A')}) on {txn.get('date', '')}"
            )

    institutions = fundamentals.get("institutional_holders", [])
    if institutions:
        sections.append("\n## Top Institutional Holders")
        for inst in institutions[:5]:
            sections.append(
                f"- {inst.get('holder', 'Unknown')}: "
                f"{inst.get('shares', '')} shares "
                f"({inst.get('pct_held', '')}% of float)"
            )

    earnings = fundamentals.get("earnings_history", [])
    if earnings:
        sections.append("\n## Earnings History (Recent)")
        for e in earnings[:4]:
            sections.append(
                f"- {e.get('date', '')}: Est ${e.get('eps_estimate', 'N/A')} "
                f"vs Actual ${e.get('eps_actual', 'N/A')} "
                f"(Surprise: {e.get('surprise_pct', 'N/A')}%)"
            )

    sections.append(f"""
## Technical Analysis
- Current Price: ${technicals.get('current_price')}
- RSI (14): {technicals.get('rsi_14')}
- Trend Strength: {technicals.get('trend_strength')}
- Relative Strength vs S&P 500 (20d): {technicals.get('relative_strength_vs_sp500')}

**Moving Averages:**
{json.dumps(technicals.get('moving_averages', {}), indent=2)}

**MACD:**
{json.dumps(technicals.get('macd', {}), indent=2)}

**Bollinger Bands:**
{json.dumps(technicals.get('bollinger_bands', {}), indent=2)}

**Volatility:**
{json.dumps(technicals.get('volatility', {}), indent=2)}

**52-Week Range:**
{json.dumps(technicals.get('range_52w', {}), indent=2)}

**ATR (14):** {technicals.get('atr_14')}
**OBV Trend:** {technicals.get('obv_trend')}
**MA Signals:** {technicals.get('ma_signals')}
""")

    if prices:
        sections.append("\n## Recent 10-Day Prices")
        for p in prices[-10:]:
            sections.append(f"- {p['date']}: ${p['close']} (Vol: {p['volume']:,})")

    macro_indicators = macro.get("indicators", {})
    sections.append(f"""
## Macroeconomic Environment
- Fed Funds Rate: {macro_indicators.get('fed_funds_rate')}%
- 10Y Treasury: {macro_indicators.get('treasury_10y')}%
- 2Y Treasury: {macro_indicators.get('treasury_2y')}%
- Yield Curve Spread: {macro_indicators.get('yield_curve_spread')}
- Yield Curve Inverted: {macro_indicators.get('yield_curve_inverted')}
- CPI YoY: {macro_indicators.get('cpi_yoy')}%
- Unemployment: {macro_indicators.get('unemployment')}%
- GDP Growth: {macro_indicators.get('gdp_growth')}%
- Consumer Sentiment: {macro_indicators.get('consumer_sentiment')}
""")

    sections.append(f"""
## Market Sentiment
- VIX: {sentiment.get('vix')} ({sentiment.get('vix_regime', 'N/A')})
- S&P 500: {sentiment.get('sp500_price')} ({sentiment.get('sp500_change_pct', 0)}%)
- NASDAQ: {sentiment.get('nasdaq_price')} ({sentiment.get('nasdaq_change_pct', 0)}%)
- Fear/Greed Score: {sentiment.get('fear_greed_score')} ({sentiment.get('fear_greed_label', 'N/A')})
""")

    rotation = sentiment.get("sector_rotation", {})
    if rotation:
        sections.append("\n## Sector Rotation (Monthly Returns)")
        for sector, data in sorted(
            rotation.items(),
            key=lambda x: x[1].get("month_return", 0),
            reverse=True,
        ):
            sections.append(
                f"- {sector}: {data.get('month_return', 0)}% "
                f"(week: {data.get('week_return', 0)}%)"
            )

    # Upcoming stock-specific events
    upcoming = stock_data.get("upcoming_events", {})
    if upcoming:
        events_list = upcoming.get("events", [])
        if events_list:
            sections.append("\n## Upcoming Stock Events")
            for evt in events_list[:10]:
                sections.append(
                    f"- {evt.get('date', 'TBD')}: {evt.get('event', '')} "
                    f"(Importance: {evt.get('importance', 'N/A')})"
                )
        next_earnings = upcoming.get("next_earnings")
        if next_earnings:
            sections.append(
                f"\n**Next Earnings:** {next_earnings.get('date', 'TBD')} "
                f"(in {upcoming.get('days_to_earnings', '?')} days)"
            )
        ex_div = upcoming.get("ex_dividend_date")
        if ex_div:
            sections.append(f"**Ex-Dividend Date:** {ex_div}")

    # Upcoming macro data releases
    releases = market_context.get("upcoming_releases", {})
    if releases:
        this_week = releases.get("this_week", [])
        next_major = releases.get("next_major")
        if this_week or next_major:
            sections.append("\n## Upcoming Economic Data Releases")
            if next_major:
                sections.append(
                    f"**Next Major Release:** {next_major.get('event', '')} "
                    f"on {next_major.get('date', '')} "
                    f"(Previous: {next_major.get('previous', 'N/A')})"
                )
            if this_week:
                sections.append("**This Week:**")
                for rel in this_week[:7]:
                    sections.append(
                        f"- {rel.get('date', '')}: {rel.get('event', '')} "
                        f"(Prev: {rel.get('previous', 'N/A')}, "
                        f"Forecast: {rel.get('forecast', 'N/A')})"
                    )

    sections.append(
        "\n\nProvide your complete analysis in the JSON format specified. "
        "Be specific with price targets and entry/exit levels. "
        "Factor in upcoming data releases and earnings dates in your "
        "entry timing and risk assessment."
    )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Response Parser
# ---------------------------------------------------------------------------

def _parse_analysis(raw_text, ticker):
    """Parse the AI response, extracting JSON if present."""
    try:
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = raw_text[json_start:json_end]
            parsed = json.loads(json_str)
            parsed["ticker"] = ticker
            return parsed
    except json.JSONDecodeError:
        pass

    return {
        "ticker": ticker,
        "rating": "HOLD",
        "confidence": 5,
        "summary": raw_text[:500],
        "parse_error": "Could not parse structured response",
    }
