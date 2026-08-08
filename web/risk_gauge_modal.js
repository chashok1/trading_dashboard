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
      '    <div class="gm-left-col">',
      '      <div class="gm-table-wrap">',
      '        <table class="gm-table">',
      '          <thead><tr><th>Symbol</th><th>Account</th><th style="text-align:right">$</th><th style="text-align:right" title="Unrealized gain/loss vs cost basis, since purchase (current snapshot)">Cumulative</th><th style="text-align:right" title="Broker-reported day change (day_chng_dollar/today_gl_dollar) for this position">Yesterday</th><th id="gmTagHead">Tag</th></tr></thead>',
      '          <tbody id="gmTableBody"></tbody>',
      '        </table>',
      '      </div>',
      '      <div class="gm-holdings-pane">',
      '        <svg class="chart" id="gmBarChart" viewBox="0 0 380 220"></svg>',
      '      </div>',
      '    </div>',
      '    <div class="gm-chart-pane">',
      '      <svg class="chart" id="gmSymHistChart" viewBox="0 0 460 160" style="display:none;"></svg>',
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
    // 2026-08-08 -- header text ("Largest holdings" h4) removed from above
    // this chart, and its vertical space reclaimed here instead (12px/5px
    // row/bar -> 18px/9px, fonts bumped back up 8px/7.5px -> 9px/8.5px) --
    // the .gm-holdings-pane is flex:0 0 auto within a grid-height-locked
    // left column, so a taller chart here just takes a bit more of that
    // column's already-fixed total height (shared with the scrollable
    // table above it) -- the POPUP's own height is set by the right
    // column and is untouched. User: "remove the header text 'LARGEST
    // HOLDINGS' and increase the height of the graph ... don't change the
    // popup height."
    // 2026-08-08 follow-up -- 50% taller again (18px/9px -> 27px/14px row/
    // bar) -- user: "increase by 50%".
    var W = 380, H = Math.max(top.length * 27, 113);
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var max = Math.max.apply(null, top.map(function (d) { return d[1]; })) || 1;
    var rowH = H / top.length, barH = 14, labelW = 108, plotW = W - labelW - 66;

    top.forEach(function (d, i) {
      var y = i * rowH + (rowH - barH) / 2;
      var isOther = /^Other/.test(d[0]);
      var color = isOther ? 'var(--text-3)' : 'var(--act-sell)';

      var name = svgns('text');
      name.setAttribute('x', labelW - 8); name.setAttribute('y', y + barH * 0.72 + 2);
      name.setAttribute('text-anchor', 'end'); name.setAttribute('class', 'bar-name');
      name.setAttribute('style', 'font-size:9px;');
      name.textContent = d[0];
      svg.appendChild(name);

      var w = (d[1] / max) * plotW;
      var rect = svgns('rect');
      rect.setAttribute('x', labelW); rect.setAttribute('y', y);
      rect.setAttribute('width', Math.max(w, 2)); rect.setAttribute('height', barH);
      rect.setAttribute('rx', 2); rect.setAttribute('fill', color);
      svg.appendChild(rect);

      var val = svgns('text');
      val.setAttribute('x', labelW + w + 8); val.setAttribute('y', y + barH * 0.72 + 2);
      val.setAttribute('class', 'bar-value'); val.setAttribute('style', 'font-size:8.5px;'); val.textContent = fmt(d[1]);
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
    // 2026-08-08 -- bar thickness reduced (11px -> 7px) to match Largest
    // holdings' earlier shrink, rows tightened accordingly -- user: "reduce
    // the bar widths for other graphs also".
    // 2026-08-08 follow-up -- rowH trimmed another 5% (58 -> 55) as part of
    // an overall 5% height reduction across both charts, so the popup fits
    // within the viewport without a scrollbar. User: "reduce height by 5%
    // so it doesn't have scroll bar".
    // 2026-08-08 follow-up -- W scaled up 29% (460 -> 594) to match the
    // right column's own 29% width increase (.gm-body grid ratio 1fr ->
    // 1.29fr) WITHOUT touching H -- these charts are width:100%/height:
    // auto off a fixed viewBox aspect ratio, so a wider container alone
    // would have stretched the rendered height too (both scale together
    // at a fixed W:H ratio). Growing viewBox W by the same factor the
    // container grew cancels that out: physical height stays put, the
    // extra physical width goes entirely to plot space (padL/labelW etc.
    // are fixed absolute units, so plotW = W - padL - ... grows with W).
    // User: "i was telling you to use [the extra width] without increasing
    // the height of the popup. or the graph heights".
    // 2026-08-08 follow-up -- W scaled up again (594 -> 672, matching the
    // right column's further 13.2% width increase from .gm-body's ratio
    // going 1.29fr -> 1.46fr), H untouched -- same cancel-the-stretch
    // reasoning as above.
    var W = 672, rowH = 55, H = groups.length * rowH + 10;
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
        var y = gy + 14 + si * 13;
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
        rect.setAttribute('width', Math.max(w, 1)); rect.setAttribute('height', 7);
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

  // 2026-08-08 -- per-symbol daily gain/loss bars, one graph reused across
  // row clicks (rowEl gets a 'selected' class to show which stock is
  // active; a second click on a different row just re-renders the SAME
  // chart with new data, not a new one). User: "Use one graph and change
  // the bars based on the stock selection."
  var _symHistReqId = 0;
  function _loadSymbolHistory(symbol, rowEl) {
    var tbody = document.getElementById('gmTableBody');
    if (tbody) Array.prototype.forEach.call(tbody.querySelectorAll('tr.selected'), function (el) {
      el.classList.remove('selected');
    });
    if (rowEl) rowEl.classList.add('selected');

    var reqId = ++_symHistReqId;
    fetch('/api/cockpit/symbol-daily-change?symbol=' + encodeURIComponent(symbol) + '&days=30')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (reqId !== _symHistReqId) return; // a later click superseded this one
        _renderSymbolHistory(data);
      })
      .catch(function (e) { console.error('symbol daily-change failed:', e); });
  }

  function _renderSymbolHistory(data) {
    var svg = document.getElementById('gmSymHistChart');
    if (!svg) return;
    var days = data.days || [];
    svg.style.display = '';
    svg.innerHTML = '';
    if (!days.length) {
      var empty = svgns('text');
      empty.setAttribute('x', 8); empty.setAttribute('y', 20);
      empty.setAttribute('class', 'bar-name'); empty.textContent = 'No daily history for ' + data.symbol + '.';
      svg.appendChild(empty);
      return;
    }

    // 2026-08-08 -- taller canvas with FIXED label bands reserved at the
    // top (positive values) and bottom (negative values, above the date
    // row) that bars are structurally capped (barHalfMax) from ever
    // reaching -- labels sit at a constant y regardless of that day's own
    // bar height, so they can never overlap ANY bar, not just their own.
    // The previous version anchored each label to its own bar's tip, which
    // let a wide "+$110 (+0.8%)" label creep into a taller NEIGHBOR bar.
    // User: "display numbers properly. they are overlapping with bars."
    // 2026-08-08 -- overall canvas grown (190 -> 260 tall) -- svg.chart is
    // width:100%/height:auto, so a taller viewBox (same W) renders visibly
    // bigger for the same container width. User: "make the daily gain/loss
    // graph bigger".
    // 2026-08-08 -- trimmed 5% (260 -> 247, padB/padT scaled to match) as
    // part of an overall 5% height reduction across both charts, so the
    // popup fits within the viewport without a scrollbar. User: "reduce
    // height by 5% so it doesn't have scroll bar".
    // 2026-08-08 follow-up -- W scaled up 29% (460 -> 594) to match the
    // right column's own width increase, H left untouched -- same
    // cancel-out-the-aspect-ratio-stretch reasoning as the Compare chart
    // above. User: "use [the extra width] without increasing the height
    // of the popup. or the graph heights".
    // 2026-08-08 follow-up -- W scaled up again (594 -> 672), H untouched,
    // matching the right column's further 13.2% width increase.
    var W = 672, H = 247, padL = 44, padB = 49, padT = 38;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var plotW = W - padL - 8, plotH = H - padB - padT;
    var max = Math.max.apply(null, days.map(function (d) { return Math.abs(d.dollar || 0); })) || 1;
    // 2026-08-08 -- widened again (0.85x -> 0.96x of the per-day slot,
    // gap shrunk 4px -> 1px) so bars fill nearly the entire per-day slot
    // instead of leaving visible gaps -- user: "increase bar sizes for
    // daily graph. Take up the whole graph space."
    var barW = Math.max((plotW / days.length - 1) * 0.96, 4);
    var zeroY = padT + plotH / 2;
    var barHalfMax = plotH / 2 - 22;
    var posLabelY = padT - 6, negLabelY = H - padB - 4;

    // 2026-08-08 -- in-chart header row (symbol left, total gain/loss over
    // the shown window right) replaces the old "Daily gain/loss — IAK" h4
    // that sat above the SVG -- reclaims that vertical space for the graph
    // itself. Total % is the compounded product of each day's own return
    // (mathematically correct for chaining daily returns, not just a naive
    // sum). User: "move the total gain or loss to the side of the amount
    // somewhere on the header. remove the text 'Daily gain/loss — IAK' and
    // use that space for the graph."
    var totalDollar = days.reduce(function (s, d) { return s + (d.dollar || 0); }, 0);
    var totalPct = (days.reduce(function (acc, d) {
      return d.pct != null ? acc * (1 + d.pct / 100) : acc;
    }, 1) - 1) * 100;
    var symLbl = svgns('text');
    symLbl.setAttribute('x', padL); symLbl.setAttribute('y', 16);
    symLbl.setAttribute('class', 'bar-name'); symLbl.setAttribute('style', 'font-size:11px;');
    symLbl.textContent = data.symbol;
    svg.appendChild(symLbl);
    // SVG text color comes from `fill`, not CSS `color` -- the shared
    // .pos/.neg classes only set `color` (built for HTML table cells), so
    // they're a no-op here; set fill directly instead, same pattern the
    // bar/rect colors elsewhere in this file already use.
    var totFill = totalDollar > 0 ? 'var(--bull, #15803d)' : totalDollar < 0 ? 'var(--bear, #b91c1c)' : 'var(--text-1)';
    var totLbl = svgns('text');
    totLbl.setAttribute('x', W - 8); totLbl.setAttribute('y', 16);
    totLbl.setAttribute('text-anchor', 'end');
    totLbl.setAttribute('style', 'font-size:11px;font-weight:700;fill:' + totFill + ';');
    totLbl.textContent = (totalDollar >= 0 ? '+' : '') + fmt(totalDollar) + ' (' + (totalPct >= 0 ? '+' : '') + totalPct.toFixed(1) + '%) over ' + days.length + 'd';
    svg.appendChild(totLbl);

    var zeroLine = svgns('line');
    zeroLine.setAttribute('x1', padL); zeroLine.setAttribute('x2', W - 8);
    zeroLine.setAttribute('y1', zeroY); zeroLine.setAttribute('y2', zeroY);
    zeroLine.setAttribute('stroke', 'var(--border)'); zeroLine.setAttribute('stroke-width', '1');
    svg.appendChild(zeroLine);

    // Thinned to every ~6th bar (was 5th) -- a bit more horizontal room
    // between labeled bars so neighboring value labels don't crowd each
    // other either.
    days.forEach(function (d, i) {
      var v = d.dollar || 0;
      var x = padL + i * (plotW / days.length) + 2;
      var h = Math.abs(v) / max * barHalfMax;
      var y = v >= 0 ? zeroY - h : zeroY;
      var color = v > 0 ? 'var(--bull, #15803d)' : v < 0 ? 'var(--bear, #b91c1c)' : 'var(--text-3)';

      var rect = svgns('rect');
      rect.setAttribute('x', x); rect.setAttribute('y', y);
      rect.setAttribute('width', barW); rect.setAttribute('height', Math.max(h, 1));
      rect.setAttribute('rx', 1); rect.setAttribute('fill', color);
      var ti = svgns('title');
      ti.textContent = d.date + ': ' + (v >= 0 ? '+' : '') + fmt(v) + (d.pct != null ? ' (' + (d.pct >= 0 ? '+' : '') + d.pct.toFixed(1) + '%)' : '');
      rect.appendChild(ti);
      svg.appendChild(rect);

      if (days.length <= 8 || i % 6 === 0 || i === days.length - 1) {
        var lbl = svgns('text');
        lbl.setAttribute('x', x + barW / 2); lbl.setAttribute('y', H - padB + 14);
        lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('class', 'bar-name');
        lbl.setAttribute('style', 'font-size:9px;font-weight:400;');
        lbl.textContent = d.date.slice(5);
        svg.appendChild(lbl);

        var valTxt = (v >= 0 ? '+' : '') + fmt(v) + (d.pct != null ? ' (' + (d.pct >= 0 ? '+' : '') + d.pct.toFixed(1) + '%)' : '');
        var val = svgns('text');
        val.setAttribute('x', x + barW / 2);
        val.setAttribute('y', v >= 0 ? posLabelY : negLabelY);
        val.setAttribute('text-anchor', 'middle'); val.setAttribute('class', 'bar-value');
        val.setAttribute('style', 'font-size:8px;');
        val.textContent = valTxt;
        svg.appendChild(val);
      }
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
    // Reset the symbol-history chart on every fresh open -- a stock
    // selected in a previous category/gauge popup shouldn't carry over.
    document.getElementById('gmSymHistChart').style.display = 'none';
    _symHistReqId++; // invalidate any in-flight history fetch from before

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
    // 2026-08-08 -- .d (amount) and .g (total gain/loss) now share a row
    // (.gm-total-row), .g pushed to the right at the same level as the
    // amount instead of stacked as a 3rd line below "% of portfolio" --
    // user: "$(%) total text is still being displayed below % of
    // portfolio. this text needs to be moved to the right side same level
    // as sector amount". .p stays on its own centered row below.
    document.getElementById('gmTotal').innerHTML = (data.dollar != null)
      ? '<div class="gm-total-row"><div class="d">' + fmt(data.dollar) + '</div>' + gainHtml + '</div>'
        + '<div class="p">' + (data.pct != null ? data.pct.toFixed(1) + '% of portfolio' : '') + '</div>'
      : '<div class="gm-total-row"><div class="d">&mdash;</div>' + gainHtml + '</div>';

    var tbody = document.getElementById('gmTableBody');
    var firstRow = null, firstSymbol = null;
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
      // 2026-08-08 -- click a row to select that stock and load its daily
      // gain/loss history into the (single, reused) chart below -- user
      // request: "i also want to see daily (or imported days) gains/losses
      // as a graph when i select a specific stock ... Use one graph and
      // change the bars based on the stock selection."
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', function () { _loadSymbolHistory(p.symbol, tr); });
      if (!firstRow) { firstRow = tr; firstSymbol = p.symbol; }
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
    // 2026-08-08 -- first row selected by default so the Daily gain/loss
    // chart isn't empty on open -- user request: "select the first stock
    // by default".
    if (firstRow) _loadSymbolHistory(firstSymbol, firstRow);
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
