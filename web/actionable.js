/* Actionable Stocks page logic */

const state = {
  date: null,
  allRows: [],   // full unfiltered dataset for the date
  baseRows: [],  // passes every filter except the action chip (drives chip counts)
  rows: [],      // filtered subset shown in grid
  sort: { key: null, dir: 1, type: 'str' },  // active column sort
  filters: {
    action: '',          // '' | REMOVE | REDUCE | INCREASE | ADD | HOLD
    source: '',
    held_only: false,
    show_acted: false,
    show_suppressed: false,
    source_filter: false,
    other_filter: false,
    show_no_action: false,  // when false, blank-action rows are hidden
    show_zero_amt: false,   // when false, rows with $0 AMT$ are hidden
  },
  current: null,
  sourceMethods: {},   // source_code -> base_weight_method (Metric-column sort)
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
  // Always fetch all rows — action/category filters applied client-side so chip counts stay accurate
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
    applyClientFilter();
  } catch (e) {
    showStatus('Failed to load actionable: ' + e.message, 'error', 0);
  }
}

// Client filters EXCEPT the action chip. Kept separate so the action-chip
// counts can reflect every other active filter.
function matchesBaseFilters(r) {
  if (!state.filters.show_no_action && !r.consolidated_action) return false;
  if (!state.filters.show_zero_amt && !r._amt) return false;
  if (state.filters.source) {
    if (!_rowHasSource(r, state.filters.source)) return false;
  }
  if (state.filters.held_only) {
    if (!r.held_today) return false;
  }
  if (state.filters.source_filter) {
    if (!r.winning_source) return false;
  }
  if (state.filters.other_filter) {
    let sources = r.source_actions;
    if (typeof sources === "string") {
      try { sources = JSON.parse(sources); } catch (_) { sources = []; }
    }
    if (!Array.isArray(sources)) return false;
    const winning = (r.winning_source || '').toString();
    const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
    if (others.length === 0) return false;
  }
  return true;
}

function applyClientFilter() {
  // A source picked in the dropdown can vanish from the dataset (e.g. when
  // switching to a date where that source has no rows). Drop the stale
  // filter so the grid doesn't silently show nothing while the dropdown has
  // already reset itself to "All".
  if (state.filters.source && !_availableSources().has(state.filters.source)) {
    state.filters.source = '';
  }
  // Rows passing every filter except the action chip (drives chip counts).
  state.baseRows = state.allRows.filter(matchesBaseFilters);
  // Apply the action chip on top for the grid itself.
  state.rows = state.baseRows.filter(r => {
    if (!state.filters.action) return true;
    if (state.filters.action === 'OVER_MAX') return _isOverMaxOverlay(r);
    return (r.consolidated_action || 'NONE').toUpperCase() === state.filters.action;
  });
  renderSummary();
  renderSourceFilter();
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
  all.className = 'act-chip' + (state.filters.action === '' ? ' active' : '');
  all.innerHTML = `<span>ALL</span><span class="count">${state.baseRows.length}</span>`;
  all.onclick = () => { state.filters.action = ''; applyClientFilter(); };
  wrap.appendChild(all);
  for (const a of order) {
    const chip = document.createElement('div');
    chip.className = 'act-chip act-chip-' + a.toLowerCase()
                   + (state.filters.action === a ? ' active' : '');
    chip.innerHTML = `<span>${ACTION_LABEL[a] || a}</span><span class="count">${counts[a] || 0}</span>`;
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
  
  const colors = {
    'REMOVE': '#d83a3a',
    'REDUCE': '#e07c1a',
    'INCREASE': '#2f9e2f',
    'ADD': '#1f7af2',
    'HOLD': '#888',
  };
  
  return others.map(s => {
    const srcCode = (s.source || s.source_code || '?');
    const src = srcCode.toLowerCase();
    const action = (s.action || '').toUpperCase() || '?';
    const color = colors[action] || '#999';
    return `<span data-srcpop data-sym="${escapeHtml(r.symbol)}" data-src="${escapeHtml(srcCode)}" style="color:${color}; font-weight:600; margin-right:8px; font-size:11px; cursor:help;">${action} <span style="font-size:9px; opacity:0.7;">(${src})</span></span>`;
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

// Instructional labels for the consolidated Action badge. The raw
// consolidated_action value, winning_source, color, chip and sort are all
// unchanged — only the badge text. When the held position exceeds the
// category Max (REMOVE excepted), the badge overlays SELL→MAX on top of
// whatever action fired, and the original label is shown in small letters
// underneath ("was BUY +1U" etc.) so the source signal is still visible.
const ACTION_LABEL = {
  REMOVE: 'SELL ALL', REDUCE: 'SELL −1U', INCREASE: 'BUY +1U',
  ADD: 'BUY→MIN', HOLD: 'HOLD', NONE: '—',
  // Synthetic pseudo-action used by the SELL→MAX summary chip. Rows are
  // matched via _isOverMaxOverlay (pos > Max), not consolidated_action.
  OVER_MAX: 'SELL→MAX',
};
// Action color palette — matches .badge-action-* in actionable.html. Used
// to tint the "was X" overlay annotation in the original action's color.
const ACTION_COLOR = {
  REMOVE: '#d83a3a', REDUCE: '#e07c1a', INCREASE: '#2f9e2f',
  ADD: '#1f7af2', HOLD: '#888', NONE: '#c4c4c4',
};
function actionLabel(row) {
  if (_isOverMaxOverlay(row)) return 'SELL→MAX';
  const a = ((row && row.consolidated_action) || 'NONE').toUpperCase();
  return ACTION_LABEL[a] || a;
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
  const row = state.rows.find(r => r.symbol === sym);
  const sa = _saFor(row, src);
  const kv = [];
  if (sa) {
    if (sa.action)               kv.push(['Action', sa.action]);
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
  if (!key) {
    // No explicit column sort. When the grid is filtered to one source,
    // Way 1: default-sort by (action severity, then that source's Metric in
    // its best-first direction).
    const src = state.filters.source;
    if (src) {
      const asc = _metricAscending(src);
      state.rows.sort((a, b) => {
        const ar = ACTION_RANK[(a.consolidated_action || '').toUpperCase()] ?? -1;
        const br = ACTION_RANK[(b.consolidated_action || '').toUpperCase()] ?? -1;
        if (ar !== br) return br - ar;
        const am = a._metric, bm = b._metric;
        const aE = am == null, bE = bm == null;
        if (aE && bE) return 0;
        if (aE) return 1;
        if (bE) return -1;
        return asc ? (am - bm) : (bm - am);
      });
    }
    return;
  }
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
      th.innerHTML = base + ' <span class="sort-ind">' +
        (state.sort.dir === 1 ? '&#9650;' : '&#9660;') + '</span>';
    } else {
      th.textContent = base;
    }
  });
}

function initSorting() {
  document.querySelectorAll('#actGrid th.sortable').forEach(th => {
    th.dataset.label = th.textContent.trim();
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
  // Compute each row's Metric and winning-source Snapshot before sorting.
  const _mSrc = state.filters.source;
  for (const r of state.rows) {
    r._metric = _rowMetric(r, _mSrc);
    r._snapshot = _winningSnapshot(r);
  }
  sortRows();
  const tb = $('actBody');
  tb.innerHTML = '';
  $('rowCount').textContent = `${state.rows.length} row${state.rows.length === 1 ? '' : 's'}`;
  $('emptyState').style.display = state.rows.length === 0 ? 'block' : 'none';

  for (const r of state.rows) {
    const tr = document.createElement('tr');
    const action = (r.consolidated_action || 'NONE').toUpperCase();
    const tags = [];
    if (r.in_my_list) tags.push('<span class="pill pill-my">&#9733; MY</span>');
    const fires = Array.isArray(r.rules_engine_fires) ? r.rules_engine_fires
                 : (typeof r.rules_engine_fires === 'string'
                    ? (() => { try { return JSON.parse(r.rules_engine_fires); } catch (_) { return []; } })()
                    : []);
    if (fires && fires.length) tags.push(`<span class="pill pill-rule">RULE&#215;${fires.length}</span>`);
    if (r.suppressed_reason) tags.push(`<span class="pill pill-suppressed">${r.suppressed_reason}</span>`);
    if (r.last_user_action) tags.push(`<span class="pill pill-acted">${r.last_user_action}</span>`);

    const reasonText = _winningReason(r);
    tr.innerHTML = `
      <td style="padding:6px 2px; text-align:center;"><button type="button" class="btn-suppress" data-sym="${escapeHtml(r.symbol)}" data-suppressed="${r.last_user_action === 'SKIPPED' ? '1' : ''}">${r.last_user_action === 'SKIPPED' ? 'Un-snooze' : 'Snooze'}</button></td>
      <td class="num">${r._metric == null ? '' : (_isPctSource(_mSrc) ? fmtPct(r._metric) : formatNum(r._metric))}</td>
      <td class="num">${fmtUsd(r.current_position_dollar)}</td>
      <td style="padding:6px 4px; max-width:70px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${typeof yahooLink === 'function' ? yahooLink(r.symbol) : ''}<strong>${r.symbol || ''}</strong></td>
      <td style="padding:6px 4px;"><span class="badge-action badge-action-${_badgeAction(r)}">${actionLabel(r)}</span>${_isOverMaxOverlay(r) ? `<div style="font-size:8px;line-height:1;font-weight:600;color:${ACTION_COLOR[action] || '#888'};margin-top:1px;">was ${ACTION_LABEL[action] || action}</div>` : ''}</td>
      <td class="num"><strong>${fmtUsd(r._amt)}</strong></td>
      <td class="src-cell" data-srcpop data-sym="${escapeHtml(r.symbol)}" data-src="${escapeHtml(r.winning_source || '')}" style="padding:6px 4px;">${r.winning_source || ''}</td>
      <td style="padding:6px 4px; max-width:170px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(reasonText)}">${escapeHtml(reasonText)}</td>
      <td>${fmtMD(r._snapshot)}</td>
      <td style="padding:6px 4px;">${_renderOtherSources(r)}</td>
      <td>${r.sector || ''}</td>
      <td>${escapeHtml(r.real_asset_class || '')}</td>
      <td class="num">${fmtUsd(r.last_price)}</td>
      <td class="num">${fmtUsd(r.net_chng)}</td>
      <td class="num">${r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : ''}</td>
      <td>${fmtAsOf(r.derived_at)}</td>
      <td>${tags.join(' ')}</td>
    `;
    tr.onclick = (e) => { if (e.target.closest('.btn-suppress')) return; openDrilldown(r); };
    tb.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
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
    ['Symbol',        r => r.symbol],
    ['AMT$',          r => r._amt],
    ['Action',        r => r.consolidated_action || ''],
    ['Source',        r => r.winning_source || ''],
    ['Metric',        r => r._metric],
    ['Reason',        r => _winningReason(r)],
    ['Other Sources', r => otherSourcesText(r)],
    ['Sector',        r => r.sector || ''],
    ['Real Asset Class', r => r.real_asset_class || ''],
    ['Pos $',         r => r.current_position_dollar],
    ['Price',         r => r.last_price],
    ['Change $',      r => r.net_chng],
    ['Change %',      r => r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : ''],
    ['As Of',         r => fmtAsOf(r.derived_at)],
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
  $('modalTitle').textContent = row.symbol;
  $('modalName').textContent = row.symbol || '';
  $('modalSub').textContent = [`as of ${row.as_of_date}`, row.position_category, row.sector].filter(Boolean).join(' · ');

  const action = (row.consolidated_action || 'NONE').toUpperCase();
  const kv = $('modalKv');
  kv.innerHTML = `
    <dt>Action</dt><dd><span class="badge-action badge-action-${_badgeAction(row)}">${actionLabel(row)}</span>${_isOverMaxOverlay(row) ? ` <small style="color:${ACTION_COLOR[action] || '#888'};font-weight:600;font-size:9px;">was ${ACTION_LABEL[action] || action}</small>` : ''}</dd>
    <dt>Winning source</dt><dd>${row.winning_source || '—'}</dd>
    <dt>Real asset class</dt><dd>${row.real_asset_class || '—'}</dd>
    <dt>Held today</dt><dd>${row.held_today ? 'Yes' : 'No'}</dd>
    <dt>Position $</dt><dd>${fmtUsd(row.current_position_dollar) || '—'}</dd>
    <dt>Price</dt><dd>${fmtUsd(row.last_price) || '—'}</dd>
    <dt>Change</dt><dd>${fmtUsd(row.net_chng)} (${row.pct_change != null ? (Number(row.pct_change).toFixed(2) + '%') : ''})</dd>
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
        <td>${sa ? `<span class="badge-action badge-action-${sa}">${sa}</span>` : ''}</td>
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
      span.className = 'pill pill-rule';
      span.innerHTML = `${escapeHtml(id)}${score}`;
      span.dataset.compositeCode = id;
      span.addEventListener('click', (e) => {
        e.stopPropagation();
        openAtomicPopover(row.symbol, row.as_of_date, id, span);
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

  await loadComparison(row.symbol, row.as_of_date);
  await loadHistory(row.symbol);

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
  const act = c.action ? '<span class="badge-action badge-action-' +
              escapeHtml((c.action || '').toUpperCase()) + '">' +
              escapeHtml((c.action || '').toUpperCase()) + '</span> ' : '';
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
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Saved (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.symbol);
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
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Dismissed (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.symbol);
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
  await loadSources();
  await loadDates();
  checkFreshness();

  $('datePicker').addEventListener('change', (e) => {
    state.date = e.target.value;
    loadActionable();
    checkFreshness();
  });
  $('refreshBtn').addEventListener('click', () => { loadActionable(); checkFreshness(); });
  $('staleRederiveBtn').addEventListener('click', rederiveStale);
  $('exportCsvBtn').addEventListener('click', exportCsv);
  initSorting();
  initSourcePopover();
  $('actBody').addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-suppress');
    if (!btn) return;
    e.stopPropagation();
    toggleSuppress(btn.dataset.sym, btn.dataset.suppressed === '1');
  });

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
  $('withSource').addEventListener('change', (e) => {
    state.filters.source_filter = e.target.checked;
    applyClientFilter();
  });
  $('withOther').addEventListener('change', (e) => {
    state.filters.other_filter = e.target.checked;
    applyClientFilter();
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

$('modalClose').addEventListener('click', () => $('modalBackdrop').classList.remove('open'));
  $('modalBackdrop').addEventListener('click', (e) => {
    if (e.target === $('modalBackdrop')) $('modalBackdrop').classList.remove('open');
  });
  $('saveActionBtn').addEventListener('click', saveUserAction);
  $('dismissActionBtn').addEventListener('click', dismissUserAction);
  $('closePop').addEventListener('click', () => $('detailPop')?.classList.remove('open'));
});
