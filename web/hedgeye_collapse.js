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

  function _init() {
    if (!_isDashboard()) return;
    var btn = document.getElementById('hedgeyeDashToggle');
    if (!btn) return;
    _applyState(localStorage.getItem(KEY) === '1');
    btn.addEventListener('click', function () {
      var collapsed = localStorage.getItem(KEY) !== '1';
      localStorage.setItem(KEY, collapsed ? '1' : '0');
      _applyState(collapsed);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
