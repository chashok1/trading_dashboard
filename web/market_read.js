/* market_read.js — TASK_145: "Market Read" panel for the Dashboard screen
 * (index.html). Replaces web/quad_rotation_panel.js (2026-08-31, now
 * retired) in the same slot (#quadRotationPanel, middle column).
 *
 * 2026-09-23 -- the single #qrFilterToggle button on the filter bar (far
 * from the panel, controlled Breadth+Themes together) was replaced with 3
 * small header bars, one directly above each independently-collapsible
 * section: Breadth (#mrBreadthToggle/mrBreadth_collapsed), Themes
 * (#mrThemesToggle/mrThemes_collapsed), and Macro Rail
 * (#macroRailToggle/macroRail_collapsed, static markup in index.html above
 * #macroRailsWrap). See _sectionHeaderHtml/_wireSectionToggle and
 * _applyMacroRailCollapse below.
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
 *   - Sector cards into #marketReadSectorCards -- its own standalone
 *     section (index.html), between the rail-panel group (#macroRailsWrap)
 *     and the filter bar. Used to share #macroRailSectorEtfs with
 *     macro_areas.js's own ETF-row Sectors rail panel (one script
 *     overwriting the other's render a beat later, visibly flashing) --
 *     separated 2026-09-22 into its own container. User: "These panels
 *     should be in their own section in the middle column above the filter
 *     bar and below the panels (volatility/major markets/etc)."
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

  // 2026-09-21, user-directed: "SSS/ETF/PS tiles -> can you change line
  // graph to green (+ve) and red (-ve) bar graph" -- RR/CALL keep the line
  // sparkline below, untouched. Bar heights still scaled min/max like the
  // line chart (so week-to-week variation stays legible in this small a
  // space), but color now carries the +ve/-ve read:
  //   colorMode 'sign'  (ETF, net can genuinely go negative) -- green if
  //     the value itself is >= 0, red if < 0.
  //   colorMode 'delta' (SSS/PS, counts are always >= 0 so raw sign is
  //     always "positive" and would never show red) -- green if this
  //     point is higher than the previous one, red if lower, per user:
  //     "color by week-over-week change."
  // "MM/DD" from an ISO date string, same slicing convention used elsewhere
  // (e.g. web/market_bar.js's tape date label).
  function _mrShortDate(iso) {
    return (iso && /^\d{4}-\d{2}-\d{2}/.test(iso)) ? iso.slice(5, 7) + '/' + iso.slice(8, 10) : '';
  }

  function _seriesMax(series) {
    var vals = (series || []).filter(function (v) { return v != null; });
    return vals.length ? Math.max.apply(null, vals) : null;
  }

  // scaleMax (2026-09-22, user-directed: "make bar sizes proportionate to
  // all tiles data not just one by itself"): when given, bars scale
  // 0..scaleMax instead of this series' own local min..max -- lets every
  // sector card's bar chart share one scale (renderSectors passes the
  // largest n_rows seen across ALL sectors' 13-week history) so a
  // 1-row sector's bar doesn't read as "full" next to Software's 13-row
  // history. Breadth-strip callers (Band ②) omit it, keeping their
  // existing per-series local scaling unchanged.
  function barSparkline(series, colorMode, dates, scaleMax) {
    var vals = (series || []).filter(function (v) { return v != null; });
    if (vals.length < 2) return '';
    var min = scaleMax != null ? 0 : Math.min.apply(null, vals);
    var max = scaleMax != null ? scaleMax : Math.max.apply(null, vals);
    var range = (max - min) || 1;
    var w = 200, h = 34, pad = 3;
    var n = series.length;
    var barW = w / n;
    var gap = Math.min(2, barW * 0.15);
    var bars = '';
    for (var i = 0; i < n; i++) {
      var v = series[i];
      if (v == null) continue;
      var frac = (v - min) / range;
      var barH = Math.max(1, frac * (h - 2 * pad));
      var x = i * barW + gap / 2;
      var bw = Math.max(1, barW - gap);
      var y = h - pad - barH;
      var cls;
      if (colorMode === 'sign') {
        cls = v >= 0 ? 'mr-bar-up' : 'mr-bar-dn';
      } else {
        var prev = i > 0 ? series[i - 1] : null;
        cls = prev == null ? 'mr-bar-flat' : v > prev ? 'mr-bar-up' : v < prev ? 'mr-bar-dn' : 'mr-bar-flat';
      }
      // 2026-09-21, user-directed: "bar hover/pop over should show the
      // number" -- native SVG <title> gives a real browser tooltip on
      // hover, no JS tooltip system needed.
      // 2026-09-22 follow-up, user-directed: "I need to see popover
      // anywhere i hover on the bar even if the bar is so small" -- a
      // near-zero bar leaves most of its column empty above it, so the
      // <title> now lives on a full-column invisible hit rect
      // (.mr-bar-hit), not the visible (possibly tiny) colored bar.
      var dateStr = _mrShortDate(dates && dates[i]);
      var tip = (dateStr ? dateStr + ': ' : '') + v;
      var colX = i * barW;
      bars += '<rect class="' + cls + '" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
          '" width="' + bw.toFixed(1) + '" height="' + barH.toFixed(1) + '"></rect>' +
        '<rect class="mr-bar-hit" x="' + colX.toFixed(1) + '" y="0" width="' + barW.toFixed(1) +
          '" height="' + h + '"><title>' + esc(tip) + '</title></rect>';
    }
    return '<svg class="mr-spark mr-bar-spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' + bars + '</svg>';
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
  // 2026-09-21, user-directed: order SSS/ETF/PS/CALL/RR (matches the API's
  // own iteration order in api/routers/cockpit.py::get_market_read -- both
  // kept in sync since breadthTile just maps data.breadth in array order).
  var BREADTH_NAME = { SSS: 'SSS', ETF: 'ETF Pro', PS: 'PS', CALL: 'CALL', RR: 'RR macro board' };
  // 2026-09-21 follow-up, user-directed: RR's original "net" hero was
  // actively unhelpful (mixes ~60 unrelated instruments into one score
  // that can cancel itself out) -- switched to a plain flip count first,
  // then user: "RR -> change it longs - shorts" -- kept the flip-count
  // fix (still avoids the cancellation problem) but broke it into a
  // directional net (etl/derive_market_read.py::rr_flip_direction_counts:
  // how many symbols flipped TO bullish vs TO bearish), same ETF/CALL
  // shape. CALL's 30-day standing net was also unhelpful (barely moves
  // day to day) -- first tried a plain turnover count, but user: "CALL
  // needs to go back to longs vs shorts" -- so it keeps the ETF-style
  // net-based shape too, just recomputed over the trailing 5 days
  // (call_turnover_counts) instead of the 30-day standing window. SSS/PS
  // are the only ones left on the plain-count path ("locked", untouched).
  // See docs/migrations.md this date for the full discussion.
  var _MR_NET_BASED = { ETF: 1, CALL: 1, RR: 1 };
  // Net-based sources: [bull-side word, bear-side word] for the header text.
  // 2026-09-21, user-directed ("BULLISH - BEARISH"): RR's ~60 instruments
  // (indices, rates, FX, commodities) don't all carry a "long/short"
  // trading concept the way ETF/CALL's equity lists do -- bull/bear wording
  // fits its own BULLISH/BEARISH outlook data better.
  var _MR_NET_WORDS = { ETF: ['longs', 'shorts'], CALL: ['longs', 'shorts'], RR: ['bull', 'bear'] };
  // Single-sided count sources: unit text after the raw count.
  var _MR_COUNT_UNIT = { SSS: 'rows on list', PS: 'names on the ranked list' };

  // 2026-09-21, user-directed exact format:
  // "▼ -11 vs 3wk ago (46) · ▼ -44 vs max 13wk 79" -- both comparisons get
  // their own arrow + sign, colored independently (a tile can be up vs one
  // reference and down vs the other).
  function _mrDeltaSeg(delta, label) {
    if (delta == null) return '';
    var cls = delta > 0 ? 'up' : delta < 0 ? 'dn' : '';
    var txt = (delta > 0 ? '▲ +' : delta < 0 ? '▼ ' : '') + delta + ' vs ' + label;
    return '<span class="' + cls + '">' + esc(txt) + '</span>';
  }

  // 2026-09-21, user-directed: "number don't mean anything here [as its own
  // line] -- you can display them in the header text itself", e.g.
  // "SSS · 33 rows on list" / "ETF Pro (-3) · 17 longs − 20 shorts".
  // Replaces the old standalone big hero number + separate L/S sub-label.
  function _mrBreadthHeaderText(b) {
    var name = BREADTH_NAME[b.source_code] || b.source_code;
    if (_MR_NET_BASED[b.source_code]) {
      var words = _MR_NET_WORDS[b.source_code] || ['bull', 'bear'];
      var net = b.hero != null ? b.hero : '—';
      var bull = b.n_bull != null ? b.n_bull : '—';
      var bear = b.n_bear != null ? b.n_bear : '—';
      return name + ' (' + net + ') · ' + bull + ' ' + words[0] + ' − ' + bear + ' ' + words[1];
    }
    var unit = _MR_COUNT_UNIT[b.source_code] || '';
    var hero = b.hero != null ? b.hero : '—';
    return name + ' · ' + hero + (unit ? ' ' + unit : '');
  }

  // SSS/PS are plain counts (never negative) -> color by week-over-week
  // change. ETF/CALL/RR are all now directional nets that can genuinely
  // cross zero (RR's flip direction: more flip-to-bullish than flip-to-
  // bearish, or vice versa) -> color by sign.
  var _MR_BAR_CHART = { SSS: 'delta', ETF: 'sign', PS: 'delta', CALL: 'sign', RR: 'sign' };

  function breadthTile(b) {
    var seg3wk = _mrDeltaSeg(b.delta_vs_3wk, '3wk ago (' + (b.prior_3wk != null ? b.prior_3wk : '—') + ')');
    var segMax = (b.hero != null && b.max_13wk != null)
      ? _mrDeltaSeg(b.hero - b.max_13wk, 'max 13wk ' + b.max_13wk) : '';
    var deltaLine = [seg3wk, segMax].filter(Boolean).join(' · ');
    var barMode = _MR_BAR_CHART[b.source_code];
    var chart = barMode ? barSparkline(b.series, barMode, b.series_dates) : sparkline(b.series, !!_MR_NET_BASED[b.source_code]);
    // 2026-09-21, user-directed: "Show current/Max right justified and
    // take first two lines combined for height" -- a right-justified
    // "current/max" readout, vertically centered against the header+delta
    // block (same flex row), chart still full-width below.
    var curMax = '', curMaxCls = '';
    if (b.hero != null && b.max_13wk != null) {
      curMax = b.hero + '/' + b.max_13wk;
      // 2026-09-21, user-directed: "Use if the count is with in 20% of
      // max, color it green else red" -- was a strict >=max check (almost
      // always red, since sitting exactly at the 13wk high is rare);
      // now green within 20% of it.
      curMaxCls = b.hero >= b.max_13wk * 0.8 ? 'up' : 'dn';
    }
    // 2026-09-23, user-directed: "differentiate colors for top 4 bar tiles
    // -- one where the count up/down by week and the other longs-shorts up/
    // down" -- .mr-tile-count (SSS/PS, barMode 'delta') switches the bar
    // chart + delta text to blue/gold instead of the shared green/red; the
    // current/max readout below stays green/red on every tile regardless
    // (user: "leave the count as in green or red" -- see styles.css's own
    // comment on .mr-tile-count for the full back-and-forth).
    var tileModeCls = barMode === 'delta' ? ' mr-tile-count' : '';
    return '<div class="mr-tile' + tileModeCls + '">' +
      '<div class="mr-tile-top">' +
        '<div class="mr-tile-left">' +
          '<div class="mr-tile-lbl">' + esc(_mrBreadthHeaderText(b)) + '</div>' +
          '<div class="mr-tile-delta">' + deltaLine + '</div>' +
        '</div>' +
        (curMax ? '<div class="mr-tile-curmax ' + curMaxCls + '" title="current / max 13wk">' + esc(curMax) + '</div>' : '') +
      '</div>' +
      chart + '</div>';
  }

  function breadthStripHtml(data) {
    var tiles = (data.breadth || []).map(breadthTile).join('');
    return '<div class="mr-tiles">' + tiles + '</div>';
  }

  // 2026-09-23, user-directed: this note used to sit under the breadth tiles
  // (.mr-flipnote) -- moved into the "Breadth" header bar itself (see
  // render()) alongside the new collapse button, so it now returns bare text
  // instead of a wrapping div.
  function flipNoteText(data) {
    var flipHtml = (data.flip_days || []).slice(0, 6)
      .map(function (f) { return '<b>' + f.date + ' (' + f.flips + ')</b>'; }).join(' · ');
    return flipHtml ? 'RR flip days (≥09 outlook changes = regime-shift marker): ' + flipHtml : '';
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
    return '<div class="mr-grid-2col">' +
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

  // 2026-09-23 -- small header bar (same .msr-section-hdr chrome as the
  // macro rail panels) above each of the 3 independently-collapsible
  // sections in this column: Breadth, Themes, Macro Rail. Replaces the old
  // single #qrFilterToggle button on the filter bar (far from the panel it
  // controlled, and controlled Breadth+Themes together as one block).
  function _sectionHeaderHtml(title, extraHtml, btnId, collapsed) {
    return '<div class="msr-section-hdr">' + esc(title) +
      (extraHtml ? '<span class="mr-sect-legend">' + extraHtml + '</span>' : '') +
      '<button class="msr-sort-btn" id="' + btnId + '" type="button" title="Collapse/expand panel" ' +
        'aria-label="' + (collapsed ? 'Expand' : 'Collapse') + ' ' + esc(title) + ' panel">' +
        (collapsed ? '&#9652;' : '&#9662;') + '</button></div>';
  }

  function _wireSectionToggle(btnId, bodyId, storageKey, title) {
    var btn = document.getElementById(btnId);
    var body = document.getElementById(bodyId);
    if (!btn || !body) return;
    btn.addEventListener('click', function () {
      var collapsed = body.style.display !== 'none';
      body.style.display = collapsed ? 'none' : 'block';
      localStorage.setItem(storageKey, collapsed ? '1' : '0');
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' ' + title + ' panel');
    });
  }

  function render(data) {
    var panel = document.getElementById('quadRotationPanel');
    var body = document.getElementById('quadRotationPanelBody');
    if (!panel || !body) return;
    if (!data || !(data.themes || []).length) { panel.style.display = 'none'; return; }

    var breadthCollapsed = localStorage.getItem('mrBreadth_collapsed') === '1';
    var themesCollapsed = localStorage.getItem('mrThemes_collapsed') === '1';
    body.innerHTML =
      _sectionHeaderHtml('Breadth', flipNoteText(data), 'mrBreadthToggle', breadthCollapsed) +
      '<div id="qrBreadthBody" style="display:' + (breadthCollapsed ? 'none' : 'block') + ';">' + breadthStripHtml(data) + '</div>' +
      _sectionHeaderHtml('Themes', '', 'mrThemesToggle', themesCollapsed) +
      '<div id="qrThemesBody" style="display:' + (themesCollapsed ? 'none' : 'block') + ';">' + themeGridHtml(data) + '</div>';
    panel.style.display = 'block';
    _wireSectionToggle('mrBreadthToggle', 'qrBreadthBody', 'mrBreadth_collapsed', 'Breadth');
    _wireSectionToggle('mrThemesToggle', 'qrThemesBody', 'mrThemes_collapsed', 'Themes');

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

  /* ---- Band ④ sector cards (renders into #marketReadSectorCards) ---- */
  var _MEM_KIND_LABEL = { ranked: 'Hedgeye ranked pick', bench: 'Hedgeye benchmark/watchlist', km: 'Hedgeye KM signal' };
  var _MEM_DOT_CLASS = { ranked: 'mr-mem-dot-ranked', bench: 'mr-mem-dot-bench', km: 'mr-mem-dot-km' };

  // 2026-09-22, user-directed: rich hover popover (was a plain native
  // `title` tooltip) -- same floating-div pattern as macro_areas.js's own
  // _macro6Pop/_macro6Show (bulleted list, fixed-position, delegated
  // mouseover/mouseout since rows are rebuilt via innerHTML on every
  // refresh). _memPopData keyed by symbol, rebuilt each memberListHtml()
  // call -- a symbol's held/action/pct data is the same wherever it
  // appears, so one shared map across every sector card is fine.
  // 2026-09-23, user-directed: "pill border green if actionable add, red if
  // reduce" -- consolidated_action's own buy/sell vocabulary (ADD/INCREASE
  // vs REMOVE/REDUCE), same REMOVE+REDUCE="sell"/INCREASE+ADD="buy" grouping
  // web/actionable.js's own _ACTION_GROUPS uses. HOLD/NONE/null stay
  // neutral gray, same as before.
  var _BUY_ACTIONS = { ADD: true, INCREASE: true };
  var _SELL_ACTIONS = { REMOVE: true, REDUCE: true };
  function _actionSide(action) {
    if (_BUY_ACTIONS[action]) return 'buy';
    if (_SELL_ACTIONS[action]) return 'sell';
    return null;
  }
  var _memPopEl = null;
  var _memPopData = {};
  function _memPop() {
    if (_memPopEl) return _memPopEl;
    var el = document.createElement('div');
    el.id = 'mr-mem-pop';
    el.style.cssText = 'display:none; position:fixed; z-index:3000; background:#fff; ' +
      'border:1px solid #d1d5db; border-radius:6px; box-shadow:0 4px 16px rgba(0,0,0,0.18); ' +
      'padding:8px 10px; font-size:10px; color:#1f2937; max-width:260px; white-space:nowrap; ' +
      'pointer-events:none;';
    document.body.appendChild(el);
    _memPopEl = el;
    return el;
  }
  function _memPopHtml(m) {
    var pctColor = m.pct_since_added == null ? '#94a3b8' : (m.pct_since_added < 0 ? '#dc2626' : '#16a34a');
    var pctTxt = m.pct_since_added != null ? (m.pct_since_added >= 0 ? '+' : '') + m.pct_since_added + '%' : 'n/a';
    var kindTxt = (_MEM_KIND_LABEL[m.kind] || 'Unranked') + (m.kind === 'ranked' && m.rank != null ? ' #' + m.rank : '');
    var heldLi;
    if (m.held) {
      var gainColor = (m.gain_dollar != null && m.gain_dollar < 0) ? '#dc2626' : '#16a34a';
      var gainTxt = m.gain_dollar != null ? (m.gain_dollar >= 0 ? '+' : '') + fmtMoney(m.gain_dollar) : 'n/a';
      heldLi = '<li style="margin:2px 0;">Held: <strong>' + (m.market_value != null ? fmtMoney(m.market_value) : '—') +
        '</strong> <span style="color:' + gainColor + ';">(' + esc(gainTxt) + ' unrealized)</span></li>';
    } else {
      heldLi = '<li style="margin:2px 0;color:#94a3b8;">Not held</li>';
    }
    var side = _actionSide(m.action);
    var actColor = side === 'buy' ? '#16a34a' : side === 'sell' ? '#dc2626' : '#9ca3af';
    var actTxt = side === 'buy' ? 'actionable — buy' : side === 'sell' ? 'actionable — sell' : 'not actionable';
    return '<div style="font-weight:700;margin-bottom:4px;">' + esc(m.symbol) + '</div>' +
      '<ul style="margin:0;padding-left:15px;list-style:disc;">' +
        '<li style="margin:2px 0;">' + esc(kindTxt) + '</li>' +
        '<li style="margin:2px 0;">% since added: <span style="color:' + pctColor + ';font-weight:600;">' + esc(pctTxt) + '</span></li>' +
        heldLi +
        '<li style="margin:2px 0;">Action: <strong>' + esc(m.action || 'None') + '</strong> ' +
          '<span style="color:' + actColor + ';">(' + actTxt + ')</span></li>' +
      '</ul>';
  }
  function _memShow(target, m) {
    var pop = _memPop();
    pop.innerHTML = _memPopHtml(m);
    pop.style.display = 'block';
    var rect = target.getBoundingClientRect();
    pop.style.top = (rect.bottom + 4) + 'px';
    pop.style.left = rect.left + 'px';
    requestAnimationFrame(function () {
      var vw = window.innerWidth, vh = window.innerHeight;
      var pr = pop.getBoundingClientRect();
      if (pr.right > vw - 8) pop.style.left = Math.max(8, vw - pr.width - 8) + 'px';
      if (pr.bottom > vh - 8) pop.style.top = Math.max(8, rect.top - pr.height - 4) + 'px';
    });
  }
  function _memHide() {
    if (_memPopEl) _memPopEl.style.display = 'none';
  }
  document.addEventListener('mouseover', function (ev) {
    var el = ev.target.closest && ev.target.closest('.mr-mem[data-mem-sym]');
    if (!el) return;
    var m = _memPopData[el.getAttribute('data-mem-sym')];
    if (m) _memShow(el, m);
  });
  document.addEventListener('mouseout', function (ev) {
    var el = ev.target.closest && ev.target.closest('.mr-mem[data-mem-sym]');
    if (!el) return;
    if (ev.relatedTarget && el.contains(ev.relatedTarget)) return;
    _memHide();
  });

  // 2026-09-22, user-directed: "below the bar chart, display all symbols
  // in SS for that sector sorted by analyst ranked, bench, km signal" --
  // s.members (api/routers/cockpit.py, from hist_sss) is already sorted
  // ranked -> bench -> km, ranked ascending by rank within that group.
  // Follow-up, user-directed: "use color dots before the symbol text ...
  // use some colors for each not green or gray [[kind]] / use $ if
  // position is held, color it green if making money otherwise red / If
  // actionable color the outline green else gray / Popover should have all
  // that information" -> "make it rich popover". Kind dot: blue=ranked,
  // violet=bench, teal=km (green/gray reserved for the $ P&L color and the
  // actionable outline).
  function memberListHtml(s) {
    var members = s.members || [];
    if (!members.length) return '';
    var spans = members.map(function (m) {
      var dotCls = _MEM_DOT_CLASS[m.kind] || 'mr-mem-dot-other';
      var side = _actionSide(m.action);
      var outlineCls = side === 'buy' ? 'mr-mem-buy' : side === 'sell' ? 'mr-mem-sell' : 'mr-mem-noact';
      var label = esc(m.symbol) + (m.kind === 'ranked' && m.rank != null ? ' ' + m.rank : '');
      // 2026-09-22, user-directed ("remove [the meta line] instead just
      // display %change since added"): per-member, not per-sector --
      // pct_since_added already resolves the "oldest available" fallback
      // server-side (api/routers/cockpit.py) when hist_sss.pct_delta itself
      // is missing.
      var pctHtml = '';
      if (m.pct_since_added != null) {
        var pctCls = m.pct_since_added < 0 ? 'dn' : 'up';
        pctHtml = ' <span class="mr-mem-pct ' + pctCls + '">' +
          (m.pct_since_added >= 0 ? '+' : '') + m.pct_since_added + '%</span>';
      }
      var dollar = '';
      if (m.held) {
        var gainCls = (m.gain_dollar != null && m.gain_dollar < 0) ? 'dn' : 'up';
        dollar = ' <span class="mr-mem-dollar ' + gainCls + '">$</span>';
      }
      _memPopData[m.symbol] = m;
      return '<span class="mr-mem ' + outlineCls + '" data-mem-sym="' + esc(m.symbol) + '">' +
        '<span class="mr-mem-dot ' + dotCls + '"></span>' + dollar + label + pctHtml + '</span>';
    });
    return '<div class="mr-sm-members">' + spans.join(' ') + '</div>';
  }

  function sectorCardHtml(s, globalMaxRows) {
    // 2026-09-22, user-directed: source label dropped (was "RR XLU"/"ETF
    // XLU") -- one chip per distinct symbol now, API already picks the
    // higher-priority source per symbol when the same ETF is tracked by
    // more than one (api/routers/cockpit.py's ref_source_precedence join).
    var chips = (s.chips || []).map(function (c) {
      var cls = c.stance === 'B' ? 'b' : c.stance === 'S' ? 's' : '';
      return '<span class="mr-chip ' + cls + '">' + esc(c.symbol) + '</span>';
    }).join(' ');
    // 2026-09-22, user-directed: "go back for that sector -- what was the
    // max number in last 13 weeks like the top panel and use it like 2/13
    // (2 current, 13 max)" -- replaces the plain "med" sub-label with the
    // same current/max-13wk readout + up/dn coloring (>=80% of the 13wk
    // high = green) the breadth strip tiles above use (breadthTile's own
    // curMax). max13 computed client-side from n_rows_series -- the API
    // doesn't send a precomputed max for sectors the way it does for
    // b.max_13wk on the breadth tiles.
    var max13 = _seriesMax(s.n_rows_series);
    // 2026-09-22, user-directed: "move that number next to Sector header
    // right justified [.mr-sm-name, via CSS flex space-between] / display
    // bar chart below that / move tickers [chips] to below that" -- then
    // "No need of header ROWS" -- bare curmax badge, no "rows" label
    // (it sat next to the sector name before as its own labeled grid cell;
    // that context made the label redundant here).
    var rowsVal = (s.n_rows != null && max13 != null)
      ? '<span class="mr-tile-curmax ' + (s.n_rows >= max13 * 0.8 ? 'up' : 'dn') +
        '" title="rows: current / max 13wk">' + s.n_rows + '/' + max13 + '</span>'
      : (s.n_rows != null ? '<span class="mr-tile-curmax">' + s.n_rows + '</span>' : '');
    return '<div class="mr-sm">' +
      // 2026-09-23, user-directed: "display those symbol pills next to the
      // sector header" -- moved from the card's very bottom (2026-09-22's
      // own placement) up onto the name line itself. Name+chips wrapped
      // together in .mr-sm-name-left so justify-content:space-between on
      // .mr-sm-name still only splits TWO items (this wrapper vs. the
      // curmax badge), keeping the chips glued to the sector name instead
      // of floating in the middle of the row.
      '<div class="mr-sm-name"><span class="mr-sm-name-left"><b>' + esc(s.sector) + '</b>' +
      (chips ? ' ' + chips : '') + '</span>' + rowsVal + '</div>' +
      // 2026-09-22, user-directed: line sparkline -> bar chart, matching
      // the breadth strip (Band ②) above -- 'delta' colorMode (week-over-
      // week up/down) is the same mode that panel uses for its own SSS
      // tile, appropriate here too since n_rows is a count, not a signed
      // net. Bonus: barSparkline's per-bar hit-rect gives a native hover
      // tooltip with the actual count, which the line version never had.
      // globalMaxRows (follow-up, user-directed): shared 0..max scale
      // across every sector card instead of each one scaling to its own
      // local min/max.
      barSparkline(s.n_rows_series, 'delta', null, globalMaxRows) +
      memberListHtml(s) +
      // 2026-09-23, user-directed ("remove the line that is end of the
      // tile"): tierBarHtml's ranked/bench/km composition bar dropped --
      // was the last element in the card. Same info is already visible per
      // member via each pill's own colored dot (memberListHtml above).
      // 2026-09-22, user-directed: the whole meta line (top pick, avg%,
      // days-on, your $, divergence flag) dropped -- "remove that instead
      // just display %change since added" per member instead (see
      // memberListHtml's own mr-mem-pct badge + popover above).
      '</div>';
  }

  // 2026-09-22, user-directed: "remove [the 'Total: rows N · books N' line]
  // add number of rows to the 'Sectors (Signal Strength)' header bar at the
  // end right justified" -- same total.n_rows the old .mr-ins line showed,
  // moved into the header (#marketReadSectorsTotal, index.html) instead.
  function _setSectorsHeaderTotal(total) {
    var el = document.getElementById('marketReadSectorsTotal');
    if (el) el.textContent = (total && total.n_rows != null) ? total.n_rows + ' rows' : '';
  }

  function renderSectors(data) {
    var container = document.getElementById('marketReadSectorCards');
    if (!container) return;
    var sectors = (data && data.sectors) || [];
    _setSectorsHeaderTotal(data && data.total);
    // 2026-09-22: own standalone container now (see file header comment) --
    // show an explicit empty state instead of leaving stale "Loading…"
    // markup when there's nothing to show.
    if (!sectors.length) {
      container.innerHTML = '<div class="msr-loading">No sector data.</div>';
      return;
    }
    // 2026-09-22, user-directed: "make bar sizes proportionate to all tiles
    // data not just one by itself" -- one shared scale across every
    // sector's bar chart, the largest single n_rows value seen anywhere in
    // any sector's 13-week history (see barSparkline's own scaleMax param).
    var globalMaxRows = Math.max.apply(null, sectors.map(function (s) { return _seriesMax(s.n_rows_series) || 0; }));
    container.innerHTML = '<div class="mr-sect">' +
      sectors.map(function (s) { return sectorCardHtml(s, globalMaxRows); }).join('') + '</div>';
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

  // 2026-09-22, user-directed: "add hide show button like others" -- own
  // independent collapse toggle for the Sectors (Signal Strength) panel,
  // same mechanism as the Hedgeye/News panels' own toggles (arrow button,
  // localStorage-persisted, own key so it doesn't share state with theirs).
  // Only ever touches #marketReadSectorCards's style.display -- renderSectors()
  // keeps refreshing its innerHTML underneath while collapsed, same
  // "content vs. visibility are separate concerns" split those two panels
  // use (see hedgeye_collapse.js's own header comment).
  var SECTORS_COLLAPSE_KEY = 'marketReadSectors_collapsed';
  function _applySectorsCollapse(collapsed) {
    var body = document.getElementById('marketReadSectorCards');
    var btn = document.getElementById('marketReadSectorsToggle');
    if (body) body.style.display = collapsed ? 'none' : '';
    if (btn) {
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Sectors panel');
    }
  }

  // 2026-09-23 -- Macro Rail header bar is static markup (index.html, above
  // #macroRailsWrap), not JS-rendered like Breadth/Themes above, so it's
  // wired the same way as the Sectors toggle just below: present on page
  // load, own localStorage key, no dependency on a render() pass first.
  var MACRO_RAIL_COLLAPSE_KEY = 'macroRail_collapsed';
  function _applyMacroRailCollapse(collapsed) {
    var body = document.getElementById('macroRailsWrap');
    var btn = document.getElementById('macroRailToggle');
    if (body) body.style.display = collapsed ? 'none' : '';
    if (btn) {
      btn.innerHTML = collapsed ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (collapsed ? 'Expand' : 'Collapse') + ' Macro Rail panel');
    }
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    var railToggle = document.getElementById('macroRailToggle');
    if (railToggle) {
      _applyMacroRailCollapse(localStorage.getItem(MACRO_RAIL_COLLAPSE_KEY) === '1');
      railToggle.addEventListener('click', function () {
        var collapsed = localStorage.getItem(MACRO_RAIL_COLLAPSE_KEY) !== '1';
        localStorage.setItem(MACRO_RAIL_COLLAPSE_KEY, collapsed ? '1' : '0');
        _applyMacroRailCollapse(collapsed);
      });
    }
    var sectToggle = document.getElementById('marketReadSectorsToggle');
    if (sectToggle) {
      _applySectorsCollapse(localStorage.getItem(SECTORS_COLLAPSE_KEY) === '1');
      sectToggle.addEventListener('click', function () {
        var collapsed = localStorage.getItem(SECTORS_COLLAPSE_KEY) !== '1';
        localStorage.setItem(SECTORS_COLLAPSE_KEY, collapsed ? '1' : '0');
        _applySectorsCollapse(collapsed);
      });
    }
    setTimeout(load, 700);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
