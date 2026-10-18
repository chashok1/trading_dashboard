/* Momentum panel, 2026-10-17 (user-directed): is the momentum trade unwinding? Cumulative return since the first day of the window for MTUM (the
 * momentum fund, drawn in the text colour = black on the light theme), SPX, RSP (equal-weight S&P 500) and QQQ, plus SMH (semiconductors) and SPHB
 * (high beta) as soon as the endpoint returns them (it only does once they have daily prices on 80% of the days). MTUM peak is marked.
 * Green background = up, red = down. Dashboard left column, below the Credit panel. Click the chart for a large popup.
 * Data: GET /api/cockpit/momentum -> {syms, rows: [date, price per sym...]} (hist_td closes). */
(function () {
  'use strict';
  var L = 34, R = 10, T = 8, B = 18;
  var SYMS = [], rowsAll = [];
  var NAME = { MTUM: 'MTUM (momentum)', SPX: 'SPX (S&P 500)', RSP: 'RSP (equal-weight S&P)', QQQ: 'QQQ (Nasdaq 100)', SMH: 'SMH (semiconductors)', SPHB: 'SPHB (high beta)' };
  var COL = { MTUM: 'currentColor', SPX: '#1668c4', RSP: '#2a9d3a', QQQ: '#e07a00', SMH: '#7a3fb5', SPHB: '#0f9aa8' };
  var ST = 'mo';
  // The chart opens with just MTUM and SPX; the other ETFs are ticked on in the table.
  SeriesToggle.defaults(ST, { RSP: 1, QQQ: 1, SMH: 1, SPHB: 1 });

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function pc(v) { return v == null ? '--' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }

  // Cumulative return % from each symbol's first price: C[i] = [date, pct per symbol...]
  function cumulative() {
    var base = SYMS.map(function (s, k) {
      for (var i = 0; i < rowsAll.length; i++) if (rowsAll[i][k + 1] != null) return rowsAll[i][k + 1];
      return null;
    });
    return rowsAll.map(function (r) {
      return [r[0]].concat(SYMS.map(function (s, k) { return r[k + 1] == null || !base[k] ? null : (r[k + 1] / base[k] - 1) * 100; }));
    });
  }

  function tableHtml(C, full) {
    var j = C.length - 1;
    var ret = function (k, off) {
      var a = C[j - off] && C[j - off][k + 1], b = C[j][k + 1];
      return a == null || b == null ? null : ((1 + b / 100) / (1 + a / 100) - 1) * 100;
    };
    var fromPeak = function (k) {
      var pk = -1e9, last = null;
      C.forEach(function (r) { var v = r[k + 1]; if (v != null) { pk = Math.max(pk, 100 + v); last = 100 + v; } });
      return last == null ? null : (last / pk - 1) * 100;
    };
    var cell = function (v) {
      if (v == null) return '<td>--</td>';
      var r = Math.round(v * 10) / 10;
      return '<td class="' + (r > 0 ? 'yc-g' : r < 0 ? 'yc-r' : '') + '">' + pc(r) + '</td>';
    };
    var head = '<tr><th>ETF</th><th>Since ' + C[0][0].slice(5) + '</th><th>Day</th><th>Week</th><th>Month</th><th>From peak</th></tr>';
    var body = SYMS.map(function (sym, k) {
      var nm = full ? (NAME[sym] || sym) : sym;
      return '<tr title="' + (NAME[sym] || sym) + '"><td>' + SeriesToggle.item(ST, sym, '<i class="mo-sw" style="background:' + (COL[sym] || 'currentColor') + '"></i>' + nm) + '</td>' +
        cell(C[j][k + 1]) + cell(ret(k, 1)) + cell(ret(k, 5)) + cell(ret(k, 21)) + cell(fromPeak(k)) + '</tr>';
    }).join('');
    return '<table class="yc-tbl">' + head + body + '</table>';
  }

  function chartHtml(C, W, H, fs, cls) {
    var n = C.length;
    if (n < 2) return '<div class="msr-loading">No momentum data yet.</div>';
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var hid = SeriesToggle.hidden(ST);
    var all = [];
    C.forEach(function (r) { for (var k = 1; k < r.length; k++) if (r[k] != null && !hid[SYMS[k - 1]]) all.push(r[k]); });
    if (!all.length) all = [0];
    var lo = Math.floor(Math.min.apply(null, all.concat([0])) / 5) * 5 - 2, hi = Math.ceil(Math.max.apply(null, all) / 5) * 5 + 2;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var s = '';
    for (var v = Math.ceil(lo / 5) * 5; v <= hi; v += 5) {
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + (v === 0 ? 'currentColor' : 'var(--border,#e5e5e2)') + '" ' + (v === 0 ? 'opacity=".4"' : '') + '/>' +
        '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v + '%</text>';
    }
    var path = function (k, color, w) {
      var p = '', on = false;
      C.forEach(function (r, i) {
        if (r[k + 1] == null) { on = false; return; }
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[k + 1]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    SYMS.forEach(function (sym, k) { if (sym !== 'MTUM' && !hid[sym]) s += path(k, COL[sym] || 'currentColor', 1.4); });
    var km = SYMS.indexOf('MTUM');
    if (km >= 0 && !hid.MTUM) {
      s += path(km, COL.MTUM, 2.2);
      var pi = 0;
      C.forEach(function (r, i) { if (r[km + 1] != null && (C[pi][km + 1] == null || r[km + 1] > C[pi][km + 1])) pi = i; });
      if (C[pi][km + 1] != null) {
        s += '<circle cx="' + x(pi) + '" cy="' + y(C[pi][km + 1]) + '" r="3.5" fill="none" stroke="currentColor" stroke-width="1.4"/>' +
          '<text x="' + (x(pi) + 7) + '" y="' + (y(C[pi][km + 1]) - 5) + '" font-size="' + fs + '" fill="currentColor">MTUM peak ' + C[pi][0].slice(5) + '</text>';
      }
    }
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], pm = '';
    C.forEach(function (r, i) {
      var m = r[0].slice(0, 7);
      if (m !== pm) { pm = m; s += '<text x="' + x(i) + '" y="' + (H - 4) + '" font-size="' + fs + '" fill="currentColor">' + MN[+m.slice(5) - 1] + '</text>'; }
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="yc-svg ' + cls + '" role="img" aria-label="Cumulative return of momentum, market and growth ETFs">' + s + '</svg>';
  }

  function noteHtml() {
    var have = SYMS.indexOf('SMH') >= 0 && SYMS.indexOf('SPHB') >= 0;
    return '<div class="cr-desc"><p>MTUM is a broad large-cap momentum fund, so it shows the timing of the momentum trade (peak and decline) but is milder than a leveraged high-beta basket. RSP is the equal-weight S&amp;P 500: a gap between RSP and SPX means a narrow market.' +
      (have ? '' : ' SMH (semiconductors) and SPHB (high beta) appear here once they have daily prices.') + '</p></div>';
  }

  function attachHover(svg, C, W) {
    if (!svg) return;
    var n = C.length, tip = null, guide = null, NS = 'http://www.w3.org/2000/svg';
    function hide() { if (tip) { tip.remove(); tip = null; } if (guide) { guide.remove(); guide = null; } }
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('mousemove', function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      var row = C[i], gx = L + (W - L - R) * i / (n - 1), vb = svg.viewBox.baseVal;
      if (!guide) {
        guide = document.createElementNS(NS, 'line');
        guide.setAttribute('stroke', '#888'); guide.setAttribute('stroke-dasharray', '3 3'); guide.setAttribute('pointer-events', 'none');
        svg.appendChild(guide);
      }
      guide.setAttribute('x1', gx); guide.setAttribute('x2', gx); guide.setAttribute('y1', T); guide.setAttribute('y2', vb.height - B);
      if (!tip) { tip = document.createElement('div'); tip.className = 'spxrv-tip'; document.body.appendChild(tip); }
      var hid = SeriesToggle.hidden(ST);
      tip.innerHTML = '<b>' + row[0] + '</b>' + SYMS.map(function (sym, k) {
        if (hid[sym]) return '';
        return '<br>' + (sym === 'MTUM' ? '' : '<span style="color:' + (COL[sym] || '#888') + '">&#9632;</span> ') + sym + ': ' + pc(row[k + 1]);
      }).join('');
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function render() {
    var body = document.getElementById('momentumBody');
    if (!body) return;
    if (!rowsAll.length || !SYMS.length) { body.innerHTML = '<div class="msr-loading">Momentum data unavailable.</div>'; return; }
    var C = cumulative();
    body.innerHTML = '<div class="yc-head"><span class="yc-ttl">Momentum</span><span class="yc-dt">as of ' + C[C.length - 1][0] + '</span></div>' +
      tableHtml(C, false) + chartHtml(C, 600, 230, 11, 'yc-click') + noteHtml();
    attachHover(body.querySelector('svg'), C, 600);
  }

  function closeModal() { var m = document.getElementById('momentumModal'); if (m) m.remove(); }
  function modalBodyHtml(C) { return tableHtml(C, true) + chartHtml(C, 1100, 420, 13, '') + noteHtml(); }
  function openModal() {
    if (!rowsAll.length) return;
    closeModal();
    var C = cumulative();
    var m = document.createElement('div');
    m.id = 'momentumModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">Momentum vs the market</h2>' +
      '<p style="margin:0;">' + C[0][0] + ' to ' + C[C.length - 1][0] + ' &middot; cumulative return from the first price</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + modalBodyHtml(C) + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), C, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
    SeriesToggle.bind(m, ST, function () { return SYMS; }, refresh);
  }
  // A toggle redraws the panel and, if the popup is open, its body too.
  function refresh() {
    render();
    var m = document.getElementById('momentumModal');
    if (m) { var C = cumulative(); m.querySelector('.modal-body').innerHTML = modalBodyHtml(C); attachHover(m.querySelector('svg'), C, 1100); }
  }

  async function load() {
    var body = document.getElementById('momentumBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/momentum' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var j = await res.json();
      SYMS = j.syms || []; rowsAll = j.rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">Momentum panel unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('momentumBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.yc-svg')) openModal(); });
    SeriesToggle.bind(host, ST, function () { return SYMS; }, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1100);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
