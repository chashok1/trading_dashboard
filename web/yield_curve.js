/* Yield curve panel, 2026-10-17 (user-directed): 2-year and 10-year Treasury yields plus the 10Y-2Y spread (right axis), with a change
 * table (rise = red background, fall = green). Dashboard left column, below Breadth. Click the chart for a large popup with the full table.
 * Data: GET /api/cockpit/yield-curve -> rows [date, dgs2, dgs10, t10y2y] (FRED; yields trail the spread by a day, so the table uses the
 * latest day that has all three and says which date that is). */
(function () {
  'use strict';
  var L = 34, R = 34, T = 8, B = 18;
  var rowsAll = [];
  var COL = { y2: '#1668c4', y10: '#d9650b', sp: '#2a9d3a' };

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
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var yl = [];
    D.forEach(function (r) { if (r[1] != null) yl.push(r[1]); if (r[2] != null) yl.push(r[2]); });
    var lo = Math.floor(Math.min.apply(null, yl) * 2) / 2 - 0.25, hi = Math.ceil(Math.max.apply(null, yl) * 2) / 2 + 0.25;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var sl = [];
    D.forEach(function (r) { if (r[3] != null) sl.push(r[3]); });
    var slo = Math.floor(Math.min.apply(null, sl) * 5) / 5 - 0.1, shi = Math.ceil(Math.max.apply(null, sl) * 5) / 5 + 0.1;
    var sy = function (v) { return T + (H - T - B) * (1 - (v - slo) / (shi - slo)); };
    var s = '';
    for (var v = Math.ceil(lo * 2) / 2; v <= hi; v += 0.5) {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
        '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v.toFixed(1) + '</text>';
    }
    for (var q = Math.ceil(slo * 5) / 5; q <= shi; q += 0.2) {
      s += '<text x="' + (W - R + 4) + '" y="' + (sy(q) + 4) + '" font-size="' + fs + '" fill="' + COL.sp + '">' + q.toFixed(1) + '</text>';
    }
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(0) + '" y2="' + sy(0) + '" stroke="' + COL.sp + '" stroke-dasharray="4 4" opacity=".5"/>';
    var path = function (k, sc, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + sc(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    s += path(3, sy, COL.sp, 1.3) + path(2, y, COL.y10, 1.4) + path(1, y, COL.y2, 1.6);
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

  function legendHtml() {
    return '<div class="yc-leg"><span><i style="background:' + COL.y2 + '"></i>2Y</span><span><i style="background:' + COL.y10 + '"></i>10Y</span>' +
      '<span><i style="background:' + COL.sp + '"></i>10Y-2Y spread (right axis)</span></div>';
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
      tip.innerHTML = '<b>' + row[0] + '</b><br><span style="color:' + COL.y2 + '">&#9632;</span> 2Y: ' + f2(row[1]) +
        '<br><span style="color:' + COL.y10 + '">&#9632;</span> 10Y: ' + f2(row[2]) +
        '<br><span style="color:' + COL.sp + '">&#9632;</span> Spread: ' + f2(row[3]);
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
      '<div class="modal-body">' + tableHtml(rowsAll, true) + legendHtml() + chartHtml(rowsAll, 1100, 420, 13, '') + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), rowsAll, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
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
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 800);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
