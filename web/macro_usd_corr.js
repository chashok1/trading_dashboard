/* macro_usd_corr.js — USD Correlations card for /actionable (TASK_79).
 *
 * Self-contained; reads GET /api/correlations?date=<D>.
 *
 * Two parts:
 *   1. Standalone collapsible "USD Correlations" card injected below the
 *      Macro read card (#macroReadWrapper).
 *   2. One-line summary row wired into #macroCorrRow (the placeholder
 *      left by macro_areas.js in the Macro read table).
 *
 * Color thresholds (mirroring ref_settings):
 *   r >= +0.50  -> green  (.ucr-pos)
 *   r <= -0.70  -> strong red (.ucr-neg-s)
 *   -0.70 < r <= -0.50 -> moderate amber (.ucr-neg-m)
 *   else        -> plain
 *   NULL        -> "—" (.ucr-nil)
 */
(function () {
  'use strict';

  /* Thresholds calibrated for daily-return Pearson r (lower than price-level r) */
  var CORR_GREEN    =  0.25;   // green  (positive)
  var CORR_RED_STR  = -0.40;   // strong red (strongly negative)
  var CORR_RED_MOD  = -0.20;   // amber  (mildly negative)

  var WINDOWS = [15, 30, 90, 120, 180];
  var WIN_LABELS = { 15: '15D', 30: '30D', 90: '90D', 120: '120D', 180: '180D' };

  /* ── utilities ────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                 '"': '&quot;', "'": '&#39;' }[c];
      });
  }

  function fmtR(v) {
    if (v === null || v === undefined) return '—';
    return (v >= 0 ? '+' : '') + Number(v).toFixed(2);
  }

  function fmtPct(v) {
    if (v === null || v === undefined) return '—';
    return (v * 100).toFixed(0) + '%';
  }

  function corrClass(v) {
    if (v === null || v === undefined) return 'ucr-nil';
    if (v >= CORR_GREEN)   return 'ucr-pos';
    if (v <= CORR_RED_STR) return 'ucr-neg-s';
    if (v <= CORR_RED_MOD) return 'ucr-neg-m';
    return '';
  }

  function corrCell(v, extraClass) {
    var cls = corrClass(v);
    if (extraClass) cls = (cls ? cls + ' ' : '') + extraClass;
    return '<td class="' + cls + '">' + fmtR(v) + '</td>';
  }

  /* ── table build ─────────────────────────────────────────────────── */
  function tableHtml(data) {
    var rows = data.rows || [];
    var hdr =
      '<thead><tr>' +
        '<th>Asset</th>' +
        WINDOWS.map(function (w) {
          return '<th>' + WIN_LABELS[w] + '</th>';
        }).join('') +
        '<th class="ucr-divider">52w Hi</th>' +
        '<th>52w Lo</th>' +
        '<th>%Pos</th>' +
        '<th>%Neg</th>' +
      '</tr></thead>';

    var body = '<tbody>';
    rows.forEach(function (r) {
      body += '<tr>' +
        '<td>' + esc(r.label) + '</td>' +
        WINDOWS.map(function (w) {
          return corrCell(r['w' + w]);
        }).join('') +
        '<td class="ucr-divider ' + corrClass(r.roll30_high) + '">' + fmtR(r.roll30_high) + '</td>' +
        '<td class="' + corrClass(r.roll30_low) + '">' + fmtR(r.roll30_low) + '</td>' +
        '<td>' + fmtPct(r.roll30_pct_pos) + '</td>' +
        '<td>' + fmtPct(r.roll30_pct_neg) + '</td>' +
      '</tr>';
    });
    body += '</tbody>';

    return '<table class="ucr-table">' + hdr + body + '</table>';
  }

  /* ── compact bar: all assets, 15D + 30D ─────────────────────────── */
  function barHtml(data) {
    var rows = data.rows || [];
    if (!rows.length) return '<span class="mra-muted">no data</span>';

    function fmtV(v) {
      if (v === null || v === undefined) return '—';
      return (v >= 0 ? '+' : '') + Number(v).toFixed(2);
    }

    return rows.map(function (r) {
      var c15 = corrClass(r.w15), c30 = corrClass(r.w30);
      return '<span class="ucr-bar-asset">' +
        '<span class="ucr-bar-lbl">' + esc(r.label) + '</span>' +
        '<span class="ucr-bar-val ' + c15 + '" title="15D">' + fmtV(r.w15) + '</span>' +
        '<span class="ucr-bar-sep">|</span>' +
        '<span class="ucr-bar-val ' + c30 + '" title="30D">' + fmtV(r.w30) + '</span>' +
        '</span>';
    }).join('');
  }

  /* ── summary chips for Macro read master-switch row ─────────────── */
  function summaryHtml(data) {
    var rows = data.rows || [];
    function findRow(key) { return rows.find(function (r) { return r.asset_key === key; }); }
    var spx  = findRow('spx');
    var gold = findRow('gold');
    var btc  = findRow('bitcoin');
    function chip(label, v) {
      if (v === null || v === undefined) return '';
      return '<span class="mra-chip ' + corrClass(v) + '" title="USD vs ' + label + ' 30D r">' +
             esc(label) + ':' + (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '</span> ';
    }
    return (chip('SPX', spx && spx.w30) + chip('Gold', gold && gold.w30) + chip('BTC', btc && btc.w30))
           || '<span class="mra-muted">no data</span>';
  }

  /* ── render / inject ─────────────────────────────────────────────── */
  function render(data) {
    var card = document.getElementById('usdCorrCard');
    if (card) {
      if (!data || !data.rows || !data.rows.length) {
        card.innerHTML =
          '<div class="ucr-err">No USD correlation data yet. ' +
          'Run <code>python -m etl.fetch_quotes --full</code> then re-derive.</div>';
      } else {
        card.innerHTML = tableHtml(data);
      }
    }

    var asOf = document.getElementById('usdCorrAsOf');
    if (asOf && data && data.as_of) asOf.textContent = data.as_of;

    /* Header bar — all assets, 15D + 30D */
    var hdrChips = document.getElementById('usdCorrHdrChips');
    if (hdrChips && data && data.rows && data.rows.length) {
      hdrChips.innerHTML = barHtml(data);
    }

    /* Update the Macro read master-switch placeholder */
    var corrSummary = document.getElementById('macroCorrSummary');
    if (corrSummary) {
      if (data && data.rows && data.rows.length) {
        corrSummary.innerHTML = summaryHtml(data);
      } else {
        corrSummary.innerHTML = '<span class="mra-muted">awaiting history</span>';
      }
    }
  }

  function renderError(msg) {
    var card = document.getElementById('usdCorrCard');
    if (card) card.innerHTML = '<div class="ucr-err">USD correlations unavailable: ' + esc(msg) + '</div>';
    var corrSummary = document.getElementById('macroCorrSummary');
    if (corrSummary) corrSummary.innerHTML = '<span class="mra-muted">unavailable</span>';
  }

  /* ── inject collapsible card below Macro read, collapsed by default ─ */
  function injectCard() {
    if (document.getElementById('usdCorrWrapper')) return;
    var wrapper = document.createElement('div');
    wrapper.id = 'usdCorrWrapper';
    wrapper.className = 'ucr-wrapper';
    wrapper.innerHTML =
      '<div class="ucr-header" id="usdCorrHeader">' +
        '<span class="ucr-title">USD Corr</span>' +
        '<span class="ucr-toggle">▶</span>' +
        '<span class="ucr-hdr-chips" id="usdCorrHdrChips"></span>' +
        '<span class="ucr-asof" id="usdCorrAsOf"></span>' +
      '</div>' +
      '<div id="usdCorrCard" class="ucr-card" style="display:none">' +
        '<span class="mra-muted">Loading…</span>' +
      '</div>';

    var anchor =
      document.getElementById('macroReadWrapper') ||
      document.getElementById('macroBand') ||
      document.querySelector('main .card');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(wrapper, anchor.nextSibling);
    }

    var hdr  = document.getElementById('usdCorrHeader');
    var body = document.getElementById('usdCorrCard');
    if (hdr && body) {
      var collapsed = true;
      hdr.addEventListener('click', function () {
        collapsed = !collapsed;
        body.style.display = collapsed ? 'none' : '';
        var icon = hdr.querySelector('.ucr-toggle');
        if (icon) icon.textContent = collapsed ? '▶' : '▼';
      });
    }
  }

  async function load() {
    injectCard();
    var dateEl = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/correlations' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      render(data);
    } catch (e) {
      renderError(e && e.message ? e.message : String(e));
    }
  }

  /* Wait for macro_areas.js to finish injecting the placeholder row */
  function init() {
    if (!document.querySelector('main .card')) return;

    /* If the macroReadReady event fires first, load immediately;
       otherwise load after DOMContentLoaded (macro_areas may not be present) */
    document.addEventListener('macroReadReady', function () {
      load();
    });

    /* Also load unconditionally after a short delay in case
       macro_areas.js is absent or fails */
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);

    setTimeout(function () {
      if (!document.getElementById('usdCorrWrapper')) load();
    }, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
