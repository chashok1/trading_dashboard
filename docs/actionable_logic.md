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

`ref_outlook_source` (8 active: RR, CALL, ETF, II, SSS, PS, RTA, RTAINFO)
drives the loop. `base_weight_method` selects the comparison window +
classifier. Each source runs inside its own SAVEPOINT so one failure
doesn't abort the rest.

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

**RTA and SSSCHG bypass the Technical gate on the buy side**
(`_compute_final_call(..., bypass_technical=(winning_source in ("RTA",
"SSSCHG")))`, `etl/derive_actionable.py`). Both are live, same-day event
triggers — RTA from Real-Time Alert emails, SSSCHG from the "Signal Strength
Stocks" Added/Removed lines (`hist_sss_change`, `etl/hedgeye/parsers.py::
parse_signal_strength`, wired in 2026-07-19 — previously informational-only,
never reached the rules engine). An ADD/INCREASE from either resolves
straight to BMN/BM at `fc_confidence='high'` without requiring `rr_action`
(Technical) to also confirm the entry, unlike every other source. Sells are
unaffected: REMOVE still exits via the Technical-agnostic step-1 gate
(unchanged, pre-existing for all sources) and REDUCE still needs normal
Technical confirmation. `SOURCE_ORDER` ranks SSSCHG right behind RTA (both
same-day triggers) — a same-day Gmail add/remove overrides the file-based
weekly `SSS` source (`hist_sss`, unchanged, its own lower tier) until SSS's
own next snapshot catches up. Trade Mode's client-side check
(`web/actionable.js::_isTradeModeQualifyingBuy`, `_TECH_GATE_EXEMPT_SRC`) has
the same RTA/SSSCHG exemption, so an RTA- or SSSCHG-sourced BM/BMN can
qualify for Trade Mode even when `rr_action` (Technical) hasn't independently
confirmed.

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

- **Held symbol** — fixed `SOURCE_ORDER` (RTA=1 · PS=2 · ETF=3 · RR=4 · SSS=5 ·
  II=6 · CALL=7 · RTAINFO=8). The highest-precedence source present sets the
  headline, whatever its action. RTA (same-day real-time trigger) ranks
  highest deliberately; RTAINFO (informational short-book sentiment, always
  HOLD) ranks lowest so it can only "win" when no other source fired that
  day — it never buries a real signal.
- **Not-held symbol** — the most-recently-updated source wins (recency of
  `source_snapshot_date`); ties on date break by `SOURCE_ORDER`.

Rule-group candidates rank after the six sources using their group `priority`
value. Group-fired candidates use `as_of_date` as their update date; a
candidate with no date is treated as oldest (ordinal 0).

Removed behaviors (as of 2026-06-17): CALL "only wins when it's the only
source" carve-out (CALL now ranks last by `SOURCE_ORDER`); not-held PS REMOVE
exclusion (a PS REMOVE can win on the not-held path if it is the freshest
signal, but is still stamped "NOT HELD" and suppressed); SSS INCREASE/REDUCE
demotion (SSS competes on equal footing by source rank or recency).

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

**Refresh & data volume.** The 30-second auto-poll reloads rows with
`loadActionable({preserveState:true})` — user sort and bulk selection
survive; manual Refresh/date change still reset. Symbol search is debounced
(~150 ms). The row payload excludes `macro_detail`/`macro_howto`; the MACRO
hover popover lazy-loads them from `GET /api/actionable/macro-detail`
(client-cached per symbol@date). Bulk Done/Skip/Snooze posts once to
`POST /api/actionable/bulk-action`.

**Action labels.** The Action badge shows an instructional label, not the
raw code: ADD → `BUY→MIN`, INCREASE → `BUY SOME`, REDUCE → `SELL SOME`,
REMOVE → `SELL ALL`, HOLD → `HOLD`. When the held position exceeds the
category Max (`current_position_dollar > target_max_dollar`, REMOVE
excepted), the badge overlays `SELL→MAX` in REDUCE orange (so the sell
intent reads at a glance) and the original label is shown underneath in
small bold letters tinted with that action's own color ("was BUY SOME" in
INCREASE green, "was BUY→MIN" in ADD blue, etc.). The stored `consolidated_action`,
`winning_source`, Reason, chip count, and sort severity are all unchanged
— it's a pure display overlay, no derive change. Summary/filter chips use
the same instructional labels (SELL ALL, SELL SOME, BUY SOME, BUY→MIN, HOLD,
— for no-action; ALL stays "ALL"). A synthetic `SELL→MAX` chip counts and
filters over-allocation rows (any row where the overlay fires); those rows
are also counted in their underlying action chip.

**AMT$** shows the delta for actionable rows: ADD / INCREASE = target −
position, REMOVE / REDUCE = position − target, all clamped ≥ 0 (suppressed
rows → 0). HOLD / no-action rows show the current held dollars, not a delta.
When the position exceeds the category Max (REMOVE excepted), AMT$
overrides to `position − Max` — the trim back to the ceiling — paired with
the `SELL→MAX` badge overlay.

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

---

## Stop-level (`drv_actionable.stop_level`)

Computed in `etl/derive_actionable.py::_compute_stop()` for held positions and
BUY/SELL-family actions (INCREASE, ADD, REDUCE, REMOVE). None otherwise.

**Formula** (mode `trade_line_or_pct`, the default):

```
stop_level = MAX(trade_line, last_price * (1 - stop_pct))
```

- `trade_line` — EOD `a_trade_value` from `drv_technicals` for that symbol/date.
- `last_price` — most recent price from `drv_quote`.
- `stop_pct` — `ref_settings.stop_pct` (default `0.08` = 8%).

If no price data is available, `stop_level` is NULL.

**Tuning knobs** (in `ref_settings`):

| setting_name | default | meaning |
|---|---|---|
| `stop_mode` | `trade_line_or_pct` | Computation mode (only one mode implemented). |
| `stop_pct` | `0.08` | Percentage below current price used as the pct-based floor. |

To change: `UPDATE ref_settings SET setting_value = '0.05' WHERE setting_name = 'stop_pct';`
then re-derive (`python -m etl.scheduler` or File Monitor → Force Re-derive).

**`stop_breached` (TASK_119, 2026-07-12).** `BOOLEAN NOT NULL DEFAULT FALSE`
on `drv_actionable`. Set TRUE for held rows where `last_price < stop_level`.
If `consolidated_action` is ADD or INCREASE, `_compute_final_call()` downgrades
the *effective* Final Call to HOLD (`fc_confidence='gate'`) while
`consolidated_action`/`source_actions` keep the original recommendation and
`suppressed_reason` is set to `'STOP BREACHED'` — the user still sees what the
system would have said. REMOVE/REDUCE/HOLD rows are just flagged, never
force-upgraded to REMOVE (bond ETFs can sit pennies below a tight stop
without being "losers"). Non-held rows are never flagged. Surfaced on
`/actionable` as a red "STOP" pill next to the ACTION badge, a red left-edge
row tint, and a "STOP n" summary chip (`web/actionable.js`).

## SELL-side confidence (`drv_actionable.low_confidence`, TASK_118)

`v_unproven_sell_rules` (`db/baseline.sql`) self-updates from
`v_rule_scorecard`: any composite with `direction='SELL'`, `fires>=500`, and
`edge_20d<0` (price recovers, on average, after the rule fires) — no
hardcoded rule list. In `etl/derive_actionable.py`, a symbol's
`low_confidence` flag is TRUE when its only sell-side evidence is a fired
composite in that set — i.e. no per-source REMOVE/REDUCE and no *proven*
SELL composite also fired. **Annotation only** — `consolidated_action` is
never changed by this flag; BUY-side rules/thresholds/weights are untouched.
`/actionable` renders a muted/outline ACTION badge with a "LOW CONF"
sub-label and a "Low" confidence badge on flagged rows. See
`docs/audit/sell_candidates_2026-07.md` for the related sell-into-strength
backtest (S1–S3, none recommended for activation).
