/* Market View stock-details popup -- 2026-08-10. Clicking a category row in
   the bottom 3 Market View grids (Sector/Asset Class/Style, Source filter
   set to RR/CALL/ETF/II/SSS/PS) opens this. Deliberately NOT the same modal
   as openFactorExposureModal (risk_gauge_modal.js) -- that one is $/holdings
   based (positions, cost basis, cumulative gain), which doesn't exist here;
   Market View is a pure market read. Reuses the SAME .gauge-modal-backdrop/
   .gm-* CSS shell (already generic, not $-specific), different element ids
   so the two modals can't collide.

   Layout: left = per-symbol table with that source's own raw columns
   (SSS: pct_delta/analyst rank/days_on; PS: rank/wk_ago/mn_ago/sizing; etc
   -- api/routers/dash.py::_SOURCE_DETAIL_COLS). Right = two vertical-bar
   charts for the category's benchmark ETF (drv_category_perf.bench_symbol,
   e.g. Technology -> XLK): daily gain/loss on top, MTD/QTD/YTD window
   returns below. User: "i need to see the stock details in the popups.
   depending on the source... right side graphs -> daily gain/loss for
   given sector symbol (ex: XLK for tech etc)... right side bottom graph ->
   display MTD YTD etc bars percentages" -- confirmed vertical bars for the
   window-returns chart specifically. */
(function () {
  var MODAL_ID = 'mvDetailModal';
  var _AXIS_LABEL = { sector: 'Sector', asset_class: 'Asset Class', style: 'Style' };
  var _COLUMN_LABELS = {
    outlook: 'Outlook', buy_trade: 'Buy Trade', sell_trade: 'Sell Trade', last_price: 'Last Price',
    outlook_modifier: 'Modifier', brr: 'BRR', trr: 'TRR', recent_price: 'Price',
    pct_delta: 'Pct Δ', anlst_best_idea_rank: 'Analyst Rank', days_on: 'Days On',
    rank: 'Rank', wk_ago: 'Wk Ago', mn_ago: 'Mn Ago', position_sizing: 'Sizing',
  };
  var _NUMERIC_INT_COLS = { rank: 1, wk_ago: 1, mn_ago: 1, days_on: 1 };

  function _ensure() {
    if (document.getElementById(MODAL_ID)) return;
    var el = document.createElement('div');
    el.id = MODAL_ID;
    el.className = 'gauge-modal-backdrop';
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('role', 'dialog');
    el.innerHTML = [
      '<div class="gm-overlay" id="mvdOverlay"></div>',
      '<div class="gauge-modal">',
      '  <div class="gm-head">',
      '    <div>',
      '      <div class="gm-title" id="mvdTitle">&nbsp;</div>',
      '      <div class="gm-sub" id="mvdSub"></div>',
      '    </div>',
      '    <button class="gm-close" id="mvdClose" aria-label="Close">&#10005;</button>',
      '  </div>',
      '  <div class="gm-body">',
      '    <div class="gm-left-col">',
      '      <div class="gm-table-wrap">',
      '        <table class="gm-table" id="mvdTable">',
      '          <thead><tr id="mvdTableHead"></tr></thead>',
      '          <tbody id="mvdTableBody"></tbody>',
      '        </table>',
      '      </div>',
      '    </div>',
      '    <div class="gm-chart-pane">',
      '      <h4 id="mvdDailyTitle">Daily gain/loss</h4>',
      '      <svg class="chart" id="mvdDailyChart" viewBox="0 0 672 190"></svg>',
      '      <h4 style="margin-top:18px;" id="mvdWindowTitle">Window returns</h4>',
      '      <svg class="chart" id="mvdWindowChart" viewBox="0 0 672 160"></svg>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(el);
    document.getElementById('mvdClose').addEventListener('click', window.closeMarketViewDetailModal);
    document.getElementById('mvdOverlay').addEventListener('click', window.closeMarketViewDetailModal);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') window.closeMarketViewDetailModal();
    });
  }

  function svgns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }

  function _fmtVal(col, v) {
    if (v == null) return '—';
    if (col === 'pct_delta') return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
    if (_NUMERIC_INT_COLS[col]) return String(Math.round(v));
    if (typeof v === 'number') return v.toFixed(2);
    return String(v);
  }

  function _renderTable(cols, rows) {
    var head = document.getElementById('mvdTableHead');
    var body = document.getElementById('mvdTableBody');
    if (!head || !body) return;
    head.innerHTML = '<th>Symbol</th>' + cols.map(function (c) {
      return '<th style="text-align:right">' + (_COLUMN_LABELS[c] || c) + '</th>';
    }).join('');
    if (!rows.length) {
      body.innerHTML = '<tr><td class="gm-empty" colspan="' + (cols.length + 1) + '">No symbols.</td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (r) {
      var cells = cols.map(function (c) {
        var v = r[c];
        var cls = (typeof v === 'number') ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : '';
        return '<td class="dollar ' + cls + '">' + _fmtVal(c, v) + '</td>';
      }).join('');
      return '<tr><td class="sym">' + r.tos_symbol + '</td>' + cells + '</tr>';
    }).join('');
  }

  // Shared vertical-bar renderer -- items = [{label, value}], value in %.
  // Used for BOTH the daily gain/loss chart (many bars, one per day) and
  // the MTD/QTD/YTD window chart (few bars, one per window) -- same
  // orientation for both per user: "vertical bars for XLK for the bottom
  // graph" (the window chart had been horizontal bars in the first draft;
  // both now match the daily chart's vertical-bar shape).
  function _renderVerticalBars(svgId, items, opts) {
    var svg = document.getElementById(svgId);
    if (!svg) return;
    svg.innerHTML = '';
    var H = (opts && opts.height) || 190;
    var W = 672;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    if (!items.length || !items.some(function (it) { return it.value != null; })) {
      var empty = svgns('text');
      empty.setAttribute('x', 8); empty.setAttribute('y', 20);
      empty.setAttribute('class', 'bar-name'); empty.textContent = 'No data.';
      svg.appendChild(empty);
      return;
    }
    var padL = 10, padR = 10, padT = 26, padB = 30;
    var plotW = W - padL - padR, plotH = H - padT - padB;
    var vals = items.filter(function (it) { return it.value != null; }).map(function (it) { return Math.abs(it.value); });
    var max = Math.max.apply(null, vals) || 1;
    var slot = plotW / items.length;
    var barW = Math.max(Math.min(slot * 0.55, 46), 4);
    var zeroY = padT + plotH / 2;
    var barHalfMax = plotH / 2 - 16;

    var zeroLine = svgns('line');
    zeroLine.setAttribute('x1', padL); zeroLine.setAttribute('x2', W - padR);
    zeroLine.setAttribute('y1', zeroY); zeroLine.setAttribute('y2', zeroY);
    zeroLine.setAttribute('stroke', 'var(--border)'); zeroLine.setAttribute('stroke-width', '1');
    svg.appendChild(zeroLine);

    items.forEach(function (it, i) {
      var cx = padL + slot * i + slot / 2;
      var dateLbl = svgns('text');
      dateLbl.setAttribute('x', cx); dateLbl.setAttribute('y', H - 8);
      dateLbl.setAttribute('text-anchor', 'middle'); dateLbl.setAttribute('class', 'bar-name');
      dateLbl.setAttribute('style', 'font-size:9px;font-weight:400;');
      dateLbl.textContent = it.label;
      svg.appendChild(dateLbl);

      if (it.value == null) return;
      var h = Math.abs(it.value) / max * barHalfMax;
      var color = it.value > 0 ? 'var(--bull, #15803d)' : it.value < 0 ? 'var(--bear, #b91c1c)' : 'var(--text-3)';
      var rect = svgns('rect');
      rect.setAttribute('x', cx - barW / 2);
      rect.setAttribute('y', it.value >= 0 ? zeroY - h : zeroY);
      rect.setAttribute('width', barW); rect.setAttribute('height', Math.max(h, 1));
      rect.setAttribute('rx', 2); rect.setAttribute('fill', color);
      svg.appendChild(rect);

      var val = svgns('text');
      val.setAttribute('x', cx);
      val.setAttribute('y', it.value >= 0 ? zeroY - h - 4 : zeroY + h + 12);
      val.setAttribute('text-anchor', 'middle');
      val.setAttribute('class', 'bar-value');
      val.setAttribute('style', 'font-size:9px;');
      val.textContent = (it.value >= 0 ? '+' : '') + it.value.toFixed(1) + '%';
      svg.appendChild(val);
    });
  }

  function _dateQS(sep) {
    return (window.state && window.state.date) ? (sep + 'date=' + encodeURIComponent(window.state.date)) : '';
  }

  var _dailyReqId = 0;
  function _loadDaily(symbol) {
    var titleEl = document.getElementById('mvdDailyTitle');
    if (titleEl) titleEl.textContent = symbol ? (symbol + ' — Daily gain/loss (30d)') : 'Daily gain/loss (no benchmark for this category)';
    if (!symbol) { _renderVerticalBars('mvdDailyChart', []); return; }
    var reqId = ++_dailyReqId;
    fetch('/api/cockpit/benchmark-daily-change?symbol=' + encodeURIComponent(symbol) + '&days=30' + _dateQS('&'))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (reqId !== _dailyReqId) return;
        var items = (data.days || []).map(function (d) { return { label: d.date.slice(5), value: d.pct }; });
        _renderVerticalBars('mvdDailyChart', items, { height: 190 });
      })
      .catch(function (e) { console.error('benchmark daily-change failed:', e); });
  }

  function _renderWindows(symbol, benchRow) {
    var titleEl = document.getElementById('mvdWindowTitle');
    if (titleEl) titleEl.textContent = symbol ? (symbol + ' — MTD / QTD / YTD') : 'Window returns (no benchmark for this category)';
    var windows = [
      { key: 'today', label: 'Today' }, { key: 'yesterday', label: 'Yday' },
      { key: 'mtd', label: 'MTD' }, { key: 'qtd', label: 'QTD' }, { key: 'ytd', label: 'YTD' },
    ];
    var items = windows.map(function (w) {
      var v = benchRow ? benchRow['bench_' + w.key] : null;
      return { label: w.label, value: v != null ? Number(v) : null };
    });
    _renderVerticalBars('mvdWindowChart', items, { height: 160 });
  }

  // axis/category/source only (same "pass primitives, modal fetches its own
  // data" convention as openFactorExposureModal in risk_gauge_modal.js) --
  // the benchmark ETF symbol/window returns come from a second fetch here
  // (drv_category_perf via /api/cockpit/factor-scorecard, the same response
  // loadMarketView already uses for the grid's own bench_mtd/etc cells).
  // source === '' means the default "All" (Hedgeye quad-outlook) view --
  // still opens, still shows the benchmark charts (category+axis driven,
  // source-independent), but skips the per-symbol table fetch: there's no
  // single source's signal to list when blending all 4 quads. User: "you
  // could still have a popup for all and show the graphs only right?"
  window.openMarketViewDetailModal = function (axis, category, source) {
    _ensure();
    document.getElementById(MODAL_ID).classList.add('open');
    document.getElementById('mvdTitle').textContent = category + ' — ' + (_AXIS_LABEL[axis] || axis);
    document.getElementById('mvdSub').textContent = source ? ('Source: ' + source) : 'Source: All (Hedgeye quad outlook)';
    document.getElementById('mvdTableHead').innerHTML = '';
    document.getElementById('mvdTableBody').innerHTML = source
      ? '<tr><td class="gm-empty">Loading…</td></tr>'
      : '<tr><td class="gm-empty">No per-symbol table for "All" -- pick a Source above (RR/CALL/ETF/II/SSS/PS) to see it. Charts on the right still apply.</td></tr>';
    _renderVerticalBars('mvdDailyChart', []);
    _renderVerticalBars('mvdWindowChart', []);

    var scoreQs = 'axis=' + encodeURIComponent(axis) + _dateQS('&');
    fetch('/api/cockpit/factor-scorecard?' + scoreQs)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var catKey = category.trim().toLowerCase();
        var bench = (data.rows || []).find(function (r) { return String(r.category).trim().toLowerCase() === catKey; });
        var benchSymbol = bench ? bench.bench_symbol : null;
        var sub = document.getElementById('mvdSub');
        var srcLabel = source ? ('Source: ' + source) : 'Source: All (Hedgeye quad outlook)';
        if (sub) sub.textContent = srcLabel + (benchSymbol ? (' · Benchmark: ' + benchSymbol) : ' · No benchmark ETF for this category');
        _loadDaily(benchSymbol);
        _renderWindows(benchSymbol, bench);
      })
      .catch(function (e) { console.error('factor-scorecard (benchmark lookup) failed:', e); });

    if (!source) return;
    var qs = 'axis=' + encodeURIComponent(axis) + '&category=' + encodeURIComponent(category)
      + '&source=' + encodeURIComponent(source) + _dateQS('&');
    fetch('/api/quad/factor-stance/source-detail?' + qs)
      .then(function (r) { return r.json(); })
      .then(function (data) { _renderTable(data.columns || [], data.rows || []); })
      .catch(function (e) {
        console.error('source-detail failed:', e);
        var body = document.getElementById('mvdTableBody');
        if (body) body.innerHTML = '<tr><td class="gm-empty">Failed to load.</td></tr>';
      });
  };

  window.closeMarketViewDetailModal = function () {
    var el = document.getElementById(MODAL_ID);
    if (el) el.classList.remove('open');
  };
})();
