/* Actionable popup builders (action popup, notes/symbol popup and their helpers).
 * Moved verbatim out of web/actionable.js (2026-10-17) so the popups can be reused; behaviour unchanged.
 * Classic script: loaded BEFORE actionable.js, shares its global scope. Reads the grid `state` at call time only. */
const $ = (id) => document.getElementById(id);

// Sign always goes before the $ ("-$188", never "$-188") -- same fix as
// universe.js's fmtUsd (2026-09-05); both branches here kept whatever sign
// Math.round(n)/n.toFixed(0) produced glued onto "$" instead of moving it
// in front.
function fmtUsd(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n)) return '';
  const abs = Math.abs(n);
  const s = abs >= 1000 ? Math.round(abs).toLocaleString() : abs.toFixed(0);
  return (n < 0 ? '-$' : '$') + s;
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

// Tiny % readout flanking the %CHG candle bar (2026-09-02, user request):
// day High's % distance from the current price above the bar, Low's %
// distance below it -- just the number, e.g. "4%" / "-2%" -- so you can
// see how far price has pulled back from today's range without a
// separate hover. No "+" prefix on a positive move (user: "you don't
// need signs") -- negative still reads as negative via its own minus.
// Returns {hi, lo} (each a small <div>, or '' if that side has no data)
// so the caller can place them above/below the candle.
// 2026-09-02, user: "make font crisper? don't increase the font size" --
// at 7px, default-weight light grey (#94a3b8) text anti-aliases into a
// soft blur. First try was font-weight 600 + AA hinting; user's follow-up
// ("may be thin but more black?") swapped that for a darker color
// instead of a heavier weight -- stays thin (weight back to normal),
// #334155 (dark slate, near-black) instead of #94a3b8 for more contrast
// against the anti-aliasing. -webkit-font-smoothing:antialiased (+ the
// -moz equivalent) still applies -- the browser's thinner, sharper AA
// hinting instead of the default subpixel/heavier one. Same font-size
// throughout both call sites (hi/lo % above/below the candle bar, and the
// $ high-low range) -- bumped 7px->8px 2026-09-02 per user request; the
// rendering-quality smoothing below is otherwise unchanged.
const _CHG_TINY_STYLE = 'font-size:8px;color:#334155;line-height:1.2;white-space:nowrap;'

function _hiLoParts(high, low, last) {
  if (last == null || !last) return { hi: '', lo: '' };
  const line = val => {
    if (val == null) return '';
    const pct = Math.round((val - last) / last * 100);
    return `<div style="${_CHG_TINY_STYLE}">${pct}%</div>`;
  };
  return { hi: line(high), lo: line(low) };
}

// The actual $ High-Low range, "$180 - $183" (2026-09-02, user: "move the
// range to below the current price") -- shown once, under the price line
// in the %CHG cell's price/chip column, rather than repeated on both
// sides of the candle (that's now just the bare % distances, see
// _hiLoParts above).
function _hiLoRangeHtml(high, low) {
  if (high == null || low == null) return '';
  // margin-top re-tuned 2026-09-02 to the Symbol column's tradability
  // badge (user: "price range center with tradability number text
  // center"), then again for the _CHG_TINY_STYLE font-size bump 7px->8px
  // -- see the call site's own comment for the full history.
  return `<div style="${_CHG_TINY_STYLE}margin-top:4.01px;">${fmtUsd(low)} - ${fmtUsd(high)}</div>`;
}

// Full %CHG widget (candle + hi/lo% + chip + price + range), exactly as
// rendered in the grid's %CHG column -- factored out 2026-09-02 (user:
// "take exactly controls like that from %CHG column and display it in
// ...popover") so the Action popup can reuse the identical markup instead
// of a re-derived copy. The per-line margin-top values baked into
// _hiLoRangeHtml/the price div were calibrated against the grid's
// SYMBOL-column badges (chip~name, price~hit-rate, range~tradability) --
// there's no such neighbor in the popover, so here the whole block just
// centers as one self-contained unit; the internal sub-pixel calibration
// is harmless (still <1px) even though its original target doesn't apply.
// `gap` (candle column <-> price/chip column): both call sites now pass
// it explicitly rather than relying on the default (kept at the original
// 9px as a fallback) -- parameterized 2026-09-02 so each context can be
// tuned independently. Grid: 9 -> 4.5 -> 3 -> 0.125 -> 0. Popover: 9 ->
// 4.5 -> 2.25 -> 1.125 -> 0. Both landed at 0 together (user: "make it
// to 0px here and also in the popover window").
function _chgCandleControlsHtml(row, gap, showPrice) {
  const pctChipHtml = _pctChgChipHtml(row.pct_change);
  const priceStr = (showPrice !== false && row.last_price != null) ? _fmtUsd2(row.last_price) : '';   // popover passes false: its header already shows the big price;   // 2026-10-03: two decimals (also the grid %CHG cell)
  const hiLo = _hiLoParts(row.high_price, row.low_price, row.last_price);
  const candleHtml = window.mtTip?.candleSvg(row.open_price, row.high_price, row.low_price, row.last_price, 28) || '';
  return `<div class="chg-candle-row" style="display:flex;align-items:center;justify-content:center;gap:${gap != null ? gap : 9}px;">
    <div style="display:flex;flex-direction:column;align-items:center;gap:1px;width:22px;flex:0 0 auto;">
      ${hiLo.hi}
      ${candleHtml}
      ${hiLo.lo}
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;width:60px;flex:0 0 auto;margin-top:0.68px;">
      ${pctChipHtml}
      ${priceStr ? `<div style="font-size:10px;color:#94a3b8;margin-top:2.29px;">${priceStr}</div>` : ''}
      ${_hiLoRangeHtml(row.high_price, row.low_price)}
    </div>
  </div>`;
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

// Symbol-name color (grid Symbol column + Action popover): green / red / grey from rr_outlook.
function _symOutlookColor(row) {
  // 2026-10-03 (user): three colors only, from the outlook (never the day's %change):
  // any bullish shade = green, any bearish shade = red, neutral / no outlook = grey.
  // Green and red are the same two the symbol column already used (BM / SA palette).
  const o = ((row && row.rr_outlook) || '').toString().toLowerCase();
  if (o.indexOf('bull') !== -1) return '#1d9e75';
  if (o.indexOf('bear') !== -1) return '#d4537e';
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

let _srcPopEl = null;

// Action severity rank — REMOVE strongest. Mirrors the consolidation sort.
const ACTION_RANK = { REMOVE: 4, REDUCE: 3, INCREASE: 2, ADD: 1, HOLD: 0 };

// actionDisplay() is provided by actions.js (loaded before this script).
// actionLabel: plain-English label for a row's consolidated_action.
function actionLabel(row) {
  const a = ((row && row.consolidated_action) || 'NONE').toUpperCase();
  return actionText(actionDisplay(a));
}

// True when the row's held position exceeds the category Max. 2026-09-03:
// no longer overrides the ACTION badge/AMT$/chip bucket (user: "Sell
// Overage ... should not drive the main action" — it's now a purely
// informational OVER MAX pill, see _finalCallHtml). REMOVE rows are
// excluded — sell-all already covers the position, over-max is moot.
// TASK_151: compact $ for per-account sizes ($17k, $30.9k).
function _fmtK(v) {
  const n = Number(v) || 0;
  if (Math.abs(n) < 1000) return '$' + Math.round(n);
  return '$' + (Math.round(n / 100) / 10).toString().replace(/\.0$/, '') + 'k';
}

// Accounts whose held $ is above their own rounded max.
function _acctOver(row) {
  return ((row && row.account_sizes) || []).filter(a => a.over);
}

// Pill label: "IRA over max ($30.9k / $17k)"; several accounts -> names only.
function _acctOverMaxText(row) {
  const o = _acctOver(row);
  if (!o.length) return null;
  if (o.length === 1) return `${o[0].name} over max (${_fmtK(o[0].held)} / ${_fmtK(o[0].max)})`;
  return o.map(a => a.name).join(', ') + ' over max';
}

function _overMaxLabel(row) {
  return _acctOverMaxText(row) || 'OVER MAX';
}

function _isOverMaxOverlay(row) {
  if (!row) return false;
  if ((row.consolidated_action || '').toUpperCase() === 'REMOVE') return false;
  // TASK_151: per-account sizes (drv_account_size) decide when present; the
  // household check below is only the fallback for rows without them.
  if (row.account_sizes && row.account_sizes.length) return _acctOver(row).length > 0;
  const pos = Number(row.current_position_dollar);
  const max = Number(row.target_max_dollar);
  return isFinite(pos) && isFinite(max) && max > 0 && pos > max;
}

// `>=` sibling of _isOverMaxOverlay (which stays strict `>`, "over" meaning
// past the ceiling, not merely at it). 2026-09-12: no longer a gate (the
// at/over-Max -> HOLD cap was removed) — used only to suppress the
// ESTABLISHED/NEAR MAX pill in favor of OVER MAX once a position reaches
// its ceiling (_sizingStagePill below), matching sizing's own AT CEILING
// suppression threshold.
function _isAtOrOverMax(row) {
  if (!row) return false;
  if ((row.consolidated_action || '').toUpperCase() === 'REMOVE') return false;
  const pos = Number(row.current_position_dollar);
  const max = Number(row.target_max_dollar);
  return isFinite(pos) && isFinite(max) && max > 0 && pos >= max;
}

// 2026-09-12: "sizing stage" pill — same precedent as OVER MAX (2026-09-03,
// user: "should not drive the main action ... should be one of the input[s]
// like Sources, Technicals, Macro"). Two SOFT signals, informational only,
// never touching the badge/AMT$/confidence:
//   ESTABLISHED — held >= Min floor already; a standing ADD re-list or a
//     confirming Technical can otherwise badge BM/BS/BMN at High confidence
//     indefinitely even though there's no urgency left to build the floor.
//   NEAR MAX    — held is most of the way from Min to Max (>= 75%); still
//     room to buy, so still a real BM/BS, just flagged as "not much room
//     left" context.
// 2026-09-12: gate 4 (at/over Max -> HOLD) was removed — position size is
// now pill-only everywhere, no exceptions (user: "why can't we just have
// the pill ... amount is going to tell me anyway I shouldn't buy"). At/over
// Max still doesn't get ESTABLISHED/NEAR MAX though — the more specific
// OVER MAX pill (_isOverMaxOverlay, _finalCallHtml) takes over instead.
const _NEAR_MAX_PCT = 0.75;

function _sizingStageInfo(row) {
  if (!row) return null;
  const ca = (row.consolidated_action || '').toUpperCase();
  if (ca !== 'ADD' && ca !== 'INCREASE') return null;
  if (!row.held_today) return null;
  if (_isAtOrOverMax(row)) return null;  // OVER MAX pill covers this instead
  const pos = Number(row.current_position_dollar);
  const min = Number(row.target_min_dollar);
  const max = Number(row.target_max_dollar);
  if (!isFinite(pos)) return null;
  if (isFinite(max) && max > (isFinite(min) ? min : 0)) {
    const floor = isFinite(min) ? min : 0;
    const pct = (pos - floor) / (max - floor);
    if (pct >= _NEAR_MAX_PCT) {
      return { label: 'NEAR MAX', detail: fmtUsd(pos) + ' of ' + fmtUsd(max) + ' Max (' + Math.round(pct * 100) + '% of the way there)' };
    }
  }
  if (isFinite(min) && min > 0 && pos >= min) {
    return { label: 'ESTABLISHED', detail: 'Held ' + fmtUsd(pos) + ' already \u2265 floor ' + fmtUsd(min) };
  }
  return null;
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
// Per-source reason lines for the Sources column: "SRC <icon> reason".
// True when the stop-breach gate (not a source) turned a buy into HOLD.
function _stopGated(r) {
  return !!(r && r.stop_breached && /STOP/i.test(r.suppressed_reason || ''));
}

// One-line plain-English text for the popup's Stop driver line: the signal,
// the actual line price, and what it did to the action.
function _stopDriverNote(r) {
  const lineVal = r.stop_signal === 'TN SA' ? r.trend_line_value : r.trade_line_value;
  const lineLabel = r.stop_signal === 'TN SA' ? 'Trend' : 'Trade';
  const px = lineVal != null ? ', ' + lineLabel + ' line ' + fmtUsd(Number(lineVal)) : '';
  return 'Price broke its stop (' + (r.stop_signal || 'stop') + px + ') — buy blocked, HOLD';
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
  // 2. Strategic exit gate: exit signal. (2026-09-03: over-max no longer
  //    gates here — it's informational only, see the OVER MAX pill.)
  if (srcIsExit) {
    if (!isHeld) return 'Exit signal but not held — no action feasible';
    return 'Sources: exit signal — Technical not evaluated';
  }
  // 3. Don't-initiate guard: not held, Sources doesn't endorse buying.
  if (!isHeld && !srcIsBuy) {
    return 'Not held + Sources don’t endorse buying — hold';
  }
  // (former step 4: at/over-Max cap, removed 2026-09-12 — see finalCall()'s
  // own comment on the same removal for the reasoning.)
  // 5/6. Technical neutral. 2026-09-12, user: an unheld ADD with no
  // Technical support isn't grounds to open a position either — no more
  // standalone "establishing position" case, falls through to the plain
  // no-active-signal reason.
  if (techIsNeutral) {
    if (!isHeld && srcIsAdd) return 'Sources says ADD but Technical hasn’t confirmed — not enough to open a position';
    if (!srcIsReduce) return 'No active signal — Sources and Technical both neutral';
  }
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
  // 2026-09-03: over-max no longer gates the Final Call (mirrors server-side
  // etl/derive_actionable.py::_compute_final_call) — informational only, see
  // the OVER MAX pill in _finalCallHtml. 2026-09-12: the former step-4 cap
  // (at/over Max -> HOLD) was removed too, same reasoning — see
  // etl/derive_actionable.py's comment on the same removal.
  var isHeld     = !!row.held_today;

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

  // ── 1. Feasibility (pre-check): never sell unheld ─────────────────────────
  // Selling an unheld position is infeasible; we'll guard this below per-path.
  // Buying past Max is a policy choice, not infeasible — over-max rows are
  // flagged via the OVER MAX pill (_finalCallHtml) instead, unchanged badge.

  // ── 2. Strategic gate: SELL ALL / REMOVE → exit regardless of Technical ──
  if (srcIsExit) {
    var exitDisp = actionDisplay('SA');
    if (!isHeld) {
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
      strength:   _FC_SCALE['SA'],
      confidence: 'gate',
      gateReason: 'Sources: exit signal — Technical not evaluated',
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
      // TASK_141 Part B: don't assert confidence the evidence hasn't
      // earned — mirrors etl/derive_actionable.py::_compute_final_call.
      // Buy-side confidence is untouched. No-op under default 'annotate'.
      confidence = (row.low_confidence && state.unprovenSellMode === 'suppress')
        ? 'mixed' : 'high';
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
    // Technical is neutral/BMN/HOLD. 2026-09-12, user: an unheld ADD with no
    // Technical support isn't even a weak entry — Technical must actively
    // confirm before a new position opens, so this now falls through to the
    // generic HOLD/gate case below instead of a standalone BMN.
    if (srcIsReduce) {
      // Sources souring, Technical neutral → HOLD (no action but watch)
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      // Mild conflict: Sources wants down, Technical neutral
      confidence = 'mixed';
    } else if (!isHeld && srcIsAdd) {
      // Not held, Sources says ADD, Technical neutral — no confirmation to
      // open a new position on
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'gate';
      gateReason = 'Sources says ADD but Technical hasn’t confirmed — not enough to open a position';
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

// TASK_149 (area driver rules): advisory per-area flags from the server
// (row.driver_flags <- drv_driver_exposure). Only holdings and buy candidates
// get a line; everything else stays silent. Never changes the Final Call.
const _AREA_VERDICT_GLYPH = { headwind: '▼ Headwind', tailwind: '▲ Tailwind',
                              stretched: '⚠ Stretched', turning: '◆ Turning' };

function _areaFlagsFor(row, side) {
  const fl = row.driver_flags;
  if (!fl || !fl.length) return [];
  return (row.held_today || side === 'buy') ? fl : [];
}

function _signalReasons(row, side) {
  const isSell = side === 'sell';
  const warn = [];
  const buy = [];

  // TASK_149: one generic line per flagged area. Buy-oriented framing like
  // everything below (Headwind/Stretched = caution, Tailwind = confirm);
  // the return at the bottom swaps the lists on sell rows.
  for (const f of _areaFlagsFor(row, side)) {
    const g = _AREA_VERDICT_GLYPH[f.verdict];
    if (!g) continue;
    const line = f.label + ' area ' + g + (f.is_new ? ' (new)' : '') +
      (f.inverted ? ' [inverse position]' : '') + (f.message ? ' — ' + f.message : '');
    if (f.verdict === 'headwind' || f.verdict === 'stretched') warn.push(line);
    else if (f.verdict === 'tailwind') buy.push(line);
  }

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

  // 2026-09-22: Risk Dial curve_inverting/3m10y_inverted gauges -- a
  // flattening/inverted yield curve squeezes bank net interest margin
  // (long-end lending rate minus short-end deposit/borrowing rate)
  // directly, on top of its usual role as a recession leading indicator --
  // Financials-only, mirrors ref_gauge_transmission's own curve->Financials
  // linkage (db/seeds_cockpit.sql). state.curveInvertedWarn fetched once in
  // loadSources(). User: "I think financials are most affected."
  if (!isSell && state.curveInvertedWarn && row.sector === 'Financials') {
    warn.push('Yield curve inverting/flattening — bank margins under pressure (Risk Dial)');
  }

  // 2026-10-01: Bear sector + non-investable volatility warnings (buy-side
  // only; swapped to the confirm list on sell rows by the return below).
  // User: "if the corresponding sector is Bear, warn me" and "if Nasdaq
  // volatility is not investable, warn me" -> extended to all vol gauges,
  // Chop or Elevated (option B). Index gauges use ref_sector's sp500/
  // nasdaq/dow/russell flags; Gold/Oil/Bond have no flag, so mapped by
  // asset class / sector.
  if (!isSell) {
    if (row.sector_stance != null && Number(row.sector_stance) < 0 && row.sector && row.sector !== 'N/A') {
      warn.push('Sector ' + row.sector + ' is Bear (stance ' + Number(row.sector_stance).toFixed(2) + ')');
    }
    const vz = state.volZones || {};
    const isFlag = v => String(v || '').trim().toUpperCase() === 'Y';
    const ac = String(row.real_asset_class || '').toLowerCase();
    const sec = String(row.sector || '').toLowerCase();
    const gauges = [];
    if (isFlag(row.idx_sp500))   gauges.push('S&P Vol');
    if (isFlag(row.idx_nasdaq))  gauges.push('Nasdaq Vol');
    if (isFlag(row.idx_dow))     gauges.push('Dow Vol');
    if (isFlag(row.idx_russell)) gauges.push('Russell Vol');
    if (/gold|silver|precious/.test(ac) || /gold|silver|precious/.test(sec)) gauges.push('Gold Vol');
    if (sec === 'energy') gauges.push('Oil Vol');
    if (/fixed income|bond/.test(ac) || sec === 'financials') gauges.push('Bond Vol');
    for (const g of gauges) {
      const z = vz[g];
      if (z && (z.zone === 'chop' || z.zone === 'elevated')) {
        warn.push(g + ' not investable (' + z.zone + (z.last != null ? ', ' + Number(z.last).toFixed(1) : '') + ')');
      }
    }
  }

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

// Minimum score to show the badge. Rescaled a third time 2026-08-15 when
// agreement got its own dedicated weight (see _buyTradabilityScore's
// agreementPts comment) — max grew back up (was ~14, now ~20). Re-checked
// against the same live data (2026-08-14 anchor, low_confidence-excluded
// buy-side rows): new distribution is max 19.90, mean 7.57, median 8.00,
// top-10% >= 14.00. Set to 12 (~top 15-20%, a bit more permissive than a
// strict top-10% cutoff so it's not ONLY the near-LRR-plus-agreement rows
// showing it). Revisit again after a few more weeks of live data.
const _TRADABILITY_BADGE_MIN = 12;

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

// Action popover "Notes" block: the same /api/notes feed the SYMBOL-cell hover shows,
// top 3 inline. Filled after the popover is shown (async) and only if it is still open.
function _actpopNotesHtml(notes) {
  if (!notes || !notes.length) return '';
  let h = '<span class="actpop-notes-h">Notes</span>';
  for (const n of notes.slice(0, 3)) {
    const dt = fmtMD(n.note_date) || '';
    const src = (n.source_type || '').replace(/_/g, ' ');
    const sk = n.signal_kind ? ' ' + String(n.signal_kind).toUpperCase() : '';
    let txt = (n.note_text || '').trim();
    if (txt.length > 160) txt = txt.slice(0, 160).replace(/\s+\S*$/, '') + '\u2026';
    h += `<div class="actpop-note"><b>${escapeHtml(dt)}</b> ${escapeHtml(src)}${escapeHtml(sk)} &mdash; ${escapeHtml(txt)}</div>`;
  }
  return h;
}

async function _actpopLoadNotes(sym) {
  const box = () => document.querySelector('#sourcePop .actpop-notes[data-sym="' + CSS.escape(sym) + '"]');
  let notes;
  if (_notesCache.has(sym)) notes = _notesCache.get(sym);
  else {
    try { notes = await fetchJson('/api/notes?ticker=' + encodeURIComponent(sym) + '&limit=15'); } catch (_) { notes = []; }
    _notesCache.set(sym, notes);
  }
  const el = box();
  if (el) el.innerHTML = _actpopNotesHtml(notes);
}

function hideSourcePop() {
  _srcPopEl = null;
  const pop = $('sourcePop');
  if (pop) pop.style.display = 'none';
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

// Display label shown on the badge -- differs from the DB decision code for
// the "@ LRR" / "WATCH-suffix" tiers per user's requested wording.
const _PVV_LABEL = {
  BUY_LRR: 'BUY@LRR', BUY_WATCH: 'BUYWATCH', SELL_WATCH: 'SELLWATCH',
};

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

// Display-label override for vlm_action (2026-09-02, user: "relabel the
// tags to be less misleading"). "Accumulate"/"Avoid" read as directional
// buy/sell calls, but the rule table behind them is mostly volume-magnitude
// -only with no price-direction check (5 of 10 rule codes test volume shape
// alone, yet 3 of them still carried a directional label -- known
// internal-consistency issue, previously audited and parked per project
// memory as its own, separate fix: RE-CLASSIFYING which rules map to which
// tier). This is a narrower, display-only change on top of that: same
// rule→tier mapping as today, just wording that can't be misread as a
// trade direction. row.vlm_action itself is untouched (still 'Accumulate'/
// 'Watch'/'Avoid' in the DB/API), so every color/class branch that compares
// against those literal values keeps working unchanged -- only the text
// shown to the user goes through this map.
const _VLM_ACTION_LABEL = { Accumulate: 'Heavy', Watch: 'Mixed', Avoid: 'Thin' };

function _vlmActionLabel(va) {
  return _VLM_ACTION_LABEL[va] || va;
}

// VLM (volume projection, 2026-08-20) — same [Label] value pattern as
// Src/Tech, always shown/dashed.
// 2026-08-20 correction: vlm_desc was originally a title= hover tooltip --
// doesn't work inside this popup (#sourcePop is pointer-events:none,
// nothing nested in it can ever get a native hover). Shown as small inline
// text instead.
function _actpopVlmPillHtml(row) {
  const va = row.vlm_action;
  const cls = !va ? 'disabled' : va === 'Accumulate' ? 'buy' : va === 'Avoid' ? 'sell' : '';
  const txt = va ? _vlmActionLabel(va) : '—';
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

// 2026-10-01: "your cost vs the Trade line" context for the Technical
// explanation (informational only -- never changes the signal). User bought
// XLE below its Trade line and asked why Technical still says SELL TO MIN;
// the signal is a trend read, not a P&L read, so this just shows both.
// Technical "why" text carries {r}..{/} (red) / {g}..{/} (green) highlight markers
// (etl/technical_why.py). _whyHtml renders them; _whyPlain strips them for places
// that can't show markup (tooltips, plain-text fallbacks).
function _whyPlain(s) { return String(s == null ? '' : s).replace(/\{(?:r|g|\/)\}/g, ''); }

function _whyHtml(s) {
  return escapeHtml(String(s == null ? '' : s))
    .replace(/\{r\}/g, '<span style="color:#dc2626;font-weight:600;">')
    .replace(/\{g\}/g, '<span style="color:#16a34a;font-weight:600;">')
    .replace(/\{\/\}/g, '</span>');
}

function _techCostNote(row) {
  const q = Number(row.held_qty), c = Number(row.held_cost);
  if (!row.held_today || !(q > 0) || !(c > 0)) return '';
  const avg = c / q;
  const last = Number(row.last_price);
  const trade = Number(row.a_trade_value);
  let s = `You hold ${Math.round(q).toLocaleString()} sh at avg cost ${_fmtUsd2(avg)}`;
  if (last > 0) {
    const pl = (last / avg - 1) * 100;
    s += ` (${pl >= 0 ? '+' : ''}${pl.toFixed(1)}% vs last ${_fmtUsd2(last)})`;
  }
  if (trade > 0) s += `; Trade line ${_fmtUsd2(trade)} is ${trade >= avg ? 'above' : 'below'} your cost`;
  return s + '.';
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
  const bulletFor = (label, actUpper, reason, dt, tag, pctSinceDrop, dropConflict, upStreak3d, tw) => {
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
    // 2026-10-02: Technical shows two label:value pieces -- Why <situation> /
    // Call <action>: <verdict> -- from rr_why's two lines (etl/technical_why.py).
    if (tw) {
      noteHtml = `<div class="actpop-tw"><span class="tw-k">Why</span>${_whyHtml(tw.why)}</div>`
        + `<div class="actpop-tw"><span class="tw-k">Call</span><b>${escapeHtml(actionLabel)}</b>: ${_whyHtml(tw.verdict)}</div>`
        + (tw.cost ? `<div class="actpop-tw tw-cost">${escapeHtml(tw.cost)}</div>` : '');
    }
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
  // 2026-10-01: when the winning source points the opposite way from the
  // Final Call and Technical is what matches it, Technical drove the
  // result -- the source conflicts. (BNO: PS BUY TO MIN, Final SELL SOME.)
  const winSide = winEntry ? actionDisplay((winEntry.action || '').toUpperCase()).side : null;
  const techSideFc = actionDisplay((row.rr_action || '').toUpperCase()).side;
  const techOverrides = !!(winEntry && side && winSide && winSide !== side && techSideFc === side);
  // 2026-10-09: a breached stop turned the buy into HOLD -- the stop drove
  // the result; every source/Technical is tagged agrees/conflicts vs the stop; Technical is
  // judged against the stop (sell side), not against HOLD.
  const stopGate = _stopGated(row);
  if (stopGate) {
    rows.push(`<div class="actpop-driver sell">
      <span class="dv-name">Stop</span>
      <span class="dv-action sell">Breached</span>
      <span class="dv-note">${escapeHtml(_stopDriverNote(row))}</span>
      <span class="dv-tag">drove it</span>
    </div>`);
  }
  if (winEntry) {
    const code = winEntry.source || winEntry.source_code || winning;
    rows.push(bulletFor(code, winEntry.action, winEntry.reason, fmtMD(winEntry.snapshot_date), stopGate ? 'conflicts' : techOverrides ? 'conflicts' : 'drove it',
      winEntry.pct_since_drop, winEntry.drop_conflict, winEntry.up_streak_3d));
  }
  const rraUpper = (row.rr_action || '').toUpperCase();
  if (rraUpper) {
    const techSide = actionDisplay(rraUpper).side;
    const tag = stopGate ? (techSide === 'sell' ? 'agrees' : techSide === 'buy' ? 'conflicts' : '')
                : techOverrides ? 'drove it' : winEntry ? (techSide === side ? 'agrees' : (techSide && side ? 'conflicts' : ''))
                          : 'drove it'; // no source row at all -- Technical is the only driver
    const desc = _whyPlain((row.rr_why || row.rr_desc || row.tn_td_desc || row.bb_desc || '') + ' ' + _techCostNote(row)).trim();  // 2026-10-01: rr_why = plain-English reason + your-cost note
    // rr_why is "why<newline>verdict" once re-derived; older rows are one sentence.
    const _twLines = String(row.rr_why || '').split('\n');
    const tw = _twLines.length >= 2 ? { why: _twLines[0], verdict: _twLines[1], cost: _techCostNote(row) } : null;
    rows.push(bulletFor('Technical', rraUpper, desc, null, tag, undefined, undefined, undefined, tw));
  }
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) => (ACTION_RANK[(b.action || '').toUpperCase()] || 0) - (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  for (const s of others) {
    const code = s.source || s.source_code || '?';
    rows.push(bulletFor(code, s.action, s.reason, fmtMD(s.snapshot_date), stopGate ? (actionDisplay((s.action || '').toUpperCase()).side === 'buy' ? 'conflicts' : actionDisplay((s.action || '').toUpperCase()).side === 'sell' ? 'agrees' : null) : null, s.pct_since_drop, s.drop_conflict, s.up_streak_3d));
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
  // 2026-10-03: HOLD / no-call rows now get the same Caution / Supporting list the grid's
  // warning pill shows (buy-style wording, rules kept as sentences) instead of nothing.
  const neutral = side !== 'buy' && side !== 'sell';
  const sig = _signalReasons(row, side);
  const isRuleText = neutral ? (() => false) : (s => /^Rule \S+ fired|^Sell rule \S+/.test(s));
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

  const rulePills = neutral ? { support: '', oppose: '', supportCount: 0, opposeCount: 0 } : _actpopRulePillsHtml(row, side);

  const oppItems = opposeSignals.map(s => `<div class="actpop-tug-item">${escapeHtml(s)}</div>`).join('');
  // 2026-10-03: a red ▼ (sell) / green ▲ (buy) before each supporting line shows which call it backs.
  const _supIc = neutral ? '' : `<span style="color:${side === 'sell' ? '#b91c1c' : '#15803d'};font-weight:700;margin-right:4px;">${side === 'sell' ? '▼' : '▲'}<span style="font-size:7px;margin-left:1px;">✓</span></span>`;
  const supItems = supportSignals.map(s => `<div class="actpop-tug-item">${_supIc}${escapeHtml(s)}</div>`).join('');
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
    <div class="actpop-tug-col oppose"><div class="actpop-tug-h">${neutral ? 'Caution' : 'Opposing'}</div>${oppBody}</div>
    <div class="actpop-tug-col support"><div class="actpop-tug-h">Supporting${neutral ? '' : (side === 'sell' ? ' the sell' : ' the buy')}</div>${supBody}</div>
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

// 2026-10-02: vertical Trade/Trend/price bar for the popover header. Fixed
// size; three parts (above both lines / between / below both) sized by price
// distance inside it. LRR/TRR lines are drawn only when the Technical reason
// text refers to them. Colors are literal (popover is light-only, like the
// rest of .actpop).
function _actpopLevelBarHtml(row) {
  const num = v => (v == null || v === '') ? null : Number(v);
  const price = num(row.last_price), trade = num(row.trade_line_value), trend = num(row.trend_line_value);
  if (price == null || trade == null || trend == null || !isFinite(price + trade + trend)) return '';
  const why = String(row.rr_why || '');
  const lrr = /LRR/.test(why) ? num(row.lrr) : null;
  const trr = /TRR/.test(why) ? num(row.trr) : null;
  const H = 110, PT = 8, W = 151, bx = 58, bw = 3;
  const hi = Math.max(trade, trend), lo = Math.min(trade, trend);
  const vals = [price, trade, trend].concat(lrr != null ? [lrr] : [], trr != null ? [trr] : []);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const span = (mx - mn) || 1, pad = span * 0.08;
  const top = mx + pad, bot = mn - pad;
  const y = p => PT + (top - p) / (top - bot) * H;
  const yHi = y(hi), yLo = y(lo), yP = y(price);
  const usd = v => '$' + v.toFixed(2);
  const lines = [
    { n: 'Trade', p: trade, c: '#1d6fd6' }, { n: 'Trend', p: trend, c: '#b4640a' },
    ...(trr != null ? [{ n: 'TRR', p: trr, c: '#7a4fc2', dash: 1 }] : []),
    ...(lrr != null ? [{ n: 'LRR', p: lrr, c: '#7a4fc2', dash: 1 }] : []),
  ].map(l => ({ ...l, y: y(l.p) })).sort((a, b) => a.y - b.y);
  lines.forEach((l, i) => { l.ty = i ? Math.max(l.y, lines[i - 1].ty + 12) : l.y; });
  let g = `<svg viewBox="0 0 ${W} ${H + PT * 2 + 6}" width="${W}" height="${H + PT * 2 + 6}" role="img" aria-label="Price vs Trade and Trend lines">`;
  g += `<rect x="${bx}" y="${PT}" width="${bw}" height="${yHi - PT}" fill="#dff1e4"/>`;
  g += `<rect x="${bx}" y="${yHi}" width="${bw}" height="${Math.max(yLo - yHi, 0)}" fill="#eceef2"/>`;
  g += `<rect x="${bx}" y="${yLo}" width="${bw}" height="${PT + H - yLo}" fill="#f8e0e0"/>`;
  g += `<rect x="${bx}" y="${PT}" width="${bw}" height="${H}" fill="none" stroke="#cbd5e1"/>`;
  for (const l of lines) {
    g += `<line x1="${bx - 3}" x2="${bx + bw + 3}" y1="${l.y}" y2="${l.y}" stroke="${l.c}" stroke-width="${l.dash ? 1.3 : 2.2}"${l.dash ? ' stroke-dasharray="4 3"' : ''}/>`;
    g += `<line x1="${bx + bw + 3}" x2="${bx + bw + 8}" y1="${l.y}" y2="${l.ty}" stroke="${l.c}" stroke-width="1"/>`;
    g += `<text x="${bx + bw + 10}" y="${l.ty + 3.5}" font-size="9.5" font-weight="700" fill="${l.c}">${l.n} ${usd(l.p)}</text>`;
  }
  g += `<polygon points="${bx - 2},${yP} ${bx - 9},${yP - 4.5} ${bx - 9},${yP + 4.5}" fill="#0f172a"/>`;
  g += `<text x="${bx - 12}" y="${yP + 4}" font-size="11" font-weight="800" text-anchor="end" fill="#0f172a">${usd(price)}</text>`;
  g += `</svg>`;
  return `<div class="actpop-lvlbar">${g}</div>`;
}

// Two-decimal dollars for the popover header (the file's fmtUsd rounds to whole dollars).
function _fmtUsd2(v) {
  const n = Number(v);
  if (v == null || v === '' || !isFinite(n)) return '';
  return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Wraps a header control group so it centers on the price/shares/earnings lines (see .actpop-ctrl-c).
function _ctrlC(html, extra) { return html ? `<div class="actpop-ctrl-c${extra ? ' ' + extra : ''}">${html}</div>` : ''; }

function _buildActionPopHtmlV2(row) {
  const fc = finalCall(row);
  const sym = row.tos_symbol || '—';
  const side = fc.side;
  const callCls = side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : 'neutral';
  const ed = row.earnings_days;
  const hasEd = ed != null && Number(ed) >= 0 && Number(ed) < 900;
  const edDays = hasEd ? Math.round(Number(ed)) : null;
  // Earnings highlight reuses the same <=3d yellow .opex-soon treatment the
  // dashboard's own earnings lines use (web/app.js::_earningsLineHtml).
  // 2026-10-02 (user): company name on top, full-decimal price (bold/larger),
  // then shares/avg-cost/amount and earnings lines under the action pill.
  // (The old "$9k . 10d" line, .actpop-co, was removed 2026-10-02.)
  const nameTxt = row.company_name ? `<span class="actpop-name" title="${escapeHtml(row.company_name)}">${escapeHtml(row.company_name)}</span>` : '';
  // Suggested trade size next to the pill (same _amt the grid's AMT column shows), only for a
  // real buy/sell call -- for HOLD _amt is just the current holding, not a trade.
  const tradeAmtTxt = ((side === 'buy' || side === 'sell') && Number(row._amt) > 0)
    ? `<span class="actpop-amt" title="Suggested trade size">${side === 'sell' ? 'sell' : 'buy'} ${escapeHtml(_actpopFmtAmt(row._amt).replace('k', 'K'))}</span>` : '';
  const pxTxt = row.last_price != null ? `<div class="actpop-px">${_fmtUsd2(row.last_price)}</div>` : '';
  const hq = Number(row.held_qty), hc = Number(row.held_cost);
  // 2026-10-03 (user): "$17K · Avg $14.20" (avg green below the current price, red above), then
  // one line per account: "F-A: 10K (700 sh) · A: 7K (500 sh)" = shares x current price.
  const _px = Number(row.last_price);
  const _avg = hq > 0 && hc > 0 ? hc / hq : null;
  const _avgColor = (_avg != null && _px > 0) ? (_avg < _px ? '#15803d' : _avg > _px ? '#b91c1c' : '') : '';
  const _acctAmt = v => v >= 1000 ? Math.round(v / 1000) + 'K' : String(Math.round(v));
  const _accts = (Array.isArray(row.held_by_account) ? row.held_by_account : []).filter(a => Number(a.qty) > 0);
  const acctTxt = (_px > 0 && _accts.length)
    ? _accts.map(a => `${escapeHtml(a.name)}: ${_acctAmt(Number(a.qty) * _px)} (${Math.round(Number(a.qty)).toLocaleString()} sh)`).join(' &middot; ')
    : '';
  const ownTxt = row.held_today && hq > 0
    ? [row.current_position_dollar != null ? _actpopFmtAmt(row.current_position_dollar).replace('k', 'K') : '',
       _avg != null ? `Avg <span${_avgColor ? ` style="color:${_avgColor};font-weight:700;"` : ''}>${_fmtUsd2(_avg)}</span>` : '']
      .filter(Boolean).join(' &middot; ')
    : 'Not held';
  const ownLine = `<div class="actpop-own">${ownTxt}</div>`
    + (row.held_today && acctTxt ? `<div class="actpop-own" style="font-size:10px;">${acctTxt}</div>` : '');
  const earnLine = hasEd
    ? `<div class="actpop-earn">Earnings in ${edDays <= 3 ? `<span class="opex-soon">${edDays}d</span>` : `${edDays}d`}</div>`
    : '';
  // Computed here (not at its original later call site) so its conviction
  // piece is ready in time for the header below -- see _actpopTugHtml's own
  // comment for why it now returns {conviction, html} instead of one string.
  const tug = _actpopTugHtml(row, side);

  let h = `<div class="actpop">`;
  // Header: symbol + Final Call badge on the top line (.actpop-sym), held
  // amount/earnings on their own line below it (.actpop-co). To its right,
  // .actpop-ctrl-row -- 4 equally-gapped control groups (2026-09-02, user:
  // "take exactly controls like that from %CHG column and display it in
  // ...popover, between Supp/Opp controls and Trade/Trend controls...
  // distribute all those controls so there is same white space/gap
  // between [them] as groups"):
  //   1. Conviction tally (tug.conviction, "N Supp / N Opp") -- pulled OUT
  //      of .actpop-sym, where it used to sit inline next to the badge.
  //   2. The %CHG column's own candle+hi/lo%+price+range widget, verbatim
  //      (_chgCandleControlsHtml -- shared with the grid's %CHG cell).
  //   3. Trade/Trend boxes (_actpopTdTnHtml).
  //   4. The RR bar (_actpopRrBarHtml).
  // .actpop-ctrl-row uses a small fixed gap (not justify-content:
  // space-between -- that stretched past the popup's own edge on a wide
  // row, see .actpop-ctrl-row's CSS comment) between ALL 4 groups.
  // 2026-09-02, user: "anchor %CHG controls & td/tn to the RR controls and
  // leave the same gap as between %CHG,Tn/Td control groups" -- %CHG is
  // wrapped in .actpop-ctrl-anchor-rr (margin-left:auto) so it, Td/Tn and
  // RR form one tight cluster flush against the popup's right edge, all 3
  // sharing that same fixed gap; Supp/Opp is left behind on the far side
  // of the auto margin, next to the symbol block instead.
  // 2026-10-03: the rest of what the SYMBOL / ACTION cells show, as short lines under the
  // earnings line (symExtras): actioned tag (not "Done" -- user), over max, sizing stage,
  // low confidence. (Hit rate is no longer here -- the sources section shows each source's own.) Over max is shown once (the tag's own over-max note is skipped).
  let symExtras = '';
  const _ai = row._actionInfo;
  const _at = (_ai && _ai.doneOnly) ? '' : _actionTagHtml(row, true);
  if (_at) symExtras += `<div class="actpop-xl">${_at}</div>`;
  if (_isOverMaxOverlay(row)) {
    symExtras += `<div class="actpop-xl" style="color:#b45309;font-weight:700;">`
       + (row.account_sizes && row.account_sizes.length
          ? escapeHtml(_overMaxLabel(row))
          : `OVER MAX by ${escapeHtml(fmtUsd(Number(row.current_position_dollar) - Number(row.target_max_dollar)))}`)
       + `</div>`;
  }
  // 2026-10-14, user: the popup shows one reference account (IRA, size x1), not the full
  // per-account list. The over-max tooltip still lists every account.
  const _refAcct = (row.account_sizes || []).find(a => a.name === 'IRA');
  if (_refAcct) {
    symExtras += `<div class="actpop-xl" style="text-align:left;">`
       + escapeHtml(`${_refAcct.name} x${_refAcct.mult.toFixed(1)}: min ${_fmtK(_refAcct.min)} / max ${_fmtK(_refAcct.max)}`
         + ` / unit ${_fmtK(_refAcct.unit)} / held ${_fmtK(_refAcct.held)}${_refAcct.over ? ' (OVER MAX)' : ''}`)
       + `</div>`;
  }
  const _sz = _sizingStageInfo(row);
  if (_sz) {
    symExtras += `<div class="actpop-xl"><b>${_sz.label}</b> ${escapeHtml(_sz.detail)}</div>`;
  }
  if (row.low_confidence && side === 'sell') {
    symExtras += `<div class="actpop-xl" style="color:#b45309;"><b>LOW CONF</b> weak sell evidence, cross-check</div>`;
  }

  // margin-left:auto goes on whichever right-hand group renders first (once).
  let _anchored = false;
  const _anch = html => { if (!html || _anchored) return ''; _anchored = true; return 'actpop-ctrl-anchor-rr'; };
  const _tdtnHtml = _actpopTdTnHtml(row), _rrHtml = _actpopRrBarHtml(row);
  h += `<div class="actpop-top"><div class="actpop-head">
    <div class="actpop-sym"><div class="actpop-symline"><span style="color:${_symOutlookColor(row)}">${escapeHtml(row.rr_name || sym)}</span>`
    + `<span class="actpop-call ${callCls}" style="margin-left:8px;">${escapeHtml(fc.label || actionText(fc) || '—')}</span>`
    + tradeAmtTxt
    + nameTxt   // 2026-10-02: company name next to the action pill
    + `</div>`
    // price / shares / earnings share one fixed band with the right-hand control groups
    // (.actpop-px-group and .actpop-ctrl-c have the same top and height, contents centered)
    + `<div class="actpop-px-group">${pxTxt}${ownLine}${earnLine}</div>`
    + (symExtras ? `<div class="actpop-sym-extra">${symExtras}</div>` : '')
    + `</div>`
    + `<div class="actpop-ctrl-row">`
    // 2026-10-02 (user): every control group except the vertical bar is centered on the
    // price / shares / earnings lines (.actpop-ctrl-c), not the whole header.
    // %CHG and Supp/Opp stay at the left, next to the symbol block; the rest are pushed to the
    // right edge by margin-left:auto on the first one present (2026-10-02, user).
    + `<div class="actpop-ctrl-c">${_chgCandleControlsHtml(row, 0, false)}</div>`
    + _ctrlC(tug.conviction)
    + _ctrlC(_tdtnHtml, _anch(_tdtnHtml))
    + _actpopLevelBarHtml(row)
    + _ctrlC(_rrHtml, _anch(_rrHtml))
    + `</div>`
    + `</div>`
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

  // 2026-10-09: skipped when the stop gated the buy -- the "Stop" driver line
  // (with "drove it") already says this, with the same line price.
  if (row.stop_breached && !_stopGated(row)) {
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
  // shown in the header (the "Earnings in Nd" line under the action pill).
  const details = [];
  if (!row.held_today && row.suggested_target_dollar != null) details.push(`target ${_actpopFmtAmt(row.suggested_target_dollar)}`);
  if (details.length) h += `<div class="actpop-details">${details.join(' &middot; ')}</div>`;

  // Tradability detail box moved to the bottom (2026-08-20) -- was between
  // driver bullets and Tug; user wanted the score breakdown last, after
  // everything else.
  h += _actpopTradabilityHtml(row);

  // Analyst notes (same feed as the SYMBOL-cell hover); filled async by _actpopLoadNotes.
  const _nc = _notesCache.get(row.tos_symbol);
  h += `<div class="actpop-notes" data-sym="${escapeHtml(row.tos_symbol)}">${_nc ? _actpopNotesHtml(_nc) : '<span class="actpop-notes-h">Notes</span> loading&hellip;'}</div>`;


  h += `</div>`;
  return h;
}

function _actionTagHtml(r, noOver) {
  const ai = r._actionInfo;
  const nl = String.fromCharCode(10);
  if (ai) {
    const tip = [
      `• You ${ai.doneOnly ? 'marked this Done' : ai.label.toLowerCase()} on ${ai.date}`,
      ...((ai.bq || ai.sq) ? [`• Today: ${ai.bq ? 'bought ' + Math.round(ai.bq).toLocaleString() + ' sh' : ''}${ai.bq && ai.sq ? ', ' : ''}${ai.sq ? 'sold ' + Math.round(ai.sq).toLocaleString() + ' sh' : ''}`] : []),
      '• It is parked in "Actioned today" below',
      '• The signal itself is unchanged',
      ...(ai.over > 0 ? [`• Position is over its max by ${fmtUsd(ai.over)} (sizing still says trim)`] : []),
      ...(ai.doneOnly ? ['• Click this tag to undo Done'] : []),
    ].join(nl);
    return `<div class="action-tag" ${ai.doneOnly ? `data-done-undo="${escapeHtml(r.tos_symbol)}"` : ''} `
      + `style="margin-top:1px;font-size:9px;font-weight:700;color:#7c3aed;white-space:nowrap;${ai.doneOnly ? 'cursor:pointer;' : ''}" title="${escapeHtml(tip)}">`
      + `${escapeHtml(ai.label)} ${escapeHtml(fmtMD(ai.date) || '')}${ai.doneOnly ? ' ✎' : ''}`
      + (ai.over > 0 && !noOver ? `<br><span style="color:#b45309;">over max ${escapeHtml(fmtUsd(ai.over))}</span>` : '')
      + `</div>`;
  }
  const code = (r.final_code || '').toUpperCase();
  if ((code === 'SA' || code === 'SS' || code === 'STM') && r.last_bought_date) {
    const day = r.as_of_date || state.date;
    const ago = Math.round((new Date(day) - new Date(r.last_bought_date)) / 86400000);
    const tip = [`• Last bought ${r.last_bought_date}` + (ago > 0 ? ` (${ago} day${ago === 1 ? '' : 's'} ago)` : ''),
                 '• Context only: the signal is unchanged'].join(nl);
    return `<div class="action-tag action-tag-ctx" style="margin-top:1px;font-size:9px;font-weight:600;color:#94a3b8;white-space:nowrap;" title="${escapeHtml(tip)}">`
      + `Bought ${escapeHtml(fmtMD(r.last_bought_date) || '')}</div>`;
  }
  return '';
}
