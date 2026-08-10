/* Dashboard-only market news list -- fixed-height, scrollable, one headline
 * per line. Sourced from GET /api/market-news (Yahoo Finance RSS, server-
 * side fetch+cache -- see api/routers/health.py). Renders into
 * #dashNewsListPanel, cat-col, directly below the Hedgeye "Top 3 Things"
 * card (#hedgeyeDashPanel).
 *
 * Replaces the earlier one-line auto-scrolling marquee (dashboard_news_feed.js,
 * fixed to the bottom of the page, removed 2026-08-10) -- user: "instead of
 * scrolling, add a panel below Hedgeye's TOP 3 things panel that will have
 * single line news and a scroll bar -- not sure if yahoo still be the best
 * source or trending view news source -- i only need specific to stock
 * market." Kept the Yahoo Finance News RSS source: it's already a
 * stock/market-specific feed (finance.yahoo.com/news/rssindex, not general
 * news), so only the presentation changed, not the source.
 *
 * Self-mounting, Dashboard (/) only.
 */
(function () {
  var fetchJson = window.fetchJson || async function (url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  var esc = window.escapeHtml || function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  // Fixed height sized to show ~5-6 rows per column before overflow kicks
  // in -- two columns (see .dash-news-list-body in styles.css) means this
  // fits ~double that many headlines in the same viewing area. Matches
  // .dash-news-list-row's row height in styles.css.
  var VISIBLE_ROWS = 6;

  function _ensureMount() {
    if (window.location.pathname.replace(/\/+$/, '') !== '' && window.location.pathname !== '/') return null;
    return document.getElementById('dashNewsListPanel');
  }

  // Source shown on hover only (title attr), not as visible text on the
  // line -- user: "remove the news source from the news lines instead add
  // it to tooltip/hover -- show the news source."
  function _rowHtml(it) {
    var tip = it.source ? it.title + ' — ' + it.source : it.title;
    var body = esc(it.title);
    return it.link
      ? '<a class="dash-news-list-row" href="' + esc(it.link) + '" target="_blank" rel="noopener" title="' + esc(tip) + '">' + body + '</a>'
      : '<div class="dash-news-list-row" title="' + esc(tip) + '">' + body + '</div>';
  }

  async function _load() {
    var body = document.getElementById('dashNewsListBody');
    if (!body) return;
    try {
      var data = await fetchJson('/api/market-news?limit=20');
      var items = data.items || [];
      body.innerHTML = items.length
        ? items.map(_rowHtml).join('')
        : '<div class="dash-news-list-row">No news available.</div>';
    } catch (e) {
      body.innerHTML = '<div class="dash-news-list-row">News unavailable.</div>';
    }
  }

  function _init() {
    var panel = _ensureMount();
    if (!panel) return;
    panel.innerHTML =
      '<div class="dash-news-list-body" id="dashNewsListBody" style="height:' + (VISIBLE_ROWS * 20) + 'px;">' +
        '<div class="dash-news-list-row">Loading&hellip;</div>' +
      '</div>';

    _load();
    // Refresh alongside the server's own 5-minute cache TTL (api/routers/
    // health.py::_MARKET_NEWS_TTL) -- no point polling faster than that.
    setInterval(_load, 5 * 60 * 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
