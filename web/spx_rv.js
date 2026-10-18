/* 2026-10-17 -- SPX realized volatility panel (1 month vs 3 month + SPX daily % change bars), 6 months.
 * Right column of the Dashboard (#spxRvBand), between Quad Outlook and E.IND.
 * Data: GET /api/cockpit/spx-realized-vol -> rows [date, rv21, rv63, pct]. */
(function () {
  'use strict';
  var L = 28, R = 30, T = 8, B = 18;
  var lastRows = [];
  var ST = 'rv', KEYS = ['m1', 'm3', 'bars'];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  // Hover: vertical guide line + floating tooltip with date, 1M, 3M and SPX daily %.
  function attachHover(svg, D, W) {
    if (!svg) return;
    var n = D.length, tip = null, guide = null;
    var NS = 'http://www.w3.org/2000/svg';
    var f = function (v) { return v == null ? '--' : v.toFixed(1) + '%'; };
    function hide() {
      if (tip) { tip.remove(); tip = null; }
      if (guide) { guide.remove(); guide = null; }
    }
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('mousemove', function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      var row = D[i], gx = L + (W - L - R) * i / (n - 1);
      var vb = svg.viewBox.baseVal;
      if (!guide) {
        guide = document.createElementNS(NS, 'line');
        guide.setAttribute('stroke', '#888'); guide.setAttribute('stroke-dasharray', '3 3');
        guide.setAttribute('pointer-events', 'none');
        svg.appendChild(guide);
      }
      guide.setAttribute('x1', gx); guide.setAttribute('x2', gx);
      guide.setAttribute('y1', T); guide.setAttribute('y2', vb.height - B);
      if (!tip) {
        tip = document.createElement('div');
        tip.className = 'spxrv-tip';
        document.body.appendChild(tip);
      }
      var hid = SeriesToggle.hidden(ST);
      tip.innerHTML = '<b>' + row[0] + '</b>' +
        (hid.m1 ? '' : '<br><span style="color:#2b2bf0">&#9632;</span> 1-month: ' + f(row[1])) +
        (hid.m3 ? '' : '<br><span style="color:#ff5a14">&#9632;</span> 3-month: ' + f(row[2])) +
        (hid.bars ? '' : '<br><span style="color:#9a9a9a">&#9632;</span> SPX day: ' + (row[3] == null ? '--' : (row[3] > 0 ? '+' : '') + row[3].toFixed(2) + '%'));
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  function draw(D, W, H, fs) {
    var n = D.length;
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var hid = SeriesToggle.hidden(ST), on = function (k) { return !hid[k]; };
    var showL = on('m1') || on('m3'), showR = on('bars');
    var vals = [], all = [];
    D.forEach(function (r) {
      if (r[1] != null) all.push(r[1]);
      if (r[2] != null) all.push(r[2]);
      if (on('m1') && r[1] != null) vals.push(r[1]);
      if (on('m3') && r[2] != null) vals.push(r[2]);
    });
    if (!vals.length) vals = all;   // both lines hidden: scale from the full range so the bars axis still lines up
    if (n < 2 || !vals.length) return '<div class="msr-loading">No SPX volatility history yet.</div>';
    var lo = Math.floor(Math.min.apply(null, vals) / 5) * 5 - 5, hi = Math.ceil(Math.max.apply(null, vals) / 5) * 5 + 5;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var pc = D.map(function (r) { return r[3]; }).filter(function (v) { return v != null; });
    var ma = Math.max.apply(null, pc.map(Math.abs).concat([0.5]));
    var rlo = -Math.ceil(ma * 1.8), rhi = Math.ceil(ma * 2.6);
    var ry = function (v) { return T + (H - T - B) * (1 - (v - rlo) / (rhi - rlo)); };
    var s = '';
    if (showL) {
      for (var v = Math.ceil(lo / 10) * 10; v <= hi; v += 10) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v + '</text>';
      }
    }
    if (showR) {
      for (var rv = Math.ceil(rlo / 2) * 2; rv <= rhi; rv += 2) {
        if (!showL) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + ry(rv) + '" y2="' + ry(rv) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (ry(rv) + 4) + '" font-size="' + fs + '" fill="#7a1fa2">' + rv + '</text>';
      }
    }
    var bw = Math.max(1, (W - L - R) / n * 0.7);
    D.forEach(function (r, i) {
      if (!showR || r[3] == null) return;
      var y0 = ry(0), y1 = ry(r[3]);
      s += '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + Math.min(y0, y1).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + Math.max(0.5, Math.abs(y1 - y0)).toFixed(1) + '" fill="#9a9a9a" opacity="0.7"/>';
    });
    var line = function (k, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) return;
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    if (on('m1')) s += line(1, '#2b2bf0', 1.5);
    if (on('m3')) s += line(2, '#ff5a14', 2.5);
    for (var t = 0; t < 4; t++) {
      var i = Math.round((n - 1) * t / 3), pp = D[i][0].split('-');
      s += '<text x="' + x(i) + '" y="' + (H - 4) + '" text-anchor="' + (t === 0 ? 'start' : t === 3 ? 'end' : 'middle') +
        '" font-size="' + fs + '" fill="currentColor">' + pp[1] + '/' + pp[2] + '/' + pp[0].slice(2) + '</text>';
    }
    var last = D[n - 1];
    var f = function (v) { return v == null ? '--' : v.toFixed(1) + '%'; };
    var head = '<div class="spxrv-head"><span class="spxrv-ttl">SPX Realized Vol</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'm1', '<i style="background:#2b2bf0"></i>1M ' + f(last[1])) + '</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'm3', '<i style="background:#ff5a14"></i>3M ' + f(last[2])) + '</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'bars', '<i style="background:#9a9a9a"></i>SPX daily %') + '</span></div>';
    return head + '<svg viewBox="0 0 ' + W + ' ' + H + '" class="spxrv-svg' + (fs > 11 ? '' : ' spxrv-click') + '" role="img" aria-label="SPX 1-month vs 3-month realized volatility">' + s + '</svg>';
  }

  function renderPanel() {
    var body = document.getElementById('spxRvBody');
    if (!body) return;
    body.innerHTML = draw(lastRows, 600, 250, 11);
    attachHover(body.querySelector('svg'), lastRows, 600);
  }

  async function load() {
    var body = document.getElementById('spxRvBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/spx-realized-vol' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      lastRows = (await res.json()).rows || [];
      renderPanel();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">SPX volatility unavailable.</div>';
    }
  }

  // Click the small chart -> large popup (same overlay/dialog classes as the Cumulative P&L expand modal).
  function closeModal() { var m = document.getElementById('spxRvModal'); if (m) m.remove(); }
  function openModal() {
    if (!lastRows.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'spxRvModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">SPX Realized Volatility</h2>' +
      '<p style="margin:0;">1 month vs 3 month, ' + lastRows[0][0] + ' to ' + lastRows[lastRows.length - 1][0] + '</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + draw(lastRows, 1100, 440, 13) + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), lastRows, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
    SeriesToggle.bind(m, ST, KEYS, refresh);
  }
  // A toggle redraws the panel and, if the popup is open, its body too.
  function refresh() {
    renderPanel();
    var m = document.getElementById('spxRvModal');
    if (m) { m.querySelector('.modal-body').innerHTML = draw(lastRows, 1100, 440, 13); attachHover(m.querySelector('svg'), lastRows, 1100); }
  }

  function init() {
    var host = document.getElementById('spxRvBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.spxrv-svg')) openModal(); });
    SeriesToggle.bind(host, ST, KEYS, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 700);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
