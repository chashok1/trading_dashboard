/* macro_areas.js — Macro read card for /actionable (TASK_78).
 *
 * Self-contained; reads GET /api/macro-areas?date=<D>.
 * Renders into #macroReadCard (injected by this module if absent).
 * Must not touch actionable.js state, filters, or the grid.
 *
 * Layout:
 *   [top-down posture banner]
 *   [area rows: name · stance pill · TRADE/TREND chips · rr-bar · extremes]
 *   [sectors row: leaders / laggards / rotate-in]
 *   [USD correlations placeholder (filled by TASK_79)]
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

  function fmtChg(v) {
    if (v === null || v === undefined) return '';
    var sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(2) + '%';
  }

  /* ── stance pill ─────────────────────────────────────────────────── */
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

  /* ── TRADE/TREND chips ───────────────────────────────────────────── */
  function durationChip(val, label) {
    if (val === null || val === undefined) return '<span class="mra-chip mra-chip-na">' + label + ':—</span>';
    var cls = val > 0 ? 'mra-chip-bull' : val < 0 ? 'mra-chip-bear' : 'mra-chip-flat';
    var arrow = val > 0 ? '▲' : val < 0 ? '▼' : '—';
    return '<span class="mra-chip ' + cls + '">' + label + ':' + arrow + '</span>';
  }

  /* ── range bar (reuses rr-rb classes from styles.css) ───────────── */
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

  /* ── per-area row ────────────────────────────────────────────────── */
  function areaRowHtml(area) {
    var isVol = area.area_key === 'volatility';
    var isRates = area.area_key === 'rates';

    /* gauge row (Volatility) */
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

    /* curve / rates row */
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

    /* standard area row */
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

  /* ── sectors row ─────────────────────────────────────────────────── */
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

  /* ── USD correlations placeholder (wired by macro_usd_corr.js) ──── */
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

  /* ── full card render ────────────────────────────────────────────── */
  function render(data) {
    var card = document.getElementById('macroReadCard');
    if (!card) return;

    var areas = (data && data.areas) || [];
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
            '<th>Area</th>' +
            '<th>Stance</th>' +
            '<th>Duration</th>' +
            '<th>Range</th>' +
            '<th>Extremes</th>' +
          '</tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>';

    var asOf = document.getElementById('macroReadAsOf');
    if (asOf && data && data.as_of) asOf.textContent = 'as of ' + data.as_of;
  }

  function renderError(msg) {
    var card = document.getElementById('macroReadCard');
    if (card) card.innerHTML = '<div class="mra-err">Macro read unavailable: ' + esc(msg) + '</div>';
  }

  /* ── collapsible toggle ──────────────────────────────────────────── */
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

  /* ── inject card HTML + load data ───────────────────────────────── */
  function injectCard() {
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

    /* Insert after #macroBand if present, else after #econPanel, else at top of .card */
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

  async function load() {
    injectCard();
    var card = document.getElementById('macroReadCard');
    /* pick up the date from the page's date-picker if present */
    var dateEl = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/macro-areas' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      render(data);
      /* Notify any USD-corr listener that the card is ready */
      document.dispatchEvent(new CustomEvent('macroReadReady', { detail: data }));
    } catch (e) {
      renderError(e && e.message ? e.message : String(e));
    }
  }

  function init() {
    /* Only activate on pages that have the actionable / cockpit layout */
    if (!document.querySelector('main .card')) return;
    load();
    /* Re-load when date picker changes */
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
