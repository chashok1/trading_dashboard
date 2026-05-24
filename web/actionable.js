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
      if (act === 'REMOVE') {
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
    if (r.winning_source !== state.filters.source) return false;
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
  // Rows passing every filter except the action chip (drives chip counts).
  state.baseRows = state.allRows.filter(matchesBaseFilters);
  // Apply the action chip on top for the grid itself.
  state.rows = state.baseRows.filter(r => {
    if (!state.filters.action) return true;
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
  const counts = { REMOVE: 0, REDUCE: 0, INCREASE: 0, ADD: 0, HOLD: 0, NONE: 0 };
  for (const r of state.baseRows) {
    const a = (r.consolidated_action || 'NONE').toUpperCase();
    if (counts[a] !== undefined) counts[a] += 1;
  }
  const wrap = $('summaryChips');
  wrap.innerHTML = '';
  const order = ['REMOVE', 'REDUCE', 'INCREASE', 'ADD', 'HOLD', 'NONE'];
  const all = document.createElement('div');
  all.className = 'act-chip' + (state.filters.action === '' ? ' active' : '');
  all.innerHTML = `<span>ALL</span><span class="count">${state.baseRows.length}</span>`;
  all.onclick = () => { state.filters.action = ''; applyClientFilter(); };
  wrap.appendChild(all);
  for (const a of order) {
    const chip = document.createElement('div');
    chip.className = 'act-chip act-chip-' + a.toLowerCase()
                   + (state.filters.action === a ? ' active' : '');
    chip.innerHTML = `<span>${a === 'NONE' ? '&mdash;' : a}</span><span class="count">${counts[a] || 0}</span>`;
    chip.onclick = () => {
      state.filters.action = (state.filters.action === a) ? '' : a;
      applyClientFilter();
    };
    wrap.appendChild(chip);
  }
}

function renderSourceFilter() {
  const sel = $('sourceFilter');
  const have = new Set();
  for (const r of state.allRows) {
    if (r.winning_source) have.add(r.winning_source);
  }
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
    feedKv.push(['Pct Delta', formatNum(f.pct_delta)],
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
  if (!key) return;
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
        state.sort.dir = 1;
        state.sort.type = th.dataset.type || 'str';
      }
      updateSortIndicators();
      renderGrid();
    });
  });
}

function renderGrid() {
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
      <td style="padding:6px 4px; max-width:70px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${typeof yahooLink === 'function' ? yahooLink(r.symbol) : ''}<strong>${r.symbol || ''}</strong></td>
      <td class="num"><strong>${fmtUsd(r._amt)}</strong></td>
      <td style="padding:6px 4px;"><span class="badge-action badge-action-${action}">${action === 'NONE' ? '&mdash;' : action}</span></td>
      <td class="src-cell" data-srcpop data-sym="${escapeHtml(r.symbol)}" data-src="${escapeHtml(r.winning_source || '')}" style="padding:6px 4px;">${r.winning_source || ''}</td>
      <td style="padding:6px 4px; max-width:170px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(reasonText)}">${escapeHtml(reasonText)}</td>
      <td style="padding:6px 4px;">${_renderOtherSources(r)}</td>
      <td>${r.sector || ''}</td>
      <td class="num">${fmtUsd(r.current_position_dollar)}</td>
      <td class="num">${fmtUsd(r.target_min_dollar)}</td>
      <td class="num">${fmtUsd(r.target_max_dollar)}</td>
      <td class="num">${fmtUsd(r.units_dollar)}</td>
      <td>${r.winning_priority ?? ''}</td>
      <td>${tags.join(' ')}</td>
    `;
    tr.onclick = () => openDrilldown(r);
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
    ['Reason',        r => _winningReason(r)],
    ['Other Sources', r => otherSourcesText(r)],
    ['Sector',        r => r.sector || ''],
    ['Pos $',         r => r.current_position_dollar],
    ['Min',           r => r.target_min_dollar],
    ['Max',           r => r.target_max_dollar],
    ['Units',         r => r.units_dollar],
    ['Pri',           r => r.winning_priority],
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

// ---- drilldown ----
async function openDrilldown(row) {
  state.current = row;
  $('modalTitle').textContent = row.symbol;
  $('modalName').textContent = row.symbol || '';
  $('modalSub').textContent = [`as of ${row.as_of_date}`, row.position_category, row.sector].filter(Boolean).join(' · ');

  const action = (row.consolidated_action || 'NONE').toUpperCase();
  const kv = $('modalKv');
  kv.innerHTML = `
    <dt>Action</dt><dd><span class="badge-action badge-action-${action}">${action === 'NONE' ? '&mdash;' : action}</span></dd>
    <dt>Winning source</dt><dd>${row.winning_source || '—'} (priority ${row.winning_priority ?? '—'})</dd>
    <dt>Asset class</dt><dd>${row.asset_class || '—'}</dd>
    <dt>Held today</dt><dd>${row.held_today ? 'Yes' : 'No'}</dd>
    <dt>Position $</dt><dd>${fmtUsd(row.current_position_dollar) || '—'}</dd>
    <dt>Target min / max</dt><dd>${fmtUsd(row.target_min_dollar)} / ${fmtUsd(row.target_max_dollar)}</dd>
    <dt>Units (per INCREASE)</dt><dd>${fmtUsd(row.units_dollar) || '—'}</dd>
    <dt>Maintain min</dt><dd>${row.maintain_min ? 'Yes' : 'No'}</dd>
    <dt>AMT$</dt><dd><strong>${fmtUsd(row._amt) || '—'}</strong></dd>
    <dt>In My List</dt><dd>${row.in_my_list ? 'Yes' : 'No'}</dd>
    <dt>Suppressed</dt><dd>${row.suppressed_reason || '—'}</dd>
  `;

  // Per-source actions table
  const srcTbody = $('modalSources').querySelector('tbody');
  srcTbody.innerHTML = '';
  let sourceList = row.source_actions;
  if (typeof sourceList === 'string') {
    try { sourceList = JSON.parse(sourceList); } catch (_) { sourceList = []; }
  }
  if (Array.isArray(sourceList) && sourceList.length) {
    for (const s of sourceList) {
      const tr = document.createElement('tr');
      const sa = (s.action || '').toUpperCase();
      const todayOl = _weightToOutlook(s.weight ?? s.base_weight);
      const prevOl  = _weightToOutlook(s.prev_weight);
      const todayMod = todayOl.modifier ? ` <span class="ol-mod">${todayOl.modifier}</span>` : '';
      const prevMod  = prevOl.modifier  ? ` <span class="ol-mod">${prevOl.modifier}</span>`  : '';
      tr.innerHTML = `
        <td><strong>${s.source_code || s.source || ''}</strong></td>
        <td>${s.base_weight_method || s.method || ''}</td>
        <td class="num">${s.base_weight ?? s.weight ?? ''}</td>
        <td class="num">${s.prev_weight ?? ''}</td>
        <td class="num">${s.weight_delta ?? ''}</td>
        <td>${escapeHtml(s.analyst_rank ?? '')}</td>
        <td><span class="${todayOl.cls}" style="font-weight:600;">${todayOl.label}</span>${todayMod}</td>
        <td><span class="${prevOl.cls}">${prevOl.label}</span>${prevMod}</td>
        <td>${s.held_today ? 'Y' : 'N'}</td>
        <td>${sa ? `<span class="badge-action badge-action-${sa}">${sa}</span>` : ''}</td>
        <td style="font-size:10px;">${escapeHtml(s.action_reason || s.reason || '')}</td>
      `;
      srcTbody.appendChild(tr);
    }
  } else {
    srcTbody.innerHTML = '<tr><td colspan="11" style="color:var(--text-2,#666); padding:8px;">No per-source actions recorded.</td></tr>';
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

  await loadProvenance(row.symbol, row.as_of_date);
  await loadHistory(row.symbol);

  $('modalBackdrop').classList.add('open');
}

// ---- source-data provenance (modal "Source data" section) ----
async function loadProvenance(symbol, asOf) {
  const tb = $('modalProvenance').querySelector('tbody');
  const empty = $('modalProvenanceEmpty');
  tb.innerHTML = '';
  let rows = [];
  try {
    rows = await fetchJson('/api/actionable/provenance?symbol=' +
      encodeURIComponent(symbol) + '&date=' + encodeURIComponent(asOf || ''));
  } catch (_) { rows = []; }
  if (!Array.isArray(rows) || !rows.length) {
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  for (const r of rows) {
    const tr = document.createElement('tr');
    const act = (r.action || '').toUpperCase();
    const loaded = String(r.loaded_at || '').replace('T', ' ').slice(0, 16);
    tr.innerHTML = `
      <td><strong>${escapeHtml(r.source || '')}</strong></td>
      <td>${act ? `<span class="badge-action badge-action-${act}">${act}</span>` : ''}</td>
      <td>${escapeHtml(r.table || '')}</td>
      <td>${escapeHtml(r.snapshot_date || '')}</td>
      <td style="font-size:10px; word-break:break-all;">${escapeHtml(r.source_file || '')}</td>
      <td style="font-size:10px;">${escapeHtml(loaded)}</td>
    `;
    tb.appendChild(tr);
  }
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

// ---- wire up ----
document.addEventListener('DOMContentLoaded', async () => {
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

  $('sourceFilter').addEventListener('change', (e) => {
    state.filters.source = e.target.value;
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
