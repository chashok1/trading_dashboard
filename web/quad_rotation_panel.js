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

  function boxesRowHtml(axisRows) {
    var sorted = axisRows.slice().sort(function (a, b) { return convictionScore(b) - convictionScore(a); });
    return '<div style="display:flex; gap:6px; flex-wrap:wrap; padding:0 8px 10px;">' +
      sorted.map(categoryBox).join('') + '</div>';
  }

  function axisLabelHtml(axisKey) {
    return '<div style="padding:2px 8px 3px; font-size:9px; font-weight:700; color:var(--text-3,#a8a29e); ' +
      'text-transform:uppercase; letter-spacing:.05em;">' + esc(AXIS_LABEL[axisKey]) + '</div>';
  }

  function axisSectionHtml(axisRows, axisKey) {
    return axisLabelHtml(axisKey) + boxesRowHtml(axisRows);
  }

  // 2026-09-01 -- header line ("QUAD ROTATION · date · N bullish
  // candidates") removed entirely, and the collapse/expand toggle moved
  // onto the Asset Class label row instead of its own header row -- user:
  // "move expand to the same row as Asset class and remove the line QUAD
  // ROTATION 2026-08-31 · 17 bullish candidates." Asset Class's label row
  // is now the panel's only always-visible element (everything else,
  // including its own boxes, lives inside the collapsible #qrPanelBody).
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

    var firstAxis = AXIS_ORDER[0];
    var restAxes = AXIS_ORDER.slice(1);

    var labelRowHtml =
      '<div style="display:flex; align-items:center; gap:8px; padding:6px 8px 3px; cursor:pointer;" ' +
      'onclick="window._qrPanelToggle()">' +
      '<span style="font-size:9px; font-weight:700; color:var(--text-3,#a8a29e); text-transform:uppercase; ' +
      'letter-spacing:.05em;">' + esc(AXIS_LABEL[firstAxis]) + '</span>' +
      '<button id="qrPanelToggle" class="btn-icon btn-icon-sm ' + (collapsed ? 'icon-off' : 'icon-on') +
      '" style="margin-left:auto; background:none; border:none; cursor:pointer; color:var(--text-3,#a8a29e); ' +
      'font-size:11px;">' + (collapsed ? '&#9656; expand' : '&#9662; collapse') + '</button>' +
      '</div>';

    var bodyHtml = '<div id="qrPanelBody" style="display:' + (collapsed ? 'none' : 'block') + ';">' +
      boxesRowHtml(byAxis[firstAxis]) +
      restAxes.map(function (a) { return axisSectionHtml(byAxis[a], a); }).join('') +
      '</div>';

    body.innerHTML = labelRowHtml + bodyHtml;
    panel.style.display = 'block';
  }

  window._qrPanelToggle = function () {
    var body = document.getElementById('qrPanelBody');
    var btn = document.getElementById('qrPanelToggle');
    if (!body) return;
    var nowHidden = body.style.display === 'none';
    body.style.display = nowHidden ? 'block' : 'none';
    if (btn) btn.innerHTML = nowHidden ? '&#9656; expand' : '&#9662; collapse';
    localStorage.setItem('qrPanel_collapsed', nowHidden ? '0' : '1');
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
    setTimeout(load, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
