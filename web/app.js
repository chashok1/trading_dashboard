/* Trading Dashboard - frontend logic.
   Six-band daily risk cockpit (TASK_133): Risk Dial, What changed, Regime,
   Factor scorecard, Shortlist, Housekeeping. The old ticker-grid landing
   screen (SECTIONS/renderTickerGrid/loadTickers/etc.) was retired here --
   see docs/dashboard_cockpit_design.md. */

const state = {
  date: null,
  anchorDate: null,
  fsAxis: 'sector',
  housekeepingOk: true,
  txnFeedGapCount: 0,
  // TASK_136 C.2 -- populated by loadRiskDial(), read by loadShortlist() so
  // the shortlist can pre-multiply AMT$ without a second risk-dial fetch.
  suggestedSizeMultiplier: null,
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

// fetchJson is provided by _common.js (window.fetchJson).

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
  { const _fd = $('footDate'); if (_fd) _fd.textContent = state.date ? fmtDate(state.date) : '—'; }
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
      chip.href = `/trace?date=${encodeURIComponent(state.date)}#${encodeURIComponent(r.tos_symbol)}`;
      chip.className = `outlook-chip outlook-${r.dominant_action.toLowerCase()}`;
      chip.title = `${r.tos_symbol}: ${r.actions.join('/')} from ${r.sources.join(', ')}` +
                   (r.held_today ? '  (held)' : '');
      chip.textContent = `${r.tos_symbol}${r.held_today ? '★' : ''}`;
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
        .map(a => `${a.tos_symbol}: ${a.action_code}${a.fwd_5d_pct != null ? ` (${a.fwd_5d_pct.toFixed(1)}%)` : ''}`)
        .join('  ·  ');
      blocks.push(`<div class="briefing-block">
        <div class="label">Recent actions</div>
        <div class="value">${nActions}</div>
        <div class="sub">${recent}</div>
      </div>`);
    }
    if (total > 0) {
      const tops = (data.outlook_flips.top_held || [])
        .map(t => `${t.tos_symbol} (${t.dominant_action})`).join(', ');
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

// ---------- Band 1: Risk Dial ----------

function _dateQS() { return state.date ? `?date=${encodeURIComponent(state.date)}` : ''; }

// TASK_134 A.5 -- risk_label -> meter-fill/number band class, tokens only
// (styles.css owns the actual colors; this just names the band).
function _riskBandClass(label) {
  switch (label) {
    case 'CLEAR': return 'b-clear';
    case 'CAUTION': return 'b-caution';
    case 'DEFENSIVE': return 'b-defensive';
    case 'NOT INVESTABLE': return 'b-notinv';
    default: return '';
  }
}

async function loadRiskDial() {
  const body = $('riskDialBody');
  if (!body) return;
  try {
    const r = await fetchJson(`/api/cockpit/risk-dial${_dateQS()}`);
    // TASK_136 C.2 -- shared with loadShortlist() so it can pre-multiply
    // AMT$ without a second fetch of this same endpoint.
    state.suggestedSizeMultiplier = r.suggested_size_multiplier != null ? r.suggested_size_multiplier : null;
    const labelClass = (r.risk_label || '').replace(/\s+/g, '');
    const bandClass = _riskBandClass(r.risk_label);
    const budget = r.risk_budget != null ? Math.max(0, Math.min(100, r.risk_budget)) : 0;
    // Band 6 -> Band 1 warning: a risk dial computed on stale/failed
    // housekeeping is worse than no risk dial (spec 7.2 Band 6).
    const staleWarning = !state.housekeepingOk
      ? `<div class="rd-stale-warning">Housekeeping flagged stale or failed data — this read may be based on incomplete inputs.</div>`
      : '';
    // TASK_134 A.4 -- severity encoded as a coloured left rail + weight chip,
    // never colour alone. loadRiskDial's caller (drv_market_stat.gauges_fired)
    // already sorts `fired` by weight descending -- kept as-is.
    const firedHtml = (r.fired || []).map(g => {
      const exp = g.exposure;
      const expTxt = (exp && exp.dollar != null)
        ? `$${Math.round(exp.dollar).toLocaleString()}${exp.pct != null ? ` (${exp.pct.toFixed(1)}%)` : ''}`
        : '';
      const wt = Math.round(g.weight || 0);
      const sev = wt >= 3 ? 3 : wt <= 1 ? 1 : 2;
      return `<div class="rd-gauge-row sev-${sev}">
        <span class="rd-rail"></span>
        <span class="rd-wt">${wt}</span>
        <span class="rd-gauge-text"><strong>${escapeHtml(g.label || g.key)}</strong> — ${escapeHtml(g.detail || '')}</span>
        <span class="rd-exp">${expTxt}</span>
      </div>`;
    }).join('') || '<div class="ev-quiet">No gauges fired.</div>';
    const quietHtml = (r.quiet || [])
      .map(g => `${escapeHtml(g.label || g.key)}: ${escapeHtml(g.detail || '')}`).join('<br>');
    // TASK_134 A.3 -- number leads: budget + label share one row, the meter
    // is 14px, and the headline drops below the meter as a plain supporting
    // sentence (13px, --text-2).
    // TASK_136 B.1 -- in a 4-col card the size-line no longer fits on the
    // same row as the number/label (it was pushed off with margin-left:auto
    // on a full-width card); it now gets its own row directly under line 1.
    body.innerHTML = `
      ${staleWarning}
      <div class="rd-top-row">
        <span class="rd-budget ${bandClass}">${r.risk_budget != null ? r.risk_budget : '—'}</span>
        <span class="rd-label ${labelClass}">${escapeHtml(r.risk_label || '')}</span>
      </div>
      ${r.suggested_size_multiplier != null
        ? `<div class="rd-size-row"><span class="rd-size-line">today's size = AMT$ &times; <strong>${r.suggested_size_multiplier}</strong></span></div>` : ''}
      <div class="rd-meter"><div class="rd-meter-fill ${bandClass}" style="width:${budget}%;"></div></div>
      <div class="rd-headline">${escapeHtml(r.headline || '')}</div>
      <div class="rd-gauge-list">${firedHtml}</div>
      <span class="rd-quiet-toggle" onclick="this.nextElementSibling.classList.toggle('open')">Quiet gauges (${(r.quiet || []).length})</span>
      <div class="rd-quiet-list">${quietHtml}</div>
    `;
  } catch (e) {
    console.error('risk-dial failed:', e);
    state.suggestedSizeMultiplier = null;
    body.innerHTML = '<div class="ev-fail">&#9888; Risk dial unavailable.</div>';
  }
}

// ---------- Band 2: What changed ----------

async function loadEventsBand() {
  const body = $('eventsBody');
  if (!body) return;
  try {
    const r = await fetchJson(`/api/cockpit/events${_dateQS()}`);
    if (r.quiet) {
      body.innerHTML = `<div class="ev-quiet">No material market events today`
        + (r.max_z_symbol ? ` (largest move: ${escapeHtml(r.max_z_symbol)}, z=${r.max_abs_z ?? '—'})` : '')
        + `.</div>`;
      return;
    }
    body.innerHTML = (r.events || []).map(ev => `
      <div class="ev-row ev-row-${escapeHtml(ev.severity || 'info')}">
        <span class="ev-rail"></span>
        <span class="ev-sev ${escapeHtml(ev.severity || 'info')}">${escapeHtml(ev.severity || '')}</span>
        <span>${escapeHtml(ev.title || '')}</span>
        ${ev.read_text ? `<span class="ev-read">— ${escapeHtml(ev.read_text)}</span>` : ''}
      </div>`).join('') || '<div class="ev-quiet">No events.</div>';
  } catch (e) {
    console.error('events band failed:', e);
    body.innerHTML = '<div class="ev-fail">&#9888; Events unavailable.</div>';
  }
}

// ---------- Band 3: Regime ----------
// No new computation (spec 7.2 Band 3) -- reads the same /api/quad-window +
// /api/quad/band-factors already powering web/actionable.js's regime band.
// The hover title carries the same bull/bear factor table as a plain-text
// popover; actionable.js's richer interactive popover was not duplicated
// here (documented simplification, see DEV_HANDOFF.md).

async function loadRegimeBand() {
  const strip = $('regimeStrip');
  if (!strip) return;
  try {
    const viewingLive = !state.date || state.date === state.anchorDate;
    const qs = viewingLive ? '' : _dateQS();
    const [windowData, factors] = await Promise.all([
      fetchJson(`/api/quad-window${qs}`).catch(() => null),
      fetchJson(`/api/quad/band-factors${qs}`).catch(() => ({ bull: [], bear: [] })),
    ]);
    if (!windowData) { strip.innerHTML = '<div class="ev-fail">&#9888; Regime data unavailable.</div>'; return; }
    const dominant = windowData.dominant_quad != null ? `Quad ${windowData.dominant_quad}` : '—';
    const months = (windowData.months || [])
      .map(m => `${escapeHtml(String(m.m).slice(5))} (Q${m.quad ?? '?'}) ${Math.round((m.w || 0) * 100)}%`)
      .join(' · ');
    const bull = (factors.bull || []).map(f => f.ticker || f.category).filter(Boolean).slice(0, 8).join(', ');
    const bear = (factors.bear || []).map(f => f.ticker || f.category).filter(Boolean).slice(0, 8).join(', ');
    const title = `Bull factors: ${bull || '—'}\nBear factors: ${bear || '—'}`;
    strip.innerHTML = `<div class="regime-line" title="${escapeHtml(title)}">
      Window (${windowData.h ?? 60}d): <strong>${escapeHtml(dominant)}</strong> — ${months || 'no window data'}
    </div>`;
  } catch (e) {
    console.error('regime band failed:', e);
    strip.innerHTML = '<div class="ev-fail">&#9888; Regime data unavailable.</div>';
  }
}

// ---------- Band 4: Factor scorecard ----------

function _fsColorCell(v) {
  if (v == null) return '';
  const n = Number(v) * 100;
  if (!Number.isFinite(n)) return '';
  const cls = n > 0 ? 'pos' : n < 0 ? 'neg' : '';
  return `<span class="${cls}">${n.toFixed(1)}%</span>`;
}

// TASK_134 A.6 -- verdict badges through the app's action-color vocabulary.
// Not a call to window.actionDisplay(): drv_category_perf's verdict codes
// (ADD/PRESS/HOLD/TRIM/TRIM_HARD/ROTATE) are category-allocation verdicts,
// a different vocabulary from actionDisplay's per-symbol BuySell codes (its
// own 'ADD' key means "buy to minimum lot", not this table's "add to this
// category") -- reusing the lookup by string would mislabel the badge.
// Spec asks for the *class-name convention* (act-buy*/act-sell*/act-neutral/
// act-mixed), which this mirrors directly against the token set.
const _VERDICT_CLS = {
  ADD: 'act-buy-weak', PRESS: 'act-buy',
  HOLD: 'act-neutral',
  TRIM: 'act-sell', TRIM_HARD: 'act-sell-strong',
  ROTATE: 'act-mixed',
};
function _verdictBadge(verdict) {
  if (!verdict) return '';
  const cls = _VERDICT_CLS[verdict] || 'act-neutral';
  return `<span class="fs-verdict ${cls}-tint">${escapeHtml(verdict)}</span>`;
}

async function loadFactorScorecard() {
  const body = $('factorScorecardBody');
  if (!body) return;
  try {
    const params = new URLSearchParams({ axis: state.fsAxis });
    if (state.date) params.set('date', state.date);
    const r = await fetchJson(`/api/cockpit/factor-scorecard?${params.toString()}`);
    const note = state.fsAxis === 'style'
      ? '<div class="fs-note">Overlapping tags — not an allocation.</div>' : '';
    const degradedNote = state.txnFeedGapCount > 0
      ? `<div class="fs-degraded">Returns degraded — ${state.txnFeedGapCount} account(s) missing transaction history. See Housekeeping.</div>`
      : '';
    const windows = ['1w', '3w', '1m', '2m', '3m'];
    const rows = (r.rows || []).map(row => {
      // TASK_136 C.1 -- keep the raw twr_*/bench_* absolute returns reachable
      // on hover via the row's title, since the cells themselves now show
      // only the vs-Mkt delta (no new fields -- same twr_*/bench_* the API
      // already returns, just not dropped from the row).
      const titleParts = windows
        .map(w => {
          const twr = row[`twr_${w}`], bench = row[`bench_${w}`];
          if (twr == null && bench == null) return null;
          const fmt = (v) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : '—';
          return `${w}: you ${fmt(twr)} / mkt ${fmt(bench)}`;
        })
        .filter(Boolean)
        .join('\n');
      const cells = windows.map(w => {
        const twr = row[`twr_${w}`], bench = row[`bench_${w}`];
        const delta = (twr != null && bench != null) ? twr - bench : null;
        return `<td>${_fsColorCell(delta)}</td>`;
      }).join('');
      const weightPct = row.weight_pct != null ? Number(row.weight_pct) : null;
      return `<tr title="${escapeHtml(titleParts)}">
        <td>${escapeHtml(row.category)}</td>
        <td class="fs-weight-cell">
          ${weightPct != null ? `<span class="fs-weight-bar" style="width:${Math.max(0, Math.min(100, weightPct))}%"></span>` : ''}
          <span class="fs-weight-text">${weightPct != null ? weightPct.toFixed(1) + '%' : ''}</span>
        </td>
        <td><span class="fs-conf ${escapeHtml(row.flows_confidence || '')}">${escapeHtml(row.flows_confidence || '')}</span></td>
        <td>${_verdictBadge(row.verdict)}</td>
        ${cells}
      </tr>`;
    }).join('');
    const unmapped = r.unmapped
      ? `<div class="fs-note">Unmapped: ${escapeHtml(r.unmapped.category)} — ${r.unmapped.weight_pct != null ? Number(r.unmapped.weight_pct).toFixed(1) + '%' : ''} of book not resolved to a category.</div>`
      : '';
    // TASK_136 A.3 -- wrapped in overflow-x:auto so the table degrades (its
    // own scrollbar) at narrow widths instead of forcing the 12-col grid
    // track wider than its share (the min-width:0 fix on .cockpit-band only
    // stops the *track*; the table itself still needs somewhere to overflow
    // to at very narrow viewports).
    body.innerHTML = `
      ${degradedNote}
      ${note}
      <div style="overflow-x:auto">
        <table class="fs-table">
          <thead><tr><th>Category</th><th>Wt%</th><th>Flows</th><th>Verdict</th>
            <th>vs Mkt 1w</th><th>vs Mkt 3w</th><th>vs Mkt 1m</th><th>vs Mkt 2m</th><th>vs Mkt 3m</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="9">No rows.</td></tr>'}</tbody>
        </table>
      </div>
      ${unmapped}
    `;
  } catch (e) {
    console.error('factor scorecard failed:', e);
    body.innerHTML = '<div class="ev-fail">&#9888; Factor scorecard unavailable.</div>';
  }
}

function _wireFsTabs() {
  const tabs = $('fsTabs');
  if (!tabs || tabs.dataset.wired) return;
  tabs.dataset.wired = '1';
  tabs.addEventListener('click', (e) => {
    const btn = e.target.closest('.fs-tab');
    if (!btn) return;
    state.fsAxis = btn.dataset.axis;
    for (const b of tabs.querySelectorAll('.fs-tab')) b.classList.toggle('active', b === btn);
    loadFactorScorecard();
  });
}

// ---------- Band 5: Shortlist ----------

async function loadShortlist() {
  const body = $('shortlistBody');
  if (!body) return;
  try {
    const r = await fetchJson(`/api/cockpit/shortlist${_dateQS()}`);
    const rows = r.rows || [];
    if (!rows.length) {
      body.innerHTML = '<div class="sl-empty">No high-conviction rows today.</div>';
      return;
    }
    body.innerHTML = rows.map(row => {
      // TASK_134 A.6 -- final_code is a real BuySell code (unlike Band 4's
      // category verdicts), so actionDisplay() is directly reusable here.
      const d = window.actionDisplay ? window.actionDisplay(row.final_code) : null;
      const actionHtml = d
        ? `<span class="${d.colorCls || 'act-neutral'}">${escapeHtml(d.code || d.label || '')}</span>`
        : escapeHtml(row.final_code || '');
      // TASK_136 C.2 -- pre-multiply AMT$ by the same suggested_size_multiplier
      // the Risk Dial shows (state.suggestedSizeMultiplier, set by
      // loadRiskDial()) so the user doesn't do the multiplication by hand
      // while reading two cards. Presentation only -- AMT$ itself, and what
      // gets written anywhere, is untouched.
      const rawAmt = row.current_position_dollar != null ? Number(row.current_position_dollar) : null;
      const mult = state.suggestedSizeMultiplier;
      let amtHtml = '';
      if (rawAmt != null && mult != null) {
        const adjusted = rawAmt * mult;
        amtHtml = `<span class="sl-amt${row.stop_breached ? ' sl-stop-breached' : ''}">$${Math.round(adjusted).toLocaleString()}</span>
        <span class="sl-amt-sub">AMT$ ${Math.round(rawAmt).toLocaleString()} &times; ${mult}</span>`;
      } else if (rawAmt != null) {
        amtHtml = `<span class="sl-amt${row.stop_breached ? ' sl-stop-breached' : ''}">$${Math.round(rawAmt).toLocaleString()}</span>`;
      }
      const stopFlag = row.stop_breached ? '<span class="sl-stop-flag">stop breached</span>' : '';
      return `<div class="sl-row">
        <span class="sl-symbol">${escapeHtml(row.tos_symbol)}</span>
        <span class="sl-action">${actionHtml}</span>
        <span class="sl-desc">${escapeHtml(row.description || '')}</span>
        ${stopFlag}
        <span class="sl-amt-block">${amtHtml}</span>
      </div>`;
    }).join('');
  } catch (e) {
    console.error('shortlist failed:', e);
    body.innerHTML = '<div class="ev-fail">&#9888; Shortlist unavailable.</div>';
  }
}

// ---------- Band 6: Housekeeping ----------

async function loadHousekeeping() {
  const line = $('housekeepingLine');
  try {
    const anchor = await fetchJson('/api/anchor-status').catch(() => null);
    state.anchorDate = anchor ? anchor.anchor_date : null;
    const ok = !anchor || !anchor.is_stale;
    state.housekeepingOk = ok;
    if (line) {
      line.innerHTML = `<span class="hk-dot ${ok ? 'ok' : 'bad'}"></span>`
        + (ok ? 'Data current.' : escapeHtml(anchor.message || 'Data behind expected market close.'));
    }
  } catch (e) {
    console.error('housekeeping (anchor-status) failed:', e);
    state.housekeepingOk = false;
    if (line) line.innerHTML = '<span class="hk-dot bad"></span>Housekeeping check failed.';
  }
  await loadTxnFeedGaps();
  await Promise.all([loadEconIndicators(), loadEarnings()]);
}

// TASK_134 C.1 -- per-account transaction-feed staleness (Schwab hist_cst /
// Fidelity hist_ft falling behind their own hist_cs/hist_f positions).
async function loadTxnFeedGaps() {
  const box = $('housekeepingGaps');
  try {
    const r = await fetchJson('/api/cockpit/housekeeping').catch(() => null);
    const gaps = (r && r.txn_feed_gaps) || [];
    state.txnFeedGapCount = gaps.length;
    if (!box) return;
    box.innerHTML = gaps.map(g => {
      const gapTxt = g.transactions_last
        ? `${g.gap_trading_days} trading days behind (last transaction ${g.transactions_last})`
        : 'no transactions ever loaded';
      return `<div class="hk-line hk-gap-line">
        <span class="hk-dot bad"></span>${escapeHtml(g.broker)} ${escapeHtml(g.account)} — ${gapTxt}
      </div>`;
    }).join('');
  } catch (e) {
    console.error('txn feed gaps failed:', e);
    state.txnFeedGapCount = 0;
    if (box) box.innerHTML = '';
  }
}

async function refreshAll() {
  // Band 6 (housekeeping) resolves state.housekeepingOk/state.anchorDate
  // first since Band 1 needs to know whether to show its stale-data warning
  // (spec 7.2 Band 6: "When it is red, Band 1 must show a warning").
  await loadHousekeeping();
  // TASK_136 C.2 -- loadRiskDial() must resolve before loadShortlist() so
  // state.suggestedSizeMultiplier is populated in time for the shortlist's
  // pre-multiplied size; sequenced ahead of the rest instead of in the same
  // Promise.all (order inside Promise.all is not guaranteed).
  await loadRiskDial();
  await Promise.all([
    loadEventsBand(),
    loadRegimeBand(),
    loadFactorScorecard(),
    loadShortlist(),
    loadOutlookChanges(),
    loadBriefing(),
  ]);
  { const _fd = $('footDate'); if (_fd) _fd.textContent = state.date ? fmtDate(state.date) : '—'; }
}


document.addEventListener('DOMContentLoaded', async () => {
  loadHealth();
  await loadDates();
  _wireFsTabs();
  const sel = $('datePicker');
  if (sel) sel.addEventListener('change', () => {
    state.date = sel.value;
    refreshAll();
  });
  const refreshBtn = $('refreshBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', () => refreshAll());
  await refreshAll();
});
