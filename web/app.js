/* Trading Dashboard - frontend logic.
   4-panel layout: Quads banner + Ticker grid + Econ Indicators + Earnings/Calendar. */

const SECTIONS = ['', 'Index', 'Volatility', 'Treasury', 'Commodity', 'Sector', 'FX', 'Stock'];
// Display order for section grouping inside the ticker grid (excludes the leading 'All').
const SECTION_ORDER = ['Index', 'Volatility', 'Treasury', 'Commodity', 'Sector', 'FX', 'Stock'];
const SECTION_RANK = Object.fromEntries(SECTION_ORDER.map((s, i) => [s, i]));
function sectionRank(s) {
  const r = SECTION_RANK[s];
  return r === undefined ? 999 : r;
}

const state = {
  date: null,
  section: '',
  search: '',
  rows: [],
};

// ---------- helpers ----------

const $ = (id) => document.getElementById(id);

function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!Number.isFinite(n)) return '';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

function fmtInt(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!Number.isFinite(n)) return '';
  return Math.round(n).toLocaleString();
}

function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!Number.isFinite(n)) return '';
  return n.toFixed(digits) + '%';
}

function fmtDate(d) {
  // Concise MM/DD. Tolerates 'YYYY-MM-DD', ISO datetimes, or Date objects.
  if (!d) return '';
  const s = String(d).slice(0, 10);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[2]}/${m[3]}`;
  // Fallback: try Date parse
  const dt = new Date(d);
  if (!isNaN(dt)) {
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const dd = String(dt.getDate()).padStart(2, '0');
    return `${mm}/${dd}`;
  }
  return s;
}

function signClass(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!Number.isFinite(n)) return '';
  if (n > 0) return 'pos';
  if (n < 0) return 'neg';
  return '';
}

// Normalize an outlook value (BULLISH / BEARISH / NEUTRAL / 0 / Bullish / etc.)
// Returns { cls, label } where cls is the CSS class suffix and label is what to display.
function normOutlook(v) {
  if (v === null || v === undefined || v === '') return { cls: '', label: '' };
  const raw = String(v).trim();
  const upper = raw.toUpperCase();
  // Map common alternate forms
  if (upper === '0' || upper === 'N' || upper === 'NEUTRAL' || upper === 'NEU') {
    return { cls: 'NEUTRAL', label: 'NEUTRAL' };
  }
  if (upper.startsWith('BULL') || upper === '+' || upper === 'POS' || upper === 'POSITIVE' || upper === 'UP') {
    return { cls: 'BULLISH', label: 'BULLISH' };
  }
  if (upper.startsWith('BEAR') || upper === '-' || upper === 'NEG' || upper === 'NEGATIVE' || upper === 'DN' || upper === 'DOWN') {
    return { cls: 'BEARISH', label: 'BEARISH' };
  }
  // Unknown — fall through with whatever we got, stripped to alnum for safe class name
  return { cls: upper.replace(/[^A-Z0-9]/g, ''), label: raw };
}

function outlookCell(td, value) {
  const { cls, label } = normOutlook(value);
  td.className = 'text';
  td.innerHTML = label ? `<span class="signal-${cls}">${label}</span>` : '';
}

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

// ---------- date picker ----------

async function loadDates() {
  const dates = await fetchJson('/api/dates');
  const sel = $('datePicker');
  sel.innerHTML = '';
  for (const d of dates) {
    const opt = document.createElement('option');
    // value stays as full ISO so the API gets YYYY-MM-DD; label is concise.
    opt.value = d; opt.textContent = fmtDate(d);
    sel.appendChild(opt);
  }
  state.date = dates[0] || null;
  if (state.date) sel.value = state.date;
  $('footDate').textContent = state.date ? fmtDate(state.date) : '—';
}

// ---------- section chips ----------

function renderSectionChips() {
  const wrap = $('sectionChips');
  wrap.innerHTML = '';
  for (const sec of SECTIONS) {
    const btn = document.createElement('button');
    btn.className = 'chip' + (state.section === sec ? ' active' : '');
    btn.dataset.section = sec;
    btn.textContent = sec || 'All';
    btn.onclick = () => {
      state.section = sec;
      renderSectionChips();
      renderTickerGrid();
    };
    wrap.appendChild(btn);
  }
}

// ---------- ticker grid (Dash K-Z) ----------

async function loadTickers() {
  if (!state.date) return;
  try {
    const rows = await fetchJson(`/api/dash?date=${encodeURIComponent(state.date)}`);
    rows.sort((a, b) => {
      const ra = sectionRank(a.section), rb = sectionRank(b.section);
      if (ra !== rb) return ra - rb;
      return (a.symbol || '').localeCompare(b.symbol || '');
    });
    state.rows = rows;
  } catch (e) {
    console.error('Failed to load /api/dash:', e);
    state.rows = [];
  }
  renderTickerGrid();
  renderIndexBar();
}

function rowMatches(r) {
  if (state.section && r.section !== state.section) return false;
  if (state.search) {
    const needle = state.search.toLowerCase();
    const sym = (r.symbol || '').toLowerCase();
    const desc = (r.description || '').toLowerCase();
    if (!sym.includes(needle) && !desc.includes(needle)) return false;
  }
  return true;
}

function buildSectionBlock(name, rows) {
  const div = document.createElement('div');
  div.className = 'section-block';
  // Caption row removed per user preference — section identity comes from the data itself.

  const table = document.createElement('table');
  table.innerHTML = `
    <thead>
      <tr>
        <th>Sym</th>
        <th class="num">%Chg</th>
        <th>HE</th>
        <th>TrTn</th>
        <th>MQ</th>
        <th>QQ</th>
        <th class="num">Last</th>
        <th class="num">Trend</th>
        <th class="num">Trade</th>
        <th class="num">%BRR</th>
        <th class="num">Lo</th>
        <th class="num">Hi</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector('tbody');

  for (const r of rows) {
    const tr = document.createElement('tr');

    const tdSym = document.createElement('td');
    if (r.symbol) {
      const symBtn = document.createElement('button');
      symBtn.onclick = () => openPortfolioModal(r.symbol);
      symBtn.style.background = 'none';
      symBtn.style.border = 'none';
      symBtn.style.color = 'var(--accent,#1d4ed8)';
      symBtn.style.cursor = 'pointer';
      symBtn.style.textDecoration = 'none';
      symBtn.style.font = 'inherit';
      symBtn.style.padding = '0';
      symBtn.textContent = r.symbol;
      if (r.description) symBtn.title = String(r.description);
      // Yahoo lookup badge before the symbol (skipped for cash/pseudo).
      if (window.yahooLink) {
        tdSym.insertAdjacentHTML('afterbegin', window.yahooLink(r.symbol));
      }
      tdSym.appendChild(symBtn);
    }
    tr.appendChild(tdSym);

    const pctChg = (r.last_price != null && r.a_trade_value != null && r.a_trade_value !== 0)
      ? ((Number(r.last_price) - Number(r.a_trade_value)) / Number(r.a_trade_value)) * 100
      : null;
    const tdPct = document.createElement('td');
    tdPct.className = 'num ' + signClass(pctChg);
    tdPct.textContent = pctChg != null ? fmtPct(pctChg, 2) : '';
    tr.appendChild(tdPct);

    const tdHeOl = document.createElement('td'); outlookCell(tdHeOl, r.rr_outlook); tr.appendChild(tdHeOl);
    const tdTrTn = document.createElement('td'); outlookCell(tdTrTn, r.call_outlook); tr.appendChild(tdTrTn);

    const tdMq = document.createElement('td'); tdMq.textContent = r.mq || ''; tr.appendChild(tdMq);
    const tdQq = document.createElement('td'); tdQq.textContent = r.qq || ''; tr.appendChild(tdQq);

    const tdLast = document.createElement('td'); tdLast.className = 'num';
    tdLast.textContent = fmtNum(r.last_price); tr.appendChild(tdLast);
    const tdTrend = document.createElement('td'); tdTrend.className = 'num';
    tdTrend.textContent = fmtNum(r.a_trend_value); tr.appendChild(tdTrend);
    const tdTrade = document.createElement('td'); tdTrade.className = 'num';
    tdTrade.textContent = fmtNum(r.a_trade_value); tr.appendChild(tdTrade);

    const tdBrr = document.createElement('td'); tdBrr.className = 'num';
    tdBrr.textContent = r.pct_brr != null ? fmtNum(r.pct_brr, 1) : ''; tr.appendChild(tdBrr);

    const tdLow = document.createElement('td'); tdLow.className = 'num';
    tdLow.textContent = fmtNum(r.threshold_low); tr.appendChild(tdLow);
    const tdHigh = document.createElement('td'); tdHigh.className = 'num';
    tdHigh.textContent = fmtNum(r.threshold_high); tr.appendChild(tdHigh);

    tbody.appendChild(tr);
  }

  div.appendChild(table);
  return div;
}

function renderTickerGrid() {
  const container = $('tickerSections');
  if (!container) return;
  container.innerHTML = '';

  const filtered = state.rows.filter(rowMatches);

  // Group by section
  const groups = new Map();
  for (const r of filtered) {
    const sec = r.section || '(unspecified)';
    if (!groups.has(sec)) groups.set(sec, []);
    groups.get(sec).push(r);
  }

  // Explicit column assignments.
  // Left:  Index -> Treasury -> Commodity -> FX  (then Stock A-half)
  // Right: Volatility -> Sector  (then Stock B-half)
  const LEFT_SECTIONS  = ['Index', 'Treasury', 'Commodity', 'FX'];
  const RIGHT_SECTIONS = ['Volatility', 'Sector'];

  const leftCol  = document.createElement('div');
  leftCol.className = 'ticker-col';
  const rightCol = document.createElement('div');
  rightCol.className = 'ticker-col';

  let total = 0;

  for (const sec of LEFT_SECTIONS) {
    const rows = groups.get(sec);
    if (!rows || rows.length === 0) continue;
    total += rows.length;
    leftCol.appendChild(buildSectionBlock(sec, rows));
  }
  for (const sec of RIGHT_SECTIONS) {
    const rows = groups.get(sec);
    if (!rows || rows.length === 0) continue;
    total += rows.length;
    rightCol.appendChild(buildSectionBlock(sec, rows));
  }

  // Stock - split into A-half (left) and B-half (right) when large
  const stockRows = groups.get('Stock');
  if (stockRows && stockRows.length > 0) {
    total += stockRows.length;
    if (stockRows.length > 12) {
      const half = Math.ceil(stockRows.length / 2);
      const left = stockRows.slice(0, half);
      const right = stockRows.slice(half);
      const lLabel = `Stock (${(left[0].symbol || 'A')[0]}-${(left[left.length - 1].symbol || 'M')[0]})`;
      const rLabel = `Stock (${(right[0].symbol || 'N')[0]}-${(right[right.length - 1].symbol || 'Z')[0]})`;
      leftCol.appendChild(buildSectionBlock(lLabel, left));
      rightCol.appendChild(buildSectionBlock(rLabel, right));
    } else {
      leftCol.appendChild(buildSectionBlock('Stock', stockRows));
    }
  }

  // Anything not in the explicit lists (e.g. '(unspecified)') goes left
  for (const [sec, rows] of groups) {
    if (LEFT_SECTIONS.includes(sec) || RIGHT_SECTIONS.includes(sec) || sec === 'Stock') continue;
    if (rows.length === 0) continue;
    total += rows.length;
    leftCol.appendChild(buildSectionBlock(sec, rows));
  }

  container.appendChild(leftCol);
  container.appendChild(rightCol);

  const cnt = $('tickerCount');
  if (cnt) cnt.textContent = `${total} row${total === 1 ? '' : 's'}`;
}

// ---------- economic indicators ----------

async function loadEconIndicators() {
  const tbody = $('econBody');
  const empty = $('econEmpty');
  tbody.innerHTML = '';
  try {
    const url = state.date
      ? `/api/dashboard/econ-indicators?date=${encodeURIComponent(state.date)}&limit=20`
      : '/api/dashboard/econ-indicators?limit=20';
    const rows = await fetchJson(url);
    if (!rows || rows.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    for (const r of rows) {
      const tr = document.createElement('tr');
      const sig = normOutlook(r.signal);
      tr.innerHTML = `
        <td class="text">${r.indicator || ''}</td>
        <td>${fmtDate(r.indicator_date)}</td>
        <td class="num">${r.days != null ? r.days : ''}</td>
        <td class="text">${sig.label ? `<span class="signal-${sig.cls}">${sig.label}</span>` : ''}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error('Failed to load econ indicators:', e);
    empty.hidden = false;
    empty.textContent = 'Failed to load.';
  }
}

// ---------- earnings / calendar events ----------

async function loadEarnings() {
  const tbody = $('earningsBody');
  const empty = $('earningsEmpty');
  tbody.innerHTML = '';
  try {
    const url = state.date
      ? `/api/dashboard/earnings?date=${encodeURIComponent(state.date)}&days_ahead=60&limit=50`
      : '/api/dashboard/earnings?days_ahead=60&limit=50';
    const rows = await fetchJson(url);
    if (!rows || rows.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    for (const r of rows) {
      const tr = document.createElement('tr');
      const days = r.days_until != null ? `${r.days_until}d` : '';
      tr.innerHTML = `
        <td class="text">${r.category || ''}</td>
        <td>${fmtDate(r.event_date)}</td>
        <td class="num">${days}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error('Failed to load earnings:', e);
    empty.hidden = false;
    empty.textContent = 'Failed to load.';
  }
}

// ---------- quads banner ----------

function quadColorClass(q) {
  const s = String(q || '');
  if (/4/.test(s)) return 'quad-q4';
  if (/3/.test(s)) return 'quad-q3';
  if (/2/.test(s)) return 'quad-q2';
  if (/1/.test(s)) return 'quad-q1';
  return 'quad-q-unknown';
}

const MONTH_3CHAR = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

function shortMonthLabel(payload) {
  // Always return 3-char uppercase month (JUN, JUL, AUG) derived from start_date.
  if (payload.start_date) {
    const d = new Date(payload.start_date);
    if (!isNaN(d)) return MONTH_3CHAR[d.getMonth()];
  }
  // Fallback: parse YYYY-MM from a label like '2026-06'.
  if (payload.label) {
    const m = String(payload.label).match(/^\d{4}-(\d{2})/);
    if (m) {
      const idx = parseInt(m[1], 10) - 1;
      if (idx >= 0 && idx < 12) return MONTH_3CHAR[idx];
    }
    return String(payload.label).toUpperCase();
  }
  return '—';
}

function shortQuarterLabel(payload) {
  if (payload.start_date) {
    const d = new Date(payload.start_date);
    if (!isNaN(d)) {
      const q = Math.floor(d.getMonth() / 3) + 1;
      return `Q${q} '${String(d.getFullYear()).slice(-2)}`;
    }
  }
  if (payload.label) return String(payload.label);
  return '—';
}

function quadMini(periodLabel, quadValue, isCurrent) {
  const wrap = document.createElement('span');
  wrap.className = 'quad-mini' + (isCurrent ? ' is-current' : '');
  const lbl = document.createElement('span');
  lbl.className = 'qlbl';
  lbl.textContent = periodLabel;
  const val = document.createElement('span');
  val.className = 'qval ' + quadColorClass(quadValue);
  val.textContent = (quadValue || '—').replace(/^Quad\s*/i, 'Q');
  wrap.appendChild(lbl);
  wrap.appendChild(val);
  return wrap;
}

// ---------- top index/volatility scorecard ----------

const INDEX_VOL_PAIRS = [
  { idxLabel: 'S&P', idxSyms: ['SPX', '$SPX', '/ES', 'GSPC', '^GSPC', 'SPY'],
    volLabel: 'VIX', volSyms: ['VIX', '$VIX', '^VIX'] },
  { idxLabel: 'NDX', idxSyms: ['NDX', '$NDX', '/NQ', '^NDX', 'QQQ'],
    volLabel: 'VXN', volSyms: ['VXN', '$VXN', '^VXN'] },
  { idxLabel: 'RUT', idxSyms: ['RUT', '$RUT', '/RTY', '^RUT', 'IWM'],
    volLabel: 'RVX', volSyms: ['RVX', '$RVX', '^RVX'] },
  { idxLabel: 'DJI', idxSyms: ['DJI', '$DJI', '/YM', 'INDU', '^DJI', 'DIA'],
    volLabel: 'VXD', volSyms: ['VXD', '$VXD', '^VXD'] },
];

function findRowBySymbols(syms) {
  if (!Array.isArray(state.rows) || state.rows.length === 0) return null;
  const upper = syms.map(s => String(s).toUpperCase());
  return state.rows.find(r => upper.includes(String(r.symbol || '').toUpperCase())) || null;
}

function pctChangeOf(r) {
  if (!r) return null;
  const last = Number(r.last_price);
  const trade = Number(r.a_trade_value);
  if (!Number.isFinite(last) || !Number.isFinite(trade) || trade === 0) return null;
  return ((last - trade) / trade) * 100;
}

function renderIndexBar() {
  const bar = $('indexBar');
  const empty = $('indexBarEmpty');
  if (!bar) return;
  [...bar.querySelectorAll('.idx-pair')].forEach(n => n.remove());

  if (!state.rows || state.rows.length === 0) {
    if (empty) { empty.hidden = false; empty.textContent = 'Loading index data…'; }
    return;
  }
  if (empty) empty.hidden = true;

  for (const pair of INDEX_VOL_PAIRS) {
    const idxRow = findRowBySymbols(pair.idxSyms);
    const volRow = findRowBySymbols(pair.volSyms);
    const idxPct = pctChangeOf(idxRow);
    const volPct = pctChangeOf(volRow);

    const wrap = document.createElement('span');
    wrap.className = 'idx-pair';
    wrap.title = `${pair.idxLabel}: ${idxRow ? idxRow.symbol : 'n/a'}  |  ${pair.volLabel}: ${volRow ? volRow.symbol : 'n/a'}`;
    wrap.innerHTML = `
      <span class="idx-cell">
        <span class="idx-name">${pair.idxLabel}</span>
        <span class="idx-pct ${signClass(idxPct)}">${idxPct != null ? fmtPct(idxPct, 2) : '—'}</span>
      </span>
      <span class="idx-sep">·</span>
      <span class="idx-cell">
        <span class="idx-name">${pair.volLabel}</span>
        <span class="idx-pct ${signClass(volPct)}">${volPct != null ? fmtPct(volPct, 2) : '—'}</span>
      </span>
    `;
    bar.appendChild(wrap);
  }
}

// ---------- quads (side panel mini-grid) ----------

async function loadQuads() {
  const line = $('quadsBody');
  const empty = $('quadsEmpty');
  if (!line) return;
  line.innerHTML = '';
  empty.hidden = true;

  try {
    const url = state.date
      ? `/api/dashboard/quads?date=${encodeURIComponent(state.date)}`
      : '/api/dashboard/quads';
    const data = await fetchJson(url);

    if (data.current_quarter) {
      line.appendChild(quadMini(shortQuarterLabel(data.current_quarter), data.current_quarter.quad, true));
    }
    if (data.next_quarter) {
      line.appendChild(quadMini(shortQuarterLabel(data.next_quarter), data.next_quarter.quad, false));
    }
    const months = Array.isArray(data.months) ? data.months : [];
    months.forEach((m, i) => {
      line.appendChild(quadMini(shortMonthLabel(m), m.quad, i === 0));
    });

    if (line.childElementCount === 0) {
      empty.hidden = false;
    }
  } catch (e) {
    console.error('Failed to load quads:', e);
    empty.hidden = false;
    empty.textContent = 'Failed to load quads.';
  }
}

// ---------- health ----------

async function loadHealth() {
  try {
    const h = await fetchJson('/health');
    const el = $('health');
    if (h.status === 'ok') {
      el.className = 'badge badge-ok';
      el.title = `API ok · ${h.pg_database}`;
    } else {
      el.className = 'badge badge-warn';
      el.title = `API ${h.status} · ${h.db}`;
    }
  } catch {
    const el = $('health');
    el.className = 'badge badge-error';
    el.title = 'API unreachable';
  }
}

// ---------- bootstrap ----------

async function loadOutlookChanges() {
  // Per-symbol outlook flips for the current snapshot date. Shown as a
  // compact banner above the ticker grid. Click a chip to deep-link into
  // Trace for that symbol.
  const bar = $('outlookBar');
  if (!bar) return;
  bar.innerHTML = '';
  if (!state.date) return;
  try {
    const rows = await fetchJson(
      `/api/outlook/changes?date=${encodeURIComponent(state.date)}&limit=12`
    );
    if (!rows || rows.length === 0) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    const counts = rows.reduce((m, r) => {
      m[r.dominant_action] = (m[r.dominant_action] || 0) + 1;
      return m;
    }, {});
    const total = rows.length;
    const head = document.createElement('span');
    head.className = 'outlook-head';
    head.textContent = `${total} outlook flip${total === 1 ? '' : 's'} today: `;
    bar.appendChild(head);
    const order = ['REMOVE', 'REDUCE', 'ADD', 'INCREASE'];
    for (const act of order) {
      if (!counts[act]) continue;
      const tag = document.createElement('span');
      tag.className = `outlook-count outlook-${act.toLowerCase()}`;
      tag.textContent = `${counts[act]} ${act}`;
      bar.appendChild(tag);
    }
    bar.appendChild(document.createTextNode('  '));
    for (const r of rows.slice(0, 10)) {
      const chip = document.createElement('a');
      chip.href = `/trace?date=${encodeURIComponent(state.date)}#${encodeURIComponent(r.symbol)}`;
      chip.className = `outlook-chip outlook-${r.dominant_action.toLowerCase()}`;
      chip.title = `${r.symbol}: ${r.actions.join('/')} from ${r.sources.join(', ')}` +
                   (r.held_today ? '  (held)' : '');
      chip.textContent = `${r.symbol}${r.held_today ? '★' : ''}`;
      bar.appendChild(chip);
    }
  } catch (e) {
    console.error('Failed to load /api/outlook/changes:', e);
    bar.hidden = true;
  }
}

async function loadBriefing() {
  const card = $('briefingCard');
  if (!card) return;
  if (!state.date) { card.hidden = true; return; }
  try {
    const data = await fetchJson(`/api/briefing?date=${encodeURIComponent(state.date)}`);
    const total = (data.outlook_flips && data.outlook_flips.total) || 0;
    const held  = (data.outlook_flips && data.outlook_flips.held)  || 0;
    const nDrift   = (data.allocation_drift || []).length;
    const nFail    = (data.load_failures   || []).length;
    const nActions = (data.yesterday_actions || []).length;

    if (total === 0 && nDrift === 0 && nFail === 0 && nActions === 0) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    const blocks = [];
    if (nActions > 0) {
      const recent = (data.yesterday_actions || []).slice(0, 3)
        .map(a => `${a.symbol}: ${a.action_code}${a.fwd_5d_pct != null ? ` (${a.fwd_5d_pct.toFixed(1)}%)` : ''}`)
        .join('  ·  ');
      blocks.push(`<div class="briefing-block">
        <div class="label">Recent actions</div>
        <div class="value">${nActions}</div>
        <div class="sub">${recent}</div>
      </div>`);
    }
    if (total > 0) {
      const tops = (data.outlook_flips.top_held || [])
        .map(t => `${t.symbol} (${t.dominant_action})`).join(', ');
      blocks.push(`<div class="briefing-block">
        <div class="label">Outlook flips today</div>
        <div class="value">${total}${held > 0 ? ` <span style="font-size:12px;color:#7c2d12;">(${held} held)</span>` : ''}</div>
        <div class="sub">${tops || 'none in your held set'}</div>
      </div>`);
    }
    if (nDrift > 0) {
      const blurb = data.allocation_drift.slice(0, 3)
        .map(c => `${c.category}: ${c.status}`).join('  ·  ');
      blocks.push(`<div class="briefing-block warn">
        <div class="label">Allocation drift</div>
        <div class="value">${nDrift}</div>
        <div class="sub">${blurb}</div>
      </div>`);
    }
    if (nFail > 0) {
      const first = data.load_failures[0];
      blocks.push(`<div class="briefing-block warn">
        <div class="label">Load failures (36h)</div>
        <div class="value">${nFail}</div>
        <div class="sub">${first.file_type || ''} — ${first.error_msg ? first.error_msg.slice(0, 60) : ''}</div>
      </div>`);
    }
    card.innerHTML = `
      <h3>Morning briefing — ${data.as_of_date}</h3>
      <div class="briefing-grid">${blocks.join('')}</div>
      ${data.warnings && data.warnings.length ? `<div style="margin-top:6px;color:#7c2d12;font-size:11px;">${data.warnings.join(' · ')}</div>` : ''}
    `;
  } catch (e) {
    console.error('briefing failed:', e);
    card.hidden = true;
  }
}

async function refreshAll() {
  await Promise.all([
    loadTickers(),
    loadEconIndicators(),
    loadEarnings(),
    loadQuads(),
    loadOutlookChanges(),
    loadBriefing(),
  ]);
  $('footDate').textContent = state.date ? fmtDate(state.date) : '—';
}


document.addEventListener('DOMContentLoaded', async () => {
  loadHealth();
  await loadDates();
  await refreshAll();
});
