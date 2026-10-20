/* Jobless claims panel, 2026-10-19 (user-directed): weekly initial jobless claims (FRED ICSA) with a 4-week average and a 250k warning line.
 * Dashboard left column, below Retail sentiment. Click the chart for a large popup with an explanation.
 * Data: GET /api/cockpit/jobless-claims -> {rows: [week_ending, claims, avg4]} (hist_macro). */
(function () {
  'use strict';
  var L = 38, R = 10, T = 8, B = 18, WARN = 250000;
  var rowsAll = [];
  var C_WK = '#1668c4', C_AVG = '#d9650b';

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function k(v) { return v == null ? '--' : Math.round(v / 1000) + 'k'; }
  function sgn(v) { return v == null ? '--' : (v > 0 ? '+' : '') + Math.round(v / 1000) + 'k'; }

  function tableHtml() {
    var n = rowsAll.length, last = rowsAll[n - 1], prev = rowsAll[n - 2];
    var yr = rowsAll.slice(-52).map(function (r) { return r[1]; });
    // Rising claims is bad for jobs, so an increase is shown red and a drop green.
    var chg = prev ? last[1] - prev[1] : null;
    var cc = chg == null || chg === 0 ? '' : (chg > 0 ? 'yc-r' : 'yc-g');
    return '<table class="yc-tbl"><tr><th>Latest</th><th>Week</th><th>4-wk avg</th><th>52-wk low</th><th>52-wk high</th></tr><tr>' +
      '<td>' + k(last[1]) + '</td><td class="' + cc + '">' + sgn(chg) + '</td><td>' + k(last[2]) + '</td>' +
      '<td>' + k(Math.min.apply(null, yr)) + '</td><td>' + k(Math.max.apply(null, yr)) + '</td></tr></table>';
  }

  function chartHtml(W, H, fs, cls) {
    var n = rowsAll.length;
    if (n < 2) return '<div class="msr-loading">No jobless claims data yet.</div>';
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var all = [WARN];
    rowsAll.forEach(function (r) { all.push(r[1]); if (r[2] != null) all.push(r[2]); });
    var lo = Math.floor(Math.min.apply(null, all) / 50000) * 50000 - 25000, hi = Math.ceil(Math.max.apply(null, all) / 50000) * 50000 + 25000;
    lo = Math.max(lo, 0);
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var s = '';
    for (var v = Math.ceil(lo / 50000) * 50000; v <= hi; v += 50000) {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
        '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + (v / 1000) + 'k</text>';
    }
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(WARN) + '" y2="' + y(WARN) + '" stroke="#c0392b" stroke-dasharray="5 4" opacity=".7"/>' +
      '<text x="' + (W - R - 2) + '" y="' + (y(WARN) - 3) + '" text-anchor="end" font-size="' + fs + '" fill="#c0392b">250k warning</text>';
    var path = function (j, color, w, op) {
      var p = '', on = false;
      rowsAll.forEach(function (r, i) {
        if (r[j] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[j]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" opacity="' + op + '" stroke-linejoin="round"/>';
    };
    s += path(1, C_WK, 1.2, 0.8) + path(2, C_AVG, 2, 1);
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    rowsAll.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) {
        pm = m;
        if (+m.slice(5) % 3 === 1) s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + (m.slice(5) === '01' ? ' ' + m.slice(2, 4) : '') + '</text>';
      }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="Weekly initial jobless claims">' + s + '</svg>';
  }

  function legendHtml() {
    return '<div class="cr-desc"><p><i class="mo-sw" style="background:' + C_WK + '"></i>Weekly claims &nbsp; <i class="mo-sw" style="background:' + C_AVG + '"></i>4-week average</p></div>';
  }

  // Plain-English guide, popup only.
  function descHtml() {
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>What this shows.</b> How many people filed a brand-new claim for unemployment benefits each week in the US. It comes out every Thursday, which makes it one of the fastest readings on the job market.</p>' +
      '<p><b>Why it matters.</b> Companies lay people off before a slowdown shows up in other numbers. So when claims climb and stay up, it is an early sign the economy is weakening, and stocks often wobble with it. When claims are low and steady, companies are holding on to their workers.</p>' +
      '<p><b>The two lines.</b> The blue line is each single week, which jumps around a lot (holidays and storms can move it by 10% or more). The orange line is the average of the last four weeks and is the one to trust.</p>' +
      '<p><b>The 250k line.</b> In healthy stretches claims usually stay below about 250,000 a week. A move above it that holds is a warning that layoffs are picking up.</p>' +
      '<p><b>How to read it.</b> <span class="cr-key">One high week means little. Watch whether the orange line is steadily rising and heading toward or through the red line.</span> Rising claims is bad news for jobs, so a rise is shown in red in the table and a fall in green.</p>' +
      '</div>';
  }

  function attachHover(svg, W) {
    if (!svg) return;
    var n = rowsAll.length, tip = null, guide = null, NS = 'http://www.w3.org/2000/svg';
    function hide() { if (tip) { tip.remove(); tip = null; } if (guide) { guide.remove(); guide = null; } }
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('mousemove', function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      var row = rowsAll[i], gx = L + (W - L - R) * i / (n - 1), vb = svg.viewBox.baseVal;
      if (!guide) {
        guide = document.createElementNS(NS, 'line');
        guide.setAttribute('stroke', '#888'); guide.setAttribute('stroke-dasharray', '3 3'); guide.setAttribute('pointer-events', 'none');
        svg.appendChild(guide);
      }
      guide.setAttribute('x1', gx); guide.setAttribute('x2', gx); guide.setAttribute('y1', T); guide.setAttribute('y2', vb.height - B);
      if (!tip) { tip = document.createElement('div'); tip.className = 'spxrv-tip'; document.body.appendChild(tip); }
      tip.innerHTML = '<b>Week ending ' + row[0] + '</b>' +
        '<br><span style="color:' + C_WK + '">&#9632;</span> Weekly: ' + k(row[1]) +
        '<br><span style="color:' + C_AVG + '">&#9632;</span> 4-week avg: ' + k(row[2]);
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('joblessBody');
    if (!body) return;
    if (rowsAll.length < 2) { body.innerHTML = '<div class="msr-loading">Jobless claims data unavailable.</div>'; return; }
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">Jobless claims</span><span class="yc-dt">week ending ' + rowsAll[rowsAll.length - 1][0] + '</span></div>' +
      tableHtml() + chartHtml(600, 230, 11, 'yc-click') + legendHtml();
    attachHover(body.querySelector('svg'), 600);
  }

  function closeModal() { var m = document.getElementById('joblessModal'); if (m) m.remove(); }
  function openModal() {
    if (rowsAll.length < 2) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'joblessModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">Jobless claims</h2>' +
      '<p style="margin:0;">' + rowsAll[0][0] + ' to ' + rowsAll[rowsAll.length - 1][0] + ' &middot; weekly initial claims for unemployment benefits</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + tableHtml() + chartHtml(1100, 420, 13, '') + legendHtml() + descHtml() + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
  }

  async function load() {
    var body = document.getElementById('joblessBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/jobless-claims' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var j = await res.json();
      rowsAll = j.rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">Jobless claims panel unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('joblessBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
