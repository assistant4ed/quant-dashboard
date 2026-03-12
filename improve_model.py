"""
Self-Improving Stock Prediction Agent

Iteratively refines the LightGBM model by:
1. Evaluating current model performance (IC, ICIR, Rank IC)
2. Proposing improvements (hyperparameters, features, data splits)
3. Implementing and testing improvements
4. Keeping the best performing model
5. Repeating until convergence or max rounds

Writes status to improvement_status.json for the dashboard to display.

Usage:
    /Users/Ed/qlib-env/bin/python /Users/Ed/qlib/dashboard/improve_model.py
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
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, SigAnaRecord

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATUS_FILE = DATA_DIR / "improvement_status.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"

PROVIDER_URI = "~/.qlib/qlib_data/us_data_fresh"
MARKET = "sp500"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("improve_agent")

# ---------------------------------------------------------------------------
# Base configuration (matches us_stock_analysis_fresh.py exactly)
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
            "train": ("2008-01-01", "2023-12-31"),
            "valid": ("2024-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2026-03-06"),
        },
    },
}

# ---------------------------------------------------------------------------
# Improvement loop parameters
# ---------------------------------------------------------------------------
MAX_ROUNDS = 8
CONVERGENCE_THRESHOLD = 0.001  # Stop if improvement < 0.1%
MAX_STALE_ROUNDS = 3  # Stop after this many rounds without improvement

# Scoring weights
IC_WEIGHT = 0.4
ICIR_WEIGHT = 0.3
RANK_IC_WEIGHT = 0.2
RANK_ICIR_WEIGHT = 0.1

# Prediction ranking parameters (must match generate_data.py)
LOOKBACK_DAYS = 20
TOP_QUARTILE_THRESHOLD = 0.75
SIGNAL_WEIGHT = 0.7
CONSISTENCY_WEIGHT = 0.3
TOP_N_CONSENSUS = 30

# ---------------------------------------------------------------------------
# Stock metadata (imported from generate_data for name resolution)
# ---------------------------------------------------------------------------
STOCK_META = {
    "AAPL": ("Apple", "苹果", "Technology", "科技"),
    "MSFT": ("Microsoft", "微软", "Technology", "科技"),
    "GOOGL": ("Alphabet", "谷歌", "Communication Services", "通信服务"),
    "AMZN": ("Amazon", "亚马逊", "Consumer Discretionary", "可选消费"),
    "NVDA": ("NVIDIA", "英伟达", "Technology", "科技"),
    "META": ("Meta Platforms", "Meta", "Communication Services", "通信服务"),
    "TSLA": ("Tesla", "特斯拉", "Consumer Discretionary", "可选消费"),
    "AMD": ("Advanced Micro Devices", "超威半导体", "Technology", "科技"),
    "INTC": ("Intel", "英特尔", "Technology", "科技"),
    "NFLX": ("Netflix", "奈飞", "Communication Services", "通信服务"),
    "STX": ("Seagate Technology", "希捷科技", "Technology", "科技"),
    "NTRS": ("Northern Trust", "北方信托", "Financial Services", "金融服务"),
    "LUV": ("Southwest Airlines", "西南航空", "Airlines", "航空"),
    "KMX": ("CarMax", "CarMax汽车", "Consumer Discretionary", "可选消费"),
    "CMG": ("Chipotle Mexican Grill", "墨式烧烤", "Consumer Discretionary", "可选消费"),
    "BA": ("Boeing", "波音", "Industrials", "工业"),
    "XRX": ("Xerox Holdings", "施乐", "Technology", "科技"),
    "RCL": ("Royal Caribbean", "皇家加勒比", "Consumer Discretionary", "可选消费"),
    "LEG": ("Leggett & Platt", "礼恩派", "Consumer Discretionary", "可选消费"),
    "BWA": ("BorgWarner", "博格华纳", "Consumer Discretionary", "可选消费"),
    "ALK": ("Alaska Air Group", "阿拉斯加航空", "Airlines", "航空"),
    "IPGP": ("IPG Photonics", "IPG光电", "Technology", "科技"),
    "IVZ": ("Invesco", "景顺", "Financial Services", "金融服务"),
    "MCHP": ("Microchip Technology", "微芯科技", "Technology", "科技"),
    "STT": ("State Street", "道富集团", "Financial Services", "金融服务"),
    "DAL": ("Delta Air Lines", "达美航空", "Airlines", "航空"),
    "ZION": ("Zions Bancorporation", "锡安银行", "Financial Services", "金融服务"),
    "MS": ("Morgan Stanley", "摩根士丹利", "Financial Services", "金融服务"),
    "GM": ("General Motors", "通用汽车", "Consumer Discretionary", "可选消费"),
    "AAP": ("Advance Auto Parts", "先进汽车零件", "Consumer Discretionary", "可选消费"),
    "HBAN": ("Huntington Bancshares", "亨廷顿银行", "Financial Services", "金融服务"),
    "ALB": ("Albemarle", "雅保", "Materials", "原材料"),
    "KEY": ("KeyCorp", "KeyCorp银行", "Financial Services", "金融服务"),
    "FMC": ("FMC Corporation", "FMC富美实", "Materials", "原材料"),
    "VFC": ("VF Corporation", "威富集团", "Consumer Discretionary", "可选消费"),
    "NEM": ("Newmont Corporation", "纽蒙特矿业", "Materials", "原材料"),
    "FFIV": ("F5 Networks", "F5网络", "Technology", "科技"),
    "TPR": ("Tapestry", "泰佩思琦", "Consumer Discretionary", "可选消费"),
    "MOS": ("Mosaic Company", "美盛", "Materials", "原材料"),
    "FCX": ("Freeport-McMoRan", "自由港", "Materials", "原材料"),
    "LB": ("L Brands", "L Brands", "Consumer Discretionary", "可选消费"),
    "JBHT": ("J.B. Hunt Transport", "JB亨特运输", "Industrials", "工业"),
    "PPG": ("PPG Industries", "PPG工业", "Materials", "原材料"),
    "JPM": ("JPMorgan Chase", "摩根大通", "Financial Services", "金融服务"),
    "BAC": ("Bank of America", "美国银行", "Financial Services", "金融服务"),
    "WFC": ("Wells Fargo", "富国银行", "Financial Services", "金融服务"),
    "GS": ("Goldman Sachs", "高盛", "Financial Services", "金融服务"),
    "C": ("Citigroup", "花旗集团", "Financial Services", "金融服务"),
    "V": ("Visa", "维萨", "Financial Services", "金融服务"),
    "MA": ("Mastercard", "万事达", "Financial Services", "金融服务"),
    "JNJ": ("Johnson & Johnson", "强生", "Healthcare", "医疗健康"),
    "PFE": ("Pfizer", "辉瑞", "Healthcare", "医疗健康"),
    "UNH": ("UnitedHealth", "联合健康", "Healthcare", "医疗健康"),
    "ABBV": ("AbbVie", "艾伯维", "Healthcare", "医疗健康"),
    "MRK": ("Merck", "默克", "Healthcare", "医疗健康"),
    "LLY": ("Eli Lilly", "礼来", "Healthcare", "医疗健康"),
    "XOM": ("Exxon Mobil", "埃克森美孚", "Energy", "能源"),
    "CVX": ("Chevron", "雪佛龙", "Energy", "能源"),
    "COP": ("ConocoPhillips", "康菲石油", "Energy", "能源"),
    "PG": ("Procter & Gamble", "宝洁", "Consumer Staples", "必需消费"),
    "KO": ("Coca-Cola", "可口可乐", "Consumer Staples", "必需消费"),
    "PEP": ("PepsiCo", "百事", "Consumer Staples", "必需消费"),
    "WMT": ("Walmart", "沃尔玛", "Consumer Staples", "必需消费"),
    "HD": ("Home Depot", "家得宝", "Consumer Discretionary", "可选消费"),
    "DIS": ("Walt Disney", "迪士尼", "Communication Services", "通信服务"),
    "CRM": ("Salesforce", "赛富时", "Technology", "科技"),
    "ORCL": ("Oracle", "甲骨文", "Technology", "科技"),
    "CSCO": ("Cisco Systems", "思科", "Technology", "科技"),
    "QCOM": ("Qualcomm", "高通", "Technology", "科技"),
    "TXN": ("Texas Instruments", "德州仪器", "Technology", "科技"),
    "AVGO": ("Broadcom", "博通", "Technology", "科技"),
    "NOW": ("ServiceNow", "ServiceNow", "Technology", "科技"),
    "CAT": ("Caterpillar", "卡特彼勒", "Industrials", "工业"),
    "GE": ("GE Aerospace", "通用电气", "Industrials", "工业"),
    "MMM": ("3M", "3M", "Industrials", "工业"),
    "UPS": ("United Parcel Service", "联合包裹", "Industrials", "工业"),
    "RTX": ("RTX Corporation", "雷神", "Industrials", "工业"),
    "HON": ("Honeywell", "霍尼韦尔", "Industrials", "工业"),
    "LMT": ("Lockheed Martin", "洛克希德马丁", "Industrials", "工业"),
    "NEE": ("NextEra Energy", "NextEra能源", "Utilities", "公用事业"),
    "DUK": ("Duke Energy", "杜克能源", "Utilities", "公用事业"),
    "SO": ("Southern Company", "南方电力", "Utilities", "公用事业"),
    "AMT": ("American Tower", "美国电塔", "Real Estate", "房地产"),
    "PLD": ("Prologis", "安博", "Real Estate", "房地产"),
    "SPG": ("Simon Property Group", "西蒙地产", "Real Estate", "房地产"),
}


def _get_stock_name(ticker):
    """Return (name, name_cn) for a ticker, falling back to ticker itself."""
    meta = STOCK_META.get(ticker)
    if meta:
        return meta[0], meta[1]
    return ticker, ticker


def _get_stock_sector(ticker):
    """Return (sector, sector_cn) for a ticker."""
    meta = STOCK_META.get(ticker)
    if meta:
        return meta[2], meta[3]
    return "Other", "其他"


# ---------------------------------------------------------------------------
# Status management
# ---------------------------------------------------------------------------


def update_status(status):
    """Write status to JSON for dashboard to read."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = STATUS_FILE.with_suffix(".tmp")
    with open(tmp_file, "w") as f:
        json.dump(status, f, indent=2, default=str)
    tmp_file.replace(STATUS_FILE)


# ---------------------------------------------------------------------------
# 1. Evaluator -- train and measure a single configuration
# ---------------------------------------------------------------------------


def evaluate_model(model_config, dataset_config):
    """Train a model and return its performance metrics.

    Returns a dict with keys: ic, icir, rank_ic, rank_icir,
    pred_df, model, dataset, recorder.
    """
    model = init_instance_by_config(model_config)
    dataset = init_instance_by_config(dataset_config)

    experiment_name = f"improve_agent_{int(time.time())}"

    with R.start(experiment_name=experiment_name):
        R.log_params(
            **flatten_dict({"model": model_config, "dataset": dataset_config})
        )
        model.fit(dataset)
        R.save_objects(**{"params.pkl": model})

        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        sar = SigAnaRecord(recorder)
        sar.generate()

    # Extract metrics from signal analysis
    metrics = _extract_sig_metrics(recorder)
    pred_df = recorder.load_object("pred.pkl")

    return {
        "ic": metrics.get("IC", 0.0),
        "icir": metrics.get("ICIR", 0.0),
        "rank_ic": metrics.get("Rank IC", 0.0),
        "rank_icir": metrics.get("Rank ICIR", 0.0),
        "pred_df": pred_df,
        "model": model,
        "dataset": dataset,
        "recorder": recorder,
    }


def _extract_sig_metrics(recorder):
    """Safely load sig_analysis.pkl and return a plain dict."""
    try:
        sig_analysis = recorder.load_object("sig_analysis.pkl")
        if isinstance(sig_analysis, dict):
            return {
                k: float(v)
                for k, v in sig_analysis.items()
                if isinstance(v, (int, float, np.integer, np.floating))
            }
        if isinstance(sig_analysis, pd.Series):
            return {
                k: float(v)
                for k, v in sig_analysis.items()
                if isinstance(v, (int, float, np.integer, np.floating))
            }
    except Exception as exc:
        logger.warning("Could not load sig_analysis.pkl: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# 2. Critic Agent -- diagnose model weaknesses
# ---------------------------------------------------------------------------

# Thresholds for IC quality tiers
IC_VERY_LOW = 0.01
IC_LOW = 0.03
ICIR_UNSTABLE = 0.1
RANK_IC_LOW = 0.01


def critic_evaluate(metrics):
    """Analyze model weaknesses and suggest focus areas.

    Returns a dict with 'issues' (human-readable) and 'suggestions'
    (machine-readable strategy tags).
    """
    issues = []
    suggestions = []

    ic = abs(metrics["ic"])
    icir = abs(metrics["icir"])
    rank_ic = abs(metrics["rank_ic"])

    if ic < IC_VERY_LOW:
        issues.append(
            f"IC is very low ({metrics['ic']:.6f}). "
            "Model has weak predictive power."
        )
        suggestions.append("increase_complexity")
        suggestions.append("adjust_learning_rate")
    elif ic < IC_LOW:
        issues.append(
            f"IC is below average ({metrics['ic']:.6f}). "
            "Room for improvement."
        )
        suggestions.append("tune_regularization")

    if icir < ICIR_UNSTABLE:
        issues.append(
            f"ICIR is unstable ({metrics['icir']:.6f}). "
            "Predictions are inconsistent across time."
        )
        suggestions.append("increase_regularization")
        suggestions.append("reduce_overfitting")

    if rank_ic < RANK_IC_LOW:
        issues.append(
            f"Rank IC too low ({metrics['rank_ic']:.6f}). "
            "Cross-sectional ranking quality is poor."
        )
        suggestions.append("try_different_features")

    if not issues:
        issues.append(
            f"Model looks reasonable (IC={metrics['ic']:.6f}, "
            f"ICIR={metrics['icir']:.6f}). Fine-tuning may still help."
        )

    return {"issues": issues, "suggestions": list(set(suggestions))}


# ---------------------------------------------------------------------------
# 3. Improvement Proposer -- generate concrete configuration changes
# ---------------------------------------------------------------------------

# Bounds to prevent unreasonable hyperparameters
MIN_LEARNING_RATE = 0.005
MAX_LEARNING_RATE = 0.1
MIN_NUM_LEAVES = 50
MAX_NUM_LEAVES = 400
MIN_MAX_DEPTH = 4
MAX_MAX_DEPTH = 12
MIN_COLSAMPLE = 0.5
MAX_COLSAMPLE = 1.0
MIN_SUBSAMPLE = 0.5
MAX_SUBSAMPLE = 1.0


def _clamp(value, lo, hi):
    """Clamp a numeric value to [lo, hi]."""
    return max(lo, min(hi, value))


def propose_improvements(round_num, critique, current_config):
    """Generate concrete configuration changes for this round.

    Each round explores a different dimension of the hyperparameter space.
    Returns a list of proposal dicts with keys: name, changes,
    and optionally dataset_changes.
    """
    kwargs = current_config["model"]["kwargs"]

    strategies = [
        _strategy_learning_rate_and_depth,
        _strategy_regularization,
        _strategy_sampling,
        _strategy_leaves_and_depth,
        _strategy_combined_profiles,
        _strategy_fine_tune,
        _strategy_data_splits,
        _strategy_final_combination,
    ]

    idx = min(round_num, len(strategies) - 1)
    return strategies[idx](kwargs)


def _strategy_learning_rate_and_depth(kwargs):
    """Round 1: Explore learning rate and tree depth."""
    lr = kwargs["learning_rate"]
    depth = kwargs["max_depth"]
    return [
        {
            "name": "Lower learning rate",
            "changes": {
                "learning_rate": _clamp(lr * 0.5, MIN_LEARNING_RATE, MAX_LEARNING_RATE),
            },
        },
        {
            "name": "Higher learning rate",
            "changes": {
                "learning_rate": _clamp(lr * 2, MIN_LEARNING_RATE, MAX_LEARNING_RATE),
            },
        },
        {
            "name": "Deeper trees",
            "changes": {
                "max_depth": _clamp(depth + 2, MIN_MAX_DEPTH, MAX_MAX_DEPTH),
            },
        },
    ]


def _strategy_regularization(kwargs):
    """Round 2: Tune L1/L2 regularization strength."""
    l1 = kwargs["lambda_l1"]
    l2 = kwargs["lambda_l2"]
    return [
        {
            "name": "Stronger L1 regularization",
            "changes": {"lambda_l1": l1 * 2},
        },
        {
            "name": "Weaker L1 regularization",
            "changes": {"lambda_l1": l1 * 0.5},
        },
        {
            "name": "Stronger L2 regularization",
            "changes": {"lambda_l2": l2 * 2},
        },
    ]


def _strategy_sampling(kwargs):
    """Round 3: Tune column and row sampling."""
    col = kwargs["colsample_bytree"]
    row = kwargs["subsample"]
    return [
        {
            "name": "More column sampling",
            "changes": {
                "colsample_bytree": _clamp(col + 0.05, MIN_COLSAMPLE, MAX_COLSAMPLE),
            },
        },
        {
            "name": "Less column sampling",
            "changes": {
                "colsample_bytree": _clamp(col - 0.1, MIN_COLSAMPLE, MAX_COLSAMPLE),
            },
        },
        {
            "name": "More row sampling",
            "changes": {
                "subsample": _clamp(row + 0.05, MIN_SUBSAMPLE, MAX_SUBSAMPLE),
            },
        },
    ]


def _strategy_leaves_and_depth(kwargs):
    """Round 4: Jointly adjust num_leaves and max_depth."""
    leaves = kwargs["num_leaves"]
    return [
        {
            "name": "More leaves",
            "changes": {
                "num_leaves": _clamp(leaves + 50, MIN_NUM_LEAVES, MAX_NUM_LEAVES),
            },
        },
        {
            "name": "Fewer leaves",
            "changes": {
                "num_leaves": _clamp(leaves - 50, MIN_NUM_LEAVES, MAX_NUM_LEAVES),
            },
        },
        {
            "name": "Balanced depth + leaves",
            "changes": {"max_depth": 10, "num_leaves": 300},
        },
    ]


def _strategy_combined_profiles(kwargs):
    """Round 5: Two contrasting full-parameter profiles."""
    return [
        {
            "name": "Conservative ensemble",
            "changes": {
                "learning_rate": 0.02,
                "num_leaves": 150,
                "max_depth": 6,
                "lambda_l1": 300,
                "lambda_l2": 800,
            },
        },
        {
            "name": "Aggressive ensemble",
            "changes": {
                "learning_rate": 0.08,
                "num_leaves": 350,
                "max_depth": 10,
                "lambda_l1": 100,
                "lambda_l2": 300,
            },
        },
    ]


def _strategy_fine_tune(kwargs):
    """Round 6: Small perturbations around current best."""
    lr = kwargs["learning_rate"]
    leaves = kwargs["num_leaves"]
    return [
        {
            "name": "Fine-tune LR +10%",
            "changes": {
                "learning_rate": _clamp(lr * 1.1, MIN_LEARNING_RATE, MAX_LEARNING_RATE),
            },
        },
        {
            "name": "Fine-tune LR -10%",
            "changes": {
                "learning_rate": _clamp(lr * 0.9, MIN_LEARNING_RATE, MAX_LEARNING_RATE),
            },
        },
        {
            "name": "Fine-tune leaves +10%",
            "changes": {
                "num_leaves": _clamp(int(leaves * 1.1), MIN_NUM_LEAVES, MAX_NUM_LEAVES),
            },
        },
    ]


def _strategy_data_splits(kwargs):
    """Round 7: Alternative train/valid/test splits."""
    return [
        {
            "name": "Extended train period",
            "changes": {},
            "dataset_changes": {
                "segments": {
                    "train": ("2008-01-01", "2024-06-30"),
                    "valid": ("2024-07-01", "2025-09-30"),
                    "test": ("2025-10-01", "2026-03-06"),
                },
            },
        },
        {
            "name": "Recent focus training",
            "changes": {},
            "dataset_changes": {
                "segments": {
                    "train": ("2012-01-01", "2024-06-30"),
                    "valid": ("2024-07-01", "2025-06-30"),
                    "test": ("2025-07-01", "2026-03-06"),
                },
            },
        },
    ]


def _strategy_final_combination(kwargs):
    """Round 8: One final combined attempt with boosted regularization."""
    return [
        {
            "name": "Best-of-all combination",
            "changes": {
                "learning_rate": kwargs["learning_rate"],
                "num_leaves": kwargs["num_leaves"],
                "max_depth": kwargs["max_depth"],
                "lambda_l1": kwargs["lambda_l1"] * 1.5,
                "lambda_l2": kwargs["lambda_l2"] * 1.5,
                "colsample_bytree": _clamp(0.9, MIN_COLSAMPLE, MAX_COLSAMPLE),
                "subsample": _clamp(0.9, MIN_SUBSAMPLE, MAX_SUBSAMPLE),
            },
        },
    ]


# ---------------------------------------------------------------------------
# 4. Implementer -- apply proposed changes to a config
# ---------------------------------------------------------------------------


def apply_improvements(base_config, proposal):
    """Return a new config dict with proposal changes applied."""
    config = deepcopy(base_config)

    for key, value in proposal.get("changes", {}).items():
        config["model"]["kwargs"][key] = value

    if "dataset_changes" in proposal:
        for key, value in proposal["dataset_changes"].items():
            if key == "segments":
                config["dataset"]["kwargs"]["segments"] = value

    return config


# ---------------------------------------------------------------------------
# 5. Validator -- compare models with a composite score
# ---------------------------------------------------------------------------


def compute_composite_score(metrics):
    """Compute a single composite score for model comparison.

    Weights: IC 40%, ICIR 30%, Rank IC 20%, Rank ICIR 10%.
    Uses absolute values so both positive and negative correlations
    are treated as signal strength.
    """
    return (
        abs(metrics["ic"]) * IC_WEIGHT
        + abs(metrics["icir"]) * ICIR_WEIGHT
        + abs(metrics["rank_ic"]) * RANK_IC_WEIGHT
        + abs(metrics["rank_icir"]) * RANK_ICIR_WEIGHT
    )


# ---------------------------------------------------------------------------
# Prediction regeneration -- update predictions.json with best model
# ---------------------------------------------------------------------------


def regenerate_predictions(recorder, pred_df):
    """Rewrite predictions.json using the best model's output.

    Preserves the existing methodology section and static metadata,
    but updates metrics, top_stocks, single_day_top, sector_breakdown,
    and market_overview.
    """
    if not PREDICTIONS_FILE.exists():
        logger.warning("predictions.json not found; skipping regeneration")
        return

    with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # -- Update model metrics --
    sig_metrics = _extract_sig_metrics(recorder)
    data["model_info"]["metrics"] = {
        "ic": round(sig_metrics.get("IC", 0.0), 6),
        "icir": round(sig_metrics.get("ICIR", 0.0), 6),
        "rank_ic": round(sig_metrics.get("Rank IC", 0.0), 6),
        "rank_icir": round(sig_metrics.get("Rank ICIR", 0.0), 6),
    }

    # -- Recompute stock rankings from new predictions --
    all_dates = sorted(pred_df.index.get_level_values("datetime").unique())
    last_date = all_dates[-1]
    recent_dates = all_dates[-LOOKBACK_DAYS:]
    recent_preds = pred_df.loc[
        pred_df.index.get_level_values("datetime").isin(recent_dates)
    ]

    stock_scores = recent_preds.groupby(level="instrument")["score"].mean()
    stock_scores = stock_scores.sort_values(ascending=False)

    # Consistency: fraction of recent days where stock was in top quartile
    consistency = {}
    for stock in stock_scores.index:
        stock_data = recent_preds.xs(stock, level="instrument")["score"]
        days_in_top = 0
        for dt in recent_dates:
            if dt in stock_data.index:
                day_scores = recent_preds.loc[dt]["score"]
                threshold = day_scores.quantile(TOP_QUARTILE_THRESHOLD)
                if stock_data.loc[dt] >= threshold:
                    days_in_top += 1
        consistency[stock] = days_in_top / len(recent_dates)

    consistency_series = pd.Series(consistency)
    combined_score = (
        stock_scores.rank(pct=True) * SIGNAL_WEIGHT
        + consistency_series.reindex(stock_scores.index).fillna(0).rank(pct=True)
        * CONSISTENCY_WEIGHT
    )
    combined_score = combined_score.sort_values(ascending=False)

    # -- Build top_stocks list --
    new_top_stocks = []
    for rank, (ticker, score) in enumerate(
        combined_score.head(TOP_N_CONSENSUS).items(), 1
    ):
        name, name_cn = _get_stock_name(ticker)
        sector, sector_cn = _get_stock_sector(ticker)
        avg_signal = float(stock_scores.get(ticker, 0))
        cons = float(consistency.get(ticker, 0))
        new_top_stocks.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "name_cn": name_cn,
            "sector": sector,
            "sector_cn": sector_cn,
            "signal": round(avg_signal, 5),
            "consistency": round(cons, 2),
            "combined_score": round(float(score), 4),
            "trend": "up" if avg_signal > 0 else "down",
        })

    data["top_stocks"] = new_top_stocks

    # -- Build single-day top list --
    last_day_preds = pred_df.loc[last_date].sort_values("score", ascending=False)
    single_day_top = []
    for rank, (idx, row) in enumerate(last_day_preds.head(10).iterrows(), 1):
        ticker = (
            idx
            if isinstance(idx, str)
            else idx[1] if isinstance(idx, tuple) else str(idx)
        )
        name, name_cn = _get_stock_name(ticker)
        single_day_top.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "name_cn": name_cn,
            "signal": round(float(row["score"]), 5),
        })
    data["single_day_top"] = single_day_top

    # -- Sector breakdown --
    sector_map = {}
    for entry in new_top_stocks:
        sector = entry["sector"]
        sector_cn = entry["sector_cn"]
        if sector not in sector_map:
            sector_map[sector] = {
                "sector": sector,
                "sector_cn": sector_cn,
                "count": 0,
                "total_signal": 0.0,
            }
        sector_map[sector]["count"] += 1
        sector_map[sector]["total_signal"] += entry["signal"]

    sector_breakdown = []
    for sector_data in sector_map.values():
        avg_sig = sector_data["total_signal"] / max(sector_data["count"], 1)
        sector_breakdown.append({
            "sector": sector_data["sector"],
            "sector_cn": sector_data["sector_cn"],
            "count": sector_data["count"],
            "avg_signal": round(avg_sig, 5),
        })
    sector_breakdown.sort(key=lambda x: x["avg_signal"], reverse=True)
    data["sector_breakdown"] = sector_breakdown

    # -- Market overview --
    positive_count = int((stock_scores > 0).sum())
    negative_count = int((stock_scores <= 0).sum())
    data["market_overview"] = {
        "date": str(last_date.date()),
        "total_stocks": len(stock_scores),
        "positive_signal_count": positive_count,
        "negative_signal_count": negative_count,
        "avg_signal": round(float(stock_scores.mean()), 4),
        "top_sector": (
            sector_breakdown[0]["sector"] if sector_breakdown else "N/A"
        ),
        "prediction_window_days": LOOKBACK_DAYS,
    }

    data["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Atomic write to avoid dashboard reading partial JSON
    tmp_file = PREDICTIONS_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_file.replace(PREDICTIONS_FILE)

    logger.info("Updated predictions.json with improved model results")


# ---------------------------------------------------------------------------
# Main improvement loop
# ---------------------------------------------------------------------------


def _metric_keys(result):
    """Extract only the scalar metric keys from an evaluate_model result."""
    return {
        k: v
        for k, v in result.items()
        if k not in ("pred_df", "model", "dataset", "recorder")
    }


def main():
    """Run the iterative self-improvement loop."""
    logger.info("=" * 70)
    logger.info("SELF-IMPROVING PREDICTION AGENT STARTING")
    logger.info("=" * 70)

    qlib.init(provider_uri=PROVIDER_URI, region=REG_US)

    status = {
        "is_running": True,
        "current_round": 0,
        "total_rounds": MAX_ROUNDS,
        "best_ic": None,
        "best_icir": None,
        "best_composite": None,
        "history": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_run": datetime.now(timezone.utc).isoformat(),
    }
    update_status(status)

    # Current best state
    best_config = {
        "model": deepcopy(BASE_MODEL_CONFIG),
        "dataset": deepcopy(BASE_DATASET_CONFIG),
    }
    best_metrics = None
    best_composite = -1.0
    best_recorder = None
    best_pred_df = None

    # ---- Round 0: Evaluate baseline ----
    logger.info("")
    logger.info("-- ROUND 0: Evaluating baseline model --")

    try:
        baseline_results = evaluate_model(BASE_MODEL_CONFIG, BASE_DATASET_CONFIG)
        best_metrics = _metric_keys(baseline_results)
        best_composite = compute_composite_score(best_metrics)
        best_recorder = baseline_results["recorder"]
        best_pred_df = baseline_results["pred_df"]

        logger.info(
            "  Baseline IC=%.6f  ICIR=%.6f  Rank IC=%.6f  Composite=%.6f",
            best_metrics["ic"],
            best_metrics["icir"],
            best_metrics["rank_ic"],
            best_composite,
        )

        status["best_ic"] = best_metrics["ic"]
        status["best_icir"] = best_metrics["icir"]
        status["best_composite"] = best_composite
        status["history"].append({
            "round": 0,
            "name": "Baseline",
            "ic": best_metrics["ic"],
            "icir": best_metrics["icir"],
            "rank_ic": best_metrics["rank_ic"],
            "rank_icir": best_metrics["rank_icir"],
            "composite": best_composite,
            "is_best": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        update_status(status)

    except Exception as exc:
        logger.error("Baseline evaluation failed: %s", exc, exc_info=True)
        status["is_running"] = False
        status["error"] = str(exc)
        update_status(status)
        return

    # ---- Improvement rounds ----
    rounds_without_improvement = 0

    for round_num in range(1, MAX_ROUNDS + 1):
        logger.info("")
        logger.info("=" * 70)
        logger.info(
            "-- ROUND %d/%d: Critic evaluating... --", round_num, MAX_ROUNDS
        )
        logger.info("=" * 70)

        status["current_round"] = round_num
        update_status(status)

        # Critic
        critique = critic_evaluate(best_metrics)
        for issue in critique["issues"]:
            logger.info("  CRITIC: %s", issue)

        # Proposer
        proposals = propose_improvements(round_num - 1, critique, best_config)
        logger.info("  PROPOSER: %d improvement proposal(s)", len(proposals))

        found_improvement_this_round = False

        for proposal in proposals:
            name = proposal["name"]
            logger.info("")
            logger.info("  Testing: %s", name)

            test_config = apply_improvements(best_config, proposal)

            try:
                results = evaluate_model(
                    test_config["model"], test_config["dataset"]
                )
                test_metrics = _metric_keys(results)
                composite = compute_composite_score(test_metrics)

                logger.info(
                    "    IC=%.6f  ICIR=%.6f  Composite=%.6f  (best=%.6f)",
                    test_metrics["ic"],
                    test_metrics["icir"],
                    composite,
                    best_composite,
                )

                is_improvement = composite > best_composite + CONVERGENCE_THRESHOLD

                status["history"].append({
                    "round": round_num,
                    "name": name,
                    "ic": test_metrics["ic"],
                    "icir": test_metrics["icir"],
                    "rank_ic": test_metrics["rank_ic"],
                    "rank_icir": test_metrics["rank_icir"],
                    "composite": composite,
                    "is_best": is_improvement,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                if is_improvement:
                    delta = composite - best_composite
                    logger.info(
                        "    >>> IMPROVEMENT FOUND! +%.6f", delta
                    )
                    best_metrics = test_metrics
                    best_composite = composite
                    best_config = test_config
                    best_recorder = results["recorder"]
                    best_pred_df = results["pred_df"]
                    found_improvement_this_round = True
                    rounds_without_improvement = 0

                    status["best_ic"] = best_metrics["ic"]
                    status["best_icir"] = best_metrics["icir"]
                    status["best_composite"] = best_composite

            except Exception as exc:
                logger.warning("    Failed: %s", exc)
                status["history"].append({
                    "round": round_num,
                    "name": name,
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            update_status(status)

        if not found_improvement_this_round:
            rounds_without_improvement += 1
            logger.info(
                "  No improvement this round (%d consecutive)",
                rounds_without_improvement,
            )
            if rounds_without_improvement >= MAX_STALE_ROUNDS:
                logger.info(
                    "  STOPPING: %d consecutive rounds without improvement",
                    MAX_STALE_ROUNDS,
                )
                break

    # ---- Final: update predictions with best model ----
    logger.info("")
    logger.info("=" * 70)
    logger.info("IMPROVEMENT COMPLETE")
    logger.info("  Best composite score: %.6f", best_composite)
    logger.info("  Best IC:              %.6f", best_metrics["ic"])
    logger.info("  Best ICIR:            %.6f", best_metrics["icir"])
    logger.info("  Best Rank IC:         %.6f", best_metrics["rank_ic"])
    logger.info("  Best Rank ICIR:       %.6f", best_metrics["rank_icir"])
    logger.info("  Rounds evaluated:     %d", len(status["history"]))
    logger.info("=" * 70)

    if best_recorder is not None and best_pred_df is not None:
        regenerate_predictions(best_recorder, best_pred_df)

    status["is_running"] = False
    status["completed_at"] = datetime.now(timezone.utc).isoformat()
    update_status(status)

    logger.info("Agent finished. Dashboard will auto-refresh with new predictions.")


if __name__ == "__main__":
    main()
