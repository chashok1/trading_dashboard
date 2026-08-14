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
  function _renderHdr() {
    var hdr = document.getElementById('dashNewsListHdr');
    if (hdr) hdr.innerHTML = 'Market News' + _extLinkChip('market_news', 'Yahoo') + _extLinkChip('market_news_cnbc', 'CNBC');
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

  // 2026-08-10 -- collapse toggle, own independent state (localStorage key
  // separate from the Hedgeye panels' shared one -- this panel isn't part
  // of that group). Toggle button ITSELF now lives only on the Accounts
  // filter bar (index.html, static markup, [data-news-toggle]) -- user:
  // "news bar still has toggle button on the panel that is extra button"
  // (the per-panel one, added in an earlier pass, was redundant once the
  // filter-bar one existed). This module now only owns the header row +
  // body, both driven by whatever [data-news-toggle] button is clicked.
  // 2026-08-10 follow-up -- header row (label only, no button) shows ONLY
  // when expanded, hidden along with the body when collapsed -- user:
  // "remove the headers for both when collapsed. only add the header row
  // when expanded (Hedgeye & Market News)." Reverses the still-earlier "no
  // header text" request only for the expanded state; collapsed still
  // shows nothing, same as before.
  // 2026-08-10 follow-up 2 -- collapsing the header/body alone left the
  // OUTER #dashNewsListPanel card (.cockpit-band's own border+padding)
  // behind as an empty white box -- user: "market news is leaving white
  // panel when collapsed. don't need anything here." Now hides the whole
  // panel element itself; hdr/body no longer need their own display logic
  // since there's nothing to show through a hidden ancestor either way.
  var COLLAPSE_KEY = 'dashNewsList_collapsed';
  // 2026-08-10 follow-up 3 -- newspaper icon prefixed on the arrow so this
  // toggle is visually distinct from the Hedgeye one beside it on the
  // filter bar at a glance, not just via tooltip -- user: "Toggle buttons,
  // have either icons or letters H and M ... Icons better."
  var ICON = '📰 '; // 📰

  function _applyNewsState(collapsed) {
    var panel = _ensureMount();
    if (panel) panel.style.display = collapsed ? 'none' : '';
    Array.prototype.forEach.call(document.querySelectorAll('[data-news-toggle]'), function (btn) {
      btn.innerHTML = ICON + (collapsed ? '&#9652;' : '&#9662;');
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' news');
    });
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
      '<div class="dash-news-list-hdr" id="dashNewsListHdr">Market News</div>' +
      '<div class="dash-news-list-body" id="dashNewsListBody" style="height:' + (VISIBLE_ROWS * 20) + 'px;">' +
        '<div class="dash-news-list-row">Loading&hellip;</div>' +
      '</div>';

    Array.prototype.forEach.call(document.querySelectorAll('[data-news-toggle]'), function (btn) {
      btn.addEventListener('click', _toggleNews);
    });
    // Applies the persisted collapsed/expanded state to the panel itself
    // (built as static HTML above, always starts "expanded") and syncs the
    // filter-bar button's icon -- it's static markup in index.html (not
    // built by this script), so it starts at its hardcoded default until
    // this runs.
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
