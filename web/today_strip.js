/* Today panel -- top of the middle column, above the US Dollar / events / outlook-change bar.
 * One-glance read of how the market is going today: headline words, cross-asset moves, equity breadth,
 * factors and areas. Display only; never feeds rules or the Final Call.
 * Data: GET /api/cockpit/today-strip (drv_quote on the anchor date + ref_symbol_theme members). */
(function () {
  'use strict';
  var KEY = 'todayStripCollapsed';
  var FACTORS = { 'Momentum': 1, 'Defensives': 1, 'Large caps': 1, 'Cyclicals': 1, 'Small caps': 1 };
  var RENAME = { 'Duration': 'Bonds', 'Tech/software': 'Software' };
  var SHORT_THEME = { 'Momentum': 'Mtum' };   // short chip names; the hover keeps the full name
  // Click targets: the Macro Rail panel that holds the same symbols.
  var JUMP = { sector: 'macroSectorEtfsBand', cross: 'macroTop9Band', Energy: 'macroEnergyBand', Gold: 'macroMetalsBand',
    'Precious metals': 'macroMetalsBand', Credit: 'macroCreditBand', Duration: 'macroRatesBand', Ags: 'macroAgBand', Crypto: 'macroCannabisBand' };
  var data = null;

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function sgn(n) { return n > 0 ? '+' : n < 0 ? '−' : ''; }
  function fpct(n) { return sgn(n) + Math.abs(n).toFixed(2) + '%'; }
  function fbp(n) { return sgn(n) + Math.abs(n).toFixed(1).replace(/\.0$/, '') + 'bp'; }
  function cls(n) { return n > 0 ? ' ts-u' : n < 0 ? ' ts-d' : ''; }
  function num(v, dp) { return v == null ? '' : Number(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }); }
  function currentDate() { var dp = document.getElementById('datePicker'); return (dp && dp.value) ? dp.value : ''; }

  // Levels of 1,000 or more drop the decimals (S&P 500, Nasdaq, Russell, Gold, BTC) to keep the chips narrow; yields show two decimals.
  function levelText(c) {
    if (c.bp != null && c.pct == null) return num(c.level, 2) + '%';   // 2Y / 10Y / 30Y yields
    var dec = c.level >= 1000 ? 0 : 2;
    if (c.sym === '/GC' || c.sym === '/CL') return '$' + num(c.level, dec);
    if (c.sym === '/BTC') return '$' + num(c.level, 0);
    return num(c.level, dec);
  }

  // One chip: name, optional level, optional move. jump = id of the Macro Rail band to scroll to.
  function chip(name, level, move, moveCls, tip, jump, extra) {
    return '<span class="ts-chip' + (moveCls || '') + '" tabindex="0"' + (jump ? ' data-jump="' + jump + '"' : '') + '>' +
      '<span class="ts-nm">' + esc(name) + '</span>' +
      (level ? '<span class="ts-lv">' + esc(level) + '</span>' : '') + (extra || '') +
      (move ? '<span class="ts-mv' + (moveCls || '') + '">' + esc(move) + '</span>' : '') +
      (tip ? '<span class="ts-tip">' + tip + '</span>' : '') + '</span>';
  }
  function tipRows(title, rows, foot) {
    return '<h4>' + esc(title) + '</h4>' + rows.map(function (r) {
      return '<div><span>' + esc(r[0]) + '</span><span class="' + (r[2] || '') + '">' + esc(r[1]) + '</span></div>';
    }).join('') + (foot ? '<div class="ts-src">' + esc(foot) + '</div>' : '');
  }

  // The one word kept from the old market line: is the S&P 500 up or down today. Everything else on that line was a
  // duplicate of a chip with the price (cross-asset row) and is gone.
  function stocksWord(d) {
    var c = d.cross.filter(function (x) { return x.sym === 'SPX'; })[0];
    if (!c || c.pct == null || c.pct === 0) return '';
    var k = c.pct > 0 ? 'ts-u' : 'ts-d';
    return '<span class="ts-chip ' + k + ' ts-w2 ts-tight"><span class="ts-nm">Stocks</span><span class="ts-mv ' + k + '">' + (c.pct > 0 ? '▲ up' : '▼ down') + '</span></span>';
  }

  // US Dollar chip: same parts as the top-bar US Dollar pill (web/macro_week.js::usdPill) -- level, 5-session arrow,
  // risk-range bar with its %, today's move and the Hedgeye outlook badge. Reuses the .mw-usd-* / .msr-rb classes.
  function usdChip(u) {
    var o = (u.outlook || '').toLowerCase();
    var word = o.indexOf('bull') === 0 ? 'Bullish' : o.indexOf('bear') === 0 ? 'Bearish' : o ? 'Neutral' : 'No outlook';
    var oc = o.indexOf('bull') === 0 ? ' ts-ob' : o.indexOf('bear') === 0 ? ' ts-os' : '';
    var has = u.rr_pos != null, pct = has ? Math.round(u.rr_pos * 100) : null;
    var tick = has ? 'calc(3px + (100% - 6px) * ' + Math.min(Math.max(u.rr_pos, 0), 1).toFixed(4) + ')' : '0';
    var bar = has ? '<span class="mw-usd-barwrap"><span class="mw-usd-rr" style="left:' + tick + '">' + pct + '%</span><span class="msr-rb mw-usd-bar"><span class="msr-rb-fill" style="width:' + tick +
      '"></span><span class="msr-rb-tick' + (u.rr_pos >= 0.85 ? ' hot' : u.rr_pos <= 0.15 ? ' cold' : '') + '" style="left:' + tick + '"></span></span></span>' : '';
    var arr = u.chg5 ? '<span class="mw-usd-d ' + (u.chg5 > 0 ? 'ts-ut' : 'ts-dt') + '">' + (u.chg5 > 0 ? '▲' : '▼') + '</span>' : '';
    var dp = u.day_pct;
    var tip = tipRows('US Dollar (DXY)', [['Today', dp == null ? '--' : fpct(dp), dp > 0 ? 'ts-ut' : dp < 0 ? 'ts-dt' : ''],
      ['Hedgeye outlook', u.outlook || '--'], ['Last', num(u.last, 2)],
      ['5-session change', u.chg5 == null ? '--' : sgn(u.chg5) + Math.abs(u.chg5).toFixed(2)],
      ['Position in risk range', has ? pct + '%' : '--']], 'Click to open the Macro Rail.');
    return '<span class="ts-chip mw-usd ts-w6' + oc + (u.day_pct > 0 ? ' mv-up' : u.day_pct < 0 ? ' mv-dn' : '') + '" tabindex="0" data-jump="' + JUMP.cross + '"><span class="mw-usd-l">US DOLLAR</span><b>' + num(u.last, 2) + '</b>' + arr + bar +
      (dp != null ? '<span class="mw-usd-dp ' + (dp > 0 ? 'bull' : dp < 0 ? 'bear' : 'neu') + '">' + fpct(dp) + '</span>' : '') +
      '<span class="mw-usd-o">' + word + '</span><span class="ts-tip">' + tip + '</span></span>';
  }

  // One price chip (VIX-pill look). Used by both lines below.
  var SHORT = { 'HY bonds': 'HYG', 'Nasdaq': 'Nsdq', 'Russell': 'Rus' };   // short chip names; lookups still use the full names
  function priceChip(c) {
      var nm = SHORT[c.name] || c.name;
      var mv = c.bp != null ? fbp(c.bp) : (c.pct != null ? fpct(c.pct) : '');
      var v = c.bp != null ? c.bp : c.pct;
      var tip = tipRows(nm, [['Last', levelText(c)], ['Today', mv, v > 0 ? 'ts-ut' : v < 0 ? 'ts-dt' : ''], ['Hedgeye outlook', c.outlook || '--']], c.stale ? 'This yield is from yesterday: today’s price is not in the data yet.' : 'Click to open the Macro Rail.');
      // Same look as the VIX pill beside the US Dollar pill (.oc-chip2). 2026-11-11, user: the chip's FILL follows today's move (green up, red down);
      // the Hedgeye OUTLOOK is only the 3px left edge. The filled pill is today's move too.
      var o = (c.outlook || '').toLowerCase(), oc = o.indexOf('bull') === 0 ? '' : o.indexOf('bear') === 0 ? ' bear' : ' neu';
      return '<span class="oc-chip2 ts-w4' + (/^(2Y|10Y|30Y|VIX)$/.test(c.name) ? ' ts-tight' : '') + oc + (v > 0 ? ' mv-up' : v < 0 ? ' mv-dn' : '') + '" tabindex="0" data-jump="' + JUMP.cross + '"><b>' + esc(nm) + '</b><span class="oc-lvl">' + esc(levelText(c)) + '</span>' +
        '<span class="oc-ft"><span class="oc-pct ' + (v > 0 ? 'bull' : v < 0 ? 'bear' : 'neu') + '">' + esc(mv) + '</span></span><span class="ts-tip">' + tip + '</span></span>';
  }

  // The Equity chips: Held (breadth of the positions you hold) and Sector breadth (how many of the sector ETFs are up, with 11 small bars).
  function equityChips(d) {
    var o = {};
    var h = d.holdings;
    if (h && h.n) {
      var htip = tipRows('Held: breadth of the positions you hold', [['Up today', String(h.up), 'ts-ut'], ['Down today', String(h.down), 'ts-dt']],
        'Counts the positions you hold across all accounts. Under 50% means fewer than half are up.');
      o.holdings = chip('Held', h.up + ' of ' + h.n + ' up · ' + h.pct + '%', '', (h.pct >= 50 ? ' ts-u' : ' ts-d') + ' ts-w5', htip);
    }
    var secs = d.sectors.slice().sort(function (a, b) { return b.pct - a.pct; });
    if (secs.length) {
      var su = secs.filter(function (x) { return x.pct > 0; }).length;
      var mini = '<span class="ts-mini">' + secs.map(function (x) { return '<i class="' + (x.pct > 0 ? '' : 'off') + '"></i>'; }).join('') + '</span>';
      var stip = tipRows('All ' + secs.length + ' sectors', secs.map(function (x) { return [x.name, fpct(x.pct), x.pct >= 0 ? 'ts-ut' : 'ts-dt']; }), 'Click to open the Sectors panel.');
      o.sector = chip('Sct', su + ' of ' + secs.length + ' up', '', (su * 2 >= secs.length ? ' ts-u' : ' ts-d') + ' ts-w4', stip, JUMP.sector, mini);
    }
    return o;
  }

  // The two top lines (user-directed layout, 2026-11-10). Each line is its own row of chips at their natural width with the same gap
  // between every pair of chips:
  //   Line 1: US Dollar, Stocks, S&P 500, Nasdaq, Russell, BTC, Gold, VIX, HY bonds, Oil, 2Y, 10Y, 30Y, Held
  //   Line 2 (sectorLine): Sct, every sector best to worst, then Defensives, Cyclicals, Momentum, Small caps, Large caps
  //   (The Areas line is switched off for now.)
  function tableHtml(d) {
    var by = {}; d.cross.forEach(function (c) { by[c.name] = c; });
    var pc = function (n) { return by[n] ? priceChip(by[n]) : ''; };
    var eq = equityChips(d);
    var row1 = [d.usd ? usdChip(d.usd) : '', stocksWord(d), pc('S&P 500'), pc('Nasdaq'), pc('Russell'), pc('BTC'), pc('Gold'), pc('VIX'),
      pc('HY bonds'), pc('Oil'), pc('2Y'), pc('10Y'), pc('30Y'), eq.holdings || ''];
    return '<div class="ts-trow">' + row1.join('') + '</div>';
  }

  function sectorLine(d) {
    var eq = equityChips(d);
    // Sector breadth first, then every sector ETF from most positive to most negative (no Best / Worst labels).
    var secs = d.sectors.slice().sort(function (a, b) { return b.pct - a.pct; });
    var th = {}; d.themes.forEach(function (t) { th[t.theme] = t; });
    var factors = ['Defensives', 'Cyclicals', 'Momentum', 'Small caps', 'Large caps'].map(function (n) { return th[n] ? themeChip(th[n], 'ts-w2') : ''; }).join('');
    return (eq.sector || '') + secs.map(function (x) {
      return chip(x.name, '', fpct(x.pct), cls(x.pct) + ' ts-w3', '', JUMP.sector);
    }).join('') + factors;   // the Factors chips close this line
  }

  function themeChip(t, w) {
    var full = RENAME[t.theme] || t.theme, nm = SHORT_THEME[t.theme] || full;
    var tip = tipRows(full + ' · average of ' + t.n + ' symbol' + (t.n === 1 ? '' : 's'),
      t.members.map(function (m) { return [m.s, fpct(m.pct), m.pct >= 0 ? 'ts-ut' : 'ts-dt']; }),
      'Today’s move for the symbols in this Hedgeye theme.');
    return chip(nm, '', fpct(t.avg), cls(t.avg) + ' ' + (w || 'ts-w3'), tip, JUMP[t.theme]);
  }
  function themeChips(list, w) {
    return list.sort(function (a, b) { return b.avg - a.avg; }).map(function (t) { return themeChip(t, w); }).join('');
  }

  function row(label, html, wide) {
    return html ? '<div class="ts-r' + (wide && wide.indexOf('ts-full') >= 0 ? ' ts-rfull' : '') + '"><div class="ts-lab">' + label + '</div><div class="ts-chips' + (wide ? ' ' + wide : '') + '">' + html + '</div></div>' : '';
  }

  function render() {
    var host = document.getElementById('todayStripBody');
    if (!host || !data) return;
    var collapsed = false;
    try { collapsed = localStorage.getItem(KEY) === '1'; } catch (e) { /* storage blocked */ }
    var d = data;
    var factors = d.themes.filter(function (x) { return FACTORS[x.theme]; });
    host.innerHTML =
      '<button type="button" class="ts-btn" id="tsToggle" title="' + (collapsed ? 'Expand' : 'Collapse') + ' the Today panel (prices as of ' +
      esc(d.price_time ? d.price_time.slice(11, 16) : '--') + ')">' + (collapsed ? '▾' : '▴') + '</button>' +
      '<div class="ts-body"' + (collapsed ? ' hidden' : '') + '>' +
      // One line (full width, no labels): US Dollar, Stocks word, cross-assets, Equity chips, Factors. Every chip is 2, 3, 4, 5 or 6 units wide
      // (w2 short, w3 medium, w4 price chips, w5 holdings breadth, w6 US Dollar) on one shared unit grid, so widths follow the content.
      // Below it: Areas.
      '<div class="ts-tab ts-rfull">' + tableHtml(d) + '</div>' +
      '<div class="ts-chips ts-sectors ts-rfull">' + sectorLine(d) + '</div>' +
      // The Areas line (one chip per Hedgeye theme: row('Areas', themeChips(areas, 'ts-w3'), 'ts-units ts-full')) is switched off for now.
      '</div>';
  }

  async function load() {
    var host = document.getElementById('todayStripBody');
    if (!host) return;
    try {
      var dt = currentDate();
      var res = await fetch('/api/cockpit/today-strip' + (dt ? '?date=' + encodeURIComponent(dt) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      data = await res.json();
      render();
    } catch (e) {
      // Show a failed draw too (it used to leave "Loading..." on screen when the data had already arrived).
      if (window.console) console.error('Today panel:', e);
      host.innerHTML = '<div class="msr-loading">Today panel unavailable.</div>';
    }
  }

  function init() {
    var host = document.getElementById('todayStripBody');
    if (!host) return;
    host.addEventListener('click', function (ev) {
      if (ev.target.closest('#tsToggle')) {
        var b = host.querySelector('.ts-body'), h = !b.hidden;
        var tb = ev.target.closest('#tsToggle');
        b.hidden = h; tb.textContent = h ? '▾' : '▴'; tb.title = (h ? 'Expand' : 'Collapse') + ' the Today panel';
        try { localStorage.setItem(KEY, h ? '1' : '0'); } catch (e) { /* storage blocked */ }
        return;
      }
      var c = ev.target.closest('.ts-chip[data-jump]');
      if (c) { var el = document.getElementById(c.getAttribute('data-jump')); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 600);
    setInterval(function () { if (!document.hidden) load(); }, 120000);   // picks up the hourly Yahoo refresh
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
