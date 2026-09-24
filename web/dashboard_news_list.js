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

  // 2026-08-14 -- header links (ext_links convention -- same table/API
  // hedgeye_panel.js's panels read, small self-contained render here since
  // this is a separate script/IIFE with no guaranteed load order relative
  // to that one). "Market News" text stays plain (2 links now, so it can't
  // unambiguously BE either one); each link renders as its own small
  // labeled chip after it instead of a bare "↗" icon -- a lone arrow with
  // only a hover title gave no visible way to tell Yahoo's icon from
  // CNBC's apart without hovering each one. User: "add some indicators/
  // text for the links."
  var _links = {};
  function _extLinkChip(key, fallbackLabel) {
    var l = _links[key];
    if (!l || !l.url) return '';
    return ' <a href="' + esc(l.url) + '" target="_blank" rel="noopener" ' +
      'class="dash-news-ext-link" title="' + esc(l.label || fallbackLabel) + '">' +
      esc(l.label || fallbackLabel) + ' <span style="font-size:7px; opacity:0.55;">&#8599;</span></a>';
  }
  // 2026-09-23 -- header rebuilt (innerHTML replace) whenever the ext-links
  // chips arrive, so the collapse button has to be part of this same
  // template each time -- otherwise _renderHdr() would wipe it out. The
  // click listener is (re)wired right after, in _renderHdr() itself.
  function _hdrHtml() {
    var collapsed = localStorage.getItem(COLLAPSE_KEY) === '1';
    return 'Market News' + _extLinkChip('market_news', 'Yahoo') + _extLinkChip('market_news_cnbc', 'CNBC') +
      '<button class="msr-sort-btn" id="dashNewsToggle" type="button" title="Collapse/expand panel" ' +
      'aria-label="' + (collapsed ? 'Expand' : 'Collapse') + ' news">' + (collapsed ? '&#9652;' : '&#9662;') + '</button>';
  }
  function _renderHdr() {
    var hdr = document.getElementById('dashNewsListHdr');
    if (!hdr) return;
    hdr.innerHTML = _hdrHtml();
    var btn = document.getElementById('dashNewsToggle');
    if (btn) btn.addEventListener('click', _toggleNews);
  }
  function _loadLinks() {
    fetchJson('/api/ext-links').then(function (links) {
      _links = links || {};
      _renderHdr();
    }).catch(function () { /* header just stays plain text -- non-critical */ });
  }

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

  // 2026-09-23 -- own independent collapse state (localStorage key,
  // separate from the Hedgeye panel's). The toggle button used to live on
  // the Accounts filter bar (📰 [data-news-toggle], removed) and hid the
  // WHOLE panel (header included) when collapsed -- same "stranded, no way
  // back in" problem the Hedgeye panel had. Now the arrow lives directly in
  // this panel's own header bar (#dashNewsListHdr, .msr-section-hdr chrome,
  // same as every other panel in this column) and only the body below it
  // collapses -- the header (and its arrow) always stays visible.
  var COLLAPSE_KEY = 'dashNewsList_collapsed';

  function _applyNewsState(collapsed) {
    var body = document.getElementById('dashNewsListBody');
    if (body) body.style.display = collapsed ? 'none' : '';
    var btn = document.getElementById('dashNewsToggle');
    if (btn) {
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' news');
    }
  }

  function _toggleNews() {
    var collapsed = localStorage.getItem(COLLAPSE_KEY) !== '1'; // flip current state
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
    _applyNewsState(collapsed);
  }

  function _init() {
    var panel = _ensureMount();
    if (!panel) return;
    panel.innerHTML =
      '<div class="msr-section-hdr" id="dashNewsListHdr">' + _hdrHtml() + '</div>' +
      '<div class="dash-news-list-body" id="dashNewsListBody" style="height:' + (VISIBLE_ROWS * 20) + 'px;">' +
        '<div class="dash-news-list-row">Loading&hellip;</div>' +
      '</div>';

    var btn = document.getElementById('dashNewsToggle');
    if (btn) btn.addEventListener('click', _toggleNews);
    _applyNewsState(localStorage.getItem(COLLAPSE_KEY) === '1');

    _load();
    _loadLinks();
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
