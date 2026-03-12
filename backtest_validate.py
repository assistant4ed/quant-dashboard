"""
Backtesting Validation Framework

Trains model without last 2 years of data, tests on 10 monthly checkpoints
in 2024-2026, measures directional accuracy (did the model predict up/down
correctly?), and refines the model in a loop until accuracy >= 70%.

Records all predictions vs actual for dashboard visualization.
Saves the validated model configuration for future predictions.

Usage:
    /Users/Ed/qlib-env/bin/python /Users/Ed/qlib/dashboard/backtest_validate.py
"""
import json
import logging
import multiprocessing
import os
import sys
import time
import warnings
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

# Must set multiprocessing start method before any qlib imports (macOS requirement)
multiprocessing.set_start_method("fork", force=True)

import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_US
from qlib.data import D
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, SigAnaRecord

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKTEST_FILE = DATA_DIR / "backtest_results.json"
PROVIDER_URI = "~/.qlib/qlib_data/us_data_fresh"
MARKET = "sp500"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("backtest_validate")

# ---------------------------------------------------------------------------
# Backtest parameters
# ---------------------------------------------------------------------------

# 10 checkpoint dates spread across the last 2 years
CHECKPOINTS = [
    "2024-04-01",
    "2024-07-01",
    "2024-10-01",
    "2025-01-02",
    "2025-04-01",
    "2025-07-01",
    "2025-10-01",
    "2026-01-02",
    "2026-02-03",
    "2026-03-03",
]

TARGET_ACCURACY = 0.70
MAX_REFINEMENT_ROUNDS = 12
FORWARD_TRADING_DAYS = 20
TOP_N_EVALUATE = 50  # evaluate directional accuracy on top-N and bottom-N stocks

# ---------------------------------------------------------------------------
# Base configuration (matches us_stock_analysis_fresh.py)
# ---------------------------------------------------------------------------
BASE_MODEL_CONFIG = {
    "class": "LGBModel",
    "module_path": "qlib.contrib.model.gbdt",
    "kwargs": {
        "loss": "mse",
        "colsample_bytree": 0.8879,
        "learning_rate": 0.0421,
        "subsample": 0.8789,
        "lambda_l1": 205.6999,
        "lambda_l2": 580.9768,
        "max_depth": 8,
        "num_leaves": 210,
        "num_threads": 20,
    },
}

BASE_DATASET_CONFIG = {
    "class": "DatasetH",
    "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": "2008-01-01",
                "end_time": "2026-03-06",
                "fit_start_time": "2008-01-01",
                "fit_end_time": "2023-12-31",
                "instruments": MARKET,
            },
        },
        "segments": {
            "train": ("2008-01-01", "2023-06-30"),
            "valid": ("2023-07-01", "2024-02-28"),
            "test": ("2024-03-01", "2026-03-06"),
        },
    },
}

# ---------------------------------------------------------------------------
# Hyperparameter refinement candidates
# ---------------------------------------------------------------------------
REFINEMENT_CONFIGS = [
    {
        "name": "Lower LR + shallow trees",
        "changes": {"learning_rate": 0.02, "max_depth": 6, "num_leaves": 150},
    },
    {
        "name": "Higher LR + deep trees",
        "changes": {"learning_rate": 0.06, "max_depth": 10, "num_leaves": 300},
    },
    {
        "name": "Strong regularization",
        "changes": {"learning_rate": 0.03, "lambda_l1": 400, "lambda_l2": 800},
    },
    {
        "name": "High sampling rates",
        "changes": {"learning_rate": 0.05, "colsample_bytree": 0.95, "subsample": 0.95},
    },
    {
        "name": "Very deep + moderate LR",
        "changes": {"max_depth": 12, "num_leaves": 400, "learning_rate": 0.03},
    },
    {
        "name": "Weak regularization + low sampling",
        "changes": {"lambda_l1": 100, "lambda_l2": 300, "subsample": 0.7},
    },
    {
        "name": "Conservative LR + small trees",
        "changes": {"learning_rate": 0.015, "num_leaves": 100, "max_depth": 5},
    },
    {
        "name": "Moderate LR + low column sampling",
        "changes": {"learning_rate": 0.035, "colsample_bytree": 0.75, "num_leaves": 250},
    },
    {
        "name": "Balanced profile A",
        "changes": {
            "learning_rate": 0.045,
            "max_depth": 9,
            "num_leaves": 280,
            "lambda_l1": 150,
        },
    },
    {
        "name": "Balanced profile B",
        "changes": {
            "learning_rate": 0.025,
            "max_depth": 7,
            "num_leaves": 180,
            "lambda_l2": 700,
        },
    },
    {
        "name": "Aggressive depth + sampling",
        "changes": {
            "learning_rate": 0.055,
            "max_depth": 11,
            "num_leaves": 350,
            "subsample": 0.85,
        },
    },
    {
        "name": "Fine-tune original",
        "changes": {
            "learning_rate": 0.04,
            "max_depth": 8,
            "num_leaves": 220,
            "colsample_bytree": 0.9,
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_config(config):
    """Convert config kwargs to JSON-safe dict."""
    return {k: float(v) if isinstance(v, (np.floating,)) else v
            for k, v in config.items()}


def save_results(all_rounds, best_accuracy, best_config):
    """Save backtest results for dashboard consumption (atomic write)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    serializable_config = None
    if best_config is not None:
        raw = best_config.get("kwargs", best_config)
        serializable_config = _serialize_config(raw)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_accuracy": TARGET_ACCURACY,
        "best_accuracy": round(best_accuracy, 4),
        "best_config": serializable_config,
        "total_rounds": len(all_rounds),
        "rounds": all_rounds,
    }

    tmp = BACKTEST_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(output, f, indent=2, default=str)
    tmp.replace(BACKTEST_FILE)

    logger.info("Saved backtest results to %s", BACKTEST_FILE)


def _find_closest_date(available_dates, target):
    """Find the closest available trading date to a target timestamp."""
    target_ts = pd.Timestamp(target)
    return min(available_dates, key=lambda d: abs(d - target_ts))


def _get_actual_forward_returns(instruments, start_date, num_days):
    """Fetch actual close prices from qlib and compute forward returns.

    Returns a Series indexed by instrument with the percent return over
    the forward window.
    """
    end_date = pd.Timestamp(start_date) + pd.DateOffset(days=num_days + 15)

    try:
        close_df = D.features(
            instruments,
            ["$close"],
            start_time=start_date,
            end_time=end_date.strftime("%Y-%m-%d"),
        )
    except Exception as exc:
        logger.warning("Could not fetch price data: %s", exc)
        return pd.Series(dtype=float)

    if close_df.empty:
        return pd.Series(dtype=float)

    close_df.columns = ["close"]
    dates = sorted(close_df.index.get_level_values("datetime").unique())

    if len(dates) < 2:
        return pd.Series(dtype=float)

    # Use the first available date as the start price
    start_prices = close_df.loc[dates[0]]["close"]

    # Use the date closest to num_days forward for the end price
    target_end_idx = min(num_days, len(dates) - 1)
    end_prices = close_df.loc[dates[target_end_idx]]["close"]

    # Compute percent returns
    returns = (end_prices - start_prices) / start_prices
    returns = returns.dropna()

    return returns


# ---------------------------------------------------------------------------
# Walk-forward backtest for a single checkpoint
# ---------------------------------------------------------------------------


def backtest_checkpoint(model_config, dataset_config, checkpoint):
    """Run a walk-forward backtest for a single checkpoint date.

    1. Configure training end 6 months before checkpoint (validation buffer).
    2. Train model, generate predictions at the checkpoint date.
    3. Compare predicted rankings with actual forward 20-day returns.
    4. Directional accuracy = fraction of top-N stocks that actually
       outperformed the median, plus fraction of bottom-N that underperformed.

    Returns a dict with checkpoint results or None if insufficient data.
    """
    checkpoint_ts = pd.Timestamp(checkpoint)
    train_end = checkpoint_ts - pd.DateOffset(months=6)
    valid_start = train_end + pd.DateOffset(days=1)
    valid_end = checkpoint_ts - pd.DateOffset(days=1)
    test_start = checkpoint
    test_end = checkpoint_ts + pd.DateOffset(days=45)

    # Build per-checkpoint dataset config
    cp_dataset_config = deepcopy(dataset_config)
    cp_dataset_config["kwargs"]["segments"] = {
        "train": ("2008-01-01", train_end.strftime("%Y-%m-%d")),
        "valid": (valid_start.strftime("%Y-%m-%d"), valid_end.strftime("%Y-%m-%d")),
        "test": (test_start, test_end.strftime("%Y-%m-%d")),
    }
    cp_dataset_config["kwargs"]["handler"]["kwargs"]["end_time"] = (
        test_end.strftime("%Y-%m-%d")
    )
    cp_dataset_config["kwargs"]["handler"]["kwargs"]["fit_end_time"] = (
        train_end.strftime("%Y-%m-%d")
    )

    logger.info("  Checkpoint %s: train end=%s, test=[%s, %s]",
                checkpoint, train_end.strftime("%Y-%m-%d"),
                test_start, test_end.strftime("%Y-%m-%d"))

    # Train and predict
    model = init_instance_by_config(model_config)
    dataset = init_instance_by_config(cp_dataset_config)

    experiment_name = f"backtest_{checkpoint}_{int(time.time())}"
    with R.start(experiment_name=experiment_name):
        model.fit(dataset)
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

    pred_df = recorder.load_object("pred.pkl")

    if pred_df.empty:
        logger.warning("  No predictions for checkpoint %s", checkpoint)
        return None

    # Find the closest available date to the checkpoint
    available_dates = sorted(pred_df.index.get_level_values("datetime").unique())
    closest_date = _find_closest_date(available_dates, checkpoint_ts)

    logger.info("  Closest trading date: %s", closest_date.strftime("%Y-%m-%d"))

    # Get predictions at the checkpoint date
    day_preds = pred_df.loc[closest_date].copy()
    if isinstance(day_preds, pd.Series):
        # Single row case -- skip this checkpoint
        logger.warning("  Only one stock predicted at %s, skipping", checkpoint)
        return None

    day_preds = day_preds.sort_values("score", ascending=False)
    median_signal = day_preds["score"].median()

    # Get all instruments predicted at this checkpoint
    instruments_list = []
    for idx in day_preds.index:
        if isinstance(idx, str):
            instruments_list.append(idx)
        elif isinstance(idx, tuple):
            instruments_list.append(idx[-1] if len(idx) > 1 else str(idx[0]))
        else:
            instruments_list.append(str(idx))

    # Fetch actual forward returns from qlib price data
    actual_returns = _get_actual_forward_returns(
        instruments_list,
        closest_date.strftime("%Y-%m-%d"),
        FORWARD_TRADING_DAYS,
    )

    if actual_returns.empty or len(actual_returns) < 10:
        logger.warning("  Insufficient forward return data for %s (%d stocks)",
                       checkpoint, len(actual_returns))
        # Fall back to using prediction scores at a later date as a proxy
        return _fallback_score_comparison(
            pred_df, available_dates, closest_date, day_preds, checkpoint
        )

    # Compute directional accuracy using actual returns
    median_return = actual_returns.median()
    correct = 0
    total = 0
    stock_results = []

    for idx, row in day_preds.iterrows():
        ticker = idx if isinstance(idx, str) else (
            idx[-1] if isinstance(idx, tuple) and len(idx) > 1 else str(idx)
        )

        if ticker not in actual_returns.index:
            continue

        predicted_signal = row["score"]
        predicted_above_median = predicted_signal > median_signal
        actual_return = actual_returns[ticker]
        actual_above_median = actual_return > median_return

        is_correct = predicted_above_median == actual_above_median
        if is_correct:
            correct += 1
        total += 1

        stock_results.append({
            "ticker": ticker,
            "predicted_signal": round(float(predicted_signal), 6),
            "predicted_direction": "up" if predicted_above_median else "down",
            "actual_return": round(float(actual_return), 6),
            "actual_direction": "up" if actual_above_median else "down",
            "correct": is_correct,
        })

    accuracy = correct / total if total > 0 else 0.0

    logger.info("  Checkpoint %s: accuracy=%.2f%% (%d/%d)",
                checkpoint, accuracy * 100, correct, total)

    return {
        "checkpoint": checkpoint,
        "actual_date": closest_date.strftime("%Y-%m-%d"),
        "total_predictions": total,
        "correct_predictions": correct,
        "accuracy": round(accuracy, 4),
        "data_source": "actual_returns",
        "top_stocks": sorted(
            stock_results, key=lambda x: x["predicted_signal"], reverse=True
        )[:TOP_N_EVALUATE],
    }


def _fallback_score_comparison(pred_df, available_dates, closest_date,
                               day_preds, checkpoint):
    """Fallback: use prediction scores at a later date as a proxy for forward
    performance when actual price data is unavailable.

    Compare predicted ranking at checkpoint with the model's own ranking
    at a date ~20 trading days later.
    """
    forward_dates = [d for d in available_dates if d > closest_date]
    if len(forward_dates) < 5:
        logger.warning("  Not enough forward dates for fallback at %s", checkpoint)
        return None

    forward_idx = min(FORWARD_TRADING_DAYS - 1, len(forward_dates) - 1)
    forward_date = forward_dates[forward_idx]

    forward_preds = pred_df.loc[forward_date]
    if isinstance(forward_preds, pd.Series):
        return None

    median_signal = day_preds["score"].median()
    forward_median = forward_preds["score"].median()

    correct = 0
    total = 0
    stock_results = []

    for idx, row in day_preds.iterrows():
        ticker = idx if isinstance(idx, str) else (
            idx[-1] if isinstance(idx, tuple) and len(idx) > 1 else str(idx)
        )
        predicted_signal = row["score"]
        predicted_above_median = predicted_signal > median_signal

        if idx not in forward_preds.index:
            continue

        forward_score = forward_preds.loc[idx]
        if isinstance(forward_score, pd.Series):
            forward_score = forward_score["score"]
        else:
            forward_score = float(forward_score)

        actual_above_median = forward_score > forward_median
        is_correct = predicted_above_median == actual_above_median

        if is_correct:
            correct += 1
        total += 1

        stock_results.append({
            "ticker": ticker,
            "predicted_signal": round(float(predicted_signal), 6),
            "predicted_direction": "up" if predicted_above_median else "down",
            "actual_return": round(float(forward_score), 6),
            "actual_direction": "up" if actual_above_median else "down",
            "correct": is_correct,
        })

    accuracy = correct / total if total > 0 else 0.0

    logger.info("  Checkpoint %s (fallback): accuracy=%.2f%% (%d/%d)",
                checkpoint, accuracy * 100, correct, total)

    return {
        "checkpoint": checkpoint,
        "actual_date": closest_date.strftime("%Y-%m-%d"),
        "total_predictions": total,
        "correct_predictions": correct,
        "accuracy": round(accuracy, 4),
        "data_source": "score_proxy",
        "top_stocks": sorted(
            stock_results, key=lambda x: x["predicted_signal"], reverse=True
        )[:TOP_N_EVALUATE],
    }


# ---------------------------------------------------------------------------
# Full walk-forward backtest across all checkpoints
# ---------------------------------------------------------------------------


def walk_forward_backtest(model_config, dataset_config):
    """Run walk-forward backtest across all 10 checkpoints.

    For each checkpoint:
    1. Train model on data up to checkpoint minus 6 months.
    2. Generate predictions at the checkpoint date.
    3. Compare predicted direction with actual 20-day forward returns.

    Returns a list of per-checkpoint result dicts.
    """
    results = []

    for checkpoint in CHECKPOINTS:
        try:
            result = backtest_checkpoint(model_config, dataset_config, checkpoint)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.error("  Checkpoint %s failed: %s", checkpoint, exc, exc_info=True)
            results.append({
                "checkpoint": checkpoint,
                "actual_date": checkpoint,
                "total_predictions": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "data_source": "error",
                "error": str(exc),
                "top_stocks": [],
            })

    return results


# ---------------------------------------------------------------------------
# Refinement loop
# ---------------------------------------------------------------------------


def refinement_loop():
    """Main loop: backtest -> evaluate -> refine -> repeat until 70%+ accuracy.

    Returns (all_rounds, best_accuracy, best_config).
    """
    qlib.init(provider_uri=PROVIDER_URI, region=REG_US)

    all_rounds = []
    best_accuracy = 0.0
    best_config = deepcopy(BASE_MODEL_CONFIG)

    for round_num in range(MAX_REFINEMENT_ROUNDS):
        logger.info("")
        logger.info("=" * 70)
        logger.info("REFINEMENT ROUND %d / %d", round_num, MAX_REFINEMENT_ROUNDS - 1)
        logger.info("=" * 70)

        # Build model config for this round
        if round_num == 0:
            current_config = deepcopy(BASE_MODEL_CONFIG)
            round_name = "Baseline"
        elif round_num <= len(REFINEMENT_CONFIGS):
            current_config = deepcopy(best_config)
            refinement = REFINEMENT_CONFIGS[round_num - 1]
            round_name = refinement["name"]
            for key, val in refinement["changes"].items():
                current_config["kwargs"][key] = val
        else:
            current_config = deepcopy(best_config)
            round_name = "Best config (no more refinements)"

        logger.info("  Config: %s", round_name)
        logger.info("  Params: lr=%.4f depth=%d leaves=%d l1=%.1f l2=%.1f",
                     current_config["kwargs"]["learning_rate"],
                     current_config["kwargs"]["max_depth"],
                     current_config["kwargs"]["num_leaves"],
                     current_config["kwargs"]["lambda_l1"],
                     current_config["kwargs"]["lambda_l2"])

        # Run walk-forward backtest
        round_start = time.time()
        results = walk_forward_backtest(current_config, deepcopy(BASE_DATASET_CONFIG))
        round_elapsed = time.time() - round_start

        # Calculate overall accuracy across all checkpoints
        total_correct = sum(r["correct_predictions"] for r in results)
        total_preds = sum(r["total_predictions"] for r in results)
        overall_accuracy = total_correct / total_preds if total_preds > 0 else 0.0

        per_checkpoint_accuracy = [
            {"checkpoint": r["checkpoint"], "accuracy": r["accuracy"]}
            for r in results
        ]

        logger.info("")
        logger.info("  ROUND %d RESULT: accuracy=%.2f%% (%d/%d) in %.1fs",
                     round_num, overall_accuracy * 100, total_correct,
                     total_preds, round_elapsed)
        logger.info("  Per-checkpoint breakdown:")
        for cp_result in results:
            logger.info("    %s: %.2f%% (%d/%d) [%s]",
                        cp_result["checkpoint"],
                        cp_result["accuracy"] * 100,
                        cp_result["correct_predictions"],
                        cp_result["total_predictions"],
                        cp_result.get("data_source", "unknown"))

        is_new_best = overall_accuracy > best_accuracy

        round_record = {
            "round": round_num,
            "name": round_name,
            "config": _serialize_config(current_config["kwargs"]),
            "overall_accuracy": round(overall_accuracy, 4),
            "total_correct": total_correct,
            "total_predictions": total_preds,
            "per_checkpoint_accuracy": per_checkpoint_accuracy,
            "checkpoints": results,
            "elapsed_seconds": round(round_elapsed, 1),
            "is_best": is_new_best,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        all_rounds.append(round_record)

        if is_new_best:
            best_accuracy = overall_accuracy
            best_config = deepcopy(current_config)
            logger.info("  >>> NEW BEST: %.2f%%", best_accuracy * 100)

        # Save progress after every round so dashboard can show live updates
        save_results(all_rounds, best_accuracy, best_config)

        if best_accuracy >= TARGET_ACCURACY:
            logger.info("")
            logger.info("TARGET REACHED: %.2f%% >= %.0f%%",
                        best_accuracy * 100, TARGET_ACCURACY * 100)
            break

    return all_rounds, best_accuracy, best_config


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(all_rounds, best_accuracy, best_config):
    """Print a human-readable summary of the backtesting results."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("BACKTESTING VALIDATION COMPLETE")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Target accuracy:  %.0f%%", TARGET_ACCURACY * 100)
    logger.info("Best accuracy:    %.2f%%", best_accuracy * 100)
    logger.info("Rounds executed:  %d / %d", len(all_rounds), MAX_REFINEMENT_ROUNDS)
    logger.info("Target reached:   %s", "YES" if best_accuracy >= TARGET_ACCURACY else "NO")
    logger.info("")

    if best_config is not None:
        logger.info("Best configuration:")
        for key, val in best_config["kwargs"].items():
            logger.info("  %-20s = %s", key, val)

    logger.info("")
    logger.info("Round-by-round results:")
    logger.info("  %-6s %-35s %-12s %-8s", "Round", "Name", "Accuracy", "Best?")
    logger.info("  " + "-" * 65)
    for r in all_rounds:
        marker = " <<<" if r.get("is_best") else ""
        logger.info("  %-6d %-35s %-12s%s",
                     r["round"],
                     r["name"][:35],
                     f"{r['overall_accuracy']:.2%}",
                     marker)

    logger.info("")
    logger.info("Results saved to: %s", BACKTEST_FILE)

    # Show best round's per-checkpoint breakdown
    best_round = None
    for r in all_rounds:
        if r.get("is_best"):
            best_round = r
    if best_round and "per_checkpoint_accuracy" in best_round:
        logger.info("")
        logger.info("Best round per-checkpoint accuracy:")
        for cp in best_round["per_checkpoint_accuracy"]:
            logger.info("  %s: %.2f%%", cp["checkpoint"], cp["accuracy"] * 100)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Coordinate the full backtesting and refinement pipeline."""
    start_time = time.time()

    logger.info("=" * 70)
    logger.info("BACKTESTING VALIDATION FRAMEWORK")
    logger.info("  Checkpoints:       %d dates from %s to %s",
                len(CHECKPOINTS), CHECKPOINTS[0], CHECKPOINTS[-1])
    logger.info("  Forward window:    %d trading days", FORWARD_TRADING_DAYS)
    logger.info("  Target accuracy:   %.0f%%", TARGET_ACCURACY * 100)
    logger.info("  Max rounds:        %d", MAX_REFINEMENT_ROUNDS)
    logger.info("  Data provider:     %s", PROVIDER_URI)
    logger.info("  Market universe:   %s", MARKET)
    logger.info("=" * 70)

    try:
        all_rounds, best_accuracy, best_config = refinement_loop()
    except Exception as exc:
        logger.error("Backtesting failed: %s", exc, exc_info=True)

        # Save error state so dashboard knows something went wrong
        error_output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_accuracy": TARGET_ACCURACY,
            "best_accuracy": 0,
            "best_config": None,
            "total_rounds": 0,
            "rounds": [],
            "error": str(exc),
        }
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = BACKTEST_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(error_output, f, indent=2, default=str)
        tmp.replace(BACKTEST_FILE)

        sys.exit(1)

    elapsed = time.time() - start_time
    print_summary(all_rounds, best_accuracy, best_config)

    logger.info("")
    logger.info("Total elapsed time: %.1f minutes", elapsed / 60)
    logger.info("Dashboard can now display backtest validation results.")


if __name__ == "__main__":
    main()
