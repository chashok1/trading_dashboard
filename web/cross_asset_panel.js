/* Cross-Asset Signals panel — dashboard screen (index.html): multi-symbol
 * RR-position rules the ordinary rules engine can't express (e.g. "Bonds
 * and USD at TRR, Gold at LRR -> buy Gold"). 2026-09-01, user request.
 * Reads: GET /api/cockpit/cross-asset-signals?date=<#datePicker value>
 * Renders into #crossAssetBody. Below Mkt Situation per user request ("in
 * its own panel... we will be adding more") -- designed to hold more rules
 * than just the one seeded so far, so it stays visible with zero rows
 * fired (shows "how close" each rule is, not just fired ones).
 *
 * A fired rule already drove its target_symbol's real Final Call via
 * derive_actionable.py (etl/derive_cross_asset_rules.py ->
 * drv_cross_asset_signal, folded in the same way a fired rule GROUP is) --
 * this panel is purely a display of that state, same "thin read, no
 * client-side re-derivation" convention every other cockpit panel follows.
 */
(function () {
  'use strict';

  var fetchJson = (window.td_common && window.td_common.fetchJson) || async function (url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Same convention as the Actionable RR column % badge / macro rail's
  // durArrow: low is favorable-entry-green, high is caution-red -- reused
  // here per-leg so a leg close to passing reads warm, far from passing
  // reads cool, regardless of whether its own condition is ">=" or "<=".
  //
  // 2026-09-24, user-directed ("if both bonds and dollar is bullish, it
  // shouldn't recommend buy") -- outlook-type legs (leg.check_type ===
  // 'outlook') added alongside the original rr_position legs: a veto leg
  // PASSING is bad news for the buy thesis (it's actively blocking the
  // rule), so it reads red/warning instead of the usual passing-green; a
  // non-veto outlook leg (none seeded yet, but the schema allows it) keeps
  // the normal green-on-pass convention. No "how close" gradient for
  // outlook checks -- BULLISH/BEARISH/NEUTRAL is categorical, there's no
  // partial-credit distance the way an RR% has.
  function _legColor(leg) {
    if (leg.check_type === 'outlook') {
      if (!leg.passed) return '#a8a29e';
      return leg.is_veto ? '#b91c1c' : '#15803d';
    }
    if (leg.rr_pct == null) return '#a8a29e';
    if (leg.passed) return '#15803d';
    // "how close": distance to the threshold, same direction as the
    // condition -- >=85 needing 60 is farther than needing 80.
    var dist = leg.comparison === '>='
      ? leg.threshold_pct - leg.rr_pct
      : leg.rr_pct - leg.threshold_pct;
    if (dist <= 10) return '#eab308';   // close
    return '#78716c';                    // far, neutral gray
  }

  // 2026-09-24, user-directed: "why confusing '...buy gold'. can we display
  // some thing else may be without buy??" -- ref_cross_asset_rule.description
  // (e.g. "...Gold (/GC) is at LRR -- buy Gold") always rendered as this
  // card's title, fired or not -- reading a live "buy Gold" call on a card
  // that's actually just watching (gray "watching" label, not the green
  // FIRED badge) was the actual confusion. The badge already states the
  // real action when the rule fires ("FIRED -- ADD GLD"); stripping the
  // description's own trailing "-- buy X" clause off the title removes the
  // only other place "buy" text could appear, so the title reads as the
  // SETUP/condition only ("...Gold (/GC) is at LRR") in both states -- the
  // full original sentence (with "buy") is still in the native title=
  // hover for anyone who wants it.
  function _setupTitle(desc) {
    if (!desc) return desc;
    return desc.replace(/\s*[-–—]+\s*(buy|sell)\s+\S+\s*$/i, '');
  }

  // 2026-09-30, user-directed: ONE compact line per rule instead of the long
  // description + chips + status badge. Shape:
  //   GLD · Watching · Bonds 88.6% ✓ · USD 81.7% · Gold 42.8%   (status right after the symbol: Buy / Don't Buy / Watching)
  // Green ✓ = condition met, grey/yellow = not met (yellow = within 10 pts),
  // status at the end (FIRED / blocked / watching). The full description,
  // each leg's target and the veto outlooks live in a bulleted hover popover.
  var _rulesByCode = {};
  var LEG_SHORT = [[/TNX|TYX/, 'Bonds'], [/DXY/, 'USD'], [/\/GC/, 'Gold']];
  function _legShort(sym) {
    for (var i = 0; i < LEG_SHORT.length; i++) if (LEG_SHORT[i][0].test(sym || '')) return LEG_SHORT[i][1];
    return sym || '';
  }

  // 2026-09-30, user-directed: "Don't Buy" (was "Blocked") only when the setup
  // is fully formed -- every normal check passes -- and only the outlook veto
  // (bonds/dollar still BULLISH) stops it. If any normal check still fails
  // the card just says Watching, even while the veto flag is on.
  function _dontBuy(r) {
    if (r.fired === true || r.veto_active !== true) return false;
    var normal = (r.detail || []).filter(function (l) { return l.check_type !== 'outlook'; });
    return normal.length > 0 && normal.every(function (l) { return l.passed; });
  }

  function ruleCard(r) {
    _rulesByCode[r.rule_code] = r;
    var fired = r.fired === true;
    var vetoActive = _dontBuy(r);
    var border = fired ? '#15803d' : vetoActive ? '#b91c1c' : 'var(--border,#e5e5e2)';
    var legs = (r.detail || []).filter(function (l) { return l.check_type !== 'outlook'; }).map(function (l) {
      var color = _legColor(l);
      var pct = l.rr_pct != null ? l.rr_pct.toFixed(1) + '%' : '—';
      return '<span style="color:' + color + '; font-weight:' + (l.passed ? '700' : '400') + '; white-space:nowrap;">' +
        esc(_legShort(l.symbol)) + ' ' + pct + '</span>';   // no check mark (user, 2026-09-30); met conditions stay bold green
    }).join('<span style="color:#d6d3d1;"> &middot; </span>');
    var status = fired
      ? '<span style="color:#15803d; font-weight:700; white-space:nowrap;">&#9679; Buy</span>'
      : vetoActive
      ? '<span style="color:#b91c1c; font-weight:700; white-space:nowrap;">&#9940; Don’t Buy</span>'
      : '<span style="color:var(--text-3,#78716c); font-weight:600; white-space:nowrap;">Watching</span>';
    var link = '/actionable?symbol=' + encodeURIComponent(r.target_symbol);
    return '<div class="ca-rule" data-ca-rule="' + esc(r.rule_code) + '" style="display:flex; flex-wrap:wrap; align-items:center; gap:2px 6px; ' +
      'padding:2px 6px; font-size:10px; line-height:1.4; background:#fff; border:1px solid var(--border,#e5e5e2); ' +
      'border-left:3px solid ' + border + '; border-radius:6px; cursor:help;">' +
      '<a href="' + esc(link) + '" style="font-weight:700; color:var(--text-1,#1c1917); text-decoration:none; white-space:nowrap;">' +
        esc(r.target_symbol) + '</a>' +
      '<span style="color:#d6d3d1;">&middot;</span>' + status +
      '<span style="color:#d6d3d1;">&middot;</span>' + legs +
    '</div>';
  }

  function _rulePopHtml(r) {
    var rows = '';
    (r.detail || []).forEach(function (l) {
      if (l.check_type === 'outlook') {
        var out = l.members && l.members.length
          ? l.members.map(function (m) { return m.symbol + ' ' + (m.outlook || '—'); }).join(', ')
          : (l.outlook || '—');
        rows += '<tr><td class="k" colspan="2">&bull; ' + esc(l.symbol) + ' outlook: <b>' + esc(out) + '</b> (veto if ' +
          esc(l.outlook_value) + ')' + (l.passed && l.is_veto ? (_dontBuy(r) ? ' &mdash; <b style="color:#b91c1c;">blocking the buy</b>' : ' &mdash; would block if the conditions were met') : '') + '</td></tr>';
      } else {
        var pct = l.rr_pct != null ? l.rr_pct.toFixed(1) + '%' : '—';
        var blend = l.members && l.members.length ? ' (' + l.members.map(function (m) {
          return m.symbol + ' ' + (m.rr_pct != null ? m.rr_pct.toFixed(1) + '%' : '—') + ' x' + m.weight;
        }).join(', ') + ')' : '';
        rows += '<tr><td class="k" colspan="2">&bull; ' + esc(_legShort(l.symbol)) + ' ' + pct + ' &mdash; need ' +
          esc(l.comparison) + ' ' + l.threshold_pct + '% ' + (l.passed ? '&#10003;' : '&#10007;') + esc(blend) + '</td></tr>';
      }
    });
    return '<div class="sp-title">' + esc(r.target_symbol) + ' setup</div><table>' +
      '<tr><td class="k" colspan="2">' + esc(_setupTitle(r.description) || r.rule_code) + '</td></tr>' + rows + '</table>';
  }
  function _wireRulePops(root) {
    root.querySelectorAll('.ca-rule').forEach(function (el) {
      el.addEventListener('mouseover', function () {
        var r = _rulesByCode[el.getAttribute('data-ca-rule')];
        if (r && typeof window._showDataPop === 'function') window._showDataPop(el, _rulePopHtml(r));
      });
      el.addEventListener('mouseout', function () {
        if (typeof window.hideSourcePop === 'function') window.hideSourcePop();
      });
    });
  }

  // 2026-09-24, user-directed: "display that along with gold message in
  // that panel box" -- "that" = the Market Read headline the user asked
  // about ("Cash/short FI, Rates up, USD bullish; ... Lists vs Quad model
  // disagree on: ... Quad model: Quad 2 · 5 conflicts") -- reuses GET
  // /api/market-read's own `headline`/`quad` fields verbatim (same thin-
  // read convention as the rule cards below; no re-derivation here), same
  // wording web/market_read.js's headlineHtml() renders on the Market Read
  // band -- this is a second display of that data, not a second source of
  // truth for it.
  // 2026-09-30, user-directed: ONE combined read instead of the old headline
  // sentence + "Disagree:" line -- a Bullish row and a Bearish row (the
  // Hedgeye lists' call per theme), each theme once, with an amber warning
  // icon on the ones where the Quad model disagrees. Hover the icon for a
  // bulleted explanation. Themes shown = the six macro themes (with a
  // Bullish/Bearish list stance) plus any other theme that is in conflict.
  var MACRO_THEMES = ['Cash/short FI', 'Rates up', 'USD', 'Credit', 'Duration', 'Volatility'];
  var _confByTheme = {};
  var _quadLabel = '';

  function _word(code) {
    var c = String(code || '').toUpperCase();
    return c === 'B' || c === 'BULLISH' ? 'Bullish' : c === 'S' || c === 'BEARISH' ? 'Bearish'
      : c === 'N' || c === 'NEUTRAL' ? 'Neutral' : 'No read';
  }
  function _themeChip(t) {
    var warn = t.quad_conflict
      ? ' <span class="ca-warn" data-ca-theme="' + esc(t.theme) + '" style="color:#d97706; font-weight:700; cursor:help;">&#9888;&#xFE0E;</span>'
      : '';
    return '<span style="white-space:nowrap;">' + esc(t.theme) + warn + '</span>';
  }
  function _readRows(themes) {
    _confByTheme = {};
    var bull = [], bear = [];
    themes.forEach(function (t) {
      var st = String(t.stance || '').toUpperCase();
      if (st !== 'B' && st !== 'S') return;
      if (MACRO_THEMES.indexOf(t.theme) === -1 && !t.quad_conflict) return;
      if (t.quad_conflict) _confByTheme[t.theme] = t;
      (st === 'B' ? bull : bear).push(t);
    });
    var row = function (label, color, list) {
      return '<div style="display:flex; gap:6px; font-size:10px; line-height:1.5;">' +
        '<span style="font-weight:700; color:' + color + '; min-width:44px;">' + label + '</span>' +
        '<span style="color:var(--text-1,#1c1917); display:flex; flex-wrap:wrap; gap:2px 8px;">' +
        (list.length ? list.map(_themeChip).join('') : '<span style="color:#a8a29e;">none</span>') + '</span></div>';
    };
    return row('Bullish', '#15803d', bull) + row('Bearish', '#b91c1c', bear);
  }
  function _wireWarnPops(root) {
    root.querySelectorAll('.ca-warn').forEach(function (el) {
      el.addEventListener('mouseover', function () {
        var t = _confByTheme[el.getAttribute('data-ca-theme')];
        if (!t || typeof window._showDataPop !== 'function') return;
        var listsSay = _word(t.stance), quadSays = _word(t.quad_says);
        var col = function (w) { return w === 'Bullish' ? '#1c6c30' : w === 'Bearish' ? '#8c1d1d' : '#78716c'; };
        window._showDataPop(el,
          '<div class="sp-title">' + esc(t.theme) + ' &mdash; lists vs quad model</div><table>' +
          '<tr><td class="k">&bull; Lists say</td><td class="v" style="color:' + col(listsSay) + '; font-weight:600;">' + listsSay + '</td></tr>' +
          '<tr><td class="k">&bull; ' + esc(_quadLabel || 'Quad') + ' model says</td><td class="v" style="color:' + col(quadSays) + '; font-weight:600;">' + quadSays + '</td></tr>' +
          '<tr><td class="k" colspan="2">&bull; The two views disagree, so confidence in this theme is lower.</td></tr>' +
          '<tr><td class="k" colspan="2">&bull; A caution flag, not a buy or sell signal.</td></tr></table>');
      });
      el.addEventListener('mouseout', function () {
        if (typeof window.hideSourcePop === 'function') window.hideSourcePop();
      });
    });
  }

  function quadConflictCard(mr) {
    if (!mr || !(mr.themes || []).length) return '';
    var q = mr.quad || {};
    _quadLabel = q.label || '';
    var badge = q.label
      ? '<span style="font-size:8.5px; font-weight:700; color:' + (q.conflicts ? '#b91c1c' : '#78716c') +
        '; background:' + (q.conflicts ? '#fde2e2' : '#f5f5f4') + '; padding:2px 8px; ' +
        'border-radius:100px; white-space:nowrap;">' + esc(q.label) +
        (q.conflicts ? ' &middot; ' + q.conflicts + ' conflicts &#9888;' : '') + '</span>'
      : '';
    return '<div style="display:flex; flex-direction:column; gap:2px; padding:3px 6px; ' +
      'background:#fff; border:1px solid var(--border,#e5e5e2); border-left:3px solid ' +
      (q.conflicts ? '#b91c1c' : 'var(--border,#e5e5e2)') + '; border-radius:6px;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">' +
        '<span style="font-size:10.5px; font-weight:700; color:var(--text-1,#1c1917);">Lists vs Quad model</span>' +
        badge +
      '</div>' +
      _readRows(mr.themes) +
    '</div>';
  }

  function render(data, mr) {
    var panel = document.getElementById('crossAssetPanel');
    var body = document.getElementById('crossAssetBody');
    if (!panel || !body) return;
    var rows = (data && data.rows) || [];
    var mrCard = quadConflictCard(mr);
    // The panel itself stays visible (it also holds the Regime/quad line above
    // the cards); only the cards area hides when there is nothing to show.
    if (!rows.length && !mrCard) { body.style.display = 'none'; return; }
    body.style.display = '';

    body.innerHTML =
      '<div style="display:flex; flex-direction:column; gap:2px; padding:0 0 2px;">' +
      mrCard + rows.map(ruleCard).join('') +
      '</div>';
    panel.style.display = 'block';
    _wireWarnPops(body);
    _wireRulePops(body);
  }

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  async function load() {
    try {
      var d = currentDate();
      var qs = d ? '?date=' + encodeURIComponent(d) : '';
      var [data, mr] = await Promise.all([
        fetchJson('/api/cockpit/cross-asset-signals' + qs),
        fetchJson('/api/market-read' + qs).catch(function () { return null; }),
      ]);
      render(data, mr);
    } catch (e) {
      var el = document.getElementById('crossAssetPanel');
      if (el) el.style.display = 'none';
    }
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
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
