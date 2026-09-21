# Actionable Logic

Deep-dive on the outlook-action → actionable path. `CLAUDE.md` carries only a
one-line pointer to this file in its Lookup index; keep the detail here.

## Overview

Two idempotent derive stages (`DELETE WHERE as_of_date=D` then INSERT):

1. `etl/derive_outlook_action.py` — evaluates the 6 sources in
   `ref_outlook_source`, writes one row per (symbol, source) into
   `drv_outlook_action`. Only real signals are written; a `None` action row
   is skipped.
2. `etl/derive_actionable.py` — consolidates all per-source actions plus
   action-type rule-group fires into one row per symbol in `drv_actionable`:
   picks a winner, resolves the sizing category, computes
   `suggested_target_dollar`, and applies position-aware suppression.

`web/actionable.js` renders `drv_actionable`.

## Diagrams

- `docs/diagrams/1_actionable_data_flow.svg` — **data flow**: trigger sources
  to ETL load, the derive cascade, `drv_actionable`, the API, the Actionable
  screen, and the `user_action_log` feedback.
- `docs/diagrams/10_actionable_logic.svg` — **decision logic**: the 6 outlook
  sources to their 4 classifiers to `drv_outlook_action`, the consolidation
  winner sort, category/sizing/suppression, and `drv_actionable`.

Keep both diagrams in sync whenever this logic changes.

## Stage 1 — per-source action

`ref_outlook_source` (11 active: RR, CALL, ETF, II, SSS, PS, RTA, RTAINFO,
SSSCHG, TOP5, MACROSHOW) drives the loop. `base_weight_method` selects the
comparison window + classifier. Each source runs inside its own SAVEPOINT so
one failure doesn't abort the rest.

| Source | Method | Cadence / window | Classifier | Notes |
|---|---|---|---|---|
| RR | outlook_modifier | Dense — exact snapshot vs. prior snapshot | `_action_standing` | `loads_prior_day_data` shifts the compare date back 1 day |
| ETF | outlook_modifier | Weekly bundle, SUN anchor + intra-week `etfchg` patches | `_action_standing` | NEUTRAL outlook = removed from list |
| II | outlook_modifier | Monthly bundle, latest snapshot ≤ D + intra-month `iichg` patches | `_action_standing` | NEUTRAL outlook = removed from list |
| CALL | outlook_modifier | Standing model — 30-day sparse window | `_action_call_standing` | see below |
| PS | rank | Weekly, FRI anchor; lower rank number = better | `_action_rank` | |
| SSS | rank_pct_delta | Weekly, MON anchor; driven by `pct_delta` | `_action_sss_pct_delta` | |
| RTA | rta_alert | Event-based — 5-day sparse window, most recent alert wins | `_action_rta` (side='long') | Real-time trigger; see below |
| RTAINFO | rta_alert | Event-based — 5-day sparse window, most recent alert wins | `_action_rta` (side='short') | Informational only; see below |
| SSSCHG | sss_change_alert | Event-based — 5-day sparse window, most recent event wins | `_action_sss_change` | Same-day trigger; see below |
| TOP5 | top5_alert | Event-based — 10-day sparse window, most recent appearance wins | `_action_top5` | Independent actionable source (acts like RTA); see below |
| MACROSHOW | stance_alert | Event-based — 5-day sparse window, most recent mention wins | `_action_macro_show` | Independent actionable source, normal Technical gate; see below |

### Classifier rules

**`_action_standing`** (RR / ETF / II) — held-agnostic standing-list
classifier. Presence on the current list with a positive weight is a buy
verdict every period, not just on first appearance; held-vs-not is resolved
downstream by `derive_actionable` suppression:

- base > 0 → ADD (positive weight on the current list)
- base < 0 → REMOVE (negative weight on the current list)
- base absent & prev present → REMOVE (dropped from the list)
- base = 0, or absent in both snapshots → silent

It never emits INCREASE / REDUCE / HOLD — only ADD, REMOVE, or silent.

**`_action_call_standing`** (CALL) — standing-recommendation model:

- Current = weight of the most recent row in the 30-day window. Prior =
  weight of the most recent *older* in-window row whose weight differs from
  current.
- current ≤ 0 → REMOVE if held, else silent
- current > 0 with a prior different weight > 0: higher → INCREASE;
  lower → REDUCE if held, else ADD
- current > 0 otherwise (flat all window, or prior ≤ 0) → ADD — a positive
  call is a standing ADD until acted on
- no CALL row in the 30-day window → silent

**`_action_rta`** (RTA / RTAINFO) — event-based classifier, not a standing
list; each hist_rta row is itself a directive (Buy/Sell/Sell-SOME on
`side='long'`, or Short/Cover/Cover-SOME on `side='short'`). Only the most
recent non-corrected, non-superseded alert per symbol within the 5-day
window is considered:

- `side='long'` (source RTA — real trigger): Buy → INCREASE (held) / ADD
  (not held); Sell → REMOVE if held, else silent; Sell-SOME → REDUCE if
  held, else silent.
- `side='short'` (source RTAINFO — Hedgeye's own short book; this
  portfolio is long-only): always HOLD, tagged with sentiment direction
  only (Sell = mild bearish, Cover/Cover-SOME = mild bullish). Never
  produces ADD/REMOVE — RTAINFO sits at the bottom of `SOURCE_ORDER` so an
  informational HOLD never masks a real signal from another source.

**`_action_top5`** (TOP5) — event-based classifier, not a standing list;
each `hist_call_top5` row tags a symbol's day on Hedgeye's Top-5 list with a
long/short bias. Only the most recent appearance per symbol within the
10-day window is considered. User decision 2026-08-19 ("TOP5 acts like
RTA"): mirrors `_action_rta`'s long side exactly — long bias → INCREASE
(held) / ADD (not held); short bias → REMOVE if held, else silent. Top-5 is
drawn from the same Hedgeye "Call" email that already feeds CALL's own
30-day standing model, but the two are treated as fully independent — no
special tie-break; `SOURCE_ORDER` decides the winner if they disagree
same-day.

**`_action_macro_show`** (MACROSHOW) — event-based classifier, not a
standing list; each `hist_hedgeye_stance` row tags a symbol's mention on
Hedgeye's "The Macro Show" as bullish or bearish. Only the most recent
mention per symbol within the 5-day window is considered. Same shape as
RTA's long side: bullish → INCREASE (held) / ADD (not held); bearish →
REMOVE if held, else silent. Unlike TOP5, does **not** bypass the Technical
gate (below) — it's a broad daily macro call, not a live per-symbol
trigger. Ranked lowest in `SOURCE_ORDER` so it never overrides a dedicated
per-symbol source.

**Only RTA bypasses the Technical gate on the buy side**
(`_compute_final_call(..., bypass_technical=(winning_source == "RTA"))`,
`etl/derive_actionable.py`). RTA is treated as a live, real-time per-symbol
trigger: an ADD/INCREASE resolves straight to BMN/BM at
`fc_confidence='high'` without requiring `rr_action` (Technical) to also
confirm the entry, unlike every other source. Sells are unaffected: REMOVE
still exits via the Technical-agnostic step-1 gate (unchanged, pre-existing
for all sources) and REDUCE still needs normal Technical confirmation.
Trade Mode's client-side check (`web/actionable.js::_isTradeModeQualifyingBuy`,
`_TECH_GATE_EXEMPT_SRC`) has the same RTA-only exemption, so an RTA-sourced
BM/BMN can qualify for Trade Mode even when `rr_action` (Technical) hasn't
independently confirmed.

SSSCHG and TOP5 previously shared this bypass (wired 2026-07-19 and
2026-08-19 respectively) but **user decision 2026-09-12 reverted both to
normal, Technical-gated sources** — both are same-day-equivalent triggers,
not real-time per-symbol alerts like RTA, so their ADD/INCREASE now needs
`rr_action` to agree for high-confidence display, same as RR/CALL/PS/etc.
SSSCHG still comes from the "Signal Strength Stocks" Added/Removed lines
(`hist_sss_change`, `etl/hedgeye/parsers.py::parse_signal_strength`, wired
in 2026-07-19 — previously informational-only, never reached the rules
engine), and TOP5 still comes from Hedgeye's daily Top-5 list — only the
Technical-bypass treatment changed, not their classifiers or `SOURCE_ORDER`
ranking (TOP5 still ranks 2, right behind RTA; SSSCHG still ranks 3, right
behind that — a same-day Gmail add/remove still overrides the file-based
weekly `SSS` source until SSS's own next snapshot catches up). MACROSHOW
was never in this list — it goes through the normal Technical gate
everywhere.

**ETFCHG/IICHG remain merged, not split out like SSSCHG** (deprecated as
standalone `ref_outlook_source` rows since this repo's initial commit —
`hist_etfchg`/`hist_iichg` events are folded into `ETF`'s/`II`'s own weight
at derive time and lose their event-vs-file provenance; see
`etl/derive_outlook_action.py`'s `_ETF_II_CHG` union). User decision
2026-07-19: rather than un-merging them (which would mean a second
decision-driving source per the SSSCHG pattern, with its own conflict rule),
`GET /api/actionable` instead adds two purely informational columns —
`etfchg_date`/`etfchg_outlook`/`etfchg_desc` and `iichg_date`/`iichg_outlook`/
`iichg_desc` — a 5-day-lookback LATERAL join straight against `hist_etfchg`/
`hist_iichg` (`api/routers/dash.py`). These never feed `consolidated_action`/
`winning_source`/`final_code` — they only answer "did a change event land
recently" for the EC/IC toolbar pills (`web/actionable.js`,
`state.filters.etfchg_only`/`iichg_only`, filtered client-side in
`matchesBaseFilters` since the flag is already in every loaded row — no
server round-trip, unlike the RTA/SC pills which reload via `state.filters.
source`).

Trade Mode's non-RTA leg checks `rr_action` (Technical) is in the buy family
`{BS, BM, BMN}` — same set as the Watchlist gate's `_ENTRY_RIPE_TECH`
(2026-07-19, swapped from `rr_bull_bear==='B'`). `rr_bull_bear` only reflects
which RR band-position table (`bull_rr_rule` vs `nbull_rr_rule`) computed the
QO leg of `rr_action`, not whether `rr_action` actually confirmed a buy on
this snapshot — `rr_action` is the more direct check.

**`_action_rank`** (PS) — lower rank number is better:

- new → ADD; dropped → REMOVE if held, else silent
- both present, held: rank improved → INCREASE; degraded → REDUCE;
  same → HOLD
- both present, not held: rank improved → INCREASE; degraded → silent
  (weakening — don't initiate); unchanged → ADD (standing recommendation)

**`_action_sss_pct_delta`** (SSS) — driven by `pct_delta` (% Delta Since
Initial); analyst rank is display-only:

- new → ADD; dropped → REMOVE if held, else silent
- on the list both weeks: pct_delta < 0 → REMOVE; rising → INCREASE;
  falling → REDUCE; steady → HOLD

## Stage 2 — consolidation (`derive_actionable.py`)

**Winner.** Every per-source action for the date, plus any fired action-type
rule groups (synthetic `RULES:<code>` candidates), compete via a
**held/not-held branch**:

- **Held symbol** — fixed `SOURCE_ORDER` (RTA=1 · TOP5=2 · SSSCHG=3 · PS=4 ·
  ETF=5 · RR=6 · SSS=7 · II=8 · CALL=9 · RTAINFO=10 · MACROSHOW=11). The
  highest-precedence source present sets the headline, whatever its action.
  RTA (same-day real-time trigger) ranks highest deliberately, with TOP5 and
  SSSCHG (same-day-equivalent triggers) right behind it; RTAINFO
  (informational short-book sentiment, always HOLD) and MACROSHOW (broad
  daily macro call) rank lowest so they can only "win" when no other source
  fired that day — they never bury a real signal.
- **Not-held symbol** — the most-recently-updated source wins (recency of
  `source_snapshot_date`); ties on date break by `SOURCE_ORDER`.

**Source ranking mode (TASK_140, 2026-09-21).**
`ref_settings.source_order_mode` — `'static'` (default) is the fixed
`SOURCE_ORDER` above, unchanged. `'measured'` re-ranks the **six outlook
sources only** (RR/SSS/CALL/II/PS/ETF) by their own measured buy-family
`edge_20d` (`ref_source_precedence.measured_rank`, recomputed nightly by
`etl/derive_source_edge.py::recompute_source_precedence` from
`v_source_edge_scorecard`) — a source with fewer than 30 buy-family samples
keeps its `static_rank` instead of guessing off a thin sample.
`RTA`/`TOP5`/`SSSCHG`/`RTAINFO`/`MACROSHOW` are **not** re-ranked in either
mode — those five ranks encode "same-day trigger beats a standing weekly
list", a timing rule, not an edge claim. `_order()` in
`etl/derive_actionable.py` resolves a candidate's rank via
`COALESCE(measured_rank, static_rank)` under `'measured'`. The not-held
sort also changes under `'measured'`: `(source_rank, -latest_update)` (rank
first, recency as tie-break) instead of today's `(-latest_update,
source_rank)`, which structurally favours CALL (the highest-volume,
lowest-edge feed) — `'static'` mode keeps the old sort exactly.
`drv_actionable.winning_source_rank`/`winning_source_edge` record what won
and its measured edge (edge populated whenever `ref_source_precedence` has
one, regardless of mode, so a `'static'`-mode history can still be scored
against what `'measured'` would have used). Released by TASK_139's
revalidation — A4 (source ranking) HELD across two market windows,
`docs/audit/signal_validation_2026-09.md` §C.

Rule-group candidates rank after the six sources using their group `priority`
value. Group-fired candidates use `as_of_date` as their update date; a
candidate with no date is treated as oldest (ordinal 0).

Removed behaviors (as of 2026-06-17): CALL "only wins when it's the only
source" carve-out (CALL now ranks last by `SOURCE_ORDER`); not-held PS REMOVE
exclusion (a PS REMOVE can win on the not-held path if it is the freshest
signal, but is still stamped "NOT HELD" and suppressed); SSS INCREASE/REDUCE
demotion (SSS competes on equal footing by source rank or recency).

**2026-09-12 — an unheld ADD with Technical neutral no longer resolves to a
standalone BMN/gate.** User: "Technicals need to support it." Previously,
`_compute_final_call()`'s technical-neutral branch treated "not held + Source
says ADD" as enough to show a weak BUY TO MIN badge even when `rr_action`
had no read either way (undefined Trade/Trend-vs-Risk-Range zone, or truly
neutral). It now falls through to the same `HOLD`/`gate` result as any other
technical-neutral, not-held case — Technical must actively confirm (BS/BM/
BMN) before a *new* position opens; a standing Source re-list with no
Technical support is not itself grounds to badge a buy. Mirrored in
`web/actionable.js`'s `finalCall()`/`_gateReasonFor()` client fallbacks.
Held ADD/INCREASE with Technical neutral was already `HOLD`/`gate` before
this change (via the `src_is_reduce`/final-else branches) and is unaffected.

**Category.** PS/ETF/ETFCHG winners look up `ref_asset_allocation` by the
symbol's `asset_class`; other sources use `position_category`. That yields
`min_dollar`, `max_dollar`, `units`, `maintain_min_position`.

**Sizing — `suggested_target_dollar`:**

| Action | Sizing |
|---|---|
| REMOVE | target 0; suppressed "NOT HELD" if no position |
| ADD | target = MIN; if held ≥ MIN → suppressed "ALREADY ESTABLISHED", target = held |
| INCREASE | not held → `min(MIN + Units, MAX)` (catch-up); held ≥ MAX → suppressed "AT CEILING"; else `min(held + Units, MAX)` |
| REDUCE | `maintain_min` on & held ≤ MIN → suppressed "AT FLOOR"; else `max(MIN, held − Units)`; no maintain → `max(0, held − Units)` |
| HOLD / none | target = current held dollars |

Suppression keeps the action but records a `suppressed_reason`, so the user
still sees what the system would have recommended.

## Display (`web/actionable.js`)

**Grid & Final Call (current as of TASK_103–110, 2026-07).** Column order:
bulk-select checkbox · H (only when Show Hidden is on) · POS$ · AMT$ · %CHG ·
Symbol · ACTION · MACRO · CALC · Sources · Technical · RR · Vlm · IV · MACD ·
MACDH · RSI · Rules (edge, capped at 4 pills + `+n`) · P(↑20d) · Agree · Act.
%CHG carries a small candle icon (open/high/low/last, via `window.mtTip.candleSvg`)
next to the change badge; Symbol's text is colored by `rr_outlook`
(Bullish/Bearish/Neutral), falling back to today's `pct_change` direction
when no outlook is set. RR is a small range-bar + tick (`.rr-rb`/`.rr-rb-tick`,
shared with `market_bar.js`'s mini-tape) showing where the last price sits
between LRR and TRR. (2026-07-06: these three replace the removed
symbol-tape chip bar that used to sit above the grid — same underlying
data, now inline in the grid instead of a separate scrollable strip.)
ACTION is the server-computed **Final Call** (`drv_actionable.final_code`,
D6) with a High/Gate/Mixed confidence badge; summary/filter chips bucket rows
by `finalCall()` so chips always match the ACTION column. A gear menu
toggles column visibility (persisted as `act_cols_v1`; CALC, P(↑20d), Agree
hidden by default) and a "?" button opens a static legend of all codes and
glyphs. All rows render by default (the earlier Top-15-row collapse +
"Show all N" bar was removed 2026-07-06 — the user preferred scrolling the
full list). MACRO sorts numerically on `macronet`.

**ACTION badge hover popover (2026-08-16, `_buildActionPopHtml`, `data-
actionpop` + `_showDataPop`).** Hovering the Final Call badge shows a rich
"how it got there" summary instead of a plain repeat of the badge text.
Iterated with the user: v1 replaced the plain `title` repeat ("instead of
repeating what I see for action ... it should say how it got there"); a
same-cell always-visible dot-tally line was tried next and reverted ("I
need to see a summary in action badge pop/hover over," not a new line in
the cell); v3 restored full source visibility and added a synthesized
headline ("I have all the sources how the final call is being made ...
organize it ... so I can see information from all sources and maybe a
recommended final decision"); v4 (current) folded in the rest of what the
SYMBOL cell already knows (Tradability Score, source hit-rate, fresh-signal
state) that wasn't reaching this popover yet. Top to bottom:
1. **Header** — symbol + Final Call.
2. **Recommendation** — a synthesized headline verdict (Strong/Moderate
   {BUY/SELL}, Weak, Conflicted, Unproven), derived from the agreement
   checklist's own agree/conflict tally (below) — distinct from
   `fc.confidence`, which only reflects the Sources×Technical two-driver
   gate, not the fuller checklist. Strong requires zero conflicts and
   agreement on ≥75% of checklist rows (`Math.ceil(checklist.length*0.75)`
   — 3/4 on sell-side rows, 4/5 on buy-side rows since Tradability only
   applies there).
3. **Confidence** — `fc.confidence` (High/Gate/Mixed/None) + a crisp,
   per-scenario reason for all four tiers, not just a flat "align"/
   "conflict" line. `_gateReasonFor(row)` (Gate) and `_highMixedReasonFor
   (row)` (High/Mixed) both walk `_compute_final_call`'s exact branch
   order (`etl/derive_actionable.py`) using the same classifier booleans,
   so the popover text always matches the actual server-side reason a row
   landed where it did — e.g. Gate covers 4 distinct branches (stop
   breach, exit-not-held, don't-initiate, no-active-signal — down from 7
   as of 2026-09-12: the at/over-Max cap and the standalone
   "establishing-position" case were both removed, see below); High/Mixed
   cover the RTA live-trigger bypass (SSSCHG/TOP5 lost this bypass
   2026-09-12) and every Sources-vs-Technical agree/disagree combination.
   Falls back to a generic "align"/"conflict" line only if neither
   scenario matches.
4. **Fresh-signal note** (buy-side, conditional) — same condition as the
   SYMBOL cell's NEW pill (`row._watchlisted && row._isNew`): winning-
   source data just landed, Technical hasn't had a chance to confirm yet.
   Shown as an informational blue note, not a risk flag — it's timing
   context, not disagreement.
5. **Sources** (the *full* per-source list, `_srcReasonsHtml` — every
   source's action + reason + date, not just the winner) — now also shows
   the winning source's own historical win rate inline (same
   `state.sourceScorecard` data as the SYMBOL cell's Trade-Mode-only
   hit-rate badge, but shown here regardless of Trade Mode) — + **Technical**
   (the tactical `rr_action` + its descriptor).
6. **Agreement checklist** — ✓ agrees / ✗ conflicts / ○ no signal, one
   short reason each, for **3-Way** (`_threeWayAgreement`), **CALC model**
   (`final_side_cal` vs `fc.side` — see the "CALC model inactive" project
   memory: currently always reads "no independent model score" since
   `ref_bull_model` has no active row), **Signals** (`_signalReasons`'
   RSI/MACD/rules tally), **PVV** (buy/sell tilt vs `fc.side`, skipping
   `NO_ACTION`/`WATCH`), and — buy-side rows only — **Tradability**
   (`_buyTradabilityScore` vs `_TRADABILITY_BADGE_MIN`, same score as the
   SYMBOL cell's 🎯 badge; conflict when the score is negative; headline
   reason is the dominant Risk Range factor, with the full item-by-item
   breakdown — Risk Range/Technical/RSI/IV/Volume/Source/Agreement, same
   `_tradabilityBreakdown` data as the 🎯 badge's own popover — indented
   underneath it, not just the one-line summary) — collapsing what used to
   be six separately-scattered agreement mechanisms (fc.confidence, the
   3-Way ▲3/▼3 badge, the CALC-vs-ACTION border, RULES edge pills, the PVV
   icon, the SYMBOL cell's 🎯 badge) into one place.
7. **Risk flags** (STOP breach, LOW CONF, earnings proximity, LT conviction
   conflict) — kept separate and always last, since these are risk, not
   directional disagreement; the Recommendation line notes their count but
   doesn't fold them into the tier itself.

**Refresh & data volume.** The 30-second auto-poll reloads rows with
`loadActionable({preserveState:true})` — user sort and bulk selection
survive; manual Refresh/date change still reset. Symbol search is debounced
(~150 ms). The row payload excludes `macro_detail`/`macro_howto`; the MACRO
hover popover lazy-loads them from `GET /api/actionable/macro-detail`
(client-cached per symbol@date). Bulk Done/Skip/Snooze posts once to
`POST /api/actionable/bulk-action`.

**Action labels.** The Action badge shows an instructional label, not the
raw code: ADD → `BUY→MIN`, INCREASE → `BUY SOME`, REDUCE → `SELL SOME`,
REMOVE → `SELL ALL`, HOLD → `HOLD`.

**Over category Max (`current_position_dollar > target_max_dollar`, REMOVE
excepted) — informational only (2026-09-03).** Previously this synthesized
a standalone `OVER_MAX`/"SO" Final Call that replaced whatever
Sources+Technical actually recommended — the same strategic-gate tier as
SELL ALL (`_compute_final_call` gate 1) — so a position could headline
"SELL OVERAGE" with no other sell signal anywhere. User: "Sell Overage
action ... should not drive the main action. Instead it should be one of
the input like Sources, Technicals, Macro." The gate was removed —
`_compute_final_call`/`finalCall()` now compute the Final Call purely from
Sources × Technical, identically whether or not the position is over its
category Max. Over-max is now flagged with an orange **OVER MAX** pill
next to the ACTION badge (`_isOverMaxOverlay`, same shape as the STOP/
earnings pills; tooltip shows the $ over cap) — it never changes
`consolidated_action`, `final_code`, `fc_confidence`, chip bucket, sort
severity, or AMT$. The pill itself deliberately stays strict
`current_position_dollar > target_max_dollar` — "over" means past the
ceiling, not merely at it. (Gate 4, the one remaining place the over-max
fact touched the Final Call, was removed later the same day — see below.)

**2026-09-12 — ESTABLISHED / NEAR MAX pill (soft sizing-stage signals).**
Same precedent as OVER MAX (2026-09-03): position-size context should
inform, never silently change, the Sources × Technical badge. User: "Pill
precedent applies to all the cases. It should not block the badge, instead
pill should tell me the situation." Two blue, informational-only pills next
to the ACTION badge (`web/actionable.js::_sizingStagePill`, same shape as
`.overmax-pill`, held BUY rows only):
- **ESTABLISHED** — held ≥ category Min floor already. Without it, a
  standing ADD re-list (several sources reissue "ADD" every period they're
  on a list) with a confirming Technical can badge BM/BS/BMN at High
  confidence indefinitely, with no visual cue that the floor was cleared
  long ago.
- **NEAR MAX** — held is ≥75% of the way from Min to Max. Still a real
  BM/BS (Technical is still confirming a genuine entry, and there's still
  room under Max), just flagged as "not much room left."

Neither changes `final_code`, `fc_confidence`, or AMT$ — same non-override
contract as OVER MAX. Initially kept separate from gate 4 (at/over Max →
HOLD) on the reasoning that a self-defined ceiling was a feasibility
constraint, not a soft preference — **superseded a few hours later, see
below.**

**2026-09-12 (same day, earlier) — gate 4's own threshold changed from `>`
to `>=`.** Held *exactly equal to* Max used to slip past this gate
(`current_position_dollar > target_max_dollar` was `False` at the
boundary), so a position sitting right at its ceiling with Technical still
confirming would show an active BM/BS at High confidence — AMT$ correctly
showed $0 (sizing's own AT CEILING suppression already used `>=`), so the
effect was a "BUY MORE — $0" badge. Fixed by aligning the comparison to
`>=`, mirrored client-side by a new `_isAtOrOverMax()` helper.

**2026-09-12 (later) — gate 4 removed entirely.** User: "why can't we just
have the pill (remove the hardstop for consistency)? ... Amount is going to
tell me anyways that i should not buy. right?" Reconsidered the
"feasibility vs. preference" distinction above — buying past a self-set Max
is a policy choice, not a physical impossibility (unlike selling a symbol
you don't hold, gate 2's don't-initiate guard, which stays). Two things
already carry the "no room to add" signal without touching the badge: AMT$
is already $0 at/over Max (sizing's own AT CEILING suppression, untouched
by this change) and the OVER MAX pill is visible everywhere the badge is,
including Trade Mode (a row filter on the same grid, not a separate column
set — AMT$ stays visible there too). `_compute_final_call`'s `at_max` local
and gate-4 branch are gone; `finalCall()`/`_gateReasonFor()` dropped their
mirrors the same way. `_isAtOrOverMax()` (client) is kept, but only to
suppress the ESTABLISHED/NEAR MAX pill in favor of OVER MAX once a position
reaches its ceiling — it no longer gates anything. A confirmed Technical
buy at/over Max now shows through as BM/BS with $0 AMT$ and the OVER MAX
pill, same non-override contract as every other sizing signal in this
section.

**AMT$** shows the delta for actionable rows: ADD / INCREASE = target −
position, REMOVE / REDUCE = position − target, all clamped ≥ 0 (suppressed
rows → 0). HOLD / no-action rows show the current held dollars, not a delta.
Over-max no longer overrides it (see above); the trim-to-cap $ is available
in the OVER MAX pill's own tooltip instead.

**2026-09-12 — AMT$ keyed off the resolved Final Call, not the raw Source
action.** Previously AMT$ (`web/actionable.js`) was computed from
`consolidated_action` alone, before `finalCall()` resolved the badge. When
Technical vetoed or flipped a Source's action — e.g. Source=INCREASE but
Technical is in a sell zone (badge flips to `SS`), or a buy/reduce vetoed
down to `HOLD` — AMT$ still showed the raw Source's dollar figure: a
buy-direction $ next to a **SELL SOME** badge, or a nonzero $ next to
**HOLD**. AMT$ now branches on `final_code` first (SA → full position; SS/
STM → position − target; BM/BS/BMN → target − position; anything else →
current held dollars, matching the HOLD convention above) — it can no
longer disagree with the badge shown alongside it. Rows without a
`final_code` yet (pre-migration fallback) keep the original
`consolidated_action`-based math.

**Snapshot dates.** The winning source's effective snapshot date — the date
the underlying data record is for (`drv_outlook_action.as_of_date`, carried
into `source_actions.snapshot_date` by `derive_actionable.py`) — is shown in
the Sources cell's per-source reason lines and in the drilldown's per-source
table / comparison panel. All snapshot dates render as MM/DD (no year).
`/api/actionable/sources` supplies each source's `base_weight_method`
(used for percent formatting of SSS metrics). The Source filter matches a
row when the chosen source is its winning source **or** appears among its
other sources.

**Snooze / skip semantics (TASK_103).** The Act column's Done/Skip/Snooze
buttons (and Focus mode, and the bulk bar) log user actions via
`POST /api/actionable/{symbol}/action` (bulk:
`POST /api/actionable/bulk-action`). Done logs the row's Final Call code as
`action_code` from every entry point. A **date-less SNOOZED** action means
"hidden for this as_of_date" (same lifetime as SKIPPED); a SNOOZED with
`snooze_until` stays hidden until that date. Hidden rows reappear under
"Show Hidden" with an H-column reason; `DELETE /api/actionable/{symbol}/action`
clears both SKIPPED and SNOOZED rows (un-snooze). A new anchor date
re-surfaces everything. Focus-mode keys: Enter/D Done · S Skip · Z Snooze ·
←/→ Prev/Next · Esc close (Esc also closes the drilldown modal, topmost
layer first). When `last_price < stop_level` the AMT$ cell's stop sub-text
renders bold red.

**Per-source inline comparison.** Each row of the drilldown's "Per-source
actions" table expands on click to a current-vs-previous record comparison
(`/api/actionable/comparison`). It is source-agnostic: every non-housekeeping
column of the source table is introspected and shown for both records with a
Δ column. A side whose `base_weight` / `prev_weight` is NULL (symbol not in
that bundle) renders blank — no stale pre-drop record is resurrected. Only
the classifier's decision-driving field(s) are highlighted — `pct_delta` for
SSS, `rank` for PS, `outlook` (+ `outlook_modifier`) for the outlook
sources — keyed off `base_weight_method`.

**Percentages.** `pct_delta` (SSS) is stored as a fraction and shown as a
percentage (× 100, `%` suffix) everywhere it surfaces — the comparison
panel, per-source table and hover popover format it client-side;
the SSS action `reason` text (e.g. `pct_delta +5% -> +6.1% (rising)`) is
percentage-formatted in `_action_sss_pct_delta` via `_pct_str`. The stored
`hist_sss` value is never changed and the classifier keeps comparing the raw
fraction.

## Re-derive

After editing this logic: `python rebuild_actionable.py` runs
`derive_outlook_action` then `derive_actionable` for the recent dates, then
restart the app.

---

## Risk Range Analysis — UI Data Flow

The **Risk Range Analysis** section appears in the Actionable drilldown modal and the Trace screen. It is rendered by `renderRRAnalysis()` in `web/_common.js` using three API endpoints.

### API Endpoints

| Endpoint | Purpose |
|---|---|
| `/api/actionable/rr-analysis?symbol=X&date=D` | Main snapshot — all fields for charts and grid |
| `/api/actionable/rr-history?symbol=X&date=D&days=60` | 60-day time-series for Graph 3 |
| `/api/actionable/rr-detail?symbol=X&date=D` | Hover tooltip detail for TrTnBBRskRng column |

### Data Flow by Section

**Graph 1 — Price bar vs RR bands**
```
hist_td   → last_price (prev close, left label)
drv_quote → last_price / high_price / low_price (today, right label)
hist_rr   → buy_trade (LRR), sell_trade (TRR)
           → MRR = (LRR + TRR) / 2
  Displayed: price bar (green=up/red=down) + TRR/MRR/LRR dashed lines + green zone
```

**Top box above Graph 1 — TRR / MRR / LRR indices**
```
drv_quote (high, last, low) + hist_rr (EC=LRR, ED=TRR) + hist_tw (std_dev)
  AC  = min(std_dev, median_sd)
  ES  = (high  - ED) / AC   → trig_ifs(lo=-0.25, hi=1)    → KI (trr_idx)
  ET  = (last  - midpoint) / AC  → trig_ifs(lo=-0.25, hi=0.25) → KJ (mrr_idx)
  EU  = (low   - EC) / AC   → trig_ifs(lo=-0.25, hi=1)    → KK (lrr_idx)
  Stored in: drv_cat_atomic_input
```

**Graph 2 — Trend / Trade lines + price indicator**
```
hist_td → a_trend_value (Trend line, fixed position)
         → a_trade_value (Trade line, fixed position)
drv_quote → last_price (price indicator: ↑ above Trade, ↓ below Trend, dashed line if between)
```

**Top box above Graph 2 — SD / Trend SD / Trade SD**
```
hist_tw → std_dev, median_sd → AC = min(std_dev, median_sd)
drv_quote → last_price
hist_td → a_trend_value, a_trade_value
  trend_sd = (last - a_trend_value) / AC
  trade_sd = (last - a_trade_value) / AC
```

**Grid — Descriptions + Decision Path**
```
drv_cat_atomic_input → Pass-3 lookups via ref_param_lookup:

  Trend/Trade (QE → QG):
    trend_sd/trade_sd/trade_trend_sd → CASE → QE (trade_trend_sd_rule)
    ref_param_lookup(tn_td_rule, QE) → short_name (badge) + description + seq (QF)

  BB Range Streak (QJ → QL):
    a_bb_top_slope / a_bb_bot_slope → CASE → QJ (bb_rng_strk_rule)
    ref_param_lookup(bb_range, QJ)  → short_name (badge) + description + seq (QK)

  RR Desc (QP/QQ):
    QJ ≥ 2 → QP='B'  → ref_param_lookup(bull_rr_rule,  QM) → short_name + seq (QO)
    QJ ≥ 0 → QP='!B' → ref_param_lookup(nbull_rr_rule, QN) → short_name + seq (QO)
    QM/QN from KI/KJ/KK + perf1d_sd_rule + macdh_direction
      perf1d_sd_rule (LH): drv_quote.net_chng / AC → trig_ifs("Perf1D SD Rule")
      macdh_direction (JG): hist_tw.a_macdh_d_brr → SIGN(x), 0→-1

  Decision Path (QR → QS):
    IF QF < 0 → QR = QF  (Trend/Trade bearish wins)
    IF QF > 0 → IF QK < 0 → QR = QK  (BB bearish wins)
               ELSE        → QR = QO  (RR signal)
    ref_param_lookup(td_tn_bb_rr_action, QR) → QS action code (BS/STM/SA/…)
```

**Graph 3 — 60-day history**
```
hist_td  → last_price, a_trend_value, a_trade_value  (daily)
hist_rr  → buy_trade (LRR), sell_trade (TRR)          (periodic, forward+backward filled)
  → /api/actionable/rr-history  (async, loads after modal opens)
  Displayed: price line (blue) + TRR/LRR step-function lines (green) + Trade/Trend lines
```

**TrTnBBRskRng column (actionable table)**
```
drv_cat_atomic_input.td_tn_bb_action_desc (QS) joined in /api/actionable query
  → shown immediately in column (no lazy load)
  → hover tooltip via /api/actionable/rr-detail: all QE..QT values + levels + indices
```

### Full Pipeline Summary

```
Excel files ──ETL──→ hist_td / hist_tw / hist_rr / drv_quote
                          ↓ derive_all()
              drv_cat_atomic_input  (KI/KJ/KK, QE..QT via Pass-1/2/3)
              drv_ma                (a_trend_value, a_trade_value)
                          ↓ API
              /api/actionable/rr-analysis   → graphs + grid
              /api/actionable/rr-history    → Graph 3 history
              /api/actionable/rr-detail     → hover tooltip
                          ↓ JS
              renderRRAnalysis()  in web/_common.js
              setupRRActionCol()  in web/actionable.js
```

---

## Final Action Tables

### Override rules (apply first, before RR signal)

| QE (Trend/Trade seq) | QK (BB Range seq) | Result |
|---|---|---|
| < 0 | any | QR = QF → **SA** or **STM** (Trend/Trade bearish wins) |
| > 0 | < 0 | QR = QK → **STM** or **SS** (BB bearish wins) |
| = 0 | any | QR = null → no action |

### Table 1 — QE × QJ → Final Action

*When no override applies, uses best-case RR signal (QM=6 / QN=5).*

| QE \ QJ | -4 | -3 | -2 | -1 | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|---|---|---|
| **-2** Bear | SA | SA | SA | SA | SA | SA | SA | SA | SA |
| **-1** Cls2Tn | SA | SA | SA | SA | SA | SA | SA | SA | SA |
| **1** >Tn<Td | STM | STM | STM | STM | STM | STM | STM | STM | STM |
| **2** <Tn>Td | — | — | — | — | — | — | — | — | — |
| **3** LesBull | STM | STM | STM | STM | **BM** | **BM** | **BM** | **BM** | **BM** |
| **4** Bull | STM | STM | STM | STM | **BM** | **BM** | **BM** | **BM** | **BM** |

QJ < 0 forces STM even when Trend/Trade is bullish. Both QE and QJ must be positive to reach the RR signal.

### Table 2 — Bull path QM → Final Action

*Only reached when QE ∈ {3,4} AND QJ ∈ {2,3,4} AND QK ≥ 0*

| QM | Short name | QO seq | Final QS | Meaning |
|---|---|---|---|---|
| -1 | D>L<M | -9 | **STM** | Sell To Min — bearish in bull zone |
| 1 | U=M | 8 | **BMN** | Buy Min — at MRR midpoint |
| 2 | D=L>Td | 8 | **BMN** | Buy Min — at LRR, above Trade |
| 3 | U>L<M<cd | 8 | **BMN** | Buy Min — above LRR, below MRR, MACDH falling |
| 4 | U=L | 9 | **BS** | Buy Some — at LRR level |
| 5 | D>M | 9 | **BS** | Buy Some — pulled back below MRR |
| 6 | U>L<M>cd | 10 | **BM** | Buy More — above LRR, below MRR, MACDH rising |

### Table 3 — Not-Bull path QN → Final Action

*Only reached when QE ∈ {3,4} AND QJ ∈ {0,1} AND QK ≥ 0*

| QN | Short name | QO seq | Final QS | Meaning |
|---|---|---|---|---|
| -1 | >=T | -8 | **SS** | Sell Some — price at/above TRR in not-bull zone |
| 1 | U>M<T | 0 | **N** | Neutral — above MRR but below Trade line |
| 2 | U>L<=M<cd | 8 | **BMN** | Buy Min — above LRR, at/below MRR, MACDH falling |
| 3 | D=L>Td>Tn | 8 | **BMN** | Buy Min — at LRR, above both Trade and Trend |
| 4 | U=L | 10 | **BM** | Buy More — at LRR level |
| 5 | U>L<=M>cd | 10 | **BM** | Buy More — above LRR, at/below MRR, MACDH rising |

### Action code reference

| QS | Full name | Priority |
|---|---|---|
| SA | Sell All | 21 |
| STM | Sell To Min | 20 |
| SS | Sell Some | 19 |
| SO | Sell Overage | 12 |
| SW | Sell Watch | 11 |
| SWW | Sell Watch Watch | 5 |
| SN | Sell Neutral | 3 |
| N | Neutral | 3 |
| BN | Buy Neutral | 3 |
| BC | Buy Conflict | 14 |
| BRW | Buy Risk Watch | 5 |
| BSW | Buy Some Watch | 9 |
| BW | Buy Watch | 10 |
| BR | Buy Risk | 13 |
| BMN | Buy Min | 15 |
| BS | Buy Some | 16 |
| BM | Buy More | 18 |

**2026-09-12 — broken LRR support forces STM, in both Tables 2 and 3.**
Previously `lrr_idx = -1` (today's low closed more than 0.25 SD below LRR —
see `EU` in `docs/...` Risk Range Analysis section above) matched none of
QM's or QN's clauses (all require `lrr_idx` ∈ {0,1}), so a broken support
level fell through to `QM`/`QN = NULL` → no Technical signal at all — the
same "silent" behavior as the undefined Trade/Trend zone. User: "if it is
below LRR instead of silent I need to see STM ... stock doesn't have a
support at LRR and might go down from there instead of a bounce."
`etl/derive.py::_derive_trend_trade_rules_impl` now checks `lrr_idx = -1`
first, before any other QM clause (bull path, QJ≥2) — reuses the existing
`bull_rr_rule` code `-1` (STM), no new reference data needed. The not-bull
path (QJ∈{0,1}) has no STM code in `nbull_rr_rule` at all (its worst case is
SS, "at/above TRR"), so the override is applied directly in Pass 2's `QO`
computation instead of the lookup table. Either way this only overrides the
RR-position sub-read (`QO`) — the Trend/Trade bearish override (`QE<0`) and
BB-range bearish override (`QJ<0`) still take priority over it, unchanged.

---

## Stop signal (`drv_actionable.stop_signal`)

Computed in `etl/derive_actionable.py::_compute_stop_signal()` for held
positions and BUY/SELL-family actions (INCREASE, ADD, REDUCE, REMOVE). NULL
otherwise.

**2026-08-12 — replaced the old `stop_level` $ price formula** (`MAX(trade
line, last_price*(1-stop_pct))`, `stop_level` column now always NULL) with
Trade/Trend-line signals. The $ formula reacted to a single day's close,
which whipsawed. `Td` = EOD `a_trade_value`, `Tn` = EOD `a_trend_value`
(same two lines the Rule Flow crossover formulas use). Price is the live
`drv_quote.last_price` on the current anchor date, falling back to that
day's frozen `drv_technicals.last_price` for prior confirmation days.

**2026-08-12 follow-up — both legs redesigned from N-day persistence to a
crossover event.** A symbol sitting below a line for weeks re-fired every
single day under plain persistence; a crossover fires only when the prior 3
`as_of_date`s (not today) all sit on one side of the line and today flips to
the other side — self-resetting by construction, since the day after a
flip, that flip day itself joins the "prior 3" window and breaks the
uniformity, so the signal shows only once, on the actual crossing day.
(Trend-line `TN SA` started as a persistence check and was converted to a
crossover in this same follow-up, matching the Trade-line legs.)

Checked in this priority order, all via the same crossover shape (prior 3
`as_of_date`s on one side of the line, today on the other) unless noted:

| Condition | `stop_signal` | Meaning |
|---|---|---|
| Trend-line crossover DOWN: prior 3 `as_of_date`s above Trend, today below | `TN SA` | Sell All — most severe, checked first |
| Trade-line crossover DOWN: prior 3 `as_of_date`s above Trade, today below | `TD STM` | Sell To Min |
| Trade-line crossover UP (prior 3 `as_of_date`s below Trade, today above), **and** also above the Trend line **today** | `TD BM` | Buy More — the stronger tier |
| Trade-line crossover UP (same as above), but at/below the Trend line today | `TD BMN` | Buy Min — the weaker tier |
| None of the above, or fewer than 4 `as_of_date`s of history yet | `NULL` | — |

`TD BM`/`TD BMN` share the same Trade-line crossover trigger — the only
difference is a same-day check: is price ALSO above the Trend line today?
(Not a lookback — just today's position, same as the `TD BM` design
before the brief 2026-08-12 "unbounded ever-above-Trend" detour, which was
reverted after checking it against LQD: price 106.12 vs Trend 106.93 —
below Trend today, so it should read `TD BMN`, not `TD BM`.)

**`stop_breached` (TASK_119, 2026-07-12; redefined 2026-08-12).** `BOOLEAN
NOT NULL DEFAULT FALSE` on `drv_actionable`. Set TRUE for held rows where
`stop_signal IN ('TD STM', 'TN SA')` (was `last_price < stop_level`). `TD BM`/
`TD BMN` (buy-side signals) never count as a breach. If `consolidated_action`
is ADD or INCREASE, `_compute_final_call()` downgrades the *effective* Final
Call to HOLD (`fc_confidence='gate'`) while `consolidated_action`/
`source_actions` keep the original recommendation and `suppressed_reason` is
set to `'STOP BREACHED'` — the user still sees what the system would have
said. REMOVE/REDUCE/HOLD rows are just flagged, never force-upgraded to
REMOVE. Non-held rows are never flagged. Surfaced on `/actionable` as a red
"STOP" pill next to the ACTION badge, a red left-edge row tint, and a
"STOP n" summary chip (`web/actionable.js`).

## SELL-side confidence (`drv_actionable.low_confidence`, TASK_118)

`v_unproven_sell_rules` (`db/baseline.sql`) self-updates from
`v_rule_scorecard`: any composite with `direction='SELL'`, `fires>=500`, and
`edge_20d<0` (price recovers, on average, after the rule fires) — no
hardcoded rule list. In `etl/derive_actionable.py`, a symbol's
`low_confidence` flag is TRUE when its only sell-side evidence is a fired
composite in that set — i.e. no per-source REMOVE/REDUCE and no *proven*
SELL composite also fired. BUY-side rules/thresholds/weights are untouched.
`/actionable` renders a muted/outline ACTION badge with a "LOW CONF"
sub-label and a "Low" confidence badge on flagged rows. See
`docs/audit/sell_candidates_2026-07.md` for the related sell-into-strength
backtest (S1–S3, none recommended for activation).

## Unproven-sell enforcement (`ref_settings.unproven_sell_mode`, TASK_141)

Released 2026-09-21 by TASK_139's revalidation (SELL-side HELD across two
windows, `docs/audit/signal_validation_2026-09.md` §E). Reuses the exact
`low_confidence` condition above — no second classifier.

- `'annotate'` (**default**) — today's TASK_118 behaviour, byte for byte:
  `low_confidence` is a flag only, `consolidated_action`/`fc_confidence`
  are never changed by it.
- `'suppress'` — a row whose `low_confidence` is TRUE has its REMOVE/REDUCE
  `group_candidates` **excluded from the winner contest** in
  `etl/derive_actionable.py`, right before the sort (source-driven REMOVE/
  REDUCE can't reach this branch — `low_confidence` requires
  `source_driven_sell` to be False by construction, so any excluded
  candidate is, by definition, backed only by the unproven rule). If that
  leaves no candidate, the row resolves to HOLD through the existing
  no-winner path — no synthesized action. The original action + rule ids
  are untouched in `source_actions`/`triggered_group_ids` (built from the
  unfiltered `src_actions`/`triggered_groups`, not the filtered contest
  list) — the drilldown still shows what the system would have said.
  `drv_actionable.unproven_sell_suppressed` records whether this actually
  removed a candidate for the row (so the effect can be scored afterwards).
  Sets `suppressed_reason = 'UNPROVEN SELL'`, same pattern as `NOT HELD`/
  `AT CEILING`.
- **Part B** — `_compute_final_call` (mirrored in `web/actionable.js`'s
  `finalCall()`) downgrades a sell-side call that would render
  `fc_confidence='high'` to `'mixed'` when its evidence is `low_confidence`
  AND `unproven_sell_mode='suppress'`. Buy-side confidence is untouched.

**2026-09-21 verification finding:** on the current dataset and
`ref_trig_rule_group` configuration, **zero** active `group_type='action'`
rows carry `action_label` `REMOVE`/`REDUCE` — the rule-groups engine simply
has no path to a sell-family winning candidate today, with or without this
switch. Consequently `low_confidence=TRUE` has never once co-occurred with
a `REMOVE`/`REDUCE` `consolidated_action` in this table's history (checked
across all dates) — Part A's filter and Part B's downgrade are both
verified correct in isolation (direct function calls — see
`DEV_HANDOFF.md` TASK_141) but have had **zero observable effect** on any
historical or live-tested date. This is a config fact, not a bug: the
moment a REMOVE/REDUCE action-type rule group is added and fires on a
`low_confidence` symbol, both parts activate exactly as designed.
