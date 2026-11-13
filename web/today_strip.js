/* Today panel -- top of the middle column, above the US Dollar / events / outlook-change bar.
 * One-glance read of how the market is going today: headline words, cross-asset moves, equity breadth,
 * factors and areas. Display only; never feeds rules or the Final Call.
 * Data: GET /api/cockpit/today-strip (drv_quote on the anchor date + ref_symbol_theme members). */
(function () {
  'use strict';
  var FACTORS = { 'Momentum': 1, 'Defensives': 1, 'Large caps': 1, 'Cyclicals': 1, 'Small caps': 1 };
  var RENAME = { 'Duration': 'Bonds', 'Tech/software': 'Software' };
  var SHORT_THEME = { 'Momentum': 'Mtum', 'Defensives': 'Def', 'Cyclicals': 'Cyc', 'Small caps': 'Small', 'Large caps': 'Large' };
  var SHORT_SECTOR = { 'Financials': 'Fin', 'Energy': 'Enrg', 'Healthcare': 'Hlth', 'Discretionary': 'Disc', 'Staples': 'Stpl', 'Utilities': 'Util', 'Industrials': 'Indu', 'Materials': 'Matl', 'Real estate': 'RE', 'Comm. svcs': 'Comm' };   // second-line chip names; hover has the full name   // short chip names; the hover keeps the full name
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

  // US Dollar chip: same parts as the top-bar US Dollar pill (web/macro_week.js::usdPill) -- level, 5-session arrow,
  // risk-range bar with its %, today's move and the Hedgeye outlook badge. Reuses the .mw-usd-* / .msr-rb classes.
  function usdChip(u) {
    var o = (u.outlook || '').toLowerCase();
    var word = o.indexOf('bull') === 0 ? 'Bullish' : o.indexOf('bear') === 0 ? 'Bearish' : o ? 'Neutral' : 'No outlook';
    var oc = o.indexOf('bull') === 0 ? ' ts-ob' : o.indexOf('bear') === 0 ? ' ts-os' : '';
    var has = u.rr_pos != null, pct = has ? Math.round(u.rr_pos * 100) : null;
    var tick = has ? (Math.min(Math.max(u.rr_pos, 0), 1) * 100).toFixed(2) + '%' : '0';
    var bar = rrPct(u.rr_pos);   // plain % next to the price, no bar (2026-11-12)
    var arr = u.chg5 ? '<span class="mw-usd-d ' + (u.chg5 > 0 ? 'ts-ut' : 'ts-dt') + '">' + (u.chg5 > 0 ? '▲' : '▼') + '</span>' : '';
    var dp = u.day_pct;
    var tip = tipRows('US Dollar (DXY)', [['Today', dp == null ? '--' : fpct(dp), dp > 0 ? 'ts-ut' : dp < 0 ? 'ts-dt' : ''],
      ['Hedgeye outlook', u.outlook || '--'], ['Last', num(u.last, 2)],
      ['5-session change', u.chg5 == null ? '--' : sgn(u.chg5) + Math.abs(u.chg5).toFixed(2)],
      ['Position in risk range', has ? pct + '%' : '--']], 'Click to open the Macro Rail.');
    return '<span class="ts-chip mw-usd ts-w6' + oc + (u.day_pct > 0 ? ' mv-up' : u.day_pct < 0 ? ' mv-dn' : '') + '" tabindex="0" data-jump="' + JUMP.cross + '"><span class="mw-usd-l">USD</span><b>' + num(u.last, 2) + '</b>' + bar + arr +
      (dp != null ? '<span class="mw-usd-dp ' + (dp > 0 ? 'bull' : dp < 0 ? 'bear' : 'neu') + '">' + fpct(dp) + '</span>' : '') +
      '<span class="mw-usd-o">' + word + '</span><span class="ts-tip">' + tip + '</span></span>';
  }

  // Risk-range bar (0% = low range line, 100% = high range line) -- same look as the US Dollar chip's bar. Only the S&P 500 chip carries one.
  function rrBar(pos, price) {
    if (pos == null) return '';
    var tick = (Math.min(Math.max(pos, 0), 1) * 100).toFixed(2) + '%';
    return '<span class="mw-usd-barwrap' + (price ? ' has-px' : '') + '">' + (price ? '<span class="mw-usd-row"><span class="mw-usd-px">' + esc(price) + '</span>' : '') + '<span class="mw-usd-rr" style="left:' + tick + '">' + Math.round(pos * 100) + '%</span>' + (price ? '</span>' : '') + '<span class="msr-rb mw-usd-bar"><span class="msr-rb-fill' + (pos >= 0.85 ? ' hot' : pos <= 0.15 ? ' cold' : '') + '" style="width:' + tick +
      '"></span><span class="msr-rb-tick' + (pos >= 0.85 ? ' hot' : pos <= 0.15 ? ' cold' : '') + '" style="left:' + tick + '"></span></span></span>';
  }
  // S&P chip: the risk-range position as a plain % next to the price (no bar). Red at 85%+, green at 15%-, grey between.
  function rrPct(pos) {
    if (pos == null) return '';
    return '<span class="mw-usd-rrp' + (pos >= 0.85 ? ' hot' : pos <= 0.15 ? ' cold' : '') + '">' + Math.round(pos * 100) + '%</span>';
  }
  // Each chip's own volatility gauge (the Macro Rail's Volatility panel). When that gauge is NOT in the Investable zone, the chip gets a small
  // warning tag (Chop = amber, Elevated = red). Filled from d.vol at the start of tableHtml.
  var VMAP = { 'S&P 500': 'VIX', 'Nasdaq': 'VXN', 'DJIA': 'VXD', 'Russell': 'RVX', 'Gold': 'GVZ', 'Oil': 'OVX', '2Y': 'MOVE', '10Y': 'MOVE', '30Y': 'MOVE' };
  var VZONE = {};
  function volTag(name) {
    var g = VMAP[name], z = g && VZONE[g];
    if (!z || z.zone === 'investable') return '';
    var short = z.zone === 'elevated' ? 'Elev' : 'Chop';
    return '<span class="ts-vz ' + z.zone + '" title="' + esc(g + ' ' + z.last + ' is ' + (z.zone === 'elevated' ? 'Elevated' : 'in Chop') + ' (not investable)') + '">⚠ ' + short + '</span>';
  }
  // One price chip (VIX-pill look). Used by both lines below.
  var SHORT = { 'DJIA': 'DJI', 'S&P 500': 'S&P', 'HY bonds': 'HYG', 'Nasdaq': 'Nq', 'Russell': 'Rus' };   // short chip names; lookups still use the full names
  function priceChip(c) {
      var nm = SHORT[c.name] || c.name;
      var mv = c.bp != null ? fbp(c.bp) : (c.pct != null ? fpct(c.pct) : '');
      var v = c.bp != null ? c.bp : c.pct;
      var tip = tipRows(nm, [['Last', levelText(c)], ['Today', mv, v > 0 ? 'ts-ut' : v < 0 ? 'ts-dt' : ''], ['Hedgeye outlook', c.outlook || '--']], c.stale ? 'This yield is from yesterday: today’s price is not in the data yet.' : 'Click to open the Macro Rail.');
      // Same look as the VIX pill beside the US Dollar pill (.oc-chip2). 2026-11-11, user: the chip's FILL follows today's move (green up, red down);
      // the Hedgeye OUTLOOK is only the 3px left edge. The filled pill is today's move too.
      var o = (c.outlook || '').toLowerCase(), oc = o.indexOf('bull') >= 0 ? '' : o.indexOf('bear') >= 0 ? ' bear' : ' neu';   // 'Mild Bearish' (Dow) counts as bearish
      return '<span class="oc-chip2 ts-w4' + (/^(2Y|10Y|30Y|VIX)$/.test(c.name) ? ' ts-tight' : '') + oc + (v > 0 ? ' mv-up' : v < 0 ? ' mv-dn' : '') + '" tabindex="0" data-jump="' + JUMP.cross + '"><b>' + esc(nm) + '</b>' + '<span class="oc-lvl">' + esc(levelText(c)) + '</span>' + rrPct(c.rr_pos) + volTag(c.name) +
        '<span class="oc-ft"><span class="oc-pct ' + (v > 0 ? 'bull' : v < 0 ? 'bear' : 'neu') + '">' + esc(mv) + '</span></span><span class="ts-tip">' + tip + '</span></span>';
  }

  // The Equity chips: Held (breadth of the positions you hold) and Sector breadth (how many of the sector ETFs are up, with 11 small bars).
  // "2▲ 9▼": the up count in green, the down count in red.
  function udHtml(up, dn) {
    // Only the dominant side is coloured (more up = green up count, more down = red down count); the other side, and a tie, stay black.
    return '<span class="ts-ud"><b class="' + (up > dn ? 'ts-ut' : '') + '">' + up + '▲</b> <b class="' + (dn > up ? 'ts-dt' : '') + '">' + dn + '▼</b></span>';
  }
  function equityChips(d) {
    var o = {};
    var h = d.holdings;
    if (h && h.n) {
      var htip = tipRows('Held: breadth of the positions you hold', [['Up today', String(h.up), 'ts-ut'], ['Down today', String(h.down), 'ts-dt']],
        'Counts the positions you hold across all accounts. Under 50% means fewer than half are up.');
      o.holdings = chip('Held', '', '', (h.pct >= 50 ? ' ts-u' : ' ts-d') + ' ts-w5', htip, null, udHtml(h.up, h.down) + ' <span class="ts-hp">' + h.pct + '%</span>');
    }
    var secs = d.sectors.slice().sort(function (a, b) { return b.pct - a.pct; });
    if (secs.length) {
      var su = secs.filter(function (x) { return x.pct > 0; }).length;
      var mini = '<span class="ts-mini">' + secs.map(function (x) { return '<i class="' + (x.pct > 0 ? '' : 'off') + '"></i>'; }).join('') + '</span>';
      var stip = tipRows('All ' + secs.length + ' sectors', secs.map(function (x) { return [x.name, fpct(x.pct), x.pct >= 0 ? 'ts-ut' : 'ts-dt']; }), 'Click to open the Sectors panel.');
      o.sector = chip('Sct', '', '', (su * 2 >= secs.length ? ' ts-u' : ' ts-d') + ' ts-w4', stip, JUMP.sector, udHtml(su, secs.length - su) + mini);
    }
    // Stocks: S&P, Nasdaq and Russell today (3 bars), same look as Sct; green when at least half are up.
    var idx = ['S&P 500', 'Nasdaq', 'Russell'].map(function (n) { return (d.cross || []).filter(function (c) { return c.name === n && c.pct != null; })[0]; }).filter(Boolean);
    if (idx.length) {
      var iu = idx.filter(function (x) { return x.pct > 0; }).length;
      var imini = '<span class="ts-mini">' + idx.map(function (x) { return '<i class="' + (x.pct > 0 ? '' : 'off') + '"></i>'; }).join('') + '</span>';
      var itip = tipRows('Stocks: main indexes', idx.map(function (x) { return [SHORT[x.name] || x.name, fpct(x.pct), x.pct >= 0 ? 'ts-ut' : 'ts-dt']; }), 'S&P 500, Nasdaq and Russell. A bar is lit when the index is up today.');
      o.stocks = chip('Stk', '', '', (iu * 2 >= idx.length ? ' ts-u' : ' ts-d') + ' ts-w4', itip, JUMP.cross, udHtml(iu, idx.length - iu) + imini);
    }
    // FX breadth: currencies vs the US dollar. Lit bar = that currency is up vs USD. Green when at least half are up (dollar weak), red otherwise (dollar strong).
    var fx = d.fx || [];
    if (fx.length) {
      var fu = fx.filter(function (x) { return x.pct > 0; }).length;
      var fmini = '<span class="ts-mini">' + fx.map(function (x) { return '<i class="' + (x.pct > 0 ? '' : 'off') + '"></i>'; }).join('') + '</span>';
      var ftip = tipRows('Currencies vs the US dollar', fx.map(function (x) { return [x.name, fpct(x.pct), x.pct >= 0 ? 'ts-ut' : 'ts-dt']; }),
        'EUR, GBP, CAD, JPY from futures; AUD, CHF from ETFs. A bar is lit when the currency is up against the dollar today.');
      o.fx = chip('FX', '', '', (fu * 2 >= fx.length ? ' ts-u' : ' ts-d') + ' ts-w4', ftip, JUMP.cross, udHtml(fu, fx.length - fu) + fmini);
    }
    return o;
  }

  // The two top lines (user-directed layout, 2026-11-10). Each line is its own row of chips at their natural width with the same gap
  // between every pair of chips:
  //   Line 1: US Dollar, S&P, Nasdaq, Russell, DJIA, BTC, Gold, VIX, HY bonds, Oil, 2Y, 10Y, 30Y, Held
  //   Line 2 (sectorLine): Sct, every sector best to worst, then Defensives, Cyclicals, Momentum, Small caps, Large caps
  //   (The Areas line is switched off for now.)
  function tableHtml(d) {
    VZONE = {}; (d.vol || []).forEach(function (x) { if (x.zone) VZONE[x.name] = x; });
    var by = {}; d.cross.forEach(function (c) { by[c.name] = c; });
    var pc = function (n) { return by[n] ? priceChip(by[n]) : ''; };
    var eq = equityChips(d);
    // Two lines on one 13-column grid (user layout 2026-11-12); each chip on line 2 sits under its line-1 partner:
    //   USD   S&P  Nq   Russell DJIA Gold Oil  2Y   10Y 30Y HYG BTC
    //   Held  VIX  VXN  RVX     VXD  GVZ  OVX  MOVE
    var no = '<span></span>';
    var row1 = [d.usd ? usdChip(d.usd) : no, pc('S&P 500'), pc('Nasdaq'), pc('Russell'), pc('DJIA'), pc('Gold'), pc('Oil'), pc('2Y'), pc('10Y'), pc('BTC')];
    var row2 = [((eq.stocks || '') + (eq.holdings || '')) ? '<span class="ts-pair">' + (eq.stocks || '') + (eq.holdings || '') + '</span>' : no, pc('VIX'), pc('VXN'), pc('RVX'), pc('VXD'), pc('GVZ'), pc('OVX'), pc('MOVE'), pc('30Y'), pc('HY bonds')];
    while (row1.length < 12) row1.push(no);
    while (row2.length < 12) row2.push(no);
    // Line 3 shares the grid: Sct + FX in column 1, the sectors and style chips start in column 2, so the first sector chip (Enrg) lines up with S&P / VIX above.
    var sl = sectorLine(d);
    var row3 = '<span class="ts-pair">' + sl.pair + '</span><span class="ts-chips ts-sectors ts-srest">' + sl.secs + sl.factors + '<span id="macroBookStrip" class="mw-strip" hidden></span></span>';   // sectors, styles, then the Book chip (macro_week.js fills #macroBookStrip)
    return '<div class="ts-trow ts-tgrid">' + row1.join('') + row2.join('') + row3 + '</div>';
  }

  function sectorLine(d) {
    var by = {}; d.cross.forEach(function (c) { by[c.name] = c; });
    var eq = equityChips(d);
    // Sector breadth first, then every sector ETF from most positive to most negative (no Best / Worst labels).
    var secs = d.sectors.slice().sort(function (a, b) { return b.pct - a.pct; });
    var th = {}; d.themes.forEach(function (t) { th[t.theme] = t; });
    var factors = ['Defensives', 'Cyclicals', 'Momentum', 'Small caps', 'Large caps'].map(function (n) { return th[n] ? themeChip(th[n], 'ts-w2') : ''; }).join('');
    var pair = (eq.sector || '') + (eq.fx || '');
    var restSecs = secs.map(function (x) {
      var so = (x.outlook || '').toLowerCase();   // left edge = Hedgeye outlook (same as the price chips); the fill and the move colour follow today's move
      return chip(SHORT_SECTOR[x.name] || x.name, '', fpct(x.pct), cls(x.pct) + ' ts-w3' + (so.indexOf('bull') >= 0 ? ' ts-ol-bull' : so.indexOf('bear') >= 0 ? ' ts-ol-bear' : ' ts-ol-neu'), tipRows(x.name, [['Today', fpct(x.pct), x.pct >= 0 ? 'ts-ut' : 'ts-dt']], 'Click to open the Sectors panel.'), JUMP.sector);
    }).join('');
    return { pair: pair, secs: restSecs, factors: factors };   // the style (factor) chips start under the 2Y / MOVE column
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
    var d = data;
    var factors = d.themes.filter(function (x) { return FACTORS[x.theme]; });
    host.innerHTML =
      '<div class="ts-body">' +
      // One line (full width, no labels): US Dollar, Stocks word, cross-assets, Equity chips, Factors. Every chip is 2, 3, 4, 5 or 6 units wide
      // (w2 short, w3 medium, w4 price chips, w5 holdings breadth, w6 US Dollar) on one shared unit grid, so widths follow the content.
      // Below it: Areas.
      '<div class="ts-tab ts-rfull">' + tableHtml(d) + '</div>' +
      // The Areas line (one chip per Hedgeye theme: row('Areas', themeChips(areas, 'ts-w3'), 'ts-units ts-full')) is switched off for now.
      '</div>';
    if (window.mwRender) window.mwRender();   // the Book chip lives inside this panel, so redraw it after every render
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
