/* market_read.js — TASK_145: "Market Read" panel for the Dashboard screen
 * (index.html). Replaces web/quad_rotation_panel.js (2026-08-31, now
 * retired) in the same slot (#quadRotationPanel, middle column) and reuses
 * its collapse/expand button (#qrFilterToggle) + localStorage key
 * (qrPanel_collapsed) so the user's collapsed/expanded state carries over.
 *
 * Design: docs/market_state_factor_sss_design.md (Addendum A-H). Mockup
 * (acceptance reference, same bands/columns/glyphs): docs/mockups/
 * market_read_one_picture_mockup.html.
 *
 * Reads:
 *   GET /api/market-read?date=D          -- breadth strip + theme grid + headline
 *   GET /api/market-read/sectors?date=D  -- SSS sector cards
 *
 * Renders:
 *   - Breadth strip + theme grid into #quadRotationPanelBody
 *   - Headline sentence + conflict count into a sibling div appended to
 *     #regimeLineBand (app.js::loadRegimeBand only ever touches
 *     #regimeLineBody's innerHTML, so a sibling here is never clobbered)
 *   - Sector cards into #macroRailSectorEtfs (overwrites macro_areas.js's
 *     own rail render for that one element -- id kept so nothing else
 *     that targets it by id breaks)
 *   - Click a theme row -> scrolls the mapped rail band into view and
 *     briefly highlights it. (Addendum G shipped these 9 panels collapsed
 *     by default; reverted 2026-09-21, user: "display them as before" --
 *     #macroRailsWrap is always visible again, this is now just a jump-to.)
 */
(function () {
  'use strict';

  var BULL = 'var(--mr-bull,#0d9488)';
  var BEAR = 'var(--mr-bear,#c2410c)';
  var NEU = 'var(--mr-neu,#6b7280)';

  var THEME_TO_BAND = {
    'Rates up': 'macroRatesBand', 'Duration': 'macroRatesBand',
    'Credit': 'macroCreditBand', 'USD': 'macroUsdBand',
    'Volatility': 'macroVolatilityBand',
    'Large caps': 'macroTop9Band', 'Small caps': 'macroTop9Band', 'Breadth': 'macroTop9Band',
    'Momentum': 'macroRemainingBand', 'Defensives': 'macroRemainingBand',
    'Cyclicals': 'macroRemainingBand', 'Healthcare': 'macroRemainingBand',
    'Tech/software': 'macroRemainingBand', 'Semis': 'macroRemainingBand',
    'Energy': 'macroCommoditiesBand', 'Precious metals': 'macroCommoditiesBand',
    'Industrial metals': 'macroCommoditiesBand', 'Ags': 'macroCommoditiesBand',
    'Crypto': 'macroCryptoBand',
    'Developed intl': 'macroCountryBand', 'Emerging': 'macroCountryBand',
  };

  var FILTER_PARAM = { sector: 'filter_sector', asset_class: 'filter_asset_class', style: 'filter_style' };

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

  function fmtMoney(v) {
    if (v == null) return '—';
    var abs = Math.abs(v);
    if (abs >= 1000) return (v < 0 ? '-$' : '$') + Math.round(abs / 1000) + 'k';
    return '$' + Math.round(v);
  }

  /* ---- glyph cells: never colour alone (Addendum E4) ---- */
  function voteCell(v, title) {
    var t = title ? ' title="' + esc(title) + '"' : '';
    if (v === 'B') return '<span class="mr-c mr-b"' + t + '>&#9650;</span>';
    if (v === 'S') return '<span class="mr-c mr-s"' + t + '>&#9660;</span>';
    if (v === 'N') return '<span class="mr-c mr-n"' + t + '>&ndash;</span>';
    if (v === 'M') return '<span class="mr-c mr-m"' + t + '>&#9650;/&#9660;</span>';
    return '<span class="mr-c mr-x"' + t + '>&mdash;</span>';
  }

  function stanceCell(v) {
    if (v === 'B') return '<span class="mr-st mr-st-b">&#9650; BULL</span>';
    if (v === 'S') return '<span class="mr-st mr-st-s">&#9660; BEAR</span>';
    if (v === 'M') return '<span class="mr-st mr-st-m">&#9650;/&#9660; SPLIT</span>';
    return '<span class="mr-st mr-st-n">&ndash; NEUTRAL</span>';
  }

  function trendGlyph(v) {
    if (v === 'up') return '<span class="mr-tr mr-tr-up">&#8593;</span>';
    if (v === 'down') return '<span class="mr-tr mr-tr-dn">&#8595;</span>';
    if (v === 'flat') return '<span class="mr-tr">&rarr;</span>';
    return '<span class="mr-tr">&mdash;</span>';
  }

  function quadCell(v, conflict) {
    var cls = 'mr-c ' + (v === 'BULLISH' ? 'mr-b' : v === 'BEARISH' ? 'mr-s' : 'mr-n') + (conflict ? ' mr-qconf' : '');
    var glyph = v === 'BULLISH' ? '&#9650;' : v === 'BEARISH' ? '&#9660;' : v == null ? '&mdash;' : '&ndash;';
    var label = v || 'n/a';
    return '<span class="' + cls + '" title="' + esc(label) + '">' + glyph + ' ' + esc(label) + '</span>';
  }

  function fitCell(fit) {
    var MAP = {
      ok: ['fit-ok', '✓'], exposed: ['fit-warn', '⚠ exposed'],
      conflict: ['fit-warn', '⚠ conflict'], none: ['fit-none', '○ none'],
      split: ['fit-mixed', '~ split'],
    };
    var m = MAP[fit];
    return m ? '<span class="' + m[0] + '">' + m[1] + '</span>' : '<span class="mr-x">&mdash;</span>';
  }

  function memberTitle(cellMembers) {
    if (!cellMembers || !cellMembers.length) return '';
    return cellMembers.map(function (m) { return m.symbol + ' ' + m.stance; }).join(' · ');
  }

  /* ---- inline SVG sparkline (mockup-shape: 2px line, dot on latest, zero line) ---- */
  function sparkline(series, hasZero) {
    var vals = (series || []).filter(function (v) { return v != null; });
    if (vals.length < 2) return '';
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var range = (max - min) || 1;
    var w = 200, h = 34, pad = 3;
    var n = series.length;
    var pts = series.map(function (v, i) {
      if (v == null) return null;
      var x = (i / (n - 1)) * w;
      var y = h - pad - ((v - min) / range) * (h - 2 * pad);
      return [x, y];
    });
    var d = pts.map(function (p, i) { return p ? ((i === 0 || !pts[i - 1] ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)) : ''; }).join(' ');
    var last = pts[pts.length - 1];
    var zeroY = h - pad - ((0 - min) / range) * (h - 2 * pad);
    var zeroLine = (hasZero && min < 0 && max > 0)
      ? '<line class="mr-spark-zero" x1="0" y1="' + zeroY.toFixed(1) + '" x2="' + w + '" y2="' + zeroY.toFixed(1) + '"/>' : '';
    return '<svg class="mr-spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' + zeroLine +
      '<path d="' + d + '"/>' + (last ? '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="3"/>' : '') +
      '</svg>';
  }

  /* ---- Band ② breadth strip ---- */
  var BREADTH_LABEL = {
    RR: 'RR macro board · net bull − bear', ETF: 'ETF Pro · longs − shorts',
    PS: 'PS · names on the ranked list', SSS: 'SSS · rows on list',
  };

  function breadthTile(b) {
    var heroSub = (b.source_code === 'ETF' && b.n_bull != null)
      ? ' <span class="mr-tile-sub">' + b.n_bull + 'L / ' + b.n_bear + 'S</span>' : '';
    var delta = b.delta_vs_3wk;
    var deltaCls = delta > 0 ? 'up' : delta < 0 ? 'dn' : '';
    var deltaTxt = delta == null ? '' :
      (delta > 0 ? '▲ +' : delta < 0 ? '▼ ' : '') + delta + ' vs 3wk ago (' + (b.prior_3wk != null ? b.prior_3wk : '—') + ')';
    return '<div class="mr-tile"><div class="mr-tile-lbl">' + esc(BREADTH_LABEL[b.source_code] || b.source_code) + '</div>' +
      '<div class="mr-tile-hero">' + (b.hero != null ? b.hero : '—') + heroSub + '</div>' +
      '<div class="mr-tile-delta ' + deltaCls + '">' + esc(deltaTxt) + '</div>' +
      sparkline(b.series, b.source_code === 'RR' || b.source_code === 'ETF') + '</div>';
  }

  function breadthStripHtml(data) {
    var tiles = (data.breadth || []).map(breadthTile).join('');
    var flipHtml = (data.flip_days || []).slice(0, 6)
      .map(function (f) { return '<b>' + f.date + ' (' + f.flips + ')</b>'; }).join(' · ');
    return '<div class="mr-sub">BREADTH — four independent lists, 13-week history, dot = latest</div>' +
      '<div class="mr-tiles">' + tiles + '</div>' +
      (flipHtml ? '<div class="mr-flipnote">RR flip days (≥09 outlook changes = regime-shift marker): ' + flipHtml + '</div>' : '');
  }

  /* ---- Band ③ theme grid ---- */
  function themeRowHtml(t) {
    var band = THEME_TO_BAND[t.theme];
    var members = t.members || {};
    var priceTxt = t.price_pct != null ? (t.price_pct + '% (' + t.price_n_above + '/' + t.price_n_tracked + ')') : '—';
    var rowCls = t.quad_conflict ? 'mr-row-conflict' : '';
    return '<tr class="' + rowCls + '" data-mr-theme="' + esc(t.theme) + '"' +
      (band ? ' data-mr-band="' + band + '" tabindex="0" role="button"' : '') + '>' +
      '<td class="mr-theme-cell">' + esc(t.theme) + '</td>' +
      '<td>' + voteCell(t.rr, memberTitle(members.rr)) + '</td>' +
      '<td>' + voteCell(t.etf, memberTitle(members.etf)) + '</td>' +
      '<td>' + voteCell(t.ps, memberTitle(members.ps)) + '</td>' +
      '<td>' + voteCell(t.sss, '') + '</td>' +
      '<td class="mr-num">' + esc(priceTxt) + '</td>' +
      '<td>' + stanceCell(t.stance) + '</td>' +
      '<td class="mr-num">' + (t.agree_n || 0) + '</td>' +
      '<td>' + trendGlyph(t.trend_1w) + '</td>' +
      '<td>' + trendGlyph(t.trend_4w) + '</td>' +
      '<td>' + quadCell(t.quad_says, t.quad_conflict) + '</td>' +
      '<td class="mr-num">' + fmtMoney(t.you_dollar) + '</td>' +
      '<td class="mr-num">' + (t.you_pct != null ? t.you_pct + '%' : '—') + '</td>' +
      '<td>' + fitCell(t.fit) + '</td>' +
      '</tr>';
  }

  // 2026-09-21, user-directed: two-column layout -- Macro + Commodities &
  // real assets stacked on the left, Equity factors + International
  // stacked on the right (matches api/routers/cockpit.py::_MR_GROUPS'
  // labels exactly; a group whose label doesn't match either list would
  // silently land in the right column via the else-branch below).
  var _MR_LEFT_COL_GROUPS = ['Macro', 'Commodities & real assets'];

  function _themeGridColHtml(groups, byTheme) {
    var rows = groups.map(function (g) {
      var body = g.themes.map(function (th) { return byTheme[th] ? themeRowHtml(byTheme[th]) : ''; }).join('');
      return '<tr class="mr-group"><td colspan="14">' + esc(g.label) + '</td></tr>' + body;
    }).join('');
    return '<div class="mr-scroll"><table class="mr-table"><thead><tr>' +
      '<th>Theme</th><th>RR</th><th>ETF</th><th>PS</th><th>SSS</th><th>Price</th>' +
      '<th>Lists</th><th>Ag</th><th>1w</th><th>4w</th><th>Quad says</th><th>You $</th><th>You %</th><th>Fit</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function themeGridHtml(data) {
    var byTheme = {};
    (data.themes || []).forEach(function (t) { byTheme[t.theme] = t; });
    var groups = data.groups || [];
    var leftGroups = groups.filter(function (g) { return _MR_LEFT_COL_GROUPS.indexOf(g.label) !== -1; });
    var rightGroups = groups.filter(function (g) { return _MR_LEFT_COL_GROUPS.indexOf(g.label) === -1; });
    return '<div class="mr-sub">THEMES — what each list says, the vote, the Quad playbook, and your exposure. ' +
      'Click a theme to see its symbols in the macro panels below.</div>' +
      '<div class="mr-grid-2col">' +
      _themeGridColHtml(leftGroups, byTheme) +
      _themeGridColHtml(rightGroups, byTheme) +
      '</div>';
  }

  function headlineHtml(data) {
    var q = data.quad || {};
    return '<div class="mr-headline"><span class="mr-headline-pill">' + esc(data.headline || '') + '</span>' +
      (q.label ? ' <span class="mr-headline-sub">Quad model: ' + esc(q.label) +
        (q.conflicts ? ' · ' + q.conflicts + ' conflicts ⚠' : '') + '</span>' : '') + '</div>';
  }

  function render(data) {
    var panel = document.getElementById('quadRotationPanel');
    var body = document.getElementById('quadRotationPanelBody');
    if (!panel || !body) return;
    if (!data || !(data.themes || []).length) { panel.style.display = 'none'; return; }

    var collapsed = localStorage.getItem('qrPanel_collapsed') === '1';
    body.innerHTML = '<div id="qrPanelBody" style="display:' + (collapsed ? 'none' : 'block') + ';">' +
      breadthStripHtml(data) + themeGridHtml(data) + '</div>';
    panel.style.display = 'block';
    _qrSyncToggleButton(collapsed);

    var headlineBand = document.getElementById('regimeLineBand');
    if (headlineBand) {
      var h = document.getElementById('mrHeadlineLine');
      if (!h) {
        h = document.createElement('div');
        h.id = 'mrHeadlineLine';
        headlineBand.appendChild(h);
      }
      h.innerHTML = headlineHtml(data);
    }

    body.querySelectorAll('[data-mr-band]').forEach(function (row) {
      row.addEventListener('click', function () { _mrExpandRail(row.getAttribute('data-mr-band')); });
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') _mrExpandRail(row.getAttribute('data-mr-band'));
      });
    });
  }

  function _mrExpandRail(bandId) {
    // #macroRailsWrap is always visible again (reverted 2026-09-21) -- this
    // is just a scroll-to-and-highlight now, no show/hide step needed.
    var band = bandId && document.getElementById(bandId);
    if (band) {
      band.classList.add('mr-rail-highlight');
      band.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(function () { band.classList.remove('mr-rail-highlight'); }, 2000);
    }
  }
  window._mrExpandRail = _mrExpandRail;

  function _qrSyncToggleButton(collapsed) {
    var btn = document.getElementById('qrFilterToggle');
    if (!btn) return;
    btn.innerHTML = '🧭 ' + (collapsed ? '&#9652;' : '&#9662;');
    btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Market Read');
  }

  window._qrPanelToggle = function () {
    var body = document.getElementById('qrPanelBody');
    if (!body) return;
    var nowHidden = body.style.display === 'none';
    body.style.display = nowHidden ? 'block' : 'none';
    localStorage.setItem('qrPanel_collapsed', nowHidden ? '0' : '1');
    _qrSyncToggleButton(!nowHidden);
  };

  /* ---- Band ④ sector cards (overwrites #macroRailSectorEtfs) ---- */
  function tierBarHtml(s) {
    var total = (s.n_ranked || 0) + (s.n_bench || 0) + (s.n_km || 0);
    if (!total) return '<div class="mr-tier"><span class="mr-tier-e" style="width:100%"></span></div>';
    var pr = (s.n_ranked || 0) / total * 100, pb = (s.n_bench || 0) / total * 100, pk = (s.n_km || 0) / total * 100;
    return '<div class="mr-tier"><span class="mr-tier-r" style="width:' + pr + '%"></span>' +
      '<span class="mr-tier-b" style="width:' + pb + '%"></span>' +
      '<span class="mr-tier-k" style="width:' + pk + '%"></span></div>';
  }

  function sectorCardHtml(s) {
    var chips = (s.chips || []).map(function (c) {
      var cls = c.stance === 'B' ? 'b' : c.stance === 'S' ? 's' : '';
      return '<span class="mr-chip ' + cls + '">' + esc(c.source) + ' ' + esc(c.symbol) + '</span>';
    }).join(' ');
    var top3 = (s.top3 || []).map(function (t) { return esc(t.symbol) + ' ' + t.rank; }).join(' · ');
    var rowsCls = s.divergence ? 'mr-sm-divergence' : '';
    return '<div class="mr-sm ' + rowsCls + '"><div class="mr-sm-name"><b>' + esc(s.sector) + '</b> ' + chips + '</div>' +
      '<div class="mr-sm-two"><div><div class="mr-k">rows</div><div class="mr-v">' + (s.n_rows != null ? s.n_rows : '—') +
      (s.n_rows_med13 != null ? ' <small>med ' + Math.round(s.n_rows_med13) + '</small>' : '') + '</div></div>' +
      '<div><div class="mr-k">book</div><div class="mr-v">' + (s.book_size != null ? s.book_size : '—') +
      (s.book_size_asof && s.book_size_asof !== s.snapshot_date ? ' <small>as of ' + s.book_size_asof + '</small>' : '') +
      '</div></div></div>' +
      sparkline(s.n_rows_series, false) + tierBarHtml(s) +
      '<div class="mr-sm-meta">' + (top3 ? 'top: ' + top3 + ' · ' : '') +
      (s.avg_strength != null ? s.avg_strength + '% avg · ' : '') +
      (s.median_days_on != null ? Math.round(s.median_days_on) + 'd · ' : '') +
      (s.you_dollar ? '<b>you ' + fmtMoney(s.you_dollar) + '</b>' : '') +
      (s.divergence ? ' · <b>rows ↓ book →/↑ — split</b>' : '') + '</div></div>';
  }

  function renderSectors(data) {
    var container = document.getElementById('macroRailSectorEtfs');
    if (!container) return;
    var sectors = (data && data.sectors) || [];
    if (!sectors.length) return;
    var total = data.total;
    var insight = (total && total.n_rows != null && total.book_size != null)
      ? '<div class="mr-ins">Total: rows ' + total.n_rows + ' · books ' + total.book_size + '</div>' : '';
    container.innerHTML = insight + '<div class="mr-sect">' + sectors.map(sectorCardHtml).join('') + '</div>';
  }

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  async function load() {
    try {
      var d = currentDate();
      var qs = d ? '?date=' + encodeURIComponent(d) : '';
      var data = await fetchJson('/api/market-read' + qs);
      render(data);
      var sectorData = await fetchJson('/api/market-read/sectors' + qs);
      renderSectors(sectorData);
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
    setTimeout(load, 700);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
