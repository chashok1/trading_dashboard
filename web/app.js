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
  // 2026-08-09 -- Cockpit Accounts filter (Sector/Asset Class/Style grids,
  // the "second column"). Empty array = all accounts (default, matches
  // today's behavior exactly -- reads the pre-computed nightly table).
  // Non-empty = live per-account recompute via GET /api/cockpit/factor-
  // scorecard's `accounts` param. account_number values (ref_accounts.
  // account_number), not short_name -- that's what the backend filter
  // matches on.
  catAccounts: [],
  // 2026-08-09 -- Market View Source filter. null = default (Hedgeye quad
  // outlook, ref_quad_outlook); one of RR/CALL/ETF/II/SSS/PS = that
  // source's own per-symbol calls instead (drv_source_standing). User:
  // "add a filter above those graphs for filtering by source."
  marketViewSource: null,
};
// 2026-08-09 BUGFIX -- `state` is declared with top-level `const` in this
// classic (non-module) script, which does NOT attach it to `window` (only
// `var`/function declarations do -- a `let`/`const` top-level binding
// lives in the script's lexical scope, reachable by bare name `state`
// within this file, but window.state is a DIFFERENT, unrelated lookup).
// risk_gauge_modal.js (and any other later-loaded script) reads
// window.state.date/window.state.catAccounts to filter its own fetches --
// window.state has been `undefined` this whole time, so those reads
// silently short-circuited to falsy and the date/accounts params were
// silently omitted, not applied. Never surfaced as visibly wrong because
// omitting `date` defaults to the anchor anyway, usually the date being
// viewed regardless. User: "popups on the my accounts not considering the
// filters (ex: one account)" surfaced it.
window.state = state;

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
// 2026-08-10 -- loadEarnings()/#eventBand removed: it was a strict subset
// of this same endpoint's own data (both ultimately read ref_calendar_event;
// this query already includes every market-structure row -- Fed Meeting,
// FOMC Minutes, expiration, etc -- unfiltered, on top of the econ releases),
// so every one of those rows was rendering in both grids. limit bumped
// 20 -> 40 to cover what the merged-away Event grid used to show on its
// own. User: "Are the entries in panels (INDICATOR and EVENT grids)
// duplicated? Can we merge those two?" -> "Merge into one grid."

async function loadEconIndicators() {
  const tbody = $('econBody');
  const empty = $('econEmpty');
  tbody.innerHTML = '';
  try {
    const url = state.date
      ? `/api/dashboard/econ-indicators?date=${encodeURIComponent(state.date)}&limit=40`
      : '/api/dashboard/econ-indicators?limit=40';
    const rows = await fetchJson(url);
    if (!rows || rows.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    for (const r of rows) {
      const tr = document.createElement('tr');
      // 2026-08-08 -- Signal column removed per user request ("remove the
      // SIGNAL column from INDICATOR grid"); normOutlook(r.signal) is no
      // longer read here.
      tr.innerHTML = `
        <td class="text">${r.indicator || ''}</td>
        <td class="num">${r.days != null ? r.days : ''}</td>
        <td>${fmtDate(r.indicator_date)}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error('Failed to load econ indicators:', e);
    empty.hidden = false;
    empty.textContent = 'Failed to load.';
  }
}

// TASK_140 follow-up 10 -- new grid below Event: earnings in the next 7
// days, scoped to held positions + actionable symbols only (not the whole
// tracked watchlist -- see api/routers/health.py::get_near_term_earnings).
// 2026-08-10 -- days_ahead 7 -> 30 ("one month") per user request.
async function loadNearTermEarnings() {
  const tbody = $('nearEarningsBody');
  const empty = $('nearEarningsEmpty');
  if (!tbody) return;
  tbody.innerHTML = '';
  try {
    const url = state.date
      ? `/api/dashboard/near-term-earnings?date=${encodeURIComponent(state.date)}&days_ahead=30`
      : '/api/dashboard/near-term-earnings?days_ahead=30';
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
        <td class="text">${escapeHtml(r.symbol || '')}</td>
        <td class="num">${days}</td>
        <td>${fmtDate(r.event_date)}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error('Failed to load near-term earnings:', e);
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
    // 2026-08-14 -- SPX upside/downside line, ALWAYS shown (not just when
    // spx_top_range/spx_top_range_warning actually fire, which only happens
    // at 70%/85%+ of its risk range -- see etl/derive_risk_dial.py). The
    // API already returns every gauge's own value/detail in fired OR quiet
    // regardless of firing state; this just surfaces spx_top_range_warning's
    // detail (which already includes "+X% to TRR / -Y% to LRR", added same
    // day) unconditionally instead of leaving it to be discovered only by
    // opening "Quiet gauges" on a day neither SPX gauge fires. User: "add
    // risk if s&P is at TRR just like today. I need to see this SPX upside
    // is 0.8% and down side is something like 2.7%" -> "Show upside/
    // downside % always, not just when fired."
    const spxGauge = (r.fired || []).concat(r.quiet || []).find(g => g.key === 'spx_top_range_warning');
    const spxRangeHtml = spxGauge ? `<div class="rd-spx-range">${escapeHtml(spxGauge.detail || '')}</div>` : '';
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
      ${spxRangeHtml}
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
    // TASK_140 follow-up 9 -- warn severity sorts before info (severe stays
    // first -- it's the most urgent tier, the user's ask only distinguished
    // warn vs info). Stable sort: same-severity events keep the API's own
    // order (event_seq).
    const _sevRank = { severe: 0, warn: 1, info: 2 };
    const events = (r.events || []).slice().sort((a, b) =>
      (_sevRank[a.severity || 'info'] ?? 2) - (_sevRank[b.severity || 'info'] ?? 2));
    body.innerHTML = events.map(ev => `
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
// TASK_140 follow-up 11 -- the hover previously used a plain-text `title`
// attribute built from f.ticker/f.category, but /api/quad/band-factors'
// bull/bear items only ever carry a `factor` field (confirmed live) -- both
// were always undefined, so the tooltip showed the "Bull factors:"/"Bear
// factors:" labels with nothing after them. Fixed to read f.factor, and
// upgraded from the native title tooltip to the shared #tip popover
// (already used by the composition charts) with colored Bull/Bear
// sections, closer to actionable.js's richer popover without duplicating
// its full click-positioned table (still a documented simplification,
// see DEV_HANDOFF.md -- actionable.js itself stays untouched).

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

// 2026-08-08 -- per-quad bull/bear factor lists, filtered from band-factors'
// `factors` array (its quad1..quad4 columns are period-independent raw
// stance per factor -- see api/routers/health.py::get_quad_band_factors'
// own docstring: "lets callers like the regime band's window-mix popover
// look up bull/bear factors for ANY quad number directly, not just the cur/
// next month|qtr periods" -- this was already built for exactly this, just
// never wired up on the frontend until now). User: "they should have bull/
// bear factors tooltip for corresponding quad ... currently is displaying
// only left side tooltip for every quad".
function _bullBearForQuadNum(allFactors, quadNum) {
  const col = 'quad' + quadNum;
  const bull = [], bear = [];
  (allFactors || []).forEach(f => {
    const v = (f[col] || '').trim().toLowerCase();
    if (v === 'bullish') bull.push({ factor: f.factor });
    else if (v === 'bearish') bear.push({ factor: f.factor });
  });
  return { bull, bear };
}

// "2026-08" -> "Aug", for the Regime line's compact month labels.
const _REGIME_MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function _regimeMonAbbr(ym) {
  const parts = String(ym).split('-');
  if (parts.length !== 2) return ym;
  const idx = parseInt(parts[1], 10) - 1;
  return _REGIME_MONTH_ABBR[idx] || ym;
}

async function loadRegimeBand() {
  const strip = $('regimeStrip');
  if (!strip) return;
  try {
    const viewingLive = !state.date || state.date === state.anchorDate;
    const qs = viewingLive ? '' : _dateQS();
    const [windowData, factors] = await Promise.all([
      fetchJson(`/api/quad-window${qs}`).catch(() => null),
      fetchJson(`/api/quad/band-factors${qs}`).catch(() => ({ bull: [], bear: [], factors: [] })),
    ]);
    if (!windowData) { strip.innerHTML = '<div class="ev-fail">&#9888; Regime data unavailable.</div>'; return; }
    const dominant = windowData.dominant_quad != null ? `Quad ${windowData.dominant_quad}` : '—';
    const allFactors = factors.factors || [];
    // 2026-08-08 -- compact format per user request: "60d Win(Q1). Aug(Q3)
    // 40% . Sep(Q1)50% . Oct(Q2)10%   Qtr(Q2)" -- replaces the old
    // "Window (60d): Quad 1 — 08 (Q3) 40% · 09 (Q1) 50% ..." wording.
    // 2026-08-08 -- single space before every "(" (Win (Q1), Aug (Q3),
    // Qtr (Q2)); % text shrunk to 9px (was inheriting the line's 13px) --
    // both per user request.
    // 2026-08-14 -- space between the quad span and the % dropped (was
    // "(Q3) 40%", now "(Q3)40%") -- user: "remove spaces between ->) and
    // percentage numbers."
    const months = (windowData.months || [])
      .map((m, i) => `<span class="month-entry" data-month-idx="${i}">${_regimeMonAbbr(m.m)} `
        + `<span style="color:${_quadColor('Q' + (m.quad ?? '?'))};font-weight:600;">(Q${m.quad ?? '?'})</span>`
        + `<span style="font-size:9px;">${Math.round((m.w || 0) * 100)}%</span></span>`)
      .join(' . ');
    // Qtr/Next-Qtr entry -- right-justified to the card's own right edge
    // (not just trailing inline after the months) via .regime-line's flex
    // layout below. User request: "right justify quarter quad to the grid".
    // 2026-08-09 -- Next Qtr added, same format as Qtr, right after it.
    // User: "Regime text -> display next quarter and quad in existing
    // fashion".
    // 2026-08-14 -- "Next" shortened to "N"; BOTH pieces now built as ONE
    // combined <span class="qtr-entry"> (was two separate .qtr-entry flex
    // children) so the "." between them sits glued tight with zero space on
    // either side -- as two separate flex children, .regime-line's own
    // gap:10px inserted space between "Qtr (Q4)" and ".N (Q2)" regardless of
    // what whitespace was/wasn't in the string itself. User: "remove spaces
    // between ... Qtr (Q4) and ., also remove ." (the space after it, before
    // N) -- desired final shape "Qtr(Q4).N(Q2)" with the "Qtr "/"N " labels'
    // own internal space kept (only the space AROUND the "." is gone).
    const qtrPart = windowData.qtr_quad != null
      ? `<span class="qtr-cur-part">Qtr <span style="color:${_quadColor('Q' + windowData.qtr_quad)};font-weight:600;">(Q${windowData.qtr_quad})</span></span>`
      : '';
    const nextQtrPart = windowData.next_qtr_quad != null
      ? `<span class="qtr-next-part">N <span style="color:${_quadColor('Q' + windowData.next_qtr_quad)};font-weight:600;">(Q${windowData.next_qtr_quad})</span></span>`
      : '';
    const qtrEntry = (qtrPart || nextQtrPart)
      ? `<span class="qtr-entry">${qtrPart}${qtrPart && nextQtrPart ? '.' : ''}${nextQtrPart}</span>`
      : '';
    // TASK_140 follow-up 11 -- band-factors items only ever carry `factor`
    // (verified live: {"factor":"Cyclical","qtr":"bull"}), not ticker/
    // category -- those were always undefined, which is why the tooltip
    // showed the "Bull factors:"/"Bear factors:" labels with nothing after.
    const bullFactors = (factors.bull || []).filter(f => f.factor);
    const bearFactors = (factors.bear || []).filter(f => f.factor);
    // 2026-08-08 -- split into 3 flex zones per user request: "remove the .
    // after 60d Win(Q1) and left align that text to the grid. monthly
    // quads -> align to center". Win-label pinned left (flex:0 0 auto),
    // months centered in the remaining middle space (flex:1, text-align:
    // center), Qtr pinned right (unchanged) -- was previously one big
    // left-flowing blob with the months embedded right after the label.
    // 2026-08-09 -- "Win" text dropped per user: "remove the text 'Win'".
    const winLabel = `<span class="regime-win-label">${windowData.h ?? 60}d (<strong style="color:${_quadColor(dominant)};">Q${windowData.dominant_quad ?? '?'}</strong>)</span>`;
    strip.innerHTML = `<div class="regime-line" data-quadbandpop="1">
      ${winLabel}<span class="regime-window-text">${months || 'no window data'}</span>${qtrEntry}
    </div>`;
    const line = strip.querySelector('.regime-line');
    if (line) {
      // Line-level fallback: hovering the "Window (60d): Quad X" summary
      // text itself (not inside a specific month/Qtr entry) still shows the
      // blended dominant-quad's factors.
      line.addEventListener('mouseover', () => _showQuadPop(line, dominant, bullFactors, bearFactors));
      line.addEventListener('mouseout', e => {
        if (e.relatedTarget && e.relatedTarget.closest('.regime-line')) return;
        _hideQuadPop();
      });
      // Each month entry shows Bull/Bear factors for ITS OWN quad (not the
      // blended dominant one) -- stopPropagation so the line-level listener
      // above doesn't override it with the generic version.
      line.querySelectorAll('.month-entry').forEach(el => {
        const idx = Number(el.dataset.monthIdx);
        const mo = (windowData.months || [])[idx];
        if (!mo || mo.quad == null) return;
        const { bull, bear } = _bullBearForQuadNum(allFactors, mo.quad);
        el.addEventListener('mouseover', e => {
          e.stopPropagation();
          _showQuadPop(el, `${String(mo.m).slice(5)} — Quad ${mo.quad}`, bull, bear);
        });
      });
      // Qtr entry -- same treatment, using the current quarter's own quad.
      // 2026-08-14 -- selector updated: qtrPart/nextQtrPart are now two
      // inner sub-spans of ONE .qtr-entry (was two separate .qtr-entry
      // flex children) -- see qtrEntry's own comment above for why.
      const qtrEl = line.querySelector('.qtr-cur-part');
      if (qtrEl && windowData.qtr_quad != null) {
        const { bull, bear } = _bullBearForQuadNum(allFactors, windowData.qtr_quad);
        qtrEl.addEventListener('mouseover', e => {
          e.stopPropagation();
          _showQuadPop(qtrEl, `${windowData.qtr_label || 'Qtr'} — Quad ${windowData.qtr_quad}`, bull, bear);
        });
      }
      // Next Qtr entry -- same treatment, using the upcoming quarter's quad.
      const nextQtrEl = line.querySelector('.qtr-next-part');
      if (nextQtrEl && windowData.next_qtr_quad != null) {
        const { bull, bear } = _bullBearForQuadNum(allFactors, windowData.next_qtr_quad);
        nextQtrEl.addEventListener('mouseover', e => {
          e.stopPropagation();
          _showQuadPop(nextQtrEl, `${windowData.next_qtr_label || 'Next'} — Quad ${windowData.next_qtr_quad}`, bull, bear);
        });
      }
    }
  } catch (e) {
    console.error('regime band failed:', e);
    strip.innerHTML = '<div class="ev-fail">&#9888; Regime data unavailable.</div>';
  }
}

// TASK_140 follow-up 18 -- replicates actionable.js's #sourcePop quad-band
// popover exactly (same _buildQuadBandPopHtml table shape: sp-title + per-
// factor rows under "↑ Bull Factors"/"↓ Bear Factors" section headers, same
// element-anchored positioning with viewport clamping as its _showDataPop),
// targeting the dashboard's own #quadPop element/.source-pop CSS (added to
// styles.css) since actionable.js/.html stay untouched -- see that file's
// _showDataPop/hideSourcePop/_buildQuadBandPopHtml for the original.
// Shared element-anchored positioning for #quadPop (viewport-clamped: flips
// above if it'd overflow the bottom, clamps left if it'd overflow the
// right) -- used by both the regime-line popover and the per-category
// quad-stance popover below.
function _positionQuadPop(el, pop) {
  const rect = el.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - pop.offsetHeight - 4);
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
}
function _showQuadPop(el, quadLabel, bullFactors, bearFactors) {
  const pop = $('quadPop');
  if (!pop) return;
  let h = `<div class="sp-title" style="color:${_quadColor(quadLabel)}">${escapeHtml(quadLabel)}</div>`;
  h += '<table>';
  if (bullFactors.length) {
    h += `<tr><td class="sp-sec" colspan="2" style="color:#1c6c30;">&#8593; Bull Factors</td></tr>`;
    for (const f of bullFactors) {
      h += `<tr><td class="k">${escapeHtml(f.factor)}</td><td class="v" style="color:#1c6c30;font-weight:600;font-size:10px;">Bullish</td></tr>`;
    }
  }
  if (bearFactors.length) {
    h += `<tr><td class="sp-sec" colspan="2" style="color:#8c1d1d;">&#8595; Bear Factors</td></tr>`;
    for (const f of bearFactors) {
      h += `<tr><td class="k">${escapeHtml(f.factor)}</td><td class="v" style="color:#8c1d1d;font-weight:600;font-size:10px;">Bearish</td></tr>`;
    }
  }
  if (!bullFactors.length && !bearFactors.length) {
    h += `<tr><td class="k" colspan="2" style="color:#9ca3af;">No factor data</td></tr>`;
  }
  h += '</table>';
  pop.innerHTML = h;
  pop.style.display = 'block';
  _positionQuadPop(el, pop);
}
function _hideQuadPop() {
  const pop = $('quadPop');
  if (pop) pop.style.display = 'none';
}

// 2026-08-07 -- per-category quad-stance popover for the Sector/Asset-class/
// Style scorecard cards ("which factor is going to do well based on the
// quads"). stanceRow comes from GET /api/quad/factor-stance -- carries this
// category's OWN per-window-period stance (stanceRow.months, matching the
// carets rendered inline) plus the blended score and raw quad1-4 outlook.
// windowData is that same response's top-level fields (h, etc).
function _showCategoryQuadPop(el, stanceRow, windowData) {
  const pop = $('quadPop');
  if (!pop || !stanceRow) return;
  const v = Number(stanceRow.score) || 0;
  const col = v > 0 ? '#1c6c30' : v < 0 ? '#8c1d1d' : '#6b7280';
  let h = `<div class="sp-title" style="color:${col}">${escapeHtml(stanceRow.category)} — ${escapeHtml(stanceRow.stance)}</div>`;
  h += '<table>';
  // 2026-08-07 -- main row = the blended 60D score (the bold caret shown
  // inline, same number driving the Verdict column), then one row per
  // window period (the smaller carets after the gap) -- this category's OWN
  // stance per period, not the generic market-wide window mix. Matches
  // "i need to see carets for all of these periods... that [60D] is the
  // main one, leave a gap between this and others".
  h += `<tr><td class="k" style="font-weight:700;">60D window (blended)</td><td class="v" style="color:${col};font-weight:700;font-size:10px;">${escapeHtml(stanceRow.stance)}</td></tr>`;
  h += `<tr><td class="sp-sec" colspan="2">By period</td></tr>`;
  (stanceRow.months || []).forEach(mo => {
    const mv = Number(mo.stance) || 0;
    const c = mv > 0 ? '#1c6c30' : mv < 0 ? '#8c1d1d' : '#6b7280';
    const lbl = `${escapeHtml(String(mo.m).slice(5))} (Q${mo.quad ?? '?'}) ${Math.round((mo.w || 0) * 100)}%`;
    const label = mv > 0 ? 'Bullish' : mv < 0 ? 'Bearish' : 'Neutral';
    h += `<tr><td class="k">${lbl}</td><td class="v" style="color:${c};font-weight:600;font-size:10px;">${label}</td></tr>`;
  });
  if (!stanceRow.months || !stanceRow.months.length) {
    h += `<tr><td class="k" colspan="2" style="color:#9ca3af;">No window data</td></tr>`;
  }
  // 2026-08-08 -- Quarter row (the small 5%-weighted one-hot anchor blended
  // into macronet, matching the new Quarter caret shown inline) -- user
  // request: "Popups don't have quarter quad info".
  h += `<tr><td class="sp-sec" colspan="2">Quarter (min wt)</td></tr>`;
  if (stanceRow.qtr && stanceRow.qtr.stance != null) {
    const qv = Number(stanceRow.qtr.stance) || 0;
    const qc = qv > 0 ? '#1c6c30' : qv < 0 ? '#8c1d1d' : '#6b7280';
    const qLbl = qv > 0 ? 'Bullish' : qv < 0 ? 'Bearish' : 'Neutral';
    h += `<tr><td class="k">${escapeHtml(stanceRow.qtr.quad || '—')}</td><td class="v" style="color:${qc};font-weight:600;font-size:10px;">${qLbl}</td></tr>`;
  } else {
    h += `<tr><td class="k" colspan="2" style="color:#9ca3af;">No quarterly data</td></tr>`;
  }
  h += `<tr><td class="sp-sec" colspan="2">By Quad (raw outlook)</td></tr>`;
  [1, 2, 3, 4].forEach(n => {
    const val = stanceRow[`quad${n}`];
    const c = /BULL/i.test(val || '') ? '#1c6c30' : /BEAR/i.test(val || '') ? '#8c1d1d' : '#6b7280';
    h += `<tr><td class="k">Quad ${n}</td><td class="v" style="color:${c};font-weight:600;font-size:10px;">${escapeHtml(val || '—')}</td></tr>`;
  });
  h += '</table>';
  pop.innerHTML = h;
  pop.style.display = 'block';
  _positionQuadPop(el, pop);
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
// TASK_140 follow-up 17 -- popover text per verdict, matching the
// (band x quad) matrix + overrides in etl/derive_category_perf.py::_verdict
// exactly (under/at/over target-allocation x bullish/neutral/bearish quad
// stance, plus the ROTATE and risk_budget<55-caps-to-HOLD overrides).
const _VERDICT_DESC = {
  ADD: 'Under-allocated here and the quad regime is bullish for it — add exposure.',
  WATCH: 'Under-allocated here but the regime is neutral — worth watching, not a clear add yet.',
  AVOID: 'Under-allocated here and the regime is bearish — the gap is deliberate, don’t add.',
  HOLD: 'At target allocation (or ADD/PRESS capped here because the Risk Dial budget is below 55) — no allocation-based action.',
  PRESS: 'At target and bullish, with a positive 1-month trailing return — lean in rather than just hold.',
  TRIM: 'At or over target and the regime has turned bearish (or neutral while over) — trim back.',
  HOLD_NO_ADD: 'Over-allocated but the regime is still bullish — hold what you have, don’t add more.',
  TRIM_HARD: 'Over-allocated and the regime is bearish — trim aggressively.',
  ROTATE: 'Would otherwise be ADD, but trailing the benchmark in most windows — rotate into something else instead.',
};
function _verdictBadge(verdict) {
  if (!verdict) return '';
  const cls = _VERDICT_CLS[verdict] || 'act-neutral';
  const desc = _VERDICT_DESC[verdict] || '';
  return `<span class="fs-verdict ${cls}-tint" title="${escapeHtml(desc)}">${escapeHtml(verdict)}</span>`;
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

// 2026-08-10 -- last param generalized from `axis` (implicitly always
// openFactorExposureModal, the $/holdings popup) to `onClick(category)` so
// Market View's chart slices/bars can wire to openMarketViewDetailModal
// instead -- same "pie/bar chart clicks should match the table row clicks"
// behavior, just a different popup per caller. Pass null/undefined for no
// click-through (unchanged default). User: "graph clicks for bottom 3
// graphs are not working" -- Market View passed a hardcoded `null` here
// (from when its charts pointed at the $ modal, which didn't apply), which
// disabled clicks entirely instead of pointing at the new modal.
// 2026-08-14 -- briefly gained a `fillGap` param (a gray "Cash" gap-filler
// slice for Sector, whose rows don't sum to 100 since cash isn't
// sector-classified) so this pie's % matched the factor-scorecard table's
// WT% column (which divides by the whole portfolio, cash included) --
// reverted same day. User, after seeing it live: "top sector included the
// cash, which it should not." This pie's % is deliberately "% of the
// visible categories shown here", not "% of whole portfolio" -- won't
// equal the table's WT% number, by design (same reasoning as the
// Portfolio Mix panel's own Sector pie, web/portfolio_mix.js).
function _renderCatPie(svgId, rows, unmapped, colorMap, onClick) {
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
    // Same popup as clicking the matching table row (TASK_139 -- user
    // request: "pie chart clicks should display the same popups for
    // corresponding pies").
    if (onClick) {
      hit.style.cursor = 'pointer';
      hit.addEventListener('click', () => onClick(d.category));
    }
    svg.appendChild(hit);
    a0 = a1;
  });
}

// 2026-08-10 -- mine-vs-market Returns column, one per row in each of the 3
// column-2 grids' own table -- user: "remove the newly added bar charts and
// add them as a column to the grid as they corresponds to each row anyways
// (ex: 'Financials')." Was a separate SVG chart beside the table (2026-08-10
// earlier pass); moved into the table itself as the LAST <td> per row since
// each bar IS that row's own mine-vs-market return, no separate chart
// needed to cross-reference against the row. Two diverging (zero-centered,
// sign-colored) mini-bars per cell -- mine at full opacity, market at 0.55
// (same "secondary/deemphasized" convention as .gm-row-closed elsewhere) --
// via _fsReturnsBarCell(), called from loadFactorScorecard()'s own row-
// building loop below. Selecting a different period (#catReturnsPeriod,
// now on the Accounts filter bar -- "add radio buttons on to the filter
// bar") just re-runs reloadFactorScorecards() so this column's numbers
// (already fetched in every row, twr_*/bench_*) reflect it -- no separate
// cache/re-render path needed the way the old standalone chart required.
function _selectedCatReturnsPeriod() {
  const el = document.querySelector('#catReturnsPeriod input[name="catReturnsPeriod"]:checked');
  return el ? el.value : 'mtd';
}

function _initCatReturnsPeriod() {
  const wrap = $('catReturnsPeriod');
  if (!wrap) return;
  wrap.querySelectorAll('input[name="catReturnsPeriod"]').forEach(r => {
    // 2026-08-10 -- also reloads Market View's own 3 grids (bottom three)
    // now that they carry a Returns column too -- user: "add the Returns
    // columns to bottom three grids also."
    r.addEventListener('change', () => { reloadFactorScorecards(); reloadMarketView(); });
  });
}

// 2026-08-10 -- $ amount (mine) added above the bars -- user: "add
// $amount (mine) to Returns columns. be creative so i can see the
// numbers." Not a fetched field (the API only has %twr per period, no
// $-per-period) -- approximated as market_value * (mine% / 100), the same
// "translate a % into its $ size" approximation _renderCatReturnsBars'
// predecessor and the rest of this app already lean on elsewhere (e.g.
// _catReturnsCache's old total-gain math). Compact K/M so it fits the
// column at a glance without hover; the exact-to-the-cent Cumulative $
// figure already lives in the Wt% cell for anyone who needs it. Market
// View passes null (no holdings, nothing to show in $).
function _fsCompactUsd(v) {
  if (v == null) return null;
  const abs = Math.abs(v);
  const sign = v >= 0 ? '+' : '-';
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${Math.round(abs)}`;
}

// max: the shared per-table scale (max |mine|/|market| across every row for
// this period) so bar lengths are comparable row-to-row, computed once by
// the caller before building rows. mineDollar: mine's approximate $ impact
// at this period (see _fsCompactUsd above) -- null on Market View (no
// holdings).
function _fsReturnsBarCell(mine, mkt, max, mineDollar) {
  const bar = (v, cls) => {
    if (v == null) return '';
    const pct = Math.min(45, Math.abs(v) / max * 45).toFixed(1);
    const side = v >= 0 ? `left:50%;` : `right:50%;`;
    const sign = v >= 0 ? 'pos' : 'neg';
    return `<div class="fs-ret-bar ${cls} ${sign}" style="${side}width:${pct}%;"></div>`;
  };
  // 2026-08-11 bugfix -- v is a raw FRACTION (twr_*/bench_*), same unit
  // issue as rowMineDollar above -- needs *100 to read as a percentage,
  // matching _fsColorCell's own `Number(v) * 100`. Bar widths (above) were
  // unaffected -- v and max are both unscaled consistently, so their ratio
  // was always right; only this tooltip text was showing ~100x-too-small
  // numbers.
  const fmt = v => v != null ? `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%` : '—';
  const dollarText = _fsCompactUsd(mineDollar);
  // 2026-08-10 follow-up -- $ label moved BESIDE the bars (flex row) instead
  // of stacked above them -- stacking added a 2nd text line inside the
  // cell, and table rows size to their tallest cell, so it was silently
  // growing every row's height table-wide. User: "why the height of the
  // row increased?" Beside it, the cell's total height is unchanged (still
  // just .fs-ret-plot's 16px) -- the widened Returns column (18% -> 24%,
  // same pass) is exactly what makes room for it here instead.
  const dollarHtml = dollarText
    ? `<div class="fs-ret-dollar ${mineDollar >= 0 ? 'pos' : 'neg'}">${dollarText}</div>` : '';
  return `<td class="fs-returns-cell" title="Mine: ${fmt(mine)}${mineDollar != null ? ' (' + dollarText + ' approx.)' : ''} / Market: ${fmt(mkt)}">
    <div class="fs-ret-wrap">
      <div class="fs-ret-plot">
        <div class="fs-ret-mid"></div>
        ${bar(mine, 'fs-ret-mine')}
        ${bar(mkt, 'fs-ret-mkt')}
      </div>
      ${dollarHtml}
    </div>
  </td>`;
}

function _renderCatBars(svgId, rows, unmapped, colorMap, onClick) {
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
    // Same popup as clicking the matching table row.
    if (onClick) {
      hit.style.cursor = 'pointer';
      hit.addEventListener('click', () => onClick(d.category));
    }
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
// 2026-08-08 -- swapped the 1w/3w/1m/2m/3m fixed-trading-day columns for
// MTD/QTD/YTD calendar-boundary columns (etl/derive_category_perf.py::
// _window_days_since) per user request. twr_1w..twr_3m are still computed
// server-side (drv_category_perf keeps them, _verdict()'s PRESS/ROTATE
// logic still reads twr_1m/WINDOWS) -- only the display list changed.
const _FS_WINDOWS = [
  { key: 'today', label: 'Today', full: 'today (1 day)' },
  { key: 'yesterday', label: 'Yesterday', full: 'yesterday (the single prior trading day, not a 2-day window)' },
  { key: 'mtd', label: 'MTD', full: 'month-to-date (first trading day of this month through today)' },
  { key: 'qtd', label: 'QTD', full: 'quarter-to-date (first trading day of this quarter through today)' },
  { key: 'ytd', label: 'YTD', full: 'year-to-date (first trading day of this year through today)' },
];

// 2026-08-09 -- fixed width reserved for the category cell's caret cluster
// (main + up to 3 period carets + qtr + next-qtr, each a fixed-width glyph
// span per the neutral-alignment fix), so the category TEXT always starts
// at the same x regardless of row content, AND the Unmapped note's own
// "Unmapped" label (rendered outside the table, see loadFactorScorecard's
// `unmapped` var) can line up with it exactly by using the same number.
// Kept in sync BY HAND -- there's no single shared DOM element both read
// from, since the note lives in a sibling div, not a table cell. Recompute
// if the caret cluster's own glyph count/widths change:
//   main(11) + gap(6) + periods(3x: 9+1+9+1+9=29) + gap(6) + qtr(11) +
//   next-qtr(9) = 72, + .cat-quad-stance's own margin-right(5) = 77 --
// left at 81 (4px of harmless slack; a reservation only needs to be >=
// the actual content, not exact) after two 2026-08-10 size trims: periods
// went 31->29 ("make first month caret same size as other months" -- the
// current-month caret no longer matches the main caret's larger/bold
// size), then next-qtr went 11->9 ("make next quarter smaller" -- now
// matches the period carets' smaller size instead of the current-quarter
// caret's larger one).
// User: "alignment should skip two more carets" -- the qtr/next-qtr carets
// were added after the original 56px reservation was sized, and the
// wrapper span's old `min-width` (not `width`) let it silently grow past
// that reservation instead of erroring, so misalignment crept in unnoticed.
const _CARET_CLUSTER_PX = 81;

// 2026-08-10 -- quad-stance caret CLUSTER (main 60D-blend + one caret per
// window period + current-quarter + next-quarter), extracted out of
// loadFactorScorecard so the Market View cards (loadMarketView) can render
// the identical cluster instead of the single flat caret they used to fall
// back to -- user: "bottom three graph should look like the top except
// dollar as accounts/holdings are not applicable." stanceRow is a row from
// GET /api/quad/factor-stance (category/score/stance/months/qtr/next_qtr);
// months/qtr/next_qtr are simply absent for the Market View Source filter's
// point-in-time sources (SSS/PS/etc -- see _quad_factor_stance_by_source),
// so this degrades gracefully to just the main caret in that case.
function _quadCaretCluster(stanceRow, curQtrOp, nextQtrOp) {
  if (!stanceRow) return '';
  const mv = Number(stanceRow.score) || 0;
  const mCol = mv > 0 ? '#16a34a' : mv < 0 ? '#dc2626' : '#9ca3af';
  const mGlyph = mv > 0 ? '&#9650;' : mv < 0 ? '&#9660;' : '&#8211;';
  // every glyph span below (main/period/qtr/next-qtr) gets a fixed inline-
  // block width + text-align:center -- the neutral glyph (&#8211; en-dash)
  // is much narrower than the bullish/bearish triangles (&#9650;/&#9660;)
  // at the same font-size, so an un-fixed-width span shifted everything
  // after it left whenever a row's carets included a neutral read.
  const mainCaret = `<span style="color:${mCol};font-size:11px;font-weight:700;display:inline-block;width:11px;text-align:center;">${mGlyph}</span>`;
  // 2026-08-10 -- all period carets (current month + later-in-window ones)
  // same size now -- the current-month caret used to match the main 60D
  // caret's larger bold size to stand out; user: "everywhere make first
  // month caret same size as other months" (applies globally -- this is
  // the one shared function both the top 3 $ grids and Market View render
  // from).
  const periodCarets = (stanceRow.months || []).map(mo => {
    const v = Number(mo.stance) || 0;
    const sCol = v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
    const glyph = v > 0 ? '&#9650;' : v < 0 ? '&#9660;' : '&#8211;';
    return `<span style="color:${sCol};width:9px;display:inline-block;text-align:center;">${glyph}</span>`;
  }).join('<span style="display:inline-block;width:1px;"></span>');
  const gap = `<span style="display:inline-block;width:6px;"></span>`;
  const qtrCaret = (stanceRow.qtr && stanceRow.qtr.stance != null) ? (() => {
    const qv = Number(stanceRow.qtr.stance) || 0;
    const qCol = qv > 0 ? '#16a34a' : qv < 0 ? '#dc2626' : '#9ca3af';
    const qGlyph = qv > 0 ? '&#9650;' : qv < 0 ? '&#9660;' : '&#8211;';
    return `<span style="color:${qCol};opacity:${curQtrOp};font-size:11px;font-weight:700;display:inline-block;width:11px;text-align:center;" title="${escapeHtml(stanceRow.qtr.quad || '')} (current quarter)">${qGlyph}</span>`;
  })() : '';
  // 2026-08-10 -- smaller than the current-quarter caret (9px, not bold --
  // same size as the period carets) so current vs. next quarter reads as
  // primary vs. secondary, matching the main-caret/period-caret size
  // convention already used elsewhere in this cluster. User: "make next
  // quarter smaller."
  const nextQtrCaret = (stanceRow.next_qtr && stanceRow.next_qtr.stance != null) ? (() => {
    const nv = Number(stanceRow.next_qtr.stance) || 0;
    const nCol = nv > 0 ? '#16a34a' : nv < 0 ? '#dc2626' : '#9ca3af';
    const nGlyph = nv > 0 ? '&#9650;' : nv < 0 ? '&#9660;' : '&#8211;';
    return `<span style="color:${nCol};opacity:${nextQtrOp};width:9px;display:inline-block;text-align:center;" title="${escapeHtml(stanceRow.next_qtr.quad || '')} (next quarter)">${nGlyph}</span>`;
  })() : '';
  // title="" breaks inheritance from the row's own title tooltip -- without
  // it, hovering a caret showed both the native browser tooltip and the
  // custom #quadPop popover at once, overlapping.
  return `<span class="cat-quad-stance" title="" style="cursor:help;margin-right:5px;font-size:9px;letter-spacing:1px;">${mainCaret}${gap}${periodCarets}${gap}${qtrCaret}${nextQtrCaret}</span>`;
}

// Current/next-quarter caret cross-fade opacities (extracted alongside
// _quadCaretCluster for the same reuse reason). Outside the last 15 days of
// the current quarter, the current-quarter caret is full color and the
// next-quarter caret sits at a fixed light/faded baseline; INSIDE that
// window they linearly cross-fade toward the opposite state as
// days_to_qtr_end counts down to 0.
function _qtrFadeOpacities(daysToQtrEnd) {
  const QTR_FADE_DAYS = 15, QTR_LIGHT_OP = 0.35;
  const qtrFadeT = (daysToQtrEnd != null && daysToQtrEnd <= QTR_FADE_DAYS)
    ? Math.max(0, Math.min(1, (QTR_FADE_DAYS - daysToQtrEnd) / QTR_FADE_DAYS)) : 0;
  return [1 - qtrFadeT * (1 - QTR_LIGHT_OP), QTR_LIGHT_OP + qtrFadeT * (1 - QTR_LIGHT_OP)];
}

async function loadFactorScorecard(axis, bodyId, chartId) {
  const body = $(bodyId);
  if (!body) return;
  try {
    const params = new URLSearchParams({ axis });
    if (state.date) params.set('date', state.date);
    // 2026-08-09 -- Accounts filter param goes on the $/Wt%/TWR endpoint
    // only -- /api/quad/factor-stance's quad stance is a per-symbol market
    // read (which quad favors which sector), the same regardless of which
    // account holds a position, so it never needs an accounts filter.
    const scoreParams = new URLSearchParams(params);
    if (state.catAccounts.length) scoreParams.set('accounts', state.catAccounts.join(','));
    const [r, stanceData] = await Promise.all([
      fetchJson(`/api/cockpit/factor-scorecard?${scoreParams.toString()}`),
      fetchJson(`/api/quad/factor-stance?${params.toString()}`).catch(() => null),
    ]);
    // 2026-08-11 -- Unmapped folded into the same row list as every other
    // category (Financials/Equities/etc) instead of the special note-
    // styled line that used to render below the table -- user: "add
    // unmapped as a row just like Equities etc." Re-sorted by weight_pct
    // (same DESC NULLS LAST convention the backend's own ORDER BY uses for
    // r.rows) so it takes its natural place by size rather than always
    // trailing last. The dedicated chart renderers (_renderCatBars/
    // _renderCatPie below) still take r.rows/r.unmapped separately -- this
    // only changes the TABLE.
    const allRows = (r.rows || []).slice();
    if (r.unmapped) allRows.push(r.unmapped);
    allRows.sort((a, b) => {
      const aw = a.weight_pct, bw = b.weight_pct;
      if (aw == null && bw == null) return 0;
      if (aw == null) return 1;
      if (bw == null) return -1;
      return Number(bw) - Number(aw);
    });
    // 2026-08-10 -- "Overlapping tags -- not an allocation" note removed
    // for Style (both here and in Market View below) per user request.
    // TASK_140 follow-up 3 -- same color, category column swatch + chart
    // slice/bar. Computed once here from the same row order the table
    // below gets, so table and chart never disagree. ('Unmapped' is
    // skipped for color assignment either way, see _catColorMap.)
    const colorMap = _catColorMap(allRows);
    // 2026-08-07 -- category name -> quad-stance row, matched case/trim-
    // insensitively since ref_quad_outlook's own casing can differ from
    // drv_category_perf's (e.g. "Health care" vs "Health Care", same gotcha
    // as the earlier Sector exposure case-sensitivity fix).
    const stanceMap = new Map();
    (stanceData?.rows || []).forEach(sr => stanceMap.set(String(sr.category).trim().toLowerCase(), sr));
    // 2026-08-09 -- current/next-quarter caret cross-fade: outside the last
    // 15 days of the current quarter, the current-quarter caret is full
    // color and the next-quarter caret sits at a fixed light/faded
    // baseline; INSIDE that window, they linearly cross-fade toward the
    // opposite state as days_to_qtr_end counts down to 0, so the next
    // quarter's caret is at full color exactly at quarter-end. User:
    // "end of current quarter (15 days to end): fade the color to light
    // and the next quarter color: use the full color, until then fade the
    // next quad caret color."
    const [curQtrOp, nextQtrOp] = _qtrFadeOpacities(stanceData?.days_to_qtr_end);
    // 2026-08-10 -- Returns column (last <td> per row) -- period comes from
    // the shared #catReturnsPeriod radio group; retMax is the shared scale
    // across every row's mine/market value at that period, computed once
    // here so bar lengths are comparable row-to-row (a single row can't
    // sensibly self-scale). See _fsReturnsBarCell.
    const _retPeriod = _selectedCatReturnsPeriod();
    const _retMax = Math.max(1, ...allRows.flatMap(rr =>
      [rr[`twr_${_retPeriod}`], rr[`bench_${_retPeriod}`]].filter(v => v != null).map(Math.abs)));
    // 2026-08-10 -- Total row (bottom of table) -- user: "i need the totals
    // somewhere based on the period selected (overall gain or loss for
    // that period)." Accumulated alongside each row's own mineDollar (same
    // market_value * twr% approximation, summed here rather than
    // recomputed). Unmapped now participates like any other row (2026-08-
    // 11) -- its API row carries the same twr_*/bench_* fields as every
    // category (they were just being split out into r.unmapped by
    // api/routers/cockpit.py, not actually missing).
    let _retTotalDollar = 0, _retTotalMv = 0;
    const rows = allRows.map(row => {
      // 2026-08-09 -- row hover replaced with $ amounts instead of the
      // per-window you/mkt performance breakdown -- category $ value, the
      // equity-sleeve $ total it's a share of (same denominator behind
      // weight_pct_equities), and the whole-portfolio $ total (same
      // denominator behind weight_pct). Both totals are backed out from
      // market_value/weight_pct rather than fetched separately -- every
      // row already carries its own weight_pct(_equities) against the
      // same shared denominator, so this is exact, not an approximation.
      // User: "hover/popover/tooltip for category column -> instead of
      // displaying market and mine percentages, display amounts $ amount,
      // $ account total and $ total portfolio."
      // 2026-08-09 follow-up -- each line also shows the % it represents
      // ("next to them indicate % of total etc"): Amount gets both %s
      // that were removed (of equities / of portfolio, same weight_pct(_
      // equities) fields as the Wt% column); Equities total gets its own
      // % of the whole portfolio (how much of your book is equities at
      // all); Portfolio total is trivially 100%, shown for symmetry.
      const fmtTipUsd = (v) => v != null ? '$' + Math.round(v).toLocaleString() : '—';
      const fmtTipPct = (v) => v != null ? `${Number(v).toFixed(1)}%` : '—';
      const mv = row.market_value != null ? Number(row.market_value) : null;
      const totalEquityDollar = (mv != null && row.weight_pct_equities) ? mv / (Number(row.weight_pct_equities) / 100) : null;
      const totalPortfolioDollar = (mv != null && row.weight_pct) ? mv / (Number(row.weight_pct) / 100) : null;
      const equityOfPortfolioPct = (totalEquityDollar != null && totalPortfolioDollar)
        ? totalEquityDollar / totalPortfolioDollar * 100 : null;
      const amountPct = row.weight_pct_equities != null
        ? `${fmtTipPct(row.weight_pct_equities)} of equities / ${fmtTipPct(row.weight_pct)} of portfolio`
        : `${fmtTipPct(row.weight_pct)} of portfolio`;
      const titleParts = [
        `Amount: ${fmtTipUsd(mv)} (${amountPct})`,
        totalEquityDollar != null
          ? `Equities total: ${fmtTipUsd(totalEquityDollar)} (${fmtTipPct(equityOfPortfolioPct)} of portfolio)` : null,
        `Portfolio total: ${fmtTipUsd(totalPortfolioDollar)} (100%)`,
      ].filter(Boolean).join('\n');
      // 2026-08-08 -- show BOTH "mine" (twr) and "not mine" (bench/mkt)
      // per user request, instead of just the twr-bench delta -- the delta
      // alone was misreadable when twr is 0 (currently the case here from
      // the stale-transaction-feed gap-guard, see loadTxnFeedGaps): a
      // genuinely-positive benchmark could still show as a negative red
      // delta with no visibility into WHY. Primary = your return (bold);
      // secondary = market/benchmark return (smaller, own sign color).
      const cells = _FS_WINDOWS.map(w => {
        const twr = row[`twr_${w.key}`], bench = row[`bench_${w.key}`];
        const you = _fsColorCell(twr) || '<span class="fs-dash">—</span>';
        const mkt = bench != null ? `<span class="fs-bench-cell">/ ${_fsColorCell(bench)}</span>` : '';
        return `<td>${you}${mkt}</td>`;
      }).join('');
      const weightPct = row.weight_pct != null ? Number(row.weight_pct) : null;
      // 2026-08-07 -- quad-stance carets: the MAIN caret is the blended 60D
      // window score (the same number driving the Verdict column), then a
      // gap, then one caret per window period so each period's own read is
      // also visible -- e.g. "▲  ▲ ▲ ▲" for 60D-blend / 08(Q3) / 09(Q1) /
      // 10(Q2). Matches the per-period breakdown already shown in the
      // Regime Band's "Window (60d): 08 (Q3) 42% · 09 (Q1) 50% · 10 (Q2) 8%"
      // line. See _showCategoryQuadPop for the full table on hover.
      const catKey = String(row.category).trim().toLowerCase();
      const stanceRow = stanceMap.get(catKey);
      const stanceIcon = _quadCaretCluster(stanceRow, curQtrOp, nextQtrOp);
      // TASK_139 -- row click opens the same exposure-detail modal as the
      // Risk Dial's fired gauges (Screen D of the design doc), keyed by
      // (axis, category) instead of gauge_key.
      return `<tr title="${escapeHtml(titleParts)}" class="fs-clickable" data-cat="${escapeHtml(catKey)}"
                   onclick="openFactorExposureModal('${escapeHtml(axis)}', '${escapeHtml(row.category).replace(/'/g, "\\'")}')">
        <td><span style="display:inline-block;width:${_CARET_CLUSTER_PX}px;">${stanceIcon}</span>${escapeHtml(row.category)}</td>
        <td class="fs-weight-cell" title="${escapeHtml(
            row.weight_pct_equities != null
              ? 'Weight — % of your EQUITIES only (bold) / % of your TOTAL portfolio incl. cash+bonds+etc (small)'
              : 'Weight — % of your total portfolio'
          )}">
          ${(() => {
            // 2026-08-08 -- equity% is primary (bar + bold figure) for
            // sector/style, since that's how sector/style allocation is
            // normally read; total-portfolio% (the old primary) drops to a
            // muted secondary line. asset_class has no weight_pct_equities
            // (not applicable -- that axis IS the total-portfolio view) so
            // it keeps total% as primary, unchanged. The <td>'s own title
            // (above) breaks inheritance from the <tr>'s twr/bench tooltip,
            // which was otherwise leaking through here -- same
            // title-inheritance issue as the caret-cluster overlap fix.
            const primary = row.weight_pct_equities != null ? Number(row.weight_pct_equities) : weightPct;
            const bar = primary != null ? `<span class="fs-weight-bar" style="width:${Math.max(0, Math.min(100, primary))}%"></span>` : '';
            const text = primary != null ? `<span class="fs-weight-text">${primary.toFixed(1)}%</span>` : '';
            const secondary = (row.weight_pct_equities != null && weightPct != null)
              ? `<span class="fs-weight-eq">/ ${weightPct.toFixed(1)}%</span>` : '';
            // 2026-08-10 -- $ amount now shown inline (was hover-tooltip
            // only, see the tooltip block above this row) -- user: "display
            // amounts where ever is applicable in the dashboard grids."
            const dollar = mv != null ? `<span class="fs-weight-eq">(${fmtTipUsd(mv)})</span>` : '';
            return bar + text + secondary + dollar;
          })()}
        </td>
        ${cells}
        ${(() => {
          const rowMine = row[`twr_${_retPeriod}`];
          // 2026-08-11 bugfix -- twr_* is stored as a raw FRACTION (e.g.
          // -0.0042 = -0.42%), not a percentage number -- confirmed against
          // _fsColorCell's own `Number(v) * 100` when formatting the %
          // TEXT. This $ approximation used to divide by 100 too (as if
          // twr were already a percentage), making every $ figure in this
          // column ~100x too small ever since it was added. User: "isn't
          // totals in all grids should be matched? ... check the numbers,
          // they are not correct."
          const rowMineDollar = (mv != null && rowMine != null) ? mv * rowMine : null;
          if (rowMineDollar != null) { _retTotalDollar += rowMineDollar; _retTotalMv += mv; }
          return _fsReturnsBarCell(rowMine, row[`bench_${_retPeriod}`], _retMax, rowMineDollar);
        })()}
      </tr>`;
    }).join('');
    // 2026-08-10 -- Total row -- see _retTotalDollar/_retTotalMv comment
    // above. Weighted-avg % approximated the same way each row's own %
    // already is (dollar / market-value-base), not a true dollar-weighted
    // TWR -- consistent with the rest of this column, not a new precision
    // claim.
    const retTotalPct = _retTotalMv ? (_retTotalDollar / _retTotalMv * 100) : null;
    const retTotalText = _fsCompactUsd(_retTotalDollar) || '$0';
    const retTotalRow = `<tr class="fs-total-row">
      <td>Total</td>
      <td class="fs-weight-cell"></td>
      ${_FS_WINDOWS.map(() => '<td class="fs-dash">—</td>').join('')}
      <td class="fs-returns-cell">
        <div class="fs-ret-total ${_retTotalDollar >= 0 ? 'pos' : 'neg'}">
          ${retTotalText}${retTotalPct != null ? ` (${retTotalPct >= 0 ? '+' : ''}${retTotalPct.toFixed(2)}%)` : ''}
        </div>
      </td>
    </tr>`;
    // 2026-08-11 -- the old special note-styled Unmapped line (below the
    // table, own alignment math to fake lining up with the Category/Wt%
    // columns) is gone -- Unmapped now renders as a genuine <tr> inside
    // `rows` above, via `allRows`, with the exact same cells/click-through/
    // tooltip every other category gets. User: "add unmapped as a row just
    // like Equities etc."
    const headCells = _FS_WINDOWS
      .map(w => `<th title="Top: your time-weighted return, ${w.full}. Bottom (smaller): its benchmark ETF's return over the same period.">${w.label}</th>`)
      .join('');
    // 2026-08-10 -- Returns column header -- period-labeled so it's clear
    // which of the 5 periods (radio group on the Accounts filter bar) the
    // bars below reflect. See _fsReturnsBarCell.
    const retLabel = (_FS_WINDOWS.find(w => w.key === _retPeriod) || {}).label || _retPeriod;
    // TASK_136 A.3 -- wrapped in overflow-x:auto so the table degrades (its
    // own scrollbar) at narrow widths instead of forcing the grid track
    // wider than its share.
    body.innerHTML = `
      <div style="overflow-x:auto">
        <table class="fs-table">
          <thead><tr><th title="Category, sector/asset-class/style">Category</th>
            <th title="Weight — % of your total portfolio">Wt%</th>
            ${headCells}
            <th title="Mine (solid) vs Market (faded), ${retLabel}">Returns (${retLabel})</th></tr></thead>
          <tbody>${rows ? rows + retTotalRow : `<tr><td colspan="${3 + _FS_WINDOWS.length}">No rows.</td></tr>`}</tbody>
        </table>
      </div>
    `;
    if (stanceData) {
      body.querySelectorAll('tr[data-cat]').forEach(tr => {
        const icon = tr.querySelector('.cat-quad-stance');
        const stanceRow = icon ? stanceMap.get(tr.dataset.cat) : null;
        if (!icon || !stanceRow) return;
        icon.addEventListener('click', e => e.stopPropagation());
        icon.addEventListener('mouseover', () => _showCategoryQuadPop(icon, stanceRow, stanceData));
        icon.addEventListener('mouseout', e => {
          if (e.relatedTarget && e.relatedTarget.closest('.cat-quad-stance')) return;
          _hideQuadPop();
        });
      });
    }
    if (chartId) {
      const onSliceClick = cat => openFactorExposureModal(axis, cat);
      if (axis === 'style') {
        _renderCatBars(chartId, r.rows, r.unmapped, colorMap, onSliceClick);
      } else {
        _renderCatPie(chartId, r.rows, r.unmapped, colorMap, onSliceClick);
        // TASK_140 follow-up 16 -- the chart is a fixed 190px square
        // (.cat-chart's flex-basis); when the table is shorter than that
        // (e.g. Asset class's 7 rows), .cat-body's flex-start row height
        // was still set by the taller chart, leaving empty space below the
        // shorter table column. Measures the table's REAL rendered height
        // (offsetHeight forces a synchronous reflow -- no CSS-estimate
        // guessing this time) and caps the chart down to match whenever
        // it's the taller one, so both columns end the row at the same
        // point.
        // 2026-08-08 BUGFIX -- this was setting chartBox.style.flexBasis,
        // but .cat-body is `display:flex` with NO flex-direction override
        // (row, the default), so flex-basis controls WIDTH, not height.
        // Setting it from a HEIGHT measurement silently squeezed .cat-chart
        // narrower whenever a table was short (Asset class's 8 rows vs
        // Sector's 11), which is exactly why Asset class's chart measured
        // 204px wide against Sector's 218px and the whole table column
        // after it started at a different x -- confirmed via user
        // screenshot + devtools measurement. Fixed to set the SVG's own
        // height instead, leaving .cat-chart's width (and therefore every
        // .cat-table-col's left edge) untouched and identical across axes.
        const svg = $(chartId);
        if (svg) {
          const tableH = body.offsetHeight;
          svg.style.height = (tableH > 0 && tableH < 190) ? `${tableH}px` : '';
        }
      }
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
  await Promise.all([loadEconIndicators(), loadNearTermEarnings()]);
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

// 2026-08-09 -- re-runs just the 3 stacked grids (Sector/Asset Class/
// Style), not the whole dashboard -- used by both refreshAll() and the
// Accounts filter's change handler (loadCatAccountFilter), which only
// needs to refresh these 3, not re-fetch Risk Dial/Regime/Events/etc.
function reloadFactorScorecards() {
  return Promise.all([
    loadFactorScorecard('sector', 'sectorScorecardBody', 'sectorChart'),
    loadFactorScorecard('asset_class', 'assetClassScorecardBody', 'assetChart'),
    loadFactorScorecard('style', 'styleScorecardBody', 'styleChart'),
  ]);
}

// 2026-08-12 -- the 3 Today-snapshot widgets (Asset Class/Sector/Style,
// _tsRow()/loadTodaySnapshot()) were removed entirely -- their numbers came
// from drv_category_perf.twr_today, a mark-to-market APPROXIMATION (freeze
// yesterday's shares, re-price at today's live quote) that can diverge
// sharply from the broker's own actual today's-gain figure whenever you've
// traded that day (a sold position still counts as held at yesterday's
// qty, a bought one isn't counted until tomorrow) -- confirmed diverging by
// ~$2400 on a live check (-$2159 approx. vs +$273.54 actual). User: "why
// the values are not correct?" -> chose "Remove those graphs" over
// rebuilding a proper broker-based per-category breakdown. The Cumulative
// P&L widget below is unaffected -- it already uses the accurate broker
// figure (day_chng_dollar/today_gl_dollar via /api/portfolio/trends +
// /api/portfolio/summary), not twr_today.

// 2026-08-11 -- Cumulative P&L mini chart -- same chart (Day Change bars +
// Cumulative P&L line) as the Portfolio screen's Trends panel (web/portfolio.js::
// renderTrendCharts/#chTrendCum), same /api/portfolio/trends endpoint,
// just trimmed to the last 10 data points client-side (no "10d" period
// exists server-side -- period only accepts mtd/ytd/1y/5y/30d/90d/180d,
// see api/routers/dash.py::get_portfolio_trends -- 30d is fetched and
// sliced rather than adding one). Whole-portfolio, unfiltered: that
// endpoint takes a single `account`, not a list, so it has no equivalent
// of the Dashboard's multi-select Accounts filter (state.catAccounts).
// User: "add same graph that you portfolio screen (cumulative p&L) but
// show last 10 days -> add it in the same line as today's graph row in
// the front."
let _cumPnlChart = null;
async function loadCumPnlSnapshot() {
  const canvas = $('tsCumPnlChart');
  const totalEl = $('tsCumPnlTotal');
  const todayEl = $('tsCumPnlToday');
  if (!canvas || typeof Chart === 'undefined') return;
  try {
    // 2026-08-11 -- period now comes from #tsCumPnlPeriod (same dropdown/
    // options/default as portfolio.html's #trendsPeriod), not a hardcoded
    // '30d' -- user: "remove the header text 10 D and replace it with same
    // drop down as portfolio screen."
    const periodEl = $('tsCumPnlPeriod');
    const period = (periodEl && periodEl.value) || '30d';
    const trendsParams = new URLSearchParams({ period });
    // 2026-08-11 -- Accounts filter (state.catAccounts) now applies here
    // too, via the new accounts= param on /api/portfolio/trends (mirrors
    // /api/cockpit/factor-scorecard's own accounts= the other 3 widgets
    // already used) -- user: "Move the filter bar to the top and apply
    // the filter to four graphs."
    const filtered = state.catAccounts.length > 0;
    if (filtered) trendsParams.set('accounts', state.catAccounts.join(','));
    const [r, summary] = await Promise.all([
      fetchJson('/api/portfolio/trends?' + trendsParams.toString()),
      // /api/portfolio/summary has no account filter of its own -- skip
      // the today-bar override entirely while a filter is active rather
      // than overwriting a filtered day with an unfiltered whole-portfolio
      // figure (see the override's own comment below for why it exists).
      filtered ? Promise.resolve(null)
               : fetchJson('/api/portfolio/summary' + (state.date ? '?date=' + encodeURIComponent(state.date) : ''))
                   .catch(() => null),
    ]);
    const N = 10;
    const dates = (r.dates || []).slice(-N);
    const dayArr = (r.day_change || []).slice(-N);
    // 2026-08-11 -- last bar overridden with /api/portfolio/summary's
    // today_gain_dollar (the same figure the Portfolio screen's "Today's
    // Gain" KPI tile shows, kpiToday in portfolio.js) instead of the plain
    // trends-endpoint day_change for that date. The two are NOT the same
    // computation even on the Portfolio screen itself: trends' day_change
    // is just broker day_chng_dollar/today_gl_dollar, while summary's
    // today_gain_dollar additionally adds the intraday move on shares SOLD
    // today and today's dividends/interest (see api/routers/dash.py::
    // get_portfolio_summary's cs_sold_move/cs_div_int) -- summary is the
    // more complete, authoritative number, so this widget now matches it.
    // User: "I need to see the same numbers (today's gain) and cum gain."
    //
    // 2026-08-11 -- Cum now taken DIRECTLY from r.cumulative_pl (same
    // running sum the Portfolio screen's own Trends chart computes from
    // this same endpoint at the SAME period, now that #tsCumPnlPeriod
    // mirrors #trendsPeriod's options/default), just sliced to the last 10
    // points for display -- NOT reset to 0 at day 1 of the window. A prior
    // version recomputed a fresh from-zero 10-day sum instead, which is a
    // different, smaller number by design (it drops everything before the
    // visible window) -- that's why it didn't match. User: "Cum number is
    // not matching with portfolio screen. I want to see same numbers."
    // Only the LAST point is nudged
    // by the same delta the today_gain_dollar override introduces below,
    // so the line's endpoint stays consistent with the (now more accurate)
    // last bar instead of silently disagreeing with it.
    const cumRaw = (r.cumulative_pl || []).slice(-N);
    const cum = cumRaw.slice();
    if (summary && summary.today_gain_dollar != null && dayArr.length && cumRaw.length) {
      const origLastDay = Number(dayArr[dayArr.length - 1] || 0);
      const newLastDay = Number(summary.today_gain_dollar);
      const delta = newLastDay - origLastDay;
      dayArr[dayArr.length - 1] = newLastDay;
      cum[cum.length - 1] = Math.round((cumRaw[cumRaw.length - 1] + delta) * 100) / 100;
    }
    if (_cumPnlChart) { _cumPnlChart.destroy(); _cumPnlChart = null; }
    if (!dates.length) {
      if (totalEl) totalEl.textContent = '';
      if (todayEl) todayEl.textContent = '';
      return;
    }
    const colorPos = '#1c6c30', colorNeg = '#b21f1f';
    const lastCum = cum.length ? cum[cum.length - 1] : 0;
    const cumColor = lastCum >= 0 ? colorPos : colorNeg;
    const yTick = v => Math.abs(v) >= 1000 ? '$' + (Math.round(v / 100) / 10).toFixed(1) + 'k' : '$' + Math.round(v);
    _cumPnlChart = new Chart(canvas, {
      type: 'bar',
      data: { labels: dates, datasets: [
        { type: 'bar', label: 'Day Change', data: dayArr,
          backgroundColor: dayArr.map(v => v >= 0 ? 'rgba(28,108,48,0.85)' : 'rgba(178,31,31,0.85)'),
          borderWidth: 0, barPercentage: 0.5, categoryPercentage: 0.7,
          yAxisID: 'y1', order: 0 },
        { type: 'line', label: 'Cumulative P&L', data: cum,
          borderColor: cumColor,
          backgroundColor: lastCum >= 0 ? 'rgba(28,108,48,0.10)' : 'rgba(178,31,31,0.10)',
          fill: false, borderWidth: 2, tension: 0.25,
          yAxisID: 'y', order: 1 },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: true, mode: 'index', intersect: false } },
        scales: {
          x:  { display: true, ticks: { font: { size: 8 }, color: '#888', maxRotation: 0, autoSkip: true, maxTicksLimit: 5 }, grid: { display: false } },
          y:  { type: 'linear', position: 'right', display: true, ticks: { font: { size: 8 }, color: '#888', callback: yTick }, grid: { color: 'rgba(0,0,0,0.06)' } },
          y1: { type: 'linear', position: 'left', display: false },
        },
        elements: { point: { radius: 0 } },
      },
    });
    // 2026-08-11 -- both numbers shown in the title bar, not just Cum --
    // user: "Display today's gain and cum in 10 chart." Today = the same
    // (possibly summary-overridden) figure as the chart's own last bar;
    // Cum = the last point of the recomputed 10-day running line.
    const lastToday = dayArr.length ? Number(dayArr[dayArr.length - 1]) : null;
    if (todayEl) {
      todayEl.className = 'ts-total' + (lastToday >= 0 ? ' pos' : ' neg');
      todayEl.textContent = lastToday != null ? 'Today ' + (_fsCompactUsd(lastToday) || '') : '';
    }
    if (totalEl) {
      totalEl.className = 'ts-total' + (lastCum >= 0 ? ' pos' : ' neg');
      totalEl.textContent = 'Cum ' + (_fsCompactUsd(lastCum) || '');  // _fsCompactUsd already signs its own output
    }
  } catch (e) {
    console.error('cum P&L snapshot failed:', e);
    if (totalEl) totalEl.textContent = '';
    if (todayEl) todayEl.textContent = '';
  }
}

// 2026-08-13 -- Portfolio Mix card: same Asset Allocation/Beta/Sector/
// Concentration pies as the Actionable screen's sidebar Portfolio Mix panel
// (web/actionable.js::renderPortfolioMix/_pmHeldRows/_pmCashTotal), reusing
// the shared web/portfolio_mix.js draw engine (pmRenderCoreMix) instead of
// re-implementing it. Macro Stance is skipped -- it depends on
// actionDisplay()'s buy/sell/neutral vocabulary, an Actionable-only concept.
// Whole-portfolio unless the Accounts filter (state.catAccounts) has a
// selection, same scoping as the Cumulative P&L widget and the 3
// factor-scorecard grids in this column. User: "display graphs from
// actionable screen, side bar -> portfolio mix -> asset allocation, Beta,
// sector, concentration ... on dashboard screen -> line below cumulative P&L."
//
// 2026-08-14 -- position source switched from /api/actionable (drv_
// actionable's held_today/current_position_dollar) to the raw /api/portfolio
// feed (hist_cs/hist_f, same as the Sector/Asset class factor-scorecard
// tables) -- drv_actionable only carries symbols with a resolved tos_symbol
// in the tracked technicals universe, silently dropping any held position
// without one (found live: QTUM/IVOL/SOFI/WRBY/INTU, ~$44k/5.75% of one
// portfolio, missing from every pie, not just misclassified). No
// /api/actionable fetch needed anymore -- this card has no macro_value
// dependency (that's Actionable-only, see above), so the raw broker
// position feed is now the ONLY position source here. /api/portfolio's own
// tos_symbol column is unreliable (NULL on most rows, even tracked ones --
// confirmed live), so the raw broker `symbol` string is used as both the
// display label and the join key into assetClassMap/sectorMap (built the
// same way, keyed by tos_symbol OR ref_sector.ticker -- see /api/portfolio/
// asset-class-map's docstring). User: "sector is not matching" -> traced to
// the drv_actionable gap -> "switch all 4 pies to source from
// /api/portfolio entirely".
async function loadDashPortfolioMix() {
  if (!$('dashPortfolioMixSection') || typeof Chart === 'undefined') return;
  try {
    const dateParam = state.date ? `?date=${encodeURIComponent(state.date)}` : '';
    const [portfolioRows, betaMap, assetClassMap, sectorMap] = await Promise.all([
      fetchJson('/api/portfolio' + dateParam),
      fetchJson('/api/portfolio/beta-map' + dateParam).catch(() => ({})),
      fetchJson('/api/portfolio/asset-class-map' + dateParam).catch(() => ({})),
      fetchJson('/api/portfolio/sector-map' + dateParam).catch(() => ({})),
    ]);
    const allPositions = Array.isArray(portfolioRows) ? portfolioRows : [];
    const accounts = state.catAccounts || [];
    const bySymbol = {};
    for (const p of allPositions) {
      if (p.is_cash || !p.symbol) continue;
      if (accounts.length && !accounts.includes(p.account_id)) continue;
      const row = bySymbol[p.symbol] || (bySymbol[p.symbol] = {
        tos_symbol: p.symbol,
        current_position_dollar: 0,
        _pmAssetClass: (assetClassMap && assetClassMap[p.symbol]) || 'Unmapped',
        _pmSector: (sectorMap && sectorMap[p.symbol]) || 'Unmapped',
      });
      row.current_position_dollar += Number(p.market_value) || 0;
    }
    const held = Object.values(bySymbol).filter(r => r.current_position_dollar > 0);
    const cashTotal = allPositions
      .filter(r => r.is_cash && (!accounts.length || accounts.includes(r.account_id)))
      .reduce((s, r) => s + (Number(r.market_value) || 0), 0);
    pmRenderCoreMix('dpm', held, cashTotal, (betaMap && typeof betaMap === 'object') ? betaMap : {});
  } catch (e) {
    console.error('dashboard portfolio mix failed:', e);
  }
}

// 2026-08-09 -- Accounts filter bar above the 3 stacked grids ("second
// column -> sector grid / asset class grid / style grid (stacked)").
// Checkbox per active account (from the same /api/actionable/accounts
// endpoint the Actionable screen's own account filter uses); empty
// selection = all accounts (default). Only re-fetches the 3 grids on
// change, not the whole dashboard. User: "Can we add a filter bar for
// second column -> accounts filter."
async function loadCatAccountFilter() {
  const el = $('catAccountFilter');
  if (!el) return;
  try {
    const qs = state.date ? `?date=${encodeURIComponent(state.date)}` : '';
    const accounts = await fetchJson(`/api/actionable/accounts${qs}`);
    // Drop any selected accounts that no longer exist for this date (e.g.
    // after navigating to a date before an account had any activity) --
    // keeps state.catAccounts from silently filtering to nothing.
    const validNums = new Set(accounts.map(a => a.account_number));
    state.catAccounts = state.catAccounts.filter(a => validNums.has(a));
    el.innerHTML = accounts.map(a => `
      <label class="cat-acct-chip">
        <input type="checkbox" value="${escapeHtml(a.account_number)}"
               ${state.catAccounts.includes(a.account_number) ? 'checked' : ''}>
        ${escapeHtml(a.display_name)}
      </label>
    `).join('');
    el.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        state.catAccounts = Array.from(el.querySelectorAll('input:checked')).map(c => c.value);
        reloadFactorScorecards();
        loadCumPnlSnapshot();
        loadDashPortfolioMix();
      });
    });
  } catch (e) {
    console.error('cat account filter failed:', e);
    el.innerHTML = '';
  }
}


// 2026-08-09 -- Market View: SAME chart+table format as the $ grids above
// (pie/bar chart + fs-table-style table with a caret), deliberately kept
// as separate cards -- pure market/quad-outlook read, zero dependency on
// what you hold. Count replaces $ weight (chart slices/bars sized by # of
// stocks, table's count column is "N / total universe" instead of a Wt%);
// benchmark ETF return (bench_mtd/etc, already computed independent of
// holdings) replaces your TWR in the window cells -- reused from the same
// /api/cockpit/factor-scorecard response the $ grids already fetch, keyed
// by category name, so no new backend work was needed for that part.
// Optional Source filter (state.marketViewSource) switches the count/
// stance data from the default Hedgeye quad outlook to one of the RR/
// CALL/ETF/II/SSS/PS per-symbol outlook sources -- see api/routers/
// dash.py::_quad_factor_stance_by_source. User: "how can i see same
// graphs for sources, only market data no money is involved" -> "i was
// envisioning the same graphs as above with no money from my holdings
// involved" -> "instead of $ percentages they will be # of stocks out of
// total stocks for a given source or all" -> "add a filter above those
// graphs for filtering by source."
async function loadMarketView(axis, bodyId, chartId) {
  const body = $(bodyId);
  if (!body) return;
  try {
    const params = new URLSearchParams({ axis });
    if (state.date) params.set('date', state.date);
    if (state.marketViewSource) params.set('source', state.marketViewSource);
    const benchParams = new URLSearchParams({ axis });
    if (state.date) benchParams.set('date', state.date);
    // 2026-08-10 -- when a Source filter is active, ALSO fetch the plain
    // quad-regime read (no source param) so the caret cluster's trailing
    // triangles (this month/qtr/next-qtr) still show -- those come from
    // Hedgeye's own quarterly outlook, a property of the CATEGORY (e.g.
    // Financials), not of which per-symbol source you're filtering the
    // stock list by. User: "when i select SSS, i still see financials so
    // shouldn't i see carets for financials?" -- correct: Financials'
    // quad-regime forecast doesn't depend on the Source filter at all, it
    // was only being dropped because the source-filtered response
    // (_quad_factor_stance_by_source) has no months/qtr/next_qtr fields of
    // its own (RR/SSS/PS/etc are point-in-time signals, not a forecast).
    // Skipped when no source is selected -- `d` already IS that same data.
    const quadParams = state.marketViewSource ? new URLSearchParams({ axis }) : null;
    if (quadParams && state.date) quadParams.set('date', state.date);
    const [d, benchData, quadData] = await Promise.all([
      fetchJson(`/api/quad/factor-stance?${params.toString()}`),
      fetchJson(`/api/cockpit/factor-scorecard?${benchParams.toString()}`).catch(() => null),
      quadParams ? fetchJson(`/api/quad/factor-stance?${quadParams.toString()}`).catch(() => null) : Promise.resolve(null),
    ]);
    const benchMap = new Map((benchData?.rows || []).map(r => [String(r.category).trim().toLowerCase(), r]));
    const quadStanceMap = new Map((quadData?.rows || d.rows || []).map(r => [String(r.category).trim().toLowerCase(), r]));
    const rows = (d.rows || []).filter(r => r.count > 0).sort((a, b) => b.count - a.count);
    const total = d.total_count || 0;
    // 2026-08-10 -- Returns column, same as the top 3 $ grids -- user:
    // "add the Returns columns to bottom three grids also (i asked it in
    // my original request)." Market View has no "mine" data by design
    // (zero dependency on what you hold), so _fsReturnsBarCell gets
    // mine=null -- it already renders just the market bar when mine is
    // absent, no changes needed there. Scale (_retMax) computed from
    // bench values only, same shared-per-table-scale reasoning as the $
    // grids.
    const _retPeriod = _selectedCatReturnsPeriod();
    const _retMax = Math.max(1, ...rows.map(rr => {
      const b = benchMap.get(rr.category.trim().toLowerCase());
      return b ? Math.abs(b[`bench_${_retPeriod}`] || 0) : 0;
    }));

    // 2026-08-10 -- chart slice/bar colors now match the top 3 $ grids'
    // scheme exactly: one distinct color per category (_catColorMap,
    // --cat1..9 vars), not the earlier bullish/bearish/neutral stance
    // coloring -- stance is still visible via the caret cluster in the
    // category column, so this isn't losing that signal, just moving chart
    // coloring onto the same categorical palette the top grids use. User:
    // "match the bottom 3 graph colors with top 3 graph colors."
    const colorMap = _catColorMap(rows);
    // days_to_qtr_end is null on the source-filtered response (it has no
    // window concept of its own) -- fall back to the always-fetched
    // quad-regime data's value so the qtr/next-qtr cross-fade still works
    // when a Source filter is active.
    const [curQtrOp, nextQtrOp] = _qtrFadeOpacities(quadData?.days_to_qtr_end ?? d.days_to_qtr_end);
    // 2026-08-10 -- chart slices/bars now open the same popup as the table
    // row (openMarketViewDetailModal), matching the top 3 $ grids' own
    // "click the chart, get the same popup as the row" behavior -- this
    // was hardcoded `null` (no click-through) from when Market View's
    // charts still pointed at the $-holdings popup, which didn't apply
    // here. User: "graph clicks for bottom 3 graphs are not working."
    const onSliceClick = cat => openMarketViewDetailModal(axis, cat, state.marketViewSource || '');
    if (axis === 'style') {
      _renderCatBars(chartId, rows.map(r => ({ category: r.category, weight_pct: r.count })), null, colorMap, onSliceClick);
    } else {
      _renderCatPie(chartId, rows.map(r => ({ category: r.category, weight_pct: r.count })), null, colorMap, onSliceClick);
    }

    const headCells = _FS_WINDOWS
      .map(w => `<th title="${escapeHtml(w.full)} -- benchmark ETF's own return, independent of your holdings">${w.label}</th>`)
      .join('');
    const retLabel = (_FS_WINDOWS.find(w => w.key === _retPeriod) || {}).label || _retPeriod;
    // 2026-08-10 -- category -> caret-cluster row, keyed for the hover
    // popover wiring below (same _showCategoryQuadPop the top 3 $ grids
    // use). User: "fix popovers on carets" -- Market View never wired this
    // at all (top grids only); adding it here, reusing the SAME merged
    // row the caret cluster itself renders from so the popover always
    // matches what's on screen (source's own read up top, quad-regime
    // detail below it).
    const catCaretMap = new Map();
    const bodyRows = rows.map(r => {
      const bench = benchMap.get(r.category.trim().toLowerCase());
      const cells = _FS_WINDOWS.map(w => {
        const v = bench ? bench[`bench_${w.key}`] : null;
        return `<td>${_fsColorCell(v) || '<span class="fs-dash">—</span>'}</td>`;
      }).join('');
      // 2026-08-10 -- main caret = the selected source's own bullish/
      // bearish read (r.score/r.stance); trailing period/qtr/next-qtr
      // carets = always the category's quad-regime forecast (quadRow),
      // regardless of Source filter -- see the quadStanceMap fetch above.
      // No source selected -> quadRow IS r already, unchanged.
      const catKey = r.category.trim().toLowerCase();
      const quadRow = quadStanceMap.get(catKey);
      const caretRow = state.marketViewSource
        ? { category: r.category, score: r.score, stance: r.stance,
            months: quadRow?.months, qtr: quadRow?.qtr, next_qtr: quadRow?.next_qtr,
            quad1: quadRow?.quad1, quad2: quadRow?.quad2, quad3: quadRow?.quad3, quad4: quadRow?.quad4 }
        : r;
      catCaretMap.set(catKey, caretRow);
      const caretHtml = _quadCaretCluster(caretRow, curQtrOp, nextQtrOp);
      // 2026-08-09 -- NOT clickable to the $ exposure popup, unlike the $
      // grids' own rows -- that popup shows YOUR holdings, which
      // contradicts Market View's whole point ("no $, no holdings"), and
      // clicking through to it made the Source filter look broken (row
      // click always showed the same $ positions regardless of which
      // source was selected, since it's a different data source entirely).
      // 2026-08-10 -- row IS clickable again, but only to the NEW
      // market_view_modal.js popup (per-symbol source detail + benchmark
      // ETF charts, no $/holdings) -- and only when a specific Source
      // filter is active. The default (no Source, Hedgeye quad-outlook)
      // view has no single per-symbol "signal value" to list, so it stays
      // non-clickable there. Same "pass primitives, let the modal fetch its
      // own data" convention as openFactorExposureModal above -- no bench
      // object embedded inline. User: "i need to see the stock details in
      // the popups. depending on the source." / confirmed: specific
      // sources only.
      // 2026-08-10 -- also clickable in the default "All" (no Source
      // filter) view now -- the benchmark ETF charts (daily gain/loss,
      // MTD/QTD/YTD) are driven by category+axis, not by source, so they
      // work identically here; only the per-symbol stock TABLE doesn't
      // apply (no single source's signal to list when blending all 4
      // quads) -- market_view_modal.js skips that fetch and shows a note
      // instead when source is ''. User: "you could still have a popup for
      // all and show the graphs only right?"
      const clickAttr = ` class="fs-clickable" data-cat="${escapeHtml(catKey)}" style="cursor:pointer;" onclick="openMarketViewDetailModal('${escapeHtml(axis)}', '${escapeHtml(r.category).replace(/'/g, "\\'")}', '${escapeHtml(state.marketViewSource || '')}')"`;
      const retBench = bench ? bench[`bench_${_retPeriod}`] : null;
      return `<tr${clickAttr}>
        <td><span style="display:inline-block;width:${_CARET_CLUSTER_PX}px;">${caretHtml}</span>${escapeHtml(r.category)}</td>
        <td class="fs-weight-cell"><span class="fs-weight-text">${r.count}</span><span class="fs-weight-eq">/ ${total}</span></td>
        ${cells}
        ${_fsReturnsBarCell(null, retBench, _retMax)}
      </tr>`;
    }).join('');

    // 2026-08-10 -- Style's "Overlapping tags -- not an allocation" note and
    // the count_universe ref_sector/ToS-tracked note both removed per user
    // request (previously explained why counts don't sum to the total).
    body.innerHTML = `
      <div style="overflow-x:auto">
        <table class="fs-table">
          <thead><tr><th title="Category, sector/asset-class/style">Category</th>
            <th title="# of stocks in this category / total universe">Count</th>
            ${headCells}
            <th title="Market return, ${retLabel} (no 'mine' bar -- Market View has no holdings)">Returns (${retLabel})</th></tr></thead>
          <tbody>${bodyRows || `<tr><td colspan="${3 + _FS_WINDOWS.length}">No rows.</td></tr>`}</tbody>
        </table>
      </div>
    `;
    // 2026-08-10 -- hover popover on the caret cluster, same
    // _showCategoryQuadPop the top 3 $ grids use (loadFactorScorecard) --
    // was never wired here at all. click stopPropagation so hovering/
    // clicking the caret itself doesn't also open the row's stock-detail
    // modal. User: "fix popovers on carets."
    body.querySelectorAll('tr[data-cat]').forEach(tr => {
      const icon = tr.querySelector('.cat-quad-stance');
      const stanceRow = icon ? catCaretMap.get(tr.dataset.cat) : null;
      if (!icon || !stanceRow) return;
      icon.addEventListener('click', e => e.stopPropagation());
      icon.addEventListener('mouseover', () => _showCategoryQuadPop(icon, stanceRow));
      icon.addEventListener('mouseout', e => {
        if (e.relatedTarget && e.relatedTarget.closest('.cat-quad-stance')) return;
        _hideQuadPop();
      });
    });
  } catch (e) {
    console.error('market view failed:', axis, e);
    body.innerHTML = '<div class="mv-empty">Failed to load.</div>';
  }
}

function reloadMarketView() {
  return Promise.all([
    loadMarketView('sector', 'marketViewSectorBody', 'marketViewSectorChart'),
    loadMarketView('asset_class', 'marketViewAssetClassBody', 'marketViewAssetClassChart'),
    loadMarketView('style', 'marketViewStyleBody', 'marketViewStyleChart'),
  ]);
}

async function refreshAll() {
  // Band 6 (housekeeping) resolves state.housekeepingOk/state.anchorDate
  // first since Band 1 needs to know whether to show its stale-data warning
  // (spec 7.2 Band 6: "When it is red, Band 1 must show a warning").
  await loadHousekeeping();
  await loadRiskDial();
  // loadCatAccountFilter awaited on its own first -- it can prune stale
  // account selections from state.catAccounts (e.g. after navigating to a
  // date before an account had activity), and reloadFactorScorecards
  // needs to read that settled value, not race it.
  await loadCatAccountFilter();
  await Promise.all([
    loadEventsBand(),
    loadRegimeBand(),
    reloadFactorScorecards(),
    loadCumPnlSnapshot(),
    loadDashPortfolioMix(),
    reloadMarketView(),
    loadBriefing(),
  ]);
  // 2026-08-10 -- Volatility/Major Markets panels (macro_areas.js, loaded on
  // this page now too) wire their own #datePicker "change" listener, but
  // not the Refresh button -- same gap actionable.js's own refresh handler
  // already works around by calling this global directly.
  if (window.reloadMacroAreas) window.reloadMacroAreas();
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
  // 2026-08-09 -- Market View Source filter -- only re-runs the 3 Market
  // View panels, not the whole dashboard. User: "add a filter above those
  // graphs for filtering by source."
  const srcSel = $('marketViewSourceSelect');
  if (srcSel) srcSel.addEventListener('change', () => {
    state.marketViewSource = srcSel.value || null;
    reloadMarketView();
  });
  // 2026-08-10 -- Returns chart period selector (Today/Yest/MTD/QTD/YTD),
  // shared across the 3 column-2 grids -- wired once here; each grid's own
  // loadFactorScorecard() populates the rows this reads from.
  _initCatReturnsPeriod();
  // 2026-08-11 -- Cumulative P&L widget's own period dropdown (mirrors
  // portfolio.html's #trendsPeriod) -- only re-runs that one widget.
  const cumPeriodSel = $('tsCumPnlPeriod');
  if (cumPeriodSel) cumPeriodSel.addEventListener('change', () => loadCumPnlSnapshot());
  await refreshAll();
});
