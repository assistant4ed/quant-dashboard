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
    'tab.guide': 'Guide',

    /* --- Guide Tab --- */
    'guide.eyebrow': 'ALPHAEDGE HK — USER GUIDE',
    'guide.title': 'Master Your Trading Intelligence',
    'guide.subtitle': 'A step-by-step guide to leveraging AI-powered analysis, quantitative signals, and alternative data for smarter investment decisions.',
    'guide.stat.features': 'Core Features',
    'guide.stat.factors': 'Analysis Factors',
    'guide.stat.categories': 'Factor Categories',
    'guide.stat.training': 'Training Data',
    'guide.f1.title': 'Market Overview Dashboard',
    'guide.f1.subtitle': 'Real-time market snapshot at a glance',
    'guide.f2.title': 'AI Strategic Analysis',
    'guide.f2.subtitle': 'Deep investment thesis powered by Claude Opus',
    'guide.f3.title': 'Quantitative Signal Engine',
    'guide.f3.subtitle': '158-factor LightGBM multi-factor scoring',
    'guide.f4.title': 'Technical Chart Analysis',
    'guide.f4.subtitle': 'K-line, SMA, EMA, Bollinger, RSI indicators',
    'guide.f5.title': 'Alternative Data Signals',
    'guide.f5.subtitle': 'Short interest, insider, congress, dark pool',
    'guide.f6.title': 'Options Analysis',
    'guide.f6.subtitle': 'Chain data, unusual activity, strategies',
    'guide.f7.title': 'Economic Calendar & Macro',
    'guide.f7.subtitle': 'CPI, GDP, PMI release tracking',
    'guide.f8.title': 'Interactive Study Module',
    'guide.f8.subtitle': 'Flashcards, quizzes, progress tracking',
    'guide.f9.title': 'Model Monitoring & Evolution',
    'guide.f9.subtitle': 'Backtest validation, quality checks, training history',
    'guide.f10.title': 'Bilingual i18n Support',
    'guide.f10.subtitle': 'EN / Traditional Chinese / Simplified Chinese',
    'guide.try.btn': 'Try It',
    'guide.pro.tip': 'Pro Tip',
    'guide.download': 'Download Guide as PDF',
    'guide.disclaimer': 'This guide describes features available in AlphaEdge HK. All data and analysis are provided for educational and research purposes only. Past model performance does not guarantee future results. This is not financial advice.',
    'guide.f1.tip': 'The overview refreshes every 5 minutes automatically. Use the manual refresh button for immediate updates during market hours.',
    'guide.f2.tip': 'Use Quick Analysis for a rapid overview, or Full Analysis for a comprehensive investment thesis with institutional-grade depth.',
    'guide.f3.tip': 'The model dynamically adjusts factor weights based on detected market regime — it weights quality and value higher in bear markets, momentum and growth higher in bull markets.',
    'guide.f4.tip': 'Combine multiple indicators for confirmation. SMA crossovers with RSI divergence provide stronger signals than any single indicator alone.',
    'guide.f5.tip': 'Congressional trading data can reveal information asymmetry. Look for clusters of similar trades across multiple members.',
    'guide.f6.tip': 'Unusual options activity with high volume-to-open-interest ratios often precedes significant price moves.',
    'guide.f7.tip': 'Focus on the deviation from consensus, not the absolute number. Markets move on surprises, not on expected data.',
    'guide.f8.tip': 'Complete all six topic decks to build a comprehensive trading knowledge foundation. Quiz scores track your progress over time.',
    'guide.f9.tip': 'Check IC (Information Coefficient) and ICIR metrics regularly. An IC above 0.05 with ICIR above 0.5 indicates a model with real predictive edge.',
    'guide.f10.tip': 'Your language preference is saved automatically and persists across sessions. Click the language button in the header to cycle through all three languages.',
    'guide.f1.s1.label': 'Stocks Analyzed',
    'guide.f1.s1.value': '500+',
    'guide.f1.s2.label': 'Update Frequency',
    'guide.f1.s2.value': '5 min',
    'guide.f1.s3.label': 'Signal Types',
    'guide.f1.s3.value': 'Bull / Bear',
    'guide.f1.s4.label': 'Sector Coverage',
    'guide.f1.s4.value': '11 GICS',
    'guide.f2.s1.label': 'AI Model',
    'guide.f2.s1.value': 'Claude Opus',
    'guide.f2.s2.label': 'Analysis Depth',
    'guide.f2.s2.value': '3 Layers',
    'guide.f3.s1.label': 'ML Model',
    'guide.f3.s1.value': 'LightGBM',
    'guide.f3.s2.label': 'Factor Count',
    'guide.f3.s2.value': '158',
    'guide.f3.s3.label': 'Factor Categories',
    'guide.f3.s3.value': '12',
    'guide.f3.s4.label': 'Market Regimes',
    'guide.f3.s4.value': '5',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI Strategic Analysis',
    'ai.method.factors': 'Multi-Factor Scoring',
    'ai.method.model1': 'Quantitative Signal Engine',
    'ai.method.label': 'Analysis Method',
    'ai.model.comparison': 'Analysis Methods',
    'ai.claude.desc': 'Claude Opus-powered comprehensive investment thesis with fundamentals, technicals, macro, and institutional data integration.',
    'ai.factors.desc': '12-category regime-weighted quantitative assessment across momentum, value, quality, growth, volatility, and macro dimensions.',
    'ai.model1.desc': 'LightGBM machine learning model with Alpha158 feature set trained on 18 years of S&P 500 data.',
    'ai.model1.type': 'Quantitative ML',
    'ai.claude.type': 'Natural Language AI',
    'ai.factors.type': 'Multi-Factor Model',
    'ai.model1.timeframe': '20-day forward',
    'ai.claude.timeframe': '6-month strategic',
    'ai.factors.timeframe': '1 week to 24 months',
    'ai.model1.bestfor': 'Medium-term trends, sector rotation',
    'ai.claude.bestfor': 'Strategic positioning, deep analysis',
    'ai.factors.bestfor': 'Regime-aware multi-horizon decisions',
    'model1.no.data': 'No Model 1 data available for this ticker. The stock may not be in the current S&P 500 prediction set.',
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
    'tab.guide': '使用指南',

    /* --- Guide Tab --- */
    'guide.eyebrow': 'ALPHAEDGE HK — 使用指南',
    'guide.title': '掌握您的交易智能工具',
    'guide.subtitle': '逐步指南：運用AI分析、量化信號及另類數據，作出更明智的投資決策。',
    'guide.stat.features': '核心功能',
    'guide.stat.factors': '分析因子',
    'guide.stat.categories': '因子類別',
    'guide.stat.training': '訓練數據',
    'guide.f1.title': '即時市場總覽',
    'guide.f1.subtitle': '一目了然的市場快照',
    'guide.f2.title': 'AI 策略分析',
    'guide.f2.subtitle': 'Claude Opus 驅動的深度投資論述',
    'guide.f3.title': '量化信號引擎',
    'guide.f3.subtitle': 'LightGBM 158因子多因子評分系統',
    'guide.f4.title': '技術圖表分析',
    'guide.f4.subtitle': 'K線圖、SMA、EMA、布林通道、RSI指標',
    'guide.f5.title': '另類數據信號',
    'guide.f5.subtitle': '沽空數據、內幕交易、國會交易、暗池數據',
    'guide.f6.title': '期權分析工具',
    'guide.f6.subtitle': '期權鏈數據、異常活動掃描、策略建議',
    'guide.f7.title': '經濟日曆與宏觀數據',
    'guide.f7.subtitle': 'CPI、GDP、PMI發布追蹤',
    'guide.f8.title': '互動學習模組',
    'guide.f8.subtitle': '學習卡片、測驗、進度追蹤',
    'guide.f9.title': '模型監控與演進',
    'guide.f9.subtitle': '回測驗證、品質檢查、訓練歷史',
    'guide.f10.title': '中英雙語支援',
    'guide.f10.subtitle': '英文 / 繁體中文 / 簡體中文',
    'guide.try.btn': '立即試用',
    'guide.pro.tip': '專業提示',
    'guide.download': '下載指南 PDF',
    'guide.disclaimer': '本指南介紹 AlphaEdge HK 的功能。所有數據及分析僅供教育及研究用途。過往模型表現不代表未來結果。本指南不構成投資建議。',
    'guide.f1.tip': '總覽每5分鐘自動刷新。在交易時段可使用手動刷新按鈕即時更新數據。',
    'guide.f2.tip': '使用「快速分析」獲取概覽，或「完整分析」獲取機構級深度投資論述。',
    'guide.f3.tip': '模型根據偵測到的市場狀態動態調整因子權重——熊市時加重質量和價值因子，牛市時加重動量和增長因子。',
    'guide.f4.tip': '結合多個指標作確認信號。SMA交叉配合RSI背離比單一指標提供更強的交易信號。',
    'guide.f5.tip': '國會議員交易數據可揭示資訊不對稱。留意多位議員同時進行類似交易的情況。',
    'guide.f6.tip': '成交量與未平倉比率異常高的期權活動，通常預示重大價格變動。',
    'guide.f7.tip': '關注數據與市場預期的偏差，而非絕對數值。市場因意外而波動，而非預期中的數據。',
    'guide.f8.tip': '完成全部六個主題課程以建立全面的交易知識基礎。測驗分數會追蹤您的學習進度。',
    'guide.f9.tip': '定期檢查IC（資訊係數）和ICIR指標。IC高於0.05且ICIR高於0.5表示模型具有真正的預測能力。',
    'guide.f10.tip': '語言偏好會自動儲存並在各次會話中保持。點擊頁首的語言按鈕可循環切換三種語言。',
    'guide.f1.s1.label': '分析股票數',
    'guide.f1.s1.value': '500+',
    'guide.f1.s2.label': '更新頻率',
    'guide.f1.s2.value': '5分鐘',
    'guide.f1.s3.label': '信號類型',
    'guide.f1.s3.value': '看漲 / 看跌',
    'guide.f1.s4.label': '板塊覆蓋',
    'guide.f1.s4.value': '11個GICS',
    'guide.f2.s1.label': 'AI模型',
    'guide.f2.s1.value': 'Claude Opus',
    'guide.f2.s2.label': '分析深度',
    'guide.f2.s2.value': '三層分析',
    'guide.f3.s1.label': '機器學習模型',
    'guide.f3.s1.value': 'LightGBM',
    'guide.f3.s2.label': '因子數量',
    'guide.f3.s2.value': '158',
    'guide.f3.s3.label': '因子類別',
    'guide.f3.s3.value': '12',
    'guide.f3.s4.label': '市場狀態',
    'guide.f3.s4.value': '5種',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI戰略分析',
    'ai.method.factors': '多因子評分',
    'ai.method.model1': '量化信號引擎',
    'ai.method.label': '分析方法',
    'ai.model.comparison': '分析方法',
    'ai.claude.desc': 'Claude Opus驅動的綜合投資論述，整合基本面、技術面、宏觀及機構數據。',
    'ai.factors.desc': '12類市場狀態加權量化評估，涵蓋動量、價值、質量、成長、波動及宏觀維度。',
    'ai.model1.desc': 'LightGBM機器學習模型，Alpha158特徵集，基於18年標普500數據訓練。',
    'ai.model1.type': '量化機器學習',
    'ai.claude.type': '自然語言AI',
    'ai.factors.type': '多因子模型',
    'ai.model1.timeframe': '未來20日',
    'ai.claude.timeframe': '6個月戰略',
    'ai.factors.timeframe': '1週至24個月',
    'ai.model1.bestfor': '中期趨勢、板塊輪動',
    'ai.claude.bestfor': '戰略定位、深度分析',
    'ai.factors.bestfor': '狀態感知多週期決策',
    'model1.no.data': '此股票無模型1數據。該股票可能不在當前標普500預測集中。',
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
    'tab.guide': '使用指南',

    /* --- Guide Tab --- */
    'guide.eyebrow': 'ALPHAEDGE HK — 使用指南',
    'guide.title': '掌握您的交易智能工具',
    'guide.subtitle': '逐步指南：运用AI分析、量化信号及另类数据，作出更明智的投资决策。',
    'guide.stat.features': '核心功能',
    'guide.stat.factors': '分析因子',
    'guide.stat.categories': '因子类别',
    'guide.stat.training': '训练数据',
    'guide.f1.title': '即时市场总览',
    'guide.f1.subtitle': '一目了然的市场快照',
    'guide.f2.title': 'AI 策略分析',
    'guide.f2.subtitle': 'Claude Opus 驱动的深度投资论述',
    'guide.f3.title': '量化信号引擎',
    'guide.f3.subtitle': 'LightGBM 158因子多因子评分系统',
    'guide.f4.title': '技术图表分析',
    'guide.f4.subtitle': 'K线图、SMA、EMA、布林通道、RSI指标',
    'guide.f5.title': '另类数据信号',
    'guide.f5.subtitle': '做空数据、内幕交易、国会交易、暗池数据',
    'guide.f6.title': '期权分析工具',
    'guide.f6.subtitle': '期权链数据、异常活动扫描、策略建议',
    'guide.f7.title': '经济日历与宏观数据',
    'guide.f7.subtitle': 'CPI、GDP、PMI发布追踪',
    'guide.f8.title': '互动学习模块',
    'guide.f8.subtitle': '学习卡片、测验、进度追踪',
    'guide.f9.title': '模型监控与演进',
    'guide.f9.subtitle': '回测验证、质量检查、训练历史',
    'guide.f10.title': '中英双语支持',
    'guide.f10.subtitle': '英文 / 繁体中文 / 简体中文',
    'guide.try.btn': '立即试用',
    'guide.pro.tip': '专业提示',
    'guide.download': '下载指南 PDF',
    'guide.disclaimer': '本指南介绍 AlphaEdge HK 的功能。所有数据及分析仅供教育及研究用途。过往模型表现不代表未来结果。本指南不构成投资建议。',
    'guide.f1.tip': '总览每5分钟自动刷新。在交易时段可使用手动刷新按钮即时更新数据。',
    'guide.f2.tip': '使用"快速分析"获取概览，或"完整分析"获取机构级深度投资论述。',
    'guide.f3.tip': '模型根据检测到的市场状态动态调整因子权重——熊市时加重质量和价值因子，牛市时加重动量和增长因子。',
    'guide.f4.tip': '结合多个指标作确认信号。SMA交叉配合RSI背离比单一指标提供更强的交易信号。',
    'guide.f5.tip': '国会议员交易数据可揭示信息不对称。留意多位议员同时进行类似交易的情况。',
    'guide.f6.tip': '成交量与未平仓比率异常高的期权活动，通常预示重大价格变动。',
    'guide.f7.tip': '关注数据与市场预期的偏差，而非绝对数值。市场因意外而波动，而非预期中的数据。',
    'guide.f8.tip': '完成全部六个主题课程以建立全面的交易知识基础。测验分数会追踪您的学习进度。',
    'guide.f9.tip': '定期检查IC（信息系数）和ICIR指标。IC高于0.05且ICIR高于0.5表示模型具有真正的预测能力。',
    'guide.f10.tip': '语言偏好会自动保存并在各次会话中保持。点击页首的语言按钮可循环切换三种语言。',
    'guide.f1.s1.label': '分析股票数',
    'guide.f1.s1.value': '500+',
    'guide.f1.s2.label': '更新频率',
    'guide.f1.s2.value': '5分钟',
    'guide.f1.s3.label': '信号类型',
    'guide.f1.s3.value': '看涨 / 看跌',
    'guide.f1.s4.label': '板块覆盖',
    'guide.f1.s4.value': '11个GICS',
    'guide.f2.s1.label': 'AI模型',
    'guide.f2.s1.value': 'Claude Opus',
    'guide.f2.s2.label': '分析深度',
    'guide.f2.s2.value': '三层分析',
    'guide.f3.s1.label': '机器学习模型',
    'guide.f3.s1.value': 'LightGBM',
    'guide.f3.s2.label': '因子数量',
    'guide.f3.s2.value': '158',
    'guide.f3.s3.label': '因子类别',
    'guide.f3.s3.value': '12',
    'guide.f3.s4.label': '市场状态',
    'guide.f3.s4.value': '5种',

    /* --- AI Analysis Methods --- */
    'ai.method.claude': 'AI战略分析',
    'ai.method.factors': '多因子评分',
    'ai.method.model1': '量化信号引擎',
    'ai.method.label': '分析方法',
    'ai.model.comparison': '分析方法',
    'ai.claude.desc': 'Claude Opus驱动的综合投资论述，整合基本面、技术面、宏观及机构数据。',
    'ai.factors.desc': '12类市场状态加权量化评估，涵盖动量、价值、质量、成长、波动及宏观维度。',
    'ai.model1.desc': 'LightGBM机器学习模型，Alpha158特征集，基于18年标普500数据训练。',
    'ai.model1.type': '量化机器学习',
    'ai.claude.type': '自然语言AI',
    'ai.factors.type': '多因子模型',
    'ai.model1.timeframe': '未来20日',
    'ai.claude.timeframe': '6个月战略',
    'ai.factors.timeframe': '1周至24个月',
    'ai.model1.bestfor': '中期趋势、板块轮动',
    'ai.claude.bestfor': '战略定位、深度分析',
    'ai.factors.bestfor': '状态感知多周期决策',
    'model1.no.data': '此股票无模型1数据。该股票可能不在当前标普500预测集中。',
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
