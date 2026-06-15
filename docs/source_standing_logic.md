# Source Standing — single source of truth (`drv_source_standing`)

Design doc. Implementation is handed to the developer agent via
`agent-tasks/TASK_9_source_standing_unification.md`. Cowork authored this; no
code is written by Cowork.

## Problem

"Which symbols are on source X's current list, and what is that source's value
for them" is currently computed **twice**, with **different snapshot rules**:

- **Action path** (`etl/derive_outlook_action.py`) → `drv_outlook_action` →
  `drv_actionable`. Mostly uses the *latest whole load ≤ D* (bundle-cap), which
  is correct.
- **Signal path** (`drv_ma` source CTEs in `etl/derive.py`) → standing signal
  columns → the rules engine. Uses *per-symbol carry-forward* (`DISTINCT ON
  (tos_symbol) … snapshot_date ≤ D`), which resurrects dropped symbols; SSS is
  additionally broken to NULL.

When the two disagree you get the observed bugs: an action shows REMOVE but the
rule never fires; a symbol dropped from a load still carries an old signal. This
is a design defect (duplicated, divergent computation), not a one-off.

Two more defects ride along:
- **`ticker`/`symbol` vs `tos_symbol` keying.** PS keys on raw `ticker`; ETF,
  II, SSS, CALL key on raw `symbol`; holdings key on `tos_symbol`. Held-detection
  misfires whenever the raw key ≠ `tos_symbol` (violates convention #15).
- **PS REMOVE never reaches the screen** for held positions in some cases, and a
  not-held REMOVE silently erases a competing ADD (see Behavior rules below).

## Solution

One canonical per-source standing layer, `drv_source_standing`, built with **one
rule**, keyed on **`tos_symbol`** always. Both paths read from it. The
technical/numeric indicators that are genuinely signal-path-only (RR bands, SD,
MACDH, moving averages, trade/trend lines) are **out of scope** — they are not
duplicated and stay where they are.

### The one rule (applies to every source; CALL is the only exception)

> Take the **single latest whole load ≤ D** (`snapshot_date =
> MAX(snapshot_date) WHERE snapshot_date ≤ D`). Use **all** symbols in that one
> load. A symbol **absent** from that load is **removed** — never fall back to an
> older load (no per-symbol carry-forward). For ETF/II, apply intra-period change
> patches (`etfchg`/`iichg`) dated after the base snapshot and ≤ D, exactly like
> today's `_state_etf_ii` bundle-cap. NEUTRAL/NULL outlook = not on list.
>
> **CALL exception:** CALL uses its existing 30-day standing window (per-symbol
> most recent row in the window), flagged `window_based`. It is the only source
> that may carry a symbol forward across loads.

### Schema (new table, `db/baseline.sql`)

```
drv_source_standing (
  as_of_date    DATE     NOT NULL,   -- anchor D
  source_code   TEXT     NOT NULL,   -- RR | ETF | II | SSS | PS | CALL
  tos_symbol    TEXT     NOT NULL,   -- normalized; never raw symbol/ticker
  snapshot_date DATE,                -- effective load date the standing came from
  on_list       BOOLEAN  NOT NULL,   -- present & non-neutral on the current load
  weight        NUMERIC,             -- normalized outlook weight (RR/ETF/II/CALL)
  rank          NUMERIC,             -- PS rank (lower = better)
  raw_value     NUMERIC,             -- source metric (e.g. SSS pct_delta)
  signal_sign   INTEGER,             -- SSS-style sign / sign projection
  rank_hl       NUMERIC,             -- SSS Rank HL
  outlook       TEXT,                -- raw outlook token (audit)
  modifier      TEXT,                -- outlook modifier (audit)
  source_run_id BIGINT,
  PRIMARY KEY (as_of_date, source_code, tos_symbol)
)
```

Idempotent: `DELETE WHERE as_of_date = D` then INSERT (convention #2). Only
`on_list = TRUE` rows are written (absence = removed is represented by no row).
Cleanup policy: `EXACT_MATCH` on `as_of_date`.

### Population

A per-source builder writes into `drv_source_standing`. Reuse the existing
formula logic (e.g. SSS's Excel rank/signal math currently in
`_derive_sss_v2_impl`) — only the **row source** (latest whole load ≤ D) and the
**key** (`tos_symbol`) change. Wire `derive_source_standing(session, D)` into
`derive_all()` **before** the action and signal consumers.

| Source | Selection | Fields populated |
|---|---|---|
| RR | dense; `drv_rr WHERE as_of_date=D` + latest `hist_rr` outlook ≤ D | weight, outlook |
| ETF | latest `hist_etf` snapshot ≤ D + `etfchg` patches; NEUTRAL excluded | weight, outlook |
| II | latest `hist_ii` snapshot ≤ D + `iichg` patches; NEUTRAL excluded | weight, outlook |
| SSS | latest whole `hist_sss` load ≤ D | raw_value (pct_delta), signal_sign, rank_hl |
| PS | latest whole `hist_ps` load ≤ D | rank |
| CALL | 30-day window, per-symbol latest (EXCEPTION) | weight, outlook, modifier |

### Consumers rewired

1. **Action path** (`derive_outlook_action.py`): the per-source classifiers
   (`_action_standing`, `_action_rank`, `_action_sss_pct_delta`,
   `_action_call_standing`) stay — but their **input state** comes from
   `drv_source_standing` at D (current) and at the prior load's date (previous),
   instead of each helper re-querying `hist_*`. Held-detection already keys on
   `tos_symbol`, so keys now match by construction.
2. **Signal path** (`drv_ma` CTEs in `derive.py`): replace the `ef`/`ii`/`sh`
   (and `cl`) CTEs with reads from `drv_source_standing WHERE as_of_date=D AND
   source_code=…`. `SSS_signal/SSS_signal_sign/SSS_rank_hl` ← the SSS rows. A
   symbol with no row → columns NULL → correctly off the list.
3. **Asset-class lookups**: re-key `asset_class_ps`/`asset_class_etf` dicts in
   `derive_actionable.py` and `api/routers/dash.py` on `tos_symbol` (they
   currently key on raw ticker/symbol and only "work" because of the bug).
4. **Delete divergent/dead code**: `compute_standing_verdicts`
   (`derive_outlook_action.py`, no caller); retire the now-unused per-source
   state recomputation; retire `drv_sss` once SSS standing lives in
   `drv_source_standing` (DDL + cleanup policy + `drv_ma` view).

### Behavior rules to bake in (from user direction)

- **SSS whole-snapshot:** dropped symbol = removed; never carried from an older
  load. (Fixes the NULL signal bug and the resurrection bug.)
- **SSS INCREASE/REDUCE stay demoted** from the consolidated headline action
  (unchanged — appear under Other Sources only).
- **PS drop emits REMOVE even when not held** (so it is recorded/visible as a
  per-source signal), but the **consolidated/final action ignores a not-held
  REMOVE** and it must not erase a competing ADD on the same symbol.
- **Default Actionable screen:** show actionable symbols sorted by rank with
  **held REMOVE on top**; **not-held REMOVE hidden by default** with a toggle to
  show it.
- **CALL** remains the documented window exception.

## Rollout (one increment per commit; re-derive + verify each)

1. Table + builder for **SSS** only (pilot). Wire SSS action input + SSS signal
   columns to it. Verify SSS REMOVE surfaces and `SSS_signal_sign` is non-NULL.
2. **ETF**, **II** (bundle-cap + patches).
3. **PS** (rank) + the PS REMOVE behavior rules + default-screen sort/visibility.
4. **RR** (dense).
5. **CALL** (window exception).
6. **Cleanup**: delete `compute_standing_verdicts`, dead per-source state code,
   dedupe asset-class lookups, retire `drv_sss`.

Each increment is idempotent, `tos_symbol`-keyed, and committed by the user from
Windows after the tester passes it.

## Out of scope

RR/SD/MACDH/MA technical indicators; AMT$ math; order execution; merging the two
paths beyond the standing layer; the edge-weighting / conviction-sizing
"make-money" ideas (separate future tasks B1–B7 in
`docs/audit/actionable_business_review.md`).
