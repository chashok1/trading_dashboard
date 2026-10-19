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
    var dp = c.day_pct, dpCls = dp > 0 ? 'bull' : dp < 0 ? 'bear' : 'neu';
    var bar = has
      ? '<span class="mw-usd-barwrap"><span class="mw-usd-rr" style="left:' + tickPos + '">' + pct + '%</span><span class="msr-rb mw-usd-bar"><span class="msr-rb-fill" style="width:' + tickPos + '"></span><span class="msr-rb-tick' +
        (c.rr_pos >= 0.85 ? ' hot' : c.rr_pos <= 0.15 ? ' cold' : '') + '" style="left:' + tickPos + '"></span></span></span>'
      : '';
    var t = [
      'US Dollar (DXY)',
      '• Today: ' + (dp == null ? '--' : (dp > 0 ? '+' : '') + dp.toFixed(2) + '%'),
      '• Hedgeye outlook: ' + (c.outlook || '--'),
      '• Last: ' + num(c.last, 2),
      '• 5-session change: ' + (c.chg5 == null ? '--' : (c.chg5 > 0 ? '+' : '') + num(c.chg5, 2)),
      '• Position in risk range (LRR to TRR): ' + (has ? pct + '%' : '--'),
      'Source: drv_quote, drv_rr ($DXY)'
    ];
    return '<span class="mw-chip mw-usd ' + olCls(c.outlook) + '" title="' + tip(t) + '"><span class="mw-usd-l">US DOLLAR</span>' +
      '<b>' + num(c.last, 2) + '</b>' + (darr(c.chg5) ? '<span class="mw-usd-d">' + darr(c.chg5) + '</span>' : '') + bar + (dp != null ? '<span class="mw-usd-dp ' + dpCls + '">' + (dp > 0 ? '+' : '') + dp.toFixed(2) + '%</span>' : '') +
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

  // ---- Quad market check (2026-10-19): what the market DATA says the Quad is, as four small bars + a click-through factor list.
  // Reads quad_check from /api/cockpit/macro-week and /api/cockpit/quad-check (etl/derive_quad_check.py, DESIGN_SPEC_8.md). Display only.
  var QM_WORD = { HOLDING: 'holding', WATCH: 'watch', TRANSITION: 'transition likely', NO_DATA: 'not enough data', NO_REF: '' };
  function marketBlock(data) {
    var m = data.quad_check;
    if (!m) return '';
    if (m.fit == null) return '<div class="qm" id="qmBlock"><b>Market reads</b> <span class="mw-dim">not enough data</span></div>';
    var qs = m.market_quads || [];
    var read = qs.length === 1 ? 'Quad ' + qs[0] : qs.length >= 4 ? 'unclear' : 'Quad ' + qs.join(' or ');
    var word = QM_WORD[m.label] || '';
    var cap = word ? word.charAt(0).toUpperCase() + word.slice(1) : '';
    var tag = word ? '<span class="qm-tag qm-' + String(m.label).toLowerCase() + '" title="Transition risk 0-100 and its label: under 40 Holding, 40-59 Watch, 60 and over Transition likely">' +
      (m.risk != null ? Math.round(m.risk) + ' - ' : '') + cap + '</span>' : '';
    var bars = [1, 2, 3, 4].map(function (k) {
      var pct = Number((m.fit || {})[String(k)] || 0);
      return '<span class="qm-bar q' + k + (qs.indexOf(k) >= 0 ? ' lead' : '') + '"><span class="qm-bl">Q' + k + '</span><span class="qm-bt"><i style="width:' +
        Math.max(2, Math.min(100, pct)) + '%"></i></span><span class="qm-bp">' + pct + '</span></span>';
    }).join('');
    var lines = ['Market check -- what the data says the Quad is (indicative)'].concat((m.lines || []).map(function (l) { return '• ' + l; }));
    lines.push('• Bars: fit of each Quad to the growth and inflation meters');
    if (m.target_quad && m.ref_quad && m.target_quad !== m.ref_quad) lines.push('• Leaning from Quad ' + m.ref_quad + ' toward Quad ' + m.target_quad);
    lines.push('Click for the factor list');
    return '<div class="qm" id="qmBlock" title="' + tip(lines) + '"><div class="qm-head"><b>Market reads</b> <span class="qm-read">' + read + '</span> ' + tag +
      '<span class="qm-go">▸</span></div><div class="qm-bars">' + bars + '</div></div>';
  }

  function fmtMove(v, unit) {
    if (v == null) return '–';
    var sg = v > 0 ? '+' : '';
    return unit === 'bp' ? sg + Math.round(v) + ' bp' : unit === 'pts' ? sg + v.toFixed(1) + ' pts' : sg + v.toFixed(1) + '%';
  }
  // Colors a check by the vote it casts (same band + direction rule as the Says column), not by the raw sign of the move.
  function voteCls(v) { return v == null ? '' : v > 0 ? 'mw-bull' : v < 0 ? 'mw-bear' : 'mw-amber'; }
  function moveCls(mv, band, dirn) {
    if (mv == null || band == null) return '';
    return voteCls((mv > band ? 1 : mv < -band ? -1 : 0) * (dirn || 1));
  }
  function saysCell(f) {
    if (f.stale_since) return '<span class="mw-dim" title="stale since ' + esc(f.stale_since) + '">– stale</span>';
    if (f.state == null) return '<span class="mw-dim">–</span>';
    return f.state > 0 ? '<span class="mw-bull">▲ up</span>' : f.state < 0 ? '<span class="mw-bear">▼ down</span>' : '<span class="mw-amber">◆ mixed</span>';
  }
  var FAMILIES = { 1: 'Risk & liquidity', 2: 'Inflation & commodities', 3: 'Growth, credit & cyclicals' };
  function popHtml(d) {
    var m = d.summary;
    if (!m) return '<div class="mw-dim">No Quad market check yet.</div>';
    var meterRow = function (name, v, rd) {
      var w = v == null ? 0 : Math.min(50, Math.abs(v) / 2);
      return '<div class="qm-m"><span class="qm-mn">' + name + '</span><span class="qm-mt"><i class="' + (v != null && v < 0 ? 'neg' : 'pos') + '" style="' +
        (v != null && v < 0 ? 'right:50%;' : 'left:50%;') + 'width:' + w + '%"></i></span><span class="qm-mv">' + (v == null ? 'n/a' : (v > 0 ? '+' : '') + v) +
        '</span><span class="mw-dim">' + (rd || '') + '</span></div>';
    };
    var hist = (d.history || []).map(function (h) { return h.risk; });
    var spark = hist.length > 1 ? '<span class="qm-spark">' + hist.map(function (r) {
      return '<i style="height:' + Math.max(2, Math.round((r == null ? 0 : r) / 100 * 22)) + 'px"></i>'; }).join('') + '</span>' : '';
    var body = '';
    [1, 2, 3].forEach(function (fam) {
      var rows = (d.factors || []).filter(function (f) { return f.family === fam; });
      if (!rows.length) return;
      body += '<tr class="qm-fam"><td colspan="5">' + fam + '. ' + FAMILIES[fam] + '</td></tr>' + rows.map(function (f) {
        var tr = f.trend_state == null ? 'n/a' : f.trend_state > 0 ? 'above / bullish' : f.trend_state < 0 ? 'below / bearish' : 'flat';
        var t = [f.label, f.note ? '• ' + f.note : '', f.breakdown ? '• Broke through its risk range two days in a row' : ''].filter(Boolean);
        return '<tr title="' + tip(t) + '"><td>' + esc(f.label) + '</td><td>' + saysCell(f) + '</td><td class="mw-num ' + moveCls(f.ret_3w, f.band_3w, f.direction) + '">' + fmtMove(f.ret_3w, f.unit) +
          '</td><td class="mw-num ' + moveCls(f.ret_3m, f.band_3m, f.direction) + '">' + fmtMove(f.ret_3m, f.unit) + '</td><td><span class="' + voteCls(f.trend_state == null ? null : f.trend_state * (f.trend_direction || 1)) + '">' + tr + '</span> <span class="mw-dim">· ' + (f.weight === 0 ? 'shown only' : f.meter) + '</span></td></tr>';
      }).join('');
    });
    var rq = m.ref_quad;
    return '<div class="qm-pop-h"><button type="button" class="qm-x" title="Close (Esc)" onclick="document.getElementById(\'qmPop\').hidden = true;">\u2715</button><b>Market check' + (rq ? ' vs Quad ' + rq + ' (dashboard 60-day Quad)' : '') + '</b><span class="mw-dim">as of ' + esc(d.as_of) + ' · indicative, thresholds are guesses</span></div>' +
      meterRow('Growth', m.growth, m.growth_read) + meterRow('Inflation', m.inflation, m.inflation_read) +
      '<div class="qm-risk">Transition risk <b>' + (m.risk == null ? 'n/a' : Math.round(m.risk) + ' / 100') + '</b>' +
        (m.target_quad && rq && m.target_quad !== rq ? ' — leaning toward Quad ' + m.target_quad : '') +
        (m.watch_days >= 2 ? ' — on watch ' + m.watch_days + ' days' : '') + spark + '</div>' +
      '<table class="mw-tbl"><thead><tr><th title="The market series behind the read, grouped like Hedgeye\'s note">Factor</th>' +
      '<th title="Effect on its meter: up, down or mixed. Credit spread widening reads down because it is bad for growth">Says</th>' +
      '<th title="Move over the last 3 weeks (about Hedgeye TRADE duration)">3W</th><th title="Move over the last 3 months (about Hedgeye TREND duration)">3M</th>' +
      '<th title="Is it above or below its trend line, and which meter it feeds. Shown only = displayed, does not vote">Trend · counts for</th></tr></thead><tbody>' + body + '</tbody></table>' +
      '<div class="qm-conf"><b>What would confirm a move from Quad ' + (rq || '?') + '</b>' +
      '<div>• Growth turning down: growth meter at or below -20 while inflation stays up (credit, cyclicals, copper/gold, QQQ, yields rolling over)</div>' +
      '<div>• To Quad 4: both meters at or below -20 (commodities, oil and energy falling; Bitcoin and QQQ breaking down; yields breaking TRADE and TREND)</div>' +
      '<div>• Inflation turning down: inflation meter at or below -20 while growth stays up</div></div>' + helpHtml();
  }
  // Plain-English guide shown at the bottom of the popup.
  function helpHtml() {
    return '<div class="qm-help"><div class="qm-help-h">How to read this</div>' +
      '<div><b>What it is.</b> A Quad is two arrows: is growth speeding up or slowing down, and is inflation speeding up or slowing down. ' +
        'Quad 1 = growth up, inflation down. Quad 2 = both up. Quad 3 = growth down, inflation up. Quad 4 = both down. This card reads those two arrows from market prices, ' +
        'independent of the Quad Hedgeye has declared.</div>' +
      '<div><b>Growth and Inflation meters.</b> Each runs from -100 to +100 (center tick = 0). Right/green = rising, left/red = falling. Between -20 and +20 is "unclear". ' +
        '"With" means the meter supports the Quad we are in, "against" means it contradicts it.</div>' +
      '<div><b>The number and label (e.g. 47 - Watch).</b> Transition risk, 0 to 100: how far the meters are from supporting the current Quad. ' +
        'Under 40 = Holding. 40 to 59 = Watch (nothing has broken, something is wobbling). 60 or more = Transition likely (a meter has turned against the Quad). ' +
        '"Leaning toward" is the Quad you would land in if the unclear or against meters flipped.</div>' +
      '<div><b>The four bars.</b> How well each Quad fits the two meters; they add up to about 100. Bold = the leading Quad(s). Indicative only.</div>' +
      '<div><b>Check / cross on the Quad cards.</b> ✓ = the market read fits that declared Quad, ✗ = it does not. Shown on US Quarterly and US Monthly only (the read is built from US prices, so it does not apply to the Global Quad).</div>' +
      '<div><b>The factor table.</b> Each row is one market series. "Says" is its effect on its meter (a widening credit spread reads down, because it is bad for growth). ' +
        '3W is the 3-week move (about Hedgeye\'s TRADE view), 3M the 3-month move (about their TREND view). A factor is up when at least two of its checks (3W, 3M, trend) agree. ' +
        '"Shown only" rows are displayed but do not count.</div>' +
      '<div class="qm-help-h" style="margin-top:8px !important">What each row means</div><div class="qm-fl">' +
        '<div class="qm-fl-h">1. Risk &amp; liquidity</div>' +
        '<div><b>QQQ (growth).</b> The tech-heavy Nasdaq ETF. Rising means investors are comfortable taking risk, so growth is up.</div>' +
        '<div><b>Bitcoin (growth).</b> A risk-appetite gauge. Hedgeye says it moves with QQQ in Quad 2, and both get hit hard in Quad 4.</div>' +
        '<div><b>10Y yield (growth).</b> The 10-year Treasury yield. Rising means a stronger economy. Yields breaking down is a Quad 4 sign.</div>' +
        '<div><b>2Y yield (growth).</b> The same idea for the 2-year yield, which follows the Fed and near-term growth more closely.</div>' +
        '<div><b>US Dollar (inflation, shown only).</b> A strong dollar normally means lower inflation. It does not vote, because Hedgeye stays long the dollar in Quad 2 as well, so it cannot tell Quad 2 from Quad 4.</div>' +
        '<div class="qm-fl-h">2. Inflation &amp; commodities</div>' +
        '<div><b>Commodity basket.</b> An equal-weight average of oil, gas, copper, gold, silver and grains, standing in for the CRB index, which we do not track yet. Rising means inflation is up.</div>' +
        '<div><b>WTI oil.</b> Crude oil. Rising oil pushes inflation up.</div>' +
        '<div><b>Energy stocks (XLE).</b> The energy sector. It rises with oil and inflation, so it confirms the oil read.</div>' +
        '<div><b>10Y breakeven.</b> The market forecast for 10-year inflation. Rising means inflation expectations are up.</div>' +
        '<div class="qm-fl-h">3. Growth, credit &amp; cyclicals</div>' +
        '<div><b>HY credit spread.</b> The extra yield junk bonds pay over safe ones. Widening means stress, so it votes growth down.</div>' +
        '<div><b>Cyclicals vs defensives.</b> Industrial, consumer, financial and materials stocks against utilities, staples and health care. Cyclicals winning means the market expects growth.</div>' +
        '<div><b>Copper vs gold.</b> Copper is an industrial metal, gold is a safe haven. Copper beating gold means growth is up.</div>' +
        '<div><b>Small caps vs S&amp;P.</b> Small companies against large ones. Small caps winning means growth is up. Counts for half weight.</div>' +
        '<div><b>Jobless claims.</b> New unemployment claims, 4-week average against 13-week average. Claims up 5% or more means growth is down. Counts for half weight.</div>' +
        '<div class="qm-fl-h" style="font-weight:400">Most rows have three checks (3-week move, 3-month move, trend) and need two to agree. Rows with no trend check (breakeven, cyclicals, copper vs gold, small caps, claims) need both moves to agree.</div>' +
      '</div>' +
      '<div><b>Watch the days.</b> "On watch N days" counts days in a row at 40 or above. Hedgeye: one bad week is a counter-trend move; weeks 2 and 3 are what matter.</div>' +
      '<div class="mw-dim"><b>Limits.</b> Thresholds and weights are guesses; there is about 8 months of price history; the CRB index is not tracked (a commodity basket stands in); ' +
        'ISM/PMI are not loaded (copper vs gold and cyclicals vs defensives stand in). Treat this as a structured checklist, not a trade signal.</div></div>';
  }
  function toggleQuadPop() {
    var pop = document.getElementById('qmPop');
    if (pop && !pop.hidden) { pop.hidden = true; return; }
    fetch('/api/cockpit/quad-check' + (currentDate() ? '?date=' + encodeURIComponent(currentDate()) : '')).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (d) {
      if (!pop) {
        pop = document.createElement('div'); pop.id = 'qmPop'; pop.className = 'qm-pop'; document.body.appendChild(pop);
        // Closes when the mouse moves out of it (2026-10-19, user-directed); moving back onto the card keeps it open.
        pop.addEventListener('mouseleave', function (e) {
          if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('#qmBlock')) return;
          pop.hidden = true;
        });
      }
      pop.innerHTML = popHtml(d);
      pop.hidden = false;   // centered on the screen by CSS (.qm-pop)
    }).catch(function () {});
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
    var ag = (data.quad_check && data.quad_check.agree) || {};
    function mark(k) {   // does the market's own read fit this declared Quad?
      var v = ag[k];
      return v == null ? '' : '<span class="qc-ck ' + (v ? 'yes' : 'no') + '" title="' + esc(v ? 'The market read fits this Quad' : 'The market read does not fit this Quad') + '">' + (v ? '\u2713' : '\u2717') + '</span>';
    }
    function card(label, quad, period, key) {
      var n = /(\d)/.exec(quad || '');
      return '<div class="qc' + (n ? ' q' + n[1] : '') + '"><div class="qc-lbl">' + label + '</div>' +
        '<div class="qc-val">' + (n ? 'Quad ' + n[1] + ' ' + period : '--') + mark(key) + '</div></div>';
    }
    el.innerHTML = card('US Quarterly', q.quarterly, qtr, 'quarterly') + card('US Monthly', q.monthly, mon, 'monthly') +
      card('Global', q.global, gq, '')   /* no check/cross: the market read is built from US prices, so it does not apply to the Global Quad */ + marketBlock(data);
    el.hidden = false;
    var qm = document.getElementById('qmBlock');
    if (qm) qm.addEventListener('click', toggleQuadPop);
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
    if (window.ocFit) window.ocFit();
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
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeList(); var qp = document.getElementById('qmPop'); if (qp) qp.hidden = true; }
    });
    document.addEventListener('mousedown', function (e) {
      var qp = document.getElementById('qmPop');
      if (qp && !qp.hidden && !e.target.closest('#qmPop') && !e.target.closest('#qmBlock')) qp.hidden = true;
    });
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
