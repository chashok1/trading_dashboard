/* IV vs RV panel, 2026-10-17 (user-directed; deck page 28): are options pricing more or less movement than each symbol has actually delivered?
 * Premium = implied vol / actual vol - 1 (5-day average), compared with the symbol's own normal (median since April): Rich if more than 15%
 * above it (red background), Cheap if more than 15% below (green), else Fair. Dashboard middle column, last panel. Collapse arrow in the header.
 * Data: GET /api/cockpit/iv-rv -> rows [{g, s, name, iv, hv, prem, w1, m1, med, ivp, noisy, date}] (hist_td, TOS exports). */
(function () {
  'use strict';
  var KEY = 'ivRvCollapsed', VIEW_KEY = 'ivRvView';
  var rows = [], mode = 'group';
  try { var sv = localStorage.getItem(VIEW_KEY); if (sv === 'rich' || sv === 'cheap' || sv === 'group') mode = sv; } catch (e) {}

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }
  function pct(v) { return v == null ? '--' : (((v - 1) * 100) > 0 ? '+' : '') + Math.round((v - 1) * 100) + '%'; }

  function prepare() {
    rows.forEach(function (o) {
      o.rel = o.prem / o.med;
      o.band = o.rel > 1.15 ? 'Rich' : o.rel < 0.85 ? 'Cheap' : 'Fair';
    });
  }

  function rowHtml(o) {
    var arrow = o.w1 == null ? '' : (o.prem > o.w1 + 0.02 ? ' <span class="ivrv-up">&#9650;</span>' : o.prem < o.w1 - 0.02 ? ' <span class="ivrv-dn">&#9660;</span>' : '');
    var gap = Math.round((o.rel - 1) * 100);
    return '<tr><td><b>' + o.s + '</b></td><td>' + o.name + '</td><td>' + o.iv.toFixed(1) + '%</td><td>' + o.hv.toFixed(1) + '%' +
      (o.noisy ? ' <span class="ivrv-nz" title="Actual volatility is 10% or lower, so TOS rounding makes the premium rough">&#8776;</span>' : '') + '</td>' +
      '<td><b>' + pct(o.prem) + '</b>' + arrow + '</td><td>' + pct(o.med) + '</td><td>' + (gap >= 0 ? '+' : '') + gap + '%</td>' +
      '<td class="ivrv-' + o.band.toLowerCase() + '">' + o.band + '</td><td>' + pct(o.w1) + '</td><td>' + pct(o.m1) + '</td><td>' + (o.ivp == null ? '--' : o.ivp) + '</td></tr>';
  }

  var HEAD = '<tr><th>Symbol</th><th>Name</th><th>Implied vol</th><th>Actual vol</th>' +
    '<th title="Options volatility compared with actual volatility, 5-day average">Premium</th>' +
    '<th title="This symbol\'s own median premium since April">Its normal</th>' +
    '<th title="Today\'s premium compared with its own normal">vs normal</th><th>Band</th><th>1 week ago</th><th>1 month ago</th>' +
    '<th title="Where implied volatility sits in its own range (from TOS)">IV rank</th></tr>';

  function render() {
    var body = document.getElementById('ivRvBody');
    if (!body) return;
    if (!rows.length) { body.innerHTML = '<div class="msr-loading">IV vs RV data unavailable.</div>'; return; }
    prepare();
    var h = HEAD;
    if (mode === 'group') {
      var g = '';
      rows.forEach(function (o) {
        if (o.g !== g) { g = o.g; h += '<tr class="ivrv-grp"><td colspan="11">' + g + '</td></tr>'; }
        h += rowHtml(o);
      });
    } else {
      rows.slice().sort(function (a, b) { return mode === 'rich' ? b.rel - a.rel : a.rel - b.rel; }).forEach(function (o) { h += rowHtml(o); });
    }
    var cnt = function (b) { return rows.filter(function (o) { return o.band === b; }).length; };
    var btn = function (id, label) { return '<button type="button" class="ivrv-btn' + (mode === id ? ' on' : '') + '" data-ivrv="' + id + '">' + label + '</button>'; };
    body.innerHTML = '<div class="ivrv-bar"><span class="ivrv-sum"><b class="ivrv-up">' + cnt('Rich') + '</b> rich &middot; <b>' + cnt('Fair') + '</b> fair &middot; <b class="ivrv-dn">' + cnt('Cheap') +
      '</b> cheap vs their own normal &middot; as of ' + rows[0].date + '</span>' + btn('group', 'By group') + btn('rich', 'Richest first') + btn('cheap', 'Cheapest first') + '</div>' +
      '<div class="ivrv-tblwrap"><table class="ivrv-tbl">' + h + '</table></div>' +
      '<div class="cr-desc"><p>Premium = implied volatility divided by actual volatility, minus 1 (+100% means options are priced at twice the actual movement), averaged over 5 days. Its normal = the symbol&#39;s own median premium since April. Rich: more than 15% above its normal. Cheap: more than 15% below. Arrows compare with a week ago. The &#8776; sign marks symbols whose actual volatility is 10% or lower, where TOS rounding makes the premium rough.</p></div>';
  }

  async function load() {
    var body = document.getElementById('ivRvBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/iv-rv' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      rows = (await res.json()).rows || [];
      render();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">IV vs RV panel unavailable.</div>';
    }
  }

  function applyCollapse(c) {
    var body = document.getElementById('ivRvBody'), btn = document.getElementById('ivRvToggle');
    if (body) body.style.display = c ? 'none' : '';
    if (btn) {
      btn.innerHTML = c ? '&#9652;' : '&#9662;';
      btn.setAttribute('aria-label', (c ? 'Expand' : 'Collapse') + ' IV vs RV panel');
    }
  }

  function init() {
    var c0 = false;
    try { c0 = localStorage.getItem(KEY) === '1'; } catch (e) {}
    applyCollapse(c0);
    var btn = document.getElementById('ivRvToggle');
    if (btn) btn.addEventListener('click', function () {
      var c = (document.getElementById('ivRvBody') || {}).style.display !== 'none';
      try { localStorage.setItem(KEY, c ? '1' : '0'); } catch (e) {}
      applyCollapse(c);
    });
    var host = document.getElementById('ivRvBody');
    if (host) host.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('[data-ivrv]') : null;
      if (!b) return;
      mode = b.getAttribute('data-ivrv');
      try { localStorage.setItem(VIEW_KEY, mode); } catch (e) {}
      render();
    });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
