/**
 * Internationalization module for the Quant Stock Predictor dashboard.
 * Supports English (en), Traditional Chinese (tc), and Simplified Chinese (sc).
 * Stores language preference in localStorage.
 */

const STORAGE_KEY = 'qlib-dashboard-lang';
const DEFAULT_LANG = 'en';
const SUPPORTED_LANGS = ['en', 'tc', 'sc'];

let currentLang = DEFAULT_LANG;

const translations = {
  en: {
    /* --- Header --- */
    'app.title': 'Quant Stock Predictor',
    'app.subtitle': 'AI-Powered Stock Opportunity Scanner',
    'last.updated': 'Last Updated',

    /* --- Overview --- */
    'market.overview': 'Market Overview',
    'stocks.analyzed': 'Stocks Analyzed',
    'positive.signals': 'Positive Signals',
    'negative.signals': 'Negative Signals',
    'avg.signal': 'Average Signal',
    'top.sector': 'Top Sector',
    'signal.ratio': 'positive / negative',

    /* --- Stock Recommendations --- */
    'top.recommendations': 'Top Stock Recommendations',
    'view.consensus': '20-Day Consensus',
    'view.singleday': 'Latest Single-Day',
    'signal.strength': 'Signal Strength',
    'consistency': 'Consistency',
    'combined.score': 'Combined Score',
    'sector': 'Sector',
    'rank': 'Rank',
    'show.more': 'Show More',
    'show.less': 'Show Less',
    'trend.up': 'Upward',
    'trend.down': 'Downward',

    /* --- Stock Analysis / Charts --- */
    'stock.analysis': 'Stock Analysis',
    'select.stock': 'Select a stock...',

    /* --- Growth Predictions --- */
    'growth.predictions': 'Growth Predictions',
    'predicted.growth': 'Predicted Growth',
    'probability': 'Probability',
    'confidence': 'Confidence',
    'high.probability': 'High Probability',
    'medium.probability': 'Medium Probability',
    'low.probability': 'Low Probability',

    /* --- Economic & Market Signals --- */
    'economic.signals': 'Economic & Market Signals',
    'financial.news': 'Financial & Political News',
    'gdp.growth': 'GDP Growth',
    'unemployment': 'Unemployment',
    'inflation.cpi': 'Inflation (CPI)',
    'interest.rate': 'Interest Rate',
    'vix.index': 'VIX Index',
    'consumer.confidence': 'Consumer Confidence',
    'trade.balance': 'Trade Balance',
    'pmi': 'Manufacturing PMI',

    /* --- News Sentiment --- */
    'news.positive': 'Positive',
    'news.negative': 'Negative',
    'news.neutral': 'Neutral',
    'news.bullish': 'Bullish',
    'news.bearish': 'Bearish',

    /* --- Time Periods --- */
    'time.1m': '1M',
    'time.3m': '3M',
    'time.6m': '6M',
    'time.1y': '1Y',
    'time.5y': '5Y',

    /* --- Indicators --- */
    'indicator.sma': 'Simple Moving Average',
    'indicator.ema': 'Exponential Moving Average',
    'indicator.bollinger': 'Bollinger Bands',

    /* --- Model Status --- */
    'model.improving': 'Model Improving',
    'improvement.round': 'Improvement Round',

    /* --- Sector Breakdown --- */
    'sector.breakdown': 'Sector Breakdown',
    'sector.stocks': 'stocks',
    'sector.avg.signal': 'Avg Signal',

    /* --- Methodology --- */
    'methodology': 'Methodology',
    'methodology.steps': 'How the Model Works',
    'methodology.quant': 'How Quant Funds Build Prediction Systems',

    /* --- Methodology Steps --- */
    'step.1.title': 'Data Collection',
    'step.1.desc': '18 years of daily OHLCV data for 458 SP500 stocks from Yahoo Finance (2008-2026)',
    'step.2.title': 'Feature Engineering',
    'step.2.desc': 'Alpha158: 158 technical alpha factors including momentum, volatility, volume patterns, and price ratios',
    'step.3.title': 'Model Training',
    'step.3.desc': 'LightGBM gradient boosting with optimized hyperparameters, trained on 16 years of data',
    'step.4.title': 'Signal Generation',
    'step.4.desc': 'Model predicts excess returns for each stock. Higher signal = stronger buy recommendation',
    'step.5.title': 'Ranking & Filtering',
    'step.5.desc': 'Combined score: 70% signal strength + 30% consistency in top quartile over 20 trading days',

    /* --- Quant Fund Approach --- */
    'quant.data.heading': 'Data Infrastructure',
    'quant.data.content': 'Top quant funds (Renaissance Technologies, Two Sigma, DE Shaw, Citadel) invest hundreds of millions in data infrastructure. They collect alternative data: satellite imagery, credit card transactions, social media sentiment, weather patterns, shipping data, and patent filings.',
    'quant.factor.heading': 'Factor Models',
    'quant.factor.content': 'Funds build multi-factor models combining: value factors (P/E, P/B), momentum factors (price trends), quality factors (ROE, debt ratios), sentiment factors (news, social), and statistical arbitrage signals.',
    'quant.ml.heading': 'Machine Learning Pipeline',
    'quant.ml.content': 'Modern quant funds use ensemble methods (gradient boosting, random forests), deep learning (LSTM, Transformers), and reinforcement learning for portfolio optimization. Models are retrained daily with walk-forward validation.',
    'quant.risk.heading': 'Risk Management',
    'quant.risk.content': 'Position sizing uses Kelly criterion or risk parity. Funds maintain sector neutrality, control for market beta, and limit drawdowns through dynamic hedging and stop-loss mechanisms.',
    'quant.exec.heading': 'Execution',
    'quant.exec.content': 'Smart order routing, dark pools, and algorithmic execution minimize market impact. Funds use co-located servers for microsecond-level execution speed.',

    /* --- Model Performance --- */
    'model.performance': 'Model Performance',
    'metric.ic': 'IC',
    'metric.icir': 'ICIR',
    'metric.rankic': 'Rank IC',
    'metric.rankicir': 'Rank ICIR',
    'period.train': 'Training Period',
    'period.valid': 'Validation Period',
    'period.test': 'Test Period',

    /* --- Footer --- */
    'disclaimer': 'Disclaimer',
    'disclaimer.text': 'This is not financial advice. Predictions are generated by a machine learning model for educational and research purposes only. Past performance does not guarantee future results. Always do your own research and consult a qualified financial advisor before making investment decisions.',
    'footer.powered': 'Powered by Microsoft Qlib + LightGBM',
    'refresh.predictions': 'Refresh Predictions',
    'auto.refresh': 'Auto-refresh',

    /* --- Sectors --- */
    'sector.Technology': 'Technology',
    'sector.Financial Services': 'Financial Services',
    'sector.Consumer Discretionary': 'Consumer Discretionary',
    'sector.Airlines': 'Airlines',
    'sector.Materials': 'Materials',
    'sector.Industrials': 'Industrials',
    'sector.Communication Services': 'Communication Services',

    /* --- Stock Detail Modal --- */
    'company.overview': 'Company Overview',
    '12m.prediction': '6-Month Price Prediction',
    'historical.performance': 'Historical Performance',
    'signal.analysis': 'Signal Analysis',
    'news.impact': 'Recent News & Impact',
    'future.environment': 'Future Environment Analysis',
    'current.price': 'Current Price',
    '12m.target': '12-Month Target',
    'predicted.price': 'Predicted Price',
    'upper.bound': 'Upper Bound',
    'lower.bound': 'Lower Bound',
    'market.cap': 'Market Cap',
    'pe.ratio': 'P/E Ratio',
    'dividend.yield': 'Dividend Yield',
    '52w.high': '52-Week High',
    '52w.low': '52-Week Low',
    'click.for.details': 'Click for details',

    /* --- Modal Updates --- */
    '6m.prediction': '6-Month Price Prediction',
    '6m.target': '6-Month Target',
    'refresh.prediction': 'Refresh Prediction',
    'sharpe.ratio': 'Sharpe Ratio',
    'annual.volatility': 'Annual Volatility',
    'max.drawdown': 'Max Drawdown Est.',
    'risk.reward': 'Risk/Reward',
    'day.change': 'Day Change',
    'volume': 'Volume',
    'forward.pe': 'Forward P/E',
    'beta': 'Beta',
    'rsi.14': 'RSI (14)',
    'revenue.growth': 'Revenue Growth',
    'earnings.growth': 'Earnings Growth',
    'profit.margin': 'Profit Margin',
    'debt.equity': 'Debt/Equity',

    /* --- Model Evolution --- */
    'model.evolution': 'Model Evolution & Testing',
    'total.rounds': 'Total Rounds',
    'starting.accuracy': 'Starting Accuracy',
    'final.accuracy': 'Final Accuracy',
    'target': 'Target',
    'ic.improvement': 'IC Improvement',
    'best.config': 'Best Config',
    'directional.accuracy': 'Directional Accuracy',
    'round': 'Round',
    'accuracy': 'Accuracy',
    'notes.label': 'Notes',

    /* --- Short-Term Trading --- */
    'shortterm.trading': 'Short-Term Day Trading',
    'recommendation': 'Recommendation',
    'support': 'Support',
    'resistance': 'Resistance',
    'options.scanner': 'Options Trading Scanner',
    'realtime.chart': 'Real-Time Candle Chart',

    /* --- Tabs --- */
    'tab.overview': 'Overview',
    'tab.ai': 'AI Analysis',
    'tab.market': 'Market Data',
    'tab.model': 'Model',
    'tab.study': 'Study',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI (Claude)',
    'ai.method.factors': '12-Factor Analysis',
    'ai.method.model1': 'Model 1: Quant Engine',
    'ai.method.model2': 'Model 2: Sentiment',
    'ai.method.label': 'Analysis Method',
    'ai.model.comparison': 'Model Comparison',
    'ai.claude.desc': 'Venture fund-grade analysis using Claude Opus 4.6. Analyzes fundamentals, technicals, macro environment, insider activity, and institutional holdings. Returns rating, price targets, catalysts, risks, and entry/exit strategies.',
    'ai.factors.desc': '12-category multi-factor analysis with dynamic regime weighting. Covers momentum, value, quality, growth, volatility, sentiment, macro, economic, industry, risk-adjusted, historical analogy, and ML adaptive factors.',
    'ai.model1.desc': 'LightGBM + Alpha158 quantitative model trained on 18 years of S&P 500 data. Uses 158 technical alpha factors to generate 20-day consensus signals. Best for medium-term trend detection.',
    'ai.model2.desc': '5-step anomaly detection pipeline: scan volume/ATR spikes, research news sentiment, predict directional edge, size positions with Kelly criterion, track outcomes. Best for short-term catalysts.',
    'ai.model1.type': 'Quantitative ML',
    'ai.model2.type': 'Behavioral/Anomaly',
    'ai.claude.type': 'Natural Language AI',
    'ai.factors.type': 'Multi-Factor Model',
    'ai.model1.timeframe': '20-day forward',
    'ai.model2.timeframe': '5-20 day catalysts',
    'ai.claude.timeframe': '6-month strategic',
    'ai.factors.timeframe': '1 week to 24 months',
    'ai.model1.bestfor': 'Medium-term trends, sector rotation',
    'ai.model2.bestfor': 'Short-term momentum, event-driven',
    'ai.claude.bestfor': 'Strategic positioning, deep analysis',
    'ai.factors.bestfor': 'Regime-aware multi-horizon decisions',
    'model1.no.data': 'No Model 1 data available for this ticker. The stock may not be in the current S&P 500 prediction set.',
    'model2.no.data': 'No Model 2 signals for this ticker. Run a scan or the stock may not have triggered any anomalies.',
    'model2.run.scan': 'Run Scan',
    'analysis.type': 'Type',
    'analysis.timeframe': 'Timeframe',
    'analysis.bestfor': 'Best For',

    /* --- Misc --- */
    'loading': 'Loading...',
    'error.fetch': 'Failed to load predictions. Please try again.',
    'no.data': 'No data available.',
  },

  tc: {
    /* --- Header --- */
    'app.title': '量化選股系統',
    'app.subtitle': 'AI驅動的股票機會掃描器',
    'last.updated': '最後更新',

    /* --- Overview --- */
    'market.overview': '市場概覽',
    'stocks.analyzed': '分析股票數',
    'positive.signals': '正向信號',
    'negative.signals': '負向信號',
    'avg.signal': '平均信號',
    'top.sector': '最強板塊',
    'signal.ratio': '正向 / 負向',

    /* --- Stock Recommendations --- */
    'top.recommendations': '推薦買入股票',
    'view.consensus': '20日共識',
    'view.singleday': '最新單日',
    'signal.strength': '信號強度',
    'consistency': '一致性',
    'combined.score': '綜合評分',
    'sector': '板塊',
    'rank': '排名',
    'show.more': '顯示更多',
    'show.less': '收起',
    'trend.up': '上升',
    'trend.down': '下降',

    /* --- Stock Analysis / Charts --- */
    'stock.analysis': '股票分析',
    'select.stock': '選擇股票',

    /* --- Growth Predictions --- */
    'growth.predictions': '增長預測',
    'predicted.growth': '預測增長',
    'probability': '概率',
    'confidence': '置信度',
    'high.probability': '高概率',
    'medium.probability': '中等概率',
    'low.probability': '低概率',

    /* --- Economic & Market Signals --- */
    'economic.signals': '經濟與市場信號',
    'financial.news': '財經與政治新聞',
    'gdp.growth': 'GDP增長率',
    'unemployment': '失業率',
    'inflation.cpi': '通脹(CPI)',
    'interest.rate': '利率',
    'vix.index': 'VIX恐慌指數',
    'consumer.confidence': '消費者信心',
    'trade.balance': '貿易差額',
    'pmi': '製造業PMI',

    /* --- News Sentiment --- */
    'news.positive': '利好',
    'news.negative': '利空',
    'news.neutral': '中性',
    'news.bullish': '看漲',
    'news.bearish': '看跌',

    /* --- Time Periods --- */
    'time.1m': '1月',
    'time.3m': '3月',
    'time.6m': '6月',
    'time.1y': '1年',
    'time.5y': '5年',

    /* --- Indicators --- */
    'indicator.sma': '簡單移動平均',
    'indicator.ema': '指數移動平均',
    'indicator.bollinger': '布林帶',

    /* --- Model Status --- */
    'model.improving': '模型優化中',
    'improvement.round': '優化輪次',

    /* --- Sector Breakdown --- */
    'sector.breakdown': '板塊分析',
    'sector.stocks': '隻股票',
    'sector.avg.signal': '平均信號',

    /* --- Methodology --- */
    'methodology': '方法論',
    'methodology.steps': '模型工作原理',
    'methodology.quant': '量化基金如何構建預測系統',

    /* --- Methodology Steps --- */
    'step.1.title': '數據採集',
    'step.1.desc': '從Yahoo Finance獲取458隻標普500成分股18年的日線OHLCV數據(2008-2026)',
    'step.2.title': '特徵工程',
    'step.2.desc': 'Alpha158: 158個技術Alpha因子，包括動量、波動率、成交量模式和價格比率',
    'step.3.title': '模型訓練',
    'step.3.desc': '使用優化超參數的LightGBM梯度提升模型，基於16年數據訓練',
    'step.4.title': '信號生成',
    'step.4.desc': '模型預測每隻股票的超額收益。信號越高 = 買入推薦越強',
    'step.5.title': '排名與篩選',
    'step.5.desc': '綜合評分: 70%信號強度 + 30%在20個交易日內進入前25%的一致性',

    /* --- Quant Fund Approach --- */
    'quant.data.heading': '數據基礎設施',
    'quant.data.content': '頂級量化基金(文藝復興科技、Two Sigma、DE Shaw、Citadel)在數據基礎設施上投入數億美元。他們收集另類數據：衛星圖像、信用卡交易、社交媒體情緒、天氣模式、航運數據和專利申請。',
    'quant.factor.heading': '因子模型',
    'quant.factor.content': '基金構建多因子模型，結合：價值因子(市盈率、市淨率)、動量因子(價格趨勢)、質量因子(ROE、負債率)、情緒因子(新聞、社交媒體)和統計套利信號。',
    'quant.ml.heading': '機器學習流程',
    'quant.ml.content': '現代量化基金使用集成方法(梯度提升、隨機森林)、深度學習(LSTM、Transformer)和強化學習進行投資組合優化。模型每日使用滾動驗證重新訓練。',
    'quant.risk.heading': '風險管理',
    'quant.risk.content': '倉位管理使用凱利準則或風險平價。基金維持行業中性、控制市場Beta，並通過動態對衝和止損機制限制回撤。',
    'quant.exec.heading': '執行',
    'quant.exec.content': '智能訂單路由、暗池和算法執行最大限度減少市場影響。基金使用機房託管伺服器實現微秒級執行速度。',

    /* --- Model Performance --- */
    'model.performance': '模型表現',
    'metric.ic': 'IC',
    'metric.icir': 'ICIR',
    'metric.rankic': 'Rank IC',
    'metric.rankicir': 'Rank ICIR',
    'period.train': '訓練區間',
    'period.valid': '驗證區間',
    'period.test': '測試區間',

    /* --- Footer --- */
    'disclaimer': '免責聲明',
    'disclaimer.text': '本分析不構成投資建議。預測由機器學習模型生成，僅供教育和研究用途。過往表現不代表未來結果。在做出投資決策前，請務必自行研究並諮詢合格的財務顧問。',
    'footer.powered': '基於 Microsoft Qlib + LightGBM 構建',
    'refresh.predictions': '刷新預測',
    'auto.refresh': '自動刷新',

    /* --- Sectors --- */
    'sector.Technology': '科技',
    'sector.Financial Services': '金融服務',
    'sector.Consumer Discretionary': '可選消費',
    'sector.Airlines': '航空',
    'sector.Materials': '原材料',
    'sector.Industrials': '工業',
    'sector.Communication Services': '通信服務',

    /* --- Stock Detail Modal --- */
    'company.overview': '公司概況',
    '12m.prediction': '6個月價格預測',
    'historical.performance': '歷史表現',
    'signal.analysis': '信號分析',
    'news.impact': '近期新聞與影響',
    'future.environment': '未來環境分析',
    'current.price': '當前價格',
    '12m.target': '12個月目標價',
    'predicted.price': '預測價格',
    'upper.bound': '上限',
    'lower.bound': '下限',
    'market.cap': '市值',
    'pe.ratio': '市盈率',
    'dividend.yield': '股息率',
    '52w.high': '52週最高',
    '52w.low': '52週最低',
    'click.for.details': '點擊查看詳情',

    /* --- Modal Updates --- */
    '6m.prediction': '6個月價格預測',
    '6m.target': '6個月目標價',
    'refresh.prediction': '刷新預測',
    'sharpe.ratio': '夏普比率',
    'annual.volatility': '年化波動率',
    'max.drawdown': '最大回撤估計',
    'risk.reward': '風險收益比',
    'day.change': '日漲跌',
    'volume': '成交量',
    'forward.pe': '遠期市盈率',
    'beta': 'Beta',
    'rsi.14': 'RSI (14)',
    'revenue.growth': '營收增長',
    'earnings.growth': '利潤增長',
    'profit.margin': '利潤率',
    'debt.equity': '負債權益比',

    /* --- Model Evolution --- */
    'model.evolution': '模型演化與測試',
    'total.rounds': '總輪次',
    'starting.accuracy': '起始準確率',
    'final.accuracy': '最終準確率',
    'target': '目標',
    'ic.improvement': 'IC提升',
    'best.config': '最佳配置',
    'directional.accuracy': '方向準確率',
    'round': '輪次',
    'accuracy': '準確率',
    'notes.label': '備註',

    /* --- Short-Term Trading --- */
    'shortterm.trading': '短線日內交易',
    'recommendation': '推薦',
    'support': '支撐位',
    'resistance': '阻力位',
    'options.scanner': '期權交易掃描',
    'realtime.chart': '實時K線圖',

    /* --- Tabs --- */
    'tab.overview': '總覽',
    'tab.ai': 'AI 分析',
    'tab.market': '市場數據',
    'tab.model': '模型',
    'tab.study': '學習',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI (Claude)',
    'ai.method.factors': '12因子分析',
    'ai.method.model1': '模型1：量化引擎',
    'ai.method.model2': '模型2：情緒代理',
    'ai.method.label': '分析方法',
    'ai.model.comparison': '模型比較',
    'ai.claude.desc': '使用Claude Opus 4.6進行風險投資級別分析。分析基本面、技術面、宏觀環境、內部人士活動和機構持倉。返回評級、目標價、催化劑、風險和進出場策略。',
    'ai.factors.desc': '12類多因子分析，配合動態市場狀態權重。涵蓋動量、價值、質量、成長、波動、情緒、宏觀、經濟、行業、風險調整、歷史類比和機器學習自適應因子。',
    'ai.model1.desc': 'LightGBM + Alpha158量化模型，基於18年標普500數據訓練。使用158個技術Alpha因子生成20日共識信號。最適合中期趨勢檢測。',
    'ai.model2.desc': '5步異常檢測流程：掃描成交量/ATR飆升、研究新聞情緒、預測方向性優勢、凱利準則倉位管理、追蹤結果。最適合短期催化劑驅動的交易。',
    'ai.model1.type': '量化機器學習',
    'ai.model2.type': '行為/異常檢測',
    'ai.claude.type': '自然語言AI',
    'ai.factors.type': '多因子模型',
    'ai.model1.timeframe': '未來20日',
    'ai.model2.timeframe': '5-20日催化劑',
    'ai.claude.timeframe': '6個月戰略',
    'ai.factors.timeframe': '1週至24個月',
    'ai.model1.bestfor': '中期趨勢、板塊輪動',
    'ai.model2.bestfor': '短期動量、事件驅動',
    'ai.claude.bestfor': '戰略定位、深度分析',
    'ai.factors.bestfor': '狀態感知多週期決策',
    'model1.no.data': '此股票無模型1數據。該股票可能不在當前標普500預測集中。',
    'model2.no.data': '此股票無模型2信號。請執行掃描，或該股票可能未觸發任何異常。',
    'model2.run.scan': '執行掃描',
    'analysis.type': '類型',
    'analysis.timeframe': '時間範圍',
    'analysis.bestfor': '最適用於',

    /* --- Misc --- */
    'loading': '載入中...',
    'error.fetch': '載入預測數據失敗，請重試。',
    'no.data': '暫無數據。',
  },

  sc: {
    /* --- Header --- */
    'app.title': '量化选股系统',
    'app.subtitle': 'AI驱动的股票机会扫描器',
    'last.updated': '最后更新',

    /* --- Overview --- */
    'market.overview': '市场概览',
    'stocks.analyzed': '分析股票数',
    'positive.signals': '正向信号',
    'negative.signals': '负向信号',
    'avg.signal': '平均信号',
    'top.sector': '最强板块',
    'signal.ratio': '正向 / 负向',

    /* --- Stock Recommendations --- */
    'top.recommendations': '推荐买入股票',
    'view.consensus': '20日共识',
    'view.singleday': '最新单日',
    'signal.strength': '信号强度',
    'consistency': '一致性',
    'combined.score': '综合评分',
    'sector': '板块',
    'rank': '排名',
    'show.more': '显示更多',
    'show.less': '收起',
    'trend.up': '上升',
    'trend.down': '下降',

    /* --- Stock Analysis / Charts --- */
    'stock.analysis': '股票分析',
    'select.stock': '选择股票',

    /* --- Growth Predictions --- */
    'growth.predictions': '增长预测',
    'predicted.growth': '预测增长',
    'probability': '概率',
    'confidence': '置信度',
    'high.probability': '高概率',
    'medium.probability': '中等概率',
    'low.probability': '低概率',

    /* --- Economic & Market Signals --- */
    'economic.signals': '经济与市场信号',
    'financial.news': '财经与政治新闻',
    'gdp.growth': 'GDP增长率',
    'unemployment': '失业率',
    'inflation.cpi': '通胀(CPI)',
    'interest.rate': '利率',
    'vix.index': 'VIX恐慌指数',
    'consumer.confidence': '消费者信心',
    'trade.balance': '贸易差额',
    'pmi': '制造业PMI',

    /* --- News Sentiment --- */
    'news.positive': '利好',
    'news.negative': '利空',
    'news.neutral': '中性',
    'news.bullish': '看涨',
    'news.bearish': '看跌',

    /* --- Time Periods --- */
    'time.1m': '1月',
    'time.3m': '3月',
    'time.6m': '6月',
    'time.1y': '1年',
    'time.5y': '5年',

    /* --- Indicators --- */
    'indicator.sma': '简单移动平均',
    'indicator.ema': '指数移动平均',
    'indicator.bollinger': '布林带',

    /* --- Model Status --- */
    'model.improving': '模型优化中',
    'improvement.round': '优化轮次',

    /* --- Sector Breakdown --- */
    'sector.breakdown': '板块分析',
    'sector.stocks': '只股票',
    'sector.avg.signal': '平均信号',

    /* --- Methodology --- */
    'methodology': '方法论',
    'methodology.steps': '模型工作原理',
    'methodology.quant': '量化基金如何构建预测系统',

    /* --- Methodology Steps --- */
    'step.1.title': '数据采集',
    'step.1.desc': '从Yahoo Finance获取458只标普500成分股18年的日线OHLCV数据(2008-2026)',
    'step.2.title': '特征工程',
    'step.2.desc': 'Alpha158: 158个技术Alpha因子，包括动量、波动率、成交量模式和价格比率',
    'step.3.title': '模型训练',
    'step.3.desc': '使用优化超参数的LightGBM梯度提升模型，基于16年数据训练',
    'step.4.title': '信号生成',
    'step.4.desc': '模型预测每只股票的超额收益。信号越高 = 买入推荐越强',
    'step.5.title': '排名与筛选',
    'step.5.desc': '综合评分: 70%信号强度 + 30%在20个交易日内进入前25%的一致性',

    /* --- Quant Fund Approach --- */
    'quant.data.heading': '数据基础设施',
    'quant.data.content': '顶级量化基金(文艺复兴科技、Two Sigma、DE Shaw、Citadel)在数据基础设施上投入数亿美元。他们收集另类数据：卫星图像、信用卡交易、社交媒体情绪、天气模式、航运数据和专利申请。',
    'quant.factor.heading': '因子模型',
    'quant.factor.content': '基金构建多因子模型，结合：价值因子(市盈率、市净率)、动量因子(价格趋势)、质量因子(ROE、负债率)、情绪因子(新闻、社交媒体)和统计套利信号。',
    'quant.ml.heading': '机器学习流程',
    'quant.ml.content': '现代量化基金使用集成方法(梯度提升、随机森林)、深度学习(LSTM、Transformer)和强化学习进行投资组合优化。模型每日使用滚动验证重新训练。',
    'quant.risk.heading': '风险管理',
    'quant.risk.content': '仓位管理使用凯利准则或风险平价。基金维持行业中性、控制市场Beta，并通过动态对冲和止损机制限制回撤。',
    'quant.exec.heading': '执行',
    'quant.exec.content': '智能订单路由、暗池和算法执行最大限度减少市场影响。基金使用机房托管服务器实现微秒级执行速度。',

    /* --- Model Performance --- */
    'model.performance': '模型表现',
    'metric.ic': 'IC',
    'metric.icir': 'ICIR',
    'metric.rankic': 'Rank IC',
    'metric.rankicir': 'Rank ICIR',
    'period.train': '训练区间',
    'period.valid': '验证区间',
    'period.test': '测试区间',

    /* --- Footer --- */
    'disclaimer': '免责声明',
    'disclaimer.text': '本分析不构成投资建议。预测由机器学习模型生成，仅供教育和研究用途。过往表现不代表未来结果。在做出投资决策前，请务必自行研究并咨询合格的财务顾问。',
    'footer.powered': '基于 Microsoft Qlib + LightGBM 构建',
    'refresh.predictions': '刷新预测',
    'auto.refresh': '自动刷新',

    /* --- Sectors --- */
    'sector.Technology': '科技',
    'sector.Financial Services': '金融服务',
    'sector.Consumer Discretionary': '可选消费',
    'sector.Airlines': '航空',
    'sector.Materials': '原材料',
    'sector.Industrials': '工业',
    'sector.Communication Services': '通信服务',

    /* --- Stock Detail Modal --- */
    'company.overview': '公司概况',
    '12m.prediction': '6个月价格预测',
    'historical.performance': '历史表现',
    'signal.analysis': '信号分析',
    'news.impact': '近期新闻与影响',
    'future.environment': '未来环境分析',
    'current.price': '当前价格',
    '12m.target': '12个月目标价',
    'predicted.price': '预测价格',
    'upper.bound': '上限',
    'lower.bound': '下限',
    'market.cap': '市值',
    'pe.ratio': '市盈率',
    'dividend.yield': '股息率',
    '52w.high': '52周最高',
    '52w.low': '52周最低',
    'click.for.details': '点击查看详情',

    /* --- Modal Updates --- */
    '6m.prediction': '6个月价格预测',
    '6m.target': '6个月目标价',
    'refresh.prediction': '刷新预测',
    'sharpe.ratio': '夏普比率',
    'annual.volatility': '年化波动率',
    'max.drawdown': '最大回撤估计',
    'risk.reward': '风险收益比',
    'day.change': '日涨跌',
    'volume': '成交量',
    'forward.pe': '远期市盈率',
    'beta': 'Beta',
    'rsi.14': 'RSI (14)',
    'revenue.growth': '营收增长',
    'earnings.growth': '利润增长',
    'profit.margin': '利润率',
    'debt.equity': '负债权益比',

    /* --- Model Evolution --- */
    'model.evolution': '模型演化与测试',
    'total.rounds': '总轮次',
    'starting.accuracy': '起始准确率',
    'final.accuracy': '最终准确率',
    'target': '目标',
    'ic.improvement': 'IC提升',
    'best.config': '最佳配置',
    'directional.accuracy': '方向准确率',
    'round': '轮次',
    'accuracy': '准确率',
    'notes.label': '备注',

    /* --- Short-Term Trading --- */
    'shortterm.trading': '短线日内交易',
    'recommendation': '推荐',
    'support': '支撑位',
    'resistance': '阻力位',
    'options.scanner': '期权交易扫描',
    'realtime.chart': '实时K线图',

    /* --- Tabs --- */
    'tab.overview': '总览',
    'tab.ai': 'AI 分析',
    'tab.market': '市场数据',
    'tab.model': '模型',
    'tab.study': '学习',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI (Claude)',
    'ai.method.factors': '12因子分析',
    'ai.method.model1': '模型1：量化引擎',
    'ai.method.model2': '模型2：情绪代理',
    'ai.method.label': '分析方法',
    'ai.model.comparison': '模型比较',
    'ai.claude.desc': '使用Claude Opus 4.6进行风险投资级别分析。分析基本面、技术面、宏观环境、内部人士活动和机构持仓。返回评级、目标价、催化剂、风险和进出场策略。',
    'ai.factors.desc': '12类多因子分析，配合动态市场状态权重。涵盖动量、价值、质量、成长、波动、情绪、宏观、经济、行业、风险调整、历史类比和机器学习自适应因子。',
    'ai.model1.desc': 'LightGBM + Alpha158量化模型，基于18年标普500数据训练。使用158个技术Alpha因子生成20日共识信号。最适合中期趋势检测。',
    'ai.model2.desc': '5步异常检测流程：扫描成交量/ATR飙升、研究新闻情绪、预测方向性优势、凯利准则仓位管理、追踪结果。最适合短期催化剂驱动的交易。',
    'ai.model1.type': '量化机器学习',
    'ai.model2.type': '行为/异常检测',
    'ai.claude.type': '自然语言AI',
    'ai.factors.type': '多因子模型',
    'ai.model1.timeframe': '未来20日',
    'ai.model2.timeframe': '5-20日催化剂',
    'ai.claude.timeframe': '6个月战略',
    'ai.factors.timeframe': '1周至24个月',
    'ai.model1.bestfor': '中期趋势、板块轮动',
    'ai.model2.bestfor': '短期动量、事件驱动',
    'ai.claude.bestfor': '战略定位、深度分析',
    'ai.factors.bestfor': '状态感知多周期决策',
    'model1.no.data': '此股票无模型1数据。该股票可能不在当前标普500预测集中。',
    'model2.no.data': '此股票无模型2信号。请执行扫描，或该股票可能未触发任何异常。',
    'model2.run.scan': '执行扫描',
    'analysis.type': '类型',
    'analysis.timeframe': '时间范围',
    'analysis.bestfor': '最适用于',

    /* --- Misc --- */
    'loading': '加载中...',
    'error.fetch': '加载预测数据失败，请重试。',
    'no.data': '暂无数据。',
  },
};

/**
 * Initialize the i18n system.
 * Reads saved language from localStorage or falls back to default.
 */
function initI18n() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && SUPPORTED_LANGS.includes(saved)) {
    currentLang = saved;
  }
  return currentLang;
}

/**
 * Get the current language code.
 * @returns {'en' | 'tc' | 'sc'}
 */
function getLang() {
  return currentLang;
}

/**
 * Translate a key to the current language.
 * Falls back to English, then to the raw key.
 * @param {string} key - Translation key
 * @returns {string}
 */
function t(key) {
  const langDict = translations[currentLang];
  if (langDict && langDict[key] !== undefined) {
    return langDict[key];
  }
  const fallback = translations[DEFAULT_LANG];
  if (fallback && fallback[key] !== undefined) {
    return fallback[key];
  }
  return key;
}

/**
 * Translate a sector name based on current language.
 * Uses the sector_cn field from data if in Chinese mode.
 * @param {string} sectorEn - English sector name
 * @param {string} [sectorCn] - Chinese sector name from data
 * @returns {string}
 */
function tSector(sectorEn, sectorCn) {
  if ((currentLang === 'tc' || currentLang === 'sc') && sectorCn) {
    return sectorCn;
  }
  const key = 'sector.' + sectorEn;
  return t(key);
}

/**
 * Get the stock display name based on current language.
 * @param {string} nameEn - English name
 * @param {string} [nameCn] - Chinese name from data
 * @returns {string}
 */
function tName(nameEn, nameCn) {
  if ((currentLang === 'tc' || currentLang === 'sc') && nameCn) {
    return nameCn;
  }
  return nameEn;
}

/**
 * Switch the active language and persist to localStorage.
 * Calls the global re-render callback if provided.
 * @param {string} lang - 'en', 'tc', or 'sc'
 */
function setLanguage(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) {
    return;
  }
  currentLang = lang;
  localStorage.setItem(STORAGE_KEY, lang);

  const langMap = { en: 'en', tc: 'zh-TW', sc: 'zh-CN' };
  document.documentElement.lang = langMap[lang] || 'en';

  if (typeof window.onLanguageChange === 'function') {
    window.onLanguageChange(lang);
  }
}

/**
 * Toggle between the three supported languages: en -> tc -> sc -> en.
 */
function toggleLanguage() {
  const cycle = { en: 'tc', tc: 'sc', sc: 'en' };
  const next = cycle[currentLang] || 'en';
  setLanguage(next);
}
