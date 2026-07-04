/* macro_areas.js — Macro read card for /actionable (TASK_78/TASK_85/TASK_116).
 *
 * Self-contained; reads GET /api/macro-areas?date=<D>.
 *
 * Renders:
 *   - Compact side-rail rows into #macroRailAreas (TASK_85 primary display)
 *   - Full-width collapsible card into #macroReadCard if present (legacy)
 *
 * Per-row compact layout (side rail, TASK_116 consolidation — see
 * docs/market_panel_consolidation_design.md):
 *   [quad glyph] [SYM] [candle] [Td] [Tn] [range bar+tick] [%chg chip]
 *
 * Volatility row: SYM colored by zone (not outlook); 3-zone volRangeBar
 *   (ported from market_bar.js via window.mtTip.volRangeBar) instead of
 *   Td/Tn+range bar; trailing zone badge kept.
 * Sectors row: unchanged — leaders/laggard summary + per-sector ETF proxy.
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
    var txt = flat ? '0.00%' : (n > 0 ? '+' : '') + n.toFixed(2) + '%';
    return '<span class="msr-chg" style="background:' + bg + ';">' + esc(txt) + '</span>';
  }

  // Native title-attribute tooltip for the compact row (symbol/price/%chg/
  // outlook) — the anatomy no longer shows a separate price column (tape
  // convention: price lives in the hover, only %chg is a visible chip).
  function _rowTitle(m) {
    var parts = [];
    if (m.symbol) parts.push(m.symbol);
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

  function etfProxyRowHtml(etf) {
    if (!etf || etf.last == null) return '';
    var tradeDir = etf.td === 'up' ? 1 : etf.td === 'down' ? -1 : null;
    var trendDir = etf.tn === 'up' ? 1 : etf.tn === 'down' ? -1 : null;
    return '<div class="msr-row msr-etf-row" style="padding-left:16px;">' +
      '<span class="msr-name msr-name-tick" style="color:' + _nameColor(etf.outlook) + '; font-weight:400;" title="' + esc(etf.symbol) + ' sector ETF proxy">' +
        _msGlyph(etf.monthly_score) + esc(etf.symbol) +
      '</span>' +
      _priceChgSpan({ last: etf.last, pct_change: etf.pct_change }) +
      durArrow(tradeDir, 'Td') +
      durArrow(trendDir, 'Tn') +
      railRangeBar(etf.rr_pos, 0.8, 0.2) +
    '</div>';
  }

  /* ── range bar (compact rail version) ──────────────────────────────── */
  function railRangeBar(rr_pos, hot_pct, cold_pct) {
    if (rr_pos === null || rr_pos === undefined) {
      return '<span class="mra-muted" style="font-size:9px;">n/a</span>';
    }
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
        '<span class="msr-pct">' + actualPct + '%</span>' +
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
              _msGlyph(m.monthly_score) + esc(m.label || area.label) +
            '</span>' +
            _candleHtml(m) +
            volBar +
            _chgChipHtml(m.pct_change, m.inverted) +
            '<span class="msr-gauge ' + gaugeClass + '">' + esc(zone) + '</span>' +
          '</div>'
        );
      }
      return (
        '<div class="msr-row" title="' + esc(_rowTitle(m)) + '">' +
          '<span class="msr-name msr-name-tick" style="color:' + _nameColor(m.outlook) + ';">' +
            _msGlyph(m.monthly_score) + esc(m.symbol) +
          '</span>' +
          _candleHtml(m) +
          durArrow(m.trade, 'Td') +
          durArrow(m.trend, 'Tn') +
          railRangeBar(m.rr_pos, area.hot_pct, area.cold_pct) +
          _chgChipHtml(m.pct_change, m.inverted) +
        '</div>'
      );
    }).join('');
  }

  /* ── sectors panel (own side-rail section) ────────────────────────── */
  function renderSectorsPanel(sectors) {
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
        railRangeBar(score, 0.7, 0.3) +
      '</div>' + etfProxyRowHtml(s.etf);
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

  /* ── main load ──────────────────────────────────────────────────────── */
  async function load() {
    var dateEl    = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/macro-areas' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();

      /* Primary: render side rail */
      renderRail(data);
      renderSectorsPanel(data && data.sectors);

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

  function init() {
    if (!document.querySelector('main .card')) return;
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
