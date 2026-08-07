/* Trading Dashboard - frontend logic.
   Six-band daily risk cockpit (TASK_133): Risk Dial, What changed, Regime,
   Factor scorecard, Shortlist, Housekeeping. The old ticker-grid landing
   screen (SECTIONS/renderTickerGrid/loadTickers/etc.) was retired here --
   see docs/dashboard_cockpit_design.md. */

const state = {
  date: null,
  anchorDate: null,
  housekeepingOk: true,
  txnFeedGapCount: 0,
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
      // TASK_138 -- fired rows open the exposure-detail modal (the card only
      // ever shows the $/% total; the modal has the full position list).
      return `<div class="rd-gauge-row sev-${sev}" tabindex="0" role="button"
                   onclick="openGaugeExposureModal('${escapeHtml(g.key)}')"
                   onkeydown="if(event.key==='Enter')openGaugeExposureModal('${escapeHtml(g.key)}')">
        <span class="rd-rail"></span>
        <span class="rd-wt">${wt}</span>
        <span class="rd-gauge-text"><strong>${escapeHtml(g.label || g.key)}</strong> — ${escapeHtml(g.detail || '')}</span>
        <span class="rd-exp">${expTxt}</span>
        <span class="rd-chev">&#8250;</span>
      </div>`;
    }).join('') || '<div class="ev-quiet">No gauges fired.</div>';
    const quietHtml = (r.quiet || [])
      .map(g => `${escapeHtml(g.label || g.key)}: ${escapeHtml(g.detail || '')}`).join('<br>');
    // TASK_140 follow-up 5/6/7 -- "Risk Dial" header removed from
    // index.html (this card is self-explanatory: the number +
    // CLEAR/CAUTION/etc. label already say what it is). Meter bar moved
    // onto the same row as the budget number/label instead of its own row
    // underneath. rd-bottom-row now holds just the Quiet-gauges toggle and
    // the Risk detail link (pushed to the far right via margin-left:auto),
    // with the housekeeping stale-data warning on its own line below that
    // row instead of sharing it -- rdQuietList is still toggled by id (not
    // this.nextElementSibling) since staleWarning can sit between the
    // toggle and the list.
    body.innerHTML = `
      <div class="rd-top-row">
        <span class="rd-budget ${bandClass}">${r.risk_budget != null ? r.risk_budget : '—'}</span>
        <span class="rd-label ${labelClass}">${escapeHtml(r.risk_label || '')}</span>
        <div class="rd-meter"><div class="rd-meter-fill ${bandClass}" style="width:${budget}%;"></div></div>
      </div>
      <div class="rd-headline">${escapeHtml(r.headline || '')}</div>
      <div class="rd-gauge-list">${firedHtml}</div>
      <div class="rd-bottom-row">
        <span class="rd-quiet-toggle" onclick="document.getElementById('rdQuietList').classList.toggle('open')">Quiet gauges (${(r.quiet || []).length})</span>
        <a class="rd-detail-link" href="/risk-detail">&#8594; Risk detail</a>
      </div>
      ${staleWarning}
      <div class="rd-quiet-list" id="rdQuietList">${quietHtml}</div>
    `;
  } catch (e) {
    console.error('risk-dial failed:', e);
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
        <span>${escapeHtml(ev.title || '')}${ev.read_text ? ` <span class="ev-read">— ${escapeHtml(ev.read_text)}</span>` : ''}</span>
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

// Duplicated from web/actionable.js::_quadColor (same hex values) rather than
// shared -- actionable.js is off-limits to touch for unrelated work and there
// is no shared module between the two pages. Keep in sync by eye if the
// palette there ever changes.
function _quadColor(q) {
  if (!q) return '#9ca3af';
  if (/1/.test(q)) return '#2f9e2f'; // Q1 = bullish/growth
  if (/2/.test(q)) return '#1f7af2'; // Q2 = neutral/up
  if (/3/.test(q)) return '#e07c1a'; // Q3 = slowing
  if (/4/.test(q)) return '#d83a3a'; // Q4 = risk-off
  return '#9ca3af';
}

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
      .map(m => `${escapeHtml(String(m.m).slice(5))} <span style="color:${_quadColor('Q' + (m.quad ?? '?'))};font-weight:600;">(Q${m.quad ?? '?'})</span> ${Math.round((m.w || 0) * 100)}%`)
      .join(' · ');
    const bull = (factors.bull || []).map(f => f.ticker || f.category).filter(Boolean).slice(0, 8).join(', ');
    const bear = (factors.bear || []).map(f => f.ticker || f.category).filter(Boolean).slice(0, 8).join(', ');
    const title = `Bull factors: ${bull || '—'}\nBear factors: ${bear || '—'}`;
    strip.innerHTML = `<div class="regime-line" title="${escapeHtml(title)}">
      Window (${windowData.h ?? 60}d): <strong style="color:${_quadColor(dominant)};">${escapeHtml(dominant)}</strong> — ${months || 'no window data'}
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

// TASK_140 follow-up 2 -- inline composition chart beside each scorecard
// table (replaces the earlier Composition popup entirely -- no click
// needed, and no second fetch: reuses the same rows loadFactorScorecard()
// already pulled). Sector/Asset class render a pie (weight%, part of a
// whole); Style renders a bar list instead of a pie since its tags overlap
// and don't sum to 100% (a stock can carry several style tags at once).
const _CAT_VARS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5', '--cat6', '--cat7', '--cat8', '--cat9'];

function _svgns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }

// Shared #tip tooltip (same element/pattern as risk_detail.js / risk_gauge_modal.js).
function _chartShowTip(evt, rows) {
  const tip = $('tip');
  if (!tip) return;
  tip.innerHTML = rows.map(r => `<div class="row"><span class="k">${r.k}</span><b>${r.v}</b></div>`).join('');
  tip.classList.add('show');
  tip.style.left = evt.clientX + 'px';
  tip.style.top = (evt.clientY - 10) + 'px';
}
function _chartHideTip() { const tip = $('tip'); if (tip) tip.classList.remove('show'); }
document.addEventListener('mousemove', e => {
  const tip = $('tip');
  if (tip && tip.classList.contains('show')) { tip.style.left = e.clientX + 'px'; tip.style.top = (e.clientY - 10) + 'px'; }
});

// TASK_140 follow-up 3 -- one color per category, assigned once and shared
// by the table's row swatch (category column) AND the chart slice/bar, so
// they're always the same color for the same category -- this replaces the
// separate legend-chip list under the pie (redundant with the table, which
// already carries category + weight% and now the color too). 'Unmapped'
// never gets one of these nine -- it's always --cat-unmapped, everywhere.
function _catColorMap(rows) {
  const map = new Map();
  let i = 0;
  (rows || []).forEach(r => {
    if (r.category === 'Unmapped' || map.has(r.category)) return;
    map.set(r.category, `var(${_CAT_VARS[i % _CAT_VARS.length]})`);
    i++;
  });
  return map;
}
function _catColor(colorMap, category) {
  if (category === 'Unmapped') return 'var(--cat-unmapped)';
  return colorMap.get(category) || 'var(--text-3)';
}

function _renderCatPie(svgId, rows, unmapped, colorMap) {
  const svg = $(svgId);
  if (!svg) return;
  svg.innerHTML = '';
  const items = (rows || []).filter(r => r.weight_pct != null && Number(r.weight_pct) > 0)
    .map(r => ({ category: r.category, weight_pct: r.weight_pct }));
  if (unmapped && unmapped.weight_pct != null) items.push({ category: unmapped.category, weight_pct: unmapped.weight_pct });
  if (!items.length) return;
  const total = items.reduce((s, r) => s + Number(r.weight_pct), 0);
  const cx = 95, cy = 90, r = 78;
  svg.setAttribute('viewBox', '0 0 190 190');
  let a0 = -Math.PI / 2;
  items.forEach(d => {
    const frac = Number(d.weight_pct) / total;
    const a1 = a0 + frac * Math.PI * 2;
    const color = _catColor(colorMap, d.category);
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const large = (a1 - a0) > Math.PI ? 1 : 0;
    const path = _svgns('path');
    path.setAttribute('d', `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} Z`);
    path.setAttribute('fill', color);
    path.setAttribute('stroke', 'var(--card-bg)'); path.setAttribute('stroke-width', '2');
    svg.appendChild(path);
    if (frac > 0.08) {
      const am = (a0 + a1) / 2, lx = cx + r * 0.65 * Math.cos(am), ly = cy + r * 0.65 * Math.sin(am);
      const lbl = _svgns('text');
      lbl.setAttribute('x', lx); lbl.setAttribute('y', ly + 3); lbl.setAttribute('class', 'slice-label');
      lbl.textContent = (frac * 100 >= 10 ? Math.round(frac * 100) : (frac * 100).toFixed(1)) + '%';
      svg.appendChild(lbl);
    }
    const hit = _svgns('path');
    hit.setAttribute('d', path.getAttribute('d')); hit.setAttribute('class', 'chart-hit');
    hit.addEventListener('mousemove', e => _chartShowTip(e, [{ k: d.category, v: (frac * 100).toFixed(1) + '%' }]));
    hit.addEventListener('mouseleave', _chartHideTip);
    svg.appendChild(hit);
    a0 = a1;
  });
}

function _renderCatBars(svgId, rows, unmapped, colorMap) {
  const svg = $(svgId);
  if (!svg) return;
  svg.innerHTML = '';
  const items = (rows || []).filter(r => r.weight_pct != null && Number(r.weight_pct) > 0)
    .map(r => ({ category: r.category, weight_pct: r.weight_pct }));
  if (unmapped && unmapped.weight_pct != null) items.push({ category: unmapped.category, weight_pct: unmapped.weight_pct });
  items.sort((a, b) => Number(b.weight_pct) - Number(a.weight_pct));
  if (!items.length) return;
  const W = 190, H = items.length * 22;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const max = Math.max(...items.map(r => Number(r.weight_pct)));
  const rowH = H / items.length, barH = 15, labelW = 74, plotW = W - labelW - 6;
  items.forEach((d, i) => {
    const y = i * rowH + (rowH - barH) / 2;
    const color = _catColor(colorMap, d.category);
    const name = _svgns('text');
    name.setAttribute('x', labelW - 6); name.setAttribute('y', y + barH * 0.75);
    name.setAttribute('text-anchor', 'end'); name.setAttribute('class', 'bar-name');
    name.setAttribute('style', 'font-size:9px;');
    name.textContent = d.category.length > 11 ? d.category.slice(0, 10) + '…' : d.category;
    svg.appendChild(name);
    const w = (Number(d.weight_pct) / max) * plotW;
    const rect = _svgns('rect');
    rect.setAttribute('x', labelW); rect.setAttribute('y', y); rect.setAttribute('width', Math.max(w, 2));
    rect.setAttribute('height', barH); rect.setAttribute('rx', 3); rect.setAttribute('fill', color);
    svg.appendChild(rect);
    const hit = _svgns('rect');
    hit.setAttribute('x', 0); hit.setAttribute('y', y - 2); hit.setAttribute('width', W); hit.setAttribute('height', barH + 4);
    hit.setAttribute('class', 'chart-hit');
    hit.addEventListener('mousemove', e => _chartShowTip(e, [{ k: d.category, v: Number(d.weight_pct).toFixed(1) + '%' }]));
    hit.addEventListener('mouseleave', _chartHideTip);
    svg.appendChild(hit);
  });
}

// TASK_140 -- one scorecard per axis, all three rendered simultaneously
// (relayout replaced the tab switcher -- see index.html/styles.css). Flows
// column dropped per user request (the "Returns degraded" banner it backed
// was also removed -- this user doesn't load transaction history often by
// design, so 'suspect' rows are expected, not actionable noise). Today/
// Yesterday are new single-day vs-Mkt columns (TASK_140,
// etl/derive_category_perf.py's EXTRA_WINDOWS), same delta convention as
// the existing 1w-3m columns.
const _FS_WINDOWS = [
  { key: 'today', label: 'Today', full: 'today (1 day)' },
  { key: 'yesterday', label: 'Yesterday', full: 'yesterday (the single prior trading day, not a 2-day window)' },
  { key: '1w', label: '1w', full: '1 week' },
  { key: '3w', label: '3w', full: '3 weeks' },
  { key: '1m', label: '1m', full: '1 month' },
  { key: '2m', label: '2m', full: '2 months' },
  { key: '3m', label: '3m', full: '3 months' },
];

async function loadFactorScorecard(axis, bodyId, chartId) {
  const body = $(bodyId);
  if (!body) return;
  try {
    const params = new URLSearchParams({ axis });
    if (state.date) params.set('date', state.date);
    const r = await fetchJson(`/api/cockpit/factor-scorecard?${params.toString()}`);
    const note = axis === 'style'
      ? '<div class="fs-note">Overlapping tags — not an allocation.</div>' : '';
    // TASK_140 follow-up 3 -- same color, category column swatch + chart
    // slice/bar. Computed once here from the same r.rows order the chart
    // renderer below also gets, so table and chart never disagree.
    const colorMap = _catColorMap(r.rows);
    const rows = (r.rows || []).map(row => {
      // TASK_136 C.1 -- keep the raw twr_*/bench_* absolute returns reachable
      // on hover via the row's title, since the cells themselves only show
      // the vs-Mkt delta.
      const titleParts = _FS_WINDOWS
        .map(w => {
          const twr = row[`twr_${w.key}`], bench = row[`bench_${w.key}`];
          if (twr == null && bench == null) return null;
          const fmt = (v) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : '—';
          return `${w.label}: you ${fmt(twr)} / mkt ${fmt(bench)}`;
        })
        .filter(Boolean)
        .join('\n');
      const cells = _FS_WINDOWS.map(w => {
        const twr = row[`twr_${w.key}`], bench = row[`bench_${w.key}`];
        const delta = (twr != null && bench != null) ? twr - bench : null;
        return `<td>${_fsColorCell(delta)}</td>`;
      }).join('');
      const weightPct = row.weight_pct != null ? Number(row.weight_pct) : null;
      // TASK_139 -- row click opens the same exposure-detail modal as the
      // Risk Dial's fired gauges (Screen D of the design doc), keyed by
      // (axis, category) instead of gauge_key.
      return `<tr title="${escapeHtml(titleParts)}" class="fs-clickable"
                   onclick="openFactorExposureModal('${escapeHtml(axis)}', '${escapeHtml(row.category).replace(/'/g, "\\'")}')">
        <td><span class="cat-swatch" style="background:${_catColor(colorMap, row.category)}"></span>${escapeHtml(row.category)}</td>
        <td class="fs-weight-cell">
          ${weightPct != null ? `<span class="fs-weight-bar" style="width:${Math.max(0, Math.min(100, weightPct))}%"></span>` : ''}
          <span class="fs-weight-text">${weightPct != null ? weightPct.toFixed(1) + '%' : ''}</span>
        </td>
        <td>${_verdictBadge(row.verdict)}</td>
        ${cells}
      </tr>`;
    }).join('');
    const unmapped = r.unmapped
      ? `<div class="fs-note">Unmapped: ${escapeHtml(r.unmapped.category)} — ${r.unmapped.weight_pct != null ? Number(r.unmapped.weight_pct).toFixed(1) + '%' : ''} of book not resolved to a category.</div>`
      : '';
    const headCells = _FS_WINDOWS
      .map(w => `<th title="Your time-weighted return in this category vs its benchmark ETF, ${w.full}">${w.label}</th>`)
      .join('');
    // TASK_136 A.3 -- wrapped in overflow-x:auto so the table degrades (its
    // own scrollbar) at narrow widths instead of forcing the grid track
    // wider than its share.
    body.innerHTML = `
      ${note}
      <div style="overflow-x:auto">
        <table class="fs-table">
          <thead><tr><th title="Category, sector/asset-class/style">Category</th>
            <th title="Weight — % of your total portfolio">Wt%</th>
            <th title="Recommendation from (over/under target-allocation) x (quad regime stance for this category)">Verdict</th>
            ${headCells}</tr></thead>
          <tbody>${rows || `<tr><td colspan="${3 + _FS_WINDOWS.length}">No rows.</td></tr>`}</tbody>
        </table>
      </div>
      ${unmapped}
    `;
    if (chartId) {
      if (axis === 'style') _renderCatBars(chartId, r.rows, r.unmapped, colorMap);
      else _renderCatPie(chartId, r.rows, r.unmapped, colorMap);
    }
  } catch (e) {
    console.error(`factor scorecard (${axis}) failed:`, e);
    body.innerHTML = '<div class="ev-fail">&#9888; Factor scorecard unavailable.</div>';
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
  await loadRiskDial();
  await Promise.all([
    loadEventsBand(),
    loadRegimeBand(),
    loadFactorScorecard('sector', 'sectorScorecardBody', 'sectorChart'),
    loadFactorScorecard('asset_class', 'assetClassScorecardBody', 'assetChart'),
    loadFactorScorecard('style', 'styleScorecardBody', 'styleChart'),
    loadBriefing(),
  ]);
  { const _fd = $('footDate'); if (_fd) _fd.textContent = state.date ? fmtDate(state.date) : '—'; }
}


document.addEventListener('DOMContentLoaded', async () => {
  loadHealth();
  await loadDates();
  const sel = $('datePicker');
  if (sel) sel.addEventListener('change', () => {
    state.date = sel.value;
    refreshAll();
  });
  const refreshBtn = $('refreshBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', () => refreshAll());
  await refreshAll();
});
