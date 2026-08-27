/* macro_areas.js — Macro read card for /actionable (TASK_78/TASK_85/TASK_116).
 *
 * Self-contained; reads GET /api/macro-areas?date=<D>.
 *
 * Renders:
 *   - Compact side-rail rows into #macroRailAreas (TASK_85 primary display)
 *   - Full-width collapsible card into #macroReadCard if present (legacy)
 *
 * Per-row compact layout (side rail, TASK_116 consolidation, refined by
 * several user requests through 2026-07-04 — see
 * docs/market_panel_consolidation_design.md):
 *
 *   Regular area row:
 *     [quad glyph][SYM] ... [Td][Tn][range bar+tick][candle][%chg chip]
 *   Td/Tn/range-bar/candle/%chg are grouped into one `.msr-data-cluster`
 *   flex unit (tight 2px internal gap) with `margin-left:auto` on the
 *   WHOLE cluster, not the chip alone — so the group stays packed together
 *   and is pushed flush to the row's right edge as a unit; the free space
 *   lands between SYM and the cluster, not inside it.
 *
 *   Volatility (gauge) row:
 *     [quad glyph][SYM zone-colored] ... [gauge badge, centered]
 *       ... [volBar][candle][%chg chip] (flush right)
 *   `.msr-gauge-wrap` (flex:1, justify-content:center) sits between SYM and
 *   the trailing `.msr-vol-cluster` (volBar+candle+%chg, no auto-margin of
 *   its own) — the wrap absorbs all the row's free space and centers the
 *   badge inside it, which also has the side effect of pushing the
 *   vol-cluster flush right (matching the other panels), since nothing
 *   else in the row competes for that leftover space.
 *
 *   Sectors row (own rail section) — different anatomy, only change here is
 *   railRangeBar(..., showPct=false): the trailing "NN%" range-bar label is
 *   suppressed and the symbol/sector name column grows to fill that freed
 *   space instead (`.msr-name` is already flex:1; `.msr-etf-row .msr-name-
 *   tick` gets a scoped override for the same effect in the ETF sub-row,
 *   which otherwise uses the fixed-width `.msr-name-tick`).
 */
(function () {
  'use strict';

  /* ── utilities ──────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                 '"': '&quot;', "'": '&#39;' }[c];
      });
  }

  // Wraps _common.js's symbolLink() defensively (same guard style this file
  // already uses for window.mtTip below) -- Yahoo Finance quote-page link on
  // the member symbol text, no separate icon.
  function symLink(html, sym) {
    return (typeof window.symbolLink === 'function') ? window.symbolLink(html, sym) : html;
  }

  function fmtPct(v, digits) {
    if (v === null || v === undefined) return '—';
    return (v * 100).toFixed(digits === undefined ? 0 : digits) + '%';
  }

  /* ── stance arrowhead SVGs (deep-arch "C" style from spec) ─────────── */
  var SVG_UP =
    '<svg class="msr-arrow msr-arrow-long" viewBox="0 0 16 16" aria-hidden="true">' +
      '<path d="M2,12.5 L8,3 L14,12.5 Q8,7 2,12.5 Z" fill="currentColor"/>' +
    '</svg>';

  var SVG_DOWN =
    '<svg class="msr-arrow msr-arrow-short" viewBox="0 0 16 16" aria-hidden="true">' +
      '<path d="M2,3.5 L8,13 L14,3.5 Q8,9 2,3.5 Z" fill="currentColor"/>' +
    '</svg>';

  var SVG_NEUT = '<span class="msr-arrow msr-arrow-neut" aria-hidden="true">&#8212;</span>';

  function stanceArrow(stance) {
    if (stance === 'Long')  return SVG_UP;
    if (stance === 'Short') return SVG_DOWN;
    return SVG_NEUT;
  }

  /* ── Td / Tn diagonal arrows ──────────────────────────────────────── */
  /* val: >0 up (↗), <0 down (↘), 0/null flat (–) */
  function durArrow(val, label) {
    if (val === null || val === undefined) {
      return '<span class="msr-dur msr-dur-flat">' + esc(label) + '&ndash;</span>';
    }
    if (val > 0) {
      return '<span class="msr-dur msr-dur-up" title="' + esc(label) + ' up">' +
        esc(label) + '&#8599;</span>';
    }
    if (val < 0) {
      return '<span class="msr-dur msr-dur-down" title="' + esc(label) + ' down">' +
        esc(label) + '&#8600;</span>';
    }
    return '<span class="msr-dur msr-dur-flat">' + esc(label) + '&ndash;</span>';
  }

  /* ── ETF proxy sub-row (single sector ETF: price/%chg/Td/Tn/Risk Range) ── */
  // Symbol-name color, same convention as rrTape's chips (market_bar.js
  // outlookBg): color by RR outlook, falling back to muted gray when there
  // isn't one.
  function _nameColor(outlook) {
    if (!outlook) return '#888';
    var c = window.outlookColor ? window.outlookColor(outlook) : 'inherit';
    return (c && c !== 'inherit') ? c : '#888';
  }

  // Zone color for Volatility members (TASK_116) — same palette as rrTape's
  // chipHtml zoneColor: investable=green, chop=amber, elevated=red. Used to
  // color the volatility SYMBOL name (not outlook) so an investable VIX
  // reads green on the rail the same way it does on the mini-tape.
  function _zoneColor(zone) {
    if (zone === 'investable') return '#1d9e75';
    if (zone === 'chop')       return '#eab308';
    if (zone === 'elevated')   return '#d4537e';
    return '#888';
  }

  // 7×14 mini candle, reusing market_bar.js's SVG builder via the shared
  // mtTip API (window.mtTip.candleSvg) — no duplicate candle-drawing code.
  function _candleHtml(m) {
    if (!window.mtTip || !window.mtTip.candleSvg) return '';
    return window.mtTip.candleSvg(m.open, m.high, m.low, m.last) || '';
  }

  // Solid %chg chip (tape convention, TASK_116) — replaces the plain colored
  // % text. Honors the member `inverted` flag (HY/HYSPRD: rising = risk-off
  // = red), same convention as market_bar.js's dirClass/INVERTED.
  function _chgChipHtml(pct, inverted) {
    if (pct === null || pct === undefined) return '<span class="msr-chg"></span>';
    var n = Number(pct);
    var flat = Math.abs(n) < 0.001;
    var up = !flat && (inverted ? n < 0 : n > 0);
    var down = !flat && (inverted ? n > 0 : n < 0);
    var bg = up ? '#1d9e75' : down ? '#d4537e' : '#888';
    var txt = flat ? '0.0%' : (n > 0 ? '+' : '') + n.toFixed(1) + '%';
    return '<span class="msr-chg" style="background:' + bg + ';">' + esc(txt) + '</span>';
  }

  // Friendly display name for a non-gauge member (2026-07-04) — ref_macro_
  // area.label is a per-row column that's the AREA's own label repeated for
  // most members (stocks/ETFs: already-readable tickers, left alone) but a
  // genuine override for cryptic ones (futures /XX, $-index tickers, FRED/
  // CGI-suffixed yields, foreign indices — e.g. '/GC' -> 'Gold'). Detect a
  // real override by checking it differs from the area's own label; only
  // then prefer it over the raw symbol.
  function _memberDisplayName(m, area) {
    return (m.label && m.label !== area.label) ? m.label : m.symbol;
  }

  // Native title-attribute tooltip for the compact row (symbol/price/%chg/
  // outlook) — the anatomy no longer shows a separate price column (tape
  // convention: price lives in the hover, only %chg is a visible chip).
  // Includes both the friendly name (if the row is showing one) and the raw
  // symbol, so a renamed row like "Gold" doesn't lose its "/GC" identity.
  function _rowTitle(m, displayName) {
    var parts = [];
    if (displayName && m.symbol && displayName !== m.symbol) {
      parts.push(displayName + ' (' + m.symbol + ')');
    } else if (m.symbol) {
      parts.push(m.symbol);
    }
    var priceTxt = _fmtPrice(m.last);
    if (priceTxt !== null) parts.push(priceTxt);
    if (m.pct_change !== null && m.pct_change !== undefined) {
      parts.push((m.pct_change > 0 ? '+' : '') + Number(m.pct_change).toFixed(2) + '%');
    }
    if (m.outlook) parts.push(m.outlook);
    return parts.join(' — ');
  }

  // Small Quad-score glyph shown before the symbol, same convention as
  // rrTape's chips (market_bar.js _msGlyphTape): green ▲ / red ▼ from
  // drv_macro_score.monthly_score (Hedgeye Quad-calendar-derived), not price.
  function _msGlyph(score) {
    var glyph = '', color = '#888';
    if (score !== null && score !== undefined) {
      var s = Number(score);
      if (s > 0) { glyph = '&#9650;'; color = '#16a34a'; }
      else if (s < 0) { glyph = '&#9660;'; color = '#dc2626'; }
    }
    // Fixed-width slot even when empty, so the symbol text starts at the
    // same x-position on every row regardless of whether it has a score.
    return '<span style="display:inline-block; width:8px; font-size:7px; color:' + color + '; vertical-align:middle;">' + glyph + '</span>';
  }

  // 2026-08-27 -- replaces the old per-sector ETF-proxy sub-row
  // (etfProxyRowHtml -- price/Trade/Trend/RR-position for one ETF like
  // XLF): that same ETF info now has its own full rail panel (see
  // #macroRailSectorEtfs / area_key 'sector_etfs', same ref_macro_area
  // mechanism as Major Markets/Country ETFs), so this sub-row shows what
  // the ETF sub-row DIDN'T: the underlying breadth numbers behind the
  // stance arrows (n stocks, raw % above Trade/Trend, already computed
  // server-side but previously unused), plus your own $ exposure to that
  // sector (drv_category_perf via /api/cockpit/factor-scorecard?axis=
  // sector, the SAME table the Sector factor-scorecard grid and Portfolio
  // Mix's Sector pie use) -- ties the macro breadth read to your actual
  // risk, which the ETF sub-row never did. User: "if we remove sectors
  // ETFs what other information ... would be useful?" -> "yes, implement
  // that."
  function sectorStatsRowHtml(s, exposureMap) {
    var bits = [];
    if (s.n != null) bits.push(s.n + ' stk');
    if (s.pct_above_trade != null) bits.push(Math.round(s.pct_above_trade * 100) + '% Td');
    if (s.pct_above_trend != null) bits.push(Math.round(s.pct_above_trend * 100) + '% Tn');
    var exp = exposureMap && exposureMap[s.sector];
    if (exp && exp.market_value) {
      bits.push((typeof fmtUsd === 'function' ? fmtUsd(exp.market_value, { compact: true }) : '$' + Math.round(exp.market_value))
        + (exp.weight_pct != null ? ' (' + exp.weight_pct.toFixed(1) + '%)' : ''));
    }
    if (!bits.length) return '';
    return '<div class="msr-row msr-sec-stats" style="padding-left:16px; font-size:10px; color:var(--text-3);">'
      + bits.join(' &middot; ') + '</div>';
  }

  /* ── range bar (compact rail version) ──────────────────────────────── */
  // showPct (default true): the trailing "42%"-style label. railAreaRow's
  // regular rows (2026-07-04) pass false since the row is already dense with
  // the candle + Td/Tn + %chg chip; the tick + hover title (still present)
  // carry the same info. renderSectorsPanel's own row doesn't pass it, so
  // it keeps the label unchanged.
  function railRangeBar(rr_pos, hot_pct, cold_pct, showPct) {
    if (rr_pos === null || rr_pos === undefined) {
      return '<span class="mra-muted" style="font-size:9px;">n/a</span>';
    }
    if (showPct === undefined) showPct = true;
    var actualPct = Math.round(rr_pos * 100);   // unclamped, for the label
    var pct    = Math.max(0, Math.min(1, rr_pos));
    var tickPx = Math.round(pct * 100);          // clamped, for bar positioning
    var isHot  = (hot_pct  !== null && hot_pct  !== undefined) ? (rr_pos >= hot_pct)  : (rr_pos >= 0.80);
    var isCold = (cold_pct !== null && cold_pct !== undefined) ? (rr_pos <= cold_pct) : (rr_pos <= 0.20);
    var extreme = isHot || isCold;
    return (
      '<div class="msr-rb-wrap">' +
        '<div class="msr-rb" title="' + actualPct + '% of range">' +
          '<div class="msr-rb-fill" style="width:' + tickPx + '%"></div>' +
          '<div class="msr-rb-tick' + (extreme ? ' extreme' : '') +
               '" style="left:' + tickPx + '%"></div>' +
        '</div>' +
        (showPct ? '<span class="msr-pct">' + actualPct + '%</span>' : '') +
      '</div>'
    );
  }


  /* ── compact area row for side rail ────────────────────────────────── */
  // One row per member symbol, for every area (Volatility already worked this
  // way; every other area used to collapse to a single aggregate row — now
  // all of them break out individually, using the same per-member fields the
  // API already computes (member.trade/trend are already signed ints
  // matching durArrow; member.rr_pos is already a 0-1 fraction matching
  // railRangeBar), so no backend change was needed for this.
  function _fmtPrice(v) {
    if (v === null || v === undefined) return null;
    return v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }

  // Standalone, fixed-width price and %chg columns — siblings of
  // .msr-name-tick (not nested inside it, and not nested inside each other),
  // so both line up at the same x-position on every row regardless of
  // symbol length or how many digits the price/chg happen to have.
  function _priceChgSpan(m) {
    var priceTxt = _fmtPrice(m.last);
    if (priceTxt === null) return '<span class="msr-price"></span><span class="msr-price-chg"></span>';
    var chg = m.pct_change;
    var chgCls = chg > 0 ? 'msr-price-chg-up' : chg < 0 ? 'msr-price-chg-down' : 'msr-price-chg-flat';
    var chgTxt = (chg !== null && chg !== undefined)
      ? (chg > 0 ? '+' : '') + chg.toFixed(2) + '%'
      : '';
    return '<span class="msr-price">' + esc(priceTxt) + '</span>' +
           '<span class="msr-price-chg ' + chgCls + '">' + esc(chgTxt) + '</span>';
  }

  // Row anatomy (TASK_116): [quad glyph][SYM][candle][Td/Tn][range bar+tick]
  // [%chg chip]. Volatility (gauge) swaps Td/Tn+range-bar for the 3-zone
  // volRangeBar and colors SYM by zone instead of outlook; the trailing zone
  // badge stays.
  function railAreaRow(area) {
    var members = area.members || [];
    return members.map(function (m) {
      if (m.role === 'gauge') {
        var zone = m.zone || '—';
        var gaugeClass = zone === 'investable' ? 'msr-gauge-g'
                       : zone === 'elevated'   ? 'msr-gauge-r'
                       : 'msr-gauge-a';
        var volBar = (window.mtTip && window.mtTip.volRangeBar)
          ? window.mtTip.volRangeBar(m.last, m.vol_low, m.vol_high)
          : '<div class="rr-rb"></div>';
        return (
          '<div class="msr-row" title="' + esc(_rowTitle(m)) + '">' +
            '<span class="msr-name msr-name-tick" style="color:' + _zoneColor(zone) + ';">' +
              _msGlyph(m.monthly_score) + symLink(esc(m.label || area.label), m.symbol) +
            '</span>' +
            '<div class="msr-gauge-wrap">' +
              '<span class="msr-gauge ' + gaugeClass + '">' + esc(zone) + '</span>' +
            '</div>' +
            '<div class="msr-vol-cluster">' +
              volBar +
              _candleHtml(m) +
              _chgChipHtml(m.pct_change, m.inverted) +
            '</div>' +
          '</div>'
        );
      }
      var dispName = _memberDisplayName(m, area);
      return (
        '<div class="msr-row" title="' + esc(_rowTitle(m, dispName)) + '">' +
          '<span class="msr-name msr-name-tick" style="color:' + _nameColor(m.outlook) + ';">' +
            _msGlyph(m.monthly_score) + symLink(esc(dispName), m.symbol) +
          '</span>' +
          '<div class="msr-data-cluster">' +
            durArrow(m.trade, 'Td') +
            durArrow(m.trend, 'Tn') +
            railRangeBar(m.rr_pos, area.hot_pct, area.cold_pct, false) +
            _candleHtml(m) +
            _chgChipHtml(m.pct_change, m.inverted) +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  /* ── sectors panel (own side-rail section) ────────────────────────── */
  function renderSectorsPanel(sectors, exposureMap) {
    var container = document.getElementById('macroRailSectors');
    if (!container) return;
    if (!sectors) { container.innerHTML = '<div class="msr-loading">No sector data.</div>'; return; }

    var laggards  = (sectors.laggards  || []).map(esc).join(' · ');
    var rotateIn  = (sectors.rotate_in || []).map(esc).join(' · ');
    var subrows = '';
    if (laggards) subrows += '<div class="msr-sec-subrow"><span class="msr-sec-down">&#9660;</span> <span class="msr-sec-lbl">Laggards:</span> ' + laggards + '</div>';
    if (rotateIn) subrows += '<div class="msr-sec-subrow"><span class="msr-sec-rotate">&#8635;</span> <span class="msr-sec-lbl">Rotate in:</span> ' + rotateIn + '</div>';

    // Full per-sector list — always visible, no collapse toggle
    var all = sectors.all || [];
    var allRows = all.map(function (s) {
      var score     = s.score != null ? s.score : 0;
      var stance    = score >= 0.5 ? 'Long' : 'Short';
      var tradeDir  = s.pct_above_trade  != null ? s.pct_above_trade  - 0.5 : null;
      var trendDir  = s.pct_above_trend  != null ? s.pct_above_trend  - 0.5 : null;
      return '<div class="msr-row">' +
        stanceArrow(stance) +
        '<span class="msr-name">' + esc(s.sector) + '</span>' +
        durArrow(tradeDir,  'Td') +
        durArrow(trendDir,  'Tn') +
        railRangeBar(score, 0.7, 0.3, false) +
      '</div>' + sectorStatsRowHtml(s, exposureMap);
    }).join('');

    if (!subrows && !allRows) subrows = '<span class="mra-muted">—</span>';

    container.innerHTML = '<div class="msr-sec-block">' + subrows + allRows + '</div>';
  }

  /* ── render into side rail ──────────────────────────────────────────── */
  // Each area_key now has its own side-panel section/container (was one
  // blob container for every area concatenated together).
  var _AREA_CONTAINER_ID = {
    volatility:          'macroRailVolatility',
    top9:                'macroRailTop9',
    rates_duration:      'macroRailRates',
    credit:              'macroRailCredit',
    commodities_credit:  'macroRailCommodities',
    usd_currency:        'macroRailUsd',
    country_etfs:        'macroRailCountry',
    crypto:               'macroRailCrypto',
    sector_etfs:         'macroRailSectorEtfs',
    remaining:           'macroRailRemaining',
  };

  // Section-header breadth summary (↑n ↓n), TASK_116 — one id per area_key
  // that has a rail container (Sectors excluded; it keeps its own
  // leaders/laggards summary instead).
  var _AREA_BREADTH_ID = {
    volatility:          'macroBreadthVolatility',
    top9:                'macroBreadthTop9',
    rates_duration:      'macroBreadthRates',
    credit:              'macroBreadthCredit',
    commodities_credit:  'macroBreadthCommodities',
    usd_currency:        'macroBreadthUsd',
    country_etfs:        'macroBreadthCountry',
    crypto:               'macroBreadthCrypto',
    sector_etfs:         'macroBreadthSectorEtfs',
    remaining:           'macroBreadthRemaining',
  };

  function _breadthHtml(area) {
    var members = area.members || [];
    var up = 0, down = 0;
    members.forEach(function (m) {
      if (m.pct_change === null || m.pct_change === undefined) return;
      var n = Number(m.pct_change);
      if (n > 0) up++;
      else if (n < 0) down++;
    });
    if (!up && !down) return '';
    return '<span class="msr-breadth-up">&#8593;' + up + '</span> ' +
           '<span class="msr-breadth-down">&#8595;' + down + '</span>';
  }

  function renderRail(data) {
    var areas = (data && data.areas) || [];
    var byContainer = {};
    areas.forEach(function (area) {
      var containerId = _AREA_CONTAINER_ID[area.area_key];
      if (!containerId) return;
      byContainer[containerId] = (byContainer[containerId] || '') + railAreaRow(area);

      var breadthId = _AREA_BREADTH_ID[area.area_key];
      var breadthEl = breadthId && document.getElementById(breadthId);
      if (breadthEl) breadthEl.innerHTML = _breadthHtml(area);
    });

    Object.keys(_AREA_CONTAINER_ID).forEach(function (key) {
      var containerId = _AREA_CONTAINER_ID[key];
      var container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = byContainer[containerId] || '<div class="msr-loading">No data.</div>';
    });
  }

  /* ── legacy full-width card (kept for backward-compat) ─────────────── */
  function stancePillHtml(stance, conviction) {
    if (!stance) return '<span class="mra-stance mra-neutral">—</span>';
    var cls = stance === 'Long' ? 'mra-long'
            : stance === 'Short' ? 'mra-short'
            : 'mra-neutral';
    var convTxt = (conviction !== null && conviction !== undefined)
      ? ' <span class="mra-conv">' + Math.round(conviction * 100) + '%</span>'
      : '';
    return '<span class="mra-stance ' + cls + '">' + esc(stance) + convTxt + '</span>';
  }

  function durationChip(val, label) {
    if (val === null || val === undefined) return '<span class="mra-chip mra-chip-na">' + label + ':—</span>';
    var cls = val > 0 ? 'mra-chip-bull' : val < 0 ? 'mra-chip-bear' : 'mra-chip-flat';
    var arrow = val > 0 ? '▲' : val < 0 ? '▼' : '—';
    return '<span class="mra-chip ' + cls + '">' + label + ':' + arrow + '</span>';
  }

  function rrBarHtml(rr_pos, is_hot, is_cold) {
    if (rr_pos === null || rr_pos === undefined) return '<span class="mra-no-rr">n/a</span>';
    var pct = Math.max(0, Math.min(1, rr_pos));
    var tickPct = Math.round(pct * 100);
    var fillCls = is_hot ? ' mra-rb-hot' : is_cold ? ' mra-rb-cold' : '';
    return (
      '<div class="rr-rb mra-rb" title="' + (tickPct) + '% of range">' +
        '<div class="rr-rb-fill' + fillCls + '" style="width:' + tickPct + '%"></div>' +
        '<div class="rr-rb-tick" style="left:' + tickPct + '%"></div>' +
      '</div>' +
      '<span class="mra-rb-label">' + tickPct + '%</span>'
    );
  }

  function extremesHtml(hot, cold) {
    var out = '';
    (hot || []).forEach(function (sym) {
      out += '<span class="mra-ext-hot" title="Overbought — trim">' + esc(sym) + ' ▲</span> ';
    });
    (cold || []).forEach(function (sym) {
      out += '<span class="mra-ext-cold" title="Oversold — add">' + esc(sym) + ' ▼</span> ';
    });
    return out || '<span class="mra-muted">—</span>';
  }

  function areaRowHtml(area) {
    var isVol   = area.area_key === 'volatility';
    var isRates = area.area_key === 'rates';

    if (isVol) {
      var vix_m = (area.members || []).find(function (m) { return m.role === 'gauge'; });
      var zone = vix_m ? (vix_m.zone || '—') : '—';
      var zoneClass = zone === 'investable' ? 'mra-zone-g'
                    : zone === 'elevated'   ? 'mra-zone-r'
                    : 'mra-zone-a';
      return (
        '<tr class="mra-row">' +
          '<td class="mra-area-name">' + esc(area.label) + '</td>' +
          '<td><span class="mra-zone ' + zoneClass + '">' + esc(zone) + '</span></td>' +
          '<td colspan="3" class="mra-muted">gauge only</td>' +
        '</tr>'
      );
    }
    if (isRates) {
      return (
        '<tr class="mra-row">' +
          '<td class="mra-area-name">' + esc(area.label) + '</td>' +
          '<td>' + stancePillHtml(area.stance, area.conviction) + '</td>' +
          '<td>' + durationChip(area.trade, 'Trade') + durationChip(area.trend, 'Trend') + '</td>' +
          '<td class="mra-muted mra-small">rate read</td>' +
          '<td>' + extremesHtml(area.extremes_hot, area.extremes_cold) + '</td>' +
        '</tr>'
      );
    }
    return (
      '<tr class="mra-row">' +
        '<td class="mra-area-name">' + esc(area.label) + '</td>' +
        '<td>' + stancePillHtml(area.stance, area.conviction) + '</td>' +
        '<td>' + durationChip(area.trade, 'Trade') + durationChip(area.trend, 'Trend') + '</td>' +
        '<td class="mra-rb-wrap">' +
          rrBarHtml(area.rr_pos, (area.extremes_hot || []).length > 0,
                                  (area.extremes_cold || []).length > 0) +
        '</td>' +
        '<td>' + extremesHtml(area.extremes_hot, area.extremes_cold) + '</td>' +
      '</tr>'
    );
  }

  function sectorsHtml(sectors) {
    if (!sectors) return '';
    function chips(arr, cls) {
      return (arr || []).map(function (s) {
        return '<span class="mra-sec-chip ' + cls + '">' + esc(s) + '</span>';
      }).join(' ');
    }
    return (
      '<tr class="mra-row mra-sectors-row">' +
        '<td class="mra-area-name">Sectors</td>' +
        '<td colspan="4">' +
          '<span class="mra-sec-label">Leaders:</span> ' +
          chips(sectors.leaders, 'mra-sec-bull') + '  ' +
          '<span class="mra-sec-label">Laggard:</span> ' +
          chips(sectors.laggards, 'mra-sec-bear') + '  ' +
          '<span class="mra-sec-label">Rotate in:</span> ' +
          chips(sectors.rotate_in, 'mra-sec-rotate') +
        '</td>' +
      '</tr>'
    );
  }

  function corrPlaceholderHtml() {
    return (
      '<tr class="mra-row mra-corr-row" id="macroCorrRow">' +
        '<td class="mra-area-name">USD Corr</td>' +
        '<td colspan="4" id="macroCorrSummary">' +
          '<span class="mra-muted">Loading…</span>' +
        '</td>' +
      '</tr>'
    );
  }

  function renderLegacyCard(data) {
    var card = document.getElementById('macroReadCard');
    if (!card) return;

    var areas   = (data && data.areas) || [];
    var sectors = data && data.sectors;
    var top_down = (data && data.top_down) || '';

    var rows = areas.map(areaRowHtml).join('');
    rows += sectorsHtml(sectors);
    rows += corrPlaceholderHtml();

    card.innerHTML =
      '<div class="mra-posture">' + esc(top_down) + '</div>' +
      '<div class="mra-body">' +
        '<table class="mra-table">' +
          '<thead><tr>' +
            '<th>Area</th><th>Stance</th><th>Duration</th><th>Range</th><th>Extremes</th>' +
          '</tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>';

    var asOf = document.getElementById('macroReadAsOf');
    if (asOf && data && data.as_of) asOf.textContent = 'as of ' + data.as_of;
  }

  function renderError(msg) {
    var rail = document.getElementById('macroRailAreas');
    if (rail) rail.innerHTML = '<div class="msr-err">Unavailable: ' + esc(msg) + '</div>';
    var card = document.getElementById('macroReadCard');
    if (card) card.innerHTML = '<div class="mra-err">Macro read unavailable: ' + esc(msg) + '</div>';
  }

  /* ── collapsible toggle (legacy card) ──────────────────────────────── */
  function initCollapse(headerEl, bodyEl) {
    if (!headerEl || !bodyEl) return;
    headerEl.style.cursor = 'pointer';
    var collapsed = false;
    headerEl.addEventListener('click', function () {
      collapsed = !collapsed;
      bodyEl.style.display = collapsed ? 'none' : '';
      var icon = headerEl.querySelector('.mra-toggle');
      if (icon) icon.textContent = collapsed ? '▶' : '▼';
    });
  }

  /* ── inject legacy card (only if the old macroReadCard anchor exists) ─ */
  function injectLegacyCard() {
    if (document.getElementById('macroReadCard')) return;
    var wrapper = document.createElement('div');
    wrapper.id = 'macroReadWrapper';
    wrapper.className = 'mra-wrapper';
    wrapper.innerHTML =
      '<div class="mra-header" id="macroReadHeader">' +
        '<span class="mra-title">Macro read</span> ' +
        '<span class="mra-toggle">▼</span>' +
        '<span class="mra-asof" id="macroReadAsOf"></span>' +
      '</div>' +
      '<div id="macroReadCard" class="mra-card"><span class="mra-muted">Loading…</span></div>';

    var anchor =
      document.getElementById('macroBand') ||
      document.getElementById('econPanel') ||
      document.querySelector('main .card');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(wrapper, anchor.nextSibling);
    }
    initCollapse(
      document.getElementById('macroReadHeader'),
      document.getElementById('macroReadCard')
    );
  }

  // 2026-08-27 -- your own $ exposure per sector, for the Sectors panel's
  // stats sub-row (sectorStatsRowHtml) -- same drv_category_perf table
  // (via /api/cockpit/factor-scorecard?axis=sector) the Sector factor-
  // scorecard grid and Portfolio Mix's Sector pie both read, so this
  // agrees with those rather than recomputing its own $ totals from raw
  // held rows. Whole-portfolio (no accounts= filter) -- this rail panel
  // has no Accounts-filter UI of its own to scope it further. Best-effort:
  // a failure here still lets the sector breadth rows render, just without
  // the $ exposure bit.
  async function _fetchSectorExposure(dateParam) {
    try {
      var qs = dateParam ? dateParam + '&axis=sector' : '?axis=sector';
      var resp = await fetch('/api/cockpit/factor-scorecard' + qs);
      if (!resp.ok) return {};
      var data = await resp.json();
      var map = {};
      (data.rows || []).forEach(function (r) { map[r.category] = r; });
      return map;
    } catch (e) { return {}; }
  }

  /* ── main load ──────────────────────────────────────────────────────── */
  async function load() {
    var dateEl    = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/macro-areas' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      var exposureMap = await _fetchSectorExposure(dateParam);

      /* Primary: render side rail */
      renderRail(data);
      renderSectorsPanel(data && data.sectors, exposureMap);

      /* Legacy full-width card (only if the old wrapper was injected by another path) */
      if (document.getElementById('macroReadCard')) {
        renderLegacyCard(data);
      }

      /* Notify USD-corr listener that areas card is ready */
      document.dispatchEvent(new CustomEvent('macroReadReady', { detail: data }));
    } catch (e) {
      renderError(e && e.message ? e.message : String(e));
    }
  }

  // 2026-08-10 -- Dashboard (/) has no `main .card` element (Actionable's
  // own layout marker) but does have #macroRailVolatility once this script
  // loads there too -- widened rather than replaced so Actionable's
  // original check still stands unchanged. User: "add Volatility & Major
  // Market panels that you see on actionable screen to dashboard screen on
  // the right side."
  function init() {
    if (!document.querySelector('main .card') && !document.getElementById('macroRailVolatility')) return;
    load();
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Exposed so actionable.js's Refresh button (loadActionable) can re-pull
  // the Macro rail too -- previously only the #datePicker "change" event
  // reloaded it, so the volatility gauges (and the rest of the rail) went
  // stale after the initial page load until the date was changed.
  window.reloadMacroAreas = load;

})();
