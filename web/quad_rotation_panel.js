/* Quad Rotation panel — sector + asset_class + style rotation view for the
 * Dashboard screen (index.html): quad-regime direction + live Trade/Trend
 * breadth per category, one box per category, ranked by conviction.
 * Reads: GET /api/actionable/quad-rotation?date=<#datePicker value>
 * Renders into #quadRotationPanel, a narrow .cat-col card (~24% of page
 * width, not the wide Actionable toolbar). Re-renders on date change and
 * Refresh. Sits directly above #hedgeyeDashPanel (2026-08-31, user request).
 *
 * 2026-08-31 follow-up -- simplified from tiles+collapsible detail-rows
 * down to ONE flat box grid per axis: "display all them as boxes. don't
 * need the details anymore." Every category (not just the top 5 bullish
 * ones) gets a box now, sorted by conviction; each box links straight to
 * Actionable filtered to that category (?filter_sector=/?filter_asset_
 * class=/?filter_style=, applied once on Actionable's load -- see
 * web/actionable.js's _qrDeepLinkApplied hook) -- "somehow provide a link
 * to go to actionable screen."
 *
 * 3 separate per-axis groups (Asset Class / Sector / Style), not one
 * blended list -- user: "Equities (sector & style) will have its own,
 * right?"
 */
(function () {
  'use strict';

  var AXIS_LABEL = { asset_class: 'Asset Class', sector: 'Sector', style: 'Style' };
  var AXIS_FILTER_PARAM = { asset_class: 'filter_asset_class', sector: 'filter_sector', style: 'filter_style' };
  var AXIS_ORDER = ['asset_class', 'sector', 'style'];
  var TILE_WIDTH = '88px';
  // 2026-09-01 -- columns per axis's own mini-grid, chosen to land ~3 rows
  // against each axis's real category count (asset_class 6 -> 2x3,
  // sector 12 -> 4x3, style ~10 -> 4 cols/3 rows w/ a partial last row) --
  // matches the exact layout the user sketched. Not auto-computed from
  // n_tracked (the axis's OWN category count, always small/fixed, isn't
  // in the API payload -- these are just sized to the current real shape).
  var AXIS_COLS = { asset_class: 2, sector: 4, style: 4 };

  var fetchJson = (window.td_common && window.td_common.fetchJson) || async function (url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function breadthPct(r) { return r.n_tracked ? Math.round((r.n_above / r.n_tracked) * 100) : 0; }

  function convictionScore(r) {
    if (r.quad_stance !== 'BULLISH') return -1;
    var w = r.n_tracked > 3 ? 1 : 0.6;
    return (breadthPct(r) / 100) * w;
  }

  function quadBadge(quad) {
    if (quad === 'BULLISH') return '<span style="display:inline-flex; align-items:center; gap:4px; ' +
      'font-size:9.5px; font-weight:700; color:var(--bull,#15803d); background:var(--act-buy-bg,#dceadd); ' +
      'padding:2px 6px; border-radius:100px; white-space:nowrap;">&#9650; BULL</span>';
    if (quad === 'BEARISH') return '<span style="display:inline-flex; align-items:center; gap:4px; ' +
      'font-size:9.5px; font-weight:700; color:var(--bear,#b91c1c); background:var(--act-sell-strong-bg,#f4e6e6); ' +
      'padding:2px 6px; border-radius:100px; white-space:nowrap;">&#9660; BEAR</span>';
    return '<span style="font-size:9.5px; color:var(--text-3,#a8a29e);">&mdash;</span>';
  }

  function borderColor(quad) {
    if (quad === 'BULLISH') return 'var(--bull,#15803d)';
    if (quad === 'BEARISH') return 'var(--bear,#b91c1c)';
    return 'var(--border-strong,#d6d5d0)';
  }

  // Whole box is a link straight to Actionable, filtered to that category
  // (state.filters.sector/asset_class/style, applied once on load).
  function categoryBox(r) {
    var pct = breadthPct(r);
    var link = '/actionable?' + AXIS_FILTER_PARAM[r.axis] + '=' + encodeURIComponent(r.category);
    return '<a href="' + esc(link) + '" style="display:flex; flex-direction:column; gap:3px; padding:6px 8px; ' +
      'background:#fff; border:1px solid var(--border,#e5e5e2); border-left:3px solid ' + borderColor(r.quad_stance) +
      '; border-radius:6px; width:' + TILE_WIDTH + '; flex:0 0 ' + TILE_WIDTH + '; text-decoration:none;">' +
      '<div style="display:flex; flex-wrap:wrap; gap:2px;">' + quadBadge(r.quad_stance) + '</div>' +
      '<div style="font-size:10.5px; font-weight:700; color:var(--text-1,#1c1917); white-space:nowrap; ' +
      'overflow:hidden; text-overflow:ellipsis;" title="' + esc(r.category) + '">' + esc(r.category) + '</div>' +
      '<div style="font-size:9px; color:var(--text-2,#57534e); font-family:ui-monospace,monospace;">' +
      pct + '% <span style="color:var(--text-3,#a8a29e);">(' + r.n_above + '/' + r.n_tracked + ')</span></div>' +
      '</a>';
  }

  function sortedByConviction(axisRows) {
    return axisRows.slice().sort(function (a, b) { return convictionScore(b) - convictionScore(a); });
  }

  // 2026-09-01 -- axis-name label, same width/border/padding/radius as
  // categoryBox() so it reads as "one of the boxes" -- tinted background
  // (not white) + no border-left color distinguishes it from an actual
  // clickable category box at a glance.
  function axisHeaderChip(axisKey) {
    return '<div style="display:flex; align-items:center; justify-content:center; padding:6px 8px; ' +
      'background:var(--card-bg-alt,#f5f5f4); border:1px solid var(--border,#e5e5e2); border-radius:6px; ' +
      'width:' + TILE_WIDTH + '; flex:0 0 ' + TILE_WIDTH + '; text-align:center; font-size:9px; ' +
      'font-weight:700; color:var(--text-3,#a8a29e); text-transform:uppercase; letter-spacing:.05em;">' +
      esc(AXIS_LABEL[axisKey]) + '</div>';
  }

  // 2026-09-01 -- rearranged into 3 side-by-side groups, each its own
  // label + a fixed-column CSS grid of that axis's boxes (wraps into
  // multiple rows on its own, independent of the other axes) -- user's
  // own sketch: "[asset class] [1][2] [Sector] 1 2 3 4 [Style] 1 2 3 4 /
  // [3][4] 5 6 7 8 5 6 7 8 / [5][6] 9 10 11 12 9 10". Replaces the single
  // continuous flow from the previous version -- each axis's boxes now
  // stay within their own column block instead of spilling into the next
  // axis's row.
  function axisGroupHtml(axisKey, axisRows) {
    var cols = AXIS_COLS[axisKey] || 4;
    var boxesHtml = sortedByConviction(axisRows).map(categoryBox).join('');
    // 2026-09-01 -- no gap between the axis label and its own box-grid
    // (was 6px) -- user: "removing the margin before those boxes would
    // do it" (paired with the TILE_WIDTH shrink above to kill the
    // horizontal scrollbar).
    return '<div style="display:flex; gap:0; align-items:flex-start;">' +
      axisHeaderChip(axisKey) +
      '<div style="display:grid; grid-template-columns:repeat(' + cols + ', ' + TILE_WIDTH + '); gap:6px;">' +
      boxesHtml + '</div></div>';
  }

  // 2026-09-01 follow-up -- nowrap: all 3 groups stay on one line (Style
  // was dropping below Asset Class + Sector once their combined width
  // exceeded the column) -- user: "Style should be in the same lines as
  // other two. whole section needs to sit besides sector." overflow-x
  // is the safety net if the column is ever too narrow to fit all 3,
  // instead of silently clipping Style off the edge.
  function boxGridHtml(byAxis) {
    return '<div style="display:flex; gap:14px; flex-wrap:nowrap; align-items:flex-start; ' +
      'padding:0 8px 10px; overflow-x:auto;">' +
      AXIS_ORDER.map(function (a) { return axisGroupHtml(a, byAxis[a]); }).join('') + '</div>';
  }

  // 2026-09-01 -- collapse/expand moved OFF the panel body entirely, onto
  // its own button on the filter bar (#qrFilterToggle, web/index.html),
  // same placement as the Hedgeye/News toggles beside it -- user: "add a
  // button to collapse or expand just like HE panel buttons next to it on
  // the filter bar." The panel body no longer carries any toggle control
  // or header line of its own -- just the axis chips + boxes.
  function render(data) {
    var panel = document.getElementById('quadRotationPanel');
    var body = document.getElementById('quadRotationPanelBody');
    if (!panel || !body) return;
    var rows = (data && data.rows) || [];
    if (!rows.length) { panel.style.display = 'none'; return; }

    var collapsed = localStorage.getItem('qrPanel_collapsed') === '1';
    var byAxis = {};
    AXIS_ORDER.forEach(function (a) { byAxis[a] = []; });
    rows.forEach(function (r) { if (byAxis[r.axis]) byAxis[r.axis].push(r); });

    body.innerHTML = '<div id="qrPanelBody" style="display:' + (collapsed ? 'none' : 'block') + ';">' +
      boxGridHtml(byAxis) + '</div>';
    panel.style.display = 'block';
    _qrSyncToggleButton(collapsed);
  }

  function _qrSyncToggleButton(collapsed) {
    var btn = document.getElementById('qrFilterToggle');
    if (!btn) return;
    btn.innerHTML = '🧭 ' + (collapsed ? '&#9652;' : '&#9662;');
    btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Quad Rotation');
  }

  window._qrPanelToggle = function () {
    var body = document.getElementById('qrPanelBody');
    if (!body) return;
    var nowHidden = body.style.display === 'none';
    body.style.display = nowHidden ? 'block' : 'none';
    localStorage.setItem('qrPanel_collapsed', nowHidden ? '0' : '1');
    _qrSyncToggleButton(!nowHidden);
  };

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  async function load() {
    try {
      var d = currentDate();
      var data = await fetchJson('/api/actionable/quad-rotation' + (d ? '?date=' + encodeURIComponent(d) : ''));
      render(data);
    } catch (e) {
      var el = document.getElementById('quadRotationPanel');
      if (el) el.style.display = 'none';
    }
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    var toggleBtn = document.getElementById('qrFilterToggle');
    if (toggleBtn) toggleBtn.addEventListener('click', window._qrPanelToggle);
    setTimeout(load, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
