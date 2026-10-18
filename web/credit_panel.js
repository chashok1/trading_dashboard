/* Credit panel, 2026-10-17 (user-directed): high-yield spread (black) and the High Yield Total Return Index (blue, right axis, rebased to
 * 100 at the start of the window), with a change table and a plain-English description of each line. (The BBB spread has its own panel.) Dashboard left column,
 * below the MOVE & VIX panel. Spread widening = red background, tightening = green; for the total return index a rise = green, a fall = red.
 * Click the chart for a large popup with the full table.
 * Data: GET /api/cockpit/credit -> rows [date, hy_oas, hy_total_return_rebased] (FRED; each series trails by a day). */
(function () {
  'use strict';
  var L = 30, R = 30, T = 8, B = 18;
  var rowsAll = [];
  var COL = { hy: 'currentColor', tr: '#1668c4' };
  var ST = 'cr', KEYS = ['hy', 'tr'];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function f2(v) { return v == null ? '--' : v.toFixed(2); }

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

  function tableHtml(D, full) {
    // kind 'bp': a spread, change in basis points, widening = red. kind 'pct': an index, change in %, a rise = green.
    var names = [['High-yield spread (%)', 1, 'bp'], ['HY total return index', 2, 'pct']];
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
    return '<div class="yc-leg"><span>' + SeriesToggle.item(ST, 'hy', '<i style="background:currentColor"></i>High-yield spread (left)') + '</span>' +
      '<span>' + SeriesToggle.item(ST, 'tr', '<i style="background:' + COL.tr + '"></i>High Yield total return index (right)') + '</span></div>';
  }

  // Rule-of-thumb read of where the spread is now (popup only): its level in the chart's range and its change over about a month.
  function phaseHtml(D) {
    var s = back(D, 1, 0), s1 = back(D, 1, 20), tr = back(D, 2, 0);
    var sp = [], trs = [];
    D.forEach(function (r) { if (r[1] != null) sp.push(r[1]); if (r[2] != null) trs.push(r[2]); });
    if (s == null || s1 == null || !sp.length) return '';
    var lo = Math.min.apply(null, sp), hi = Math.max.apply(null, sp), d = s - s1, pos = hi > lo ? (s - lo) / (hi - lo) : 0.5;
    // [text, highlight]: red = worry building, green = worry fading or calm, amber = expensive, none = no signal
    var rd = d >= 0.3 ? ['worry is building' + (pos > 0.66 ? ' from an already high level' : ''), 'r']
      : d <= -0.3 ? (pos > 0.5 ? ['worry is fading from a high level, which is usually the best entry', 'g'] : ['calm is returning', 'g'])
      : pos <= 0.15 ? ['the spread is very low, so bonds are expensive', 'a']
      : ['no strong signal', ''];
    var read = '<span class="cr-read ' + rd[1] + '">' + rd[0] + '</span>';
    var trTxt = tr != null && trs.length ? ' The total return index is ' + Math.abs((tr / Math.max.apply(null, trs) - 1) * 100).toFixed(1) + '% below its high.' : '';
    return '<p><b>Right now.</b> The spread is ' + f2(s) + '%, ' + (d >= 0 ? 'up ' : 'down ') + Math.abs(d).toFixed(2) + ' points over the past month, and ' + (s - lo).toFixed(2) +
      ' above its low of ' + f2(lo) + '% on this chart.' + trTxt + ' Rule-of-thumb read: ' + read + '.</p>';
  }

  // Plain-English description of each line; the current values are filled in from the data.
  function descHtml(D) {
    var hy = back(D, 1, 0);
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>Black line:</b> the high-yield spread. It&#39;s the extra yield investors demand over Treasuries, currently ' + f2(hy) + '%. A higher number means more worry.</p>' +
      '<p><b style="color:' + COL.tr + '">Blue line (right axis):</b> the High Yield Total Return Index, what a holder of those bonds has actually earned (100 = the start of the chart).</p>' +
      '<p><b>When does it pay to buy?</b> In general, high-yield bonds are best bought when worry is high and starting to fade, and approached with care when worry is very low.</p>' +
      '<ul>' +
      '<li><b>Black line high and turning down:</b> worry has peaked and is fading. This is usually the best entry, because you get a high yield and prices recovering.</li>' +
      '<li><b>Black line falling and blue line rising:</b> calm is returning, and the gains are already coming.</li>' +
      '<li><b>Black line very low:</b> everyone is comfortable. Bonds are expensive, there is little room to gain, and the risk is the spread widening.</li>' +
      '<li><b>Black line rising fast and blue line falling:</b> worry is building. Prices usually keep falling for a while, so waiting is usually better.</li>' +
      '</ul>' +
      '<p>These are rules of thumb, not guarantees. A widening spread can keep going, and calm can last longer than expected.</p>' +
      '<p><b>How it relates to HYG and LQD.</b> HYG is an ETF of high-yield corporate bonds, the riskier companies, so it moves with the lines on this chart. LQD is an ETF of investment-grade corporate bonds, the safer companies. When worry rises, both kinds of spread usually widen, but high yield moves roughly three to four times as much, so HYG usually falls more than LQD in a credit scare. LQD is more sensitive to interest rates because it holds longer-dated bonds, so when yields rise it tends to fall more than HYG, while HYG is driven more by credit worry.</p>' +
      '<ul>' +
      '<li><b>HYG falling while LQD holds up:</b> the worry is about risky companies.</li>' +
      '<li><b>Both falling together with the 10-year yield rising:</b> it is an interest rate move, not a credit scare.</li>' +
      '</ul>' +
      '<p>The 10-Year BBB spread panel sits between the two: it tracks the lowest rung of investment-grade.</p>' +
      phaseHtml(D) +
      '</div>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No credit data yet.</div>';
    var hid = SeriesToggle.hidden(ST), showHy = !hid.hy, showTr = !hid.tr;
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var sp = [], tr = [];
    D.forEach(function (r) {
      if (r[1] != null) sp.push(r[1]);
      if (r[2] != null) tr.push(r[2]);
    });
    var lo = Math.floor(Math.min.apply(null, sp) * 2) / 2 - 0.25, hi = Math.ceil(Math.max.apply(null, sp) * 2) / 2 + 0.25;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var tlo = Math.floor(Math.min.apply(null, tr)) - 1, thi = Math.ceil(Math.max.apply(null, tr)) + 1;
    var ty = function (v) { return T + (H - T - B) * (1 - (v - tlo) / (thi - tlo)); };
    var s = '';
    if (showHy) {
      for (var v = Math.ceil(lo * 2) / 2; v <= hi; v += 0.5) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v.toFixed(1) + '</text>';
      }
    }
    if (showTr) {
      for (var q = Math.ceil(tlo / 2) * 2; q <= thi; q += 2) {
        if (!showHy) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + ty(q) + '" y2="' + ty(q) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (ty(q) + 4) + '" font-size="' + fs + '" fill="' + COL.tr + '">' + q + '</text>';
      }
    }
    var path = function (k, sc, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + sc(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    if (showTr) s += path(2, ty, COL.tr, 1.5);
    if (showHy) s += path(1, y, COL.hy, 1.8);
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if ((+m.slice(5) - 1) % 3 === 1) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + " '" + m.slice(2, 4) + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="High-yield spread and High Yield total return index">' + s + '</svg>';
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
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">Credit: high-yield spread and High Yield total return</h2>' +
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
