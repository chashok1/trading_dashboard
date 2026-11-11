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

  // 2026-11-11, user-directed: the panels are OPEN in the morning, collapse themselves at 11:00 AM (the browser's local time), and stay
  // collapsed for the rest of the day if you collapsed them yourself. Your own choice is stored per day as "YYYY-MM-DD:c:phase"
  // (c = 1 collapsed / 0 expanded; phase = am before 11:00, pm from 11:00). Rules for today:
  //   - you collapsed it (any time)                      -> collapsed
  //   - it is 11:00 or later and you did not expand it
  //     after 11:00 yourself                              -> collapsed (the automatic collapse)
  //   - otherwise                                         -> expanded
  // A value from an earlier day reads as "no choice". The old "YYYY-MM-DD:1|0" format still reads (0 counts as an expand made in the morning).
  var COLLAPSE_HOUR = 11;
  function _todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function _phase() { return new Date().getHours() >= COLLAPSE_HOUR ? 'pm' : 'am'; }
  function _dailyCollapsed(key) {
    var choice = null;
    try {
      var v = localStorage.getItem(key) || '', parts = v.split(':');
      if (parts.length >= 2 && parts[0] === _todayStr()) choice = { c: parts[1] === '1', p: parts[2] === 'pm' ? 'pm' : 'am' };
    } catch (e) { /* storage blocked: fall back to the time rule */ }
    if (choice && choice.c) return true;                 // you collapsed it
    if (_phase() === 'pm') return !(choice && choice.p === 'pm');   // 11:00 or later: collapsed unless you expanded it after 11:00
    return false;                                        // morning: open
  }
  function _dailyStore(key, collapsed) {
    try { localStorage.setItem(key, _todayStr() + ':' + (collapsed ? '1' : '0') + ':' + _phase()); } catch (e) {}
  }

  function _isDashboard() {
    return window.location.pathname.replace(/\/+$/, '') === '' || window.location.pathname === '/';
  }

  function _applyState(collapsed, bodyId, btnId, label) {
    var body = document.getElementById(bodyId || 'hedgeyeDashPanelBody');
    var btn = document.getElementById(btnId || 'hedgeyeDashToggle');
    if (body) body.style.display = collapsed ? 'none' : '';
    if (btn) {
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' ' + (label || 'Hedgeye panel'));
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
      [['market_news', 'Yahoo'], ['market_news_cnbc', 'CNBC'], ['market_news_econ', 'Econ']].forEach(function (p) {
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
    // 2026-10-20: second panel below it (Actionable's Hedgeye tiles), own daily collapse state.
    var KEY2 = 'heActDashPanel_collapsed';
    var btn2 = document.getElementById('hedgeyeActDashToggle');
    if (btn2) {
      _applyState(_dailyCollapsed(KEY2), 'hedgeyeActDashPanelBody', 'hedgeyeActDashToggle', 'Hedgeye signals panel');
      btn2.addEventListener('click', function () {
        var c2 = !_dailyCollapsed(KEY2);
        _dailyStore(KEY2, c2);
        _applyState(c2, 'hedgeyeActDashPanelBody', 'hedgeyeActDashToggle', 'Hedgeye signals panel');
      });
    }
  }

  // Re-apply the rule every minute so a page left open since the morning collapses at 11:00 on its own.
  function _tick() {
    if (!_isDashboard() || !document.getElementById('hedgeyeDashToggle')) return;
    _applyState(_dailyCollapsed('heDashPanels_collapsed'));
    if (document.getElementById('hedgeyeActDashToggle')) _applyState(_dailyCollapsed('heActDashPanel_collapsed'), 'hedgeyeActDashPanelBody', 'hedgeyeActDashToggle', 'Hedgeye signals panel');
  }
  setInterval(_tick, 60000);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
