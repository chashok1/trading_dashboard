/* area_verdicts.js -- TASK_149 Area Driver Rules on `/`.
 *
 * (1) Compact area tiles in #areaVerdictStrip (centre column; same bar as the Macro Week chips):
 *     verdict glyph + colour, "$ held" only on Headwind/Stretched tiles, quiet areas collapsed
 *     into "+N quiet", a "$X headwind" total. Click a tile -> drawer with its driver legs
 *     (check / cross / ?), read text and linked stocks.
 * (2) Verdict pills on the existing macro rails (decorateRails(), called by macro_areas.js after
 *     every renderRail and again when this data lands). One area per rail -> header pill;
 *     multi-area rails -> pill on the driving row (data-sym); parent roll-up -> "2 ▼" header pill.
 *
 * Reads GET /api/cockpit/area-verdicts. Advisory only: never changes a Final Call. Every state has
 * a glyph, never colour alone (CVD-safe --mr-* pair).
 */
(function () {
  'use strict';

  var G = { headwind: '▼', tailwind: '▲', turning: '◆', stretched: '⚠', unclear: '○', quiet: '–' };
  var NAME = { headwind: 'Headwind', tailwind: 'Tailwind', turning: 'Turning', stretched: 'Stretched',
               unclear: 'Unclear', quiet: 'Quiet' };
  var MEANS = {
    headwind: 'Drivers are working against this area. Think twice before buying; consider trimming.',
    tailwind: 'Drivers support this area. Buy signals here are confirmed.',
    turning: 'A driver just flipped (last 5 days) and price is not stretched. Put it on watch.',
    stretched: 'Good trend, but price is at the top of its range or vol is above calm. Do not chase.',
    unclear: 'The usual driver link is broken, or an input is missing or stale. Trust price, not the driver rules.',
    quiet: 'No rule fires. Nothing to do.'
  };
  var RAIL_CONTAINER = {
    commodities_metals: 'macroRailMetals', commodities_ag: 'macroRailAg', commodities_energy: 'macroRailEnergy',
    crypto: 'macroRailCrypto', top9: 'macroRailTop9', rates_duration: 'macroRailRates',
    credit: 'macroRailCredit', country_etfs: 'macroRailCountry'
  };

  var data = null;
  var showQuiet = false;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function usd(v) {
    if (v == null) return '--';
    var a = Math.abs(v);
    return '$' + (a >= 10000 ? Math.round(a / 1000) + 'k' : a >= 1000 ? (a / 1000).toFixed(1) + 'k' : Math.round(a));
  }
  function byKey(k) {
    if (!data) return null;
    var all = data.areas.concat(data.parents || []);
    for (var i = 0; i < all.length; i++) if (all[i].area_key === k) return all[i];
    return null;
  }
  function isQuiet(a) { return !a.verdict || a.verdict === 'quiet'; }

  function meansFor(a) {
    var he = a.gate && a.gate.he;
    if (he && he.cancelled) return 'A rates headwind fires, but Hedgeye is bullish on most of this group, so it is set aside.';
    return MEANS[a.verdict || 'quiet'];
  }
  var LEAN = { bull: ['av-lean-bull', '▲', 'bullish'], mixed: ['av-lean-mix', '◆', 'mixed / neutral'],
               bear: ['av-lean-bear', '▼', 'bearish'] };
  function heGroupHtml(a) {
    var he = a.gate && a.gate.he;
    if (!he || !he.stocks || !he.stocks.length) return '';
    var chips = he.stocks.map(function (x) {
      var l = LEAN[x.lean] || ['av-lean-none', '–', 'no Hedgeye outlook'];
      return '<span class="av-stk ' + l[0] + '" title="' + esc(x.s + ' - Hedgeye ' + l[2]) + '">' + esc(x.s) + ' ' + l[1] + '</span>';
    }).join('');
    return '<div class="av-sh">Group stocks and Hedgeye lean</div>' +
      '<div class="av-dim">' + he.bull + ' of ' + he.covered + ' covered stocks bullish (' + he.members + ' in group). ▲ bullish · ◆ mixed/neutral · ▼ bearish · – none</div>' +
      '<div class="av-stks">' + chips + '</div>';
  }
  function tileTip(a) {
    var l = [a.label + ': ' + (G[a.verdict] || '') + ' ' + NAME[a.verdict || 'quiet'],
             '• ' + meansFor(a)];
    if (a.read_text) l.push('• ' + a.read_text);
    if (a.since_date) l.push('• Since ' + a.since_date + (a.is_new ? ' (new)' : ''));
    if (a.held_dollar) l.push('• Held in this area: $' + Math.round(a.held_dollar).toLocaleString('en-US'));
    l.push('Advisory only -- never changes a Final Call. Click for the drivers.');
    return l.join('\n');
  }

  function tileHtml(a) {
    var v = a.verdict;
    var money = (v === 'headwind' || v === 'stretched') && a.held_dollar > 0
      ? ' <span class="av-usd">' + usd(a.held_dollar) + '</span>' : '';
    var dot = a.is_new ? '<span class="av-new" title="Verdict changed in the last few days">●</span>' : '';
    return '<button type="button" class="av-tile av-' + esc(v) + '" data-av="' + esc(a.area_key) + '" title="' +
      esc(tileTip(a)) + '">' + esc(a.short_label) + ' <b>' + G[v] + '</b>' + money + dot + '</button>';
  }

  function render() {
    var strip = document.getElementById('areaVerdictStrip');
    var sep = document.querySelector('.mw-areasep');
    if (!strip) { renderHeadwindPanel(); return; }   // tile card removed 2026-10-16; the right-column panel is all that renders here
    if (!data || !data.areas || !data.areas.length) { strip.style.display = 'none'; if (sep) sep.style.display = 'none'; return; }
    strip.style.display = '';
    if (sep) sep.style.display = '';
    var loud = data.areas.filter(function (a) { return !isQuiet(a); });
    var quiet = data.areas.filter(isQuiet);
    var shown = showQuiet ? data.areas : loud;
    var html = '';
    // Grouped like the Outlook changes strip, with a gap instead of a text label (group name kept as a hover title).
    var GLBL = { metals: 'Metals', energy: 'Energy', risk: 'Risk assets', rates: 'Rates & Credit' };
    var order = [], byG = {};
    shown.forEach(function (a) {
      var g = a.group_key || '';
      if (!byG[g]) { byG[g] = []; order.push(g); }
      byG[g].push(a);
    });
    order.forEach(function (g) {
      html += '<span class="oc-grp oc-grp-gap" title="' + esc(GLBL[g] || g) + '">' + byG[g].map(function (a) {
        return isQuiet(a)
          ? '<button type="button" class="av-tile av-quiet" data-av="' + esc(a.area_key) + '" title="' + esc(tileTip(a)) + '">' +
            esc(a.short_label) + ' <b>—</b></button>'
          : tileHtml(a);
      }).join('') + '</span>';
    });
    if (quiet.length) {
      html += '<button type="button" class="av-more" id="avQuietBtn" title="Areas where no rule fires (silence is the default)">' +
        (showQuiet ? 'hide quiet' : '+' + quiet.length + ' quiet') + '</button>';
    }
    if (data.headwind_count > 0 || data.headwind_dollar > 0) {
      html += '<button type="button" class="av-tile av-total" id="avTotalBtn" title="' +
        esc('Money you hold (once per stock) in areas currently in Headwind. Inverse positions are not counted.\nClick for the list.') +
        '">' + usd(data.headwind_dollar) + ' headwind ↘</button>';
    }
    strip.innerHTML = html;
    renderHeadwindPanel();
  }

  /* ── drawer ─────────────────────────────────────────────────────── */
  function closeDrawer() {
    var d = document.getElementById('avDrawer');
    if (d) d.remove();
  }
  function placeDrawer(el, anchor) {
    var r = anchor.getBoundingClientRect();
    var w = Math.min(460, window.innerWidth - 16);
    el.style.width = w + 'px';
    el.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + 'px';
    el.style.top = Math.min(r.bottom + 4, window.innerHeight - 120) + 'px';
  }
  function legHtml(l) {
    var mark = l.missing ? '?' : l.passed ? '✓' : '✗';
    var cls = l.missing ? 'av-leg-na' : l.passed ? 'av-leg-ok' : 'av-leg-no';
    return '<div class="av-leg ' + cls + '"><span class="av-mark">' + mark + '</span> ' + esc(l.phrase) + '</div>';
  }
  function stockChips(a) {
    if (!a.stocks || !a.stocks.length) return '<div class="av-dim">No linked stocks today.</div>';
    var chips = a.stocks.map(function (s) {
      var t = s.tos_symbol + ' - ' + s.tier + (s.inverted ? ' - inverse position (verdict flipped)' : '') +
        (s.held ? ' - held $' + Math.round(s.position_dollar).toLocaleString('en-US') : '');
      return '<span class="av-stk' + (s.held ? ' av-stk-held' : '') + '" title="' + esc(t) + '">' + esc(s.tos_symbol) +
        (s.inverted ? '↺' : '') + (s.held ? ' ' + usd(s.position_dollar) : '') + '</span>';
    }).join('');
    var more = a.n_stocks > a.stocks.length ? ' <span class="av-dim">+' + (a.n_stocks - a.stocks.length) + ' more</span>' : '';
    return '<div class="av-stks">' + chips + more + '</div>';
  }
  function areaDrawerHtml(a) {
    var v = a.verdict || 'quiet';
    var h = '<div class="av-dh av-' + esc(v) + '"><b>' + esc(a.label) + '</b> ' + G[v] + ' ' + NAME[v] +
      (a.since_date ? '<span class="av-dim"> since ' + esc(a.since_date) + '</span>' : '') + '</div>';
    h += '<div class="av-dim">' + esc(meansFor(a)) + '</div>';
    if (a.read_text) h += '<div class="av-read">' + esc(a.read_text) + '</div>';
    if (a.gate && a.gate.applies) {
      h += '<div class="av-dim">Dollar link (' + esc(a.gate.asset) + (a.gate.fallback ? ', borrowed' : '') + '): 30d correlation ' +
        (a.gate.w30 == null ? 'n/a' : Number(a.gate.w30).toFixed(2)) + ' -- ' +
        (a.gate.ok === true ? 'valid' : a.gate.ok === false ? 'not valid' : 'no data') + '</div>';
    }
    (a.rules || []).forEach(function (r) {
      h += '<div class="av-rule' + (r.fired ? ' av-rule-fired' : '') + '"><div class="av-rule-h">' +
        (r.fired ? '<b>' : '') + esc(r.description) + (r.fired ? '</b>' : '') +
        ' <span class="av-dim">(' + esc(NAME[r.verdict] || r.verdict) + (r.data_missing ? ', input missing' : '') + ')</span></div>' +
        (r.legs || []).map(legHtml).join('') + '</div>';
    });
    h += heGroupHtml(a);
    if ((a.stocks && a.stocks.length) || !(a.gate && a.gate.he)) h += '<div class="av-sh">Linked stocks</div>' + stockChips(a);
    return h;
  }
  // 2026-10-16, user-directed: the "$X headwind" pill's list now lives in a right-column panel (#headwindBand, between
  // Dollar correlation and Sectors) instead of a popup; clicking the pill scrolls to it.
  function renderHeadwindPanel() {
    var band = document.getElementById('headwindBand'), body = document.getElementById('headwindBody');
    if (!band || !body) return;
    var has = data && data.areas && data.areas.some(function (a) { return a.verdict === 'headwind'; });
    band.hidden = !has;
    if (!has) { body.innerHTML = ''; return; }
    var tot = document.getElementById('headwindTotal');
    if (tot) tot.textContent = usd(data.headwind_dollar || 0);
    // Colour the arrows (green up, red down) in the reasons and area names.
    body.innerHTML = totalDrawerHtml().replace(/▲/g, '<span class="av-up">▲</span>').replace(/▼/g, '<span class="av-dn">▼</span>');
  }
  function totalDrawerHtml() {
    var rows = data.areas.filter(function (a) { return a.verdict === 'headwind'; });
    var h = '<div class="av-dh av-headwind"><b>Headwind areas</b><span class="av-dim"> $ you hold (inverse positions excluded)</span></div>';
    if (!rows.length) return h + '<div class="av-dim">None.</div>';
    rows.forEach(function (a) {
      // 2026-10-17 -- compact row: area name, its reason on the same line, then held-stock chips only if there are any.
      var held = (a.stocks || []).filter(function (s) { return s.held; });
      h += '<div class="av-hw"><span class="av-sh">' + esc(a.label) + ' ▼ ' + (a.held_dollar ? usd(a.held_dollar) : '') + '</span> ' +
        '<span class="av-read">' + esc(a.read_text || '') + '</span>' +
        (held.length ? stockChips({ stocks: held, n_stocks: held.length }) : '') + '</div>';
    });
    return h;
  }
  function openDrawer(anchor, html) {
    closeDrawer();
    var el = document.createElement('div');
    el.id = 'avDrawer';
    el.className = 'av-drawer';
    el.innerHTML = '<button type="button" class="av-x" aria-label="Close">×</button>' + html;
    document.body.appendChild(el);
    placeDrawer(el, anchor);
    el.querySelector('.av-x').addEventListener('click', closeDrawer);
  }

  /* ── rail pills ─────────────────────────────────────────────────── */
  function pillHtml(a, text) {
    var v = a.verdict;
    if (!v || v === 'quiet') return '';
    return '<span class="av-pill av-' + esc(v) + '" data-av="' + esc(a.area_key) + '" title="' + esc(tileTip(a)) + '">' + text + '</span>';
  }
  function rollupText(p) {
    var parts = [];
    ['headwind', 'stretched', 'turning', 'tailwind', 'unclear'].forEach(function (k) {
      if (p.counts && p.counts[k]) parts.push(p.counts[k] + ' ' + G[k]);
    });
    return parts.join(' · ');
  }
  function rollupClass(p) {
    var order = ['headwind', 'stretched', 'turning', 'tailwind', 'unclear'];
    for (var i = 0; i < order.length; i++) if (p.counts && p.counts[order[i]]) return order[i];
    return 'unclear';
  }
  function decorateRails() {
    if (!data || !data.rails) return;
    document.querySelectorAll('.av-pill[data-rail]').forEach(function (n) { n.remove(); });
    Object.keys(data.rails).forEach(function (railKey) {
      var cid = RAIL_CONTAINER[railKey];
      var cont = cid && document.getElementById(cid);
      if (!cont) return;
      var slot = data.rails[railKey];
      var hdr = cont.previousElementSibling;
      if (slot.header && hdr) {
        var a = byKey(slot.header);
        if (a) {
          var txt = a.is_leaf ? G[a.verdict] + ' ' + NAME[a.verdict] : rollupText(a);
          var html = a.is_leaf ? pillHtml(a, txt) : (rollupText(a) ? '<span class="av-pill av-' + rollupClass(a) +
            '" data-av="' + esc(a.area_key) + '" title="' + esc('Roll-up of ' + (a.children || []).join(', ') + '. Click for the areas.') + '">' + txt + '</span>' : '');
          if (html) {
            var tmp = document.createElement('span');
            tmp.innerHTML = html;
            var pill = tmp.firstChild;
            pill.setAttribute('data-rail', railKey);
            var btn = hdr.querySelector('.msr-sort-btn');
            hdr.insertBefore(pill, btn || null);
          }
        }
      }
      Object.keys(slot.rows || {}).forEach(function (sym) {
        var a2 = byKey(slot.rows[sym]);
        if (!a2) return;
        var html2 = a2.is_leaf ? pillHtml(a2, G[a2.verdict] || '')
          : (rollupText(a2) ? '<span class="av-pill av-' + rollupClass(a2) + '" data-av="' + esc(a2.area_key) +
            '" title="' + esc('Roll-up of ' + (a2.children || []).join(', ') + '. Click for the areas.') + '">' + rollupText(a2) + '</span>' : '');
        if (!html2) return;
        var row = cont.querySelector('.msr-row[data-sym="' + sym.replace(/["\\]/g, '') + '"]');
        var nm = row && row.querySelector('.msr-name');
        if (!nm) return;
        var t2 = document.createElement('span');
        t2.innerHTML = html2;
        t2.firstChild.setAttribute('data-rail', railKey);
        nm.appendChild(t2.firstChild);
      });
    });
  }

  /* ── load / wiring ──────────────────────────────────────────────── */
  async function load() {
    var dp = document.getElementById('datePicker');
    var d = dp && dp.value;
    try {
      var res = await fetch('/api/cockpit/area-verdicts' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
    } catch (e) {
      data = null;
    }
    render();
    decorateRails();
    document.dispatchEvent(new Event('av-loaded'));
  }

  function onClick(e) {
    var tgt = e.target.closest ? e.target.closest('[data-av], #avQuietBtn, #avTotalBtn') : null;
    if (!tgt) return;
    if (tgt.id === 'avQuietBtn') { showQuiet = !showQuiet; render(); return; }
    if (tgt.id === 'avTotalBtn') {
      var hb = document.getElementById('headwindBand');
      if (hb && !hb.hidden) { hb.scrollIntoView({ behavior: 'smooth', block: 'center' }); hb.classList.add('av-flash'); setTimeout(function () { hb.classList.remove('av-flash'); }, 1500); }
      return;
    }
    var a = byKey(tgt.getAttribute('data-av'));
    if (!a) return;
    e.stopPropagation();
    if (!a.is_leaf) {
      var kids = (a.children || []).map(byKey).filter(Boolean);
      openDrawer(tgt, kids.map(areaDrawerHtml).join('<hr class="av-hr">'));
    } else {
      openDrawer(tgt, areaDrawerHtml(a));
    }
  }

  function init() {
    if (!document.getElementById('areaVerdictStrip') && !document.getElementById('headwindBand')) return;
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDrawer(); });
    document.addEventListener('mousedown', function (e) {
      var d = document.getElementById('avDrawer');
      if (d && !d.contains(e.target) && !(e.target.closest && e.target.closest('[data-av], #avTotalBtn'))) closeDrawer();
    });
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    load();
  }

  // Themes grid "Driver" cell (web/market_read.js): the verdict for the area/parent whose label equals the theme name.
  // Same hover text as the tile; click opens the same drawer. '' until the data lands or when no area matches.
  function cellFor(theme) {
    if (!data) return '';
    var t = String(theme).toLowerCase();
    var same = function (x) { return String(x.label).toLowerCase() === t; };
    var a = (data.areas || []).filter(same)[0];
    if (a) {
      var v = a.verdict || 'quiet';
      return '<span class="av-pill av-' + esc(v) + '" data-av="' + esc(a.area_key) + '" title="' + esc(tileTip(a)) + '">' +
        (a.is_new ? '<span class="av-new" title="Verdict changed in the last few days">●</span> ' : '') +
        (v === 'quiet' ? G[v] : G[v] + ' ' + NAME[v]) +
        ((v === 'headwind' || v === 'stretched') && a.held_dollar > 0 ? ' <span class="av-usd">' + usd(a.held_dollar) + '</span>' : '') + '</span>';
    }
    var p = (data.parents || []).filter(same)[0];
    if (p) {
      var kids = (p.children || []).map(byKey).filter(Boolean);
      var txt = rollupText(p) || '–';
      var heldSum = kids.reduce(function (n, k) { return n + ((k.verdict === 'headwind' || k.verdict === 'stretched') ? (k.held_dollar || 0) : 0); }, 0);
      return '<span class="av-pill av-' + (rollupText(p) ? rollupClass(p) : 'quiet') + '" data-av="' + esc(p.area_key) + '" title="' +
        esc(['Roll-up of ' + kids.map(function (k) { return k.label; }).join(', ')].concat(kids.map(tileTip)).join(String.fromCharCode(10, 10))) +
        '">' + (kids.some(function (k) { return k.is_new; }) ? '<span class="av-new" title="A verdict changed in the last few days">●</span> ' : '') + txt + (heldSum > 0 ? ' <span class="av-usd">' + usd(heldSum) + '</span>' : '') + '</span>';
    }
    return '';
  }

  window.AreaVerdicts = { load: load, decorateRails: decorateRails, cellFor: cellFor };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
