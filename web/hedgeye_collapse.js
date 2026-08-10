/* Shared collapse/expand toggle across the 3 Hedgeye Dashboard panels --
 * Mkt Situation (left column), Early Look/Macro Commentary/Top 3 Things
 * (center column), INFL (right rail). User: "make hedgeye panels
 * (together) ... collapable and expandable" -- ONE shared state: clicking
 * the toggle on ANY of the 3 collapses/expands all 3 together.
 *
 * Deliberately separate from hedgeye_panel.js, which owns each panel's
 * OUTER display:block/none (data-presence -- hide entirely when there's
 * nothing to show). This script only ever touches the INNER
 * .he-collapse-body wrapper each panel already has for exactly this
 * reason, so the two concerns never fight over the same style.display.
 * Self-mounting, Dashboard (/) only.
 */
(function () {
  var KEY = 'heDashPanels_collapsed';

  function _isDashboard() {
    return window.location.pathname.replace(/\/+$/, '') === '' || window.location.pathname === '/';
  }

  function _applyState(collapsed) {
    Array.prototype.forEach.call(document.querySelectorAll('.he-collapse-body'), function (el) {
      el.style.display = collapsed ? 'none' : '';
    });
    // 2026-08-10 -- the per-panel "Hedgeye" header row itself now also
    // hides when collapsed (not just the body below it) -- the filter-bar
    // toggle is the way back in, so there's nothing left to click on these
    // 3 individual headers while collapsed. User: "you can remove the
    // headers for both when collapsed. only add the header row when
    // expanded (Hedgeye & Market News)." Scoped to .he-collapse-hdr only
    // (the 3 panels' own header divs) -- the filter-bar's own toggle
    // button is a separate element (not wrapped in .he-collapse-hdr) and
    // always stays visible; its icon is still kept in sync below via
    // .he-collapse-btn, a class it also carries.
    Array.prototype.forEach.call(document.querySelectorAll('.he-collapse-hdr'), function (hdr) {
      hdr.style.display = collapsed ? 'none' : '';
    });
    Array.prototype.forEach.call(document.querySelectorAll('.he-collapse-btn'), function (btn) {
      // 2026-08-10 -- bar-chart icon prefixed on the arrow, filter-bar
      // button only (that one has no adjacent text label, unlike the 3
      // panels' own headers which already say "Hedgeye") -- makes it
      // visually distinct from the News toggle beside it at a glance, not
      // just via tooltip. User: "Toggle buttons, have either icons or
      // letters H and M ... Icons better."
      var icon = btn.classList.contains('cat-filter-toggle') ? '📊 ' : ''; // 📊
      btn.innerHTML = icon + (collapsed ? '&#9652;' : '&#9662;');
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Hedgeye panels');
    });
  }

  function _toggle() {
    var collapsed = localStorage.getItem(KEY) !== '1'; // flip current state
    localStorage.setItem(KEY, collapsed ? '1' : '0');
    _applyState(collapsed);
  }

  function _init() {
    if (!_isDashboard()) return;
    var headers = document.querySelectorAll('[data-he-toggle]');
    if (!headers.length) return;
    _applyState(localStorage.getItem(KEY) === '1');
    Array.prototype.forEach.call(headers, function (hdr) {
      hdr.style.cursor = 'pointer';
      hdr.addEventListener('click', _toggle);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
