/* Outlook changes panel -- top of the dashboard's centre column (2026-10-15, user-directed).
   Macro Rail symbols whose Risk Range outlook changed in the last 7 days; Country ETFs excluded.
   Reads GET /api/cockpit/outlook-changes. Display only. */
(function () {
  'use strict';
  var SC = ['Bearish', 'Neutral', 'Bullish'];
  var rank = function (o) { return SC.indexOf(o); };
  var cls = function (o) { return /bull/i.test(o) ? 'bull' : /bear/i.test(o) ? 'bear' : 'neu'; };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var st = { data: null, panel: 'All', dir: 'All', sort: 'size', open: true };
  try { st.open = localStorage.getItem('ocOpen') !== '0'; } catch (e) {}

  function ago(s, asOf) {
    if (!s) return '';
    var n = Math.round((new Date(asOf) - new Date(s)) / 864e5);
    return n <= 0 ? 'today' : n + 'd ago';
  }
  function meter(a, b) {
    var lo = Math.min(a, b), hi = Math.max(a, b);
    return '<div class="oc-meter">' + SC.map(function (_, i) {
      return '<i class="' + (i === b ? 't' : (i >= lo && i <= hi ? 'p' : '')) + '"></i>';
    }).join('') + '</div>';
  }
  // Compact chip: "XLP  Bearish -> Bullish" (green = upgrade, red = downgrade); details in the tooltip.
  function chip(d, asOf) {
    var up = d.delta > 0;
    var tip = [d.symbol + (d.desc ? ' - ' + d.desc : ''), d.panel,
      d.from + ' -> ' + d.to + ' (' + (up ? '+' : '') + d.delta + ' step' + (Math.abs(d.delta) === 1 ? '' : 's') + ')',
      'Changed ' + (ago(d.changed_on, asOf) || 'this week')].join(String.fromCharCode(10));
    return '<span class="oc-chip2 ' + cls(d.to) + '" title="' + esc(tip) + '"><b>' + esc(d.symbol) + '</b>' +
      '<span class="oc-ft"><span class="oc-w ' + cls(d.from) + '">' + esc(d.from) + '</span> &rarr; <span class="oc-w ' + cls(d.to) + '">' + esc(d.to) + '</span></span>' +
      (d.changed_on ? '<span class="oc-dt">' + d.changed_on.slice(5, 7) + '/' + d.changed_on.slice(8, 10) + '</span>' : '') + '</span>';
  }

  var ORDER = ['Major Markets', 'Sectors', 'Tech & ETFs', 'Currency', 'USD, Rates & Duration', 'Credit', 'Precious Metals',
               'Industrial & Ag', 'Energy', 'Crypto', 'Volatility', 'Cannabis'];

  function render() {
    var el = document.getElementById('outlookChangesCard');
    var D = st.data;
    if (!el || !D) return;
    var all = D.changes.map(function (c) { var o = Object.assign({}, c); o.a = rank(c.from); o.b = rank(c.to); o.delta = o.b - o.a; return o; });
    var panels = Array.from(new Set(all.map(function (d) { return d.panel; })))
      .sort(function (x, y) { var a = ORDER.indexOf(x), b = ORDER.indexOf(y); return (a < 0 ? 99 : a) - (b < 0 ? 99 : b); });
    if (st.panel !== 'All' && panels.indexOf(st.panel) < 0) st.panel = 'All';
    var byMove = function (x, y) { return Math.abs(y.delta) - Math.abs(x.delta) || x.symbol.localeCompare(y.symbol); };
    var groups = panels.filter(function (p) { return st.panel === 'All' || st.panel === p; }).map(function (p) {
      var L = all.filter(function (d) { return d.panel === p; }).sort(byMove);
      return '<span class="oc-grp"><span class="oc-gl">' + esc(p) + '</span>' + L.map(function (d) { return chip(d, D.as_of); }).join('') + '</span>';
    }).join('');
    var arrow = '<button class="oc-tog" id="ocToggle" type="button" title="Collapse/expand">' + (st.open ? '&#9662;' : '&#9656;') + '</button>';
    el.innerHTML = '<div class="oc-body">' + arrow +
      (st.open ? groups : '<span class="oc-gl">Outlook changes &middot; ' + all.length + '</span>') + '</div>';
    el.querySelector('#ocToggle').onclick = function () {
      st.open = !st.open; try { localStorage.setItem('ocOpen', st.open ? '1' : '0'); } catch (e) {} render();
    };
    el.hidden = false;
  }

  async function load() {
    var el = document.getElementById('outlookChangesCard');
    if (!el) return;
    try {
      var d = (window._dateQS ? window._dateQS() : '') || '';
      var res = await fetch('/api/cockpit/outlook-changes' + d);
      if (!res.ok) throw new Error(res.status);
      st.data = await res.json();
      if (!st.data.changes || !st.data.changes.length) { el.hidden = true; return; }
      render();
    } catch (e) { el.hidden = true; }
  }
  window.loadOutlookChanges = load;
  document.addEventListener('DOMContentLoaded', load);
})();
