/**
 * Internationalization module for the Quant Stock Predictor dashboard.
 * Supports English (en) and Chinese (cn).
 * Stores language preference in localStorage.
 */

const STORAGE_KEY = 'qlib-dashboard-lang';
const DEFAULT_LANG = 'en';
const SUPPORTED_LANGS = ['en', 'cn'];

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

    /* --- Misc --- */
    'loading': 'Loading...',
    'error.fetch': 'Failed to load predictions. Please try again.',
    'no.data': 'No data available.',
  },

  cn: {
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
 * @returns {'en' | 'cn'}
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
  if (currentLang === 'cn' && sectorCn) {
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
  if (currentLang === 'cn' && nameCn) {
    return nameCn;
  }
  return nameEn;
}

/**
 * Switch the active language and persist to localStorage.
 * Calls the global re-render callback if provided.
 * @param {string} lang - 'en' or 'cn'
 */
function setLanguage(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) {
    return;
  }
  currentLang = lang;
  localStorage.setItem(STORAGE_KEY, lang);

  document.documentElement.lang = lang === 'cn' ? 'zh-CN' : 'en';

  if (typeof window.onLanguageChange === 'function') {
    window.onLanguageChange(lang);
  }
}

/**
 * Toggle between the two supported languages.
 */
function toggleLanguage() {
  const next = currentLang === 'en' ? 'cn' : 'en';
  setLanguage(next);
}
