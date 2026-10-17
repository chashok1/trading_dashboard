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
  // One chip per symbol: its path through the window as icons ("RSP  up -> down -> Bullish"); the last step is spelled
  // out for the newest two days. Paths longer than 4 states keep the last 4 behind an ellipsis; details in the tooltip.
  function chip(d, asOf, wordy) {
    var path = d.path && d.path.length > 1 ? d.path : [d.from, d.to];
    var flips = [];
    for (var i = 0; i + 1 < path.length; i++) {
      flips.push(path[i] + ' -> ' + path[i + 1] + (d.path_dates && d.path_dates[i] ? '  (' + d.path_dates[i].slice(5, 7) + '/' + d.path_dates[i].slice(8, 10) + ')' : ''));
    }
    var tip = [d.symbol + (d.desc ? ' - ' + d.desc : ''), d.panel].concat(flips).join(String.fromCharCode(10));
    var shown = path.length > 4 ? path.slice(-4) : path;
    var last = shown.length - 1;
    var steps = shown.map(function (st, i) {
      return (i ? '<i class="oc-ar">&rarr;</i>' : '') +
        (i === last && wordy ? '<span class="oc-w ' + cls(st) + '">' + esc(st) + '</span>' : shape(st));
    }).join('');
    return '<span class="oc-chip2 ' + cls(d.to) + '" title="' + esc(tip) + '"><b>' + esc(d.symbol) + '</b>' +
      '<span class="oc-ft">' + (path.length > shown.length ? '<i class="oc-ar">&hellip;</i>' : '') + steps + '</span></span>';
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
  var _ro = false, _docClick = false;
  function render() {
    var el = document.getElementById('outlookChangesCard');
    var D = st.data;
    if (!el || !D) return;
    var all = D.changes.map(function (c) { var o = Object.assign({}, c); o.a = rank(c.from); o.b = rank(c.to); o.delta = o.b - o.a; return o; });
    all.sort(function (x, y) {
      return String(y.changed_on || '').localeCompare(String(x.changed_on || '')) ||
        Math.abs(y.delta) - Math.abs(x.delta) || x.symbol.localeCompare(y.symbol);
    });
    // Flat list, newest first: a date label ("10/15") ahead of each day's chips.
    // The two newest change days (today + yesterday) spell out the new state: "▼ → Bullish"; older days are icons only.
    var recent = {};
    all.map(function (d) { return d.changed_on || ''; }).filter(function (v, i, a) { return a.indexOf(v) === i; })
      .sort().reverse().slice(0, 2).forEach(function (v) { recent[v] = 1; });
    var items = [], lastDay = null;
    all.forEach(function (d) {
      var day = d.changed_on ? d.changed_on.slice(5, 7) + '/' + d.changed_on.slice(8, 10) : '';
      if (day !== lastDay) { if (lastDay !== null) items.push({ label: day || 'This week', html: '<span class="oc-dl">' + esc(day || 'This week') + '</span>' }); lastDay = day; }   // the newest day's label is left off (user-directed)
      items.push({ chip: true, day: day, html: chip(d, D.as_of, !!recent[d.changed_on || '']) });
    });
    var chips = items.map(function (i) { return i.html; }).join('');
    // The skeleton (#ocLine, #ocMore, #ocPop, and #macroWeekStrip ahead of them) lives in index.html so the Macro Week
    // pills (event, Book) can sit at the start of this bar; only the chips are filled here.
    var line = el.querySelector('#ocLine'), more = el.querySelector('#ocMore'), pop = el.querySelector('#ocPop');
    if (!line || !more || !pop) return;
    line.innerHTML = chips;
    line.hidden = false;
    window.syncOcCard();
    function setOpen(v) { st.open = v; pop.hidden = !v; more.classList.toggle('on', v); }
    // Count the chips that do not fit on the one line.
    // Index of the first item that wraps past the two rows, measured with the button showing `label`.
    function firstOverflow(label) {
      more.hidden = false; more.textContent = label;   // the button narrows the line, so measure with its real text
      Array.prototype.forEach.call(line.children, function (c) { c.style.visibility = ''; });
      // Two static rows: size the line to two chip-rows; anything that wraps onto a third row goes to the overlay.
      var fc = line.querySelector('.oc-chip2'), h = (fc && fc.offsetHeight) || 18, first = -1;
      var gap = parseFloat(getComputedStyle(line).rowGap) || 4;   // row gap comes from CSS (8px)
      line.style.maxHeight = (2 * h + gap) + 'px';
      var lb = line.getBoundingClientRect().bottom;
      Array.prototype.forEach.call(line.children, function (c, i) {
        if (first < 0 && c.getBoundingClientRect().bottom > lb + 0.5) first = i;
      });
      // A date label left alone at the end of the line (its chips pushed to the overlay) moves to the overlay too.
      if (first > 0 && !items[first].label && items[first - 1].label) { first--; line.children[first].style.visibility = 'hidden'; }
      return first;
    }
    function countChips(first) {
      var n = 0;
      if (first >= 0) items.forEach(function (it, i) { if (i >= first && it.chip) n++; });
      return n;
    }
    function fit() {
      // The button's text changes the line width (+99 is wider than +1), which can pull a chip back onto row 2 and make
      // it appear twice (row 2 and the overlay). Re-measure with the real count until it settles.
      var first = firstOverflow('+99 more ▾'), nChips = countChips(first);
      for (var k = 0; k < 3; k++) {
        var f2 = firstOverflow(nChips ? '+' + nChips + ' more ▾' : '+0 more ▾'), n2 = countChips(f2);
        first = f2;
        if (n2 === nChips) break;
        nChips = n2;
      }
      // Overlay = what does not fit on the line; if it starts mid-day, repeat that day's label.
      var rest = first < 0 ? [] : items.slice(first);
      if (rest.length && rest[0].chip) rest.unshift({ html: '<span class="oc-dl">' + esc(rest[0].day || 'This week') + '</span>' });
      pop.innerHTML = rest.map(function (i) { return i.html; }).join('');
      more.hidden = !nChips;
      more.textContent = '+' + nChips + ' more ▾';
      if (!nChips) setOpen(false);
    }
    more.onclick = function (e) { e.stopPropagation(); setOpen(!st.open); };
    if (!_docClick) { _docClick = true; document.addEventListener('click', function (e) { if (st.open && !el.contains(e.target)) { var p2 = document.getElementById('ocPop'), m2 = document.getElementById('ocMore'); if (p2) p2.hidden = true; if (m2) m2.classList.remove('on'); st.open = false; } }); }
    setOpen(false);
    fit();
    if (!_ro && window.ResizeObserver) { _ro = true; new ResizeObserver(function () { fit(); }).observe(el); }
  }

  // The card is shown when it has anything: Macro Week pills at its start and/or outlook-change chips.
  window.syncOcCard = function () {
    var el = document.getElementById('outlookChangesCard');
    if (!el) return;
    var strip = document.getElementById('macroWeekStrip'), usd = document.getElementById('usdPill'), line = document.getElementById('ocLine');
    el.hidden = !((strip && !strip.hidden) || (usd && usd.innerHTML) || (line && !line.hidden && line.children.length));
  };
  function hideLine() {
    var line = document.getElementById('ocLine'), more = document.getElementById('ocMore'), pop = document.getElementById('ocPop');
    if (line) { line.hidden = true; line.innerHTML = ''; }
    if (more) more.hidden = true;
    if (pop) pop.hidden = true;
    window.syncOcCard();
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
        (st.data.changes || []).forEach(function (c) { if (!m[c.symbol]) m[c.symbol] = c; });   // rail marker = the symbol's newest change
        window._ocMap = m;
        addChip(Object.keys(m).length);
        document.dispatchEvent(new Event('oc-loaded'));
      } catch (e2) { console.warn('outlook rail markers failed', e2); }
      if (!st.data.changes || !st.data.changes.length) { hideLine(); return; }
      render();
    } catch (e) { hideLine(); }
  }
  window.loadOutlookChanges = load;
  document.addEventListener('DOMContentLoaded', load);
})();
