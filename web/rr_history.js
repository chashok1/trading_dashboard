/* Risk range history chart (2026-10-22, user-directed): click a risk range bar on the Macro Rail -> a popup chart of how that symbol's
 * risk range (low / high) and price have moved. On demand only: nothing is fetched until a bar is clicked.
 * Reads GET /api/cockpit/rr-history. Display only. */
(function () {
  'use strict';
  var chart = null, cur = { sym: null, label: '', days: 90 };
  var WINDOWS = [[30, '1M'], [90, '3M'], [180, '6M'], [0, 'All']];

  function ensure() {
    var el = document.getElementById('rrHistModal');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'rrHistModal';
    el.hidden = true;
    el.innerHTML = '<div class="rrh-box"><div class="rrh-hdr"><b id="rrhTitle"></b><span id="rrhNow"></span><span class="rrh-btns" id="rrhBtns"></span>' +
      '<button type="button" id="rrhClose" title="Close (Esc)">&times;</button></div>' +
      '<div class="rrh-body"><canvas id="rrhCanvas"></canvas><div id="rrhMsg"></div></div></div>';
    document.body.appendChild(el);
    el.addEventListener('mousedown', function (e) { if (e.target === el) close(); });
    document.getElementById('rrhClose').addEventListener('click', close);
    document.getElementById('rrhBtns').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-days]');
      if (b) { cur.days = Number(b.getAttribute('data-days')); load(); }
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    return el;
  }

  function close() {
    var el = document.getElementById('rrHistModal');
    if (el) el.hidden = true;
    if (chart) { chart.destroy(); chart = null; }
  }

  function buttons() {
    document.getElementById('rrhBtns').innerHTML = WINDOWS.map(function (w) {
      return '<button type="button" data-days="' + w[0] + '"' + (w[0] === cur.days ? ' class="on"' : '') + '>' + w[1] + '</button>';
    }).join('');
  }

  async function load() {
    buttons();
    var msg = document.getElementById('rrhMsg');
    msg.textContent = 'Loading...';
    try {
      var res = await fetch('/api/cockpit/rr-history?symbol=' + encodeURIComponent(cur.sym) + '&days=' + cur.days);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      draw((await res.json()).points || []);
    } catch (e) {
      msg.textContent = 'Could not load the risk range history.';
    }
  }

  function draw(pts) {
    var msg = document.getElementById('rrhMsg');
    if (chart) { chart.destroy(); chart = null; }
    if (!pts.length || !window.Chart) { msg.textContent = pts.length ? 'Chart library not loaded.' : 'No risk range history stored for this symbol.'; return; }
    msg.textContent = '';
    var last = pts[pts.length - 1];
    var pos = (last.lrr != null && last.trr != null && last.price != null && last.trr > last.lrr)
      ? Math.round((last.price - last.lrr) / (last.trr - last.lrr) * 100) : null;
    document.getElementById('rrhNow').textContent = ' ' + last.date.slice(5) + '  low ' + (last.lrr == null ? '--' : last.lrr) +
      '  high ' + (last.trr == null ? '--' : last.trr) + (pos == null ? '' : '  price at ' + pos + '% of range');
    var labels = pts.map(function (p) { return p.date.slice(5); });
    chart = new window.Chart(document.getElementById('rrhCanvas'), {
      type: 'line',
      data: { labels: labels, datasets: [
        { label: 'Range low', data: pts.map(function (p) { return p.lrr; }), borderColor: '#16a34a', borderWidth: 1.5, pointRadius: 0, cubicInterpolationMode: 'monotone' },
        { label: 'Range high', data: pts.map(function (p) { return p.trr; }), borderColor: '#dc2626', borderWidth: 1.5, pointRadius: 0, cubicInterpolationMode: 'monotone',
          fill: '-1', backgroundColor: 'rgba(148,163,184,0.18)' },
        { label: 'Price', data: pts.map(function (p) { return p.price; }), borderColor: '#111827', borderWidth: 2, pointRadius: 0, cubicInterpolationMode: 'monotone' },
        { label: 'Trade line', data: pts.map(function (p) { return p.trade; }), borderColor: '#2563eb', borderWidth: 1.5, borderDash: [5, 3], pointRadius: 0, cubicInterpolationMode: 'monotone' },
        { label: 'Trend line', data: pts.map(function (p) { return p.trend; }), borderColor: '#9333ea', borderWidth: 1.5, borderDash: [2, 2], pointRadius: 0, cubicInterpolationMode: 'monotone' }
      ] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, spanGaps: true,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } },
                   tooltip: { itemSort: function (a, b) { return b.datasetIndex - a.datasetIndex; } } },
        scales: { x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } }, y: { ticks: { font: { size: 10 } } } } }
    });
  }

  document.addEventListener('click', function (e) {
    var bar = e.target.closest ? e.target.closest('.msr-rb-wrap') : null;
    if (!bar) return;
    var row = bar.closest('[data-sym]');
    if (!row) return;
    cur.sym = row.getAttribute('data-sym');
    var nm = row.querySelector('.msr-name-tick');
    cur.label = (nm ? nm.textContent : cur.sym).trim();
    cur.days = 90;
    ensure().hidden = false;
    document.getElementById('rrhTitle').textContent = cur.label + (cur.label !== cur.sym ? ' (' + cur.sym + ')' : '') + ' -- risk range';
    load();
  });
})();
