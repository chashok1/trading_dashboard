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
  function chip(d, asOf, wordy, showDate) {
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
      (showDate && d.changed_on ? '<span class="oc-dt">' + d.changed_on.slice(5, 7) + '/' + d.changed_on.slice(8, 10) + '</span>' : '') +
      '<span class="oc-ft">' + (path.length > shown.length ? '<i class="oc-ar">&hellip;</i>' : '') + steps + '</span></span>';
  }

  // ---- Macro Rail row markers (2026-10-16): "from -> to" in a reserved slot on each rail row. ----
  var SHAPE = { Bullish: ['bull', '▲'], Bearish: ['bear', '▼'], Neutral: ['neu', '■'] };
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
  // Per-panel "Δ N" filter pills (2026-10-17, user-directed): every rail panel with a collapse arrow gets its own pill next to it.
  // N = rows in THAT panel whose outlook changed this week; clicking hides the unchanged rows in that panel only (the Macro Rail
  // pill covers all of its sub-columns via #macroRailsWrap). On/off is remembered per panel.
  var SCOPES = [
    { id: 'rail', toggle: 'macroRailToggle', scope: '#macroRailsWrap', key: 'ocOnly', name: 'Macro Rail' },
    { id: 'sect', toggle: 'marketReadSectorsToggle', scope: '#marketReadSectorsBand', key: 'ocOnly_sect', name: 'Sectors' },
    { id: 'psetf', toggle: 'psEtfToggle', scope: '#psEtfBand', key: 'ocOnly_psetf', name: 'PS & ETF' },
    { id: 'call', toggle: 'callToggle', scope: '#callBand', key: 'ocOnly_call', name: 'CALL' },
    { id: 'ai', toggle: 'aiBubbleToggle', scope: '#aiBubbleBand', key: 'ocOnly_ai', name: 'AI Bubble' },
    { id: 'acct', toggle: 'accountsToggle', scope: '#macroAccountsBand', key: 'ocOnly_acct', name: 'Accounts' }
  ];
  function getOnly(sc) { try { return localStorage.getItem(sc.key) === '1'; } catch (e) { return false; } }
  var _watched = {};
  // Global filter (2026-10-17, user-directed): one button in the page header that turns the per-panel filters on/off together.
  function refreshGlobal() {
    // 2026-10-17, user-directed: the global pill lives in the Macro Rail header, centred, under a small "global" label.
    var rt = document.getElementById('macroRailToggle');
    var hdr = rt && rt.parentNode;
    if (!hdr) return;
    var live = SCOPES.filter(function (sc) { var p = document.getElementById('ocFilter_' + sc.id); return p && !p.hidden; });
    var syms = {};
    live.forEach(function (sc) {
      document.querySelectorAll(sc.scope + ' .msr-row.has-oc').forEach(function (r) { syms[r.getAttribute('data-sym')] = 1; });
    });
    var wrap = document.getElementById('ocGlobalWrap');
    if (!wrap) {
      wrap = document.createElement('span');
      wrap.id = 'ocGlobalWrap'; wrap.className = 'oc-global-wrap';
      wrap.innerHTML = '<span class="oc-global-lbl">global</span>';
      var b0 = document.createElement('button');
      b0.id = 'ocGlobal'; b0.type = 'button'; b0.className = 'oc-global';
      b0.title = 'Show only the rows whose outlook changed in the last 7 days, in every rail panel (click again to show all rows)';
      b0.onclick = function () {
        var act = SCOPES.filter(function (sc) { var p = document.getElementById('ocFilter_' + sc.id); return p && !p.hidden; });
        var allOn = act.length > 0 && act.every(getOnly);
        act.forEach(function (sc) { try { localStorage.setItem(sc.key, allOn ? '0' : '1'); } catch (e) {} });
        refreshChips();
      };
      wrap.appendChild(b0);
      // Radio filters (two groups, AND-combined; All = no filter): outlook and final action. CSS does the hiding.
      function grp(name, opts, key) {
        var cur = 'all';
        try { cur = localStorage.getItem('rf_' + key) || 'all'; } catch (e) {}
        document.body.setAttribute('data-rf-' + key, cur);
        var g = document.createElement('span');
        g.className = 'oc-rf';
        g.setAttribute('role', 'radiogroup');
        g.innerHTML = opts.map(function (o) {
          return '<label><input type="radio" name="' + name + '" value="' + o[0] + '"' + (o[0] === cur ? ' checked' : '') + '> ' + o[1] + '</label>';
        }).join('');
        g.addEventListener('change', function (e) {
          var v = e.target && e.target.value;
          if (!v) return;
          document.body.setAttribute('data-rf-' + key, v);
          try { localStorage.setItem('rf_' + key, v); } catch (e2) {}
          syncClear();
        });
        return g;
      }
      wrap.appendChild(grp('rfOutlook', [['all', 'All'], ['bull', 'Bullish'], ['bear', 'Bearish'], ['neu', 'Neutral']], 'ol'));
      wrap.appendChild(grp('rfAction', [['all', 'All'], ['buy', 'Buy'], ['sell', 'Sell'], ['hold', 'Hold']], 'act'));
      wrap.appendChild(grp('rfDir', [['all', 'All'], ['up', 'Up'], ['dn', 'Dn']], 'dir'));   // day %chg direction (2026-10-19, user-directed)
      // Clear (2026-10-19, user-directed): resets every global filter at once -- Δ changed off in all panels, Outlook = All, Action = All.
      var clr = document.createElement('button');
      clr.id = 'ocClear'; clr.type = 'button'; clr.className = 'oc-clear'; clr.textContent = 'Clear filters';
      clr.title = 'Reset the Δ changed, Outlook and Action filters (show all rows)';
      clr.onclick = function () {
        SCOPES.forEach(function (sc) { try { localStorage.setItem(sc.key, '0'); } catch (e) {} });
        ['rfOutlook', 'rfAction', 'rfDir'].forEach(function (nm) {
          var all = document.querySelector('input[name="' + nm + '"][value="all"]');
          if (all && !all.checked) { all.checked = true; all.dispatchEvent(new Event('change', { bubbles: true })); }
        });
        refreshChips();
      };
      wrap.appendChild(clr);
      // The chip-mode radios (% $ Price Act Hld, owned by macro_areas.js) live in this global area too, after the two filter groups: move the existing node
      // (its listeners come with it).
      var modeR = document.querySelector('input[name="msrValueMode"]');
      var modeBox = modeR && modeR.closest('.msr-mode-toggle');
      if (modeBox) wrap.appendChild(modeBox);
      hdr.classList.add('has-oc-global');
      hdr.appendChild(wrap);
    }
    var b = document.getElementById('ocGlobal');
    var txt = 'Δ ' + Object.keys(syms).length + ' changed';
    if (b.textContent !== txt) b.textContent = txt;
    // The radios are always shown; only the changed-count pill (and its label) hide when no panel has changes.
    b.hidden = !live.length;
    wrap.querySelector('.oc-global-lbl').hidden = !live.length;
    b.classList.toggle('on', live.length > 0 && live.every(getOnly));
    syncClear();
  }
  // The Clear button shows only while some global filter is active.
  function syncClear() {
    var c = document.getElementById('ocClear');
    if (!c) return;
    var radio = ['rfOutlook', 'rfAction', 'rfDir'].some(function (nm) {
      var r = document.querySelector('input[name="' + nm + '"]:checked');
      return r && r.value !== 'all';
    });
    var delta = SCOPES.some(function (sc) { var p = document.getElementById('ocFilter_' + sc.id); return p && !p.hidden && getOnly(sc); });
    c.hidden = !(radio || delta);
  }
  function refreshChips() {
    SCOPES.forEach(function (sc) {
      var root = document.querySelector(sc.scope), t = document.getElementById(sc.toggle);
      if (!root || !t || !t.parentNode) return;
      var n = root.querySelectorAll('.msr-row.has-oc').length;
      var b = document.getElementById('ocFilter_' + sc.id);
      if (!b) {
        b = document.createElement('button');
        b.id = 'ocFilter_' + sc.id; b.type = 'button'; b.className = 'oc-filter';
        b.title = 'Show only ' + sc.name + ' rows whose outlook changed in the last 7 days';
        b.onclick = function () { try { localStorage.setItem(sc.key, getOnly(sc) ? '0' : '1'); } catch (e) {} refreshChips(); };
        // Order in every header: [title ...] [radios] [delta pill] [arrow] -- the pill sits right next to the collapse arrow.
        t.parentNode.insertBefore(b, t);
      }
      var txt = 'Δ ' + n;
      if (b.textContent !== txt) b.textContent = txt;
      b.hidden = !n;
      var on = getOnly(sc);
      b.classList.toggle('on', on);
      root.classList.toggle('oc-only-scope', on && n > 0);
      // Rows are redrawn by other scripts: re-count when a panel's content changes (guarded so our own pill cannot loop).
      if (!_watched[sc.id] && window.MutationObserver) {
        _watched[sc.id] = true;
        var timer = null;
        new MutationObserver(function () {
          clearTimeout(timer);
          timer = setTimeout(function () {
            var cur = root.querySelectorAll('.msr-row.has-oc').length;
            var pill = document.getElementById('ocFilter_' + sc.id);
            if (!pill || pill.textContent !== 'Δ ' + cur) refreshChips();
          }, 150);
        }).observe(root, { childList: true, subtree: true });
      }
    });
    refreshGlobal();
  }

  // One line of chips (newest change first, no grouping); the rest float in an overlay under it.
  var _ro = false, _docClick = false;
  function render() {
    var el = document.getElementById('outlookChangesCard');
    var D = st.data;
    if (!el || !D) return;
    var all = D.changes.map(function (c) { var o = Object.assign({}, c); o.a = rank(c.from); o.b = rank(c.to); o.delta = o.b - o.a; return o; });
    // 2026-10-18, user-directed: Major Markets first, then Sectors, then everything else; newest change first inside each group.
    var grpOf = function (c) { return c.panel === 'Major Markets' ? 0 : c.panel === 'Sectors' ? 1 : 2; };
    // Inside a group: Bearish, then Bullish, then Neutral (by the new outlook); Major Markets / Sectors order by that first,
    // the other chips order by it within each date.
    var olOrd = function (c) { return c.to === 'Bearish' ? 0 : c.to === 'Bullish' ? 1 : 2; };
    all.sort(function (x, y) {
      return grpOf(x) - grpOf(y) ||
        (grpOf(x) < 2 ? olOrd(x) - olOrd(y) : 0) ||
        String(y.changed_on || '').localeCompare(String(x.changed_on || '')) ||
        olOrd(x) - olOrd(y) ||
        Math.abs(y.delta) - Math.abs(x.delta) || x.symbol.localeCompare(y.symbol);
    });
    // Flat list, newest first: a date label ("10/15") ahead of each day's chips.
    // The two newest change days (today + yesterday) spell out the new state: "▼ → Bullish"; older days are icons only.
    var recent = {};
    all.map(function (d) { return d.changed_on || ''; }).filter(function (v, i, a) { return a.indexOf(v) === i; })
      .sort().reverse().slice(0, 2).forEach(function (v) { recent[v] = 1; });
    // Major Markets / Sectors chips carry their date inside the pill (mm/dd) and get no date labels; the rest keep date labels.
    var items = [], lastDay = null, lastGrp = null;
    all.forEach(function (d) {
      var day = d.changed_on ? d.changed_on.slice(5, 7) + '/' + d.changed_on.slice(8, 10) : '';
      var g = grpOf(d), newGrp = g !== lastGrp, first = lastGrp === null;
      lastGrp = g;
      if (g < 2) {
        lastDay = null;
      } else if (day !== lastDay || newGrp) {
        if (!first || lastDay !== null) items.push({ label: day || 'This week', html: '<span class="oc-dl">' + esc(day || 'This week') + '</span>' });   // the very first label is left off (user-directed)
        lastDay = day;
      }
      items.push({ chip: true, day: day, grp: g, html: chip(d, D.as_of, true, g < 2) });
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
      // Three static rows (2026-10-18, user-directed: one more line): size the line to three chip-rows; anything that wraps onto a third row goes to the overlay.
      var fc = line.querySelector('.oc-chip2'), h = (fc && fc.offsetHeight) || 18, first = -1;
      var gap = parseFloat(getComputedStyle(line).rowGap) || 4;   // row gap comes from CSS (8px)
      line.style.maxHeight = (3 * h + 2 * gap) + 'px';
      var lr = line.getBoundingClientRect(), lb = lr.bottom;
      // Book + the button sit over the third row's right end: chips there must stop short of them.
      var stopX = Infinity, row3Top = lr.top + 2 * (h + gap) - 1;
      [document.querySelector('#outlookChangesCard .oc-grp[title="Book"]'), more].forEach(function (b) {
        if (b && !b.hidden && b.offsetParent) stopX = Math.min(stopX, b.getBoundingClientRect().left - 8);
      });
      Array.prototype.forEach.call(line.children, function (c, i) {
        var r = c.getBoundingClientRect();
        if (first < 0 && (r.bottom > lb + 0.5 || (r.top >= row3Top && r.right > stopX))) first = i;
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
      if (rest.length && rest[0].chip && rest[0].grp > 1) rest.unshift({ html: '<span class="oc-dl">' + esc(rest[0].day || 'This week') + '</span>' });
      pop.innerHTML = rest.map(function (i) { return i.html; }).join('');
      more.hidden = !nChips;
      more.textContent = '+' + nChips + ' more ▾';
      if (!nChips) setOpen(false);
    }
    window.ocFit = fit;   // macro_week.js re-fits once the Book chip is drawn (it reserves room on the third row)
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
    var mk = document.getElementById('mktPills');
    el.hidden = !((strip && !strip.hidden) || (usd && usd.innerHTML) || (mk && mk.innerHTML) || (line && !line.hidden && line.children.length));
    if (!el.hidden) alignVix();   // the VIX offset can only be measured once the card is visible
  };
  function hideLine() {
    var line = document.getElementById('ocLine'), more = document.getElementById('ocMore'), pop = document.getElementById('ocPop');
    if (line) { line.hidden = true; line.innerHTML = ''; }
    if (more) more.hidden = true;
    if (pop) pop.hidden = true;
    window.syncOcCard();
  }

  // Market pills under the US Dollar pill (2026-10-18, user-directed): SPX / Ndq / Rus / VIX / Oil / Gld / 10Y / BTC as chips with the day % change.
  // Colour = the day % change (green up, red down, grey flat; the Hedgeye outlook is in the tooltip). Reads GET /api/cockpit/index-pills. Display only.
  // VIX sits in its own slot (row 2), flush left under the US Dollar pill (2026-10-19, user-directed; it was briefly shifted right to
  // line up with 10Y). Kept as a function so the callers below stay valid.
  function alignVix() {
    var vb = document.getElementById('vixPill');
    if (vb) vb.style.marginLeft = '0px';
  }
  window.addEventListener('resize', alignVix);
  async function loadPills() {
    var box = document.getElementById('mktPills');
    if (!box) return;
    try {
      var d = (window._dateQS ? window._dateQS() : '') || '';
      var res = await fetch('/api/cockpit/index-pills' + d);
      if (!res.ok) throw new Error(res.status);
      var D = await res.json(), NL = String.fromCharCode(10);
      var html = (D.pills || []).map(function (p) {
        var pc = p.pct_change, pcCls = pc > 0 ? 'bull' : pc < 0 ? 'bear' : 'neu', txt = pc == null ? '--' : (pc > 0 ? '+' : '') + pc.toFixed(2) + '%';
        var tip = [p.label + ' (' + p.symbol + ')', '• Day change: ' + txt, '• Hedgeye outlook: ' + (p.outlook || '--'),
          'Source: drv_quote, drv_rr'].join(NL);
        // VIX shows its current level between the label and the % change (2026-10-19, user-directed).
        var lvl = p.label === 'VIX' && p.last_price != null ? '<span class="oc-lvl">' + p.last_price.toFixed(2) + '</span>' : '';
        // 2026-10-19, user-directed: the chip's own colour (border + fill) is the Hedgeye OUTLOOK; the day % change colours only its %chg text.
        var chipCls = cls(p.outlook || 'Neutral');
        return '<span class="oc-chip2 ' + chipCls + '" data-lbl="' + esc(p.label) + '" title="' + esc(tip) + '"><b>' + esc(p.label) + '</b>' + lvl +
          '<span class="oc-ft"><span class="oc-pct ' + pcCls + '">' + txt + '</span></span></span>';
      });
      // Stacked columns (top to bottom), each sitting at its first member's old spot and growing upward over the lines above it.
      var pills = D.pills || [], STACKS = [['Oil', 'Gld', 'BTC']], out = [], seen = {}, slot = {}, vixHtml = '', tenYAt = -1;
      pills.forEach(function (p, i) {
        var k = -1;
        STACKS.forEach(function (st, j) { if (st.indexOf(p.label) >= 0) k = j; });
        if (p.label === 'VIX') { vixHtml = html[i]; tenYAt = out.length; out.push(null); return; }   // VIX lives in its own slot (#vixPill), left, below the US Dollar pill; 10Y keeps VIX's old place in the row
        if (p.label === '10Y' && tenYAt >= 0) { out[tenYAt] = html[i]; return; }
        if (k < 0) { out.push(html[i]); return; }
        if (!slot[k]) { slot[k] = { at: out.length, items: [] }; out.push(null); }
        slot[k].items[STACKS[k].indexOf(p.label)] = html[i];
      });
      STACKS.forEach(function (st, k) {
        if (slot[k]) out[slot[k].at] = '<span class="oc-stack oc-stack' + st.length + '">' + slot[k].items.filter(Boolean).join('') + '</span>';
      });
      out = out.filter(Boolean);
      box.innerHTML = out.join('');
      var vb = document.getElementById('vixPill'); if (vb) vb.innerHTML = vixHtml;
      alignVix();
    } catch (e) { box.innerHTML = ''; var vb2 = document.getElementById('vixPill'); if (vb2) vb2.innerHTML = ''; }
    window.syncOcCard();
  }

  async function load() {
    loadPills();
    var el = document.getElementById('outlookChangesCard');
    if (!el) return;
    try {
      var d = (window._dateQS ? window._dateQS() : '') || '';
      var res = await fetch('/api/cockpit/outlook-changes' + d);
      if (!res.ok) throw new Error(res.status);
      st.data = await res.json();
      // Rail glyphs cover every symbol with an RR outlook (Accounts, AI Bubble, Country...), not just Macro Rail members.
      var allRes = await fetch('/api/cockpit/outlook-changes' + (d ? d + '&' : '?') + 'all_symbols=true').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
      // Rail markers are isolated: a failure here must never hide the top bar below.
      try {
        var m = {};
        ((allRes && allRes.changes) || st.data.changes || []).forEach(function (c) { if (!m[c.symbol]) m[c.symbol] = c; });   // rail marker = the symbol's newest change
        window._ocMap = m;
        refreshChips();
        document.dispatchEvent(new Event('oc-loaded'));
      } catch (e2) { console.warn('outlook rail markers failed', e2); }
      if (!st.data.changes || !st.data.changes.length) { hideLine(); return; }
      render();
    } catch (e) { hideLine(); }
  }
  window.loadOutlookChanges = load;
  document.addEventListener('DOMContentLoaded', load);
})();
