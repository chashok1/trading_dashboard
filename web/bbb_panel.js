/* 10-Year BBB Corporate Spread panel, 2026-10-17 (user-directed; deck page 33): ICE BofA BBB US Corporate effective yield minus the 10-year
 * Treasury yield, from Oct 2023, with the ICE BofA High Yield spread alongside on the right axis (2026-10-18) so you can see how the two move.
 * A change table (widening = red background, tightening = green), legend checkboxes to show or hide each line, and a plain-English description in the popup.
 * Dashboard left column, below the Credit panel. Click the chart for a large popup.
 * Data: GET /api/cockpit/bbb-spread -> rows [date, bbb_spread, hy_spread] (FRED; trails by a day). */
(function () {
  'use strict';
  var L = 30, R = 30, T = 8, B = 18;
  var rowsAll = [];
  var COL = { bbb: 'currentColor', hy: '#7a3fb5' };
  var ST = 'bb', KEYS = ['bbb', 'hy'];

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

  function tableHtml(D, full) {
    var cell = function (cur, past) {
      if (cur == null || past == null) return '<td>--</td>';
      var bp = Math.round((cur - past) * 100);
      return '<td class="' + (bp > 0 ? 'yc-r' : bp < 0 ? 'yc-g' : '') + '">' + (bp > 0 ? '+' : '') + bp + ' bp</td>';
    };
    var row = function (name, k) {
      var v = back(D, k, 0), d1 = back(D, k, 1), w1 = back(D, k, 5), m1 = back(D, k, 20);
      var tip = 'Latest ' + f2(v) + ' | 1 day ago ' + f2(d1) + ' | 1 week ago ' + f2(w1) + ' | 4 weeks ago ' + f2(m1);
      return '<tr title="' + tip + '"><td>' + name + '</td><td><b>' + f2(v) + '</b></td>' +
        (full ? '<td>' + f2(d1) + '</td><td>' + f2(w1) + '</td><td>' + f2(m1) + '</td>' : '') +
        cell(v, d1) + cell(v, w1) + cell(v, m1) + '</tr>';
    };
    return '<table class="yc-tbl"><tr><th>Series</th><th>Latest</th>' + (full ? '<th>1 day ago</th><th>1 week ago</th><th>4 weeks ago</th>' : '') +
      '<th>Day</th><th>Week</th><th>Month</th></tr>' + row('BBB spread (%)', 1) + row('High-yield spread (%)', 2) + '</table>';
  }

  function legendHtml() {
    var it = function (k, text) { return '<span>' + SeriesToggle.item(ST, k, '<i style="background:' + COL[k] + '"></i>' + text) + '</span>'; };
    return '<div class="yc-leg">' + it('bbb', 'BBB spread (left)') + it('hy', 'High-yield spread (right axis)') + '</div>';
  }

  // Rule-of-thumb read (popup only): the BBB spread's place in the chart's range and its change over about a month, and how big the
  // high-yield spread is compared with it.
  function phaseHtml(D) {
    var s = back(D, 1, 0), s1 = back(D, 1, 20), h = back(D, 2, 0);
    var vs = D.map(function (r) { return r[1]; }).filter(function (v) { return v != null; });
    if (s == null || s1 == null || !vs.length) return '';
    var lo = Math.min.apply(null, vs), d = s - s1;
    // [text, highlight]: red = widening, green = tightening
    var rd = d >= 0.1 ? ['worry is building', 'r'] : d <= -0.1 ? ['worry is easing', 'g'] : ['no strong signal', ''];
    var ratios = D.filter(function (r) { return r[1] > 0 && r[2] != null; }).map(function (r) { return r[2] / r[1]; }).sort(function (a, b) { return a - b; });
    var ratioTxt = h != null && ratios.length
      ? ' The high-yield spread is ' + (h / s).toFixed(1) + ' times the BBB spread (usual range ' + ratios[0].toFixed(1) + ' to ' + ratios[ratios.length - 1].toFixed(1) + ' on this chart).' : '';
    return '<p><b>Right now.</b> The BBB spread is ' + f2(s) + '%, ' + (d >= 0 ? 'up ' : 'down ') + Math.abs(d).toFixed(2) + ' points over the past month, and ' + (s - lo).toFixed(2) +
      ' above its low of ' + f2(lo) + '% on this chart.' + ratioTxt + ' Rule-of-thumb read: <span class="cr-read ' + rd[1] + '">' + rd[0] + '</span>.</p>';
  }

  function descHtml(D) {
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>The line:</b> the extra yield the lowest rung of investment-grade company bonds (BBB) pays over the 10-year Treasury, currently ' +
      f2(back(D, 1, 0)) + '%. It is the extra pay you get for taking company risk instead of lending to the government. A higher number means more worry, because investors want more extra pay and BBB bond prices are falling. A lower number means calm.</p>' +
      '<p><b>Why BBB is the bridge.</b> Company bonds are graded on a ladder: AAA, AA, A and BBB are investment-grade (the safe companies, held by LQD), and BB and below are high yield, or junk (the risky companies, held by HYG). BBB is the last rung of the safe group, right next to the line where bonds become junk, so it sits between what LQD and HYG hold.</p>' +
      '<p><b>BBB and high yield together.</b> The purple line is the high-yield spread, on its own axis on the right because it is much bigger. The two usually move in the same direction, but high yield moves roughly three times as much. <span class="cr-key">High yield widening while BBB stays flat means the worry is still in the weak companies. Both widening means worry is spreading beyond the weakest companies.</span></p>' +
      '<p><b>Downgrade risk.</b> BBB is a large slice of investment-grade. <span class="cr-key">If companies are downgraded from BBB to junk, it can force selling</span>, because many funds are only allowed to hold investment-grade bonds.</p>' +
      phaseHtml(D) + '</div>';
  }

  function chartHtml(D, W, H, fs, cls) {
    var n = D.length;
    if (n < 2) return '<div class="msr-loading">No BBB data yet.</div>';
    var hid = SeriesToggle.hidden(ST), showL = !hid.bbb, showR = !hid.hy;
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var vs = D.map(function (r) { return r[1]; });
    var lo = Math.floor(Math.min.apply(null, vs) * 10) / 10 - 0.05, hi = Math.ceil(Math.max.apply(null, vs) * 10) / 10 + 0.05;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var hs = D.map(function (r) { return r[2]; }).filter(function (v) { return v != null; });
    if (!hs.length) showR = false;
    var hlo = hs.length ? Math.floor(Math.min.apply(null, hs) * 2) / 2 - 0.25 : 0, hhi = hs.length ? Math.ceil(Math.max.apply(null, hs) * 2) / 2 + 0.25 : 1;
    var hy = function (v) { return T + (H - T - B) * (1 - (v - hlo) / (hhi - hlo)); };
    var step = (hi - lo) > 0.9 ? 0.2 : 0.1, s = '';
    if (showL) {
      for (var q = Math.ceil(lo / step) * step; q <= hi + 1e-9; q += step) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(q) + '" y2="' + y(q) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(q) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + q.toFixed(1) + '</text>';
      }
    }
    if (showR) {
      for (var h = Math.ceil(hlo * 2) / 2; h <= hhi; h += 0.5) {
        if (!showL) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + hy(h) + '" y2="' + hy(h) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (hy(h) + 4) + '" font-size="' + fs + '" fill="' + COL.hy + '">' + h.toFixed(1) + '</text>';
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
    if (showR) s += path(2, hy, COL.hy, 1.4);
    if (showL) s += path(1, y, COL.bbb, 1.6) + '<circle cx="' + x(n - 1) + '" cy="' + y(D[n - 1][1]) + '" r="3" fill="currentColor"/>';
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    D.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if ((+m.slice(5) - 1) % 3 === 0) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + " '" + m.slice(2, 4) + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="BBB corporate bond spread over the 10-year Treasury, with the high-yield spread">' + s + '</svg>';
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
      tip.innerHTML = '<b>' + row[0] + '</b>' + (hid.bbb ? '' : '<br>BBB spread: ' + f2(row[1]) + '%') +
        (hid.hy ? '' : '<br><span style="color:' + COL.hy + '">&#9632;</span> High-yield spread: ' + f2(row[2]) + '%');
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
      tableHtml(D, false) + legendHtml() + chartHtml(D, 600, 200, 11, 'yc-click');
    attachHover(body.querySelector('svg'), D, 600);
  }

  function closeModal() { var m = document.getElementById('bbbModal'); if (m) m.remove(); }
  function modalBodyHtml() { return tableHtml(rowsAll, true) + legendHtml() + chartHtml(rowsAll, 1100, 400, 13, '') + descHtml(rowsAll); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'bbbModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">10-Year BBB Corporate Spread</h2>' +
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
    var m = document.getElementById('bbbModal');
    if (m) { m.querySelector('.modal-body').innerHTML = modalBodyHtml(); attachHover(m.querySelector('svg'), rowsAll, 1100); }
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
    SeriesToggle.bind(host, ST, KEYS, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1050);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
