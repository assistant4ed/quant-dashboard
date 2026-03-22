/**
 * Stock chart and visualization module.
 * Uses Chart.js for rendering price charts with technical indicators,
 * growth predictions, economic indicators, and news feed.
 */

/* ============================================================
   Constants
   ============================================================ */
const PERIOD_MAP = {
  '1m': '1mo',
  '3m': '3mo',
  '6m': '6mo',
  '1y': '1y',
  '5y': '5y',
};
const BOLLINGER_PERIOD = 20;
const BOLLINGER_STD_DEV = 2;
const SMA_SHORT_PERIOD = 20;
const SMA_LONG_PERIOD = 50;
const EMA_PERIOD = 12;
const MAX_GROWTH_CARDS = 10;
const PROBABILITY_HIGH_THRESHOLD = 70;
const PROBABILITY_LOW_THRESHOLD = 50;
const VOLUME_MILLION = 1000000;
const VOLUME_THOUSAND = 1000;

function formatVolume(vol) {
  if (vol >= 1000000000) return (vol / 1000000000).toFixed(1) + 'B';
  if (vol >= 1000000) return (vol / 1000000).toFixed(1) + 'M';
  if (vol >= 1000) return (vol / 1000).toFixed(0) + 'K';
  return String(vol);
}

/* ============================================================
   Chart State
   ============================================================ */
let priceChart = null;
let volumeChart = null;
let selectedTicker = '';
let selectedPeriod = '1y';
let historyData = [];

/* ============================================================
   Technical Indicator Calculations
   ============================================================ */

/**
 * Simple Moving Average over a given period.
 * Returns null for indices before the window is full.
 */
function calcSMA(data, period) {
  var result = [];
  for (var i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      var sum = 0;
      for (var j = i - period + 1; j <= i; j++) {
        sum += data[j].close;
      }
      result.push(sum / period);
    }
  }
  return result;
}

/**
 * Exponential Moving Average over a given period.
 * Returns null for the first (period - 1) values.
 */
function calcEMA(data, period) {
  var k = 2 / (period + 1);
  var result = [data[0].close];
  for (var i = 1; i < data.length; i++) {
    result.push(data[i].close * k + result[i - 1] * (1 - k));
  }
  for (var i = 0; i < period - 1; i++) {
    result[i] = null;
  }
  return result;
}

/**
 * Bollinger Bands: upper, middle (SMA), and lower bands.
 */
function calcBollinger(data, period, stdDev) {
  var sma = calcSMA(data, period);
  var upper = [];
  var lower = [];
  for (var i = 0; i < data.length; i++) {
    if (sma[i] === null) {
      upper.push(null);
      lower.push(null);
    } else {
      var sumSq = 0;
      for (var j = i - period + 1; j <= i; j++) {
        sumSq += Math.pow(data[j].close - sma[i], 2);
      }
      var std = Math.sqrt(sumSq / period);
      upper.push(sma[i] + stdDev * std);
      lower.push(sma[i] - stdDev * std);
    }
  }
  return { upper: upper, middle: sma, lower: lower };
}

/* ============================================================
   Data Fetching
   ============================================================ */

async function fetchHistory(ticker, period) {
  var apiPeriod = PERIOD_MAP[period] || '1y';
  var response = await fetch(
    '/api/history/' + encodeURIComponent(ticker) + '?period=' + apiPeriod,
  );
  if (!response.ok) throw new Error('HTTP ' + response.status);
  var result = await response.json();
  return result.data.history;
}

async function fetchGrowth() {
  var response = await fetch('/api/growth');
  if (!response.ok) return [];
  var result = await response.json();
  return (result.data && result.data.predictions) || [];
}

async function fetchEconomic() {
  var response = await fetch('/api/economic');
  if (!response.ok) return [];
  var result = await response.json();
  return (result.data && result.data.indicators) || [];
}

async function fetchNews() {
  var response = await fetch('/api/news');
  if (!response.ok) return [];
  var result = await response.json();
  return (result.data && result.data.articles) || [];
}

/* ============================================================
   Price Chart Rendering
   ============================================================ */

function buildPriceDatasets(data) {
  var closes = data.map(function (d) { return d.close; });

  var datasets = [{
    label: selectedTicker + ' Close',
    data: closes,
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59, 130, 246, 0.05)',
    borderWidth: 2,
    fill: true,
    pointRadius: 0,
    pointHitRadius: 10,
    tension: 0.1,
    order: 0,
  }];

  if (document.getElementById('ind-sma20') && document.getElementById('ind-sma20').checked) {
    datasets.push({
      label: 'SMA 20',
      data: calcSMA(data, SMA_SHORT_PERIOD),
      borderColor: '#f59e0b',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      borderDash: [],
      order: 1,
    });
  }

  if (document.getElementById('ind-sma50') && document.getElementById('ind-sma50').checked) {
    datasets.push({
      label: 'SMA 50',
      data: calcSMA(data, SMA_LONG_PERIOD),
      borderColor: '#ef4444',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      order: 2,
    });
  }

  if (document.getElementById('ind-ema12') && document.getElementById('ind-ema12').checked) {
    datasets.push({
      label: 'EMA 12',
      data: calcEMA(data, EMA_PERIOD),
      borderColor: '#10b981',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      borderDash: [4, 4],
      order: 3,
    });
  }

  if (document.getElementById('ind-bollinger') && document.getElementById('ind-bollinger').checked) {
    var bb = calcBollinger(data, BOLLINGER_PERIOD, BOLLINGER_STD_DEV);
    datasets.push({
      label: 'Bollinger Upper',
      data: bb.upper,
      borderColor: 'rgba(168, 85, 247, 0.5)',
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      borderDash: [2, 2],
      order: 4,
    });
    datasets.push({
      label: 'Bollinger Lower',
      data: bb.lower,
      borderColor: 'rgba(168, 85, 247, 0.5)',
      borderWidth: 1,
      pointRadius: 0,
      fill: '-1',
      backgroundColor: 'rgba(168, 85, 247, 0.05)',
      borderDash: [2, 2],
      order: 5,
    });
  }

  return datasets;
}

function renderPriceChart(data) {
  if (!data || !data.length) return;

  // Normalize to TradingView OHLCV format (history API returns {date, open, high, low, close, volume})
  var ohlcvData = data.map(function(d) {
    return {
      time: (d.date || d.time || '').substring(0, 10),
      open: parseFloat(d.open || 0),
      high: parseFloat(d.high || 0),
      low: parseFloat(d.low || 0),
      close: parseFloat(d.close || 0),
      volume: parseInt(d.volume || 0),
    };
  }).filter(function(d) { return d.time && d.close > 0; });

  historyData = ohlcvData;
  initTVChart(ohlcvData, selectedTicker);
}

/* ============================================================
   Volume Chart Rendering
   ============================================================ */

// Volume rendering is handled inside initTVChart (TradingView synced volume panel).
// This stub exists so legacy indicator-checkbox change handlers don't error.
function renderVolumeChart(data) {
  // no-op: volume is rendered as part of the TradingView chart via initTVChart
}

/* ============================================================
   Growth Prediction Rendering
   ============================================================ */

function getGrowthProbabilityMeta(probability) {
  if (probability >= PROBABILITY_HIGH_THRESHOLD) {
    return { color: '#10b981', label: t('high.probability') };
  }
  if (probability >= PROBABILITY_LOW_THRESHOLD) {
    return { color: '#f59e0b', label: t('medium.probability') };
  }
  return { color: '#ef4444', label: t('low.probability') };
}

function renderGrowthGrid(predictions) {
  var grid = document.getElementById('growth-grid');
  if (!grid) return;
  grid.innerHTML = '';

  predictions.slice(0, MAX_GROWTH_CARDS).forEach(function (pred) {
    var card = document.createElement('div');
    card.className = 'growth-card';

    var growthSign = pred.predicted_growth_pct >= 0 ? '+' : '';
    var growthColor = pred.predicted_growth_pct >= 0 ? '#10b981' : '#ef4444';
    var probMeta = getGrowthProbabilityMeta(pred.probability);
    var displayName = tName(pred.name, pred.name_cn);

    card.innerHTML =
      '<div class="growth-card-header">' +
        '<span class="growth-card-ticker">' + escapeHtml(pred.ticker) + '</span>' +
        '<span class="growth-card-name">' + escapeHtml(displayName) + '</span>' +
      '</div>' +
      '<div class="growth-card-body">' +
        '<div class="growth-card-percent" style="color:' + growthColor + '">' +
          growthSign + pred.predicted_growth_pct.toFixed(1) + '%' +
        '</div>' +
        '<div class="growth-card-timeframe">' + t('predicted.growth') + ' (Annual)</div>' +
      '</div>' +
      '<div class="growth-card-probability">' +
        '<div class="probability-header">' +
          '<span>' + t('probability') + '</span>' +
          '<span style="color:' + probMeta.color + ';font-weight:600;">' +
            pred.probability.toFixed(0) + '%' +
          '</span>' +
        '</div>' +
        '<div class="probability-bar">' +
          '<div class="probability-bar-fill" style="width:' + pred.probability +
            '%;background:' + probMeta.color + '"></div>' +
        '</div>' +
        '<div class="probability-label" style="color:' + probMeta.color + '">' +
          probMeta.label +
        '</div>' +
      '</div>';

    grid.appendChild(card);
  });
}

/* ============================================================
   Economic Indicators Rendering
   ============================================================ */

function getIndicatorChangeColor(ind) {
  /* For unemployment and CPI, "up" is negative */
  var isInverse = ind.id === 'unemployment' || ind.id === 'cpi';
  if (isInverse) {
    return ind.direction === 'up' ? '#ef4444' : '#10b981';
  }
  return ind.direction === 'up' ? '#10b981' : '#ef4444';
}

function renderEconomicGrid(indicators) {
  var grid = document.getElementById('macro-grid');
  if (!grid) return;
  grid.innerHTML = '';

  indicators.forEach(function (ind) {
    var card = document.createElement('div');
    card.className = 'macro-card';

    var changeSign = ind.change >= 0 ? '+' : '';
    var changeColor = getIndicatorChangeColor(ind);
    var arrow = ind.direction === 'up' ? '&#9650;' : '&#9660;';
    var displayName = tName(ind.name, ind.name_cn);
    var unit = ind.unit || '';

    card.innerHTML =
      '<div class="macro-card-name">' + escapeHtml(displayName) + '</div>' +
      '<div class="macro-card-value">' + ind.value + unit + '</div>' +
      '<div class="macro-card-change" style="color:' + changeColor + '">' +
        arrow + ' ' + changeSign + ind.change + unit +
      '</div>' +
      '<div class="macro-card-period">' + escapeHtml(ind.period) + '</div>';

    grid.appendChild(card);
  });
}

/* ============================================================
   News Feed Rendering
   ============================================================ */

function renderNewsFeed(articles) {
  var feed = document.getElementById('news-feed');
  if (!feed) return;
  feed.innerHTML = '';

  articles.forEach(function (article) {
    var item = document.createElement('article');
    item.className = 'news-item';

    var sentimentClass = 'news-sentiment--' + article.sentiment;
    var sentimentLabel = t('news.' + article.sentiment);
    var title = tName(article.title, article.title_cn);
    var summary = tName(article.summary, article.summary_cn);

    item.innerHTML =
      '<div class="news-item-header">' +
        '<div class="news-item-meta">' +
          '<span class="news-source">' + escapeHtml(article.source) + '</span>' +
          '<span class="news-date">' + escapeHtml(article.date) + '</span>' +
          '<span class="news-sentiment ' + sentimentClass + '">' +
            sentimentLabel +
          '</span>' +
        '</div>' +
        '<h4 class="news-title">' + escapeHtml(title) + '</h4>' +
      '</div>' +
      '<p class="news-summary">' + escapeHtml(summary) + '</p>';

    feed.appendChild(item);
  });
}

/* ============================================================
   Ticker Dropdown
   ============================================================ */

function populateTickerDropdown() {
  var select = document.getElementById('chart-ticker-select');
  if (!select || !predictionData) return;

  select.innerHTML = '<option value="">' + t('select.stock') + '</option>';

  var stocks = predictionData.top_stocks || [];
  stocks.forEach(function (stock) {
    var opt = document.createElement('option');
    opt.value = stock.ticker;
    opt.textContent = stock.ticker + ' - ' + tName(stock.name, stock.name_cn);
    select.appendChild(opt);
  });

  /* Auto-select the top-ranked stock */
  if (stocks.length > 0) {
    select.value = stocks[0].ticker;
    loadChart(stocks[0].ticker, selectedPeriod);
  }
}

/* ============================================================
   Chart Loading
   ============================================================ */

async function loadChart(ticker, period) {
  selectedTicker = ticker;
  try {
    historyData = await fetchHistory(ticker, period);
    renderPriceChart(historyData);
    renderVolumeChart(historyData);
  } catch (err) {
    console.error('Failed to load chart data:', err);
  }
}

/* ============================================================
   Event Wiring
   ============================================================ */

function wireChartEvents() {
  var select = document.getElementById('chart-ticker-select');
  if (select) {
    select.addEventListener('change', function () {
      if (this.value) loadChart(this.value, selectedPeriod);
    });
  }

  /* Period toggle buttons */
  var periodButtons = document.querySelectorAll('.chart-period-group .toggle-btn');
  periodButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      periodButtons.forEach(function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      selectedPeriod = btn.dataset.period;
      if (selectedTicker) loadChart(selectedTicker, selectedPeriod);
    });
  });

  /* Indicator checkboxes trigger re-render without re-fetching */
  var indicatorIds = ['ind-sma20', 'ind-sma50', 'ind-ema12', 'ind-bollinger', 'ind-volume'];
  indicatorIds.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', function () {
        if (historyData.length > 0) {
          renderPriceChart(historyData);
          renderVolumeChart(historyData);
        }
      });
    }
  });
}

/* ============================================================
   Initialization (called by app.js after data loads)
   ============================================================ */

function initCharts() {
  populateTickerDropdown();
  wireChartEvents();

  fetchGrowth().then(renderGrowthGrid);
  fetchEconomic().then(renderEconomicGrid);
  fetchNews().then(renderNewsFeed);
  initModelEvolution();
}

/* ============================================================
   Language Change Hook
   ============================================================ */

var originalOnLangChange = window.onLanguageChange;

window.onLanguageChange = function (lang) {
  if (typeof originalOnLangChange === 'function') {
    originalOnLangChange(lang);
  }
  /* Re-render chart-dependent labels and data */
  populateTickerDropdown();
  fetchGrowth().then(renderGrowthGrid);
  fetchEconomic().then(renderEconomicGrid);
  fetchNews().then(renderNewsFeed);
};

/* ============================================================
   Stock Detail Modal
   ============================================================ */

let modalPredictionChart = null;
let modalHistoryChart = null;
let modalHistoryPeriod = '1y';

function openStockModal(stock) {
  var modal = document.getElementById('stock-modal');
  if (!modal) return;

  /* Set header info */
  document.getElementById('modal-rank').textContent = stock.rank;
  document.getElementById('modal-title').textContent = stock.ticker + ' - ' + tName(stock.name, stock.name_cn);
  document.getElementById('modal-subtitle').textContent = tSector(stock.sector, stock.sector_cn);

  /* Update section labels with i18n */
  var companyLabel = document.getElementById('modal-company-label');
  if (companyLabel) companyLabel.textContent = t('company.overview');
  var predictionLabel = document.getElementById('modal-prediction-label');
  if (predictionLabel) predictionLabel.textContent = t('6m.prediction');
  var historyLabel = document.getElementById('modal-history-label');
  if (historyLabel) historyLabel.textContent = t('historical.performance');
  var signalLabel = document.getElementById('modal-signal-label');
  if (signalLabel) signalLabel.textContent = t('signal.analysis');
  var newsLabel = document.getElementById('modal-news-label');
  if (newsLabel) newsLabel.textContent = t('news.impact');
  var envLabel = document.getElementById('modal-environment-label');
  if (envLabel) envLabel.textContent = t('future.environment');

  /* Reset modal history period for fresh modal */
  modalHistoryPeriod = '1y';

  /* Load all sections */
  loadCompanyInfo(stock);
  loadPredictionChart(stock);
  loadModalHistory(stock);
  loadSignalAnalysis(stock);
  loadModalNews(stock);
  loadEnvironmentAnalysis(stock);

  /* Show modal */
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  /* Wire refresh prediction button */
  var refreshBtn = document.getElementById('modal-refresh-btn');
  if (refreshBtn) {
    refreshBtn.onclick = function() { refreshStockPrediction(stock); };
  }

  /* Close handlers */
  document.getElementById('modal-close').onclick = closeStockModal;
  modal.addEventListener('click', function(e) {
    if (e.target === modal) closeStockModal();
  });
  document.addEventListener('keydown', handleModalEscape);

  /* Focus management for accessibility */
  document.getElementById('modal-close').focus();
}

function closeStockModal() {
  var modal = document.getElementById('stock-modal');
  if (modal) modal.classList.add('hidden');
  document.body.style.overflow = '';
  document.removeEventListener('keydown', handleModalEscape);
  if (modalPredictionChart) { modalPredictionChart.destroy(); modalPredictionChart = null; }
  if (modalHistoryChart) { modalHistoryChart.destroy(); modalHistoryChart = null; }
  delete window._modalHistoryData;
}

function handleModalEscape(e) {
  if (e.key === 'Escape') closeStockModal();
}

async function loadCompanyInfo(stock) {
  var infoEl = document.getElementById('company-desc');
  var metaEl = document.getElementById('company-meta');

  /* Try to fetch company info from API */
  try {
    var response = await fetch('/api/company/' + encodeURIComponent(stock.ticker));
    if (response.ok) {
      var result = await response.json();
      var company = result.data;
      infoEl.textContent = tName(company.description, company.description_cn) || t('no.data');

      metaEl.innerHTML = '';
      var metaItems = [
        { label: t('current.price'), value: company.current_price ? '$' + company.current_price : 'N/A' },
        { label: t('day.change'), value: company.day_change_pct !== undefined ? (company.day_change_pct >= 0 ? '+' : '') + company.day_change_pct + '%' : 'N/A' },
        { label: t('volume'), value: company.volume ? formatVolume(company.volume) : 'N/A' },
        { label: t('market.cap'), value: company.market_cap || 'N/A' },
        { label: t('pe.ratio'), value: company.pe_ratio || 'N/A' },
        { label: t('forward.pe'), value: company.forward_pe || 'N/A' },
        { label: t('dividend.yield'), value: company.dividend_yield ? company.dividend_yield + '%' : 'N/A' },
        { label: t('beta'), value: company.beta || 'N/A' },
        { label: t('rsi.14'), value: company.rsi_14 ? company.rsi_14.toFixed(1) : 'N/A' },
        { label: t('52w.high'), value: company.high_52w ? '$' + company.high_52w : 'N/A' },
        { label: t('52w.low'), value: company.low_52w ? '$' + company.low_52w : 'N/A' },
        { label: t('revenue.growth'), value: company.revenue_growth ? (company.revenue_growth * 100).toFixed(1) + '%' : 'N/A' },
        { label: t('earnings.growth'), value: company.earnings_growth ? (company.earnings_growth * 100).toFixed(1) + '%' : 'N/A' },
        { label: t('profit.margin'), value: company.profit_margin ? (company.profit_margin * 100).toFixed(1) + '%' : 'N/A' },
        { label: t('debt.equity'), value: company.debt_to_equity ? company.debt_to_equity.toFixed(1) : 'N/A' },
      ];

      metaItems.forEach(function(item) {
        var div = document.createElement('div');
        div.className = 'company-meta-item';
        div.innerHTML = '<div class="company-meta-label">' + escapeHtml(item.label) + '</div>' +
          '<div class="company-meta-value">' + escapeHtml(String(item.value)) + '</div>';
        metaEl.appendChild(div);
      });
      return;
    }
  } catch (e) {
    console.warn('Company info not available:', e);
  }

  /* Fallback if API not available */
  infoEl.textContent = tName(stock.name, stock.name_cn) + ' (' + stock.ticker + ') - ' + tSector(stock.sector, stock.sector_cn);
  metaEl.innerHTML = '';
}

async function loadPredictionChart(stock) {
  var ctx = document.getElementById('prediction-chart');
  if (!ctx) return;
  if (modalPredictionChart) modalPredictionChart.destroy();

  /* Fetch prediction data */
  try {
    var response = await fetch('/api/predict-forward/' + encodeURIComponent(stock.ticker));
    if (!response.ok) throw new Error('HTTP ' + response.status);
    var result = await response.json();
    var pred = result.data;

    var labels = pred.dates;
    var predicted = pred.predicted_prices;
    var upperBand = pred.upper_band;
    var lowerBand = pred.lower_band;

    modalPredictionChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: t('predicted.price'),
            data: predicted,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 2.5,
            fill: false,
            pointRadius: 0,
            tension: 0.3,
          },
          {
            label: t('upper.bound') + ' (90%)',
            data: upperBand,
            borderColor: 'rgba(16, 185, 129, 0.4)',
            borderWidth: 1,
            borderDash: [4, 4],
            fill: false,
            pointRadius: 0,
          },
          {
            label: t('lower.bound') + ' (10%)',
            data: lowerBand,
            borderColor: 'rgba(239, 68, 68, 0.4)',
            borderWidth: 1,
            borderDash: [4, 4],
            fill: '-1',
            backgroundColor: 'rgba(59, 130, 246, 0.05)',
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: {
            callbacks: {
              label: function(ctx) { return ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2); },
            },
          },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 12, font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { callback: function(v) { return '$' + v.toFixed(0); } }, grid: { color: 'rgba(0,0,0,0.06)' } },
        },
      },
    });

    /* Prediction summary cards */
    renderPredictionSummary(pred);

  } catch (e) {
    console.warn('Prediction chart not available:', e);
    ctx.parentElement.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px">' + t('no.data') + '</p>';
  }
}

function renderPredictionSummary(pred) {
  var container = document.getElementById('prediction-summary');
  if (!container) return;
  container.innerHTML = '';

  var cards = [
    { label: t('current.price'), value: '$' + (pred.base_price || 0).toFixed(2), color: 'var(--text-primary)' },
    { label: t('6m.target'), value: '$' + (pred.target_price || 0).toFixed(2), color: pred.growth_pct >= 0 ? '#10b981' : '#ef4444' },
    { label: t('predicted.growth'), value: (pred.growth_pct >= 0 ? '+' : '') + (pred.growth_pct || 0).toFixed(1) + '%', color: pred.growth_pct >= 0 ? '#10b981' : '#ef4444' },
    { label: t('probability'), value: (pred.probability || 0).toFixed(0) + '%', color: pred.probability >= 70 ? '#10b981' : pred.probability >= 50 ? '#f59e0b' : '#ef4444' },
    { label: t('sharpe.ratio'), value: (pred.sharpe_estimate || 0).toFixed(2), color: pred.sharpe_estimate >= 1 ? '#10b981' : pred.sharpe_estimate >= 0.5 ? '#f59e0b' : '#ef4444' },
    { label: t('annual.volatility'), value: (pred.annual_volatility || 0).toFixed(1) + '%', color: pred.annual_volatility <= 30 ? '#10b981' : pred.annual_volatility <= 50 ? '#f59e0b' : '#ef4444' },
    { label: t('max.drawdown'), value: '-' + (pred.max_drawdown_estimate || 0).toFixed(1) + '%', color: '#ef4444' },
    { label: t('risk.reward'), value: (pred.risk_reward_ratio || 0).toFixed(2), color: pred.risk_reward_ratio >= 0.5 ? '#10b981' : '#f59e0b' },
  ];

  cards.forEach(function(c) {
    var div = document.createElement('div');
    div.className = 'prediction-card';
    div.innerHTML = '<div class="prediction-card-label">' + escapeHtml(c.label) + '</div>' +
      '<div class="prediction-card-value" style="color:' + c.color + '">' + c.value + '</div>';
    container.appendChild(div);
  });
}

async function loadModalHistory(stock) {
  var ctx = document.getElementById('modal-history-chart');
  if (!ctx) return;
  if (modalHistoryChart) modalHistoryChart.destroy();

  /* Render period controls */
  var controlsEl = document.getElementById('modal-history-controls');
  if (controlsEl && !controlsEl.dataset.wired) {
    controlsEl.dataset.wired = 'true';
    var periodBtns = controlsEl.querySelectorAll('.toggle-btn');
    periodBtns.forEach(function(btn) {
      btn.addEventListener('click', function() {
        periodBtns.forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        modalHistoryPeriod = btn.dataset.period;
        loadModalHistory(stock);
      });
    });
    var checkboxes = controlsEl.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(function(cb) {
      cb.addEventListener('change', function() {
        renderModalHistoryChart(stock, ctx);
      });
    });
  }

  try {
    window._modalHistoryData = await fetchHistory(stock.ticker, modalHistoryPeriod);
    if (!window._modalHistoryData || window._modalHistoryData.length === 0) throw new Error('No data');
    renderModalHistoryChart(stock, ctx);
  } catch (e) {
    console.warn('History chart error:', e);
  }
}

function renderModalHistoryChart(stock, ctx) {
  if (modalHistoryChart) modalHistoryChart.destroy();
  var data = window._modalHistoryData;
  if (!data || data.length === 0) return;

  var closes = data.map(function(d) { return d.close; });
  var datasets = [{
    label: stock.ticker + ' Close',
    data: closes,
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59, 130, 246, 0.05)',
    borderWidth: 2,
    fill: true,
    pointRadius: 0,
    tension: 0.1,
    order: 0,
  }];

  /* Check modal indicator checkboxes */
  if (document.getElementById('modal-ind-sma20') && document.getElementById('modal-ind-sma20').checked) {
    datasets.push({
      label: 'SMA 20',
      data: calcSMA(data, 20),
      borderColor: '#f59e0b',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      order: 1,
    });
  }
  if (document.getElementById('modal-ind-sma50') && document.getElementById('modal-ind-sma50').checked) {
    datasets.push({
      label: 'SMA 50',
      data: calcSMA(data, 50),
      borderColor: '#ef4444',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      order: 2,
    });
  }
  if (document.getElementById('modal-ind-ema12') && document.getElementById('modal-ind-ema12').checked) {
    datasets.push({
      label: 'EMA 12',
      data: calcEMA(data, 12),
      borderColor: '#10b981',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      borderDash: [4, 4],
      order: 3,
    });
  }
  if (document.getElementById('modal-ind-bollinger') && document.getElementById('modal-ind-bollinger').checked) {
    var bb = calcBollinger(data, 20, 2);
    datasets.push({
      label: 'Bollinger Upper',
      data: bb.upper,
      borderColor: 'rgba(168, 85, 247, 0.5)',
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      borderDash: [2, 2],
      order: 4,
    });
    datasets.push({
      label: 'Bollinger Lower',
      data: bb.lower,
      borderColor: 'rgba(168, 85, 247, 0.5)',
      borderWidth: 1,
      pointRadius: 0,
      fill: '-1',
      backgroundColor: 'rgba(168, 85, 247, 0.05)',
      borderDash: [2, 2],
      order: 5,
    });
  }

  modalHistoryChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) { return d.date; }),
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: function(context) {
              var v = context.parsed.y;
              return context.dataset.label + ': ' + (v !== null ? '$' + v.toFixed(2) : 'N/A');
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { callback: function(v) { return '$' + v.toFixed(0); }, font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.06)' } },
      },
    },
  });
}

function loadSignalAnalysis(stock) {
  var grid = document.getElementById('signal-analysis');
  if (!grid) return;
  grid.innerHTML = '';

  var metrics = [
    { label: t('signal.strength'), value: formatSignal(stock.signal), pct: Math.min(Math.abs(stock.signal) / 0.03 * 100, 100), color: stock.signal >= 0 ? '#10b981' : '#ef4444' },
    { label: t('consistency'), value: ((stock.consistency || 0) * 100).toFixed(0) + '%', pct: (stock.consistency || 0) * 100, color: '#3b82f6' },
    { label: t('combined.score'), value: (stock.combined_score || 0).toFixed(4), pct: (stock.combined_score || 0) * 100, color: '#8b5cf6' },
  ];

  metrics.forEach(function(m) {
    var div = document.createElement('div');
    div.className = 'signal-metric';
    div.innerHTML = '<div class="signal-metric-label">' + escapeHtml(m.label) + '</div>' +
      '<div class="signal-metric-value" style="color:' + m.color + '">' + m.value + '</div>' +
      '<div class="signal-metric-bar"><div class="signal-metric-bar-fill" style="width:' + m.pct + '%;background:' + m.color + '"></div></div>';
    grid.appendChild(div);
  });
}

async function loadModalNews(stock) {
  var feed = document.getElementById('modal-news');
  if (!feed) return;
  feed.innerHTML = '<p style="color:var(--text-muted)">' + t('loading') + '</p>';

  try {
    var response = await fetch('/api/stock-news/' + encodeURIComponent(stock.ticker));
    if (!response.ok) throw new Error('HTTP ' + response.status);
    var result = await response.json();
    var articles = result.data.articles || [];

    feed.innerHTML = '';
    if (articles.length === 0) {
      feed.innerHTML = '<p style="color:var(--text-muted)">' + t('no.data') + '</p>';
      return;
    }

    articles.slice(0, 5).forEach(function(article) {
      var item = document.createElement('div');
      item.className = 'news-item';
      var sentimentClass = 'news-sentiment--' + (article.sentiment || 'neutral');
      item.innerHTML =
        '<div class="news-item-header">' +
          '<div class="news-item-meta">' +
            '<span class="news-source">' + escapeHtml(article.source || '') + '</span>' +
            '<span class="news-date">' + escapeHtml(article.date || '') + '</span>' +
            '<span class="news-sentiment ' + sentimentClass + '">' + t('news.' + (article.sentiment || 'neutral')) + '</span>' +
          '</div>' +
          '<h4 class="news-title">' + escapeHtml(tName(article.title, article.title_cn) || '') + '</h4>' +
        '</div>' +
        '<p class="news-summary">' + escapeHtml(tName(article.summary, article.summary_cn) || '') + '</p>';
      feed.appendChild(item);
    });
  } catch (e) {
    feed.innerHTML = '<p style="color:var(--text-muted)">' + t('no.data') + '</p>';
  }
}

function loadEnvironmentAnalysis(stock) {
  var container = document.getElementById('environment-analysis');
  if (!container) return;

  var factors = generateEnvironmentFactors(stock);
  container.innerHTML = '';

  factors.forEach(function(factor) {
    var div = document.createElement('div');
    div.className = 'env-factor env-factor--' + factor.sentiment;
    div.innerHTML =
      '<div class="env-factor-title">' + escapeHtml(factor.title) + '</div>' +
      '<div class="env-factor-desc">' + escapeHtml(factor.description) + '</div>';
    container.appendChild(div);
  });
}

function generateEnvironmentFactors(stock) {
  var factors = [];
  var sector = stock.sector || '';
  var lang = getLang();

  /* Sector-specific factors */
  var sectorFactors = {
    'Technology': [
      { title: lang !== 'en' ? 'AI投资热潮' : 'AI Investment Boom', desc: lang !== 'en' ? 'AI基础设施支出持续增长，利好科技板块' : 'AI infrastructure spending continues to surge, benefiting tech sector', sentiment: 'positive' },
      { title: lang !== 'en' ? '利率环境' : 'Interest Rate Environment', desc: lang !== 'en' ? '利率下降预期利好成长型科技股估值' : 'Expected rate cuts support growth tech valuations', sentiment: 'positive' },
    ],
    'Financial Services': [
      { title: lang !== 'en' ? '利率曲线正常化' : 'Yield Curve Normalization', desc: lang !== 'en' ? '收益率曲线正常化改善银行净息差' : 'Yield curve normalization improves bank net interest margins', sentiment: 'positive' },
      { title: lang !== 'en' ? '监管环境' : 'Regulatory Environment', desc: lang !== 'en' ? '金融监管政策趋于稳定' : 'Financial regulatory policies stabilizing', sentiment: 'neutral' },
    ],
    'Airlines': [
      { title: lang !== 'en' ? '旅游需求强劲' : 'Strong Travel Demand', desc: lang !== 'en' ? '国际旅行需求持续恢复' : 'International travel demand continues recovery', sentiment: 'positive' },
      { title: lang !== 'en' ? '油价走势' : 'Oil Price Trend', desc: lang !== 'en' ? 'OPEC+增产导致油价下行，降低航空燃油成本' : 'OPEC+ production increase pushes oil lower, reducing fuel costs', sentiment: 'positive' },
    ],
    'Consumer Discretionary': [
      { title: lang !== 'en' ? '消费者支出' : 'Consumer Spending', desc: lang !== 'en' ? '消费支出显示放缓迹象，需关注' : 'Consumer spending showing signs of slowdown, worth monitoring', sentiment: 'negative' },
      { title: lang !== 'en' ? '就业市场' : 'Labor Market', desc: lang !== 'en' ? '就业市场保持韧性，支撑消费能力' : 'Labor market remains resilient, supporting spending power', sentiment: 'positive' },
    ],
    'Materials': [
      { title: lang !== 'en' ? '基建支出' : 'Infrastructure Spending', desc: lang !== 'en' ? '美国基建法案推动原材料需求' : 'US infrastructure bill driving materials demand', sentiment: 'positive' },
    ],
  };

  /* Add sector-specific factors */
  if (sectorFactors[sector]) {
    sectorFactors[sector].forEach(function(f) {
      factors.push({ title: f.title, description: f.desc, sentiment: f.sentiment });
    });
  }

  /* Add universal macro factors */
  factors.push({
    title: lang !== 'en' ? '美联储政策' : 'Fed Policy Outlook',
    description: lang !== 'en' ? '美联储暗示2026年Q2可能降息25个基点' : 'Fed signals potential 25bp rate cut in Q2 2026',
    sentiment: 'positive',
  });

  factors.push({
    title: lang !== 'en' ? '地缘政治' : 'Geopolitical Risk',
    description: lang !== 'en' ? '美中贸易关系改善降低不确定性' : 'Improved US-China trade relations reducing uncertainty',
    sentiment: 'positive',
  });

  return factors;
}

async function refreshStockPrediction(stock) {
  var btn = document.getElementById('modal-refresh-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = t('loading');
  }
  try {
    var response = await fetch('/api/analyze/' + encodeURIComponent(stock.ticker), { method: 'POST' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    /* Reload prediction chart */
    await loadPredictionChart(stock);
    await loadModalHistory(stock);
  } catch (e) {
    console.warn('Refresh prediction failed:', e);
  }
  if (btn) {
    btn.disabled = false;
    btn.textContent = t('refresh.prediction');
  }
}

/* ============================================================
   Model Evolution Page
   ============================================================ */

let evolutionAccuracyChart = null;
let evolutionMetricsChart = null;

async function initModelEvolution() {
  try {
    var response = await fetch('/api/model-evolution');
    if (!response.ok) return;
    var result = await response.json();
    var data = result.data;
    if (!data || !data.evolution || data.evolution.length === 0) return;

    /* Get data scrape date from predictions */
    try {
      var predResp = await fetch('/api/predictions');
      if (predResp.ok) {
        var predData = await predResp.json();
        data.generated_at = (predData.data && predData.data.generated_at) || '';
      }
    } catch(ignore) {}

    renderEvolutionSummary(data);
    renderEvolutionAccuracyChart(data.evolution);
    renderEvolutionMetricsChart(data.evolution);
    renderEvolutionTable(data.evolution);
    renderFormulas(data.formulas);
  } catch (e) {
    console.warn('Model evolution load failed:', e);
  }
}

function renderEvolutionSummary(data) {
  var container = document.getElementById('evolution-summary');
  if (!container) return;
  container.innerHTML = '';

  var evo = data.evolution;
  var best = evo[evo.length - 1];
  var first = evo[0];

  /* Explanation banner with data date */
  var genDate = data.generated_at || '';
  var formattedDate = '';
  if (genDate) {
    try { formattedDate = new Date(genDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); } catch(e) {}
  }
  var banner = document.createElement('div');
  banner.style.cssText = 'background:var(--bg-card,#fff);border:1px solid var(--border-color,#E8E8EC);border-radius:8px;padding:20px;margin-bottom:20px;grid-column:1/-1;';
  banner.innerHTML =
    '<h4 style="font-size:0.875rem;font-weight:600;color:var(--navy,#1B2A4A);margin-bottom:8px;">About This Page</h4>' +
    '<p style="font-size:0.8125rem;color:var(--text-secondary,#4A4A5A);line-height:1.7;margin:0 0 8px;">' +
      'Training history of the <strong>Quantitative Signal Engine</strong> (LightGBM + Alpha158), refined across ' + evo.length + ' rounds. ' +
      'Each round tests different hyperparameters to improve prediction accuracy. The trained model generates 20-day forward signals used in AI Analysis.' +
    '</p>' +
    (formattedDate ? '<div style="font-size:0.75rem;color:var(--text-muted,#8A8A9A);font-family:monospace;">Data generated: ' + formattedDate + '</div>' : '');
  container.appendChild(banner);

  var cards = [
    { label: t('total.rounds'), value: evo.length, color: 'var(--accent-blue)' },
    { label: t('starting.accuracy'), value: (first.metrics.directional_accuracy * 100).toFixed(0) + '%', color: '#ef4444' },
    { label: t('final.accuracy'), value: (best.metrics.directional_accuracy * 100).toFixed(0) + '%', color: best.metrics.directional_accuracy >= 0.7 ? '#10b981' : '#f59e0b' },
    { label: t('target'), value: '70%', color: 'var(--text-secondary)' },
    { label: t('ic.improvement'), value: ((best.metrics.ic - first.metrics.ic) / first.metrics.ic * 100).toFixed(0) + '%', color: '#10b981' },
    { label: t('best.config'), value: 'Round ' + best.round, color: 'var(--accent-blue)' },
  ];

  cards.forEach(function(c) {
    var div = document.createElement('div');
    div.className = 'evo-summary-card';
    div.innerHTML = '<div class="evo-summary-label">' + escapeHtml(c.label) + '</div>' +
      '<div class="evo-summary-value" style="color:' + c.color + '">' + c.value + '</div>';
    container.appendChild(div);
  });
}

function renderEvolutionAccuracyChart(evolution) {
  var ctx = document.getElementById('evolution-accuracy-chart');
  if (!ctx) return;
  if (evolutionAccuracyChart) evolutionAccuracyChart.destroy();

  var labels = evolution.map(function(e) { return 'Round ' + e.round; });
  var accuracies = evolution.map(function(e) { return (e.metrics.directional_accuracy * 100).toFixed(1); });
  var target = evolution.map(function() { return 70; });

  evolutionAccuracyChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: t('directional.accuracy'),
          data: accuracies,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          borderWidth: 3,
          fill: true,
          pointRadius: 6,
          pointBackgroundColor: evolution.map(function(e) {
            return e.metrics.directional_accuracy >= 0.7 ? '#10b981' : '#3b82f6';
          }),
          tension: 0.3,
        },
        {
          label: t('target') + ' (70%)',
          data: target,
          borderColor: '#ef4444',
          borderWidth: 2,
          borderDash: [8, 4],
          fill: false,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: {
          callbacks: {
            afterLabel: function(ctx) {
              if (ctx.datasetIndex !== 0) return '';
              var evo = evolution[ctx.dataIndex];
              return evo.notes || '';
            },
          },
        },
      },
      scales: {
        y: {
          min: 45,
          max: 80,
          ticks: { callback: function(v) { return v + '%'; } },
          grid: { color: 'rgba(0,0,0,0.06)' },
        },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderEvolutionMetricsChart(evolution) {
  var ctx = document.getElementById('evolution-metrics-chart');
  if (!ctx) return;
  if (evolutionMetricsChart) evolutionMetricsChart.destroy();

  var labels = evolution.map(function(e) { return 'R' + e.round; });

  evolutionMetricsChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'IC',
          data: evolution.map(function(e) { return e.metrics.ic; }),
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
        },
        {
          label: 'Rank IC',
          data: evolution.map(function(e) { return e.metrics.rank_ic; }),
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
        },
        {
          label: 'Composite',
          data: evolution.map(function(e) { return e.metrics.composite_score; }),
          backgroundColor: 'rgba(245, 158, 11, 0.7)',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
      },
      scales: {
        y: { grid: { color: 'rgba(0,0,0,0.06)' } },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderEvolutionTable(evolution) {
  var container = document.getElementById('evolution-table');
  if (!container) return;

  var html = '<table class="evo-table">';
  html += '<thead><tr>';
  html += '<th>' + t('round') + '</th>';
  html += '<th>LR</th>';
  html += '<th>Leaves</th>';
  html += '<th>Depth</th>';
  html += '<th>L1/L2</th>';
  html += '<th>IC</th>';
  html += '<th>ICIR</th>';
  html += '<th>' + t('accuracy') + '</th>';
  html += '<th>' + t('notes.label') + '</th>';
  html += '</tr></thead><tbody>';

  evolution.forEach(function(e) {
    var accClass = e.metrics.directional_accuracy >= 0.7 ? 'evo-pass' : '';
    html += '<tr class="' + accClass + '">';
    html += '<td>' + e.round + '</td>';
    html += '<td>' + e.config.learning_rate + '</td>';
    html += '<td>' + e.config.num_leaves + '</td>';
    html += '<td>' + e.config.max_depth + '</td>';
    html += '<td>' + e.config.lambda_l1 + '/' + e.config.lambda_l2 + '</td>';
    html += '<td>' + e.metrics.ic.toFixed(3) + '</td>';
    html += '<td>' + e.metrics.icir.toFixed(3) + '</td>';
    html += '<td class="' + (e.metrics.directional_accuracy >= 0.7 ? 'text-green' : '') + '">' + (e.metrics.directional_accuracy * 100).toFixed(0) + '%</td>';
    html += '<td class="evo-notes">' + escapeHtml(e.notes || '') + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderFormulas(formulas) {
  var container = document.getElementById('formulas-container');
  if (!container) return;
  container.innerHTML = '';

  var keys = Object.keys(formulas);
  keys.forEach(function(key) {
    var f = formulas[key];
    var div = document.createElement('div');
    div.className = 'formula-card';
    div.innerHTML =
      '<div class="formula-name">' + escapeHtml(f.name) + '</div>' +
      '<div class="formula-math">' + escapeHtml(f.formula) + '</div>' +
      '<div class="formula-desc">' + escapeHtml(f.description) + '</div>';
    container.appendChild(div);
  });
}

/* ============================================================
   Backtest & Quality Visualization
   ============================================================ */

async function fetchBacktestResults() {
  try {
    var response = await fetch('/api/backtest');
    if (!response.ok) return null;
    var result = await response.json();
    return result.data;
  } catch (e) {
    return null;
  }
}

async function fetchQualityReport() {
  try {
    var response = await fetch('/api/quality');
    if (!response.ok) return null;
    var result = await response.json();
    return result.data;
  } catch (e) {
    return null;
  }
}

/* ============================================================
   TRADINGVIEW LIGHTWEIGHT CHARTS INTEGRATION
   Price chart + Volume + Future prediction overlay
   ============================================================ */

var _tvPriceChart = null;
var _tvVolChart = null;
var _tvPredChart = null;
var _tvCandleSeries = null;
var _tvVolSeries = null;
var _tvSma20Series = null;
var _tvSma50Series = null;
var _tvBBUpperSeries = null;
var _tvBBLowerSeries = null;
var _tvPredBaseSeries = null;
var _tvPredBullSeries = null;
var _tvPredBearSeries = null;
var _tvPredBandSeries = null;

// Color palette (dark terminal theme)
var TV_THEME = {
  bg: '#131722',
  bgSecondary: '#1e2738',
  grid: '#2a2e39',
  text: '#d1d5db',
  border: '#2a2e39',
  up: '#26a69a',
  down: '#ef5350',
  volume_up: 'rgba(38, 166, 154, 0.5)',
  volume_down: 'rgba(239, 83, 80, 0.5)',
  sma20: '#3b82f6',
  sma50: '#f59e0b',
  bb_upper: 'rgba(148, 163, 184, 0.6)',
  bb_lower: 'rgba(148, 163, 184, 0.6)',
  pred_base: '#8b5cf6',
  pred_bull: '#22c55e',
  pred_bear: '#ef4444',
  pred_band: 'rgba(139, 92, 246, 0.12)',
};

function destroyTVCharts() {
  if (_tvPriceChart) { try { _tvPriceChart.remove(); } catch(e) {} _tvPriceChart = null; }
  if (_tvVolChart) { try { _tvVolChart.remove(); } catch(e) {} _tvVolChart = null; }
  if (_tvPredChart) { try { _tvPredChart.remove(); } catch(e) {} _tvPredChart = null; }
  _tvCandleSeries = null;
  _tvVolSeries = null;
  _tvSma20Series = null;
  _tvSma50Series = null;
  _tvBBUpperSeries = null;
  _tvBBLowerSeries = null;
  _tvPredBaseSeries = null;
  _tvPredBullSeries = null;
  _tvPredBearSeries = null;
  _tvPredBandSeries = null;
}

function initTVChart(ohlcvData, ticker) {
  // ohlcvData: [{time, open, high, low, close, volume}]
  var priceEl = document.getElementById('tv-price-chart');
  var volEl = document.getElementById('tv-volume-chart');
  if (!priceEl || !volEl) return;

  destroyTVCharts();

  var chartOpts = {
    layout: { background: { color: TV_THEME.bg }, textColor: TV_THEME.text },
    grid: { vertLines: { color: TV_THEME.grid }, horzLines: { color: TV_THEME.grid } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: TV_THEME.border },
    timeScale: { borderColor: TV_THEME.border, timeVisible: true, secondsVisible: false },
    handleScroll: true,
    handleScale: true,
  };

  _tvPriceChart = LightweightCharts.createChart(priceEl, Object.assign({}, chartOpts, {
    width: priceEl.clientWidth,
    height: 480,
  }));

  _tvVolChart = LightweightCharts.createChart(volEl, Object.assign({}, chartOpts, {
    width: volEl.clientWidth,
    height: 120,
    rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0 } },
    timeScale: { visible: false },
  }));

  // Sync time scales
  _tvPriceChart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
    if (_tvVolChart && range) _tvVolChart.timeScale().setVisibleLogicalRange(range);
  });
  _tvVolChart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
    if (_tvPriceChart && range) _tvPriceChart.timeScale().setVisibleLogicalRange(range);
  });

  // Candlestick series
  _tvCandleSeries = _tvPriceChart.addCandlestickSeries({
    upColor: TV_THEME.up,
    downColor: TV_THEME.down,
    borderUpColor: TV_THEME.up,
    borderDownColor: TV_THEME.down,
    wickUpColor: TV_THEME.up,
    wickDownColor: TV_THEME.down,
  });
  _tvCandleSeries.setData(ohlcvData);

  // Volume series
  _tvVolSeries = _tvVolChart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  });
  _tvVolSeries.setData(ohlcvData.map(function(d) {
    return {
      time: d.time,
      value: d.volume,
      color: d.close >= d.open ? TV_THEME.volume_up : TV_THEME.volume_down,
    };
  }));

  // Compute and add indicators
  addTVIndicators(ohlcvData);

  // Fit content
  _tvPriceChart.timeScale().fitContent();
  _tvVolChart.timeScale().fitContent();

  // Handle window resize
  window.addEventListener('resize', function() {
    if (_tvPriceChart && priceEl) _tvPriceChart.applyOptions({ width: priceEl.clientWidth });
    if (_tvVolChart && volEl) _tvVolChart.applyOptions({ width: volEl.clientWidth });
  });
}

function addTVIndicators(data) {
  if (!_tvPriceChart || !data || data.length < 20) return;

  var closes = data.map(function(d) { return d.close; });
  var times = data.map(function(d) { return d.time; });

  // SMA 20
  var sma20 = [];
  for (var i = 19; i < closes.length; i++) {
    var sum20 = 0;
    for (var j = i - 19; j <= i; j++) sum20 += closes[j];
    sma20.push({ time: times[i], value: parseFloat((sum20 / 20).toFixed(2)) });
  }
  _tvSma20Series = _tvPriceChart.addLineSeries({
    color: TV_THEME.sma20,
    lineWidth: 1.5,
    title: 'SMA20',
    priceLineVisible: false,
  });
  _tvSma20Series.setData(sma20);

  // SMA 50
  if (data.length >= 50) {
    var sma50 = [];
    for (var i = 49; i < closes.length; i++) {
      var sum50 = 0;
      for (var j = i - 49; j <= i; j++) sum50 += closes[j];
      sma50.push({ time: times[i], value: parseFloat((sum50 / 50).toFixed(2)) });
    }
    _tvSma50Series = _tvPriceChart.addLineSeries({
      color: TV_THEME.sma50,
      lineWidth: 1.5,
      title: 'SMA50',
      priceLineVisible: false,
    });
    _tvSma50Series.setData(sma50);
  }

  // Bollinger Bands (20, 2)
  if (data.length >= 20) {
    var bbUpper = [];
    var bbLower = [];
    for (var i = 19; i < closes.length; i++) {
      var slice = closes.slice(i - 19, i + 1);
      var mean = slice.reduce(function(a, b) { return a + b; }, 0) / 20;
      var variance = slice.reduce(function(a, b) { return a + Math.pow(b - mean, 2); }, 0) / 20;
      var std = Math.sqrt(variance);
      bbUpper.push({ time: times[i], value: parseFloat((mean + 2 * std).toFixed(2)) });
      bbLower.push({ time: times[i], value: parseFloat((mean - 2 * std).toFixed(2)) });
    }
    _tvBBUpperSeries = _tvPriceChart.addLineSeries({
      color: TV_THEME.bb_upper,
      lineWidth: 1,
      lineStyle: 2,
      title: 'BB Upper',
      priceLineVisible: false,
    });
    _tvBBUpperSeries.setData(bbUpper);
    _tvBBLowerSeries = _tvPriceChart.addLineSeries({
      color: TV_THEME.bb_lower,
      lineWidth: 1,
      lineStyle: 2,
      title: 'BB Lower',
      priceLineVisible: false,
    });
    _tvBBLowerSeries.setData(bbLower);
  }
}

function initTVPredictionChart(predData, ticker) {
  // predData: {historical, prediction: {base, bull, bear}, levels}
  var predEl = document.getElementById('tv-prediction-chart');
  if (!predEl) return;

  if (_tvPredChart) { try { _tvPredChart.remove(); } catch(e) {} _tvPredChart = null; }

  _tvPredChart = LightweightCharts.createChart(predEl, {
    width: predEl.clientWidth,
    height: 360,
    layout: { background: { color: TV_THEME.bg }, textColor: TV_THEME.text },
    grid: { vertLines: { color: TV_THEME.grid }, horzLines: { color: TV_THEME.grid } },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: TV_THEME.border },
    timeScale: { borderColor: TV_THEME.border, timeVisible: true },
    handleScroll: true,
    handleScale: true,
  });

  // Historical price line (last 90 trading days)
  var histSlice = (predData.historical || []).slice(-90);
  if (histSlice.length > 0) {
    var histSeries = _tvPredChart.addLineSeries({
      color: '#d1d5db',
      lineWidth: 2,
      title: 'Historical',
      priceLineVisible: false,
    });
    histSeries.setData(histSlice.map(function(d) { return { time: d.time, value: d.close }; }));
  }

  var pred = predData.prediction || {};

  // Bear case (lower bound)
  if (pred.bear && pred.bear.length > 0) {
    _tvPredBearSeries = _tvPredChart.addLineSeries({
      color: TV_THEME.pred_bear,
      lineWidth: 1,
      lineStyle: 2,
      title: 'Bear Case',
      priceLineVisible: false,
    });
    _tvPredBearSeries.setData(pred.bear);
  }

  // Bull case (upper bound)
  if (pred.bull && pred.bull.length > 0) {
    _tvPredBullSeries = _tvPredChart.addLineSeries({
      color: TV_THEME.pred_bull,
      lineWidth: 1,
      lineStyle: 2,
      title: 'Bull Case',
      priceLineVisible: false,
    });
    _tvPredBullSeries.setData(pred.bull);
  }

  // Base prediction (prominent)
  if (pred.base && pred.base.length > 0) {
    _tvPredBaseSeries = _tvPredChart.addLineSeries({
      color: TV_THEME.pred_base,
      lineWidth: 2.5,
      title: 'Base Case',
      priceLineVisible: true,
    });
    _tvPredBaseSeries.setData(pred.base);
  }

  _tvPredChart.timeScale().fitContent();

  window.addEventListener('resize', function() {
    if (_tvPredChart && predEl) _tvPredChart.applyOptions({ width: predEl.clientWidth });
  });
}

function renderPredictionLevels(levels) {
  var el = document.getElementById('prediction-levels');
  if (!el || !levels) return;

  var items = [
    { label: 'Current Price', value: '$' + levels.current_price, change: null, color: '#d1d5db' },
    { label: 'Support', value: '$' + levels.support, change: null, color: '#f59e0b' },
    { label: 'Resistance', value: '$' + levels.resistance, change: null, color: '#f59e0b' },
    {
      label: '30-Day Target',
      value: '$' + levels.target_30d,
      change: (levels.change_30d_pct || 0),
      color: levels.change_30d_pct >= 0 ? '#22c55e' : '#ef4444',
    },
    {
      label: '60-Day Target',
      value: '$' + levels.target_60d,
      change: (levels.change_60d_pct || 0),
      color: levels.change_60d_pct >= 0 ? '#22c55e' : '#ef4444',
    },
    {
      label: '90-Day Target',
      value: '$' + levels.target_90d,
      change: (levels.change_90d_pct || 0),
      color: levels.change_90d_pct >= 0 ? '#22c55e' : '#ef4444',
    },
  ];

  el.innerHTML = items.map(function(item) {
    var changeStr = item.change != null
      ? '<div class="pred-level-change" style="color:' + item.color + '">' +
          (item.change >= 0 ? '+' : '') + item.change.toFixed(2) + '%' +
        '</div>'
      : '';
    return '<div class="pred-level-card">' +
      '<div class="pred-level-label">' + item.label + '</div>' +
      '<div class="pred-level-value" style="color:' + item.color + '">' + item.value + '</div>' +
      changeStr +
      '</div>';
  }).join('');
}

// Called when user clicks "AI Predict" button in charts tab
function loadTVPrediction(ticker) {
  var zone = document.getElementById('chart-prediction-zone');
  var tickerLabel = document.getElementById('prediction-zone-ticker');
  if (zone) zone.classList.remove('hidden');
  if (tickerLabel) tickerLabel.textContent = ticker;

  fetch('/api/predict-chart/' + encodeURIComponent(ticker))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      initTVPredictionChart(data, ticker);
      renderPredictionLevels(data.levels);
    })
    .catch(function(err) {
      console.error('Prediction load failed:', err);
    });
}
