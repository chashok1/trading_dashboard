/* Actionable Stocks page logic */

// ── Column show/hide manager (TASK_105 U1) ──────────────────────────────────
// Toggleable columns (everything except the non-toggleable core: LT hold,
// bulk checkbox, H, Symbol, ACTION, AMT$). `id` matches each th/td's
// data-col attribute; visibility is applied via a single dynamic <style>
// rule (see applyColumnVisibility()) rather than per-cell DOM edits.
const COL_STORAGE_KEY = 'act_cols_v1';
const TOGGLEABLE_COLS = [
  { id: 'pos',       label: 'POS$' },
  { id: 'chg',       label: '%CHG' },
  { id: 'macro',     label: 'MACRO' },
  { id: 'calc',      label: 'CALC' },
  { id: 'sources',   label: 'Sources' },
  { id: 'technical', label: 'Technical' },
  { id: 'rr',        label: 'RR' },
  { id: 'vlm',       label: 'Vlm' },
  { id: 'iv',        label: 'IV' },
  { id: 'macd',      label: 'MACD' },
  { id: 'macdh',     label: 'MACDH' },
  { id: 'rsi',       label: 'RSI' },
  { id: 'rules',     label: 'Rules (edge)' },
  { id: 'bullprob',  label: 'P(↑ 20d)' },
  { id: 'agree',     label: 'Agree' },
  { id: 'pvv',       label: 'PVV' },
];
// Default-hidden: model-diagnostic columns not needed for day-to-day workflow.
const DEFAULT_HIDDEN_COLS = ['calc', 'bullprob', 'agree'];
function _loadHiddenCols() {
  try {
    const raw = localStorage.getItem(COL_STORAGE_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) return new Set(arr);
    }
  } catch (_) {}
  return new Set(DEFAULT_HIDDEN_COLS);
}

const state = {
  date: null,
  anchorDate: null,  // latest available date (dates[0]) -- "viewing live" reference
  allRows: [],   // full unfiltered dataset for the date
  baseRows: [],  // passes every filter except the action chip (drives chip counts)
  rows: [],      // filtered subset shown in grid
  sort: { key: '_priority', dir: -1, type: 'num' },  // default: priority DESC
  filters: {
    action: '',          // '' | REMOVE | REDUCE | INCREASE | ADD | HOLD
    source: '',
    account: '',
    held_only: false,
    show_hidden: false,  // when true, reveals suppressed/$0/no-action/acted/unheld-remove rows
    symbol_search: '',   // symbol search text filter
    conviction: 'any',   // 'any' | 'multi' | 'proven'
    actionable_only: true, // hides HOLD and NONE rows by default
    bull_prob_min: 0,    // TASK_66: minimum bull_prob (0 = no filter)
    agreement_class: '', // TASK_69: '' = all; else exact match on agreement_class
    stopOnly: false,     // TASK_119: STOP chip — filter to stop_breached rows
    trade_mode: true,    // TASK_124: show only qualifying buys / SA sells / stop breaches
                         // (always starts ON, not persisted — reset near page init)
    asset_class: '',     // '' = all; else exact match on r._assetClass (normalized real_asset_class)
    symbols_multi: [],   // multi-symbol filter popup — exact-match list, empty = no filter
    etfchg_only: false,  // EC pill — recent ETF Pro Change event (etfchg_date), informational only
    iichg_only: false,   // IC pill — recent II Pro Change event (iichg_date), informational only
    rr_min: 0, rr_max: 100, // RR (Risk Range %) dual-thumb slider — 0/100 = no filter
  },
  // TASK_120 buy-noise gate: manual expand/collapse for the "Watchlist (n)"
  // band (gated unheld ADD/BMN rows). Auto-expands (without flipping this
  // flag) whenever an active filter/search matches a row inside the band.
  watchlistExpanded: false,
  current: null,
  sourceMethods: {},   // source_code -> base_weight_method (Metric-column sort)
  buysellSeq: {},      // buysell code -> seq from ref_param_lookup (priority sort)
  agreementScorecard: null, // TASK_69: {agreement_class -> avg_fwd_20d} cache
  // quadFactors (was: cached from /api/quad/band-factors for the removed
  // Regime band's own popover) removed 2026-08-10 -- no other reader.
  quadData: null,           // cached from /api/dashboard/quads (period dates for dtb)
  allAccounts: [],          // [{account_number, display_name, short_name, custom_name}] from /api/actionable/accounts
  // Pass 3: bulk select
  selected: new Set(),
  // Pass 3: focus mode
  focusIdx: 0,
  // TASK_105: column visibility (set of hidden column ids, incl. 'h' when
  // show_hidden is off — see applyColumnVisibility()).
  hiddenCols: _loadHiddenCols(),
};
// 2026-08-14 -- exposed on window so later-loaded scripts can read it --
// a top-level `const`/`let` binding lives in this file's own lexical
// scope only, NOT on window, even in a classic (non-module) script (only
// `var`/function declarations do). risk_gauge_modal.js's _dateQS() reads
// window.state.date to scope the exposure-detail popup (opened by the
// Portfolio Mix panel's Asset Allocation/Sector pies, see portfolio_mix.js
// ::_pmOpenCategoryModal) to whichever date is being viewed here -- same
// fix already applied in app.js (see that file's own comment on this) for
// the Dashboard screen's equivalent gap. User: "add same click actions on
// the top graphs also."
window.state = state;

const $ = (id) => document.getElementById(id);

// fetchJson is provided by _common.js (window.fetchJson).

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
function fmtDateMD(d) {
  if (!d) return '—';
  const s = d.toString().slice(0, 10); // YYYY-MM-DD
  return s.slice(5, 7) + '/' + s.slice(8, 10);
}

// Solid %CHG chip (2026-09-01, user: "use boxes like you are using in
// dashboard panels" -- matches macro_areas.js's _chgChipHtml/the tape's
// %chg convention) — replaces the old plain colored text (.pct-positive/
// .pct-negative). Reuses the shared .msr-chg class (styles.css) for the
// pill shape/font, overriding its fixed flex-basis (tuned for that panel's
// 1-decimal values) to auto since this column keeps its existing 2-decimal
// precision, which can run a character wider.
function _pctChgChipHtml(pct) {
  if (pct === null || pct === undefined) return '';
  const n = Number(pct);
  const flat = Math.abs(n) < 0.001;
  const bg = flat ? '#888' : (n > 0 ? '#1d9e75' : '#d4537e');
  const txt = (n > 0 ? '+' : '') + n.toFixed(2) + '%';
  return `<span class="msr-chg" style="background:${bg};flex:0 0 auto;">${escapeHtml(txt)}</span>`;
}

// ---------- Side panel helpers + MACRO band (TASK_74) ----------

// ── MACRO column cell renderer (TASK_74) ────────────────────────────────────
// Renders a single cell for the MACRO column using the existing actionDisplay()
// colors/vocabulary. The turn arrow (↗/↘ + next quad/%) is appended when present.
// Confidence cue: faded badge at < 60% confidence. 2026-08-12: confidence is
// now technical-direction agreement % across the window (see macro_conf
// comment in api/routers/dash.py), not "how near-term the window is".
// On hover, a tooltip shows the full MacroNet breakdown from macro_detail.
// Data-completeness flag: no ref_sector row for this symbol means
// _resolve_memberships() (api/routers/dash.py) couldn't add a Sector
// membership, so the MACRO score here rests on Asset Class + style factors
// only — same signal the quad-data-gaps audit checks. See /api/admin/quad-data-gaps.
function _macroGapMark(r) {
  if (r.sector) return '';
  return `<span style="color:#f59e0b;font-size:8px;font-weight:700;vertical-align:super;margin-left:1px;" title="No sector classification (ref_sector) for this symbol — MACRO score is based on Asset Class + style factors only. Hover the badge for detail.">!</span>`;
}

function _stanceColor(v) {
  return v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
}

// Tracking-vs-score conflict mark (2026-08-12): r.macro_conflict is true
// when the FINAL blended macronet sign disagrees with the symbol's
// technical direction (price vs 50 DMA — etl/derive_macro.py's
// tracking_conflict, promoted onto the grid row in api/routers/dash.py).
// Distinct glyph/color from _macroGapMark's data-completeness "!" so the two
// unrelated warnings never look like the same thing at a glance.
// Shared bolt-shaped conflict icon (magenta #ec4899, 11x15 stretched, no
// stroke) -- established 2026-08-20 for the MACRO column's tracking-vs-
// score conflict (below). Reused for any other "disagrees with reality"
// signal (e.g. _srcReasonsHtml's premature-drop conflict) so "conflict"
// reads as one consistent visual language across the screen instead of a
// new glyph per feature. Plain SVG fill (not the ⚡ CHARACTER) because that
// glyph is a COLOR emoji on Windows/Mac -- its fill is baked into the font's
// own COLR/CBDT color table and ignores CSS `color` entirely.
function _conflictBoltHtml(title) {
  return `<span style="display:inline-block;vertical-align:middle;margin-left:2px;color:#ec4899;" `
    + `title="${escapeHtml(title)}">`
    + `<svg width="11" height="15" viewBox="0 0 24 24" preserveAspectRatio="none" style="display:inline-block;vertical-align:middle;">`
    + `<path fill="currentColor" d="M13 2 3 14h7v8l10-12h-7z"/></svg></span>`;
}
function _macroConflictMark(r) {
  if (r.macro_conflict !== true) return '';
  return _conflictBoltHtml('CONFLICT: MacroNet score disagrees with technical direction (price vs 50-day average). Hover the badge for detail.');
}
// Fixed-width slot for the conflict bolt (2026-09-01, user: "align the
// action buttons like BS with others when there is no conflict and there
// is conflict") -- macroCellHtml's badge/label row centers its children as
// a group (badge + bolt), so a conflict row's badge sat visibly left of
// where the same badge sits on a no-conflict row (badge alone). Reserving
// the bolt's ~13px footprint (11px icon + 2px margin) even when it's not
// shown keeps every row's centered group the same total width, so the
// badge itself lands in the same spot column-to-column either way.
function _macroConflictSlotHtml(r) {
  const mark = _macroConflictMark(r);
  return mark || '<span style="display:inline-block;width:13px;visibility:hidden;" aria-hidden="true"></span>';
}

// Premature-drop pill (2026-08-20): always shown for a REMOVE ("dropped
// from list") source_actions entry, next to the drop message, in the same
// pill style as every other percentage in the app (.hit-rate-pill) instead
// of plain colored text. Color now follows sign (2026-09-01, user: "use
// light colors instead of grey so i can see +ve or -ve") -- light green
// (hit-rate-pill-high) if price is up since the drop, light red
// (hit-rate-pill-neg) if it's down, no more grey either way. The magenta
// conflict bolt is layered on top when drop_conflict is true -- a single
// flag computed etl-side as EITHER the cumulative move clearing +5% OR a
// fresh 3-day up-streak (up_streak_3d, same 4-date window
// _compute_stop_signal already uses) -- either one alone is reason to flag.
// Shared by _srcReasonsHtml (grid Sources column) and _actpopDriverBullets
// (Action popup driver bullets) -- also read by _actpopTugHtml to surface a
// flagged drop as an Opposing signal on a sell-side row.
function _dropPctPillHtml(s) {
  if (s.action !== 'REMOVE' || s.pct_since_drop == null) return '';
  const pct = Number(s.pct_since_drop);
  const sign = pct >= 0 ? '+' : '';
  const flagged = s.drop_conflict === true;
  const cls = pct >= 0 ? 'hit-rate-pill-high' : 'hit-rate-pill-neg';
  const title = `${sign}${pct.toFixed(1)}% since dropped` + (flagged ? (s.up_streak_3d ? ' — up 3 days running' : ' — up >5% since') : '');
  const bolt = flagged
    ? _conflictBoltHtml(`Dropped but up ${sign}${pct.toFixed(1)}% since — may have been premature`)
    : '';
  return ` <span class="hit-rate-pill ${cls}" title="${escapeHtml(title)}">${sign}${pct.toFixed(1)}%</span>${bolt}`;
}

// Sector/asset-class/style dots (2026-08-01) — one small bar per membership
// dimension of the quad engine's live regime read, same color/height
// convention as the monthly sparkline bars. Styles are NOT averaged into one
// number: a symbol can carry several independent style tags (Momentum,
// Cyclical, Value, …) that can disagree with each other, so each gets its
// own bar — an average would hide a real split by canceling it to ~0/grey.
function _macroMemberBarsHtml(r) {
  const bars = [];
  if (r.sector_stance != null) {
    bars.push({ label: `Sector: ${r.sector || '?'}`, v: Number(r.sector_stance) });
  }
  if (r.asset_class_stance != null) {
    bars.push({ label: `Asset class: ${r.real_asset_class || '?'}`, v: Number(r.asset_class_stance) });
  }
  let styles = r.style_stances;
  if (typeof styles === 'string') { try { styles = JSON.parse(styles); } catch (_) { styles = []; } }
  if (Array.isArray(styles)) {
    for (const s of styles) {
      if (s && s.stance != null) bars.push({ label: `Style: ${s.label}`, v: Number(s.stance) });
    }
  }
  if (!bars.length) return '';
  const maxAbs = Math.max(...bars.map(b => Math.abs(b.v)), 0.001);
  const spans = bars.map(b => {
    const bh = Math.max(2, Math.round(Math.abs(b.v) / maxAbs * 6));
    const col = _stanceColor(b.v);
    const ti = `${b.label}: ${b.v >= 0 ? '+' : ''}${b.v.toFixed(2)} (live quad regime)`;
    return `<span title="${escapeHtml(ti)}" style="display:inline-block;width:2px;height:${bh}px;background:${col};vertical-align:bottom;"></span>`;
  }).join('<span style="display:inline-block;width:1px;"></span>');
  return `<div style="display:flex;justify-content:center;align-items:flex-end;gap:1px;height:7px;margin-top:1px;cursor:help;" `
       + `title="Sector / Asset class / Style — live quad-regime bullish(green)/bearish(red) read per dimension">${spans}</div>`;
}

function macroCellHtml(r) {
  const mv = r.macro_value;
  // macro_turn (ramp-proximity alert) is retired (TASK_126) — the sliding
  // window is continuous by construction, so there's no discrete "turn"
  // event to flag anymore.
  const conf = r.macro_conf != null ? r.macro_conf : null;
  const opacity = conf != null && conf < 0.6 ? Math.max(0.45, conf / 0.6) : 1.0;
  const sym = r.tos_symbol || '';
  // TASK_126: the old cur-month/next-month/cur-quarter 3-dot ramp indicator
  // is retired (month_now_net/month_next_net are no longer populated —
  // superseded by the sliding window shown in the hover tooltip/popover).
  const dotsLine = '';
  // Sparkline: one bar per available month, height ∝ |score|, color = direction
  const _sparksRaw = r.monthly_scores_json;
  const _sparks = Array.isArray(_sparksRaw) ? _sparksRaw
    : (typeof _sparksRaw === 'string'
        ? (() => { try { return JSON.parse(_sparksRaw); } catch(_e) { return null; } })()
        : null);
  let sparkLine = '';
  const _curIdx = _sparks ? _sparks.findIndex(s => s.is_current) : -1;
  const _sparksVis = _sparks && _curIdx >= 0 ? _sparks.slice(_curIdx) : _sparks;
  if (_sparksVis && _sparksVis.length >= 2) {
    const maxAbs = Math.max(..._sparksVis.map(s => Math.abs(s.score || 0)), 0.001);
    const bars = _sparksVis.map(s => {
      const sc  = s.score || 0;
      const bh  = Math.max(2, Math.round(Math.abs(sc) / maxAbs * 8));
      const col = sc > 0 ? '#16a34a' : sc < 0 ? '#dc2626' : '#9ca3af';
      // 2026-08-12 -- current-month bar previously got a border/outline to
      // mark it as "current". Both approaches put a second color directly
      // adjacent to (or, with border, cutting into) the bar's own fill on
      // all 4 sides -- at these 2-8px sizes that reads as a different color
      // entirely, not "red with a highlight". Dropped the ring styling
      // altogether: the ONLY difference from other bars now is 1px more
      // width, so its background color renders through exactly the same
      // `background:${col}` as every other bar. (Reported 3x: "first bar
      // red not visible" / "shows up entirely different from other bars".)
      const bw  = s.is_current ? '3' : '2';
      const ti  = `${s.label || ''} (${s.quad || ''}) ${sc >= 0 ? '+' : ''}${sc.toFixed(2)}${s.is_current ? ' — current month' : ''}`;
      return `<span title="${escapeHtml(ti)}" style="display:inline-block;width:${bw}px;height:${bh}px;background:${col};vertical-align:bottom;"></span>`;
    }).join('<span style="display:inline-block;width:1px;"></span>');
    sparkLine = `<div data-scorespop="${escapeHtml(sym)}" style="display:flex;justify-content:center;align-items:flex-end;gap:1px;height:9px;margin-top:1px;cursor:help;">${bars}</div>`;
  }
  const memberBars = _macroMemberBarsHtml(r);
  // MacroNet score (drv_macro_score.macronet) -- small muted number under the
  // badge/HOLD label so the raw signed score is visible at a glance without
  // needing to open the tooltip/popover. Same colour convention as the other
  // stance bars (green>0 / red<0 / grey=0). Confidence % (window weight
  // agreeing with technical direction, see macro_conf comment in
  // api/routers/dash.py) appended as "score - conf%" next to the score,
  // 2026-08-12. white-space:nowrap keeps it on one line at the wider size.
  const netVal = r.macronet != null ? Number(r.macronet) : null;
  const confPctTxt = conf != null ? ` - ${Math.round(conf * 100)}%` : '';
  const netHtml = netVal != null
    ? `<div style="font-size:9px;line-height:1;white-space:nowrap;color:${_stanceColor(netVal)};margin-top:1px;" title="MacroNet score: ${netVal >= 0 ? '+' : ''}${netVal.toFixed(4)}${conf != null ? ` — confidence ${Math.round(conf * 100)}%` : ''}">${netVal >= 0 ? '+' : ''}${netVal.toFixed(2)}<span style="color:#94a3b8;">${confPctTxt}</span></div>`
    : '';
  // Confidence-driven opacity used to sit on the ONE outer wrapper div that
  // held everything, including the conflict icon -- nested opacity can't be
  // un-dimmed by a child (CSS composites the whole dimmed subtree as a
  // group), so a low-confidence conflict row faded the ⚡ right along with
  // the badge, making the one thing you most need to see the hardest to
  // see. Fix: opacity now sits on its own inner wrapper(s) around the stuff
  // that SHOULD dim (badge/label, gap mark, net score, sparkline, member
  // bars); the conflict icon is a sibling of that wrapper, not a
  // descendant, so it stays at full opacity regardless.
  if (!mv || mv === 'HOLD') {
    const holdCls = mv ? 'color:#9ca3af' : 'color:#cbd5e1';
    const lbl = mv ? 'HOLD' : '—';
    return `<div style="cursor:help;text-align:center;" data-macropop="${escapeHtml(sym)}">`
      + `<div style="display:flex;align-items:center;justify-content:center;">`
      + `<span style="${holdCls};font-size:10px;opacity:${opacity.toFixed(2)};">${escapeHtml(lbl)}${_macroGapMark(r)}</span>`
      + _macroConflictSlotHtml(r)
      + `</div>`
      + `<div style="opacity:${opacity.toFixed(2)};">${netHtml}${dotsLine}${sparkLine}${memberBars}</div>`
      + `</div>`;
  }
  const d = actionDisplay(mv);
  const cls = d.colorCls || 'act-neutral';
  return `<div style="text-align:center;cursor:help;" data-macropop="${escapeHtml(sym)}">`
       + `<div style="display:flex;align-items:center;justify-content:center;">`
       + `<span style="opacity:${opacity.toFixed(2)};"><span class="act-badge ${cls}-tint" style="font-size:10px;padding:1px 5px;">${escapeHtml(d.code || mv)}</span>${_macroGapMark(r)}</span>`
       + _macroConflictSlotHtml(r)
       + `</div>`
       + `<div style="opacity:${opacity.toFixed(2)};">${netHtml}${dotsLine}${sparkLine}${memberBars}</div>`
       + `</div>`;
}

// Build tooltip text for a MACRO cell from macro_detail + macro_howto.
// TASK_126: Month/Quarter ramp sections replaced by the sliding look-ahead
// window mix (effective blend line + per-month table + tracking tag).
// Layout: Conflict warning (if any) → How to act → Window mix + per-month
//         table → Category drivers → Quarter (now/next-quarter blend during
//         the quarter's last month, 2026-08-12) → MacroNet
function _macroTooltip(r) {
  let det = r.macro_detail;
  if (typeof det === 'string') { try { det = JSON.parse(det); } catch (_) { det = null; } }
  if (!det) return r.macro_value ? `MacroNet → ${r.macro_value}` : '';
  const lines = [];

  // ── Tracking-vs-score conflict (2026-08-12) ────────────────────────────────
  // det.tracking_conflict = true when the FINAL macronet sign disagrees with
  // the technical direction (price vs 50 DMA) — a stronger, single-number
  // check than "does any window month agree" (that's what confidence now
  // measures, see macro_conf comment in api/routers/dash.py).
  if (det.tracking_conflict === true) {
    lines.push('⚠ CONFLICT: MacroNet direction disagrees with technical direction (price vs 50 DMA)');
    lines.push('');
  }

  // ── How to act ────────────────────────────────────────────────────────────
  if (r.macro_howto) {
    lines.push('HOW TO ACT');
    lines.push(r.macro_howto);
    lines.push('');
  }

  // ── Window mix ─────────────────────────────────────────────────────────────
  const win = det.window || {};
  const months = win.months || [];
  if (months.length) {
    lines.push(`WINDOW (${win.h ?? '?'}d look-ahead, coverage ${win.coverage_pct ?? '?'}%${win.fallback ? ' — FALLBACK' : ''})`);
    const mixStr = months.map(m => `${m.m} ${Math.round(m.w * 100)}%`).join(' · ');
    lines.push(`  ${mixStr}`);
    months.forEach(m => {
      lines.push(`  ${m.m} (Quad ${m.quad ?? '?'})  w=${(m.w * 100).toFixed(1)}%  stance=${m.stance}`);
    });
    const eff = win.eff || {};
    const effStr = ['q1', 'q2', 'q3', 'q4']
      .map(k => `${k.toUpperCase()} ${eff[k] ?? 0}%`).join(' · ');
    lines.push(`  Effective mix: ${effStr}`);
    if (win.tracking) {
      lines.push(`  Tracking: ${win.tracking}`);
    } else {
      lines.push('  Tracking: fighting the quad path (no forward month confirms it)');
    }
    const nv = win.near_vs_far || {};
    if (nv.override && nv.override !== 'none') {
      lines.push(`  Near/far agreement → ${nv.override} (near month=${nv.near}, far-other months=${nv.far})`);
    }
  }

  // ── Category / Subcategory / Outlook drivers ──────────────────────────────
  const mems = det.memberships || [];
  if (mems.length) {
    lines.push('');
    lines.push('CATEGORY DRIVERS');
    mems.forEach(m => {
      const st = m.stance > 0 ? '+1' : m.stance < 0 ? '-1' : ' 0';
      const cat = m.category ? `${m.category} / ${m.sub_cat || m.label}` : m.label;
      lines.push(`  ${cat}  (×${m.weight})  →  ${m.outlook || '—'} [${st}]`);
    });
  }

  // ── Quarter ────────────────────────────────────────────────────────────────
  // det.quarter_window (etl/derive_macro.py, 2026-08-12) is the authoritative
  // source: current-quarter leg always shown; the next-quarter leg is ALSO
  // always shown once its forecast exists (2026-08-12 follow-up), labeled
  // "Next Qtr (Quad N)" so it's identifiable even at w=0% before the last-
  // month fade actually starts blending it in. Falls back to the legacy
  // single-anchor det.quarter only when a derive hasn't populated
  // drv_macro_score yet.
  const qw = det.quarter_window;
  if (qw && qw.cur) {
    const fading = qw.next && qw.next.w > 0;
    lines.push('');
    lines.push(`QUARTER${fading ? ' WINDOW (fading into next quarter)' : ' (current quarter only)'}`);
    lines.push(`  ${qw.cur.label} (Quad ${qw.cur.quad ?? '?'})  w=${(qw.cur.w * 100).toFixed(1)}%  stance=${qw.cur.stance}`);
    if (qw.next) {
      lines.push(`  Next Qtr (Quad ${qw.next.quad ?? '?'}) — ${qw.next.label}  w=${(qw.next.w * 100).toFixed(1)}%  stance=${qw.next.stance}`);
    }
    lines.push(`  → Qtr=${det.quarterly_score ?? '?'}${qw.dtb != null ? `  (${qw.dtb}d left in quarter)` : ''}`);
  } else {
    const qtr = det.quarter || {};
    if (qtr.now) {
      lines.push('');
      lines.push('QUARTER (fixed top-level anchor, no blend)');
      const qtrLine = `  ${qtr.now}  →  Qtr=${det.quarterly_score ?? '?'}`;
      const dtbStr = qtr.dtb != null ? `  (${qtr.dtb}d left)` : '';
      lines.push(qtrLine + dtbStr);
    }
  }

  // ── MacroNet ──────────────────────────────────────────────────────────────
  // Uses quarterly_score/monthly_score (the values actually fed into
  // macro_net, from drv_macro_score) -- NOT det.quarter.Qtr, which is a
  // separate, differently-scaled "Equities outlook" indicator computed by
  // the older live engine and no longer what drives the real combine.
  lines.push('');
  lines.push(`MacroNet = ${det.a}×Qtr(${det.quarterly_score ?? '?'}) + ${det.b}×M_window(${det.monthly_score ?? '?'}) = ${det.macro_net}  →  ${det.vocab}`);

  return lines.join('\n');
}

// Rich HTML popover for a MACRO cell — reuses #sourcePop / _showDataPop.
// F2: macro_detail/macro_howto are no longer shipped with every grid row —
// they're lazy-fetched (see showMacroPop / _macroDetailCache below). `loading`
// renders a "Loading…" placeholder on first hover, before the fetch resolves.
// TASK_126: Cur/Nxt Month + ramp-blend cards replaced by the sliding
// look-ahead window's per-month table + effective mix + tracking tag.
function _buildMacroPopHtml(r, loading) {
  let det = r.macro_detail;
  if (typeof det === 'string') { try { det = JSON.parse(det); } catch (_) { det = null; } }
  const mv   = r.macro_value || '—';
  const conf = r.macro_conf != null ? Math.round(r.macro_conf * 100) : null;
  const sym  = r.tos_symbol || '—';

  const _quadDistBar = dist => {
    if (!dist || !dist.length) return '';
    const segs = dist.map(x =>
      `<div style="width:${x.pct}%;background:${_quadColor(x.quad)};height:100%;" title="${escapeHtml(x.quad)} ${x.pct}%"></div>`
    ).join('');
    return `<div style="display:inline-flex;width:110px;height:7px;border-radius:3px;overflow:hidden;border:1px solid #e2e8f0;vertical-align:middle;margin-right:6px;">${segs}</div>`;
  };
  const _quadDistBreakdown = dist =>
    (dist || []).map(x =>
      `<span style="color:${_quadColor(x.quad)};font-weight:600;">${escapeHtml(x.quad)}</span> ${x.pct}%`
    ).join(' &nbsp;·&nbsp; ');
  // {q1:58,q2:10,...} -> [{quad:'Quad 1',pct:58}, ...] (zero legs dropped)
  const _effToDistArr = eff => !eff ? [] : ['q1', 'q2', 'q3', 'q4']
    .map((k, i) => ({ quad: `Quad ${i + 1}`, pct: eff[k] || 0 }))
    .filter(x => x.pct > 0);

  const _vocabColor = v => {
    if (!v) return '#9ca3af';
    const u = v.toUpperCase();
    if (u === 'SA')  return '#991b1b';
    if (u === 'STM') return '#ef4444';
    if (u === 'BS')  return '#22c55e';
    if (u === 'BM')  return '#14532d';
    return '#9ca3af';
  };
  const _sigColor     = v => v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
  const _coloredQuad  = q => q ? `<span style="color:${_quadColor(q)};font-weight:600;">${escapeHtml(q)}</span>` : '—';
  const _coloredVocab = v => v ? `<span style="color:${_vocabColor(v)};font-weight:700;">${escapeHtml(v)}</span>` : '—';

  const mvColor = _vocabColor(mv !== '—' ? mv : null);
  let h = `<div class="sp-title">${escapeHtml(sym)} &mdash; <span style="color:${mvColor};font-weight:700;">${escapeHtml(mv)}</span></div>`;

  if (!r.sector) {
    h += `<div style="color:#b45309;background:#fffbeb;border:1px solid #fde68a;border-radius:4px;`
       + `padding:3px 6px;font-size:9.5px;margin-bottom:6px;">`
       + `&#9888; No sector classification for ${escapeHtml(sym)} in ref_sector — this score reflects `
       + `Asset Class + style factors only. See Ref &rarr; ref_sector, or GET /api/admin/quad-data-gaps.`
       + `</div>`;
  }

  // Tracking-vs-score conflict banner (2026-08-12) — r.macro_conflict is on
  // the grid row already (api/routers/dash.py), so this shows even before
  // the lazy detail fetch resolves. See _macroConflictMark for the column
  // glyph and the CONFLICT line in _macroTooltip for the plain-text version.
  if (r.macro_conflict === true) {
    h += `<div style="color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:4px;`
       + `padding:3px 6px;font-size:9.5px;margin-bottom:6px;font-weight:600;">`
       + `&#9889; CONFLICT: MacroNet score disagrees with technical direction (price vs 50-day average).`
       + `</div>`;
  }

  if (!det) {
    h += loading
      ? `<div style="color:#94a3b8;font-size:10px;">Loading&hellip;</div>`
      : `<div style="color:#94a3b8;font-size:10px;">No detail available.</div>`;
    return h;
  }

  const mems = det.memberships || [];
  const win  = det.window || {};
  const wmonths = win.months || [];
  const qtr  = det.quarter || {};
  const qQuad = qtr.quad_label || qtr.now;
  const qDtb  = qtr.dtb;

  const netVal = det.macro_net != null ? Number(det.macro_net) : (r.macronet != null ? Number(r.macronet) : null);
  const Mv = det.monthly_score != null ? Number(det.monthly_score) : (r.monthly_score != null ? Number(r.monthly_score) : null);
  const Qv = det.quarterly_score != null ? Number(det.quarterly_score) : (r.quarterly_score != null ? Number(r.quarterly_score) : null);
  const wQtr = det.a ?? 0.05, wMo = det.b ?? 0.95;
  const qtrContrib = Qv != null ? wQtr * Qv : null;
  const moContrib  = Mv != null ? wMo * Mv : null;
  const macroFormulaHtml =
    `${wQtr}×Qtr(<span style="color:${Qv != null ? _sigColor(Qv) : '#475569'}">${Qv != null ? Qv.toFixed(2) : '?'}</span>) `
    + (qtrContrib != null ? `<span style="color:#94a3b8;">=${qtrContrib >= 0 ? '+' : ''}${qtrContrib.toFixed(4)}</span> ` : '')
    + `+ ${wMo}×M_window(<span style="color:${Mv != null ? _sigColor(Mv) : '#475569'}">${Mv != null ? Mv.toFixed(3) : '?'}</span>) `
    + (moContrib != null ? `<span style="color:#94a3b8;">=${moContrib >= 0 ? '+' : ''}${moContrib.toFixed(4)}</span> ` : '')
    + `= <span style="color:${netVal != null ? _sigColor(netVal) : '#475569'};font-weight:700;">${netVal != null ? netVal.toFixed(4) : '?'}</span>`;

  h += '<table>';

  // ── Window per-month table (nearest-first) -- built here but inserted
  // BELOW the Category Drivers (monthly) table and ABOVE the Quarter table,
  // per user request, rather than appended immediately.
  let windowHtml = '';
  if (wmonths.length) {
    windowHtml += `<tr><td class="sp-sec" colspan="2">Window (${win.h ?? '?'}d look-ahead`
       + (win.coverage_pct != null ? `, coverage ${win.coverage_pct}%` : '')
       + (win.fallback ? ' — <span style="color:#f97316;">fallback</span>' : '') + ')</td></tr>';
    windowHtml += `<tr><td colspan="2" style="padding:2px 0 4px;">`;
    let _mSum = 0;
    let _mSumKnown = true;
    wmonths.forEach(m => {
      const s = m.stance;
      const gc = s > 0 ? '#16a34a' : s < 0 ? '#dc2626' : '#9ca3af';
      const gl = s > 0 ? '▲' : s < 0 ? '▼' : '—';
      let contribHtml = '';
      if (s != null && m.w != null) {
        const contrib = m.w * s;
        _mSum += contrib;
        const cc = contrib > 0 ? '#16a34a' : contrib < 0 ? '#dc2626' : '#9ca3af';
        contribHtml = `<span style="color:#94a3b8;"> &times; </span>`
          + `<span style="color:${cc};font-weight:700;width:56px;display:inline-block;">`
          + `${contrib >= 0 ? '+' : ''}${contrib.toFixed(4)}</span>`;
      } else {
        _mSumKnown = false;
      }
      windowHtml += `<div style="display:flex;align-items:center;gap:5px;font-size:9px;padding:1px 0;">`
         + `<span style="color:${_quadColor('Quad ' + m.quad)};font-weight:700;width:70px;">${escapeHtml(_shortMonth(m.m))} (Q${m.quad ?? '?'})</span>`
         + `<span style="color:#64748b;width:44px;">w=${(m.w * 100).toFixed(1)}%</span>`
         + `<span style="color:${gc};width:56px;">${gl} ${s != null ? s.toFixed(4) : '?'}</span>`
         + contribHtml
         + `</div>`;
    });
    if (wmonths.length > 1 && _mSumKnown) {
      windowHtml += `<div style="display:flex;align-items:center;gap:5px;font-size:9px;padding:2px 0 0;border-top:1px solid #e2e8f0;margin-top:2px;">`
         + `<span style="width:70px;"></span><span style="width:44px;"></span><span style="width:56px;"></span>`
         + `<span style="color:#94a3b8;"> &Sigma; = </span>`
         + `<span style="color:${_sigColor(_mSum)};font-weight:700;">M_window = ${_mSum >= 0 ? '+' : ''}${_mSum.toFixed(4)}</span>`
         + `</div>`;
    }
    windowHtml += `</td></tr>`;
  }

  // ── Window mix tail (effective distribution / tracking / near-far) and
  // the MacroNet formula / confidence / how-to-act -- built here but
  // appended at the BOTTOM of the popup (after Category Drivers/Quarter),
  // per user request, so the per-month math and driver tables read first.
  let mixTailHtml = '';
  if (wmonths.length) {
    const effArr = _effToDistArr(win.eff);
    if (effArr.length) {
      mixTailHtml += `<tr><td colspan="2" style="padding:2px 0 4px;">`
         + `<span style="font-size:8px;color:#94a3b8;">Effective mix&nbsp;</span>`
         + `${_quadDistBar(effArr)}<span style="font-size:9px;color:#475569;">${_quadDistBreakdown(effArr)}</span>`
         + `</td></tr>`;
    }
    // One checkmark/x per window month (m.agrees, from etl/derive_macro.py)
    // instead of naming only the single nearest confirming month -- lets you
    // see at a glance which months back up the current technical direction
    // and which don't. Month/quad text keeps the usual quad palette; the
    // mark itself is always green (agrees) / red (disagrees) / gray (no
    // technical direction to compare against).
    let trackingHtml;
    const _anyDir = wmonths.some(m => m.agrees != null);
    if (!_anyDir) {
      trackingHtml = `<span style="color:#94a3b8;">&#8212; no clear technical direction to compare</span>`;
    } else {
      trackingHtml = wmonths.map(m => {
        const qColor = _quadColor('Quad ' + (m.quad ?? '?'));
        const mark = m.agrees === true  ? `<span style="color:#16a34a;">&#10003;</span>`
                   : m.agrees === false ? `<span style="color:#dc2626;">&#10007;</span>`
                   : `<span style="color:#94a3b8;">&#8212;</span>`;
        return `<span style="display:inline-flex;align-items:center;gap:2px;margin-right:8px;white-space:nowrap;">`
          + `${mark} <span style="color:${qColor};font-weight:700;">${escapeHtml(_shortMonth(m.m))} (Q${m.quad ?? '?'})</span></span>`;
      }).join('');
      if (!win.tracking) {
        trackingHtml += `<div style="color:#d97706;font-size:8px;margin-top:1px;">`
          + `&#9888; fighting the quad path — no month confirms the current technical direction</div>`;
      }
    }
    mixTailHtml += `<tr><td class="k" style="font-size:9px;color:#475569;white-space:nowrap;">Tracking`
       + `<span style="font-size:7.5px;color:#94a3b8;font-weight:400;"> (checked price against 50 DMA)</span></td>`
       + `<td class="v" style="font-size:9px;">${trackingHtml}</td></tr>`;
    const nv = win.near_vs_far || {};
    if (nv.override && nv.override !== 'none') {
      mixTailHtml += `<tr><td class="k" style="font-size:9px;color:#475569;">Near/far</td>`
         + `<td class="v" style="font-size:9px;">agree &rarr; ${_coloredVocab(nv.override)} `
         + `(near month ${nv.near != null ? nv.near.toFixed(2) : '?'}, far-other months ${nv.far != null ? nv.far.toFixed(2) : '?'})</td></tr>`;
    }
  }

  let macroFooterHtml = `<tr><td class="k">MacroNet</td><td class="v" style="font-size:9px;">${macroFormulaHtml} → ${_coloredVocab(mv)}</td></tr>`;
  if (conf != null) {
    const confNum = r.macro_conf != null ? Number(r.macro_conf) : 0;
    const confColor = confNum >= 0.7 ? '#16a34a' : confNum >= 0.4 ? '#d97706' : '#dc2626';
    macroFooterHtml += `<tr><td class="k">Confidence</td><td class="v" style="color:${confColor};font-weight:700;">${conf}%`
       + `<span style="color:#94a3b8;font-weight:400;font-size:8px;"> (window weight agreeing with technical direction)</span></td></tr>`;
  }
  if (det.tracking_conflict === true) {
    macroFooterHtml += `<tr><td class="k">Tracking</td><td class="v" style="color:#dc2626;font-weight:700;">`
       + `&#9889; CONFLICT<span style="color:#94a3b8;font-weight:400;font-size:8px;"> (MacroNet vs. price/50-DMA direction disagree)</span></td></tr>`;
  }

  if (r.macro_howto) {
    const howtoTrimmed = r.macro_howto.replace(/\s*Technical\/Sources.*$/i, '').trim();
    if (howtoTrimmed) {
      // Color the two structured tokens embedded in the free-text howto:
      // "(Quad N)" via the usual quad palette, and action codes "(SA)" /
      // "(STM)" / "(BS)" / "(BM)" / "(HOLD)" via the same vocab colors used
      // for the ACTION badge elsewhere in this popup.
      const howtoHtml = escapeHtml(howtoTrimmed)
        .replace(/\(Quad (\d)\)/g, (_m, q) =>
          `(<span style="color:${_quadColor('Quad ' + q)};font-weight:700;">Quad ${q}</span>)`)
        .replace(/\((SA|STM|BS|BM|HOLD)\)/g, (_m, code) => `(${_coloredVocab(code)})`);
      macroFooterHtml += `<tr><td class="sp-sec" colspan="2">How to Act</td></tr>`;
      macroFooterHtml += `<tr><td colspan="2" style="font-size:10px;color:#374151;padding:2px 0 5px;">${howtoHtml}</td></tr>`;
    }
  }

  // ── Category drivers — full per-window-month breakdown (TASK_126 follow-
  // up): one column per window month instead of just the nearest one, so
  // the visible per-membership math reconciles exactly with each month's
  // stance shown in the Window section above (det.month_breakdown, same
  // _membership_net math as the real derive). Falls back to the old
  // nearest-month-only view if month_breakdown isn't present (e.g. a stale
  // cached API response).
  const _ocOf  = v => { const u = (v || '').toUpperCase(); return u === 'BULLISH' ? '#1c6c30' : u === 'BEARISH' ? '#8c1d1d' : u ? '#5b4900' : '#9ca3af'; };
  const _olLbl = v => { if (!v) return '—'; const u = v.toUpperCase(); return u === 'BULLISH' ? 'Bullish' : u === 'BEARISH' ? 'Bearish' : v; };
  const _stOf  = v => { const u = (v || '').toUpperCase(); return u === 'BULLISH' ? 1 : u === 'BEARISH' ? -1 : 0; };

  const mb = det.month_breakdown;
  if (mb && mb.rows && mb.rows.length && mb.months && mb.months.length) {
    h += `<tr><td class="sp-sec" colspan="2">Category Drivers</td></tr>`;
    h += `<tr><td colspan="2" style="padding:2px 0 4px;overflow-x:auto;">`;
    h += `<table style="border-collapse:collapse;font-size:8.5px;width:100%;">`;
    h += '<tr><td></td>' + mb.months.map((mk, i) => {
      const wm = wmonths[i] || {};
      const q = wm.quad ?? '?';
      return `<td style="padding:1px 4px;text-align:right;white-space:nowrap;">`
           + `<span style="color:${_quadColor('Quad ' + q)};font-weight:700;">${escapeHtml(_shortMonth(mk))}</span>`
           + `<br><span style="color:#94a3b8;">(Q${q})</span></td>`;
    }).join('') + '</tr>';
    const colTotals = new Array(mb.months.length).fill(0);
    const colKnown = new Array(mb.months.length).fill(true);
    mb.rows.forEach(r => {
      const cat = r.category
        ? `${escapeHtml(r.category)} / ${escapeHtml(r.sub_cat || r.label || '')}`
        : escapeHtml(r.label || '');
      h += `<tr><td style="padding:1px 4px 1px 0;max-width:110px;white-space:normal;word-break:break-word;color:#475569;">`
         + `${cat} <span style="color:#94a3b8;">(&times;${r.weight})</span></td>`
         + r.cells.map((c, i) => {
             if (c != null) colTotals[i] += c; else colKnown[i] = false;
             const cc = c > 0 ? '#16a34a' : c < 0 ? '#dc2626' : '#9ca3af';
             return `<td style="padding:1px 4px;text-align:right;color:${cc};">`
                  + `${c != null ? (c >= 0 ? '+' : '') + c.toFixed(2) : '—'}</td>`;
           }).join('') + '</tr>';
    });
    h += '<tr style="border-top:1px solid #e2e8f0;"><td style="padding:2px 4px 0 0;color:#94a3b8;">&Sigma;</td>'
       + colTotals.map((t, i) => {
           const tc = t > 0 ? '#16a34a' : t < 0 ? '#dc2626' : '#9ca3af';
           return `<td style="padding:2px 4px 0;text-align:right;font-weight:700;color:${tc};">`
                + `${colKnown[i] ? (t >= 0 ? '+' : '') + t.toFixed(4) : '?'}</td>`;
         }).join('') + '</tr>';
    h += '</table></td></tr>';
  } else if (mems.length) {
    const nearestQuad = wmonths.length ? `Quad ${wmonths[0].quad ?? '?'}` : null;
    h += `<tr><td class="sp-sec" colspan="2">Category Drivers`
       + (nearestQuad ? ` <span style="color:${_quadColor(nearestQuad)};font-size:9px;font-weight:400;">${escapeHtml(nearestQuad)}</span>` : '')
       + `</td></tr>`;
    let score = 0;
    for (const m of mems) {
      const ol = m.outlook;
      const st = _stOf(ol);
      score += st * (m.weight || 1);
      const stSym   = st > 0 ? '▲' : st < 0 ? '▼' : '→';
      const stColor = st > 0 ? '#16a34a' : st < 0 ? '#dc2626' : '#9ca3af';
      const cat = m.category
        ? `${escapeHtml(m.category)} / ${escapeHtml(m.sub_cat || m.label || '')}`
        : escapeHtml(m.label || '');
      h += `<tr><td class="k" style="font-size:9px;max-width:140px;white-space:normal;word-break:break-word;">${cat}</td>`
         + `<td class="v" style="font-size:9px;white-space:nowrap;">`
         + `<span style="color:${stColor}">${stSym}</span> `
         + `<span style="color:${_ocOf(ol)};font-weight:600;">${escapeHtml(_olLbl(ol))}</span>`
         + ` <span style="color:#94a3b8;">(×${m.weight})</span></td></tr>`;
    }
    const scColor = score > 0 ? '#16a34a' : score < 0 ? '#dc2626' : '#9ca3af';
    h += `<tr><td class="k" style="font-size:9px;color:#475569;">Score</td>`
       + `<td class="v" style="color:${scColor};font-weight:700;font-size:11px;">${score > 0 ? '+' : ''}${score.toFixed(2)}</td></tr>`;
  }

  h += windowHtml;

  // Quarter section (2026-08-12) — authoritative from det.quarter_window
  // (etl/derive_macro.py): current-quarter leg always shown; the next-
  // quarter leg is ALSO always shown once its forecast exists (2026-08-12
  // follow-up: "add next quarter column, fine if all zeros"), labeled
  // "Next Qtr (Quad N)" so it's identifiable before it's actually blended
  // in — its weight only leaves 0% during the current quarter's last
  // calendar month. Same row/summary layout as the Window section above,
  // including its 9px final-score font, so Quarter and Month read as the
  // same kind of number (was 11px here before).
  const qw = det.quarter_window;
  if (qw && qw.cur) {
    const qLegs = [qw.cur, ...(qw.next ? [qw.next] : [])];
    const fading = qw.next && qw.next.w > 0;
    h += `<tr><td class="sp-sec" colspan="2">Quarter${fading ? ' (fading into next quarter)' : ''}`
       + `${qw.dtb != null ? ` <span style="color:#94a3b8;font-size:9px;font-weight:400;">(${qw.dtb}d left)</span>` : ''}</td></tr>`;
    h += `<tr><td colspan="2" style="padding:2px 0 4px;">`;
    let _qSum = 0;
    qLegs.forEach((leg, i) => {
      const s = leg.stance;
      const gc = s > 0 ? '#16a34a' : s < 0 ? '#dc2626' : '#9ca3af';
      const gl = s > 0 ? '▲' : s < 0 ? '▼' : '—';
      const contrib = leg.w * s;
      _qSum += contrib;
      const cc = contrib > 0 ? '#16a34a' : contrib < 0 ? '#dc2626' : '#9ca3af';
      const labelTxt = i === 1
        ? `Next Qtr (Quad ${leg.quad ?? '?'}) — ${leg.label}`
        : `${leg.label} (Quad ${leg.quad ?? '?'})`;
      h += `<div style="display:flex;align-items:center;gap:5px;font-size:9px;padding:1px 0;">`
         + `<span style="color:${_quadColor('Quad ' + leg.quad)};font-weight:700;width:130px;">${escapeHtml(labelTxt)}</span>`
         + `<span style="color:#64748b;width:44px;">w=${(leg.w * 100).toFixed(1)}%</span>`
         + `<span style="color:${gc};width:56px;">${gl} ${s != null ? s.toFixed(4) : '?'}</span>`
         + `<span style="color:#94a3b8;"> &times; </span>`
         + `<span style="color:${cc};font-weight:700;width:56px;display:inline-block;">${contrib >= 0 ? '+' : ''}${contrib.toFixed(4)}</span>`
         + `</div>`;
    });
    if (qLegs.length > 1) {
      h += `<div style="display:flex;align-items:center;gap:5px;font-size:9px;padding:2px 0 0;border-top:1px solid #e2e8f0;margin-top:2px;">`
         + `<span style="width:130px;"></span><span style="width:44px;"></span><span style="width:56px;"></span>`
         + `<span style="color:#94a3b8;"> &Sigma; = </span>`
         + `<span style="color:${_sigColor(_qSum)};font-weight:700;">Qtr_window = ${_qSum >= 0 ? '+' : ''}${_qSum.toFixed(4)}</span>`
         + `</div>`;
    }
    h += `</td></tr>`;
  } else if (mems.length) {
    // Legacy fallback — only reachable if a derive hasn't populated
    // drv_macro_score.detail.quarter_window yet.
    h += `<tr><td class="sp-sec" colspan="2">Quarter${qQuad ? ` <span style="color:${_quadColor(qQuad)};font-size:9px;font-weight:400;">${escapeHtml(qQuad)}</span>` : ''}`
       + `${qDtb != null ? ` <span style="color:#94a3b8;font-size:9px;">(${qDtb}d left)</span>` : ''}</td></tr>`;
    let qScore = 0;
    for (const m of mems) {
      const ol = m.qtr_outlook;
      const st = _stOf(ol);
      qScore += st * (m.weight || 1);
      const stSym   = st > 0 ? '▲' : st < 0 ? '▼' : '→';
      const stColor = st > 0 ? '#16a34a' : st < 0 ? '#dc2626' : '#9ca3af';
      const cat = m.category
        ? `${escapeHtml(m.category)} / ${escapeHtml(m.sub_cat || m.label || '')}`
        : escapeHtml(m.label || '');
      h += `<tr><td class="k" style="font-size:9px;max-width:140px;white-space:normal;word-break:break-word;">${cat}</td>`
         + `<td class="v" style="font-size:9px;white-space:nowrap;">`
         + `<span style="color:${stColor}">${stSym}</span> `
         + `<span style="color:${_ocOf(ol)};font-weight:600;">${escapeHtml(_olLbl(ol))}</span>`
         + ` <span style="color:#94a3b8;">(×${m.weight})</span></td></tr>`;
    }
    const qScColor = qScore > 0 ? '#16a34a' : qScore < 0 ? '#dc2626' : '#9ca3af';
    h += `<tr><td class="k" style="font-size:9px;color:#475569;">Score</td>`
       + `<td class="v" style="color:${qScColor};font-weight:700;font-size:9px;">${qScore > 0 ? '+' : ''}${qScore.toFixed(2)}</td></tr>`;
  }

  h += mixTailHtml + macroFooterHtml;
  h += '</table>';
  return h;
}

// Monthly scores popover — triggered by hovering the sparkline bars.
// Shows current month + future only (no past months).
function _buildScoresPopHtml(r) {
  const sym = r.tos_symbol || '—';
  const _sparksRaw = r.monthly_scores_json;
  const all = Array.isArray(_sparksRaw) ? _sparksRaw
    : (typeof _sparksRaw === 'string'
        ? (() => { try { return JSON.parse(_sparksRaw); } catch (_) { return null; } })()
        : null);
  if (!all || !all.length) return `<div class="sp-title">${escapeHtml(sym)} — Monthly Scores</div><div style="color:#94a3b8;font-size:10px;">No data.</div>`;

  const curIdx = all.findIndex(s => s.is_current);
  const rows = curIdx >= 0 ? all.slice(curIdx) : all;

  const _sigColor = v => v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
  let h = `<div class="sp-title">${escapeHtml(sym)} — Monthly Scores</div><table>`;
  h += `<tr><td class="sp-sec" colspan="2">Current &amp; Forward Months</td></tr>`;
  for (const s of rows) {
    const sc  = s.score != null ? Number(s.score) : null;
    const col = sc == null ? '#9ca3af' : _sigColor(sc);
    const gl  = sc == null ? '—' : sc > 0 ? '▲' : sc < 0 ? '▼' : '→';
    const scHtml = sc != null
      ? `<span style="color:${col};font-weight:700;">${sc >= 0 ? '+' : ''}${sc.toFixed(2)}</span>`
      : '<span style="color:#9ca3af;">—</span>';
    const isCur = !!s.is_current;
    const qcol  = s.quad ? _quadColor(s.quad) : '#9ca3af';
    const distSegs = [
      {q:'Quad 1',pct:s.q1||0},{q:'Quad 2',pct:s.q2||0},
      {q:'Quad 3',pct:s.q3||0},{q:'Quad 4',pct:s.q4||0},
    ].filter(x => x.pct > 0);
    const distBar = distSegs.length
      ? `<span style="display:inline-flex;width:50px;height:4px;border-radius:2px;overflow:hidden;vertical-align:middle;margin-left:4px;border:1px solid #e2e8f0;">`
        + distSegs.map(x => `<div style="width:${x.pct}%;background:${_quadColor(x.q)};height:100%;" title="${escapeHtml(x.q)} ${x.pct}%"></div>`).join('')
        + `</span>`
      : '';
    h += `<tr${isCur ? ' style="background:#f1f5f9;"' : ''}>`
       + `<td class="k" style="font-size:9px;${isCur ? 'font-weight:700;' : ''}padding:1px 4px;">${escapeHtml(s.label || '')}</td>`
       + `<td class="v" style="font-size:9px;padding:1px 4px;white-space:nowrap;">`
       + `<span style="color:${qcol};font-weight:600;font-size:8px;">${escapeHtml(s.quad || '')}</span>`
       + distBar
       + `&nbsp;<span style="color:${col};">${gl}</span>&nbsp;${scHtml}`
       + `</td></tr>`;
  }
  h += '</table>';
  return h;
}

// 2026-08-10 -- MACRO Regime Band (#macroBand) removed entirely per user
// request ("actionable screen -> remove REGIME panel altogether"); its
// Asset Class/Sector/Style filter chips were relocated into
// #moreFiltersPanel (still populated by renderAssetClassSummary() etc.,
// unchanged) rather than deleted -- see web/actionable.html's
// #moreFiltersPanel comment. _buildQuadBandPopHtml (the band's own rich
// quad-factor popover, keyed off state.quadFactors from the now-removed
// /api/quad/band-factors fetch) and _regimeVerdictHtml (the band's same-day
// risk-gauge verdict badge) were both dedicated solely to that band's own
// rendering, so they're removed too, not just left as dead code. The
// "Quads" side panel (#quadOutlookBody, loadQuadOutlook/
// _renderQuadOutlookPanel, plus their _shortMonthLbl/_shortQtrLbl/
// _quadShort/_effectiveQuad/_qdLbl/_qLbl helpers) was kept here for a
// while after that removal, then MOVED to web/app.js entirely (2026-09-01,
// user request: "Move the quads side panel from actionable to dashboard
// side panel") -- it's a Dashboard-only panel now, not a shared one; see
// app.js's own copy for the current implementation. _quadColor stays here
// (duplicated in app.js too) since the MACRO column popover below still
// needs it independently of the Quads panel.
function _msGlyph(score) {
  const s = score == null ? null : Number(score);
  if (s > 0) return '<span style="font-size:6px;color:#16a34a;line-height:1;vertical-align:middle;">▲</span>';
  if (s < 0) return '<span style="font-size:6px;color:#dc2626;line-height:1;vertical-align:middle;">▼</span>';
  return '';
}
// Symbol-name color: rr_outlook (BULLISH/BEARISH/NEUTRAL) when available,
// else falls back to today's pct_change direction.
function _symOutlookColor(row) {
  if (row.rr_outlook && window.outlookColor) {
    const c = window.outlookColor(row.rr_outlook);
    if (c && c !== 'inherit') return c;
  }
  const pct = row.pct_change != null ? Number(row.pct_change) : null;
  if (pct != null && pct > 0.001)  return '#1d9e75';
  if (pct != null && pct < -0.001) return '#d4537e';
  return 'inherit';
}
// "2026-07" -> "Jul" -- short label for month-keyed values in the MACRO
// popup (Window table, Category Drivers header, Tracking checklist).
const _MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function _shortMonth(ym) {
  if (!ym) return ym;
  const parts = String(ym).split('-');
  if (parts.length !== 2) return ym;
  const idx = parseInt(parts[1], 10) - 1;
  return _MONTH_ABBR[idx] || ym;
}
function _quadColor(q) {
  if (!q) return '#9ca3af';
  if (/1/.test(q)) return '#2f9e2f'; // Q1 = bullish/growth
  if (/2/.test(q)) return '#1f7af2'; // Q2 = neutral/up
  if (/3/.test(q)) return '#e07c1a'; // Q3 = slowing
  if (/4/.test(q)) return '#d83a3a'; // Q4 = risk-off
  return '#9ca3af';
}


// _econActualCellHtml/_wireEconActualEdit/loadSideEcon/loadSideSymbolEarnings/
// loadSidePanels (Actionable's own Econ Indicators/Earnings side-panel copies)
// REMOVED (2026-09-01, user request: "remove the side panel from actionable
// screen altogether") -- see the Portfolio Mix removal comment below for the
// full list of what moved/already existed on Dashboard. Dashboard's own
// Econ Indicators (#econBody, web/app.js) and Symbol/Earnings
// (#nearEarningsBody, separate independent implementation) panels are
// unaffected -- always two independent per-page implementations, not a
// shared module, per this block's own prior comment.
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

// ── Column visibility (TASK_105 U1/U4) ──────────────────────────────────────
// Single dynamic <style> tag drives visibility for every data-col cell —
// cheaper than looping every row/cell on toggle, and works for the H column
// too (folded in here as 'h', shown only when show_hidden is on — U4).
function applyColumnVisibility() {
  let styleEl = document.getElementById('colVisibilityStyle');
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'colVisibilityStyle';
    document.head.appendChild(styleEl);
  }
  const hidden = new Set(state.hiddenCols);
  if (!state.filters.show_hidden) hidden.add('h');
  const sel = Array.from(hidden).map(id => `.act-grid [data-col="${id}"]`).join(', ');
  styleEl.textContent = sel ? `${sel} { display: none; }` : '';
}

function _renderColMenu() {
  const pop = $('colMenuPop');
  if (!pop) return;
  let html = '<div class="sp-title">Columns</div>'
    + '<div style="display:flex;flex-direction:column;gap:1px;max-height:320px;overflow-y:auto;">';
  for (const c of TOGGLEABLE_COLS) {
    const checked = state.hiddenCols.has(c.id) ? '' : ' checked';
    html += `<label style="display:flex;align-items:center;gap:6px;font-size:11px;padding:2px 4px;cursor:pointer;white-space:nowrap;">`
          + `<input type="checkbox" data-col-toggle="${c.id}"${checked}> ${escapeHtml(c.label)}</label>`;
  }
  html += '</div>';
  pop.innerHTML = html;
}

// Shared positioning for click-toggled popovers (columns manager, legend) —
// same fixed-position-below-anchor logic as the hover popovers, but these
// stay open until dismissed (pointer-events: auto).
function _positionClickPop(pop, anchorEl) {
  pop.style.display = 'block';
  const rect = anchorEl.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - pop.offsetHeight - 4);
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
}

function _closeClickPops() {
  const colPop = $('colMenuPop'); if (colPop) colPop.style.display = 'none';
  const legPop = $('legendPop');  if (legPop)  legPop.style.display  = 'none';
  const msPop  = $('multiSymPop'); if (msPop)  msPop.style.display  = 'none';
}

function _initColMenu() {
  const btn = $('columnsBtn');
  const pop = $('colMenuPop');
  if (!btn || !pop) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasOpen = pop.style.display === 'block';
    _closeClickPops();
    if (!wasOpen) { _renderColMenu(); _positionClickPop(pop, btn); }
  });
  pop.addEventListener('click', (e) => e.stopPropagation());
  pop.addEventListener('change', (e) => {
    const chk = e.target.closest('[data-col-toggle]');
    if (!chk) return;
    const id = chk.dataset.colToggle;
    if (chk.checked) state.hiddenCols.delete(id); else state.hiddenCols.add(id);
    try { localStorage.setItem(COL_STORAGE_KEY, JSON.stringify(Array.from(state.hiddenCols))); } catch (_) {}
    applyColumnVisibility();
  });
}

// ── Multi-symbol filter popover ──────────────────────────────────────────────
// Comma-separated symbol list -> exact-match filter (state.filters.symbols_multi),
// combined with every other active filter via AND (matchesBaseFilters).
function _renderMultiSymPop() {
  const pop = $('multiSymPop');
  if (!pop) return;
  const cur = (state.filters.symbols_multi || []).join(', ');
  pop.innerHTML = `
    <div class="sp-title">Filter by symbols</div>
    <div style="font-size:10px;color:#94a3b8;margin-bottom:4px;">Comma-separated, e.g. AAPL, MSFT, NVDA</div>
    <textarea id="multiSymInput" rows="4" style="width:260px;font-size:11px;padding:4px;border:1px solid var(--border);border-radius:4px;resize:vertical;">${escapeHtml(cur)}</textarea>
    <div style="display:flex;gap:6px;margin-top:6px;justify-content:flex-end;">
      <button type="button" id="multiSymClearBtn" class="btn" style="font-size:11px;">Clear</button>
      <button type="button" id="multiSymApplyBtn" class="btn" style="font-size:11px;">Apply</button>
    </div>`;
}

function _initMultiSymPop() {
  const btn = $('multiSymBtn');
  const pop = $('multiSymPop');
  if (!btn || !pop) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasOpen = pop.style.display === 'block';
    _closeClickPops();
    if (!wasOpen) { _renderMultiSymPop(); _positionClickPop(pop, btn); $('multiSymInput').focus(); }
  });
  pop.addEventListener('click', (e) => {
    e.stopPropagation();
    if (e.target.id === 'multiSymApplyBtn') {
      const raw = ($('multiSymInput').value || '');
      const list = raw.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
      state.filters.symbols_multi = list;
      pop.style.display = 'none';
      btn.classList.toggle('active', list.length > 0);
      if (list.length) { _resetToggleFiltersForLookup(); loadActionable(); }
      else applyClientFilter();
    } else if (e.target.id === 'multiSymClearBtn') {
      state.filters.symbols_multi = [];
      pop.style.display = 'none';
      btn.classList.remove('active');
      applyClientFilter();
    }
  });
}

// ── Legend popover (TASK_105 U5) ─────────────────────────────────────────────
function _legendHtml() {
  const row = (a, b) => `<div style="display:flex;gap:14px;margin-bottom:2px;">
      <span style="min-width:70px;font-weight:700;color:#0f172a;">${a}</span>
      <span style="color:#475569;">${b}</span>
    </div>`;
  return `
    <div class="sp-title">Screen Legend</div>
    <div style="font-size:11px;line-height:1.5;max-width:380px;">
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:4px 0 3px;">Action codes</div>
      ${row('SA', 'Sell All')}
      ${row('STM', 'Sell Trim (partial)')}
      ${row('SS', 'Sell Some')}
      ${row('SO', 'Sell Overage — trim back to category Max')}
      ${row('BMN', 'Buy to Min — establish a starter position')}
      ${row('BS', 'Buy Some')}
      ${row('BM', 'Buy More')}
      ${row('HOLD', 'No change recommended')}
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Chips</div>
      <div style="color:#475569;">REMOVE / OVER_MAX / REDUCE / INCREASE / ADD / HOLD / NONE group rows by
        consolidated_action; click a chip to filter, click ALL to clear.</div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Confidence flag</div>
      ${row('Low', 'LOW CONF — the only sell evidence is a rule with a demonstrated negative historical edge (v_unproven_sell_rules); consolidated_action is unchanged, this is a confidence flag')}
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">STOP pill / chip</div>
      <div style="color:#475569;">A held position that just crossed below its Trade line ("TD STM") or its Trend
        line ("TN SA") — prior 3 days above the line, today below it — red left edge + ▼TD/▼TN pill next to ACTION.
        An effective ADD/INCREASE on a breached row is downgraded to HOLD (suppressed_reason = "STOP BREACHED") —
        breach never auto-forces a sell. Click the STOP chip to filter to these rows.</div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Trade Mode</div>
      <div style="color:#475569;">Toggle in the toolbar collapses the grid to only rows with measured
        positive edge (docs/actionable_playbook.md §3.3): (1) qualifying buys — BM/BMN, feasible, Risk
        Range bullish, no stop breach, MACRO not SA/STM, any winning source; (2) held SA sells;
        (3) held stop breaches, whatever the action. Everything else (Watchlist band, HOLD/no-action
        rows) is hidden. <strong>WEAK SRC</strong> pill = the qualifying buy's winning source measured
        negative buy-edge in the last validation — size down or skip; see
        docs/audit/signal_validation_2026-07.md. Not persisted — always starts ON.
        <strong>Strict</strong> sub-toggle (next to Trade Mode, only shown while it's on; also not
        persisted, defaults ON): narrows qualifying buys further to exclude macro/index/FX/futures
        instruments (you can't place a simple buy order on an index or a yield curve) and require the
        Tradability Score to meet its own 🎯 badge threshold. Turn Strict off to see the original,
        looser qualifying-buy list.</div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Conviction filter</div>
      ${row('Any', 'No filter')}
      ${row('Multi', '2+ sources agree on this row')}
      ${row('Proven', 'A fired rule has a positive historical edge')}
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Rules (edge) column</div>
      <div style="color:#475569;">Fired rules, winning-first. Edge = historical forward 20-day return
        when the rule fires (+n.n%), with win-rate and ✓ once proven (adequate sample, CI excludes 0);
        muted/greyed = unproven (n too small or CI straddles 0). Click a rule to open its Rule Flow trace.</div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Other markers</div>
      ${row('IDY', 'Quote is intraday — fresher than the EOD anchor, within market hours')}
      ${row('RVOL', 'Relative volume dot vs 10d avg — hollow=below, gray=~avg, amber/green=above; caret=vs yesterday')}
      ${row('IV', 'IVP (blue) · HV (slate) · IV (dark) glyph; background shade = IV/HV discount')}
      ${row('MACRO', '▲▼ dots = Cur month / Nxt month / Cur quarter direction; sparkline = forward monthly scores')}
      ${row('▼3 / ▲3', 'Symbol: 2 of 3 of MACRO/Sources/Technical agree sell / buy with none opposing. Display-only — no longer drives the default sort.')}
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:8px 0 3px;">Default sort (TASK_120/122)</div>
      <div style="color:#475569;">Stops → credible sells → buys ranked by how many signals agree
        (Tech+Sources+Macro) → holds; unheld buys without a ripe Technical wait in the Watchlist.
        Tier 0 — held rows trading below stop (STOP pill), by position $ desc.
        Tier 1 — credible SELLs on held positions (Sources+Technical both sell, or a source-driven
        exit), by $ at stake desc. LOW CONF sells are never "credible" — they sink to Bottom instead.
        Tier 2 — BUYs that passed the technical gate, sub-ranked by agreement: 2a = Technical + Sources
        + MACRO all buy-side, 2b = Technical + one other buy-side with nothing opposing, 2c = Technical
        ripe only; each sub-tier ordered by dollar-weighted edge desc (sum of the row's fired rules'
        historical edge_20d, weighted by dollars at stake, log-scaled). Tier 3 — HOLD / mixed /
        no-action, by dollar-weighted edge desc. Rows with no scored fired rules fall back to Final
        Call severity, scaled to sit near the middle of the pack.
        Watchlist — buy-noise gate: Technical decides WHEN, Sources decide WHAT. An UNHELD row whose
        effective action is ADD (source ADD or Final Call code BMN) only reaches Tier 2 when Technical
        (the QS code) is BS or BM — the entry-ripe codes near LRR with momentum/pullback confirmation.
        Everything else (BMN, N, watch/sell codes, or no Technical) collapses into the "Watchlist (n)"
        band above Bottom, collapsed by default — click it to expand. A source listing alone never
        promotes an unheld buy; rows whose winning source just landed for this date show a NEW pill
        inside the band instead. Held rows are never gated. Chip filters and symbol search still match
        rows inside the band and auto-expand it on a match — nothing is ever permanently hidden.
        Bottom — LOW CONF sells, infeasible, or suppressed rows sink last regardless of dollars.
        Click a column header to sort by that column instead; Refresh/date-change restores this default.</div>
    </div>`;
}

function _initLegendPopover() {
  const btn = $('legendBtn');
  const pop = $('legendPop');
  if (!btn || !pop) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasOpen = pop.style.display === 'block';
    _closeClickPops();
    if (!wasOpen) { pop.innerHTML = _legendHtml(); _positionClickPop(pop, btn); }
  });
  pop.addEventListener('click', (e) => e.stopPropagation());
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
  state.anchorDate = state.date;
  if (state.date) sel.value = state.date;
  await loadActionable();
  checkEodFeed();
}

// ---- source metadata (base_weight_method per source, for Metric sort) ----
// 2026-08-21: 7 fetches batched into one Promise.all instead of 7 sequential
// awaits -- this ran as a waterfall before, and 3 of the 7 (factor-scorecard,
// source-scorecard, rules/scorecard) each take 1.5-3.2s on their own because
// they hit unmaterialized SQL views that recompute a full aggregation from
// scratch every call (v_factor_scorecard, v_source_edge_scorecard,
// v_rule_scorecard). Sequentially that summed to ~5-10s, awaited before
// loadActionable() even starts fetching the grid's own data. None of the 7
// depend on another's result, so running them concurrently is safe --
// total wait drops to ~max(slowest one) instead of the sum. Each call keeps
// its own try/catch + fallback default exactly as before, just wrapped in
// an immediately-invoked async fn so a rejection can't short-circuit the
// others.
async function loadSources() {
  await Promise.all([
    (async () => {
      try {
        const rows = await fetchJson('/api/actionable/sources');
        state.sourceMethods = {};
        for (const r of rows) state.sourceMethods[r.source_code] = r.base_weight_method;
      } catch (_) { state.sourceMethods = {}; }
    })(),
    // Rule track-record (v_rule_scorecard) keyed by composite code, for the
    // edge badges on fired-rule pills. Diagnostic only while history is shallow.
    (async () => {
      try {
        const sc = await fetchJson('/api/rules/scorecard?min_fires=0&limit=2000');
        state.scorecard = {};
        for (const r of sc) state.scorecard[r.rule_id] = r;
      } catch (_) { state.scorecard = {}; }
    })(),
    // Buysell code→seq map from ref_param_lookup for the default priority sort.
    // SA has seq=21 (highest); sorting by seq DESC puts SA at the top.
    (async () => {
      try {
        state.buysellSeq = await fetchJson('/api/ref/buysell');
      } catch (_) { state.buysellSeq = {}; }
    })(),
    // TASK_106/F5: tunable conviction-proven-edge threshold (ref_settings),
    // instead of hardcoding 0.5 in _hasPositiveEdge.
    (async () => {
      try {
        const settings = await fetchJson('/api/actionable/settings');
        state.convictionProvenEdgeMin = Number(settings.conviction_proven_edge_min);
        if (!isFinite(state.convictionProvenEdgeMin)) state.convictionProvenEdgeMin = 0.5;
        state.rsiOverbought = Number(settings.rsi_overbought);
        if (!isFinite(state.rsiOverbought)) state.rsiOverbought = 70;
        state.rsiOversold = Number(settings.rsi_oversold);
        if (!isFinite(state.rsiOversold)) state.rsiOversold = 30;
        state.vlmRvolAvoidThreshold = Number(settings.vlm_rvol_avoid_threshold);
        if (!isFinite(state.vlmRvolAvoidThreshold)) state.vlmRvolAvoidThreshold = 1.5;
      } catch (_) {
        state.convictionProvenEdgeMin = 0.5;
        state.rsiOverbought = 70;
        state.rsiOversold = 30;
        state.vlmRvolAvoidThreshold = 1.5;
      }
    })(),
    // Per-source buy-family hit rate (v_source_edge_scorecard, same table
    // etl/derive_source_edge.py recomputes ref_settings.trade_mode_weak_buy_sources
    // from nightly) — the Trade Mode Symbol-cell badge shows this number
    // directly instead of a binary WEAK SRC flag.
    (async () => {
      try {
        state.sourceScorecard = await fetchJson('/api/actionable/source-scorecard');
      } catch (_) { state.sourceScorecard = {}; }
    })(),
    // TASK_69: agreement scorecard — keyed by agreement_class -> avg_fwd_20d.
    (async () => {
      try {
        const asc = await fetchJson('/api/rules/agreement-scorecard');
        state.agreementScorecard = {};
        for (const r of (asc || [])) {
          if (r.agreement_class != null) {
            state.agreementScorecard[r.agreement_class] = r.avg_fwd_20d;
          }
        }
      } catch (_) { state.agreementScorecard = {}; }
    })(),
    // 2026-08-01: factor scorecard (v_factor_scorecard) — keyed by "factor|bucket"
    // for the small track-record tags on the RSI/IV grid cells.
    (async () => {
      try {
        const fsc = await fetchJson('/api/rules/factor-scorecard?min_n=30');
        state.factorScorecard = {};
        for (const r of (fsc || [])) {
          state.factorScorecard[r.factor + '|' + r.bucket] = r;
        }
      } catch (_) { state.factorScorecard = {}; }
    })(),
  ]);
}

// Small track-record tag for a grid cell, reading state.factorScorecard
// (populated from /api/rules/factor-scorecard). Colored/valued by DELTA vs
// the 'Baseline'/'All stocks' row, not raw sign — this data covers a rising
// market where the baseline itself is positive, so most buckets are
// nominally positive even when they clearly underperform the average stock
// (e.g. "RSI Neutral" +1.24% vs baseline +1.27% — worse, but raw-positive).
// Coloring on raw sign made almost every tag show green regardless of
// whether the bucket was actually good or bad; fixed 2026-08-01.
// standalone=true renders a <span> for its own line (no vertical-align:super
// shift); default renders a <sup> for inline placement next to a value.
// Returns '' if no data for that bucket yet (min_n=30 not met) or the
// baseline itself isn't loaded — deliberately quiet rather than misleading.
// Raw numeric delta (bucket's avg_fwd_20d minus the 'Baseline'/'All stocks'
// row) — the same lookup _factorEdgeTag renders as a badge, extracted so the
// buy-tradability score (2026-08-15, see _buyTradabilityScore below) can use
// the actual measured number instead of a hand-picked weight. Returns null
// if there's no data for that bucket yet or the baseline isn't loaded.
function _factorEdgeDelta(factor, bucket) {
  if (!bucket) return null;
  const r = (state.factorScorecard || {})[factor + '|' + bucket];
  const base = (state.factorScorecard || {})['Baseline|All stocks'];
  if (!r || r.avg_fwd_20d == null || !base || base.avg_fwd_20d == null) return null;
  return Number(r.avg_fwd_20d) - Number(base.avg_fwd_20d);
}
// 2026-08-15: win-rate delta (percentage points) — used by _buyTradabilityScore
// INSTEAD of _factorEdgeDelta's mean. User: "IV can be high while price is
// going up or it can cause stock to go down — did you consider both facts?"
// Checked directly against drv_factor_snapshot: elevated/extreme IV's mean
// forward return (+1.7/+2.0%) is real but heavily right-tail-skewed — median
// is only +0.6/+0.9% (well under the mean), and Extreme IV carries the
// WORST downside tail of any IV bucket (15.8% of 20-day windows land below
// -10%, vs 11.6% for Low IV). The mean alone hides that IV is a two-sided
// dispersion signal (bigger moves either way), not a clean directional one.
// Win rate (just: did it end up positive at all) is far less distorted by a
// few huge winners, so it's the more honest "did this typically work"
// measure. Cross-checked RSI/RVOL the same way — both hold up fine (RSI
// oversold: median 2.72 close to its 3.69 mean, LOWER downside-tail risk
// than neutral/overbought; RVOL high+up-day: median near zero, HIGHEST
// downside-tail risk, confirming the existing "buying climax" caution) — so
// only IV's contribution actually needed correcting, not the other two.
function _factorWinRateDelta(factor, bucket) {
  if (!bucket) return null;
  const r = (state.factorScorecard || {})[factor + '|' + bucket];
  const base = (state.factorScorecard || {})['Baseline|All stocks'];
  if (!r || r.win_rate == null || !base || base.win_rate == null) return null;
  return (Number(r.win_rate) - Number(base.win_rate)) * 100; // fraction -> pp
}

// 2026-08-20: like _factorWinRateDelta, but also gates on n_symbols (DISTINCT
// tickers, not row-days) -- found live: v_factor_scorecard's 'Sector'
// bucket had Gold at n=234 row-days but n_symbols=2, Fixed Income/
// Commodities/'Health Care' (capital C, a casing dupe of the real 68-ticker
// 'Health care') each n_symbols=1 -- single tickers' repeated daily history
// masquerading as a broad sector effect. min_symbols defaults to 5.
// Returns {delta, n, nSymbols} or null if missing/gated out.
function _factorWinRateDeltaGated(factor, bucket, minSymbols) {
  if (!bucket) return null;
  const r = (state.factorScorecard || {})[factor + '|' + bucket];
  const base = (state.factorScorecard || {})['Baseline|All stocks'];
  if (!r || r.win_rate == null || !base || base.win_rate == null) return null;
  const nSymbols = r.n_symbols != null ? Number(r.n_symbols) : 0;
  if (nSymbols < (minSymbols != null ? minSymbols : 5)) return null;
  return { delta: (Number(r.win_rate) - Number(base.win_rate)) * 100, n: r.n, nSymbols };
}

function _factorEdgeTag(factor, bucket, standalone) {
  const r = (state.factorScorecard || {})[factor + '|' + bucket];
  const base = (state.factorScorecard || {})['Baseline|All stocks'];
  const delta = _factorEdgeDelta(factor, bucket);
  if (delta == null) return '';
  const e = Number(r.avg_fwd_20d);
  const baseAvg = Number(base.avg_fwd_20d);
  // Suppress near-zero deltas (rounds to "0.0%") instead of showing a tag
  // that carries no signal — e.g. RSI's "Neutral" bucket is ~95% of rows on
  // a given day and sits within 0.03pp of baseline, so showing it on almost
  // every row was just noise (2026-08-01).
  if (Math.abs(delta) < 0.05) return '';
  const color = delta > 0 ? '#15803d' : delta < 0 ? '#b91c1c' : '#64748b';
  const sign = delta >= 0 ? '+' : '';
  const conf = r.confidence || 'unproven';
  const tag = standalone ? 'span' : 'sup';
  const leadSpace = standalone ? '' : ' ';
  // No confidence checkmark here — RSI/IV buckets cover ~1000 stocks/day, so
  // they clear the "proven" sample-size bar almost universally and the mark
  // stopped being a useful distinction (2026-08-01). Still shown as a real
  // column on the Performance screen's Factor scorecard, where bucket sizes
  // vary enough (e.g. Sector, Winning source) for it to mean something.
  return `${leadSpace}<${tag} style="font-size:8px;font-weight:700;color:${color};cursor:help;" `
       + `title="${escapeHtml(bucket)}: historically ${e >= 0 ? '+' : ''}${e.toFixed(1)}% avg 20d fwd return `
       + `vs baseline ${baseAvg >= 0 ? '+' : ''}${baseAvg.toFixed(1)}% (n=${r.n}, ${conf}) `
       + `— /performance Factor scorecard">${sign}${delta.toFixed(1)}%</${tag}>`;
}

// RSI/IV bucket helpers — mirror etl/compute_factor_outcomes.py's SQL exactly
// so the grid tag looks up the same bucket the scorecard was computed on.
function _rsiBucket(rsi) {
  if (rsi == null) return null;
  const rv = Number(rsi);
  const hi = state.rsiOverbought != null ? state.rsiOverbought : 70;
  const lo = state.rsiOversold   != null ? state.rsiOversold   : 30;
  if (rv <= lo) return 'Oversold (<=' + lo + ')';
  if (rv >= hi) return 'Overbought (>=' + hi + ')';
  return 'Neutral';
}
function _ivBucket(ivPct) {
  if (ivPct == null) return null;
  const v = Number(ivPct);
  if (v >= 90) return 'Extreme (>=90)';
  if (v >= 70) return 'Elevated (70-90)';
  if (v <= 30) return 'Low (<=30)';
  return 'Mid (30-70)';
}
// 2026-08-15: mirrors etl/compute_factor_outcomes.py's rvol_bucket CASE
// exactly (same "same bucket the scorecard was computed on" contract as
// _rsiBucket/_ivBucket above) — used by _buyTradabilityScore.
function _rvolBucket(rvol, pctChange) {
  if (rvol == null) return null;
  const hi = state.vlmRvolAvoidThreshold != null ? state.vlmRvolAvoidThreshold : 1.5;
  const rv = Number(rvol);
  if (rv >= hi && pctChange != null && Number(pctChange) > 0) return 'High RVOL + up day';
  if (rv >= hi && pctChange != null && Number(pctChange) < 0) return 'High RVOL + down day';
  return 'Normal/low RVOL';
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
// Confidence buckets: 'proven' = solid badge; 'promising' = normal; 'unproven' = muted grey.
function ruleEdgeBadge(code) {
  const sc = (state.scorecard || {})[code];
  if (!sc || sc.edge_20d == null) return '';
  const e = Number(sc.edge_20d);
  const conf = sc.confidence || 'unproven';
  const n = sc.n_fires != null ? sc.n_fires : (sc.fires != null ? sc.fires : '?');
  const ciLow  = sc.edge_20d_ci_low  != null ? Number(sc.edge_20d_ci_low).toFixed(1)  : null;
  const ciHigh = sc.edge_20d_ci_high != null ? Number(sc.edge_20d_ci_high).toFixed(1) : null;
  const ciStr  = ciLow != null ? ` CI [${ciLow}%,${ciHigh}%]` : '';
  if (conf === 'unproven') {
    // Muted grey badge — no color signal until sample is adequate
    return ` <span class="rule-edge-badge rule-neutral rule-weak" style="opacity:0.55;" `
         + `title="Unproven (n=${n}, too few fires or CI straddles 0${ciStr}) — diagnostic only">`
         + `n=${n}</span>`;
  }
  const side = _ruleSide(code);
  const sideCls = side === 'buy' ? 'rule-buy' : side === 'sell' ? 'rule-sell' : 'rule-neutral';
  const emphCls = conf === 'proven' ? 'rule-strong' : (e > 0 ? 'rule-strong' : 'rule-weak');
  const wr = (sc.win_rate != null) ? ` · ${(Number(sc.win_rate) * 100).toFixed(0)}%` : '';
  const sign = e >= 0 ? '+' : '';
  const provenMark = conf === 'proven' ? ' ✓' : '';
  return ` <span class="rule-edge-badge ${sideCls} ${emphCls}" `
       + `title="${conf}: 20d edge (n=${n}${ciStr}) — diagnostic, shallow history">`
       + `${sign}${e.toFixed(1)}%${wr}${provenMark}</span>`;
}

// Grid cell: fired rules ordered winning-first (highest score), each with its
// historical edge. Hue = Final Call action side (all pills match row's action);
// fill = edge emphasis (bold border=positive edge, light border=non-positive).
// Unproven rules (n<30 or CI straddles 0) render muted regardless of edge sign.
// maxCount (U1b): caps the grid cell to N pills + a "+n" suffix so the Rules
// column doesn't force the whole grid wide. The drilldown modal and symbol
// tile popover call this with no limit (full list); the grid cell click
// still opens /rule-flow for the complete trace.
function firesCellHtml(r, maxCount) {
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return '<span style="color:#cbd5e1">—</span>';
  const sc = state.scorecard || {};
  const items = fires.map(f => {
    const id = String(f.rule_id || f.id || f);
    const s   = sc[id] || {};
    const e   = s.edge_20d  != null ? Number(s.edge_20d)  : null;
    const conf = s.confidence || 'unproven';
    const n    = s.n_fires   != null ? s.n_fires : (s.fires != null ? s.fires : null);
    const score = (f.score != null) ? Number(f.score) : 0;
    return { id, e, conf, n, score };
  });
  // winning first: highest fired score, then strongest edge
  items.sort((a, b) => (b.score - a.score) || ((b.e ?? -99) - (a.e ?? -99)));
  const extra = (maxCount && items.length > maxCount) ? items.length - maxCount : 0;
  const shown = extra ? items.slice(0, maxCount) : items;
  const _RULE_CLR = {
    'act-sell-strong': '#991b1b', 'act-sell': '#ef4444', 'act-sell-weak': '#f97316',
    'act-buy-strong':  '#14532d', 'act-buy':  '#22c55e', 'act-buy-weak':  '#86efac',
  };
  // D5: _RULE_EXTRA (BR/B overrides) removed — BR and B now in actions.js _MAP.
  const _ruleColor = (id) => {
    for (const part of String(id).toUpperCase().split('-')) {
      const d = actionDisplay(part);
      const cls = (d.colorCls && d.colorCls !== 'act-neutral') ? d.colorCls : null;
      if (cls && _RULE_CLR[cls]) return _RULE_CLR[cls];
    }
    return '#94a3b8';
  };
  const pills = shown.map(it => {
    const color = _ruleColor(it.id);
    if (it.conf === 'unproven') {
      const nLabel = it.n != null ? `n=${it.n}` : '';
      const tip = `Unproven rule${it.n != null ? ' ('+nLabel+')' : ''} — too few fires or CI straddles 0`;
      return `<span style="white-space:nowrap;opacity:0.45;font-size:11px;color:${color};" title="${tip}">`
           + `${escapeHtml(it.id)}${nLabel ? ' <b>'+nLabel+'</b>' : ''}</span>`;
    }
    const weight = (it.e != null && it.e > 0) ? '700' : '400';
    const edge = it.e == null ? '' : ` <b>${it.e >= 0 ? '+' : ''}${it.e.toFixed(1)}</b>`;
    return `<span style="white-space:nowrap;font-size:11px;font-weight:${weight};color:${color};">${escapeHtml(it.id)}${edge}</span>`;
  });
  if (extra) {
    const moreIds = items.slice(maxCount).map(it => it.id).join(', ');
    pills.push(`<span style="white-space:nowrap;font-size:11px;color:#94a3b8;" title="${escapeHtml(moreIds)}">+${extra}</span>`);
  }
  return pills.join(' ');
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

// Normalize real_asset_class into a small set of display/filter buckets --
// used for r._assetClass (Asset Class filter chips/dropdown), independent
// of the Portfolio Mix pies this was originally extracted alongside.
// 2026-09-01 BUGFIX: got left behind in web/portfolio_mix.js when that
// script's tag was removed from actionable.html (side panel removal,
// "remove the side panel from actionable screen altogether") -- broke the
// whole page load ("Failed to load actionable: _normAssetClass is not
// defined") since this is called from the main row-normalization loop
// below, not from anything Portfolio-Mix-specific. Restored here directly
// rather than re-adding the whole portfolio_mix.js script tag just for
// these two small definitions -- same "duplicate small helpers per page"
// convention this file's own _quadColor (vs. app.js's copy) already uses.
const _ASSET_CLASS_ALIAS = {
  'domestic equities': 'Equities', 'global equities': 'Equities',
  'international equities': 'Equities', 'emerging markets equities': 'Equities',
  'equities': 'Equities',
  'us fixed income': 'Fixed Income', 'domestic fixed income': 'Fixed Income',
  'fixed income': 'Fixed Income',
  'foreign currencies': 'FX', 'foreign currency': 'FX', 'fx': 'FX',
  'commodities': 'Commodities',
  'crypto': 'Crypto',
  'gold': 'Gold',
  'cash': 'Cash',
};
function _normAssetClass(raw) {
  if (!raw) return 'Unclassified';
  const key = String(raw).trim().toLowerCase();
  return _ASSET_CLASS_ALIAS[key] || raw;
}

// ---- core load ----
// opts.preserveState: when true (auto-poll path only), keep the user's current
// column sort and bulk selection instead of resetting them. Manual Refresh /
// date-picker change call loadActionable() with no opts (default reset behavior).
async function loadActionable(opts) {
  const preserveState = !!(opts && opts.preserveState);
  if (!state.date) return;
  // Reset to default actionability sort on every fresh data load (date change / refresh).
  // Column-header clicks override this until the next load or Clear.
  // Skipped when preserveState is true (background auto-refresh) so the user's sort sticks.
  if (!preserveState) {
    state.sort = { key: '_priority', dir: -1, type: 'num' };
  }
  // Always fetch all rows -- action/category filters applied client-side so chip counts stay accurate
  // When show_hidden is on, also fetch acted/suppressed rows from the API.
  const params = new URLSearchParams({ date: state.date });
  if (state.filters.show_hidden) {
    params.append('show_acted', 'true');
    params.append('show_suppressed', 'true');
  }
  // TASK_124: Trade Mode's stop-breach category needs suppressed rows too —
  // a held ADD/INCREASE downgraded to HOLD by a stop breach carries
  // suppressed_reason='STOP BREACHED' and would otherwise be excluded server-side.
  // trade_mode_diff (2026-08-28) doesn't itself surface suppressed rows
  // (it's buys-only by construction, see _isTradeModeDiffBuy), but fetching
  // them anyway keeps this consistent/harmless if that ever changes.
  if ((state.filters.trade_mode || state.filters.trade_mode_diff) && !state.filters.show_hidden) {
    params.append('show_suppressed', 'true');
  }
  try {
    const dateParam = state.date ? `?date=${encodeURIComponent(state.date)}` : '';
    const [rows, accts, betaMap, portfolioRows, assetClassMap, sectorMap, macroAreas] = await Promise.all([
      fetchJson('/api/actionable?' + params.toString()),
      fetchJson(`/api/actionable/accounts${dateParam}`).catch(() => []),
      fetchJson(`/api/portfolio/beta-map${dateParam}`).catch(() => ({})),
      fetchJson(`/api/portfolio${dateParam}`).catch(() => []),
      fetchJson(`/api/portfolio/asset-class-map${dateParam}`).catch(() => ({})),
      fetchJson(`/api/portfolio/sector-map${dateParam}`).catch(() => ({})),
      // Sector-ETF proxy (2026-08-20) -- Action popup's "Sector ETF" line
      // (_actpopSectorEtfHtml) needs XLF/XLK/etc.'s own outlook/%chg/risk-range
      // position, not the symbol's. /api/macro-areas already computes this per
      // GICS sector via _sector_etf_proxy (api/routers/macro_areas.py) for the
      // side-rail Sectors card -- reused as-is, own fetch (not shared with
      // web/macro_areas.js's copy) per user's "own fetch, simpler" call.
      fetchJson(`/api/macro-areas${dateParam}`).catch(() => null),
    ]);
    state.allAccounts = Array.isArray(accts) ? accts : [];
    state.allRows = Array.isArray(rows) ? rows : [];
    state.betaMap = (betaMap && typeof betaMap === 'object') ? betaMap : {};
    // 2026-08-14 -- Portfolio Mix now sources its HELD POSITIONS from the raw
    // /api/portfolio feed (hist_cs/hist_f, same as the Sector/Asset class
    // factor-scorecard tables), not from state.allRows (drv_actionable) --
    // drv_actionable only carries symbols with a resolved tos_symbol in the
    // tracked technicals universe, silently dropping any held position that
    // lacks one (found live: QTUM/IVOL/SOFI/WRBY/INTU, ~$44k/5.75% of the
    // portfolio, missing from every pie, not just misclassified). User:
    // "sector is not matching" -> traced to this gap -> "switch all 4 pies
    // to source from /api/portfolio entirely". See _pmHeldRows/_pmCashTotal
    // below (built from state.portfolioRows/assetClassMap/sectorMap/allRows
    // set here, not from drv_actionable's held_today/current_position_dollar).
    state.portfolioRows = Array.isArray(portfolioRows) ? portfolioRows : [];
    state.assetClassMap = (assetClassMap && typeof assetClassMap === 'object') ? assetClassMap : {};
    state.sectorMap = (sectorMap && typeof sectorMap === 'object') ? sectorMap : {};
    // lowercased sector name -> {symbol, last, pct_change, td, tn, rr_pos, outlook}
    // (macro_areas.py::_sector_etf_proxy). Keyed lowercase, not by the API's
    // display-cased s.sector, because row.sector (ref_sector.equity_sector,
    // read straight off drv_actionable) isn't guaranteed the same casing --
    // macro_areas.py's own _GICS_DISPLAY map exists specifically to merge
    // "Health care"/"Health Care" variants; _sectorEtfFor below does the same
    // lowercase + healthcare alias fold before lookup. Missing/null when a
    // sector has no mapped ETF (e.g. "Country ETF") or the ETF itself has no
    // drv_quote row.
    state.sectorEtfMap = {};
    for (const s of ((macroAreas && macroAreas.sectors && macroAreas.sectors.all) || [])) {
      if (s.sector && s.etf) state.sectorEtfMap[s.sector.trim().toLowerCase()] = s.etf;
    }
    state.allRows.forEach(r => {
      r._assetClass = _normAssetClass(r.real_asset_class);
      // RR column sort key (2026-08-12) — same formula _buildRowEl's rrBarHtml
      // already computes for the bar's tick position, hoisted here so the RR
      // header can sort by it (0 = at LRR, 100 = at TRR) without duplicating
      // the formula at render time.
      {
        const lrrN = r.lrr != null ? Number(r.lrr) : null;
        const trrN = r.trr != null ? Number(r.trr) : null;
        const lastN = r.last_price != null ? Number(r.last_price) : null;
        r._rrPos = (lrrN != null && trrN != null && lastN != null && trrN !== lrrN)
          ? Math.round(Math.max(0, Math.min(100, (lastN - lrrN) / (trrN - lrrN) * 100)))
          : null;
      }
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
      r._watchlisted = _buyNoiseGated(r);
      r._priority = _computePriority(r);
      r._agree3 = _agree3Score(r);
      r._pvv_rank = _pvvRank(r.pvv_decision);
    });
    // Expose monthly score map for market_bar.js tape chips
    window._macroScoreMap = Object.fromEntries(
      state.allRows.map(r => [r.tos_symbol, r.monthly_score ?? null])
    );
    if (window._refreshTapeGlyphs) window._refreshTapeGlyphs();
    // 2026-08-31 -- one-time deep-link filter from the Dashboard's Quad
    // Rotation panel ("see all N in Actionable" link): ?filter_sector=/
    // ?filter_asset_class=/?filter_style= pre-applies the same client
    // filter the sector/asset-class/style summary chips already set via
    // state.filters + applyClientFilter() (see renderSectorSummary() etc.
    // above) -- reuses that existing mechanism rather than a new one.
    // Guarded to run only once so a manual Refresh/date-change afterward
    // doesn't keep re-forcing the filter back on if the user cleared it.
    if (!window._qrDeepLinkApplied) {
      window._qrDeepLinkApplied = true;
      const qp = new URLSearchParams(window.location.search);
      const fSector = qp.get('filter_sector');
      const fAssetClass = qp.get('filter_asset_class');
      const fStyle = qp.get('filter_style');
      if (fSector) state.filters.sector = fSector;
      if (fAssetClass) state.filters.asset_class = fAssetClass;
      if (fStyle) state.filters.style = fStyle;
      // init()'s own syncFilterUi() call already ran (before this filter
      // state existed) -- re-sync now so the new sector/asset-class/style
      // <select> dropdowns visually reflect the deep-linked value too, not
      // just the grid.
      if (fSector || fAssetClass || fStyle) syncFilterUi();
    }
    applyClientFilter(preserveState ? { preserveSelection: true } : undefined);
    const now = new Date();
    const mo = now.getMonth() + 1;
    const dd = String(now.getDate()).padStart(2, '0');
    let hh = now.getHours(), mm = String(now.getMinutes()).padStart(2, '0');
    const ap = hh >= 12 ? 'PM' : 'AM';
    if (hh > 12) hh -= 12; else if (hh === 0) hh = 12;
    const el = document.getElementById('loadedAt');
    if (el) el.textContent = mo + '/' + dd + ' ' + hh + ':' + mm + ' ' + ap;
  } catch (e) {
    showStatus('Failed to load actionable: ' + e.message, 'error', 0);
  }
}

// TASK_124: Trade Mode — narrow the grid to the three categories measured
// to have positive edge in docs/actionable_playbook.md §3.3. Everything else
// (including the Watchlist band and HOLD/no-action rows) is hidden. Buys from
// ANY source qualify; a buy whose winning source measured negative buy-edge
// (ref_settings.trade_mode_weak_buy_sources) is tagged WEAK SRC instead.
// RTA (Real-Time Alert) and SSSCHG (Signal Strength Stocks Gmail
// Added/Removed) are exempt from the Technical check — same rationale as
// the server-side bypass_technical in _compute_final_call: a same-day live
// trigger doesn't need the deep-TA stack to also confirm.
// Swapped rr_bull_bear -> rr_action (Technical, same buy-family set as the
// Watchlist gate's _ENTRY_RIPE_TECH): rr_bull_bear only reflects whether the
// RR band-position leg (QO) used the bull_rr_rule or nbull_rr_rule table,
// not whether Technical actually confirmed a buy on this snapshot.
//
// 2026-08-25, user: "too many [buys] — reduce to perfect ones." Four
// tightening passes were added on top of the original (TASK_124) criteria,
// gated behind a separate "Strict" sub-toggle (defaulted ON but could be
// turned off to see the original looser set).
// 2026-08-28, user: "Make trade mode button behave strict mode" -- Strict
// is no longer an opt-out sub-toggle; the tightening passes are now always
// applied by the Trade Mode button itself (_isTradeModeQualifyingBuy below
// = the old "Strict" function, unconditionally). The original looser
// criteria are kept as their own function (_isTradeModeQualifyingBuyLoose)
// so the new "Non-Strict" button (was the Strict toggle's old DOM slot,
// tradeModeDiffBtn) can show exactly what these tightening passes filter
// out -- user: "create a new button and display all current trade mode
// stocks without strict mode stocks."
//   1. Exclude macro/index/FX/futures instruments (a.is_macro_instrument,
//      api/routers/dash.py — ref_rrt.y_ticker format: '^' prefix = index,
//      '=F'/'=X' suffix = futures/FX). RR's outlook source covers these as
//      well as real stocks/ETFs (asset_class='RR' alone doesn't
//      distinguish XOP the ETF from SPX the index), and you can't actually
//      place a simple buy order on an index or a yield curve. Confirmed
//      live 2026-08-25: 5 of 37 qualifying buys were this category.
//   2. Require the existing Tradability Score (_buyTradabilityScore,
//      SYMBOL cell's 🎯 badge) to meet its own badge threshold
//      (_TRADABILITY_BADGE_MIN). Reuses the already-validated LRR-dominant
//      score instead of a new invented cutoff — "perfect" now means
//      "would already show a 🎯 badge," not a separate concept.
const _TECH_GATE_EXEMPT_SRC = ['RTA', 'SSSCHG', 'TOP5'];
// Original (pre-2026-08-25) TASK_124 criteria only -- no tightening passes.
// Kept standalone (not folded into the strict function below) so the new
// "Non-Strict" button can compute loose-minus-strict.
function _isTradeModeQualifyingBuyLoose(r) {
  const code = (r.final_code || '').toUpperCase();
  if (code !== 'BM' && code !== 'BMN') return false;
  if (!(r.fc_feasible === true || r.fc_feasible === 'true')) return false;
  const src = (r.winning_source || '').toString().toUpperCase();
  const tech = (r.rr_action || '').toUpperCase();
  if (_TECH_GATE_EXEMPT_SRC.indexOf(src) === -1 && _ENTRY_RIPE_TECH.indexOf(tech) === -1) return false;
  if (r.stop_breached) return false;
  const mv = (r.macro_value || '').toUpperCase();
  if (mv === 'SA' || mv === 'STM') return false;
  return true;
}
// Strict criteria -- now the Trade Mode button's ONLY buy gate (see comment
// block above). Builds on the loose criteria above, plus 5 tightening passes.
function _isTradeModeQualifyingBuy(r) {
  if (!_isTradeModeQualifyingBuyLoose(r)) return false;
  const code = (r.final_code || '').toUpperCase();
  const tech = (r.rr_action || '').toUpperCase();
  if (r.is_macro_instrument === true || r.is_macro_instrument === 'true') return false;
  if (_buyTradabilityScore(r) < _TRADABILITY_BADGE_MIN) return false;
  // 2026-08-27, 3rd Strict-only tightening pass -- closes the
  // RTA/SSSCHG/TOP5 tech-gate EXEMPTION above for Strict mode
  // specifically (the loose function above keeps it). Those sources
  // bypass the Technical check entirely on the theory that a same-day
  // live trigger doesn't need TA to also confirm, but Strict's whole
  // point is "perfect only" -- require rr_action to actually be
  // entry-ripe here regardless of source. User: "In Trade + Strict mode,
  // don't include the ones that technicals are not aligned for today
  // (AMZN, TJX)."
  if (_ENTRY_RIPE_TECH.indexOf(tech) === -1) return false;
  // 2026-08-27, 4th Strict-only tightening pass -- PVV's own AVOID
  // decision (r.pvv_decision, condition "outlook=Bearish, today=NEUTRAL/
  // NA/DRIFT" -- see _PVV_DECISION_INFO) is a second, independent
  // sell-tilted signal Strict mode wasn't checking; exclude it same as
  // the other tightening rules here. User: "Also remove PVV -> AVOID
  // from strict mode."
  if (r.pvv_decision === 'AVOID') return false;
  // 2026-08-28, 5th Strict-only tightening pass -- BUY TO MIN (BMN, a
  // starter position — not yet held) only qualifies when price is
  // actually above the Trade line (docs/drv_cat_atomic_input_logic.md's
  // trade_trend_sd_rule: last_price > trade_line_value). BUY MORE (BM,
  // adding to an existing position) is unaffected. User: "include BUYTOMIN
  // only if it is above trade."
  if (code === 'BMN' && !(r.last_price > r.trade_line_value)) return false;
  return true;
}
function _isTradeModeHeldSaSell(r) {
  return !!r.held_today && (r.final_code || '').toUpperCase() === 'SA';
}
function _isTradeModeStopBreach(r) {
  return !!r.held_today && !!r.stop_breached;
}
function _matchesTradeMode(r) {
  return _isTradeModeQualifyingBuy(r) || _isTradeModeHeldSaSell(r) || _isTradeModeStopBreach(r);
}
// "Non-Strict" button (tradeModeDiffBtn) -- current Trade Mode stocks
// WITHOUT the ones Strict also keeps: loose-qualifying buys minus
// strict-qualifying buys. Held SA-sells/stop-breaches are identical under
// both (Strict never touches them), so they cancel out of this difference
// and don't appear here -- this view is buys-only by construction, which
// matches its purpose (show what the tightening passes filtered out).
function _isTradeModeDiffBuy(r) {
  return _isTradeModeQualifyingBuyLoose(r) && !_isTradeModeQualifyingBuy(r);
}
function _matchesTradeModeDiff(r) {
  return _isTradeModeDiffBuy(r);
}
// Numeric hit-rate badge for a qualifying Trade Mode row — the winning
// source's 20d win rate from state.sourceScorecard, shown in place of the
// old binary WEAK SRC pill (TASK_124) so every source's track record is
// visible, not just the three that happened to be below zero at one point
// in time. 2026-08-20: was buy-only (_isTradeModeQualifyingBuy, BM/BMN)
// with no sell-side equivalent even though a held SA row already qualifies
// for Trade Mode on its own (_isTradeModeHeldSaSell) -- the badge itself
// just never got wired to it. Now covers both, picking .buy/.sell to match
// (same side-aware data source-scorecard's other consumers use).
function _sourceHitRateBadge(r) {
  const side = _isTradeModeQualifyingBuy(r) ? 'buy' : _isTradeModeHeldSaSell(r) ? 'sell' : null;
  if (!side) return '';
  const src = (r.winning_source || '').toString().toUpperCase();
  const sc = ((state.sourceScorecard || {})[src] || {})[side];
  if (!sc || sc.win_rate_20d == null || sc.n < 5) return '';
  const pct = Math.round(sc.win_rate_20d * 100);
  const cls = pct < 45 ? 'hit-rate-pill-low' : pct > 55 ? 'hit-rate-pill-high' : 'hit-rate-pill-mid';
  const edgeStr = sc.edge_20d != null ? (sc.edge_20d >= 0 ? '+' : '') + sc.edge_20d.toFixed(2) + '%' : 'n/a';
  const title = `${src} ${side} hit rate: ${pct}% of ${sc.n} historical ${side}s were `
    + `${side === 'buy' ? 'positive' : 'negative'} at 20d (avg edge ${edgeStr}).`;
  return `<span class="hit-rate-pill ${cls}" title="${escapeHtml(title)}">${pct}%</span>`;
}

// Client filters EXCEPT the action chip. Kept separate so the action-chip
// counts can reflect every other active filter.
// All active filters combine with AND.
function matchesBaseFilters(r) {
  // TASK_124: Trade Mode replaces the default show_hidden suppression logic
  // outright — its own criteria are the complete gate. Toggle OFF (default)
  // leaves this whole block unreached, keeping OFF pixel-identical to before.
  // Trade Mode and its "Non-Strict" counterpart (2026-08-28) are mutually
  // exclusive alternate views (enforced in the click handlers below), so
  // this only ever needs to check one or the other, never both.
  if (state.filters.trade_mode) {
    if (!_matchesTradeMode(r)) return false;
  } else if (state.filters.trade_mode_diff) {
    if (!_matchesTradeModeDiff(r)) return false;
  } else if (!state.filters.show_hidden) {
    // When show_hidden is OFF, hide suppressed/$0 AMT/no-action/acted/unheld-remove rows.
    if (r.suppressed_reason) return false;
    const ua = (r.last_user_action || '').toUpperCase();
    if (ua === 'DONE' || ua === 'SKIPPED' || ua === 'OVERRIDDEN') return false;
    if (ua === 'SNOOZED' && (!r.snooze_until || r.snooze_until >= state.date)) return false;
    if (!r.consolidated_action) return false;
    if (!r._amt) return false;
    const ca = (r.consolidated_action || '').toUpperCase();
    if (ca === 'REMOVE' && !r.held_today) return false;
  }
  if (state.filters.source) {
    if (!_rowHasSource(r, state.filters.source)) return false;
  }
  if (state.filters.account) {
    if (!r.held_accounts) return false;
    const accts = r.held_accounts.split(',').map(a => a.trim());
    if (!accts.includes(state.filters.account)) return false;
  }
  if (state.filters.held_only) {
    if (!r.held_today) return false;
  }
  if (state.filters.conviction === 'multi') {
    if (_agreeingSources(r) < 2) return false;
  } else if (state.filters.conviction === 'proven') {
    if (!_hasPositiveEdge(r)) return false;
  }
  const symSearch = state.filters.symbol_search || '';
  if (symSearch) {
    const search = symSearch.toUpperCase();
    if (!r.tos_symbol || !r.tos_symbol.toUpperCase().includes(search)) return false;
  }
  const symList = state.filters.symbols_multi;
  if (symList && symList.length) {
    if (!r.tos_symbol || !symList.includes(r.tos_symbol.toUpperCase())) return false;
  }
  // TASK_66: bull_prob minimum filter
  const bpMin = Number(state.filters.bull_prob_min) || 0;
  if (bpMin > 0) {
    if (r.bull_prob == null || Number(r.bull_prob) < bpMin) return false;
  }
  // TASK_69: agreement_class filter
  const agCls = state.filters.agreement_class || '';
  if (agCls && r.agreement_class !== agCls) return false;
  // EC / IC pills — recent ETF/II Pro Change event (informational only,
  // doesn't drive ETF's/II's own action — see docs/actionable_logic.md).
  if (state.filters.etfchg_only && !r.etfchg_date) return false;
  if (state.filters.iichg_only && !r.iichg_date) return false;
  // RR (Risk Range %) slider — r._rrPos is already computed per-row during
  // load (0-100, null if lrr/trr/last_price unavailable). Rows with no RR
  // data are excluded once the band is narrowed off its full 0-100 default.
  const rrMin = state.filters.rr_min || 0, rrMax = state.filters.rr_max != null ? state.filters.rr_max : 100;
  if (rrMin > 0 || rrMax < 100) {
    if (r._rrPos == null || r._rrPos < rrMin || r._rrPos > rrMax) return false;
  }
  return true;
}

// opts.preserveSelection: when true (auto-poll path via loadActionable({preserveState:true})),
// keep state.selected intersected with the new symbol set instead of clearing it outright.
function applyClientFilter(opts) {
  const preserveSelection = !!(opts && opts.preserveSelection);
  if (state.filters.source && !_availableSources().has(state.filters.source)) {
    state.filters.source = '';
  }
  // baseRows: all filters except the action chip (drives chip counts that reflect
  // every other active filter, via matchesBaseFilters).
  state.baseRows = state.allRows.filter(matchesBaseFilters);
  // rows: baseRows + action chip filter + actionable_only (AND combined)
  state.rows = state.baseRows.filter(r => {
    // Asset class filter lives here (not in matchesBaseFilters) so baseRows —
    // and the asset-class chip $ amounts computed from it — stay unrestricted
    // by this specific filter, same reasoning as action/stopOnly below: you
    // can see every category's total while one is selected, not just the one.
    if (state.filters.asset_class && r._assetClass !== state.filters.asset_class) return false;
    if (state.filters.sector && (r.sector || 'Unclassified') !== state.filters.sector) return false;
    if (state.filters.style && !_rowStyleLabels(r).includes(state.filters.style)) return false;
    if (state.filters.stopOnly && !r.stop_breached) return false;
    if (state.filters.action) {
      const grp = _ACTION_GROUPS[state.filters.action];
      return grp ? grp.indexOf(_chipAction(r)) !== -1 : _chipAction(r) === state.filters.action;
    }
    if (state.filters.actionable_only) {
      const a = _chipAction(r);
      return a !== 'HOLD' && a !== 'NONE';
    }
    return true;
  });
  // Reset selection on filter change.
  if (preserveSelection) {
    // Auto-refresh: keep the user's selection, dropping symbols no longer present.
    const symSet = new Set(state.rows.map(r => r.tos_symbol));
    for (const s of Array.from(state.selected)) {
      if (!symSet.has(s)) state.selected.delete(s);
    }
  } else {
    state.selected.clear();
  }
  renderBulkBar();
  renderSummary();
  renderAssetClassSummary();
  renderSectorSummary();
  renderStyleSummary();
  renderSourceFilter();
  renderAccountFilter();
  renderGrid();
}

// RR (Risk Range %) dual-thumb slider — same pattern as Universe's
// wireRrSlider() (web/universe.js), split into a UI-sync helper (called from
// syncFilterUi/clearAllFilters, no re-render) and the input listeners below
// (added in the DOM-wiring block, drive state + applyClientFilter).
function _syncRrSliderUi() {
  const minEl = $('actRrMin'), maxEl = $('actRrMax'), rangeEl = $('actRrRange'), row = $('actRrRow');
  if (!minEl || !maxEl || !rangeEl || !row) return;
  const lo = state.filters.rr_min || 0, hi = state.filters.rr_max != null ? state.filters.rr_max : 100;
  minEl.value = String(lo); maxEl.value = String(hi);
  rangeEl.style.left = lo + '%';
  rangeEl.style.right = (100 - hi) + '%';
  // No visible label (2026-09-01, compact main-toolbar placement) — current
  // range is conveyed via the container's title tooltip instead.
  row.title = `Risk Range %: ${lo}–${hi}%`;
}

// ---- Portfolio Mix panel (renderPortfolioMix/_pmHeldRows/_pmCashTotal) --
// REMOVED (2026-09-01, user request: "remove the side panel from
// actionable screen altogether"). The whole Actionable side panel
// (#actSidePanel) is gone -- every panel it had (Volatility, Major
// Markets, Econ Indicators, Earnings, Dollar Correlation, Sectors,
// Portfolio Mix, Rates & Duration, Credit, USD & Currency, Commodities,
// Tech & ETFs, Crypto, Country ETFs) already has a Dashboard equivalent.
// Portfolio Mix specifically: Asset Allocation/Beta/Sector/Concentration
// via web/portfolio_mix.js (shared, unchanged); Macro Stance (the one pie
// that wasn't already on Dashboard, since it needs actionDisplay()'s
// vocabulary) moved to web/app.js::_renderDashMacroStance() -- see that
// function's own comment and #dashPortfolioMixSection's dpmBetaCard in
// web/index.html (Macro Stance now takes that card's pie slot; Beta
// demoted to a legend-only row underneath it).
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

// ---- Task 2: EOD feed missing banner ----
async function checkEodFeed() {
  const banner = $('eodMissingBanner');
  if (!banner || !state.date) return;
  try {
    const f = await fetchJson('/api/eod-feed-status?date=' +
      encodeURIComponent(state.date));
    if (f && f.missing) {
      $('eodMissingMsg').textContent = f.message ||
        'EOD price feed (TOSL) missing for this date — recommendations may be unreliable.';
      banner.style.display = 'block';
      // Apply warning style to every data row
      document.querySelectorAll('#actGrid tbody tr').forEach(tr => {
        tr.style.opacity = '0.7';
      });
    } else {
      banner.style.display = 'none';
      document.querySelectorAll('#actGrid tbody tr').forEach(tr => {
        tr.style.opacity = '';
      });
    }
  } catch (_) {
    banner.style.display = 'none';
  }
}

// ---- Auto-refresh once when fresh TL (TOSL) / Yahoo quote data lands ------
// Mirrors hedgeye_panel.js's checkForNewEmail: poll a lightweight signal and
// reload only when it changes, so the grid picks up new prices without
// waiting for a manual Refresh click, and without refreshing on every poll.
let _lastDataSignal = null;
async function checkForNewData() {
  try {
    const status = await fetchJson('/api/actionable/data-status');
    const sig = (status && status.last_at) || '';
    if (_lastDataSignal !== null && sig !== _lastDataSignal) {
      loadActionable({ preserveState: true });
      checkFreshness();
      checkEodFeed();
    }
    _lastDataSignal = sig;
  } catch (_) { /* non-critical, ignore */ }
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
  let stopCount = 0;
  for (const r of state.baseRows) {
    const a = _chipAction(r);
    if (counts[a] !== undefined) counts[a] += 1;
    if (r.stop_breached) stopCount += 1;
  }
  const wrap = $('summaryChips');
  wrap.innerHTML = '';
  const all = document.createElement('div');
  all.className = 'act-chip' + (state.filters.action === '' ? ' active' : '');
  all.innerHTML = `<span>ALL</span><span class="count">${state.baseRows.length}</span>`;
  all.onclick = () => {
    state.filters.action = '';
    applyClientFilter();
  };
  wrap.appendChild(all);
  // S / B group chips — aggregate REMOVE+REDUCE / INCREASE+ADD so the whole
  // sell or buy side can be isolated in one click without picking a single
  // granular bucket. The individual REMOVE/OVER_MAX/REDUCE/INCREASE/ADD/
  // HOLD/NONE chips (SA/OM/SR/BM/BA/H/N) were dropped 2026-09-01 — user:
  // "keep chips All, S, B, Stop and remove other chips" — down to just the
  // four requested. Their filter values (state.filters.action = 'REMOVE'
  // etc.) and matchesBaseFilters/_chipAction handling are untouched, only
  // no chip sets them anymore.
  const groupChip = (key, label, title) => {
    const n = _ACTION_GROUPS[key].reduce((sum, a) => sum + (counts[a] || 0), 0);
    const chip = document.createElement('div');
    chip.className = 'act-chip act-chip-group-' + key.toLowerCase()
                   + (state.filters.action === key ? ' active' : '');
    chip.title = title;
    chip.innerHTML = `<span>${label}</span><span class="count">${n}</span>`;
    chip.onclick = () => {
      state.filters.action = (state.filters.action === key) ? '' : key;
      applyClientFilter();
    };
    return chip;
  };
  wrap.appendChild(groupChip('SELL', 'S', 'All sells — SELL ALL + SELL SOME (REMOVE + REDUCE)'));
  wrap.appendChild(groupChip('BUY', 'B', 'All buys — BUY MORE + BUY TO MIN (INCREASE + ADD)'));
  // TASK_119: STOP chip — orthogonal to the action buckets above (a REDUCE
  // row can also be stop_breached), so it toggles independently rather than
  // joining the mutually-exclusive action-chip set.
  const stopChip = document.createElement('div');
  stopChip.className = 'act-chip act-chip-stop' + (state.filters.stopOnly ? ' active' : '');
  stopChip.title = 'Held positions that just crossed below their Trade or Trend line (prior 3 days above, today below)';
  stopChip.innerHTML = `<span>STOP</span><span class="count">${stopCount}</span>`;
  stopChip.onclick = () => {
    state.filters.stopOnly = !state.filters.stopOnly;
    applyClientFilter();
  };
  wrap.appendChild(stopChip);
}

// Portfolio-composition chips: held $ grouped by normalized asset class
// (r._assetClass — see _normAssetClass). Computed from state.baseRows (every
// active filter EXCEPT this one's own selection — see the asset_class check
// in applyClientFilter's second stage) so the amounts reflect whatever else
// is filtered (Source/Acct/Trade Mode/Conviction/...), same "filtered but not
// self-restricted" reasoning as the action-chip counts in renderSummary().
// Doubles as the filter UI — clicking a chip toggles state.filters.asset_class.
function renderAssetClassSummary() {
  const wrap = $('assetClassSummary');
  if (!wrap) return;
  const byClass = new Map();  // class -> dollars
  for (const r of state.baseRows) {
    if (!r.held_today) continue;
    const cls = r._assetClass || 'Unclassified';
    const amt = Math.abs(Number(r.current_position_dollar) || 0);
    byClass.set(cls, (byClass.get(cls) || 0) + amt);
  }
  wrap.innerHTML = '';
  if (byClass.size === 0) return;
  const entries = Array.from(byClass.entries()).sort((a, b) => b[1] - a[1]);
  for (const [cls, dollars] of entries) {
    const chip = document.createElement('div');
    chip.className = 'act-chip' + (state.filters.asset_class === cls ? ' active' : '');
    chip.title = `${cls}: ${window.fmtUsd ? window.fmtUsd(dollars) : dollars} held — click to filter`;
    chip.innerHTML = `<span>${escapeHtml(cls)}</span><span class="count">`
                    + `${window.fmtUsd ? window.fmtUsd(dollars, { compact: true }) : Math.round(dollars)}</span>`;
    chip.onclick = () => {
      state.filters.asset_class = (state.filters.asset_class === cls) ? '' : cls;
      applyClientFilter();
    };
    wrap.appendChild(chip);
  }
}

// Held $ by GICS-11 equity sector (r.sector, already shipped on every
// /api/actionable row from drv_actionable.sector — no API change needed).
// Same "computed from baseRows, doubles as the filter UI" pattern as
// renderAssetClassSummary above.
function renderSectorSummary() {
  const wrap = $('sectorSummary');
  if (!wrap) return;
  const bySector = new Map();  // sector -> dollars
  for (const r of state.baseRows) {
    if (!r.held_today) continue;
    const sec = r.sector || 'Unclassified';
    const amt = Math.abs(Number(r.current_position_dollar) || 0);
    bySector.set(sec, (bySector.get(sec) || 0) + amt);
  }
  wrap.innerHTML = '';
  if (bySector.size === 0) return;
  const entries = Array.from(bySector.entries()).sort((a, b) => b[1] - a[1]);
  for (const [sec, dollars] of entries) {
    const chip = document.createElement('div');
    chip.className = 'act-chip' + (state.filters.sector === sec ? ' active' : '');
    chip.title = `${sec}: ${window.fmtUsd ? window.fmtUsd(dollars) : dollars} held — click to filter`;
    chip.innerHTML = `<span>${escapeHtml(sec)}</span><span class="count">`
                    + `${window.fmtUsd ? window.fmtUsd(dollars, { compact: true }) : Math.round(dollars)}</span>`;
    chip.onclick = () => {
      state.filters.sector = (state.filters.sector === sec) ? '' : sec;
      applyClientFilter();
    };
    wrap.appendChild(chip);
  }
}

// Style labels carried by a row (drv_macro_score.style_stances — Momentum/
// High Beta/Low Beta/Value/Dividend/Cyclical/Defensives/Secular/Small Caps/
// Mid Caps/...). Kept as a JSONB array, not a single value, because a symbol
// can carry several independent style tags that disagree with each other.
function _rowStyleLabels(r) {
  const arr = Array.isArray(r.style_stances) ? r.style_stances : [];
  return arr.map(s => s && s.label).filter(Boolean);
}

// Held $ by equity style. A row can contribute to more than one chip (a
// symbol tagged both Momentum and Small Caps counts toward both totals),
// unlike asset_class/sector which are one-per-row buckets.
function renderStyleSummary() {
  const wrap = $('styleSummary');
  if (!wrap) return;
  const byStyle = new Map();  // style label -> dollars
  for (const r of state.baseRows) {
    if (!r.held_today) continue;
    const amt = Math.abs(Number(r.current_position_dollar) || 0);
    for (const label of _rowStyleLabels(r)) {
      byStyle.set(label, (byStyle.get(label) || 0) + amt);
    }
  }
  wrap.innerHTML = '';
  if (byStyle.size === 0) return;
  const entries = Array.from(byStyle.entries()).sort((a, b) => b[1] - a[1]);
  for (const [label, dollars] of entries) {
    const chip = document.createElement('div');
    chip.className = 'act-chip' + (state.filters.style === label ? ' active' : '');
    chip.title = `${label}: ${window.fmtUsd ? window.fmtUsd(dollars) : dollars} held — click to filter`;
    chip.innerHTML = `<span>${escapeHtml(label)}</span><span class="count">`
                    + `${window.fmtUsd ? window.fmtUsd(dollars, { compact: true }) : Math.round(dollars)}</span>`;
    chip.onclick = () => {
      state.filters.style = (state.filters.style === label) ? '' : label;
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
  // Placeholder reads "Source" (no separate label), same convention as the
  // Acct/Sectors/Asset Classes/Styles dropdowns.
  sel.innerHTML = '<option value="">Source</option>';
  for (const c of Array.from(have).sort()) {
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    if (c === cur) o.selected = true;
    sel.appendChild(o);
  }
  _syncTriggerSourcePills();
}

// Keeps the RTA/EC/SC/IC quick-filter pills' active state in sync with
// state.filters.source (RTA/SC) or the etfchg_only/iichg_only flags (EC/IC),
// whichever control (pill or dropdown) last changed it.
function _syncTriggerSourcePills() {
  const wrap = $('triggerSourcePills');
  if (!wrap) return;
  wrap.querySelectorAll('[data-src-pill]').forEach(el => {
    el.classList.toggle('active', state.filters.source === el.dataset.srcPill);
  });
  wrap.querySelectorAll('[data-flag-pill]').forEach(el => {
    el.classList.toggle('active', !!state.filters[el.dataset.flagPill]);
  });
}

// Returns the display name for an account_number using state.allAccounts lookup.
function _acctDisplayName(acctNum) {
  const a = state.allAccounts.find(x => x.account_number === acctNum);
  return a ? (a.display_name || a.account_number) : acctNum;
}

// Returns comma-separated display names for a held_accounts string (account_numbers).
function _heldAccountsDisplay(held) {
  if (!held) return '';
  return held.split(',').map(n => _acctDisplayName(n.trim())).join(', ');
}

function _availableAccounts() {
  const have = new Set();
  for (const r of state.allRows) {
    if (!r.held_accounts) continue;
    for (const a of r.held_accounts.split(',')) {
      const t = a.trim();
      if (t) have.add(t);
    }
  }
  return have;
}

function renderAccountFilter() {
  const sel = $('accountFilter');
  if (!sel) return;
  // Use dedicated accounts list (objects with account_number + display_name).
  // Fall back to scraping raw account_numbers from state.allRows.
  const fallbackNums = state.allAccounts.length ? null : _availableAccounts();
  const accounts = state.allAccounts.length
    ? state.allAccounts
    : Array.from(fallbackNums).map(n => ({ account_number: n, display_name: n }));

  if (state.filters.account && !accounts.some(a => a.account_number === state.filters.account)) {
    state.filters.account = '';
  }
  const cur = state.filters.account;
  // Placeholder reads "Acct" (no separate <label> anymore), same convention
  // as the Sectors/Asset Classes/Styles dropdowns.
  sel.innerHTML = '<option value="">Acct</option>';
  const sorted = [...accounts].sort((a, b) =>
    (a.display_name || a.account_number).localeCompare(b.display_name || b.account_number));
  for (const a of sorted) {
    const o = document.createElement('option');
    o.value = a.account_number;
    o.textContent = a.display_name || a.account_number;
    if (a.account_number === cur) o.selected = true;
    sel.appendChild(o);
  }
}


function syncFilterUi() {
  // Sync all UI elements to current state.filters
  const f = state.filters;
  const heldOnly = $('heldOnly');
  if (heldOnly) {
    heldOnly.classList.toggle('active', !!f.held_only);
    heldOnly.setAttribute('data-tip', f.held_only ? 'Positions Only  →  Show All' : 'All Symbols  →  Positions Only');
  }
  const acctFilter = $('accountFilter'); if (acctFilter) acctFilter.value = f.account || '';
  const showHidden = $('showHidden');
  if (showHidden) {
    showHidden.classList.toggle('active', !!f.show_hidden);
    showHidden.setAttribute('data-tip', f.show_hidden ? 'Show Hidden  →  Active Only' : 'Active Only  →  Show Hidden');
  }
  const tradeModeBtn = $('tradeModeBtn');
  if (tradeModeBtn) tradeModeBtn.classList.toggle('active', !!f.trade_mode);
  // 2026-08-28: "Non-Strict" button -- mutually exclusive alternate view to
  // Trade Mode (not a sub-toggle anymore, always visible).
  const tradeModeDiffBtn = $('tradeModeDiffBtn');
  if (tradeModeDiffBtn) tradeModeDiffBtn.classList.toggle('active', !!f.trade_mode_diff);
  const multiSymBtn = $('multiSymBtn');
  if (multiSymBtn) multiSymBtn.classList.toggle('active', !!(f.symbols_multi && f.symbols_multi.length));
  const sym = $('symbolSearch');        if (sym) sym.value = f.symbol_search || '';
  const bp = $('bullProbFilter');       if (bp) bp.value = f.bull_prob_min || 0;
  const ag = $('agreementFilter');      if (ag) ag.value = f.agreement_class || '';
  // 2026-08-31 -- Sector/Asset class/Style dropdowns (all values, not just
  // held) -- same sync-on-load/refresh pattern as Agree above.
  const sf = $('sectorFilter');         if (sf) sf.value = f.sector || '';
  const acf = $('assetClassFilter');    if (acf) acf.value = f.asset_class || '';
  const styf = $('styleFilter');        if (styf) styf.value = f.style || '';
  _syncRrSliderUi();
  // conviction segmented
  document.querySelectorAll('#convictionCtrl button').forEach(b => {
    b.classList.toggle('seg-active', b.dataset.conv === f.conviction);
  });
  // actionable_only toggle
  const aoBtn = $('actionableOnlyBtn');
  if (aoBtn) {
    aoBtn.classList.toggle('active', !!f.actionable_only);
    aoBtn.setAttribute('data-tip', f.actionable_only ? 'Actionable Only  →  Show All' : 'Show All  →  Actionable Only');
  }
}

// A Source/Account/Symbol/P(up) lookup is a targeted search — the row(s) it
// names shouldn't be silently swallowed by an unrelated toggle (Positions
// Only / Active Only / Actionable Only / Trade Mode) left on from earlier
// browsing. Reset those four to their "show everything" state whenever one
// of the lookup filters is actively set to a non-empty value.
function _resetToggleFiltersForLookup() {
  const f = state.filters;
  f.held_only = false;
  f.show_hidden = true;
  f.actionable_only = false;
  f.trade_mode = false;
  syncFilterUi();
}

function clearAllFilters() {
  const f = state.filters;
  f.action = ''; f.source = ''; f.account = ''; f.held_only = false;
  f.show_hidden = false; f.actionable_only = true;
  f.symbol_search = ''; f.conviction = 'any';
  f.bull_prob_min = 0;
  f.agreement_class = '';
  f.symbols_multi = [];
  f.etfchg_only = false; f.iichg_only = false;
  f.sector = ''; f.style = ''; f.asset_class = '';
  f.rr_min = 0; f.rr_max = 100;
  const bpEl = $('bullProbFilter'); if (bpEl) bpEl.value = '0';
  const agEl = $('agreementFilter'); if (agEl) agEl.value = '';
  const sfEl = $('sectorFilter'); if (sfEl) sfEl.value = '';
  const acfEl = $('assetClassFilter'); if (acfEl) acfEl.value = '';
  const styfEl = $('styleFilter'); if (styfEl) styfEl.value = '';
  const rrMinEl = $('actRrMin'); if (rrMinEl) rrMinEl.value = '0';
  const rrMaxEl = $('actRrMax'); if (rrMaxEl) rrMaxEl.value = '100';
  _syncRrSliderUi();
  _syncTriggerSourcePills();
  // Reset sort to default actionability order (updateSortIndicators called in renderGrid)
  state.sort = { key: '_priority', dir: -1, type: 'num' };
  // Reset show_hidden -> requires refetch (show_hidden=false excludes acted/suppressed from API)
  syncFilterUi();
  loadActionable();
}

// ---- grid ----
// Helper: render other (non-winning) source actions as inline pills
// ---- source-data hover popover ----
const _srcDataCache = new Map();   // symbol -> { RR:{...}, ETF:{...}, ... }
let _srcPopEl = null;
// F2: lazy MACRO detail cache, keyed "sym@date" (macro_detail/macro_howto are
// no longer shipped with every /api/actionable row — see showMacroPop below).
const _macroDetailCache = new Map();
const _FEED_SRC = ['RR', 'ETF', 'PS', 'SSS'];

function _saFor(row, src) {
  let sa = row && row.source_actions;
  if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
  if (!Array.isArray(sa)) return null;
  return sa.find(s => (s.source || s.source_code || '') === src) || null;
}

// Action severity rank — REMOVE strongest. Mirrors the consolidation sort.
const ACTION_RANK = { REMOVE: 4, REDUCE: 3, INCREASE: 2, ADD: 1, HOLD: 0 };

// Per-code colors shared by Sources and Technical columns — matches Final Call / Portfolio palette.
const ACTION_CODE_COLOR = {
  SA:'#d83a3a',
  SS:'#e07c1a', STM:'#e07c1a', SO:'#e07c1a', SW:'#e07c1a', SWW:'#e07c1a',
  BM:'#2f9e2f', BS:'#2f9e2f',
  BMN:'#1f7af2', BW:'#1f7af2', BSW:'#1f7af2',
};
function _actionCodeColor(disp) {
  return ACTION_CODE_COLOR[disp.code] || (disp.side === 'sell' ? '#d83a3a' : disp.side === 'buy' ? '#2f9e2f' : '#888');
}

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
// Aggregate summary-chip groups — S (all sells) / B (all buys) — map onto
// state.filters.action alongside the individual REMOVE/REDUCE/INCREASE/ADD
// values; matched in matchesBaseFilters via _chipAction membership.
const _ACTION_GROUPS = {
  SELL: ['REMOVE', 'REDUCE'],
  BUY:  ['INCREASE', 'ADD'],
};
// Chip bucket for a row — derived from finalCall() so filter pills match
// what the Final Call column actually shows.
// Returns one of: REMOVE | REDUCE | INCREASE | ADD | HOLD | OVER_MAX | NONE
function _chipAction(row) {
  if (_isOverMaxOverlay(row)) return 'OVER_MAX';
  const fc = finalCall(row);
  if (!fc.feasible) return 'NONE';
  const code = (fc.code || '').toUpperCase();
  if (code === 'SA') return 'REMOVE';
  if (code === 'SS' || code === 'STM' || code === 'SO') return 'REDUCE';
  if (code === 'BM' || code === 'BS') return 'INCREASE';
  if (code === 'BMN') return 'ADD';
  if (fc.side === 'neutral' || code === 'HOLD') return 'HOLD';
  return 'NONE';
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

// ETF/II source-reason entries carry the shared weekly-bundle snapshot_date
// (e.g. last Sunday's rotation), not the date an intra-week ETFCHG/IICHG
// event actually landed. The row already carries that receipt date via the
// 5-day-lookback etfchg_date/iichg_date fields (api/routers/dash.py) — this
// looks it up so the source badge can show both.
function _srcChangeEventDate(row, srcCode) {
  const sc = (srcCode || '').toUpperCase();
  if (sc === 'ETF') return row.etfchg_date || null;
  if (sc === 'II') return row.iichg_date || null;
  return null;
}

// Source-code abbreviations for the Sources column's tight 2-char label.
// Most codes are legible from their own first 2 chars (RR, PS, II, ETF...);
// a few need an explicit override because the blind slice reads as
// something else entirely -- TOP5 -> "TO" looked like nothing. 2026-08-19
// (user decision "change TO to T5 everywhere"): only overrides listed here.
const _SRC_ABBR = { TOP5: 'T5', MACROSHOW: 'MS' };
function _srcAbbr(srcCode) {
  const up = (srcCode || '').toString().toUpperCase();
  return _SRC_ABBR[up] || (srcCode || '').toString().slice(0, 2);
}

// ── Source sub-line (Action cell second line) ──────────────────────────────
// Returns compact HTML like: RR·<colored>BS</colored>  II·<colored>BM</colored>
// Winning source first, then others sorted by severity.  Empty → ''.
// Per-source reason lines for the Sources column: "SRC <icon> reason".
function _srcReasonsHtml(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const rows = winner.concat(others).map(s => {
    const srcCode = s.source || s.source_code || '?';
    const src    = escapeHtml(_srcAbbr(srcCode));
    const ic     = actionIcon(s.action);
    const reason = s.reason ? escapeHtml(s.reason) : '';
    const dtRaw  = fmtMD(s.snapshot_date);
    const dt     = dtRaw ? `<span style="font-size:9px;font-weight:400;opacity:0.7;"> (${dtRaw.replace(/^0/, '')})</span>` : '';
    const chgRaw = fmtMD(_srcChangeEventDate(r, srcCode));
    const chg    = (chgRaw && chgRaw !== dtRaw)
      ? `<span style="font-size:9px;font-weight:400;opacity:0.7;"> → ${chgRaw.replace(/^0/, '')}</span>`
      : '';
    const dropPct = _dropPctPillHtml(s);
    // 2026-08-20: winning-source indicator -- same "drove it" black pill
    // the Action popup's driver bullets already use (_actpopDriverBullets),
    // so a row with several source lines shows at a glance which one
    // actually determined the row's action instead of just sorting the
    // winner first with no visual distinction from the others. Shortened
    // to just "D" to save space in the compact grid column.
    const droveIt = srcCode === winning
      ? `<span class="dv-tag drove-it-pill" style="margin-left:3px;" title="Drove the action">D</span>` : '';
    return `<div class="src-reason-line">
      <span class="src-ic" style="color:${ic.color};">${ic.glyph}</span>
      <span class="src-tag">${src}${dt}${chg}</span>${droveIt}
      <span class="src-rsn">${reason}${dropPct}</span>
    </div>`;
  });
  return `<div class="src-reasons">${rows.join('')}</div>`;
}

function _srcTooltip(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const lines = winner.concat(others).map(s => {
    const isWin = (s.source || s.source_code || '') === winning;
    const src   = s.source || s.source_code || '?';
    const ic    = actionIcon(s.action);
    const act   = (s.action || '').toUpperCase();
    const dtRaw = fmtMD(s.snapshot_date);
    const chgRaw = fmtMD(_srcChangeEventDate(r, src));
    const dt    = (dtRaw || '?') + (chgRaw && chgRaw !== dtRaw ? ` → ${chgRaw}` : '');
    const rsn   = s.reason || '';
    return (isWin ? '✓ ' : '  ') + src + '  ' + ic.glyph + '  ' + act + '  ' + dt + '  ' + rsn;
  });
  return 'ALL SOURCES\n' + lines.join('\n');
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
  const threshold = (state.convictionProvenEdgeMin != null)
    ? state.convictionProvenEdgeMin : 0.5;
  for (const f of fires) {
    const id = String(f.rule_id || f.id || f);
    if (sc[id] && sc[id].edge_20d != null && Number(sc[id].edge_20d) > threshold) return true;
  }
  return false;
}

// Returns the hidden reason string for a row, or null if not hidden.
function _hiddenReason(r) {
  if (r.suppressed_reason) return 'Snoozed: ' + r.suppressed_reason;
  const ua = (r.last_user_action || '').toUpperCase();
  if (ua === 'DONE' || ua === 'SKIPPED' || ua === 'OVERRIDDEN') return 'Acted: ' + ua;
  if (ua === 'SNOOZED' && (!r.snooze_until || r.snooze_until >= state.date)) return 'Acted: SNOOZED';
  if (!r.consolidated_action) return 'No action';
  if (!r._amt) return 'AMT$ = 0';
  const ca = (r.consolidated_action || '').toUpperCase();
  if (ca === 'REMOVE' && !r.held_today) return 'REMOVE – not held';
  return null;
}

// Conviction badge HTML for grid cell.
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
/**
 * finalCall(row) -> {label, code, side, strength, confidence, feasible}
 *
 * D6: server (derive_actionable.py::_compute_final_call) is the single source
 * of truth. This function reads final_code/final_side/fc_* when present.
 * The client-side computation below is a fallback ONLY for:
 *   (a) historical dates pre-TASK_53 migration (no final_code column yet), or
 *   (b) rows returned by a non-derived path (e.g. direct DB query without derive).
 * Do NOT add decision logic here — keep it in _compute_final_call on the server.
 *
 * Two-driver hierarchical decision (mirrored server-side):
 *   Sources (consolidated_action) = strategic: gates ownership (own it or exit).
 *   Technical (rr_action)         = tactical: trim/add while owning.
 *   Rules/edge are NOT consulted here — kept in the Rules column for manual
 *   cross-reference only.
 */
// Deterministic-gate reason classifier (2026-08-12) — walks the SAME branch
// order as etl/derive_actionable.py::_compute_final_call() purely to name
// WHY a 'gate' confidence tier fired, for the Gate badge tooltip. The
// server doesn't persist that reason text (no gate_reason column on
// drv_actionable) so this re-derives it client-side from the same fields
// already on the row (consolidated_action, rr_action, held_today,
// stop_breached, the Max-overlay). Returns null if the row doesn't land in
// a gate branch (caller should fall back to the generic tooltip text).
function _gateReasonFor(row) {
  var ca  = (row.consolidated_action || '').toUpperCase();
  var rra = (row.rr_action           || '').toUpperCase();
  if (!ca || ca === 'NONE') return null;

  var atMax       = _isOverMaxOverlay(row);
  var isHeld      = !!row.held_today;
  var srcIsExit   = (ca === 'REMOVE' || ca === 'SA');
  var srcIsReduce = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
  var srcIsBuy    = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
  var srcIsAdd    = (ca === 'ADD' || ca === 'BMN');
  var techIsSell    = (rra === 'SS' || rra === 'STM' || rra === 'SO' || rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
  var techIsBuy     = (rra === 'BS' || rra === 'BM' || rra === 'INCREASE');
  var techIsBuyMin  = (rra === 'BMN' || rra === 'ADD');
  var techIsNeutral = (!techIsSell && !techIsBuy && !techIsBuyMin);

  // 1. Stop breach downgrade (TASK_119) — highest priority, checked first
  //    server-side too (etl/derive_actionable.py, stop_breached block).
  if (row.stop_breached && (ca === 'ADD' || ca === 'INCREASE')) {
    return 'Held position crossed its stop (' + (row.stop_signal || 'stop') + ') — ADD/INCREASE downgraded to HOLD';
  }
  // 2. Strategic exit gate: exit signal or over category Max.
  if (srcIsExit || atMax) {
    if (!isHeld && !atMax) return 'Exit signal but not held — no action feasible';
    return atMax ? 'Over category Max — trim back to cap'
                 : 'Sources: exit signal — Technical not evaluated';
  }
  // 3. Don't-initiate guard: not held, Sources doesn't endorse buying.
  if (!isHeld && !srcIsBuy) {
    return 'Not held + Sources don’t endorse buying — hold';
  }
  // 4. Technical confirms buy, but capped at/over Max.
  if ((techIsBuy || techIsBuyMin) && atMax) {
    return 'At/over category Max — cannot add more';
  }
  // 5/6. Technical neutral — either establishing a starter position, or
  // truly no signal from either lens.
  if (techIsNeutral) {
    if (!isHeld && srcIsAdd) return 'Sources says ADD, Technical neutral — establishing position';
    if (!srcIsReduce) return 'No active signal — Sources and Technical both neutral';
  }
  return null;
}

// 2026-08-16: sibling to _gateReasonFor -- same branch order/classifiers,
// crisp per-scenario text for the High/Mixed confidence tiers instead of
// the flat "Sources and Technical align"/"...conflict" the popover used to
// show regardless of which of the several High/Mixed branches actually
// fired. User: "did we add these to tooltip with crisp reasoning/why?" —
// Gate already was (this function's sibling); High/Mixed weren't. Returns
// null when neither tier's scenario matches (falls back to the generic
// text in the caller).
function _highMixedReasonFor(row) {
  var ca  = (row.consolidated_action || '').toUpperCase();
  var rra = (row.rr_action           || '').toUpperCase();
  if (!ca || ca === 'NONE') return null;

  var isHeld      = !!row.held_today;
  var srcIsReduce = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
  var srcIsBuy    = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
  var srcIsAdd    = (ca === 'ADD' || ca === 'BMN');
  var techIsSell    = (rra === 'SS' || rra === 'STM' || rra === 'SO' || rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
  var techIsBuy     = (rra === 'BS' || rra === 'BM' || rra === 'INCREASE');
  var techIsBuyMin  = (rra === 'BMN' || rra === 'ADD');
  var src = (row.winning_source || '').toString().toUpperCase();

  // Live-trigger bypass (RTA/SSSCHG) — resolves the buy on its own, no
  // Technical confirmation needed. Checked first, same as the server.
  if ((src === 'RTA' || src === 'SSSCHG') && srcIsBuy) {
    return src + ' is a live, same-day trigger — resolves the buy on its own, Technical confirmation not required';
  }
  if (techIsSell) {
    if (!isHeld) return 'Technical says sell, but nothing is held to sell — netted to HOLD';
    if (srcIsReduce) return 'Sources and Technical both say sell — confirmed';
    return 'Technical says sell but Sources doesn’t confirm it — Technical overrides the call, flagged as Mixed';
  }
  if (techIsBuy || techIsBuyMin) {
    if (srcIsReduce) return 'Technical says buy but Sources says reduce — direct conflict, netted to HOLD';
    if (!isHeld && srcIsAdd) return 'Sources and Technical both confirm — starter position';
    if (srcIsBuy) return 'Sources and Technical both confirm buy';
    return 'Technical says buy but Sources isn’t backing it — Technical driving the call alone';
  }
  if (srcIsReduce) return 'Sources says reduce but Technical has no read either way — flagged as Mixed';
  return null;
}

function finalCall(row) {
  // D6: prefer server-computed final call (derived at ETL time via _compute_final_call).
  // Client-side code below is a thin read-only fallback for pre-migration rows.
  if (row.final_code !== undefined && row.final_code !== null) {
    var _feasible = (row.fc_feasible === true || row.fc_feasible === 'true');
    var _strength = Number(row.fc_strength) || 0;
    var _confidence = row.fc_confidence || 'none';
    var _code = row.final_code || '';
    var _label = row.final_action || '';
    var _side = row.final_side || 'neutral';
    return {
      label: _label, code: _code, side: _side,
      strength: _strength, confidence: _confidence, feasible: _feasible,
      gateReason: _confidence === 'gate' ? _gateReasonFor(row) : null,
    };
  }

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

// Two-way signal reasons for the ACTION column's icon: { warn: [...], buy: [...] }.
// warn = amber "argues against this call" reasons; buy = green "argues for /
// confirms this call" reasons. A row can only show one icon color — warn
// takes precedence over buy when both fire (caution wins on conflict).
// Checks are written buy-oriented first (e.g. oversold RSI = supportive)
// then swapped for sell-side rows (2026-08-12) so the color always reflects
// agreement with the row's own Final Call side, not a hardcoded buy
// assumption.
// Checks earnings proximity, VLM, IV/vol caution, RSI, and Rules(edge).
// MACD/MACDH momentum moved out (2026-08-20) to a caret on the grid
// columns themselves — see _macdCaret. No-fired-rules is not itself a
// warning or a buy signal.
// Standalone earnings-proximity check (split out from _signalReasons
// 2026-08-01) — earnings-date risk is a different kind of caution than
// technical/rules signals: it's calendar-driven, not resolved by waiting
// for a better RSI/MACD/IV read, and applies uniformly regardless of the
// direction of the other signals. Returns the days-until-earnings number,
// or null if not within the warning window (mt.earnings_days: NUMERIC
// days-until, decremented daily; -99 sentinel means no data).
function _earningsWarning(row) {
  const ed = row.earnings_days;
  if (ed == null) return null;
  const n = Number(ed);
  if (n >= 0 && n <= 3) return n;
  return null;
}

function _signalReasons(row, side) {
  const isSell = side === 'sell';
  const warn = [];
  const buy = [];

  // 2026-08-10 -- advisory-only buy warnings (never touch consolidated_
  // action/final_code server-side -- see etl/derive_actionable.py's own
  // comment on these two columns). User: "I should only buy a stock if
  // above trade/trend and at LRR ... can we have them as warnings in case
  // of buys instead of adding a concrete rule?"
  // Meaningless once the row's own Final Call is a sell (nothing to swap
  // them into that makes sense), so skip entirely on sell-side rows.
  // 2026-08-20: was row.warn_not_at_lrr (server-side low_lrr atomic rule !=
  // 3, i.e. "not exactly at the LRR tier") relabeled to "price at TRR"
  // without actually checking TRR -- wired up a real calculation instead,
  // mirroring _tradabilityBreakdown's own "near LRR" convention (rawPos <=
  // 15) symmetrically at the other end of the range (rawPos >= 85).
  const _rrPosForWarn = !isSell ? _rawRrPos(row) : null;
  if (_rrPosForWarn != null && _rrPosForWarn >= 85) {
    warn.push('Caution: price at TRR');
  }
  if (!isSell && row.warn_added_this_leg) {
    warn.push('Already bought this symbol since price last closed at/above TRR — repeat buy signal this leg');
  }

  // Earnings proximity has its own dedicated icon (_earningsWarning below) —
  // split out 2026-08-01 so an earnings-date caution isn't lumped in with
  // technical/rules signals that mean something different and can be acted
  // on differently (earnings risk isn't resolved by waiting for a better
  // RSI/MACD read the way the other warn reasons are).

  // VLM: high relative volume (rvol = current/10d-avg volume) on an UP day —
  // a "buying climax" pattern (a sharp, heavy-volume pop that's often already
  // extended and prone to cool off). 2026-08-01 factor backtest (231
  // factor/bucket/horizon combos, 1wk/3wk/3mo forward returns) found this
  // beats baseline at every horizon; the opposite pairing (high RVOL + DOWN
  // day, the original hypothesis) also beat baseline at every horizon —
  // backwards from the original "distribution" assumption, so the direction
  // was flipped here rather than removed.
  if (row.rvol != null && row.pct_change != null) {
    const rvolHi = state.vlmRvolAvoidThreshold != null ? state.vlmRvolAvoidThreshold : 1.5;
    if (Number(row.rvol) >= rvolHi && Number(row.pct_change) > 0) {
      warn.push('VLM: high RVOL (' + Number(row.rvol).toFixed(1) + 'x) on an up day — possible buying climax');
    }
  }

  // IV/vol caution (mt.d_vlt_caution) intentionally NOT checked as a warning.
  // The 2026-08-01 factor backtest found extreme/elevated IV beat baseline at
  // every horizon (1wk/3wk/3mo) — opposite of the original "elevated IV =
  // caution" assumption. Not flipped to a buy signal either: plausibly a
  // confound with this period's growth-stock rally rather than a standalone
  // edge, so it's dropped from the icon pending a longer, less regime-specific
  // check.

  // MACD/MACDH momentum (2026-08-20): used to push a 'MACD momentum
  // strengthening/weakening' warn/buy signal here (MACDH sign IS the trend
  // direction — positive = MACD rising above its own signal line, <=0 =
  // falling below it). Moved out of the Action popup's caution/confirm
  // signals to a caret directly on the MACD/MACDH grid columns instead
  // (_macdCaret) — always visible there without opening the popup, so no
  // need to duplicate it in this list too.

  // RSI: two-sided, tunable via ref_settings (rsi_overbought/rsi_oversold).
  // Overbought = caution (topping risk); oversold = buy-supportive (dip/bounce).
  if (row.rsi != null) {
    const rv = Number(row.rsi);
    const hi = state.rsiOverbought != null ? state.rsiOverbought : 70;
    const lo = state.rsiOversold   != null ? state.rsiOversold   : 30;
    if (rv >= hi) warn.push('RSI overbought (' + rv + ')');
    else if (rv <= lo) buy.push('RSI oversold (' + rv + ')');
  }

  // Winning Source / Sector track record (2026-08-20, revised same day
  // after review): reuses v_factor_scorecard, the same backtest data the
  // Tradability box's Source item and the grid's RSI/IV edge tags already
  // draw from. -3pp threshold (meaningfully negative, not just noise)
  // mirrors _tradabilityDeltaColor's own -1.5 cutoff for "this clearly
  // hurts." Buy-oriented framing (swapped below for sell-side rows) like
  // every other check here — win_rate is "forward 20d was positive," a bad
  // number is bad news for a BUY specifically.
  // Gated on n_symbols>=5 via _factorWinRateDeltaGated (not just row-count
  // n) -- found live: 'Sector' had single-ticker buckets (Gold n_symbols=2,
  // Fixed Income/Commodities/'Health Care' n_symbols=1 each) whose large
  // row-count came from one ticker's daily history repeating for months,
  // not a real sector-wide sample. Also dropped "proven" from the wording
  // -- v_factor_scorecard's own confidence column is one-sided (only ever
  // certifies a *positive* edge "proven"; PS/Gold/etc all show 'unproven'
  // even with a real, gated sample), so claiming "proven negative" was
  // never accurate regardless of n_symbols.
  if (row.winning_source) {
    const srcCode = row.winning_source.toString().toUpperCase();
    const g = _factorWinRateDeltaGated('Winning source', srcCode);
    if (g && g.delta < -3) {
      warn.push('Winning source ' + srcCode + ' historically underperforms (' + g.delta.toFixed(1) + 'pp vs baseline, ' + g.nSymbols + ' symbols)');
    }
  }
  // 'N/A' is a real v_factor_scorecard bucket (no sector classification),
  // not an actual sector -- excluded regardless of n_symbols.
  if (row.sector && row.sector !== 'N/A') {
    const g = _factorWinRateDeltaGated('Sector', row.sector);
    if (g && g.delta < -3) {
      warn.push('Sector ' + row.sector + ' historically underperforms (' + g.delta.toFixed(1) + 'pp vs baseline, ' + g.nSymbols + ' symbols)');
    }
  }

  // Rules (edge), buy-oriented framing (swapped below for sell-side rows):
  // a fired buy-side rule with non-positive or unproven edge, or a fired
  // sell-side rule with a proven-positive (historically correct) edge,
  // argues against buying. Mirror case: a fired buy-side rule with a
  // *proven* positive edge is buy-supportive.
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (Array.isArray(fires)) {
    const sc = state.scorecard || {};
    for (const f of fires) {
      const id = String(f.rule_id || f.id || f);
      const s = sc[id];
      if (!s || s.edge_20d == null) continue;
      const e = Number(s.edge_20d);
      const conf = s.confidence || 'unproven';
      const ruleSide = _ruleSide(id);
      if (ruleSide === 'buy') {
        if (e <= 0 || conf === 'unproven') {
          warn.push('Rule ' + id + ' fired buy with ' + (conf === 'unproven' ? 'unproven' : 'negative') + ' edge');
        } else if (conf === 'proven') {
          buy.push('Rule ' + id + ' fired buy with proven positive edge (+' + e.toFixed(1) + '%)');
        }
      } else if (ruleSide === 'sell' && e > 0) {
        warn.push('Sell rule ' + id + ' historically correct (+' + e.toFixed(1) + '%)');
      }
    }
  }

  // 2026-08-12 -- everything above is framed as buy caution vs buy support
  // (that's how this function originated -- see the LRR comment above).
  // For a row whose own Final Call is a SELL, that framing is inverted: e.g.
  // weakening MACD momentum isn't a caution against selling, it *confirms*
  // the sell. Swap the two lists so the icon color always reflects agreement
  // with the row's own action rather than a hardcoded buy assumption.
  return isSell ? { warn: buy, buy: warn } : { warn, buy };
}

// 2026-08-16: PVV icon folded into the Final Call confidence slot (same
// mechanism as the conviction-hold 🔭/🚫 icon below). Revised three times:
// v1 was shape-only agree/caution/conflict (✅/✋/❌), user found that
// "confusing"; v2 switched to colored ▲/▼ triangles; v3 went back to the
// original colored-circle icons (🟢/🟡/🔴) instead of triangles, with a
// text-decoration strikethrough for conflicts; user then asked for a
// proper "no entry" stop-sign glyph for the conflict case instead of a
// strikethrough -- "circle like around and a line from 1.5 hour in clock
// to 7.5" -- so conflicts now render as a small inline SVG (colored ring +
// diagonal, NE-to-SW at exactly the 1:30/7:30 clock positions) via
// _pvvStopIconSvg() rather than CSS text-decoration. 🟢 = PVV buy-tilted
// (BUY_LRR/BUY_DIP), 🔴 = PVV sell-tilted (SELL/REDUCE/TRIM/AVOID), 🟡 = a
// caution tier (BUY_WATCH/SELL_WATCH) -- same color used for both the
// plain dot (no conflict) and the stop-sign ring (conflict). Shows ANY
// time PVV has an actionable decision, regardless of what (or whether)
// ACTION itself has to say (user: "I need to see some kind of icon always
// ... regardless of the action column values") -- including the plain "—"
// no-recommendation case below, and rows where fc.side is 'neutral'
// (HOLD); those never conflict (nothing to conflict with), so always get
// the plain dot. Nothing shown when PVV has no row or is NO_ACTION/WATCH
// (no confirmed setup either way).
const _PVV_BUY_SIDE = ['BUY_LRR', 'BUY_DIP', 'BUY_WATCH'];
const _PVV_SELL_SIDE = ['SELL', 'SELL_WATCH', 'REDUCE', 'TRIM', 'AVOID'];
const _PVV_CAUTION = ['BUY_WATCH', 'SELL_WATCH'];
const _PVV_DOT_COLOR = { green: '#16a34a', red: '#dc2626', yellow: '#d97706' };
// Colored ring + diagonal from the 1:30 to 7:30 clock position (45deg NE to
// 225deg SW through center) -- a "no entry" stop-sign glyph, tinted to
// match the dot it replaces rather than a universal red.
function _pvvStopIconSvg(color) {
  return '<svg width="11" height="11" viewBox="0 0 12 12" style="vertical-align:-1px;">'
       + '<circle cx="6" cy="6" r="5" fill="none" stroke="' + color + '" stroke-width="1.6"/>'
       + '<line x1="9.5" y1="2.5" x2="2.5" y2="9.5" stroke="' + color + '" stroke-width="1.6"/>'
       + '</svg>';
}
function _pvvAgreementIcon(row, fcSide) {
  const d = row.pvv_decision;
  if (!d || d === 'NO_ACTION' || d === 'WATCH') return '';
  const pvvSide = _PVV_BUY_SIDE.includes(d) ? 'buy' : (_PVV_SELL_SIDE.includes(d) ? 'sell' : null);
  if (!pvvSide) return '';
  const info = _PVV_DECISION_INFO[d];
  const label = _PVV_LABEL[d] || d;
  const conflicts = (fcSide === 'buy' || fcSide === 'sell') && pvvSide !== fcSide;
  const title = `PVV: ${label}` + (info ? ` — ${info.meaning}` : '')
    + (conflicts ? ' — CONFLICTS with the computed action' : '');
  const tone = _PVV_CAUTION.includes(d) ? 'yellow' : (pvvSide === 'buy' ? 'green' : 'red');
  const glyph = conflicts
    ? _pvvStopIconSvg(_PVV_DOT_COLOR[tone])
    : (tone === 'yellow' ? '🟡' : (tone === 'green' ? '🟢' : '🔴'));
  return ` <span title="${escapeHtml(title)}">${glyph}</span>`;
}

// HTML for the Final Call cell (label + confidence badge).
function _finalCallHtml(row) {
  var fc = finalCall(row);
  if (!fc.feasible || fc.confidence === 'none') {
    var _pvvNone = _pvvAgreementIcon(row, fc.side).trim();
    return '<span style="color:#cbd5e1;">—</span>' + (_pvvNone ? ' ' + _pvvNone : '');
  }
  var text = fc.label || actionText(fc);  // plain-English label (e.g. "SELL ALL")
  // TASK_118: low_confidence — sell evidence comes only from rules with a
  // proven-negative historical edge (v_unproven_sell_rules). Annotation only;
  // consolidated_action / final_code are unchanged server-side. 2026-08-15:
  // gated on fc.side === 'sell' — the flag is computed purely from SELL-side
  // fired composites (etl/derive_actionable.py's own comment: "does not
  // touch consolidated_action or any BUY-side logic"), but was being applied
  // to ANY row regardless of side, muting/burying legitimate BUY signals
  // that merely had an unrelated unproven SELL rule also fire in the
  // background (found live: REAL — a real BMN buy, wrongly shown muted with
  // a "LOW CONF — Sell evidence..." badge that doesn't even apply to it).
  var isLowConf = !!row.low_confidence && fc.side === 'sell';
  // Badge
  // 2026-08-20: confidence badge (High/Gate/Mixed) removed from display —
  // user: it's after-the-fact from the Final Call decision itself
  // (_compute_final_call), not new information on top of it. fc.confidence
  // still drives the underlying decision logic (untouched); fc.gateReason /
  // _highMixedReasonFor() are no longer read by anything but left in place
  // (cheap, still correct) in case a future feature wants them again.
  // LT-conflict and PVV icons below still use this badge slot.
  var badgeHtml = '';
  // Color via actions.js token (act-*-fill gives solid fill + white text, matching Portfolio Action column)
  var fcDisp = actionDisplay(fc.code || (fc.side === 'sell' ? 'SA' : fc.side === 'buy' ? 'BS' : 'HOLD'));
  // low_confidence rows render muted/outline (-tint) instead of the solid -fill
  // so a shaky sell doesn't headline with the same visual weight as a real one.
  var colorCls = (fcDisp.colorCls || 'act-neutral') + (isLowConf ? '-tint' : '-fill');
  // 2026-08-15: LT conflict — a SELL-side Final Call on a symbol with an
  // active conviction HOLD note, OR a BUY-side Final Call on a symbol with
  // an active conviction AVOID note ("don't buy" — mirrors HOLD the other
  // direction, User: "if I have a note saying don't buy, it should do the
  // same for Buy actions"). User: "I need stronger color change... hard to
  // see the change" (the plain 🔭 icon in the SYMBOL cell wasn't loud enough
  // on a SELL ALL). A thick ring around the badge (purple for HOLD, amber for
  // AVOID), on top of whatever color the action already uses, plus the
  // direction icon next to the confidence text (High/Gate/Mixed) —
  // annotation only, the underlying action/color is untouched, this is a
  // visual overlay. (Tried a separate pill + sub-line first; user asked to
  // drop those and fold the icon into the confidence slot instead.)
  var ltAvoid = row.conviction_direction === 'AVOID';
  var ltConflict = !!row.conviction_hold && fc.side === (ltAvoid ? 'buy' : 'sell');
  if (ltConflict) {
    var ltIcon = '<span title="Long-term conviction ' + (ltAvoid ? 'avoid' : 'hold') + ' on file — '
      + escapeHtml(row.conviction_note || '') + '\n\nConflicts with this '
      + (ltAvoid ? 'BUY/ADD/INCREASE' : 'SELL/REDUCE') + ' signal.">' + (ltAvoid ? '🚫' : '🔭') + '</span>';
    badgeHtml = badgeHtml ? badgeHtml + ' ' + ltIcon : ltIcon;
  }
  var pvvIcon = _pvvAgreementIcon(row, fc.side).trim();
  if (pvvIcon) badgeHtml = badgeHtml ? badgeHtml + ' ' + pvvIcon : pvvIcon;
  // SA (SELL ALL) / BM (BUY MORE) match the HEDGEYE panel's red/green exactly;
  // weaker tiers (SS/STM/SO/SW, BS/BMN/BW) and neutral keep the standard palette.
  var hedgeyeStyle = isLowConf ? 'opacity:0.8;'
                    : fcDisp.code === 'SA' ? 'background:#d4537e;'
                    : fcDisp.code === 'BM' ? 'background:#1d9e75;'
                    : '';
  if (ltConflict) hedgeyeStyle += 'box-shadow:0 0 0 3px ' + (ltAvoid ? '#b45309' : '#7c3aed') + ';';
  var lowConfSub = isLowConf
    ? '<div style="font-size:8px;font-weight:700;color:#b45309;letter-spacing:0.3px;text-align:center;margin-top:3px;" title="Sell evidence comes only from rules with a demonstrated negative historical edge — cross-check before acting">LOW CONF</div>' : '';
  // TASK_119: STOP pill — held position that just crossed below its Trade
  // or Trend line (prior 3 days above, today below). 2026-08-12: text
  // "STOP" swapped for a down-cross icon (▼, the same glyph this file
  // already uses for a bearish stance elsewhere) + which line broke, e.g.
  // "▼TD" / "▼TN" — more compact than a word, and shows which line at a
  // glance.
  var _stopWhy = 'just crossed below its ' + (row.stop_signal === 'TN SA' ? 'Trend' : 'Trade')
    + ' line (prior 3 days above, today below)';
  var _stopIconTxt = '▼' + (row.stop_signal === 'TN SA' ? 'TN' : 'TD');
  var stopPill = row.stop_breached
    ? ` <span class="stop-pill" title="${escapeHtml(row.stop_signal || 'STOP')} — held, ${_stopWhy}; an effective ADD/INCREASE here is downgraded to HOLD">${_stopIconTxt}</span>`
    : '';
  var earningsDays = _earningsWarning(row);
  var earningsPill = earningsDays != null
    ? ' <span class="earnings-warn-pill" title="Earnings in ' + earningsDays + 'd — calendar risk, separate from technical/rules signals">📅' + earningsDays + 'd</span>'
    : '';
  var sig = _signalReasons(row, fc.side);
  var signalPill = '';
  // 2026-08-12: rich popover (one reason per line, data-signalpop + #sourcePop)
  // instead of a plain " · "-joined title attribute.
  if (sig.warn.length) {
    signalPill = ' <span class="dontbuy-warn-pill" data-signalpop="' + escapeHtml(row.tos_symbol) + '" data-signalpop-warn="1">⚠</span>';
  } else if (sig.buy.length) {
    signalPill = ' <span class="buy-signal-pill" data-signalpop="' + escapeHtml(row.tos_symbol) + '" data-signalpop-warn="0">▲</span>';
  }
  var subIcon = '<div style="font-size:9px;line-height:1.4;text-align:center;margin-top:3px;">' + badgeHtml + '</div>' + lowConfSub;
  // 2026-08-15: user asked for the action badge on its own centered line,
  // with everything else (stop/earnings/signal pills, confidence text,
  // LOW CONF) moved to line(s) below instead of crowding the same line.
  // 2026-08-16: rich hover popover (data-actionpop + _showDataPop, same
  // mechanism as PVV/signal popovers) replaces the old plain `title`
  // attribute -- user: "instead of repeating what I see for action (SELL
  // SOME) it should say how it got there." See _buildActionPopHtml().
  var badgeLine = '<div style="text-align:center;">'
    + '<span class="act-badge act-badge-sm ' + colorCls + '" style="' + hedgeyeStyle + ';cursor:help;" '
    + 'data-actionpop="' + escapeHtml(row.tos_symbol) + '">' + escapeHtml(text) + '</span>'
    + '</div>';
  var pillsLine = (stopPill || earningsPill || signalPill)
    ? '<div style="text-align:center;margin-top:2px;">' + stopPill + earningsPill + signalPill + '</div>'
    : '';
  return badgeLine + pillsLine + subIcon;
}

// ── Pass 2: Priority score (TASK_120 — dollar-weighted-edge default sort;
// TASK_122 — credible-sells-first / agreement-ranked-buys tier restructure) ──
// New tiers, top to bottom (DESCENDING — state.sort = {_priority, -1}):
//
//   Tier 0     — stop_breached held rows (TASK_119)   → position $ desc
//   Tier 1     — credible SELLs on HELD positions     → $ at stake desc
//                (fc.side === 'sell' AND held_today;
//                 low_confidence rows are never "credible" — they were
//                 already routed to Bottom above this check)
//   Tier 2     — BUYs that passed the technical gate  → one flat ranking by
//                (fc.side === 'buy', not watchlisted)   _buyTradabilityScore
//                                                        (2026-08-15 — LRR
//                                                        proximity/RSI/IV/
//                                                        RVOL edges, agreement
//                                                        folded in as a small
//                                                        bonus, not the outer
//                                                        tier it used to be —
//                                                        v_agreement_scorecard
//                                                        has zero rows, so
//                                                        "agreement beats
//                                                        entry quality" was
//                                                        never validated),
//                                                        dollar desc tiebreak
//   Tier 3     — HOLD / mixed / no-action              → dollar-weighted edge desc
//   Watchlist  — gated unheld ADD/BMN rows, Technical  → collapsed band, dollar-weighted
//                not entry-ripe (see _buyNoiseGated)     edge desc inside; below Tier 3,
//                                                         above Bottom
//   Bottom     — low_confidence-only sells (TASK_118),
//                infeasible, or suppressed rows        → always last
//
// Dollar-weighted edge: netEdge = sum of edge_20d (state.scorecard, already
// direction-adjusted per rule — a SELL rule's edge_20d is negative when the
// rule fires and price then recovers) across the row's fired composites, so
// a SELL row's negative-edge rules subtract net confidence with no extra
// sign flip needed. score = netEdge * log10(1 + dollarsAtStake), where
// dollarsAtStake is |_amt| for an actionable (non-HOLD/NONE) row or the
// current position $ for a HOLD row. Rows with no fired/scored composites
// use _fallbackEdge() — the old buysell-SEQ ordering squashed into
// [-0.5, +0.5] — so "no evidence" lands inside the scored cluster near 0
// instead of dominating either extreme.
const _MACRO_BUY = new Set(['BM', 'BS']), _MACRO_SELL = new Set(['STM', 'SA']);
const _SRC_BUY   = new Set(['ADD', 'INCREASE']), _SRC_SELL = new Set(['REDUCE', 'REMOVE']);
const _TECH_BUY  = new Set(['BM', 'BS', 'BMN', 'BR']), _TECH_SELL = new Set(['SA', 'STM', 'SS', 'SO']);

// 'sell' | 'buy' | null. Renamed from _agreementDir (TASK_120): the old name
// implied 2-of-3 agreement but the logic was really "no dissent" — a single
// signal with the other two silent/neutral qualified. Now requires >= 2 of
// the 3 columns (MACRO / Sources / Technical) to point the same way AND zero
// columns opposing before calling it agreement. Display-only (▼3/▲3 marker
// next to Symbol, and the legend entry) — no longer drives the default sort
// (see _computePriority below).
function _threeWayAgreement(row) {
  const m = (row.macro_value || '').toUpperCase();
  const s = (row.consolidated_action || '').toUpperCase();
  const t = (row.rr_action || '').toUpperCase();
  const sellVotes = (_MACRO_SELL.has(m) ? 1 : 0) + (_SRC_SELL.has(s) ? 1 : 0) + (_TECH_SELL.has(t) ? 1 : 0);
  const buyVotes  = (_MACRO_BUY.has(m)  ? 1 : 0) + (_SRC_BUY.has(s)  ? 1 : 0) + (_TECH_BUY.has(t)  ? 1 : 0);
  if (sellVotes >= 2 && buyVotes === 0) return 'sell';
  if (buyVotes  >= 2 && sellVotes === 0) return 'buy';
  return null;
}
// Sort key for the "3W" column: sell-agreement ranks above buy-agreement
// above no-agreement, so sorting descending surfaces negatives (sells) first.
function _agree3Score(row) {
  const dir = _threeWayAgreement(row);
  return dir === 'sell' ? 2 : dir === 'buy' ? 1 : 0;
}
// Back-compat: other call sites in this file still say "Dir" for brevity.
const _agreementDir = _threeWayAgreement;

// TASK_122 Tier 2 sub-ranking: 2 = 2a (Technical + Sources + MACRO all
// buy-side, 3/3), 1 = 2b (Technical + one other buy-side, none opposing,
// 2/3), 0 = 2c (Technical ripe only / partial agreement with opposition).
// Unlike _threeWayAgreement (display-only ▼3/▲3 marker, uses the full
// _TECH_BUY set including BMN/BR), the Technical leg here is deliberately
// the entry-ripe set only (_ENTRY_RIPE_TECH = BS/BM) — this only runs on
// rows already classified fc.side === 'buy', so "Technical" here means
// "did the entry actually get ripe," matching the buy-noise gate's own
// definition of readiness.
function _buyAgreementSubTier(row) {
  const m = (row.macro_value || '').toUpperCase();
  const s = (row.consolidated_action || '').toUpperCase();
  const t = (row.rr_action || '').toUpperCase();
  const techBuy   = _ENTRY_RIPE_TECH.indexOf(t) !== -1;
  const srcBuy    = _SRC_BUY.has(s);
  const macroBuy  = _MACRO_BUY.has(m);
  const anySell   = _TECH_SELL.has(t) || _SRC_SELL.has(s) || _MACRO_SELL.has(m);
  const buyVotes  = (techBuy ? 1 : 0) + (srcBuy ? 1 : 0) + (macroBuy ? 1 : 0);
  if (buyVotes === 3) return 2;                       // 2a
  if (buyVotes === 2 && !anySell) return 1;            // 2b
  return 0;                                            // 2c
}

// ── Buy Tradability Score (2026-08-15) ──────────────────────────────────
// "Bring the most tradable stock to the top" of the BUY tier — ranks rows
// WITHIN their existing 2a/2b/2c agreement group (_buyAgreementSubTier
// above stays the primary grouping) by how clean the entry looks right
// now, replacing the plain dollar-weighted tiebreak _computePriority used
// there before. Works unchanged inside Trade Mode too — Trade Mode only
// filters which rows are shown (_isTradeModeQualifyingBuy), it has no sort
// of its own, so this becomes the Trade Mode ranking automatically.
//
// Weights come from this system's OWN measured history (state.factorScorecard,
// same v_factor_scorecard data the RSI/IV grid-cell edge tags already use),
// not hand-picked point values — checked empirically before building rather
// than assumed from textbook TA, because several textbook assumptions turned
// out backwards in this system's actual outcome history:
//   - LRR proximity dominates: the single best-proven BUY composite rule in
//     this system's history (52-BS-BRR, "Buy Strong at the bottom of the
//     Risk Range") is pure LRR proximity, edge_20d +1.94% vs a ~1.4%
//     baseline (n=27,477) — roughly double the edge of the "kitchen sink"
//     rule that ANDs RSI+MACD+Volume+IV/HV+IV-at-BRR together (+0.80% on a
//     comparable n). Stacking required conditions measurably DILUTES edge
//     in this system's own history, so this score is a weighted SUM, never
//     an AND-gate.
//   - RSI oversold outperforms "neutral" (62% win rate vs neutral's ~52%,
//     baseline 49%) — the opposite of "avoid extremes". Median forward
//     return (2.72%) sits close to its mean (3.69%) and its downside tail
//     (10.7% of windows below -10%) is the LOWEST of the three RSI
//     buckets — a genuinely robust signal, not a mean-driven fluke.
//   - High RVOL + up day is the WEAKEST RVOL bucket on win rate (49%, flat
//     vs baseline) AND has the HIGHEST downside tail risk (15.3% below
//     -10%) of the three RVOL buckets — confirms the existing "buying
//     climax" warning in _signalReasons is real, not just a mean artifact.
//   - IV: originally scored via the cross-sectional IV-percentile bucket
//     (win rate — see git history), but that mixes structurally-high-IV
//     names (nothing unusual happening) with names that just had a genuine
//     event-driven spike, since it only says where a stock ranks among ALL
//     stocks, not against its OWN normal range. User: "IV can be high
//     while price is going up or it can cause stock to go down." 2026-08-15:
//     replaced with `row.iv_ratio` — the user's own ThinkOrSwim IV-spike/
//     normalize study (4-day-smoothed IV vs a dynamic 63-day trailing
//     average of that SAME symbol's own IV), exported as a TOSD custom
//     column (`A_IVRatio` -> hist_td.iv_ratio -> drv_technicals.iv_ratio,
//     see db/baseline.sql's 2026-08-15 migration). Self-relative instead
//     of cross-sectional — see _ivRatioScore below.
// MACDH and PVV are deliberately NOT scored: MACDH's two buckets sit within
// ~0.2pp of each other in the factor scorecard (not a reliable signal), and
// PVV is explicitly "Informational v1" in docs/pvv_logic.md with no
// outcome-tracking table yet. Same for IV/HV discount — no factor-scorecard
// entry exists for it yet, so it's excluded rather than guessed.
// Score thresholds (>1.15 spiked, <1 below its own baseline) mirror the
// user's own script's RED/GREEN/YELLOW label logic exactly — not re-derived.
function _ivRatioScore(ratio) {
  if (ratio == null) return 0;
  const r = Number(ratio);
  if (r > 1.15) return -3;  // spiked -- "the red line", be careful
  if (r < 1) return 3;      // below its own 63-day baseline -- favorable
  return 0;                 // 1.00-1.15 -- elevated but not spiked, neutral
}
// Raw (unclamped) LRR-relative position in % — negative below LRR, >100
// above TRR. Distinct from row._rrPos (clamped to [0,100] for the RR bar's
// fixed-width display/sort) — the score needs the unclamped value so
// "below LRR" isn't silently indistinguishable from "right at LRR" the
// way the clamped display value makes it look.
function _rawRrPos(row) {
  if (row.lrr == null || row.trr == null || row.last_price == null) return null;
  const lrr = Number(row.lrr), trr = Number(row.trr), last = Number(row.last_price);
  if (trr === lrr) return null;
  return (last - lrr) / (trr - lrr) * 100;
}
function _lrrProximityScore(row) {
  const rawPos = _rawRrPos(row);
  if (rawPos == null) return 0;
  const turningUp = row.pct_change != null && Number(row.pct_change) >= 0;
  // 2026-08-15: below LRR scored separately and MUCH lower, not treated
  // the same as "at LRR" (the old code clamped at 0% and couldn't tell the
  // two apart). User: "<LRR is not desirable and have to lot of caution. I
  // would rather buy once going up from there." — so below LRR AND still
  // falling is a real penalty (this system's own proven-edge rule,
  // 52-BS-BRR, is keyed on price AT the Risk Range bottom, not below it);
  // below LRR but already turning up gets a small, capped bounce credit —
  // never as much as being at LRR itself.
  if (rawPos < 0) {
    if (!turningUp) return -1;
    return Math.max(0, 0.3 - Math.abs(rawPos) / 100);
  }
  // At/near LRR, tapering linearly to 0 by 40% of the way to TRR — mirrors
  // 52-BS-BRR's own condition. "about to go up or going up" (pct_change >=
  // 0) adds a partial bonus on top; still credits "at LRR, flat" since
  // 52-BS-BRR's proven edge is keyed on the LRR position itself, not
  // today's tick direction.
  const base = Math.max(0, 1 - rawPos / 40);
  return base * (turningUp ? 1 : 0.7);
}
// 2026-08-15: winning source's own buy-family (ADD+INCREASE) win-rate track
// record (state.sourceScorecard, same v_source_edge_scorecard data the
// Trade Mode hit-rate badge already shows — TASK_123). Checked the mean
// (edge_20d) before using it, same as every other factor here: RR/ADD's
// mean is +6.76% but its MEDIAN is -0.17% (SD=87, a handful of huge
// outliers driving the mean) and its win rate is 47.9% — barely a coin
// flip, actually slightly BELOW the ~49.4% baseline. RTA (66.3% win rate)
// and SSSCHG (60.9%) are the genuinely reliable sources; PS (37.6%) is
// genuinely bad. Scored on win_rate_20d for the same reason IV/RSI/RVOL
// are — mean alone would have ranked RR as the best source when it's
// actually flat-to-negative on the metric that matters.
function _sourceTrackRecordScore(row) {
  const src = (row.winning_source || '').toString().toUpperCase();
  // Buy-family win rate specifically, even on a sell row -- this score
  // formula stays buy-calibrated by design (see _buyTradabilityScore's
  // header comment); the Source item's DISPLAYED text picks side-aware
  // win rate separately (_tradabilityBreakdown), this is just the point
  // contribution.
  const sc = ((state.sourceScorecard || {})[src] || {}).buy;
  const base = (state.factorScorecard || {})['Baseline|All stocks'];
  if (!sc || sc.win_rate_20d == null || sc.n < 5 || !base || base.win_rate == null) return 0;
  const delta = (Number(sc.win_rate_20d) - Number(base.win_rate)) * 100;
  return Math.max(-3, Math.min(6, delta));
}
function _buyTradabilityScore(row) {
  // Technical bracket: rr_action (the QS code) already blends Trade/Trend/
  // BB-streak/MACDH per docs/drv_cat_atomic_input_logic.md. Flat credit for
  // any entry-ripe code (BS/BM/BMN) rather than tiering BS > BM > BMN —
  // v_final_call_scorecard shows BS/high-confidence at a NEGATIVE edge on a
  // small sample (n=64), which doesn't support ranking BS above BM/BMN.
  const tech = (row.rr_action || '').toUpperCase();
  const techPts = _ENTRY_RIPE_TECH.indexOf(tech) !== -1 ? 1 : 0;
  const lrrPts = _lrrProximityScore(row);
  // 2026-08-15: win-rate delta (pp), not mean-return delta — see
  // _factorWinRateDelta's header comment for why (IV's mean hides real
  // downside-tail risk that win rate doesn't).
  const rsiDelta  = _factorWinRateDelta('RSI', _rsiBucket(row.rsi));
  const rvolDelta = _factorWinRateDelta('RVOL + direction', _rvolBucket(row.rvol, row.pct_change));
  // Each delta is a measured win-rate edge in percentage points (typically
  // -3..+13ish, RSI oversold's ~13pp is the outlier) — clamp so one
  // outsized bucket can't swamp LRR proximity (the dominant term below);
  // missing data (null, not enough history yet) contributes 0, never a
  // penalty.
  const clamp = v => v == null ? 0 : Math.max(-3, Math.min(6, v));
  const factorPts = clamp(rsiDelta) + _ivRatioScore(row.iv_ratio) + clamp(rvolDelta)
    + _sourceTrackRecordScore(row);
  // 2026-08-15: cap the SUM of every non-LRR, non-agreement term, not just
  // each one individually. User: "tickers that are not at LRR are above the
  // ones at LRR" — checked live and confirmed: tech(2) + RSI(6) + IV(3) +
  // RVOL(6) + source(6) can total 23, well over LRR's own max of 10, so a
  // stock 50%+ away from LRR with several decent-but-unremarkable secondary
  // factors was routinely outranking one actually AT LRR. This is the exact
  // "stacking dilutes the dominant signal" failure mode the whole score
  // exists to avoid (52-BS-BRR alone beats the multi-factor kitchen-sink
  // rule) — recreated by accumulation as terms were added one at a time
  // without rechecking the total. Capped so the combined secondary terms
  // can nudge/break ties but can never manufacture a bigger swing than a
  // real LRR gap.
  const secondaryRaw = techPts * 2 + factorPts;
  const secondaryPts = Math.max(-6, Math.min(8, secondaryRaw));
  // 2026-08-15: agreement (2a/2b/2c — Technical+Sources+MACRO 3-way, see
  // _buyAgreementSubTier) given its OWN dedicated weight, separate from the
  // capped secondaryPts bucket above. User: "agreeing all three sources
  // get high score" — full agreement wasn't actually standing out: it only
  // added +3 inside the shared secondaryPts cap, so once RSI/IV/RVOL/source
  // already filled that cap on their own (common — many rows hit the 8-pt
  // ceiling regardless of agreement level), the +3 changed nothing.
  // Weighted at 60% of LRR's max (agreement is still unvalidated in this
  // system's own history — v_agreement_scorecard has ZERO rows, unlike LRR's
  // proven 52-BS-BRR — so it can meaningfully lift a score but can't fully
  // override a genuinely bad LRR position on its own: 6 < LRR's 10).
  const agreementPts = _buyAgreementSubTier(row) * 3; // 0, 3, or 6 (2c/2b/2a)
  // LRR proximity weighted far above everything else (matches its outsized
  // proven edge vs any combination of the other factors, see 52-BS-BRR note
  // above) — secondaryPts can add/subtract at most 8/-6, agreementPts up to
  // 6, both against LRR's own [-10,+10] range. Range roughly [-16, +24] (a
  // still-falling below-LRR row's -10 LRR term is a real penalty, not a
  // floor of 0 — see _lrrProximityScore).
  return lrrPts * 10 + secondaryPts + agreementPts;
}
// Structured breakdown for the tradability badge's popover (2026-08-15:
// "make it rich and use some colors" — switched from a native title=
// tooltip to a real hover popover, same #sourcePop/_showDataPop mechanism
// as the Vol/IV/Macro/PVV/Signal cells). Each item is colored by whether
// it's actually helping the score: green = favorable/proven-positive,
// amber = mixed/moderate, grey = neutral or no data. Colors reflect the
// SAME measured deltas the score itself is built from — never decorative.
// Threshold at 1.5pp win rate (not 0) — a win-rate delta under that is
// noise at these sample sizes, not a real tilt either way.
function _tradabilityDeltaColor(d) {
  if (d == null) return '#94a3b8';
  if (d > 1.5) return '#16a34a';
  if (d < -1.5) return '#dc2626';
  return '#94a3b8';
}
function _tradabilityBreakdown(row) {
  const items = [];
  const fmtDelta = d => (d >= 0 ? '+' : '') + d.toFixed(1) + 'pp win rate vs baseline';

  // Raw (unclamped) position, not row._rrPos — a below-LRR row must read
  // as "below LRR", not "0% up from LRR" (which is what the RR bar's
  // clamped display value would otherwise make it look like).
  const rawPos = _rawRrPos(row);
  const turningUpForLrr = row.pct_change != null && Number(row.pct_change) >= 0;
  items.push({
    label: 'Risk Range',
    detail: rawPos == null ? 'no LRR/TRR data'
      : rawPos < 0
        ? Math.abs(Math.round(rawPos)) + '% BELOW LRR' + (turningUpForLrr ? ' — bouncing, but still under the line' : ' — falling below LRR, be cautious')
        : Math.round(rawPos) + '% up from LRR' + (rawPos <= 15 ? ' — near LRR, the strongest proven buy signal (52-BS-BRR)' : rawPos <= 40 ? ' — reasonably close to LRR' : ' — well above LRR'),
    color: rawPos == null ? '#94a3b8'
      : rawPos < 0 ? (turningUpForLrr ? '#d97706' : '#dc2626')
      : rawPos <= 15 ? '#16a34a' : rawPos <= 40 ? '#d97706' : '#94a3b8',
  });

  const tech = (row.rr_action || '').toUpperCase();
  const techRipe = _ENTRY_RIPE_TECH.indexOf(tech) !== -1;
  items.push({
    label: 'Technical',
    detail: tech ? (tech + (techRipe ? ' — entry-ripe' : '')) : 'no Technical (QS) code',
    color: techRipe ? '#16a34a' : '#94a3b8',
  });

  const rsiB = _rsiBucket(row.rsi);
  const rsiD = _factorWinRateDelta('RSI', rsiB);
  items.push({
    label: 'RSI',
    detail: (row.rsi != null ? Number(row.rsi).toFixed(1) + ' — ' : '') + (rsiB || 'no data') + (rsiD != null ? ' (' + fmtDelta(rsiD) + ')' : ''),
    color: _tradabilityDeltaColor(rsiD),
  });

  // IV: self-relative ratio (user's own ThinkOrSwim study — this symbol's
  // own IV vs its own 63-day baseline), not the cross-sectional percentile
  // bucket — see _ivRatioScore's comment for why.
  const ivRatio = row.iv_ratio != null ? Number(row.iv_ratio) : null;
  items.push({
    label: 'IV',
    detail: ivRatio == null ? 'no data'
      : ivRatio.toFixed(2) + 'x its own 63-day average'
        + (ivRatio > 1.15 ? ' — spiked, above the 1.15x red line, be careful'
           : ivRatio < 1 ? ' — below its own normal range'
           : ' — elevated but not yet spiked'),
    color: ivRatio == null ? '#94a3b8' : ivRatio > 1.15 ? '#dc2626' : ivRatio < 1 ? '#16a34a' : '#d97706',
  });

  const rvolB = _rvolBucket(row.rvol, row.pct_change);
  const rvolD = _factorWinRateDelta('RVOL + direction', rvolB);
  items.push({
    label: 'Volume',
    detail: (rvolB || 'no data') + (rvolD != null ? ' (' + fmtDelta(rvolD) + ')' : ''),
    color: _tradabilityDeltaColor(rvolD),
  });

  // Winning source's own win-rate track record, side-matched to this row's
  // actual Final Call (2026-08-20: displayed text was hardcoded buy-family
  // even on sell rows -- v_source_edge_scorecard computes sell-family win
  // rate too, direction-aware (hit = fwd20 < 0 for REDUCE/REMOVE), just
  // wasn't exposed via the API until now). The colored delta (srcD) driving
  // this item's amber/green still comes from _sourceTrackRecordScore, which
  // stays buy-calibrated by design (see its own header comment) — only the
  // win-rate number/label shown below is side-aware.
  const src = (row.winning_source || '').toString().toUpperCase();
  const srcSide = finalCall(row).side;
  const srcSc = ((state.sourceScorecard || {})[src] || {})[srcSide];
  const srcHasData = !!src && !!srcSc && srcSc.win_rate_20d != null && srcSc.n >= 5;
  const srcD = _sourceTrackRecordScore(row);
  items.push({
    label: 'Source',
    detail: !src ? 'no winning source'
      : !srcHasData ? src + (srcSide === 'buy' || srcSide === 'sell' ? ' — not enough ' + srcSide + ' history yet' : ' — no directional read')
      : src + ': ' + Math.round(srcSc.win_rate_20d * 100) + '% ' + srcSide + ' win rate (n=' + srcSc.n + ') (' + fmtDelta(srcD) + ')',
    color: _tradabilityDeltaColor(srcHasData ? srcD : null),
  });

  const subtier = _buyAgreementSubTier(row);
  items.push({
    label: 'Agreement',
    detail: subtier === 2 ? '3-way — Technical + Sources + MACRO all agree'
          : subtier === 1 ? 'Partial — 2 of 3 agree, none opposing'
          : 'Weak/solo — not independently corroborated',
    color: subtier === 2 ? '#16a34a' : subtier === 1 ? '#d97706' : '#94a3b8',
  });

  return items;
}
// Rich colored popover HTML — same .source-pop/.sp-title convention as
// _buildSignalPopHtml/_buildPvvPopHtml above, shown via #sourcePop.
function _buildTradabilityPopHtml(row) {
  const sym = row.tos_symbol || '—';
  const score = _buyTradabilityScore(row);
  const scoreColor = score >= 16 ? '#16a34a' : score >= _TRADABILITY_BADGE_MIN ? '#d97706' : '#94a3b8';
  let h = `<div class="sp-title">\u{1F3AF} ${escapeHtml(sym)} &mdash; Tradability `
        + `<span style="color:${scoreColor};">${score.toFixed(1)}</span></div>`;
  h += `<div style="color:#94a3b8;font-size:9px;margin:-2px 0 6px;">Weighted by this system's own measured trading history — Risk Range position dominates, everything else is a smaller nudge.</div>`;
  h += '<table>';
  _tradabilityBreakdown(row).forEach(it => {
    h += `<tr><td style="padding:2px 8px 2px 0;color:${it.color};font-weight:700;vertical-align:top;white-space:nowrap;font-size:10px;">${escapeHtml(it.label)}</td>`
       + `<td style="padding:2px 0;font-size:10px;color:#374151;line-height:1.4;">${escapeHtml(it.detail)}</td></tr>`;
  });
  h += '</table>';
  return h;
}
// Minimum score to show the badge. Rescaled a third time 2026-08-15 when
// agreement got its own dedicated weight (see _buyTradabilityScore's
// agreementPts comment) — max grew back up (was ~14, now ~20). Re-checked
// against the same live data (2026-08-14 anchor, low_confidence-excluded
// buy-side rows): new distribution is max 19.90, mean 7.57, median 8.00,
// top-10% >= 14.00. Set to 12 (~top 15-20%, a bit more permissive than a
// strict top-10% cutoff so it's not ONLY the near-LRR-plus-agreement rows
// showing it). Revisit again after a few more weeks of live data.
const _TRADABILITY_BADGE_MIN = 12;
// 2026-08-15: every row gets something here now, not just ones clearing
// the threshold — the 🎯 icon at/above _TRADABILITY_BADGE_MIN, the raw
// numeric score (muted, smaller) below it. User: "display the tradability
// score instead of icon when it doesn't meet the min score" — so a
// below-threshold row is still visible/comparable at a glance instead of
// disappearing, and the same rich popover works either way. (2026-08-20:
// no longer buy-only either, see the function's own comment.)
function _tradabilityBadge(row) {
  // 2026-08-20: was buy-only (fc.side !== 'buy' -> ''). Score/breakdown are
  // still buy-calibrated under the hood (see _buyTradabilityScore's header
  // comment) but now always computed/shown per user request -- the Source
  // item's win-rate wording was relabeled (_tradabilityBreakdown) so it
  // doesn't read as a sell-side stat it isn't.
  const score = _buyTradabilityScore(row);
  const meetsMin = score >= _TRADABILITY_BADGE_MIN;
  const cls = 'tradability-badge' + (meetsMin ? '' : ' tradability-badge-num');
  // 2026-08-20: was the 🎯 CHARACTER (a color emoji, see _tradabilityIconSvg's
  // header comment) -- same inline SVG the Action popup uses now, so the
  // grid and the popup show the identical icon for the identical score.
  const content = meetsMin ? _tradabilityIconSvg(12) : score.toFixed(1);
  // title="" (empty, not omitted) suppresses the SYMBOL cell's own
  // ancestor title="...Click for chart" from bleeding through on hover —
  // without it the browser shows that native tooltip layered on top of
  // this span's rich data-tradabilitypop popover, since this span has no
  // title of its own to take precedence.
  return '<span class="' + cls + '" data-tradabilitypop="' + escapeHtml(row.tos_symbol) + '" title="">' + content + '</span>';
}

// Fired composite rule ids from rules_engine_fires (same parsing as
// firesCellHtml, kept separate so the sort path doesn't depend on rendering).
function _firedRuleIds(row) {
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires)) return [];
  return fires.map(f => String((f && (f.rule_id || f.id)) || f));
}

// Sum of edge_20d across fired composites present in state.scorecard, or
// null when none of the row's fired rules have a scorecard entry yet.
function _netEdge(row) {
  const sc = state.scorecard || {};
  let sum = 0, any = false;
  for (const id of _firedRuleIds(row)) {
    const s = sc[id];
    if (s && s.edge_20d != null) { sum += Number(s.edge_20d); any = true; }
  }
  return any ? sum : null;
}

// |_amt| for actionable rows, current position $ for HOLD/NONE rows.
function _dollarsAtStake(row) {
  const a = _chipAction(row);
  const isActionable = a !== 'HOLD' && a !== 'NONE';
  return Math.abs(Number(isActionable ? row._amt : row.current_position_dollar) || 0);
}

// Fallback "edge" for rows with no scored fired composites: the buysell SEQ
// (same vocabulary the old tier-3 sort used) normalized to [-1, 1] against
// its observed range (SA=21 highest, -1 = infeasible/none) then halved to
// [-0.5, +0.5] — deliberately smaller than a single real proven rule's edge
// (typically |edge_20d| >= 1) so unscored rows sit inside the scored cluster
// near 0 rather than out-ranking or under-ranking genuinely scored rows.
function _fallbackEdge(row) {
  var fc = finalCall(row);
  var code = (fc.code || '').toUpperCase();
  if (code === 'OVER_MAX') code = 'SO';
  var seqMap = state.buysellSeq || {};
  var seq = (seqMap[code] !== undefined) ? seqMap[code] : -1;
  var norm = Math.max(-1, Math.min(1, seq / 21));
  return norm * 0.5;
}

function _dollarWeightedScore(row) {
  const dollars = _dollarsAtStake(row);
  const netEdge = _netEdge(row);
  const edge = netEdge != null ? netEdge : _fallbackEdge(row);
  return edge * Math.log10(1 + dollars);
}

// ── Buy-noise gate (TASK_120 "Buy-noise gate" section) ──────────────────────
// Diagnosis E.3: ~4,635 ADD recs over 40 anchors (~116/day), 93% unheld —
// standing-list sources re-emit ADD daily and BMN is the default bull
// outcome, burying the few rows that matter. Gate: an UNHELD row whose
// effective (reconciled) action is ADD — which covers both a raw source ADD
// and a Final Call code of BMN, since _chipAction() already maps BMN → ADD —
// ranks in Tier 1 only when its Technical value (rr_action, the QS code from
// drv_cat_atomic_input.td_tn_bb_action_desc) is one of the strong-buy codes
// Tables 2–3 emit only near LRR with momentum/pullback confirmation
// (mirrors the proven 52-BS-BRR entry). BMN, N, watch codes, sell codes, or
// missing Technical are "not ripe" and park in the Watchlist band instead.
// Deliberately does NOT use raw LRR proximity — QS already encodes it plus
// Trend/Trade, BB-streak and MACDH context (a falling knife near LRR shows
// SA/STM and stays gated).
const _ENTRY_RIPE_TECH = ['BS', 'BM', 'BMN'];

// True when a row should be parked in the Watchlist band instead of Tier 1.
// Held rows are never gated — this only governs *initiating* new positions.
// TASK_122: Technical decides WHEN (entry timing), Sources decide WHAT
// (conviction) — a source listing alone (however fresh) never promotes an
// unheld buy out of the gate. The former "new arrival" bypass (any row whose
// winning source's snapshot_date == the row's own as_of_date skipped the
// gate once) leaked daily-refreshing sources like RR/CALL, which re-stamp
// snapshot_date every day, permanently out of the Watchlist band even with
// blank Technical (confirmed case: FAB). Removed — see _isNewSnapshot() for
// the display-only "NEW" pill that replaces it inside the band.
function _buyNoiseGated(row) {
  if (row.held_today) return false;
  if (_chipAction(row) !== 'ADD') return false;
  const tech = (row.rr_action || '').toUpperCase();
  return _ENTRY_RIPE_TECH.indexOf(tech) === -1;
}

// TASK_122: display-only "NEW" pill inside the Watchlist band — never used
// to gate/promote a row. True when the winning source's underlying
// snapshot_date equals the current anchor date (the source data just landed
// for the date being viewed).
function _isNewSnapshot(row) {
  const snap = _winningSnapshot(row);
  const anchor = state.anchorDate || state.date;
  return !!snap && !!anchor && snap === anchor;
}

// "Near-equal score" threshold for the Watchlist band's NEW-first tiebreak
// (see renderGrid's watchRows sort) — roughly half a buysell-SEQ step at a
// typical $10k-$50k position, per _fallbackEdge/_dollarWeightedScore's scale.
const _NEW_TIEBREAK_EPS = 0.15;

const _TIER_STOP      = 1e10;  // Tier 0: stop_breached held rows, by position $
const _TIER_SELL      = 1e8;   // Tier 1: credible SELLs on held positions, by $ at stake
const _TIER_BUY       = 1e6;   // Tier 2: buys past the gate, sub-ranked by agreement (2a/2b/2c)
const _TIER_HOLD      = 1e4;   // Tier 3: HOLD / mixed / no-action, dollar-weighted edge
const _TIER_WATCHLIST = 0;     // Watchlist band: gated unheld ADD/BMN rows, dollar-weighted
                                // edge UNscaled — deliberately sits in a narrow band around 0,
                                // well clear of Tier 3 (1e4 ± ~150) and Bottom (-1e6 ± ~20) so
                                // gated rows stay contiguous in the sorted list with no overlap.
const _TIER_BOTTOM    = -1e6;  // Bottom: low_confidence-only sells / infeasible / suppressed
// _BUY_SUBTIER_STEP (2a/2b/2c as a hard outer tier) retired 2026-08-15 —
// agreement is now a small additive term inside _buyTradabilityScore
// instead of a wall that could bury a clean entry below a merely-agreed-on
// mediocre one. See _buyTradabilityScore's header comment.

// 2026-08-19 (user decision): Tier 1 (credible held sells) sub-ranked 1a/1b
// by whether trig_action (rules-engine trend/trade read, BuySell vocab) also
// confirms bearish. A sell where Sources AND the rules engine both agree
// (e.g. dropped from a list AND the trend line is breaking down) is more
// convicted than a sell driven by Sources alone (e.g. dropped from a list
// while the trend still looks fine) — should rank above it regardless of
// dollar size. 1e7 sits well inside the 1e6-1e8 gap between Tier 2 (buys)
// and Tier 1's own $-at-stake range (real positions run well under $1e6),
// so 1a-with-small-$ always outranks 1b-with-large-$ but never spills into
// an adjacent tier.
const _TIER_SELL_CONFIRMED = 1e7;
const _TREND_TRADE_BEARISH = ['SA', 'STM', 'SS'];

function _computePriority(row) {
  // Tier 0 (TASK_119): held + trading below stop — position $ desc, always
  // above every other tier regardless of edge/dollars.
  if (row.stop_breached && row.held_today) {
    return _TIER_STOP + Math.abs(Number(row.current_position_dollar) || 0);
  }

  var fc = finalCall(row);
  // Bottom: a low_confidence sell (TASK_118), an infeasible Final Call, or a
  // suppressed row sinks below every real tier regardless of dollars — still
  // ordered internally by dollar-weighted score. low_confidence sells are
  // never "credible" (Tier 1) — this check runs first so they land here
  // instead. 2026-08-15: low_confidence gated on fc.side === 'sell' — it's
  // computed purely from SELL-side fired composites (see _finalCallHtml's
  // comment on isLowConf) and was wrongly burying legitimate BUY rows that
  // merely had an unrelated unproven SELL rule also fire in the background.
  if ((row.low_confidence && fc.side === 'sell') || !fc.feasible || row.suppressed_reason) {
    return _TIER_BOTTOM + _dollarWeightedScore(row);
  }

  // Watchlist band: unheld ADD/BMN rows whose Technical isn't entry-ripe
  // (row._watchlisted, set by the caller via _buyNoiseGated before this runs)
  // collapse below Tier 3 instead of flooding Tier 2.
  if (row._watchlisted) {
    return _TIER_WATCHLIST + _dollarWeightedScore(row);
  }

  // TASK_122 Tier 1: a credible SELL on a HELD position — sub-ranked 1a/1b
  // by whether trig_action also confirms bearish (see _TIER_SELL_CONFIRMED
  // above), then by $ at stake desc within each sub-tier. (low_confidence
  // sells already routed to Bottom above, so every sell that reaches here
  // is "credible" per the spec's definition.)
  if (row.held_today && fc.side === 'sell') {
    var trigConfirms = _TREND_TRADE_BEARISH.indexOf((row.trig_action || '').toUpperCase()) !== -1;
    return _TIER_SELL + (trigConfirms ? _TIER_SELL_CONFIRMED : 0) + _dollarsAtStake(row);
  }

  // TASK_122 Tier 2: a BUY that passed the technical gate (never watchlisted
  // — held buys are never gated; unheld buys only reach here when
  // _buyNoiseGated already said no), sub-ranked 2a/2b/2c by how many of
  // Technical/Sources/MACRO agree. 2026-08-15: within each 2a/2b/2c group,
  // ranked by _buyTradabilityScore (how clean the entry looks right now —
  // see that function's header comment) instead of plain dollar size —
  // "bring the most tradable stock to the top". 2026-08-15: agreement is no
  // longer an outer tier here either — folded into _buyTradabilityScore
  // itself as a small bonus (see that function), so this is one flat
  // ranking across every buy, not agreement-group-then-tradability. Dollar-
  // weighted edge drops to a *0.01 tiebreak, only decisive on an exact
  // tradability-score tie (score range ~[-3,+21] * 10 vs dollarWeightedScore's
  // own "well under a few hundred" range, so tradability always wins short
  // of a tie).
  if (fc.side === 'buy') {
    // 2026-08-27 -- Trade Mode only: PVV-confirmed buys sub-ranked above
    // everything else within Tier 2 -- BUY_DIP highest, other confirmed
    // bullish PVV reads (_PVV_BUY_SIDE) next, NO_ACTION/unconfirmed last --
    // mirrors etl/export_trade_mode.py's own Buys sort exactly (see that
    // module's docstring on keeping the two in sync). Off (the general
    // grid, Trade Mode not active) stays pixel-identical to before: pure
    // tradability-score ranking, untouched. Bonuses (2000/1000) dwarf
    // tradability's own max contribution (~210, score range ~[-3,+21]*10)
    // so a PVV tier always wins over score, same guarantee the Python sort
    // makes via tuple ordering. User: "Bring BUY_DIP stocks to the top in
    // Buys." -> "NO ACTION ones are coming in the middle." -> "EX: XLRE &
    // FWONK should be below ETSY."
    let pvvBonus = 0;
    if (state.filters.trade_mode) {
      const pvv = (row.pvv_decision || '').toUpperCase();
      pvvBonus = pvv === 'BUY_DIP' ? 2000 : (_PVV_BUY_SIDE.indexOf(pvv) !== -1 ? 1000 : 0);
    }
    return _TIER_BUY + pvvBonus + _buyTradabilityScore(row) * 10 + _dollarWeightedScore(row) * 0.01;
  }

  // TASK_122 Tier 3: HOLD / mixed / no-action — dollar-weighted edge desc.
  return _TIER_HOLD + _dollarWeightedScore(row);
}

// True if `src` drove this row OR appears among its other sources.
function _rowHasSource(row, src) {
  if (!src) return true;
  if ((row.winning_source || '') === src) return true;
  return _sourcesOf(row).some(s => (s.source || s.source_code || '') === src);
}

// Normalized weight delta for `src` on this row — per-source default sort key.
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

// F2: lazy-fetch the heavy MACRO detail/how-to on first hover, cached by
// "sym@date" (same pattern as showSourcePop/_srcDataCache above).
async function showMacroPop(el, r) {
  const sym = r.tos_symbol || '';
  const key = sym + '@' + (state.date || '');
  if (_macroDetailCache.has(key)) {
    _showDataPop(el, _buildMacroPopHtml(Object.assign({}, r, _macroDetailCache.get(key))));
    return;
  }
  _showDataPop(el, _buildMacroPopHtml(r, true)); // "Loading…" placeholder
  let detail;
  try {
    detail = await fetchJson('/api/actionable/macro-detail?symbol=' +
      encodeURIComponent(sym) + '&date=' + encodeURIComponent(state.date || ''));
  } catch (_) {
    detail = { macro_detail: null, macro_howto: null };
  }
  _macroDetailCache.set(key, detail);
  _showDataPop(el, _buildMacroPopHtml(Object.assign({}, r, detail)));
}

// Symbol-column notes popover — all note_repo comments tagged with this
// ticker (Hedgeye Call/Position Monitor/RTA/etc.), lazy-fetched + cached per
// symbol (same pattern as showMacroPop above).
const _notesCache = new Map();   // symbol -> notes array

function _buildNotesPopHtml(sym, notes, desc) {
  let h = `<div class="sp-title">${escapeHtml(sym)} &mdash; ${escapeHtml(desc || 'Comments')}</div>`;
  if (!notes || !notes.length)
    return h + '<div style="color:#94a3b8;font-size:10px;">No comments found.</div>';

  const _srcColor = t => {
    const u = (t || '').toLowerCase();
    if (u.includes('call'))            return '#7c3aed';
    if (u.includes('position'))        return '#2563eb';
    if (u.includes('rta') || u.includes('alert')) return '#dc2626';
    if (u.includes('sss') || u.includes('stance')) return '#0891b2';
    return '#64748b';
  };
  const _sideColor = sk => {
    const u = (sk || '').toLowerCase();
    if (u === 'long' || u === 'bullish')  return '#16a34a';
    if (u === 'short' || u === 'bearish') return '#dc2626';
    return '#94a3b8';
  };

  h += '<div style="max-width:420px;">';
  for (const n of notes.slice(0, 10)) {
    const dt  = fmtMD(n.note_date) || '';
    const src = (n.source_type || '').replace(/_/g, ' ');
    const sk  = n.signal_kind
      ? `<span style="color:${_sideColor(n.signal_kind)};font-weight:600;text-transform:uppercase;font-size:9px;"> ${escapeHtml(n.signal_kind)}</span>`
      : '';
    let txt = (n.note_text || '').trim();
    if (txt.length > 220) txt = txt.slice(0, 220).replace(/\s+\S*$/, '') + '…';
    h += `<div style="margin-bottom:7px;padding-bottom:7px;border-bottom:1px solid #f1f5f9;">`
       + `<div style="font-size:9px;color:${_srcColor(src)};font-weight:700;text-transform:uppercase;letter-spacing:0.3px;">`
       + `${escapeHtml(src)}${sk} <span style="color:#94a3b8;font-weight:400;text-transform:none;">${dt}</span></div>`
       + `<div style="font-size:10.5px;color:#334155;margin-top:2px;">${escapeHtml(txt)}</div>`
       + `</div>`;
  }
  h += '</div>';
  return h;
}

async function showNotesPop(el, sym, desc) {
  if (_notesCache.has(sym)) {
    _showDataPop(el, _buildNotesPopHtml(sym, _notesCache.get(sym), desc));
    return;
  }
  _showDataPop(el, `<div class="sp-title">${escapeHtml(sym)} &mdash; ${escapeHtml(desc || 'Comments')}</div><div style="color:#94a3b8;font-size:10px;">Loading&hellip;</div>`);
  let notes;
  try {
    notes = await fetchJson('/api/notes?ticker=' + encodeURIComponent(sym) + '&limit=15');
  } catch (_) {
    notes = [];
  }
  _notesCache.set(sym, notes);
  _showDataPop(el, _buildNotesPopHtml(sym, notes, desc));
}

function hideSourcePop() {
  _srcPopEl = null;
  const pop = $('sourcePop');
  if (pop) pop.style.display = 'none';
}


function initGridSymClick() {
  const body = $('actBody');
  if (!body) return;
  body.addEventListener('click', (e) => {
    if (e.target.closest('.lt-quick-btn')) return;
    const cell = e.target.closest('[data-sym-cell]');
    if (!cell) return;
    const sym = cell.dataset.symCell;
    const r   = state.rows.find(row => row.tos_symbol === sym);
    const disp = actionDisplay(r?.consolidated_action || '');
    const code = actionText(disp);
    const cls  = (disp.colorCls || 'act-neutral') + '-tint';
    openChartModal(sym, {
      description: r?.description,
      price:       r?.last_price,
      pctChange:   r?.pct_change,
      badgeHtml:   code ? `<span class="act-badge ${cls}">${escapeHtml(code)}</span>` : '',
    });
  });
}

// _initSidePanels() (per-panel collapse/expand wiring for #actSidePanel
// .sp-hdr headers) REMOVED (2026-09-01, user request: "remove the side
// panel from actionable screen altogether") -- #actSidePanel no longer
// exists.

function initEcoBarClick() {
  ['rrTape1'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('click', (e) => {
      const chip = e.target.closest('.rr-chip[data-sym]');
      if (!chip) return;
      const sym = chip.dataset.sym;
      const r   = state.rows.find(row => row.tos_symbol === sym)
               || { tos_symbol: sym, as_of_date: state.date };
      openDrilldown(r);
    });
  });
}

// ---- rich Vol popover -------------------------------------------------------
function _decodeVolumeSpike(FF) {
  // Reproduces Excel: FH = RIGHT("0000000000" & FG & REPT("0",9-LEN(FG)), 10)
  // Source of truth: etl/derive_cat_atomic_input.py::_decode_vs (Python).
  // Step 1: right-pad fgStr to >=9 chars; Step 2: prepend 10 zeros; Step 3: last 10.
  if (FF == null || FF === 0) return null;
  const FG = Math.abs(Number(FF));
  const fgStr = FG.toFixed(2);
  const reptPad = Math.max(0, 9 - fgStr.length);
  const FH = ('0000000000' + fgStr + '0'.repeat(reptPad)).slice(-10);
  const nv = s => { const n = parseInt(s, 10); return isNaN(n) ? 0 : n; };
  return { FI: nv(FH.slice(0,2)), FJ: nv(FH.slice(2,5)),
           FL: nv(FH.slice(5,7)), FM: nv(FH.slice(8,10)) };
}

function _macdColor(v) {
  if (v == null) return '';
  const n = Number(v);
  if (n >  0.5) return '#15803d';   // strong bull  — green-700
  if (n >  0)   return '#4ade80';   // mild bull    — green-400
  if (n < -0.5) return '#b91c1c';   // strong bear  — red-700
  if (n <  0)   return '#f87171';   // mild bear    — red-400
  return '#6b7280';                  // flat         — gray-500
}
// 2026-08-20: MACD momentum direction used to only show up as a "MACD
// momentum strengthening/weakening" line in the Action popup's caution/
// confirm signals (_signalReasons) — moved here instead, as a caret right
// on the MACD/MACDH grid columns themselves, so it's visible without
// opening the popup. MACDH's sign IS the direction (positive = MACD rising
// above its own signal line; <=0 = falling below it — same convention
// _signalReasons used); MACD's raw level doesn't carry direction on its
// own, so both columns mirror the same MACDH-derived caret.
function _macdCaret(macdhVal) {
  if (macdhVal == null) return '';
  const mv = Number(macdhVal);
  const up = mv > 0;
  return `<span style="margin-left:2px;color:${_macdColor(mv)};" `
    + `title="MACD momentum ${up ? 'strengthening' : 'weakening'} (MACDH ${mv.toFixed(2)})">${up ? '▲' : '▼'}</span>`;
}
function _rsiColor(v) {
  if (v == null) return '';
  const n = Number(v);
  if (n >= 70) return '#b91c1c';    // overbought   — red-700
  if (n >= 60) return '#f97316';    // elevated     — orange-500
  if (n <= 30) return '#15803d';    // oversold     — green-700
  if (n <= 40) return '#4ade80';    // low          — green-400
  return '#6b7280';                  // neutral      — gray-500
}

function _buildVolPopHtml(r) {
  const fmtV = v => v != null ? Number(v).toLocaleString() : '—';
  const fmtR = v => v != null ? Number(v).toFixed(2) + '×' : '—';
  const fmtN = v => v != null ? Number(v).toFixed(2) : '—';
  const fmtP = v => v != null ? Number(v).toFixed(1) + '%' : '—';
  const dir = r.rvol != null && r.rvol_prior != null && r.rvol_prior > 0
    ? (r.rvol / r.rvol_prior > 1.05 ? '▲' : r.rvol / r.rvol_prior < 0.95 ? '▼' : '→') : '';
  const dirCls = dir === '▲' ? 'color:#16a34a' : dir === '▼' ? 'color:#dc2626' : 'color:#888';
  const vs = _decodeVolumeSpike(r.a_volume_spike);
  const rows = [
    // 2026-08-21: "(d ÷ 10d)" added per user -- clarifies RVOL is today's
    // daily volume (hist_tw.volume, loaded fresh every day) over the 10-day
    // average, not a weekly figure -- the "W_" in the source Excel's
    // W_Vlm_Expn_Ratio formula name is just that tab's naming prefix, not a
    // weekly time window (see etl/derive_v2.py's mirrored formula comment).
    ['Rel Vlm (RVOL, d ÷ 10d)', fmtR(r.rvol)],
    ['Prior Day RVOL',   fmtR(r.rvol_prior)],
    ['vs Prior',         dir ? `<span style="${dirCls}">${dir}</span>` : '—'],
    ['Volume',           fmtV(r.w_volume || r.volume)],
    ['Proj Volume',      fmtV(r.vlm_projected)],
    ['Avg Vlm 10d',      fmtV(r.volume_avg_10d)],
    ['Avg Vlm 3m',       fmtV(r.volume_avg_3m)],
    ['Vlm vs 3m Avg',    fmtP(r.vlm_3m_pct)],
    ['Vlm Rate Chg',     fmtN(r.volume_rate_change)],
    ['Vlm Signal',       r.vlm_desc || '—'],
    ['Vlm Action',       r.vlm_action ? (r.vlm_action === 'Accumulate' ? 'Accum' : r.vlm_action) : '—'],
  ];
  let html = '<div class="sp-title">Volume</div><table>';
  for (const [k, v] of rows)
    html += `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`;
  if (vs && vs.FI > 60) {
    const dir = (r.a_volume_spike || 0) >= 0 ? '↑' : '↓';
    const spikeStr = vs.FI === 0 ? '—' : vs.FI <= 15 ? 'Minor' : vs.FI <= 35 ? 'Mild' : vs.FI <= 60 ? 'Moderate' : vs.FI <= 80 ? 'Strong' : 'Extreme';
    const priceStr = vs.FJ === 0 ? '—' : `${dir} ${vs.FJ <= 100 ? 'Small' : vs.FJ <= 300 ? 'Moderate' : vs.FJ <= 600 ? 'Large' : 'Sharp'}`;
    const volStr   = vs.FL === 0 ? '—' : vs.FL <= 25 ? 'Low' : vs.FL <= 50 ? 'Moderate' : vs.FL <= 75 ? 'Elevated' : 'High';
    const daysStr  = vs.FM === 0 ? '—' : vs.FM === 1 ? '1 day' : `${vs.FM} days`;
    html += '<tr><td class="sp-sec" colspan="2">Vlm Spike (decoded)</td></tr>';
    html += '<tr><td colspan="2" style="font-size:9px;color:#94a3b8;padding:1px 4px 4px;">TOS unusual volume event: how big, price direction, volatility, when it occurred</td></tr>';
    html += `<tr><td class="k">Spike Strength</td><td class="v">${spikeStr}</td></tr>`;
    html += `<tr><td class="k">Price Move</td><td class="v">${priceStr}</td></tr>`;
    html += `<tr><td class="k">Volatility</td><td class="v">${volStr}</td></tr>`;
    html += `<tr><td class="k">Days Ago</td><td class="v">${daysStr}</td></tr>`;
  }
  return html + '</table>';
}

// ---- rich IV popover --------------------------------------------------------
function _buildIvPopHtml(r) {
  const fmtP = v => v != null ? Number(v).toFixed(1) + '%' : '—';
  const fmtN = v => v != null ? Number(v).toFixed(1) : '—';
  const iv  = r.imp_volatility != null ? r.imp_volatility * 100 : null;
  const hv  = r.hv             != null ? r.hv             * 100 : null;
  const dc  = r.iv_to_hv_discount;
  const dcStr = dc != null
    ? (dc > 0 ? '<span style="color:#16a34a">cheap ' : '<span style="color:#dc2626">rich ') +
      Math.abs(dc).toFixed(1) + '%</span>'
    : '—';
  const ivpVal = r.iv_percentile != null ? Math.round(Number(r.iv_percentile)) : null;
  const ivpColor = window._ivpBarColor ? window._ivpBarColor(ivpVal) : '#333';
  const ivpHtml = ivpVal != null
    ? `<span style="color:${ivpColor};font-weight:700;">${ivpVal}</span>`
    : '—';
  const rows = [
    ['IVP (IV Rank)',    ivpHtml],
    ['HV (Hist Vol)',    fmtP(hv)],
    ['IV (Impl Vol)',    fmtP(iv)],
    ['IV/HV Status',    dcStr],
    ['HV Percentile',   fmtN(r.hv_percentile)],
    ['Range Compress',  fmtN(r.range_compression)],
    ['IV/HV Ratio',     r.d_iv_to_hv != null ? Number(r.d_iv_to_hv).toFixed(3) : '—'],
  ];
  let html = '<div class="sp-title">Volatility</div><table>';
  for (const [k, v] of rows)
    html += `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`;
  return html + '</table>';
}

// ---- rich Warn/Buy-signal popover (2026-08-12) ------------------------------
// Replaces the plain title=" · "-joined tooltip on the ACTION cell's ⚠/▲
// pill (_finalCallHtml's signalPill) with a rich popover, one reason per
// line — same #sourcePop/_showDataPop mechanism as Vol/IV/Macro/PVV above.
// `sig` is the same {warn, buy} object _finalCallHtml already computed via
// _signalReasons(row, fc.side); isWarn picks which list/style to render
// (a row only ever shows one pill — warn wins over buy on conflict, see
// _signalReasons' own comment — so the caller already knows which).
function _buildSignalPopHtml(sym, sig, isWarn) {
  const items = isWarn ? sig.warn : sig.buy;
  const color = isWarn ? '#b45309' : '#15803d';
  const icon  = isWarn ? '⚠' : '▲';
  const title = isWarn ? 'Caution signals' : 'Supporting signals';
  let html = `<div class="sp-title">${escapeHtml(sym)} &mdash; ${title}</div>`;
  html += '<table>';
  items.forEach(reason => {
    html += `<tr><td style="padding:2px 5px 2px 0;color:${color};font-weight:700;vertical-align:top;width:14px;">${icon}</td>`
         + `<td style="padding:2px 0;font-size:10px;color:#374151;line-height:1.4;">${escapeHtml(reason)}</td></tr>`;
  });
  html += '</table>';
  return html;
}

function _showDataPop(el, html) {
  const pop = $('sourcePop');
  if (!pop) return;
  pop.innerHTML = html;
  pop.style.display = 'block';
  const rect = el.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8)
    top = Math.max(8, rect.top - pop.offsetHeight - 4);
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8)
    left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  pop.style.top  = top  + 'px';
  pop.style.left = left + 'px';
}

function initSourcePopover() {
  const body = $('actBody');
  if (!body) return;
  const _onOver = (e) => {
    const el = e.target.closest('[data-srcpop]');
    if (el && el.dataset.src) { showSourcePop(el); return; }
    const volEl = e.target.closest('[data-volpop]');
    if (volEl) {
      const r = state.rows.find(x => x.tos_symbol === volEl.dataset.sym);
      if (r) _showDataPop(volEl, _buildVolPopHtml(r));
      return;
    }
    const ivEl = e.target.closest('[data-ivpop]');
    if (ivEl) {
      const r = state.rows.find(x => x.tos_symbol === ivEl.dataset.sym);
      if (r) _showDataPop(ivEl, _buildIvPopHtml(r));
      return;
    }
    const scoresEl = e.target.closest('[data-scorespop]');
    if (scoresEl) {
      const r = state.rows.find(x => x.tos_symbol === scoresEl.dataset.scorespop);
      if (r) _showDataPop(scoresEl, _buildScoresPopHtml(r));
      return;
    }
    const macroEl = e.target.closest('[data-macropop]');
    if (macroEl) {
      const r = state.rows.find(x => x.tos_symbol === macroEl.dataset.macropop);
      if (r) showMacroPop(macroEl, r);
      return;
    }
    const notesEl = e.target.closest('[data-notespop]');
    if (notesEl && notesEl.dataset.notespop) {
      const nr = state.rows.find(x => x.tos_symbol === notesEl.dataset.notespop);
      showNotesPop(notesEl, notesEl.dataset.notespop, nr && nr.company_name);
      return;
    }
    const pvvEl = e.target.closest('[data-pvvpop]');
    if (pvvEl) {
      const r = state.rows.find(x => x.tos_symbol === pvvEl.dataset.pvvpop);
      if (r) _showDataPop(pvvEl, _buildPvvPopHtml(r));
      return;
    }
    const actionEl = e.target.closest('[data-actionpop]');
    if (actionEl) {
      const r = state.rows.find(x => x.tos_symbol === actionEl.dataset.actionpop);
      // V2 redesign (driver-first layout, see _buildActionPopHtmlV2) is now
      // the default. Rollback escape hatch: `localStorage.setItem('actionPopV2','0')`
      // in the browser console. Drop this branch + _buildActionPopHtml once
      // V2 is validated in the field.
      if (r) _showDataPop(actionEl, _actionPopV2Enabled() ? _buildActionPopHtmlV2(r) : _buildActionPopHtml(r));
      return;
    }
    const signalEl = e.target.closest('[data-signalpop]');
    if (signalEl) {
      const r = state.rows.find(x => x.tos_symbol === signalEl.dataset.signalpop);
      if (r) {
        const isWarn = signalEl.dataset.signalpopWarn === '1';
        const sig = _signalReasons(r, finalCall(r).side);
        _showDataPop(signalEl, _buildSignalPopHtml(r.tos_symbol, sig, isWarn));
      }
      return;
    }
    const tradEl = e.target.closest('[data-tradabilitypop]');
    if (tradEl) {
      const r = state.rows.find(x => x.tos_symbol === tradEl.dataset.tradabilitypop);
      if (r) _showDataPop(tradEl, _buildTradabilityPopHtml(r));
    }
  };
  const _onOut = (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('[data-srcpop],[data-volpop],[data-ivpop],[data-macropop],[data-scorespop],[data-notespop],[data-pvvpop],[data-signalpop],[data-tradabilitypop],[data-actionpop]')) return;
    hideSourcePop();
  };
  body.addEventListener('mouseover', _onOver);
  body.addEventListener('mouseout', _onOut);
}

// ---- TASK_66: bull_prob cell renderer ----
// Shows probability as a percent with color coding.
// Agreement badge: green dot = high agreement (≥0.7), amber = mixed (0.4–0.7), red = split (<0.4).
function _bullProbCellHtml(r) {
  const prob = r.bull_prob;
  if (prob == null) return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  const pct = Math.round(Number(prob) * 100);
  const probColor = pct >= 65 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626';
  const agr = r.bull_agreement;
  let agrBadge = '';
  if (agr != null) {
    const agrVal = Number(agr);
    const agrColor = agrVal >= 0.7 ? '#16a34a' : agrVal >= 0.4 ? '#d97706' : '#dc2626';
    const agrTitle = `Signal agreement: ${Math.round(agrVal * 100)}% of signals bullish`;
    agrBadge = `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${agrColor};margin-left:3px;vertical-align:middle;" title="${agrTitle}"></span>`;
  }
  return `<span style="font-weight:700;font-size:11px;color:${probColor};">${pct}%</span>${agrBadge}`;
}

// ---- TASK_69: agreement_class cell renderer ----
// Colors: agree_bull=green, agree_bear=red, split_tech_bull=amber, split_tech_bear=orange, neutral=slate.
// Edge badge loaded from v_agreement_scorecard (stored in state.agreementScorecard).
const _AGR_LABEL = {
  agree_bull:      'Bull',
  agree_bear:      'Bear',
  split_tech_bull: 'SplTB',
  split_tech_bear: 'SplTSB',
  neutral:         'Neutral',
};
const _AGR_COLOR = {
  agree_bull:      '#16a34a',
  agree_bear:      '#dc2626',
  split_tech_bull: '#d97706',
  split_tech_bear: '#ea580c',
  neutral:         '#94a3b8',
};
function _agreementCellHtml(r) {
  const cls = r.agreement_class;
  if (!cls) return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  const lbl = _AGR_LABEL[cls] || cls;
  const color = _AGR_COLOR[cls] || '#64748b';
  // Edge badge from scorecard (populated after /api/rules/agreement-scorecard loads)
  let edgeBadge = '';
  if (state.agreementScorecard && state.agreementScorecard[cls] != null) {
    const e = Number(state.agreementScorecard[cls]);
    const eColor = e > 0.5 ? '#16a34a' : e < -0.5 ? '#dc2626' : '#d97706';
    const eSign = e >= 0 ? '+' : '';
    edgeBadge = `<span style="font-size:9px;color:${eColor};margin-left:3px;" title="Avg fwd 20d for ${cls}: ${eSign}${e.toFixed(2)}%">${eSign}${e.toFixed(1)}</span>`;
  }
  return `<span style="font-size:10px;font-weight:700;color:${color};" title="${cls}">${lbl}</span>${edgeBadge}`;
}

// ---- PVV (Price/Volume/Volatility) cell renderer ----
// Informational-only decision badge; hover shows the 4-bucket detail table
// (same data-XXXpop / _showDataPop mechanism as MACRO/Vol/Scores popovers).
// 2026-08-16 revision (user-directed, dip-buyer philosophy): plain "BUY" is
// gone -- BUY_LRR only fires when price is at LRR; NO_ACTION ("no confirmed
// setup") replaces WATCH everywhere, including the Neutral/no-outlook
// fallback; BUY_WATCH/SELL_WATCH are new caution tiers. "WATCH" itself is
// retired as a decide_pvv() output but kept below so already-derived
// historical drv_pvv rows (past dates, pre-2026-08-16) still render instead
// of falling through to the unknown-code default. Sort order (ascending =
// most-actionable first): BUY_LRR, BUY_DIP, SELL, SELL_WATCH, BUY_WATCH,
// REDUCE, TRIM, AVOID, WATCH, NO_ACTION, then no-row last.
const _PVV_RANK = {
  BUY_LRR: 0, BUY_DIP: 1, SELL: 2, SELL_WATCH: 3, BUY_WATCH: 4,
  REDUCE: 5, TRIM: 6, AVOID: 7, WATCH: 8, NO_ACTION: 9,
};
function _pvvRank(decision) {
  return (decision != null && _PVV_RANK[decision] != null) ? _PVV_RANK[decision] : 10;
}
// Reuses the existing act-badge tint classes rather than inventing new CSS.
const _PVV_CLASS = {
  BUY_LRR:    'act-buy-strong-tint',
  BUY_DIP:    'act-buy-tint',
  BUY_WATCH:  'act-buy-tint',
  SELL:       'act-sell-strong-tint',
  SELL_WATCH: 'act-sell-tint',
  REDUCE:     'act-sell-tint',
  TRIM:       'act-sell-weak-tint',
  AVOID:      'act-sell-weak-tint',
  WATCH:      'act-neutral-tint',
};
// Display label shown on the badge -- differs from the DB decision code for
// the "@ LRR" / "WATCH-suffix" tiers per user's requested wording.
const _PVV_LABEL = {
  BUY_LRR: 'BUY@LRR', BUY_WATCH: 'BUYWATCH', SELL_WATCH: 'SELLWATCH',
};
function _pvvCellHtml(r) {
  const decision = r.pvv_decision;
  if (!decision || decision === 'NO_ACTION') {
    return `<span style="color:#cbd5e1;font-size:10px;" data-pvvpop="${escapeHtml(r.tos_symbol || '')}">—</span>`;
  }
  const cls = _PVV_CLASS[decision] || 'act-neutral-tint';
  const label = _PVV_LABEL[decision] || decision;
  return `<span class="act-badge ${cls}" data-pvvpop="${escapeHtml(r.tos_symbol)}" `
       + `style="font-size:10px;padding:1px 5px;cursor:help;">${escapeHtml(label)}</span>`;
}
// Small arrow glyph for a bucket leg direction ('up'/'down'/'flat'/null).
function _pvvArrow(dir) {
  if (dir === 'up')   return '<span style="color:#16a34a;">&#9650;</span>';
  if (dir === 'down') return '<span style="color:#dc2626;">&#9660;</span>';
  if (dir === 'flat') return '<span style="color:#94a3b8;">&#8212;</span>';
  return '<span style="color:#cbd5e1;">?</span>';
}
function _pvvSigColor(sig) {
  if (!sig) return '#94a3b8';
  if (['STRONG_BULL', 'OVEREXT_BULL', 'WEAK_BULL'].includes(sig)) return '#16a34a';
  if (['STRONG_BEAR', 'MILD_BEAR', 'BEAR_LEAN', 'BEAR_DIV'].includes(sig)) return '#dc2626';
  if (sig === 'NA') return '#cbd5e1';
  return '#94a3b8';
}
function _pvvPct(v) {
  if (v == null) return '—';
  const color = Number(v) >= 0 ? '#16a34a' : '#dc2626';
  return `<span style="color:${color};">${v >= 0 ? '+' : ''}${(Number(v) * 100).toFixed(2)}%</span>`;
}
// Ratio version for the 3m bucket's P/50 and 50/200 (centered on 1.0, not 0 --
// "positive" there means above the reference average, not a positive sign).
function _pvvRatio(v) {
  if (v == null) return '—';
  const n = Number(v);
  const color = n > 1 ? '#16a34a' : (n < 1 ? '#dc2626' : '#94a3b8');
  return `<span style="color:${color};">${n.toFixed(2)}</span>`;
}
// Decision matrix reference (docs/pvv_logic.md §4, 2026-08-16 revision) --
// condition + meaning shown in the hover tooltip header so the badge is
// self-explanatory. decide_pvv(sig_today, outlook, at_lrr): RR outlook
// decides WHAT, sig_today decides WHEN, at_lrr gates the two price-up rows
// (dip-buyer philosophy -- a same-day price-up reading alone is no longer
// a buy trigger). TRIM/WATCH/NO_ACTION each cover more than one matrix cell
// (see condition text); BUY_LRR/BUY_DIP/BUY_WATCH are Bullish-outlook-only,
// SELL/SELL_WATCH/REDUCE/AVOID are Bearish-outlook-only except SELL_WATCH
// which is the Bullish-side STRONG_BEAR cell.
const _PVV_DECISION_INFO = {
  BUY_LRR:    { condition: 'outlook=Bullish, today=STRONG_BULL/WEAK_BULL, price at LRR',
                meaning: 'Price up today, confirmed by volume/volatility, and sitting right at the LRR support line — a genuine buy setup.' },
  BUY_DIP:    { condition: 'outlook=Bullish, today=DRIFT/BEAR_LEAN',
                meaning: "Bullish outlook intact; today's soft pullback is a dip to buy, not a reversal. Your most reliable signal." },
  BUY_WATCH:  { condition: 'outlook=Bullish, today=MILD_BEAR',
                meaning: "Bullish outlook, but today's down move came with rising volume — a softer, less-confirmed dip. Worth watching for an entry, not a confirmed buy yet." },
  TRIM:       { condition: 'outlook=Bullish & today=OVEREXT_BULL, or outlook=Bearish & today=STRONG_BULL/WEAK_BULL/OVEREXT_BULL/BEAR_DIV',
                meaning: 'Either an overbought pop in a bullish name, or a rip in a bearish one ("sell the rip") — take some off either way.' },
  REDUCE:     { condition: 'outlook=Bearish, today=MILD_BEAR/BEAR_LEAN',
                meaning: 'Bearish outlook with the tape confirming the down move — lighten up.' },
  SELL:       { condition: 'outlook=Bearish, today=STRONG_BEAR',
                meaning: "Bearish outlook and today's heavy-volume selloff both confirm — exit." },
  SELL_WATCH: { condition: 'outlook=Bullish, today=STRONG_BEAR',
                meaning: "Bullish outlook, but today is a heavy-volume selloff — a serious warning sign. Watch closely; you may need to get rid of the stock despite the bullish thesis." },
  AVOID:      { condition: 'outlook=Bearish, today=NEUTRAL/NA/DRIFT',
                meaning: "Bearish outlook, no confirming setup yet — don't initiate." },
  NO_ACTION:  { condition: 'outlook=Bullish & today=BEAR_DIV/NEUTRAL/NA, or today=STRONG_BULL/WEAK_BULL but not at LRR',
                meaning: 'No confirmed setup today — sit tight.' },
  WATCH:      { condition: 'outlook=Neutral/none (any today)',
                meaning: 'No outlook conviction either way — nothing to act on.' },
};
// green = buy-tilted, red = sell-tilted, gray = neutral/no-action.
const _PVV_DECISION_COLOR = {
  BUY_LRR: '#16a34a', BUY_DIP: '#16a34a', BUY_WATCH: '#16a34a',
  SELL: '#dc2626', SELL_WATCH: '#dc2626', REDUCE: '#dc2626', TRIM: '#dc2626', AVOID: '#dc2626',
  WATCH: '#94a3b8', NO_ACTION: '#94a3b8',
};
// Rich hover tooltip: 4-row table (Today / 5d / 3w / 3m), signal + P/V/Vol
// arrows + ROC values, gated/vol-src annotations. Reuses _showDataPop/#sourcePop.
// 2026-08-16: rich "how it got there" hover for the ACTION column's Final
// Call badge -- reuses already-computed fields/helpers, no new data.
// Rewritten (v3) per user, iterating on the same request: "organize it
// proper way so I can see information from all sources and maybe a
// recommended final decision." Structure, top to bottom:
//   1. Header (symbol + Final Call)
//   2. Recommended Decision -- a synthesized headline verdict (Strong /
//      Moderate / Weak / Conflicted), computed from the SAME agreement
//      checklist as (5) below, so it's not just restating the badge --
//      distinct from finalCall()'s own confidence tier.
//   3. Confidence -- fc.confidence (High/Gate/Mixed) + why
//   4. Sources (ALL of them, full per-source list via _srcReasonsHtml --
//      the earlier v2 trimmed this to just the winning vote; user asked
//      for full source visibility back) + Technical's tactical read
//   5. Agreement checklist -- ✓ agree / ✗ conflict / ○ no signal, one
//      short reason each, for 3-Way / CALC model / Signals / PVV --
//      collapsing what used to be six scattered agreement mechanisms
//      (fc.confidence, 3-Way badge, CALC-vs-ACTION border, RULES edge
//      pills, PVV icon) into one place
//   6. Risk flags (STOP/LT/LOW CONF/earnings) -- risk, not disagreement,
//      kept separate and always shown last regardless of how strong the
//      recommendation reads above.
function _buildActionPopHtml(row) {
  const fc = finalCall(row);
  const sym = row.tos_symbol || '—';
  const text = fc.label || actionText(fc);
  const side = fc.side;
  const color = side === 'sell' ? '#dc2626' : side === 'buy' ? '#16a34a' : '#64748b';
  let h = `<div class="sp-title">${escapeHtml(sym)} Final Call &mdash; `
        + `<span style="color:${color};font-weight:700;">${escapeHtml(text)}</span></div>`;

  // ---- Agreement checklist (built first -- the Recommendation headline
  // above it is derived from this same tally) ----
  let checklist = [];
  if (side === 'buy' || side === 'sell') {
    const sig = _signalReasons(row, side);
    const threeWay = _threeWayAgreement(row);
    const calSide = row.final_side_cal || null;
    const pvvD = row.pvv_decision;
    const pvvSide = (pvvD && pvvD !== 'NO_ACTION' && pvvD !== 'WATCH')
      ? (_PVV_BUY_SIDE.includes(pvvD) ? 'buy' : (_PVV_SELL_SIDE.includes(pvvD) ? 'sell' : null)) : null;
    // Icons reuse the SAME glyphs these concepts already wear elsewhere on
    // the grid, not new ones: 3-Way mirrors the agree3 column's own ▲3/▼3
    // badge; Signals mirrors the ⚠/▲ warn/buy-signal pills; PVV mirrors the
    // ACTION column's own 🟢/🔴/🟡 PVV dot; Tradability mirrors the SYMBOL
    // cell's 🎯 badge. CALC model has no existing icon anywhere else, so
    // 🧮 is a new pick there.
    checklist = [
      { agree: threeWay === side, conflict: !!threeWay && threeWay !== side,
        icon: side === 'buy' ? '▲3' : '▼3', label: '3-Way',
        reason: threeWay === side ? 'MACRO+Sources+Technical all ' + side
          : threeWay ? 'MACRO+Sources+Technical lean ' + threeWay : 'no 3-way alignment' },
      { agree: calSide === side, conflict: !!calSide && calSide !== side,
        icon: '🧮', label: 'CALC model',
        reason: calSide === side ? 'independent model agrees'
          : calSide ? 'independent model says ' + calSide : 'no independent model score' },
      { agree: !sig.warn.length && !!sig.buy.length, conflict: !!sig.warn.length,
        icon: sig.warn.length ? '⚠' : sig.buy.length ? '▲' : null, label: 'Signals',
        reason: sig.warn.length ? sig.warn[0] : sig.buy.length ? sig.buy[0] : 'no RSI/MACD/rule signal' },
      { agree: pvvSide === side, conflict: !!pvvSide && pvvSide !== side,
        icon: pvvD && _PVV_CAUTION.includes(pvvD) ? '🟡' : pvvSide === 'buy' ? '🟢' : pvvSide === 'sell' ? '🔴' : null,
        label: 'PVV',
        reason: pvvSide === side ? (_PVV_LABEL[pvvD] || pvvD) + ' confirms'
          : pvvSide ? (_PVV_LABEL[pvvD] || pvvD) + ' conflicts' : 'no confirmed setup today' },
    ];
    // Tradability Score is buy-only (SYMBOL cell's 🎯 badge) -- the single
    // most empirically-tuned signal in the app, so it's weighted the same
    // as the other checklist rows here (counts toward the Recommendation
    // tally) rather than bolted on separately. Its dominant factor (Risk
    // Range position) doubles as the reason text.
    if (side === 'buy') {
      const tScore = _buyTradabilityScore(row);
      const tBreakdown = _tradabilityBreakdown(row);
      const rrItem = tBreakdown.find(it => it.label === 'Risk Range');
      checklist.push({ agree: tScore >= _TRADABILITY_BADGE_MIN, conflict: tScore < 0,
        icon: '🎯', label: 'Tradability',
        reason: tScore.toFixed(1) + ' — ' + (rrItem ? rrItem.detail : 'no breakdown available'),
        sub: tBreakdown });
    }
  }

  // ---- Risk flags (computed early too -- the Recommendation caveats on these) ----
  const flags = [];
  if (row.low_confidence && side === 'sell') {
    flags.push('LOW CONF — sell evidence comes only from rules with a demonstrated negative historical edge');
  }
  if (row.stop_breached) {
    flags.push((row.stop_signal || 'STOP') + ' — held, just crossed below its '
      + (row.stop_signal === 'TN SA' ? 'Trend' : 'Trade') + ' line');
  }
  const ed = _earningsWarning(row);
  if (ed != null) flags.push('Earnings in ' + ed + 'd');
  const ltAvoid = row.conviction_direction === 'AVOID';
  const ltConflict = !!row.conviction_hold && side === (ltAvoid ? 'buy' : 'sell');
  if (ltConflict) {
    flags.push('Conflicts with long-term conviction ' + (ltAvoid ? 'AVOID' : 'HOLD')
      + ' note: ' + (row.conviction_note || ''));
  }

  // ---- Recommended Decision headline ----
  if (side === 'buy' || side === 'sell') {
    const agreeN = checklist.filter(c => c.agree).length;
    const conflictN = checklist.filter(c => c.conflict).length;
    const strongMin = Math.ceil(checklist.length * 0.75); // 3/4 or 4/5
    let tier, why;
    if (conflictN === 0 && agreeN >= strongMin) { tier = 'Strong ' + side.toUpperCase(); why = agreeN + '/' + checklist.length + ' confirm, no conflicts'; }
    else if (conflictN === 0 && agreeN >= 1) { tier = 'Moderate ' + side.toUpperCase(); why = agreeN + '/' + checklist.length + ' confirm, no conflicts'; }
    else if (agreeN > conflictN) { tier = 'Moderate ' + side.toUpperCase(); why = agreeN + ' confirm vs ' + conflictN + ' conflict'; }
    else if (agreeN === conflictN && conflictN > 0) { tier = 'Conflicted'; why = 'evenly split (' + agreeN + ' vs ' + conflictN + ')'; }
    else if (conflictN > agreeN) { tier = 'Weak'; why = conflictN + ' conflict vs ' + agreeN + ' confirm'; }
    else { tier = 'Unproven'; why = 'no supporting signal yet'; }
    const tierColor = tier === 'Conflicted' || tier === 'Weak' ? '#b45309' : color;
    const caution = flags.length ? ' — ⚠ ' + flags.length + ' risk flag' + (flags.length > 1 ? 's' : '') + ' below' : '';
    h += `<div style="font-size:11px;margin:3px 0 6px;padding:3px 6px;background:#f8fafc;border-radius:3px;">`
       + `Recommendation : <span style="color:${tierColor};font-weight:700;">${escapeHtml(tier)}</span>`
       + ` <span style="color:#64748b;">(${escapeHtml(why)}${caution})</span></div>`;
  }

  // 2026-08-20: "Confidence : High/Gate/Mixed" line removed from display —
  // user: it's after-the-fact from the Final Call decision itself
  // (_compute_final_call), not new information on top of it. fc.confidence
  // still exists and drives the underlying decision logic, just not shown
  // as its own line here anymore.

  // Fresh-signal note (same condition as the SYMBOL cell's NEW pill) --
  // informational, not a risk flag: Technical hasn't had a chance to
  // confirm yet, it's not disagreeing.
  if (row._watchlisted && row._isNew) {
    h += `<div style="font-size:10px;color:#0a84ff;margin:0 0 4px;">🆕 Fresh signal — winning source data just landed, `
       + `Technical isn't entry-ripe yet</div>`;
  }

  // ---- All sources (full list, not just the winner) + Technical ----
  const ca = row.consolidated_action ? escapeHtml(String(row.consolidated_action)) : 'none';
  // Winning source's own historical win rate (same data as the SYMBOL
  // cell's Trade-Mode-only hit-rate badge -- shown here regardless of
  // Trade Mode, since it's directly relevant to how much to trust this call).
  const winSrcCode = (row.winning_source || '').toString().toUpperCase();
  // 2026-08-20: side-matched (was hardcoded buy-family, blank on sell rows).
  const winSrcSc = ((state.sourceScorecard || {})[winSrcCode] || {})[finalCall(row).side];
  let winRateStr = '';
  if (winSrcCode && winSrcSc && winSrcSc.win_rate_20d != null && winSrcSc.n >= 5) {
    const wrPct = Math.round(winSrcSc.win_rate_20d * 100);
    const wrCls = wrPct < 45 ? 'hit-rate-pill-low' : wrPct > 55 ? 'hit-rate-pill-high' : 'hit-rate-pill-mid';
    const wrEdge = winSrcSc.edge_20d != null
      ? (winSrcSc.edge_20d >= 0 ? '+' : '') + Number(winSrcSc.edge_20d).toFixed(2) + '%' : 'n/a';
    winRateStr = `<span class="hit-rate-pill ${wrCls}" style="font-size:9px;vertical-align:middle;margin:0 4px;">${wrPct}%</span>`
      + `<span style="color:#94a3b8;">(${escapeHtml(winSrcCode)} hit rate, n=${Number(winSrcSc.n)}, avg edge ${escapeHtml(wrEdge)})</span>`;
  }
  // Sources/Technical colored the same way -- does THIS lens's own side
  // agree with the row's overall side (color), actively oppose it (amber),
  // or have no directional read at all (gray)?
  const caUpper = (row.consolidated_action || '').toUpperCase();
  const srcSide = _SRC_BUY.has(caUpper) ? 'buy' : _SRC_SELL.has(caUpper) ? 'sell' : null;
  const srcColor = srcSide === side ? color : srcSide ? '#b45309' : '#94a3b8';
  h += `<div style="font-size:10px;line-height:1.5;"><div>Sources : <b style="color:${srcColor};">${ca}</b>${winRateStr}</div>`;
  const srcHtml = _srcReasonsHtml(row);
  h += srcHtml ? `<div style="margin:2px 0 4px 4px;">${srcHtml}</div>`
               : `<div style="margin:2px 0 4px 4px;color:#94a3b8;">no source rows</div>`;
  const rra = row.rr_action ? escapeHtml(String(row.rr_action)) : 'none';
  const rraUpper = (row.rr_action || '').toUpperCase();
  const techSide = _TECH_BUY.has(rraUpper) ? 'buy' : _TECH_SELL.has(rraUpper) ? 'sell' : null;
  const techColor = techSide === side ? color : techSide ? '#b45309' : '#94a3b8';
  const techDesc = row.rr_desc || row.tn_td_desc || row.bb_desc || '';
  h += `<div>Technical : <b style="color:${techColor};">${rra}</b></div>`
     + `<div style="margin:2px 0 4px 4px;color:#64748b;">${techDesc ? escapeHtml(techDesc) : 'no descriptor'}</div></div>`;

  // ---- Agreement checklist -- rows with a `sub` breakdown (Tradability)
  // get the same full item-by-item list the SYMBOL cell's 🎯 popover shows
  // (_tradabilityBreakdown), indented underneath, instead of just the
  // one-line summary -- user: "what I see in [the Tradability] popover, can
  // we add the missing parts to Final Call popover?"
  if (checklist.length) {
    h += `<div style="font-size:10px;line-height:1.6;border-top:1px solid #e5e7eb;margin-top:4px;padding-top:4px;">`
       + checklist.map(rw => {
           // Same color-by-value treatment as the Tradability sub-list's
           // own labels (_tradabilityBreakdown's it.color) -- bold, colored
           // by agree/conflict/neutral, not just the ✓/✗/○ glyph.
           const rowColor = rw.agree ? color : rw.conflict ? '#b45309' : '#94a3b8';
           const icon = rw.agree ? '<span style="color:' + color + ';">✓</span>'
             : rw.conflict ? '<span style="color:#b45309;">✗</span>'
             : '<span style="color:#cbd5e1;">○</span>';
           const glyph = rw.icon ? escapeHtml(rw.icon) + ' ' : '';
           let line = `<div>${icon} ${glyph}<span style="color:${rowColor};font-weight:700;">${escapeHtml(rw.label)}</span>`
             + ` — <span style="color:#374151;">${escapeHtml(rw.reason)}</span></div>`;
           if (rw.sub && rw.sub.length) {
             line += `<div style="margin:2px 0 4px 16px;">` + rw.sub.map(it =>
               `<div><span style="color:${it.color};font-weight:700;">${escapeHtml(it.label)}</span>: `
               + `<span style="color:#374151;">${escapeHtml(it.detail)}</span></div>`
             ).join('') + `</div>`;
           }
           return line;
         }).join('') + `</div>`;
  }

  if (flags.length) {
    h += `<div style="font-size:10px;color:#b45309;border-top:1px solid #e5e7eb;padding-top:4px;margin-top:4px;">`
       + flags.map(f => '⚠ ' + escapeHtml(f)).join('<br>') + `</div>`;
  }
  return h;
}

// ==========================================================================
// Action popup V2 — driver-first redesign (mockup approved 2026-08-20).
// Reuses the SAME real computations _buildActionPopHtml already relies on
// (finalCall, _tradabilityBreakdown, _signalReasons, state.scorecard,
// state.sourceScorecard, _macroMemberBarsHtml's stance data) rendered into
// the mockup's 3-tier layout instead of the original's checklist layout.
// Behind a temporary toggle — see the [data-actionpop] handler above.
// ==========================================================================

function _actionPopV2Enabled() {
  // V2 is the default as of 2026-08-20. Old layout (_buildActionPopHtml) is
  // kept only as a rollback escape hatch (localStorage.actionPopV2='0') until
  // V2 is validated in the field, at which point delete _buildActionPopHtml,
  // this function, and the ternary at the [data-actionpop] handler above.
  try { return localStorage.getItem('actionPopV2') !== '0'; } catch (_) { return true; }
}

// "$7,356" -> "$7k" (>=1000, rounded to nearest thousand); untouched below 1000.
function _actpopFmtAmt(v) {
  const n = Number(v);
  if (!isFinite(n)) return '';
  const abs = Math.abs(n);
  if (abs >= 1000) return (n < 0 ? '-' : '') + '$' + Math.round(abs / 1000) + 'k';
  return fmtUsd(n);
}

// Same monthly_scores_json parse+slice (from current month onward) as
// macroCellHtml's inline sparkline — factored out so the popup can build its
// own bar row from the identical data without duplicating the JSON handling.
function _monthlyScoresVisible(r) {
  const raw = r.monthly_scores_json;
  const arr = Array.isArray(raw) ? raw
    : (typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch (_e) { return null; } })() : null);
  if (!arr) return null;
  const curIdx = arr.findIndex(s => s.is_current);
  return curIdx >= 0 ? arr.slice(curIdx) : arr;
}

// Two bar rows side by side: forward monthly quad-regime sparkline, and the
// Sector/Asset class/Style stance bars (same data _macroMemberBarsHtml uses,
// rebuilt here with .actpop-mbar classes to match the popup's own palette).
function _actpopMacroBarsHtml(r) {
  const sparks = _monthlyScoresVisible(r);
  let sparkRow = '';
  if (sparks && sparks.length >= 2) {
    const maxAbs = Math.max(...sparks.map(s => Math.abs(s.score || 0)), 0.001);
    const bars = sparks.map(s => {
      const sc = s.score || 0;
      const bh = Math.max(3, Math.round(Math.abs(sc) / maxAbs * 16));
      const cls = sc > 0 ? 'buy' : sc < 0 ? 'sell' : 'neutral';
      const ti = `${s.label || ''} (${s.quad || ''}) ${sc >= 0 ? '+' : ''}${sc.toFixed(2)}${s.is_current ? ' — current month' : ''}`;
      return `<span class="actpop-mbar ${cls}" style="height:${bh}px;" title="${escapeHtml(ti)}"></span>`;
    }).join('');
    sparkRow = `<div class="actpop-mrow spark" title="Forward monthly quad-regime score (live sparkline)">${bars}</div>`;
  }
  const memberItems = [];
  if (r.sector_stance != null) memberItems.push({ label: `Sector: ${r.sector || '?'}`, v: Number(r.sector_stance) });
  if (r.asset_class_stance != null) memberItems.push({ label: `Asset class: ${r.real_asset_class || '?'}`, v: Number(r.asset_class_stance) });
  let styles = r.style_stances;
  if (typeof styles === 'string') { try { styles = JSON.parse(styles); } catch (_) { styles = []; } }
  if (Array.isArray(styles)) {
    for (const s of styles) if (s && s.stance != null) memberItems.push({ label: `Style: ${s.label}`, v: Number(s.stance) });
  }
  let memberRow = '';
  if (memberItems.length) {
    const maxAbs = Math.max(...memberItems.map(b => Math.abs(b.v)), 0.001);
    const bars = memberItems.map(b => {
      const bh = Math.max(3, Math.round(Math.abs(b.v) / maxAbs * 14));
      const cls = b.v > 0 ? 'buy' : b.v < 0 ? 'sell' : 'neutral';
      const ti = `${b.label}: ${b.v >= 0 ? '+' : ''}${b.v.toFixed(2)} (live quad regime)`;
      return `<span class="actpop-mbar ${cls}" style="height:${bh}px;" title="${escapeHtml(ti)}"></span>`;
    }).join('');
    memberRow = `<div class="actpop-mrow member" title="Sector / Asset class / Style — live quad-regime stance">${bars}</div>`;
  }
  if (!sparkRow && !memberRow) return '';
  return `<div class="actpop-mgroup-wrap"><div class="actpop-mgroup">${sparkRow}${memberRow}</div></div>`;
}

// VLM (volume projection, 2026-08-20) — same [Label] value pattern as
// Src/Tech, always shown/dashed. Note: vlm_action's own rule table has a
// known internal-consistency issue (5 of 10 rule codes test volume shape
// only with no price-direction check, yet 3 of them still carry a
// directional label) -- relabel audit is on hold per project memory, this
// surfaces the value AS COMPUTED TODAY, not a corrected version.
// 2026-08-20 correction: vlm_desc was originally a title= hover tooltip --
// doesn't work inside this popup (#sourcePop is pointer-events:none,
// nothing nested in it can ever get a native hover). Shown as small inline
// text instead.
function _actpopVlmPillHtml(row) {
  const va = row.vlm_action;
  const cls = !va ? 'disabled' : va === 'Accumulate' ? 'buy' : va === 'Avoid' ? 'sell' : '';
  const txt = va ? (va === 'Accumulate' ? 'Accum' : va) : '—';
  const detail = row.vlm_desc ? `<span style="font-size:8px;color:#94a3b8;margin-left:3px;">${escapeHtml(row.vlm_desc)}</span>` : '';
  return `<span class="actpop-lv"><span class="actpop-lbl">VLM</span><span class="actpop-val ${cls}">${escapeHtml(txt)}</span>${detail}</span>`;
}

// CALC model (2026-08-20) -- P(up 20d) probability, same 3-tier color the
// grid's own bull_prob cell uses (>=65% green, >=50% amber, else red), not
// the buy/sell/disabled convention (a probability isn't a side). NOTE:
// ref_bull_model currently has no active row (parked 2026-08-16, see
// project memory) so this will show "—" for every row until reactivated --
// the slot is wired and ready, not a broken display.
function _actpopCalcPillHtml(row) {
  const p = row.bull_prob;
  const has = p != null;
  const pct = has ? Math.round(Number(p) * 100) : null;
  const color = !has ? '' : pct >= 65 ? 'var(--act-buy-strong)' : pct >= 50 ? '#d97706' : 'var(--act-sell-strong)';
  const txt = has ? pct + '%' : '—';
  return `<span class="actpop-lv"><span class="actpop-lbl">CAL</span><span class="actpop-val${has ? '' : ' disabled'}"${has ? ` style="color:${color};"` : ''}>${escapeHtml(txt)}</span></span>`;
}

function _sectorEtfFor(row) {
  const raw = (row.sector || '').trim().toLowerCase();
  if (!raw) return null;
  const key = raw === 'healthcare' ? 'health care' : raw;
  return (state.sectorEtfMap || {})[key] || null;
}

// Sector ETF proxy row (2026-08-20) -- "JPM -> Financials -> how's XLF doing":
// the Sector pill above is a historical win-rate stat (does this GICS sector's
// past BUY calls beat baseline), not a live read. This is the live one --
// the sector's own SPDR ETF's current outlook (drv_rr.outlook), %chg
// (drv_quote), and risk-range position (drv_rr lrr/trr), same fields/formula
// /api/macro-areas already computes for the side-rail Sectors card
// (macro_areas.py::_sector_etf_proxy). rr_pos there is a [0,1] fraction, not
// raw lrr/trr, so this bar has no LRR/TRR $ labels like the stock's own RR
// bar (_actpopRrBarHtml) -- position only.
// 2026-08-20: now rendered INSIDE .actpop-rr-info (a vertical stack sharing
// the RR row with .actpop-rr-icons -- Tradability/CALC/PVV/Macro), not as
// its own full-width row below it -- so no outer margin of its own anymore;
// .actpop-rr-info's own `gap` handles spacing between its lines, and an
// empty '' return here just means one fewer line in that stack instead of
// needing a spacer placeholder.
function _actpopSectorEtfHtml(row) {
  const etf = _sectorEtfFor(row);
  if (!etf) return '';
  const pos = etf.rr_pos != null ? Math.max(0, Math.min(100, Number(etf.rr_pos) * 100)) : null;
  const pct = etf.pct_change != null ? Number(etf.pct_change) : null;
  const pctTxt = pct != null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '&mdash;';
  const pctColor = pct == null ? '#94a3b8' : pct >= 0 ? 'var(--act-buy-strong)' : 'var(--act-sell-strong)';
  const outlookTxt = etf.outlook || '&mdash;';
  const outlookCss = etf.outlook && window.outlookColor ? window.outlookColor(etf.outlook) : '#94a3b8';
  // 2026-08-30: bar is a fixed 45px again (briefly tried flex:1 1 auto,
  // "maximize sector bar to use whitespace" -- reverted: that made the
  // whole line/box grow to fill the row, which the user then flagged as
  // "expanded into the middle of the popover, should not". Small fixed bar
  // + margin-left:auto (below) keeps this compact and right-flush, back to
  // how it was before that detour -- do not reintroduce flex-grow here.
  const bar = pos != null
    ? `<div class="actpop-rr-track" style="width:45px;display:inline-block;vertical-align:middle;flex-shrink:0;">
         <div class="actpop-rr-fill" style="width:${pos}%;"></div>
         <div class="actpop-rr-tick" style="left:${pos}%;"></div>
       </div><span style="font-size:9px;color:#94a3b8;margin-left:3px;">${Math.round(pos)}%</span>`
    : '';
  // 2026-08-30: flex row, label/symbol/outlook/%chg grouped tight on the
  // left (own overflow:hidden/ellipsis span, in case a longer sector name
  // ever doesn't fit) and the bar pushed flush right via margin-left:auto
  // -- see .actpop-rr-info's own CSS comment (actionable.html) for why
  // this whole box stays shrink-to-fit rather than growing to fill the row.
  return `<div class="actpop-sector-etf" style="font-size:9px;color:#64748b;`
    + `display:flex;align-items:center;width:100%;">`
    + `<span style="display:flex;align-items:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">`
    + `<span class="actpop-lbl" style="margin-right:4px;flex-shrink:0;">Sector ETF</span>`
    + `<b style="flex-shrink:0;">${escapeHtml(etf.symbol || '')}</b>`
    + `<span style="margin-left:6px;flex-shrink:0;">Outlook <b style="color:${outlookCss};">${escapeHtml(outlookTxt)}</b></span>`
    + `<span style="margin-left:6px;flex-shrink:0;color:${pctColor};">${pctTxt}</span>`
    + `</span>`
    + `<span style="margin-left:auto;flex-shrink:0;display:flex;align-items:center;padding-left:4px;">${bar}</span>`
    + `</div>`;
}

// Proximity-to-stop ("delta from trade/trend line" in HV-normalized SD --
// see db/baseline.sql's migration comment for the full rationale). Was a
// single right-aligned line in .actpop-rr-info reading the backend's one
// "closest" reading (etl/derive_actionable.py's stop_proximity_sd/_line);
// 2026-08-29: moved next to the Td/Tn boxes as its own small badge PER
// LINE, so both Trade and Trend show their own reading instead of only
// whichever was closer. Recomputed here (not a second backend field) from
// data already on the row -- same HV daily-move-normalized-distance formula
// the backend uses for its own stop_proximity_sd. 2026-08-29 follow-ups:
// (1) always shown now (was hidden past 1.5 SD), 3-tier colored instead of
// 2-tier: <0.5 SD urgent red, <1.5 SD amber (getting close), >=1.5 SD green
// (safely clear); (2) held_today/stop_breached/"price still above the
// line" gating dropped -- user wants this for every row, held or not.
// 2026-08-30: SIGNED again (was Math.abs -- unsigned "either direction"
// distance) -- user: "if price is below trade, it should show in negative
// and red color" -- below-the-line is a materially different, worse
// situation than being N SDs above it, and needs to read that way rather
// than looking identical to a healthy cushion. Only null (badge hidden)
// when the reading genuinely can't be computed -- missing price/HV/line
// data.
function _lineProximitySd(row, lineVal) {
  const px = row.last_price != null ? Number(row.last_price) : null;
  const hv = row.hv != null ? Number(row.hv) : null;
  if (px == null || hv == null || hv <= 0 || lineVal == null) return null;
  const dailyMove = px * hv / Math.sqrt(252);
  return dailyMove > 0 ? (px - lineVal) / dailyMove : null;
}
// 2026-08-30: below the line (sd < 0) is always red now, regardless of how
// far below -- distance doesn't make "below" better, unlike above the line
// where farther is safer. The 3-tier red/amber/green scale only applies
// once price is actually above the line (sd >= 0).
function _tdtnSdBadge(sd) {
  if (sd == null) return '';
  const below = sd < 0;
  const color = below ? '#b91c1c' : sd < 0.5 ? '#b91c1c' : sd < 1.5 ? '#d97706' : 'var(--act-buy-strong)';
  const note = below ? ' — below this line' : sd < 0.5 ? ' — close' : sd < 1.5 ? ' — getting close' : ' — clear';
  return `<span class="actpop-tdtn-sd" style="color:${color};border-color:${color};" `
    + `title="${sd.toFixed(1)}σ from this line${note}">${sd.toFixed(1)}&sigma;</span>`;
}

// VLM line in .actpop-rr-info (2026-08-20 -- renamed from
// _actpopHeaderPillsHtml, its old header-pills days; Src/Tech/CALC/Sector
// all moved elsewhere or were dropped over several rounds of layout
// changes the same day -- this is the one survivor, now on its own line
// between Sector ETF and the stop-proximity line).
// 2026-08-21: RVOL moved here from the .actpop-details line at the very
// bottom of the popup -- same value (row.rvol), just relocated next to
// VLM (the volume-projection signal RVOL itself feeds) and right-justified
// via .actpop-vlm-line's own width:100%/space-between (that width only
// reaches the popup's true right edge because .actpop-rr-info now grows to
// fill the row instead of shrinking to its content, see actionable.html).
function _actpopVlmLineHtml(row) {
  // "(d/10d)" added 2026-08-21, same clarification as _buildVolPopHtml's
  // "Rel Vlm (RVOL, d ÷ 10d)" label -- today's daily volume over the 10-day
  // average, not a weekly figure.
  const rvolTxt = row.rvol != null ? `<span style="font-size:9px;color:#94a3b8;">RVOL ${Number(row.rvol).toFixed(2)}&times; (d/10d)</span>` : '';
  return `<div class="actpop-vlm-line">${_actpopVlmPillHtml(row)}${rvolTxt}</div>`;
}

// Macro pill + bar charts — sits on the RR bar line (_buildActionPopHtmlV2),
// not the header. Extracted from the header block so the RR bar could be
// narrowed to share its line with this.
function _actpopMacroStackHtml(row) {
  const mv = row.macro_value;
  const mcls = (mv === 'BM' || mv === 'BS') ? 'buy' : (mv === 'SA' || mv === 'STM') ? 'sell' : '';
  // 2026-08-20: was its own amber ⚠ (.mc-conflict), a different glyph/color
  // than the grid's MACRO column for the exact same macro_conflict signal.
  // Matched to the shared magenta bolt (_conflictBoltHtml) instead, same
  // one _macroConflictMark uses on the grid.
  const conflictMark = row.macro_conflict === true
    ? _conflictBoltHtml('MacroNet disagrees with technical direction (price vs 50-day average)') : '';
  return `<span class="actpop-macro-stack">
    <span class="actpop-lv"><span class="actpop-lbl">Macro</span><span class="actpop-val ${mcls}">${escapeHtml(mv || 'HOLD')}</span>${conflictMark}</span>
    ${_actpopMacroBarsHtml(row)}
  </span>`;
}

// PVV action pill — sits on the RR bar line between the Tradability icon
// and the Macro stack (2026-08-20). Same [Label] value pattern as Src/Tech
// in the header, always shown (dashed/disabled when PVV has no confirmed
// setup today, i.e. NO_ACTION/WATCH) rather than only appearing as a
// driver bullet when it has something to say.
function _actpopPvvActionHtml(row) {
  const d = row.pvv_decision;
  const hasReal = !!d && d !== 'NO_ACTION' && d !== 'WATCH';
  const pvvSide = hasReal ? (_PVV_BUY_SIDE.includes(d) ? 'buy' : _PVV_SELL_SIDE.includes(d) ? 'sell' : null) : null;
  const caution = hasReal && _PVV_CAUTION.includes(d);
  const cls = !hasReal ? 'disabled' : caution ? '' : (pvvSide === 'buy' ? 'buy' : pvvSide === 'sell' ? 'sell' : '');
  const txt = hasReal ? (_PVV_LABEL[d] || d) : '—';
  return `<span class="actpop-lv"><span class="actpop-lbl">PVV</span><span class="actpop-val ${cls}">${escapeHtml(txt)}</span></span>`;
}

// Shared target/bullseye icon (2026-08-20) -- inline SVG, fill/stroke=
// currentColor so it actually responds to CSS `color`/.disabled, unlike
// the 🎯 CHARACTER it replaced (a COLOR emoji on Windows/Mac, fill baked
// into the font, ignores CSS `color` entirely -- same bug class as the
// MACRO conflict icon, see _macroConflictMark). Used by both the Action
// popup's Tradability icon (_actpopTradIconHtml) and the grid SYMBOL
// column's badge (_tradabilityBadge) so they're the same icon, not two
// different ones for the same score.
function _tradabilityIconSvg(size) {
  const s = size || 12;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="display:inline-block;vertical-align:middle;">`
    + `<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2.5"/>`
    + `<circle cx="12" cy="12" r="5.5" fill="none" stroke="currentColor" stroke-width="2.5"/>`
    + `<circle cx="12" cy="12" r="1.8" fill="currentColor"/></svg>`;
}

// Tradability icon — always shown, score always computed regardless of
// side (2026-08-20: was buy-only/disabled-greyed on sell rows; the score
// itself is still buy-calibrated under the hood, see _buyTradabilityScore's
// header comment, but user asked it be calculated and displayed
// regardless of the row's own Final Call). Score rendered below the icon,
// own two-row column shape (.actpop-trad-col). Lives in .actpop-rr-icons,
// between Macro and PVV/CALC (2026-08-30: after a few rounds -- briefly in
// the header centered under Td/Tn, then its own grid column on this row
// still under Td/Tn -- user settled on back inside .actpop-rr-icons in
// this specific position, with extra side margins, see .actpop-rr-trad).
function _actpopTradIconHtml(row) {
  const score = _buyTradabilityScore(row);
  const meetsMin = score >= _TRADABILITY_BADGE_MIN;
  const scoreColor = score >= 16 ? 'var(--act-buy-strong)' : meetsMin ? '#d97706' : '#94a3b8';
  // icon itself goes into .disabled styling (grey, same treatment as a
  // non-buy row before the always-show change) whenever the score doesn't
  // clear _TRADABILITY_BADGE_MIN -- previously stayed "active"-looking
  // even on a low/negative score, same visual weight as a genuinely
  // tradable setup.
  const icon = `<span class="actpop-trad-icon${meetsMin ? '' : ' disabled'}" title="Tradability read below">`
    + _tradabilityIconSvg(12) + `</span>`;
  const scoreLine = `<div class="actpop-trad-score" style="color:${scoreColor};" title="Tradability score">${score.toFixed(1)}</div>`;
  return `<span class="actpop-trad-col">${icon}${scoreLine}</span>`;
}

// RR position bar — same _rawRrPos formula as the grid's RR column tick
// (unclamped, so an above-TRR/below-LRR row still shows its real % — the
// grid's own .rr-rb only shows the clamped tick; this popup wants the number).
function _actpopRrBarHtml(row) {
  const rawPos = _rawRrPos(row);
  if (rawPos == null) return '';
  const lrr = row.lrr != null ? Number(row.lrr) : null;
  const trr = row.trr != null ? Number(row.trr) : null;
  const clamped = Math.max(0, Math.min(100, rawPos));
  const tagBg = rawPos > 100 ? 'var(--act-sell-strong-bg)' : rawPos < 0 ? 'var(--act-buy-bg)' : '#f1f5f9';
  const tagColor = rawPos > 100 ? 'var(--act-sell-strong)' : rawPos < 0 ? 'var(--act-buy-strong)' : '#475569';
  return `<div class="actpop-rr">
    <div class="actpop-rr-track">
      <div class="actpop-rr-tag" style="left:${clamped}%;background:${tagBg};color:${tagColor};">${Math.round(rawPos)}%</div>
      <div class="actpop-rr-fill" style="width:${clamped}%;"></div>
      <div class="actpop-rr-tick" style="left:${clamped}%;"></div>
    </div>
    <div class="actpop-rr-labels"><span>LRR ${lrr != null ? lrr.toFixed(2) : '&mdash;'}</span>`
    + `<span class="num">${row.last_price != null ? fmtUsd(row.last_price) : ''}</span>`
    + `<span>TRR ${trr != null ? trr.toFixed(2) : '&mdash;'}</span></div>
  </div>`;
}

// Tier 1 — "Driven by": one bullet per source_actions entry + Technical,
// winning source first ("drove it"), Technical tagged agrees/conflicts vs
// the row's own side, each with a real historical hit-rate pill from
// state.sourceScorecard (same v_source_edge_scorecard data / thresholds as
// the Trade Mode hit-rate badge — TASK_123).
function _actpopDriverBullets(row, side) {
  const sc = state.sourceScorecard || {};
  // reason/dt are escaped separately and joined with a literal HTML entity
  // AFTER escaping -- escaping the already-built "reason &middot; snapshot
  // X" string as one unit would double-escape that entity into &amp;middot;.
  const bulletFor = (label, actUpper, reason, dt, tag, pctSinceDrop, dropConflict, upStreak3d) => {
    const d = actionDisplay(actUpper);
    const cls = d.side === 'buy' ? 'buy' : d.side === 'sell' ? 'sell' : '';
    // 2026-08-20: side-matched to THIS bullet's own action (was hardcoded
    // buy-family, so a sell-side source bullet showed nothing/wrong data).
    const srcSc = (sc[(label || '').toUpperCase()] || {})[d.side];
    let hit = '';
    if (srcSc && srcSc.win_rate_20d != null && srcSc.n >= 5) {
      const wr = Math.round(srcSc.win_rate_20d * 100);
      const hcls = wr < 45 ? 'hit-rate-pill-low' : wr > 55 ? 'hit-rate-pill-high' : 'hit-rate-pill-mid';
      hit = `<span class="actpop-hit hit-rate-pill ${hcls}" title="${escapeHtml(label)} hit rate: ${wr}% (n=${srcSc.n})">${wr}%</span>`;
    }
    const actionLabel = d.label || actUpper || '—'; // literal em dash, not an entity -- see note above
    let noteHtml = escapeHtml(reason || '') + (dt ? ` &middot; snapshot ${escapeHtml(dt)}` : '');
    // Premature-drop pill (2026-08-20) -- see _dropPctPillHtml's own header
    // comment; _srcReasonsHtml's grid-column twin of this same treatment.
    noteHtml += _dropPctPillHtml({ action: actUpper, pct_since_drop: pctSinceDrop, drop_conflict: dropConflict, up_streak_3d: upStreak3d });
    return `<div class="actpop-driver ${cls}">
      <span class="dv-name">${escapeHtml(label)}</span>${hit}
      <span class="dv-action ${cls}">${escapeHtml(actionLabel)}</span>
      <span class="dv-note">${noteHtml}</span>
      ${tag ? `<span class="dv-tag">${escapeHtml(tag)}</span>` : ''}
    </div>`;
  };

  const rows = [];
  const sources = _sourcesOf(row);
  const winning = (row.winning_source || '').toString();
  const winEntry = sources.find(s => (s.source || s.source_code || '') === winning);
  if (winEntry) {
    const code = winEntry.source || winEntry.source_code || winning;
    rows.push(bulletFor(code, winEntry.action, winEntry.reason, fmtMD(winEntry.snapshot_date), 'drove it',
      winEntry.pct_since_drop, winEntry.drop_conflict, winEntry.up_streak_3d));
  }
  const rraUpper = (row.rr_action || '').toUpperCase();
  if (rraUpper) {
    const techSide = actionDisplay(rraUpper).side;
    const tag = winEntry ? (techSide === side ? 'agrees' : (techSide && side ? 'conflicts' : ''))
                          : 'drove it'; // no source row at all -- Technical is the only driver
    const desc = row.rr_desc || row.tn_td_desc || row.bb_desc || '';
    rows.push(bulletFor('Technical', rraUpper, desc, null, tag));
  }
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) => (ACTION_RANK[(b.action || '').toUpperCase()] || 0) - (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  for (const s of others) {
    const code = s.source || s.source_code || '?';
    rows.push(bulletFor(code, s.action, s.reason, fmtMD(s.snapshot_date), null, s.pct_since_drop, s.drop_conflict, s.up_streak_3d));
  }
  // PVV (2026-08-20, ported into V2): a real PVV decision (anything besides
  // NO_ACTION/WATCH) previously only showed up as an ABSENCE, via
  // _actpopNeutralLine's "no read" line -- not represented anywhere when it
  // actually had something to say. Same agree/conflict framing
  // _pvvAgreementIcon already uses elsewhere in the grid (buy/sell side vs.
  // the row's own side; BUY_WATCH/SELL_WATCH are caution, neither side).
  const pvvD = row.pvv_decision;
  if (pvvD && pvvD !== 'NO_ACTION' && pvvD !== 'WATCH') {
    const pvvSide = _PVV_BUY_SIDE.includes(pvvD) ? 'buy' : (_PVV_SELL_SIDE.includes(pvvD) ? 'sell' : null);
    if (pvvSide) {
      const caution = _PVV_CAUTION.includes(pvvD);
      const cls = caution ? '' : pvvSide;
      const conflicts = (side === 'buy' || side === 'sell') && pvvSide !== side;
      const tag = conflicts ? 'conflicts' : (pvvSide === side ? 'agrees' : '');
      const info = _PVV_DECISION_INFO[pvvD];
      rows.push(`<div class="actpop-driver ${cls}">
        <span class="dv-name">PVV</span>
        <span class="dv-action ${cls}">${escapeHtml(_PVV_LABEL[pvvD] || pvvD)}</span>
        <span class="dv-note">${escapeHtml(info ? info.meaning : '')}</span>
        ${tag ? `<span class="dv-tag">${escapeHtml(tag)}</span>` : ''}
      </div>`);
    }
  }
  return rows.length ? `<div class="actpop-drivers">${rows.join('')}</div>` : '';
}

// Fired composite rules, partitioned by whether their proven direction
// (state.scorecard / _ruleSide) agrees with the row's own side -- reuses the
// exact same edge/confidence data and color convention as firesCellHtml's
// grid pills, just grouped into supporting vs opposing instead of one list.
function _actpopRulePillsHtml(row, side) {
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return { support: '', oppose: '', supportCount: 0, opposeCount: 0 };
  const sc = state.scorecard || {};
  const supportPills = [], opposePills = [];
  for (const f of fires) {
    const id = String(f.rule_id || f.id || f);
    const s = sc[id];
    const ruleSide = _ruleSide(id);
    if (ruleSide !== 'buy' && ruleSide !== 'sell') continue;
    const bucket = ruleSide === side ? supportPills : opposePills;
    const cls = ruleSide === 'buy' ? 'buy' : 'sell';
    const conf = (s && s.confidence) || 'unproven';
    const e = (s && s.edge_20d != null) ? Number(s.edge_20d) : null;
    if (conf === 'unproven' || e == null) {
      const n = s && (s.n_fires != null ? s.n_fires : s.fires);
      bucket.push(`<span class="rule-edge-badge act-badge-sm rule-${cls} rule-weak" style="opacity:.55;" `
        + `title="Unproven${n != null ? ' (n=' + n + ')' : ''} — too few fires or CI straddles 0">${escapeHtml(id)}</span>`);
    } else {
      const strong = conf === 'proven' ? 'rule-strong' : 'rule-weak';
      bucket.push(`<span class="rule-edge-badge act-badge-sm rule-${cls} ${strong}" title="${conf}: 20d edge, diagnostic">`
        + `${escapeHtml(id)} ${e >= 0 ? '+' : ''}${e.toFixed(1)}%</span>`);
    }
  }
  return {
    support: supportPills.length ? `<div class="actpop-rule-pills">${supportPills.join('')}</div>` : '',
    oppose: opposePills.length ? `<div class="actpop-rule-pills">${opposePills.join('')}</div>` : '',
    supportCount: supportPills.length,
    opposeCount: opposePills.length,
  };
}

// Tier 2 — Opposing/Supporting: reuses _signalReasons(row, side) (the same
// direction-aware RSI/MACD/RVOL classification the original popup's
// "Signals" checklist row already used) for Signals, filtered to drop its
// "Rule ... fired" text entries since those get their own pills below
// instead, from _actpopRulePillsHtml.
// 2026-08-20: returns {conviction, html} instead of one HTML string --
// conviction (the net tally, no "Conviction:" label) moved up into the
// popup header next to the Final Call, so _buildActionPopHtmlV2 now calls
// this once up front and splices conviction into the header while html
// (the Opposing/Supporting columns, tally line removed) still renders at
// its original later position.
function _actpopTugHtml(row, side) {
  if (side !== 'buy' && side !== 'sell') return { conviction: '', html: '' };
  const sig = _signalReasons(row, side);
  const isRuleText = s => /^Rule \S+ fired|^Sell rule \S+/.test(s);
  const supportSignals = sig.buy.filter(s => !isRuleText(s));
  let opposeSignals = sig.warn.filter(s => !isRuleText(s));

  // Premature-drop conflict (2026-08-20): a flagged REMOVE entry
  // (drop_conflict -- see _dropPctPillHtml) argues against a SELL call —
  // the source dropped the symbol and price has since rallied, undermining
  // the sell thesis. Sell-side only; on a buy row this wouldn't read as
  // opposition (it'd actually support the buy, out of scope here).
  if (side === 'sell') {
    const dropOpp = _sourcesOf(row)
      .filter(s => s.action === 'REMOVE' && s.drop_conflict === true)
      .map(s => {
        const src = s.source || s.source_code || '?';
        const pct = Number(s.pct_since_drop);
        const sign = pct >= 0 ? '+' : '';
        return `${src} dropped it but up ${sign}${pct.toFixed(1)}% since — may have been premature`;
      });
    opposeSignals = opposeSignals.concat(dropOpp);
  }

  const rulePills = _actpopRulePillsHtml(row, side);

  const oppItems = opposeSignals.map(s => `<div class="actpop-tug-item">${escapeHtml(s)}</div>`).join('');
  const supItems = supportSignals.map(s => `<div class="actpop-tug-item">${escapeHtml(s)}</div>`).join('');
  if (!oppItems && !supItems && !rulePills.oppose && !rulePills.support) return { conviction: '', html: '' };

  const oppBody = (oppItems || rulePills.oppose)
    ? `${oppItems}${rulePills.oppose}`
    : `<div class="actpop-tug-item" style="color:#94a3b8;">none</div>`;
  const supBody = (supItems || rulePills.support)
    ? `${supItems}${rulePills.support}`
    : `<div class="actpop-tug-item" style="color:#94a3b8;">none</div>`;

  // Conviction (2026-08-20): a plain, honest tally of everything already
  // listed below -- how many things point which way -- NOT a weighted/
  // calibrated score. Deliberately not pretending to the same precision as
  // _buyTradabilityScore (whose per-factor weights are individually
  // backtested); this just counts what's already visible in Opposing/
  // Supporting so there's a single number to glance at instead of having
  // to read every line. PVV excluded on purpose -- backtested 2026-08-20
  // and found backwards on its one statistically meaningful bucket (AVOID:
  // +3.66% avg 20d forward return, proven confidence, opposite of what
  // "avoid" should mean) -- not trustworthy as a vote in anything yet.
  const supportN = supportSignals.length + rulePills.supportCount;
  const opposeN = opposeSignals.length + rulePills.opposeCount;
  const net = supportN - opposeN;
  const netColor = net > 0 ? 'var(--act-buy-strong)' : net < 0 ? 'var(--act-sell-strong)' : '#94a3b8';
  // No "Conviction:" label here (2026-08-20) -- this now sits in the header
  // next to the Final Call badge, where the label would be redundant; the
  // colored net number + support/oppose carry the meaning on their own.
  // 2026-08-20: stacked 3 lines (Supp / net / Opp) instead of one
  // "+8 (8 support, 0 oppose)" line, per user's exact layout -- easier to
  // scan at a glance than a parenthetical.
  // 2026-08-20: net number moved beside the Supp/Opp pair, not stacked
  // between them -- three items sharing one tight line-height had the
  // bigger (13px) net number clipping into its 8px neighbors. Supp/Opp are
  // their own tight little column instead so they read as one unit.
  const conviction = (supportN + opposeN) > 0
    ? `<span class="actpop-tug-conviction">`
      + `<b style="font-size:13px;color:${netColor};">${net > 0 ? '+' : ''}${net}</b>`
      + `<span class="actpop-tug-conviction-nn">`
      + `<span class="actpop-tug-conviction-n" style="color:var(--act-buy-strong);">${supportN} Supp</span>`
      + `<span class="actpop-tug-conviction-n" style="color:var(--act-sell-strong);">${opposeN} Opp</span>`
      + `</span></span>`
    : '';

  const html = `<div class="actpop-tug">
    <div class="actpop-tug-col oppose"><div class="actpop-tug-h">Opposing</div>${oppBody}</div>
    <div class="actpop-tug-col support"><div class="actpop-tug-h">Supporting</div>${supBody}</div>
  </div>`;
  return { conviction, html };
}

// Bottom "no read" line — factors that don't clear a real lean threshold,
// so they stay out of the Opposing/Supporting pills rather than padding them
// with noise (RSI's own overbought/oversold band, IV's Mid/Low bucket which
// the factor scorecard shows near-50/50, PVV/CALC model when unset).
function _actpopNeutralLine(row) {
  const bits = [];
  const mv = row.macro_value;
  if (!mv || mv === 'HOLD') {
    const confPct = row.macro_conf != null ? Math.round(row.macro_conf * 100) + '%' : null;
    bits.push('MACRO' + (confPct ? ` (Hold, ${confPct})` : ''));
  }
  if (row.rsi != null) {
    const rv = Number(row.rsi);
    const hi = state.rsiOverbought != null ? state.rsiOverbought : 70;
    const lo = state.rsiOversold != null ? state.rsiOversold : 30;
    if (rv > lo && rv < hi) bits.push('RSI ' + Math.round(rv));
  }
  if (row.iv_percentile != null) {
    const bucket = _ivBucket(row.iv_percentile);
    if (bucket === 'Mid (30-70)' || bucket === 'Low (<=30)') bits.push('IV ' + Math.round(row.iv_percentile) + 'pt');
  }
  const pvvD = row.pvv_decision;
  if (!pvvD || pvvD === 'NO_ACTION' || pvvD === 'WATCH') bits.push('PVV');
  if (row.final_side_cal == null) bits.push('CALC model');
  if (!bits.length) return '';
  return `<div class="actpop-neutral">no read: ${bits.join(' &middot; ')} &mdash; none extreme enough to lean either way</div>`;
}

// Tradability box — always shown regardless of side (2026-08-20: was
// buy-only, same gate as the SYMBOL cell's 🎯 badge), reusing
// _tradabilityBreakdown's already-computed, already-colored items verbatim
// rather than re-deriving RSI/IV/RVOL thresholds a second time. The score
// itself stays buy-calibrated under the hood — see _buyTradabilityScore's
// header comment — the Source item's win-rate wording was relabeled so it
// doesn't misread as a sell-side stat.
function _actpopTradabilityHtml(row) {
  const score = _buyTradabilityScore(row);
  const scoreColor = score >= 16 ? 'var(--act-buy-strong)' : score >= _TRADABILITY_BADGE_MIN ? '#d97706' : '#94a3b8';
  const items = _tradabilityBreakdown(row).map(it =>
    `<div class="actpop-trad-item"><b style="color:${it.color};">${escapeHtml(it.label)}</b>: `
    + `<span style="color:#374151;">${escapeHtml(it.detail)}</span></div>`).join('');
  return `<div class="actpop-trad">
    <div class="actpop-trad-h"><span>Tradability</span><span style="color:${scoreColor};font-size:12px;">${score.toFixed(1)}</span></div>
    ${items}
  </div>`;
}

// Trade/Trend line boxes (2026-08-29) -- middle of .actpop-head, between
// the symbol block and the RR bar widget. Descriptive (today's Trade/Trend
// line prices, same fields the stop-breach banner reads) plus, as a
// separate small badge next to each box, that line's own stop-proximity SD
// (_lineProximitySd/_tdtnSdBadge -- shown whenever it applies, 3-tier
// colored red/amber/green). Whichever line is currently higher sits on top; order is
// decided here in JS (column order), not CSS, since it's data-dependent
// per row.
function _actpopTdTnHtml(row) {
  const td = row.trade_line_value != null ? Number(row.trade_line_value) : null;
  const tn = row.trend_line_value != null ? Number(row.trend_line_value) : null;
  if (td == null && tn == null) return '';
  // 2026-08-29: green/red per box -- last price above that line reads
  // bullish, below reads bearish (same convention as the BMN trade-line
  // check and the stop-breach banner elsewhere in this file).
  const lp = row.last_price != null ? Number(row.last_price) : null;
  const lineCls = v => (lp == null || v == null) ? '' : lp >= v ? ' buy' : ' sell';
  const tdRow = td != null
    ? `<span class="actpop-tdtn-row"><span class="actpop-tdtn-box${lineCls(td)}">Td ${td.toFixed(1)}</span>`
      + `${_tdtnSdBadge(_lineProximitySd(row, td))}</span>`
    : '';
  const tnRow = tn != null
    ? `<span class="actpop-tdtn-row"><span class="actpop-tdtn-box${lineCls(tn)}">Tn ${tn.toFixed(1)}</span>`
      + `${_tdtnSdBadge(_lineProximitySd(row, tn))}</span>`
    : '';
  const top = (tn != null && (td == null || tn > td)) ? tnRow : tdRow;
  const bottom = top === tdRow ? tnRow : tdRow;
  return `<div class="actpop-tdtn">${top}${bottom}</div>`;
}

function _buildActionPopHtmlV2(row) {
  const fc = finalCall(row);
  const sym = row.tos_symbol || '—';
  const side = fc.side;
  const callCls = side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : 'neutral';
  const amtTxt = row.held_today && row.current_position_dollar != null
    ? _actpopFmtAmt(row.current_position_dollar) : 'not held (yet)';
  const ed = row.earnings_days;
  const hasEd = ed != null && Number(ed) >= 0 && Number(ed) < 900;
  const edDays = hasEd ? Math.round(Number(ed)) : null;
  // 2026-08-29: dropped the "e " label prefix; highlight reuses the same
  // <=3d yellow .opex-soon treatment the dashboard's own earnings lines use
  // (web/app.js::_earningsLineHtml/_opexLineHtml) instead of inventing a
  // separate threshold/color here.
  const edTxt = hasEd
    ? ` &middot; ${edDays <= 3 ? `<span class="opex-soon">${edDays}d</span>` : `${edDays}d`}`
    : '';
  // Computed here (not at its original later call site) so its conviction
  // piece is ready in time for the header below -- see _actpopTugHtml's own
  // comment for why it now returns {conviction, html} instead of one string.
  const tug = _actpopTugHtml(row, side);

  let h = `<div class="actpop">`;
  // Header: symbol + Final Call badge + Conviction tally on the top line
  // (.actpop-sym), held amount/earnings on their own line below it
  // (.actpop-co, 2026-08-29: was inline next to the symbol); Trade/Trend
  // boxes (_actpopTdTnHtml) and the RR bar (_actpopRrBarHtml) as two more
  // grid columns (2026-08-30: .actpop-head is CSS Grid now, was flex --
  // see actionable.html's own comment on .actpop-head for why: symmetric
  // 1fr flanks around the Td/Tn column is what actually centers it in the
  // popover, which plain flex can't guarantee. Originally also needed to
  // keep .actpop-rr-row's Tradability column aligned under this one, but
  // Tradability has since moved back into .actpop-rr-icons -- see that
  // row's own comment -- so .actpop-rr-row is plain flex again; this grid
  // stays for the popover-centering reason alone now).
  h += `<div class="actpop-head">
    <div class="actpop-sym">${escapeHtml(sym)}`
    + `<span class="actpop-call ${callCls}" style="margin-left:8px;">${escapeHtml(fc.label || actionText(fc) || '—')}</span>`
    + tug.conviction
    + `<div class="actpop-co">${escapeHtml(amtTxt)}${edTxt}</div>`
    + `</div>`
    + _actpopTdTnHtml(row)
    + _actpopRrBarHtml(row)
    + `</div>`;

  // Second row: Macro/PVV/CALC grouped on the left (.actpop-rr-icons);
  // Sector ETF / VLM / stop-proximity stacked on the right
  // (.actpop-rr-info), three lines top to bottom.
  // 2026-08-21: PVV moved next to Tradability; CALC moved below PVV (its
  // own small vertical pair, .actpop-pvv-calc-col) instead of sitting in
  // the same horizontal row as Tradability/Macro.
  // 2026-08-29: Macro moved to the front (was last) -- user wanted the
  // Macro-related controls (action pill, conflict bolt, bar charts) leading
  // the row, ahead of Tradability and PVV/CAL.
  // 2026-08-30: Tradability's journey -- .actpop-rr-icons (original spot,
  // first item) -> header, centered under Td/Tn -> its own middle grid
  // column here, still under Td/Tn but back on this row -> now back inside
  // .actpop-rr-icons, this time BETWEEN Macro and PVV/CALC (user request),
  // in its own .actpop-rr-trad wrapper for the extra side margins that
  // asks for. Row-to-row grid alignment with .actpop-head's Td/Tn column
  // is no longer needed (nothing here targets that column anymore), so
  // .actpop-rr-row itself reverted from grid back to flex -- see its own
  // CSS comment.
  h += `<div class="actpop-rr-row">`
    + `<div class="actpop-rr-icons">${_actpopMacroStackHtml(row)}`
    + `<span class="actpop-rr-trad">${_actpopTradIconHtml(row)}</span>`
    + `<span class="actpop-pvv-calc-col">${_actpopPvvActionHtml(row)}${_actpopCalcPillHtml(row)}</span>`
    + `</div>`
    + `<div class="actpop-rr-info">${_actpopSectorEtfHtml(row)}${_actpopVlmLineHtml(row)}</div>`
    + `</div>`;

  if (row.stop_breached) {
    // 2026-08-20: shows the actual line price now (trade_line_value/
    // trend_line_value, today's Trade/Trend line -- same fields the Td/Tn
    // header boxes show), not just the crossover code with no number to
    // check it against.
    const lineVal = row.stop_signal === 'TN SA' ? row.trend_line_value : row.trade_line_value;
    const lineLabel = row.stop_signal === 'TN SA' ? 'Trend' : 'Trade';
    const priceTxt = lineVal != null ? ` (${lineLabel} line ${fmtUsd(Number(lineVal))})` : '';
    h += `<div class="actpop-neutral" style="color:#b91c1c;font-weight:700;">&#9888; Stop breached &mdash; `
       + `${escapeHtml(row.stop_signal || 'trade line broke down')}${priceTxt}</div>`;
  }
  // Proximity-to-stop ("delta from trade/trend line") moved 2026-08-20 into
  // .actpop-rr-info as a standalone banner, then 2026-08-29 into a per-line
  // badge next to each Td/Tn header box instead -- see _tdtnSdBadge, called
  // from _actpopTdTnHtml.

  // LT conviction-hold conflict (2026-08-20: ported from V1, was dropped in
  // the V2 rewrite) — a SELL-side Final Call fighting an active conviction
  // HOLD note, or a BUY-side Final Call fighting an active AVOID note.
  const ltAvoid = row.conviction_direction === 'AVOID';
  const ltConflict = !!row.conviction_hold && side === (ltAvoid ? 'buy' : 'sell');
  if (ltConflict) {
    h += `<div class="actpop-neutral" style="color:#7c3aed;font-weight:700;">`
       + `${ltAvoid ? '&#128683;' : '&#128301;'} Conflicts with long-term conviction ${ltAvoid ? 'AVOID' : 'HOLD'} `
       + `&mdash; ${escapeHtml(row.conviction_note || '')}</div>`;
  }

  // Fresh-signal note (2026-08-20: also ported from V1) — informational,
  // not a risk flag: Technical hasn't had a chance to confirm yet, it's
  // not disagreeing.
  if (row._watchlisted && row._isNew) {
    h += `<div class="actpop-neutral" style="color:#0a84ff;">&#127991; Fresh signal &mdash; winning source data `
       + `just landed, Technical isn't entry-ripe yet</div>`;
  }

  h += _actpopDriverBullets(row, side);
  h += tug.html;
  h += _actpopNeutralLine(row);

  // RVOL moved 2026-08-21 to the VLM line (.actpop-rr-info) -- not
  // duplicated here anymore. Earnings dropped the same day -- already
  // shown in the header (.actpop-co, next to the amount, edTxt above).
  const details = [];
  if (!row.held_today && row.suggested_target_dollar != null) details.push(`target ${_actpopFmtAmt(row.suggested_target_dollar)}`);
  if (details.length) h += `<div class="actpop-details">${details.join(' &middot; ')}</div>`;

  // Tradability detail box moved to the bottom (2026-08-20) -- was between
  // driver bullets and Tug; user wanted the score breakdown last, after
  // everything else.
  h += _actpopTradabilityHtml(row);

  h += `</div>`;
  return h;
}

function _buildPvvPopHtml(r) {
  const sym = r.tos_symbol || '—';
  let det = r.pvv_detail;
  if (typeof det === 'string') { try { det = JSON.parse(det); } catch (_) { det = null; } }
  const isNoAction = !r.pvv_decision || r.pvv_decision === 'NO_ACTION';
  const todaySig = det && det.today ? det.today.sig : null;
  const decision = isNoAction
    ? `– ${todaySig ? `(${todaySig}, no confirmed setup)` : '(no confirmed setup)'}`
    : (_PVV_LABEL[r.pvv_decision] || r.pvv_decision);
  const dColor = _PVV_DECISION_COLOR[r.pvv_decision] || '#94a3b8';
  const info = _PVV_DECISION_INFO[r.pvv_decision] || null;
  let h = `<div class="sp-title">${escapeHtml(sym)} PVV &mdash; `
        + `<span style="color:${dColor};font-weight:700;">${escapeHtml(decision)}</span>`
        + (info ? ` <span style="color:#94a3b8;font-weight:400;font-size:9px;">(${escapeHtml(info.condition)})</span>` : '')
        + `</div>`;
  if (info) {
    h += `<div style="color:#64748b;font-size:10px;margin:2px 0 6px;">${escapeHtml(info.meaning)}</div>`;
  }
  if (!det) {
    h += `<div style="color:#94a3b8;font-size:10px;">No PVV detail available.</div>`;
    return h;
  }
  // TASK_127: outlook line + decision-formula line, above the bucket table.
  const outlookInfo = det.outlook || null;
  const outlookVal = outlookInfo ? outlookInfo.value : null;
  const outlookSrc = outlookInfo ? outlookInfo.source : null;
  const outlookColor = outlookVal === 'Bullish' ? '#16a34a' : (outlookVal === 'Bearish' ? '#dc2626' : '#94a3b8');
  const outlookLabel = outlookVal
    ? `${outlookVal} (${outlookSrc || 'RR'})`
    : 'no outlook — BB fallback';
  const sigTodayForFormula = (det.today && det.today.sig) ? det.today.sig : '—';
  h += `<div style="font-size:10px;margin:0 0 2px;">Outlook: `
     + `<span style="color:${outlookColor};font-weight:700;">${escapeHtml(outlookLabel)}</span></div>`;
  h += `<div style="color:#94a3b8;font-size:9px;margin:0 0 6px;">decision = outlook &times; today `
     + `= ${escapeHtml(outlookVal || 'none')} &times; ${escapeHtml(sigTodayForFormula)}</div>`;
  const rowsDef = [
    ['Today', det.today],
    ['5d',    det.d5],
    ['3w',    det.w3],
    ['3m',    det.m3],
  ];
  h += '<table class="pvv-tbl"><colgroup>'
     + '<col class="pvv-col-k"><col class="pvv-col-v"><col class="pvv-col-v"><col class="pvv-col-v"><col class="pvv-col-v">'
     + '</colgroup>';
  h += `<tr class="pvv-hdr"><td class="k"></td><td class="v">Signal</td><td class="v">Price</td>`
     + `<td class="v">Volume</td><td class="v">Vol</td></tr>`;
  for (const [label, b] of rowsDef) {
    if (!b) { h += `<tr><td class="k">${label}</td><td colspan="4" class="v">—</td></tr>`; continue; }
    const sig = b.sig || 'NA';
    const sigColor = _pvvSigColor(sig);
    const gatedMark = b.gated ? ' <span style="color:#f59e0b;" title="Demoted by the 3w trend-value gate">(gated)</span>' : '';
    const srcMark = b.vol_src === 'hv' ? ' <span style="color:#94a3b8;" title="IV unavailable — using historical_vol">[hv]</span>' : '';
    if (label === '3m') {
      h += `<tr><td class="k">${label}</td>`
         + `<td class="v" style="color:${sigColor};font-weight:700;">${escapeHtml(sig)}</td>`
         + `<td class="v" style="white-space:normal;" title="Price/SMA50 &middot; SMA50/SMA200 (ratio, >1 = above)">`
         +   `P/50 ${_pvvRatio(b.price_vs_sma50)}<br>50/200 ${_pvvRatio(b.sma50_vs_sma200)}</td>`
         + `<td class="v" style="color:#94a3b8;" title="3m bucket has no volume leg (price-structure + IV only, per spec)">n/a</td>`
         + `<td class="v" title="IV percentile">IVp ${b.iv_pctile != null ? Number(b.iv_pctile).toFixed(0) : '—'}${srcMark}</td></tr>`;
      continue;
    }
    h += `<tr><td class="k">${label}${gatedMark}</td>`
       + `<td class="v" style="color:${sigColor};font-weight:700;">${escapeHtml(sig)}</td>`
       + `<td class="v">${_pvvArrow(b.p_dir)} ${_pvvPct(b.p_roc)}</td>`
       + `<td class="v">${_pvvArrow(b.v_dir)} ${_pvvPct(b.v_roc)}</td>`
       + `<td class="v">${_pvvArrow(b.vol_dir)} ${_pvvPct(b.vol_roc)}${srcMark}</td></tr>`;
  }
  h += '</table>';
  return h;
}

// ---- TASK_70: Final Call (cal) cell renderer ----
// Shows the calibrated final call (derived from bull_prob) beside the existing
// Final Call column so the user can compare them side-by-side.
// Uses the same badge style as _finalCallHtml but reads *_cal fields.
// A "vs" highlight (amber border) is added when the two disagree on side.
function _finalCallCalHtml(r) {
  const code = r.final_code_cal;
  if (code == null || code === '') {
    return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  }
  const label    = r.final_action_cal || code;
  const side     = r.final_side_cal   || 'neutral';
  const strength = Number(r.fc_strength_cal) || 0;
  // Treat as feasible when code is non-null.
  var fcDisp = actionDisplay(code);
  var colorCls = (fcDisp.colorCls || 'act-neutral') + '-fill';
  // "vs" highlight: amber left-border when cal side differs from existing FC side.
  var vsBorder = '';
  var vsTitle   = '';
  const existSide = r.final_side || 'neutral';
  if (existSide && side !== existSide) {
    vsBorder = 'border-left:3px solid #f59e0b;padding-left:3px;';
    vsTitle  = ' — disagrees with Final Call (' + existSide + ' vs ' + side + ')';
  }
  var tipText = 'Cal: ' + label + ' (strength ' + strength + ', p=' +
    (r.bull_prob != null ? Math.round(Number(r.bull_prob)*100) + '%' : '?') +
    ')' + vsTitle;
  return '<span class="act-badge act-badge-sm ' + colorCls + '" ' +
    'style="' + vsBorder + '" title="' + escapeHtml(tipText) + '">' +
    escapeHtml(label) + '</span>';
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

// Columns whose most useful first-click order is descending, not the
// generic ascending default — currently just "3W" (_agree3: sell=2 > buy=1
// > none=0), so one click surfaces sell-agreement rows immediately instead
// of requiring a second click to flip direction.
const _DEFAULT_DESC_SORT_KEYS = new Set(['_agree3']);

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
        state.sort.dir = _DEFAULT_DESC_SORT_KEYS.has(key) ? -1 : 1;
        state.sort.type = th.dataset.type || 'str';
      }
      updateSortIndicators();
      renderGrid();
    });
  });
}

// Empty-state message (U11). Distinguishes "nothing left to do" (everything
// acted/snoozed — matchesBaseFilters excluded every row) from "your filters
// hid everything" (action chip / actionable-only filtered a non-empty
// baseRows down to zero), each with the right message + affordance.
function _emptyStateHtml() {
  // TASK_124: Trade Mode empty state — positive framing, distinct from the
  // "all caught up" / "filters hid everything" messages below.
  if (state.filters.trade_mode && state.rows.length === 0) {
    return 'No trades today — nothing passed the playbook checks.';
  }
  if (state.allRows.length > 0 && state.baseRows.length === 0) {
    return `All caught up for ${escapeHtml(state.date || '')}.`;
  }
  if (state.allRows.length > 0 && state.rows.length === 0) {
    return 'No rows match these filters. '
      + '<button type="button" id="emptyClearFiltersBtn" class="btn" style="margin-left:6px;">Clear Filters</button>';
  }
  return 'No actionable rows match these filters.';
}

function renderGrid() {
  for (const r of state.rows) {
    r._snapshot = _winningSnapshot(r);
    r._isNew = _isNewSnapshot(r);
    // Re-compute priority and final call here in case scorecard loaded after allRows.
    var fc = finalCall(r);
    r._fc_strength = fc.strength;
    r._fc_code     = fc.code;
    r._fc_side     = fc.side;
    // TASK_124: Trade Mode's own criteria already narrows to entry-ripe
    // qualifying buys — never band these into the collapsed Watchlist.
    r._watchlisted = state.filters.trade_mode ? false : _buyNoiseGated(r);
    r._priority = _computePriority(r);
    r._agree3 = _agree3Score(r);
    r._pvv_rank = _pvvRank(r.pvv_decision);
  }
  hideSourcePop();
  sortRows();
  updateSortIndicators();
  const tb = $('actBody');
  tb.innerHTML = '';
  const total = state.rows.length;
  $('rowCount').textContent = `${total} row${total === 1 ? '' : 's'}`;
  const emptyEl = $('emptyState');
  if (emptyEl) {
    emptyEl.style.display = total === 0 ? 'block' : 'none';
    if (total === 0) emptyEl.innerHTML = _emptyStateHtml();
  }

  // TASK_120 buy-noise gate: split watchlisted rows (unheld ADD/BMN, Technical
  // not in _ENTRY_RIPE_TECH) out of the main sequence into a collapsed
  // "Watchlist (n)" band, regardless of the active column sort — a custom
  // header-sort shouldn't resurface the buy-noise flood the gate exists to
  // hide. Within the band, always ordered by dollar-weighted edge desc (same
  // scoring used across the ranked tiers) so the best-of-the-rest rises to
  // the band's top.
  const mainRows  = state.rows.filter(r => !r._watchlisted);
  // TASK_122: within a group of equal/near-equal score (|diff| < _NEW_TIEBREAK_EPS),
  // a NEW-pilled row (winning source's snapshot just landed for this anchor —
  // see _isNewSnapshot()) sorts first so fresh list arrivals surface near the
  // band's top instead of being buried under older gated rows with a
  // marginally higher score. Never changes which band a row is in — display
  // order only.
  const watchRows = state.rows.filter(r => r._watchlisted)
    .sort((a, b) => {
      const diff = _dollarWeightedScore(b) - _dollarWeightedScore(a);
      if (Math.abs(diff) < _NEW_TIEBREAK_EPS && a._isNew !== b._isNew) {
        return a._isNew ? -1 : 1;
      }
      return diff;
    });
  // Auto-expand (without flipping the sticky manual toggle) whenever an
  // active filter/search narrows the grid and could have a match inside the
  // band — nothing filters/search touch is ever permanently hidden.
  const filtersActive = !!(state.filters.symbol_search || state.filters.action ||
    state.filters.source || state.filters.account || state.filters.held_only ||
    state.filters.conviction !== 'any' || state.filters.bull_prob_min > 0 ||
    state.filters.agreement_class || state.filters.stopOnly ||
    state.filters.etfchg_only || state.filters.iichg_only ||
    (state.filters.symbols_multi && state.filters.symbols_multi.length));
  const bandExpanded = state.watchlistExpanded || (filtersActive && watchRows.length > 0);

  // Cached so copySymbols() can copy exactly what's on screen right now.
  // Must match DOM append order below (mainRows, then watchRows when the
  // band is expanded) -- state.rows alone is sorted by the active column
  // sort, which is a different order once the watchlist band is expanded.
  const visibleRows = bandExpanded ? mainRows.concat(watchRows) : mainRows;
  state.visibleRows = visibleRows;

  for (const r of mainRows) {
    tb.appendChild(_buildRowEl(r));
  }

  if (watchRows.length > 0) {
    tb.appendChild(_watchlistBandRowEl(watchRows.length, bandExpanded));
    if (bandExpanded) {
      for (const r of watchRows) {
        const tr = _buildRowEl(r);
        tr.classList.add('row-watchlisted');
        // No dedicated stylesheet rule for .row-watchlisted (display-layer-only
        // change, actionable.js only) — mute inline, matching the low_confidence
        // row treatment used elsewhere in this file.
        tr.style.opacity = '0.75';
        tb.appendChild(tr);
      }
    }
  }

  // Sync select-all checkbox
  const allChk = $('bulkSelectAll');
  if (allChk) {
    allChk.checked = state.selected.size > 0 && state.selected.size >= visibleRows.length;
    allChk.indeterminate = state.selected.size > 0 && state.selected.size < visibleRows.length;
  }
}

// Collapsed/expand toggle row for the Watchlist band (TASK_120 buy-noise
// gate). One <tr><td colspan> spanning every grid column (23 — keep in sync
// with the <th data-col> count in actionable.html); clicking toggles
// state.watchlistExpanded and re-renders.
function _watchlistBandRowEl(count, expanded) {
  const tr = document.createElement('tr');
  tr.className = 'watchlist-band-row';
  const td = document.createElement('td');
  td.colSpan = 23;
  td.style.cssText = 'padding:6px 10px;background:#f8fafc;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.style.cssText = 'display:flex;align-items:center;gap:6px;background:none;border:none;cursor:pointer;'
    + 'font-size:11px;font-weight:600;color:#64748b;padding:2px 0;width:100%;text-align:left;';
  btn.title = 'Unheld ADD/BMN rows where Technical (rr_action) is not BS or BM — parked here instead '
    + 'of Tier 1 until entry timing improves. Click to expand/collapse.';
  btn.innerHTML = `<span style="display:inline-block;width:10px;">${expanded ? '&#9660;' : '&#9654;'}</span>`
    + `<span>Watchlist (${count})</span>`
    + `<span style="font-weight:400;color:#94a3b8;">— unheld buys, entry not yet ripe (Technical not BS/BM)</span>`;
  btn.addEventListener('click', () => {
    state.watchlistExpanded = !state.watchlistExpanded;
    renderGrid();
  });
  td.appendChild(btn);
  tr.appendChild(td);
  return tr;
}

// Td/Tn diagonal-arrow chip — same convention as the macro rail at the
// bottom of this screen (web/macro_areas.js's durArrow): label + up/down/
// flat glyph, colored green/red/gray, reusing that file's .msr-dur* CSS
// (styles.css) so the two read as one visual language. val: >0 up (↗),
// <0 down (↘), 0 flat (–), null/undefined = no data (blank, keeps the
// fixed-width box so nothing shifts).
function _durArrow(val, label) {
  if (val === null || val === undefined) {
    return `<span class="msr-dur" title="${escapeHtml(label)}: no data"></span>`;
  }
  if (val > 0) {
    return `<span class="msr-dur msr-dur-up" title="${escapeHtml(label)} up">${escapeHtml(label)}&#8599;</span>`;
  }
  if (val < 0) {
    return `<span class="msr-dur msr-dur-down" title="${escapeHtml(label)} down">${escapeHtml(label)}&#8600;</span>`;
  }
  return `<span class="msr-dur msr-dur-flat" title="${escapeHtml(label)}">${escapeHtml(label)}&ndash;</span>`;
}

// Td/Tn cell content for the Technical column: sign of (last_price - the
// Trade/Trend line), i.e. is price currently above or below each line —
// same formula api/routers/macro_areas.py uses for the rail's Td/Tn arrows.
function _technicalDurHtml(r) {
  const last = r.last_price != null ? Number(r.last_price) : null;
  const tradeVal = r.a_trade_value != null ? Number(r.a_trade_value) : null;
  const trendVal = r.a_trend_value != null ? Number(r.a_trend_value) : null;
  const tradeSig = (last != null && tradeVal != null) ? Math.sign(last - tradeVal) : null;
  const trendSig = (last != null && trendVal != null) ? Math.sign(last - trendVal) : null;
  if (tradeSig === null && trendSig === null) return '';
  return `<div style="display:flex;gap:4px;">${_durArrow(tradeSig, 'Td')}${_durArrow(trendSig, 'Tn')}</div>`;
}

// Builds one <tr> for the main grid or an expanded Watchlist band row.
// Extracted from renderGrid (TASK_120) so both share identical row markup.
function _buildRowEl(r) {
    const tr = document.createElement('tr');
    const action = (r.consolidated_action || 'NONE').toUpperCase();
    const _ua = (r.last_user_action || '').toUpperCase();
    const isActed = r._rowActed || _ua === 'DONE' || _ua === 'SKIPPED' || _ua === 'OVERRIDDEN';
    if (isActed) tr.classList.add('row-acted');
    if (r.stop_breached) tr.classList.add('row-stop-breach');
    if (r.conviction_hold && r.conviction_direction === 'AVOID' && r._fc_side === 'buy') {
      tr.classList.add('row-lt-avoid-conflict');
    } else if (r.conviction_hold && r.conviction_direction !== 'AVOID' && r._fc_side === 'sell') {
      tr.classList.add('row-lt-conflict');
    }
    tr.dataset.sym = r.tos_symbol;

    const pctChipHtml = _pctChgChipHtml(r.pct_change);
    const priceStr = r.last_price != null ? fmtUsd(r.last_price) : '';
    const hitRateBadge = state.filters.trade_mode ? _sourceHitRateBadge(r) : '';
    const tradabilityBadge = _tradabilityBadge(r);
    // vh=28 (2026-09-01, user request): tall enough to visually span both
    // the chip row and the price row stacked beside it below (see the
    // data-col="chg" cell markup) instead of just the chip's own ~14px row.
    const candleHtml = window.mtTip?.candleSvg(r.open_price, r.high_price, r.low_price, r.last_price, 28) || '';
    // Task 4: intraday marker — shown only when quote is fresher than EOD anchor
    //         AND export_time falls within regular market hours (0930–1559 ET).
    const _idyRaw = String(r.export_time || '').replace(/:/g, '');
    const _idyTime = _idyRaw.length >= 4 ? ' @ ' + _idyRaw.slice(0,2) + ':' + _idyRaw.slice(2,4) : '';
    const _idyHHMM = _idyRaw.length >= 4 ? parseInt(_idyRaw.slice(0,4)) : null;
    const _inMktHours = _idyHHMM != null && _idyHHMM >= 930 && _idyHHMM < 1600;
    const _idySourceLabel = { TL: 'TOS Level', TD: 'TOS Daily', Y: 'Yahoo', CACHE: 'Yahoo (cached)' }[r.quote_source] || r.quote_source || 'unknown';
    const intradayTag = r.quote_is_intraday && _inMktHours
      ? `<span title="Source: ${escapeHtml(_idySourceLabel)}${escapeHtml(_idyTime)} — pct_brr/zone computed against live quote" style="font-size:8px;color:#0a84ff;font-weight:700;margin-left:2px;">IDY</span>`
      : '';
    const isChecked = state.selected.has(r.tos_symbol);

    // TrTnBBRskRng cell: run action through actionDisplay; attach rr-action-cell for hover tooltip
    const rrRaw = r.rr_action || '';
    const rrDisp = actionDisplay(rrRaw);
    const _rrIcData = actionIcon(rrRaw);
    const rrHtml = rrRaw
      ? `<span class="rr-main-ic" style="font-family:ui-monospace,monospace;font-size:24px;font-weight:700;color:${_rrIcData.color};cursor:help;flex-shrink:0;display:inline-block;width:36px;text-align:center;">${_rrIcData.glyph}</span>`
      : `<span class="rr-main-ic" style="font-size:12px;color:#cbd5e1;cursor:default;flex-shrink:0;display:inline-block;width:36px;text-align:center;">—</span>`;
    // TASK_132: BB-vs-RR band drift flag (drv_bb_rr_gap) — shows only when
    // the rolling 20d median APE has crossed WARN/ALERT; see
    // docs/tos_rr_calibration.md "Ongoing monitoring".
    const _bbDrift = r.bb_rr_drift_flag;
    const _bbDriftLine = (() => {
      if (!_bbDrift) return '';
      const fmtPct = v => v != null ? Number(v).toFixed(2) + '%' : 'n/a';
      const title = `BB vs RR band drift (20d median APE) — Top ${fmtPct(r.bb_rr_ape_top_med20)}, `
        + `Bottom ${fmtPct(r.bb_rr_ape_bottom_med20)} — recalibrate: python -m etl.calibrate_tos_rr`;
      const color = _bbDrift === 'ALERT' ? '#ef4444' : '#f59e0b';
      return `<div style="white-space:nowrap;color:${color};font-weight:700;" title="${escapeHtml(title)}">Drift: ${escapeHtml(_bbDrift)}</div>`;
    })();
    const _rrSubLineHtml = (() => {
      const td = r.tn_td_desc || '', bb = r.bb_desc || '';
      const rr = r.rr_desc || (rrRaw && r.rr_bull_bear ? (r.rr_bull_bear === 'B' ? 'Bull' : 'Not-Bull') : '');
      if (!td && !bb && !rr && !_bbDriftLine) return '';
      const line = t => `<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">${escapeHtml(t)}</div>`;
      return `<div class="rr-sub-line" style="font-size:9px;color:#94a3b8;line-height:1.4;" data-filled="1">${td ? line('TnTd: ' + td) : ''}${bb ? line('BB: ' + bb) : ''}${rr ? line('RR: ' + rr) : ''}${_bbDriftLine}</div>`;
    })();

    // RR column: reuses the shared .rr-rb/.rr-rb-tick bar (also used by
    // market_bar.js's mini-tape) — a tick showing where last price sits
    // between LRR (0%, left) and TRR (100%, right). Computed directly from
    // lrr/trr/last_price — NOT quote_pct_brr/ma_pct_brr, which position price
    // between the Trend/Trade technical lines (a different reference frame;
    // see etl/derive.py's pct_brr formula), not the Risk Range at all.
    const _lrrNum = r.lrr != null ? Number(r.lrr) : null;
    const _trrNum = r.trr != null ? Number(r.trr) : null;
    // r._rrPos is hoisted to load time (same formula, see the state.allRows
    // normalization pass) so the RR column header can sort by it — reused
    // here instead of recomputing, to avoid the two ever drifting apart.
    const _rrBarW = r._rrPos;
    // Compact number format so LRR/TRR labels fit the narrow 44px column
    // without wrapping: fewer decimals as magnitude grows.
    const _fmtRR = v => Math.abs(v) >= 100 ? Math.round(v).toString()
                       : Math.abs(v) >= 10  ? v.toFixed(1)
                       : v.toFixed(2);
    // % position number, colored the same low=green/high=red scale as the
    // IV percentile column (window._ivpBarColor) — low (near LRR) is the
    // favorable entry zone, high (near/at TRR, >=85) is the "caution" zone
    // _srcReasonsHtml's warn logic already flags (see _rawRrPos comment
    // above), so the color meaning lines up with that existing convention.
    const _rrPosColor = window._ivpBarColor ? window._ivpBarColor(_rrBarW) : '#7c3aed';
    const _rrPosPctHtml = _rrBarW != null
      ? `<div style="font-size:10px;line-height:1;font-weight:700;text-align:center;font-variant-numeric:tabular-nums;color:${_rrPosColor};" title="Risk Range position: ${_rrBarW}% (LRR ${_lrrNum.toFixed(2)} – TRR ${_trrNum.toFixed(2)})">${_rrBarW}%</div>`
      : '';
    const rrBarHtml = _rrBarW != null
      ? `<div style="display:flex;flex-direction:column;align-items:stretch;gap:4px;">
           ${_rrPosPctHtml}
           <div style="font-size:8px;line-height:1;color:#94a3b8;text-align:left;" title="LRR ${_lrrNum.toFixed(2)}">${_fmtRR(_lrrNum)}</div>
           <div class="rr-rb" title="Risk Range position: ${_rrBarW}% (LRR ${_lrrNum.toFixed(2)} – TRR ${_trrNum.toFixed(2)})"><div class="rr-rb-tick" style="left:${_rrBarW}%;"></div></div>
           <div style="font-size:8px;line-height:1;color:#94a3b8;text-align:right;" title="TRR ${_trrNum.toFixed(2)}">${_fmtRR(_trrNum)}</div>
         </div>`
      : '';

    // Final Call cell — reconciled action + confidence badge
    const fcHtml = _finalCallHtml(r);

    const posStr = fmtCompact(r.current_position_dollar);
    const _hReason = _hiddenReason(r);
    tr.innerHTML = `
      <td data-col="lt" style="padding:4px 2px; text-align:center;">${r.conviction_hold
          ? `<span class="lt-quick-btn lt-scope-btn lt-scope-active" data-sym="${escapeHtml(r.tos_symbol)}" title="Long-term conviction ${r.conviction_direction === 'AVOID' ? 'avoid' : 'hold'} — ${escapeHtml(r.conviction_note || '')}\n\nClick to view/close.">${r.conviction_direction === 'AVOID' ? '🚫' : '🔭'}</span>`
          : `<span class="lt-quick-btn lt-scope-btn" data-sym="${escapeHtml(r.tos_symbol)}" title="Add a long-term conviction note (analyst call note) — a reminder only. Hold badges this row so a SELL/REDUCE signal doesn't get mistaken for a reason to abandon the thesis; Avoid badges it so a BUY/ADD/INCREASE signal doesn't get mistaken for a reason to chase it. Doesn't suppress or change the signal itself.">🔭</span>`}
      </td>
      <td data-col="bulk" style="padding:4px 6px; text-align:center;">
        <input type="checkbox" class="row-check" data-sym="${escapeHtml(r.tos_symbol)}"${isChecked ? ' checked' : ''}>
      </td>
      <td data-col="h" class="num" style="font-size:10px;color:#f59e0b;font-weight:700;text-align:center;">${_hReason ? `<span title="${escapeHtml(_hReason)}">Y</span>` : ''}</td>
      <td data-col="pos" class="num" style="font-size:11px; color:#475569;" ${r.held_accounts ? `title="Held in: ${escapeHtml(_heldAccountsDisplay(r.held_accounts))}"` : ''}>${posStr || '<span style="color:#cbd5e1;">—</span>'}</td>
      <td data-col="amt" class="num">
        <span class="amt-primary">${fmtUsd(r._amt)}</span>
        ${r.stop_signal ? (
          // 2026-08-12: color by the SIGN of stop_signal itself (TD STM/TN SA
          // = sell = red, TD BM/TD BMN = buy = green), not r.stop_breached --
          // stop_breached also requires held_today=True, so a sell signal on
          // a NOT-held symbol (stop_breached=false) was wrongly rendering
          // green here.
          (r.stop_signal === 'TD STM' || r.stop_signal === 'TN SA')
            ? `<div style="font-size:9px;color:#dc2626;font-weight:700;white-space:nowrap;" title="Price just crossed below its ${r.stop_signal === 'TN SA' ? 'Trend' : 'Trade'} line (prior 3 days above, today below)">${escapeHtml(r.stop_signal)}</div>`
            : `<div style="font-size:9px;color:#16a34a;white-space:nowrap;" title="Price just crossed above its Trade line (prior 3 days below, today above)${r.stop_signal === 'TD BM' ? ', and is also above its Trend line today' : ' (still at/below its Trend line today)'}">${escapeHtml(r.stop_signal)}</div>`
        ) : ''}
      </td>
      <td data-col="chg" class="num">
        <div class="chg-candle-row" style="display:flex;align-items:center;justify-content:flex-end;gap:4px;">
          ${candleHtml}
          <div style="display:flex;flex-direction:column;align-items:center;gap:1px;">
            ${pctChipHtml}
            ${intradayTag ? `<div>${intradayTag}</div>` : ''}
            ${priceStr ? `<div style="font-size:10px;color:#94a3b8;">${priceStr}</div>` : ''}
          </div>
        </div>
      </td>
      <td data-col="sym" data-sym-cell="${escapeHtml(r.tos_symbol)}" style="padding:6px 4px; cursor:pointer; text-align:center;" title="${r.rr_name && r.rr_name !== r.tos_symbol ? escapeHtml(r.tos_symbol) + ' · ' : ''}Click for chart">
        <strong class="tv-sym-link" data-notespop="${escapeHtml(r.tos_symbol)}" style="font-size:11px;color:${_symOutlookColor(r)};" title="Hover for comments">${escapeHtml(r.rr_name || r.tos_symbol || '')}</strong>
        ${r._watchlisted && r._isNew
          ? '<span class="new-pill" title="Winning source data just landed for this date — Technical isn\'t entry-ripe yet, so it waits here rather than promoting to Tier 1">NEW</span>'
          : ''}
        ${hitRateBadge ? '<div style="margin-top:1px;">' + hitRateBadge + '</div>' : ''}
        ${tradabilityBadge ? '<div style="margin-top:1px;">' + tradabilityBadge + '</div>' : ''}
      </td>
      <td data-col="agree3" style="padding:6px 4px; text-align:center;">${(() => {
        const dir = _agreementDir(r);
        if (dir === 'sell') return `<span title="3-Way Agreement: MACRO/Sources/Technical agree sell, none opposing" style="color:#dc2626;font-size:12px;font-weight:700;">&#9660;3</span>`;
        if (dir === 'buy')  return `<span title="3-Way Agreement: MACRO/Sources/Technical agree buy, none opposing" style="color:#16a34a;font-size:12px;font-weight:700;">&#9650;3</span>`;
        return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
      })()}</td>
      <td data-col="action" style="padding:6px 4px;">${fcHtml}</td>
      <td data-col="macro" style="padding:4px 6px; text-align:center;">${macroCellHtml(r)}</td>
      <td data-col="calc" style="padding:6px 4px;">${_finalCallCalHtml(r)}</td>
      <td data-col="sources" class="act-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" style="padding:6px 4px; cursor:help;">
        <div style="display:flex;align-items:flex-start;gap:8px;">
          ${_isOverMaxOverlay(r) ? `<div style="width:38px;flex-shrink:0;align-self:center;text-align:center;font-size:8px;line-height:1;font-weight:600;" class="${_actionColorCls(action)}">was ${actionText(actionDisplay(action))}</div>` : ''}
          ${_srcReasonsHtml(r)}
        </div>
      </td>
      <td data-col="technical" class="rr-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" data-date="${escapeHtml(r.as_of_date || state.date || '')}" style="padding:6px 4px;">
        <div style="display:flex;align-items:flex-start;gap:6px;">
          ${rrHtml}
          <div>
            ${_technicalDurHtml(r)}
            ${_rrSubLineHtml}
          </div>
        </div>
      </td>
      <td data-col="rr" style="padding:6px 4px;">${rrBarHtml}</td>
      <td data-col="vlm" class="num rvol-cell" data-sym="${escapeHtml(r.tos_symbol)}" data-volpop style="cursor:default;">${typeof rvolDot === 'function' ? rvolDot(r.rvol, r.rvol_prior) : ''}${r.vlm_action ? `<span style="display:inline-block;margin-left:3px;font-size:9px;padding:1px 3px;border-radius:3px;background:${r.vlm_action==='Accumulate'?'#bbf7d0':r.vlm_action==='Avoid'?'#fecaca':'#e5e7eb'};color:#374151;font-weight:600;text-decoration:none;vertical-align:middle;">${escapeHtml(r.vlm_action === 'Accumulate' ? 'Accum' : r.vlm_action)}</span>` : ''}</td>
      <td data-col="iv" class="num" data-sym="${escapeHtml(r.tos_symbol)}" data-ivpop style="padding:3px 4px;cursor:default;text-align:center;">${(() => {
        const ivpVal = r.iv_percentile != null ? Math.round(Number(r.iv_percentile)) : null;
        const hvVal  = r.hv != null ? Number(r.hv) * 100 : null;
        const ivVal  = r.imp_volatility != null ? Number(r.imp_volatility) * 100 : null;
        const glyph  = window.ivGlyph ? window.ivGlyph(ivpVal, ivVal, hvVal, r.iv_to_hv_discount) : '';
        const ivpCol = window._ivpBarColor ? window._ivpBarColor(ivpVal) : '#7c3aed';
        const fmt = v => v != null ? Math.round(v) : '—';
        const edgeTag = ivpVal != null ? _factorEdgeTag('IV percentile', _ivBucket(ivpVal), true) : '';
        return glyph
          + `<div style="font-size:8px;line-height:1.2;white-space:nowrap;font-variant-numeric:tabular-nums;">`
          + `<span style="color:${ivpCol};font-weight:700;">${fmt(ivpVal)}</span>`
          + `<span style="color:#cbd5e1;">/</span>`
          + `<span style="color:#374151;">${fmt(hvVal)}</span>`
          + `<span style="color:#cbd5e1;">/</span>`
          + `<span style="color:#000;">${fmt(ivVal)}</span>`
          + `</div>`
          + (edgeTag ? `<div style="line-height:1.2;">${edgeTag}</div>` : '');
      })()}</td>
      <td data-col="macd" class="num" style="font-size:11px;font-weight:600;color:${_macdColor(r.a_macd_brr)}">${r.a_macd_brr != null ? Number(r.a_macd_brr).toFixed(2) : ''}${_macdCaret(r.a_macdh_d_brr)}</td>
      <td data-col="macdh" class="num" style="font-size:11px;font-weight:600;color:${_macdColor(r.a_macdh_d_brr)}">${r.a_macdh_d_brr != null ? Number(r.a_macdh_d_brr).toFixed(2) : ''}${_macdCaret(r.a_macdh_d_brr)}</td>
      <td data-col="rsi" class="num" style="font-size:11px;font-weight:600;color:${_rsiColor(r.rsi)}">${r.rsi != null ? Number(r.rsi).toFixed(1) : ''}${r.rsi != null ? _factorEdgeTag('RSI', _rsiBucket(r.rsi)) : ''}</td>
      <td data-col="rules" class="rules-link-cell" data-sym="${escapeHtml(r.tos_symbol)}" style="padding:4px 6px; max-width:340px; overflow:hidden; cursor:pointer;" title="Open Rule Flow for ${escapeHtml(r.tos_symbol)}">${firesCellHtml(r, 4)}</td>
      <td data-col="bullprob" class="num" style="padding:4px 6px; white-space:nowrap;">${_bullProbCellHtml(r)}</td>
      <td data-col="agree" style="padding:4px 6px; white-space:nowrap;">${_agreementCellHtml(r)}</td>
      <td data-col="pvv" style="padding:4px 6px; text-align:center; white-space:nowrap;">${_pvvCellHtml(r)}</td>
    `;
    tr.onclick = (e) => {
      if (e.target.closest('.row-check') || e.target.closest('.lt-quick-btn')) return;
      const rulesCell = e.target.closest('.rules-link-cell');
      if (rulesCell) {
        window.location.href = '/rule-flow?symbol=' + encodeURIComponent(rulesCell.dataset.sym);
        return;
      }
      openDrilldown(r);
    };
    return tr;
}

// escapeHtml is provided by _common.js (window.escapeHtml).

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

// F1: one round-trip for bulk-selected rows (was a sequential inlineAction
// loop — N POSTs). Server loops the same forensic-snapshot insert in one
// transaction (POST /api/actionable/bulk-action).
async function bulkAction(action) {
  const syms = Array.from(state.selected);
  if (!syms.length) return;
  const isLegacyAction = ['DONE','SKIPPED','SNOOZED','OVERRIDDEN'].includes((action||'').toUpperCase());
  const userAction = isLegacyAction ? action.toUpperCase() : 'DONE';
  const actionCode = isLegacyAction ? null : action;
  const payload = {
    symbols: syms, as_of_date: state.date, user_action: userAction,
    action_code: actionCode, user_notes: 'bulk',
  };
  try {
    const resp = await fetchJson('/api/actionable/bulk-action', {
      method: 'POST', body: JSON.stringify(payload),
    });
    let okCount = 0;
    for (const r of (resp.results || [])) {
      if (r.error) continue;
      okCount++;
      const row = state.allRows.find(rr => rr.tos_symbol === r.symbol);
      if (row) row._rowActed = true;
      const tr = document.querySelector(`#actBody tr[data-sym="${CSS.escape(r.symbol)}"]`);
      if (tr) tr.classList.add('row-acted');
    }
    showStatus(`${action}: ${okCount} of ${syms.length} symbol(s)`, 'success', 2500);
  } catch (e) {
    showStatus(`${action} failed: ${e.message}`, 'error');
  }
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
  // Final Call badge (same source as the grid's ACTION column and the Done
  // button's logged code) so the card matches what gets recorded.
  const fc = finalCall(r);
  if (!fc.feasible || fc.confidence === 'none') {
    $('fcAction').innerHTML = '<span style="color:#cbd5e1;font-size:16px;">—</span>';
  } else {
    const fcText = fc.label || actionText(fc);
    const fcDisp = actionDisplay(fc.code || (fc.side === 'sell' ? 'SA' : fc.side === 'buy' ? 'BS' : 'HOLD'));
    const fcColorCls = (fcDisp.colorCls || 'act-neutral') + '-fill';
    const fcHedgeyeStyle = fcDisp.code === 'SA' ? 'background:#d4537e;' : fcDisp.code === 'BM' ? 'background:#1d9e75;' : '';
    $('fcAction').innerHTML = `<span class="act-badge ${fcColorCls}" style="${fcHedgeyeStyle}font-size:16px;padding:4px 14px;" title="${escapeHtml(fc.label || fcText)}">${escapeHtml(fcText)}</span>`;
  }
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
    // 'DONE' logs the row's Final Call code (matches the grid's inline Done
    // button, doneBtn.dataset.fc || 'DONE') so both entry points record the
    // same action_code (addendum, carried forward from TASK_107 review).
    const actCode = action === 'DONE' ? (r._fc_code || 'DONE') : action;
    inlineAction(r.tos_symbol, actCode).then(() => {
      state.focusIdx = Math.min(state.focusIdx, _focusRows().length - 1);
      _renderFocusCard();
    });
  } else {
    state.focusIdx = Math.min(state.focusIdx + 1, _focusRows().length - 1);
    _renderFocusCard();
  }
}

function focusPrev() {
  if (!_focusRows().length) return;
  state.focusIdx = Math.max(0, state.focusIdx - 1);
  _renderFocusCard();
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
  // Column-visibility (TASK_105): mirror the grid — a column hidden via the
  // gear menu (or the 'H' column when "show hidden" is off) is excluded here.
  const hidden = new Set(state.hiddenCols);
  if (!state.filters.show_hidden) hidden.add('h');
  const shown = id => !hidden.has(id);

  const cols = [
    ['Symbol',        r => r.tos_symbol],
    ['Change %',      r => r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : ''],
    ['AMT$',          r => r._amt],
    ['Stop Signal',   r => r.stop_signal || ''],
    ['Action',        r => r.consolidated_action ? actionText(actionDisplay(r.consolidated_action)) : ''],
    ['Final Call',    r => { const fc = finalCall(r); return (fc.feasible && fc.confidence !== 'none') ? (fc.label || fc.code || '') : ''; }],
    ['Final Call Confidence', r => { const fc = finalCall(r); return (fc.feasible && fc.confidence !== 'none') ? fc.confidence : ''; }],
    ['TrTnBBRskRng',  r => r.rr_action || ''],
    ['Source',        r => r.winning_source || ''],
    ['Reason',        r => _winningReason(r)],
    ['Other Sources', r => otherSourcesText(r)],
    ['Sector',        r => r.sector || ''],
    ['Real Asset Class', r => r.real_asset_class || ''],
  ];
  // Trig column: trig_action is no longer surfaced anywhere else on this
  // screen (TASK_109) — drop it from the export too.
  if (shown('macro'))
    cols.push(['MACRO', r => r.macro_value ? (r.macro_value + (r.macro_turn ? ' ' + r.macro_turn : '')) : '']);
  if (shown('calc'))
    cols.push(['CALC', r => r.final_action_cal || r.final_code_cal || '']);
  if (shown('bullprob'))
    cols.push(['P(↑ 20d)', r => r.bull_prob != null ? Math.round(Number(r.bull_prob) * 100) + '%' : '']);
  if (shown('agree'))
    cols.push(['Agree', r => r.agreement_class ? (_AGR_LABEL[r.agreement_class] || r.agreement_class) : '']);
  if (shown('rr'))
    cols.push(['RR%', r => {
      const lo = r.lrr != null ? Number(r.lrr) : null;
      const hi = r.trr != null ? Number(r.trr) : null;
      const last = r.last_price != null ? Number(r.last_price) : null;
      if (lo == null || hi == null || last == null || hi === lo) return '';
      return Math.round(Math.max(0, Math.min(100, (last - lo) / (hi - lo) * 100))) + '%';
    }]);
  if (shown('vlm'))
    cols.push(['RVOL', r => r.rvol != null ? Number(r.rvol).toFixed(2) : '']);
  if (shown('iv')) {
    cols.push(['IVP', r => r.iv_percentile != null ? r.iv_percentile : '']);
    cols.push(['IV',  r => r.imp_volatility != null ? (Number(r.imp_volatility) * 100).toFixed(1) + '%' : '']);
    cols.push(['HV',  r => r.hv != null ? (Number(r.hv) * 100).toFixed(1) + '%' : '']);
  }
  if (shown('macd'))
    cols.push(['MACD', r => r.a_macd_brr != null ? Number(r.a_macd_brr).toFixed(2) : '']);
  if (shown('macdh'))
    cols.push(['MACDH', r => r.a_macdh_d_brr != null ? Number(r.a_macdh_d_brr).toFixed(2) : '']);
  if (shown('rsi'))
    cols.push(['RSI', r => r.rsi != null ? Number(r.rsi).toFixed(1) : '']);

  cols.push(
    // kept in CSV even though removed from table
    ['POS$',          r => r.current_position_dollar],
    ['Price',         r => r.last_price],
    ['Change $',      r => r.net_chng],
    ['As Of',         r => fmtAsOfExport(r.export_date, r.export_time, r.loaded_at)],
    ['Held',          r => r.held_today ? 'Y' : 'N'],
    ['In My List',    r => r.in_my_list ? 'Y' : 'N'],
    ['Suppressed',    r => r.suppressed_reason || ''],
  );
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

// Copy the symbols actually on screen right now as a comma-separated list
// (2026-07-05): state.visibleRows (cached by renderGrid) reflects the
// Top-N collapse when active, unlike state.rows (the full filtered set,
// which is what exportCsv still uses -- CSV export intentionally exports
// everything matching the filter, not just what's currently paginated
// into view).
async function copySymbols() {
  const rows = state.visibleRows || state.rows;
  const symbols = rows.map(r => r.tos_symbol).filter(Boolean);
  if (!symbols.length) return;
  const text = symbols.join(',');
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      // Fallback for non-secure contexts without the async Clipboard API.
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    showStatus(`Copied ${symbols.length} symbols`, 'success');
  } catch (e) {
    console.error('Copy symbols failed:', e);
    showStatus('Copy symbols failed: ' + e.message, 'error');
  }
}

// 2026-08-25, user-directed: "add a small email button so i can send email
// from actionable screen" -- on-demand send of the same Trade Mode digest
// the nightly job emails (etl/export_trade_mode.py), via
// POST /api/actionable/email-trade-mode. That endpoint deliberately skips
// the nightly job's NOTIFY_EMAIL-off / stale-anchor guards -- clicking this
// button is an explicit "send it now" regardless of time of day.
async function emailTradeMode() {
  const btn = $('emailTradeModeBtn');
  if (btn) btn.disabled = true;
  showStatus('Sending Trade Mode email…', 'info');
  try {
    const result = await fetchJson('/api/actionable/email-trade-mode', { method: 'POST' });
    showStatus(
      `Sent: ${result.buys} buy(s), ${result.sells} sell(s), ${result.breaches} breach(es)`,
      'success'
    );
  } catch (e) {
    console.error('Email Trade Mode failed:', e);
    showStatus('Email failed: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
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

// ---- drilldown TV chart ----
const _DD_TV_MAP = {
  '$SPX':'SP:SPX','SPX':'SP:SPX','$COMP':'NASDAQ:NDX','COMP':'NASDAQ:NDX','COMPQ':'NASDAQ:NDX',
  '$DJI':'DJ:DJI','DJI':'DJ:DJI','INDU':'DJ:DJI','RUT':'TVC:RUT',
  'VIX':'TVC:VIX','VXN':'TVC:VXN','VXD':'TVC:VXD','RVX':'TVC:RVX',
  'OVX':'TVC:OVX','GVZ':'TVC:GVZ','MOVE':'TVC:MOVE',
  'DXY':'TVC:DXY','$DXY':'TVC:DXY',
  '/CL':'TVC:USOIL','/GC':'TVC:GOLD','/ES':'SP:SPX','/NQ':'NASDAQ:NDX','/RTY':'TVC:RUT',
};
let _ddTvSeq = 0;
function _loadDrilldownChart(sym) {
  const dailyEl = $('modalTvChart');
  const intradayEl = $('modalTvChartIntraday');
  if (!dailyEl || !intradayEl) return;
  dailyEl.innerHTML = '';
  intradayEl.innerHTML = '';
  if (!sym || sym.startsWith('$_CASH')) {
    const noChart = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:12px;">No chart</div>';
    dailyEl.innerHTML = noChart;
    intradayEl.innerHTML = noChart;
    return;
  }
  let tvSym = _DD_TV_MAP[sym] || (sym.startsWith('$') ? sym.slice(1) : sym.startsWith('/') ? sym.slice(1)+'1!' : sym);
  const dailyId = 'dd_tv_' + (++_ddTvSeq);
  const intradayId = 'dd_tv_' + (++_ddTvSeq);
  const dailyWrap = document.createElement('div');
  dailyWrap.id = dailyId;
  dailyWrap.style.cssText = 'width:100%;height:100%;';
  dailyEl.appendChild(dailyWrap);
  const intradayWrap = document.createElement('div');
  intradayWrap.id = intradayId;
  intradayWrap.style.cssText = 'width:100%;height:100%;';
  intradayEl.appendChild(intradayWrap);
  const _render = () => {
    new TradingView.widget({
      autosize:true, symbol:tvSym, interval:'D',
      timezone:'America/New_York', theme:'light', style:'1', locale:'en',
      enable_publishing:false, allow_symbol_change:true, save_image:false,
      studies:['BB@tv-basicstudies','RSI@tv-basicstudies'],
      container_id:dailyId,
    });
    new TradingView.widget({
      autosize:true, symbol:tvSym, interval:'5', range:'1D',
      timezone:'America/New_York', theme:'light', style:'1', locale:'en',
      enable_publishing:false, allow_symbol_change:true, save_image:false,
      container_id:intradayId,
    });
  };
  if (window.TradingView) {
    _render();
  } else {
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/tv.js';
    s.onload = _render;
    document.head.appendChild(s);
  }
}

// ---- drilldown ----
async function openDrilldown(row) {
  hideSourcePop();
  state.current = row;
  $('modalTitle').textContent = row.tos_symbol;
  $('modalPrice').textContent = row.last_price != null ? '$' + Number(row.last_price).toFixed(2) : '';
  $('modalSector').textContent = row.sector || '';
  const _ac = row.real_asset_class || '';
  $('modalAssetClass').textContent = _ac;
  $('modalAssetClass').style.display = _ac ? '' : 'none';
  const _posDollar = row.current_position_dollar != null ? 'Pos: ' + fmtUsd(row.current_position_dollar) : '';
  $('modalPositionDollar').textContent = _posDollar;
  $('modalPositionDollar').style.display = _posDollar ? '' : 'none';
  const _cname = row.company_name || '';
  $('modalCompanyName').textContent = _cname;
  $('modalCompanyName').style.display = _cname ? '' : 'none';

  const chgEl = $('modalPriceChange');
  if (row.net_chng != null && row.pct_change != null) {
    const nc = Number(row.net_chng), pc = Number(row.pct_change);
    const chgCls = nc >= 0 ? 'act-buy-strong' : 'act-sell-strong';
    const fmtAmt = v => { const a = Math.abs(v); return (v < 0 ? '-' : '+') + '$' + (a >= 1000 ? Math.round(a).toLocaleString() : a.toFixed(2)); };
    chgEl.innerHTML = `<span class="${chgCls}" style="font-weight:700;font-size:15px;">${fmtAmt(nc)} (${pc.toFixed(2)}%)</span>`;
  } else {
    chgEl.innerHTML = '';
  }

  const action = (row.consolidated_action || 'NONE').toUpperCase();
  const kv = $('modalKv');
  kv.innerHTML = `
    <dt>Action</dt><dd><span class="act-badge ${(actionDisplay(_badgeAction(row)).colorCls || 'act-neutral') + '-tint'}">${actionLabel(row)}</span>${_isOverMaxOverlay(row) ? ` <small class="${_actionColorCls(action)}" style="font-weight:600;font-size:9px;">was ${actionText(actionDisplay(action))}</small>` : ''}</dd>
    <dt>Winning source</dt><dd>${row.winning_source || '—'}</dd>
    <dt>AMT$</dt><dd><strong>${fmtUsd(row._amt) || '—'}</strong></dd>
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
      const srcCode = s.source || s.source_code || '';
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
        <td style="font-size:10px;">${escapeHtml(s.reason || s.action_reason || '')}</td>
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
  await loadConviction(row.tos_symbol);
  loadRRAnalysis(row.tos_symbol, row.as_of_date);
  _loadDrilldownChart(row.tos_symbol);

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
  if (srcCode === 'CALL') _loadCallNote(td);
}

// CALL source only: fetch every analyst commentary paragraph for this symbol
// from the CALL email (note_repo) - a symbol can have both a Top-5 blurb and
// a separate fuller write-up in the same email - and fill in the placeholder
// left by _comparisonPanelHtml. Joined on snapshot_date (not message_id -
// hist_call's message_id column is always NULL, since hist_call is populated
// via the file-loader round-trip which drops it). The comparison record's
// current and previous snapshot_date are usually two different CALL emails
// (e.g. this week's vs. last week's) - fetch and show notes for both, since
// showing only "current" hides the previous email's notes entirely.
async function _loadCallNote(container) {
  const el = container.querySelector('#cmpCallNote');
  if (!el) return;
  const c = _cmpData.get('CALL');
  const curD = (c && c.current && !c.current.dropped) ? c.current.snapshot_date : null;
  const prvD = (c && c.previous && !c.previous.dropped) ? c.previous.snapshot_date : null;
  const sym = state.current && state.current.tos_symbol;
  const dateGroups = [];
  if (curD) dateGroups.push({ label: 'Current', date: curD });
  if (prvD && prvD !== curD) dateGroups.push({ label: 'Previous', date: prvD });
  if (!dateGroups.length || !sym) { el.textContent = 'No analyst comment available.'; return; }

  const _label = st => st === 'the_call_top5' ? 'Top 5 idea' : 'Commentary';
  try {
    const groups = await Promise.all(dateGroups.map(async g => {
      const data = await fetchJson('/api/actionable/call-note?symbol=' + encodeURIComponent(sym) +
        '&date=' + encodeURIComponent(g.date));
      const notes = (data && Array.isArray(data.notes)) ? data.notes.filter(n => n && n.note_text) : [];
      return { label: g.label, date: g.date, notes };
    }));
    const nonEmpty = groups.filter(g => g.notes.length);
    if (!nonEmpty.length) { el.textContent = 'No analyst comment available.'; return; }
    el.innerHTML = nonEmpty.map(g => {
      const body = g.notes.map(note => {
        const link = note.gmail_link
          ? ` &middot; <a href="${escapeHtml(note.gmail_link)}" target="_blank" rel="noopener">open email</a>` : '';
        return '<div class="cmp-call-note-block">' +
          '<div class="cmp-call-note-head">' + _label(note.source_type) + link + '</div>' +
          '<div class="cmp-call-note-body">' + escapeHtml(note.note_text) + '</div>' +
        '</div>';
      }).join('');
      return '<div class="cmp-call-note-group">' +
        '<div class="cmp-call-note-group-head">' + g.label + ' &middot; ' + fmtMD(g.date) + '</div>' +
        body +
      '</div>';
    }).join('');
  } catch (_) {
    el.textContent = 'No analyst comment available.';
  }
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
  const callNoteBlock = (srcCode === 'CALL')
    ? '<div class="cmp-call-note" id="cmpCallNote">Loading analyst comment&hellip;</div>' : '';
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
    callNoteBlock +
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

// ---- Long-term conviction hold (2026-08-14) -----------------------------------
// Manual tracker for analyst-call (HE Call) picks to accumulate long-term, so
// short-term SELL/REDUCE signals don't get acted on by mistake. Annotation
// only server-side (drv_actionable.conviction_hold/conviction_note) — this
// panel is the add/close UI, keyed to whichever symbol the drilldown modal
// is currently open on. At most one ACTIVE hold per symbol (DB-enforced).
let _convictionActiveId = null;

// 2026-08-15: icon per direction — 🔭 Hold (don't sell), 🚫 Avoid (don't buy).
// Shared by the grid badge, the drilldown modal, and the quick-add popover.
function _convictionDirIcon(direction) {
  return direction === 'AVOID' ? '🚫' : '🔭';
}
function _convictionDirLabel(direction) {
  return direction === 'AVOID' ? 'Avoid — don\'t buy' : 'Hold — don\'t sell';
}

async function loadConviction(symbol) {
  _convictionActiveId = null;
  $('convictionStatus').textContent = '';
  let rows = [];
  try {
    rows = await fetchJson('/api/actionable/conviction-holds?symbol=' + encodeURIComponent(symbol));
  } catch (_) { rows = []; }
  const active = Array.isArray(rows) ? rows.find(r => r.status === 'ACTIVE') : null;
  if (active) {
    _convictionActiveId = active.id;
    const added = (active.added_at || '').toString().slice(0, 10);
    const tgt = active.target_date ? ' · target ' + active.target_date : '';
    $('convictionActiveText').textContent =
      `${_convictionDirIcon(active.direction)} ${_convictionDirLabel(active.direction)} — added ${added}${tgt} — ${active.thesis_note}`;
    $('convictionActive').style.display = '';
    $('convictionAdd').style.display = 'none';
  } else {
    $('convictionActive').style.display = 'none';
    $('convictionAdd').style.display = '';
    $('convictionDirection').value = 'HOLD';
    $('convictionThesis').value = '';
    $('convictionTargetDate').value = '';
  }
}

async function addConvictionHold() {
  if (!state.current) return;
  const thesis_note = $('convictionThesis').value.trim();
  if (!thesis_note) {
    $('convictionStatus').textContent = 'Thesis note is required.';
    return;
  }
  try {
    await fetchJson('/api/actionable/conviction-holds', {
      method: 'POST',
      body: JSON.stringify({
        tos_symbol: state.current.tos_symbol,
        thesis_note,
        target_date: $('convictionTargetDate').value || null,
        direction: $('convictionDirection').value || 'HOLD',
      }),
    });
    $('convictionStatus').textContent = 'Added.';
    await loadConviction(state.current.tos_symbol);
    loadActionable();  // refresh grid so the LT badge appears
  } catch (e) {
    $('convictionStatus').textContent = 'Add failed: ' + e.message;
  }
}

async function closeConvictionHold() {
  if (!_convictionActiveId) return;
  try {
    await fetchJson('/api/actionable/conviction-holds/' + encodeURIComponent(_convictionActiveId), {
      method: 'PATCH',
      body: JSON.stringify({
        status: $('convictionCloseStatus').value,
        closed_note: $('convictionCloseNote').value || null,
      }),
    });
    $('convictionStatus').textContent = 'Closed.';
    $('convictionCloseNote').value = '';
    await loadConviction(state.current.tos_symbol);
    loadActionable();
  } catch (e) {
    $('convictionStatus').textContent = 'Close failed: ' + e.message;
  }
}

// Hard delete — for cleaning up a mistaken entry, not the normal
// end-of-thesis workflow (that's closeConvictionHold above, which keeps the
// row as history). Not reversible, so confirm first.
async function deleteConvictionHold() {
  if (!_convictionActiveId) return;
  if (!confirm('Delete this conviction hold? This cannot be undone (use Close instead to keep it as history).')) return;
  try {
    await fetchJson('/api/actionable/conviction-holds/' + encodeURIComponent(_convictionActiveId), {
      method: 'DELETE',
    });
    $('convictionStatus').textContent = 'Deleted.';
    await loadConviction(state.current.tos_symbol);
    loadActionable();
  } catch (e) {
    $('convictionStatus').textContent = 'Delete failed: ' + e.message;
  }
}

// ---- Long-term conviction hold: inline quick-add popover -----------------------
// User: "instead of going to a popup, why can't you add a button in SYMBOL
// column below %button so I can add it from there in a editable small form."
// A click-toggled popover anchored to the +LT / 🔭 LT button in the grid's
// SYMBOL cell — no need to open the full drilldown modal just to log a
// thesis. Self-contained (doesn't touch state.current, so it works from any
// row regardless of whether the drilldown modal is open).
let _cpSym = null;
let _cpActiveId = null;

function closeConvictionPop() {
  _cpSym = null;
  const pop = $('convictionPop');
  if (pop) pop.style.display = 'none';
}

function _positionConvictionPop(pop, anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
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

function _convictionPopHtml(sym, active) {
  if (active) {
    const added = (active.added_at || '').toString().slice(0, 10);
    const tgt = active.target_date ? ' &middot; target ' + escapeHtml(active.target_date) : '';
    const dirIcon = _convictionDirIcon(active.direction);
    const dirLabel = _convictionDirLabel(active.direction);
    return `
      <div class="cp-title">${dirIcon} ${escapeHtml(sym)} &mdash; ${escapeHtml(dirLabel)}</div>
      <div style="margin-bottom:7px;">Added ${escapeHtml(added)}${tgt}<br>${escapeHtml(active.thesis_note)}</div>
      <select id="cpCloseStatus" style="width:100%;font:inherit;padding:4px;border:1px solid #e2e8f0;border-radius:5px;margin-bottom:6px;">
        <option value="CLOSED_WIN">Close as: Won — thesis played out</option>
        <option value="CLOSED_LOSS">Close as: Lost — thesis broke</option>
        <option value="EXPIRED">Close as: Expired / no longer tracking</option>
      </select>
      <input type="text" id="cpCloseNote" placeholder="close note (optional)…">
      <div class="cp-actions">
        <button class="btn" id="cpDeleteBtn" title="Hard-delete this entry (not reversible) — use Close instead to keep it as history" style="color:#dc2626;border-color:#dc2626;">Delete</button>
        <button class="btn" id="cpCloseBtn">Close</button>
      </div>
      <div class="cp-status" id="cpStatus"></div>`;
  }
  return `
    <div class="cp-title">&#128301; ${escapeHtml(sym)} &mdash; Add Long-Term Note</div>
    <select id="cpDirection" style="width:100%;font:inherit;padding:4px;border:1px solid #e2e8f0;border-radius:5px;margin-bottom:6px;" title="Hold: don't sell on short-term noise, badges SELL/REDUCE. Avoid: don't chase a BUY signal, badges BUY/ADD/INCREASE.">
      <option value="HOLD">🔭 Hold — don't sell</option>
      <option value="AVOID">🚫 Avoid — don't buy</option>
    </select>
    <textarea id="cpThesis" placeholder="e.g. HE Call: strong Q3 setup, accumulate on weakness…"></textarea>
    <label style="display:flex;align-items:center;gap:6px;color:#64748b;margin-bottom:6px;">Target date
      <input type="date" id="cpTargetDate">
    </label>
    <div class="cp-actions">
      <button class="btn" id="cpAddBtn">Add note</button>
    </div>
    <div class="cp-status" id="cpStatus"></div>`;
}

function _wireConvictionPop(sym) {
  const addBtn = document.getElementById('cpAddBtn');
  if (addBtn) addBtn.addEventListener('click', async () => {
    const statusEl = document.getElementById('cpStatus');
    const thesis = document.getElementById('cpThesis').value.trim();
    if (!thesis) { statusEl.textContent = 'Thesis note is required.'; return; }
    try {
      await fetchJson('/api/actionable/conviction-holds', {
        method: 'POST',
        body: JSON.stringify({
          tos_symbol: sym,
          thesis_note: thesis,
          target_date: document.getElementById('cpTargetDate').value || null,
          direction: document.getElementById('cpDirection').value || 'HOLD',
        }),
      });
      closeConvictionPop();
      loadActionable();  // refresh grid so the LT badge appears
    } catch (e) {
      statusEl.textContent = 'Add failed: ' + e.message;
    }
  });
  const closeBtn = document.getElementById('cpCloseBtn');
  if (closeBtn) closeBtn.addEventListener('click', async () => {
    const statusEl = document.getElementById('cpStatus');
    if (!_cpActiveId) return;
    try {
      await fetchJson('/api/actionable/conviction-holds/' + encodeURIComponent(_cpActiveId), {
        method: 'PATCH',
        body: JSON.stringify({
          status: document.getElementById('cpCloseStatus').value,
          closed_note: document.getElementById('cpCloseNote').value || null,
        }),
      });
      closeConvictionPop();
      loadActionable();
    } catch (e) {
      statusEl.textContent = 'Close failed: ' + e.message;
    }
  });
  const deleteBtn = document.getElementById('cpDeleteBtn');
  if (deleteBtn) deleteBtn.addEventListener('click', async () => {
    const statusEl = document.getElementById('cpStatus');
    if (!_cpActiveId) return;
    if (!confirm('Delete this conviction hold? This cannot be undone (use Close instead to keep it as history).')) return;
    try {
      await fetchJson('/api/actionable/conviction-holds/' + encodeURIComponent(_cpActiveId), {
        method: 'DELETE',
      });
      closeConvictionPop();
      loadActionable();
    } catch (e) {
      statusEl.textContent = 'Delete failed: ' + e.message;
    }
  });
}

async function openConvictionPop(sym, anchorEl) {
  const pop = $('convictionPop');
  if (!pop) return;
  if (_cpSym === sym && pop.style.display === 'block') {
    closeConvictionPop();  // clicking the same button again toggles it off
    return;
  }
  _cpSym = sym;
  pop.innerHTML = `<div class="cp-title">&#128301; ${escapeHtml(sym)} &mdash; Long-Term Note</div><div class="cp-status">Loading&hellip;</div>`;
  pop.style.display = 'block';
  _positionConvictionPop(pop, anchorEl);

  let rows = [];
  try {
    rows = await fetchJson('/api/actionable/conviction-holds?symbol=' + encodeURIComponent(sym));
  } catch (_) { rows = []; }
  if (_cpSym !== sym) return;  // closed or reopened on a different symbol while this was loading
  const active = Array.isArray(rows) ? rows.find(r => r.status === 'ACTIVE') : null;
  _cpActiveId = active ? active.id : null;
  pop.innerHTML = _convictionPopHtml(sym, active);
  _positionConvictionPop(pop, anchorEl);
  _wireConvictionPop(sym);
}

function initConvictionQuickBtn() {
  const body = $('actBody');
  if (!body) return;
  body.addEventListener('click', (e) => {
    const btn = e.target.closest('.lt-quick-btn');
    if (!btn) return;
    openConvictionPop(btn.dataset.sym, btn);
  });
  // Outside click closes the popover (mirrors modalBackdrop's dismiss pattern).
  document.addEventListener('click', (e) => {
    if (!_cpSym) return;
    const pop = $('convictionPop');
    if (pop && (pop.contains(e.target) || e.target.closest('.lt-quick-btn'))) return;
    closeConvictionPop();
  });
}

// ---- TradingView tape toggle --------------------------------------------------
const _TV_LS_KEY = 'act_tv_tape';

// Regular session (Mon–Fri 9:30–16:00 ET): cash index symbols
const _TV_SYMS_REGULAR = [
  {proName:'FOREXCOM:SPXUSD',  title:'S&P 500'},
  {proName:'FOREXCOM:NSXUSD',  title:'Nasdaq 100'},
  {proName:'FOREXCOM:DJI',     title:'Dow Jones'},
  {proName:'FOREXCOM:US2000',  title:'Russell 2K'},
  {proName:'CAPITALCOM:VIX',   title:'VIX'},
  {proName:'CAPITALCOM:DXY',   title:'Dollar'},
  {proName:'TVC:GOLD',         title:'Gold'},
  {proName:'TVC:SILVER',       title:'Silver'},
  {proName:'TVC:USOIL',        title:'WTI Crude'},
  {proName:'TVC:UKOIL',        title:'Brent'},
  {proName:'CAPITALCOM:NATURALGAS', title:'Nat Gas'},
  {proName:'BITSTAMP:BTCUSD',  title:'Bitcoin'},
  {proName:'FX:EURUSD',        title:'EUR/USD'},
  {proName:'FX:USDJPY',        title:'USD/JPY'},
  {proName:'FX:GBPUSD',        title:'GBP/USD'},
];

// Futures session: FOREXCOM/OANDA CFD equivalents — these track the futures
// overnight and work in the free TradingView embed (CME contracts require a
// paid CME data subscription and show "No Data" in free embeds).
const _TV_SYMS_FUTURES = [
  {proName:'FOREXCOM:SPXUSD',  title:'S&P Fut'},
  {proName:'FOREXCOM:NSXUSD',  title:'Nasdaq Fut'},
  {proName:'FOREXCOM:DJI',     title:'Dow Fut'},
  {proName:'FOREXCOM:US2000',  title:'Russell Fut'},
  {proName:'CAPITALCOM:VIX',   title:'VIX'},
  {proName:'CAPITALCOM:DXY',   title:'Dollar'},
  {proName:'TVC:GOLD',         title:'Gold'},
  {proName:'TVC:SILVER',       title:'Silver'},
  {proName:'TVC:USOIL',        title:'WTI Crude'},
  {proName:'TVC:UKOIL',        title:'Brent'},
  {proName:'CAPITALCOM:NATURALGAS', title:'Nat Gas'},
  {proName:'BITSTAMP:BTCUSD',  title:'Bitcoin'},
  {proName:'FX:EURUSD',        title:'EUR/USD'},
  {proName:'FX:USDJPY',        title:'USD/JPY'},
  {proName:'FX:GBPUSD',        title:'GBP/USD'},
];

// Returns 'regular' | 'futures' | 'none'
// Regular:  Mon–Fri 09:30–16:00 ET
// Futures:  Sun 18:00 ET through Fri 17:00 ET, outside regular hours
//           (US equity futures run Sun 18:00 – Fri 17:00 ET with daily ~5–5:15 PM break)
// None:     Fri 17:00 ET – Sun 18:00 ET (weekend, futures closed)
function _tvMode() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date());
  const get = t => (parts.find(p => p.type === t) || {}).value || '';
  const day  = get('weekday');
  const mins = parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10);

  if (day === 'Sat') return 'none';
  if (day === 'Sun' && mins < 1080) return 'none';   // before 18:00 ET Sunday
  if (day === 'Fri' && mins >= 1020) return 'none';  // Fri 17:00 ET and later
  // Regular trading window
  if (['Mon','Tue','Wed','Thu','Fri'].includes(day) && mins >= 570 && mins < 960) return 'regular';
  return 'futures';
}

function _buildTvWidget(symbols) {
  const wrapper = $('tv-tape-wrapper');
  if (!wrapper) return;
  wrapper.innerHTML = '';
  const container = document.createElement('div');
  container.className = 'tradingview-widget-container';
  const wd = document.createElement('div');
  wd.className = 'tradingview-widget-container__widget';
  container.appendChild(wd);
  const sc = document.createElement('script');
  sc.type = 'text/javascript';
  sc.src = 'https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js';
  sc.async = true;
  sc.textContent = JSON.stringify({
    symbols, showSymbolLogo: false, isTransparent: false,
    displayMode: 'adaptive', colorTheme: 'light', locale: 'en',
  });
  container.appendChild(sc);
  wrapper.appendChild(container);
}

function _setTvTape(visible) {
  const wrapper = $('tv-tape-wrapper');
  if (wrapper) wrapper.style.display = visible ? '' : 'none';
  const btn = $('tvToggleBtn');
  if (btn) {
    btn.title = visible ? 'Hide TradingView tape' : 'Show TradingView tape';
    btn.classList.toggle('active', visible);
    btn.disabled = false;
  }
  try { localStorage.setItem(_TV_LS_KEY, visible ? '1' : '0'); } catch (_) {}
}

function _initTvToggle() {
  const mode = _tvMode();
  const btn = $('tvToggleBtn');

  if (mode === 'none') {
    // Futures closed — hide tape, disable button
    const wrapper = $('tv-tape-wrapper');
    if (wrapper) wrapper.style.display = 'none';
    if (btn) {
      btn.innerHTML = 'TV &#9660;';
      btn.title = 'TradingView tape (market closed)';
      btn.disabled = true;
      btn.classList.remove('active');
    }
    return;
  }

  // Load the correct symbol set for the current session
  _buildTvWidget(mode === 'regular' ? _TV_SYMS_REGULAR : _TV_SYMS_FUTURES);

  // Visibility: respect user's localStorage preference, default to visible
  let show = true;
  try {
    const stored = localStorage.getItem(_TV_LS_KEY);
    if (stored !== null) show = stored === '1';
  } catch (_) {}
  _setTvTape(show);

  if (btn) btn.addEventListener('click', () => {
    const wrapper = $('tv-tape-wrapper');
    _setTvTape(!wrapper || wrapper.style.display === 'none');
  });
}

// ---- wire up ----
document.addEventListener('DOMContentLoaded', async () => {
  // initSorting must run before loadDates/renderGrid so th.dataset.label is
  // captured from the clean header text (before sort indicators are injected).
  initSorting();
  initGridSymClick();
  initConvictionQuickBtn();
  initEcoBarClick();
  _initColMenu();
  _initMultiSymPop();
  _initLegendPopover();
  applyColumnVisibility();
  document.addEventListener('click', () => _closeClickPops());
  // ── Global keyboard handling: Esc layering (atomic popover → modal →
  // focus card → click-popovers) + focus-mode rapid-triage keys (U8). A
  // single delegated listener — no per-open/close attach/detach.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      _closeClickPops();
      const atomicPop = $('atomicPopover');
      const modalBackdrop = $('modalBackdrop');
      const focusBackdrop = $('focusBackdrop');
      // Topmost layer only: atomic popover → modal → focus card.
      if (atomicPop && atomicPop.classList.contains('open')) {
        closeAtomicPopover();
      } else if (modalBackdrop && modalBackdrop.classList.contains('open')) {
        _closeModal();
      } else if (focusBackdrop && focusBackdrop.classList.contains('open')) {
        focusBackdrop.classList.remove('open');
      }
      return;
    }

    // Focus-mode rapid-triage keys — active only while the focus card is
    // open, and ignored while typing in a filter/input field.
    const focusBackdrop = $('focusBackdrop');
    if (!focusBackdrop || !focusBackdrop.classList.contains('open')) return;
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

    if (e.key === 'Enter' || e.key === 'd' || e.key === 'D') {
      e.preventDefault();
      focusAdvance('DONE');
    } else if (e.key === 's' || e.key === 'S') {
      e.preventDefault();
      focusAdvance('SKIPPED');
    } else if (e.key === 'z' || e.key === 'Z') {
      e.preventDefault();
      focusAdvance('SNOOZED');
    } else if (e.key === 'ArrowRight' || e.key === 'n' || e.key === 'N') {
      e.preventDefault();
      focusAdvance(null);
    } else if (e.key === 'ArrowLeft' || e.key === 'p' || e.key === 'P') {
      e.preventDefault();
      focusPrev();
    }
  });
  const emptyStateEl = $('emptyState');
  if (emptyStateEl) emptyStateEl.addEventListener('click', (e) => {
    if (e.target.closest('#emptyClearFiltersBtn')) clearAllFilters();
  });

  // TASK_124: Trade Mode always starts ON on entering the screen — not
  // persisted across visits (the user explicitly wants it re-armed every
  // time, not remembered from a prior session). 2026-08-28: Strict is no
  // longer a separate sub-toggle (state.filters.trade_mode_strict retired)
  // -- Trade Mode's own gate is always the strict one now; trade_mode_diff
  // (the "Non-Strict" button) is its mutually-exclusive alternate view,
  // off by default same re-armed-every-visit convention.
  state.filters.trade_mode = true;
  state.filters.trade_mode_diff = false;

  await loadSources();
  await loadDates();
  checkFreshness();
  checkForNewData();
  setInterval(checkForNewData, 30000);

  // Sync UI to restored state
  syncFilterUi();

  // 2026-08-30 -- ?symbol=XYZ deep link (web/universe.js's drilldown jumps
  // here after a symbol tile click: `/actionable?symbol=XYZ`). Same lookup
  // path the manual #symbolSearch input already uses, just applied once on
  // load instead of on keystroke -- takes precedence over restored/
  // persisted filter state, which is why it runs after syncFilterUi().
  const _deepLinkSymbol = new URLSearchParams(window.location.search).get('symbol');
  if (_deepLinkSymbol) {
    const symEl = $('symbolSearch');
    if (symEl) symEl.value = _deepLinkSymbol;
    state.filters.symbol_search = _deepLinkSymbol;
    _resetToggleFiltersForLookup();
    loadActionable();
  }

  $('datePicker').addEventListener('change', (e) => {
    state.date = e.target.value;
    loadActionable();
    checkFreshness();
    checkEodFeed();
  });
  $('refreshBtn').addEventListener('click', () => {
    loadActionable();
    checkFreshness();
    checkEodFeed();
  });
  $('staleRederiveBtn').addEventListener('click', rederiveStale);
  $('exportCsvBtn').addEventListener('click', exportCsv);
  $('emailTradeModeBtn').addEventListener('click', emailTradeMode);
  $('copySymbolsBtn').addEventListener('click', copySymbols);
  initSourcePopover();
  // Row-check (bulk-select) — the per-row inline Act/Skip/Snooze buttons
  // (ACT column) were removed 2026-08-15: user "don't need it, I can use
  // the checkbox [+ bulk action buttons] for now." inlineAction() itself is
  // kept — Focus Mode (focusAdvance) still calls it.
  $('actBody').addEventListener('click', (e) => {
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
  $('fcPrevBtn').addEventListener('click', focusPrev);
  $('fcCloseBtn').addEventListener('click', () => $('focusBackdrop').classList.remove('open'));

  // ── Filter zone wire-ups ────────────────────────────────────────────────────
  $('sourceFilter').addEventListener('change', (e) => {
    state.filters.source = e.target.value;
    _syncTriggerSourcePills();
    if (state.filters.source) { _resetToggleFiltersForLookup(); loadActionable(); return; }
    applyClientFilter();
  });
  const triggerSourcePillsEl = $('triggerSourcePills');
  if (triggerSourcePillsEl) {
    triggerSourcePillsEl.addEventListener('click', (e) => {
      const flagEl = e.target.closest('[data-flag-pill]');
      if (flagEl) {
        // EC/IC: purely client-side, no server round-trip -- the
        // etfchg_date/iichg_date lookback flag is already in every loaded row.
        const key = flagEl.dataset.flagPill;
        state.filters[key] = !state.filters[key];
        _syncTriggerSourcePills();
        applyClientFilter();
        return;
      }
      const el = e.target.closest('[data-src-pill]');
      if (!el) return;
      const src = el.dataset.srcPill;
      state.filters.source = (state.filters.source === src) ? '' : src;
      _syncTriggerSourcePills();
      const selEl = $('sourceFilter');
      if (selEl) selEl.value = state.filters.source;
      if (state.filters.source) { _resetToggleFiltersForLookup(); loadActionable(); return; }
      applyClientFilter();
    });
  }
  $('accountFilter').addEventListener('change', (e) => {
    state.filters.account = e.target.value;
    if (state.filters.account) { _resetToggleFiltersForLookup(); loadActionable(); return; }
    applyClientFilter();
  });
  $('heldOnly').addEventListener('click', () => {
    state.filters.held_only = !state.filters.held_only;
    $('heldOnly').classList.toggle('active', state.filters.held_only);
    $('heldOnly').setAttribute('data-tip', state.filters.held_only ? 'Positions Only  →  Show All' : 'All Symbols  →  Positions Only');
    applyClientFilter();
  });
  $('showHidden').addEventListener('click', () => {
    state.filters.show_hidden = !state.filters.show_hidden;
    $('showHidden').classList.toggle('active', state.filters.show_hidden);
    $('showHidden').setAttribute('data-tip', state.filters.show_hidden ? 'Show Hidden  →  Active Only' : 'Active Only  →  Show Hidden');
    // H column (U4) only renders when show_hidden is on.
    applyColumnVisibility();
    // show_hidden also controls whether acted/suppressed rows are fetched from the API
    loadActionable();
  });
  // TASK_124: Trade Mode toggle — always starts ON (see above); not persisted,
  // so toggling off only lasts for the current page session. 2026-08-28:
  // mutually exclusive with the "Non-Strict" button (trade_mode_diff) below
  // — turning Trade Mode on forces trade_mode_diff off.
  const tradeModeBtn = $('tradeModeBtn');
  if (tradeModeBtn) {
    tradeModeBtn.addEventListener('click', () => {
      state.filters.trade_mode = !state.filters.trade_mode;
      if (state.filters.trade_mode) state.filters.trade_mode_diff = false;
      tradeModeBtn.classList.toggle('active', state.filters.trade_mode);
      const diffBtn = $('tradeModeDiffBtn');
      if (diffBtn) diffBtn.classList.toggle('active', state.filters.trade_mode_diff);
      // Trade Mode also controls whether suppressed rows (e.g. STOP BREACHED)
      // are fetched from the API — needs a full reload, not just a re-filter.
      loadActionable();
    });
  }
  // 2026-08-28: "Non-Strict" button -- current Trade Mode stocks WITHOUT the
  // ones Strict also keeps (was the old Strict sub-toggle's DOM slot; Strict
  // itself is no longer optional, see _isTradeModeQualifyingBuy). Mutually
  // exclusive with Trade Mode -- an alternate view, not a refinement of it
  // — so this needs the same full reload Trade Mode's own toggle does (same
  // show_suppressed fetch-param dependency), not just a re-filter.
  const tradeModeDiffBtn = $('tradeModeDiffBtn');
  if (tradeModeDiffBtn) {
    tradeModeDiffBtn.addEventListener('click', () => {
      state.filters.trade_mode_diff = !state.filters.trade_mode_diff;
      if (state.filters.trade_mode_diff) state.filters.trade_mode = false;
      tradeModeDiffBtn.classList.toggle('active', state.filters.trade_mode_diff);
      tradeModeBtn.classList.toggle('active', state.filters.trade_mode);
      loadActionable();
    });
  }
  // Debounced ~150ms trailing: typing a symbol shouldn't re-render the full grid + tape on every keystroke.
  let _symbolSearchTimer = null;
  $('symbolSearch').addEventListener('input', (e) => {
    const val = e.target.value;
    clearTimeout(_symbolSearchTimer);
    _symbolSearchTimer = setTimeout(() => {
      state.filters.symbol_search = val;
      if (val) { _resetToggleFiltersForLookup(); loadActionable(); return; }
      applyClientFilter();
    }, 150);
  });

  // TASK_66: Bull Prob minimum filter
  const bullProbFilterEl = $('bullProbFilter');
  if (bullProbFilterEl) {
    bullProbFilterEl.addEventListener('input', (e) => {
      state.filters.bull_prob_min = parseFloat(e.target.value) || 0;
      if (state.filters.bull_prob_min > 0) { _resetToggleFiltersForLookup(); loadActionable(); return; }
      applyClientFilter();
    });
  }

  // TASK_69: Agreement class filter
  const agreementFilterEl = $('agreementFilter');
  if (agreementFilterEl) {
    agreementFilterEl.addEventListener('change', (e) => {
      state.filters.agreement_class = e.target.value || '';
      applyClientFilter();
    });
  }

  // 2026-08-31 -- Sector/Asset class/Style dropdowns (all values, not just
  // held) -- same change-listener pattern as Agree above.
  const sectorFilterEl = $('sectorFilter');
  if (sectorFilterEl) {
    sectorFilterEl.addEventListener('change', (e) => {
      state.filters.sector = e.target.value || '';
      applyClientFilter();
    });
  }
  const assetClassFilterEl = $('assetClassFilter');
  if (assetClassFilterEl) {
    assetClassFilterEl.addEventListener('change', (e) => {
      state.filters.asset_class = e.target.value || '';
      applyClientFilter();
    });
  }
  const styleFilterEl = $('styleFilter');
  if (styleFilterEl) {
    styleFilterEl.addEventListener('change', (e) => {
      state.filters.style = e.target.value || '';
      applyClientFilter();
    });
  }

  // RR (Risk Range %) dual-thumb slider — thumb-crossing prevention mirrors
  // Universe's wireRrSlider() (web/universe.js).
  const actRrMinEl = $('actRrMin'), actRrMaxEl = $('actRrMax');
  if (actRrMinEl && actRrMaxEl) {
    const updateRr = () => {
      let lo = parseInt(actRrMinEl.value, 10), hi = parseInt(actRrMaxEl.value, 10);
      if (lo > hi) {
        if (document.activeElement === actRrMaxEl) { lo = hi; actRrMinEl.value = String(lo); }
        else { hi = lo; actRrMaxEl.value = String(hi); }
      }
      state.filters.rr_min = lo; state.filters.rr_max = hi;
      _syncRrSliderUi();
      applyClientFilter();
    };
    actRrMinEl.addEventListener('input', updateRr);
    actRrMaxEl.addEventListener('input', updateRr);
  }

  // Conviction segmented control
  $('convictionCtrl').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-conv]');
    if (!btn) return;
    state.filters.conviction = btn.dataset.conv;
    document.querySelectorAll('#convictionCtrl button').forEach(b =>
      b.classList.toggle('seg-active', b === btn));
    applyClientFilter();
  });

  // Actionable-only toggle
  $('actionableOnlyBtn').addEventListener('click', () => {
    state.filters.actionable_only = !state.filters.actionable_only;
    syncFilterUi();
    applyClientFilter();
  });

  // TradingView tape toggle
  _initTvToggle();

  // Clear all filters
  $('clearFiltersBtn').addEventListener('click', clearAllFilters);

  // More filters panel (Conv / P(↑20d) / Agree) — collapsed by default,
  // toggle state persisted in localStorage.
  const moreFiltersBtn = $('moreFiltersBtn');
  const moreFiltersPanel = $('moreFiltersPanel');
  if (moreFiltersBtn && moreFiltersPanel) {
    const _MORE_FILTERS_KEY = 'actMoreFiltersOpen';
    const _setMoreFiltersOpen = (open) => {
      moreFiltersPanel.style.display = open ? 'flex' : 'none';
      moreFiltersBtn.classList.toggle('active', open);
      moreFiltersBtn.textContent = open ? 'More ▴' : 'More ▾';
    };
    _setMoreFiltersOpen(localStorage.getItem(_MORE_FILTERS_KEY) === '1');
    moreFiltersBtn.addEventListener('click', () => {
      const open = moreFiltersPanel.style.display === 'none';
      _setMoreFiltersOpen(open);
      try { localStorage.setItem(_MORE_FILTERS_KEY, open ? '1' : '0'); } catch (_) {}
    });
  }

const _closeModal = () => {
    $('modalBackdrop').classList.remove('open');
    const tc = $('modalTvChart'); if (tc) tc.innerHTML = '';
  };
  $('modalClose').addEventListener('click', _closeModal);
  $('modalBackdrop').addEventListener('click', (e) => {
    if (e.target === $('modalBackdrop')) _closeModal();
  });
  $('saveActionBtn').addEventListener('click', saveUserAction);
  $('dismissActionBtn').addEventListener('click', dismissUserAction);
  $('convictionAddBtn').addEventListener('click', addConvictionHold);
  $('convictionCloseBtn').addEventListener('click', closeConvictionHold);
  $('convictionDeleteBtn').addEventListener('click', deleteConvictionHold);
  $('closePop').addEventListener('click', () => closeAtomicPopover());

  // Side panel toggle REMOVED (2026-09-01, user request: "remove the side
  // panel from actionable screen altogether") -- #actSidePanel/#sidePanelBtn
  // no longer exist.

  // ── Action column hover popup ──────────────────────────────────────────────
  setupActionCol();
  // ── TrTnBBRskRng column: lazy-load action + hover tooltip ─────────────────
  setupRRActionCol();
});

// ── Action-cell hover popup ────────────────────────────────────────────────
// Builds a glance-level "why" popup from fields already on the row.
// Reuses the same fixed-position tooltip pattern as the TrTnBBRskRng popup.

function _actionPopHtml(sym) {
  const r = state.rows.find(row => row.tos_symbol === sym);
  if (!r) return '';

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
  const _hIc = actionIcon(_badgeAction(r));
  const _hPrice = r.last_price != null ? fmtUsd(r.last_price) : '';
  let html = `<div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;display:flex;align-items:baseline;gap:6px;">` +
    `<span>${escapeHtml(sym)}</span>` +
    `<span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}">${escapeHtml(actionLabel(r))}</span>` +
    `<span style="font-size:10px;font-weight:400;color:#475569;">${escapeHtml(_hIc.label)}</span>` +
    (_hPrice ? `<span style="margin-left:auto;font-size:12px;font-weight:700;color:#0f172a;">${escapeHtml(_hPrice)}</span>` : '') +
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
      const ic      = actionIcon(srcAct);
      const actText = actionText(actionDisplay(srcAct)) || srcAct;
      const dt      = fmtMD(s.snapshot_date) || '—';
      const rsn     = s.reason || '';
      html += `<div style="display:flex;align-items:baseline;gap:5px;margin-bottom:3px;font-size:10px;">` +
        `<span style="min-width:10px;color:#16a34a;font-weight:700;">${isWin ? '✓' : ''}</span>` +
        `<span style="min-width:32px;color:#475569;font-weight:600;">${escapeHtml(srcCode)}</span>` +
        `<span style="font-family:ui-monospace,monospace;font-size:12px;font-weight:700;color:${ic.color};min-width:14px;text-align:center;" title="${escapeHtml(ic.title)}">${ic.glyph}</span>` +
        `<span style="min-width:46px;color:#0f172a;font-weight:600;">${escapeHtml(actText)}</span>` +
        `<span style="min-width:30px;color:#94a3b8;">${escapeHtml(dt)}</span>` +
        `<span style="color:#475569;white-space:normal;line-height:1.3;">${escapeHtml(rsn)}</span>` +
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

  // 2026-08-20: was .act-main-ic (the big final-outcome glyph, removed from
  // the Sources cell) -- reattached to the 'D' (drove-it) pill instead,
  // same detail popup (_actionPopHtml) on the same hover mechanism.
  body.addEventListener('mouseover', (e) => {
    const ic = e.target.closest('.drove-it-pill');
    if (!ic) return;
    const cell = ic.closest('.act-action-cell');
    if (!cell) return;
    const sym = cell.dataset.sym;
    if (!sym) return;
    tip.innerHTML = _actionPopHtml(sym);
    const rect = ic.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.right + 8;
    if (left + tipW > window.innerWidth - 4) left = rect.left - tipW - 8;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('.drove-it-pill')) return;
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
    const ic = e.target.closest('.rr-main-ic');
    if (!ic) return;
    const cell = ic.closest('.rr-action-cell');
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
      ? `<span style="margin-left:auto;font-size:12px;font-weight:700;color:#0f172a;">${fmtUsd(lastPrice)}</span>`
      : '';
    const _rrHDisp = actionDisplay(d.action || rowData?.rr_action || '');
    const _rrHCode = actionText(_rrHDisp);
    const _rrHDesc = _rrHDisp.label || '';

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
    const shortDesc = (short, desc) => {
      const sHtml = short ? `<span style="font-weight:700;">${escapeHtml(short)}</span>` : '';
      const dPart = (desc && desc !== short) ? escapeHtml(desc) : '';
      return [sHtml, dPart].filter(Boolean).join(': ') || escapeHtml(desc) || '—';
    };

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
      <div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;display:flex;align-items:baseline;gap:6px;">
        <span>${escapeHtml(sym)}</span>
        ${_rrHCode && _rrHCode !== '--' ? `<span class="act-badge ${(_rrHDisp.colorCls || 'act-neutral') + '-tint'}">${escapeHtml(_rrHCode)}</span>` : ''}
        ${_rrHDesc ? `<span style="font-size:10px;font-weight:400;color:#475569;">${escapeHtml(_rrHDesc)}</span>` : ''}
        ${priceHtml}
      </div>
      ${rowScore('Trend/Trade',    d.trend_trade, shortDesc(null, rowData?.tn_td_desc || d.tn_td_desc))}
      ${rowScore('BB Range Streak', d.bb_streak,  shortDesc(null, rowData?.bb_desc   || d.bb_desc))}
      ${(()=>{ const _z=rowData?.rr_bull_bear?(rowData.rr_bull_bear==='B'?'Bull Up':'Bull Side Ways'):''; const _zc=rowData?.rr_bull_bear==='B'?'#16a34a':'#f59e0b'; return rowScore(`RR${_z?` <span style="font-size:8px;font-weight:400;text-transform:none;color:${_zc};">${_z}</span>`:''}`,d.rr_action,shortDesc(null,d.rr_desc)); })()}
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

    const rect = ic.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.left - tipW - 8;
    if (left < 4) left = rect.right + 8;
    tip.style.left = left + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('.rr-main-ic')) return;
    tip.style.display = 'none';
  });
}
