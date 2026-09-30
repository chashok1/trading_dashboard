/* Collapse/expand toggle for the Hedgeye "Early Look/Macro Commentary/
 * Top 3 Things" panel (Dashboard center column, #hedgeyeDashPanel). Its own
 * header bar (#hedgeyeDashHdr/#hedgeyeDashToggle) carries the arrow, same
 * .msr-section-hdr/.msr-sort-btn chrome as every other collapsible bar in
 * this column (see web/market_read.js).
 *
 * 2026-09-23 -- was a shared broadcast toggle across 3 Hedgeye panels (Mkt
 * Situation / center / INFL) driven by a 📊 button on the filter bar
 * ([data-he-toggle] on all 3 + the button). Mkt Situation and INFL dropped
 * their own collapse headers earlier and are now always expanded (see
 * index.html's own history comments on #heMktSituationPanel/#heInflPanel),
 * so only the center panel still collapses -- this is now a single
 * self-contained toggle, and the filter-bar button is gone.
 * Self-mounting, Dashboard (/) only.
 */
(function () {
  var KEY = 'heDashPanels_collapsed';

  // 2026-09-30, user-directed: start each day EXPANDED, then remember the
  // collapse state for the rest of that day. Stored as "YYYY-MM-DD:1|0"
  // (1 = collapsed); a value from an earlier day (or the old bare "0"/"1"
  // format) reads as expanded.
  function _todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function _dailyCollapsed(key) {
    try {
      var v = localStorage.getItem(key) || '';
      var i = v.indexOf(':');
      return i > 0 && v.slice(0, i) === _todayStr() && v.slice(i + 1) === '1';
    } catch (e) { return false; }
  }
  function _dailyStore(key, collapsed) {
    try { localStorage.setItem(key, _todayStr() + ':' + (collapsed ? '1' : '0')); } catch (e) {}
  }

  function _isDashboard() {
    return window.location.pathname.replace(/\/+$/, '') === '' || window.location.pathname === '/';
  }

  function _applyState(collapsed) {
    var body = document.getElementById('hedgeyeDashPanelBody');
    var btn = document.getElementById('hedgeyeDashToggle');
    if (body) body.style.display = collapsed ? 'none' : '';
    if (btn) {
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Hedgeye panel');
    }
  }

  // 2026-09-30, user-directed: the Yahoo and CNBC news links (ext_links
  // panel_keys market_news / market_news_cnbc, GET /api/ext-links) moved here
  // from the removed Market News panel -- small pill chips before the arrow.
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function _addNewsLinks(btn) {
    fetch('/api/ext-links').then(function (r) { return r.ok ? r.json() : {}; }).then(function (links) {
      var html = '';
      [['market_news', 'Yahoo'], ['market_news_cnbc', 'CNBC']].forEach(function (p) {
        var l = links && links[p[0]];
        if (!l || !l.url) return;
        html += '<a href="' + _esc(l.url) + '" target="_blank" rel="noopener" class="he-ext-link" title="' +
          _esc(l.label || p[1]) + '" style="margin-left:6px;">' + _esc(l.label || p[1]) +
          ' <span style="font-size:7px; opacity:0.55;">&#8599;</span></a>';
      });
      if (html) btn.insertAdjacentHTML('beforebegin', html);
    }).catch(function () { /* links are non-critical */ });
  }

  function _init() {
    if (!_isDashboard()) return;
    var btn = document.getElementById('hedgeyeDashToggle');
    if (!btn) return;
    _addNewsLinks(btn);
    _applyState(_dailyCollapsed(KEY));
    btn.addEventListener('click', function () {
      var collapsed = !_dailyCollapsed(KEY);   // flip today's state
      _dailyStore(KEY, collapsed);
      _applyState(collapsed);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
