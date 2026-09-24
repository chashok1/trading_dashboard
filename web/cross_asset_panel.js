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

  function _outlookLegChip(leg) {
    var color = _legColor(leg);
    var vetoTag = leg.is_veto ? (leg.passed ? ' (blocking)' : ' (veto, not active)') : '';
    var valTxt, titleTxt;
    if (leg.members && leg.members.length) {
      // Blended categorical-AND check (e.g. "TNX:CGI + TYX:CGI") -- no
      // single combined outlook to show, list each member's own reading.
      valTxt = leg.members.map(function (m) { return m.outlook || '—'; }).join('/');
      titleTxt = leg.symbol + ' need ' + leg.outlook_value + vetoTag + ' — ' +
        leg.members.map(function (m) { return m.symbol + ' ' + (m.outlook || '—'); }).join(', ');
    } else {
      valTxt = leg.outlook || '—';
      titleTxt = leg.symbol + ' outlook ' + valTxt + ' (need ' + leg.outlook_value + ')' + vetoTag;
    }
    return '<span style="display:inline-flex; align-items:center; gap:3px; ' +
      'font-size:9px; padding:2px 6px; border-radius:100px; white-space:nowrap; ' +
      'background:' + (leg.passed && leg.is_veto ? '#fde2e2' : leg.passed ? '#dceadd' : '#f5f5f4') +
      '; color:' + color + '; font-weight:' + (leg.passed ? '700' : '400') + ';" ' +
      'title="' + esc(titleTxt) + '">' +
      (leg.passed && leg.is_veto ? '&#9940; ' : leg.passed ? '&#10003; ' : '') +
      esc(leg.symbol) + ' ' + esc(valTxt) +
      '</span>';
  }

  function legChip(leg) {
    if (leg.check_type === 'outlook') return _outlookLegChip(leg);
    var color = _legColor(leg);
    var pctTxt = leg.rr_pct != null ? leg.rr_pct.toFixed(1) + '%' : '—';
    var condTxt = leg.comparison + ' ' + leg.threshold_pct + '%';
    // Blended checks (leg.members present, e.g. "10Y+30Y weighted 70/30")
    // spell out each member's own RR%/weight in the tooltip -- the chip
    // itself only shows the combined value, same as any other check.
    var titleTxt = leg.symbol + ' RR ' + pctTxt + ' (need ' + condTxt + ')';
    if (leg.members && leg.members.length) {
      titleTxt += ' — blend of ' + leg.members.map(function (m) {
        var mPct = m.rr_pct != null ? m.rr_pct.toFixed(1) + '%' : '—';
        return m.symbol + ' ' + mPct + ' (weight ' + m.weight + ')';
      }).join(', ');
    }
    return '<span style="display:inline-flex; align-items:center; gap:3px; ' +
      'font-size:9px; padding:2px 6px; border-radius:100px; white-space:nowrap; ' +
      'background:' + (leg.passed ? '#dceadd' : '#f5f5f4') + '; color:' + color + '; ' +
      'font-weight:' + (leg.passed ? '700' : '400') + ';" ' +
      'title="' + esc(titleTxt) + '">' +
      (leg.passed ? '&#10003; ' : '') + esc(leg.symbol) + ' ' + pctTxt +
      '</span>';
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

  function ruleCard(r) {
    var fired = r.fired === true;
    // 2026-09-24 -- veto_active (etl/derive_cross_asset_rules.py) means the
    // normal legs all passed but an outlook veto blocked it -- a plain
    // gray "watching" would misleadingly suggest the setup just isn't
    // there yet, when it's actually fully formed except for the veto.
    var vetoActive = !fired && r.veto_active === true;
    var border = fired ? '#15803d' : vetoActive ? '#b91c1c' : 'var(--border,#e5e5e2)';
    var badge = fired
      ? '<span style="font-size:8.5px; font-weight:700; color:#15803d; background:#dceadd; ' +
        'padding:2px 8px; border-radius:100px; white-space:nowrap;">&#9679; FIRED &mdash; ' +
        esc(r.target_action) + ' ' + esc(r.target_symbol) + '</span>'
      : vetoActive
      ? '<span style="font-size:8.5px; font-weight:700; color:#b91c1c; background:#fde2e2; ' +
        'padding:2px 8px; border-radius:100px; white-space:nowrap;">&#9940; BLOCKED &mdash; trend still bullish</span>'
      : '<span style="font-size:8.5px; color:var(--text-3,#a8a29e);">watching</span>';
    var legsHtml = (r.detail || []).map(legChip).join(' ');
    var link = '/actionable?symbol=' + encodeURIComponent(r.target_symbol);
    var setupTxt = _setupTitle(r.description) || r.rule_code;
    return '<div style="display:flex; flex-direction:column; gap:5px; padding:8px 10px; ' +
      'background:#fff; border:1px solid var(--border,#e5e5e2); border-left:3px solid ' + border +
      '; border-radius:6px;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">' +
        '<a href="' + esc(link) + '" style="font-size:10.5px; font-weight:700; color:' +
        (fired ? 'var(--text-1,#1c1917)' : 'var(--text-3,#78716c)') + '; ' +
        'text-decoration:none;" title="' + esc(r.description || r.rule_code) +
        ' — open ' + esc(r.target_symbol) + ' on Actionable">' +
        esc(setupTxt) + '</a>' +
        badge +
      '</div>' +
      '<div style="display:flex; flex-wrap:wrap; gap:4px;">' + legsHtml + '</div>' +
    '</div>';
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
  function quadConflictCard(mr) {
    if (!mr || !mr.headline) return '';
    var q = mr.quad || {};
    var badge = q.label
      ? '<span style="font-size:8.5px; font-weight:700; color:' + (q.conflicts ? '#b91c1c' : '#78716c') +
        '; background:' + (q.conflicts ? '#fde2e2' : '#f5f5f4') + '; padding:2px 8px; ' +
        'border-radius:100px; white-space:nowrap;">' + esc(q.label) +
        (q.conflicts ? ' &middot; ' + q.conflicts + ' conflicts &#9888;' : '') + '</span>'
      : '';
    return '<div style="display:flex; flex-direction:column; gap:5px; padding:8px 10px; ' +
      'background:#fff; border:1px solid var(--border,#e5e5e2); border-left:3px solid ' +
      (q.conflicts ? '#b91c1c' : 'var(--border,#e5e5e2)') + '; border-radius:6px;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">' +
        '<span style="font-size:10.5px; font-weight:700; color:var(--text-1,#1c1917);">Lists vs Quad model</span>' +
        badge +
      '</div>' +
      '<div style="font-size:10px; color:var(--text-2,#57534e); line-height:1.4;">' + esc(mr.headline) + '</div>' +
    '</div>';
  }

  function render(data, mr) {
    var panel = document.getElementById('crossAssetPanel');
    var body = document.getElementById('crossAssetBody');
    if (!panel || !body) return;
    var rows = (data && data.rows) || [];
    var mrCard = quadConflictCard(mr);
    if (!rows.length && !mrCard) { panel.style.display = 'none'; return; }

    body.innerHTML =
      '<div style="display:flex; flex-direction:column; gap:6px; padding:2px 0 6px;">' +
      mrCard + rows.map(ruleCard).join('') +
      '</div>';
    panel.style.display = 'block';
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
