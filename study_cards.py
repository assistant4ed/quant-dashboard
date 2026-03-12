"""
Trading education module with study cards and quizzes.

Provides flashcard decks covering technical analysis, fundamental analysis,
options trading, risk management, market mechanics, and macroeconomics.
Quizzes pull live stock data via yfinance (with data_sources.py fallback) to
generate contextual questions grounded in real market conditions.
"""
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

logger = logging.getLogger("study_cards")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROGRESS_FILE = DATA_DIR / "study_progress.json"

# In-memory store for generated quizzes so score_quiz can look them up
_active_quizzes: dict[str, dict] = {}

# TTL for active quizzes (seconds) - quizzes older than 1 hour are evicted
QUIZ_TTL_SECONDS = 3600

# Grading thresholds (percentage -> letter grade)
GRADE_THRESHOLDS = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]

# Skill-level thresholds (accuracy percentage -> label)
SKILL_THRESHOLDS = [
    (80, "advanced"),
    (60, "intermediate"),
    (0, "beginner"),
]

# Popular tickers for live-data quiz question generation
QUIZ_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "TSLA",
    "GOOGL", "META", "JPM", "V", "AVGO",
]


# ---------------------------------------------------------------------------
# Study card decks
# ---------------------------------------------------------------------------

def _build_technical_analysis_deck():
    """Build the technical analysis study card deck."""
    return [
        {
            "id": "ta_rsi_01",
            "deck": "technical_analysis",
            "front": "What does the Relative Strength Index (RSI) measure, and what are the standard overbought/oversold thresholds?",
            "back": "RSI measures the speed and magnitude of recent price changes on a 0-100 scale. Readings above 70 indicate overbought conditions; below 30 indicates oversold. The standard period is 14 days.",
            "difficulty": 1,
            "tags": ["rsi", "momentum", "oscillator"],
        },
        {
            "id": "ta_rsi_02",
            "deck": "technical_analysis",
            "front": "What is RSI divergence, and why is it significant?",
            "back": "RSI divergence occurs when price makes a new high/low but RSI does not confirm it. Bearish divergence (price higher high, RSI lower high) warns of potential reversal downward. Bullish divergence (price lower low, RSI higher low) suggests upward reversal. It signals weakening momentum.",
            "difficulty": 2,
            "tags": ["rsi", "divergence", "reversal"],
        },
        {
            "id": "ta_macd_01",
            "deck": "technical_analysis",
            "front": "What are the three components of MACD, and how is each calculated?",
            "back": "1) MACD Line: 12-period EMA minus 26-period EMA. 2) Signal Line: 9-period EMA of the MACD Line. 3) Histogram: MACD Line minus Signal Line. A bullish signal occurs when the MACD line crosses above the signal line.",
            "difficulty": 1,
            "tags": ["macd", "moving_average", "trend"],
        },
        {
            "id": "ta_macd_02",
            "deck": "technical_analysis",
            "front": "What is MACD histogram divergence, and how does it differ from a standard MACD crossover?",
            "back": "Histogram divergence happens when the histogram starts shrinking while price continues trending, signaling momentum loss before the actual MACD crossover. It provides earlier warning than a crossover signal, but generates more false signals.",
            "difficulty": 3,
            "tags": ["macd", "divergence", "histogram"],
        },
        {
            "id": "ta_ma_01",
            "deck": "technical_analysis",
            "front": "What is the difference between a Simple Moving Average (SMA) and an Exponential Moving Average (EMA)?",
            "back": "SMA gives equal weight to all periods. EMA gives exponentially more weight to recent prices, making it more responsive to new data. EMA reacts faster to price changes but is more prone to whipsaws. Traders often use EMA for short-term and SMA for long-term trends.",
            "difficulty": 1,
            "tags": ["moving_average", "sma", "ema"],
        },
        {
            "id": "ta_ma_02",
            "deck": "technical_analysis",
            "front": "What is a Golden Cross, and what is a Death Cross?",
            "back": "A Golden Cross occurs when the 50-day SMA crosses above the 200-day SMA, signaling a potential long-term bullish trend. A Death Cross is the opposite: the 50-day crosses below the 200-day, signaling a potential bearish trend. Both are lagging indicators.",
            "difficulty": 2,
            "tags": ["moving_average", "golden_cross", "death_cross"],
        },
        {
            "id": "ta_bb_01",
            "deck": "technical_analysis",
            "front": "How are Bollinger Bands constructed, and what do they indicate?",
            "back": "Bollinger Bands use a 20-period SMA as the middle band, with upper and lower bands at +/- 2 standard deviations. Wide bands indicate high volatility; narrow bands (a 'squeeze') indicate low volatility and often precede a big move. Price touching the upper band does not automatically mean 'sell'.",
            "difficulty": 1,
            "tags": ["bollinger_bands", "volatility"],
        },
        {
            "id": "ta_bb_02",
            "deck": "technical_analysis",
            "front": "What is a Bollinger Band squeeze, and how do traders use it?",
            "back": "A squeeze occurs when band width contracts to an unusually narrow range, indicating very low volatility. Since low volatility periods tend to be followed by high volatility, traders watch for a breakout from the squeeze. The direction of the breakout determines the trade direction.",
            "difficulty": 2,
            "tags": ["bollinger_bands", "squeeze", "volatility"],
        },
        {
            "id": "ta_sr_01",
            "deck": "technical_analysis",
            "front": "How do support and resistance levels form, and why do they matter?",
            "back": "Support forms at price levels where buying demand historically prevented further decline. Resistance forms where selling pressure halted advances. They matter because many traders watch the same levels, creating self-fulfilling prophecies. When broken, support becomes resistance and vice versa.",
            "difficulty": 1,
            "tags": ["support_resistance", "price_levels"],
        },
        {
            "id": "ta_vol_01",
            "deck": "technical_analysis",
            "front": "Why is volume analysis important in confirming price trends?",
            "back": "Volume confirms the strength of a price move. Rising prices with increasing volume suggest strong conviction. Rising prices with declining volume warn of a weakening trend. Volume spikes often occur at trend reversals. On-Balance Volume (OBV) tracks cumulative buying/selling pressure.",
            "difficulty": 2,
            "tags": ["volume", "obv", "confirmation"],
        },
        {
            "id": "ta_candle_01",
            "deck": "technical_analysis",
            "front": "What is a Doji candlestick pattern, and what does it signify?",
            "back": "A Doji forms when the open and close are nearly equal, creating a cross-like shape. It signals indecision between buyers and sellers. A Doji after a strong trend may signal exhaustion and potential reversal. Context matters: a Doji in a sideways market is less significant.",
            "difficulty": 2,
            "tags": ["candlestick", "doji", "reversal"],
        },
        {
            "id": "ta_candle_02",
            "deck": "technical_analysis",
            "front": "What is the difference between a hammer and a hanging man candlestick pattern?",
            "back": "Both have small bodies and long lower shadows. A hammer appears after a downtrend and signals potential bullish reversal (buyers stepped in). A hanging man appears after an uptrend and warns of bearish reversal (selling pressure emerging). The pattern is the same; context determines the name.",
            "difficulty": 2,
            "tags": ["candlestick", "hammer", "reversal"],
        },
    ]


def _build_fundamental_analysis_deck():
    """Build the fundamental analysis study card deck."""
    return [
        {
            "id": "fa_pe_01",
            "deck": "fundamental_analysis",
            "front": "What does the Price-to-Earnings (P/E) ratio measure, and what are its limitations?",
            "back": "P/E = Stock Price / Earnings Per Share. It shows how much investors pay per dollar of earnings. Limitations: ignores growth rate, varies by industry, negative earnings make it meaningless, can be distorted by one-time charges, and trailing P/E uses backward-looking data.",
            "difficulty": 1,
            "tags": ["pe_ratio", "valuation"],
        },
        {
            "id": "fa_peg_01",
            "deck": "fundamental_analysis",
            "front": "How does the PEG ratio improve upon the P/E ratio?",
            "back": "PEG = P/E / Expected Annual Earnings Growth Rate. It accounts for growth: a P/E of 30 is expensive for a 5% grower but cheap for a 40% grower. PEG < 1 suggests undervalued relative to growth; PEG > 2 suggests expensive. Limitation: depends on accuracy of growth estimates.",
            "difficulty": 2,
            "tags": ["peg_ratio", "growth", "valuation"],
        },
        {
            "id": "fa_de_01",
            "deck": "fundamental_analysis",
            "front": "What does the Debt-to-Equity ratio indicate about a company's financial health?",
            "back": "D/E = Total Liabilities / Shareholders' Equity. High D/E means the company relies heavily on debt financing, increasing risk during downturns. Normal ranges vary by industry: utilities often have D/E > 1.5, while tech companies may have D/E < 0.5. Rising D/E over time is a red flag.",
            "difficulty": 1,
            "tags": ["debt_to_equity", "leverage", "risk"],
        },
        {
            "id": "fa_roe_01",
            "deck": "fundamental_analysis",
            "front": "What is Return on Equity (ROE), and how does the DuPont decomposition break it down?",
            "back": "ROE = Net Income / Shareholders' Equity. DuPont breaks it into: Profit Margin x Asset Turnover x Equity Multiplier. This reveals whether high ROE comes from profitability, efficiency, or leverage. ROE > 15% is generally good. Rising leverage can inflate ROE while increasing risk.",
            "difficulty": 2,
            "tags": ["roe", "dupont", "profitability"],
        },
        {
            "id": "fa_fcf_01",
            "deck": "fundamental_analysis",
            "front": "Why is Free Cash Flow (FCF) considered more reliable than net income?",
            "back": "FCF = Operating Cash Flow - Capital Expenditures. Unlike net income, FCF is harder to manipulate with accounting choices. It shows actual cash available for dividends, buybacks, and debt repayment. Consistently positive FCF indicates a healthy business; negative FCF may signal trouble even with positive earnings.",
            "difficulty": 2,
            "tags": ["free_cash_flow", "cash_flow"],
        },
        {
            "id": "fa_eg_01",
            "deck": "fundamental_analysis",
            "front": "What is the difference between revenue growth and earnings growth, and why does the distinction matter?",
            "back": "Revenue growth shows top-line expansion; earnings growth shows bottom-line profitability improvement. A company can grow revenue while earnings shrink (margin compression) or grow earnings while revenue stagnates (cost cutting). Sustainable value creation requires both revenue and earnings growth.",
            "difficulty": 1,
            "tags": ["earnings_growth", "revenue_growth"],
        },
        {
            "id": "fa_bv_01",
            "deck": "fundamental_analysis",
            "front": "What is Book Value per Share, and when is Price-to-Book (P/B) most useful?",
            "back": "Book Value = Total Assets - Total Liabilities. P/B = Price / Book Value per Share. P/B < 1 means the stock trades below its accounting value. P/B is most useful for asset-heavy industries (banks, REITs, manufacturing). It is less useful for tech companies where value lies in intangible assets.",
            "difficulty": 2,
            "tags": ["book_value", "price_to_book", "valuation"],
        },
        {
            "id": "fa_margin_01",
            "deck": "fundamental_analysis",
            "front": "What do gross margin, operating margin, and net margin each tell you?",
            "back": "Gross margin = (Revenue - COGS) / Revenue: measures production efficiency. Operating margin = Operating Income / Revenue: includes SGA and R&D costs, shows core business profitability. Net margin = Net Income / Revenue: the bottom line after all expenses and taxes. Expanding margins over time signal improving business economics.",
            "difficulty": 2,
            "tags": ["margins", "profitability"],
        },
        {
            "id": "fa_ev_01",
            "deck": "fundamental_analysis",
            "front": "Why do analysts prefer EV/EBITDA over P/E for comparing companies?",
            "back": "Enterprise Value (EV) includes debt and excludes cash, giving a more complete picture of total cost to acquire a business. EBITDA removes capital structure and tax differences. Together, EV/EBITDA allows apples-to-apples comparison across companies with different debt levels and tax situations.",
            "difficulty": 3,
            "tags": ["ev_ebitda", "enterprise_value", "valuation"],
        },
        {
            "id": "fa_div_01",
            "deck": "fundamental_analysis",
            "front": "What is the dividend payout ratio, and what does a very high payout ratio signal?",
            "back": "Payout ratio = Dividends / Net Income. It shows what fraction of earnings is paid to shareholders. A ratio above 80% may be unsustainable, leaving little room for reinvestment or dividend increases. A ratio below 40% suggests room for growth. Negative payout ratio means the company pays dividends despite losses.",
            "difficulty": 1,
            "tags": ["dividend", "payout_ratio"],
        },
    ]


def _build_options_trading_deck():
    """Build the options trading study card deck."""
    return [
        {
            "id": "opt_delta_01",
            "deck": "options_trading",
            "front": "What does Delta measure in options trading, and what is its range for calls vs puts?",
            "back": "Delta measures how much an option's price changes per $1 move in the underlying. Call delta ranges from 0 to +1; put delta ranges from -1 to 0. ATM options have delta near +/-0.50. Delta also approximates the probability of expiring in the money.",
            "difficulty": 1,
            "tags": ["delta", "greeks"],
        },
        {
            "id": "opt_gamma_01",
            "deck": "options_trading",
            "front": "What is Gamma, and why is it highest for at-the-money options near expiration?",
            "back": "Gamma measures the rate of change of delta per $1 move in the underlying. ATM options near expiration have the highest gamma because small price changes dramatically shift whether the option expires ITM or OTM. High gamma means delta changes rapidly, creating both opportunity and risk.",
            "difficulty": 2,
            "tags": ["gamma", "greeks"],
        },
        {
            "id": "opt_theta_01",
            "deck": "options_trading",
            "front": "How does Theta (time decay) affect option buyers vs sellers?",
            "back": "Theta measures daily loss in option value due to passing time. Buyers lose theta daily (negative for long positions). Sellers collect theta (positive for short positions). Theta accelerates as expiration approaches, especially for ATM options. This is why option sellers prefer short-dated options.",
            "difficulty": 1,
            "tags": ["theta", "greeks", "time_decay"],
        },
        {
            "id": "opt_vega_01",
            "deck": "options_trading",
            "front": "What is Vega, and how does implied volatility affect option prices?",
            "back": "Vega measures price change per 1% change in implied volatility (IV). Higher IV increases both call and put prices. ATM options have the highest vega. Vega decreases as expiration approaches. Buying options before earnings (high IV) and selling after (IV crush) is a common strategy consideration.",
            "difficulty": 2,
            "tags": ["vega", "greeks", "implied_volatility"],
        },
        {
            "id": "opt_pcr_01",
            "deck": "options_trading",
            "front": "What does the Put/Call Ratio indicate about market sentiment?",
            "back": "Put/Call Ratio = Put Volume / Call Volume. Ratio > 1.0 means more puts traded, suggesting bearish sentiment. Ratio < 0.7 suggests bullish sentiment. Extreme readings are often contrarian indicators: very high put/call may signal a market bottom (excessive fear), very low may signal a top (complacency).",
            "difficulty": 2,
            "tags": ["put_call_ratio", "sentiment"],
        },
        {
            "id": "opt_iv_01",
            "deck": "options_trading",
            "front": "What is the difference between implied volatility and historical volatility?",
            "back": "Historical volatility (HV) measures actual past price fluctuations. Implied volatility (IV) is derived from option prices and reflects the market's expectation of future volatility. When IV > HV, options are relatively expensive. When IV < HV, options are relatively cheap. IV Rank and IV Percentile help contextualize current IV.",
            "difficulty": 2,
            "tags": ["implied_volatility", "historical_volatility"],
        },
        {
            "id": "opt_strat_01",
            "deck": "options_trading",
            "front": "What is an Iron Condor, and when would a trader use it?",
            "back": "An Iron Condor sells an OTM put spread and an OTM call spread simultaneously. It profits when the underlying stays within a range. Max profit = net credit received. Max loss = width of wider spread minus credit. Used when expecting low volatility and range-bound price action.",
            "difficulty": 3,
            "tags": ["iron_condor", "strategy", "neutral"],
        },
        {
            "id": "opt_strat_02",
            "deck": "options_trading",
            "front": "What is a Covered Call strategy, and what are its trade-offs?",
            "back": "Covered Call = own 100 shares + sell 1 call. It generates income from the premium but caps upside at the strike price. If the stock drops, the premium provides partial downside protection. It works best for neutral-to-slightly-bullish outlook. Risk: full downside exposure minus the premium received.",
            "difficulty": 1,
            "tags": ["covered_call", "strategy", "income"],
        },
        {
            "id": "opt_decay_01",
            "deck": "options_trading",
            "front": "Why does time decay accelerate in the last 30 days before option expiration?",
            "back": "Time value decays at a rate proportional to the square root of time remaining. As expiration nears, each day represents a larger fraction of remaining time. An option loses approximately 1/3 of its time value in the last month. This is why weekly options have very high theta relative to their price.",
            "difficulty": 2,
            "tags": ["time_decay", "theta", "expiration"],
        },
        {
            "id": "opt_spread_01",
            "deck": "options_trading",
            "front": "What is the difference between a debit spread and a credit spread?",
            "back": "A debit spread costs money to open (buy expensive option, sell cheaper one) and profits when the underlying moves in your direction. A credit spread collects premium upfront (sell expensive option, buy cheaper one) and profits when the underlying stays away from the short strike. Debit spreads have defined risk and reward.",
            "difficulty": 2,
            "tags": ["spreads", "strategy", "debit", "credit"],
        },
    ]


def _build_risk_management_deck():
    """Build the risk management study card deck."""
    return [
        {
            "id": "rm_sizing_01",
            "deck": "risk_management",
            "front": "What is the 1% rule for position sizing, and how do you calculate position size?",
            "back": "The 1% rule means risking no more than 1% of total portfolio value on any single trade. Position Size = (Account Value x 0.01) / (Entry Price - Stop Loss Price). For a $100K account with a $2 stop loss, max position = $1,000 / $2 = 500 shares.",
            "difficulty": 1,
            "tags": ["position_sizing", "risk_per_trade"],
        },
        {
            "id": "rm_sizing_02",
            "deck": "risk_management",
            "front": "What is the Kelly Criterion, and why do most traders use a fraction of it?",
            "back": "Kelly Criterion = (Win% x Avg Win - Loss% x Avg Loss) / Avg Win. It calculates the optimal bet size to maximize long-term growth. Full Kelly is too aggressive for most traders due to large drawdowns. Half-Kelly or quarter-Kelly reduces volatility while preserving most of the growth benefit.",
            "difficulty": 3,
            "tags": ["position_sizing", "kelly_criterion"],
        },
        {
            "id": "rm_stop_01",
            "deck": "risk_management",
            "front": "What are the main types of stop-loss strategies?",
            "back": "1) Fixed percentage stop (e.g., sell if down 5%). 2) ATR-based stop (e.g., 2x ATR below entry). 3) Technical stop (below support level or moving average). 4) Trailing stop (moves up with price, locks in gains). 5) Time stop (exit if trade has not moved in X days). ATR-based stops adapt to volatility.",
            "difficulty": 2,
            "tags": ["stop_loss", "exit_strategy"],
        },
        {
            "id": "rm_rr_01",
            "deck": "risk_management",
            "front": "What is a risk-reward ratio, and why is a minimum of 1:2 commonly recommended?",
            "back": "Risk-Reward = Potential Loss / Potential Gain. A 1:2 ratio means risking $1 to make $2. At 1:2, you only need to win 34% of trades to break even. At 1:1, you need 50%. Higher ratios allow lower win rates to be profitable. Professional traders typically seek 1:3 or better.",
            "difficulty": 1,
            "tags": ["risk_reward", "expectancy"],
        },
        {
            "id": "rm_div_01",
            "deck": "risk_management",
            "front": "What is the difference between diversification and diworsification?",
            "back": "Diversification spreads risk across uncorrelated assets to reduce portfolio volatility. Diworsification (a Peter Lynch term) means owning too many positions, diluting returns without meaningfully reducing risk because holdings are correlated. Holding 30 tech stocks is not diversified. True diversification requires low-correlation assets.",
            "difficulty": 2,
            "tags": ["diversification", "correlation"],
        },
        {
            "id": "rm_dd_01",
            "deck": "risk_management",
            "front": "What is Maximum Drawdown, and why is it a critical risk metric?",
            "back": "Max Drawdown = largest peak-to-trough decline in portfolio value. It measures worst-case loss an investor would have experienced. A 50% drawdown requires a 100% gain to recover. Max drawdown reveals the true risk of a strategy that average returns may hide. Professional funds target max drawdown under 20%.",
            "difficulty": 2,
            "tags": ["max_drawdown", "risk_metric"],
        },
        {
            "id": "rm_corr_01",
            "deck": "risk_management",
            "front": "Why does correlation between assets tend to increase during market crashes?",
            "back": "During crises, investors sell risky assets indiscriminately, causing 'correlation convergence to 1.' Assets that appeared uncorrelated in calm markets become highly correlated during stress. This is why portfolios diversified with stocks alone often fail in crashes. True crisis diversification requires assets like treasuries, gold, or managed futures.",
            "difficulty": 3,
            "tags": ["correlation", "crisis", "tail_risk"],
        },
        {
            "id": "rm_var_01",
            "deck": "risk_management",
            "front": "What does Value at Risk (VaR) measure, and what is its main limitation?",
            "back": "VaR estimates the maximum expected loss over a time period at a given confidence level. For example, 95% daily VaR of $10K means there is a 5% chance of losing more than $10K in a day. Limitation: VaR says nothing about the size of losses beyond the threshold (tail risk). CVaR (Conditional VaR) addresses this.",
            "difficulty": 3,
            "tags": ["var", "risk_metric", "tail_risk"],
        },
        {
            "id": "rm_vol_01",
            "deck": "risk_management",
            "front": "How should you adjust position sizes based on a stock's volatility?",
            "back": "More volatile stocks require smaller position sizes to maintain consistent risk. Use volatility-adjusted sizing: Position Size = Target Risk / (ATR x Multiplier). If Stock A has ATR of $2 and Stock B has ATR of $5, Stock B gets 40% the position size of Stock A for equal risk exposure.",
            "difficulty": 2,
            "tags": ["position_sizing", "volatility", "atr"],
        },
        {
            "id": "rm_pf_01",
            "deck": "risk_management",
            "front": "What is the Sharpe Ratio, and what constitutes a good Sharpe Ratio?",
            "back": "Sharpe Ratio = (Portfolio Return - Risk-Free Rate) / Portfolio Standard Deviation. It measures risk-adjusted return. Sharpe > 1.0 is good, > 2.0 is very good, > 3.0 is exceptional. Limitation: it penalizes upside volatility equally with downside. The Sortino Ratio addresses this by only using downside deviation.",
            "difficulty": 2,
            "tags": ["sharpe_ratio", "risk_adjusted_return"],
        },
    ]


def _build_market_mechanics_deck():
    """Build the market mechanics study card deck."""
    return [
        {
            "id": "mm_order_01",
            "deck": "market_mechanics",
            "front": "What are the differences between market, limit, and stop orders?",
            "back": "Market order: executes immediately at best available price (guaranteed fill, not guaranteed price). Limit order: executes only at specified price or better (guaranteed price, not guaranteed fill). Stop order: becomes a market order once the stop price is reached (used for stop-losses). Stop-limit combines both.",
            "difficulty": 1,
            "tags": ["order_types", "market_order", "limit_order"],
        },
        {
            "id": "mm_order_02",
            "deck": "market_mechanics",
            "front": "What is the difference between a stop-loss order and a stop-limit order?",
            "back": "A stop-loss becomes a market order when triggered, guaranteeing execution but not price (slippage risk in fast markets). A stop-limit becomes a limit order when triggered, guaranteeing price but not execution (may not fill if price gaps past the limit). In a flash crash, stop-limits may not execute at all.",
            "difficulty": 2,
            "tags": ["order_types", "stop_loss", "stop_limit"],
        },
        {
            "id": "mm_short_01",
            "deck": "market_mechanics",
            "front": "How does short selling work, and what are its unique risks?",
            "back": "Short selling: borrow shares, sell them, buy back later at (hopefully) a lower price. Risks: unlimited loss potential (stock can rise infinitely), short squeeze risk, borrow costs, dividend payments owed, and margin calls. Uptick rule may restrict shorting during declines.",
            "difficulty": 2,
            "tags": ["short_selling", "borrowing"],
        },
        {
            "id": "mm_margin_01",
            "deck": "market_mechanics",
            "front": "What is a margin call, and what triggers it?",
            "back": "A margin call occurs when account equity falls below the maintenance margin requirement (typically 25-30%). If you buy $100K of stock with $50K cash and $50K margin, a drop to $66K triggers a call. You must deposit funds or liquidate positions. Brokers can liquidate without warning in extreme cases.",
            "difficulty": 2,
            "tags": ["margin", "margin_call", "leverage"],
        },
        {
            "id": "mm_spread_01",
            "deck": "market_mechanics",
            "front": "What determines the bid-ask spread, and why does it matter?",
            "back": "The spread is the difference between the highest buy price (bid) and lowest sell price (ask). Factors: liquidity (high volume = tighter spread), volatility, tick size, and market maker competition. Wider spreads mean higher transaction costs. Large-cap stocks like AAPL often have $0.01 spreads; small-caps can have 1-5% spreads.",
            "difficulty": 1,
            "tags": ["bid_ask_spread", "liquidity"],
        },
        {
            "id": "mm_maker_01",
            "deck": "market_mechanics",
            "front": "What role do market makers play in the stock market?",
            "back": "Market makers provide liquidity by continuously quoting bid and ask prices. They profit from the spread and are obligated to maintain orderly markets. They manage inventory risk by adjusting quotes. Without market makers, stocks would have wider spreads and less consistent pricing. Major makers include Citadel Securities and Virtu Financial.",
            "difficulty": 2,
            "tags": ["market_makers", "liquidity"],
        },
        {
            "id": "mm_dark_01",
            "deck": "market_mechanics",
            "front": "What are dark pools, and why do institutional investors use them?",
            "back": "Dark pools are private trading venues where orders are not displayed publicly. Institutions use them to execute large orders without revealing their intent, which would move the market against them. About 40% of US equity volume trades in dark pools. Drawback: less price transparency and potential conflicts of interest.",
            "difficulty": 3,
            "tags": ["dark_pools", "institutional"],
        },
        {
            "id": "mm_settle_01",
            "deck": "market_mechanics",
            "front": "What is T+1 settlement, and why does it matter?",
            "back": "T+1 means trades settle one business day after execution. Until settlement, you technically do not own the shares and the seller has not received payment. This affects short-term trading: selling before settlement on a cash account causes a good-faith violation. Margin accounts allow trading before settlement.",
            "difficulty": 1,
            "tags": ["settlement", "t_plus_1"],
        },
        {
            "id": "mm_etf_01",
            "deck": "market_mechanics",
            "front": "How does ETF creation/redemption keep ETF prices close to NAV?",
            "back": "Authorized Participants (APs) can create new ETF shares by delivering the underlying basket of stocks, or redeem shares for the underlying basket. If ETF trades above NAV, APs create shares (increasing supply, pushing price down). If below NAV, they redeem shares (decreasing supply, pushing price up). This arbitrage mechanism keeps prices aligned.",
            "difficulty": 3,
            "tags": ["etf", "creation_redemption", "nav"],
        },
        {
            "id": "mm_halt_01",
            "deck": "market_mechanics",
            "front": "What triggers a circuit breaker or trading halt?",
            "back": "Market-wide circuit breakers (S&P 500): Level 1 at -7%, Level 2 at -13% (15-minute halt each), Level 3 at -20% (trading halts for the day). Individual stocks: LULD (Limit Up-Limit Down) halts if price moves beyond acceptable bands. News-based halts pause trading for material announcements.",
            "difficulty": 2,
            "tags": ["circuit_breaker", "trading_halt"],
        },
    ]


def _build_macro_economics_deck():
    """Build the macroeconomics study card deck."""
    return [
        {
            "id": "macro_rate_01",
            "deck": "macro_economics",
            "front": "How do Federal Reserve interest rate decisions affect stock prices?",
            "back": "Rate hikes increase borrowing costs, reduce corporate profits, and make bonds more attractive relative to stocks (negative for equities). Rate cuts do the opposite (positive for equities). The market often moves on expectations, not the actual decision. The Fed Funds rate influences all other rates in the economy.",
            "difficulty": 1,
            "tags": ["interest_rates", "fed_policy", "monetary_policy"],
        },
        {
            "id": "macro_inf_01",
            "deck": "macro_economics",
            "front": "How does inflation impact different types of stocks?",
            "back": "Moderate inflation (2-3%) is generally positive. High inflation hurts growth stocks (future earnings worth less), benefits commodity producers and pricing-power companies. CPI measures consumer inflation; PPI measures producer costs. Real returns = nominal returns minus inflation. The Fed targets 2% PCE inflation.",
            "difficulty": 2,
            "tags": ["inflation", "cpi", "stock_impact"],
        },
        {
            "id": "macro_yc_01",
            "deck": "macro_economics",
            "front": "What is the yield curve, and why does an inverted yield curve predict recessions?",
            "back": "The yield curve plots Treasury yields by maturity. Normal: longer maturities yield more (compensating for time risk). Inverted: short-term rates exceed long-term rates. Inversion predicts recessions because it signals the market expects the Fed will cut rates due to economic weakness. The 10Y-2Y spread is the most-watched measure.",
            "difficulty": 2,
            "tags": ["yield_curve", "recession", "treasury"],
        },
        {
            "id": "macro_sector_01",
            "deck": "macro_economics",
            "front": "How does sector rotation work across the business cycle?",
            "back": "Early recovery: cyclicals, technology, financials outperform. Mid-cycle: industrials, energy, materials lead. Late cycle: energy, healthcare, staples perform best. Recession: utilities, healthcare, consumer staples (defensives) outperform. Understanding the current cycle phase helps with sector allocation.",
            "difficulty": 2,
            "tags": ["sector_rotation", "business_cycle"],
        },
        {
            "id": "macro_gdp_01",
            "deck": "macro_economics",
            "front": "What are the key GDP indicators, and how do they affect markets?",
            "back": "GDP = Consumer Spending + Business Investment + Government Spending + Net Exports. Leading indicators: PMI, building permits, yield curve. Coincident: employment, income, industrial production. Lagging: unemployment rate, CPI. Two consecutive quarters of negative GDP growth is a common recession definition. Markets react to GDP vs expectations.",
            "difficulty": 2,
            "tags": ["gdp", "economic_indicators"],
        },
        {
            "id": "macro_fed_01",
            "deck": "macro_economics",
            "front": "What tools does the Federal Reserve use beyond interest rates?",
            "back": "1) Quantitative Easing (QE): buying bonds to inject liquidity and lower long-term rates. 2) Quantitative Tightening (QT): reducing bond holdings to remove liquidity. 3) Forward guidance: communicating future policy intentions. 4) Reserve requirements. 5) Discount window lending. QE/QT have massive impact on asset prices and financial conditions.",
            "difficulty": 2,
            "tags": ["fed_policy", "qe", "qt"],
        },
        {
            "id": "macro_usd_01",
            "deck": "macro_economics",
            "front": "How does US dollar strength affect different types of companies?",
            "back": "Strong dollar hurts US multinationals (foreign revenue worth less when converted to USD) and commodity prices (priced in USD, more expensive for foreign buyers). It benefits US importers and consumers buying foreign goods. The Dollar Index (DXY) measures USD against a basket of six currencies.",
            "difficulty": 2,
            "tags": ["us_dollar", "currency", "multinationals"],
        },
        {
            "id": "macro_empl_01",
            "deck": "macro_economics",
            "front": "Why is the monthly jobs report (Non-Farm Payrolls) so market-moving?",
            "back": "NFP measures the change in employed workers excluding farms. It is a key indicator of economic health and heavily influences Fed policy. Strong jobs = potential rate hikes (bad for stocks short-term). Weak jobs = potential rate cuts (good for stocks). Markets react to NFP vs consensus, not the absolute number. Revisions to prior months also matter.",
            "difficulty": 1,
            "tags": ["employment", "nfp", "jobs_report"],
        },
        {
            "id": "macro_oil_01",
            "deck": "macro_economics",
            "front": "How do oil prices affect the broader economy and stock market?",
            "back": "Rising oil prices increase input costs for most businesses, reduce consumer spending power, and raise inflation expectations. Energy sector benefits; transport, airlines, and consumer discretionary suffer. Very high oil prices have preceded several recessions. Low oil prices act as a tax cut for consumers and reduce production costs.",
            "difficulty": 2,
            "tags": ["oil", "energy", "inflation"],
        },
        {
            "id": "macro_housing_01",
            "deck": "macro_economics",
            "front": "Why is the housing market considered a leading economic indicator?",
            "back": "Housing is sensitive to interest rates and consumer confidence, making it an early signal. Housing starts, building permits, and mortgage applications decline before recessions. Housing represents the largest asset for most Americans; falling home prices reduce wealth and consumer spending. Housing-related industries (construction, furnishing, lending) amplify the impact.",
            "difficulty": 2,
            "tags": ["housing", "leading_indicator"],
        },
    ]


# Combine all deck builders into a registry
_DECK_BUILDERS = {
    "technical_analysis": _build_technical_analysis_deck,
    "fundamental_analysis": _build_fundamental_analysis_deck,
    "options_trading": _build_options_trading_deck,
    "risk_management": _build_risk_management_deck,
    "market_mechanics": _build_market_mechanics_deck,
    "macro_economics": _build_macro_economics_deck,
}

DECK_DESCRIPTIONS = {
    "technical_analysis": "RSI, MACD, moving averages, Bollinger Bands, support/resistance, volume analysis, candlestick patterns",
    "fundamental_analysis": "P/E ratio, PEG ratio, debt-to-equity, ROE, free cash flow, earnings growth, book value",
    "options_trading": "Greeks (delta/gamma/theta/vega), put-call ratio, implied volatility, option strategies, time decay",
    "risk_management": "Position sizing, stop-loss strategies, risk-reward ratio, portfolio diversification, max drawdown",
    "market_mechanics": "Order types (market/limit/stop), short selling, margin trading, bid-ask spread, market makers",
    "macro_economics": "Interest rates, inflation impact, yield curve, sector rotation, GDP indicators, Fed policy",
}


# ---------------------------------------------------------------------------
# yfinance live data fetcher
# ---------------------------------------------------------------------------

def _fetch_live_ticker_data(ticker):
    """Fetch current price, technical indicators, and fundamental ratios
    directly from yfinance.

    Returns a dict with keys: ticker, current_price, rsi_14,
    moving_averages, pe, forward_pe, volume, market_cap, beta,
    dividend_yield, fifty_two_week_high/low, debt_to_equity,
    profit_margin, and data_source.

    Falls back to reasonable defaults if the API call fails.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        hist = stock.history(period="6mo")
        if hist.empty:
            logger.warning("empty history for %s, using fallback", ticker)
            return _fallback_ticker_data(ticker)

        close = hist["Close"]
        price = round(float(close.iloc[-1]), 2)

        # RSI (14-day)
        rsi = _calculate_rsi(close)

        # Moving averages
        sma_50 = round(float(close.tail(50).mean()), 2) if len(close) >= 50 else round(price * 0.98, 2)
        sma_200 = round(float(close.mean()), 2) if len(close) >= 100 else round(price * 0.94, 2)
        sma_20 = round(float(close.tail(20).mean()), 2) if len(close) >= 20 else round(price * 0.99, 2)

        # Volume
        volume = int(hist["Volume"].tail(20).mean()) if "Volume" in hist.columns else 50_000_000

        pe = round(float(info.get("trailingPE", 0) or 0), 1) or 25.0
        forward_pe = round(float(info.get("forwardPE", 0) or 0), 1) or 22.0
        beta = round(float(info.get("beta", 0) or 0), 2) or 1.1
        market_cap = int(info.get("marketCap", 0) or 0) or 2_500_000_000_000
        high_52w = round(float(info.get("fiftyTwoWeekHigh", 0) or 0), 2) or price * 1.2
        low_52w = round(float(info.get("fiftyTwoWeekLow", 0) or 0), 2) or price * 0.75
        de = round(float(info.get("debtToEquity", 0) or 0), 1)
        margin = round(float(info.get("profitMargins", 0) or 0), 4)
        div_yield_raw = float(info.get("dividendYield", 0) or 0)
        div_yield = round(div_yield_raw * 100, 2) if div_yield_raw < 1 else round(div_yield_raw, 2)
        roe = round(float(info.get("returnOnEquity", 0) or 0), 4)
        peg = round(float(info.get("pegRatio", 0) or 0), 2)
        rev_growth = round(float(info.get("revenueGrowth", 0) or 0), 4)

        # Range position
        pct_from_high = round(((price - high_52w) / high_52w) * 100, 1) if high_52w else 0
        pct_from_low = round(((price - low_52w) / low_52w) * 100, 1) if low_52w else 0

        return {
            "ticker": ticker,
            "current_price": price,
            "rsi_14": rsi,
            "moving_averages": {
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
            },
            "range_52w": {
                "high": high_52w,
                "low": low_52w,
                "pct_from_high": pct_from_high,
                "pct_from_low": pct_from_low,
            },
            "volume": volume,
            "ratios": {
                "pe_trailing": pe,
                "forward_pe": forward_pe,
                "pb_ratio": round(float(info.get("priceToBook", 0) or 0), 1),
                "debt_to_equity": de,
                "profit_margin": margin,
                "roe": roe,
                "peg_ratio": peg,
                "beta": beta,
                "dividend_yield": div_yield_raw,
            },
            "growth": {
                "revenue_growth": rev_growth,
            },
            "market_cap": market_cap,
            "beta": beta,
            "dividend_yield": div_yield,
            "data_source": "yfinance",
        }
    except Exception as exc:
        logger.warning("live data fetch failed for %s: %s", ticker, exc)
        return _fallback_ticker_data(ticker)


def _fallback_ticker_data(ticker):
    """Return reasonable defaults when live data is unavailable."""
    return {
        "ticker": ticker,
        "current_price": 150.0,
        "rsi_14": 55.0,
        "moving_averages": {
            "sma_20": 149.0,
            "sma_50": 148.0,
            "sma_200": 142.0,
        },
        "range_52w": {
            "high": 180.0,
            "low": 120.0,
            "pct_from_high": -16.7,
            "pct_from_low": 25.0,
        },
        "volume": 50_000_000,
        "ratios": {
            "pe_trailing": 25.0,
            "forward_pe": 22.0,
            "pb_ratio": 8.0,
            "debt_to_equity": 150.0,
            "profit_margin": 0.25,
            "roe": 0.30,
            "peg_ratio": 1.5,
            "beta": 1.1,
            "dividend_yield": 0.005,
        },
        "growth": {
            "revenue_growth": 0.08,
        },
        "market_cap": 2_500_000_000_000,
        "beta": 1.1,
        "dividend_yield": 0.5,
        "data_source": "fallback",
    }


def _calculate_rsi(close_series, period=14):
    """Calculate RSI from a pandas Series of closing prices."""
    try:
        delta = close_series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        value = rsi.dropna().iloc[-1]
        return round(float(value), 1)
    except Exception:
        return 55.0


def _ensure_four_options(question):
    """Pad or trim options list to exactly 4 items.

    Existing correct_answer index is preserved by appending neutral
    distractor options when fewer than 4 are present.
    """
    options = question.get("options", [])
    correct_idx = question.get("correct_answer", 0)

    distractor_pool = [
        "Cannot be determined from this data alone",
        "More information is needed to assess",
        "None of the above applies in this context",
        "This indicator is not meaningful here",
    ]

    while len(options) < 4:
        for d in distractor_pool:
            if d not in options:
                options.append(d)
                break
        else:
            options.append(f"Additional context needed ({len(options)})")

    # If more than 4, keep the correct answer and trim
    if len(options) > 4:
        if correct_idx < len(options):
            correct_option = options[correct_idx]
            other_options = [o for i, o in enumerate(options) if i != correct_idx]
            random.shuffle(other_options)
            new_options = other_options[:3]
            insert_pos = min(correct_idx, 3)
            new_options.insert(insert_pos, correct_option)
            question["options"] = new_options
            question["correct_answer"] = insert_pos
        else:
            question["options"] = options[:4]
    else:
        question["options"] = options


# ---------------------------------------------------------------------------
# Live-data quiz question builders (yfinance-powered)
# ---------------------------------------------------------------------------

def _build_live_options_questions(data):
    """Generate options trading questions from live ticker data."""
    ticker = data.get("ticker", "???")
    price = data.get("current_price", 150)
    beta = data.get("beta", 1.1)
    high = data.get("range_52w", {}).get("high", price * 1.2)
    low = data.get("range_52w", {}).get("low", price * 0.8)
    rsi = data.get("rsi_14", 50)
    sma_50 = data.get("moving_averages", {}).get("sma_50", price)
    questions = []

    range_pct = round(((high - low) / low) * 100, 1) if low > 0 else 30

    if range_pct > 60:
        iv_correct = 0
        iv_explanation = f"{ticker}'s 52-week range of ${low}-${high} ({range_pct}% spread) indicates high historical volatility, correlating with elevated implied volatility and more expensive option premiums."
    elif range_pct > 30:
        iv_correct = 1
        iv_explanation = f"{ticker}'s 52-week range of ${low}-${high} ({range_pct}% spread) shows moderate historical volatility, suggesting average implied volatility and reasonably priced premiums."
    else:
        iv_correct = 2
        iv_explanation = f"{ticker}'s 52-week range of ${low}-${high} ({range_pct}% spread) indicates low historical volatility, typically meaning cheaper option premiums."

    questions.append({
        "question": f"{ticker}'s 52-week range is ${low}-${high} (a {range_pct}% spread). What would you expect about its option premiums?",
        "context": {"ticker": ticker, "indicator": "52w_range_pct", "value": f"{range_pct}%"},
        "options": [
            "Expensive - high implied volatility due to large price swings",
            "Average - moderate implied volatility",
            "Cheap - low implied volatility due to tight price range",
            "Cannot determine IV from price range alone",
        ],
        "correct_answer": iv_correct,
        "explanation": iv_explanation,
        "difficulty": 2,
        "tags": ["implied_volatility", "options_pricing"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "options_trading",
    })

    # Strategy recommendation based on RSI and trend
    is_uptrend = price > sma_50
    if rsi > 65 and is_uptrend:
        strat_correct = 0
        strat_explanation = f"With RSI at {rsi} (elevated) and price above 50-day SMA, a covered call captures premium from strength while maintaining upside exposure."
    elif rsi < 35:
        strat_correct = 1
        strat_explanation = f"With RSI at {rsi} (oversold), a cash-secured put lets you collect premium and potentially acquire shares at a discount."
    elif 40 <= rsi <= 60:
        strat_correct = 2
        strat_explanation = f"With RSI at {rsi} (neutral) and no strong directional bias, an iron condor profits from range-bound conditions and time decay."
    else:
        strat_correct = 3
        strat_explanation = f"With mixed signals (RSI {rsi}, price {'above' if is_uptrend else 'below'} 50-day SMA), a vertical spread defines risk while expressing a directional view."

    questions.append({
        "question": f"{ticker} has RSI of {rsi} and trades {'above' if is_uptrend else 'below'} its 50-day SMA (${sma_50}). Which options strategy fits?",
        "context": {"ticker": ticker, "indicator": "RSI_and_trend", "value": f"RSI={rsi}"},
        "options": [
            "Covered call - capture premium near elevated levels",
            "Cash-secured put - accumulate shares at a discount",
            "Iron condor - profit from range-bound conditions",
            "Vertical spread - define risk with directional bias",
        ],
        "correct_answer": strat_correct,
        "explanation": strat_explanation,
        "difficulty": 2,
        "tags": ["strategy", "options_trading"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "options_trading",
    })

    return questions


def _build_live_risk_questions(data):
    """Generate risk management questions from live ticker data."""
    ticker = data.get("ticker", "???")
    price = data.get("current_price", 150)
    beta = data.get("beta", 1.1)
    high = data.get("range_52w", {}).get("high", price * 1.2)
    questions = []

    # Position sizing question
    portfolio_value = 100_000
    stop_distance = round(price * 0.05, 2)
    risk_amount = portfolio_value * 0.01
    shares = int(risk_amount / stop_distance) if stop_distance > 0 else 10

    questions.append({
        "question": f"With a $100K portfolio and {ticker} at ${price}, using 1% risk and 5% stop-loss, how many shares should you buy?",
        "context": {"ticker": ticker, "indicator": "position_sizing", "value": f"${price}"},
        "options": [
            f"~{shares} shares (risk ${int(risk_amount)} with ${stop_distance} stop distance)",
            f"~{shares * 2} shares (risk 2% of portfolio)",
            f"~{max(shares // 2, 1)} shares (risk 0.5% of portfolio)",
            f"~{shares * 3} shares (maximize position size)",
        ],
        "correct_answer": 0,
        "explanation": f"1% rule: risk ${int(risk_amount)} max. Stop distance = 5% of ${price} = ${stop_distance}. Shares = ${int(risk_amount)} / ${stop_distance} = {shares}.",
        "difficulty": 1,
        "tags": ["position_sizing", "risk_per_trade"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "risk_management",
    })

    # Drawdown recovery question
    drawdown_pct = round(((high - price) / high) * 100, 1) if high > 0 else 10
    recovery_pct = round(((high - price) / price) * 100, 1) if price > 0 else 11

    if drawdown_pct > 5:
        questions.append({
            "question": f"{ticker} is at ${price}, down {drawdown_pct}% from its 52-week high of ${high}. What gain is needed to recover?",
            "context": {"ticker": ticker, "indicator": "drawdown", "value": f"-{drawdown_pct}%"},
            "options": [
                f"~{recovery_pct}% gain needed (losses are asymmetric)",
                f"~{drawdown_pct}% gain matches the loss percentage",
                f"~{drawdown_pct / 2:.1f}% since recovery is faster than decline",
                "Cannot calculate without knowing the time horizon",
            ],
            "correct_answer": 0,
            "explanation": f"A {drawdown_pct}% decline requires a {recovery_pct}% gain to recover. The asymmetry of losses means protecting capital is critical.",
            "difficulty": 2,
            "tags": ["max_drawdown", "recovery"],
            "data_source": f"Live {ticker} data via yfinance",
            "topic": "risk_management",
        })

    return questions


def _build_live_mechanics_questions(data):
    """Generate market mechanics questions from live ticker data."""
    ticker = data.get("ticker", "???")
    volume = data.get("volume", 50_000_000)
    price = data.get("current_price", 150)
    rsi = data.get("rsi_14", 50)
    volume_m = round(volume / 1_000_000, 1)
    questions = []

    # Spread/liquidity question
    if volume_m > 30:
        spread_correct = 0
        spread_explanation = f"With {volume_m}M shares daily, {ticker} has extremely high liquidity with penny-wide spreads and efficient execution."
    elif volume_m > 5:
        spread_correct = 1
        spread_explanation = f"With {volume_m}M shares daily, {ticker} has good liquidity. Spreads are typically a few cents."
    else:
        spread_correct = 2
        spread_explanation = f"With {volume_m}M shares daily, {ticker} has moderate liquidity. Limit orders recommended."

    questions.append({
        "question": f"{ticker} trades {volume_m}M shares per day. What bid-ask spread would you expect?",
        "context": {"ticker": ticker, "indicator": "avg_volume", "value": f"{volume_m}M"},
        "options": [
            "Very tight (1 cent) - extremely high liquidity",
            "Narrow (a few cents) - good liquidity",
            "Wider spread - moderate liquidity, use limit orders",
            "Extremely wide - avoid market orders entirely",
        ],
        "correct_answer": spread_correct,
        "explanation": spread_explanation,
        "difficulty": 1,
        "tags": ["bid_ask_spread", "liquidity"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "market_mechanics",
    })

    return questions


def _build_live_macro_questions(data):
    """Generate macro questions using a ticker's rate sensitivity profile."""
    ticker = data.get("ticker", "???")
    pe = data.get("ratios", {}).get("pe_trailing", 25)
    beta = data.get("beta", 1.1)
    div_yield = data.get("dividend_yield", 0.5)
    questions = []

    # Rate sensitivity question
    if pe and pe > 30 and beta > 1.0:
        rate_correct = 0
        rate_explanation = f"{ticker} with P/E {pe} and beta {beta} is a high-growth stock most vulnerable to rate hikes due to distant future earnings."
    elif pe and pe < 20:
        rate_correct = 1
        rate_explanation = f"{ticker} with P/E {pe} is a value stock with near-term earnings, less affected by discount rate changes."
    else:
        rate_correct = 2
        rate_explanation = f"{ticker} with P/E {pe} and beta {beta} shows moderate rate sensitivity proportional to the market."

    questions.append({
        "question": f"{ticker} has P/E of {pe} and beta of {beta}. How would a 50bp Fed rate hike likely affect this stock?",
        "context": {"ticker": ticker, "indicator": "rate_sensitivity", "value": f"P/E={pe}"},
        "options": [
            "Significant negative impact - high-growth stocks are most rate-sensitive",
            "Minimal impact - value stocks with near-term earnings are less rate-sensitive",
            "Moderate impact - proportional to the broader market decline",
            "Positive impact - higher rates always benefit stocks",
        ],
        "correct_answer": rate_correct,
        "explanation": rate_explanation,
        "difficulty": 2,
        "tags": ["interest_rates", "fed_policy", "valuation"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "macro_economics",
    })

    # Dividend / bond competition question
    if div_yield > 2.0:
        div_correct = 0
        div_explanation = f"{ticker}'s yield of {div_yield}% faces bond competition in rising rate environments."
    elif div_yield > 0:
        div_correct = 1
        div_explanation = f"{ticker}'s yield of {div_yield}% is modest, less affected by bond yield competition."
    else:
        div_correct = 2
        div_explanation = f"{ticker} pays no dividend, so bond yield competition is not directly relevant."

    questions.append({
        "question": f"{ticker}'s dividend yield is {div_yield}%. How sensitive is it to rising bond yields?",
        "context": {"ticker": ticker, "indicator": "dividend_yield", "value": f"{div_yield}%"},
        "options": [
            "High sensitivity - dividend stocks compete with bonds for income investors",
            "Moderate sensitivity - modest yield makes bond competition less relevant",
            "Low sensitivity - no dividend means no direct bond yield competition",
            "Dividend yield has no relationship to bond yield sensitivity",
        ],
        "correct_answer": div_correct,
        "explanation": div_explanation,
        "difficulty": 2,
        "tags": ["dividend", "interest_rates", "bond_competition"],
        "data_source": f"Live {ticker} data via yfinance",
        "topic": "macro_economics",
    })

    return questions


# ---------------------------------------------------------------------------
# Live-data quiz question templates (data_sources.py format)
# ---------------------------------------------------------------------------

def _build_technical_questions(technical_data):
    """Generate quiz questions from live technical data."""
    ticker = technical_data.get("ticker", "???")
    questions = []

    # RSI question
    rsi = technical_data.get("rsi_14")
    if rsi is not None:
        if rsi > 70:
            correct = 0
            explanation = f"RSI of {rsi} is above 70, the standard overbought threshold. This indicates buying momentum may be exhausted and a pullback could follow."
        elif rsi < 30:
            correct = 2
            explanation = f"RSI of {rsi} is below 30, the standard oversold threshold. This suggests selling pressure may be exhausted and a bounce could follow."
        else:
            correct = 1
            explanation = f"RSI of {rsi} is between 30 and 70, indicating neutral momentum. Neither overbought nor oversold conditions are present."
        questions.append({
            "question": f"{ticker}'s RSI is currently {rsi}. This stock is:",
            "context": {"ticker": ticker, "indicator": "RSI", "value": rsi},
            "options": ["Overbought (RSI > 70)", "Neutral (RSI 30-70)", "Oversold (RSI < 30)"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["rsi", "momentum"],
            "data_source": f"Live {ticker} technical data",
        })

    # MACD crossover question
    macd = technical_data.get("macd", {})
    macd_line = macd.get("macd_line")
    signal_line = macd.get("signal_line")
    histogram = macd.get("histogram")
    if macd_line is not None and signal_line is not None:
        is_above = macd_line > signal_line
        if is_above:
            correct = 0
            explanation = f"MACD line ({macd_line:.4f}) is above the signal line ({signal_line:.4f}), producing a positive histogram. This is a bullish crossover signal suggesting upward momentum."
        else:
            correct = 1
            explanation = f"MACD line ({macd_line:.4f}) is below the signal line ({signal_line:.4f}), producing a negative histogram. This is a bearish signal suggesting downward momentum."
        questions.append({
            "question": f"{ticker}'s MACD line is {'above' if is_above else 'below'} the signal line with a histogram of {histogram:.4f}. This is a:",
            "context": {"ticker": ticker, "indicator": "MACD", "value": {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}},
            "options": ["Bullish signal", "Bearish signal", "Neutral - no signal"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["macd", "trend"],
            "data_source": f"Live {ticker} technical data",
        })

    # Bollinger Bands position question
    bb = technical_data.get("bollinger_bands", {})
    bb_upper = bb.get("upper")
    bb_lower = bb.get("lower")
    price = technical_data.get("current_price")
    if bb_upper is not None and bb_lower is not None and price is not None:
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            position_pct = (price - bb_lower) / bb_range * 100
            if position_pct > 90:
                correct = 0
                explanation = f"{ticker} at ${price} is near the upper Bollinger Band (${bb_upper}), placing it at the {position_pct:.0f}th percentile of the band range. This suggests the stock is at the top of its recent trading range."
            elif position_pct < 10:
                correct = 2
                explanation = f"{ticker} at ${price} is near the lower Bollinger Band (${bb_lower}), placing it at the {position_pct:.0f}th percentile of the band range. This suggests the stock is at the bottom of its recent trading range."
            else:
                correct = 1
                explanation = f"{ticker} at ${price} is within the Bollinger Bands (${bb_lower} - ${bb_upper}), at the {position_pct:.0f}th percentile. This is within normal trading range."
            questions.append({
                "question": f"{ticker} is at ${price}. Bollinger Bands are ${bb_upper} (upper) and ${bb_lower} (lower). The stock is:",
                "context": {"ticker": ticker, "indicator": "Bollinger Bands", "value": {"price": price, "upper": bb_upper, "lower": bb_lower}},
                "options": ["Near the upper band - potential resistance", "Within normal range", "Near the lower band - potential support"],
                "correct_answer": correct,
                "explanation": explanation,
                "difficulty": 2,
                "tags": ["bollinger_bands", "volatility"],
                "data_source": f"Live {ticker} technical data",
            })

    # Moving average trend question
    ma = technical_data.get("moving_averages", {})
    sma_50 = ma.get("sma_50")
    sma_200 = ma.get("sma_200")
    if price is not None and sma_50 is not None and sma_200 is not None:
        if sma_50 > sma_200:
            correct = 0
            explanation = f"{ticker}'s 50-day SMA (${sma_50}) is above its 200-day SMA (${sma_200}), which is a Golden Cross formation. This is a bullish long-term trend signal."
        else:
            correct = 1
            explanation = f"{ticker}'s 50-day SMA (${sma_50}) is below its 200-day SMA (${sma_200}), which is a Death Cross formation. This is a bearish long-term trend signal."
        questions.append({
            "question": f"{ticker}'s 50-day SMA is ${sma_50} and 200-day SMA is ${sma_200}. This represents a:",
            "context": {"ticker": ticker, "indicator": "Moving Averages", "value": {"sma_50": sma_50, "sma_200": sma_200}},
            "options": ["Golden Cross (bullish)", "Death Cross (bearish)", "No significant pattern"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["moving_average", "golden_cross", "death_cross"],
            "data_source": f"Live {ticker} technical data",
        })

    # Price vs SMA trend alignment question
    if price is not None and sma_50 is not None:
        above_sma20 = price > ma.get("sma_20", 0) if ma.get("sma_20") else False
        above_sma50 = price > sma_50
        above_sma200 = price > sma_200 if sma_200 else False
        all_above = above_sma20 and above_sma50 and above_sma200
        all_below = not above_sma20 and not above_sma50 and (not above_sma200 if sma_200 else True)
        if all_above:
            correct = 0
            explanation = f"{ticker} at ${price} is above all major moving averages (SMA 20, 50, 200). This strong alignment indicates a robust uptrend with all time frames in agreement."
        elif all_below:
            correct = 1
            explanation = f"{ticker} at ${price} is below all major moving averages. This alignment indicates a strong downtrend with all time frames in agreement."
        else:
            correct = 2
            explanation = f"{ticker} at ${price} is above some moving averages but below others, indicating a mixed or transitional trend where different time frames disagree."
        sma200_part = ""
        if sma_200 is not None:
            sma200_label = "above" if above_sma200 else "below"
            sma200_part = f", and {sma200_label} its 200-day SMA"
        sma20_label = "above" if above_sma20 else "below"
        sma50_label = "above" if above_sma50 else "below"
        question_text = (
            f"{ticker} at ${price} is {sma20_label} its 20-day SMA, "
            f"{sma50_label} its 50-day SMA{sma200_part}. The trend is:"
        )
        questions.append({
            "question": question_text,
            "context": {"ticker": ticker, "indicator": "Trend Alignment", "value": {"price": price, "sma_20": ma.get("sma_20"), "sma_50": sma_50, "sma_200": sma_200}},
            "options": ["Strongly bullish - all MAs aligned upward", "Strongly bearish - all MAs aligned downward", "Mixed - conflicting signals across timeframes"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["moving_average", "trend"],
            "data_source": f"Live {ticker} technical data",
        })

    # Volatility question
    vol = technical_data.get("volatility", {})
    annual_vol = vol.get("annual")
    if annual_vol is not None:
        if annual_vol > 50:
            correct = 0
            explanation = f"Annual volatility of {annual_vol}% is very high. This means the stock's price could reasonably move up or down by this percentage in a year. High volatility requires wider stop-losses and smaller position sizes."
        elif annual_vol > 25:
            correct = 1
            explanation = f"Annual volatility of {annual_vol}% is moderate, typical for individual stocks. Standard position sizing and risk management apply."
        else:
            correct = 2
            explanation = f"Annual volatility of {annual_vol}% is low, suggesting relatively stable price action. This allows tighter stop-losses and larger position sizes."
        questions.append({
            "question": f"{ticker}'s annualized volatility is {annual_vol}%. This indicates:",
            "context": {"ticker": ticker, "indicator": "Volatility", "value": annual_vol},
            "options": ["High volatility - needs wider stops and smaller positions", "Moderate volatility - standard risk management", "Low volatility - allows tighter stops and larger positions"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["volatility", "risk_management"],
            "data_source": f"Live {ticker} technical data",
        })

    # 52-week range position question
    range_data = technical_data.get("range_52w", {})
    pct_from_high = range_data.get("pct_from_high")
    pct_from_low = range_data.get("pct_from_low")
    if pct_from_high is not None and pct_from_low is not None:
        if abs(pct_from_high) < 5:
            correct = 0
            explanation = f"{ticker} is {pct_from_high}% from its 52-week high and {pct_from_low}% from its low. Trading near the high suggests strong momentum but may face resistance."
        elif abs(pct_from_high) > 30:
            correct = 2
            explanation = f"{ticker} is {pct_from_high}% from its 52-week high and {pct_from_low}% from its low. Being well below the high could indicate either a buying opportunity or fundamental deterioration."
        else:
            correct = 1
            explanation = f"{ticker} is {pct_from_high}% from its 52-week high and {pct_from_low}% from its low. The stock is in the middle of its range, with room in both directions."
        questions.append({
            "question": f"{ticker} is {pct_from_high}% from its 52-week high and +{pct_from_low}% from its 52-week low. The stock is:",
            "context": {"ticker": ticker, "indicator": "52-Week Range", "value": {"pct_from_high": pct_from_high, "pct_from_low": pct_from_low}},
            "options": ["Near the top of its range - momentum trade", "Mid-range - neutral positioning", "Near the bottom of its range - potential value or value trap"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["price_range", "momentum"],
            "data_source": f"Live {ticker} technical data",
        })

    # Trend strength question
    trend = technical_data.get("trend_strength")
    if trend is not None:
        if trend in ("strong_bullish", "bullish"):
            correct = 0
            explanation = f"{ticker} has a '{trend}' trend strength based on price position relative to multiple moving averages and cross signals. Multiple bullish signals align."
        elif trend in ("bearish",):
            correct = 1
            explanation = f"{ticker} has a '{trend}' trend strength. Price is below key moving averages, indicating downward pressure."
        else:
            correct = 2
            explanation = f"{ticker} has a '{trend}' trend strength. Conflicting signals suggest waiting for clearer direction before taking a position."
        questions.append({
            "question": f"{ticker}'s overall trend strength is classified as '{trend}' based on moving average alignment. A trader should:",
            "context": {"ticker": ticker, "indicator": "Trend Strength", "value": trend},
            "options": ["Look for long (buy) entries with the trend", "Look for short (sell) entries or exit longs", "Wait for clearer signals before committing capital"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["trend", "strategy"],
            "data_source": f"Live {ticker} technical data",
        })

    return questions


def _build_fundamental_questions(fundamental_data):
    """Generate quiz questions from live fundamental data."""
    ticker = fundamental_data.get("ticker", "???")
    ratios = fundamental_data.get("ratios", {})
    growth = fundamental_data.get("growth", {})
    questions = []

    # P/E ratio interpretation
    pe = ratios.get("pe_trailing")
    if pe is not None and pe > 0:
        if pe > 40:
            correct = 1
            explanation = f"A P/E of {pe} is well above the S&P 500 average of ~20-25. This premium suggests the market expects high future growth. Whether it is justified depends on the company's growth rate."
        elif pe < 15:
            correct = 2
            explanation = f"A P/E of {pe} is below the market average, suggesting the stock may be undervalued or the market sees limited growth potential. Low P/E can indicate a value opportunity or a value trap."
        else:
            correct = 0
            explanation = f"A P/E of {pe} is roughly in line with the broader market average. This suggests the market values this stock similarly to its peers in terms of earnings expectations."
        questions.append({
            "question": f"{ticker} has a trailing P/E ratio of {pe}. Compared to the S&P 500 average of ~22, this suggests:",
            "context": {"ticker": ticker, "indicator": "P/E Ratio", "value": pe},
            "options": ["Fairly valued relative to the market", "Growth premium - market expects above-average growth", "Potentially undervalued or limited growth expected"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["pe_ratio", "valuation"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # PEG ratio question
    peg = ratios.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg < 1:
            correct = 0
            explanation = f"PEG of {peg} is below 1.0, suggesting the stock's P/E is low relative to its expected growth rate. Peter Lynch considered PEG < 1 a sign of undervaluation."
        elif peg > 2:
            correct = 2
            explanation = f"PEG of {peg} is above 2.0, meaning the P/E ratio is high even after accounting for expected growth. The stock may be overvalued relative to its growth prospects."
        else:
            correct = 1
            explanation = f"PEG of {peg} is between 1 and 2, suggesting the stock's valuation is roughly in line with its expected growth rate. This is considered fairly valued by the PEG metric."
        questions.append({
            "question": f"{ticker} has a PEG ratio of {peg}. Growth-adjusted, this stock appears:",
            "context": {"ticker": ticker, "indicator": "PEG Ratio", "value": peg},
            "options": ["Undervalued relative to growth (PEG < 1)", "Fairly valued (PEG 1-2)", "Expensive relative to growth (PEG > 2)"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["peg_ratio", "growth", "valuation"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # Debt-to-equity question
    de = ratios.get("debt_to_equity")
    if de is not None:
        if de > 200:
            correct = 0
            explanation = f"D/E of {de} (expressed as percentage) is very high. This means the company has twice as much debt as equity. While acceptable in some industries (utilities, REITs), it increases financial risk and vulnerability to rising interest rates."
        elif de < 50:
            correct = 2
            explanation = f"D/E of {de} is conservative, indicating the company is primarily funded by equity. This provides financial flexibility and resilience during downturns."
        else:
            correct = 1
            explanation = f"D/E of {de} is moderate. The company uses a balanced mix of debt and equity financing. This is common for established companies that can service debt comfortably."
        questions.append({
            "question": f"{ticker} has a debt-to-equity ratio of {de}. This level of leverage is:",
            "context": {"ticker": ticker, "indicator": "Debt-to-Equity", "value": de},
            "options": ["Highly leveraged - elevated financial risk", "Moderately leveraged - balanced financing", "Conservative - low financial risk"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["debt_to_equity", "leverage"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # ROE question
    roe = ratios.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if abs(roe) < 1 else roe
        if roe_pct > 20:
            correct = 0
            explanation = f"ROE of {roe_pct:.1f}% is excellent, well above the 15% threshold that indicates strong profitability. This suggests the company generates substantial returns on shareholder investment."
        elif roe_pct > 10:
            correct = 1
            explanation = f"ROE of {roe_pct:.1f}% is decent but not exceptional. The company generates adequate returns on equity but has room for improvement."
        else:
            correct = 2
            explanation = f"ROE of {roe_pct:.1f}% is below average, suggesting the company is not efficiently converting shareholder equity into profits. This could indicate operational issues or heavy reinvestment."
        questions.append({
            "question": f"{ticker} has a Return on Equity (ROE) of {roe_pct:.1f}%. This profitability level is:",
            "context": {"ticker": ticker, "indicator": "ROE", "value": roe_pct},
            "options": ["Excellent (ROE > 20%)", "Adequate (ROE 10-20%)", "Below average (ROE < 10%)"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["roe", "profitability"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # Profit margin question
    margin = ratios.get("profit_margin")
    if margin is not None:
        margin_pct = margin * 100 if abs(margin) < 1 else margin
        if margin_pct > 20:
            correct = 0
            explanation = f"Net profit margin of {margin_pct:.1f}% is high, indicating strong pricing power and cost control. Companies with high margins can better absorb cost increases and economic downturns."
        elif margin_pct > 5:
            correct = 1
            explanation = f"Net profit margin of {margin_pct:.1f}% is moderate. The company is profitable but margins could be compressed by competition or cost pressures."
        else:
            correct = 2
            explanation = f"Net profit margin of {margin_pct:.1f}% is thin, leaving little room for error. Even small revenue declines or cost increases could eliminate profitability."
        questions.append({
            "question": f"{ticker}'s net profit margin is {margin_pct:.1f}%. This indicates:",
            "context": {"ticker": ticker, "indicator": "Profit Margin", "value": margin_pct},
            "options": ["Strong pricing power and cost efficiency", "Moderate profitability", "Thin margins - vulnerable to cost pressures"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["margins", "profitability"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # Revenue growth question
    rev_growth = growth.get("revenue_growth")
    if rev_growth is not None:
        rev_growth_pct = rev_growth * 100 if abs(rev_growth) < 5 else rev_growth
        if rev_growth_pct > 20:
            correct = 0
            explanation = f"Revenue growth of {rev_growth_pct:.1f}% is strong, well above the economy's growth rate. This justifies a higher P/E multiple and suggests the company is gaining market share."
        elif rev_growth_pct > 0:
            correct = 1
            explanation = f"Revenue growth of {rev_growth_pct:.1f}% is positive but moderate. The company is growing but not fast enough to be classified as a high-growth stock."
        else:
            correct = 2
            explanation = f"Revenue growth of {rev_growth_pct:.1f}% indicates declining revenue. This is a red flag that could signal market share loss, industry headwinds, or product lifecycle issues."
        questions.append({
            "question": f"{ticker}'s year-over-year revenue growth is {rev_growth_pct:.1f}%. This growth rate is:",
            "context": {"ticker": ticker, "indicator": "Revenue Growth", "value": rev_growth_pct},
            "options": ["High growth (>20%) - market share expansion", "Moderate growth - steady but not exceptional", "Declining revenue - potential concern"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["revenue_growth", "growth"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # Dividend yield question
    div_yield = ratios.get("dividend_yield")
    if div_yield is not None and div_yield > 0:
        div_pct = div_yield * 100 if div_yield < 1 else div_yield
        if div_pct > 4:
            correct = 0
            explanation = f"A dividend yield of {div_pct:.2f}% is high. While attractive for income investors, very high yields can signal that the market expects a dividend cut or the stock price has dropped significantly."
        elif div_pct > 1.5:
            correct = 1
            explanation = f"A dividend yield of {div_pct:.2f}% is moderate and sustainable for most companies. This provides steady income while leaving room for reinvestment in growth."
        else:
            correct = 2
            explanation = f"A dividend yield of {div_pct:.2f}% is low, typical of growth-oriented companies that prefer to reinvest earnings rather than distribute them."
        questions.append({
            "question": f"{ticker} has a dividend yield of {div_pct:.2f}%. For an income-oriented investor, this yield is:",
            "context": {"ticker": ticker, "indicator": "Dividend Yield", "value": div_pct},
            "options": ["High yield - income opportunity but check sustainability", "Moderate yield - balanced income and growth", "Low yield - growth-focused company"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["dividend", "income"],
            "data_source": f"Live {ticker} fundamental data",
        })

    # Beta question
    beta = ratios.get("beta")
    if beta is not None:
        if beta > 1.5:
            correct = 0
            explanation = f"Beta of {beta} means {ticker} is significantly more volatile than the market. When the S&P 500 moves 1%, {ticker} historically moves about {beta}%. Higher potential returns come with higher risk."
        elif beta > 0.8:
            correct = 1
            explanation = f"Beta of {beta} means {ticker} moves roughly in line with the market. It provides average market exposure without excessive volatility premium."
        else:
            correct = 2
            explanation = f"Beta of {beta} means {ticker} is less volatile than the market. This is typical of defensive stocks (utilities, staples) that underperform in bull markets but hold up better in downturns."
        questions.append({
            "question": f"{ticker} has a beta of {beta}. This means the stock is:",
            "context": {"ticker": ticker, "indicator": "Beta", "value": beta},
            "options": ["More volatile than the market - aggressive", "Roughly in line with the market", "Less volatile than the market - defensive"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["beta", "volatility", "risk"],
            "data_source": f"Live {ticker} fundamental data",
        })

    return questions


def _build_macro_questions(macro_data):
    """Generate quiz questions from live macroeconomic data."""
    indicators = macro_data.get("indicators", {})
    questions = []

    # Yield curve question
    yield_spread = indicators.get("yield_curve_spread")
    if yield_spread is not None:
        if yield_spread < 0:
            correct = 0
            explanation = f"The yield curve spread is {yield_spread}%, meaning short-term rates exceed long-term rates (inverted). An inverted yield curve has preceded every US recession since 1970, though with variable lead times of 6-24 months."
        elif yield_spread < 0.5:
            correct = 1
            explanation = f"The yield curve spread is {yield_spread}%, which is flat. A flattening curve suggests the bond market sees slowing growth ahead, though it has not yet inverted to signal recession."
        else:
            correct = 2
            explanation = f"The yield curve spread is {yield_spread}%, which is positively sloped. This is the normal shape, indicating the bond market expects continued economic growth."
        questions.append({
            "question": f"The 10Y-2Y Treasury yield curve spread is currently {yield_spread}%. This historically signals:",
            "context": {"indicator": "Yield Curve Spread", "value": yield_spread},
            "options": ["Recession risk - inverted curve", "Caution - flattening curve", "Economic expansion - normal curve"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["yield_curve", "recession", "treasury"],
            "data_source": "Live FRED macroeconomic data",
        })

    # Fed funds rate question
    fed_rate = indicators.get("fed_funds_rate")
    if fed_rate is not None:
        if fed_rate > 5:
            correct = 0
            explanation = f"The Fed Funds rate at {fed_rate}% is restrictive. High rates slow economic growth, increase borrowing costs for companies, and make bonds more attractive relative to stocks. This is generally negative for stock valuations."
        elif fed_rate > 2:
            correct = 1
            explanation = f"The Fed Funds rate at {fed_rate}% is moderate. This level is near what economists consider 'neutral' - neither stimulating nor restricting economic growth."
        else:
            correct = 2
            explanation = f"The Fed Funds rate at {fed_rate}% is accommodative. Low rates stimulate borrowing, investment, and risk-taking. This environment is generally supportive of stock valuations."
        questions.append({
            "question": f"The Federal Funds rate is {fed_rate}%. This monetary policy stance is:",
            "context": {"indicator": "Fed Funds Rate", "value": fed_rate},
            "options": ["Restrictive - headwind for stocks", "Neutral - balanced impact", "Accommodative - tailwind for stocks"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["interest_rates", "fed_policy"],
            "data_source": "Live FRED macroeconomic data",
        })

    # Unemployment question
    unemployment = indicators.get("unemployment")
    if unemployment is not None:
        if unemployment > 6:
            correct = 0
            explanation = f"Unemployment at {unemployment}% is elevated, suggesting labor market weakness. Historically, rising unemployment indicates economic contraction and may lead to Fed rate cuts."
        elif unemployment > 4.5:
            correct = 1
            explanation = f"Unemployment at {unemployment}% is moderate, slightly above what economists consider full employment. The labor market is cooling but not distressed."
        else:
            correct = 2
            explanation = f"Unemployment at {unemployment}% indicates a tight labor market near full employment. While good for workers, it can drive wage inflation and may prompt Fed tightening."
        questions.append({
            "question": f"The US unemployment rate is {unemployment}%. This labor market condition suggests:",
            "context": {"indicator": "Unemployment Rate", "value": unemployment},
            "options": ["Weak economy - potential rate cuts", "Moderate - labor market cooling", "Tight labor market - potential wage inflation"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 1,
            "tags": ["employment", "economic_indicators"],
            "data_source": "Live FRED macroeconomic data",
        })

    # Treasury 10Y question
    treasury_10y = indicators.get("treasury_10y")
    if treasury_10y is not None:
        if treasury_10y > 4.5:
            correct = 0
            explanation = f"The 10-year Treasury yield at {treasury_10y}% is high by post-2008 standards. High long-term rates increase the discount rate for stock valuations, making future earnings less valuable today. Growth stocks are especially sensitive."
        elif treasury_10y > 3:
            correct = 1
            explanation = f"The 10-year Treasury yield at {treasury_10y}% is moderate. This level provides some competition for stocks but is not extreme enough to significantly impair equity valuations."
        else:
            correct = 2
            explanation = f"The 10-year Treasury yield at {treasury_10y}% is low, making bonds less attractive relative to stocks. Low yields support higher stock valuations through the 'TINA' effect (There Is No Alternative)."
        questions.append({
            "question": f"The 10-year Treasury yield is {treasury_10y}%. For stock valuations, this means:",
            "context": {"indicator": "10Y Treasury Yield", "value": treasury_10y},
            "options": ["Headwind - high rates compress stock valuations", "Moderate impact on valuations", "Supportive - low rates boost stock valuations"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["treasury", "interest_rates", "valuation"],
            "data_source": "Live FRED macroeconomic data",
        })

    # GDP growth question
    gdp = indicators.get("gdp_growth")
    if gdp is not None:
        if gdp > 3:
            correct = 0
            explanation = f"GDP growth of {gdp}% is strong, well above the long-term average of ~2%. Strong growth supports corporate earnings but may prompt the Fed to tighten monetary policy."
        elif gdp > 0:
            correct = 1
            explanation = f"GDP growth of {gdp}% is moderate. The economy is expanding but at a pace unlikely to trigger aggressive Fed intervention in either direction."
        else:
            correct = 2
            explanation = f"GDP growth of {gdp}% indicates contraction. Negative GDP growth raises recession risk, which is negative for cyclical stocks but may lead to supportive Fed policy (rate cuts)."
        questions.append({
            "question": f"US GDP growth is {gdp}% (annualized). For the stock market, this indicates:",
            "context": {"indicator": "GDP Growth", "value": gdp},
            "options": ["Strong expansion - earnings tailwind but rate hike risk", "Moderate growth - goldilocks scenario", "Contraction risk - potential recession"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["gdp", "economic_cycle"],
            "data_source": "Live FRED macroeconomic data",
        })

    # Consumer sentiment question
    sentiment = indicators.get("consumer_sentiment")
    if sentiment is not None:
        if sentiment > 80:
            correct = 0
            explanation = f"Consumer sentiment at {sentiment} is high, indicating optimism about the economy. High sentiment supports consumer spending, which drives ~70% of US GDP. However, extreme optimism can be a contrarian sell signal."
        elif sentiment > 60:
            correct = 1
            explanation = f"Consumer sentiment at {sentiment} is moderate. Consumers are neither overly optimistic nor pessimistic, suggesting stable spending patterns."
        else:
            correct = 2
            explanation = f"Consumer sentiment at {sentiment} is low, indicating pessimism. Low sentiment typically precedes reduced consumer spending, which can drag down GDP and corporate earnings."
        questions.append({
            "question": f"The University of Michigan Consumer Sentiment Index is {sentiment}. This reading suggests:",
            "context": {"indicator": "Consumer Sentiment", "value": sentiment},
            "options": ["High confidence - supportive of spending", "Moderate confidence - stable outlook", "Low confidence - potential spending pullback"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 2,
            "tags": ["consumer_sentiment", "economic_indicators"],
            "data_source": "Live FRED macroeconomic data",
        })

    # Real interest rate question
    real_rate = indicators.get("real_interest_rate")
    if real_rate is not None:
        if real_rate > 2:
            correct = 0
            explanation = f"A real interest rate of {real_rate}% (Fed Funds minus CPI) is significantly positive, meaning monetary policy is truly restrictive. Savers earn real returns, but borrowing costs are high. This is a headwind for economic growth and asset prices."
        elif real_rate > 0:
            correct = 1
            explanation = f"A real interest rate of {real_rate}% is slightly positive. Policy is mildly restrictive but not punishing borrowers or the economy severely."
        else:
            correct = 2
            explanation = f"A real interest rate of {real_rate}% is negative, meaning inflation exceeds the policy rate. This effectively penalizes savers and encourages borrowing and risk-taking. It is a tailwind for asset prices."
        questions.append({
            "question": f"The real interest rate (Fed Funds minus CPI) is {real_rate}%. This means:",
            "context": {"indicator": "Real Interest Rate", "value": real_rate},
            "options": ["Restrictive policy - real cost of borrowing is high", "Slightly positive - mildly restrictive", "Negative real rates - inflationary, asset-price supportive"],
            "correct_answer": correct,
            "explanation": explanation,
            "difficulty": 3,
            "tags": ["real_rates", "monetary_policy"],
            "data_source": "Live FRED macroeconomic data",
        })

    return questions


def _build_static_options_questions():
    """Generate static options trading quiz questions."""
    return [
        {
            "question": "A call option has a delta of 0.65. If the underlying stock moves up $1, the option price will approximately:",
            "context": {"indicator": "Delta", "value": 0.65},
            "options": ["Increase by $0.65", "Increase by $1.00", "Increase by $0.35"],
            "correct_answer": 0,
            "explanation": "Delta measures the option price change per $1 move in the underlying. A delta of 0.65 means the option gains approximately $0.65 for each $1 increase in the stock price.",
            "difficulty": 1,
            "tags": ["delta", "greeks"],
            "data_source": "Options theory",
        },
        {
            "question": "An option has theta of -0.05. This means each day the option loses approximately:",
            "context": {"indicator": "Theta", "value": -0.05},
            "options": ["$0.05 in value", "$5.00 in value", "$0.50 in value"],
            "correct_answer": 0,
            "explanation": "Theta represents the daily time decay of an option. Theta of -0.05 means the option loses $0.05 per day, all else being equal. Theta accelerates as expiration approaches.",
            "difficulty": 1,
            "tags": ["theta", "time_decay"],
            "data_source": "Options theory",
        },
        {
            "question": "Implied volatility is at 60% while historical volatility is at 25%. Options are:",
            "context": {"indicator": "IV vs HV", "value": {"iv": 60, "hv": 25}},
            "options": ["Expensive relative to historical norms", "Cheap relative to historical norms", "Fairly priced"],
            "correct_answer": 0,
            "explanation": "When IV significantly exceeds HV, options are expensive because the market is pricing in more volatility than has historically occurred. This often happens before earnings or major events. Option sellers benefit from IV crush when IV contracts.",
            "difficulty": 2,
            "tags": ["implied_volatility", "historical_volatility"],
            "data_source": "Options theory",
        },
        {
            "question": "A trader expects a stock to stay in a narrow range. The best options strategy is:",
            "context": {"indicator": "Strategy Selection", "value": "range-bound"},
            "options": ["Iron Condor (sell OTM call and put spreads)", "Long Straddle (buy ATM call and put)", "Bull Call Spread (buy lower, sell higher call)"],
            "correct_answer": 0,
            "explanation": "An Iron Condor profits when the stock stays within a range. It collects premium from selling OTM options and benefits from time decay and IV contraction. A straddle profits from large moves (opposite). A bull spread is directional.",
            "difficulty": 2,
            "tags": ["iron_condor", "strategy", "neutral"],
            "data_source": "Options theory",
        },
        {
            "question": "Gamma is highest for which type of option?",
            "context": {"indicator": "Gamma", "value": "position_comparison"},
            "options": ["At-the-money options near expiration", "Deep in-the-money LEAPS", "Far out-of-the-money options with months to expiry"],
            "correct_answer": 0,
            "explanation": "Gamma is highest for ATM options near expiration because delta changes most rapidly at the strike price, and shorter time to expiry amplifies this effect. This creates 'gamma risk' for option sellers.",
            "difficulty": 2,
            "tags": ["gamma", "greeks"],
            "data_source": "Options theory",
        },
        {
            "question": "Vega is most important to consider when:",
            "context": {"indicator": "Vega", "value": "application"},
            "options": ["Trading around earnings announcements", "Holding options to expiration", "Day-trading weekly options"],
            "correct_answer": 0,
            "explanation": "Vega measures sensitivity to implied volatility changes. IV typically spikes before earnings and collapses after (IV crush). Understanding vega helps traders avoid buying expensive pre-earnings options or position for the IV crush.",
            "difficulty": 2,
            "tags": ["vega", "implied_volatility", "earnings"],
            "data_source": "Options theory",
        },
        {
            "question": "The put-call ratio for the market is 1.4. As a contrarian indicator, this suggests:",
            "context": {"indicator": "Put/Call Ratio", "value": 1.4},
            "options": ["Bullish - excessive fear may signal a bottom", "Bearish - more puts indicate further downside", "Neutral - normal market conditions"],
            "correct_answer": 0,
            "explanation": "A put/call ratio of 1.4 indicates heavy put buying (fear). Contrarian theory suggests extreme fear leads to capitulation and market bottoms. When 'everyone' is bearish, there are few sellers left, and the market tends to reverse upward.",
            "difficulty": 2,
            "tags": ["put_call_ratio", "sentiment", "contrarian"],
            "data_source": "Options theory",
        },
        {
            "question": "A covered call writer's maximum profit is:",
            "context": {"indicator": "Covered Call", "value": "max_profit"},
            "options": ["Premium received + (strike - stock purchase price)", "Unlimited, like owning stock", "Premium received only"],
            "correct_answer": 0,
            "explanation": "Maximum profit on a covered call = premium + (strike - entry price). If the stock is called away, the writer keeps the premium and gains up to the strike. Above the strike, gains on the stock are offset by losses on the short call.",
            "difficulty": 2,
            "tags": ["covered_call", "strategy"],
            "data_source": "Options theory",
        },
    ]


def _build_static_risk_questions():
    """Generate static risk management quiz questions."""
    return [
        {
            "question": "You have a $50,000 portfolio and want to risk 2% per trade. Your stop loss is $3 below entry. Maximum shares to buy:",
            "context": {"indicator": "Position Sizing", "value": {"portfolio": 50000, "risk_pct": 2, "stop_distance": 3}},
            "options": ["333 shares", "1,000 shares", "500 shares"],
            "correct_answer": 0,
            "explanation": "Risk per trade = $50,000 x 2% = $1,000. Max shares = $1,000 / $3 stop distance = 333 shares. This ensures no single trade can lose more than 2% of the portfolio.",
            "difficulty": 1,
            "tags": ["position_sizing", "risk_per_trade"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "A strategy has a 45% win rate with average win of $200 and average loss of $100. The expectancy per trade is:",
            "context": {"indicator": "Expectancy", "value": {"win_rate": 45, "avg_win": 200, "avg_loss": 100}},
            "options": ["Positive: +$35", "Break-even: $0", "Negative: -$35"],
            "correct_answer": 0,
            "explanation": "Expectancy = (Win% x Avg Win) - (Loss% x Avg Loss) = (0.45 x $200) - (0.55 x $100) = $90 - $55 = +$35. Despite winning less than half the time, the favorable risk-reward ratio produces positive expectancy.",
            "difficulty": 2,
            "tags": ["expectancy", "risk_reward"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "A portfolio drops 40% from peak. What gain is needed to recover to the previous peak?",
            "context": {"indicator": "Drawdown Recovery", "value": {"drawdown_pct": 40}},
            "options": ["66.7% gain", "40% gain", "50% gain"],
            "correct_answer": 0,
            "explanation": "If $100 drops 40% to $60, you need ($100 - $60) / $60 = 66.7% gain to return to $100. This asymmetry is why avoiding large drawdowns is critical. A 50% loss requires a 100% gain to recover.",
            "difficulty": 2,
            "tags": ["max_drawdown", "recovery"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "Your portfolio has a Sharpe ratio of 0.3. This risk-adjusted performance is:",
            "context": {"indicator": "Sharpe Ratio", "value": 0.3},
            "options": ["Poor - below average risk-adjusted returns", "Good - solid risk-adjusted returns", "Excellent - exceptional risk-adjusted returns"],
            "correct_answer": 0,
            "explanation": "A Sharpe ratio of 0.3 means the portfolio barely compensates for its risk above the risk-free rate. Sharpe > 1.0 is considered good, > 2.0 very good. A ratio of 0.3 suggests either returns are too low or volatility is too high.",
            "difficulty": 2,
            "tags": ["sharpe_ratio", "risk_adjusted_return"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "An ATR-based stop loss uses 2x ATR. If ATR is $4.50, the stop should be placed:",
            "context": {"indicator": "ATR Stop", "value": {"atr": 4.50, "multiplier": 2}},
            "options": ["$9.00 below entry price", "$4.50 below entry price", "$2.25 below entry price"],
            "correct_answer": 0,
            "explanation": "Stop distance = 2 x ATR = 2 x $4.50 = $9.00 below entry. ATR-based stops adapt to each stock's volatility, providing wider stops for volatile stocks and tighter stops for stable ones. This avoids getting stopped out by normal price fluctuations.",
            "difficulty": 2,
            "tags": ["stop_loss", "atr"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "You hold 5 tech stocks and 5 financial stocks. Your diversification is:",
            "context": {"indicator": "Diversification", "value": {"sectors": 2, "stocks": 10}},
            "options": ["Poor - only 2 sectors, likely correlated", "Good - 10 stocks is diversified", "Excellent - different sectors means low correlation"],
            "correct_answer": 0,
            "explanation": "Having 10 stocks in just 2 sectors provides limited diversification. Tech and financials can be correlated during market stress. True diversification requires uncorrelated assets across asset classes (bonds, international, commodities, real estate).",
            "difficulty": 1,
            "tags": ["diversification", "correlation"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "A risk-reward ratio of 1:3 means you need a minimum win rate of approximately:",
            "context": {"indicator": "Risk-Reward Breakeven", "value": {"ratio": "1:3"}},
            "options": ["25% to break even", "33% to break even", "50% to break even"],
            "correct_answer": 0,
            "explanation": "At 1:3 risk-reward, risking $1 to make $3: Breakeven = Risk / (Risk + Reward) = 1 / (1 + 3) = 25%. You only need to win 1 out of 4 trades to break even. This is why favorable risk-reward ratios are more important than high win rates.",
            "difficulty": 2,
            "tags": ["risk_reward", "expectancy"],
            "data_source": "Risk management calculation",
        },
        {
            "question": "Correlation between two assets is -0.7. Adding both to a portfolio will:",
            "context": {"indicator": "Correlation", "value": -0.7},
            "options": ["Significantly reduce portfolio volatility", "Have no effect on portfolio risk", "Increase portfolio volatility"],
            "correct_answer": 0,
            "explanation": "Negative correlation (-0.7) means the assets tend to move in opposite directions. Combining them reduces portfolio volatility because when one drops, the other tends to rise. This is the fundamental principle behind diversification and portfolio construction.",
            "difficulty": 2,
            "tags": ["correlation", "diversification", "portfolio"],
            "data_source": "Risk management calculation",
        },
    ]


def _build_static_market_mechanics_questions():
    """Generate static market mechanics quiz questions."""
    return [
        {
            "question": "You place a market order for 1,000 shares of a stock with a $0.50 bid-ask spread. Your expected cost from the spread is:",
            "context": {"indicator": "Spread Cost", "value": {"shares": 1000, "spread": 0.50}},
            "options": ["$500 (you buy at the ask)", "$250 (half the spread)", "$0 (market orders are free)"],
            "correct_answer": 0,
            "explanation": "Market orders execute at the ask price when buying. The spread cost = 1,000 shares x $0.50 spread = $500 above the mid-price. This is an implicit transaction cost on top of commissions. Wide spreads significantly increase trading costs.",
            "difficulty": 1,
            "tags": ["bid_ask_spread", "order_types", "transaction_costs"],
            "data_source": "Market mechanics",
        },
        {
            "question": "A stock drops 8% in pre-market on bad earnings. Your stop-loss order at -5% will execute at approximately:",
            "context": {"indicator": "Gap Risk", "value": {"gap_pct": -8, "stop_pct": -5}},
            "options": ["-8% (at the market open price, not -5%)", "-5% (at your stop price exactly)", "It will not execute until the stock reaches -5%"],
            "correct_answer": 0,
            "explanation": "Stop-loss orders become market orders when triggered. If the stock gaps below your stop, you get the first available price, which is -8% in this case. This is called 'gap risk' and is why stop-losses do not guarantee your maximum loss.",
            "difficulty": 2,
            "tags": ["stop_loss", "gap_risk", "order_types"],
            "data_source": "Market mechanics",
        },
        {
            "question": "A short seller borrows and sells 100 shares at $50. The stock rises to $75. The unrealized loss is:",
            "context": {"indicator": "Short Selling", "value": {"entry": 50, "current": 75, "shares": 100}},
            "options": ["$2,500 (and losses are theoretically unlimited)", "$2,500 (capped at the entry price)", "$5,000"],
            "correct_answer": 0,
            "explanation": "Short loss = (Current Price - Entry Price) x Shares = ($75 - $50) x 100 = $2,500. Unlike long positions where loss is capped at the invested amount, short selling has unlimited loss potential because a stock can rise indefinitely.",
            "difficulty": 2,
            "tags": ["short_selling", "unlimited_risk"],
            "data_source": "Market mechanics",
        },
        {
            "question": "You buy $200,000 of stock with $100,000 cash and $100,000 margin. The maintenance margin is 25%. A margin call triggers when the account value drops to:",
            "context": {"indicator": "Margin Call", "value": {"purchase": 200000, "margin_loan": 100000, "maintenance_pct": 25}},
            "options": ["~$133,333", "$150,000", "$125,000"],
            "correct_answer": 0,
            "explanation": "Margin call triggers when equity / account value < 25%. Equity = Account Value - Loan. So (Value - $100,000) / Value = 0.25, solving: Value = $100,000 / 0.75 = $133,333. A drop of $66,667 (33%) triggers the call.",
            "difficulty": 3,
            "tags": ["margin", "margin_call", "leverage"],
            "data_source": "Market mechanics",
        },
        {
            "question": "The S&P 500 drops 7% at 10:00 AM on a trading day. What happens?",
            "context": {"indicator": "Circuit Breaker", "value": {"drop_pct": 7, "time": "10:00 AM"}},
            "options": ["Level 1 circuit breaker - 15-minute trading halt", "Trading continues normally", "Market closes for the day"],
            "correct_answer": 0,
            "explanation": "A 7% decline in the S&P 500 triggers a Level 1 circuit breaker: a 15-minute market-wide trading halt. Level 2 (13%) triggers another 15-minute halt. Level 3 (20%) closes the market for the day. Circuit breakers only trigger before 3:25 PM ET (except Level 3).",
            "difficulty": 2,
            "tags": ["circuit_breaker", "market_rules"],
            "data_source": "Market mechanics",
        },
        {
            "question": "A limit order to buy at $50 when the stock is at $52 will:",
            "context": {"indicator": "Limit Order", "value": {"limit_price": 50, "current_price": 52}},
            "options": ["Wait until the stock drops to $50 or below", "Execute immediately at $52", "Execute immediately at $50"],
            "correct_answer": 0,
            "explanation": "A buy limit order sets the maximum price you are willing to pay. Since the stock is at $52, above your $50 limit, the order joins the order book and waits. It fills only if the price drops to $50 or lower. The trade-off: guaranteed price but not guaranteed fill.",
            "difficulty": 1,
            "tags": ["limit_order", "order_types"],
            "data_source": "Market mechanics",
        },
        {
            "question": "Dark pool volume accounts for approximately what percentage of US equity trading?",
            "context": {"indicator": "Dark Pools", "value": "market_share"},
            "options": ["35-45%", "5-10%", "75-80%"],
            "correct_answer": 0,
            "explanation": "Dark pools handle roughly 35-45% of US equity volume. Institutional investors use them to trade large blocks without revealing their orders to the market. While this helps institutions, it reduces price transparency on public exchanges.",
            "difficulty": 3,
            "tags": ["dark_pools", "market_structure"],
            "data_source": "Market mechanics",
        },
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_decks():
    """Return metadata for all available study card decks.

    Returns a list of dicts with id, name, description, and card_count
    for each deck. Does not include the cards themselves.
    """
    decks = []
    for deck_id, builder in _DECK_BUILDERS.items():
        cards = builder()
        decks.append({
            "id": deck_id,
            "name": deck_id.replace("_", " ").title(),
            "description": DECK_DESCRIPTIONS.get(deck_id, ""),
            "card_count": len(cards),
        })
    return decks


# Backward-compatible alias
get_study_decks = get_decks


def get_cards(deck_id):
    """Return study cards for a specific deck.

    Parameters:
        deck_id: One of the six deck identifiers
            (e.g., 'technical_analysis').

    Returns:
        List of study card dicts, or empty list if deck not found.
    """
    builder = _DECK_BUILDERS.get(deck_id)
    if builder is None:
        logger.warning("deck not found: %s", deck_id)
        return []
    return builder()


# Backward-compatible alias
get_deck_cards = get_cards


def generate_quiz(deck_id, num_questions=5, use_live_data=True):
    """Generate a quiz with questions, using live market data from yfinance.

    Each question includes: question text, 4 options, correct_answer (index),
    explanation, context (ticker, indicator, value), data_source, and topic.

    Parameters:
        deck_id: Which deck to draw questions from.
        num_questions: Number of questions to include (1-20, default 5).
        use_live_data: Whether to fetch real stock data for questions.

    Returns:
        A quiz dict with quiz_id, questions, and metadata.
        Returns None if the deck is not found.
    """
    _cleanup_expired_quizzes()

    if deck_id not in _DECK_BUILDERS:
        logger.warning("cannot generate quiz: deck not found: %s", deck_id)
        return None

    num_questions = max(1, min(num_questions, 20))
    questions = []

    if use_live_data:
        questions = _fetch_live_questions(deck_id)

    # If we do not have enough live questions, add static ones
    static_questions = _get_static_questions(deck_id)
    questions.extend(static_questions)

    # Ensure all questions have exactly 4 options
    for q in questions:
        _ensure_four_options(q)

    # Ensure all questions have a topic field
    for q in questions:
        if "topic" not in q:
            q["topic"] = deck_id

    # Deduplicate by checking question text
    seen_texts = set()
    unique_questions = []
    for q in questions:
        text = q["question"]
        if text not in seen_texts:
            seen_texts.add(text)
            unique_questions.append(q)

    # Shuffle and limit to requested count
    random.shuffle(unique_questions)
    selected = unique_questions[:num_questions]

    # Assign sequential IDs
    for idx, q in enumerate(selected, 1):
        q["id"] = idx

    quiz_id = uuid.uuid4().hex[:12]
    quiz = {
        "quiz_id": quiz_id,
        "deck_id": deck_id,
        "questions": selected,
        "num_questions": len(selected),
        "created_at": time.time(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Store for later scoring
    _store_quiz(quiz_id, quiz)

    logger.info(
        "generated quiz %s for deck %s with %d questions",
        quiz_id, deck_id, len(selected),
    )
    return quiz


def score_quiz(quiz_id, answers):
    """Score a completed quiz and save progress.

    Parameters:
        quiz_id: The unique quiz identifier from generate_quiz.
        answers: A list of integer indices matching the user's choices.

    Returns:
        Dict with correct, total, score_pct, grade, results per question,
        weak_areas, strong_areas, and recommendations.
        Returns None if the quiz is not found or has expired.
    """
    _cleanup_expired_quizzes()

    quiz = _active_quizzes.get(quiz_id)
    if quiz is None:
        logger.warning("quiz not found or expired: %s", quiz_id)
        return None

    questions = quiz.get("questions", [])
    total = len(questions)

    if len(answers) != total:
        logger.warning(
            "answer count mismatch: expected %d, got %d",
            total, len(answers),
        )

    correct_count = 0
    by_topic: dict[str, dict] = {}
    results = []

    for idx, question in enumerate(questions):
        user_answer = answers[idx] if idx < len(answers) else -1
        is_correct = user_answer == question["correct_answer"]
        if is_correct:
            correct_count += 1

        # Track by topic using tags and topic field
        topic_key = question.get("topic", quiz.get("deck_id", "unknown"))
        if topic_key not in by_topic:
            by_topic[topic_key] = {"correct": 0, "total": 0}
        by_topic[topic_key]["total"] += 1
        if is_correct:
            by_topic[topic_key]["correct"] += 1

        for tag in question.get("tags", []):
            if tag not in by_topic:
                by_topic[tag] = {"correct": 0, "total": 0}
            by_topic[tag]["total"] += 1
            if is_correct:
                by_topic[tag]["correct"] += 1

        results.append({
            "question": question.get("question", ""),
            "your_answer": user_answer,
            "correct_answer": question["correct_answer"],
            "is_correct": is_correct,
            "explanation": question.get("explanation", ""),
            "context": question.get("context", {}),
        })

    score_pct = round((correct_count / total * 100), 1) if total > 0 else 0.0
    grade = _calculate_grade(score_pct)

    # Identify weak and strong areas
    weak_areas = []
    strong_areas = []
    for topic, counts in by_topic.items():
        if counts["total"] > 0:
            accuracy = counts["correct"] / counts["total"] * 100
            if accuracy < 50:
                weak_areas.append(topic)
            elif accuracy >= 80:
                strong_areas.append(topic)

    deck_id = quiz.get("deck_id", quiz.get("deck", ""))
    recommendations = _generate_recommendations(weak_areas, deck_id)

    score_result = {
        "quiz_id": quiz_id,
        "deck_id": deck_id,
        "correct": correct_count,
        "total": total,
        "score_pct": score_pct,
        "grade": grade,
        "results": results,
        "by_topic": by_topic,
        "weak_areas": weak_areas,
        "strong_areas": strong_areas,
        "recommendations": recommendations,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Update persistent progress
    _update_progress(score_result)

    # Remove from active quizzes after scoring
    _active_quizzes.pop(quiz_id, None)

    return score_result


def get_user_progress():
    """Read cumulative study progress with computed statistics.

    Returns a dict with total_quizzes, overall_accuracy, streak,
    by_deck stats (including skill_levels), and recent history.
    """
    progress = _load_progress()

    overall_total = progress.get("total_questions", 0)
    overall_correct = progress.get("total_correct", 0)
    overall_accuracy = round(
        (overall_correct / overall_total * 100), 1,
    ) if overall_total > 0 else 0.0

    by_deck = {}
    for deck_id, stats in progress.get("by_deck", {}).items():
        deck_total = stats.get("total_questions", 0)
        deck_correct = stats.get("total_correct", 0)
        deck_accuracy = round(
            (deck_correct / deck_total * 100), 1,
        ) if deck_total > 0 else 0.0

        by_deck[deck_id] = {
            "name": deck_id.replace("_", " ").title(),
            "quizzes": stats.get("quizzes", 0),
            "correct": deck_correct,
            "total": deck_total,
            "accuracy": deck_accuracy,
            "skill_level": _calculate_skill_level(deck_accuracy),
        }

    return {
        "total_quizzes": progress.get("total_quizzes", 0),
        "overall_accuracy": overall_accuracy,
        "overall_correct": overall_correct,
        "overall_total": overall_total,
        "streak": progress.get("streak", 0),
        "last_quiz_date": progress.get("last_quiz"),
        "by_deck": by_deck,
        "skill_levels": {
            deck_id: info["skill_level"]
            for deck_id, info in by_deck.items()
        },
        "recent_history": progress.get("quiz_history", [])[-10:],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_live_questions(deck_id):
    """Fetch live data via yfinance and build contextual quiz questions.

    Tries yfinance directly first. Falls back to data_sources.py
    functions if available, otherwise uses fallback values.
    """
    questions = []

    try:
        if deck_id in ("technical_analysis", "fundamental_analysis",
                        "options_trading", "risk_management",
                        "market_mechanics", "macro_economics"):
            tickers = random.sample(
                QUIZ_TICKERS, min(3, len(QUIZ_TICKERS)),
            )
            for ticker in tickers:
                try:
                    data = _fetch_live_ticker_data(ticker)
                    if data is not None:
                        if deck_id == "technical_analysis":
                            questions.extend(_build_technical_questions(data))
                        elif deck_id == "fundamental_analysis":
                            questions.extend(_build_fundamental_questions(data))
                        elif deck_id == "options_trading":
                            questions.extend(_build_live_options_questions(data))
                        elif deck_id == "risk_management":
                            questions.extend(_build_live_risk_questions(data))
                        elif deck_id == "market_mechanics":
                            questions.extend(_build_live_mechanics_questions(data))
                        elif deck_id == "macro_economics":
                            questions.extend(_build_live_macro_questions(data))
                except Exception as exc:
                    logger.warning(
                        "live question build failed for %s/%s: %s",
                        deck_id, ticker, exc,
                    )

        # Also try data_sources.py for richer data when available
        if deck_id == "technical_analysis":
            _try_data_sources_technical(questions)
        elif deck_id == "fundamental_analysis":
            _try_data_sources_fundamental(questions)
        elif deck_id == "macro_economics":
            _try_data_sources_macro(questions)

    except Exception as exc:
        logger.warning("live question generation error: %s", exc)

    return questions


def _try_data_sources_technical(questions):
    """Attempt to extend questions using data_sources.get_technical_profile."""
    try:
        from data_sources import get_technical_profile
        tickers = random.sample(QUIZ_TICKERS, min(2, len(QUIZ_TICKERS)))
        for ticker in tickers:
            try:
                data = get_technical_profile(ticker)
                if "error" not in data:
                    questions.extend(_build_technical_questions(data))
            except Exception as exc:
                logger.debug("data_sources technical fallback failed for %s: %s", ticker, exc)
    except ImportError:
        pass


def _try_data_sources_fundamental(questions):
    """Attempt to extend questions using data_sources.get_fundamentals."""
    try:
        from data_sources import get_fundamentals
        tickers = random.sample(QUIZ_TICKERS, min(2, len(QUIZ_TICKERS)))
        for ticker in tickers:
            try:
                data = get_fundamentals(ticker)
                if "error" not in data:
                    questions.extend(_build_fundamental_questions(data))
            except Exception as exc:
                logger.debug("data_sources fundamental fallback failed for %s: %s", ticker, exc)
    except ImportError:
        pass


def _try_data_sources_macro(questions):
    """Attempt to extend questions using data_sources.get_macro_indicators."""
    try:
        from data_sources import get_macro_indicators
        data = get_macro_indicators()
        questions.extend(_build_macro_questions(data))
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("data_sources macro fallback failed: %s", exc)


def _get_static_questions(deck_name):
    """Return pre-built static questions for a given deck."""
    if deck_name == "options_trading":
        return _build_static_options_questions()
    elif deck_name == "risk_management":
        return _build_static_risk_questions()
    elif deck_name == "market_mechanics":
        return _build_static_market_mechanics_questions()
    return []


def _cleanup_expired_quizzes():
    """Remove quizzes older than QUIZ_TTL_SECONDS from active quizzes."""
    now = time.time()
    expired = [
        qid for qid, quiz in _active_quizzes.items()
        if now - quiz.get("created_at", 0) > QUIZ_TTL_SECONDS
    ]
    for qid in expired:
        del _active_quizzes[qid]
    if expired:
        logger.info("cleaned up %d expired quizzes", len(expired))


def _store_quiz(quiz_id, quiz):
    """Store a quiz in memory for later scoring with TTL cleanup."""
    _cleanup_expired_quizzes()
    _active_quizzes[quiz_id] = quiz


def _calculate_grade(score_pct):
    """Map a percentage score to a letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score_pct >= threshold:
            return grade
    return "F"


def _calculate_skill_level(accuracy):
    """Map accuracy percentage to a skill level label."""
    for threshold, level in SKILL_THRESHOLDS:
        if accuracy >= threshold:
            return level
    return "beginner"


def _generate_recommendations(weak_areas, deck_name):
    """Generate study recommendations based on weak areas."""
    recommendations_map = {
        "rsi": "Review RSI interpretation: focus on overbought (>70) and oversold (<30) thresholds, and RSI divergence patterns.",
        "macd": "Study MACD signals: understand the relationship between MACD line, signal line, and histogram for trend identification.",
        "moving_average": "Practice moving average analysis: learn Golden/Death Cross patterns and how price interaction with SMA 20/50/200 confirms trends.",
        "bollinger_bands": "Review Bollinger Bands: focus on band squeeze patterns and how price position within the bands indicates potential reversals.",
        "volume": "Study volume analysis: learn how volume confirms price moves and On-Balance Volume (OBV) trends.",
        "candlestick": "Practice candlestick pattern recognition: focus on reversal patterns like Doji, Hammer, and Engulfing patterns in context.",
        "pe_ratio": "Review P/E ratio interpretation: understand how to compare trailing vs forward P/E and sector-specific norms.",
        "peg_ratio": "Study PEG ratio: learn how growth-adjusted valuation reveals whether a high P/E is justified by earnings growth.",
        "debt_to_equity": "Review leverage analysis: understand how D/E ratios vary by industry and signal financial risk.",
        "roe": "Study Return on Equity: learn the DuPont decomposition to distinguish profitability, efficiency, and leverage effects.",
        "free_cash_flow": "Review free cash flow analysis: understand why FCF is more reliable than net income for assessing financial health.",
        "margins": "Study margin analysis: learn how gross, operating, and net margins reveal business quality and competitive position.",
        "delta": "Review options delta: understand how delta approximates probability of expiring ITM and changes with moneyness.",
        "gamma": "Study gamma risk: learn why ATM options near expiration have the highest gamma and what that means for position management.",
        "theta": "Review time decay concepts: understand why theta accelerates near expiration and how sellers profit from it.",
        "vega": "Study implied volatility: learn about IV crush around earnings and how vega exposure affects option positions.",
        "implied_volatility": "Review IV vs HV analysis: understand when options are cheap or expensive relative to historical norms.",
        "put_call_ratio": "Study put/call ratio as a contrarian indicator: extreme readings often signal market turning points.",
        "position_sizing": "Review position sizing rules: practice the 1% risk rule and ATR-based position calculations.",
        "stop_loss": "Study stop-loss strategies: understand ATR-based, technical, and trailing stop methods and when to use each.",
        "risk_reward": "Review risk-reward mathematics: understand breakeven win rates for different R:R ratios.",
        "diversification": "Study portfolio diversification: learn about correlation and why true diversification requires uncorrelated assets.",
        "max_drawdown": "Review drawdown concepts: understand the asymmetric nature of losses and the math of recovery.",
        "sharpe_ratio": "Study risk-adjusted return metrics: learn to evaluate Sharpe and Sortino ratios in context.",
        "order_types": "Review order type mechanics: understand how market, limit, stop, and stop-limit orders execute differently.",
        "short_selling": "Study short selling: understand the unique risks including unlimited loss potential and short squeeze dynamics.",
        "margin": "Review margin mechanics: understand maintenance requirements, margin calls, and the leverage amplification effect.",
        "bid_ask_spread": "Study bid-ask spreads: understand how liquidity affects spreads and the implicit cost of wider spreads.",
        "yield_curve": "Review yield curve analysis: understand what normal, flat, and inverted curves signal about economic conditions.",
        "interest_rates": "Study Fed policy impact: learn how rate decisions flow through to stock valuations and sector performance.",
        "fed_policy": "Review Federal Reserve tools: understand QE, QT, forward guidance, and their impact on markets.",
        "gdp": "Study GDP indicators: learn leading, coincident, and lagging indicators and their market implications.",
        "employment": "Review employment data: understand Non-Farm Payrolls and unemployment as economic and market indicators.",
        "consumer_sentiment": "Study consumer sentiment: learn how the Michigan Index predicts spending trends and market direction.",
        "sector_rotation": "Review sector rotation: understand which sectors lead in each phase of the business cycle.",
    }

    recommendations = []
    for area in weak_areas:
        rec = recommendations_map.get(area)
        if rec:
            recommendations.append(rec)

    if not recommendations:
        deck_label = deck_name.replace("_", " ")
        recommendations.append(
            f"Continue studying {deck_label} concepts. "
            "Focus on areas where you felt least confident."
        )

    return recommendations


def _load_progress():
    """Load progress data from disk, returning defaults if absent."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load study progress: %s", exc)

    return {
        "total_quizzes": 0,
        "total_questions": 0,
        "total_correct": 0,
        "overall_accuracy": 0.0,
        "by_deck": {},
        "skill_levels": {},
        "streak": 0,
        "last_quiz": None,
        "quiz_history": [],
    }


def _save_progress(progress):
    """Persist progress data to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as fh:
            json.dump(progress, fh, indent=2)
    except OSError as exc:
        logger.error("Failed to save study progress: %s", exc)


def _update_progress(score_result):
    """Append a quiz result to the cumulative progress record."""
    progress = _load_progress()

    deck = score_result.get("deck_id", score_result.get("deck", "unknown"))
    total_q = score_result.get("total", score_result.get("total_questions", 0))
    correct = score_result.get("correct", 0)
    timestamp = score_result.get("timestamp", datetime.now(timezone.utc).isoformat())

    progress["total_quizzes"] += 1
    progress["total_questions"] += total_q
    progress["total_correct"] += correct

    if progress["total_questions"] > 0:
        progress["overall_accuracy"] = round(
            progress["total_correct"] / progress["total_questions"] * 100, 1,
        )

    # By-deck tracking
    if deck not in progress["by_deck"]:
        progress["by_deck"][deck] = {
            "quizzes": 0,
            "total_questions": 0,
            "total_correct": 0,
            "accuracy": 0.0,
        }
    deck_stats = progress["by_deck"][deck]
    deck_stats["quizzes"] += 1
    deck_stats["total_questions"] += total_q
    deck_stats["total_correct"] += correct
    if deck_stats["total_questions"] > 0:
        deck_stats["accuracy"] = round(
            deck_stats["total_correct"] / deck_stats["total_questions"] * 100, 1,
        )

    # Update skill levels
    for d, stats in progress["by_deck"].items():
        progress["skill_levels"][d] = _calculate_skill_level(stats["accuracy"])

    # Streak tracking: consecutive days with at least one quiz
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_quiz = progress.get("last_quiz")
    if last_quiz:
        last_date_str = last_quiz[:10]
        if last_date_str == today_str:
            pass  # Same day, streak unchanged
        elif _is_consecutive_day(last_date_str, today_str):
            progress["streak"] += 1
        else:
            progress["streak"] = 1
    else:
        progress["streak"] = 1

    progress["last_quiz"] = timestamp

    # Keep recent history (last 50 quizzes)
    max_history = 50
    history_entry = {
        "quiz_id": score_result.get("quiz_id"),
        "deck": deck,
        "score_pct": score_result.get("score_pct"),
        "grade": score_result.get("grade"),
        "timestamp": timestamp,
    }
    history = progress.get("quiz_history", [])
    history.append(history_entry)
    progress["quiz_history"] = history[-max_history:]

    _save_progress(progress)


def _is_consecutive_day(date_str_a, date_str_b):
    """Check if date_str_b is exactly one day after date_str_a."""
    try:
        from datetime import timedelta
        date_a = datetime.strptime(date_str_a, "%Y-%m-%d")
        date_b = datetime.strptime(date_str_b, "%Y-%m-%d")
        return (date_b - date_a) == timedelta(days=1)
    except ValueError:
        return False
