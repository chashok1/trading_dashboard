/* 10-Year BBB Corporate Spread panel, 2026-10-17 (user-directed; deck page 33): ICE BofA BBB US Corporate effective yield minus the 10-year
 * Treasury yield, from Oct 2023. A change table (widening = red background, tightening = green), the line, and a plain-English description.
 * Dashboard left column, below the Credit panel. Click the chart for a large popup.
 * Data: GET /api/cockpit/bbb-spread -> rows [date, spread] (FRED; trails by a day). */
(function () {
  'use strict';
  var L = 30, R = 10, T = 8, B = 18;
  var rowsAll = [];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function f2(v) { return v == null ? '--' : v.toFixed(2); }
  function at(D, off) { var r = D[D.length - 1 - off]; return r ? r[1] : null; }

  function tableHtml(D, full) {
    var v = at(D, 0), d1 = at(D, 1), w1 = at(D, 5), m1 = at(D, 20);
    var cell = function (cur, past) {
      if (cur == null || past == null) return '<td>--</td>';
      var bp = Math.round((cur - past) * 100);
      return '<td class="' + (bp > 0 ? 'yc-r' : bp < 0 ? 'yc-g' : '') + '">' + (bp > 0 ? '+' : '') + bp + ' bp</td>';
    };
    var tip = 'Latest ' + f2(v) + ' | 1 day ago ' + f2(d1) + ' | 1 week ago ' + f2(w1) + ' | 4 weeks ago ' + f2(m1);
    return '<table class="yc-tbl"><tr><th>Series</th><th>Latest</th>' + (full ? '<th>1 day ago</th><th>1 week ago</th><th>4 weeks ago</th>' : '') +
      '<th>Day</th><th>Week</th><th>Month</th></tr><tr title="' + tip + '"><td>BBB spread (%)</td><td><b>' + f2(v) + '</b></td>' +
      (full ? '<td>' + f2(d1) + '</td><td>' + f2(w1) + '</td><td>' + f2(m1) + '</td>' : '') +
      cell(v, d1) + cell(v, w1) + cell(v, m1) + '</tr></table>';
  }

  function descHtml(D) {
    return '<div class="cr-desc"><p><b>The line:</b> the extra yield the lowest rung of investment-grade company bonds (BBB) pays over the 10-year Treasury, currently ' +
      f2(at(D, 0)) + '%. A higher number means more worry. If it widens along with high yield, worry is spreading beyond the weakest companies.</p></div>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No BBB data yet.</div>';
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var vs = D.map(function (r) { return r[1]; });
    var lo = Math.floor(Math.min.apply(null, vs) * 10) / 10 - 0.05, hi = Math.ceil(Math.max.apply(null, vs) * 10) / 10 + 0.05;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var step = (hi - lo) > 0.9 ? 0.2 : 0.1, s = '';
    for (var q = Math.ceil(lo / step) * step; q <= hi + 1e-9; q += step) {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(q) + '" y2="' + y(q) + '" stroke="var(--border,#e5e5e2)"/>' +
        '<text x="' + (L - 4) + '" y="' + (y(q) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + q.toFixed(1) + '</text>';
    }
    var p = '';
    D.forEach(function (r, i) { p += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[1]).toFixed(1); });
    s += '<path d="' + p + '" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
      '<circle cx="' + x(n - 1) + '" cy="' + y(D[n - 1][1]) + '" r="3" fill="currentColor"/>';
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if ((+m.slice(5) - 1) % 3 === 0) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + " '" + m.slice(2, 4) + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="BBB corporate bond spread over the 10-year Treasury">' + s + '</svg>';
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
      tip.innerHTML = '<b>' + row[0] + '</b><br>BBB spread: ' + f2(row[1]) + '%';
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('bbbBody');
    if (!body) return;
    var D = rowsAll;
    if (!D.length) { body.innerHTML = '<div class="msr-loading">BBB data unavailable.</div>'; return; }
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">10-Year BBB Corporate Spread</span><span class="yc-dt">through ' + D[D.length - 1][0] + '</span></div>' +
      tableHtml(D, false) + chartHtml(D, 600, 200, 11, 'yc-click') + descHtml(D);
    attachHover(body.querySelector('svg'), D, 600);
  }

  function closeModal() { var m = document.getElementById('bbbModal'); if (m) m.remove(); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'bbbModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">10-Year BBB Corporate Spread</h2>' +
      '<p style="margin:0;">' + rowsAll[0][0] + ' to ' + rowsAll[rowsAll.length - 1][0] + '</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + tableHtml(rowsAll, true) + chartHtml(rowsAll, 1100, 400, 13, '') + descHtml(rowsAll) + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), rowsAll, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
  }

  async function load() {
    var body = document.getElementById('bbbBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/bbb-spread' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      rowsAll = (await res.json()).rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">BBB panel unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('bbbBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1050);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
