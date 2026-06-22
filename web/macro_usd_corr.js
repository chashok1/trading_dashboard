/* macro_usd_corr.js — USD Correlations for /actionable (TASK_79/TASK_85).
 *
 * Self-contained; reads GET /api/correlations?date=<D>.
 *
 * TASK_85 (primary): compact heatmap rendered into #macroRailCorr (side rail).
 *   Rows = SPX, Gold, Brent, CRB, BTC; cols = 15/30/90/120/180D.
 *   Color cells by existing price-level thresholds. Value in-cell; NULL → "—".
 *   Hover a row → shows 52-wk Hi/Lo/%pos/%neg in a tooltip.
 *
 * Legacy: standalone collapsible card below Macro read card (#macroReadWrapper).
 * Also fills #macroCorrSummary placeholder row (in legacy card if present).
 *
 * Color thresholds (price-level Pearson r):
 *   r >= +0.50  -> green  (.ucr-pos)
 *   r <= -0.70  -> strong red (.ucr-neg-s)
 *   -0.70 < r <= -0.40 -> moderate amber (.ucr-neg-m)
 *   else        -> plain
 *   NULL        -> "—" (.ucr-nil)
 */
(function () {
  'use strict';

  /* Thresholds calibrated for price-level Pearson r (trend-dominated).
   * Price-level r is much stronger than daily-return r — values of ±0.7+ are common. */
  var CORR_GREEN    =  0.50;   // green  (positive)
  var CORR_RED_STR  = -0.70;   // strong red
  var CORR_RED_MOD  = -0.40;   // amber  (mildly negative)

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

  function corrCell(v) {
    var cls = corrClass(v);
    return '<td class="' + cls + '">' + fmtR(v) + '</td>';
  }

  /* ── compact rail heatmap ─────────────────────────────────────────── */
  function railHeatmapHtml(data) {
    var rows = data.rows || [];
    if (!rows.length) {
      return '<div class="msr-loading">No data yet.</div>';
    }

    var hdr =
      '<thead><tr>' +
        '<th></th>' +
        WINDOWS.map(function (w) {
          return '<th>' + WIN_LABELS[w] + '</th>';
        }).join('') +
      '</tr></thead>';

    var body = '<tbody>';
    rows.forEach(function (r) {
      /* Build 52-wk tooltip */
      var tip =
        esc(r.label) + ' | 52w: ' +
        'Hi ' + fmtR(r.roll30_high) + ' ' +
        'Lo ' + fmtR(r.roll30_low) + ' ' +
        '%+ ' + fmtPct(r.roll30_pct_pos) + ' ' +
        '%- ' + fmtPct(r.roll30_pct_neg);
      body += '<tr data-tip="' + tip + '">' +
        '<td>' + esc(r.label) + '</td>' +
        WINDOWS.map(function (w) {
          return corrCell(r['w' + w]);
        }).join('') +
      '</tr>';
    });
    body += '</tbody>';

    return '<table class="msr-ucr-table">' + hdr + body + '</table>';
  }

  /* ── render into side rail ─────────────────────────────────────────── */
  function renderRail(data) {
    var container = document.getElementById('macroRailCorr');
    if (!container) return;

    if (!data || !data.rows || !data.rows.length) {
      container.innerHTML =
        '<div class="msr-loading">No USD corr data yet. ' +
        'Run <code>python -m etl.fetch_quotes --full</code>.</div>';
      return;
    }

    container.innerHTML = railHeatmapHtml(data);

    /* Wire 52-wk tooltip on row hover */
    var tooltip = document.getElementById('msrUcrTooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.id = 'msrUcrTooltip';
      tooltip.className = 'msr-tooltip';
      document.body.appendChild(tooltip);
    }

    container.querySelectorAll('tr[data-tip]').forEach(function (row) {
      row.addEventListener('mouseenter', function (e) {
        var tipText = row.dataset.tip || '';
        /* Parse "Asset | 52w: Hi +X Lo -Y %+ Z%- W%" into structured HTML */
        tooltip.innerHTML = _buildUcrTip(tipText, row);
        tooltip.style.display = 'block';
        _positionTooltip(tooltip, e);
      });
      row.addEventListener('mousemove', function (e) { _positionTooltip(tooltip, e); });
      row.addEventListener('mouseleave', function () { tooltip.style.display = 'none'; });
    });
  }

  function _buildUcrTip(raw, row) {
    /* raw format: "Label | 52w: Hi +X Lo -Y %+ Z %- W" */
    var idx = raw.indexOf('|');
    var label = idx >= 0 ? raw.slice(0, idx).trim() : raw;
    var rest  = idx >= 0 ? raw.slice(idx + 1).trim() : '';
    /* Extract values from cells */
    var cells = row.querySelectorAll('td');
    var windowVals = '';
    WINDOWS.forEach(function (w, i) {
      var td = cells[i + 1];
      if (td) {
        var cls = td.className;
        var style = cls.indexOf('ucr-pos') >= 0 ? 'color:#166534;font-weight:700;'
                  : cls.indexOf('ucr-neg-s') >= 0 ? 'color:#991b1b;font-weight:700;'
                  : cls.indexOf('ucr-neg-m') >= 0 ? 'color:#854d0e;'
                  : '';
        windowVals += '<div class="msr-tooltip-row">' +
          '<span class="msr-tooltip-k">' + WIN_LABELS[w] + '</span>' +
          '<span class="msr-tooltip-v" style="' + style + '">' + esc(td.textContent) + '</span>' +
          '</div>';
      }
    });
    return (
      '<div class="msr-tooltip-title">' + esc(label) + ' vs USD</div>' +
      windowVals +
      '<div style="margin-top:4px;padding-top:3px;border-top:1px solid #e2e8f0;font-size:10px;color:#64748b;">' +
        rest.replace(/52w:/,'52-wk:') +
      '</div>'
    );
  }

  function _positionTooltip(el, e) {
    var x = e.clientX + 12, y = e.clientY + 12;
    var vw = window.innerWidth, vh = window.innerHeight;
    if (x + 260 > vw) x = e.clientX - 264;
    if (y + 180 > vh) y = e.clientY - 184;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
  }

  /* ── legacy full-width card table ─────────────────────────────────── */
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
          var cls = corrClass(r['w' + w]);
          return '<td class="' + cls + '">' + fmtR(r['w' + w]) + '</td>';
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

  /* ── render legacy full-width card ──────────────────────────────────── */
  function renderLegacyCard(data) {
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

    var hdrChips = document.getElementById('usdCorrHdrChips');
    if (hdrChips && data && data.rows && data.rows.length) {
      hdrChips.innerHTML = barHtml(data);
    }

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
    var rail = document.getElementById('macroRailCorr');
    if (rail) rail.innerHTML = '<div class="msr-err">USD corr unavailable: ' + esc(msg) + '</div>';
    var card = document.getElementById('usdCorrCard');
    if (card) card.innerHTML = '<div class="ucr-err">USD correlations unavailable: ' + esc(msg) + '</div>';
    var corrSummary = document.getElementById('macroCorrSummary');
    if (corrSummary) corrSummary.innerHTML = '<span class="mra-muted">unavailable</span>';
  }

  /* ── inject legacy full-width card (if #macroReadWrapper exists) ──── */
  function injectLegacyCard() {
    if (document.getElementById('usdCorrWrapper')) return;
    var wrapper = document.createElement('div');
    wrapper.id = 'usdCorrWrapper';
    wrapper.className = 'ucr-wrapper';
    wrapper.innerHTML =
      '<div class="ucr-header" id="usdCorrHeader">' +
        '<span class="ucr-title">USD Corr</span>' +
        '<span class="ucr-toggle">▶</span>' +
        '<span class="ucr-method" title="Pearson of raw daily closes — matches provider methodology (price-levels, not returns)">price-levels</span>' +
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

  /* ── main load ──────────────────────────────────────────────────────── */
  async function load() {
    var dateEl    = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/correlations' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();

      /* Primary: render side rail heatmap */
      renderRail(data);

      /* Legacy: full-width collapsible card (only if wrapper was injected) */
      if (document.getElementById('usdCorrCard')) {
        renderLegacyCard(data);
      }
    } catch (e) {
      renderError(e && e.message ? e.message : String(e));
    }
  }

  function init() {
    if (!document.querySelector('main .card')) return;

    /* Load immediately when the macro-areas card is ready, or after short delay */
    document.addEventListener('macroReadReady', function () {
      load();
    });

    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);

    /* Fallback: load unconditionally after 1.2s if not triggered yet */
    setTimeout(function () {
      if (!document.getElementById('macroRailCorr') ||
          document.getElementById('macroRailCorr').querySelector('.msr-loading')) {
        load();
      }
    }, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
