/* Dashboard hover popups, 2026-10-17 (user-directed): hover a rail row's Act tag -> the Actionable screen's Action popup;
 * hover a rail row's symbol -> its Notes popup. Both come from web/actionable_pops.js, the same code the Actionable screen runs.
 *
 * That file is a classic script written for the Actionable page (it declares globals such as $, fmtUsd and fmtMD that the Dashboard's
 * own scripts also declare), so it is NOT loaded with a <script> tag here. It is fetched on the first hover and evaluated inside a
 * function scope: nothing leaks into the Dashboard's globals, and `state` is handed in as a parameter.
 * The rows and settings it reads are fetched once from the same /api endpoints the Actionable screen uses. */
(function () {
  'use strict';
  var POPS_URL = '/static/actionable_pops.js?v=20261023zh';
  var api = null, loading = null, rows = {};
  var popState = {
    date: null, anchorDate: null, rows: [], allRows: [], filters: { trade_mode: false, act_only: false },
    sort: { key: '_priority', dir: -1, type: 'num' },
    scorecard: {}, sourceScorecard: {}, factorScorecard: {}, agreementScorecard: {}, buysellSeq: {}, mySymbols: new Set(),
    rsiOverbought: 70, rsiOversold: 30, vlmRvolAvoidThreshold: 1.5, convictionProvenEdgeMin: 0.5, unprovenSellMode: 'annotate',
    curveInvertedWarn: false, volZones: {}, sectorEtfMap: {}, unparkedSyms: null, unparkedDay: null
  };
  var hoverEl = null;

  // 2026-10-22: the Action popup's indicators line calls _macdColor / _macdCaret / _rsiColor, which live in actionable.js (not loaded on the
  // Dashboard) -- without them the popup threw a ReferenceError and never appeared. Same code, defined here inside the evaluated scope.
  var HELPERS = `
function _macdColor(v) { if (v == null) return ''; var n = Number(v);
  if (n > 0.5) return '#15803d'; if (n > 0) return '#4ade80'; if (n < -0.5) return '#b91c1c'; if (n < 0) return '#f87171'; return '#6b7280'; }
function _macdCaret(h) { if (h == null) return ''; var mv = Number(h), up = mv > 0;
  return '<span style="margin-left:2px;color:' + _macdColor(mv) + ';" title="MACD momentum ' + (up ? 'strengthening' : 'weakening') + ' (MACDH ' + mv.toFixed(2) + ')">' + (up ? '▲' : '▼') + '</span>'; }
function _rsiColor(v) { if (v == null) return ''; var n = Number(v);
  if (n >= 70) return '#b91c1c'; if (n >= 60) return '#f97316'; if (n <= 30) return '#15803d'; if (n <= 40) return '#4ade80'; return '#6b7280'; }
`;

  function dateQS() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? '?date=' + encodeURIComponent(dp.value) : '';
  }
  function getJson(url) {
    return fetch(url).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function loadAll() {
    if (loading) return loading;
    var qs = dateQS();
    loading = Promise.all([
      fetch(POPS_URL).then(function (r) { return r.text(); }),
      getJson('/api/actionable' + qs),
      getJson('/api/actionable/settings'),
      getJson('/api/rules/scorecard?min_fires=0&limit=2000'),
      getJson('/api/actionable/source-scorecard'),
      getJson('/api/rules/factor-scorecard?min_n=30'),
      getJson('/api/macro-areas' + qs),
      getJson('/api/cockpit/risk-dial' + qs)
    ]).then(function (r) {
      var src = r[0], list = r[1], settings = r[2] || {}, sc = r[3], srcSc = r[4], fsc = r[5], areas = r[6], rd = r[7];
      var dp = document.getElementById('datePicker');
      popState.date = (dp && dp.value) || null;
      popState.anchorDate = popState.date;
      var n = Number(settings.rsi_overbought); popState.rsiOverbought = isFinite(n) ? n : 70;
      n = Number(settings.rsi_oversold); popState.rsiOversold = isFinite(n) ? n : 30;
      n = Number(settings.vlm_rvol_avoid_threshold); popState.vlmRvolAvoidThreshold = isFinite(n) ? n : 1.5;
      n = Number(settings.conviction_proven_edge_min); popState.convictionProvenEdgeMin = isFinite(n) ? n : 0.5;
      popState.unprovenSellMode = settings.unproven_sell_mode || 'annotate';
      (sc || []).forEach(function (x) { popState.scorecard[x.rule_id] = x; });
      popState.sourceScorecard = srcSc || {};
      (fsc || []).forEach(function (x) { popState.factorScorecard[x.factor + '|' + x.bucket] = x; });
      var fired = {};
      ((rd && rd.fired) || []).forEach(function (g) { fired[g.key] = 1; });
      popState.curveInvertedWarn = !!(fired.curve_inverting || fired['3m10y_inverted']);
      ((areas && areas.areas) || []).forEach(function (ar) {
        if (ar.area_key !== 'volatility') return;
        (ar.members || []).forEach(function (m) { if (m.zone) popState.volZones[m.label] = { zone: m.zone, last: m.last }; });
      });
      (((areas && areas.sectors && areas.sectors.all) || [])).forEach(function (s) {
        if (s.sector && s.etf) popState.sectorEtfMap[s.sector.trim().toLowerCase()] = s.etf;
      });
      // Evaluate the shared popup code in its own scope (see header comment).
      api = new Function('state', HELPERS + src + '\n;return {build: _buildActionPopHtmlV2, loadNotes: _actpopLoadNotes, notes: showNotesPop,' +
        ' showData: _showDataPop, hide: hideSourcePop, prep: prepareActionableRow, noise: _buyNoiseGated,' +
        ' isNew: _isNewSnapshot, actioned: _actionedInfo};')(popState);
      popState.allRows = popState.rows = Array.isArray(list) ? list : (list && list.rows) || [];
      popState.allRows.forEach(function (row) {
        try {
          api.prep(row);
          row._watchlisted = api.noise(row);
          row._isNew = api.isNew(row);
          row._actionInfo = api.actioned(row);
        } catch (e) { /* a row with odd data just gets a thinner popup */ }
        rows[row.tos_symbol] = row;
      });
    }).catch(function (e) { loading = null; console.warn('Dashboard popups unavailable:', e); });
    return loading;
  }

  function ensurePopEl() {
    var el = document.getElementById('sourcePop');
    if (!el) {
      el = document.createElement('div');
      el.id = 'sourcePop';
      el.className = 'source-pop';
      document.body.appendChild(el);
    }
    return el;
  }

  // Small placeholder while the popup data is still loading.
  function loadingNote(el) {
    var pop = ensurePopEl();
    pop.innerHTML = '<span style="color:#94a3b8;font-size:10px;">Loading popup data&hellip;</span>';
    pop.style.display = 'block';
    var r = el.getBoundingClientRect();
    pop.style.top = (r.bottom + 4) + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 180)) + 'px';
  }

  // The row carries a native title tooltip; suppress it while a popup is up so the two do not stack.
  function muteTitle(rowEl, on) {
    if (!rowEl) return;
    if (on) { if (rowEl.hasAttribute('title')) { rowEl.setAttribute('data-title', rowEl.getAttribute('title')); rowEl.removeAttribute('title'); } }
    else if (rowEl.hasAttribute('data-title')) { rowEl.setAttribute('title', rowEl.getAttribute('data-title')); rowEl.removeAttribute('data-title'); }
  }

  function show(el, kind) {
    var rowEl = el.closest('.msr-row');
    var sym = rowEl && rowEl.getAttribute('data-sym');
    var row = sym && rows[sym];
    if (!api || !row || hoverEl !== el) return;
    ensurePopEl();
    muteTitle(rowEl, true);
    try {
      if (kind === 'act') {
        api.showData(el, api.build(row));
        api.loadNotes(sym);
      } else {
        // showNotesPop is async (fetches the notes, then re-shows the popup): if the pointer has left by then, hide it again.
        var pr = api.notes(el, sym, row.company_name);
        if (pr && pr.then) pr.then(function () { if (hoverEl !== el) { try { api.hide(); } catch (e) { /* ignore */ } } });
      }
    } catch (e) { console.warn('popup failed for', sym, e); }
  }

  function targetOf(e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return null;
    var tag = t.closest('.msr-row .ms-tag');
    if (tag) return { el: tag, kind: 'act' };
    var nm = t.closest('.msr-row .msr-name-tick');
    if (nm) return { el: nm, kind: 'sym' };
    return null;
  }

  // X button in the popup header: the shared code hides the popup; this resets the hover state so the same symbol can be hovered again.
  document.addEventListener('click', function (e) {
    if (!(e.target && e.target.closest && e.target.closest('[data-actpop-close]'))) return;
    clearTimeout(hideT);
    if (hoverEl) { muteTitle(hoverEl.closest('.msr-row'), false); hoverEl = null; }
  });
  // The shared popup code closed the popup because the pointer left it: reset the hover state so the same symbol can be hovered again.
  window.addEventListener('actpop:closed', function () {
    clearTimeout(hideT);
    if (hoverEl) { muteTitle(hoverEl.closest('.msr-row'), false); hoverEl = null; }
  });
  var hideT = null;   // short grace period so the mouse can cross the gap between the symbol and the popup
  document.addEventListener('mouseover', function (e) {
    if (e.target && e.target.closest && e.target.closest('#sourcePop')) clearTimeout(hideT);
    var t = targetOf(e);
    if (t) clearTimeout(hideT);
    if (!t || t.el === hoverEl) return;
    hoverEl = t.el;
    if (api) { show(t.el, t.kind); return; }
    loadingNote(t.el);   // data still loading (first hover before the background preload finished): say so, then show it
    loadAll().then(function () { show(t.el, t.kind); });   // shows if the pointer is still there
  });
  document.addEventListener('mouseout', function (e) {
    if (!hoverEl) return;
    var rel = e.relatedTarget;
    if (rel && (hoverEl.contains(rel) || (rel.closest && rel.closest('#sourcePop')))) return;
    var gone = hoverEl;
    clearTimeout(hideT);
    hideT = setTimeout(function () {
      if (hoverEl !== gone) return;   // the pointer moved on to another symbol meanwhile
      var rowEl = gone.closest('.msr-row');
      hoverEl = null;
      muteTitle(rowEl, false);
      if (api) { try { api.hide(); } catch (err) { /* ignore */ } }
      else { var pe = document.getElementById('sourcePop'); if (pe) pe.style.display = 'none'; }
    }, 200);
  });
  // New date or refresh: drop the cached rows so the next hover loads fresh ones.
  function reset() { api = null; loading = null; rows = {}; setTimeout(loadAll, 1500); }
  // Preload quietly a few seconds after the page opens, so the first real hover is instant.
  setTimeout(function () { if (!loading) loadAll(); }, 3000);
  document.addEventListener('DOMContentLoaded', function () {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', reset);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', reset);
  });
})();
