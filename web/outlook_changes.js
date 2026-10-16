/* Outlook changes panel -- top of the dashboard's centre column (2026-10-15, user-directed).
   Macro Rail symbols whose Risk Range outlook changed in the last 7 days; Country ETFs excluded.
   Reads GET /api/cockpit/outlook-changes. Display only. */
(function () {
  'use strict';
  var SC = ['Bearish', 'Neutral', 'Bullish'];
  var rank = function (o) { return SC.indexOf(o); };
  var cls = function (o) { return /bull/i.test(o) ? 'bull' : /bear/i.test(o) ? 'bear' : 'neu'; };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var st = { data: null, open: false };

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

  // ---- Macro Rail row markers (2026-10-16): "from -> to" in a reserved slot on each rail row. ----
  var SHAPE = { Bullish: ['bull', '▲'], Bearish: ['bear', '▼'], Neutral: ['neu', '■'] };
  var only = false;
  try { only = localStorage.getItem('ocOnly') === '1'; } catch (e) {}
  function shape(o) { var h = SHAPE[o] || SHAPE.Neutral; return '<i class="oc-s ' + h[0] + '">' + h[1] + '</i>'; }
  // Slot HTML for one rail row: always the fixed-width slot (empty when nothing changed) so columns stay aligned.
  window.ocMarker = function (sym) {
    var d = window._ocMap && window._ocMap[sym];
    if (!d) return '<span class="oc-slot"></span>';
    var n = rank(d.to) - rank(d.from);
    var tip = [sym + (d.desc ? ' - ' + d.desc : ''), d.from + ' -> ' + d.to + ' (' + (n > 0 ? '+' : '') + n + ')',
      d.changed_on ? 'Changed ' + d.changed_on : 'Changed this week'].join(String.fromCharCode(10));
    return '<span class="oc-slot has" title="' + esc(tip) + '">' + shape(d.from) + '<i class="oc-ar">&rarr;</i>' + shape(d.to) + '</span>';
  };
  window.ocHas = function (sym) { return !!(window._ocMap && window._ocMap[sym]); };
  function applyOnly() {
    document.body.classList.toggle('oc-only', only);
    var b = document.getElementById('ocFilter');
    if (b) b.classList.toggle('on', only);
  }
  function addChip(n) {
    var hdr = document.querySelector('.msr-section-hdr');
    if (!hdr) return;
    var b = document.getElementById('ocFilter');
    if (!b) {
      b = document.createElement('button');
      b.id = 'ocFilter'; b.type = 'button'; b.className = 'oc-filter';
      b.title = 'Show only Macro Rail rows whose outlook changed in the last 7 days';
      b.onclick = function () { only = !only; try { localStorage.setItem('ocOnly', only ? '1' : '0'); } catch (e) {} applyOnly(); };
      var t = document.getElementById('macroRailToggle');
      if (t && t.parentNode === hdr) hdr.insertBefore(b, t); else hdr.appendChild(b);
    }
    b.textContent = 'Δ ' + n;
    b.hidden = !n;
    applyOnly();
  }

  // One line of chips (newest change first, no grouping); the rest float in an overlay under it.
  var _ro = false;
  function render() {
    var el = document.getElementById('outlookChangesCard');
    var D = st.data;
    if (!el || !D) return;
    var all = D.changes.map(function (c) { var o = Object.assign({}, c); o.a = rank(c.from); o.b = rank(c.to); o.delta = o.b - o.a; return o; });
    all.sort(function (x, y) {
      return String(y.changed_on || '').localeCompare(String(x.changed_on || '')) ||
        Math.abs(y.delta) - Math.abs(x.delta) || x.symbol.localeCompare(y.symbol);
    });
    var parts = all.map(function (d) { return chip(d, D.as_of); });
    var chips = parts.join('');
    el.innerHTML = '<div class="oc-body"><span class="oc-line" id="ocLine">' + chips + '</span>' +
      '<button class="oc-more" id="ocMore" type="button" title="Show all outlook changes" hidden></button></div>' +
      '<div class="oc-pop" id="ocPop" hidden></div>';
    el.hidden = false;
    var line = el.querySelector('#ocLine'), more = el.querySelector('#ocMore'), pop = el.querySelector('#ocPop');
    function setOpen(v) { st.open = v; pop.hidden = !v; more.classList.toggle('on', v); }
    // Count the chips that do not fit on the one line.
    function fit() {
      var lr = line.getBoundingClientRect().right, hidden = 0;
      Array.prototype.forEach.call(line.children, function (c) { if (c.getBoundingClientRect().right > lr + 0.5) hidden++; });
      pop.innerHTML = parts.slice(parts.length - hidden).join('');   // overlay = only the chips that do not fit on the line
      more.hidden = !hidden;
      more.textContent = '+' + hidden + ' more ▾';
      if (!hidden) setOpen(false);
    }
    more.onclick = function (e) { e.stopPropagation(); setOpen(!st.open); };
    document.addEventListener('click', function (e) { if (st.open && !el.contains(e.target)) setOpen(false); });
    setOpen(false);
    fit();
    if (!_ro && window.ResizeObserver) { _ro = true; new ResizeObserver(function () { fit(); }).observe(el); }
  }

  async function load() {
    var el = document.getElementById('outlookChangesCard');
    if (!el) return;
    try {
      var d = (window._dateQS ? window._dateQS() : '') || '';
      var res = await fetch('/api/cockpit/outlook-changes' + d);
      if (!res.ok) throw new Error(res.status);
      st.data = await res.json();
      // Rail markers are isolated: a failure here must never hide the top bar below.
      try {
        var m = {};
        (st.data.changes || []).forEach(function (c) { m[c.symbol] = c; });
        window._ocMap = m;
        addChip(Object.keys(m).length);
        document.dispatchEvent(new Event('oc-loaded'));
      } catch (e2) { console.warn('outlook rail markers failed', e2); }
      if (!st.data.changes || !st.data.changes.length) { el.hidden = true; return; }
      render();
    } catch (e) { el.hidden = true; }
  }
  window.loadOutlookChanges = load;
  document.addEventListener('DOMContentLoaded', load);
})();
