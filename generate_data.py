"""
Generate stock predictions using the qlib LightGBM + Alpha158 model.

Trains (or re-trains) the model on SP500 data, generates predictions for
the test period, computes 20-day average signals and consistency scores,
and exports everything to data/predictions.json.

Usage:
    /Users/Ed/qlib-env/bin/python generate_data.py
"""
import multiprocessing
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROVIDER_URI = "~/.qlib/qlib_data/us_data_fresh"
MARKET = "sp500"
BENCHMARK = "^gspc"

TRAIN_START = "2008-01-01"
TRAIN_END = "2023-12-31"
VALID_START = "2024-01-01"
VALID_END = "2025-06-30"
TEST_START = "2025-07-01"
TEST_END = "2026-03-06"

LOOKBACK_DAYS = 20
TOP_QUARTILE_THRESHOLD = 0.75
SIGNAL_WEIGHT = 0.7
CONSISTENCY_WEIGHT = 0.3
TOP_N_CONSENSUS = 30
TOP_N_SINGLE_DAY = 10

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "predictions.json"

# ---------------------------------------------------------------------------
# Stock metadata: name, Chinese translation, sector classification
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
# Core pipeline
# ---------------------------------------------------------------------------


def main():
    """Train the model, generate predictions, and export to JSON."""
    warnings.filterwarnings("ignore")
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

    import qlib
    import pandas as pd
    import numpy as np
    from qlib.constant import REG_US
    from qlib.utils import init_instance_by_config, flatten_dict
    from qlib.workflow import R
    from qlib.workflow.record_temp import SignalRecord, SigAnaRecord

    print("=" * 70)
    print("INITIALIZING QLIB WITH FRESH US MARKET DATA")
    print("=" * 70)
    qlib.init(provider_uri=PROVIDER_URI, region=REG_US)

    model_config = {
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

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": "Alpha158",
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "start_time": TRAIN_START,
                    "end_time": TEST_END,
                    "fit_start_time": TRAIN_START,
                    "fit_end_time": TRAIN_END,
                    "instruments": MARKET,
                },
            },
            "segments": {
                "train": (TRAIN_START, TRAIN_END),
                "valid": (VALID_START, VALID_END),
                "test": (TEST_START, TEST_END),
            },
        },
    }

    task_config = {
        "model": model_config,
        "dataset": dataset_config,
    }

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------
    print("\nTraining LightGBM + Alpha158 model ...")
    print(f"  Train:  {TRAIN_START} to {TRAIN_END}")
    print(f"  Valid:  {VALID_START} to {VALID_END}")
    print(f"  Test:   {TEST_START} to {TEST_END}")

    model = init_instance_by_config(task_config["model"])
    dataset = init_instance_by_config(task_config["dataset"])

    with R.start(experiment_name="dashboard_predictions"):
        R.log_params(**flatten_dict(task_config))
        model.fit(dataset)
        R.save_objects(**{"params.pkl": model})

        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        sar = SigAnaRecord(recorder)
        sar.generate()

    # ------------------------------------------------------------------
    # Load predictions
    # ------------------------------------------------------------------
    pred_df = recorder.load_object("pred.pkl")
    print(f"\nPrediction shape: {pred_df.shape}")

    all_dates = sorted(pred_df.index.get_level_values("datetime").unique())
    last_date = all_dates[-1]
    recent_dates = all_dates[-LOOKBACK_DAYS:]

    recent_preds = pred_df.loc[
        pred_df.index.get_level_values("datetime").isin(recent_dates)
    ]

    # ------------------------------------------------------------------
    # Compute average signals and consistency
    # ------------------------------------------------------------------
    print("Computing 20-day average signals and consistency scores ...")

    stock_scores = recent_preds.groupby(level="instrument")["score"].mean()
    stock_scores = stock_scores.sort_values(ascending=False)

    total_tickers = len(stock_scores)

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

    combined = (
        stock_scores.rank(pct=True) * SIGNAL_WEIGHT
        + consistency_series.reindex(stock_scores.index).fillna(0).rank(pct=True)
        * CONSISTENCY_WEIGHT
    )
    combined = combined.sort_values(ascending=False)

    # ------------------------------------------------------------------
    # Single-day top
    # ------------------------------------------------------------------
    last_day_preds = pred_df.loc[last_date].sort_values("score", ascending=False)

    # ------------------------------------------------------------------
    # Signal analysis metrics
    # ------------------------------------------------------------------
    metrics = {}
    try:
        sig_analysis = recorder.load_object("sig_analysis.pkl")
        if isinstance(sig_analysis, dict):
            for key, val in sig_analysis.items():
                if isinstance(val, (int, float, np.integer, np.floating)):
                    metrics[key] = round(float(val), 6)
        elif isinstance(sig_analysis, pd.Series):
            for key, val in sig_analysis.items():
                if isinstance(val, (int, float, np.integer, np.floating)):
                    metrics[key] = round(float(val), 6)
    except Exception:
        metrics = {"ic": 0.0, "icir": 0.0, "rank_ic": 0.0, "rank_icir": 0.0}

    # ------------------------------------------------------------------
    # Build top stocks list (consensus)
    # ------------------------------------------------------------------
    top_consensus = []
    for rank, (ticker, score) in enumerate(
        combined.head(TOP_N_CONSENSUS).items(), 1
    ):
        avg_signal = float(stock_scores.get(ticker, 0))
        cons = float(consistency.get(ticker, 0))
        name, name_cn = _get_stock_name(ticker)
        sector, sector_cn = _get_stock_sector(ticker)
        is_positive = avg_signal > 0
        top_consensus.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "name_cn": name_cn,
            "sector": sector,
            "sector_cn": sector_cn,
            "signal": round(avg_signal, 5),
            "consistency": round(cons, 2),
            "combined_score": round(float(score), 4),
            "trend": "up" if is_positive else "down",
        })

    # ------------------------------------------------------------------
    # Build single-day top list
    # ------------------------------------------------------------------
    single_day_top = []
    for rank, (idx, row) in enumerate(
        last_day_preds.head(TOP_N_SINGLE_DAY).iterrows(), 1
    ):
        ticker = idx if isinstance(idx, str) else idx[1] if isinstance(idx, tuple) else str(idx)
        name, name_cn = _get_stock_name(ticker)
        single_day_top.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "name_cn": name_cn,
            "signal": round(float(row["score"]), 5),
        })

    # ------------------------------------------------------------------
    # Sector breakdown from consensus top stocks
    # ------------------------------------------------------------------
    sector_map = {}
    for entry in top_consensus:
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
        avg_sig = sector_data["total_signal"] / sector_data["count"]
        sector_breakdown.append({
            "sector": sector_data["sector"],
            "sector_cn": sector_data["sector_cn"],
            "count": sector_data["count"],
            "avg_signal": round(avg_sig, 5),
        })
    sector_breakdown.sort(key=lambda x: x["avg_signal"], reverse=True)

    # ------------------------------------------------------------------
    # Market overview
    # ------------------------------------------------------------------
    positive_count = int((stock_scores > 0).sum())
    negative_count = int((stock_scores <= 0).sum())
    avg_signal = round(float(stock_scores.mean()), 4)

    top_sector = sector_breakdown[0]["sector"] if sector_breakdown else "N/A"

    # ------------------------------------------------------------------
    # Methodology (static content)
    # ------------------------------------------------------------------
    methodology = {
        "steps": [
            {
                "title": "Data Collection",
                "title_cn": "数据采集",
                "desc": (
                    "18 years of daily OHLCV data for "
                    f"{total_tickers} SP500 stocks from Yahoo Finance "
                    f"({TRAIN_START[:4]}-{TEST_END[:4]})"
                ),
                "desc_cn": (
                    f"从Yahoo Finance获取{total_tickers}只标普500成分股18年的"
                    f"日线OHLCV数据({TRAIN_START[:4]}-{TEST_END[:4]})"
                ),
            },
            {
                "title": "Feature Engineering",
                "title_cn": "特征工程",
                "desc": (
                    "Alpha158: 158 technical alpha factors including "
                    "momentum, volatility, volume patterns, and price ratios"
                ),
                "desc_cn": (
                    "Alpha158: 158个技术Alpha因子，包括动量、波动率、"
                    "成交量模式和价格比率"
                ),
            },
            {
                "title": "Model Training",
                "title_cn": "模型训练",
                "desc": (
                    "LightGBM gradient boosting with optimized "
                    "hyperparameters, trained on "
                    f"{int(TRAIN_END[:4]) - int(TRAIN_START[:4])} years of data"
                ),
                "desc_cn": (
                    "使用优化超参数的LightGBM梯度提升模型，基于"
                    f"{int(TRAIN_END[:4]) - int(TRAIN_START[:4])}年数据训练"
                ),
            },
            {
                "title": "Signal Generation",
                "title_cn": "信号生成",
                "desc": (
                    "Model predicts excess returns for each stock. "
                    "Higher signal = stronger buy recommendation"
                ),
                "desc_cn": (
                    "模型预测每只股票的超额收益。信号越高 = 买入推荐越强"
                ),
            },
            {
                "title": "Ranking & Filtering",
                "title_cn": "排名与筛选",
                "desc": (
                    f"Combined score: {int(SIGNAL_WEIGHT * 100)}% signal "
                    f"strength + {int(CONSISTENCY_WEIGHT * 100)}% consistency "
                    f"in top quartile over {LOOKBACK_DAYS} trading days"
                ),
                "desc_cn": (
                    f"综合评分: {int(SIGNAL_WEIGHT * 100)}%信号强度 + "
                    f"{int(CONSISTENCY_WEIGHT * 100)}%在{LOOKBACK_DAYS}个"
                    "交易日内进入前25%的一致性"
                ),
            },
        ],
        "quant_fund_approach": {
            "title": "How Quant Funds Build Prediction Systems",
            "title_cn": "量化基金如何构建预测系统",
            "sections": [
                {
                    "heading": "Data Infrastructure",
                    "heading_cn": "数据基础设施",
                    "content": (
                        "Top quant funds (Renaissance Technologies, Two Sigma, "
                        "DE Shaw, Citadel) invest hundreds of millions in data "
                        "infrastructure. They collect alternative data: satellite "
                        "imagery, credit card transactions, social media sentiment, "
                        "weather patterns, shipping data, and patent filings."
                    ),
                    "content_cn": (
                        "顶级量化基金(文艺复兴科技、Two Sigma、DE Shaw、Citadel)"
                        "在数据基础设施上投入数亿美元。他们收集另类数据：卫星图像、"
                        "信用卡交易、社交媒体情绪、天气模式、航运数据和专利申请。"
                    ),
                },
                {
                    "heading": "Factor Models",
                    "heading_cn": "因子模型",
                    "content": (
                        "Funds build multi-factor models combining: value factors "
                        "(P/E, P/B), momentum factors (price trends), quality "
                        "factors (ROE, debt ratios), sentiment factors (news, "
                        "social), and statistical arbitrage signals."
                    ),
                    "content_cn": (
                        "基金构建多因子模型，结合：价值因子(市盈率、市净率)、"
                        "动量因子(价格趋势)、质量因子(ROE、负债率)、"
                        "情绪因子(新闻、社交媒体)和统计套利信号。"
                    ),
                },
                {
                    "heading": "Machine Learning Pipeline",
                    "heading_cn": "机器学习流程",
                    "content": (
                        "Modern quant funds use ensemble methods (gradient boosting, "
                        "random forests), deep learning (LSTM, Transformers), and "
                        "reinforcement learning for portfolio optimization. Models "
                        "are retrained daily with walk-forward validation."
                    ),
                    "content_cn": (
                        "现代量化基金使用集成方法(梯度提升、随机森林)、"
                        "深度学习(LSTM、Transformer)和强化学习进行投资组合优化。"
                        "模型每日使用滚动验证重新训练。"
                    ),
                },
                {
                    "heading": "Risk Management",
                    "heading_cn": "风险管理",
                    "content": (
                        "Position sizing uses Kelly criterion or risk parity. "
                        "Funds maintain sector neutrality, control for market beta, "
                        "and limit drawdowns through dynamic hedging and stop-loss "
                        "mechanisms."
                    ),
                    "content_cn": (
                        "仓位管理使用凯利准则或风险平价。基金维持行业中性、"
                        "控制市场Beta，并通过动态对冲和止损机制限制回撤。"
                    ),
                },
                {
                    "heading": "Execution",
                    "heading_cn": "执行",
                    "content": (
                        "Smart order routing, dark pools, and algorithmic execution "
                        "minimize market impact. Funds use co-located servers for "
                        "microsecond-level execution speed."
                    ),
                    "content_cn": (
                        "智能订单路由、暗池和算法执行最大限度减少市场影响。"
                        "基金使用机房托管服务器实现微秒级执行速度。"
                    ),
                },
            ],
        },
    }

    # ------------------------------------------------------------------
    # Assemble final payload
    # ------------------------------------------------------------------
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_info": {
            "name": "LightGBM + Alpha158",
            "description": (
                "Gradient boosting model with 158 technical alpha factors"
            ),
            "train_period": [TRAIN_START, TRAIN_END],
            "valid_period": [VALID_START, VALID_END],
            "test_period": [TEST_START, TEST_END],
            "last_prediction_date": str(last_date.date()),
            "total_tickers_analyzed": total_tickers,
            "data_source": "Yahoo Finance (full history)",
            "metrics": metrics,
        },
        "market_overview": {
            "date": str(last_date.date()),
            "total_stocks": total_tickers,
            "positive_signal_count": positive_count,
            "negative_signal_count": negative_count,
            "avg_signal": avg_signal,
            "top_sector": top_sector,
            "prediction_window_days": LOOKBACK_DAYS,
        },
        "top_stocks": top_consensus,
        "single_day_top": single_day_top,
        "sector_breakdown": sector_breakdown,
        "methodology": methodology,
    }

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f"\nPredictions exported to {OUTPUT_FILE}")
    print(f"  Total tickers analyzed: {total_tickers}")
    print(f"  Consensus top {TOP_N_CONSENSUS} stocks saved")
    print(f"  Single-day top {TOP_N_SINGLE_DAY} stocks saved")
    print(f"  Sector breakdown: {len(sector_breakdown)} sectors")
    print("Done.")


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    main()
