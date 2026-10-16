/* macro_week.js -- TASK_148 Macro Week Strip on `/`.
 *
 * One line of macro chips at the top of the centre column (#macroWeekStrip in #macroWeekCard) plus a checklist
 * (#macroWeekList) that is hidden (0px) until the "Your book" chip is clicked.
 * Reads GET /api/cockpit/macro-week. Display only (cockpit rule C4).
 * Every state carries a glyph, never colour alone (CVD-safe --mr-* pair).
 */
(function () {
  'use strict';

  var TOP_N = 7;
  var showAll = false;
  var last = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function tip(lines) { return esc(lines.join('\n')); }
  function num(v, dp) { return v == null ? '--' : Number(v).toFixed(dp); }
  function arrow(v) { return v == null ? '' : v > 0 ? '▲' : v < 0 ? '▼' : '–'; }
  // App-wide convention: up = green, down = red, for every instrument (no inversion).
  // Amber is reserved for a warning (watched yield level, elevated/choppy volatility).
  function darr(v) {
    if (v == null || v === 0) return '';
    return '<span class="' + (v > 0 ? 'mw-bull' : 'mw-bear') + '">' + (v > 0 ? '▲' : '▼') + '</span>';
  }
  function qn(label) { var m = /(\d)/.exec(label || ''); return m ? 'Q' + m[1] : '--'; }
  function usd(v) {
    if (v == null) return '--';
    return '$' + Math.round(v).toLocaleString('en-US');
  }
  function dayName(iso) {
    var d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short' });
  }

  // Surrounding colour = Hedgeye outlook (green bullish / red bearish / grey neutral or none),
  // same meaning as the RR strips below. The arrow inside is the 5-session move.
  function olCls(o) {
    var v = (o || '').toLowerCase();
    return v.indexOf('bull') === 0 ? 'mw-bull' : v.indexOf('bear') === 0 ? 'mw-bear' : '';
  }
  function warn(txt) { return ' <span class="mw-amber">' + txt + '</span>'; }

  function chip(cls, html, title) {
    return '<span class="mw-chip ' + cls + '" title="' + tip(title) + '">' + html + '</span>';
  }

  function quadChip(q) {
    var g = q.global ? qn(q.global) + (q.global_stale ? '*' : '') : '--';
    var t = [
      'Quad regime (Hedgeye) -- M monthly, Q quarterly, G global',
      '• Monthly: ' + (q.monthly || 'not set'),
      '• Quarterly: ' + (q.quarterly || 'not set'),
      '• Global: ' + (q.global || 'not set') +
        (q.global_stale ? ' (latest on file is ' + q.global_label + '; current quarter not entered)' : ''),
      'Source: ref_quad_periods (maintained by hand in /ref)'
    ];
    function qb(letter, label, stale) {
      var n = /(\d)/.exec(label || '');
      return '<span class="mw-q mw-q' + (n ? n[1] : 'x') + '">' + letter + (n ? n[1] : '-') + (stale ? '*' : '') + '</span>';
    }
    return chip('', qb('M', q.monthly) + qb('Q', q.quarterly) + qb('G', q.global, q.global_stale), t);
  }

  function dxyChip(c) {
    var pos = c.rr_pos == null ? '--' : Math.round(c.rr_pos * 100) + '%';
    var t = [
      'US dollar index',
      '• Last: ' + num(c.last, 2),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2)),
      '• Position in risk range (LRR to TRR): ' + pos,
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      'Source: drv_quote, drv_rr ($DXY)'
    ];
    return chip(olCls(c.outlook), 'DXY ' + num(c.last, 1) + darr(c.chg5) + '<span class="mw-dim"> ' + pos + '</span>', t);
  }

  // US Dollar pill (second card, right end): outlook word, DXY level, 5-session move, and where price sits in its risk range.
  function usdPill(c) {
    if (!c) return '';
    var o = (c.outlook || '').toLowerCase();
    var word = o.indexOf('bull') === 0 ? 'Bullish' : o.indexOf('bear') === 0 ? 'Bearish' : o ? 'Neutral' : 'No outlook';
    var has = c.rr_pos != null;
    var pct = has ? Math.round(c.rr_pos * 100) : null;
    var tickPos = has ? 'calc(3px + (100% - 6px) * ' + Math.min(Math.max(c.rr_pos, 0), 1).toFixed(4) + ')' : '0';
    var bar = has
      ? '<span class="msr-rb mw-usd-bar"><span class="msr-rb-fill" style="width:' + tickPos + '"></span><span class="msr-rb-tick' +
        (c.rr_pos >= 0.85 ? ' hot' : c.rr_pos <= 0.15 ? ' cold' : '') + '" style="left:' + tickPos + '"></span></span>'
      : '';
    var t = [
      'US Dollar (DXY)',
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      '• Last: ' + num(c.last, 2),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2)),
      '• Position in risk range (LRR to TRR): ' + (has ? pct + '%' : '--'),
      'Source: drv_quote, drv_rr ($DXY)'
    ];
    return '<span class="mw-chip mw-usd ' + olCls(c.outlook) + '" title="' + tip(t) + '"><span class="mw-usd-l">US DOLLAR</span>' +
      '<b>' + num(c.last, 2) + '</b>' + darr(c.chg5) + bar + (has ? '<span class="mw-dim">' + pct + '%</span>' : '') +
      '<span class="mw-usd-o">' + word + '</span></span>';
  }

  function yieldChip(name, c, src) {
    var hi = c.above_level;
    var t = [
      name + ' Treasury yield',
      '• Level: ' + num(c.pct, 2) + '%',
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2) + ' pts'),
      '• Watched level: ' + (c.level == null ? '--' : num(c.level, 2) + '%') + (hi ? ' (at or above it)' : ''),
      'Source: ' + src + ', ref_level_watch'
    ];
    return chip(olCls(c.outlook),
      name + ' ' + num(c.pct, 2) + '%' + darr(c.chg5) + (hi ? warn('⚠') : ''), t);
  }

  function tnxChip(c) {
    var hi = c.above_level;
    var t = [
      '10-year Treasury yield',
      '• Level: ' + num(c.pct, 2) + '%',
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2) + ' pts'),
      '• Watched level: ' + (c.level == null ? '--' : num(c.level, 2) + '%') + (hi ? ' (at or above it)' : ''),
      'Source: drv_quote TNX:CGI (stored x10; shown as %), ref_level_watch'
    ];
    return chip(olCls(c.outlook),
      '10Y ' + num(c.pct, 2) + '%' + darr(c.chg5) + (hi ? warn('⚠') : ''), t);
  }

  function cmdtyChip(name, c, src) {
    var pos = c.rr_pos == null ? '--' : Math.round(c.rr_pos * 100) + '%';
    var t = [
      name,
      '• Last: ' + num(c.last, 2),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2)),
      '• Position in risk range (LRR to TRR): ' + pos,
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      'Source: drv_quote, drv_rr (' + src + ')'
    ];
    return chip(olCls(c.outlook),
      (name === 'Gold' ? 'Gold ' + Math.round(c.last).toLocaleString('en-US') : 'WTI ' + num(c.last, 2)) +
      darr(c.chg5) + '<span class="mw-dim"> ' + pos + '</span>', t);
  }

  function volChip(name, c, dp) {
    var b = c.bucket;
    var glyph = b === 'elevated' ? warn('⚠') : b === 'chop' ? warn('◆') : '';
    var cls = olCls(c.outlook);
    var t = [
      name + ' volatility',
      '• Level: ' + num(c.last, dp),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, dp)),
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      '• Bucket: ' + (b || '--') + (c.low != null ? ' (calm below ' + c.low + ', elevated from ' + c.high + ')' : ''),
      'Source: drv_quote, ref_vol_threshold'
    ];
    var word = b === 'elevated' ? ' high' : b === 'chop' ? ' chop' : '';
    return chip(cls, name + ' ' + num(c.last, dp) + darr(c.chg5) + word + glyph, t);
  }

  function eventChip(events) {
    var major = events.filter(function (e) { return e.major; });
    if (!major.length) return '';
    var first = major[0];
    var same = major.filter(function (e) { return e.date === first.date; }).length - 1;
    var when = first.days === 0 ? 'today' : dayName(first.date);
    var t = ['Next 7 days (day only -- no release times on file)'].concat(
      events.map(function (e) { return '• ' + dayName(e.date) + ' ' + e.date.slice(5) + ' ' + e.name; }),
      ['Source: ref_calendar_event']);
    return chip('mw-ev', '⚑ ' + esc(first.name) + ' ' + when + (same > 0 ? ' +' + same : ''), t);
  }

  function bookChip(counts, hotN, hot, open) {
    var t = [
      'Your book vs your signals -- two separate checks',
      'Quad vs HE outlook (▲ ▼ ◆):',
      '• Aligned: Quad tailwind and HE outlooks bullish',
      '• Against: Quad headwind and HE outlooks bearish',
      '• Mixed: they disagree, or no HE outlook on file',
      'Risk range (⚠):',
      '• Holdings priced at or above ' + Math.round(hot * 100) + '% of their risk range (stretched)',
      'Click to ' + (open ? 'hide' : 'show') + ' the per-holding list'
    ];
    function cnt(cls, glyph, n) {
      return '<span class="' + cls + (n ? '' : ' mw-zero') + '">' + glyph + n + '</span>';
    }
    return '<button type="button" class="mw-chip mw-book" id="mwBookBtn" aria-expanded="' + open +
      '" title="' + tip(t) + '"><b>Book</b> ' + cnt('mw-cnt-up', '▲', counts.aligned) + ' ' +
      cnt('mw-cnt-dn', '▼', counts.against) + ' ' + cnt('mw-cnt-mx', '◆', counts.mixed) +
      ' <span class="mw-sep">|</span> ' + cnt('mw-cnt-hot', '⚠', hotN) + ' ' + (open ? '▾' : '▸') + '</button>';
  }

  function heCell(h) {
    var g = h.he.map(function (x) { return x === 'up' ? '▲' : x === 'dn' ? '▼' : x === 'flat' ? '–' : '–'; }).join('');
    var txt = h.he_n ? h.he_bull + '/' + h.he_n + ' bull' : 'no HE';
    var t = ['Hedgeye outlooks: RR / CALL / ETF / II / SSS (signal strength) / PS / GOANY (on the list = bullish)',
      '• ' + h.he.map(function (x, i) {
        return ['RR', 'CALL', 'ETF', 'II', 'SSS', 'PS', 'GOANY'][i] + ' ' + (x === 'up' ? 'bullish' : x === 'dn' ? 'bearish' : x === 'flat' ? 'neutral' : 'none');
      }).join('\n• ')];
    if (!h.he_n) g = '–––––––';
    return '<td title="' + tip(t) + '"><span class="mw-he">' + g + '</span> <span class="mw-dim">' + txt + '</span></td>';
  }

  var VERDICT = {
    aligned: ['mw-bull', '▲ aligned'],
    against: ['mw-bear', '▼ against'],
    mixed: ['mw-warn', '◆ mixed']
  };

  function rowHtml(h) {
    var fit = h.fit === 'tailwind' ? '<span class="mw-bull">▲ tailwind</span>'
      : h.fit === 'headwind' ? '<span class="mw-bear">▼ headwind</span>' : '<span class="mw-dim">– none</span>';
    var pos = h.range_pos == null ? '--' : Math.round(h.range_pos * 100) + '%';
    var rng = '<span class="' + (h.hot ? 'mw-warn' : '') + '">' + pos + (h.hot ? ' ⚠' : '') + '</span>';
    var v = VERDICT[h.verdict];
    return '<tr><td><b>' + esc(h.symbol) + '</b></td><td class="mw-num">' + usd(h.value) + '</td>' +
      '<td title="' + tip(['Quad fit', '• MacroNet: ' + num(h.macronet, 2), 'Source: drv_macro_score']) + '">' + fit + '</td>' +
      heCell(h) + '<td class="' + v[0] + '">' + v[1] + '</td>' +
      '<td title="Position between LRR (0%) and TRR (100%); warning at or above the hot cut-off">' + rng + '</td></tr>';
  }

  function listHtml(data) {
    var hs = data.holdings;
    var shown = showAll ? hs : hs.slice(0, TOP_N);
    var more = hs.length - TOP_N;
    var evs = data.events.length
      ? data.events.map(function (e) {
        return '<div>' + (e.major ? '⚑ ' : '') + '<b>' + dayName(e.date) + '</b> ' + esc(e.name) + '</div>';
      }).join('')
      : '<div class="mw-dim">Nothing scheduled</div>';
    return '<div class="mw-list-grid"><div class="mw-list-main">' +
      '<table class="mw-tbl"><thead><tr><th>Holding</th><th>$ held</th><th>Quad fit</th><th>HE outlooks</th><th>Quad vs HE outlook</th><th>Risk range</th></tr></thead><tbody>' +
      shown.map(rowHtml).join('') + '</tbody></table>' +
      (more > 0 ? '<button type="button" class="mw-more" id="mwMoreBtn">' +
        (showAll ? 'show top ' + TOP_N : 'show all ' + hs.length) + '</button>' : '') +
      '</div><div class="mw-list-side"><div class="mw-side-h">Next 7 days</div>' + evs + '</div></div>';
  }

  // Three Quad cards on the left column (index.html #quadCardsPanel), below MKT SIT.
  function renderQuadCards(data) {
    var el = document.getElementById('quadCardsPanel');
    if (!el || !data.quad) return;
    var q = data.quad, d = new Date((data.as_of || '') + 'T00:00:00');
    var M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var yy = function (y) { return String(y).slice(-2); };
    var qtr = isNaN(d) ? '' : (Math.floor(d.getMonth() / 3) + 1) + 'Q' + yy(d.getFullYear()) + 'E';
    var mon = isNaN(d) ? '' : M[d.getMonth()] + '-' + yy(d.getFullYear());
    var gm = /Q(\d)\s+(\d{4})/.exec(q.global_label || '');
    var gq = gm ? gm[1] + 'Q' + yy(gm[2]) + 'E' : qtr;
    function card(label, quad, period) {
      var n = /(\d)/.exec(quad || '');
      return '<div class="qc' + (n ? ' q' + n[1] : '') + '"><div class="qc-lbl">' + label + '</div>' +
        '<div class="qc-val">' + (n ? 'Quad ' + n[1] + ' ' + period : '--') + '</div></div>';
    }
    el.innerHTML = card('US Quarterly', q.quarterly, qtr) + card('US Monthly', q.monthly, mon) + card('Global', q.global, gq);
    el.hidden = false;
  }

  function render(data) {
    var strip = document.getElementById('macroWeekStrip');
    var list = document.getElementById('macroWeekList');
    if (!strip || !list) return;
    var open = !list.hidden;
    var c = data.chips;
    // Grouped like the Outlook changes strip, but with a gap instead of a text label (label kept as a hover title).
    var grp = function (label, chips) {
      var h = chips.filter(Boolean).join('');
      return h ? '<span class="oc-grp oc-grp-gap" title="' + label + '">' + h + '</span>' : '';
    };
    strip.innerHTML = [
      // Market chips (DXY/2Y/10Y/VIX/MOVE/Gold/WTI) dropped 2026-10-16: those symbols are on the Macro Rail.
      grp('Next event', [eventChip(data.events)]),
      grp('Book', [data.holdings.length ? bookChip(data.counts, data.hot_count, data.hot_pct, open) : ''])
    ].join('');
    var usdEl = document.getElementById('usdPill');
    if (usdEl) usdEl.innerHTML = usdPill(c.dxy);
    strip.hidden = !strip.innerHTML;
    if (window.syncOcCard) window.syncOcCard();
    renderQuadCards(data);
    list.innerHTML = open ? listHtml(data) : '';
    if (open) placeList(list);
    var btn = document.getElementById('mwBookBtn');
    if (btn) btn.addEventListener('click', function () {
      list.hidden = !list.hidden;
      render(last);
    });
    var more = document.getElementById('mwMoreBtn');
    if (more) more.addEventListener('click', function () { showAll = !showAll; render(last); });
  }

  // The checklist opens as a popover under the strip, left-aligned to it -- 0px when closed.
  function placeList(list) {
    var r = document.getElementById('outlookChangesCard').getBoundingClientRect();
    var w = Math.min(Math.max(r.width, 560), window.innerWidth - 24);
    list.style.top = Math.round(r.bottom + 4) + 'px';
    list.style.left = Math.max(12, Math.min(Math.round(r.left), window.innerWidth - w - 12)) + 'px';
    list.style.width = w + 'px';
  }

  function closeList() {
    var list = document.getElementById('macroWeekList');
    if (list && !list.hidden) { list.hidden = true; if (last) render(last); }
  }

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  async function load() {
    var strip = document.getElementById('macroWeekStrip');
    if (!strip) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/macro-week' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      last = await res.json();
      render(last);
    } catch (e) {
      strip.hidden = true;
      if (window.syncOcCard) window.syncOcCard();
      var list = document.getElementById('macroWeekList');
      if (list) list.hidden = true;
    }
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeList(); });
    document.addEventListener('mousedown', function (e) {
      if (!e.target.closest('#macroWeekList') && !e.target.closest('#mwBookBtn')) closeList();
    });
    window.addEventListener('resize', function () {
      var l = document.getElementById('macroWeekList'); if (l && !l.hidden) placeList(l);
    });
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
