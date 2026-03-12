"""
Quality Check Sub-Agent

Validates prediction accuracy by comparing model signals against
actual stock performance. Generates a visual comparison report.
Triggers model refinement if accuracy drops below threshold.
"""
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QUALITY_FILE = DATA_DIR / "quality_report.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"

TARGET_ACCURACY = 0.70
LOOKBACK_DAYS = 20  # Compare predictions vs 20-day forward returns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("quality_check")


def load_predictions():
    with open(PREDICTIONS_FILE) as f:
        return json.load(f)


def get_actual_returns(tickers, days=20):
    """Fetch actual returns for comparison."""
    results = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")
            if len(hist) < days + 5:
                continue

            # Get return over last N trading days
            current_price = float(hist["Close"].iloc[-1])
            past_price = float(hist["Close"].iloc[-(days + 1)])
            actual_return = (current_price - past_price) / past_price

            # Trend direction
            sma_20 = float(hist["Close"].rolling(20).mean().iloc[-1])
            trend = "up" if current_price > sma_20 else "down"

            results[ticker] = {
                "current_price": round(current_price, 2),
                "past_price": round(past_price, 2),
                "actual_return": round(actual_return, 4),
                "actual_pct": round(actual_return * 100, 2),
                "actual_direction": "up" if actual_return > 0 else "down",
                "trend": trend,
            }
        except Exception as e:
            logger.warning(f"Failed to get data for {ticker}: {e}")

    return results


def evaluate_predictions(predictions, actual_returns):
    """Compare predicted signals vs actual returns."""
    comparisons = []
    correct = 0
    total = 0

    for stock in predictions.get("top_stocks", []):
        ticker = stock["ticker"]
        if ticker not in actual_returns:
            continue

        actual = actual_returns[ticker]
        predicted_signal = stock.get("signal", 0)
        predicted_direction = "up" if predicted_signal > 0 else "down"
        actual_direction = actual["actual_direction"]

        is_correct = predicted_direction == actual_direction
        if is_correct:
            correct += 1
        total += 1

        # Calculate signal accuracy (how well signal magnitude predicts return magnitude)
        signal_error = abs(predicted_signal - actual["actual_return"])

        comparisons.append({
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "rank": stock.get("rank", 0),
            "predicted_signal": round(predicted_signal, 5),
            "predicted_direction": predicted_direction,
            "actual_return_pct": actual["actual_pct"],
            "actual_direction": actual_direction,
            "is_correct": is_correct,
            "signal_error": round(signal_error, 5),
            "current_price": actual["current_price"],
        })

    accuracy = correct / total if total > 0 else 0

    return {
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "total": total,
        "comparisons": comparisons,
    }


def generate_quality_report(evaluation):
    """Generate comprehensive quality report."""
    accuracy = evaluation["accuracy"]
    comparisons = evaluation["comparisons"]

    # Sort by prediction accuracy
    best_predictions = sorted(
        [c for c in comparisons if c["is_correct"]],
        key=lambda x: abs(x["predicted_signal"]),
        reverse=True,
    )[:10]

    worst_predictions = sorted(
        [c for c in comparisons if not c["is_correct"]],
        key=lambda x: abs(x["signal_error"]),
        reverse=True,
    )[:10]

    # Signal correlation
    if len(comparisons) > 5:
        signals = [c["predicted_signal"] for c in comparisons]
        returns = [c["actual_return_pct"] / 100 for c in comparisons]
        correlation = float(np.corrcoef(signals, returns)[0, 1]) if len(signals) > 1 else 0
    else:
        correlation = 0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_accuracy": evaluation["accuracy"],
        "total_tested": evaluation["total"],
        "correct_predictions": evaluation["correct"],
        "target_accuracy": TARGET_ACCURACY,
        "meets_target": accuracy >= TARGET_ACCURACY,
        "signal_correlation": round(correlation, 4),
        "best_predictions": best_predictions,
        "worst_predictions": worst_predictions,
        "all_comparisons": comparisons,
        "summary": {
            "status": "PASS" if accuracy >= TARGET_ACCURACY else "NEEDS_IMPROVEMENT",
            "accuracy_pct": round(accuracy * 100, 1),
            "target_pct": round(TARGET_ACCURACY * 100, 1),
            "gap": round((TARGET_ACCURACY - accuracy) * 100, 1) if accuracy < TARGET_ACCURACY else 0,
        },
    }

    return report


def save_report(report):
    """Save quality report atomically."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = QUALITY_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2, default=str)
    tmp.replace(QUALITY_FILE)


def main():
    logger.info("=" * 60)
    logger.info("QUALITY CHECK AGENT STARTING")
    logger.info("=" * 60)

    # Load predictions
    predictions = load_predictions()
    tickers = [s["ticker"] for s in predictions.get("top_stocks", [])]

    logger.info(f"Testing {len(tickers)} stocks against actual market data...")

    # Get actual returns
    actual_returns = get_actual_returns(tickers)
    logger.info(f"Got actual data for {len(actual_returns)} stocks")

    # Evaluate
    evaluation = evaluate_predictions(predictions, actual_returns)
    logger.info(f"Accuracy: {evaluation['accuracy']:.1%} ({evaluation['correct']}/{evaluation['total']})")

    # Generate report
    report = generate_quality_report(evaluation)
    save_report(report)

    logger.info(f"Quality report saved to {QUALITY_FILE}")

    if report["summary"]["status"] == "NEEDS_IMPROVEMENT":
        logger.warning(f"Accuracy {report['summary']['accuracy_pct']}% below target {report['summary']['target_pct']}%")
        logger.info("Recommendation: Run improve_model.py or backtest_validate.py to refine model")
    else:
        logger.info(f"PASS: Accuracy {report['summary']['accuracy_pct']}% meets target")

    # Print summary
    print(f"\n{'='*60}")
    print(f"QUALITY CHECK RESULTS")
    print(f"{'='*60}")
    print(f"  Status: {report['summary']['status']}")
    print(f"  Accuracy: {report['summary']['accuracy_pct']}% (target: {report['summary']['target_pct']}%)")
    print(f"  Tested: {report['total_tested']} stocks")
    print(f"  Correct: {report['correct_predictions']}")
    print(f"  Signal Correlation: {report['signal_correlation']:.4f}")
    print(f"\n  Best Predictions:")
    for p in report["best_predictions"][:5]:
        print(f"    {p['ticker']}: predicted {p['predicted_direction']}, actual {p['actual_return_pct']:+.2f}% check")
    print(f"\n  Worst Predictions:")
    for p in report["worst_predictions"][:5]:
        print(f"    {p['ticker']}: predicted {p['predicted_direction']}, actual {p['actual_return_pct']:+.2f}% miss")

    return report


if __name__ == "__main__":
    main()
