/* macro_areas.js — Macro read card for /actionable (TASK_78/TASK_85).
 *
 * Self-contained; reads GET /api/macro-areas?date=<D>.
 *
 * Renders:
 *   - Compact side-rail rows into #macroRailAreas (TASK_85 primary display)
 *   - Full-width collapsible card into #macroReadCard if present (legacy)
 *
 * Per-row compact layout (side rail):
 *   [stance arrowhead SVG] [name] [Td] [Tn] [range bar] [%]
 *
 * Volatility row: gauge text only (zone · VIX value)
 * Sectors row: leaders/laggard summary
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

  function fmt1(v) {
    if (v === null || v === undefined) return '—';
    return (Math.round(v * 10) / 10).toFixed(1);
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

  /* ── range bar (compact rail version) ──────────────────────────────── */
  function railRangeBar(rr_pos, hot_pct, cold_pct) {
    if (rr_pos === null || rr_pos === undefined) {
      return '<span class="mra-muted" style="font-size:9px;">n/a</span>';
    }
    var pct    = Math.max(0, Math.min(1, rr_pos));
    var tickPx = Math.round(pct * 100);
    var isHot  = (hot_pct  !== null && hot_pct  !== undefined) ? (rr_pos >= hot_pct)  : (rr_pos >= 0.80);
    var isCold = (cold_pct !== null && cold_pct !== undefined) ? (rr_pos <= cold_pct) : (rr_pos <= 0.20);
    var extreme = isHot || isCold;
    return (
      '<div class="msr-rb-wrap">' +
        '<div class="msr-rb" title="' + tickPx + '% of range">' +
          '<div class="msr-rb-fill" style="width:' + tickPx + '%"></div>' +
          '<div class="msr-rb-tick' + (extreme ? ' extreme' : '') +
               '" style="left:' + tickPx + '%"></div>' +
        '</div>' +
        '<span class="msr-pct">' + tickPx + '%</span>' +
      '</div>'
    );
  }

  /* ── tooltip HTML for hover ─────────────────────────────────────────── */
  function buildTooltip(area) {
    var rows = '';
    if (area.stance) {
      rows += '<div class="msr-tooltip-row"><span class="msr-tooltip-k">Stance</span>' +
              '<span class="msr-tooltip-v">' + esc(area.stance) + '</span></div>';
    }
    if (area.conviction !== null && area.conviction !== undefined) {
      rows += '<div class="msr-tooltip-row"><span class="msr-tooltip-k">Conviction</span>' +
              '<span class="msr-tooltip-v">' + Math.round(area.conviction * 100) + '%</span></div>';
    }
    if (area.rr_pos !== null && area.rr_pos !== undefined) {
      rows += '<div class="msr-tooltip-row"><span class="msr-tooltip-k">RR pos</span>' +
              '<span class="msr-tooltip-v">' + Math.round(area.rr_pos * 100) + '%</span></div>';
    }
    var hot = (area.extremes_hot || []);
    var cold = (area.extremes_cold || []);
    if (hot.length) {
      rows += '<div class="msr-tooltip-row"><span class="msr-tooltip-k">Overbought</span>' +
              '<span class="msr-tooltip-v" style="color:#b91c1c;">' + hot.map(esc).join(', ') + '</span></div>';
    }
    if (cold.length) {
      rows += '<div class="msr-tooltip-row"><span class="msr-tooltip-k">Oversold</span>' +
              '<span class="msr-tooltip-v" style="color:#1d4ed8;">' + cold.map(esc).join(', ') + '</span></div>';
    }
    var members = (area.members || []);
    if (members.length) {
      rows += '<div class="msr-tooltip-row" style="margin-top:3px;"><span class="msr-tooltip-k">Members</span>' +
              '<span class="msr-tooltip-v" style="font-size:10px;">' +
              members.slice(0, 8).map(function (m) { return esc(m.tos_symbol || m.symbol || ''); }).join(', ') +
              (members.length > 8 ? '…' : '') + '</span></div>';
    }
    return '<div class="msr-tooltip-title">' + esc(area.label) + '</div>' + rows;
  }

  /* ── compact area row for side rail ────────────────────────────────── */
  function railAreaRow(area) {
    var isVol = area.area_key === 'volatility';

    if (isVol) {
      /* Volatility: gauge text only */
      var vix_m   = (area.members || []).find(function (m) { return m.role === 'gauge'; });
      var zone    = vix_m ? (vix_m.zone || '—') : '—';
      var vixVal  = vix_m ? (vix_m.last !== null && vix_m.last !== undefined ? fmt1(vix_m.last) : null) : null;
      var gaugeClass = zone === 'investable' ? 'msr-gauge-g'
                     : zone === 'elevated'   ? 'msr-gauge-r'
                     : 'msr-gauge-a';
      var vixSpan = vixVal !== null
        ? '<span class="msr-gauge-vix">VIX ' + esc(vixVal) + '</span>'
        : '';
      return (
        '<div class="msr-row" data-tooltip="' + esc(buildTooltip(area)) + '">' +
          SVG_NEUT +
          '<span class="msr-name">' + esc(area.label) + '</span>' +
          '<span class="msr-gauge ' + gaugeClass + '">' + esc(zone) + '</span>' +
          vixSpan +
        '</div>'
      );
    }

    return (
      '<div class="msr-row" data-tooltip="' + esc(buildTooltip(area)) + '">' +
        stanceArrow(area.stance) +
        '<span class="msr-name">' + esc(area.label) + '</span>' +
        durArrow(area.trade, 'Td') +
        durArrow(area.trend, 'Tn') +
        railRangeBar(area.rr_pos, area.hot_pct, area.cold_pct) +
      '</div>'
    );
  }

  /* ── sectors compact row ────────────────────────────────────────────── */
  function railSectorsRow(sectors) {
    if (!sectors) return '';
    var leaders   = (sectors.leaders   || []).map(esc).join(' · ');
    var laggards  = (sectors.laggards  || []).map(esc).join(' · ');
    var rotateIn  = (sectors.rotate_in || []).map(esc).join(' · ');
    var subrows = '';
    if (leaders)  subrows += '<div class="msr-sec-subrow"><span class="msr-sec-up">&#9650;</span> <span class="msr-sec-lbl">Leaders:</span> ' + leaders + '</div>';
    if (laggards) subrows += '<div class="msr-sec-subrow"><span class="msr-sec-down">&#9660;</span> <span class="msr-sec-lbl">Laggards:</span> ' + laggards + '</div>';
    if (rotateIn) subrows += '<div class="msr-sec-subrow"><span class="msr-sec-rotate">&#8635;</span> <span class="msr-sec-lbl">Rotate in:</span> ' + rotateIn + '</div>';
    if (!subrows) subrows = '<span class="mra-muted">—</span>';

    // All-sectors collapsible sub-panel — same row format as area rows
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
      '</div>';
    }).join('');

    var allDetail = all.length
      ? '<details class="msr-all-sectors"><summary class="msr-all-summary">All sectors (' + all.length + ')</summary>' +
          '<div class="msr-all-body">' + (allRows || '<span class="mra-muted">No data</span>') + '</div>' +
        '</details>'
      : '';

    return (
      '<div class="msr-row msr-sectors-block">' +
        '<div class="msr-sec-block">' +
          '<div class="msr-sec-title">Sectors</div>' +
          subrows +
          allDetail +
        '</div>' +
      '</div>'
    );
  }

  /* ── render into side rail ──────────────────────────────────────────── */
  function renderRail(data) {
    var container = document.getElementById('macroRailAreas');
    if (!container) return;

    var areas   = (data && data.areas) || [];
    var sectors = data && data.sectors;

    var html = areas.map(railAreaRow).join('');
    html += railSectorsRow(sectors);

    if (!html) {
      container.innerHTML = '<div class="msr-loading">No macro data.</div>';
      return;
    }
    container.innerHTML = html;

    /* Wire tooltip on hover */
    var tooltip = document.getElementById('msrTooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.id = 'msrTooltip';
      tooltip.className = 'msr-tooltip';
      document.body.appendChild(tooltip);
    }

    container.querySelectorAll('.msr-row[data-tooltip]').forEach(function (row) {
      row.addEventListener('mouseenter', function (e) {
        tooltip.innerHTML = row.dataset.tooltip || '';
        tooltip.style.display = 'block';
        _positionTooltip(tooltip, e);
      });
      row.addEventListener('mousemove', function (e) { _positionTooltip(tooltip, e); });
      row.addEventListener('mouseleave', function () { tooltip.style.display = 'none'; });
    });
  }

  function _positionTooltip(el, e) {
    var x = e.clientX + 12, y = e.clientY + 12;
    var vw = window.innerWidth, vh = window.innerHeight;
    if (x + 260 > vw) x = e.clientX - 264;
    if (y + 140 > vh) y = e.clientY - 144;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
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

})();
