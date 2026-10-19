/* Credit panel, 2026-10-17 (user-directed); combined with the 10-Year BBB spread 2026-10-18: the high-yield spread (black) and the BBB spread (purple),
 * which share the left axis (both are spreads in %), and the High Yield Total Return Index (blue, right axis, rebased to 100 at the start of the window).
 * A change table, legend checkboxes to show or hide each line, and a plain-English guide in the popup. Spread widening = red background, tightening = green;
 * for the total return index a rise = green, a fall = red. Dashboard left column, below the Volatility panel. Click the chart for a large popup.
 * Data: GET /api/cockpit/credit -> rows [date, hy_oas, hy_total_return_rebased, bbb_spread] (FRED; each series trails by a day). */
(function () {
  'use strict';
  var L = 30, R = 34, T = 8, B = 18;
  var rowsAll = [];
  var COL = { hy: 'currentColor', bbb: '#7a3fb5', tr: '#1668c4' };
  var ST = 'cr', KEYS = ['hy', 'bbb', 'tr'];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function f2(v) { return v == null ? '--' : v.toFixed(2); }

  // Value of column k, `off` observations back from the latest (skipping gaps).
  function back(D, k, off) {
    var c = 0;
    for (var i = D.length - 1; i >= 0; i--) {
      if (D[i][k] != null) { if (c === off) return D[i][k]; c++; }
    }
    return null;
  }
  function lastDate(D, k) {
    for (var i = D.length - 1; i >= 0; i--) if (D[i][k] != null) return D[i][0];
    return '';
  }
  function colVals(D, k) { return D.map(function (r) { return r[k]; }).filter(function (v) { return v != null; }); }

  function tableHtml(D, full) {
    // kind 'bp': a spread, change in basis points, widening = red. kind 'pct': an index, change in %, a rise = green.
    var names = [['High-yield spread (%)', 1, 'bp'], ['BBB spread (%)', 3, 'bp'], ['HY total return index', 2, 'pct']];
    var cell = function (cur, past, kind) {
      if (cur == null || past == null) return '<td>--</td>';
      var v = kind === 'bp' ? Math.round((cur - past) * 100) : Math.round((cur / past - 1) * 1000) / 10;   // pct rounded to 0.1 so -0.04% reads as 0.0, not red
      var up = v > 0, dn = v < 0;
      var cls = kind === 'bp' ? (up ? 'yc-r' : dn ? 'yc-g' : '') : (up ? 'yc-g' : dn ? 'yc-r' : '');
      return '<td class="' + cls + '">' + (up ? '+' : '') + (kind === 'bp' ? v + ' bp' : v.toFixed(1) + '%') + '</td>';
    };
    var head = '<tr><th>Series</th><th>Latest</th>' + (full ? '<th>1 day ago</th><th>1 week ago</th><th>4 weeks ago</th>' : '') +
      '<th>Day</th><th>Week</th><th>Month</th></tr>';
    var body = names.map(function (a) {
      var k = a[1], kind = a[2], v = back(D, k, 0), d1 = back(D, k, 1), w1 = back(D, k, 5), m1 = back(D, k, 20);
      var tip = 'Latest ' + f2(v) + ' (' + lastDate(D, k) + ') | 1 day ago ' + f2(d1) + ' | 1 week ago ' + f2(w1) + ' | 4 weeks ago ' + f2(m1);
      return '<tr title="' + tip + '"><td>' + a[0] + '</td><td><b>' + f2(v) + '</b></td>' +
        (full ? '<td>' + f2(d1) + '</td><td>' + f2(w1) + '</td><td>' + f2(m1) + '</td>' : '') +
        cell(v, d1, kind) + cell(v, w1, kind) + cell(v, m1, kind) + '</tr>';
    }).join('');
    return '<table class="yc-tbl">' + head + body + '</table>';
  }

  function legendHtml() {
    var it = function (k, text) { return '<span>' + SeriesToggle.item(ST, k, '<i style="background:' + COL[k] + '"></i>' + text) + '</span>'; };
    return '<div class="yc-leg">' + it('hy', 'High-yield spread (left)') + it('bbb', 'BBB spread (left)') + it('tr', 'High Yield total return index (right axis)') + '</div>';
  }

  // [text, highlight] for a spread: its change over about a month (`wide` points) and its place in the chart's range.
  // red = worry building, green = worry fading or calm, amber = very low (expensive), none = no signal
  function readOf(d, pos, wide) {
    return d >= wide ? ['worry is building' + (pos > 0.66 ? ' from an already high level' : ''), 'r']
      : d <= -wide ? (pos > 0.5 ? ['worry is fading from a high level, which is usually the best entry', 'g'] : ['calm is returning', 'g'])
      : pos <= 0.15 ? ['the spread is very low, so bonds are expensive', 'a']
      : ['no strong signal', ''];
  }
  function tagHtml(rd) { return '<span class="cr-read ' + rd[1] + '">' + rd[0] + '</span>'; }

  // Rule-of-thumb reads (popup only): high yield, BBB, the total return gap, the high-yield/BBB ratio, and one combined read.
  function phaseHtml(D) {
    var h = back(D, 1, 0), h1 = back(D, 1, 20), b = back(D, 3, 0), b1 = back(D, 3, 20), tr = back(D, 2, 0);
    var hs = colVals(D, 1), bs = colVals(D, 3), trs = colVals(D, 2);
    if (h == null || h1 == null || !hs.length) return '';
    var hlo = Math.min.apply(null, hs), hhi = Math.max.apply(null, hs), hd = h - h1, hpos = hhi > hlo ? (h - hlo) / (hhi - hlo) : 0.5;
    var trTxt = tr != null && trs.length ? ' The total return index is ' + Math.abs((tr / Math.max.apply(null, trs) - 1) * 100).toFixed(1) + '% below its high.' : '';
    var out = '<p><b>Right now.</b> The high-yield spread is ' + f2(h) + '%, ' + (hd >= 0 ? 'up ' : 'down ') + Math.abs(hd).toFixed(2) + ' points over the past month, and ' + (h - hlo).toFixed(2) +
      ' above its low of ' + f2(hlo) + '% on this chart.' + trTxt + ' Rule-of-thumb read: ' + tagHtml(readOf(hd, hpos, 0.3)) + '.</p>';
    if (b == null || b1 == null || !bs.length) return out;
    var blo = Math.min.apply(null, bs), bhi = Math.max.apply(null, bs), bd = b - b1, bpos = bhi > blo ? (b - blo) / (bhi - blo) : 0.5;
    var ratios = D.filter(function (r) { return r[3] > 0 && r[1] != null; }).map(function (r) { return r[1] / r[3]; }).sort(function (x, y) { return x - y; });
    var ratioTxt = ratios.length ? ' The high-yield spread is ' + (h / b).toFixed(1) + ' times the BBB spread (usual range ' + ratios[0].toFixed(1) + ' to ' + ratios[ratios.length - 1].toFixed(1) + ' on this chart).' : '';
    out += '<p>The BBB spread is ' + f2(b) + '%, ' + (bd >= 0 ? 'up ' : 'down ') + Math.abs(bd).toFixed(2) + ' points over the past month, and ' + (b - blo).toFixed(2) +
      ' above its low of ' + f2(blo) + '% on this chart.' + ratioTxt + ' Rule-of-thumb read: ' + tagHtml(readOf(bd, bpos, 0.1)) + '.</p>';
    var bw = bd >= 0.1, bt = bd <= -0.1, hw = hd >= 0.3, ht = hd <= -0.3;
    var tg = bw && hw ? ['both spreads are widening, so worry is spreading beyond the weakest companies', 'r']
      : hw ? ['high yield is widening but BBB is not, so the worry is still in the weak companies and has not spread to BBB yet', 'a']
      : bw ? ['BBB is widening but high yield is not, which is unusual and worth watching', 'a']
      : bt && ht ? ['both spreads are tightening, so calm is returning', 'g']
      : ['no strong signal from the pair', ''];
    return out + '<p><b>Together:</b> ' + tagHtml(tg) + '.</p>';
  }

  // Plain-English guide, popup only; the current values are filled in from the data.
  function descHtml(D) {
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>Black line:</b> the high-yield spread. A bond&#39;s yield is the interest rate you earn on it. The yield on US Treasuries is what the government pays to borrow, the safest rate there is. High-yield bonds come from riskier companies (rated BB or lower, also called junk), so they pay more. The spread is the difference: the high-yield bond yield minus the Treasury yield, currently ' + f2(back(D, 1, 0)) + ' points. A higher spread means more worry, because investors want more extra pay and prices are falling. A lower spread means calm.</p>' +
      '<p><b style="color:' + COL.bbb + '">Purple line:</b> the BBB spread, the same idea for safer companies. BBB bonds come from companies the rating agencies call safe, but only just: BBB is the lowest &quot;safe&quot; rating. The spread is the BBB yield minus the 10-year Treasury yield, currently ' + f2(back(D, 3, 0)) + ' points. It sits on the same left axis, so you can see that high yield moves much more.</p>' +
      '<p><b style="color:' + COL.tr + '">Blue line (right axis):</b> the High Yield Total Return Index, what a holder of high-yield bonds has actually earned from interest and price changes (100 = the start of the chart).</p>' +
      '<p><b>Why BBB is the bridge.</b> Company bonds are graded on a ladder: AAA, AA, A and BBB are investment-grade (the safe companies, held by LQD), and BB and below are high yield, or junk (the risky companies, held by HYG). BBB is the last rung of the safe group, right next to the line where bonds become junk, so it sits between what LQD and HYG hold. <span class="cr-key">LQD&#39;s price follows the 10-year yield much more than the BBB spread, so treat the BBB spread as a credit-worry gauge, not a forecast for LQD.</span></p>' +
      '<p><b>High yield and BBB together.</b> The two spreads usually move in the same direction, but high yield moves roughly three times as much. <span class="cr-key">High yield widening while BBB stays flat means the worry is still in the weak companies. Both widening means worry is spreading beyond the weakest companies.</span></p>' +
      '<p><b>When does it pay to buy high yield?</b> In general, high-yield bonds are best bought when worry is high and starting to fade, and approached with care when worry is very low.</p>' +
      '<ul>' +
      '<li><b>Black line high and turning down:</b> worry has peaked and is fading. This is usually the best entry, because you get a high yield and prices recovering.</li>' +
      '<li><b>Black line falling and blue line rising:</b> calm is returning, and the gains are already coming.</li>' +
      '<li><b>Black line very low:</b> everyone is comfortable. Bonds are expensive, there is little room to gain, and the risk is the spread widening.</li>' +
      '<li><b>Black line rising fast and blue line falling:</b> worry is building. Prices usually keep falling for a while, so waiting is usually better.</li>' +
      '</ul>' +
      '<p>These are rules of thumb, not guarantees. A widening spread can keep going, and calm can last longer than expected.</p>' +
      '<p><b>How it relates to HYG.</b> HYG is an ETF of high-yield corporate bonds, the riskier companies. It is the one that follows the black and blue lines most closely: when the high-yield spread widens, HYG usually falls, and the blue line is roughly what HYG holders earn. HYG also reacts to interest rates: when the 10-year yield rises, it tends to fall.</p>' +
      '<ul>' +
      '<li><b>HYG falling while the spread widens:</b> the worry is about risky companies.</li>' +
      '<li><b>HYG falling while the 10-year yield rises and the spread is flat:</b> it is an interest rate move, not a credit scare.</li>' +
      '</ul>' +
      '<p><b>Downgrade risk.</b> BBB is a large slice of investment-grade. <span class="cr-key">If companies are downgraded from BBB to junk, it can force selling</span>, because many funds are only allowed to hold investment-grade bonds.</p>' +
      phaseHtml(D) +
      '</div>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No credit data yet.</div>';
    var hid = SeriesToggle.hidden(ST), on = function (k) { return !hid[k]; };
    var showL = on('hy') || on('bbb'), showR = on('tr');
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    // The left axis fits the spreads that are showing; the right axis fits the total return index.
    var sp = [];
    if (on('hy')) sp = sp.concat(colVals(D, 1));
    if (on('bbb')) sp = sp.concat(colVals(D, 3));
    if (!sp.length) sp = colVals(D, 1).concat(colVals(D, 3));
    var lo = Math.floor(Math.min.apply(null, sp) * 4) / 4 - 0.15, hi = Math.ceil(Math.max.apply(null, sp) * 4) / 4 + 0.15;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var trv = colVals(D, 2);
    var tlo = trv.length ? Math.floor(Math.min.apply(null, trv)) - 1 : 0, thi = trv.length ? Math.ceil(Math.max.apply(null, trv)) + 1 : 1;
    if (!trv.length) showR = false;
    var ty = function (v) { return T + (H - T - B) * (1 - (v - tlo) / (thi - tlo)); };
    var step = (hi - lo) <= 2 ? 0.25 : (hi - lo) <= 4.5 ? 0.5 : 1, tstep = (thi - tlo) > 20 ? 5 : 2;
    var s = '';
    if (showL) {
      for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v.toFixed(step < 0.5 ? 2 : 1) + '</text>';
      }
    }
    if (showR) {
      for (var q = Math.ceil(tlo / tstep) * tstep; q <= thi; q += tstep) {
        if (!showL) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + ty(q) + '" y2="' + ty(q) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (ty(q) + 4) + '" font-size="' + fs + '" fill="' + COL.tr + '">' + q + '</text>';
      }
    }
    var path = function (k, sc, color, w) {
      var p = '', pen = false;
      D.forEach(function (r, i) {
        if (r[k] == null) { pen = false; return; }
        p += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + sc(r[k]).toFixed(1); pen = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    if (showR) s += path(2, ty, COL.tr, 1.5);
    if (on('bbb')) s += path(3, y, COL.bbb, 1.5);
    if (on('hy')) s += path(1, y, COL.hy, 1.8);
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if ((+m.slice(5) - 1) % 3 === 0) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + " '" + m.slice(2, 4) + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="High-yield and BBB spreads and the High Yield total return index">' + s + '</svg>';
  }

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
      tip.innerHTML = '<b>' + row[0] + '</b>' + (hid.hy ? '' : '<br>High-yield spread: ' + f2(row[1]) + '%') +
        (hid.bbb ? '' : '<br><span style="color:' + COL.bbb + '">&#9632;</span> BBB spread: ' + f2(row[3]) + '%') +
        (hid.tr ? '' : '<br><span style="color:' + COL.tr + '">&#9632;</span> HY total return: ' + f2(row[2]));
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('creditBody');
    if (!body) return;
    var D = rowsAll;
    if (!D.length) { body.innerHTML = '<div class="msr-loading">Credit data unavailable.</div>'; return; }
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">Credit</span><span class="yc-dt">spread data through ' + lastDate(D, 1) + '</span></div>' +
      tableHtml(D, false) + legendHtml() + chartHtml(D, 600, 230, 11, 'yc-click');
    attachHover(body.querySelector('svg'), D, 600);
  }

  function closeModal() { var m = document.getElementById('creditModal'); if (m) m.remove(); }
  function modalBodyHtml() { return tableHtml(rowsAll, true) + legendHtml() + chartHtml(rowsAll, 1100, 420, 13, '') + descHtml(rowsAll); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'creditModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">Credit: high-yield and BBB spreads, and High Yield total return</h2>' +
      '<p style="margin:0;">' + rowsAll[0][0] + ' to ' + rowsAll[rowsAll.length - 1][0] + '</p></div>' +
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
    var m = document.getElementById('creditModal');
    if (m) { m.querySelector('.modal-body').innerHTML = modalBodyHtml(); attachHover(m.querySelector('svg'), rowsAll, 1100); }
  }

  async function load() {
    var body = document.getElementById('creditBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/credit' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      rowsAll = (await res.json()).rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">Credit panel unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('creditBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    SeriesToggle.bind(host, ST, KEYS, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
