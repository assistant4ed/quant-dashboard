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

var SECTION_ICONS = {
  shortInterest: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="2,4 6,8 10,6 14,12"/></svg>',
  insider: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="5" r="3"/><path d="M2,14 Q2,10 8,10 Q14,10 14,14"/></svg>',
  congress: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3,14 L3,7 M8,14 L8,7 M13,14 L13,7 M1,7 L15,7 M8,2 L2,7 L14,7 Z"/></svg>',
  darkPool: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2"/></svg>',
  calendar: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="1.5"/><line x1="2" y1="7" x2="14" y2="7"/><line x1="5" y1="1" x2="5" y2="5"/><line x1="11" y1="1" x2="11" y2="5"/></svg>',
  provider: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="10" rx="2"/><circle cx="5" cy="8" r="1" fill="currentColor"/><line x1="8" y1="7" x2="12" y2="7"/><line x1="8" y1="10" x2="11" y2="10"/></svg>',
  signal: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2,12 L5,5 L8,9 L11,3 L14,8"/></svg>',
};

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
let newsAutoRefreshTimer = null;
let newsLastUpdated = null;
let newsNextRefresh = null;
let activeAnalysisMethod = 'ai';

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
  var clockLangMap = { en: 'en-US', tc: 'zh-TW', sc: 'zh-CN' };
  var lang = (typeof getLang === 'function') ? (clockLangMap[getLang()] || 'en-US') : 'en-US';

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

  /* Trigger chart resize when switching to AI tab (contains charts) */
  if (tabId === 'ai' && typeof Chart !== 'undefined') {
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
    var langLabels = { en: 'EN', tc: '\u7E41\u4E2D', sc: '\u7B80\u4E2D' };
    dom.langBtn.textContent = langLabels[getLang()] || 'EN';
    dom.langBtn.setAttribute('aria-label', 'Switch language');
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
    { key: 'SP500',       label: 'S&P 500',   icon: '' },
    { key: 'NASDAQ',      label: 'NASDAQ',     icon: '' },
    { key: 'DOW',         label: 'DOW',        icon: '' },
    { key: 'RUSSELL2000', label: 'RUT',        icon: '' },
    { key: 'VIX',         label: 'VIX',        icon: '' },
    { key: 'GOLD',        label: 'Gold',       icon: '' },
    { key: 'OIL',         label: 'Oil',        icon: '' },
    { key: 'TREASURY10Y', label: '10Y Yield',  icon: '' },
    { key: 'BTC',         label: 'Bitcoin',    icon: '' },
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
      var filtered = articles.filter(isFinanceNews);
      filtered.sort(function(a, b) { return scoreArticle(b) - scoreArticle(a); });
      renderOverviewNews(filtered);
      newsLastUpdated = new Date();
      updateNewsRefreshStatus();
      var ts = document.getElementById('overview-news-timestamp');
      if (ts) ts.textContent = 'Updated: ' + formatTimeET(newsLastUpdated);
    })
    .catch(function () {});
}

function renderOverviewNews(articles) {
  var el = document.getElementById('overview-news-grid');
  if (!el) return;
  if (!articles || !articles.length) {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:0.875rem;">No recent finance news available.</p>';
    return;
  }

  var html = '';
  articles.slice(0, 12).forEach(function (a) {
    var title = escapeHtml(a.title || 'No title');
    var summary = escapeHtml((a.summary || '').substring(0, 200));
    var source = escapeHtml(a.source || '');
    var url = a.url || '#';
    var pubDate = '';
    var pubDateFull = '';
    if (a.publishedAt) {
      try {
        var d = new Date(a.publishedAt);
        pubDate = formatArticleDateET(d);
        pubDateFull = d.toLocaleString('en-US', {
          timeZone: 'America/New_York',
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true,
        }) + ' ET';
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
        '</div>' +
        '<div class="overview-news-date-prominent" title="' + escapeHtml(pubDateFull) + '">' + pubDate + '</div>' +
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
      var filtered = articles.filter(isFinanceNews);
      if (!filtered.length) {
        feed.innerHTML = '<p style="color:var(--text-muted);font-size:0.875rem;">No recent finance news available.</p>';
        return;
      }
      var html = '';
      filtered.slice(0, 20).forEach(function (a) {
        var title = escapeHtml(a.title || 'No title');
        var summary = escapeHtml((a.summary || '').substring(0, 180));
        var source = escapeHtml(a.source || '');
        var url = a.url || '#';
        var pubDate = '';
        if (a.publishedAt) {
          try {
            var d = new Date(a.publishedAt);
            pubDate = formatArticleDateET(d);
          } catch (e) {}
        }
        html +=
          '<a class="overview-news-card" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer" style="display:block;margin-bottom:0.75rem;">' +
            '<div class="overview-news-meta">' +
              '<span class="overview-news-source">' + source + '</span>' +
              (pubDate ? '<span class="overview-news-date-badge">' + pubDate + '</span>' : '') +
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

/* ============================================================
   News Helpers: Finance Filter, Date Formatting, Auto-Refresh
   ============================================================ */

var FINANCE_KEYWORDS = [
  'stock', 'market', 'trade', 'invest', 'earning', 'revenue', 'profit',
  'loss', 'fed', 'rate', 'inflation', 'gdp', 'bond', 'treasury', 'sp500',
  's&p', 'nasdaq', 'dow', 'ipo', 'merger', 'acquisition', 'dividend',
  'buyback', 'forecast', 'outlook', 'bull', 'bear', 'rally', 'crash',
  'sell-off', 'volatil', 'crypto', 'bitcoin', 'oil', 'gold', 'commodity',
  'tech', 'bank', 'financ', 'economy', 'tariff', 'cpi', 'pce', 'jobs',
  'employment', 'retail', 'housing', 'sec', 'regulation', 'wall street',
  'hedge fund', 'etf', 'mutual fund', 'analyst', 'upgrade', 'downgrade',
  'guidance', 'sector', 'index', 'futures', 'options', 'short', 'margin',
];

var HIGH_IMPACT_KEYWORDS = [
  'war', 'conflict', 'iran', 'military', 'strike', 'sanction', 'tariff',
  'fed rate', 'rate cut', 'rate hike', 'fomc', 'central bank', 'powell',
  'cpi', 'pce', 'jobs report', 'nonfarm', 'unemployment', 'gdp',
  'recession', 'default', 'debt ceiling', 'shutdown', 'election',
  'crash', 'crisis', 'pandemic', 'inflation report',
  'geopolitic', 'nato', 'china', 'russia', 'ukraine', 'taiwan',
  'opec', 'oil embargo', 'nuclear', 'missile',
];

var FINANCE_SOURCES = [
  'bloomberg', 'reuters', 'cnbc', 'wsj', 'ft', 'barron', 'marketwatch',
  'seeking alpha', 'investopedia', 'yahoo finance', 'benzinga', 'thestreet',
  'motley', 'zacks',
];

function scoreArticle(article) {
  var title = (article.title || '').toLowerCase();
  var summary = (article.summary || '').toLowerCase();
  var source = (article.source || '').toLowerCase();
  var text = title + ' ' + summary;
  var score = 0;

  for (var i = 0; i < FINANCE_SOURCES.length; i++) {
    if (source.indexOf(FINANCE_SOURCES[i]) >= 0) { score += 2; break; }
  }
  for (var i = 0; i < HIGH_IMPACT_KEYWORDS.length; i++) {
    if (text.indexOf(HIGH_IMPACT_KEYWORDS[i]) >= 0) { score += 3; break; }
  }
  for (var i = 0; i < FINANCE_KEYWORDS.length; i++) {
    if (title.indexOf(FINANCE_KEYWORDS[i]) >= 0) { score += 1; break; }
  }
  return score;
}

function isFinanceNews(article) {
  return scoreArticle(article) >= 2;
}

function formatArticleDateET(date) {
  try {
    return date.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }) + ' ET';
  } catch (e) {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }
}

function formatTimeET(date) {
  try {
    return date.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }) + ' ET';
  } catch (e) {
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  }
}

function isUSTradingHours() {
  var now = new Date();
  var etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  var day = etNow.getDay();
  if (day === 0 || day === 6) return false;
  var timeMinutes = etNow.getHours() * 60 + etNow.getMinutes();
  return timeMinutes >= 570 && timeMinutes < 960;
}

var NEWS_REFRESH_TRADING_MS = 300000;
var NEWS_REFRESH_OFF_HOURS_MS = 900000;

function startNewsAutoRefresh() {
  if (newsAutoRefreshTimer) {
    clearInterval(newsAutoRefreshTimer);
    newsAutoRefreshTimer = null;
  }
  var interval = isUSTradingHours() ? NEWS_REFRESH_TRADING_MS : NEWS_REFRESH_OFF_HOURS_MS;
  newsNextRefresh = new Date(Date.now() + interval);
  updateNewsRefreshStatus();

  newsAutoRefreshTimer = setInterval(function () {
    fetchOverviewNews();
    fetchMarketNewsFeed();
    var nextInterval = isUSTradingHours() ? NEWS_REFRESH_TRADING_MS : NEWS_REFRESH_OFF_HOURS_MS;
    if (nextInterval !== interval) {
      startNewsAutoRefresh();
    } else {
      newsNextRefresh = new Date(Date.now() + nextInterval);
      updateNewsRefreshStatus();
    }
  }, interval);
}

function updateNewsRefreshStatus() {
  var el = document.getElementById('news-refresh-status');
  if (!el) return;
  var parts = [];
  if (newsLastUpdated) {
    parts.push('Last updated: ' + formatTimeET(newsLastUpdated));
  }
  if (newsNextRefresh) {
    parts.push('Next: ' + formatTimeET(newsNextRefresh));
  }
  if (isUSTradingHours()) {
    parts.push('(Trading hours - 5 min refresh)');
  } else {
    parts.push('(Off hours - 15 min refresh)');
  }
  el.textContent = parts.join(' | ');
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
    '', '', '', '', '',
    '', '', '',
  ];
  var sections = (methodology.quant_fund_approach || {}).sections || [];
  sections.forEach(function (section, idx) {
    var heading = tName(section.heading, section.heading_cn);
    var content = tName(section.content, section.content_cn);
    var icon = quantIcons[idx] || '';
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
    /* News has its own trading-hours-aware refresh timer */
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
  updateModelComparisonLabels();
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
    if (ticker) runFullAnalysisSuite(ticker, false);
  });

  quickBtn.addEventListener('click', function() {
    var ticker = getSelectedTicker();
    if (ticker) runFullAnalysisSuite(ticker, true);
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      var ticker = getSelectedTicker();
      if (ticker) runFullAnalysisSuite(ticker, false);
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

function runFullAnalysisSuite(ticker, isQuick) {
  /* Run analysis based on selected method + always load chart */
  if (typeof loadChart === 'function') loadChart(ticker, typeof selectedPeriod !== 'undefined' ? selectedPeriod : '1y');

  if (activeAnalysisMethod === 'ai') {
    runAiAnalysis(ticker, isQuick);
  } else if (activeAnalysisMethod === 'factors') {
    if (typeof runFactorAnalysis === 'function') runFactorAnalysis(ticker);
  } else if (activeAnalysisMethod === 'model1') {
    runModel1StockAnalysis(ticker);
  }
}

function goAnalyze(ticker) {
  /* Navigate to AI Analysis tab and run full analysis for the ticker */
  switchTab('ai');
  var input = document.getElementById('ai-ticker-input');
  var select = document.getElementById('ai-ticker-select');
  if (input) input.value = ticker;
  if (select) select.value = '';
  runFullAnalysisSuite(ticker, false);
  window.scrollTo({ top: 0, behavior: 'smooth' });
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
    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 90000);

    var response = await fetch(endpoint, { method: 'POST', signal: controller.signal });
    clearTimeout(timeoutId);
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
    var msg = err.name === 'AbortError'
      ? 'AI analysis timed out. Please try again.'
      : 'Failed to connect to AI service: ' + escapeHtml(err.message);
    results.innerHTML = '<div class="ai-error">' + msg + '</div>';
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
  /* Rating emoji removed */
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
    { label: 'Fundamental', value: data.fundamental_score, color: '#3b82f6', icon: '' },
    { label: 'Technical', value: data.technical_score, color: '#8b5cf6', icon: '' },
    { label: 'Sentiment', value: data.sentiment_score, color: '#f59e0b', icon: '' },
    { label: 'Risk', value: data.risk_score, color: '#ef4444', icon: '' },
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
    { title: 'Fundamental Rationale', key: 'fundamentals', icon: '' },
    { title: 'Technical Setup', key: 'technicals', icon: '' },
    { title: 'Macro Impact', key: 'macro_impact', icon: '' },
    { title: 'Smart Money Activity', key: 'insider_institutional', icon: '' },
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
    tableEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted)">No options data available.</div>';
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
    html += '<div class="calendar-highlight-label">' + SECTION_ICONS.calendar + ' Next Major Event</div>';
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
  /* Factor analysis is now triggered by the AI Analysis input via runFullAnalysisSuite.
     No separate input controls needed. */
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
          '<div class="provider-name">' + SECTION_ICONS.provider + ' ' + escapeHtml(p.name) + '</div>' +
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
          '<span class="alt-card-title">' + SECTION_ICONS.shortInterest + ' Short Interest</span>' +
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
          '<span class="alt-card-title">' + SECTION_ICONS.insider + ' Insider Activity</span>' +
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
          '<span class="alt-card-title">' + SECTION_ICONS.congress + ' Congressional Trading</span>' +
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
          '<span class="alt-card-title">' + SECTION_ICONS.darkPool + ' Dark Pool Activity</span>' +
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

  var langMap = { en: 'en', tc: 'zh-TW', sc: 'zh-CN' };
  document.documentElement.lang = langMap[getLang()] || 'en';

  /* Fetch data */
  fetchPredictions();
  initAiAnalysis();
  initFactorAnalysis();
  fetchMarketSentiment();
  fetchMarketLive();
  fetchMacroData();
  fetchOverviewNews();
  fetchMarketNewsFeed();
  /* Initialize options */
  initOptions();

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

  /* Start news-specific auto-refresh (trading hours aware) */
  startNewsAutoRefresh();

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      stopAutoRefresh();
      if (newsAutoRefreshTimer) {
        clearInterval(newsAutoRefreshTimer);
        newsAutoRefreshTimer = null;
      }
    } else {
      startAutoRefresh();
      startNewsAutoRefresh();
    }
  });

  /* Initialize analysis method selector */
  initMethodSelector();
});

/* ============================================================
   Model 1: Scan Top Stocks (LightGBM)
   ============================================================ */

async function runModel1Scan() {
  try {
    var response = await fetch('/api/top-stocks?n=100&view=consensus');
    if (response.ok) {
      var result = await response.json();
      if (result.data) renderModel1Predictions(result.data.stocks || []);
    }
  } catch (err) {
    console.error('Failed to load predictions:', err);
  }
}

function renderModel1Predictions(stocks) {
  var container = document.getElementById('model1-predictions-container');
  if (!container) return;
  if (!stocks || !stocks.length) {
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:1.5rem;">No Model 1 predictions available.</p>';
    return;
  }

  var html = '<div style="overflow-x:auto;">' +
    '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">' +
    '<thead><tr style="border-bottom:2px solid var(--border);text-align:left;">' +
    '<th style="padding:0.5rem;">#</th>' +
    '<th style="padding:0.5rem;">Ticker</th>' +
    '<th style="padding:0.5rem;">Signal</th>' +
    '<th style="padding:0.5rem;">Direction</th>' +
    '<th style="padding:0.5rem;">Consistency</th>' +
    '<th style="padding:0.5rem;">Price</th>' +
    '<th style="padding:0.5rem;">Day %</th>' +
    '<th style="padding:0.5rem;">Rationale</th>' +
    '</tr></thead><tbody>';

  stocks.forEach(function (s, idx) {
    var signal = s.signal || 0;
    var consistency = s.consistency || 0;
    var isUp = signal > 0;
    var dirColor = isUp ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
    var dirIcon = isUp ? '&#9650;' : '&#9660;';
    var dirLabel = isUp ? 'Bullish' : 'Bearish';
    var signalPct = (signal * 100).toFixed(2);
    var consistencyPct = (consistency * 100).toFixed(0);
    var dayChg = s.day_change_pct || 0;
    var dayColor = dayChg >= 0 ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';

    var rationale = [];
    if (Math.abs(signal) > 0.02) rationale.push('Strong ' + (signal > 0 ? 'buy' : 'sell') + ' signal (' + signalPct + '%)');
    else if (Math.abs(signal) > 0.01) rationale.push('Moderate signal (' + signalPct + '%)');
    else rationale.push('Weak signal (' + signalPct + '%)');
    if (consistency > 0.8) rationale.push('High consistency (' + consistencyPct + '%) across 20 trading days');
    else if (consistency > 0.6) rationale.push('Moderate consistency (' + consistencyPct + '%)');
    else rationale.push('Low consistency (' + consistencyPct + '%) - signal may reverse');
    if (s.sector) rationale.push('Sector: ' + s.sector);

    html += '<tr style="border-bottom:1px solid var(--border);">' +
      '<td style="padding:0.5rem;color:var(--text-muted);">' + (idx + 1) + '</td>' +
      '<td style="padding:0.5rem;font-weight:600;">' +
        '<a href="#" onclick="goAnalyze(\'' + escapeHtml(s.ticker) + '\');return false;" ' +
        'style="color:inherit;text-decoration:none;cursor:pointer;" title="Click to run AI Analysis for ' + escapeHtml(s.ticker) + '">' +
        escapeHtml(s.ticker) + '</a>' +
        '<div style="font-size:0.75rem;color:var(--text-muted);">' + escapeHtml(s.name || '') + '</div></td>' +
      '<td style="padding:0.5rem;font-weight:600;color:' + dirColor + ';">' + signalPct + '%</td>' +
      '<td style="padding:0.5rem;color:' + dirColor + ';">' + dirIcon + ' ' + dirLabel + '</td>' +
      '<td style="padding:0.5rem;">' +
        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
        '<div style="width:50px;height:6px;background:var(--border);border-radius:3px;overflow:hidden;">' +
        '<div style="width:' + consistencyPct + '%;height:100%;background:' + dirColor + ';border-radius:3px;"></div></div>' +
        '<span>' + consistencyPct + '%</span></div></td>' +
      '<td style="padding:0.5rem;">$' + (s.current_price || 0).toFixed(2) + '</td>' +
      '<td style="padding:0.5rem;color:' + dayColor + ';">' + (dayChg >= 0 ? '+' : '') + dayChg.toFixed(2) + '%</td>' +
      '<td style="padding:0.5rem;font-size:0.78rem;color:var(--text-muted);max-width:300px;">' + escapeHtml(rationale.join('. ') + '.') + '</td>' +
      '</tr>';
  });

  html += '</tbody></table></div>' +
    '<p style="font-size:0.75rem;color:var(--text-muted);margin-top:0.75rem;">Top ' + stocks.length + ' by 20-day consensus signal. Updated: ' + new Date().toLocaleTimeString() + '</p>';

  container.innerHTML = html;
}


/* ============================================================
   Analysis Method Selector
   ============================================================ */

function initMethodSelector() {
  var methodBtns = document.querySelectorAll('.ai-method-selector .toggle-btn');
  methodBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var method = btn.getAttribute('data-method');
      setAnalysisMethod(method);
    });
  });
}

function setAnalysisMethod(method) {
  activeAnalysisMethod = method;

  /* Update button states */
  document.querySelectorAll('.ai-method-selector .toggle-btn').forEach(function(btn) {
    var isActive = btn.getAttribute('data-method') === method;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });

  /* Update description text */
  var descEl = document.getElementById('ai-method-description');
  if (descEl) {
    var descriptions = {
      ai: t('ai.claude.desc'),
      factors: t('ai.factors.desc'),
      model1: t('ai.model1.desc'),
    };
    descEl.textContent = descriptions[method] || '';
  }

  /* Update loading text */
  var loadingTexts = {
    ai: 'Analyzing with Claude Opus 4.6... This may take 15-30 seconds.',
    factors: 'Computing factor exposures across 12 categories...',
    model1: 'Running Quantitative Signal Engine...',
  };
  var loadTextEl = document.getElementById('ai-loading-text');
  if (loadTextEl) loadTextEl.textContent = loadingTexts[method] || '';

  /* Show/hide result containers - preserve content, just toggle visibility */
  var aiResults = document.getElementById('ai-results');
  var factorsResults = document.getElementById('factors-results');
  var model1Results = document.getElementById('model1-results');
  var factorsSection = document.querySelector('[aria-labelledby="factors-label"]');

  /* Hide all non-active containers */
  if (aiResults) aiResults.classList.add('hidden');
  if (factorsResults) factorsResults.classList.add('hidden');
  if (model1Results) model1Results.classList.add('hidden');
  if (factorsSection) factorsSection.style.display = 'none';

  /* Show active method's container if it has cached content */
  if (method === 'ai' && aiResults && aiResults.innerHTML.trim()) {
    aiResults.classList.remove('hidden');
  }
  if (method === 'factors') {
    if (factorsSection) factorsSection.style.display = '';
    if (factorsResults && factorsResults.innerHTML.trim()) {
      factorsResults.classList.remove('hidden');
    }
  }
  if (method === 'model1' && model1Results && model1Results.innerHTML.trim()) {
    model1Results.classList.remove('hidden');
  }

  /* Update Analyze button text */
  var analyzeBtn = document.getElementById('ai-analyze-btn');
  var quickBtn = document.getElementById('ai-quick-btn');
  if (analyzeBtn) {
    if (method === 'ai') {
      analyzeBtn.textContent = 'Full Analysis';
      if (quickBtn) quickBtn.style.display = '';
    } else if (method === 'factors') {
      analyzeBtn.textContent = 'Analyze Factors';
      if (quickBtn) quickBtn.style.display = 'none';
    } else if (method === 'model1') {
      analyzeBtn.textContent = 'Load Predictions';
      if (quickBtn) quickBtn.style.display = 'none';
    }
  }
}

/* ============================================================
   Model 1: Per-Stock LightGBM Analysis
   ============================================================ */

async function runModel1StockAnalysis(ticker) {
  var loading = document.getElementById('ai-loading');
  var container = document.getElementById('model1-results');
  var resultEl = document.getElementById('model1-stock-result');
  var analyzeBtn = document.getElementById('ai-analyze-btn');

  if (loading) loading.classList.remove('hidden');
  if (container) container.classList.add('hidden');
  if (analyzeBtn) analyzeBtn.disabled = true;

  try {
    /* First try the prediction set */
    var response = await fetch('/api/top-stocks?n=500&view=consensus');
    var result = response.ok ? await response.json() : { data: { stocks: [] } };
    var stocks = (result.data && result.data.stocks) || [];
    var stock = stocks.find(function(s) {
      return s.ticker && s.ticker.toUpperCase() === ticker.toUpperCase();
    });

    /* If not in prediction set, run on-demand analysis */
    if (!stock) {
      var analyzeResp = await fetch('/api/analyze/' + encodeURIComponent(ticker), { method: 'POST' });
      if (!analyzeResp.ok) throw new Error('Analysis failed (HTTP ' + analyzeResp.status + ')');
      var analyzeResult = await analyzeResp.json();
      if (analyzeResult.error) throw new Error(analyzeResult.error.message || 'Analysis failed');

      var d = analyzeResult.data;
      /* Normalize on-demand result to match prediction format */
      stock = {
        ticker: d.ticker,
        name: d.name || d.ticker,
        signal: d.signal || 0,
        consistency: 0,
        current_price: d.current_price || 0,
        day_change_pct: 0,
        sector: d.sector || '',
        trend: d.trend || '',
        sma_20: d.sma_20 || 0,
        sma_50: d.sma_50 || 0,
        volatility: d.volatility || 0,
        momentum: d.momentum || 0,
        status: d.status || 'analyzed',
        source: 'on_demand',
      };
    }

    if (loading) loading.classList.add('hidden');
    if (analyzeBtn) analyzeBtn.disabled = false;
    if (container) container.classList.remove('hidden');

    var signal = stock.signal || 0;
    var consistency = stock.consistency || 0;
    var isUp = signal > 0;
    var dirColor = isUp ? 'var(--accent-green, #22c55e)' : 'var(--accent-red, #ef4444)';
    var dirLabel = isUp ? 'Bullish' : 'Bearish';
    var dirIcon = isUp ? '\u25B2' : '\u25BC';
    var signalPct = (signal * 100).toFixed(2);
    var consistencyPct = (consistency * 100).toFixed(0);
    var dayChg = stock.day_change_pct || 0;
    var dayColor = dayChg >= 0 ? 'var(--accent-green, #22c55e)' : 'var(--accent-red, #ef4444)';
    var isOnDemand = stock.source === 'on_demand';

    /* Find rank if in prediction set */
    var rank = stocks.findIndex(function(s) { return s.ticker === stock.ticker; }) + 1;
    var rankDisplay = rank > 0 ? '#' + rank : 'N/A';
    var rankOf = rank > 0 ? ' (of ' + stocks.length + ')' : ' (on-demand)';

    /* Build analysis rationale */
    var rationale = [];
    if (isOnDemand) {
      rationale.push('On-demand analysis via yfinance (not in pre-computed prediction set)');
      if (stock.momentum) rationale.push('Momentum: ' + stock.momentum + '% (distance from 50-day SMA)');
      if (stock.volatility) rationale.push('Annualized volatility: ' + stock.volatility + '%');
      if (stock.sma_20 && stock.sma_50) {
        var smaSignal = stock.current_price > stock.sma_20 ? 'above' : 'below';
        rationale.push('Price $' + stock.current_price.toFixed(2) + ' is ' + smaSignal + ' SMA20 ($' + stock.sma_20.toFixed(2) + ')');
      }
      rationale.push('Trend: ' + (stock.trend || 'unknown'));
    } else {
      if (Math.abs(signal) > 0.02) rationale.push('Strong ' + (signal > 0 ? 'buy' : 'sell') + ' signal at ' + signalPct + '%');
      else if (Math.abs(signal) > 0.01) rationale.push('Moderate signal at ' + signalPct + '%');
      else rationale.push('Weak signal at ' + signalPct + '%');
      if (consistency > 0.8) rationale.push('High consistency (' + consistencyPct + '%) across 20 trading days');
      else if (consistency > 0.6) rationale.push('Moderate consistency (' + consistencyPct + '%)');
      else rationale.push('Low consistency (' + consistencyPct + '%) — signal may reverse');
    }
    if (stock.sector) rationale.push('Sector: ' + stock.sector);

    /* Source badge */
    var sourceBadge = isOnDemand
      ? '<span style="display:inline-block;font-size:0.6875rem;font-weight:600;padding:2px 8px;border-radius:4px;background:var(--gold-dim,rgba(196,169,98,0.1));color:var(--gold-dark,#A68B3E);margin-left:8px;">LIVE ANALYSIS</span>'
      : '<span style="display:inline-block;font-size:0.6875rem;font-weight:600;padding:2px 8px;border-radius:4px;background:var(--navy-dim,rgba(27,42,74,0.06));color:var(--navy,#1B2A4A);margin-left:8px;">FROM PREDICTION SET</span>';

    var html =
      '<div class="ai-report-header" style="margin-bottom:1.5rem;">' +
        '<div class="ai-rating-section">' +
          '<div class="ai-rating-badge-lg" style="background:' + dirColor + ';color:#fff;padding:8px 20px;border-radius:8px;font-size:1.1rem;">' +
            dirIcon + ' ' + dirLabel + '</div>' +
          '<div style="margin-top:8px;">' +
            '<span style="font-size:1.5rem;font-weight:700;">' + escapeHtml(ticker) + '</span>' +
            '<span style="color:var(--text-muted);margin-left:8px;">' + escapeHtml(stock.name || '') + '</span>' +
            sourceBadge +
          '</div>' +
        '</div>' +
      '</div>' +
      /* Stat cards */
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:0.75rem;margin-bottom:1.5rem;">' +
        '<div class="stat-card"><div class="stat-value" style="color:' + dirColor + ';">' + signalPct + '%</div><div class="stat-label">Signal Strength</div></div>' +
        (isOnDemand
          ? '<div class="stat-card"><div class="stat-value">' + (stock.momentum || 0) + '%</div><div class="stat-label">Momentum</div></div>'
          : '<div class="stat-card"><div class="stat-value">' + consistencyPct + '%</div><div class="stat-label">20-Day Consistency</div></div>'
        ) +
        '<div class="stat-card"><div class="stat-value">' + rankDisplay + '</div><div class="stat-label">Rank' + escapeHtml(rankOf) + '</div></div>' +
        '<div class="stat-card"><div class="stat-value">$' + (stock.current_price || 0).toFixed(2) + '</div><div class="stat-label">Current Price</div></div>' +
        (isOnDemand
          ? '<div class="stat-card"><div class="stat-value">' + (stock.volatility || 0) + '%</div><div class="stat-label">Volatility (Ann.)</div></div>'
          : '<div class="stat-card"><div class="stat-value" style="color:' + dayColor + ';">' + (dayChg >= 0 ? '+' : '') + dayChg.toFixed(2) + '%</div><div class="stat-label">Day Change</div></div>'
        ) +
        '<div class="stat-card"><div class="stat-value">' + escapeHtml(stock.sector || 'N/A') + '</div><div class="stat-label">Sector</div></div>' +
      '</div>' +
      /* Signal Analysis */
      '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px;padding:20px;margin-bottom:1.5rem;">' +
        '<h4 style="font-size:0.875rem;font-weight:600;color:var(--navy,#1B2A4A);margin-bottom:10px;">Signal Analysis</h4>' +
        '<ul style="margin:0;padding-left:20px;font-size:0.8125rem;color:var(--text-secondary);line-height:1.8;">' +
          rationale.map(function(r) { return '<li>' + escapeHtml(r) + '</li>'; }).join('') +
        '</ul>' +
      '</div>' +
      /* Calculation Methodology */
      '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px;padding:20px;">' +
        '<h4 style="font-size:0.875rem;font-weight:600;color:var(--navy,#1B2A4A);margin-bottom:10px;">Calculation Methodology</h4>' +
        '<div style="font-size:0.8125rem;color:var(--text-secondary);line-height:1.8;">' +
          '<div style="display:grid;grid-template-columns:140px 1fr;gap:4px 16px;">' +
            '<span style="font-weight:600;color:var(--text-primary);">Signal</span><span>' + (isOnDemand ? 'Composite of momentum, volatility, and short-term trend' : '20-day consensus from Alpha158 features via LightGBM') + ' (' + signalPct + '%)</span>' +
            (isOnDemand
              ? '<span style="font-weight:600;color:var(--text-primary);">SMA 20</span><span>$' + (stock.sma_20 || 0).toFixed(2) + '</span>' +
                '<span style="font-weight:600;color:var(--text-primary);">SMA 50</span><span>$' + (stock.sma_50 || 0).toFixed(2) + '</span>'
              : '<span style="font-weight:600;color:var(--text-primary);">Consistency</span><span>% of 20 trading days with same directional signal (' + consistencyPct + '%)</span>'
            ) +
            '<span style="font-weight:600;color:var(--text-primary);">Direction</span><span>' + dirLabel + ' — signal is ' + (isUp ? 'positive (predicted upward)' : 'negative (predicted downward)') + '</span>' +
            '<span style="font-weight:600;color:var(--text-primary);">Model</span><span>' + (isOnDemand ? 'On-demand technical analysis (momentum + volatility + trend)' : 'LightGBM + Alpha158 (158 factors, 18yr training set)') + '</span>' +
          '</div>' +
        '</div>' +
      '</div>';

    resultEl.innerHTML = html;
    updateSectionTimestamp('ai');
  } catch (err) {
    if (loading) loading.classList.add('hidden');
    if (analyzeBtn) analyzeBtn.disabled = false;
    if (container) container.classList.remove('hidden');
    resultEl.innerHTML = '<div class="ai-error">Failed to analyze ' + escapeHtml(ticker) + ': ' + escapeHtml(err.message) + '</div>';
  }
}

function renderModel1Table(stocks, highlightTicker) {
  if (!stocks || !stocks.length) return '<p style="color:var(--text-muted);">No predictions available.</p>';

  var html = '<div style="overflow-x:auto;">' +
    '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">' +
    '<thead><tr style="border-bottom:2px solid var(--border);text-align:left;">' +
    '<th style="padding:0.5rem;">#</th>' +
    '<th style="padding:0.5rem;">Ticker</th>' +
    '<th style="padding:0.5rem;">Signal</th>' +
    '<th style="padding:0.5rem;">Direction</th>' +
    '<th style="padding:0.5rem;">Consistency</th>' +
    '<th style="padding:0.5rem;">Price</th>' +
    '<th style="padding:0.5rem;">Sector</th>' +
    '</tr></thead><tbody>';

  stocks.forEach(function(s, idx) {
    var signal = s.signal || 0;
    var isUp = signal > 0;
    var dirColor = isUp ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)';
    var isHighlighted = highlightTicker && s.ticker && s.ticker.toUpperCase() === highlightTicker.toUpperCase();
    var rowBg = isHighlighted ? 'background:var(--accent-blue-dim);' : '';

    html += '<tr style="border-bottom:1px solid var(--border);' + rowBg + '">' +
      '<td style="padding:0.5rem;color:var(--text-muted);">' + (idx + 1) + '</td>' +
      '<td style="padding:0.5rem;font-weight:600;">' + escapeHtml(s.ticker) + '</td>' +
      '<td style="padding:0.5rem;font-weight:600;color:' + dirColor + ';">' + (signal * 100).toFixed(2) + '%</td>' +
      '<td style="padding:0.5rem;color:' + dirColor + ';">' + (isUp ? '\u25B2 Bullish' : '\u25BC Bearish') + '</td>' +
      '<td style="padding:0.5rem;">' + ((s.consistency || 0) * 100).toFixed(0) + '%</td>' +
      '<td style="padding:0.5rem;">$' + (s.current_price || 0).toFixed(2) + '</td>' +
      '<td style="padding:0.5rem;font-size:0.78rem;color:var(--text-muted);">' + escapeHtml(s.sector || '') + '</td>' +
      '</tr>';
  });

  html += '</tbody></table></div>';
  return html;
}

/* ============================================================
   Method Comparison i18n Updates
   ============================================================ */

function updateModelComparisonLabels() {
  var el;
  el = document.getElementById('model-comparison-title');
  if (el) el.textContent = t('ai.model.comparison');
  el = document.getElementById('mc-claude-desc');
  if (el) el.textContent = t('ai.claude.desc');
  el = document.getElementById('mc-factors-desc');
  if (el) el.textContent = t('ai.factors.desc');
  el = document.getElementById('mc-model1-desc');
  if (el) el.textContent = t('ai.model1.desc');
  el = document.getElementById('mc-claude-type');
  if (el) el.textContent = t('ai.claude.type');
  el = document.getElementById('mc-factors-type');
  if (el) el.textContent = t('ai.factors.type');
  el = document.getElementById('mc-model1-type');
  if (el) el.textContent = t('ai.model1.type');
  el = document.getElementById('mc-claude-time');
  if (el) el.textContent = t('ai.claude.timeframe');
  el = document.getElementById('mc-factors-time');
  if (el) el.textContent = t('ai.factors.timeframe');
  el = document.getElementById('mc-model1-time');
  if (el) el.textContent = t('ai.model1.timeframe');
  el = document.getElementById('mc-claude-best');
  if (el) el.textContent = t('ai.claude.bestfor');
  el = document.getElementById('mc-factors-best');
  if (el) el.textContent = t('ai.factors.bestfor');
  el = document.getElementById('mc-model1-best');
  if (el) el.textContent = t('ai.model1.bestfor');

  /* Update method selector button labels */
  document.querySelectorAll('.ai-method-selector .toggle-btn').forEach(function(btn) {
    var method = btn.getAttribute('data-method');
    var keys = { ai: 'ai.method.claude', factors: 'ai.method.factors', model1: 'ai.method.model1' };
    if (keys[method]) btn.textContent = t(keys[method]);
  });

  /* Update description for current method */
  var descEl = document.getElementById('ai-method-description');
  if (descEl) {
    var descKeys = { ai: 'ai.claude.desc', factors: 'ai.factors.desc', model1: 'ai.model1.desc' };
    descEl.textContent = t(descKeys[activeAnalysisMethod] || 'ai.claude.desc');
  }
}
