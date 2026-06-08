/* Actionable Stocks page logic */

const state = {
  date: null,
  allRows: [],   // full unfiltered dataset for the date
  baseRows: [],  // passes every filter except the action chip (drives chip counts)
  rows: [],      // filtered subset shown in grid
  sort: { key: '_priority', dir: -1, type: 'num' },  // default: priority DESC
  filters: {
    action: '',          // '' | REMOVE | REDUCE | INCREASE | ADD | HOLD
    buys_sells: '',      // '' | 'buy' | 'sell' (quick toggle)
    source: '',
    held_only: false,
    show_acted: false,
    show_suppressed: false,
    show_no_action: false,  // when false, blank-action rows are hidden
    show_zero_amt: false,   // when false, rows with $0 AMT$ are hidden
    symbol_search: '',   // symbol search text filter
    sector: '',          // sector dropdown
    asset_class: '',     // asset class dropdown
    conviction: 'any',   // 'any' | 'multi' | 'proven'
    amt_min: 0,          // 0 | 5000 | 25000
  },
  current: null,
  sourceMethods: {},   // source_code -> base_weight_method (Metric-column sort)
  buysellSeq: {},      // buysell code -> seq from ref_param_lookup (priority sort)
  // Pass 2: top-N collapse
  showAll: false,
  TOP_N: 15,
  // Pass 3: bulk select
  selected: new Set(),
  // Pass 3: focus mode
  focusIdx: 0,
};

const $ = (id) => document.getElementById(id);

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(e.detail || r.statusText);
  }
  return r.json();
}

function fmtUsd(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n)) return '';
  if (Math.abs(n) >= 1000) return '$' + (Math.round(n)).toLocaleString();
  return '$' + n.toFixed(0);
}
// Compact currency: $38k, $1.2m, $500 — for Pos $ column
function fmtCompact(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n) || n === 0) return '';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e6) return sign + '$' + (abs / 1e6).toFixed(1).replace(/\.0$/, '') + 'm';
  if (abs >= 1e3) return sign + '$' + Math.round(abs / 1e3) + 'k';
  return sign + '$' + Math.round(abs);
}
function fmtDate(d) {
  if (!d) return '—';
  return d.toString().slice(0, 10);
}
// Short MM/DD date for snapshot columns (no year). '' for empty.
function fmtMD(d) {
  if (!d) return '';
  const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? (m[2] + '/' + m[3]) : String(d);
}
// Format derived_at timestamp: show M/DD if yesterday, HH:MM AM/PM if today.
function fmtAsOf(ts) {
  if (!ts) return '';
  const dt = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const tsDate = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const yestDate = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate());
  if (tsDate.getTime() === yestDate.getTime()) {
    return (yesterday.getMonth() + 1) + '/' + String(yesterday.getDate()).padStart(2, '0');
  } else if (tsDate.getTime() === todayDate.getTime()) {
    return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  }
  return fmtMD(ts);
}

function fmtAsOfExport(exportDate, exportTime, loadedAt) {
  // Use export_date/time if available, otherwise fall back to loaded_at timestamp
  if (exportDate) {
    // Parse export_date as YYYY-MM-DD string
    const parts = String(exportDate).split('-');
    if (parts.length === 3) {
      const expYear = parseInt(parts[0]);
      const expMonth = parseInt(parts[1]);
      const expDay = parseInt(parts[2]);

      const today = new Date();
      const todayYear = today.getFullYear();
      const todayMonth = today.getMonth() + 1;
      const todayDay = today.getDate();

      const yesterday = new Date(today);
      yesterday.setDate(yesterday.getDate() - 1);
      const yestYear = yesterday.getFullYear();
      const yestMonth = yesterday.getMonth() + 1;
      const yestDay = yesterday.getDate();

      // Compare dates
      if (expYear === yestYear && expMonth === yestMonth && expDay === yestDay) {
        return yestMonth + '/' + String(yestDay).padStart(2, '0');
      } else if (expYear === todayYear && expMonth === todayMonth && expDay === todayDay) {
        // Format time: convert HHMM to HH:MM AM/PM
        if (exportTime) {
          const timeStr = String(exportTime).replace(':', '').trim();
          let hours = parseInt(timeStr.substring(0, timeStr.length - 2)) || 0;
          let minutes = parseInt(timeStr.substring(timeStr.length - 2)) || 0;
          const ampm = hours >= 12 ? 'PM' : 'AM';
          if (hours > 12) hours -= 12;
          if (hours === 0) hours = 12;
          return hours + ':' + String(minutes).padStart(2, '0') + ' ' + ampm;
        }
        return '';
      }
      return fmtMD(exportDate);
    }
  }
  // Fallback to loaded_at if export_date is missing
  if (loadedAt) {
    return fmtAsOf(loadedAt);
  }
  return '';
}
function showStatus(msg, kind = 'info', timeout = 4000) {
  const el = $('statusBar');
  el.className = 'status-bar ' + kind;
  el.textContent = msg;
  if (timeout) setTimeout(() => { el.style.display = 'none'; }, timeout);
}

// ---- date picker ----
async function loadDates() {
  const dates = await fetchJson('/api/actionable/dates');
  if (dates.length === 0) {
    showStatus('No actionable data computed yet. Run Admin > Rebuild to generate actionable recommendations.', 'warning', 0);
    return;
  }
  const sel = $('datePicker');
  sel.innerHTML = '';
  for (const d of dates) {
    const o = document.createElement('option');
    o.value = d; o.textContent = d;
    sel.appendChild(o);
  }
  state.date = dates[0] || null;
  if (state.date) sel.value = state.date;
  await loadActionable();
}

// ---- source metadata (base_weight_method per source, for Metric sort) ----
async function loadSources() {
  try {
    const rows = await fetchJson('/api/actionable/sources');
    state.sourceMethods = {};
    for (const r of rows) state.sourceMethods[r.source_code] = r.base_weight_method;
  } catch (_) { state.sourceMethods = {}; }
  // Rule track-record (v_rule_scorecard) keyed by composite code, for the
  // edge badges on fired-rule pills. Diagnostic only while history is shallow.
  try {
    const sc = await fetchJson('/api/rules/scorecard?min_fires=0&limit=2000');
    state.scorecard = {};
    for (const r of sc) state.scorecard[r.rule_id] = r;
  } catch (_) { state.scorecard = {}; }
  // Buysell code→seq map from ref_param_lookup for the default priority sort.
  // SA has seq=21 (highest); sorting by seq DESC puts SA at the top.
  try {
    state.buysellSeq = await fetchJson('/api/ref/buysell');
  } catch (_) { state.buysellSeq = {}; }
}

// Resolve the buy/sell side for a fired rule ID via actions.js (single source
// of truth). Uses the scorecard's direction field ('BUY'/'SELL') and maps it
// through actionDisplay() to get the canonical side string ('buy'/'sell'/'neutral').
function _ruleSide(id) {
  const sc = (state.scorecard || {})[id];
  if (!sc || !sc.direction) return 'neutral';
  // Map scorecard direction → representative BuySell code → actionDisplay side.
  const code = sc.direction === 'BUY' ? 'BM' : sc.direction === 'SELL' ? 'SA' : '';
  return actionDisplay(code).side; // 'buy' | 'sell' | 'neutral'
}

// Build the inline edge badge HTML for a fired composite code (or '' if unknown).
// Color = direction (buy=green, sell=red, neutral=grey); fill = edge strength.
function ruleEdgeBadge(code) {
  const sc = (state.scorecard || {})[code];
  if (!sc || sc.edge_20d == null) return '';
  const e = Number(sc.edge_20d);
  const side = _ruleSide(code);
  const sideCls = side === 'buy' ? 'rule-buy' : side === 'sell' ? 'rule-sell' : 'rule-neutral';
  const emphCls = e > 0 ? 'rule-strong' : 'rule-weak';
  const wr = (sc.win_rate != null) ? ` · ${(Number(sc.win_rate) * 100).toFixed(0)}%` : '';
  const sign = e >= 0 ? '+' : '';
  return ` <span class="rule-edge-badge ${sideCls} ${emphCls}" `
       + `title="Rule's historical 20d edge across all symbols (${sc.fires} fires) — diagnostic, shallow history">`
       + `${sign}${e.toFixed(1)}%${wr}</span>`;
}

// Grid cell: fired rules ordered winning-first (highest score), each with its
// historical edge. Hue = direction (buy=green, sell=red, neutral=grey);
// fill = edge emphasis (solid=positive, muted/outlined=non-positive).
function firesCellHtml(r) {
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return '<span style="color:#cbd5e1">—</span>';
  const sc = state.scorecard || {};
  const items = fires.map(f => {
    const id = String(f.rule_id || f.id || f);
    const e  = (sc[id] && sc[id].edge_20d != null) ? Number(sc[id].edge_20d) : null;
    const score = (f.score != null) ? Number(f.score) : 0;
    return { id, e, score };
  });
  // winning first: highest fired score, then strongest edge
  items.sort((a, b) => (b.score - a.score) || ((b.e ?? -99) - (a.e ?? -99)));
  return items.map(it => {
    const side = _ruleSide(it.id);
    const sideCls = side === 'buy' ? 'rule-buy' : side === 'sell' ? 'rule-sell' : 'rule-neutral';
    const emphCls = (it.e != null && it.e > 0) ? 'rule-strong' : 'rule-weak';
    const edge = it.e == null ? '' : ` <b>${it.e >= 0 ? '+' : ''}${it.e.toFixed(1)}</b>`;
    return `<span class="act-badge act-badge-sm ${sideCls} ${emphCls}" style="white-space:nowrap;">${escapeHtml(it.id)}${edge}</span>`;
  }).join(' ');
}

// Best-first Metric direction: rank ascending (rank 1 best), else descending.
function _metricAscending(src) {
  return (state.sourceMethods || {})[src] === 'rank';
}

// The selected source's driver metric for a row (rank for PS, weight for
// outlook sources) - read from that source's source_actions entry.
function _rowMetric(row, src) {
  if (!src) return null;
  const e = _sourcesOf(row).find(s => (s.source || s.source_code || '') === src);
  if (!e || e.weight == null) return null;
  const n = Number(e.weight);
  return isFinite(n) ? n : null;
}

// SSS-style metrics (base_weight_method = rank_pct_delta) are percentages.
function _isPctSource(src) {
  return (state.sourceMethods || {})[src] === 'rank_pct_delta';
}

// Format a fraction as a percentage for display. pct_delta is stored as a
// fraction (e.g. 0.053) - scaled x100 here for display only; the stored
// value is never changed.
function fmtPct(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return isFinite(n) ? (formatNum(n * 100) + '%') : '';
}

// ---- core load ----
async function loadActionable() {
  if (!state.date) return;
  // Reset to default actionability sort on every fresh data load (date change / refresh).
  // Column-header clicks override this until the next load or Clear.
  state.sort = { key: '_priority', dir: -1, type: 'num' };
  // Always fetch all rows -- action/category filters applied client-side so chip counts stay accurate
  const params = new URLSearchParams({ date: state.date });
  if (state.filters.show_acted) params.append('show_acted', 'true');
  if (state.filters.show_suppressed) params.append('show_suppressed', 'true');
  try {
    const rows = await fetchJson('/api/actionable?' + params.toString());
    state.allRows = Array.isArray(rows) ? rows : [];
    state.allRows.forEach(r => {
      const act = (r.consolidated_action || '').toUpperCase();
      if (_isOverMaxOverlay(r)) {
        // Over-allocation overlay — AMT$ = trim back to the category Max.
        r._amt = Number(r.current_position_dollar) - Number(r.target_max_dollar);
      } else if (act === 'REMOVE') {
        r._amt = r.current_position_dollar;
      } else if (act === 'ADD' && r.target_min_dollar != null) {
        // ADD: AMT$ is the top-up needed to reach Min. Already at/above Min → 0.
        const pos = Number(r.current_position_dollar) || 0;
        const min = Number(r.target_min_dollar);
        r._amt = pos < min ? min - pos : 0;
      } else if (act === 'INCREASE') {
        // INCREASE: AMT$ = target - position (amount to buy). Suppressed -> 0.
        const pos = Number(r.current_position_dollar) || 0;
        const tgt = Number(r.suggested_target_dollar) || 0;
        r._amt = tgt > pos ? tgt - pos : 0;
      } else if (act === 'REDUCE') {
        // REDUCE: AMT$ = position - target (amount to sell). Suppressed -> 0.
        const pos = Number(r.current_position_dollar) || 0;
        const tgt = Number(r.suggested_target_dollar) || 0;
        r._amt = pos > tgt ? pos - tgt : 0;
      } else {
        r._amt = r.suggested_target_dollar;
      }
    });
    // Priority and Final Call must be computed after _amt (uses _agreeingSources +
    // _hasPositiveEdge which need source_actions and scorecard, both already loaded).
    state.allRows.forEach(r => {
      var fc = finalCall(r);
      r._fc_strength = fc.strength;
      r._fc_code     = fc.code;
      r._fc_side     = fc.side;
      r._priority = _computePriority(r);
    });
    applyClientFilter();
  } catch (e) {
    showStatus('Failed to load actionable: ' + e.message, 'error', 0);
  }
}

// Client filters EXCEPT the action chip. Kept separate so the action-chip
// counts can reflect every other active filter (including buys_sells).
// All active filters combine with AND.
function matchesBaseFilters(r) {
  if (!state.filters.show_no_action && !r.consolidated_action) return false;
  if (!state.filters.show_zero_amt && !r._amt) return false;
  if (state.filters.source) {
    if (!_rowHasSource(r, state.filters.source)) return false;
  }
  if (state.filters.held_only) {
    if (!r.held_today) return false;
  }
  if (state.filters.sector) {
    if ((r.sector || '') !== state.filters.sector) return false;
  }
  if (state.filters.asset_class) {
    const rac = r.real_asset_class || r.asset_class || '';
    if (rac !== state.filters.asset_class) return false;
  }
  if (state.filters.conviction === 'multi') {
    if (_agreeingSources(r) < 2) return false;
  } else if (state.filters.conviction === 'proven') {
    if (!_hasPositiveEdge(r)) return false;
  }
  if (state.filters.amt_min > 0) {
    if (Math.abs(Number(r._amt) || 0) < state.filters.amt_min) return false;
  }
  const symSearch = state.filters.symbol_search || state.filters.tos_symbol_search || '';
  if (symSearch) {
    const search = symSearch.toUpperCase();
    if (!r.tos_symbol || !r.tos_symbol.toUpperCase().includes(search)) return false;
  }
  // buys_sells included here so chip counts reflect it (AND logic with action chip)
  if (state.filters.buys_sells === 'buy') {
    const a = (r.consolidated_action || '').toUpperCase();
    if (a !== 'INCREASE' && a !== 'ADD') return false;
  } else if (state.filters.buys_sells === 'sell') {
    const a = (r.consolidated_action || '').toUpperCase();
    if (a !== 'REMOVE' && a !== 'REDUCE' && !_isOverMaxOverlay(r)) return false;
  }
  return true;
}

function applyClientFilter() {
  if (state.filters.source && !_availableSources().has(state.filters.source)) {
    state.filters.source = '';
  }
  // baseRows: all filters except the action chip (drives chip counts that reflect
  // every active filter including buys_sells, via matchesBaseFilters).
  state.baseRows = state.allRows.filter(matchesBaseFilters);
  // rows: baseRows + action chip filter (AND combined)
  state.rows = state.baseRows.filter(r => {
    if (!state.filters.action) return true;
    if (state.filters.action === 'OVER_MAX') return _isOverMaxOverlay(r);
    return (r.consolidated_action || 'NONE').toUpperCase() === state.filters.action;
  });
  // Reset collapse and selection on filter change.
  state.showAll = false;
  state.selected.clear();
  renderBulkBar();
  renderSummary();
  renderSourceFilter();
  renderSectorFilter();
  renderAssetClassFilter();
  updateFilterBadge();
  saveFiltersToStorage();
  renderGrid();
}

// ---- staleness banner ----
async function checkFreshness() {
  const banner = $('staleBanner');
  if (!banner || !state.date) return;
  try {
    const f = await fetchJson('/api/actionable/freshness?date=' +
      encodeURIComponent(state.date));
    if (f && f.stale) {
      $('staleBannerMsg').textContent =
        "This date's data is stale - newer source data was loaded after it " +
        "was last derived. Re-derive to refresh.";
      banner.style.display = 'flex';
    } else {
      banner.style.display = 'none';
    }
  } catch (_) {
    banner.style.display = 'none';
  }
}

async function rederiveStale() {
  const btn = $('staleRederiveBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Re-deriving...'; }
  try {
    await fetchJson('/api/monitor/derive-stale/run', { method: 'POST' });
  } catch (_) { /* ignore - banner re-check below reflects the result */ }
  if (btn) { btn.disabled = false; btn.textContent = 'Re-derive now'; }
  await loadActionable();
  await checkFreshness();
}

// ---- summary chips (act as quick action filters) ----
function renderSummary() {
  const counts = { REMOVE: 0, OVER_MAX: 0, REDUCE: 0, INCREASE: 0, ADD: 0, HOLD: 0, NONE: 0 };
  for (const r of state.baseRows) {
    const a = (r.consolidated_action || 'NONE').toUpperCase();
    if (counts[a] !== undefined) counts[a] += 1;
    // OVER_MAX is a synthetic chip — rows tagged via the display overlay
    // (pos > Max), independent of consolidated_action. A row counts in BOTH
    // its underlying action chip AND OVER_MAX.
    if (_isOverMaxOverlay(r)) counts.OVER_MAX += 1;
  }
  const wrap = $('summaryChips');
  wrap.innerHTML = '';
  const order = ['REMOVE', 'OVER_MAX', 'REDUCE', 'INCREASE', 'ADD', 'HOLD', 'NONE'];
  const all = document.createElement('div');
  all.className = 'act-chip' + (state.filters.action === '' && !state.filters.buys_sells ? ' active' : '');
  all.innerHTML = `<span>ALL</span><span class="count">${state.baseRows.length}</span>`;
  all.onclick = () => {
    state.filters.action = '';
    state.filters.buys_sells = '';
    const buyBtn = $('buyToggle');  if (buyBtn) buyBtn.classList.remove('active');
    const sellBtn = $('sellToggle'); if (sellBtn) sellBtn.classList.remove('active');
    applyClientFilter();
  };
  wrap.appendChild(all);
  for (const a of order) {
    const chip = document.createElement('div');
    const disp = actionDisplay(a);
    chip.className = 'act-chip act-chip-' + a.toLowerCase()
                   + (state.filters.action === a ? ' active' : '');
    chip.title = disp.label || a;
    chip.innerHTML = `<span>${actionText(disp)}</span><span class="count">${counts[a] || 0}</span>`;
    chip.onclick = () => {
      state.filters.action = (state.filters.action === a) ? '' : a;
      applyClientFilter();
    };
    wrap.appendChild(chip);
  }
}

// Set of every source code present in the current dataset (winning + other).
function _availableSources() {
  const have = new Set();
  for (const r of state.allRows) {
    if (r.winning_source) have.add(r.winning_source);
    for (const s of _sourcesOf(r)) {
      const c = s.source || s.source_code || '';
      if (c) have.add(c);
    }
  }
  return have;
}

function renderSourceFilter() {
  const sel = $('sourceFilter');
  const have = _availableSources();
  // preserve current selection if still present
  const cur = state.filters.source;
  sel.innerHTML = '<option value="">All</option>';
  for (const c of Array.from(have).sort()) {
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    if (c === cur) o.selected = true;
    sel.appendChild(o);
  }
}

function renderSectorFilter() {
  const sel = $('sectorFilter');
  if (!sel) return;
  const cur = state.filters.sector;
  const sectors = new Set();
  for (const r of state.allRows) { if (r.sector) sectors.add(r.sector); }
  sel.innerHTML = '<option value="">All Sectors</option>';
  for (const s of Array.from(sectors).sort()) {
    const o = document.createElement('option');
    o.value = s; o.textContent = s;
    if (s === cur) o.selected = true;
    sel.appendChild(o);
  }
}

function renderAssetClassFilter() {
  const sel = $('assetClassFilter');
  if (!sel) return;
  const cur = state.filters.asset_class;
  const classes = new Set();
  for (const r of state.allRows) {
    const v = r.real_asset_class || r.asset_class || '';
    if (v) classes.add(v);
  }
  sel.innerHTML = '<option value="">All Asset Classes</option>';
  for (const c of Array.from(classes).sort()) {
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    if (c === cur) o.selected = true;
    sel.appendChild(o);
  }
}

// Count of non-default active filters (for the N-active badge)
function _countActiveFilters() {
  const f = state.filters;
  let n = 0;
  if (f.action) n++;
  if (f.buys_sells) n++;
  if (f.source) n++;
  if (f.held_only) n++;
  if (f.sector) n++;
  if (f.asset_class) n++;
  if (f.conviction !== 'any') n++;
  if (f.amt_min > 0) n++;
  if (f.show_no_action) n++;
  if (f.show_zero_amt) n++;
  if (f.show_suppressed) n++;
  if (f.show_acted) n++;
  if (f.symbol_search) n++;
  return n;
}

function updateFilterBadge() {
  const badge = $('filterActiveBadge');
  if (!badge) return;
  const n = _countActiveFilters();
  if (n > 0) {
    badge.textContent = n;
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

// localStorage persistence
const LS_KEY = 'act_filters_v2';
function saveFiltersToStorage() {
  try {
    const f = state.filters;
    const toSave = {
      source: f.source, held_only: f.held_only, show_acted: f.show_acted,
      show_suppressed: f.show_suppressed, show_no_action: f.show_no_action,
      show_zero_amt: f.show_zero_amt, symbol_search: f.symbol_search,
      sector: f.sector, asset_class: f.asset_class, conviction: f.conviction,
      amt_min: f.amt_min, buys_sells: f.buys_sells,
    };
    localStorage.setItem(LS_KEY, JSON.stringify(toSave));
  } catch (_) {}
}

function loadFiltersFromStorage() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    const f = state.filters;
    if (saved.source !== undefined)       f.source = saved.source;
    if (saved.held_only !== undefined)    f.held_only = saved.held_only;
    if (saved.show_acted !== undefined)   f.show_acted = saved.show_acted;
    if (saved.show_suppressed !== undefined) f.show_suppressed = saved.show_suppressed;
    if (saved.show_no_action !== undefined) f.show_no_action = saved.show_no_action;
    if (saved.show_zero_amt !== undefined) f.show_zero_amt = saved.show_zero_amt;
    if (saved.symbol_search !== undefined) f.symbol_search = saved.symbol_search;
    if (saved.sector !== undefined)       f.sector = saved.sector;
    if (saved.asset_class !== undefined)  f.asset_class = saved.asset_class;
    if (saved.conviction !== undefined)   f.conviction = saved.conviction;
    if (saved.amt_min !== undefined)      f.amt_min = Number(saved.amt_min) || 0;
    if (saved.buys_sells !== undefined)   f.buys_sells = saved.buys_sells;
  } catch (_) {}
}

function syncFilterUi() {
  // Sync all UI elements to current state.filters
  const f = state.filters;
  const heldOnly = $('heldOnly');     if (heldOnly) heldOnly.checked = f.held_only;
  const showActed = $('showActed');   if (showActed) showActed.checked = f.show_acted;
  const showSup = $('showSuppressed'); if (showSup) showSup.checked = f.show_suppressed;
  const showNA = $('showNoAction');   if (showNA) showNA.checked = f.show_no_action;
  const showZ = $('showZeroAmt');     if (showZ) showZ.checked = f.show_zero_amt;
  const sym = $('symbolSearch');      if (sym) sym.value = f.symbol_search || '';
  // conviction segmented
  document.querySelectorAll('#convictionCtrl button').forEach(b => {
    b.classList.toggle('seg-active', b.dataset.conv === f.conviction);
  });
  // amt segmented
  document.querySelectorAll('#amtCtrl button').forEach(b => {
    b.classList.toggle('seg-active', Number(b.dataset.amt) === f.amt_min);
  });
  // buy/sell toggle
  const buyBtn  = $('buyToggle');  if (buyBtn)  buyBtn.classList.toggle('active', f.buys_sells === 'buy');
  const sellBtn = $('sellToggle'); if (sellBtn) sellBtn.classList.toggle('active', f.buys_sells === 'sell');
}

function clearAllFilters() {
  const f = state.filters;
  f.action = ''; f.buys_sells = ''; f.source = ''; f.held_only = false;
  f.show_acted = false; f.show_suppressed = false; f.show_no_action = false;
  f.show_zero_amt = false; f.symbol_search = ''; f.sector = ''; f.asset_class = '';
  f.conviction = 'any'; f.amt_min = 0;
  // Reset sort to default actionability order (updateSortIndicators called in renderGrid)
  state.sort = { key: '_priority', dir: -1, type: 'num' };
  // Reset show_acted / show_suppressed -> requires refetch
  syncFilterUi();
  loadActionable();
}

// ---- grid ----
// Helper: render other (non-winning) source actions as inline pills
function _renderOtherSources(r) {
  let sources = r.source_actions;
  if (typeof sources === 'string') {
    try { sources = JSON.parse(sources); } catch (_) { sources = []; }
  }
  if (!Array.isArray(sources) || sources.length === 0) return '';
  
  const winning = (r.winning_source || '').toString();
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  
  if (others.length === 0) return '';

  // Strongest action first — same severity order as the consolidation sort.
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  
  // colorCls from actions.js (single source of truth)
  return others.map(s => {
    const srcCode = (s.source || s.source_code || '?');
    const src = srcCode.toLowerCase();
    const action = (s.action || '').toUpperCase() || '?';
    const actDisp = actionDisplay(action);
    const colorCls = (actDisp.colorCls || 'act-neutral') + '-tint';
    const actLabel = actionText(actDisp) || action;
    return `<span data-srcpop data-sym="${escapeHtml(r.tos_symbol)}" data-src="${escapeHtml(srcCode)}" class="act-badge act-badge-sm ${colorCls}" style="margin-right:4px; cursor:help;" title="${escapeHtml(srcCode)}">${escapeHtml(actLabel)} <span style="font-size:8px; opacity:0.8;">(${src})</span></span>`;
  }).join('');
}

// ---- source-data hover popover ----
const _srcDataCache = new Map();   // symbol -> { RR:{...}, ETF:{...}, ... }
let _srcPopEl = null;
const _FEED_SRC = ['RR', 'ETF', 'PS', 'SSS'];

function _saFor(row, src) {
  let sa = row && row.source_actions;
  if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
  if (!Array.isArray(sa)) return null;
  return sa.find(s => (s.source || s.source_code || '') === src) || null;
}

// Action severity rank — REMOVE strongest. Mirrors the consolidation sort.
const ACTION_RANK = { REMOVE: 4, REDUCE: 3, INCREASE: 2, ADD: 1, HOLD: 0 };

// Action color lookup: returns a CSS class from the token palette (actions.js).
// Used to color the "was X" overlay annotation via the act-* CSS utility classes.
function _actionColorCls(act) {
  return actionDisplay(act).colorCls || 'act-neutral';
}
// actionDisplay() is provided by actions.js (loaded before this script).
// actionLabel: plain-English label for a row's consolidated_action.
// OVER_MAX synthetic overlay gets its own display entry.
function actionLabel(row) {
  if (_isOverMaxOverlay(row)) return actionText(actionDisplay('OVER_MAX'));
  const a = ((row && row.consolidated_action) || 'NONE').toUpperCase();
  return actionText(actionDisplay(a));
}
// Badge color class — REDUCE (orange) when the over-Max overlay fires so
// the sell intent reads at a glance; otherwise mirrors consolidated_action.
function _badgeAction(row) {
  if (_isOverMaxOverlay(row)) return 'REDUCE';
  return ((row && row.consolidated_action) || 'NONE').toUpperCase();
}
// True when the row's held position exceeds the category Max and the
// SELL→MAX overlay applies (badge label + AMT$ + "was X" annotation).
// REMOVE rows are excluded — sell-all is stronger than sell-to-max.
function _isOverMaxOverlay(row) {
  if (!row) return false;
  if ((row.consolidated_action || '').toUpperCase() === 'REMOVE') return false;
  const pos = Number(row.current_position_dollar);
  const max = Number(row.target_max_dollar);
  return isFinite(pos) && isFinite(max) && max > 0 && pos > max;
}

// Parsed source_actions array for a row (winning + every "other" source).
function _sourcesOf(row) {
  let sa = row && row.source_actions;
  if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
  return Array.isArray(sa) ? sa : [];
}

// ── Source sub-line (Action cell second line) ──────────────────────────────
// Returns compact HTML like: RR·<colored>BS</colored>  II·<colored>BM</colored>
// Winning source first, then others sorted by severity.  Empty → ''.
function _srcSubLineHtml(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  // Put winning source first, then sort remainder by severity.
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const ordered = winner.concat(others);
  const tokens = ordered.map(s => {
    const srcCode = escapeHtml(s.source || s.source_code || '?');
    const act = (s.action || '').toUpperCase();
    const disp = actionDisplay(act);
    const colorCls = disp.colorCls || 'act-neutral';
    const actText = escapeHtml(actionText(disp) || act || '?');
    return `<span class="act-src-token"><span class="act-src-label">${srcCode}</span>·<span class="${colorCls}">${actText}</span></span>`;
  });
  return `<div class="act-src-sub">${tokens.join('')}</div>`;
}

// ── Pass 1: Conviction ─────────────────────────────────────────────────────
// Count source_actions entries whose action aligns with consolidated_action direction.
// "align" = same sell/buy side (REMOVE/REDUCE/OVER_MAX → sell; INCREASE/ADD → buy).
function _agreeingSources(row) {
  const ca = (row.consolidated_action || '').toUpperCase();
  const isSell = ca === 'REMOVE' || ca === 'REDUCE' || ca === 'OVER_MAX';
  const isBuy  = ca === 'INCREASE' || ca === 'ADD';
  const sources = _sourcesOf(row);
  if (!sources.length) return 0;
  let count = 0;
  for (const s of sources) {
    const sa = (s.action || '').toUpperCase();
    if (isSell && (sa === 'REMOVE' || sa === 'REDUCE')) count++;
    else if (isBuy && (sa === 'INCREASE' || sa === 'ADD')) count++;
  }
  return count;
}

// True if any fired rule has positive 20d edge.
function _hasPositiveEdge(row) {
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return false;
  const sc = state.scorecard || {};
  for (const f of fires) {
    const id = String(f.rule_id || f.id || f);
    if (sc[id] && sc[id].edge_20d != null && Number(sc[id].edge_20d) > 0.5) return true;
  }
  return false;
}

// Conviction badge HTML for grid cell.
function _convictionHtml(row) {
  const n = _agreeingSources(row);
  const edge = _hasPositiveEdge(row);
  const cls = edge ? 'conviction-badge edge-positive' : 'conviction-badge edge-none';
  const sources = _sourcesOf(row);
  const labels = sources
    .filter(s => {
      const ca = (row.consolidated_action || '').toUpperCase();
      const sa = (s.action || '').toUpperCase();
      const isSell = ca === 'REMOVE' || ca === 'REDUCE';
      const isBuy  = ca === 'INCREASE' || ca === 'ADD';
      return (isSell && (sa === 'REMOVE' || sa === 'REDUCE')) || (isBuy && (sa === 'INCREASE' || sa === 'ADD'));
    })
    .map(s => s.source || s.source_code || '?')
    .join(', ');
  const tip = labels || 'no agreeing sources';
  return `<span class="${cls}" title="${escapeHtml(tip)}">${n}&#10003;${edge ? ' &#9650;' : ''}</span>`;
}

// ── Final Call — reconcile three action lenses into one decision ────────────
//
// Scale: sell-all=-3, sell-some=-2, sell-overage=-1, hold=0,
//        buy-some/min/more=+2
// (OVER_MAX synthetic uses -1 so it sorts below genuine sells.)
var _FC_SCALE = {
  SA: -3, REMOVE: -3,
  SS: -2, STM: -2, REDUCE: -2,
  OVER_MAX: -1,
  HOLD: 0, NONE: 0,
  BS: 2, INCREASE: 2, BMN: 2, ADD: 2, BM: 2,
};

function _fcStrength(code) {
  if (!code) return 0;
  var v = _FC_SCALE[('' + code).toUpperCase()];
  return (v !== undefined) ? v : 0;
}

// Best-matching action display for a numeric strength (pick the canonical code
// that sits nearest to the target strength, honouring sign).
function _fcStrengthToAction(strength, consolidated) {
  // Round to nearest integer for lookup
  var s = Math.round(strength);
  if (s <= -3) return actionDisplay('SA');
  if (s === -2) return actionDisplay('SS');
  if (s === -1) return actionDisplay('OVER_MAX');
  if (s === 0)  return actionDisplay('HOLD');
  // positive: prefer what consolidated_action says if same side
  var ca = (consolidated || '').toUpperCase();
  if (s >= 2) {
    if (ca === 'ADD' || ca === 'BMN') return actionDisplay('ADD');
    if (ca === 'BM')  return actionDisplay('BM');
    return actionDisplay('INCREASE');
  }
  return actionDisplay('HOLD');
}

/**
 * finalCall(row) -> {label, code, side, strength, confidence, feasible}
 *
 * Two-driver hierarchical decision:
 *   Sources (consolidated_action) = strategic: gates ownership (own it or exit).
 *   Technical (rr_action)         = tactical: trim/add while owning.
 *   Rules/edge are NOT consulted here — kept in the Rules column for manual
 *   cross-reference only.
 */
function finalCall(row) {
  var ca  = (row.consolidated_action || '').toUpperCase();
  var rra = (row.rr_action           || '').toUpperCase();

  // ── 0. No recommendation at all ──────────────────────────────────────────
  if (!ca || ca === 'NONE') {
    var dispNone = actionDisplay('HOLD');
    return {
      label: dispNone.label, code: dispNone.code,
      side: 'neutral', strength: 0,
      confidence: 'none', feasible: false,
    };
  }

  // ── Helper classifiers ────────────────────────────────────────────────────
  var caOverMax  = _isOverMaxOverlay(row);
  var isHeld     = !!row.held_today;
  var atMax      = caOverMax;  // position already exceeds category Max

  // Sources side categorisation
  var srcIsExit    = (ca === 'REMOVE' || ca === 'SA');
  var srcIsReduce  = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
  var srcIsBuy     = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
  var srcIsAdd     = (ca === 'ADD' || ca === 'BMN');  // specifically "ADD to position / BUY TO MIN"
  var srcIsHold    = (!srcIsExit && !srcIsReduce && !srcIsBuy);  // HOLD or neutral

  // Technical side categorisation
  var techIsSell   = (rra === 'SS' || rra === 'STM' || rra === 'SO' ||
                      rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
  var techIsBuy    = (rra === 'BS' || rra === 'BM' ||
                      rra === 'INCREASE');
  var techIsBuyMin = (rra === 'BMN' || rra === 'ADD');
  var techIsNeutral = (!techIsSell && !techIsBuy && !techIsBuyMin);

  // ── 1. Feasibility (pre-check): never sell unheld, never buy past Max ─────
  // Selling an unheld position is infeasible; we'll guard this below per-path.
  // Buying past Max is infeasible; over-max rows are flagged via caOverMax.

  // ── 2. Strategic gate: SELL ALL / REMOVE → exit regardless of Technical ──
  if (srcIsExit || caOverMax) {
    // Over-max uses the OVER_MAX strength so it sorts below genuine SELL ALL.
    var exitStrength = caOverMax ? _FC_SCALE['OVER_MAX'] : _FC_SCALE['SA'];
    var exitCode     = caOverMax ? 'OVER_MAX' : 'SA';
    var exitDisp     = actionDisplay(exitCode);
    // Feasibility: can only sell if held (or over-max which implies held via overlay).
    if (!isHeld && !caOverMax) {
      var holdDisp = actionDisplay('HOLD');
      return {
        label: holdDisp.label, code: holdDisp.code,
        side: 'neutral', strength: 0,
        confidence: 'gate',
        gateReason: 'Exit signal but not held — no action feasible',
        feasible: false,
      };
    }
    return {
      label:      exitDisp.label,
      code:       exitDisp.code,
      side:       exitDisp.side,
      cls:        exitDisp.cls,
      strength:   exitStrength,
      confidence: 'gate',
      gateReason: caOverMax
        ? 'Over category Max — trim back to cap'
        : 'Sources: exit signal — Technical not evaluated',
      feasible:   true,
    };
  }

  // ── 3. Sources endorses owning → Technical drives tactical action ─────────
  // At this point ca is REDUCE, HOLD, INCREASE, ADD, or equivalent.

  // Don't-initiate guard: NOT held AND Sources doesn't endorse buying → HOLD
  if (!isHeld && !srcIsBuy) {
    var holdD = actionDisplay('HOLD');
    return {
      label: holdD.label, code: holdD.code,
      side: 'neutral', strength: 0,
      confidence: 'gate',
      gateReason: 'Not held + Sources don’t endorse buying — hold',
      feasible: true,
    };
  }

  var fcDisp, fcStrength, confidence, gateReason;

  if (techIsSell) {
    // Technical says trim — but only if held (can't sell what you don't have).
    if (!isHeld) {
      // Technical wants to sell, but not held → HOLD (infeasible sell).
      // At this point srcIsBuy must be true (the !isHeld && !srcIsBuy guard above
      // already returned). So Sources says buy but Technical says sell — genuine
      // conflict, even though the sell is infeasible.  Use 'mixed', not 'high'.
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'mixed';
    } else if (srcIsReduce) {
      // Sources AND Technical both say sell → High confidence SELL SOME
      fcDisp     = actionDisplay('SS');
      fcStrength = _FC_SCALE['SS'];
      confidence = 'high';
    } else {
      // Sources owns/buys, Technical says sell → Mixed (conflict)
      fcDisp     = actionDisplay('SS');
      fcStrength = _FC_SCALE['SS'];
      confidence = 'mixed';
    }
  } else if (techIsBuy || techIsBuyMin) {
    // Technical says add.
    // Note: at this point srcIsBuy is true OR isHeld is true (the don't-initiate
    // guard above already filtered out !isHeld && !srcIsBuy).
    if (srcIsReduce) {
      // Sources is souring (REDUCE), Technical says buy — conflict: downgrade to HOLD
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'mixed';
    } else if (atMax) {
      // Already at/past Max — cap: can't add more
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'gate';
      gateReason = 'At/over category Max — cannot add more';
    } else if (!isHeld && srcIsAdd) {
      // Not yet held, Sources says ADD (buy-to-min intent) → BUY TO MIN (establish)
      fcDisp     = actionDisplay('BMN');
      fcStrength = _FC_SCALE['BMN'];
      confidence = 'high';
    } else {
      // Sources owns/buys (or held), Technical says buy — add.
      // Prefer BM (buy-more) if either lens calls for it strongly.
      var buyCode = (rra === 'BM' || ca === 'BM' || ca === 'INCREASE' || ca === 'BS') ? 'BM' : 'BS';
      fcDisp     = actionDisplay(buyCode);
      fcStrength = _FC_SCALE[buyCode] || _FC_SCALE['BS'];
      confidence = (srcIsBuy) ? 'high' : 'mixed';
    }
  } else {
    // Technical is neutral/BMN/HOLD
    if (!isHeld && srcIsAdd) {
      // Not held, Sources says ADD → BUY TO MIN (establish position)
      fcDisp     = actionDisplay('BMN');
      fcStrength = _FC_SCALE['BMN'];
      confidence = 'gate';
      gateReason = 'Sources says ADD, Technical neutral — establishing position';
    } else if (srcIsReduce) {
      // Sources souring, Technical neutral → HOLD (no action but watch)
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      // Mild conflict: Sources wants down, Technical neutral
      confidence = 'mixed';
    } else {
      // Sources neutral/hold, Technical neutral — no active signal from either lens
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'gate';
      gateReason = 'No active signal — Sources and Technical both neutral';
    }
  }

  return {
    label:      fcDisp.label,
    code:       fcDisp.code,
    side:       fcDisp.side,
    cls:        fcDisp.cls,
    strength:   fcStrength,
    confidence: confidence,
    gateReason: gateReason || null,
    feasible:   true,
  };
}

// HTML for the Final Call cell (label + confidence badge).
function _finalCallHtml(row) {
  var fc = finalCall(row);
  if (!fc.feasible || fc.confidence === 'none') {
    return '<span style="color:#cbd5e1;">—</span>';
  }
  var text = actionText(fc);  // code-only (e.g. "SA"), full label in tooltip via fc.label
  // Badge
  var badgeHtml;
  if (fc.confidence === 'high') {
    badgeHtml = '<span class="fc-conf-badge fc-conf-high" title="Sources and Technical align">High</span>';
  } else if (fc.confidence === 'gate') {
    var gateTitle = fc.gateReason || 'Deterministic gate — Technical not evaluated';
    badgeHtml = '<span class="fc-conf-badge fc-conf-gate" title="' + escapeHtml(gateTitle) + '">Gate</span>';
  } else {
    badgeHtml = '<span class="fc-conf-badge fc-conf-mixed" title="Sources and Technical conflict — cross-check the Rules column">&#9888; Mixed</span>';
  }
  // Color via actions.js token (act-*-tint gives soft colored fill + colored text + border)
  var fcDisp = actionDisplay(fc.code || (fc.side === 'sell' ? 'SA' : fc.side === 'buy' ? 'BS' : 'HOLD'));
  var colorCls = (fcDisp.colorCls || 'act-neutral') + '-tint';
  return '<span class="act-badge ' + colorCls + '" title="' +
         escapeHtml(fc.label || text) + '">' +
         escapeHtml(text) + '</span> ' + badgeHtml;
}

// ── Pass 2: Priority score ──────────────────────────────────────────────────
// Priority = buysell SEQ of the Final Call action code (from ref_param_lookup).
// Sort direction is DESCENDING so the highest seq (SA=21) appears at the top.
//
// Feasibility gate: infeasible Final Call (e.g. unheld SELL ALL → HOLD)
// receives seq = -1 so it sinks below all real codes (lowest seqs start at 3).
//
// Codes not present in the buysell map (HOLD, OVER_MAX, none) also receive
// seq = -1 and sort to the bottom. Dollars at stake break ties within the
// same seq tier (×1e12 keeps tiers from crossing).
function _computePriority(row) {
  var fc = finalCall(row);
  var amt = Math.abs(Number(row._amt) || 0);
  if (!fc.feasible) {
    // Infeasible: sink to bottom (seq = -1 < all real codes).
    return -1 * 1e12 + amt;
  }
  var code = (fc.code || '').toUpperCase();
  var seqMap = state.buysellSeq || {};
  // OVER_MAX is a synthetic code; map it to SO (SellOverage, seq=12) for sorting.
  if (code === 'OVER_MAX') code = 'SO';
  var seq = (seqMap[code] !== undefined) ? seqMap[code] : -1;
  return seq * 1e12 + amt;
}

// True if `src` drove this row OR appears among its other sources.
function _rowHasSource(row, src) {
  if (!src) return true;
  if ((row.winning_source || '') === src) return true;
  return _sourcesOf(row).some(s => (s.source || s.source_code || '') === src);
}

// Normalized weight delta for `src` on this row — per-source default sort key.
function _sourceWeightDelta(row, src) {
  const e = _sourcesOf(row).find(s => (s.source || s.source_code || '') === src);
  if (!e || e.weight_delta == null) return NaN;
  const n = Number(e.weight_delta);
  return isFinite(n) ? n : NaN;
}

function _renderSourcePop(el, sym, src, feed, loading) {
  if (_srcPopEl !== el) return;
  const pop = $('sourcePop');
  if (!pop) return;
  const row = state.rows.find(r => r.tos_symbol === sym);
  const sa = _saFor(row, src);
  const kv = [];
  let saActionHtml = '';
  if (sa) {
    if (sa.action) {
      const saAct = (sa.action || '').toUpperCase();
      const saDisp = actionDisplay(saAct);
      const saText = actionText(saDisp) || saAct;
      const saCls = (saDisp.colorCls || 'act-neutral') + '-tint';
      saActionHtml = `<span class="act-badge act-badge-sm ${saCls}" style="font-size:10px;">${escapeHtml(saText)}</span>`;
    }
    if (sa.weight != null)       kv.push(['Weight', formatNum(sa.weight)]);
    if (sa.prev_weight != null)  kv.push(['Prev wt', formatNum(sa.prev_weight)]);
    if (sa.weight_delta != null) kv.push(['&#916;', formatNum(sa.weight_delta)]);
  }
  const f = feed && feed[src];
  if (f && f.snapshot_date) kv.push(['Snapshot', f.snapshot_date]);
  const feedKv = [];
  if (src === 'RR' && f) {
    feedKv.push(['Buy Trade', formatNum(f.buy_trade)], ['Sell Trade', formatNum(f.sell_trade)]);
  } else if (src === 'ETF' && f) {
    feedKv.push(['BRR', formatNum(f.brr)], ['TRR', formatNum(f.trr)]);
  } else if (src === 'PS' && f) {
    feedKv.push(['Rank', formatNum(f.rank)]);
  } else if (src === 'SSS' && f) {
    feedKv.push(['Pct Delta', fmtPct(f.pct_delta)],
                ['Analyst Rank', (f.anlst_best_idea_rank == null ? '' : f.anlst_best_idea_rank)]);
  }
  let html = '<div class="sp-title">' + escapeHtml(src) + '</div><table>';
  if (saActionHtml) {
    html += '<tr><td class="k">Action</td><td class="v">' + saActionHtml + '</td></tr>';
  }
  for (const [k, v] of kv) {
    html += '<tr><td class="k">' + k + '</td><td class="v">' + escapeHtml(v) + '</td></tr>';
  }
  const showFeed = feedKv.length || (loading && _FEED_SRC.indexOf(src) >= 0);
  if (showFeed) {
    html += '<tr><td class="sp-sec" colspan="2">Feed</td></tr>';
    if (loading && !feedKv.length) {
      html += '<tr><td class="k" colspan="2">loading...</td></tr>';
    }
    for (const [k, v] of feedKv) {
      html += '<tr><td class="k">' + k + '</td><td class="v">' + escapeHtml(v) + '</td></tr>';
    }
  }
  if (sa && sa.reason) {
    html += '<tr><td class="sp-sec" colspan="2">Reason</td></tr>' +
            '<tr><td colspan="2" style="white-space:normal;">' + escapeHtml(sa.reason) + '</td></tr>';
  }
  html += '</table>';
  pop.innerHTML = html;
  pop.style.display = 'block';
  const rect = el.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - pop.offsetHeight - 4);
  }
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  }
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
}

async function showSourcePop(el) {
  const sym = el.dataset.sym;
  const src = el.dataset.src;
  if (!sym || !src) return;
  _srcPopEl = el;
  _renderSourcePop(el, sym, src, _srcDataCache.get(sym), !_srcDataCache.has(sym));
  if (!_srcDataCache.has(sym)) {
    let data = {};
    try {
      data = await fetchJson('/api/actionable/source-data?symbol=' +
        encodeURIComponent(sym) + '&date=' + encodeURIComponent(state.date || ''));
    } catch (_) { data = {}; }
    _srcDataCache.set(sym, data);
    _renderSourcePop(el, sym, src, data, false);
  }
}

function hideSourcePop() {
  _srcPopEl = null;
  const pop = $('sourcePop');
  if (pop) pop.style.display = 'none';
}

function initSourcePopover() {
  const body = $('actBody');
  if (!body) return;
  body.addEventListener('mouseover', (e) => {
    const el = e.target.closest('[data-srcpop]');
    if (el && el.dataset.src) showSourcePop(el);
  });
  body.addEventListener('mouseout', (e) => {
    const el = e.target.closest('[data-srcpop]');
    if (!el) return;
    if (e.relatedTarget && el.contains(e.relatedTarget)) return;
    hideSourcePop();
  });
}

// ---- column sorting ----
function sortRows() {
  const { key, dir, type } = state.sort;
  const num = type === 'num';
  state.rows.sort((a, b) => {
    let va = a[key], vb = b[key];
    const aE = va === null || va === undefined || va === '';
    const bE = vb === null || vb === undefined || vb === '';
    if (aE && bE) return 0;
    if (aE) return 1;
    if (bE) return -1;
    if (num) {
      va = Number(va); vb = Number(vb);
      if (isNaN(va) && isNaN(vb)) return 0;
      if (isNaN(va)) return 1;
      if (isNaN(vb)) return -1;
      return (va - vb) * dir;
    }
    va = String(va).toLowerCase();
    vb = String(vb).toLowerCase();
    return va < vb ? -dir : va > vb ? dir : 0;
  });
}

function updateSortIndicators() {
  document.querySelectorAll('#actGrid th.sortable').forEach(th => {
    const base = th.dataset.label || th.textContent.trim();
    if (th.dataset.key === state.sort.key) {
      th.innerHTML = escapeHtml(base) + ' <span class="sort-ind">' +
        (state.sort.dir === 1 ? '&#9650;' : '&#9660;') + '</span>';
    } else {
      th.innerHTML = escapeHtml(base);
    }
  });
}

function initSorting() {
  document.querySelectorAll('#actGrid th.sortable').forEach(th => {
    // Preserve data-label if already set in HTML (e.g. for multi-line headers)
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sort.key === key) {
        state.sort.dir = -state.sort.dir;
      } else {
        state.sort.key = key;
        state.sort.dir = (key === '_metric' && !_metricAscending(state.filters.source)) ? -1 : 1;
        state.sort.type = th.dataset.type || 'str';
      }
      updateSortIndicators();
      renderGrid();
    });
  });
}

function renderGrid() {
  for (const r of state.rows) {
    r._snapshot = _winningSnapshot(r);
    // Re-compute priority and final call here in case scorecard loaded after allRows.
    var fc = finalCall(r);
    r._fc_strength = fc.strength;
    r._fc_code     = fc.code;
    r._fc_side     = fc.side;
    r._priority = _computePriority(r);
  }
  sortRows();
  updateSortIndicators();
  const tb = $('actBody');
  tb.innerHTML = '';
  const total = state.rows.length;
  $('rowCount').textContent = `${total} row${total === 1 ? '' : 's'}`;
  $('emptyState').style.display = total === 0 ? 'block' : 'none';

  const visibleRows = state.showAll ? state.rows : state.rows.slice(0, state.TOP_N);

  for (const r of visibleRows) {
    const tr = document.createElement('tr');
    const action = (r.consolidated_action || 'NONE').toUpperCase();
    const isActed = r._rowActed;
    if (isActed) tr.classList.add('row-acted');
    tr.dataset.sym = r.tos_symbol;

    const pctCls = r.pct_change != null ? (Number(r.pct_change) >= 0 ? 'pct-positive' : 'pct-negative') : '';
    const pctStr = r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : '';
    const priceStr = r.last_price != null ? fmtUsd(r.last_price) : '';
    const isChecked = state.selected.has(r.tos_symbol);

    // TrTnBBRskRng cell: run action through actionDisplay; attach rr-action-cell for hover tooltip
    const rrRaw = r.rr_action || '';
    const rrDisp = actionDisplay(rrRaw);
    const rrHtml = rrRaw
      ? `<span class="act-badge ${(rrDisp.colorCls || 'act-neutral') + '-tint'}" title="${escapeHtml(rrDisp.label || rrRaw)}">${actionText(rrDisp)}</span>`
      : '<span style="color:#cbd5e1;">--</span>';
    const _rrSubLineHtml = (() => {
      const td = r.tn_td_desc || '', bb = r.bb_desc || '', rr = r.rr_desc || '';
      if (!td && !bb && !rr) return '';
      const line = t => `<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">${escapeHtml(t)}</div>`;
      return `<div class="rr-sub-line" style="font-size:9px;color:#94a3b8;line-height:1.4;" data-filled="1">${td ? line('TnTd: ' + td) : ''}${bb ? line('BB: ' + bb) : ''}${rr ? line('RR: ' + rr) : ''}</div>`;
    })();

    // Final Call cell — reconciled action + confidence badge
    const fcHtml = _finalCallHtml(r);
    // Default Act action: use final call code when available, else 'DONE'
    const fcActCode = r._fc_code || 'DONE';

    const posStr = fmtCompact(r.current_position_dollar);
    tr.innerHTML = `
      <td style="padding:4px 6px; text-align:center;">
        <input type="checkbox" class="row-check" data-sym="${escapeHtml(r.tos_symbol)}"${isChecked ? ' checked' : ''}>
      </td>
      <td class="num" style="font-size:11px; color:#475569;">${posStr || '<span style="color:#cbd5e1;">—</span>'}</td>
      <td class="num">
        <span class="${pctCls}" style="font-weight:700;">${pctStr}</span>
        ${priceStr ? `<div style="font-size:10px;color:#94a3b8;">${priceStr}</div>` : ''}
      </td>
      <td class="num">${_convictionHtml(r)}</td>
      <td class="num"><span class="amt-primary">${fmtUsd(r._amt)}</span></td>
      <td style="padding:6px 4px;">
        ${typeof yahooLink === 'function' ? yahooLink(r.tos_symbol) : ''}
        <strong style="font-size:13px;">${escapeHtml(r.tos_symbol || '')}</strong>
        ${r.sector ? `<div style="font-size:9px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px;">${escapeHtml(r.sector)}</div>` : ''}
      </td>
      <td class="act-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" style="padding:6px 4px; cursor:help;">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          <span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}" title="${escapeHtml(actionDisplay(_badgeAction(r)).label || actionLabel(r))}">${actionLabel(r)}</span>
          ${_srcSubLineHtml(r)}
        </div>
        ${_isOverMaxOverlay(r) ? `<div style="font-size:8px;line-height:1;font-weight:600;margin-top:1px;" class="${_actionColorCls(action)}">was ${actionText(actionDisplay(action))}</div>` : ''}
      </td>
      <td class="rr-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" data-date="${escapeHtml(r.as_of_date || state.date || '')}" style="padding:6px 4px; cursor:help;">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          ${rrHtml}
          ${_rrSubLineHtml}
        </div>
      </td>
      <td style="padding:6px 4px;">${fcHtml}</td>
      <td style="padding:4px 6px; max-width:720px; overflow:hidden;">${firesCellHtml(r)}</td>
      <td style="padding:4px 6px;">
        <div class="act-inline-btns">
          <button type="button" class="btn-done btn-inline-done" data-sym="${escapeHtml(r.tos_symbol)}" data-fc="${escapeHtml(fcActCode)}" title="Act: log final call action">&#10003; ${escapeHtml(fcActCode)}</button>
          <button type="button" class="btn-skip btn-inline-skip" data-sym="${escapeHtml(r.tos_symbol)}" title="Skip">&#10007;</button>
          <button type="button" class="btn-snz btn-inline-snz"  data-sym="${escapeHtml(r.tos_symbol)}" title="Snooze">&#128164;</button>
        </div>
      </td>
    `;
    tr.onclick = (e) => {
      if (e.target.closest('.btn-inline-done') || e.target.closest('.btn-inline-skip') ||
          e.target.closest('.btn-inline-snz')  || e.target.closest('.row-check')) return;
      openDrilldown(r);
    };
    tb.appendChild(tr);
  }

  // Top-N collapse bar
  const oldBar = tb.parentElement.querySelector('.show-all-bar');
  if (oldBar) oldBar.remove();
  if (!state.showAll && total > state.TOP_N) {
    const bar = document.createElement('div');
    bar.className = 'show-all-bar';
    bar.innerHTML = `<button>Show all (${total})</button>`;
    bar.querySelector('button').onclick = () => { state.showAll = true; renderGrid(); };
    tb.parentElement.appendChild(bar);
  }

  // Sync select-all checkbox
  const allChk = $('bulkSelectAll');
  if (allChk) {
    allChk.checked = state.selected.size > 0 && state.selected.size >= visibleRows.length;
    allChk.indeterminate = state.selected.size > 0 && state.selected.size < visibleRows.length;
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// ── Pass 3: Bulk bar ───────────────────────────────────────────────────────
function renderBulkBar() {
  const bar = $('bulkBar');
  if (!bar) return;
  const n = state.selected.size;
  if (n > 0) {
    bar.classList.add('visible');
    $('bulkCount').textContent = `${n} selected`;
  } else {
    bar.classList.remove('visible');
  }
}

// Inline action: call the same endpoint as the modal Save/Dismiss.
async function inlineAction(sym, action) {
  if (!sym || !state.date) return;
  const row = state.allRows.find(r => r.tos_symbol === sym);
  const asOf = row ? row.as_of_date : state.date;
  // user_action must be the legacy enum (DONE/SKIPPED/SNOOZED/OVERRIDDEN).
  // The Final Call BuySell code (SA/SS/BM/etc.) goes into action_code.
  const isLegacyAction = ['DONE','SKIPPED','SNOOZED','OVERRIDDEN'].includes((action||'').toUpperCase());
  const userAction = isLegacyAction ? action.toUpperCase() : 'DONE';
  const actionCode = isLegacyAction ? null : action;
  const payload = { as_of_date: asOf, user_action: userAction,
                    action_code: actionCode, user_notes: 'inline' };
  try {
    await fetchJson('/api/actionable/' + encodeURIComponent(sym) + '/action', {
      method: 'POST', body: JSON.stringify(payload),
    });
    // Mark row visually acted; keep in grid until next reload.
    if (row) row._rowActed = true;
    const tr = document.querySelector(`#actBody tr[data-sym="${CSS.escape(sym)}"]`);
    if (tr) tr.classList.add('row-acted');
    showStatus(`${action}: ${sym}`, 'success', 2500);
  } catch (e) {
    showStatus(`${action} failed: ${e.message}`, 'error');
  }
}

async function bulkAction(action) {
  const syms = Array.from(state.selected);
  if (!syms.length) return;
  for (const sym of syms) await inlineAction(sym, action);
  state.selected.clear();
  renderBulkBar();
  renderGrid();
}

// ── Pass 3: Focus mode ─────────────────────────────────────────────────────
function _focusRows() {
  return state.rows.filter(r => !r._rowActed);
}

function openFocusMode() {
  state.focusIdx = 0;
  _renderFocusCard();
  $('focusBackdrop').classList.add('open');
}

function _renderFocusCard() {
  const rows = _focusRows();
  if (!rows.length) {
    $('focusBackdrop').classList.remove('open');
    showStatus('All done! No more rows.', 'success', 3000);
    return;
  }
  if (state.focusIdx >= rows.length) state.focusIdx = rows.length - 1;
  const r = rows[state.focusIdx];
  $('fcProg').textContent = `${state.focusIdx + 1} of ${rows.length}`;
  $('fcSym').textContent = r.tos_symbol || '';
  $('fcAction').innerHTML = `<span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}" style="font-size:16px;padding:4px 14px;">${actionLabel(r)}</span>`;
  $('fcAmt').textContent = fmtUsd(r._amt) || '—';
  // "Why": top fired rule or winning source + reason snippet.
  let why = '';
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (Array.isArray(fires) && fires.length) {
    const topRule = String(fires[0].rule_id || fires[0].id || fires[0]);
    why = 'Rule: ' + topRule;
  } else if (r.winning_source) {
    why = r.winning_source;
    const reason = _winningReason(r);
    if (reason) why += ': ' + reason.slice(0, 80);
  }
  $('fcWhy').textContent = why;
}

function focusAdvance(action) {
  const rows = _focusRows();
  if (!rows.length) return;
  const r = rows[state.focusIdx];
  if (action) {
    inlineAction(r.tos_symbol, action).then(() => {
      state.focusIdx = Math.min(state.focusIdx, _focusRows().length - 1);
      _renderFocusCard();
    });
  } else {
    state.focusIdx = Math.min(state.focusIdx + 1, _focusRows().length - 1);
    _renderFocusCard();
  }
}

// ---- CSV export (current filtered + sorted view) ----
function otherSourcesText(r) {
  let sources = r.source_actions;
  if (typeof sources === 'string') {
    try { sources = JSON.parse(sources); } catch (_) { sources = []; }
  }
  if (!Array.isArray(sources)) return '';
  const winning = (r.winning_source || '').toString();
  return sources
    .filter(s => (s.source || s.source_code || '') !== winning)
    .map(s => `${(s.action || '').toUpperCase()} (${s.source || s.source_code || '?'})`)
    .join('; ');
}

function exportCsv() {
  const cols = [
    ['Symbol',        r => r.tos_symbol],
    ['Change %',      r => r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : ''],
    ['AMT$',          r => r._amt],
    ['Action',        r => r.consolidated_action ? actionText(actionDisplay(r.consolidated_action)) : ''],
    ['TrTnBBRskRng',  r => r.rr_action || ''],
    ['Trig',          r => r.trig_action ? actionText(actionDisplay(r.trig_action)) : ''],
    ['Source',        r => r.winning_source || ''],
    ['Metric',        r => r._metric],
    ['Reason',        r => _winningReason(r)],
    ['Other Sources', r => otherSourcesText(r)],
    ['Sector',        r => r.sector || ''],
    ['Real Asset Class', r => r.real_asset_class || ''],
    // kept in CSV even though removed from table
    ['Pos $',         r => r.current_position_dollar],
    ['Price',         r => r.last_price],
    ['Change $',      r => r.net_chng],
    ['As Of',         r => fmtAsOfExport(r.export_date, r.export_time, r.loaded_at)],
    ['Held',          r => r.held_today ? 'Y' : 'N'],
    ['In My List',    r => r.in_my_list ? 'Y' : 'N'],
    ['Suppressed',    r => r.suppressed_reason || ''],
  ];
  const esc = (v) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [cols.map(c => esc(c[0])).join(',')];
  for (const r of state.rows) {
    lines.push(cols.map(c => esc(c[1](r))).join(','));
  }
  const csv = '\ufeff' + lines.join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `actionable_${state.date || 'export'}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Map a numeric weight back to an {outlook, modifier} label pair.
// Standard convention: BULLISH=3, BEARISH=-3, NEUTRAL=0; "Bench" modifier
// divides the magnitude by 3 → fractional. We infer from magnitude.
function _weightToOutlook(w) {
  if (w === null || w === undefined || w === '' || Number.isNaN(Number(w))) {
    return { label: 'none', cls: 'ol-none', modifier: '' };
  }
  const n = Number(w);
  if (n > 2)       return { label: 'BULLISH', cls: 'ol-bullish', modifier: '' };
  if (n >= 0.5)    return { label: 'BULLISH', cls: 'ol-bullish', modifier: 'Bench' };
  if (n > -0.5 && n < 0.5) return { label: 'NEUTRAL', cls: 'ol-neutral', modifier: '' };
  if (n >= -2)     return { label: 'BEARISH', cls: 'ol-bearish', modifier: 'Bench' };
  return { label: 'BEARISH', cls: 'ol-bearish', modifier: '' };
}

// Render a two-line chip cell. `base` = today's weight, `prev` = yesterday's.
function _outlookChip(base, prev) {
  const a = _weightToOutlook(base);
  const b = _weightToOutlook(prev);
  const aMod = a.modifier ? `<span class="ol-mod">${a.modifier}</span>` : '';
  const bMod = b.modifier ? `<span class="ol-mod">${b.modifier}</span>` : '';
  return `<div class="outlook-cell">
    <div class="ol-today ${a.cls}">${a.label}${aMod}</div>
    <div class="ol-was">was <span class="${b.cls}">${b.label}</span>${bMod}</div>
  </div>`;
}

// Find the winning source's entry inside the source_actions JSONB.
// `sourceActions` may be the parsed array or a JSON string.
function _winningSourceEntry(row) {
  let sa = row.source_actions;
  if (typeof sa === 'string') {
    try { sa = JSON.parse(sa); } catch (_) { sa = []; }
  }
  if (!Array.isArray(sa) || !sa.length) return null;
  const want = (row.winning_source || '').toString();
  return sa.find(s => (s.source || s.source_code || '') === want) || sa[0];
}

// Snapshot date of the winning source's underlying record (ISO string).
function _winningSnapshot(row) {
  const e = _winningSourceEntry(row);
  return (e && e.snapshot_date) ? e.snapshot_date : null;
}

// Reason text for the winning/consolidated action only. Returns '' when the
// winner is a rule group (no per-source entry) so the grid never shows a
// misleading reason borrowed from a non-winning source.
function _winningReason(row) {
  let sa = row.source_actions;
  if (typeof sa === 'string') {
    try { sa = JSON.parse(sa); } catch (_) { sa = []; }
  }
  if (!Array.isArray(sa) || !sa.length) return '';
  const want = (row.winning_source || '').toString();
  const hit = sa.find(s => (s.source || s.source_code || '') === want);
  return hit ? (hit.reason || hit.action_reason || '') : '';
}

// Asset class for the grid/CSV. drv_stks.asset_class is only populated for
// TL-master stocks; ETF-feed / PS symbols (e.g. EQRR) carry the same value in
// position_category. Fall back to it only for those sources.
function _assetClass(r) {
  if (r.asset_class) return r.asset_class;
  const ws = (r.winning_source || '').toUpperCase();
  if (ws === 'ETF' || ws === 'ETFCHG' || ws === 'PS') return r.position_category || '';
  return '';
}

// ---- drilldown ----
async function openDrilldown(row) {
  state.current = row;
  $('modalTitle').textContent = row.tos_symbol;
  $('modalName').textContent = row.tos_symbol || '';
  $('modalSub').textContent = [`as of ${row.as_of_date}`, row.position_category, row.sector].filter(Boolean).join(' · ');

  const chgEl = $('modalPriceChange');
  if (row.net_chng != null && row.pct_change != null) {
    const nc = Number(row.net_chng), pc = Number(row.pct_change);
    const chgCls = nc >= 0 ? 'act-buy-strong' : 'act-sell-strong';
    const fmtAmt = v => { const a = Math.abs(v); return (v < 0 ? '-' : '') + '$' + (a >= 1000 ? Math.round(a).toLocaleString() : a.toFixed(0)); };
    chgEl.innerHTML = `<span class="${chgCls}" style="font-weight:700;font-size:20px;line-height:1.3;">${fmtAmt(nc)} (${pc.toFixed(2)}%)</span>`;
    chgEl.style.display = 'block';
  } else {
    chgEl.innerHTML = '';
    chgEl.style.display = 'none';
  }

  const action = (row.consolidated_action || 'NONE').toUpperCase();
  const kv = $('modalKv');
  kv.innerHTML = `
    <dt>Action</dt><dd><span class="act-badge ${(actionDisplay(_badgeAction(row)).colorCls || 'act-neutral') + '-tint'}">${actionLabel(row)}</span>${_isOverMaxOverlay(row) ? ` <small class="${_actionColorCls(action)}" style="font-weight:600;font-size:9px;">was ${actionText(actionDisplay(action))}</small>` : ''}</dd>
    <dt>Winning source</dt><dd>${row.winning_source || '—'}</dd>
    <dt>Real asset class</dt><dd>${row.real_asset_class || '—'}</dd>
    <dt>Held today</dt><dd>${row.held_today ? 'Yes' : 'No'}</dd>
    <dt>Position $</dt><dd>${fmtUsd(row.current_position_dollar) || '—'}</dd>
    <dt>Price</dt><dd>${fmtUsd(row.last_price) || '—'}</dd>
    <dt>Change</dt><dd>${fmtUsd(row.net_chng)} (<span class="${row.pct_change != null ? (Number(row.pct_change) >= 0 ? 'pct-positive' : 'pct-negative') : ''}">${row.pct_change != null ? (Number(row.pct_change).toFixed(2) + '%') : ''}</span>)</dd>
    <dt>As of</dt><dd>${fmtAsOf(row.derived_at) || '—'}</dd>
    <dt>AMT$</dt><dd><strong>${fmtUsd(row._amt) || '—'}</strong></dd>
    <dt>In My List</dt><dd>${row.in_my_list ? 'Yes' : 'No'}</dd>
    <dt>Suppressed</dt><dd>${row.suppressed_reason || '—'}</dd>
  `;

  // Per-source actions table — each row expands inline to a full
  // current-vs-previous record comparison (toggleCmpRow / loadComparison).
  const srcTbody = $('modalSources').querySelector('tbody');
  srcTbody.innerHTML = '';
  let sourceList = row.source_actions;
  if (typeof sourceList === 'string') {
    try { sourceList = JSON.parse(sourceList); } catch (_) { sourceList = []; }
  }
  if (Array.isArray(sourceList) && sourceList.length) {
    for (const s of sourceList) {
      const srcCode = s.source_code || s.source || '';
      const tr = document.createElement('tr');
      tr.dataset.cmpsrc = srcCode;
      tr.className = 'cmp-src-row';
      const sa = (s.action || '').toUpperCase();
      const _wfmt = (v) => (v == null || v === '') ? ''
                    : (_isPctSource(srcCode) ? fmtPct(v) : v);
      const todayOl = _weightToOutlook(s.weight ?? s.base_weight);
      const prevOl  = _weightToOutlook(s.prev_weight);
      const todayMod = todayOl.modifier ? ` <span class="ol-mod">${todayOl.modifier}</span>` : '';
      const prevMod  = prevOl.modifier  ? ` <span class="ol-mod">${prevOl.modifier}</span>`  : '';
      tr.innerHTML = `
        <td><span class="cmp-caret">&#9656;</span><strong>${escapeHtml(srcCode)}</strong></td>
        <td>${escapeHtml(s.base_weight_method || s.method || '')}</td>
        <td>${fmtMD(s.snapshot_date)}</td>
        <td class="num">${_wfmt(s.base_weight ?? s.weight)}</td>
        <td class="num">${_wfmt(s.prev_weight)}</td>
        <td class="num">${_wfmt(s.weight_delta)}</td>
        <td>${fmtMD(s.prev_date)}</td>
        <td>${escapeHtml(s.analyst_rank ?? '')}</td>
        <td><span class="${todayOl.cls}" style="font-weight:600;">${todayOl.label}</span>${todayMod}</td>
        <td><span class="${prevOl.cls}">${prevOl.label}</span>${prevMod}</td>
        <td>${s.held_today ? 'Y' : 'N'}</td>
        <td>${sa ? `<span class="act-badge ${(actionDisplay(sa).colorCls || 'act-neutral') + '-tint'}">${actionText(actionDisplay(sa)) || sa}</span>` : ''}</td>
        <td style="font-size:10px;">${escapeHtml(s.action_reason || s.reason || '')}</td>
      `;
      tr.addEventListener('click', () => toggleCmpRow(tr, srcCode));
      srcTbody.appendChild(tr);
    }
  } else {
    srcTbody.innerHTML = '<tr><td colspan="13" style="color:var(--text-2,#666); padding:8px;">No per-source actions recorded.</td></tr>';
  }

  // Rules fires — pills are clickable; clicking one opens the atomic-rule popover
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') {
    try { fires = JSON.parse(fires); } catch (_) { fires = []; }
  }
  const firesEl = $('modalFires');
  closeAtomicPopover();
  if (Array.isArray(fires) && fires.length) {
    firesEl.innerHTML = '';
    for (const f of fires) {
      const id    = String(f.rule_id || f.id || f);
      const score = (f.score != null) ? ` <span style="opacity:.65;font-size:10px;">${f.score}</span>` : '';
      const span = document.createElement('span');
      span.className = 'act-badge act-badge-sm pill-rule';
      span.innerHTML = `${escapeHtml(id)}${score}${ruleEdgeBadge(id)}`;
      span.dataset.compositeCode = id;
      span.addEventListener('click', (e) => {
        e.stopPropagation();
        openAtomicPopover(row.tos_symbol, row.as_of_date, id, span);
      });
      firesEl.appendChild(span);
      firesEl.appendChild(document.createTextNode(' '));
    }
  } else {
    firesEl.textContent = '—';
  }

  // Pre-fill snooze date
  $('userAction').value = 'DONE';
  $('userTarget').value = '';
  $('snoozeUntil').value = '';
  $('userNotes').value = '';
  $('actionStatus').textContent = '';

  await loadComparison(row.tos_symbol, row.as_of_date);
  await loadHistory(row.tos_symbol);
  loadRRAnalysis(row.tos_symbol, row.as_of_date);

  $('modalBackdrop').classList.add('open');
}

// ---- inline current-vs-previous record comparison ----
// loadComparison fetches the two source records each rule compared (current
// snapshot vs the prior one) and caches them by source code. Clicking a row in
// the Per-source actions table expands an inline panel showing every column of
// both records side by side. Source-agnostic: whatever columns the API returns
// are rendered, so a new source needs no client change.
const _cmpData = new Map();   // source code -> comparison row from the API

async function loadComparison(symbol, asOf) {
  _cmpData.clear();
  let rows = [];
  try {
    rows = await fetchJson('/api/actionable/comparison?symbol=' +
      encodeURIComponent(symbol) + '&date=' + encodeURIComponent(asOf || ''));
  } catch (_) { rows = []; }
  if (Array.isArray(rows)) {
    for (const r of rows) _cmpData.set(r.source || '', r);
  }
}

// Toggle the inline comparison panel under a per-source row. One open at a time.
function toggleCmpRow(tr, srcCode) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('cmp-expand-row')) {
    next.remove();
    tr.classList.remove('expanded');
    return;
  }
  document.querySelectorAll('#modalSources tr.cmp-expand-row')
          .forEach(el => el.remove());
  document.querySelectorAll('#modalSources tr.cmp-src-row.expanded')
          .forEach(el => el.classList.remove('expanded'));
  const exp = document.createElement('tr');
  exp.className = 'cmp-expand-row';
  const td = document.createElement('td');
  td.colSpan = 13;
  td.innerHTML = _comparisonPanelHtml(srcCode);
  exp.appendChild(td);
  tr.after(exp);
  tr.classList.add('expanded');
}

// Build the Field / Current / Previous / Delta table for one source.
function _comparisonPanelHtml(srcCode) {
  const c = _cmpData.get(srcCode);
  if (!c) {
    return '<div class="cmp-panel"><div class="cmp-empty">No comparison record available for ' +
           escapeHtml(srcCode) + '.</div></div>';
  }
  const cur = c.current || {}, prv = c.previous || {};
  const cf = cur.fields || {}, pf = prv.fields || {};
  // Only the classifier's decision-driving field(s) get highlighted.
  const drivers = new Set(c.driver_fields || []);
  const keys = [];
  for (const k of Object.keys(cf)) keys.push(k);
  for (const k of Object.keys(pf)) if (!keys.includes(k)) keys.push(k);

  const fmtV = (k, v) => (v === null || v === undefined || v === '')
    ? '' : (k === 'pct_delta' ? fmtPct(v) : escapeHtml(String(v)));
  let body =
    '<tr><td class="cmp-field">snapshot_date</td>' +
    '<td class="cmp-val">' + (cur.dropped ? '' : fmtMD(cur.snapshot_date)) + '</td>' +
    '<td class="cmp-val">' + (prv.dropped ? '' : fmtMD(prv.snapshot_date)) + '</td>' +
    '<td class="cmp-val"><span class="cmp-delta-none">&mdash;</span></td></tr>';
  if (!keys.length) {
    body += '<tr><td colspan="4" class="cmp-empty">No record columns returned.</td></tr>';
  }
  for (const k of keys) {
    const cv = cf[k], pv = pf[k];
    const isPct = (k === 'pct_delta');
    const changed = String(cv ?? '') !== String(pv ?? '');
    let delta = '<span class="cmp-delta-none">&mdash;</span>';
    if (changed) {
      const cn = Number(cv), pn = Number(pv);
      if (cv != null && pv != null && cv !== '' && pv !== '' &&
          isFinite(cn) && isFinite(pn)) {
        const d = cn - pn;
        const cls = d > 0 ? 'cmp-delta-up' : 'cmp-delta-down';
        const arrow = d > 0 ? '&#9650;' : '&#9660;';
        const mag = isPct ? fmtPct(Math.abs(d)) : formatNum(Math.abs(d));
        delta = '<span class="' + cls + '">' + arrow + ' ' + mag + '</span>';
      } else {
        delta = '<span class="cmp-delta-changed">changed</span>';
      }
    }
    body += '<tr class="' + (drivers.has(k) ? 'cmp-changed' : '') + '">' +
            '<td class="cmp-field">' + escapeHtml(k) + '</td>' +
            '<td class="cmp-val">' + fmtV(k, cv) + '</td>' +
            '<td class="cmp-val">' + fmtV(k, pv) + '</td>' +
            '<td class="cmp-val">' + delta + '</td></tr>';
  }
  const sideLabel = (rec, kind) => (rec && rec.dropped)
    ? ('not in ' + kind + ' bundle')
    : ((fmtMD(rec && rec.snapshot_date) || '?') +
       ((rec && rec.weight != null) ? (' &middot; wt ' + formatNum(rec.weight)) : ''));
  const _actCode = (c.action || '').toUpperCase();
  const act = _actCode ? '<span class="act-badge ' +
              escapeHtml((actionDisplay(_actCode).colorCls || 'act-neutral') + '-tint') + '">' +
              escapeHtml(actionText(actionDisplay(_actCode)) || _actCode) + '</span> ' : '';
  return '<div class="cmp-panel">' +
    '<div class="cmp-panel-head">' +
      '<span class="cmp-src">' + act + escapeHtml(srcCode) + ' &middot; record comparison</span>' +
      '<span class="cmp-meta">current ' + sideLabel(cur, 'current') +
      '  vs  previous ' + sideLabel(prv, 'previous') + '</span>' +
    '</div>' +
    '<table class="cmp-table">' +
      '<thead><tr><th>Field</th><th>Current</th><th>Previous</th><th>&Delta;</th></tr></thead>' +
      '<tbody>' + body + '</tbody>' +
    '</table>' +
    '<div class="cmp-empty">Highlighted = the field(s) that drive ' + escapeHtml(srcCode) + '&#39;s action. Other rows may differ but are informational.</div>' +
  '</div>';
}

// ---- atomic-rule popover (composite drill-down) ----
const traceCache = new Map();   // key = symbol + '@' + date  ->  trace payload

async function fetchTrace(symbol, asOf) {
  const key = symbol + '@' + asOf;
  if (traceCache.has(key)) return traceCache.get(key);
  const url = '/api/trace/' + encodeURIComponent(symbol) + '?date=' + encodeURIComponent(asOf);
  const payload = await fetchJson(url);
  traceCache.set(key, payload);
  return payload;
}

function closeAtomicPopover() {
  const pop = $('atomicPopover');
  if (pop) pop.classList.remove('open');
  // Clear any "active" pill highlight
  document.querySelectorAll('#modalFires .pill-rule.active')
          .forEach(el => el.classList.remove('active'));
}

async function openAtomicPopover(symbol, asOf, compositeCode, pillEl) {
  const pop = $('atomicPopover');
  const codeEl = $('popComposite');
  const loadingEl = $('popLoading');
  const contentEl = $('popContent');

  // Toggle off if the same pill is clicked again
  if (pillEl && pillEl.classList.contains('active')) {
    closeAtomicPopover();
    return;
  }
  closeAtomicPopover();
  if (pillEl) pillEl.classList.add('active');

  codeEl.textContent = compositeCode;
  contentEl.innerHTML = '';
  loadingEl.style.display = 'block';
  pop.classList.add('open');

  let trace;
  try {
    trace = await fetchTrace(symbol, asOf);
  } catch (e) {
    loadingEl.style.display = 'none';
    contentEl.innerHTML = `<div style="color:#8c1d1d;">Failed to load trace: ${escapeHtml(e.message)}</div>`;
    return;
  }
  loadingEl.style.display = 'none';

  // Filter atomic rules whose rolls_into contains this composite_code
  const atomics = (trace.atomics || []).filter(a =>
    Array.isArray(a.rolls_into) && a.rolls_into.includes(compositeCode)
  );

  if (!atomics.length) {
    contentEl.innerHTML = `<div style="color:var(--text-2,#666); padding:4px;">No atomic rules map to this composite, or the composite has only data/composite members.</div>`;
    return;
  }

  // Sort: fired first (by absolute weight desc), then unfired
  atomics.sort((x, y) => {
    if ((x.fired ? 1 : 0) !== (y.fired ? 1 : 0)) return (y.fired ? 1 : 0) - (x.fired ? 1 : 0);
    return Math.abs(y.weight || 0) - Math.abs(x.weight || 0);
  });

  const rows = atomics.map(a => {
    const fired = !!a.fired;
    const wt = Number(a.weight) || 0;
    const wtClass = wt > 0 ? 'wt-pos' : (wt < 0 ? 'wt-neg' : '');
    return `
      <tr class="${fired ? 'fired' : ''}">
        <td>${a.id ?? ''}</td>
        <td><strong>${escapeHtml(a.rule_name || '')}</strong></td>
        <td style="font-family:ui-monospace,Menlo,monospace; opacity:.75;">${escapeHtml(a.ma_column || '')}</td>
        <td class="num">${formatNum(a.value)}</td>
        <td class="num">${formatNum(a.brkeout_from)}</td>
        <td class="num">${formatNum(a.brkeout_to)}</td>
        <td class="num ${wtClass}">${formatNum(a.weight)}</td>
        <td>${fired ? '✓' : ''}</td>
      </tr>`;
  }).join('');

  contentEl.innerHTML = `
    <table class="atomic-table">
      <thead>
        <tr>
          <th style="width:30px;">#</th>
          <th>Rule</th>
          <th>MA column</th>
          <th class="num">Value</th>
          <th class="num">Brk From</th>
          <th class="num">Brk To</th>
          <th class="num">Weight</th>
          <th style="width:30px;">Fired</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="font-size:10px; color:var(--text-2,#666); padding-top:4px;">
      ${atomics.filter(a => a.fired).length} of ${atomics.length} atomic rules fired for this composite.
    </div>`;
}

function formatNum(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n)) return '';
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(3).replace(/\.?0+$/, '');
}

async function loadRRAnalysis(symbol, date) {
  const sec = $('rrSection');
  const el  = $('rrChart');
  sec.style.display = 'none';
  el.innerHTML = '<span style="color:#94a3b8;font-size:12px;">Loading…</span>';
  try {
    const data = await fetchJson(`/api/actionable/rr-analysis?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`);
    if (data && (data.levels.lrr != null || data.levels.trr != null ||
                 data.levels.trend != null || data.levels.trade != null)) {
      sec.style.display = '';
      if (window.td_common && window.td_common.renderRRAnalysis) {
        window.td_common.renderRRAnalysis(data, el, symbol, date);
      }
    }
  } catch(_) {}
}


async function loadHistory(symbol) {
  const tb = $('modalHistory').querySelector('tbody');
  tb.innerHTML = '';
  $('modalHistoryEmpty').style.display = 'none';
  try {
    const rows = await fetchJson('/api/actionable/history?symbol=' + encodeURIComponent(symbol) + '&limit=50');
    if (!rows.length) {
      $('modalHistoryEmpty').style.display = 'block';
      return;
    }
    for (const h of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${(h.acted_at || '').toString().slice(0, 19).replace('T', ' ')}</td>
        <td>${h.user_id || ''}</td>
        <td>${h.user_action || ''}</td>
        <td>${h.user_action_target || ''}</td>
        <td>${(h.winning_source || '')} / ${h.winning_priority ?? ''}</td>
        <td style="font-size:10px;">${escapeHtml(h.user_notes || '')}</td>
      `;
      tb.appendChild(tr);
    }
  } catch (e) {
    $('modalHistoryEmpty').textContent = 'Failed to load history: ' + e.message;
    $('modalHistoryEmpty').style.display = 'block';
  }
}

async function saveUserAction() {
  if (!state.current) return;
  const payload = {
    as_of_date: state.current.as_of_date,
    user_action: $('userAction').value,
    user_action_target: $('userTarget').value || null,
    snooze_until: $('snoozeUntil').value || null,
    user_notes: $('userNotes').value || null,
  };
  try {
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.tos_symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Saved (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.tos_symbol);
    // Reload grid so the chip updates
    loadActionable();
  } catch (e) {
    $('actionStatus').textContent = 'Save failed: ' + e.message;
  }
}

async function dismissUserAction() {
  // Quick "dismiss this from the actionable list" — log a SKIPPED with no snooze.
  // Notes are preserved if the user typed any; target is forced null because
  // SKIPPED is a no-op-with-rationale, not an override.
  if (!state.current) return;
  const payload = {
    as_of_date: state.current.as_of_date,
    user_action: 'SKIPPED',
    user_action_target: null,
    snooze_until: null,
    user_notes: $('userNotes').value || 'dismissed',
  };
  try {
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.tos_symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Dismissed (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.tos_symbol);
    loadActionable();
  } catch (e) {
    $('actionStatus').textContent = 'Dismiss failed: ' + e.message;
  }
}

// ---- per-row snooze toggle ----
// The row "Snooze" button logs a SKIPPED user action for (snapshot date,
// symbol); "Un-snooze" clears it. Snoozed rows are hidden unless "Show
// acted/snoozed" is on. The action is keyed to the snapshot date, so the next
// data load (a new snapshot date) surfaces the row again.
async function toggleSuppress(symbol, isSuppressed) {
  if (!symbol || !state.date) return;
  try {
    if (isSuppressed) {
      await fetchJson('/api/actionable/' + encodeURIComponent(symbol) +
        '/action?date=' + encodeURIComponent(state.date), { method: 'DELETE' });
    } else {
      await fetchJson('/api/actionable/' + encodeURIComponent(symbol) + '/action', {
        method: 'POST',
        body: JSON.stringify({ as_of_date: state.date,
                               user_action: 'SKIPPED',
                               user_notes: 'suppressed' }),
      });
    }
    await loadActionable();
  } catch (e) {
    showStatus('Snooze toggle failed: ' + e.message, 'error');
  }
}

// ---- wire up ----
document.addEventListener('DOMContentLoaded', async () => {
  // Restore filters before loading data
  loadFiltersFromStorage();
  // initSorting must run before loadDates/renderGrid so th.dataset.label is
  // captured from the clean header text (before sort indicators are injected).
  initSorting();

  await loadSources();
  await loadDates();
  checkFreshness();

  // Sync UI to restored state
  syncFilterUi();

  $('datePicker').addEventListener('change', (e) => {
    state.date = e.target.value;
    loadActionable();
    checkFreshness();
  });
  $('refreshBtn').addEventListener('click', () => { loadActionable(); checkFreshness(); });
  $('staleRederiveBtn').addEventListener('click', rederiveStale);
  $('exportCsvBtn').addEventListener('click', exportCsv);
  initSourcePopover();
  // Inline action buttons (Pass 3)
  $('actBody').addEventListener('click', (e) => {
    const doneBtn = e.target.closest('.btn-inline-done');
    if (doneBtn) {
      e.stopPropagation();
      // Use final call code as the action if available, else 'DONE'
      const actCode = doneBtn.dataset.fc || 'DONE';
      inlineAction(doneBtn.dataset.sym, actCode);
      return;
    }
    const skipBtn = e.target.closest('.btn-inline-skip');
    if (skipBtn) { e.stopPropagation(); inlineAction(skipBtn.dataset.sym, 'SKIPPED'); return; }
    const snzBtn = e.target.closest('.btn-inline-snz');
    if (snzBtn) { e.stopPropagation(); inlineAction(snzBtn.dataset.sym, 'SNOOZED'); return; }
    const chk = e.target.closest('.row-check');
    if (chk) {
      e.stopPropagation();
      const sym = chk.dataset.sym;
      if (chk.checked) state.selected.add(sym); else state.selected.delete(sym);
      renderBulkBar();
      const allChk = $('bulkSelectAll');
      if (allChk) {
        const vis = Array.from(document.querySelectorAll('.row-check'));
        allChk.checked = vis.length > 0 && vis.every(c => c.checked);
        allChk.indeterminate = state.selected.size > 0 && !allChk.checked;
      }
      return;
    }
    const btn = e.target.closest('.btn-suppress');
    if (!btn) return;
    e.stopPropagation();
    toggleSuppress(btn.dataset.sym, btn.dataset.suppressed === '1');
  });

  // Bulk select-all
  $('bulkSelectAll').addEventListener('change', (e) => {
    const vis = Array.from(document.querySelectorAll('.row-check'));
    if (e.target.checked) vis.forEach(c => { state.selected.add(c.dataset.sym); c.checked = true; });
    else { state.selected.clear(); vis.forEach(c => { c.checked = false; }); }
    renderBulkBar();
  });

  // Bulk action buttons
  $('bulkDoneBtn').addEventListener('click', () => bulkAction('DONE'));
  $('bulkSkipBtn').addEventListener('click', () => bulkAction('SKIPPED'));
  $('bulkSnzBtn').addEventListener('click',  () => bulkAction('SNOOZED'));
  $('bulkClearBtn').addEventListener('click', () => { state.selected.clear(); renderBulkBar(); renderGrid(); });

  // Focus mode
  $('focusModeBtn').addEventListener('click', openFocusMode);
  $('fcDoneBtn').addEventListener('click', () => focusAdvance('DONE'));
  $('fcSkipBtn').addEventListener('click', () => focusAdvance('SKIPPED'));
  $('fcSnzBtn').addEventListener('click',  () => focusAdvance('SNOOZED'));
  $('fcNextBtn').addEventListener('click', () => focusAdvance(null));
  $('fcCloseBtn').addEventListener('click', () => $('focusBackdrop').classList.remove('open'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $('focusBackdrop').classList.contains('open')) {
      $('focusBackdrop').classList.remove('open');
    }
  });

  // ── Filter zone wire-ups ────────────────────────────────────────────────────
  $('sourceFilter').addEventListener('change', (e) => {
    state.filters.source = e.target.value;
    state.sort = { key: null, dir: 1, type: 'str' };
    updateSortIndicators();
    applyClientFilter();
  });
  $('heldOnly').addEventListener('change', (e) => {
    state.filters.held_only = e.target.checked;
    applyClientFilter();
  });
  $('showActed').addEventListener('change', (e) => {
    state.filters.show_acted = e.target.checked;
    loadActionable();
  });
  $('showNoAction').addEventListener('change', (e) => {
    state.filters.show_no_action = e.target.checked;
    applyClientFilter();
  });
  $('showZeroAmt').addEventListener('change', (e) => {
    state.filters.show_zero_amt = e.target.checked;
    applyClientFilter();
  });
  $('showSuppressed').addEventListener('change', (e) => {
    state.filters.show_suppressed = e.target.checked;
    loadActionable();
  });
  $('symbolSearch').addEventListener('input', (e) => {
    state.filters.symbol_search = e.target.value;
    applyClientFilter();
  });
  $('sectorFilter').addEventListener('change', (e) => {
    state.filters.sector = e.target.value;
    applyClientFilter();
  });
  $('assetClassFilter').addEventListener('change', (e) => {
    state.filters.asset_class = e.target.value;
    applyClientFilter();
  });

  // Conviction segmented control
  $('convictionCtrl').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-conv]');
    if (!btn) return;
    state.filters.conviction = btn.dataset.conv;
    document.querySelectorAll('#convictionCtrl button').forEach(b =>
      b.classList.toggle('seg-active', b === btn));
    applyClientFilter();
  });

  // $ at stake segmented control
  $('amtCtrl').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-amt]');
    if (!btn) return;
    state.filters.amt_min = Number(btn.dataset.amt) || 0;
    document.querySelectorAll('#amtCtrl button').forEach(b =>
      b.classList.toggle('seg-active', b === btn));
    applyClientFilter();
  });

  // Buys/Sells quick toggle
  $('buyToggle').addEventListener('click', () => {
    state.filters.buys_sells = (state.filters.buys_sells === 'buy') ? '' : 'buy';
    if (state.filters.buys_sells) state.filters.action = '';  // clear chip selection
    $('buyToggle').classList.toggle('active', state.filters.buys_sells === 'buy');
    $('sellToggle').classList.remove('active');
    applyClientFilter();
  });
  $('sellToggle').addEventListener('click', () => {
    state.filters.buys_sells = (state.filters.buys_sells === 'sell') ? '' : 'sell';
    if (state.filters.buys_sells) state.filters.action = '';  // clear chip selection
    $('sellToggle').classList.toggle('active', state.filters.buys_sells === 'sell');
    $('buyToggle').classList.remove('active');
    applyClientFilter();
  });

  // More panel toggle
  $('moreFiltersBtn').addEventListener('click', () => {
    $('morePanel').classList.toggle('open');
    $('moreFiltersBtn').textContent = $('morePanel').classList.contains('open') ? 'Less ✕' : 'More ⋯';
  });

  // Clear all filters
  $('clearFiltersBtn').addEventListener('click', clearAllFilters);

$('modalClose').addEventListener('click', () => $('modalBackdrop').classList.remove('open'));
  $('modalBackdrop').addEventListener('click', (e) => {
    if (e.target === $('modalBackdrop')) $('modalBackdrop').classList.remove('open');
  });
  $('saveActionBtn').addEventListener('click', saveUserAction);
  $('dismissActionBtn').addEventListener('click', dismissUserAction);
  $('closePop').addEventListener('click', () => $('detailPop')?.classList.remove('open'));

  // ── Action column hover popup ──────────────────────────────────────────────
  setupActionCol();
  // ── TrTnBBRskRng column: lazy-load action + hover tooltip ─────────────────
  document.addEventListener('DOMContentLoaded', setupRRActionCol);
  setupRRActionCol();
});

// ── Action-cell hover popup ────────────────────────────────────────────────
// Builds a glance-level "why" popup from fields already on the row.
// Reuses the same fixed-position tooltip pattern as the TrTnBBRskRng popup.

function _actionPopHtml(sym) {
  const r = state.rows.find(row => row.tos_symbol === sym);
  if (!r) return '';

  const action = (r.consolidated_action || 'NONE').toUpperCase();
  const dispAct = actionDisplay(action);
  const actionLbl = actionText(dispAct) || action;

  // Winning source entry
  const winEntry = _winningSourceEntry(r);
  const winSrc   = r.winning_source || (winEntry && (winEntry.source || winEntry.source_code)) || '';
  const winMethod = (winEntry && (winEntry.base_weight_method || winEntry.method)) || '';
  const winReason = _winningReason(r);

  // Section helpers
  const sec = label =>
    `<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:6px 0 2px;">${label}</div>`;
  const kv = (k, v) =>
    `<div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:2px;">
       <span style="color:#475569;white-space:nowrap;">${k}</span>
       <span style="font-weight:600;color:#0f172a;text-align:right;">${v}</span>
     </div>`;

  // ── Header ────────────────────────────────────────────────────────────────
  let html = `<div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;">` +
    `${escapeHtml(sym)} — ` +
    `<span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}">${escapeHtml(actionLbl)}</span>` +
    `</div>`;

  // ── Suppression ────────────────────────────────────────────────────────────
  if (r.suppressed_reason) {
    html += `<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:4px;padding:4px 8px;margin-bottom:6px;font-size:10px;color:#991b1b;font-weight:600;">` +
      `Suppressed: ${escapeHtml(r.suppressed_reason)}</div>`;
  }

  // ── Winning source ─────────────────────────────────────────────────────────
  if (winSrc) {
    html += sec('Winning Source');
    html += kv('Source', escapeHtml(winSrc));
    if (winMethod) html += kv('Method/Metric', escapeHtml(winMethod));
    if (winReason) {
      html += `<div style="font-size:10px;color:#475569;margin-top:3px;white-space:normal;line-height:1.4;">` +
        `${escapeHtml(winReason)}</div>`;
    }
  }

  // ── Other sources ──────────────────────────────────────────────────────────
  let sources = r.source_actions;
  if (typeof sources === 'string') { try { sources = JSON.parse(sources); } catch (_) { sources = []; } }
  if (Array.isArray(sources) && sources.length) {
    // Winning first, then others sorted by action severity
    const winFirst = sources.filter(s => (s.source || s.source_code || '') === winSrc);
    const others = sources.filter(s => (s.source || s.source_code || '') !== winSrc);
    others.sort((a, b) =>
      (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
      (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
    const ordered = [...winFirst, ...others];

    html += sec('All Sources');
    for (const s of ordered) {
      const srcCode = s.source || s.source_code || '?';
      const srcAct  = (s.action || '').toUpperCase() || '?';
      const isWin   = srcCode === winSrc;
      const dispS   = actionDisplay(srcAct);
      const actText = actionText(dispS) || srcAct;
      html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">` +
        `<span style="font-size:10px;color:#475569;min-width:44px;">${escapeHtml(srcCode)}</span>` +
        `<span class="act-badge act-badge-sm ${(actionDisplay(srcAct).colorCls || 'act-neutral') + '-tint'}">${escapeHtml(actText)}</span>` +
        (isWin ? `<span style="font-size:9px;color:#16a34a;font-weight:600;">&#10003; winning</span>` : '') +
        `</div>`;
    }
  }

  // ── Sizing ─────────────────────────────────────────────────────────────────
  const hasSize = r.current_position_dollar != null || r.suggested_target_dollar != null ||
                  r.target_min_dollar != null || r.target_max_dollar != null || r._amt != null;
  if (hasSize) {
    html += sec('Sizing');
    if (r.current_position_dollar != null)  html += kv('Current Pos $', fmtUsd(r.current_position_dollar));
    if (r.suggested_target_dollar != null)  html += kv('Target $',      fmtUsd(r.suggested_target_dollar));
    if (r.target_min_dollar != null)        html += kv('Min $',         fmtUsd(r.target_min_dollar));
    if (r.target_max_dollar != null)        html += kv('Max $',         fmtUsd(r.target_max_dollar));
    if (r._amt != null)                     html += kv('AMT$',          fmtUsd(r._amt));
  }

  return html;
}

function setupActionCol() {
  let tip = document.getElementById('actDetailTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'actDetailTip';
    tip.style.cssText = 'position:fixed;z-index:9999;display:none;background:#fff;color:#1e293b;' +
      'border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;font-size:11px;line-height:1.6;max-width:300px;' +
      'box-shadow:0 4px 16px rgba(0,0,0,0.12);pointer-events:none;';
    document.body.appendChild(tip);
  }

  const body = $('actBody');
  if (!body) return;

  body.addEventListener('mouseover', (e) => {
    const cell = e.target.closest('.act-action-cell');
    if (!cell) return;
    const sym = cell.dataset.sym;
    if (!sym) return;
    tip.innerHTML = _actionPopHtml(sym);
    const rect = cell.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.right + 8;
    if (left + tipW > window.innerWidth - 4) left = rect.left - tipW - 8;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (!e.target.closest('.act-action-cell')) return;
    if (e.relatedTarget && e.target.closest('.act-action-cell')?.contains(e.relatedTarget)) return;
    tip.style.display = 'none';
  });
}

// Cache keyed by "sym@date"
const _rrDetailCache = new Map();

async function _fetchRRDetail(sym, date) {
  const key = sym + '@' + date;
  if (_rrDetailCache.has(key)) return _rrDetailCache.get(key);
  try {
    const d = await fetchJson(`/api/actionable/rr-detail?symbol=${encodeURIComponent(sym)}&date=${encodeURIComponent(date)}`);
    _rrDetailCache.set(key, d);
    return d;
  } catch(_) { return null; }
}

function setupRRActionCol() {
  let tip = document.getElementById('rrDetailTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'rrDetailTip';
    tip.style.cssText = 'position:fixed;z-index:9999;display:none;background:#fff;color:#1e293b;' +
      'border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;font-size:11px;line-height:1.6;max-width:320px;' +
      'box-shadow:0 4px 16px rgba(0,0,0,0.12);pointer-events:none;';
    document.body.appendChild(tip);
  }

  const fmt2 = v => v == null ? '—' : Number(v).toFixed(2);
  const scoreCol = v => v == null ? '#94a3b8' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#94a3b8';

  const body = $('actBody');
  if (!body) return;

  body.addEventListener('mouseover', async (e) => {
    const cell = e.target.closest('.rr-action-cell');
    if (!cell) return;
    const sym = cell.dataset.sym, date = cell.dataset.date;
    if (!sym || !date) return;

    const d = await _fetchRRDetail(sym, date);
    if (!d) return;

    // Update sub-line in the cell with the Trend/Trade · BB · RR component triplet.
    const subLine = cell.querySelector('.rr-sub-line');
    if (subLine && !subLine.dataset.filled) {
      const _sc = v => v == null ? '—' : String(v);
      const _scColor = v => v == null ? '#94a3b8' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#64748b';
      subLine.innerHTML =
        `<span style="color:${_scColor(d.tn_td_action)}">${_sc(d.tn_td_action)}</span>` +
        `<span style="color:#cbd5e1;margin:0 1px;">·</span>` +
        `<span style="color:${_scColor(d.bb_action)}">${_sc(d.bb_action)}</span>` +
        `<span style="color:#cbd5e1;margin:0 1px;">·</span>` +
        `<span style="color:${_scColor(d.rr_action)}">${_sc(d.rr_action)}</span>`;
      subLine.dataset.filled = '1';
    }

    // Look up row price for the tooltip header.
    const rowData = state.rows.find(r => r.tos_symbol === sym);
    const lastPrice = rowData && rowData.last_price != null ? rowData.last_price : null;
    const priceHtml = lastPrice != null
      ? `<span style="font-size:13px;font-weight:700;color:#0f172a;margin-left:6px;">${fmtUsd(lastPrice)}</span>`
      : '';

    const row = (label, val, color) =>
      `<div style="display:flex;justify-content:space-between;gap:12px;">
         <span style="color:#475569;white-space:nowrap;">${label}</span>
         <span style="font-weight:600;color:${color || '#0f172a'};text-align:right;">${val}</span>
       </div>`;
    const rowScore = (label, score, desc) => {
      const sc = score != null ? score : null;
      const scCol = sc == null ? '#94a3b8' : sc > 0 ? '#16a34a' : sc < 0 ? '#dc2626' : '#64748b';
      const scBg  = sc == null ? '#f8fafc' : sc > 0 ? '#f0fdf4' : sc < 0 ? '#fef2f2' : '#f8fafc';
      const scBdr = sc == null ? '#e2e8f0' : sc > 0 ? '#bbf7d0' : sc < 0 ? '#fecaca' : '#e2e8f0';
      return `<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:5px;">
        <span style="font-size:9px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.04em;white-space:nowrap;">${label}</span>
        <span style="font-size:11px;color:${scCol};line-height:1.3;text-align:right;margin-left:auto;">${desc || '—'}</span>
      </div>`;
    };
    const sec = label =>
      `<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:5px 0 2px;">${label}</div>`;
    const shortDesc = (short, desc) => [short ? `<span style="font-weight:700;">${short}</span>` : '', desc].filter(Boolean).join(': ') || '—';

    // ── QR decision path ─────────────────────────────────────────────────────
    // qf/qk/qo are the stored seq values (QF/QK/QO from PARM_LOOKUP_SQL).
    // qr is the ground-truth stored score (QR from Pass 2, which uses the
    // atomic-input QE — potentially a different source than PARM_LOOKUP_SQL QF).
    // Drive the path display from qr (ground truth) with qf/qk/qo as context.
    const qf = d.tn_td_action, qk = d.bb_action, qo = d.rr_action, qr = d.final_score;
    const step = (indent, label, val, note, active) => {
      const pad = '&nbsp;'.repeat(indent * 3);
      const col = active ? '#0f172a' : '#94a3b8';
      const valCol = val < 0 ? '#dc2626' : val > 0 ? '#16a34a' : '#64748b';
      const arrow = active ? '<span style="color:#4338ca;font-weight:700;">→</span>' : '<span style="color:#cbd5e1;">→</span>';
      return `<div style="font-family:monospace;font-size:10px;color:${col};line-height:1.7;">
        ${pad}${label} <span style="font-weight:700;color:${valCol};">${val != null ? val : '—'}</span>
        ${arrow} <span style="color:${active?'#475569':'#cbd5e1'};font-style:italic;">${note}</span>
      </div>`;
    };

    let decisionHtml = '';
    if (qr != null) {
      // Determine which driver caused qr, using qr as ground truth.
      // qf < 0 means Trend/Trade was bearish and should have driven qr = qf.
      // qk < 0 (with qf > 0) means BB was bearish and should have driven qr = qk.
      // Otherwise qr should equal qo (RR signal).
      if (qf != null && qf < 0 && qr < 0) {
        // Trend/Trade bearish wins — consistent with qr.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bearish → wins', true);
      } else if (qf != null && qf > 0 && qk != null && qk < 0 && qr < 0) {
        // BB bearish wins over bullish Trend/Trade — consistent with qr.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'bearish → wins', true);
      } else if (qf != null && qf > 0 && (qk == null || qk >= 0)) {
        // Should be RR path.  Show it, but flag if qr diverges from qo
        // (can happen when the Pass-2 QE source differs from PARM_LOOKUP_SQL QF).
        const rrNote = (qo != null && qr != null && qo !== qr)
          ? 'QO=' + qo + ' but score overridden (see Score)'
          : '→ Score';
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        decisionHtml += step(1, 'BB Range Streak (QK)', qk != null ? qk : 0, 'not bearish → use RR', true);
        decisionHtml += step(2, 'RR (QO)', qo, rrNote, true);
      } else if (qr < 0) {
        // qr is negative but QF path doesn't clearly explain it — show QF as context.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, qf != null && qf < 0 ? 'bearish → wins' : 'see score', true);
      } else {
        // Neutral / no path
        if (qf != null) decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'neutral → null', true);
      }
    } else if (qf != null) {
      // No stored score yet — reconstruct from qf/qk/qo as before.
      if (qf < 0) {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bearish → wins', true);
      } else if (qf > 0) {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        if (qk != null) {
          if (qk < 0) {
            decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'bearish → wins', true);
          } else {
            decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'not bearish → use RR', true);
            decisionHtml += step(2, 'RR (QO)', qo, '→ Score', true);
          }
        }
      } else {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'neutral → null', true);
      }
    }

    tip.innerHTML = `
      <div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;display:flex;align-items:baseline;gap:8px;">${escapeHtml(sym)} — TrTnBBRskRng${priceHtml}</div>
      ${rowScore('Trend/Trade',    d.trend_trade, shortDesc(d.tn_td_short, d.tn_td_desc))}
      ${rowScore('BB Range Streak', d.bb_streak,  shortDesc(d.bb_short,   d.bb_desc))}
      ${rowScore('RR',              d.rr_action,  shortDesc(d.rr_short,   d.rr_desc))}
      ${sec('Decision Path')}
      ${decisionHtml}
      <div style="margin-top:3px;font-size:11px;font-weight:700;color:${scoreCol(qr)};">Score = ${qr != null ? qr : '—'} → ${d.action || '—'}</div>
      ${sec('Levels' + (lastPrice != null ? ' · Price ' + fmtUsd(lastPrice) : ''))}
      ${row('Trade',   fmt2(d.trade), '#ea580c')}
      ${row('Trend',   fmt2(d.trend), '#6366f1')}
      ${row('TRR',     fmt2(d.trr),   '#16a34a')}
      ${row('LRR',     fmt2(d.lrr),   '#16a34a')}
      ${sec('Indices')}
      ${row('TRR Idx', d.trr_idx != null ? String(d.trr_idx) : '—', scoreCol(d.trr_idx))}
      ${row('MRR Idx', d.mrr_idx != null ? String(d.mrr_idx) : '—', scoreCol(d.mrr_idx))}
      ${row('LRR Idx', d.lrr_idx != null ? String(d.lrr_idx) : '—', scoreCol(d.lrr_idx))}`;

    const rect = cell.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.left - tipW - 8;
    if (left < 4) left = rect.right + 8;
    tip.style.left = left + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (!e.target.closest('.rr-action-cell')) return;
    if (e.relatedTarget && e.target.closest('.rr-action-cell')?.contains(e.relatedTarget)) return;
    tip.style.display = 'none';
  });
}
