/* Exposure drill-down modal -- shared by two triggers:
     - a fired gauge row on the Risk Dial card (openGaugeExposureModal)
     - a Factor Scorecard row, band 3 of the cockpit grid (openFactorExposureModal)
   Both card/table only ever show a 1-line $/% total; this shows the full
   position list behind it. Self-contained: injects its own DOM on first
   open, same pattern as chart_modal.js (Escape / overlay-click / X to
   close). The two backend responses differ slightly (gauge exposure-detail
   has label/categories/tag; factor exposure-detail has axis/category, no
   tag) -- _renderData() normalizes both into the same table + bar chart. */
(function () {
  var MODAL_ID = 'gaugeExpModal';

  function _ensure() {
    if (document.getElementById(MODAL_ID)) return;
    var el = document.createElement('div');
    el.id = MODAL_ID;
    el.className = 'gauge-modal-backdrop';
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('role', 'dialog');
    el.innerHTML = [
      '<div class="gm-overlay" id="gmOverlay"></div>',
      '<div class="gauge-modal">',
      '  <div class="gm-head">',
      '    <div>',
      '      <div class="gm-title" id="gmTitle">&nbsp;</div>',
      '      <div class="gm-sub" id="gmSub"></div>',
      '    </div>',
      '    <div class="gm-total" id="gmTotal"></div>',
      '    <button class="gm-close" id="gmClose" aria-label="Close">&#10005;</button>',
      '  </div>',
      '  <div class="gm-body" id="gmBody">',
      '    <div class="gm-table-wrap">',
      '      <table class="gm-table">',
      '        <thead><tr><th>Symbol</th><th>Account</th><th style="text-align:right">$</th><th style="text-align:right" title="Unrealized gain/loss vs cost basis, since purchase (current snapshot)">Cumulative</th><th style="text-align:right" title="Broker-reported day change (day_chng_dollar/today_gl_dollar) for this position">Yesterday</th><th id="gmTagHead">Tag</th></tr></thead>',
      '        <tbody id="gmTableBody"></tbody>',
      '      </table>',
      '    </div>',
      '    <div class="gm-chart-pane">',
      '      <h4>Largest holdings</h4>',
      '      <svg class="chart" id="gmBarChart" viewBox="0 0 380 300"></svg>',
      '      <h4 id="gmCompareTitle" style="margin-top:18px;">Yesterday: stock vs rest of category vs sector</h4>',
      '      <svg class="chart" id="gmCompareChart" viewBox="0 0 380 220"></svg>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(el);
    document.getElementById('gmClose').addEventListener('click', window.closeGaugeExposureModal);
    document.getElementById('gmOverlay').addEventListener('click', window.closeGaugeExposureModal);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') window.closeGaugeExposureModal();
    });
  }

  function _dateQS(sep) {
    return (window.state && window.state.date) ? (sep + 'date=' + encodeURIComponent(window.state.date)) : '';
  }

  function fmt(n) { return '$' + Math.round(n).toLocaleString('en-US'); }
  // Signed dollar amount for gain/loss cells -- '+$229' / '-$68', sign
  // always shown so a glance tells profit vs loss without reading color.
  function fmtSigned(n) { return (n >= 0 ? '+$' : '-$') + Math.round(Math.abs(n)).toLocaleString('en-US'); }
  function svgns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }

  function _renderBars(rows) {
    // Aggregate per symbol across accounts, take top 6 + an "Other" bucket --
    // a 20-row donut/bar is unreadable; this mirrors the design mockup.
    var bySym = {};
    rows.forEach(function (r) { bySym[r.symbol] = (bySym[r.symbol] || 0) + r.dollar; });
    var pairs = Object.keys(bySym).map(function (s) { return [s, bySym[s]]; })
      .sort(function (a, b) { return b[1] - a[1]; });
    var top = pairs.slice(0, 6);
    var restTotal = pairs.slice(6).reduce(function (s, p) { return s + p[1]; }, 0);
    var restCount = pairs.length - top.length;
    if (restCount > 0) top.push(['Other (' + restCount + ' pos.)', restTotal]);

    var svg = document.getElementById('gmBarChart');
    svg.innerHTML = '';
    var W = 380, H = Math.max(top.length * 32, 120);
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var max = Math.max.apply(null, top.map(function (d) { return d[1]; })) || 1;
    var rowH = H / top.length, barH = 20, labelW = 108, plotW = W - labelW - 66;

    top.forEach(function (d, i) {
      var y = i * rowH + (rowH - barH) / 2;
      var isOther = /^Other/.test(d[0]);
      var color = isOther ? 'var(--text-3)' : 'var(--act-sell)';

      var name = svgns('text');
      name.setAttribute('x', labelW - 8); name.setAttribute('y', y + barH * 0.72);
      name.setAttribute('text-anchor', 'end'); name.setAttribute('class', 'bar-name');
      name.textContent = d[0];
      svg.appendChild(name);

      var w = (d[1] / max) * plotW;
      var rect = svgns('rect');
      rect.setAttribute('x', labelW); rect.setAttribute('y', y);
      rect.setAttribute('width', Math.max(w, 2)); rect.setAttribute('height', barH);
      rect.setAttribute('rx', 4); rect.setAttribute('fill', color);
      svg.appendChild(rect);

      var val = svgns('text');
      val.setAttribute('x', labelW + w + 8); val.setAttribute('y', y + barH * 0.72);
      val.setAttribute('class', 'bar-value'); val.textContent = fmt(d[1]);
      svg.appendChild(val);
    });
  }

  // 2026-08-08 -- "stock vs rest of category vs sector" comparison chart,
  // next to Largest holdings. User request: "show it as a stock's %gain/
  // loss of the category vs rest vs sector". Three bars per top holding:
  //   - Stock: that symbol's own Yesterday % (dollar-weighted across
  //     accounts, from each position's yesterday_dollar/dollar already in
  //     the response)
  //   - Rest: the category's Yesterday % with that symbol excluded --
  //     derived client-side from the SAME positions list (category total
  //     minus this symbol's contribution), not a separate API call
  //   - Sector: the benchmark ETF's Yesterday % (data.sector_yesterday_pct)
  //     -- the one figure that isn't derivable from position data, same
  //     for every bar group since it's a single market reference
  // Only available on the Factor Scorecard popup (axis/category is a single
  // clean pair there); the Risk Dial gauge popup's response has no
  // category_yesterday_pct/sector_yesterday_pct, so this chart just hides.
  function _renderCompareChart(data) {
    var svg = document.getElementById('gmCompareChart');
    var title = document.getElementById('gmCompareTitle');
    if (!svg) return;
    svg.innerHTML = '';
    var positions = (data.positions || []).filter(function (p) { return p.yesterday_dollar != null; });
    if (!positions.length || data.sector_yesterday_pct == null) {
      if (title) title.style.display = 'none';
      svg.style.display = 'none';
      return;
    }
    if (title) title.style.display = '';
    svg.style.display = '';

    // Aggregate per symbol across accounts: dollar (today's mv) and
    // yesterday_dollar (yesterday's $ change), so a symbol held in several
    // accounts gets one combined bar, same as _renderBars.
    var bySym = {};
    positions.forEach(function (p) {
      var b = bySym[p.symbol] || (bySym[p.symbol] = { dollar: 0, yd: 0 });
      b.dollar += p.dollar; b.yd += p.yesterday_dollar;
    });
    var catTotalYd = 0, catPriorValue = 0;
    Object.keys(bySym).forEach(function (s) {
      catTotalYd += bySym[s].yd;
      catPriorValue += (bySym[s].dollar - bySym[s].yd);
    });

    var syms = Object.keys(bySym).sort(function (a, b) { return bySym[b].dollar - bySym[a].dollar; }).slice(0, 4);
    var groups = syms.map(function (s) {
      var b = bySym[s];
      var priorValue = b.dollar - b.yd;
      var stockPct = priorValue ? (b.yd / priorValue * 100) : null;
      var restYd = catTotalYd - b.yd, restPrior = catPriorValue - priorValue;
      var restPct = restPrior ? (restYd / restPrior * 100) : null;
      return { symbol: s, stock: stockPct, rest: restPct, sector: data.sector_yesterday_pct };
    });

    // 2026-08-08 -- widened + more vertical room per row (labels were
    // overlapping the bars: negative bars could extend all the way back to
    // the label column with no gap between them). labelW/gap/valueGap now
    // reserve dedicated space so a max-magnitude bar's rect AND its value
    // text never reach the row-label or symbol-name text. User: "Labels
    // are overlapping with bars. you have to increase graph size."
    var W = 460, rowH = 72, H = groups.length * rowH + 10;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var vals = [];
    groups.forEach(function (g) { [g.stock, g.rest, g.sector].forEach(function (v) { if (v != null) vals.push(Math.abs(v)); }); });
    var max = Math.max.apply(null, vals.length ? vals : [1]) || 1;
    var labelW = 60, valueGap = 46, plotStart = labelW + 8, plotEnd = W - valueGap;
    var plotHalf = (plotEnd - plotStart) / 2, midX = plotStart + plotHalf;
    // "Stock" (my own holding) colors green/+ve, red/-ve like everywhere
    // else in the app (.pos/.neg convention) -- Rest/Sector stay neutral
    // gray/blue since they're reference lines, not "my" performance. User:
    // "Use green for +ves and reds for -ves for my stocks."
    var series = [
      { key: 'stock', label: 'Stock', color: null },
      { key: 'rest', label: 'Rest', color: 'var(--text-3)' },
      { key: 'sector', label: 'Sector', color: 'var(--accent, #1d4ed8)' },
    ];

    groups.forEach(function (g, gi) {
      var gy = gi * rowH + 6;
      var name = svgns('text');
      name.setAttribute('x', 4); name.setAttribute('y', gy + 10);
      name.setAttribute('class', 'bar-name'); name.textContent = g.symbol;
      svg.appendChild(name);

      series.forEach(function (ser, si) {
        var v = g[ser.key];
        var y = gy + 16 + si * 16;
        var lbl = svgns('text');
        lbl.setAttribute('x', labelW - 4); lbl.setAttribute('y', y + 8);
        lbl.setAttribute('text-anchor', 'end'); lbl.setAttribute('class', 'bar-name');
        lbl.setAttribute('style', 'font-size:9px;font-weight:400;'); lbl.textContent = ser.label;
        svg.appendChild(lbl);

        if (v == null) return;
        var color = ser.color || (v > 0 ? 'var(--bull, #15803d)' : v < 0 ? 'var(--bear, #b91c1c)' : 'var(--text-3)');
        var w = Math.abs(v) / max * plotHalf;
        var x = v >= 0 ? midX : midX - w;
        var rect = svgns('rect');
        rect.setAttribute('x', x); rect.setAttribute('y', y);
        rect.setAttribute('width', Math.max(w, 1)); rect.setAttribute('height', 11);
        rect.setAttribute('rx', 2); rect.setAttribute('fill', color);
        svg.appendChild(rect);

        var val = svgns('text');
        val.setAttribute('x', v >= 0 ? midX + w + 4 : midX - w - 4);
        val.setAttribute('y', y + 8);
        val.setAttribute('text-anchor', v >= 0 ? 'start' : 'end');
        val.setAttribute('class', 'bar-value');
        val.textContent = (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
        svg.appendChild(val);
      });

      var mid = svgns('line');
      mid.setAttribute('x1', midX); mid.setAttribute('x2', midX);
      mid.setAttribute('y1', gy); mid.setAttribute('y2', gy + rowH - 8);
      mid.setAttribute('stroke', 'var(--border)'); mid.setAttribute('stroke-width', '1');
      svg.appendChild(mid);
    });
  }

  // opts: {title, subtitlePrefix} -- title shown if the response has no
  // better one (factor response has no `label`); subtitlePrefix prepends
  // e.g. "Sector match" before the position/account count.
  function _open(fetchUrl, fallbackTitle, subtitlePrefix) {
    _ensure();
    var modal = document.getElementById(MODAL_ID);
    modal.classList.add('open');
    document.getElementById('gmTitle').textContent = fallbackTitle;
    document.getElementById('gmSub').textContent = 'Loading…';
    document.getElementById('gmTotal').innerHTML = '';
    document.getElementById('gmTableBody').innerHTML = '';
    document.getElementById('gmBarChart').innerHTML = '';

    fetch(fetchUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) { _renderData(data, fallbackTitle, subtitlePrefix); })
      .catch(function (e) {
        console.error('exposure detail failed:', e);
        document.getElementById('gmSub').textContent = 'Failed to load exposure detail.';
      });
  }

  function _renderData(data, fallbackTitle, subtitlePrefix) {
    var hasTag = (data.positions || []).some(function (p) { return p.tag; });
    document.getElementById('gmTagHead').style.display = hasTag ? '' : 'none';

    document.getElementById('gmTitle').textContent = data.label || fallbackTitle;
    var cats = (data.categories || []).join(' · ');
    var n = (data.positions || []).length;
    var acctCount = new Set((data.positions || []).map(function (p) { return p.account; })).size;
    var prefix = cats ? ('Match: ' + cats + '  ·  ') : (subtitlePrefix ? subtitlePrefix + '  ·  ' : '');
    document.getElementById('gmSub').textContent =
      prefix + n + ' position' + (n === 1 ? '' : 's') +
      (acctCount ? ' across ' + acctCount + ' account' + (acctCount === 1 ? '' : 's') : '');
    // Total gain/loss across every position shown -- sum(gain_dollar)
    // straightforwardly; total % isn't a simple average of per-position %s
    // (that would over-weight small positions), so it's derived the same
    // way each row's own % is: gain / cost-basis, with cost-basis backed
    // out as dollar - gain_dollar (unrealized-gain identity, matches
    // api/routers/cockpit.py::_gain_fields). User request: "show total sum
    // of gains or losses in the popups".
    var totalGain = null, totalGainPct = null;
    var gainRows = (data.positions || []).filter(function (p) { return p.gain_dollar != null; });
    if (gainRows.length) {
      var sumGain = gainRows.reduce(function (s, p) { return s + p.gain_dollar; }, 0);
      var sumCostBasis = gainRows.reduce(function (s, p) {
        return s + ((p.dollar != null ? p.dollar : 0) - p.gain_dollar);
      }, 0);
      totalGain = sumGain;
      totalGainPct = sumCostBasis ? (sumGain / sumCostBasis * 100) : null;
    }
    var gainHtml = '';
    if (totalGain != null) {
      var gainCls = totalGain > 0 ? 'pos' : totalGain < 0 ? 'neg' : '';
      gainHtml = '<div class="g ' + gainCls + '">' + fmtSigned(totalGain) +
        (totalGainPct != null ? ' (' + (totalGainPct >= 0 ? '+' : '') + totalGainPct.toFixed(1) + '%)' : '') +
        ' total</div>';
    }
    document.getElementById('gmTotal').innerHTML = (data.dollar != null)
      ? '<div class="d">' + fmt(data.dollar) + '</div><div class="p">' + (data.pct != null ? data.pct.toFixed(1) + '% of portfolio' : '') + '</div>' + gainHtml
      : '<div class="d">&mdash;</div>' + gainHtml;

    var tbody = document.getElementById('gmTableBody');
    (data.positions || []).forEach(function (p) {
      var tr = document.createElement('tr');
      var symTd = document.createElement('td'); symTd.className = 'sym'; symTd.textContent = p.symbol;
      var acctTd = document.createElement('td'); acctTd.className = 'acct'; acctTd.textContent = p.account;
      var dTd = document.createElement('td'); dTd.className = 'dollar'; dTd.textContent = fmt(p.dollar);
      var glTd = document.createElement('td'); glTd.className = 'dollar';
      if (p.gain_pct != null) {
        // 2026-08-08 BUGFIX -- classList.add('') throws SyntaxError on a
        // flat (exactly 0) value, silently aborting the rest of this
        // forEach and every row after it -- "missing colors" (and rows)
        // report. Only add a class when there actually is one.
        var glCls = p.gain_pct > 0 ? 'pos' : p.gain_pct < 0 ? 'neg' : '';
        if (glCls) glTd.classList.add(glCls);
        // $ and % shown together now (previously $ was tooltip-only, easy
        // to miss) -- user request: "add $ loss or gain to these popups
        // along with %loss/%gain".
        var glText = (p.gain_pct >= 0 ? '+' : '') + p.gain_pct.toFixed(1) + '%';
        if (p.gain_dollar != null) glText = fmtSigned(p.gain_dollar) + ' (' + glText + ')';
        glTd.textContent = glText;
        glTd.title = (p.gain_dollar != null ? fmt(p.gain_dollar) : '') + ' unrealized';
      } else {
        glTd.textContent = '—';
      }
      // 2026-08-08 -- per-stock Yesterday $/%, same broker day_chng_dollar/
      // today_gl_dollar figures the category-level "Yesterday" column sums
      // (etl/derive_category_perf.py::_yesterday_actual_change) -- user
      // request: "Can the popups include these numbers for each stock?"
      var yTd = document.createElement('td'); yTd.className = 'dollar';
      if (p.yesterday_dollar != null) {
        var yCls = p.yesterday_dollar > 0 ? 'pos' : p.yesterday_dollar < 0 ? 'neg' : '';
        if (yCls) yTd.classList.add(yCls);
        var yText = fmtSigned(p.yesterday_dollar);
        if (p.yesterday_pct != null) yText += ' (' + (p.yesterday_pct >= 0 ? '+' : '') + p.yesterday_pct.toFixed(1) + '%)';
        yTd.textContent = yText;
      } else {
        yTd.textContent = '—';
      }
      tr.appendChild(symTd); tr.appendChild(acctTd); tr.appendChild(dTd); tr.appendChild(glTd); tr.appendChild(yTd);
      if (hasTag) {
        var tagTd = document.createElement('td'); tagTd.className = 'tag'; tagTd.textContent = p.tag || '';
        tr.appendChild(tagTd);
      }
      tbody.appendChild(tr);
    });
    if (!(data.positions || []).length) {
      var tr = document.createElement('tr');
      var td = document.createElement('td'); td.colSpan = hasTag ? 6 : 5; td.className = 'gm-empty';
      td.textContent = 'No positions match.';
      tr.appendChild(td); tbody.appendChild(tr);
    } else {
      _renderBars(data.positions);
    }
    _renderCompareChart(data);
  }

  window.openGaugeExposureModal = function (gaugeKey) {
    _open('/api/cockpit/risk-dial/' + encodeURIComponent(gaugeKey) + '/exposure-detail' + _dateQS('?'),
          gaugeKey, null);
  };

  window.openFactorExposureModal = function (axis, category) {
    var axisLabel = axis === 'asset_class' ? 'Asset class' : (axis === 'style' ? 'Style' : 'Sector');
    _open('/api/cockpit/factor-scorecard/' + encodeURIComponent(axis) + '/' + encodeURIComponent(category) +
          '/exposure-detail' + _dateQS('?'), category, axisLabel + ' match');
  };

  window.closeGaugeExposureModal = function () {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.remove('open');
  };
})();
