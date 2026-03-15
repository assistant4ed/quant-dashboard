/**
 * Quant Stock Predictor Dashboard - Main Application Logic
 *
 * Tabbed dashboard with per-section timestamps and refresh.
 */

/* ============================================================
   Constants
   ============================================================ */
const DEFAULT_VISIBLE_COUNT = 10;
const MAX_VISIBLE_COUNT = 30;
const AUTO_REFRESH_INTERVAL_MS = 300000; /* 5 minutes */
const SIGNAL_BAR_MAX = 0.07;

/* ============================================================
   State
   ============================================================ */
let predictionData = null;
let activeView = 'consensus';
let isExpanded = false;
let autoRefreshTimer = null;
let isAutoRefreshEnabled = true;
let activeTab = 'overview';
let sectionTimestamps = {};

/* ============================================================
   DOM References
   ============================================================ */
let dom = {};

function cacheDom() {
  dom = {
    headerTitle: document.getElementById('header-title'),
    headerSubtitle: document.getElementById('header-subtitle'),
    langBtn: document.getElementById('lang-toggle'),
    refreshIndicator: document.getElementById('refresh-indicator'),
    refreshLabel: document.getElementById('refresh-label'),

    clockDate: document.getElementById('clock-date'),
    clockTime: document.getElementById('clock-time'),
    clockMarketStatus: document.getElementById('clock-market-status'),

    overviewSection: document.getElementById('overview-section'),
    overviewLabel: document.getElementById('overview-label'),
    cardStocks: document.getElementById('card-stocks'),
    cardStocksLabel: document.getElementById('card-stocks-label'),
    cardStocksValue: document.getElementById('card-stocks-value'),
    cardPositive: document.getElementById('card-positive'),
    cardPositiveLabel: document.getElementById('card-positive-label'),
    cardPositiveValue: document.getElementById('card-positive-value'),
    cardPositiveSub: document.getElementById('card-positive-sub'),
    cardSignal: document.getElementById('card-signal'),
    cardSignalLabel: document.getElementById('card-signal-label'),
    cardSignalValue: document.getElementById('card-signal-value'),
    cardSector: document.getElementById('card-sector'),
    cardSectorLabel: document.getElementById('card-sector-label'),
    cardSectorValue: document.getElementById('card-sector-value'),

    recsLabel: document.getElementById('recs-label'),
    toggleConsensus: document.getElementById('toggle-consensus'),
    toggleSingleday: document.getElementById('toggle-singleday'),
    stockGrid: document.getElementById('stock-grid'),
    showMoreContainer: document.getElementById('show-more-container'),
    showMoreBtn: document.getElementById('show-more-btn'),

    sectorLabel: document.getElementById('sector-label'),
    sectorChart: document.getElementById('sector-chart'),

    methodologyLabel: document.getElementById('methodology-label'),
    methodologyStepsLabel: document.getElementById('methodology-steps-label'),
    methodologySteps: document.getElementById('methodology-steps'),
    quantLabel: document.getElementById('quant-label'),
    quantSections: document.getElementById('quant-sections'),

    perfLabel: document.getElementById('perf-label'),
    metricsGrid: document.getElementById('metrics-grid'),
    periodInfo: document.getElementById('period-info'),

    disclaimerLabel: document.getElementById('disclaimer-label'),
    disclaimerText: document.getElementById('disclaimer-text'),
    footerPowered: document.getElementById('footer-powered'),

    growthLabel: document.getElementById('growth-label'),
    growthGrid: document.getElementById('growth-grid'),
    macroLabel: document.getElementById('macro-label'),
    macroGrid: document.getElementById('macro-grid'),
    newsLabel: document.getElementById('news-label'),
    newsFeed: document.getElementById('news-feed'),
    chartLabel: document.getElementById('chart-label'),

    altDataGrid: document.getElementById('alt-data-grid'),
    altDataTicker: document.getElementById('alt-data-ticker'),
    altDataLoadBtn: document.getElementById('alt-data-load-btn'),
    providersGrid: document.getElementById('providers-grid'),
  };
}

/* ============================================================
   Live Clock & Market Status
   ============================================================ */
function updateClock() {
  var now = new Date();
  var dateOpts = { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' };
  var timeOpts = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
  var lang = (typeof getLang === 'function' && getLang() === 'cn') ? 'zh-CN' : 'en-US';

  if (dom.clockDate) {
    dom.clockDate.textContent = now.toLocaleDateString(lang, dateOpts);
  }
  if (dom.clockTime) {
    dom.clockTime.textContent = now.toLocaleTimeString(lang, timeOpts);
  }
  if (dom.clockMarketStatus) {
    var status = getMarketStatus(now);
    dom.clockMarketStatus.textContent = status.label;
    dom.clockMarketStatus.className = 'clock-market-status ' + status.cssClass;
  }
}

function getMarketStatus(now) {
  var etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  var day = etNow.getDay();
  var hours = etNow.getHours();
  var minutes = etNow.getMinutes();
  var timeMinutes = hours * 60 + minutes;

  if (day === 0 || day === 6) {
    return { label: 'Market Closed (Weekend)', cssClass: 'market-closed' };
  }
  if (timeMinutes >= 570 && timeMinutes < 960) {
    return { label: 'Market Open', cssClass: 'market-open' };
  }
  if (timeMinutes >= 240 && timeMinutes < 570) {
    return { label: 'Pre-Market', cssClass: 'market-premarket' };
  }
  if (timeMinutes >= 960 && timeMinutes < 1200) {
    return { label: 'After-Hours', cssClass: 'market-afterhours' };
  }
  return { label: 'Market Closed', cssClass: 'market-closed' };
}

/* ============================================================
   Tab Navigation
   ============================================================ */
function initTabs() {
  var tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      switchTab(btn.getAttribute('data-tab'));
    });
  });
}

function switchTab(tabId) {
  activeTab = tabId;

  document.querySelectorAll('.tab-btn').forEach(function (btn) {
    var isActive = btn.getAttribute('data-tab') === tabId;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });

  document.querySelectorAll('.tab-panel').forEach(function (panel) {
    var isActive = panel.id === 'tab-' + tabId;
    panel.classList.toggle('active', isActive);
  });

  /* Trigger chart resize when switching to charts tab */
  if (tabId === 'charts' && typeof Chart !== 'undefined') {
    setTimeout(function () {
      Chart.helpers.each(Chart.instances, function (instance) {
        instance.resize();
      });
    }, 50);
  }
}

/* ============================================================
   Section Timestamps & Refresh
   ============================================================ */
function updateSectionTimestamp(sectionId) {
  var now = new Date();
  sectionTimestamps[sectionId] = now;
  var el = document.getElementById(sectionId + '-timestamp');
  if (el) {
    el.textContent = 'Updated: ' + formatTimestamp(now);
  }
}

function formatTimestamp(date) {
  var opts = {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  };
  return date.toLocaleString('en-US', opts);
}

function initSectionRefresh() {
  document.querySelectorAll('.btn-refresh').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = btn.getAttribute('data-refresh');
      btn.disabled = true;
      btn.textContent = 'Loading...';
      handleSectionRefresh(target).finally(function () {
        btn.disabled = false;
        btn.textContent = 'Refresh';
      });
    });
  });
}

async function handleSectionRefresh(target) {
  switch (target) {
    case 'overview':
    case 'predictions':
      await fetchPredictions();
      break;
    case 'sentiment':
      await fetchMarketSentiment();
      break;
    case 'macro':
      await fetchMacroData();
      break;
    case 'shortterm':
      await fetchShorttermData();
      break;
    case 'options':
      var optTicker = document.getElementById('options-ticker-input');
      if (optTicker && optTicker.value.trim()) {
        await loadOptionsChain(optTicker.value.trim().toUpperCase());
      }
      await fetchUnusualOptions();
      break;
    case 'calendar':
      await fetchEconomicCalendar();
      break;
    case 'overview-news':
      fetchOverviewNews();
      break;
  }
}

async function fetchMacroData() {
  try {
    var response = await fetch('/api/macro');
    if (!response.ok) return;
    var result = await response.json();
    if (result.data && dom.macroGrid) {
      renderMacroGrid(result.data);
      updateSectionTimestamp('macro');
    }
  } catch (err) {
    console.error('Failed to fetch macro data:', err);
  }
}

function renderMacroGrid(data) {
  if (!dom.macroGrid) return;
  var cards = Object.entries(data).map(function (entry) {
    var key = entry[0];
    var val = entry[1];
    var displayVal = typeof val === 'number' ? val.toFixed(2) : String(val || 'N/A');
    var label = key.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    return '<div class="macro-card">' +
      '<div class="macro-card-label">' + escapeHtml(label) + '</div>' +
      '<div class="macro-card-value">' + escapeHtml(displayVal) + '</div>' +
      '</div>';
  }).join('');
  dom.macroGrid.innerHTML = cards;
}

async function fetchShorttermData() {
  updateSectionTimestamp('shortterm');
}

/* ============================================================
   Data Fetching
   ============================================================ */
async function fetchPredictions() {
  try {
    var response = await fetch('/api/predictions');
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    var result = await response.json();
    predictionData = result.data;
    renderAll();
    updateSectionTimestamp('overview');
    updateSectionTimestamp('recs');
  } catch (err) {
    console.error('Failed to fetch predictions:', err);
    showError(t('error.fetch'));
  }
}

function showError(message) {
  if (dom.stockGrid) {
    dom.stockGrid.innerHTML =
      '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">' +
      escapeHtml(message) +
      '</div>';
  }
}

/* ============================================================
   Rendering: Full Page
   ============================================================ */
function renderAll() {
  if (!predictionData) return;

  renderLabels();
  renderOverview();
  renderStockGrid();
  renderSectorChart();
  renderMethodology();
  renderPerformance();
  renderFooter();
  if (typeof initCharts === 'function') initCharts();
}

/* ============================================================
   Rendering: Static Labels (i18n)
   ============================================================ */
function renderLabels() {
  if (dom.headerTitle) dom.headerTitle.textContent = t('app.title');
  if (dom.headerSubtitle) dom.headerSubtitle.textContent = t('app.subtitle');
  if (dom.langBtn) {
    dom.langBtn.textContent = getLang() === 'en' ? 'CN' : 'EN';
    dom.langBtn.setAttribute(
      'aria-label',
      getLang() === 'en' ? 'Switch to Chinese' : 'Switch to English',
    );
  }
  if (dom.refreshLabel) dom.refreshLabel.textContent = t('auto.refresh');

  if (dom.overviewLabel) dom.overviewLabel.textContent = t('market.overview');
  if (dom.recsLabel) dom.recsLabel.textContent = t('top.recommendations');
  if (dom.toggleConsensus) dom.toggleConsensus.textContent = t('view.consensus');
  if (dom.toggleSingleday) dom.toggleSingleday.textContent = t('view.singleday');
  if (dom.showMoreBtn) dom.showMoreBtn.textContent = isExpanded ? t('show.less') : t('show.more');
  if (dom.sectorLabel) dom.sectorLabel.textContent = t('sector.breakdown');
  if (dom.methodologyLabel) dom.methodologyLabel.textContent = t('methodology');
  if (dom.methodologyStepsLabel) dom.methodologyStepsLabel.textContent = t('methodology.steps');
  if (dom.quantLabel) dom.quantLabel.textContent = t('methodology.quant');
  if (dom.perfLabel) dom.perfLabel.textContent = t('model.performance');

  if (dom.chartLabel) dom.chartLabel.textContent = t('stock.analysis');
  if (dom.growthLabel) dom.growthLabel.textContent = t('growth.predictions');
  if (dom.macroLabel) dom.macroLabel.textContent = t('economic.signals');
  if (dom.newsLabel) dom.newsLabel.textContent = t('financial.news');
}

/* ============================================================
   Rendering: Overview Cards
   ============================================================ */
function renderOverview() {
  var overview = predictionData.market_overview;
  if (!overview) return;

  if (dom.cardStocksLabel) dom.cardStocksLabel.textContent = t('stocks.analyzed');
  if (dom.cardStocksValue) dom.cardStocksValue.textContent = overview.total_stocks;

  if (dom.cardPositiveLabel) dom.cardPositiveLabel.textContent = t('positive.signals');
  if (dom.cardPositiveValue) dom.cardPositiveValue.textContent =
    overview.positive_signal_count + ' / ' + overview.negative_signal_count;
  if (dom.cardPositiveSub) dom.cardPositiveSub.textContent = t('signal.ratio');

  if (dom.cardSignalLabel) dom.cardSignalLabel.textContent = t('avg.signal');
  if (dom.cardSignalValue) dom.cardSignalValue.textContent = formatSignal(overview.avg_signal);

  var topSectorKey = 'sector.' + overview.top_sector;
  if (dom.cardSectorLabel) dom.cardSectorLabel.textContent = t('top.sector');
  if (dom.cardSectorValue) dom.cardSectorValue.textContent = t(topSectorKey);
}

/* ============================================================
   Rendering: Stock Grid
   ============================================================ */
function renderStockGrid() {
  var el = document.getElementById('stock-grid');
  if (!el) return;

  var stocks = getActiveStocks();
  var visibleCount = isExpanded ? MAX_VISIBLE_COUNT : DEFAULT_VISIBLE_COUNT;
  var visible = stocks.slice(0, visibleCount);

  el.innerHTML = '';

  visible.forEach(function (stock, index) {
    var card = createStockCard(stock, index);
    el.appendChild(card);
  });

  var showMoreContainer = document.getElementById('show-more-container');
  var showMoreBtn = document.getElementById('show-more-btn');
  if (showMoreContainer && showMoreBtn) {
    if (stocks.length > DEFAULT_VISIBLE_COUNT) {
      showMoreContainer.classList.remove('hidden');
      showMoreBtn.textContent = isExpanded ? t('show.less') : t('show.more');
    } else {
      showMoreContainer.classList.add('hidden');
    }
  }
}

/* ============================================================
   LIVE MARKET BAR
   ============================================================ */

function fetchMarketLive() {
  fetch('/api/market-live')
    .then(function (r) { return r.json(); })
    .then(function (resp) {
      renderMarketLiveBar(resp.data || {});
    })
    .catch(function () {
      var el = document.getElementById('market-live-bar');
      if (el) el.innerHTML = '<span style="color:var(--text-muted);font-size:0.813rem;">Market data unavailable</span>';
    });
}

function renderMarketLiveBar(data) {
  var el = document.getElementById('market-live-bar');
  if (!el) return;

  var items = [
    { key: 'SP500',       label: 'S&P 500',   icon: '📈' },
    { key: 'NASDAQ',      label: 'NASDAQ',     icon: '💻' },
    { key: 'DOW',         label: 'DOW',        icon: '🏛' },
    { key: 'RUSSELL2000', label: 'RUT',        icon: '📊' },
    { key: 'VIX',         label: 'VIX',        icon: '⚡' },
    { key: 'GOLD',        label: 'Gold',       icon: '🥇' },
    { key: 'OIL',         label: 'Oil',        icon: '🛢' },
    { key: 'TREASURY10Y', label: '10Y Yield',  icon: '🏦' },
    { key: 'BTC',         label: 'Bitcoin',    icon: '₿' },
  ];

  var html = '<div class="market-live-grid">';
  items.forEach(function (item) {
    var d = data[item.key] || {};
    var price = d.price != null
      ? d.price.toLocaleString('en-US', { maximumFractionDigits: 2 })
      : '--';
    var chg = d.change_pct != null
      ? (d.change_pct >= 0 ? '+' : '') + d.change_pct.toFixed(2) + '%'
      : '--';
    var dir = d.direction || (d.change_pct != null && d.change_pct >= 0 ? 'up' : 'down');
    var color = dir === 'up' ? 'var(--accent-green)' : 'var(--accent-red)';
    var arrow = dir === 'up' ? '▲' : '▼';
    var dirClass = dir === 'up' ? 'market-live-card--up' : 'market-live-card--down';
    html +=
      '<div class="market-live-card ' + dirClass + '">' +
        '<div class="market-live-header">' +
          '<span class="market-live-icon">' + item.icon + '</span>' +
          '<span class="market-live-label">' + item.label + '</span>' +
        '</div>' +
        '<div class="market-live-price">' + price + '</div>' +
        '<div class="market-live-change" style="color:' + color + '">' + arrow + ' ' + chg + '</div>' +
        '<div class="market-live-source">' + escapeHtml(d.source || 'Yahoo Finance') + '</div>' +
      '</div>';
  });
  html += '</div>';

  var ts = document.getElementById('overview-timestamp');
  if (ts) ts.textContent = 'Updated: ' + new Date().toLocaleTimeString();
  el.innerHTML = html;
}

/* ============================================================
   OVERVIEW NEWS (7-DAY FILTER)
   ============================================================ */

function fetchOverviewNews() {
  fetch('/api/news')
    .then(function (r) { return r.json(); })
    .then(function (resp) {
      var articles = (resp.data || {}).articles || [];
      renderOverviewNews(articles);
      var ts = document.getElementById('overview-news-timestamp');
      if (ts) ts.textContent = 'Updated: ' + new Date().toLocaleTimeString();
    })
    .catch(function () {});
}

function renderOverviewNews(articles) {
  var el = document.getElementById('overview-news-grid');
  if (!el) return;
  if (!articles || !articles.length) {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:0.875rem;">No recent news available.</p>';
    return;
  }

  var html = '';
  articles.slice(0, 12).forEach(function (a) {
    var title = escapeHtml(a.title || 'No title');
    var summary = escapeHtml((a.summary || '').substring(0, 200));
    var source = escapeHtml(a.source || '');
    var url = a.url || '#';
    var pubDate = '';
    if (a.publishedAt) {
      try {
        var d = new Date(a.publishedAt);
        pubDate = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      } catch (e) {}
    }
    var sentimentDot = '';
    if (a.sentiment === 'positive') {
      sentimentDot = '<span class="news-sentiment-dot news-sentiment-dot--positive" title="Positive sentiment" aria-label="Positive sentiment"></span>';
    } else if (a.sentiment === 'negative') {
      sentimentDot = '<span class="news-sentiment-dot news-sentiment-dot--negative" title="Negative sentiment" aria-label="Negative sentiment"></span>';
    } else if (a.sentiment === 'neutral') {
      sentimentDot = '<span class="news-sentiment-dot news-sentiment-dot--neutral" title="Neutral sentiment" aria-label="Neutral sentiment"></span>';
    }
    html +=
      '<a class="overview-news-card" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
        '<div class="overview-news-meta">' +
          '<span class="overview-news-source">' + source + '</span>' +
          sentimentDot +
          '<span class="overview-news-date">' + pubDate + '</span>' +
        '</div>' +
        '<div class="overview-news-title">' + title + '</div>' +
        (summary ? '<div class="overview-news-summary">' + summary + '...</div>' : '') +
      '</a>';
  });
  el.innerHTML = html;
}

function fetchMarketNewsFeed() {
  var feed = document.getElementById('news-feed');
  if (!feed) return;
  fetch('/api/news')
    .then(function (r) { return r.json(); })
    .then(function (resp) {
      var articles = (resp.data || {}).articles || [];
      if (!articles.length) {
        feed.innerHTML = '<p style="color:var(--text-muted);font-size:0.875rem;">No recent news available.</p>';
        return;
      }
      var html = '';
      articles.slice(0, 20).forEach(function (a) {
        var title = escapeHtml(a.title || 'No title');
        var summary = escapeHtml((a.summary || '').substring(0, 180));
        var source = escapeHtml(a.source || '');
        var url = a.url || '#';
        var pubDate = '';
        if (a.publishedAt) {
          try {
            var d = new Date(a.publishedAt);
            pubDate = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
          } catch (e) {}
        }
        html +=
          '<a class="overview-news-card" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer" style="display:block;margin-bottom:0.75rem;">' +
            '<div class="overview-news-meta">' +
              '<span class="overview-news-source">' + source + '</span>' +
              '<span class="overview-news-date">' + pubDate + '</span>' +
            '</div>' +
            '<div class="overview-news-title">' + title + '</div>' +
            (summary ? '<div class="overview-news-summary">' + summary + '...</div>' : '') +
          '</a>';
      });
      feed.innerHTML = html;
      updateSectionTimestamp('news');
    })
    .catch(function () {
      feed.innerHTML = '<p style="color:var(--text-muted);font-size:0.875rem;">Failed to load news.</p>';
    });
}

function getActiveStocks() {
  if (activeView === 'singleday') {
    return predictionData.single_day_top || [];
  }
  return predictionData.top_stocks || [];
}

function createStockCard(stock, index) {
  var card = document.createElement('div');
  card.className = 'stock-card';
  card.style.animationDelay = (index * 0.05) + 's';

  var rank = stock.rank;
  if (rank === 1) card.className += ' stock-card--rank-1';
  if (rank === 2) card.className += ' stock-card--rank-2';
  if (rank === 3) card.className += ' stock-card--rank-3';

  var rankClass = 'stock-card-rank';
  if (rank === 1) rankClass += ' stock-card-rank--gold';
  else if (rank === 2) rankClass += ' stock-card-rank--silver';
  else if (rank === 3) rankClass += ' stock-card-rank--bronze';

  var isPositive = stock.signal >= 0;
  var signalPercent = Math.min(Math.abs(stock.signal) / SIGNAL_BAR_MAX * 100, 100);
  var signalClass = isPositive ? 'signal-bar-fill--positive' : 'signal-bar-fill--negative';
  var signalValueClass = isPositive ? 'signal-label-value--positive' : 'signal-label-value--negative';

  var trendHtml = '';
  if (stock.trend) {
    var isUp = stock.trend === 'up';
    var trendIcon = isUp ? '&#9650;' : '&#9660;';
    var trendClass = isUp ? 'stock-card-trend--up' : 'stock-card-trend--down';
    var trendLabel = isUp ? t('trend.up') : t('trend.down');
    trendHtml =
      '<span class="stock-card-trend ' + trendClass + '" aria-label="' + trendLabel + '" title="' + trendLabel + '">' +
      trendIcon +
      '</span>';
  }

  var displayName = tName(stock.name, stock.name_cn);

  var html = '';

  html += '<div class="stock-card-header">';
  html += '<span class="' + rankClass + '" aria-label="' + t('rank') + ' ' + rank + '">' + rank + '</span>';
  html += '<div class="stock-card-identity">';
  html += '<div class="stock-card-ticker">' + escapeHtml(stock.ticker) + '</div>';
  html += '<div class="stock-card-name" title="' + escapeHtml(displayName) + '">' + escapeHtml(displayName) + '</div>';
  html += '</div>';
  html += trendHtml;
  html += '</div>';

  html += '<div class="signal-row">';
  html += '<div class="signal-label">';
  html += '<span class="signal-label-text">' + t('signal.strength') + '</span>';
  html += '<span class="signal-label-value ' + signalValueClass + '">' + formatSignal(stock.signal) + '</span>';
  html += '</div>';
  html += '<div class="signal-bar" role="progressbar" aria-valuenow="' + signalPercent.toFixed(0) + '" aria-valuemin="0" aria-valuemax="100" aria-label="' + t('signal.strength') + '">';
  html += '<div class="signal-bar-fill ' + signalClass + '" style="width:' + signalPercent + '%"></div>';
  html += '</div>';
  html += '</div>';

  if (stock.consistency !== undefined) {
    var consistPercent = (stock.consistency * 100).toFixed(0);
    html += '<div class="consistency-row">';
    html += '<div class="signal-label">';
    html += '<span class="signal-label-text">' + t('consistency') + '</span>';
    html += '<span class="signal-label-value" style="color:var(--accent-blue);">' + consistPercent + '%</span>';
    html += '</div>';
    html += '<div class="signal-bar" role="progressbar" aria-valuenow="' + consistPercent + '" aria-valuemin="0" aria-valuemax="100" aria-label="' + t('consistency') + '">';
    html += '<div class="consistency-bar-fill" style="width:' + consistPercent + '%"></div>';
    html += '</div>';
    html += '</div>';
  }

  html += '<div class="stock-card-footer">';
  if (stock.combined_score !== undefined) {
    html += '<div class="combined-score">';
    html += '<span class="combined-score-label">' + t('combined.score') + '</span>';
    html += '<span class="combined-score-value">' + stock.combined_score.toFixed(4) + '</span>';
    html += '</div>';
  } else {
    html += '<div></div>';
  }
  if (stock.sector) {
    html += '<span class="sector-tag">' + escapeHtml(tSector(stock.sector, stock.sector_cn)) + '</span>';
  }
  html += '</div>';

  card.innerHTML = html;

  card.style.cursor = 'pointer';
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  card.addEventListener('click', function () {
    openStockModal(stock);
  });
  card.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openStockModal(stock);
    }
  });

  return card;
}

/* ============================================================
   Rendering: Sector Breakdown
   ============================================================ */
function renderSectorChart() {
  var sectors = predictionData.sector_breakdown;
  if (!sectors || sectors.length === 0 || !dom.sectorChart) return;

  var maxSignal = 0;
  sectors.forEach(function (s) {
    if (s.avg_signal > maxSignal) maxSignal = s.avg_signal;
  });

  var sorted = sectors.slice().sort(function (a, b) {
    return b.avg_signal - a.avg_signal;
  });

  dom.sectorChart.innerHTML = '';

  sorted.forEach(function (sector) {
    var barPercent = maxSignal > 0 ? (sector.avg_signal / maxSignal * 100) : 0;
    var sectorName = tSector(sector.sector, sector.sector_cn);

    var row = document.createElement('div');
    row.className = 'sector-row';

    row.innerHTML =
      '<div class="sector-name" title="' + escapeHtml(sectorName) + '">' + escapeHtml(sectorName) + '</div>' +
      '<div class="sector-bar-container">' +
      '<div class="sector-bar-fill" style="width:' + barPercent + '%">' +
      '<span class="sector-bar-label">' + formatSignal(sector.avg_signal) + '</span>' +
      '</div>' +
      '</div>' +
      '<div class="sector-count">' + sector.count + ' ' + t('sector.stocks') + '</div>';

    dom.sectorChart.appendChild(row);
  });
}

/* ============================================================
   Rendering: Methodology
   ============================================================ */
function renderMethodology() {
  var methodology = predictionData.methodology || {};

  dom.methodologySteps.innerHTML = '';
  var steps = methodology.steps || [];
  steps.forEach(function (step, idx) {
    var title = tName(step.title, step.title_cn);
    var desc = tName(step.desc, step.desc_cn);
    var item = createAccordionItem(
      String(idx + 1),
      title,
      desc,
      'step',
    );
    dom.methodologySteps.appendChild(item);
  });

  dom.quantSections.innerHTML = '';
  var quantIcons = [
    '\u{1F4BE}', '\u{1F4CA}', '\u{1F916}', '\u{1F6E1}', '\u26A1',
    '\u{1F50D}', '\u{1F527}', '\u{1F4C8}',
  ];
  var sections = (methodology.quant_fund_approach || {}).sections || [];
  sections.forEach(function (section, idx) {
    var heading = tName(section.heading, section.heading_cn);
    var content = tName(section.content, section.content_cn);
    var icon = quantIcons[idx] || '\u{1F4CB}';
    var item = createAccordionItem(icon, heading, content, 'section');
    dom.quantSections.appendChild(item);
  });
}

function createAccordionItem(badge, title, content, type) {
  var item = document.createElement('div');
  item.className = 'accordion-item';

  var badgeClass = type === 'step' ? 'accordion-step-num' : 'accordion-section-icon';

  item.innerHTML =
    '<button class="accordion-trigger" aria-expanded="false">' +
    '<span class="' + badgeClass + '">' + badge + '</span>' +
    '<span>' + escapeHtml(title) + '</span>' +
    '<span class="accordion-chevron" aria-hidden="true">&#9660;</span>' +
    '</button>' +
    '<div class="accordion-content" role="region">' +
    '<div class="accordion-content-inner">' + escapeHtml(content) + '</div>' +
    '</div>';

  var trigger = item.querySelector('.accordion-trigger');
  trigger.addEventListener('click', function () {
    var isOpen = item.classList.contains('open');
    item.classList.toggle('open');
    trigger.setAttribute('aria-expanded', String(!isOpen));
  });

  return item;
}

/* ============================================================
   Rendering: Model Performance
   ============================================================ */
function renderPerformance() {
  var info = predictionData.model_info;
  if (!info) return;

  var metrics = info.metrics || {};

  dom.metricsGrid.innerHTML = '';
  var metricEntries = [
    { key: 'metric.ic', value: metrics.ic },
    { key: 'metric.icir', value: metrics.icir },
    { key: 'metric.rankic', value: metrics.rank_ic },
    { key: 'metric.rankicir', value: metrics.rank_icir },
  ];

  metricEntries.forEach(function (entry) {
    var card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML =
      '<div class="metric-label">' + t(entry.key) + '</div>' +
      '<div class="metric-value">' + (entry.value !== undefined ? entry.value.toFixed(6) : 'N/A') + '</div>';
    dom.metricsGrid.appendChild(card);
  });

  dom.periodInfo.innerHTML = '';
  var periods = [
    { key: 'period.train', value: info.train_period },
    { key: 'period.valid', value: info.valid_period },
    { key: 'period.test', value: info.test_period },
  ];

  periods.forEach(function (period) {
    var card = document.createElement('div');
    card.className = 'period-card';
    var rangeStr = Array.isArray(period.value)
      ? period.value[0] + ' ~ ' + period.value[1]
      : String(period.value);
    card.innerHTML =
      '<div class="period-label">' + t(period.key) + '</div>' +
      '<div class="period-value">' + escapeHtml(rangeStr) + '</div>';
    dom.periodInfo.appendChild(card);
  });
}

/* ============================================================
   Rendering: Footer
   ============================================================ */
function renderFooter() {
  dom.disclaimerLabel.textContent = t('disclaimer');
  dom.disclaimerText.textContent = t('disclaimer.text');
  dom.footerPowered.innerHTML = escapeHtml(t('footer.powered'));
}

/* ============================================================
   Event Handlers
   ============================================================ */
function handleViewToggle(view) {
  if (view === activeView) return;
  activeView = view;
  isExpanded = false;

  dom.toggleConsensus.classList.toggle('active', view === 'consensus');
  dom.toggleSingleday.classList.toggle('active', view === 'singleday');

  renderStockGrid();
}

function handleShowMore() {
  isExpanded = !isExpanded;
  renderStockGrid();
}

function handleLangToggle() {
  toggleLanguage();
}

/* ============================================================
   Auto-Refresh
   ============================================================ */
function startAutoRefresh() {
  stopAutoRefresh();
  if (!isAutoRefreshEnabled) return;
  autoRefreshTimer = setInterval(function () {
    fetchPredictions();
    fetchMarketSentiment();
    fetchMarketLive();
    fetchOverviewNews();
  }, AUTO_REFRESH_INTERVAL_MS);
  updateRefreshIndicator();
}

function stopAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

function updateRefreshIndicator() {
  var dot = dom.refreshIndicator.querySelector('.refresh-dot');
  if (isAutoRefreshEnabled) {
    dot.classList.remove('refresh-dot--paused');
  } else {
    dot.classList.add('refresh-dot--paused');
  }
}

/* ============================================================
   Language Change Callback
   ============================================================ */
window.onLanguageChange = function () {
  if (predictionData) {
    renderAll();
  }
};

/* ============================================================
   Utility Functions
   ============================================================ */
function formatSignal(value) {
  if (value === null || value === undefined) return 'N/A';
  var percent = (value * 100).toFixed(2);
  var prefix = value >= 0 ? '+' : '';
  return prefix + percent + '%';
}

function escapeHtml(text) {
  if (!text) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

/* ============================================================
   AI Analysis (Claude Opus 4.6)
   ============================================================ */
function initAiAnalysis() {
  var select = document.getElementById('ai-ticker-select');
  var input = document.getElementById('ai-ticker-input');
  var analyzeBtn = document.getElementById('ai-analyze-btn');
  var quickBtn = document.getElementById('ai-quick-btn');
  if (!analyzeBtn) return;

  function getSelectedTicker() {
    var custom = input.value.trim().toUpperCase();
    if (custom) return custom;
    return select ? select.value : '';
  }

  analyzeBtn.addEventListener('click', function() {
    var ticker = getSelectedTicker();
    if (ticker) runAiAnalysis(ticker, false);
  });

  quickBtn.addEventListener('click', function() {
    var ticker = getSelectedTicker();
    if (ticker) runAiAnalysis(ticker, true);
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var ticker = getSelectedTicker();
      if (ticker) runAiAnalysis(ticker, false);
    }
  });

  /* When dropdown changes, clear custom input */
  if (select) {
    select.addEventListener('change', function() {
      input.value = '';
    });
  }
  /* When custom input is typed, deselect dropdown */
  input.addEventListener('input', function() {
    if (select && input.value.trim()) select.value = '';
  });
}

async function runAiAnalysis(ticker, isQuick) {
  var loading = document.getElementById('ai-loading');
  var results = document.getElementById('ai-results');
  var analyzeBtn = document.getElementById('ai-analyze-btn');
  var quickBtn = document.getElementById('ai-quick-btn');

  loading.classList.remove('hidden');
  results.classList.add('hidden');
  analyzeBtn.disabled = true;
  quickBtn.disabled = true;

  var endpoint = isQuick
    ? '/api/ai-quick/' + ticker
    : '/api/ai-analyze/' + ticker;

  try {
    var response = await fetch(endpoint, { method: 'POST' });
    var result = await response.json();

    loading.classList.add('hidden');
    analyzeBtn.disabled = false;
    quickBtn.disabled = false;

    if (result.error) {
      results.classList.remove('hidden');
      results.innerHTML = '<div class="ai-error">' + escapeHtml(result.error.message || 'Analysis failed') + '</div>';
      return;
    }

    updateSectionTimestamp('ai');

    if (isQuick) {
      renderQuickAnalysis(result.data);
    } else {
      renderFullAnalysis(result.data);
    }
  } catch (err) {
    loading.classList.add('hidden');
    analyzeBtn.disabled = false;
    quickBtn.disabled = false;
    results.classList.remove('hidden');
    results.innerHTML = '<div class="ai-error">Failed to connect to AI service: ' + escapeHtml(err.message) + '</div>';
  }
}

function renderQuickAnalysis(data) {
  var results = document.getElementById('ai-results');
  results.classList.remove('hidden');
  var analyzedTime = data.analyzed_at ? formatTimestamp(new Date(data.analyzed_at)) : '';
  results.innerHTML =
    '<div class="ai-quick-result">' +
    '<h3>' + escapeHtml(data.ticker) + ' - Quick Analysis</h3>' +
    '<p>' + escapeHtml(data.quick_analysis || data.error || 'No analysis available') + '</p>' +
    '<small>Model: ' + escapeHtml(data.model || 'Claude Opus 4.6') + ' | Analyzed: ' + escapeHtml(analyzedTime) + '</small>' +
    '</div>';
}

function renderFullAnalysis(data) {
  var results = document.getElementById('ai-results');
  results.classList.remove('hidden');

  /* 1. Header with rating badge and confidence */
  var ratingClass = getRatingClass(data.rating);
  var headerRow = document.getElementById('ai-header-row');
  var ratingEmoji = {'STRONG_BUY': '\uD83D\uDFE2\uD83D\uDFE2', 'BUY': '\uD83D\uDFE2', 'HOLD': '\uD83D\uDFE1', 'SELL': '\uD83D\uDD34', 'STRONG_SELL': '\uD83D\uDD34\uD83D\uDD34'}[data.rating] || '\u26AA';
  headerRow.innerHTML =
    '<div class="ai-report-header">' +
    '<div class="ai-rating-section">' +
    '<div class="ai-rating-badge-lg ' + ratingClass + '">' + escapeHtml(data.rating || 'N/A') + '</div>' +
    '<div class="ai-conf-section">' +
    '<div class="ai-conf-bar-track"><div class="ai-conf-bar-fill" style="width:' + ((data.confidence || 0) * 10) + '%"></div></div>' +
    '<span class="ai-conf-text">Confidence: <span class="hl-number">' + (data.confidence || 'N/A') + '/10</span></span>' +
    '</div>' +
    '</div>' +
    '<div class="ai-summary-block">' +
    '<h3>Executive Summary</h3>' +
    '<p>' + highlightText(data.summary || '') + '</p>' +
    '</div>' +
    '</div>';

  /* 2. Score cards with visual bars */
  var scoresGrid = document.getElementById('ai-scores-grid');
  var scores = [
    { label: 'Fundamental', value: data.fundamental_score, color: '#3b82f6', icon: '\uD83D\uDCCA' },
    { label: 'Technical', value: data.technical_score, color: '#8b5cf6', icon: '\uD83D\uDCC8' },
    { label: 'Sentiment', value: data.sentiment_score, color: '#f59e0b', icon: '\uD83C\uDFAF' },
    { label: 'Risk', value: data.risk_score, color: '#ef4444', icon: '\u26A0\uFE0F' },
  ];
  scoresGrid.innerHTML = scores.map(function(s) {
    var pct = ((s.value || 0) / 10 * 100);
    var valClass = s.label === 'Risk' ? (s.value >= 7 ? 'hl-red' : s.value >= 4 ? 'hl-blue' : 'hl-green') : (s.value >= 7 ? 'hl-green' : s.value >= 4 ? 'hl-blue' : 'hl-red');
    return '<div class="ai-score-card-v2">' +
      '<div class="ai-score-top"><span>' + s.icon + ' ' + s.label + '</span><span class="' + valClass + ' ai-score-num">' + (s.value || 'N/A') + '/10</span></div>' +
      '<div class="ai-score-bar"><div class="ai-score-fill" style="width:' + pct + '%;background:' + s.color + '"></div></div>' +
      '</div>';
  }).join('');

  /* 3. Price Targets */
  var targets = data.price_targets || {};
  var priceTargets = document.getElementById('ai-price-targets');
  priceTargets.innerHTML =
    '<div class="ai-report-section">' +
    '<h3>Price Targets <span class="ai-timeframe">(' + escapeHtml(targets.timeframe || '6 months') + ')</span></h3>' +
    '<div class="ai-targets-row">' +
    '<div class="ai-target ai-target--bear"><div class="ai-target-label">Bear Case</div><div class="ai-target-price hl-red">$' + (targets.bear_case || 'N/A') + '</div></div>' +
    '<div class="ai-target ai-target--base"><div class="ai-target-label">Base Case</div><div class="ai-target-price hl-blue">$' + (targets.base_case || 'N/A') + '</div></div>' +
    '<div class="ai-target ai-target--bull"><div class="ai-target-label">Bull Case</div><div class="ai-target-price hl-green">$' + (targets.bull_case || 'N/A') + '</div></div>' +
    '</div>' +
    '</div>';

  /* 4. Catalysts & Risks with highlighting */
  var catalystsRisks = document.getElementById('ai-catalysts-risks');
  var catalysts = (data.key_catalysts || []).map(function(c) {
    return '<li>' + highlightText(c) + '</li>';
  }).join('');
  var risks = (data.key_risks || []).map(function(r) {
    return '<li>' + highlightText(r) + '</li>';
  }).join('');
  catalystsRisks.innerHTML =
    '<div class="ai-report-section">' +
    '<h3>Catalysts & Risks</h3>' +
    '<div class="ai-cat-risk-grid">' +
    '<div class="ai-catalysts"><h4>Key Catalysts</h4><ul>' + (catalysts || '<li>N/A</li>') + '</ul></div>' +
    '<div class="ai-risks"><h4>Key Risks</h4><ul>' + (risks || '<li>N/A</li>') + '</ul></div>' +
    '</div>' +
    '</div>';

  /* 5. Strategy with highlighting */
  var strategy = document.getElementById('ai-strategy');
  strategy.innerHTML =
    '<div class="ai-report-section">' +
    '<h3>Trading Strategy</h3>' +
    '<div class="ai-strategy-grid">' +
    '<div class="ai-strat-item"><h4>Entry Strategy</h4><p>' + highlightText(data.entry_strategy || 'N/A') + '</p></div>' +
    '<div class="ai-strat-item"><h4>Exit Strategy</h4><p>' + highlightText(data.exit_strategy || 'N/A') + '</p></div>' +
    '<div class="ai-strat-item"><h4>Position Sizing</h4><p>' + highlightText(data.position_sizing || 'N/A') + '</p></div>' +
    '<div class="ai-strat-item"><h4>Sector Outlook</h4><p>' + highlightText(data.sector_outlook || 'N/A') + '</p></div>' +
    '</div>' +
    '</div>';

  /* 5.5 Growth Assessment (LightGBM model + historical data) */
  var growth = data.growth_assessment || {};
  var growthEl = document.getElementById('ai-growth');
  if (growth && Object.keys(growth).length > 0) {
    growthEl.innerHTML =
      '<div class="ai-report-section ai-growth-section">' +
      '<h3>Growth Assessment & Model Signal</h3>' +
      '<div class="ai-growth-grid">' +
      '<div class="ai-growth-item"><h4>Historical Revenue Growth</h4><p>' + highlightText(growth.historical_revenue_growth || 'N/A') + '</p></div>' +
      '<div class="ai-growth-item"><h4>Historical Earnings Growth</h4><p>' + highlightText(growth.historical_earnings_growth || 'N/A') + '</p></div>' +
      '<div class="ai-growth-item ai-growth-predicted"><h4>Predicted Growth (12m)</h4><p>' + highlightText(growth.predicted_growth_next_12m || 'N/A') + '</p></div>' +
      '<div class="ai-growth-item ai-growth-model"><h4>LightGBM Model Signal</h4><p>' + highlightText(growth.model_signal_interpretation || 'N/A') + '</p></div>' +
      '</div>' +
      '<div class="ai-growth-rationale"><h4>Growth Rationale</h4><p>' + highlightText(growth.growth_rationale || 'N/A') + '</p></div>' +
      '</div>';
  } else {
    growthEl.innerHTML = '';
  }

  /* 6. Detailed Analysis (the rationale) with full highlighting */
  var detailed = data.detailed_analysis || {};
  var detailedEl = document.getElementById('ai-detailed');
  var sections = [
    { title: 'Fundamental Rationale', key: 'fundamentals', icon: '\uD83D\uDCCA' },
    { title: 'Technical Setup', key: 'technicals', icon: '\uD83D\uDCC8' },
    { title: 'Macro Impact', key: 'macro_impact', icon: '\uD83C\uDF0D' },
    { title: 'Smart Money Activity', key: 'insider_institutional', icon: '\uD83C\uDFE6' },
  ];
  var detailHtml = '<div class="ai-report-section"><h3>Detailed Rationale</h3><div class="ai-rationale-grid">';
  sections.forEach(function(sec) {
    var content = detailed[sec.key] || 'N/A';
    detailHtml += '<div class="ai-rationale-block">' +
      '<h4>' + sec.icon + ' ' + sec.title + '</h4>' +
      '<p>' + highlightText(content) + '</p>' +
      '</div>';
  });
  detailHtml += '</div></div>';

  /* Meta info */
  var analyzedTime = data.analyzed_at ? formatTimestamp(new Date(data.analyzed_at)) : '';
  detailHtml += '<div class="ai-meta">' +
    '<span>Model: ' + escapeHtml(data.model || 'Claude Opus 4.6') + '</span>' +
    '<span>Tokens: ' + ((data.tokens_used || {}).input || 0) + ' in / ' + ((data.tokens_used || {}).output || 0) + ' out</span>' +
    '<span>Analyzed: ' + escapeHtml(analyzedTime) + '</span>' +
    '</div>';

  detailedEl.innerHTML = detailHtml;
}

function getRatingClass(rating) {
  var r = (rating || '').toUpperCase();
  if (r === 'STRONG_BUY') return 'ai-rating--strong-buy';
  if (r === 'BUY') return 'ai-rating--buy';
  if (r === 'HOLD') return 'ai-rating--hold';
  if (r === 'SELL') return 'ai-rating--sell';
  if (r === 'STRONG_SELL') return 'ai-rating--strong-sell';
  return 'ai-rating--hold';
}

/* ============================================================
   Market Sentiment
   ============================================================ */
async function fetchMarketSentiment() {
  try {
    var response = await fetch('/api/market-sentiment');
    if (!response.ok) return;
    var result = await response.json();
    renderSentiment(result.data);
    updateSectionTimestamp('sentiment');
  } catch (err) {
    console.error('Failed to fetch sentiment:', err);
  }
}

function renderSentiment(data) {
  var grid = document.getElementById('sentiment-grid');
  if (!grid || !data) return;

  var cards = [];

  if (data.fear_greed_score !== undefined) {
    var fgColor = data.fear_greed_score < 40 ? '#ef4444' : data.fear_greed_score > 60 ? '#22c55e' : '#f59e0b';
    cards.push(
      '<div class="sentiment-card">' +
      '<div class="sentiment-card-label">Fear & Greed Index</div>' +
      '<div class="sentiment-card-value" style="color:' + fgColor + '">' + data.fear_greed_score + '</div>' +
      '<div class="sentiment-card-sub">' + escapeHtml(data.fear_greed_label || '') + '</div>' +
      '</div>'
    );
  }

  if (data.vix !== undefined) {
    var vixColor = data.vix > 25 ? '#ef4444' : data.vix > 18 ? '#f59e0b' : '#22c55e';
    cards.push(
      '<div class="sentiment-card">' +
      '<div class="sentiment-card-label">VIX (Volatility)</div>' +
      '<div class="sentiment-card-value" style="color:' + vixColor + '">' + data.vix + '</div>' +
      '<div class="sentiment-card-sub">' + escapeHtml(data.vix_regime || '') + '</div>' +
      '</div>'
    );
  }

  var indices = [
    { key: 'sp500', label: 'S&P 500' },
    { key: 'nasdaq', label: 'NASDAQ' },
    { key: 'dow', label: 'DOW' },
    { key: 'russell2000', label: 'Russell 2000' },
  ];
  indices.forEach(function (idx) {
    var price = data[idx.key + '_price'];
    var change = data[idx.key + '_change_pct'];
    if (price) {
      var clr = change >= 0 ? '#22c55e' : '#ef4444';
      var arrow = change >= 0 ? '&#9650;' : '&#9660;';
      cards.push(
        '<div class="sentiment-card">' +
        '<div class="sentiment-card-label">' + idx.label + '</div>' +
        '<div class="sentiment-card-value">' + price.toLocaleString() + '</div>' +
        '<div class="sentiment-card-sub" style="color:' + clr + '">' + arrow + ' ' + (change || 0).toFixed(2) + '%</div>' +
        '</div>'
      );
    }
  });

  if (data.gold_price) {
    cards.push(
      '<div class="sentiment-card">' +
      '<div class="sentiment-card-label">Gold</div>' +
      '<div class="sentiment-card-value">$' + data.gold_price.toLocaleString() + '</div>' +
      '</div>'
    );
  }

  grid.innerHTML = cards.join('');

  var rotationGrid = document.getElementById('sector-rotation-grid');
  var rotation = data.sector_rotation || {};
  var sectors = Object.entries(rotation).sort(function (a, b) {
    return (b[1].month_return || 0) - (a[1].month_return || 0);
  });

  if (sectors.length > 0) {
    var rotHtml = '<h4 style="margin:16px 0 8px;color:var(--text-secondary);font-size:0.875rem;">Sector Rotation (30d)</h4>';
    rotHtml += '<div class="rotation-bars">';
    sectors.forEach(function (entry) {
      var name = entry[0].replace(/_/g, ' ');
      var ret = entry[1].month_return || 0;
      var barClr = ret >= 0 ? '#22c55e' : '#ef4444';
      var barW = Math.min(Math.abs(ret) * 8, 100);
      rotHtml += '<div class="rotation-row">' +
        '<span class="rotation-name">' + name + '</span>' +
        '<div class="rotation-bar-track">' +
        '<div class="rotation-bar-fill" style="width:' + barW + '%;background:' + barClr + '"></div>' +
        '</div>' +
        '<span class="rotation-val" style="color:' + barClr + '">' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%</span>' +
        '</div>';
    });
    rotHtml += '</div>';
    rotationGrid.innerHTML = rotHtml;
  }
}

/* ============================================================
   Open Stock Modal
   ============================================================ */
function triggerAiFromModal(ticker) {
  var input = document.getElementById('ai-ticker-input');
  if (input) {
    input.value = ticker;
    switchTab('ai');
  }
}

/* ============================================================
   IBKR Connection Check
   ============================================================ */
async function checkIbkrConnection() {
  var dot = document.getElementById('ibkr-status-dot');
  var text = document.getElementById('ibkr-status-text');
  try {
    var response = await fetch('/api/ibkr/status');
    if (!response.ok) throw new Error('not ok');
    var result = await response.json();
    if (result.data && result.data.connected) {
      dot.className = 'ibkr-status-dot ibkr-connected';
      text.textContent = 'IBKR Connected';
      updateSectionTimestamp('shortterm');
    } else {
      dot.className = 'ibkr-status-dot ibkr-disconnected';
      text.textContent = 'IBKR Disconnected';
    }
  } catch (err) {
    if (dot) dot.className = 'ibkr-status-dot ibkr-disconnected';
    if (text) text.textContent = 'IBKR Unavailable';
  }
}

/* ============================================================
   AI Trading
   ============================================================ */
function initTrading() {
  var analyzeBtn = document.getElementById('trade-analyze-btn');
  var input = document.getElementById('trade-ticker-input');
  if (!analyzeBtn) return;

  analyzeBtn.addEventListener('click', function() {
    var ticker = input.value.trim().toUpperCase();
    if (ticker) runTradeAnalysis(ticker);
  });
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var ticker = input.value.trim().toUpperCase();
      if (ticker) runTradeAnalysis(ticker);
    }
  });

  // Load portfolio on tab switch to trading
  fetchPortfolio();
}

async function runTradeAnalysis(ticker) {
  var loading = document.getElementById('trading-loading');
  var results = document.getElementById('trading-results');
  var btn = document.getElementById('trade-analyze-btn');

  loading.classList.remove('hidden');
  results.classList.add('hidden');
  btn.disabled = true;

  try {
    var response = await fetch('/api/ai-analyze-full/' + ticker, { method: 'POST' });
    var result = await response.json();

    loading.classList.add('hidden');
    btn.disabled = false;

    if (result.error) {
      results.classList.remove('hidden');
      results.innerHTML = '<div class="ai-error">' + escapeHtml(result.error.message) + '</div>';
      return;
    }

    renderTradeResults(result.data);
    updateSectionTimestamp('trading');
  } catch (err) {
    loading.classList.add('hidden');
    btn.disabled = false;
    results.classList.remove('hidden');
    results.innerHTML = '<div class="ai-error">Failed: ' + escapeHtml(err.message) + '</div>';
  }
}

function renderTradeResults(data) {
  var results = document.getElementById('trading-results');
  var recEl = document.getElementById('trade-recommendation');
  var inputDataEl = document.getElementById('trade-input-data');
  var execSection = document.getElementById('trade-execute-section');

  results.classList.remove('hidden');

  var analysis = data.analysis || {};
  var model = data.model_prediction;
  var inputData = data.input_data || {};
  var sources = data.data_sources_used || [];

  // Recommendation card with highlighted numbers
  var ratingClass = getRatingClass(analysis.rating);
  var html = '<div class="trade-rec-card">';
  html += '<div class="trade-rec-header">';
  html += '<div class="ai-rating-badge ' + ratingClass + '">' + escapeHtml(analysis.rating || 'N/A') + '</div>';
  html += '<div class="trade-rec-confidence">Confidence: <span class="hl-number">' + (analysis.confidence || 'N/A') + '/10</span></div>';
  html += '</div>';
  html += '<p class="trade-rec-summary">' + highlightText(analysis.summary || '') + '</p>';

  // Price targets with highlighting
  var targets = analysis.price_targets || {};
  html += '<div class="trade-targets">';
  html += '<div class="trade-target trade-target--bear">Bear: <span class="hl-price hl-red">$' + (targets.bear_case || 'N/A') + '</span></div>';
  html += '<div class="trade-target trade-target--base">Base: <span class="hl-price hl-blue">$' + (targets.base_case || 'N/A') + '</span></div>';
  html += '<div class="trade-target trade-target--bull">Bull: <span class="hl-price hl-green">$' + (targets.bull_case || 'N/A') + '</span></div>';
  html += '</div>';

  // Model prediction if available
  if (model) {
    html += '<div class="trade-model-pred">';
    html += '<h4>LightGBM Model Prediction</h4>';
    html += '<div class="trade-model-row">';
    html += '<span>Signal: <span class="hl-number">' + formatSignal(model.signal) + '</span></span>';
    html += '<span>Consistency: <span class="hl-number">' + ((model.consistency || 0) * 100).toFixed(0) + '%</span></span>';
    html += '<span>Rank: <span class="hl-number">#' + (model.rank || 'N/A') + '</span></span>';
    html += '</div></div>';
  }

  // Scores with highlighted bars
  var scores = [
    { label: 'Fundamental', value: analysis.fundamental_score, color: '#3b82f6' },
    { label: 'Technical', value: analysis.technical_score, color: '#8b5cf6' },
    { label: 'Sentiment', value: analysis.sentiment_score, color: '#f59e0b' },
    { label: 'Risk', value: analysis.risk_score, color: '#ef4444' },
  ];
  html += '<div class="ai-scores-grid">';
  html += scores.map(function(s) {
    var pct = ((s.value || 0) / 10 * 100);
    return '<div class="ai-score-card"><div class="ai-score-label">' + s.label + '</div>' +
      '<div class="ai-score-bar"><div class="ai-score-fill" style="width:' + pct + '%;background:' + s.color + '"></div></div>' +
      '<div class="ai-score-value"><span class="hl-number">' + (s.value || 'N/A') + '/10</span></div></div>';
  }).join('');
  html += '</div>';

  // Upcoming events
  var upcomingEvents = data.upcoming_events || {};
  var stockEvents = upcomingEvents.events || [];
  if (stockEvents.length > 0 || upcomingEvents.next_earnings) {
    html += '<div class="trade-events-card">';
    html += '<h4 style="margin-bottom:8px;color:var(--accent-blue);font-size:0.875rem;">Upcoming Events</h4>';
    if (upcomingEvents.next_earnings) {
      var daysTo = upcomingEvents.days_to_earnings;
      var urgency = daysTo <= 7 ? ' calendar-urgent' : daysTo <= 14 ? ' calendar-soon' : '';
      html += '<div class="trade-event-highlight' + urgency + '">';
      html += '<span class="hl-keyword">EARNINGS</span> ';
      html += '<span class="hl-timestamp">' + escapeHtml(upcomingEvents.next_earnings.date || 'TBD') + '</span> ';
      html += '(<span class="hl-number">' + (daysTo || '?') + '</span> days)';
      html += '</div>';
    }
    if (upcomingEvents.ex_dividend_date) {
      html += '<div class="trade-event-item"><span class="hl-keyword">EX-DIV</span> <span class="hl-timestamp">' + escapeHtml(upcomingEvents.ex_dividend_date) + '</span></div>';
    }
    stockEvents.slice(0, 5).forEach(function(evt) {
      var impClass = evt.importance === 'high' ? 'cal-imp-high' : evt.importance === 'medium' ? 'cal-imp-medium' : 'cal-imp-low';
      html += '<div class="trade-event-item"><span class="cal-imp-dot ' + impClass + '"></span> <span class="hl-timestamp">' + escapeHtml(evt.date || '') + '</span> ' + escapeHtml(evt.event || '') + '</div>';
    });
    html += '</div>';
  }

  html += '</div>';
  recEl.innerHTML = html;

  // Input data transparency section
  var inputHtml = '<div class="input-data-toggle">';
  inputHtml += '<button type="button" class="btn btn-sm" id="toggle-input-data">Show Input Data & Sources</button>';
  inputHtml += '</div>';
  inputHtml += '<div class="input-data-content hidden" id="input-data-content">';

  // Data sources used
  inputHtml += '<h4>Data Sources Used</h4>';
  inputHtml += '<div class="data-sources-grid">';
  sources.forEach(function(src) {
    inputHtml += '<div class="data-source-card">';
    inputHtml += '<div class="data-source-name">' + escapeHtml(src.name) + '</div>';
    inputHtml += '<div class="data-source-type">' + escapeHtml(src.type) + '</div>';
    inputHtml += '<div class="data-source-fields">' + (src.fields || []).join(', ') + '</div>';
    inputHtml += '</div>';
  });
  inputHtml += '</div>';

  // Fundamentals data
  var fundData = inputData.fundamentals || {};
  var ratios = fundData.ratios || {};
  if (Object.keys(ratios).length > 0) {
    inputHtml += '<h4>Fundamental Data (Input)</h4>';
    inputHtml += '<div class="input-data-table">';
    Object.entries(ratios).forEach(function(entry) {
      var val = entry[1];
      var displayVal = val !== null && val !== undefined ? String(val) : 'N/A';
      var label = entry[0].replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
      inputHtml += '<div class="input-data-row"><span class="input-data-label">' + label + '</span><span class="input-data-value hl-number">' + displayVal + '</span></div>';
    });
    inputHtml += '</div>';
  }

  // Technical data - all indicators
  var techData = inputData.technicals || {};
  if (Object.keys(techData).length > 0) {
    inputHtml += '<h4>Technical Data (Input)</h4>';
    inputHtml += '<div class="input-data-table">';
    ['current_price', 'rsi_14', 'atr_14', 'trend_strength', 'obv_trend', 'relative_strength_vs_sp500', 'ma_signals'].forEach(function(key) {
      if (techData[key] !== undefined) {
        var label = key.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
        inputHtml += '<div class="input-data-row"><span class="input-data-label">' + label + '</span><span class="input-data-value hl-number">' + techData[key] + '</span></div>';
      }
    });
    // Moving averages
    var mas = techData.moving_averages || {};
    if (Object.keys(mas).length > 0) {
      Object.entries(mas).forEach(function(entry) {
        if (entry[1] !== null) {
          inputHtml += '<div class="input-data-row"><span class="input-data-label">' + entry[0].toUpperCase() + '</span><span class="input-data-value hl-price">$' + Number(entry[1]).toFixed(2) + '</span></div>';
        }
      });
    }
    // MACD
    var macd = techData.macd || {};
    if (macd.macd_line !== undefined) {
      inputHtml += '<div class="input-data-row"><span class="input-data-label">MACD Line</span><span class="input-data-value hl-number">' + Number(macd.macd_line).toFixed(4) + '</span></div>';
      inputHtml += '<div class="input-data-row"><span class="input-data-label">MACD Signal</span><span class="input-data-value hl-number">' + Number(macd.signal_line).toFixed(4) + '</span></div>';
      inputHtml += '<div class="input-data-row"><span class="input-data-label">MACD Histogram</span><span class="input-data-value hl-number">' + Number(macd.histogram).toFixed(4) + '</span></div>';
    }
    // Bollinger Bands
    var bb = techData.bollinger_bands || {};
    if (bb.upper !== undefined) {
      inputHtml += '<div class="input-data-row"><span class="input-data-label">Bollinger Upper</span><span class="input-data-value hl-price">$' + Number(bb.upper).toFixed(2) + '</span></div>';
      inputHtml += '<div class="input-data-row"><span class="input-data-label">Bollinger Lower</span><span class="input-data-value hl-price">$' + Number(bb.lower).toFixed(2) + '</span></div>';
      inputHtml += '<div class="input-data-row"><span class="input-data-label">BB Width %</span><span class="input-data-value hl-number">' + Number(bb.bandwidth_pct || 0).toFixed(2) + '%</span></div>';
    }
    // 52-Week range
    var range52 = techData.range_52w || {};
    if (range52.high !== undefined) {
      inputHtml += '<div class="input-data-row"><span class="input-data-label">52W High</span><span class="input-data-value hl-price">$' + Number(range52.high).toFixed(2) + '</span></div>';
      inputHtml += '<div class="input-data-row"><span class="input-data-label">52W Low</span><span class="input-data-value hl-price">$' + Number(range52.low).toFixed(2) + '</span></div>';
      if (range52.pct_from_high !== undefined) {
        inputHtml += '<div class="input-data-row"><span class="input-data-label">% from 52W High</span><span class="input-data-value hl-number">' + Number(range52.pct_from_high).toFixed(1) + '%</span></div>';
      }
    }
    // Volatility
    var vol = techData.volatility || {};
    if (vol.annualized !== undefined) {
      inputHtml += '<div class="input-data-row"><span class="input-data-label">Annualized Vol</span><span class="input-data-value hl-number">' + Number(vol.annualized).toFixed(2) + '%</span></div>';
    }
    inputHtml += '</div>';
  }

  // Recent prices
  var prices = inputData.recent_prices || [];
  if (prices.length > 0) {
    inputHtml += '<h4>Recent Price History (Last 10 Days)</h4>';
    inputHtml += '<div class="price-history-table">';
    inputHtml += '<div class="price-row price-header"><span>Date</span><span>Close</span><span>Volume</span></div>';
    prices.forEach(function(p) {
      inputHtml += '<div class="price-row"><span>' + p.date + '</span><span class="hl-price">$' + p.close + '</span><span>' + (p.volume || 0).toLocaleString() + '</span></div>';
    });
    inputHtml += '</div>';
  }

  // Macro data
  var macroData = inputData.macro || {};
  var macroIndicators = macroData.indicators || {};
  if (Object.keys(macroIndicators).length > 0) {
    inputHtml += '<h4>Macroeconomic Data (Input)</h4>';
    inputHtml += '<div class="input-data-table">';
    Object.entries(macroIndicators).forEach(function(entry) {
      var val = entry[1];
      var displayVal = val !== null && val !== undefined ? String(val) : 'N/A';
      var label = entry[0].replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
      inputHtml += '<div class="input-data-row"><span class="input-data-label">' + label + '</span><span class="input-data-value hl-number">' + displayVal + '</span></div>';
    });
    inputHtml += '</div>';
  }

  // Sentiment data
  var sentimentData = inputData.sentiment || {};
  if (sentimentData.fear_greed_score !== undefined) {
    inputHtml += '<h4>Market Sentiment (Input)</h4>';
    inputHtml += '<div class="input-data-table">';
    ['fear_greed_score', 'fear_greed_label', 'vix', 'vix_regime', 'sp500_change_pct', 'nasdaq_change_pct'].forEach(function(key) {
      if (sentimentData[key] !== undefined) {
        var label = key.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
        inputHtml += '<div class="input-data-row"><span class="input-data-label">' + label + '</span><span class="input-data-value hl-number">' + sentimentData[key] + '</span></div>';
      }
    });
    inputHtml += '</div>';
  }

  // Historical data range
  var range = data.historical_data_range || {};
  inputHtml += '<h4>Data Coverage</h4>';
  inputHtml += '<div class="data-coverage">';
  Object.entries(range).forEach(function(entry) {
    inputHtml += '<div class="coverage-item"><span class="coverage-label">' + entry[0].replace(/_/g, ' ') + '</span><span class="coverage-value">' + entry[1] + '</span></div>';
  });
  inputHtml += '</div>';

  inputHtml += '</div>';
  inputDataEl.innerHTML = inputHtml;
  inputDataEl.classList.remove('hidden');

  // Toggle input data visibility
  setTimeout(function() {
    var toggleBtn = document.getElementById('toggle-input-data');
    var content = document.getElementById('input-data-content');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function() {
        content.classList.toggle('hidden');
        toggleBtn.textContent = content.classList.contains('hidden') ? 'Show Input Data & Sources' : 'Hide Input Data & Sources';
      });
    }
  }, 0);

  // Show execute section for BUY/SELL ratings
  var rating = (analysis.rating || '').toUpperCase();
  if (rating === 'BUY' || rating === 'STRONG_BUY' || rating === 'SELL' || rating === 'STRONG_SELL') {
    execSection.classList.remove('hidden');
    var paramsEl = document.getElementById('trade-params');
    paramsEl.innerHTML = '<div class="trade-param-grid">' +
      '<div><span class="trade-param-label">Action</span><span class="hl-keyword">' + (rating.includes('BUY') ? 'BUY' : 'SELL') + '</span></div>' +
      '<div><span class="trade-param-label">Entry Strategy</span><span>' + escapeHtml(analysis.entry_strategy || 'N/A') + '</span></div>' +
      '<div><span class="trade-param-label">Exit Strategy</span><span>' + escapeHtml(analysis.exit_strategy || 'N/A') + '</span></div>' +
      '<div><span class="trade-param-label">Position Sizing</span><span>' + escapeHtml(analysis.position_sizing || 'N/A') + '</span></div>' +
      '</div>';

    var execBtn = document.getElementById('trade-execute-btn');
    execBtn.disabled = false;
    execBtn.onclick = function() {
      if (confirm('Are you sure you want to execute this trade? This will place a real order on your IBKR account.')) {
        executeTrade(analysis);
      }
    };

    var cancelBtn = document.getElementById('trade-cancel-btn');
    cancelBtn.onclick = function() {
      execSection.classList.add('hidden');
    };
  }
}

function highlightText(text) {
  if (!text) return '';
  // Highlight dollar amounts
  var result = escapeHtml(text);
  result = result.replace(/\$[\d,]+\.?\d*/g, '<span class="hl-price">$&</span>');
  // Highlight percentages
  result = result.replace(/[\-+]?\d+\.?\d*%/g, '<span class="hl-number">$&</span>');
  // Highlight key words
  var keywords = ['BUY', 'SELL', 'HOLD', 'STRONG_BUY', 'STRONG_SELL', 'bullish', 'bearish', 'overbought', 'oversold', 'support', 'resistance'];
  keywords.forEach(function(kw) {
    var re = new RegExp('\\b(' + kw + ')\\b', 'gi');
    result = result.replace(re, '<span class="hl-keyword">$1</span>');
  });
  return result;
}

async function executeTrade(analysis) {
  var execBtn = document.getElementById('trade-execute-btn');
  execBtn.disabled = true;
  execBtn.textContent = 'Executing...';

  try {
    var response = await fetch('/api/trading/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: document.getElementById('trade-ticker-input').value.trim().toUpperCase(),
        action: (analysis.rating || '').includes('BUY') ? 'BUY' : 'SELL',
        order_type: 'LMT',
        confirm: true,
      }),
    });
    var result = await response.json();
    if (result.error) {
      alert('Trade failed: ' + result.error.message);
    } else {
      alert('Order placed successfully! Order ID: ' + (result.data && result.data.order_id || 'pending'));
      fetchPortfolio();
    }
  } catch (err) {
    alert('Trade execution failed: ' + err.message);
  } finally {
    execBtn.disabled = false;
    execBtn.textContent = 'Confirm & Execute Trade';
  }
}

async function fetchPortfolio() {
  try {
    var response = await fetch('/api/trading/portfolio');
    if (!response.ok) return;
    var result = await response.json();
    renderPortfolio(result.data);
  } catch (err) {
    // Portfolio unavailable - IBKR not connected
  }
}

function renderPortfolio(data) {
  var grid = document.getElementById('portfolio-grid');
  if (!grid || !data) return;

  var account = data.account || {};
  var positions = data.positions || [];

  var html = '<div class="portfolio-account">';
  html += '<div class="portfolio-stat"><span>Net Liquidation</span><span class="hl-price">$' + (account.net_liquidation || 'N/A') + '</span></div>';
  html += '<div class="portfolio-stat"><span>Buying Power</span><span class="hl-price">$' + (account.buying_power || 'N/A') + '</span></div>';
  html += '<div class="portfolio-stat"><span>Positions</span><span class="hl-number">' + positions.length + '</span></div>';
  html += '</div>';

  if (positions.length > 0) {
    html += '<div class="positions-table">';
    html += '<div class="position-row position-header"><span>Symbol</span><span>Qty</span><span>Avg Cost</span><span>Market Value</span><span>P&L</span></div>';
    positions.forEach(function(pos) {
      var plClass = (pos.unrealized_pnl || 0) >= 0 ? 'hl-green' : 'hl-red';
      html += '<div class="position-row">';
      html += '<span class="hl-keyword">' + (pos.symbol || '') + '</span>';
      html += '<span>' + (pos.quantity || 0) + '</span>';
      html += '<span class="hl-price">$' + (pos.avg_cost || 0).toFixed(2) + '</span>';
      html += '<span class="hl-price">$' + (pos.market_value || 0).toFixed(2) + '</span>';
      html += '<span class="' + plClass + '">$' + (pos.unrealized_pnl || 0).toFixed(2) + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  grid.innerHTML = html;
}

/* ============================================================
   Options Trading (Enhanced)
   ============================================================ */
function initOptions() {
  var loadBtn = document.getElementById('options-load-chain-btn');
  var input = document.getElementById('options-ticker-input');
  if (!loadBtn) return;

  loadBtn.addEventListener('click', function() {
    var ticker = input.value.trim().toUpperCase();
    if (ticker) loadOptionsChain(ticker);
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var ticker = input.value.trim().toUpperCase();
      if (ticker) loadOptionsChain(ticker);
    }
  });

  // Load unusual activity
  fetchUnusualOptions();
}

async function loadOptionsChain(ticker) {
  updateSectionTimestamp('options');
  var tableEl = document.getElementById('options-chain-table');
  var summaryEl = document.getElementById('options-summary');

  tableEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted)">Loading options chain...</div>';

  try {
    var response = await fetch('/api/options/overview/' + ticker);
    var result = await response.json();

    if (result.data) {
      var data = result.data;
      summaryEl.innerHTML = '<div class="options-summary-grid">' +
        '<div class="options-stat"><span>Underlying</span><span class="hl-keyword">' + ticker + '</span></div>' +
        '<div class="options-stat"><span>Price</span><span class="hl-price">$' + (data.underlying_price || 'N/A') + '</span></div>' +
        '<div class="options-stat"><span>Updated</span><span class="hl-timestamp">' + formatTimestamp(new Date()) + '</span></div>' +
        '</div>';

      // Populate expiry dropdown
      var expirySelect = document.getElementById('options-expiry-select');
      expirySelect.innerHTML = '<option value="">Select expiration...</option>';
      (data.expirations || []).forEach(function(exp) {
        expirySelect.innerHTML += '<option value="' + exp + '">' + exp + '</option>';
      });
    }

    // Load chain data
    var chainResp = await fetch('/api/options/chain/' + ticker);
    var chainResult = await chainResp.json();
    renderOptionsChain(chainResult.data);

    // Load flow
    fetchOptionsFlow(ticker);

  } catch (err) {
    tableEl.innerHTML = '<div class="ai-error">Failed to load options: ' + escapeHtml(err.message) + '</div>';
  }
}

function renderOptionsChain(data) {
  var tableEl = document.getElementById('options-chain-table');
  if (!data || !data.chain) {
    tableEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted)">No options data available. Ensure IBKR is connected.</div>';
    return;
  }

  var chain = data.chain || [];
  var html = '<table class="options-table">';
  html += '<thead><tr>';
  html += '<th>Type</th><th>Strike</th><th>Bid</th><th>Ask</th><th>Last</th><th>Vol</th><th>OI</th><th>IV</th><th>Delta</th><th>Theta</th><th>Time</th>';
  html += '</tr></thead><tbody>';

  chain.forEach(function(opt) {
    var typeClass = opt.right === 'C' ? 'option-call' : 'option-put';
    html += '<tr class="' + typeClass + '">';
    html += '<td><span class="hl-keyword">' + (opt.right === 'C' ? 'CALL' : 'PUT') + '</span></td>';
    html += '<td class="hl-price">$' + (opt.strike || '') + '</td>';
    html += '<td>' + (opt.bid || '-') + '</td>';
    html += '<td>' + (opt.ask || '-') + '</td>';
    html += '<td class="hl-number">' + (opt.last || '-') + '</td>';
    html += '<td>' + (opt.volume || '-') + '</td>';
    html += '<td>' + (opt.open_interest || '-') + '</td>';
    html += '<td class="hl-number">' + (opt.implied_vol ? (opt.implied_vol * 100).toFixed(1) + '%' : '-') + '</td>';
    html += '<td>' + (opt.delta ? opt.delta.toFixed(3) : '-') + '</td>';
    html += '<td>' + (opt.theta ? opt.theta.toFixed(3) : '-') + '</td>';
    html += '<td class="hl-timestamp">' + (opt.timestamp || '') + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table>';
  tableEl.innerHTML = html;
}

async function fetchOptionsFlow(ticker) {
  try {
    var response = await fetch('/api/options/flow/' + ticker);
    var result = await response.json();
    var flowEl = document.getElementById('options-flow-data');
    if (result.data && flowEl) {
      var data = result.data;
      flowEl.innerHTML = '<div class="flow-stats">' +
        '<div class="flow-stat"><span>Put/Call Ratio</span><span class="hl-number">' + (data.put_call_ratio || 'N/A') + '</span></div>' +
        '<div class="flow-stat"><span>Call Volume</span><span class="hl-number">' + (data.call_volume || 0).toLocaleString() + '</span></div>' +
        '<div class="flow-stat"><span>Put Volume</span><span class="hl-number">' + (data.put_volume || 0).toLocaleString() + '</span></div>' +
        '<div class="flow-stat"><span>Implied Move</span><span class="hl-number">' + (data.implied_move || 'N/A') + '</span></div>' +
        '<div class="flow-stat"><span>Updated</span><span class="hl-timestamp">' + formatTimestamp(new Date()) + '</span></div>' +
        '</div>';
    }
  } catch (err) {
    console.error('Options flow error:', err);
  }
}

async function fetchUnusualOptions() {
  try {
    var response = await fetch('/api/options/unusual');
    var result = await response.json();
    var unusualEl = document.getElementById('options-unusual-data');
    if (result.data && unusualEl) {
      var items = result.data.unusual || [];
      if (items.length === 0) {
        unusualEl.innerHTML = '<div style="color:var(--text-muted)">No unusual activity detected</div>';
        return;
      }
      var html = '<div class="unusual-grid">';
      items.forEach(function(item) {
        html += '<div class="unusual-card">';
        html += '<span class="hl-keyword">' + (item.symbol || '') + '</span>';
        html += '<span class="hl-number">' + (item.volume_ratio || 0).toFixed(1) + 'x avg</span>';
        html += '<span>' + (item.right === 'C' ? 'CALL' : 'PUT') + ' $' + (item.strike || '') + '</span>';
        html += '<span class="hl-timestamp">' + (item.timestamp || '') + '</span>';
        html += '</div>';
      });
      html += '</div>';
      unusualEl.innerHTML = html;
    }
  } catch (err) {
    console.error('Unusual options error:', err);
  }
}

/* ============================================================
   Economic Calendar
   ============================================================ */
async function fetchEconomicCalendar() {
  try {
    var response = await fetch('/api/economic-calendar');
    if (!response.ok) return;
    var result = await response.json();
    if (result.data) {
      renderCalendarHighlights(result.data);
      renderCalendarGrid(result.data);
      updateSectionTimestamp('calendar');
    }
  } catch (err) {
    console.error('Failed to fetch economic calendar:', err);
  }
}

function renderCalendarHighlights(data) {
  var el = document.getElementById('calendar-highlights');
  if (!el) return;

  var nextMajor = data.next_major;
  var thisWeek = data.this_week || [];

  var html = '<div class="calendar-highlight-cards">';

  if (nextMajor) {
    var daysUntil = Math.ceil((new Date(nextMajor.date) - new Date()) / 86400000);
    var urgencyClass = daysUntil <= 1 ? 'calendar-urgent' : daysUntil <= 3 ? 'calendar-soon' : '';
    html += '<div class="calendar-highlight-card ' + urgencyClass + '">';
    html += '<div class="calendar-highlight-label">Next Major Event</div>';
    html += '<div class="calendar-highlight-event"><span class="hl-keyword">' + escapeHtml(nextMajor.event) + '</span></div>';
    html += '<div class="calendar-highlight-date">' + escapeHtml(nextMajor.date) + (nextMajor.time ? ' ' + nextMajor.time : '') + '</div>';
    html += '<div class="calendar-highlight-days"><span class="hl-number">' + daysUntil + '</span> day' + (daysUntil !== 1 ? 's' : '') + ' away</div>';
    if (nextMajor.previous) html += '<div class="calendar-highlight-prev">Previous: <span class="hl-number">' + escapeHtml(nextMajor.previous) + '</span></div>';
    html += '</div>';
  }

  // This week events
  if (thisWeek.length > 0) {
    html += '<div class="calendar-highlight-card">';
    html += '<div class="calendar-highlight-label">This Week (' + thisWeek.length + ' events)</div>';
    thisWeek.slice(0, 5).forEach(function(evt) {
      var impClass = evt.importance === 'high' ? 'cal-imp-high' : evt.importance === 'medium' ? 'cal-imp-medium' : 'cal-imp-low';
      html += '<div class="calendar-week-item">';
      html += '<span class="cal-imp-dot ' + impClass + '"></span>';
      html += '<span class="calendar-week-date">' + escapeHtml(evt.date.slice(5)) + '</span>';
      html += '<span>' + escapeHtml(evt.event) + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

function renderCalendarGrid(data) {
  var el = document.getElementById('calendar-grid');
  if (!el) return;

  var events = data.events || [];
  if (events.length === 0) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px;">No upcoming events found</div>';
    return;
  }

  // Show top 8 events in overview, with link to Market Data tab for full list
  var displayEvents = events.slice(0, 8);

  var html = '<div class="calendar-table">';
  html += '<div class="calendar-row calendar-header"><span>Date</span><span>Time</span><span>Event</span><span>Importance</span><span>Previous</span><span>Forecast</span></div>';

  displayEvents.forEach(function(evt) {
    var impClass = evt.importance === 'high' ? 'cal-imp-high' : evt.importance === 'medium' ? 'cal-imp-medium' : 'cal-imp-low';
    var today = new Date().toISOString().slice(0, 10);
    var isToday = evt.date === today;
    var rowClass = isToday ? 'calendar-row calendar-today' : 'calendar-row';

    html += '<div class="' + rowClass + '">';
    html += '<span class="hl-timestamp">' + escapeHtml(evt.date) + '</span>';
    html += '<span>' + escapeHtml(evt.time || '--') + '</span>';
    html += '<span><span class="cal-imp-dot ' + impClass + '"></span>' + escapeHtml(evt.event) + '</span>';
    html += '<span class="' + impClass + '">' + escapeHtml(evt.importance) + '</span>';
    html += '<span class="hl-number">' + escapeHtml(evt.previous || '--') + '</span>';
    html += '<span class="hl-number">' + escapeHtml(evt.forecast || '--') + '</span>';
    html += '</div>';
  });

  html += '</div>';

  // Link banner to Market Data tab for full released data
  if (events.length > 8) {
    html += '<div class="calendar-link-banner" onclick="switchTab(\'market\')" role="button" tabindex="0">';
    html += '<span class="calendar-link-text"><strong>' + events.length + ' total events</strong> — View full economic calendar and released data on the Market Data tab</span>';
    html += '<span class="calendar-link-arrow">&rarr;</span>';
    html += '</div>';
  } else {
    html += '<div class="calendar-link-banner" onclick="switchTab(\'market\')" role="button" tabindex="0">';
    html += '<span class="calendar-link-text">View released data and full economic indicators on the <strong>Market Data</strong> tab</span>';
    html += '<span class="calendar-link-arrow">&rarr;</span>';
    html += '</div>';
  }

  el.innerHTML = html;
}

/* ============================================================
   Auto Trading Controls
   ============================================================ */
function initAutoTrading() {
  var startBtn = document.getElementById('auto-trade-start-btn');
  var stopBtn = document.getElementById('auto-trade-stop-btn');
  if (!startBtn) return;

  startBtn.addEventListener('click', startAutoTrading);
  stopBtn.addEventListener('click', stopAutoTrading);

  // Refresh status every 30 seconds
  fetchAutoTradeStatus();
  setInterval(fetchAutoTradeStatus, 30000);

  // Load IBKR session status
  fetchSessionStatus();
  setInterval(fetchSessionStatus, 60000);
}

async function startAutoTrading() {
  var paperMode = document.getElementById('auto-trade-paper-mode').checked;

  if (!paperMode) {
    if (!confirm('WARNING: You are about to start LIVE auto-trading with real money. Are you sure?')) {
      return;
    }
  }

  var config = {
    max_trades_per_day: parseInt(document.getElementById('at-max-trades').value) || 10,
    max_position_size_pct: parseFloat(document.getElementById('at-position-size').value) || 5,
    max_daily_loss_dollars: parseFloat(document.getElementById('at-max-loss').value) || 1000,
    min_confidence: parseInt(document.getElementById('at-min-confidence').value) || 7,
    stop_loss_pct: parseFloat(document.getElementById('at-stop-loss').value) || 2,
    take_profit_pct: parseFloat(document.getElementById('at-take-profit').value) || 5,
    scan_interval_seconds: parseInt(document.getElementById('at-scan-interval').value) || 300,
    auto_close_eod: document.getElementById('at-auto-close').checked,
    paper_mode: paperMode,
  };

  try {
    var response = await fetch('/api/auto-trade/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    var result = await response.json();
    if (result.error) {
      alert('Failed to start: ' + result.error.message);
    } else {
      document.getElementById('auto-trade-start-btn').disabled = true;
      document.getElementById('auto-trade-stop-btn').disabled = false;
      fetchAutoTradeStatus();
    }
  } catch (err) {
    alert('Error: ' + err.message);
  }
}

async function stopAutoTrading() {
  try {
    await fetch('/api/auto-trade/stop', { method: 'POST' });
    document.getElementById('auto-trade-start-btn').disabled = false;
    document.getElementById('auto-trade-stop-btn').disabled = true;
    fetchAutoTradeStatus();
  } catch (err) {
    console.error('Stop failed:', err);
  }
}

async function fetchAutoTradeStatus() {
  try {
    var response = await fetch('/api/auto-trade/status');
    if (!response.ok) return;
    var result = await response.json();
    if (result.data) renderAutoTradeStatus(result.data);
  } catch (err) {
    // Auto-trade not available
  }
}

function renderAutoTradeStatus(data) {
  // Status bar
  var dot = document.getElementById('auto-trade-dot');
  var text = document.getElementById('auto-trade-status-text');
  var modeEl = document.getElementById('auto-trade-mode');

  if (dot) {
    dot.className = 'auto-trade-status-dot ' + (data.running ? 'at-running' : 'at-stopped');
  }
  if (text) {
    text.textContent = 'Auto-trading: ' + (data.running ? 'Active' : 'Stopped');
  }
  if (modeEl) {
    modeEl.textContent = data.paper_mode ? 'Paper Mode' : 'LIVE MODE';
    modeEl.className = 'auto-trade-mode ' + (data.paper_mode ? 'at-paper' : 'at-live');
  }

  // Button states
  var startBtn = document.getElementById('auto-trade-start-btn');
  var stopBtn = document.getElementById('auto-trade-stop-btn');
  if (startBtn) startBtn.disabled = data.running;
  if (stopBtn) stopBtn.disabled = !data.running;

  // Stats
  var statsGrid = document.getElementById('auto-trade-stats-grid');
  if (statsGrid) {
    var pnlClass = (data.daily_pnl || 0) >= 0 ? 'hl-green' : 'hl-red';
    statsGrid.innerHTML =
      '<div class="at-stat"><span>Trades Today</span><span class="hl-number">' + (data.trades_today || 0) + '</span></div>' +
      '<div class="at-stat"><span>Daily P&L</span><span class="' + pnlClass + '">$' + (data.daily_pnl || 0).toFixed(2) + '</span></div>' +
      '<div class="at-stat"><span>Daily P&L %</span><span class="' + pnlClass + '">' + (data.daily_pnl_pct || 0).toFixed(2) + '%</span></div>' +
      '<div class="at-stat"><span>Open Positions</span><span class="hl-number">' + (data.open_positions || []).length + '</span></div>' +
      '<div class="at-stat"><span>Next Scan</span><span class="hl-timestamp">' + (data.next_scan ? formatTimestamp(new Date(data.next_scan)) : '--') + '</span></div>' +
      '<div class="at-stat"><span>Alerts</span><span class="hl-number">' + (data.alerts || []).length + '</span></div>';
  }

  // Trade log
  var logEl = document.getElementById('trade-log-table');
  if (logEl && data.trade_log) {
    var trades = data.trade_log || [];
    if (trades.length === 0) {
      logEl.innerHTML = '<div style="color:var(--text-muted);padding:12px;">No trades yet today</div>';
    } else {
      var logHtml = '<div class="trade-log-row trade-log-header"><span>Time</span><span>Ticker</span><span>Action</span><span>Qty</span><span>Price</span><span>Status</span><span>P&L</span></div>';
      trades.forEach(function(t) {
        var plClass = (t.pnl || 0) >= 0 ? 'hl-green' : 'hl-red';
        logHtml += '<div class="trade-log-row">';
        logHtml += '<span class="hl-timestamp">' + (t.timestamp ? formatTimestamp(new Date(t.timestamp)) : '') + '</span>';
        logHtml += '<span class="hl-keyword">' + escapeHtml(t.ticker || '') + '</span>';
        logHtml += '<span class="hl-keyword">' + escapeHtml(t.action || '') + '</span>';
        logHtml += '<span>' + (t.quantity || 0) + '</span>';
        logHtml += '<span class="hl-price">$' + (t.price || 0).toFixed(2) + '</span>';
        logHtml += '<span>' + escapeHtml(t.status || '') + '</span>';
        logHtml += '<span class="' + plClass + '">$' + (t.pnl || 0).toFixed(2) + '</span>';
        logHtml += '</div>';
      });
      logEl.innerHTML = logHtml;
    }
  }

  updateSectionTimestamp('auto-trade');
}

async function fetchSessionStatus() {
  try {
    var response = await fetch('/api/ibkr/session-status');
    if (!response.ok) return;
    var result = await response.json();
    if (result.data) renderSessionInfo(result.data);
  } catch (err) {
    // Session status not available
  }
}

function renderSessionInfo(data) {
  var el = document.getElementById('session-info-grid');
  if (!el) return;

  var statusClass = data.status === 'connected' ? 'hl-green' : data.status === 'reconnecting' ? 'hl-blue' : 'hl-red';
  var uptimeMin = Math.floor((data.uptime_seconds || 0) / 60);

  el.innerHTML =
    '<div class="session-stat"><span>Status</span><span class="' + statusClass + '">' + escapeHtml(data.status || 'unknown') + '</span></div>' +
    '<div class="session-stat"><span>Authenticated</span><span class="' + (data.authenticated ? 'hl-green' : 'hl-red') + '">' + (data.authenticated ? 'Yes' : 'No') + '</span></div>' +
    '<div class="session-stat"><span>Uptime</span><span class="hl-number">' + uptimeMin + ' min</span></div>' +
    '<div class="session-stat"><span>Reconnects</span><span class="hl-number">' + (data.reconnect_count || 0) + '</span></div>' +
    '<div class="session-stat"><span>Last Keepalive</span><span class="hl-timestamp">' + (data.last_tickle ? formatTimestamp(new Date(data.last_tickle)) : '--') + '</span></div>' +
    '<div class="session-stat"><span>Day Trade Ready</span><span class="' + (data.is_day_trading_ready ? 'hl-green' : 'hl-red') + '">' + (data.is_day_trading_ready ? 'Yes' : 'No') + '</span></div>';
}

/* ============================================================
   Study Cards & Quiz
   ============================================================ */
var studyState = {
  cards: [],
  cardIndex: 0,
  isFlipped: false,
  quiz: null,
  quizIndex: 0,
  quizAnswers: [],
};

function initStudyCards() {
  var cardsBtn = document.getElementById('study-cards-btn');
  var quizBtn = document.getElementById('study-quiz-btn');
  if (!cardsBtn) return;

  cardsBtn.addEventListener('click', loadStudyCards);
  quizBtn.addEventListener('click', startQuiz);

  document.getElementById('study-prev-btn').addEventListener('click', function() { navigateCard(-1); });
  document.getElementById('study-next-btn').addEventListener('click', function() { navigateCard(1); });

  var card = document.getElementById('study-card');
  if (card) {
    card.addEventListener('click', flipCard);
    card.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flipCard(); }
    });
  }

  fetchStudyProgress();
}

async function loadStudyCards() {
  var deck = document.getElementById('study-deck-select').value;
  if (!deck) { alert('Please select a topic first'); return; }

  try {
    var response = await fetch('/api/study/cards/' + deck);
    var result = await response.json();
    if (result.data) {
      studyState.cards = result.data.cards || [];
      studyState.cardIndex = 0;
      studyState.isFlipped = false;
      document.getElementById('study-cards-view').classList.remove('hidden');
      document.getElementById('study-quiz-view').classList.add('hidden');
      document.getElementById('study-results').classList.add('hidden');
      renderStudyCard();
    }
  } catch (err) {
    console.error('Failed to load cards:', err);
  }
}

function renderStudyCard() {
  var card = studyState.cards[studyState.cardIndex];
  if (!card) return;

  var front = document.getElementById('study-card-front');
  var back = document.getElementById('study-card-back');
  var starFilled = '\u2605';
  var starEmpty = '\u2606';
  front.innerHTML = '<div class="card-difficulty">Difficulty: ' + starFilled.repeat(card.difficulty) + starEmpty.repeat(3 - card.difficulty) + '</div><div class="card-question">' + escapeHtml(card.front) + '</div>';
  back.innerHTML = '<div class="card-answer">' + highlightText(card.back) + '</div>';

  document.getElementById('study-card-inner').classList.remove('flipped');
  studyState.isFlipped = false;

  var counter = document.getElementById('study-card-counter');
  counter.textContent = (studyState.cardIndex + 1) + ' / ' + studyState.cards.length;

  document.getElementById('study-prev-btn').disabled = studyState.cardIndex === 0;
  document.getElementById('study-next-btn').disabled = studyState.cardIndex >= studyState.cards.length - 1;
}

function flipCard() {
  document.getElementById('study-card-inner').classList.toggle('flipped');
  studyState.isFlipped = !studyState.isFlipped;
}

function navigateCard(direction) {
  studyState.cardIndex += direction;
  studyState.cardIndex = Math.max(0, Math.min(studyState.cardIndex, studyState.cards.length - 1));
  renderStudyCard();
}

async function startQuiz() {
  var deck = document.getElementById('study-deck-select').value;
  if (!deck) { alert('Please select a topic first'); return; }

  try {
    var response = await fetch('/api/study/quiz', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deck: deck, num_questions: 5 }),
    });
    var result = await response.json();
    if (result.data) {
      studyState.quiz = result.data;
      studyState.quizIndex = 0;
      studyState.quizAnswers = [];
      document.getElementById('study-quiz-view').classList.remove('hidden');
      document.getElementById('study-cards-view').classList.add('hidden');
      document.getElementById('study-results').classList.add('hidden');
      renderQuizQuestion();
    }
  } catch (err) {
    console.error('Failed to start quiz:', err);
  }
}

function renderQuizQuestion() {
  var questions = studyState.quiz.questions || [];
  var q = questions[studyState.quizIndex];
  if (!q) return;

  var total = questions.length;
  var pct = ((studyState.quizIndex) / total * 100);
  document.getElementById('quiz-progress-fill').style.width = pct + '%';
  document.getElementById('quiz-question-num').textContent = 'Question ' + (studyState.quizIndex + 1) + ' of ' + total;

  var ctx = q.context || {};
  var ctxHtml = '';
  if (ctx.ticker) {
    ctxHtml = '<span class="hl-keyword">' + escapeHtml(ctx.ticker) + '</span>';
    if (ctx.indicator) ctxHtml += ' | ' + escapeHtml(ctx.indicator);
    if (ctx.value !== undefined) ctxHtml += ': <span class="hl-number">' + ctx.value + '</span>';
    ctxHtml += ' <span class="quiz-data-badge">Live Data</span>';
  }
  document.getElementById('quiz-context').innerHTML = ctxHtml;
  document.getElementById('quiz-question-text').innerHTML = highlightText(q.question);

  var optionsHtml = '';
  (q.options || []).forEach(function(opt, i) {
    optionsHtml += '<button type="button" class="quiz-option" data-index="' + i + '">' +
      '<span class="quiz-option-letter">' + String.fromCharCode(65 + i) + '</span>' +
      '<span>' + escapeHtml(opt) + '</span></button>';
  });
  document.getElementById('quiz-options').innerHTML = optionsHtml;
  document.getElementById('quiz-explanation').classList.add('hidden');
  document.getElementById('quiz-next-question').style.display = 'none';

  /* Attach click handlers */
  document.querySelectorAll('.quiz-option').forEach(function(btn) {
    btn.addEventListener('click', function() { handleQuizAnswer(parseInt(btn.getAttribute('data-index'))); });
  });
}

function handleQuizAnswer(selectedIndex) {
  var q = studyState.quiz.questions[studyState.quizIndex];
  var isCorrect = selectedIndex === q.correct_answer;
  studyState.quizAnswers.push(selectedIndex);

  /* Highlight correct/wrong */
  document.querySelectorAll('.quiz-option').forEach(function(btn, i) {
    btn.disabled = true;
    if (i === q.correct_answer) btn.classList.add('quiz-correct');
    if (i === selectedIndex && !isCorrect) btn.classList.add('quiz-wrong');
  });

  /* Show explanation */
  var expEl = document.getElementById('quiz-explanation');
  expEl.innerHTML = '<div class="quiz-exp-' + (isCorrect ? 'correct' : 'wrong') + '">' +
    '<strong>' + (isCorrect ? 'Correct!' : 'Incorrect') + '</strong>' +
    '<p>' + highlightText(q.explanation || '') + '</p>' +
    (q.data_source ? '<small class="quiz-data-source">Data: ' + escapeHtml(q.data_source) + '</small>' : '') +
    '</div>';
  expEl.classList.remove('hidden');

  /* Show next button */
  var nextBtn = document.getElementById('quiz-next-question');
  nextBtn.style.display = 'block';
  if (studyState.quizIndex >= studyState.quiz.questions.length - 1) {
    nextBtn.textContent = 'See Results';
    nextBtn.onclick = submitQuiz;
  } else {
    nextBtn.textContent = 'Next Question';
    nextBtn.onclick = function() {
      studyState.quizIndex++;
      renderQuizQuestion();
    };
  }
}

async function submitQuiz() {
  try {
    var response = await fetch('/api/study/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quiz_id: studyState.quiz.quiz_id, answers: studyState.quizAnswers }),
    });
    var result = await response.json();
    if (result.data) renderQuizResults(result.data);
  } catch (err) {
    console.error('Failed to score quiz:', err);
  }
}

function renderQuizResults(data) {
  var el = document.getElementById('study-results');
  el.classList.remove('hidden');
  document.getElementById('study-quiz-view').classList.add('hidden');

  var gradeClass = data.score_pct >= 80 ? 'hl-green' : data.score_pct >= 60 ? 'hl-blue' : 'hl-red';

  var html = '<div class="quiz-results-card">';
  html += '<div class="quiz-results-header">';
  html += '<div class="quiz-grade ' + gradeClass + '">' + escapeHtml(data.grade || 'N/A') + '</div>';
  html += '<div class="quiz-score"><span class="hl-number">' + data.correct + '</span> / <span class="hl-number">' + data.total_questions + '</span> correct</div>';
  html += '<div class="quiz-pct ' + gradeClass + '">' + (data.score_pct || 0).toFixed(0) + '%</div>';
  html += '</div>';

  /* Weak areas */
  if (data.weak_areas && data.weak_areas.length > 0) {
    html += '<div class="quiz-feedback"><h4>Areas to Improve</h4><ul>';
    data.weak_areas.forEach(function(area) {
      html += '<li class="hl-red">' + escapeHtml(area.replace(/_/g, ' ')) + '</li>';
    });
    html += '</ul></div>';
  }

  /* Strong areas */
  if (data.strong_areas && data.strong_areas.length > 0) {
    html += '<div class="quiz-feedback"><h4>Strong Areas</h4><ul>';
    data.strong_areas.forEach(function(area) {
      html += '<li class="hl-green">' + escapeHtml(area.replace(/_/g, ' ')) + '</li>';
    });
    html += '</ul></div>';
  }

  /* Recommendations */
  if (data.recommendations && data.recommendations.length > 0) {
    html += '<div class="quiz-feedback"><h4>Recommendations</h4><ul>';
    data.recommendations.forEach(function(rec) {
      html += '<li>' + escapeHtml(rec) + '</li>';
    });
    html += '</ul></div>';
  }

  html += '<button type="button" class="btn btn-primary btn-sm" onclick="startQuiz()">Try Again</button>';
  html += '</div>';
  el.innerHTML = html;

  fetchStudyProgress();
  updateSectionTimestamp('study');
}

async function fetchStudyProgress() {
  try {
    var response = await fetch('/api/study/progress');
    if (!response.ok) return;
    var result = await response.json();
    if (result.data) renderStudyProgress(result.data);
  } catch (err) {
    /* Progress not available yet */
  }
}

function renderStudyProgress(data) {
  /* Progress header */
  var progEl = document.getElementById('study-progress');
  if (progEl && data.total_quizzes > 0) {
    progEl.innerHTML = '<div class="study-progress-bar">' +
      '<div class="study-progress-stats">' +
      '<span>Quizzes: <span class="hl-number">' + data.total_quizzes + '</span></span>' +
      '<span>Accuracy: <span class="hl-number">' + (data.overall_accuracy || 0).toFixed(0) + '%</span></span>' +
      '<span>Streak: <span class="hl-number">' + (data.streak || 0) + '</span></span>' +
      '</div></div>';
  }

  /* Skills grid */
  var skillsGrid = document.getElementById('study-skills-grid');
  if (skillsGrid && data.by_deck) {
    var html = '';
    Object.entries(data.by_deck).forEach(function(entry) {
      var deck = entry[0];
      var stats = entry[1];
      var level = (data.skill_levels || {})[deck] || 'beginner';
      var levelClass = level === 'advanced' ? 'hl-green' : level === 'intermediate' ? 'hl-blue' : 'hl-red';
      var label = deck.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
      html += '<div class="study-skill-card">' +
        '<div class="study-skill-name">' + label + '</div>' +
        '<div class="study-skill-level ' + levelClass + '">' + level + '</div>' +
        '<div class="study-skill-accuracy">Accuracy: <span class="hl-number">' + (stats.accuracy || 0).toFixed(0) + '%</span></div>' +
        '<div class="study-skill-bar"><div class="study-skill-fill" style="width:' + (stats.accuracy || 0) + '%"></div></div>' +
        '</div>';
    });
    skillsGrid.innerHTML = html;
  }
}

/* ============================================================
   FACTOR ANALYSIS MODULE
   ============================================================ */

function initFactorAnalysis() {
  var analyzeBtn = document.getElementById('factors-analyze-btn');
  var tickerInput = document.getElementById('factors-ticker-input');
  var quickBtns = document.querySelectorAll('.factor-quick-btn');

  if (analyzeBtn) {
    analyzeBtn.addEventListener('click', function() {
      var ticker = (tickerInput ? tickerInput.value : '').toUpperCase().trim();
      if (ticker) runFactorAnalysis(ticker);
    });
  }
  if (tickerInput) {
    tickerInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        var ticker = tickerInput.value.toUpperCase().trim();
        if (ticker) runFactorAnalysis(ticker);
      }
    });
  }
  quickBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var ticker = btn.dataset.ticker;
      if (tickerInput) tickerInput.value = ticker;
      runFactorAnalysis(ticker);
    });
  });
}

function runFactorAnalysis(ticker) {
  var loading = document.getElementById('factors-loading');
  var results = document.getElementById('factors-results');
  var ts = document.getElementById('factors-timestamp');

  if (loading) loading.classList.remove('hidden');
  if (results) results.classList.add('hidden');

  fetch('/api/factors/' + ticker)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (loading) loading.classList.add('hidden');
      if (data.error && data.signal === 'ERROR') {
        showError('Factor analysis failed: ' + data.error);
        return;
      }
      renderFactorResults(data);
      if (results) results.classList.remove('hidden');
      if (ts) ts.textContent = new Date().toLocaleTimeString();
    })
    .catch(function(err) {
      if (loading) loading.classList.add('hidden');
      showError('Factor analysis error: ' + err.message);
    });
}

function renderFactorResults(data) {
  renderFactorCompositeHeader(data);
  renderFactorGroupBars(data);
  renderFactorDetailGrid(data);
  renderFactorRadarChart(data);
  renderFactorAttributionChart(data);
  renderFactorMacroGrid(data);
}

function renderFactorCompositeHeader(data) {
  var el = document.getElementById('factor-composite-header');
  if (!el) return;
  var score = data.composite || 0;
  var signal = data.signal || 'HOLD';
  var signalColors = {
    STRONG_BUY: '#16a34a', BUY: '#22c55e', HOLD: '#f59e0b',
    SELL: '#ef4444', STRONG_SELL: '#991b1b', ERROR: '#94a3b8'
  };
  var color = signalColors[signal] || '#94a3b8';
  var scoreBar = Math.round((score + 5) / 10 * 100);
  el.innerHTML =
    '<div class="factor-composite-card">' +
      '<div class="factor-composite-left">' +
        '<div class="factor-composite-ticker">' + escapeHtml(data.ticker) + '</div>' +
        '<div class="factor-composite-signal" style="color:' + color + '">' + signal.replace('_', ' ') + '</div>' +
        '<div class="factor-composite-desc">12-Factor Composite Score</div>' +
      '</div>' +
      '<div class="factor-composite-right">' +
        '<div class="factor-composite-score" style="color:' + color + '">' + score.toFixed(2) + '</div>' +
        '<div class="factor-composite-range">Range: -5 to +5</div>' +
        '<div class="factor-composite-bar-wrap"><div class="factor-composite-bar" style="width:' + scoreBar + '%;background:' + color + '"></div></div>' +
      '</div>' +
    '</div>';
}

function renderFactorGroupBars(data) {
  var el = document.getElementById('factor-group-bars');
  if (!el) return;
  var groups = data.group_scores || {};
  var labels = {
    momentum: 'Momentum 动量', value: 'Value 估值', quality: 'Quality 质量',
    growth: 'Growth 成长', volatility: 'Volatility 波动', sentiment: 'Sentiment 情绪',
    macro: 'Macro 宏观', economic: 'Economic 经济周期', industry: 'Industry 行业前景',
    risk_adjusted: 'Risk-Adj 风险调整', historical: 'Historical 历史类比', ml_adaptive: 'ML Adaptive 机器学习'
  };
  var html = '';
  Object.keys(labels).forEach(function(k) {
    var score = groups[k] != null ? groups[k] : 0;
    var pct = Math.round((score + 5) / 10 * 100);
    var color = score >= 1 ? '#22c55e' : score >= -1 ? '#f59e0b' : '#ef4444';
    html +=
      '<div class="factor-bar-row">' +
        '<div class="factor-bar-label">' + labels[k] + '</div>' +
        '<div class="factor-bar-track">' +
          '<div class="factor-bar-fill" style="width:' + pct + '%;background:' + color + '"></div>' +
          '<div class="factor-bar-center-line"></div>' +
        '</div>' +
        '<div class="factor-bar-score" style="color:' + color + '">' + (score >= 0 ? '+' : '') + score.toFixed(2) + '</div>' +
      '</div>';
  });
  el.innerHTML = html;
}

function renderFactorDetailGrid(data) {
  var el = document.getElementById('factor-detail-grid');
  if (!el) return;
  var groupOrder = ['momentum', 'value', 'quality', 'growth', 'volatility', 'sentiment', 'macro', 'economic', 'industry', 'risk_adjusted', 'historical', 'ml_adaptive'];
  var groups = data.groups || {};
  var generatedAt = data.generated_at || '';
  var html = '';

  /* Data retrieval timestamp banner */
  if (generatedAt) {
    var dt = new Date(generatedAt);
    var timeStr = dt.toLocaleString('en-HK', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false, timeZoneName: 'short'
    });
    html += '<div class="factor-data-timestamp">';
    html += 'Data Retrieved: <strong>' + escapeHtml(timeStr) + '</strong>';
    html += ' &middot; Cache TTL: 30 min &middot; Source: yfinance + FRED API';
    html += '</div>';
  }

  groupOrder.forEach(function(gKey) {
    var g = groups[gKey];
    if (!g) return;
    var label = (g.label || gKey) + ' ' + (g.label_cn || '');
    var composite = g.composite || 0;
    var color = composite >= 1 ? '#22c55e' : composite >= -1 ? '#f59e0b' : '#ef4444';
    var srcSummary = g.data_source_summary || '';
    html += '<div class="factor-detail-card">';
    html += '<div class="factor-detail-card-header">';
    html += '<span class="factor-detail-card-title">' + escapeHtml(label) + '</span>';
    html += '<span class="factor-detail-card-score" style="color:' + color + '">' + (composite >= 0 ? '+' : '') + composite.toFixed(2) + '</span>';
    html += '</div>';
    if (srcSummary) {
      html += '<div class="factor-source-summary">' + escapeHtml(srcSummary) + '</div>';
    }
    html += '<table class="factor-table"><thead><tr>';
    html += '<th>Factor 因子</th><th>Value 数值</th><th>Score 评分</th><th>Source 数据来源</th>';
    html += '</tr></thead><tbody>';
    (g.factors || []).forEach(function(f) {
      var sc = f.score || 0;
      var scColor = sc >= 1 ? '#22c55e' : sc >= -1 ? '#f59e0b' : '#ef4444';
      var valStr = f.value != null ? (f.value + (f.unit || '')) : 'N/A';
      var src = f.source || '';
      html += '<tr>';
      html += '<td><span title="' + escapeHtml(f.name_cn || '') + '">' + escapeHtml(f.name || '') + '</span></td>';
      html += '<td class="factor-table-val">' + escapeHtml(String(valStr)) + '</td>';
      html += '<td class="factor-table-score" style="color:' + scColor + '">' + (sc >= 0 ? '+' : '') + sc.toFixed(1) + '</td>';
      html += '<td class="factor-table-source">' + escapeHtml(src) + '</td>';
      html += '</tr>';
    });
    html += '</tbody></table></div>';
  });
  el.innerHTML = html;
}

function renderFactorRadarChart(data) {
  var canvas = document.getElementById('factor-radar-chart');
  if (!canvas) return;
  var scores = data.group_scores || {};
  var labels = ['Momentum\n动量', 'Value\n估值', 'Quality\n质量', 'Growth\n成长', 'Volatility\n波动', 'Sentiment\n情绪', 'Macro\n宏观', 'Economic\n经济', 'Industry\n行业', 'Risk-Adj\n风险调整', 'Historical\n历史类比', 'ML\n机器学习'];
  var values = [
    (scores.momentum || 0) + 5,
    (scores.value || 0) + 5,
    (scores.quality || 0) + 5,
    (scores.growth || 0) + 5,
    (scores.volatility || 0) + 5,
    (scores.sentiment || 0) + 5,
    (scores.macro || 0) + 5,
    (scores.economic || 0) + 5,
    (scores.industry || 0) + 5,
    (scores.risk_adjusted || 0) + 5,
    (scores.historical || 0) + 5,
    (scores.ml_adaptive || 0) + 5,
  ];
  if (window._factorRadarChart) { window._factorRadarChart.destroy(); }
  window._factorRadarChart = new Chart(canvas, {
    type: 'radar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Factor Score',
        data: values,
        backgroundColor: 'rgba(59, 130, 246, 0.2)',
        borderColor: 'rgba(59, 130, 246, 0.9)',
        borderWidth: 2,
        pointBackgroundColor: 'rgba(59, 130, 246, 1)',
        pointRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        r: {
          min: 0, max: 10,
          ticks: { stepSize: 2, display: false },
          grid: { color: 'rgba(148,163,184,0.2)' },
          pointLabels: { font: { size: 11 }, color: '#94a3b8' }
        }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function renderFactorAttributionChart(data) {
  var canvas = document.getElementById('factor-attribution-chart');
  if (!canvas) return;
  var scores = data.group_scores || {};
  var weights = data.weights || {};
  var labels = ['Momentum', 'Value', 'Quality', 'Growth', 'Volatility', 'Sentiment', 'Macro', 'Economic', 'Industry', 'Risk-Adj', 'Historical', 'ML Adaptive'];
  var keys = ['momentum', 'value', 'quality', 'growth', 'volatility', 'sentiment', 'macro', 'economic', 'industry', 'risk_adjusted', 'historical', 'ml_adaptive'];
  var contributions = keys.map(function(k) {
    return parseFloat(((scores[k] || 0) * (weights[k] || 0)).toFixed(3));
  });
  var colors = contributions.map(function(v) {
    return v >= 0 ? 'rgba(34, 197, 94, 0.8)' : 'rgba(239, 68, 68, 0.8)';
  });
  if (window._factorAttrChart) { window._factorAttrChart.destroy(); }
  window._factorAttrChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Weighted Contribution',
        data: contributions,
        backgroundColor: colors,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      scales: {
        x: {
          grid: { color: 'rgba(148,163,184,0.1)' },
          ticks: { color: '#94a3b8' }
        },
        y: { ticks: { color: '#94a3b8' } }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) { return 'Contribution: ' + (ctx.raw >= 0 ? '+' : '') + ctx.raw.toFixed(3); }
          }
        }
      }
    }
  });
}

function renderFactorMacroGrid(data) {
  var el = document.getElementById('factor-macro-grid');
  if (!el) return;
  var macroGroup = (data.groups || {}).macro || {};
  var factors = macroGroup.factors || [];
  var html = '';
  factors.forEach(function(f) {
    var sc = f.score || 0;
    var color = sc >= 1 ? '#22c55e' : sc >= -1 ? '#f59e0b' : '#ef4444';
    html +=
      '<div class="factor-macro-card">' +
        '<div class="factor-macro-name">' + escapeHtml(f.name) + '</div>' +
        '<div class="factor-macro-name-cn">' + escapeHtml(f.name_cn || '') + '</div>' +
        '<div class="factor-macro-value">' + (f.value != null ? f.value + (f.unit || '') : 'N/A') + '</div>' +
        '<div class="factor-macro-score" style="color:' + color + '">' + (sc >= 0 ? '+' : '') + sc.toFixed(1) + '</div>' +
      '</div>';
  });
  if (!html) html = '<p style="color:#94a3b8;font-size:0.875rem;">Macro factors calculated from market data.</p>';
  el.innerHTML = html;
}

/* ============================================================
   DATA PROVIDER STATUS
   ============================================================ */
function fetchProviderStatus() {
  fetch('/api/providers')
    .then(function(r) { return r.json(); })
    .then(function(resp) {
      renderProviderStatus(resp.data || []);
      updateSectionTimestamp('providers');
    })
    .catch(function() {});
}

function renderProviderStatus(providers) {
  var el = document.getElementById('providers-grid');
  if (!el) return;
  var html = '<div class="provider-status-grid">';
  providers.forEach(function(p) {
    var statusClass = p.available ? 'provider-online' : 'provider-offline';
    var statusText = p.available ? 'Online' : 'No API Key';
    var dot = p.available ? '\u25CF' : '\u25CB';
    html +=
      '<div class="provider-card ' + statusClass + '">' +
        '<div class="provider-dot">' + dot + '</div>' +
        '<div class="provider-info">' +
          '<div class="provider-name">' + escapeHtml(p.name) + '</div>' +
          '<div class="provider-status-text">' + statusText + '</div>' +
        '</div>' +
      '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

/* ============================================================
   ALTERNATIVE DATA (SHORT INTEREST, INSIDER, CONGRESSIONAL, DARK POOL)
   ============================================================ */
function initAltData() {
  var btn = document.getElementById('alt-data-load-btn');
  var input = document.getElementById('alt-data-ticker');
  if (btn) {
    btn.addEventListener('click', function() {
      var ticker = (input && input.value || '').trim().toUpperCase();
      if (ticker) fetchAltData(ticker);
    });
  }
  if (input) {
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        var ticker = input.value.trim().toUpperCase();
        if (ticker) fetchAltData(ticker);
      }
    });
  }
}

async function fetchAltData(ticker) {
  var grid = document.getElementById('alt-data-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="alt-data-loading"><div class="ai-spinner"></div><span>Loading alternative data for ' + escapeHtml(ticker) + '...</span></div>';

  try {
    var resp = await fetch('/api/alt-data/' + encodeURIComponent(ticker));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var result = await resp.json();
    renderAltData(result.data, ticker);
    updateSectionTimestamp('alt-data');
  } catch (err) {
    grid.innerHTML = '<p style="color:var(--accent-red);font-size:0.875rem;">Failed to load alt data: ' + escapeHtml(err.message) + '</p>';
  }
}

function renderAltData(data, ticker) {
  var grid = document.getElementById('alt-data-grid');
  if (!grid || !data) return;
  var html = '<div class="alt-data-ticker-header">' + escapeHtml(ticker) + ' \u2014 Alternative Data Signals</div>';
  html += '<div class="alt-data-cards">';

  // Short Interest Card
  var si = data.short_interest;
  if (si && si.data && si.data.length) {
    var latest = si.data[0];
    var ratio = latest.shortVolumeRatio != null ? (latest.shortVolumeRatio * 100).toFixed(1) + '%' : 'N/A';
    var svol = latest.shortVolume != null ? formatNumber(latest.shortVolume) : 'N/A';
    var tvol = latest.totalVolume != null ? formatNumber(latest.totalVolume) : 'N/A';
    html +=
      '<div class="alt-card alt-card--short">' +
        '<div class="alt-card-header">' +
          '<span class="alt-card-icon" aria-hidden="true">&#x1F4C9;</span>' +
          '<span class="alt-card-title">Short Interest</span>' +
          '<span class="alt-card-source">Fintel</span>' +
        '</div>' +
        '<div class="alt-card-metric">' +
          '<span class="alt-card-value">' + ratio + '</span>' +
          '<span class="alt-card-label">Short Volume Ratio</span>' +
        '</div>' +
        '<div class="alt-card-details">' +
          '<div class="alt-detail"><span>Short Volume</span><span>' + svol + '</span></div>' +
          '<div class="alt-detail"><span>Total Volume</span><span>' + tvol + '</span></div>' +
          '<div class="alt-detail"><span>Date</span><span>' + escapeHtml(latest.marketDate || '') + '</span></div>' +
        '</div>' +
        renderShortInterestChart(si.data) +
      '</div>';
  }

  // Insider Trades Card
  var ins = data.insider_trades;
  if (ins) {
    var ownership = ins.insiderOwnershipPercentFloat != null ? (ins.insiderOwnershipPercentFloat * 100).toFixed(2) + '%' : 'N/A';
    var insiders = ins.insiders || [];
    var buys = insiders.filter(function(i) { return i.code === 'Purchase' || i.code === 'P'; }).length;
    var sells = insiders.filter(function(i) { return i.code === 'Sale' || i.code === 'S'; }).length;
    var gifts = insiders.filter(function(i) { return i.code === 'Gift'; }).length;
    html +=
      '<div class="alt-card alt-card--insider">' +
        '<div class="alt-card-header">' +
          '<span class="alt-card-icon" aria-hidden="true">&#x1F464;</span>' +
          '<span class="alt-card-title">Insider Activity</span>' +
          '<span class="alt-card-source">Fintel</span>' +
        '</div>' +
        '<div class="alt-card-metric">' +
          '<span class="alt-card-value">' + ownership + '</span>' +
          '<span class="alt-card-label">Insider Ownership</span>' +
        '</div>' +
        '<div class="alt-card-details">' +
          '<div class="alt-detail"><span>Purchases</span><span class="alt-buy">' + buys + '</span></div>' +
          '<div class="alt-detail"><span>Sales</span><span class="alt-sell">' + sells + '</span></div>' +
          '<div class="alt-detail"><span>Gifts</span><span>' + gifts + '</span></div>' +
          '<div class="alt-detail"><span>Total Transactions</span><span>' + insiders.length + '</span></div>' +
        '</div>' +
        renderInsiderTimeline(insiders.slice(0, 8)) +
      '</div>';
  }

  // Congressional Trades Card
  var congress = data.congressional_trades;
  if (congress && congress.length) {
    var cBuys = congress.filter(function(c) { return c.Transaction === 'Purchase'; }).length;
    var cSells = congress.filter(function(c) { return c.Transaction === 'Sale'; }).length;
    html +=
      '<div class="alt-card alt-card--congress">' +
        '<div class="alt-card-header">' +
          '<span class="alt-card-icon" aria-hidden="true">&#x1F3DB;</span>' +
          '<span class="alt-card-title">Congressional Trading</span>' +
          '<span class="alt-card-source">Quiver Quant</span>' +
        '</div>' +
        '<div class="alt-card-metric">' +
          '<span class="alt-card-value">' + congress.length + '</span>' +
          '<span class="alt-card-label">Total Trades</span>' +
        '</div>' +
        '<div class="alt-card-details">' +
          '<div class="alt-detail"><span>Purchases</span><span class="alt-buy">' + cBuys + '</span></div>' +
          '<div class="alt-detail"><span>Sales</span><span class="alt-sell">' + cSells + '</span></div>' +
        '</div>' +
        renderCongressionalTable(congress.slice(0, 6)) +
      '</div>';
  }

  // Dark Pool Card
  var dp = data.dark_pool;
  if (dp && dp.length) {
    var latestDp = dp[0];
    html +=
      '<div class="alt-card alt-card--darkpool">' +
        '<div class="alt-card-header">' +
          '<span class="alt-card-icon" aria-hidden="true">&#x1F311;</span>' +
          '<span class="alt-card-title">Dark Pool Activity</span>' +
          '<span class="alt-card-source">Quiver Quant</span>' +
        '</div>' +
        '<div class="alt-card-metric">' +
          '<span class="alt-card-value">' + (latestDp.ShortVolume ? formatNumber(latestDp.ShortVolume) : formatNumber(latestDp.Volume || 0)) + '</span>' +
          '<span class="alt-card-label">Latest Dark Pool Volume</span>' +
        '</div>' +
        '<div class="alt-card-details">' +
          '<div class="alt-detail"><span>Date</span><span>' + escapeHtml(latestDp.Date || latestDp.date || '') + '</span></div>' +
        '</div>' +
      '</div>';
  }

  html += '</div>';

  // No data message
  if (!si && !ins && !congress && !dp) {
    html += '<p style="color:var(--text-muted);font-size:0.875rem;">No alternative data available for ' + escapeHtml(ticker) + '.</p>';
  }

  grid.innerHTML = html;
}

function renderShortInterestChart(data) {
  if (!data || data.length < 2) return '';
  var reversed = data.slice().reverse();
  var maxRatio = Math.max.apply(null, reversed.map(function(d) { return d.shortVolumeRatio || 0; }));
  if (maxRatio === 0) maxRatio = 1;
  var bars = reversed.map(function(d) {
    var h = Math.round((d.shortVolumeRatio / maxRatio) * 40);
    var color = d.shortVolumeRatio > 0.3 ? 'var(--accent-red)' : d.shortVolumeRatio > 0.15 ? 'var(--accent-gold)' : 'var(--accent-blue)';
    return '<div class="si-bar" style="height:' + h + 'px;background:' + color + ';" title="' + d.marketDate + ': ' + (d.shortVolumeRatio * 100).toFixed(1) + '%"></div>';
  }).join('');
  return '<div class="si-chart" role="img" aria-label="10-day short volume trend chart"><div class="si-bars">' + bars + '</div><div class="si-chart-label">10-Day Short Volume Trend</div></div>';
}

function renderInsiderTimeline(insiders) {
  if (!insiders || !insiders.length) return '';
  var html = '<div class="insider-timeline" role="list" aria-label="Recent insider transactions">';
  insiders.forEach(function(ins) {
    var typeClass = (ins.code === 'Purchase' || ins.code === 'P') ? 'insider-buy' : (ins.code === 'Sale' || ins.code === 'S') ? 'insider-sell' : 'insider-other';
    var val = ins.value ? '$' + formatNumber(ins.value) : '';
    html +=
      '<div class="insider-entry ' + typeClass + '" role="listitem">' +
        '<span class="insider-date">' + escapeHtml(ins.transactionDate || ins.fileDate || '') + '</span>' +
        '<span class="insider-name">' + escapeHtml(ins.name || '') + '</span>' +
        '<span class="insider-action">' + escapeHtml(ins.code || '') + '</span>' +
        '<span class="insider-shares">' + formatNumber(Math.abs(ins.shares || 0)) + ' shares</span>' +
        (val ? '<span class="insider-value">' + val + '</span>' : '') +
      '</div>';
  });
  html += '</div>';
  return html;
}

function renderCongressionalTable(trades) {
  if (!trades || !trades.length) return '';
  var html = '<div class="congress-table" role="list" aria-label="Recent congressional trades">';
  trades.forEach(function(t) {
    var txnClass = t.Transaction === 'Purchase' ? 'alt-buy' : 'alt-sell';
    html +=
      '<div class="congress-row" role="listitem">' +
        '<span class="congress-rep">' + escapeHtml(t.Representative || '') + '</span>' +
        '<span class="congress-party">(' + escapeHtml(t.Party ? t.Party.charAt(0) : '') + ')</span>' +
        '<span class="congress-txn ' + txnClass + '">' + escapeHtml(t.Transaction || '') + '</span>' +
        '<span class="congress-range">' + escapeHtml(t.Range || '') + '</span>' +
        '<span class="congress-date">' + escapeHtml(t.TransactionDate || '') + '</span>' +
      '</div>';
  });
  html += '</div>';
  return html;
}

function formatNumber(num) {
  if (num == null) return 'N/A';
  if (typeof num !== 'number') num = parseFloat(num);
  if (isNaN(num)) return 'N/A';
  if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(2) + 'B';
  if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(2) + 'M';
  if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(1) + 'K';
  return num.toLocaleString();
}

/* ============================================================
   Initialization
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {
  initI18n();
  cacheDom();

  /* Initialize tabs */
  initTabs();

  /* Initialize section refresh buttons */
  initSectionRefresh();

  /* Start live clock */
  updateClock();
  setInterval(updateClock, 1000);

  /* Wire up event listeners */
  if (dom.langBtn) dom.langBtn.addEventListener('click', handleLangToggle);
  if (dom.showMoreBtn) dom.showMoreBtn.addEventListener('click', handleShowMore);
  if (dom.toggleConsensus) {
    dom.toggleConsensus.addEventListener('click', function () {
      handleViewToggle('consensus');
    });
    dom.toggleConsensus.classList.add('active');
  }
  if (dom.toggleSingleday) {
    dom.toggleSingleday.addEventListener('click', function () {
      handleViewToggle('singleday');
    });
  }

  document.documentElement.lang = getLang() === 'cn' ? 'zh-CN' : 'en';

  /* Fetch data */
  fetchPredictions();
  initAiAnalysis();
  initFactorAnalysis();
  fetchMarketSentiment();
  fetchMarketLive();
  fetchMacroData();
  fetchOverviewNews();
  fetchMarketNewsFeed();
  checkIbkrConnection();

  /* Initialize trading and options */
  initTrading();
  initOptions();

  /* Initialize auto trading */
  initAutoTrading();

  /* Fetch economic calendar */
  fetchEconomicCalendar();

  /* Fetch data provider status */
  fetchProviderStatus();

  /* Initialize alternative data */
  initAltData();
  fetchAltData('AAPL');

  /* Initialize study cards */
  initStudyCards();

  /* Start auto-refresh */
  startAutoRefresh();

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      stopAutoRefresh();
    } else {
      startAutoRefresh();
    }
  });

  /* Load Model 2 cached predictions on startup */
  loadModel2Predictions();
  loadModelComparison();
});

/* ============================================================
   Model 2: Sentiment & Market Agent
   ============================================================ */

let model2Data = null;

async function runModel2Scan() {
  var btn = document.getElementById('model2-scan-btn');
  var status = document.getElementById('model2-scan-status');
  if (!btn || !status) return;

  btn.disabled = true;
  btn.textContent = 'Scanning...';
  status.textContent = 'Running 5-step pipeline (this may take 1-2 minutes)...';
  status.style.color = 'var(--accent)';

  try {
    var response = await fetch('/api/model2/scan', { method: 'POST' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    var result = await response.json();
    if (result.error) throw new Error(result.error.message || 'Scan failed');

    model2Data = result.data;
    renderModel2Predictions(model2Data);
    renderModel2Stats(model2Data);
    renderModel2PostMortem(model2Data.post_mortem);
    status.textContent = 'Scan complete at ' + new Date().toLocaleTimeString();
    status.style.color = 'var(--green)';

    /* Refresh comparison after new scan */
    loadModelComparison();
  } catch (err) {
    console.error('Model 2 scan failed:', err);
    status.textContent = 'Scan failed: ' + err.message;
    status.style.color = 'var(--red, #ef4444)';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Sentiment Scan';
  }
}

async function loadModel2Predictions() {
  try {
    var response = await fetch('/api/model2/predictions');
    if (!response.ok) return;
    var result = await response.json();
    if (!result.data) return;

    model2Data = result.data;
    renderModel2Predictions(model2Data);
    renderModel2Stats(model2Data);
    renderModel2PostMortem(model2Data.post_mortem);
  } catch (err) {
    console.error('Failed to load Model 2 predictions:', err);
  }
}

function renderModel2Stats(data) {
  var statsEl = document.getElementById('model2-scan-stats');
  if (!statsEl || !data) return;

  var scan = data.scan_results || {};
  var predictions = data.predictions || [];
  var pm = data.post_mortem || {};

  document.getElementById('m2-scanned').textContent = scan.total_scanned || 0;
  document.getElementById('m2-shortlisted').textContent = scan.shortlisted || 0;
  document.getElementById('m2-signals').textContent = predictions.length;
  document.getElementById('m2-hitrate').textContent =
    pm.hit_rate != null ? (pm.hit_rate * 100).toFixed(1) + '%' : '--';

  statsEl.style.display = 'block';
}

function renderModel2Predictions(data) {
  var container = document.getElementById('model2-predictions-container');
  if (!container) return;

  var predictions = (data && data.predictions) || [];
  if (!predictions.length) {
    container.innerHTML =
      '<p style="color:var(--text-muted);text-align:center;padding:2rem;">No trade signals yet. Run a scan to generate predictions.</p>';
    return;
  }

  var html = '<div style="overflow-x:auto;">' +
    '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">' +
    '<thead><tr style="border-bottom:2px solid var(--border);text-align:left;">' +
    '<th style="padding:0.5rem;">Ticker</th>' +
    '<th style="padding:0.5rem;">Direction</th>' +
    '<th style="padding:0.5rem;">Confidence</th>' +
    '<th style="padding:0.5rem;">Edge</th>' +
    '<th style="padding:0.5rem;">Sentiment</th>' +
    '<th style="padding:0.5rem;">R:R</th>' +
    '<th style="padding:0.5rem;">Position %</th>' +
    '<th style="padding:0.5rem;">Entry</th>' +
    '<th style="padding:0.5rem;">Stop</th>' +
    '<th style="padding:0.5rem;">Target</th>' +
    '</tr></thead><tbody>';

  predictions.forEach(function (p) {
    var dirColor = p.direction === 'LONG' ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
    var dirIcon = p.direction === 'LONG' ? '&#9650;' : '&#9660;';
    var confBar = Math.min(p.confidence || 0, 10);
    var confColor = confBar >= 7 ? 'var(--green, #22c55e)' : confBar >= 4 ? 'var(--yellow, #eab308)' : 'var(--red, #ef4444)';

    html += '<tr style="border-bottom:1px solid var(--border);">' +
      '<td style="padding:0.5rem;font-weight:600;">' + escapeHtml(p.ticker) +
        '<div style="font-size:0.75rem;color:var(--text-muted);">' + escapeHtml(p.name || '') + '</div></td>' +
      '<td style="padding:0.5rem;color:' + dirColor + ';font-weight:600;">' + dirIcon + ' ' + escapeHtml(p.direction) + '</td>' +
      '<td style="padding:0.5rem;">' +
        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
        '<div style="width:60px;height:6px;background:var(--border);border-radius:3px;overflow:hidden;">' +
        '<div style="width:' + (confBar * 10) + '%;height:100%;background:' + confColor + ';border-radius:3px;"></div></div>' +
        '<span>' + confBar + '/10</span></div></td>' +
      '<td style="padding:0.5rem;color:' + dirColor + ';">' + (p.edge_pct > 0 ? '+' : '') + (p.edge_pct || 0).toFixed(1) + '%</td>' +
      '<td style="padding:0.5rem;">' + (p.sentiment_score || 0).toFixed(2) + '</td>' +
      '<td style="padding:0.5rem;">' + (p.risk_reward || 0).toFixed(1) + ':1</td>' +
      '<td style="padding:0.5rem;">' + (p.position_size_pct || 0).toFixed(1) + '%</td>' +
      '<td style="padding:0.5rem;">$' + (p.current_price || 0).toFixed(2) + '</td>' +
      '<td style="padding:0.5rem;color:var(--red, #ef4444);">$' + (p.stop_loss || 0).toFixed(2) + '</td>' +
      '<td style="padding:0.5rem;color:var(--green, #22c55e);">$' + (p.take_profit || 0).toFixed(2) + '</td>' +
      '</tr>';

    /* Entry reason row */
    if (p.entry_reason) {
      html += '<tr style="border-bottom:1px solid var(--border);">' +
        '<td colspan="10" style="padding:0.25rem 0.5rem 0.5rem;font-size:0.78rem;color:var(--text-muted);">' +
        '&#x1F4AC; ' + escapeHtml(p.entry_reason) + '</td></tr>';
    }
  });

  html += '</tbody></table></div>';

  if (data.generated_at) {
    html += '<p style="font-size:0.75rem;color:var(--text-muted);margin-top:0.75rem;">Generated: ' +
      escapeHtml(data.generated_at) + '</p>';
  }

  container.innerHTML = html;
}

function renderModel2PostMortem(pm) {
  var el = document.getElementById('model2-postmortem');
  if (!el) return;

  if (!pm || (!pm.total_past && !pm.evaluated)) {
    el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:1rem;">No historical data yet. Run scans to build track record.</p>';
    return;
  }

  var hitColor = (pm.hit_rate || 0) >= 0.5 ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
  var avgColor = (pm.avg_return || 0) >= 0 ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';

  var html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.75rem;">' +
    '<div class="stat-card"><div class="stat-value">' + (pm.total_past || 0) + '</div><div class="stat-label">Total Predictions</div></div>' +
    '<div class="stat-card"><div class="stat-value">' + (pm.evaluated || 0) + '</div><div class="stat-label">Evaluated</div></div>' +
    '<div class="stat-card"><div class="stat-value" style="color:' + hitColor + ';">' + ((pm.hit_rate || 0) * 100).toFixed(1) + '%</div><div class="stat-label">Hit Rate</div></div>' +
    '<div class="stat-card"><div class="stat-value" style="color:' + avgColor + ';">' + (pm.avg_return >= 0 ? '+' : '') + (pm.avg_return || 0).toFixed(2) + '%</div><div class="stat-label">Avg Return</div></div>' +
    '</div>';

  if (pm.best_trade) {
    html += '<p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.75rem;">Best: ' + escapeHtml(pm.best_trade) + '</p>';
  }
  if (pm.worst_trade) {
    html += '<p style="font-size:0.8rem;color:var(--text-muted);">Worst: ' + escapeHtml(pm.worst_trade) + '</p>';
  }

  el.innerHTML = html;
}

async function loadModelComparison() {
  var container = document.getElementById('model-compare-container');
  if (!container) return;

  try {
    var response = await fetch('/api/models/compare');
    if (!response.ok) throw new Error('HTTP ' + response.status);
    var result = await response.json();
    if (!result.data) return;

    renderModelComparison(result.data, container);
  } catch (err) {
    console.error('Failed to load model comparison:', err);
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:1rem;">Could not load comparison data.</p>';
  }
}

function renderModelComparison(data, container) {
  var comparison = data.comparison || [];
  if (!comparison.length) {
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:1rem;">No comparison data available. Need predictions from both models.</p>';
    return;
  }

  var html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.75rem;margin-bottom:1rem;">' +
    '<div class="stat-card"><div class="stat-value">' + (data.model1_count || 0) + '</div><div class="stat-label">Model 1 Signals</div></div>' +
    '<div class="stat-card"><div class="stat-value">' + (data.model2_count || 0) + '</div><div class="stat-label">Model 2 Signals</div></div>' +
    '<div class="stat-card"><div class="stat-value">' + (data.both_models || 0) + '</div><div class="stat-label">Overlap</div></div>' +
    '</div>';

  html += '<div style="overflow-x:auto;">' +
    '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">' +
    '<thead><tr style="border-bottom:2px solid var(--border);text-align:left;">' +
    '<th style="padding:0.5rem;">Ticker</th>' +
    '<th style="padding:0.5rem;">Model 1 (LightGBM)</th>' +
    '<th style="padding:0.5rem;">Model 2 (Sentiment)</th>' +
    '<th style="padding:0.5rem;">Agreement</th>' +
    '</tr></thead><tbody>';

  comparison.forEach(function (c) {
    var m1Html = '--';
    var m2Html = '--';
    var agreeHtml = '<span style="color:var(--text-muted);">N/A</span>';

    if (c.model1) {
      var m1Color = c.model1.trend === 'up' ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
      m1Html = '<span style="color:' + m1Color + ';font-weight:600;">' +
        (c.model1.trend === 'up' ? '&#9650; Bullish' : '&#9660; Bearish') +
        '</span><div style="font-size:0.75rem;color:var(--text-muted);">Signal: ' +
        (c.model1.signal * 100).toFixed(2) + '% | Score: ' + (c.model1.combined_score || 0).toFixed(2) + '</div>';
    }

    if (c.model2) {
      var m2Color = c.model2.direction === 'LONG' ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
      m2Html = '<span style="color:' + m2Color + ';font-weight:600;">' +
        (c.model2.direction === 'LONG' ? '&#9650; LONG' : '&#9660; SHORT') +
        '</span><div style="font-size:0.75rem;color:var(--text-muted);">Conf: ' +
        (c.model2.confidence || 0) + '/10 | Edge: ' + (c.model2.edge_pct || 0).toFixed(1) + '%</div>';
    }

    if (c.models_agree !== undefined) {
      agreeHtml = c.models_agree
        ? '<span style="color:var(--green, #22c55e);font-weight:600;">&#10003; Agree</span>'
        : '<span style="color:var(--yellow, #eab308);font-weight:600;">&#10007; Disagree</span>';
    }

    html += '<tr style="border-bottom:1px solid var(--border);">' +
      '<td style="padding:0.5rem;font-weight:600;">' + escapeHtml(c.ticker) + '</td>' +
      '<td style="padding:0.5rem;">' + m1Html + '</td>' +
      '<td style="padding:0.5rem;">' + m2Html + '</td>' +
      '<td style="padding:0.5rem;">' + agreeHtml + '</td>' +
      '</tr>';
  });

  html += '</tbody></table></div>';
  container.innerHTML = html;
}
