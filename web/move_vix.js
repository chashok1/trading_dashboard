/* Volatility panel (MOVE, VIX, VXN, RVX, GVZ, OVX), 2026-10-17 (user-directed; was the MOVE & VIX panel): change table with zone tags (Investable / Chop / Elevated from the Risk Dial's own
 * thresholds) and a chart with MOVE on the left axis and VIX, VXN and RVX on the right (GVZ and OVX are table-only), dashed lines at MOVE 100 / 120. Rising volatility = red background,
 * falling = green. Dashboard left column, below the Yield curve panel. Click the chart for a large popup with the full table.
 * Data: GET /api/cockpit/move-vix -> rows [date, move, vix, vxn, rvx, gvz, ovx] (hist_td closes), thresholds {sym: {low, high}}. */
(function () {
  'use strict';
  var L = 34, R = 30, T = 8, B = 18;
  var rowsAll = [], TH = {};
  var COL = { move: '#1668c4', vix: '#d9650b', vxn: '#0f9aa8', rvx: '#7a3fb5', warn: '#b7791f', hot: '#b3342b' };

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
  function zone(sym, v) {
    var t = TH[sym];
    if (!t || v == null) return ['', '--'];
    return v >= t.high ? ['hot', 'Elevated'] : v >= t.low ? ['chop', 'Chop'] : ['ok', 'Investable'];
  }

  function tableHtml(D, full) {
    var names = [['MOVE (bond vol)', 1, 'MOVE:GIF'], ['VIX (S&P)', 2, 'VIX'], ['VXN (Nasdaq)', 3, 'VXN:CGI'], ['RVX (Russell)', 4, 'RVX'],
      ['GVZ (gold)', 5, 'GVZ:CGI'], ['OVX (oil)', 6, 'OVX:CGI']];
    var cell = function (cur, past) {
      if (cur == null || past == null) return '<td>--</td>';
      var d = cur - past;
      return '<td class="' + (d > 0.005 ? 'yc-r' : d < -0.005 ? 'yc-g' : '') + '">' + (d > 0 ? '+' : '') + d.toFixed(1) + '</td>';
    };
    var head = '<tr><th>Series</th><th>Latest</th><th>Zone</th>' + (full ? '<th>1 day ago</th><th>1 week ago</th><th>4 weeks ago</th>' : '') +
      '<th>Day</th><th>Week</th><th>Month</th></tr>';
    var body = names.map(function (a) {
      var k = a[1], v = back(D, k, 0), d1 = back(D, k, 1), w1 = back(D, k, 5), m1 = back(D, k, 20), z = zone(a[2], v);
      var tip = 'Latest ' + f2(v) + ' | 1 day ago ' + f2(d1) + ' | 1 week ago ' + f2(w1) + ' | 4 weeks ago ' + f2(m1);
      return '<tr title="' + tip + '"><td>' + a[0] + '</td><td><b>' + f2(v) + '</b></td><td class="mv-z mv-' + z[0] + '">' + z[1] + '</td>' +
        (full ? '<td>' + f2(d1) + '</td><td>' + f2(w1) + '</td><td>' + f2(m1) + '</td>' : '') +
        cell(v, d1) + cell(v, w1) + cell(v, m1) + '</tr>';
    }).join('');
    return '<table class="yc-tbl">' + head + body + '</table>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No volatility data yet.</div>';
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var mv = [], vv = [];
    D.forEach(function (r) { if (r[1] != null) mv.push(r[1]); for (var c = 2; c <= 4; c++) if (r[c] != null) vv.push(r[c]); });
    var t = TH['MOVE:GIF'] || { low: 100, high: 120 };
    var lo = Math.floor(Math.min.apply(null, mv.concat([t.low])) / 10) * 10 - 5, hi = Math.ceil(Math.max.apply(null, mv.concat([t.high])) / 10) * 10 + 5;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var vlo = Math.floor(Math.min.apply(null, vv) / 5) * 5 - 2, vhi = Math.ceil(Math.max.apply(null, vv) / 5) * 5 + 2;
    var vy = function (v) { return T + (H - T - B) * (1 - (v - vlo) / (vhi - vlo)); };
    var s = '';
    for (var v = Math.ceil(lo / 10) * 10; v <= hi; v += 10) {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
        '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="' + COL.move + '">' + v + '</text>';
    }
    for (var q = Math.ceil(vlo / 5) * 5; q <= vhi; q += 5) {
      s += '<text x="' + (W - R + 4) + '" y="' + (vy(q) + 4) + '" font-size="' + fs + '" fill="' + COL.vix + '">' + q + '</text>';
    }
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t.low) + '" y2="' + y(t.low) + '" stroke="' + COL.warn + '" stroke-dasharray="5 4"/>' +
      '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t.high) + '" y2="' + y(t.high) + '" stroke="' + COL.hot + '" stroke-dasharray="5 4"/>';
    var path = function (k, sc, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + sc(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    s += path(4, vy, COL.rvx, 1.3) + path(3, vy, COL.vxn, 1.3) + path(2, vy, COL.vix, 1.5) + path(1, y, COL.move, 1.8);
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) { pm = m; s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + '</text>'; }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="MOVE, VIX, VXN and RVX with the caution and elevated lines for MOVE">' + s + '</svg>';
  }

  function legendHtml() {
    var t = TH['MOVE:GIF'] || { low: 100, high: 120 };
    return '<div class="yc-leg"><span><i style="background:' + COL.move + '"></i>MOVE (left)</span><span><i style="background:' + COL.vix + '"></i>VIX</span><span><i style="background:' + COL.vxn + '"></i>VXN</span><span><i style="background:' + COL.rvx + '"></i>RVX (right axis)</span>' +
      '<span><i style="background:' + COL.warn + '"></i>MOVE ' + t.low + '</span><span><i style="background:' + COL.hot + '"></i>MOVE ' + t.high + '</span></div>';
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
      tip.innerHTML = '<b>' + row[0] + '</b><br><span style="color:' + COL.move + '">&#9632;</span> MOVE: ' + f2(row[1]) +
        '<br><span style="color:' + COL.vix + '">&#9632;</span> VIX: ' + f2(row[2]) +
        '<br><span style="color:' + COL.vxn + '">&#9632;</span> VXN: ' + f2(row[3]) +
        '<br><span style="color:' + COL.rvx + '">&#9632;</span> RVX: ' + f2(row[4]) +
        '<br>GVZ: ' + f2(row[5]) + '<br>OVX: ' + f2(row[6]);
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('moveVixBody');
    if (!body) return;
    var D = rowsAll;
    if (!D.length) { body.innerHTML = '<div class="msr-loading">Volatility data unavailable.</div>'; return; }
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">Volatility</span><span class="yc-dt">as of ' + D[D.length - 1][0] + '</span></div>' +
      tableHtml(D, false) + legendHtml() + chartHtml(D, 600, 230, 11, 'yc-click');
    attachHover(body.querySelector('svg'), D, 600);
  }

  function closeModal() { var m = document.getElementById('moveVixModal'); if (m) m.remove(); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'moveVixModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">Volatility</h2>' +
      '<p style="margin:0;">' + rowsAll[0][0] + ' to ' + rowsAll[rowsAll.length - 1][0] + '</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + tableHtml(rowsAll, true) + legendHtml() + chartHtml(rowsAll, 1100, 420, 13, '') + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), rowsAll, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
  }

  async function load() {
    var body = document.getElementById('moveVixBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/move-vix' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var j = await res.json();
      rowsAll = j.rows || []; TH = j.thresholds || {};
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">Volatility unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('moveVixBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 900);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
