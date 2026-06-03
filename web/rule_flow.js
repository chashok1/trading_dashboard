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
  _clearIntermediatesCache();

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
    <div style="display:flex;gap:8px;align-items:flex-start">
      <div style="flex:1;min-width:0">${renderAtomics(d)}</div>
      <div style="flex:1;min-width:0">${renderComposites(d)}</div>
    </div>
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
let _atomicSort   = { col: null, dir: 1 };

function renderAtomics(d) {
  const sm = d.summary || {};
  return `
  <div class="tier open" id="tier-atomic">
    <div class="tier-hdr" onclick="toggleTier('tier-atomic')">
      <span class="tier-title">Tier 1 — Atomic Rules</span>
      ${firedBadge(sm.n_atomic_fired, sm.n_atomic_total)}
      <span class="tier-toggle">▾</span>
    </div>
    <div class="tier-body">
      <div class="rf-filter">
        <input id="atomicQ" type="text" placeholder="Search rule name…" oninput="filterAtomics()">
        <label><input type="checkbox" id="atomicThreshold" onchange="filterAtomics()"> Threshold</label>
        <label><input type="checkbox" id="atomicDirect"    onchange="filterAtomics()"> Direct</label>
      </div>
      <div id="atomicTableWrap">${buildAtomicTable(d.atomics || [])}</div>
    </div>
  </div>`;
}

function filterAtomics() {
  const q         = document.getElementById('atomicQ').value.toLowerCase();
  const showThresh = document.getElementById('atomicThreshold').checked;
  const showDirect = document.getElementById('atomicDirect').checked;
  const isThresh = a => a.brkeout_from != null || a.brkeout_to != null ||
                        a.wt_below != null || a.wt_between != null || a.wt_above != null;
  const atomics = (window._rfData?.atomics || []).filter(a => {
    if (q && !(a.rule_name||'').toLowerCase().includes(q)) return false;
    // If neither box checked show all; if one/both checked filter to matching type(s)
    if (showThresh || showDirect) {
      const thresh = isThresh(a);
      if (showThresh && showDirect) return true;       // both checked → show all
      if (showThresh && !thresh) return false;          // Threshold only → hide Direct
      if (showDirect &&  thresh) return false;          // Direct only → hide Threshold
    }
    return true;
  });
  document.getElementById('atomicTableWrap').innerHTML = buildAtomicTable(atomics);
}

function sortAtomics(col) {
  if (_atomicSort.col === col) _atomicSort.dir *= -1;
  else { _atomicSort.col = col; _atomicSort.dir = 1; }
  filterAtomics();
}

function buildAtomicTable(atomics) {
  if (!atomics.length) return '<div class="status-msg">No rules match filter</div>';

  // Apply sort
  if (_atomicSort.col) {
    const isThreshold = a => a.brkeout_from != null || a.brkeout_to != null ||
                              a.wt_below != null || a.wt_between != null || a.wt_above != null;
    const sortKey = {
      type:   a => isThreshold(a) ? 0 : 1,
      col:    a => (a.ma_column || '').toLowerCase(),
      value:  a => (a.source_value ?? a.value) ?? -Infinity,
      zone:   a => a.brkeout_from  ?? -Infinity,
      band:   a => a.band          || '',
      wts:    a => a.wt_below      ?? -Infinity,
      weight: a => a.weight        ?? -Infinity,
    }[_atomicSort.col];
    if (sortKey) atomics = [...atomics].sort((a, b) => {
      const av = sortKey(a), bv = sortKey(b);
      return _atomicSort.dir * (av < bv ? -1 : av > bv ? 1 : 0);
    });
  }

  const th = (label, col, align) => {
    const active = _atomicSort.col === col;
    const ind = active ? (_atomicSort.dir === 1 ? ' ▲' : ' ▼') : '';
    const a = align ? `text-align:${align};` : '';
    return `<th style="${a}cursor:pointer;white-space:nowrap;user-select:none"
               onclick="sortAtomics('${col}')">${label}${ind}</th>`;
  };

  const rows = atomics.map(a => {
    const weightCls = a.weight > 0 ? 'fired-yes' : a.weight < 0 ? 'fired-no' : '';
    const band = a.band ? `<span class="badge-band band-${a.band}">${a.band}</span>` : '';
    const cat  = a.category ? `<span class="cat-badge">${esc(a.category)}</span>` : '';
    const zone = (a.brkeout_from != null || a.brkeout_to != null)
      ? `[${fmt(a.brkeout_from)}, ${fmt(a.brkeout_to)}]` : '—';
    const wts  = (a.wt_below != null)
      ? `(${fmt(a.wt_below,0)}, ${fmt(a.wt_between,0)}, ${fmt(a.wt_above,0)})` : '—';
    // Value = raw pre-scoring input (source_value); Weight = drv_cat_atomic_input score
    const displayVal = a.source_value ?? a.value;
    const ruleType = (a.brkeout_from != null || a.brkeout_to != null ||
                      a.wt_below != null || a.wt_between != null || a.wt_above != null)
      ? '<span style="font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;background:#dbeafe;color:#1e40af">Threshold</span>'
      : '<span style="font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;background:#dcfce7;color:#166534">Direct</span>';
    const colShort = (a.ma_column||'').replace('drv_cat_atomic_input.','');
    const colTip   = `${esc(a.rule_name||'')}&#10;${esc(a.ma_column||'')}`;
    return `<tr data-rule-id="${a.id}" data-col="${esc(a.ma_column||'')}"
               style="cursor:pointer" onclick="toggleDataFlow(this,${a.id},'${esc(a.rule_name||'')}')">
      <td style="font-family:monospace;font-size:10px;color:var(--text-2)"
          title="${colTip}">${cat}${esc(colShort)}</td>
      <td style="text-align:right">${displayVal != null ? fmt(displayVal) : '—'}</td>
      <td>${zone}</td>
      <td style="text-align:center">${band}</td>
      <td style="text-align:right;color:var(--text-3);font-size:10px">${wts}</td>
      <td class="${weightCls}" style="text-align:right;font-weight:700">${fmt(a.weight)}</td>
      <td style="text-align:center;white-space:nowrap">${ruleType}</td>
    </tr>`;
  }).join('');
  return `<div style="overflow-x:auto">
    <table class="rf-table" id="atomicTable">
      <thead><tr>
        ${th('Column','col')}${th('Value','value','right')}${th('Zone','zone')}
        ${th('Band','band','center')}${th('Weights (b/z/a)','wts')}
        ${th('Weight','weight','right')}${th('Type','type','center')}
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── Data Flow panel (Tier 2 row click) ───────────────────────────────────────

let _intermediatesCache = null;   // {key: value} for current sym+date

// Column → relevant intermediate keys + formulas to display
const _CHAIN = {
  // BRR% family
  brrpct_rule:     { keys:['last_price','lrr','trr','EE'], label:'BRR% position in range' },
  brrpct_lrr:      { keys:['last_price','lrr','trr','EE'], label:'BRR% vs LRR' },
  brrpct_r2:       { keys:['last_price','lrr','trr','EE'], label:'BRR% R2' },
  brrpct_lrr2:     { keys:['last_price','lrr','trr','EE'], label:'BRR% LRR2' },
  brrpct_trr:      { keys:['last_price','lrr','trr','EE'], label:'BRR% vs TRR' },
  brrpct_puts:     { keys:['last_price','lrr','trr','EE'], label:'BRR% Puts' },
  brrpct_trr_puts: { keys:['last_price','lrr','trr','EE'], label:'BRR% TRR Puts' },
  // BB streak family
  bb_direction:    { keys:['a_bb_streak','AT','AY','AU','AV','AW','AN'], label:'BB Direction (from streak)' },
  bb_threshold:    { keys:['a_bb_streak','AT','AY','AU','AX','AW','AV'], label:'BB Threshold Crossover' },
  bbthresh_co_days: { keys:['a_bb_streak','AT','AY','AU','AX'], label:'BBThresh CO Days' },
  bbthresh_co_days2:{ keys:['a_bb_streak','AT','AY','AU','AX2'], label:'BBThresh CO Days2' },
  bbstreak_rule:   { keys:['a_bb_streak','AT','AY'], label:'BB Streak count' },
  bbstreakrule1:   { keys:['a_bb_streak','AT','AY'], label:'BB Streak Rule1' },
  bbstreak_rule2:  { keys:['a_bb_streak','AT','AY'], label:'BB Streak Rule2' },
  bbstreak_days_rule:  { keys:['a_bb_streak','AT','AY','AU','AZ'], label:'BB Streak Days' },
  bbstreak_days_rule2: { keys:['a_bb_streak','AT','AY','AU','AZ'], label:'BB Streak Days Rule2' },
  bbstreak_days_rule3: { keys:['a_bb_streak','AT','AY','AU','AZ'], label:'BB Streak Days Rule3' },
  bbstreak_days_rule4: { keys:['a_bb_streak','AT','AY','AU','AZ'], label:'BB Streak Days Rule4' },
  bbhighdays:      { keys:['a_bb_high_low_days','AQ'], label:'BB High Days' },
  bblowdays:       { keys:['a_bb_high_low_days','AR'], label:'BB Low Days' },
  // Trade / Trend crossover
  trade_cross_over:{ keys:['last_price','a_trade_value','EF','high_today','low_today'], label:'IFS(D>AF AND AF>MIN(EF,J),+1, MAX(EF,I)>AF AND AF>D,-1, 0)' },
  trend_cross_over:{ keys:['last_price','a_trend_value','BZ','EF','high_today','low_today'], label:'IFS(D>AE AND AE>MIN(BZ,EF,J),+1, MAX(BZ,EF,I)>AE AND AE>D,-1, 0)' },
  trade_rule:      { keys:['last_price','a_trade_value','AC','AH'], label:'Trade SD position' },
  trend_rule:      { keys:['last_price','a_trend_value','AC','AG'], label:'Trend SD position' },
  trade_trend_sd_rule:{ keys:['a_trade_value','a_trend_value','AC','AI'], label:'Trade-Trend SD spread' },
  // IV / HV
  ivhv:            { keys:['imp_volatility','historical_vol','FR'], label:'IV/HV ratio' },
  ivhv_puts:       { keys:['imp_volatility','historical_vol','FR'], label:'IV/HV Puts' },
  ivpercentile:    { keys:['a_iv_percentile'], label:'IV Percentile (from TD)' },
  ivpercentile_puts:{ keys:['a_iv_percentile'], label:'IV Percentile Puts' },
  hvpercentile:    { keys:['a_hv_percentile'], label:'HV Percentile (from TD)' },
  hvpercentile_puts:{ keys:['a_hv_percentile'], label:'HV Percentile Puts' },
  hvabsolute:      { keys:['historical_vol'], label:'HV Absolute' },
  ivabsolute:      { keys:['imp_volatility'], label:'IV Absolute' },
  ivrule:          { keys:['imp_volatility','historical_vol','FR'], label:'IV Rule' },
  // RSI
  rsi_rule:        { keys:['rsi'], label:'RSI vs thresholds' },
  rsi_top:         { keys:['rsi'], label:'RSI Top' },
  rsi_puts:        { keys:['rsi'], label:'RSI Puts' },
  overbought:      { keys:['rsi'], label:'Overbought condition' },
  // MACD
  macdh_direction: { keys:['a_macdh_d_brr'], label:'MACDH direction sign' },
  macd_direction:  { keys:['a_macd_brr'], label:'MACD direction sign' },
  macd_rule:       { keys:['a_macd_brr'], label:'MACD rule' },
  macdh_rule:      { keys:['a_macdh_d_brr'], label:'MACDH rule' },
  macdh_days:      { keys:['a_macdays_streak'], label:'MACDH streak days' },
  macdh_days2:     { keys:['a_macdays_streak'], label:'MACDH Days2' },
  // Volume / Current
  current_volume_rule: { keys:['tl_volume','volume_avg_3m','GB'], label:'Current vol vs 3M avg' },
  current_price_sd_rule:{ keys:['last_price','AC'], label:'Current price SD' },
  current_volatility_rule:{ keys:['imp_volatility'], label:'Current volatility' },
  // BRR/TRR trade proximity
  brrtrade:        { keys:['last_price','lrr','a_trade_value','AC'], label:'Price near LRR' },
  trrtrade:        { keys:['last_price','trr','a_trade_value','AC'], label:'Price near TRR' },
  // 52-week
  '52_wk_high_rule':  { keys:['last_price','high_52','low_52','CE'], label:'52-wk high position' },
  '52_wk_low_rule':   { keys:['last_price','high_52','low_52','CE'], label:'52-wk low position' },
  // DMA
  '50_dma_rule':   { keys:['last_price','sma_50'], label:'Price vs 50-DMA' },
  '50_dma_crossover':{ keys:['last_price','sma_50','a_perf_3d','BZ'], label:'50-DMA crossover' },
  '200_dma_rule':  { keys:['last_price','sma_200'], label:'Price vs 200-DMA' },
  '200_dma_crossover':{ keys:['last_price','sma_200','a_perf_3d','BZ'], label:'200-DMA crossover' },
  // Perf SD rules
  perf3mn_sd_rule: { keys:['last_price','a_trend_value','AC','BQ'], label:'3M perf SD' },
  perf2m_sd_rule:  { keys:['a_perf_2m','AD','BS'], label:'2M perf SD' },
  perf3wk_sd_rule: { keys:['last_price','a_trade_value','AC','BU'], label:'3W perf SD' },
  perf2wk_sd_rule: { keys:['a_perf_2wk','AD','BW'], label:'2W perf SD' },
  perf3d_sd_rule:  { keys:['a_perf_3d','AD','BY'], label:'3D perf SD' },
  perf1d_sd_rule:  { keys:['net_chng','AC','CA'], label:'1D perf SD' },
  // Outlook
  bull:            { keys:['last_price','a_trade_value','a_trend_value','AC'], label:'Bullish composite' },
  // High/Low TRR
  high_trr:        { keys:['last_price','trr','high_today','td_high','AC','EO'], label:'High vs TRR' },
  low_lrr:         { keys:['last_price','lrr','low_today','td_low','AC','EP'], label:'Low vs LRR' },
  trend_below_trr: { keys:['a_trend_value','trr','AC','EQ'], label:'Trend line vs TRR' },
  lrr_above_trade: { keys:['lrr','a_trade_value','AC','ER'], label:'LRR vs trade line' },
  trr_idx:         { keys:['last_price','trr','AC'], label:'TRR index' },
  mrr_idx:         { keys:['last_price','mrr','AC'], label:'MRR index' },
  lrr_idx:         { keys:['last_price','lrr','AC'], label:'LRR index' },
};

// Human-readable labels for raw/intermediate keys
const _KEY_LABEL = {
  last_price:'last_price (D)', lrr:'drv_rr.lrr (EC)', trr:'drv_rr.trr (ED)', mrr:'drv_rr.mrr',
  a_trade_value:'a_trade_value (AF)', a_trend_value:'a_trend_value (AE)',
  a_bb_streak:'a_bb_streak (AS)', a_bb_high_low_days:'a_bb_high_low_days (AP)',
  a_iv_percentile:'a_iv_percentile (CX)', a_hv_percentile:'a_hv_percentile (CW)',
  a_macd_brr:'a_macd_brr (CI)', a_macdh_d_brr:'a_macdh_d_brr (CK)',
  a_macdays_streak:'a_macdays_streak (CM)', a_perf_3d:'a_perf_3d (BX)',
  a_perf_2m:'a_perf_2m (BR)', a_perf_2wk:'a_perf_2wk (BV)',
  imp_volatility:'imp_volatility (DT)', historical_vol:'historical_vol (CV)',
  rsi:'rsi (DS)', net_chng:'net_chng (G)', AC:'AC = MIN(SD,MedianSD)',
  AD:'AD = AC/D', AG:'AG = (D-AE)/AC', AH:'AH = (D-AF)/AC', AI:'AI = (AF-AE)/AC',
  AT:'AT = TRUNC(AS)', AY:'AY = TRUNC(AT/1000)', AU:'AU = AT-AY×1000',
  AV:'AV = ABS(TRUNC(AU/100))', AW:'AW = IF(AV=1,−1,1)', AX:'AX = |AU| % 100',
  AX2:'AX2 = signed AX', AN:'AN = BB Direction (decoded)',
  AQ:'AQ = TRUNC(AP) (BBHighDays)', AR:'AR = ABS(100×(AP-AQ)) (BBLowDays)',
  AZ:'AZ = ROUND((|AS|-|AT|)×100,0) (BB Streak Days)',
  BQ:'BQ = (D-AE)/AC (Perf3M_sd)', BS:'BS = Perf2M/(AD×100)',
  BU:'BU = (D-AF)/AC (Perf3W_sd)', BW:'BW = Perf2Wk/(AD×100)',
  BY:'BY = Perf3D/(AD×100)', CA:'CA = NetChng/AC (Perf1D_sd)',
  BZ:'BZ = 100×D/(100+BX) (≈ prev close)', EE:'EE = (D-EC)×100/(ED-EC)',
  EO:'EO = (ED-MAX(High,TDHigh))/AC', EP:'EP = (MIN(Low,TDLow)-EC)/AC',
  EQ:'EQ = (ED-AE)/AC', ER:'ER = (EC-AF)/AC',
  FR:'FR = ImpVol×100/HV (IVHV ratio)',
  GB:'GB = (vol-avg3m)/avg3m×100',
  CE:'CE = (52H-D)×100/(52H-52L)',
  high_52:'high_52 (CD)', low_52:'low_52 (CC)',
  sma_50:'sma_50 (CG)', sma_200:'sma_200 (CH)',
  EF:'EF = td_last (prior session close, CN)',
  high_today:'high_today (EH = today intraday high)', low_today:'low_today (EI = today intraday low)',
  td_high:'td_high (EK)', td_low:'td_low (EL)',
  tl_volume:'tl_volume (current day TOSL)', volume_avg_3m:'volume_avg_3m (3M avg)',
};

function _fmtVal(v) {
  if (v == null) return '<span style="color:var(--text-3)">null</span>';
  const n = parseFloat(v);
  if (!isNaN(n)) return `<b>${n.toFixed(Math.abs(n) < 10 ? 4 : 2)}</b>`;
  return `<b>${esc(String(v))}</b>`;
}

function _isRaw(k) {
  return !['AC','AD','AG','AH','AI','AT','AY','AU','AV','AW','AX','AX2','AN',
           'AQ','AR','AZ','BQ','BS','BU','BW','BY','CA','BZ','EE','EO','EP',
           'EQ','ER','FR','GB','CE'].includes(k);
}

function renderDataFlow(ruleName, dbCol, intermediates) {
  const chain = _CHAIN[dbCol] || { keys: [], label: dbCol };
  const keys = chain.keys.length ? chain.keys : [dbCol];

  const rows = keys.map(k => {
    const raw = _isRaw(k);
    const label = _KEY_LABEL[k] || k;
    const val = intermediates[k] ?? intermediates[k.toLowerCase()];
    const src = raw
      ? `<span style="font-size:9px;color:var(--text-3);font-style:italic">source</span>`
      : `<span style="font-size:9px;color:#7c3aed;font-style:italic">computed</span>`;
    return `<tr style="line-height:1.8">
      <td style="font-family:monospace;font-size:11px;padding:2px 8px;white-space:nowrap">${src}</td>
      <td style="font-family:monospace;font-size:11px;padding:2px 8px;color:var(--text-2);white-space:nowrap">${esc(label)}</td>
      <td style="font-family:monospace;font-size:12px;padding:2px 8px;text-align:right">${_fmtVal(val)}</td>
    </tr>`;
  }).join('');

  // For crossover columns: show clause-by-clause evaluation
  let formulaSection = '';
  if (dbCol === 'trade_cross_over' || dbCol === 'trend_cross_over') {
    const D   = intermediates['last_price'];
    const MA  = dbCol === 'trade_cross_over' ? intermediates['a_trade_value'] : intermediates['a_trend_value'];
    const EF  = intermediates['EF'];
    const Hi  = intermediates['high_today'];
    const Lo  = intermediates['low_today'];
    const BZ  = intermediates['BZ'];
    const maLabel = dbCol === 'trade_cross_over' ? 'AF (trade line)' : 'AE (trend line)';
    const minEF   = dbCol === 'trade_cross_over' ? Math.min(EF??D, Lo??D) : Math.min(BZ??D, EF??D, Lo??D);
    const maxEF   = dbCol === 'trade_cross_over' ? Math.max(EF??D, Hi??D) : Math.max(BZ??D, EF??D, Hi??D);
    const minLabel = dbCol === 'trade_cross_over' ? 'MIN(EF,J)' : 'MIN(BZ,EF,J)';
    const maxLabel = dbCol === 'trade_cross_over' ? 'MAX(EF,I)' : 'MAX(BZ,EF,I)';
    const c1a = D != null && MA != null && D > MA;
    const c1b = MA != null && MA > minEF;
    const c2a = maxEF > (MA??0);
    const c2b = MA != null && D != null && MA > D;
    const result = (c1a && c1b) ? '+1' : (c2a && c2b) ? '-1' : '0';
    const clr = result==='+1'?'#15803d':result==='-1'?'#b91c1c':'#6b7280';
    formulaSection = `
    <div style="margin-top:10px;padding:8px;background:#fff;border:1px solid #e5e7eb;border-radius:4px;font-family:monospace;font-size:11px">
      <div style="font-weight:700;color:var(--text-2);margin-bottom:6px">Formula evaluation:</div>
      <div style="margin:2px 0">Clause +1: D(${_fmtVal(D)}) &gt; ${maLabel}(${_fmtVal(MA)})? <b>${c1a}</b>
        AND ${maLabel}(${_fmtVal(MA)}) &gt; ${minLabel}(${_fmtVal(minEF)})? <b>${c1b}</b>
        → <b style="color:${c1a&&c1b?'#15803d':'#999'}">${c1a&&c1b?'+1':'skip'}</b></div>
      <div style="margin:2px 0">Clause -1: ${maxLabel}(${_fmtVal(maxEF)}) &gt; ${maLabel}(${_fmtVal(MA)})? <b>${c2a}</b>
        AND ${maLabel}(${_fmtVal(MA)}) &gt; D(${_fmtVal(D)})? <b>${c2b}</b>
        → <b style="color:${c2a&&c2b?'#b91c1c':'#999'}">${c2a&&c2b?'-1':'skip'}</b></div>
      <div style="margin-top:6px;font-size:13px;font-weight:700;color:${clr}">Result = ${result}</div>
    </div>`;
  }

  return `
  <div style="background:#f8faff;border:1px solid #c7d7f5;border-radius:6px;
              margin:4px 0 8px 0;padding:10px 14px;font-size:11px">
    <div style="font-weight:700;font-size:12px;color:var(--accent);margin-bottom:4px">
      ⟶ Data Flow: ${esc(ruleName)}
    </div>
    <div style="font-size:10px;color:var(--text-3);margin-bottom:8px;font-family:monospace">${esc(chain.label||'')}</div>
    <table style="border-collapse:collapse;width:100%">
      <thead>
        <tr style="border-bottom:1px solid #dde">
          <th style="font-size:9px;text-align:left;padding:2px 8px;color:var(--text-3);font-weight:600">TYPE</th>
          <th style="font-size:9px;text-align:left;padding:2px 8px;color:var(--text-3);font-weight:600">KEY / FORMULA</th>
          <th style="font-size:9px;text-align:right;padding:2px 8px;color:var(--text-3);font-weight:600">VALUE</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${formulaSection}
  </div>`;
}

async function toggleDataFlow(tr, ruleId, ruleName) {
  const nextTr = tr.nextElementSibling;
  // If already open for this rule, close it
  if (nextTr && nextTr.classList.contains('df-panel') && nextTr.dataset.ruleId == ruleId) {
    nextTr.remove();
    tr.style.background = '';
    return;
  }
  // Close any other open panel
  document.querySelectorAll('tr.df-panel').forEach(el => {
    if (el.previousElementSibling) el.previousElementSibling.style.background = '';
    el.remove();
  });
  tr.style.background = '#eef4ff';

  // Load intermediates (cached per load)
  if (!_intermediatesCache) {
    const sym  = document.getElementById('symInput').value.trim().toUpperCase();
    const date = document.getElementById('dateInput').value;
    try {
      const url = `/api/rule-flow/${encodeURIComponent(sym)}/intermediates${date ? '?date='+date : ''}`;
      const resp = await fetch(url);
      _intermediatesCache = resp.ok ? await resp.json() : {};
    } catch(e) { _intermediatesCache = {}; }
  }

  const dbCol = (tr.dataset.col || '').replace('drv_cat_atomic_input.', '');
  const html  = renderDataFlow(ruleName, dbCol, _intermediatesCache);
  const colCount = tr.querySelectorAll('td').length;
  const panelTr  = document.createElement('tr');
  panelTr.className = 'df-panel';
  panelTr.dataset.ruleId = ruleId;
  panelTr.innerHTML = `<td colspan="${colCount}" style="padding:0 8px 4px 8px;background:#f0f4ff">${html}</td>`;
  tr.insertAdjacentElement('afterend', panelTr);
}

// Tier 3 member row click — same data-flow panel as Tier 2, inserted as a div
async function toggleDataFlowInDiv(elemId, ruleId, ruleName) {
  const el = document.getElementById(elemId);
  if (!el) return;

  const nextEl = el.nextElementSibling;
  // Toggle off if already open for this rule
  if (nextEl && nextEl.classList.contains('df-panel-div') && nextEl.dataset.ruleId == ruleId) {
    nextEl.remove();
    el.style.background = '';
    return;
  }
  // Close any other open div panels
  document.querySelectorAll('.df-panel-div').forEach(p => {
    if (p.previousElementSibling) p.previousElementSibling.style.background = '';
    p.remove();
  });
  el.style.background = '#eef4ff';

  // Load intermediates (shared cache with Tier 2)
  if (!_intermediatesCache) {
    const sym  = document.getElementById('symInput').value.trim().toUpperCase();
    const date = document.getElementById('dateInput').value;
    try {
      const url = `/api/rule-flow/${encodeURIComponent(sym)}/intermediates${date ? '?date='+date : ''}`;
      const resp = await fetch(url);
      _intermediatesCache = resp.ok ? await resp.json() : {};
    } catch(e) { _intermediatesCache = {}; }
  }

  const dbCol = (el.dataset.col || '').replace('drv_cat_atomic_input.', '');
  const html  = renderDataFlow(ruleName, dbCol, _intermediatesCache);

  const panel = document.createElement('div');
  panel.className = 'df-panel-div';
  panel.dataset.ruleId = ruleId;
  panel.style.cssText = 'padding:6px 8px 6px 14px;background:#f0f4ff;margin:0 0 2px 0;border-radius:4px;border-left:3px solid #93c5fd';
  panel.innerHTML = html;
  el.insertAdjacentElement('afterend', panel);
}

// Clear intermediates cache when a new symbol/date is loaded
function _clearIntermediatesCache() {
  _intermediatesCache = null;
  document.querySelectorAll('.df-panel-div').forEach(p => p.remove());
}

// ── Tier 3: Composites ────────────────────────────────────────────────────────

// Classify composite as Buy or Sell from its code prefix
function _compSide(code) {
  const m = (code||'').match(/^\d+-([A-Z]+)-/);
  if (!m) return 'other';
  const p = m[1];
  if (['SA','SS','STM','SW','SH'].includes(p)) return 'sell';
  if (['B','BS','BR','BW','BM','BMN'].includes(p)) return 'buy';
  return 'other';
}

function _buildCompCol(title, color, comps) {
  if (!comps.length) return `<div style="flex:1"><div style="font-size:10px;font-weight:700;color:${color};text-transform:uppercase;letter-spacing:.06em;padding:4px 6px;border-bottom:2px solid ${color}20;margin-bottom:4px">${title} &nbsp;<span style="font-weight:400;color:var(--text-3)">0 rules</span></div></div>`;
  const metAll = comps.filter(c => c.fired).length;
  const items  = [...comps.filter(c => c.fired), ...comps.filter(c => !c.fired)]
                   .map(c => buildCompItem(c)).join('');
  return `
  <div style="flex:1;min-width:0">
    <div style="font-size:10px;font-weight:700;color:${color};text-transform:uppercase;
                letter-spacing:.06em;padding:4px 6px;border-bottom:2px solid ${color}40;margin-bottom:4px">
      ${title} &nbsp;<span style="font-weight:400;color:var(--text-3)">${metAll}/${comps.length} all-met</span>
    </div>
    <div>${items}</div>
  </div>`;
}

function _buildCompsHtml(comps) {
  const buy   = comps.filter(c => _compSide(c.code) === 'buy');
  const sell  = comps.filter(c => _compSide(c.code) === 'sell');
  const other = comps.filter(c => _compSide(c.code) === 'other');
  const sideBySide = `
  <div style="display:flex;gap:8px;align-items:flex-start">
    ${_buildCompCol('▲ Buy', '#15803d', buy)}
    ${_buildCompCol('▼ Sell', '#b91c1c', sell)}
  </div>`;
  const otherHtml = other.length
    ? `<div style="margin-top:8px">${_buildCompCol('Other', '#6b7280', other)}</div>`
    : '';
  return sideBySide + otherHtml;
}

function renderComposites(d) {
  const sm   = d.summary || {};
  const comp = d.composites || [];
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
        <label><input type="checkbox" id="compMetAll" onchange="filterComposites('')"> Met all</label>
      </div>
      <div id="compList">${_buildCompsHtml(comp)}</div>
    </div>
  </div>`;
}

function filterComposites(q) {
  const metAll = document.getElementById('compMetAll')?.checked;
  const comps  = (window._rfData?.composites || []).filter(c => {
    if (metAll && !c.fired) return false;
    if (q && !(c.code||'').toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const list = document.getElementById('compList');
  if (list) list.innerHTML = _buildCompsHtml(comps);
}

function buildCompItem(c) {
  const isInactive = c.active === false;
  const edgeCls = isInactive ? 'comp-nofired'
                : c.precondition_blocked ? 'comp-blocked'
                : c.fired ? 'comp-fired' : 'comp-nofired';
  const id = 'comp_' + (c.code||'').replace(/[^a-z0-9]/gi,'_');
  const members = (c.members || []).map((m, midx) => {
    const met  = m.condition_met ?? m.fired;   // condition met (new) or fired (legacy)
    const mCls = met ? 'mem-fired' : 'mem-nofired';
    const wt   = m.weight != null ? (met ? `<b style="color:#15803d">${fmt(m.weight)}</b>` : `<span style="color:#9ca3af">${fmt(m.weight)}</span>`) : '';
    const checkMark = met
      ? `<span style="color:#15803d;font-weight:700">✓</span>`
      : `<span style="color:#ef4444;font-weight:700">✗</span>`;

    if (m.kind === 'atomic') {
      const thr = m.threshold;
      const val = m.value;
      // Operator comes from threshold sign (positive→>=, negative→<=)
      const opSymMap = {'>=':'≥', '<=':'≤', '>':'>', '<':'<', '=':'='};
      const op = m.operator ? (opSymMap[m.operator] || m.operator)
               : thr != null ? (thr >= 0 ? '≥' : '≤') : '≠0';
      const valStr  = `<span style="font-size:10px;color:var(--text-3)">val:</span><span style="font-family:monospace;font-size:11px;font-weight:600">${fmt(val)}</span>`;
      const condPart = thr != null
        ? `<span style="font-size:10px;color:var(--text-3)">cond:</span><span style="font-family:monospace;font-size:11px;font-weight:600;color:${met?'#15803d':'#ef4444'}">${op} ${thr}</span>`
        : `<span style="font-size:10px;color:var(--text-3)">cond: ≠0</span>`;
      const memElemId = `${id}_m${midx}`;
      const dbCol = esc((m.ma_column||'').replace('drv_cat_atomic_input.',''));
      return `<div class="mem-item ${mCls}" id="${memElemId}"
          data-col="${dbCol}" data-rule-id="${m.rule_id}"
          style="display:grid;grid-template-columns:14px minmax(120px,1fr) auto auto auto;gap:6px;align-items:center;padding:3px 4px;cursor:pointer"
          onclick="toggleDataFlowInDiv('${memElemId}',${m.rule_id},'${esc(m.rule_name||'')}')">
        ${checkMark}
        <span class="mem-name" style="font-size:11px">${esc(m.rule_name||'')} <span style="font-size:9px;color:var(--text-3)">▼ details</span></span>
        <span style="display:flex;gap:4px;align-items:center">${valStr}</span>
        <span style="display:flex;gap:4px;align-items:center">${condPart}</span>
        ${wt}
      </div>`;
    } else if (m.kind === 'data') {
      return `<div class="mem-item ${mCls}" style="display:grid;grid-template-columns:14px 1fr auto;gap:4px;align-items:center;padding:3px 4px">
        ${checkMark}
        <span class="mem-name" style="font-size:11px">data: ${esc(m.column||'')}</span>
        ${wt}
      </div>`;
    } else {
      const childFired = m.fired ?? false;
      return `<div class="mem-item ${mCls}" style="display:grid;grid-template-columns:14px 1fr auto;gap:4px;align-items:center;padding:3px 4px">
        ${checkMark}
        <span class="mem-name" style="font-size:11px">↳ <em>${esc(m.child||'')}</em> ${childFired?'(fired)':'(not fired)'}</span>
        ${wt}
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
      <span class="comp-score">${isInactive ? '<span style="color:#9ca3af;font-style:italic">disabled</span>' : `score ${fmt(c.score,1)} · ${c.n_member_hit}/${(c.members||[]).length} conditions met ${c.fired ? '✓ ALL' : ''}`}</span>
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
