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
  function _legColor(leg) {
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

  function legChip(leg) {
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
      'font-size:10px; padding:2px 6px; border-radius:100px; white-space:nowrap; ' +
      'background:' + (leg.passed ? '#dceadd' : '#f5f5f4') + '; color:' + color + '; ' +
      'font-weight:' + (leg.passed ? '700' : '400') + ';" ' +
      'title="' + esc(titleTxt) + '">' +
      (leg.passed ? '&#10003; ' : '') + esc(leg.symbol) + ' ' + pctTxt +
      '</span>';
  }

  function ruleCard(r) {
    var fired = r.fired === true;
    var border = fired ? '#15803d' : 'var(--border,#e5e5e2)';
    var badge = fired
      ? '<span style="font-size:9.5px; font-weight:700; color:#15803d; background:#dceadd; ' +
        'padding:2px 8px; border-radius:100px; white-space:nowrap;">&#9679; FIRED &mdash; ' +
        esc(r.target_action) + ' ' + esc(r.target_symbol) + '</span>'
      : '<span style="font-size:9.5px; color:var(--text-3,#a8a29e);">watching</span>';
    var legsHtml = (r.detail || []).map(legChip).join(' ');
    var link = '/actionable?symbol=' + encodeURIComponent(r.target_symbol);
    return '<div style="display:flex; flex-direction:column; gap:5px; padding:8px 10px; ' +
      'background:#fff; border:1px solid var(--border,#e5e5e2); border-left:3px solid ' + border +
      '; border-radius:6px;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">' +
        '<a href="' + esc(link) + '" style="font-size:11.5px; font-weight:700; color:var(--text-1,#1c1917); ' +
        'text-decoration:none;" title="Open ' + esc(r.target_symbol) + ' on Actionable">' +
        esc(r.description || r.rule_code) + '</a>' +
        badge +
      '</div>' +
      '<div style="display:flex; flex-wrap:wrap; gap:4px;">' + legsHtml + '</div>' +
    '</div>';
  }

  function render(data) {
    var panel = document.getElementById('crossAssetPanel');
    var body = document.getElementById('crossAssetBody');
    if (!panel || !body) return;
    var rows = (data && data.rows) || [];
    if (!rows.length) { panel.style.display = 'none'; return; }

    body.innerHTML = '<div class="msr-section-hdr">Cross-Asset Signals</div>' +
      '<div style="display:flex; flex-direction:column; gap:6px; padding:2px 0 6px;">' +
      rows.map(ruleCard).join('') +
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
      var data = await fetchJson('/api/cockpit/cross-asset-signals' + (d ? '?date=' + encodeURIComponent(d) : ''));
      render(data);
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
