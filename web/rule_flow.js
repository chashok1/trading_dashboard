'use strict';

// ── Helpers ──────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmt(v, dec=2) {
  if (v == null) return '—';
  const n = parseFloat(v);
  return isNaN(n) ? esc(v) : n.toFixed(dec).replace(/\.?0+$/, '');
}
function firedBadge(n, total) {
  if (!total) return '<span class="tier-badge badge-none">0 / 0</span>';
  const cls = n > 0 ? 'badge-ok' : 'badge-none';
  return `<span class="tier-badge ${cls}">${n} / ${total} fired</span>`;
}
function dot(fired, blocked) {
  const bg = blocked ? '#f59e0b' : fired ? 'var(--bull)' : 'var(--border)';
  return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${bg};vertical-align:middle;flex-shrink:0"></span>`;
}
function actionColor(a) {
  if (!a) return 'val-null';
  const m = {'SA':'val-sa','STM':'val-stm','SS':'val-ss','SW':'val-ss',
             'BM':'val-bm','BS':'val-bs','BW':'val-bw','BR':'val-bw','BMN':'val-bw',
             'ADD':'val-add','INCREASE':'val-add','REMOVE':'val-remove',
             'REDUCE':'val-stm','HOLD':'val-hold'};
  return m[a] || 'val-hold';
}
function buysellColor(a) {
  if (!a) return 'grp-neutral';
  if (['SA','STM','SS','SW','S'].includes(a)) return 'grp-bearish';
  if (['BM','BS','BW','BR','BMN','B'].includes(a)) return 'grp-bullish';
  return 'grp-neutral';
}

// ── Toggle helpers ────────────────────────────────────────────────────────────

function toggleTier(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}
function toggleComp(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}
function toggleGrp(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}

// ── Main load ─────────────────────────────────────────────────────────────────

async function loadFlow() {
  const sym  = document.getElementById('symInput').value.trim().toUpperCase();
  if (sym) localStorage.setItem('ruleflow_symbol', sym);
  const date = document.getElementById('dateInput').value;
  if (!sym) { alert('Enter a symbol'); return; }

  const cont = document.getElementById('rfContent');
  cont.innerHTML = '<div class="status-msg">Loading…</div>';

  // Update URL
  history.replaceState(null, '', `?symbol=${encodeURIComponent(sym)}${date ? '&date='+date : ''}`);

  try {
    const url = `/api/rule-flow/${encodeURIComponent(sym)}${date ? '?date='+date : ''}`;
    const res = await fetch(url);
    if (!res.ok) {
      let msg = res.statusText;
      try { const e = await res.json(); msg = e.detail || msg; } catch {}
      throw new Error(`${res.status} ${msg}`);
    }
    const d = await res.json();
    render(d);
  } catch(e) {
    cont.innerHTML = `<div class="status-msg" style="color:#b91c1c">Error: ${esc(e.message)}</div>`;
  }
}

document.getElementById('symInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') loadFlow();
});

(function restoreSym() {
  const saved = localStorage.getItem('ruleflow_symbol');
  if (saved) { document.getElementById('symInput').value = saved; loadFlow(); }
})();

// ── Render ────────────────────────────────────────────────────────────────────

function render(d) {
  const sm = d.summary || {};
  document.getElementById('symTitle').textContent = d.tos_symbol;
  document.getElementById('symMeta').textContent =
    [sm.description, sm.sector, sm.asset_class, sm.last_price ? `$${fmt(sm.last_price)}` : '',
     sm.rsi ? `RSI ${fmt(sm.rsi,1)}` : '', sm.composite_label].filter(Boolean).join('  ·  ');

  document.getElementById('rfContent').innerHTML = `
    ${renderAtomics(d)}
    <div class="rf-arrow">↓</div>
    ${renderComposites(d)}
    <div class="rf-arrow">↓</div>
    ${renderGroups(d)}
    <div class="rf-arrow">↓</div>
    ${renderFinal(d)}
    ${renderRawData(d)}
  `;
}

// ── Source value lookup ───────────────────────────────────────────────────────
// Searches hist_raw + drv_raw for a column matching the source_column label.
// Normalises by lowercasing and stripping non-alphanumeric chars (% → pct).
// Also tries stripping a leading 'a_' prefix that drv_ma uses (e.g. a_macd_brr).
function _findSourceVal(label, histRaw, drvRaw) {
  if (!label) return null;
  const norm = s => s.toLowerCase().replace(/%/g, 'pct').replace(/[^a-z0-9]/g, '');
  const nl = norm(label);
  if (!nl) return null;
  for (const map of [drvRaw || {}, histRaw || {}]) {
    for (const cols of Object.values(map)) {
      for (const [k, v] of Object.entries(cols || {})) {
        if (v == null) continue;
        const nk = norm(k);
        if (nk === nl) return v;
        if (nk.startsWith('a') && nk.slice(1) === nl) return v;
      }
    }
  }
  return null;
}

// ── Raw side panels (hist_raw + drv_raw) ──────────────────────────────────────

const _RAW_SKIP_COLS = new Set([
  'source_file','source','file_name','file_path','description',
]);

const RPANEL_VCOLS = 13;

function renderRawPanels(d) {
  const allTables = [
    ...Object.entries(d.hist_raw || {}),
    ...Object.entries(d.drv_raw  || {}).filter(([k]) => k !== 'drv_cat_atomic_input'),
  ];
  return allTables.map(([tbl, cols]) => {
    const entries = Object.entries(cols || {})
      .filter(([k, v]) => !_RAW_SKIP_COLS.has(k) && v != null);
    if (!entries.length) return '';
    const cells = entries.map(([k, v]) => {
      const isDate = typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v);
      const disp = typeof v === 'boolean' ? String(v) : isDate ? v.slice(0, 10) : fmt(v);
      return `<div style="padding:1px 3px;border-bottom:1px solid #f4f4f2;min-width:0">
        <div style="font-family:monospace;font-size:11px;color:var(--text-3);
                    overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
             title="${esc(k)}">${esc(k)}</div>
        <div style="font-family:monospace;font-size:13px;font-weight:600;
                    overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
             title="${esc(String(v ?? ''))}">${esc(disp)}</div>
      </div>`;
    }).join('');
    return `<div style="margin-bottom:4px">
      <div style="font-size:9px;font-weight:700;color:var(--accent);text-transform:uppercase;
                  letter-spacing:.06em;line-height:1.4;padding:0 2px">${esc(tbl)}</div>
      <div style="display:grid;grid-template-columns:repeat(${RPANEL_VCOLS},1fr);gap:0;
                  padding-left:16px">${cells}</div>
    </div>`;
  }).join('');
}

// ── Raw data panel (below final output) ──────────────────────────────────────

function renderRawData(d) {
  const html = renderRawPanels(d);
  if (!html) return '';
  return `
  <div class="rf-arrow">↓</div>
  <div class="tier open" id="tier-raw">
    <div class="tier-hdr" onclick="toggleTier('tier-raw')">
      <span class="tier-title">Raw Source Data</span>
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">${html}</div>
  </div>`;
}

// ── Tier 2: Atomic rules ──────────────────────────────────────────────────────

let _atomicFilter = { q: '', cat: '', fired: '' };

function renderAtomics(d) {
  const sm = d.summary || {};
  return `
  <div class="tier open" id="tier-atomic">
    <div class="tier-hdr" onclick="toggleTier('tier-atomic')">
      <span class="tier-title">Tier 2 — Atomic Rules</span>
      ${firedBadge(sm.n_atomic_fired, sm.n_atomic_total)}
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">
      <div class="rf-filter">
        <input id="atomicQ" type="text" placeholder="Search rule name…" oninput="filterAtomics()">
        <select id="atomicCat" onchange="filterAtomics()">
          <option value="">All categories</option>
          ${[...new Set((d.atomics||[]).map(a=>a.category).filter(Boolean))].sort()
              .map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}
        </select>
        <label><input type="checkbox" id="atomicFired" onchange="filterAtomics()"> Fired only</label>
        <label><input type="checkbox" id="atomicIssues" onchange="filterAtomics()"> Issues only</label>
      </div>
      <div id="atomicTableWrap">${buildAtomicTable(d.atomics || [])}</div>
    </div>
  </div>`;
}

function filterAtomics() {
  const q      = document.getElementById('atomicQ').value.toLowerCase();
  const cat    = document.getElementById('atomicCat').value;
  const fired  = document.getElementById('atomicFired').checked;
  const issues = document.getElementById('atomicIssues').checked;
  // Re-fetch and filter from cached data — use global store
  const atomics = (window._rfData?.atomics || []).filter(a => {
    if (q && !(a.rule_name||'').toLowerCase().includes(q)) return false;
    if (cat && a.category !== cat) return false;
    if (fired && !a.fired) return false;
    if (issues && !['no_column','no_data','no_thresholds'].some(x => (a.reason||'').startsWith(x))) return false;
    return true;
  });
  document.getElementById('atomicTableWrap').innerHTML = buildAtomicTable(atomics);
}

function buildAtomicTable(atomics) {
  if (!atomics.length) return '<div class="status-msg">No rules match filter</div>';
  const rows = atomics.map(a => {
    const firedCls = a.fired ? 'fired-yes' : 'fired-no';
    const isIssue  = ['no_column','no_data','no_thresholds'].some(x => (a.reason||'').startsWith(x));
    const reasonCls = isIssue ? 'reason-bad' : 'reason-ok';
    const band = a.band ? `<span class="badge-band band-${a.band}">${a.band}</span>` : '';
    const cat  = a.category ? `<span class="cat-badge">${esc(a.category)}</span>` : '';
    const zone = (a.brkeout_from != null || a.brkeout_to != null)
      ? `[${fmt(a.brkeout_from)}, ${fmt(a.brkeout_to)}]` : '—';
    const wts  = (a.wt_below != null)
      ? `(${fmt(a.wt_below,0)}, ${fmt(a.wt_between,0)}, ${fmt(a.wt_above,0)})` : '—';
    const srcLabel = a.source_column || '';
    const srcVal   = a.source_value != null ? a.source_value
                   : _findSourceVal(srcLabel, window._rfData?.hist_raw, window._rfData?.drv_raw);
    return `<tr>
      <td>${cat} ${esc(a.rule_name||'')}</td>
      <td style="font-family:monospace;font-size:10px;color:var(--text-2)">${esc(a.ma_column||'')}</td>
      <td style="font-size:11px;color:var(--text-2);font-family:monospace;max-width:120px;white-space:normal;word-break:break-all;line-height:1.3">${esc(srcLabel)||'—'}</td>
      <td style="text-align:right;font-weight:${srcVal!=null?'600':'400'};color:${srcVal!=null?'var(--text-1)':'var(--text-3)'}">${srcVal!=null?fmt(srcVal):'—'}</td>
      <td style="text-align:right">${fmt(a.value)}</td>
      <td>${zone}</td>
      <td style="text-align:center">${band}</td>
      <td style="text-align:right">${wts}</td>
      <td class="${firedCls}" style="text-align:right;font-weight:700">${fmt(a.weight)}</td>
      <td class="${firedCls}">${a.fired ? '✓' : '✗'}</td>
      <td class="${reasonCls}" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(a.reason||'')}">${esc(a.reason||'')}</td>
    </tr>`;
  }).join('');
  return `<div style="overflow-x:auto;max-height:400px;overflow-y:auto">
    <table class="rf-table">
      <thead><tr>
        <th>Rule</th><th>Column</th><th>Source</th><th style="text-align:right">Src Val</th><th>Value</th><th>Zone</th>
        <th>Band</th><th>Weights (b/z/a)</th><th>Weight</th><th>Fired</th><th>Reason</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── Tier 3: Composites ────────────────────────────────────────────────────────

function renderComposites(d) {
  const sm   = d.summary || {};
  const comp = d.composites || [];
  const fired   = comp.filter(c => c.fired);
  const notFired = comp.filter(c => !c.fired);
  const items = [...fired, ...notFired].map(c => buildCompItem(c)).join('');
  return `
  <div class="tier open" id="tier-comp">
    <div class="tier-hdr" onclick="toggleTier('tier-comp')">
      <span class="tier-title">Tier 3 — Composite Rules</span>
      ${firedBadge(sm.n_composite_fired, sm.n_composite_total)}
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">
      <div class="rf-filter">
        <input type="text" placeholder="Search composite…" oninput="filterComposites(this.value)">
        <label><input type="checkbox" id="compFiredOnly" onchange="filterComposites('')"> Fired only</label>
      </div>
      <div class="comp-list" id="compList">${items}</div>
    </div>
  </div>`;
}

function filterComposites(q) {
  const firedOnly = document.getElementById('compFiredOnly')?.checked;
  const comps = window._rfData?.composites || [];
  const filtered = comps.filter(c => {
    if (firedOnly && !c.fired) return false;
    if (q && !(c.code||'').toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const fired   = filtered.filter(c => c.fired);
  const notFired = filtered.filter(c => !c.fired);
  const items = [...fired, ...notFired].map(c => buildCompItem(c)).join('');
  const list = document.getElementById('compList');
  if (list) list.innerHTML = items;
}

function buildCompItem(c) {
  const edgeCls = c.precondition_blocked ? 'comp-blocked' : c.fired ? 'comp-fired' : 'comp-nofired';
  const id = 'comp_' + (c.code||'').replace(/[^a-z0-9]/gi,'_');
  const members = (c.members || []).map(m => {
    const fired = m.fired;
    const mCls  = fired ? 'mem-fired' : 'mem-nofired';
    const wt    = m.weight != null ? (fired ? `<b>${fmt(m.weight)}</b>` : `${fmt(m.weight)}`) : '';
    if (m.kind === 'atomic') {
      const band = m.band ? `<span class="badge-band band-${m.band}" style="font-size:9px">${m.band}</span>` : '';
      const zone = (m.brkeout_from != null || m.brkeout_to != null)
        ? `[${fmt(m.brkeout_from)},${fmt(m.brkeout_to)}]` : '';
      return `<div class="mem-item ${mCls}">
        <span class="mem-kind">atomic</span>
        <span class="mem-name">${esc(m.rule_name||'')}</span>
        <span class="mem-val">${m.value!=null?fmt(m.value):''} ${zone} ${band}</span>
        <span class="mem-wt" style="color:${fired?'#15803d':'#9ca3af'}">${wt}</span>
        <span style="font-size:10px;color:var(--text-2)">${esc((m.reason||'').split(' ')[0])}</span>
      </div>`;
    } else if (m.kind === 'data') {
      return `<div class="mem-item ${mCls}">
        <span class="mem-kind">data</span>
        <span class="mem-name">${esc(m.column||'')}</span>
        <span class="mem-wt" style="color:${fired?'#15803d':'#9ca3af'}">${wt}</span>
      </div>`;
    } else {
      return `<div class="mem-item ${mCls}">
        <span class="mem-kind">composite</span>
        <span class="mem-name">${esc(m.child||'')}</span>
        <span class="mem-wt" style="color:${fired?'#15803d':'#9ca3af'}">${wt}</span>
      </div>`;
    }
  }).join('');

  const pre = c.precondition_blocked
    ? `<div style="font-size:11px;color:#b45309;padding:4px 0">Precondition blocked: <code>${esc(c.precondition||'')}</code></div>`
    : c.precondition
      ? `<div style="font-size:11px;color:var(--text-2);padding:4px 0">Precondition: <code>${esc(c.precondition)}</code></div>`
      : '';

  return `
  <div class="comp-item ${edgeCls}" id="${id}">
    <div class="comp-hdr" onclick="toggleComp('${id}')">
      ${dot(c.fired, c.precondition_blocked)}
      <span class="comp-code">${esc(c.code||'')}</span>
      <span class="comp-score">score ${fmt(c.score,1)} · ${c.n_member_hit}/${(c.members||[]).length} members hit</span>
      <span style="font-size:12px;color:var(--text-3)">▾</span>
    </div>
    <div class="comp-body">
      ${pre}
      <div class="mem-list">${members || '<span style="color:var(--text-2);font-size:11px">No members</span>'}</div>
    </div>
  </div>`;
}

// ── Tier 4: Rule Groups ───────────────────────────────────────────────────────

function renderGroups(d) {
  const sm  = d.summary || {};
  const grps = d.rule_groups || [];
  const fired   = grps.filter(g => g.fired);
  const notFired = grps.filter(g => !g.fired);
  const items = [...fired, ...notFired].map(g => buildGrpItem(g)).join('');
  return `
  <div class="tier open" id="tier-grp">
    <div class="tier-hdr" onclick="toggleTier('tier-grp')">
      <span class="tier-title">Tier 4 — Rule Groups</span>
      ${firedBadge(sm.n_group_fired, sm.n_group_total)}
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">
      <div class="grp-list">${items}</div>
    </div>
  </div>`;
}

function buildGrpItem(g) {
  const edgeCls = g.fired ? 'grp-fired' : 'grp-nofired';
  const id = 'grp_' + (g.code||'').replace(/[^a-z0-9]/gi,'_');
  const actionCls = buysellColor(g.action_label);
  const actionBadge = g.action_label
    ? `<span class="grp-action ${actionCls}">${esc(g.action_label)}</span>` : '';
  const prioBadge = g.priority != null
    ? `<span style="font-size:11px;color:var(--text-2)">prio ${g.priority}</span>` : '';

  const members = (g.members || []).map(m => {
    const mCls = m.fired ? 'grp-mem-fired' : 'grp-mem-nofired';
    return `<div class="grp-member ${mCls}">
      <span class="op-badge">${esc(m.operator||'')}</span>
      <span style="flex:1;font-weight:600;font-family:monospace;font-size:11px">${esc(m.code||'')}</span>
      ${dot(m.fired)}
    </div>`;
  }).join('');

  return `
  <div class="grp-item ${edgeCls}" id="${id}">
    <div class="grp-hdr" onclick="toggleGrp('${id}')">
      ${dot(g.fired)}
      <span class="grp-code">${esc(g.code||'')}</span>
      ${actionBadge} ${prioBadge}
      <span style="font-size:12px;color:var(--text-3)">▾</span>
    </div>
    <div class="grp-body">
      ${g.intent_text ? `<div style="font-size:11px;color:var(--text-2);margin-bottom:6px">${esc(g.intent_text)}</div>` : ''}
      <div>${members}</div>
    </div>
  </div>`;
}

// ── Tier 5: Final Output ──────────────────────────────────────────────────────

function renderFinal(d) {
  const f = d.final || {};
  const bs = f.buysell_scores || {};
  const trig  = f.trig_action;
  const cons  = f.consolidated_action;
  const score = trig ? (bs[trig] != null ? fmt(bs[trig], 0) : '—') : '—';
  const firedGroups = (f.triggered_groups || []);
  const pills = firedGroups.map(g =>
    `<span class="grp-pill">${esc(g.rule_group_code||'')} → ${esc(g.action||'')}</span>`
  ).join('');

  return `
  <div class="tier open" id="tier-final">
    <div class="tier-hdr" onclick="toggleTier('tier-final')">
      <span class="tier-title">Tier 5 — Final Output</span>
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">
      <div class="final-grid">
        <div class="final-card">
          <div class="final-label">Trig Action <small>(rule groups)</small></div>
          <div class="final-value ${actionColor(trig)}">${trig || '—'}</div>
          <div style="font-size:11px;color:var(--text-2);margin-top:4px">BuySell score: ${score}</div>
        </div>
        <div class="final-card">
          <div class="final-label">Consolidated Action</div>
          <div class="final-value ${actionColor(cons)}">${cons || '—'}</div>
          <div style="font-size:11px;color:var(--text-2);margin-top:4px">
            Source: ${esc(f.winning_source || '—')}
          </div>
        </div>
        <div class="final-card" style="grid-column:span 2">
          <div class="final-label">Fired Rule Groups</div>
          ${pills
            ? `<div class="grp-fired-list">${pills}</div>`
            : '<div style="color:var(--text-3);font-size:13px;margin-top:6px">No groups fired</div>'}
          ${f.suppressed_reason
            ? `<div style="font-size:11px;color:#b45309;margin-top:8px">Suppressed: ${esc(f.suppressed_reason)}</div>`
            : ''}
        </div>
      </div>
    </div>
  </div>`;
}

// Store data globally for filters
const _origRender = render;
window.render = function(d) {
  window._rfData = d;
  _origRender(d);
};
