/* Yield curve panel, 2026-10-17 (user-directed): 2-year and 10-year Treasury yields plus the 10Y-2Y spread (right axis), with a change
 * table (rise = red background, fall = green). Dashboard left column, below Breadth. Click the chart for a large popup with the full table.
 * Data: GET /api/cockpit/yield-curve -> rows [date, dgs2, dgs10, t10y2y] (FRED; yields trail the spread by a day, so the table uses the
 * latest day that has all three and says which date that is). */
(function () {
  'use strict';
  var L = 34, R = 34, T = 8, B = 18;
  var rowsAll = [];
  // Matches the Hedgeye Macro Show yield-curve chart: 2Y black, 10Y gray, spread blue.
  var COL = { y2: '#000000', y10: '#7f7f7f', sp: '#1f6fb8' };
  var ST = 'yc', KEYS = ['y2', 'y10', 'sp'];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function f2(v) { return v == null ? '--' : v.toFixed(2); }

  // Latest index that has all three series, and the value n observations back for a series (skipping gaps).
  function lastFull(D) {
    var i = D.length - 1;
    while (i > 0 && (D[i][1] == null || D[i][2] == null || D[i][3] == null)) i--;
    return i;
  }
  function back(D, upto, k, off) {
    var c = 0;
    for (var i = upto; i >= 0; i--) {
      if (D[i][k] != null) { if (c === off) return D[i][k]; c++; }
    }
    return null;
  }

  function tableHtml(D, full) {
    var li = lastFull(D), names = [['2-year yield', 1], ['10-year yield', 2], ['10Y - 2Y spread', 3]];
    var cell = function (cur, past) {
      if (cur == null || past == null) return '<td>--</td>';
      var bp = Math.round((cur - past) * 100);
      return '<td class="' + (bp > 0 ? 'yc-r' : bp < 0 ? 'yc-g' : '') + '">' + (bp > 0 ? '+' : '') + bp + ' bp</td>';
    };
    var head = '<tr><th>Series</th><th>Latest</th>' + (full ? '<th>1 day ago</th><th>1 week ago</th><th>4 weeks ago</th>' : '') +
      '<th>Day</th><th>Week</th><th>Month</th></tr>';
    var body = names.map(function (a) {
      var k = a[1], v = back(D, li, k, 0), d1 = back(D, li, k, 1), w1 = back(D, li, k, 5), m1 = back(D, li, k, 20);
      var tip = 'Latest ' + f2(v) + ' | 1 day ago ' + f2(d1) + ' | 1 week ago ' + f2(w1) + ' | 4 weeks ago ' + f2(m1);
      return '<tr title="' + tip + '"><td>' + a[0] + '</td><td><b>' + f2(v) + '</b></td>' +
        (full ? '<td>' + f2(d1) + '</td><td>' + f2(w1) + '</td><td>' + f2(m1) + '</td>' : '') +
        cell(v, d1) + cell(v, w1) + cell(v, m1) + '</tr>';
    }).join('');
    return '<table class="yc-tbl">' + head + body + '</table>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No yield data yet.</div>';
    var hid = SeriesToggle.hidden(ST), on = function (k) { return !hid[k]; };
    var showL = on('y2') || on('y10'), showR = on('sp');
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    // Axis ranges come from the lines still showing on that axis.
    var yl = [];
    D.forEach(function (r) { if (on('y2') && r[1] != null) yl.push(r[1]); if (on('y10') && r[2] != null) yl.push(r[2]); });
    if (!yl.length) yl = [0, 1];
    var lo = Math.floor(Math.min.apply(null, yl) * 2) / 2 - 0.25, hi = Math.ceil(Math.max.apply(null, yl) * 2) / 2 + 0.25;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var sl = [];
    D.forEach(function (r) { if (r[3] != null) sl.push(r[3]); });
    var slo = Math.floor(Math.min.apply(null, sl) * 5) / 5 - 0.1, shi = Math.ceil(Math.max.apply(null, sl) * 5) / 5 + 0.1;
    var sy = function (v) { return T + (H - T - B) * (1 - (v - slo) / (shi - slo)); };
    var s = '';
    if (showL) {
      for (var v = Math.ceil(lo * 2) / 2; v <= hi; v += 0.5) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v.toFixed(1) + '</text>';
      }
    }
    if (showR) {
      for (var q = Math.ceil(slo * 5) / 5; q <= shi; q += 0.2) {
        if (!showL) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(q) + '" y2="' + sy(q) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (sy(q) + 4) + '" font-size="' + fs + '" fill="' + COL.sp + '">' + q.toFixed(1) + '</text>';
      }
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(0) + '" y2="' + sy(0) + '" stroke="' + COL.sp + '" stroke-dasharray="4 4" opacity=".5"/>';
    }
    var path = function (k, sc, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + sc(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    if (on('sp')) s += path(3, sy, COL.sp, 1.3);
    if (on('y10')) s += path(2, y, COL.y10, 1.4);
    if (on('y2')) s += path(1, y, COL.y2, 1.6);
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if ((+m.slice(5) - 1) % 3 === 0) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + " '" + m.slice(2, 4) + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="2-year and 10-year Treasury yields and the 10Y-2Y spread">' + s + '</svg>';
  }

  // Curve shape over `off` observations back: spread change vs how the 2Y and 10Y moved (bp). A move under 3 bp in the spread reads as unchanged.
  function shapeRead(D, off, label) {
    var li = lastFull(D), n2 = back(D, li, 1, 0), n10 = back(D, li, 2, 0), ns = back(D, li, 3, 0);
    var p2 = back(D, li, 1, off), p10 = back(D, li, 2, off), ps = back(D, li, 3, off);
    if ([n2, n10, ns, p2, p10, ps].some(function (v) { return v == null; })) return '';
    var d2 = Math.round((n2 - p2) * 100), d10 = Math.round((n10 - p10) * 100), ds = Math.round((ns - ps) * 100);
    var head = 'Over the ' + label + ' the spread went from ' + f2(ps) + ' to ' + f2(ns) + ' (' + (ds > 0 ? '+' : '') + ds + ' bp); the 2Y moved ' + (d2 > 0 ? '+' : '') + d2 + ' bp and the 10Y ' + (d10 > 0 ? '+' : '') + d10 + ' bp. ';
    if (Math.abs(ds) < 3) return head + 'The curve is about unchanged.';
    var bull = (d2 + d10) / 2 < 0;
    return head + 'That is a <b>' + (bull ? 'bull' : 'bear') + ' ' + (ds > 0 ? 'steepener' : 'flattener') + '</b>.';
  }

  // Plain-English guide to each line and to curve shapes, with the live read filled in from the data.
  function descHtml(D) {
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>2-year yield (black):</b> what the US government pays to borrow for 2 years. It follows what traders expect the Fed to do with interest rates: it falls when cuts are expected and rises when hikes are expected.</p>' +
      '<p><b>10-year yield (gray):</b> what the government pays to borrow for 10 years. It reflects the longer-term view on growth and inflation, and it is the rate that mortgages and corporate loans are priced off.</p>' +
      '<p><b style="color:' + COL.sp + '">10Y - 2Y spread (blue, right axis):</b> the 10-year minus the 2-year, which shows how steep the curve is. Positive is normal. Negative means the curve is inverted (short-term rates above long-term), which has often come before recessions.</p>' +
      '<p><b>Steepener</b> = the spread is rising. <b>Flattener</b> = the spread is falling. <b>Bull</b> = yields are falling overall (bond prices rising); <b>bear</b> = yields are rising overall.</p>' +
      '<ul>' +
      '<li><b>Bull steepener:</b> the 2Y falls faster than the 10Y. The market expects the Fed to cut rates. <i>For stocks: usually the best case if the economy is healthy; banks and small companies tend to do well. If the cuts come because the economy is breaking, stocks can fall anyway.</i></li>' +
      '<li><b>Bear steepener:</b> the 10Y rises faster than the 2Y. Investors want more pay for holding long bonds (inflation or heavy government borrowing). <i>For stocks: usually the worst case. Higher long rates pull valuations down, hitting tech, growth and housing.</i></li>' +
      '<li><b>Bull flattener:</b> the 10Y falls faster than the 2Y. Worry about growth is pulling long-term yields down. <i>For stocks: mixed. Defensive and big growth stocks hold up better, while cyclical stocks and banks do worse. It is a mild warning about growth.</i></li>' +
      '<li><b>Bear flattener:</b> the 2Y rises faster than the 10Y. The market expects the Fed to raise or hold rates high. <i>For stocks: usually negative. Tighter money hurts, especially small caps and growth stocks; it is typical of the late stage of an expansion.</i></li>' +
      '</ul>' +
      '<p><b>ETFs for the view.</b> <b>IVOL</b> is a steepener: it is meant to gain when the 10Y - 2Y spread widens (the blue line rises), and Hedgeye&#39;s core rates expression is long IVOL. <b>BNDD</b> is a flattener: it is meant to gain when the spread narrows (the blue line falls). Both also move with other things, such as inflation, deflation and option costs, so neither is a pure curve trade.</p>' +
      '<p><b>What it means for bond prices.</b> Bond prices move opposite to yields. When yields rise, existing bonds lose value, and when yields fall, they gain. Roughly, a 1 point change in yields moves a 2-year bond about 2%, a 10-year about 7%, and a 20+ year bond about 16%.</p>' +
      '<p><b>If you buy an ETF.</b> SHY follows the 2-year area, IEF the 10-year, and TLT the 20+ year. You receive a small cash payout every month, which is the interest on the bonds the fund holds. It can change from month to month. The fund never matures, so there is no date when you get your money back. You get the price when you sell, plus the payouts you collected.</p>' +
      '<p>Example (numbers vary): you buy $1,000 of IEF. If the 10-year yield rises 1 point, the price falls about $70, so selling would give you about $930 plus the payouts. If it falls 1 point, the price rises about $70, so selling would give you about $1,070 plus the payouts.</p>' +
      '<p><b>If you buy a bond directly.</b> Example (numbers vary): you buy a 10-year Treasury for $1,000 paying 4%, so $40 a year, fixed. If yields rise 1 point, the price falls about $70 on paper. If you hold to maturity, that does not matter: you collect the $40 a year and get your $1,000 back at the end. It only matters if you sell early, when you would get about $930.</p>' +
      '<p><b>Right now.</b> ' + shapeRead(D, 5, 'past week') + '</p>' +
      '<p>' + shapeRead(D, 20, 'past month') + '</p>' +
      '</div>';
  }

  function legendHtml() {
    var it = function (k, text) { return '<span>' + SeriesToggle.item(ST, k, '<i style="background:' + COL[k] + '"></i>' + text) + '</span>'; };
    return '<div class="yc-leg">' + it('y2', '2Y') + it('y10', '10Y') + it('sp', '10Y-2Y spread (right axis)') + '</div>';
  }

  // Hover: dashed guide + tooltip with the three values for the nearest day.
  function attachHover(svg, D, W) {
    if (!svg) return;
    var n = D.length, tip = null, guide = null, NS = 'http://www.w3.org/2000/svg';
    function hide() { if (tip) { tip.remove(); tip = null; } if (guide) { guide.remove(); guide = null; } }
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('mousemove', function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      var row = D[i], gx = L + (W - L - R) * i / (n - 1), vb = svg.viewBox.baseVal;
      if (!guide) {
        guide = document.createElementNS(NS, 'line');
        guide.setAttribute('stroke', '#888'); guide.setAttribute('stroke-dasharray', '3 3'); guide.setAttribute('pointer-events', 'none');
        svg.appendChild(guide);
      }
      guide.setAttribute('x1', gx); guide.setAttribute('x2', gx); guide.setAttribute('y1', T); guide.setAttribute('y2', vb.height - B);
      if (!tip) { tip = document.createElement('div'); tip.className = 'spxrv-tip'; document.body.appendChild(tip); }
      var hid = SeriesToggle.hidden(ST);
      tip.innerHTML = '<b>' + row[0] + '</b>' +
        (hid.y2 ? '' : '<br><span style="color:' + COL.y2 + '">&#9632;</span> 2Y: ' + f2(row[1])) +
        (hid.y10 ? '' : '<br><span style="color:' + COL.y10 + '">&#9632;</span> 10Y: ' + f2(row[2])) +
        (hid.sp ? '' : '<br><span style="color:' + COL.sp + '">&#9632;</span> Spread: ' + f2(row[3]));
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('yieldCurveBody');
    if (!body) return;
    var D = rowsAll;
    if (!D.length) { body.innerHTML = '<div class="msr-loading">Yield data unavailable.</div>'; return; }
    var li = lastFull(D);
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">Yield curve</span><span class="yc-dt">as of ' + D[li][0] + '</span></div>' +
      tableHtml(D, false) + legendHtml() + chartHtml(D, 600, 230, 11, 'yc-click');
    attachHover(body.querySelector('svg'), D, 600);
  }

  function closeModal() { var m = document.getElementById('yieldCurveModal'); if (m) m.remove(); }
  function modalBodyHtml() { return tableHtml(rowsAll, true) + legendHtml() + chartHtml(rowsAll, 1100, 420, 13, '') + descHtml(rowsAll); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var li = lastFull(rowsAll);
    var m = document.createElement('div');
    m.id = 'yieldCurveModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">US Treasury Yield Curve</h2>' +
      '<p style="margin:0;">' + rowsAll[0][0] + ' to ' + rowsAll[rowsAll.length - 1][0] + ' &middot; table as of ' + rowsAll[li][0] + '</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + modalBodyHtml() + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), rowsAll, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
    SeriesToggle.bind(m, ST, KEYS, refresh);
  }
  // A toggle redraws the panel and, if the popup is open, its body too.
  function refresh() {
    render();
    var m = document.getElementById('yieldCurveModal');
    if (m) { m.querySelector('.modal-body').innerHTML = modalBodyHtml(); attachHover(m.querySelector('svg'), rowsAll, 1100); }
  }

  async function load() {
    var body = document.getElementById('yieldCurveBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/yield-curve' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      rowsAll = (await res.json()).rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">Yield curve unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('yieldCurveBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    SeriesToggle.bind(host, ST, KEYS, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 800);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
