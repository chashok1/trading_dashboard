# drv_cat_atomic_input — design & rules

Authoritative deep-dive for the rule-engine atomic-input layer that mirrors
Excel `MA` columns **JF..NP** and **QE..QT**.

CLAUDE.md index pointer: see *Atomic-input column derivation*.

---

## What it is

`drv_cat_atomic_input` is the per-(date, symbol) materialization of every
**atomic-input** column on the Excel MA tab — the rule scores that feed
`drv_trig`, `drv_stks`, and the composite/group resolver. Each column is one
of seven formula shapes documented below, all driven by `ref_trig_atomic_rule`
(loaded from the workbook's Trig tab).

Before 2026-05-27 the table was populated by `_derive_cat_table_impl` →
`ma_codegen.build_dml` → `INSERT…SELECT` whose `source_expr` came from
`ref_ma_columns`. Almost every output column had `source_expr = NULL`, so the
codegen silently skipped them (warning to stderr) and the row landed all-NULL.
That path is now retired for this table. Replacement is
`etl/derive_cat_atomic_input.py`.

---

## Pipeline (5 passes)

```
derive_all(D)
  …
  drv_quote   ──┐
  drv_ma      ──┤   (both required as inputs)
                ▼
  drv_cat_atomic_input        ← Python deriver (Pass 1 + Pass 2)
                ▼
  trend_trade_rules           ← UPDATE adds QE/QJ/QM/QN/QR
                ▼
  drv_cat_atomic_input_pass3  ← UPDATE adds QF/QG/QK/QL/QO/QP/QQ/QS/QT
                ▼
  drv_dash / drv_stks / …
```

Step | Where | What
---|---|---
1 — working set | `WORKING_SET_SQL` in `derive_cat_atomic_input.py` | `SELECT` from hist_td / hist_tw / drv_quote / hist_rr (`DISTINCT ON (symbol)` latest snapshot ≤ D) plus per-symbol `percentile_cont(0.5)` median of `standard_dev`.
2 — intermediates | `compute_intermediates(row)` | Per-row Python arithmetic for the MA-sheet derived inputs (AC, AD, AG, AH, AI, BB..CA, EE, EO..ER, FR, GB, …). Cheaper than re-deriving every one in SQL.
3 — Pass-1 outputs | `COLUMN_SPECS_PASS1` + `eval_specs(...)` | trig_ifs / negate / passthru / composite / zero_guard / dma. trig_ifs delegates to `etl.derive.eval_atomic_rule` (same engine that powers `drv_trig` and `drv_stks`).
4 — Pass-2 outputs | `COLUMN_SPECS_PASS2` | Composites that read Pass-1 outputs in the same row (KD, KT, LB, LK, LW, MI, MQ, MS, …).
5 — Pass-3 update | `PARM_LOOKUP_SQL` | One SQL UPDATE joining `ref_param_lookup` four times to fill QF/QG/QK/QL/QO/QP/QQ/QS/QT.

QE/QJ/QM/QN/QR are NOT in `COLUMN_SPECS` — they're already correctly populated by `_derive_trend_trade_rules_impl` in `derive.py`. Pass-3 reads what that step writes.

---

## Formula taxonomy

Every output column maps to exactly one of these shapes:

Shape | Used by | Behaviour
---|---|---
`trig_ifs` | JN, JQ, JV, JW–KC, KE, KF, KL, KU–KW, KX–LA, LC–LH, LJ, LP–LR, MA, MB, MD, ME, MG, MH, MK–MN, NE, NL, NM | Look up `ref_trig_atomic_rule` by `rule_name`; evaluate via local `_eval_trig_ifs()` — see "Scoring divergence" below. Supports `jump` (six-clause IFS) / `linear` / `sigmoid` modes.

### Scoring divergence from `eval_atomic_rule` (important)

`drv_trig` / `drv_stks` use `etl.derive.eval_atomic_rule()`, which implements a **3-clause** `jump`:

```
v < lo   -> wt_below
v > hi   -> wt_above
else     -> wt_between
```

The Excel MA-tab `trig_ifs` formulas implement a **6-clause** signed IFS:

```
v >= hi   ->  wt_above       v <= -hi  -> -wt_above
v >= lo   ->  wt_between     v <= -lo  -> -wt_between
v >= 0    ->  wt_below       v <  0    -> -wt_below
```

For symmetric atomic rules (e.g. `Trade-Rule` with `lo=1, hi=5, wt_below=1, wt_between=2, wt_above=3`) and `v = -4.5`:
- Excel: `-wt_between = -2`
- `eval_atomic_rule`: `wt_below = 1` (since `v < lo`)

Different sign, different magnitude. This deriver implements the 6-clause locally in `_eval_trig_ifs` to match Excel. The 3-clause path is still used by `drv_trig`/`drv_stks` — that's a separate pre-existing behaviour we have NOT touched.

Take-away: a `drv_cat_atomic_input.trade_rule` value of `-2` will not equal `drv_trig.score` for the same atomic_rule_id. They measure different things; do not equate them in queries.
`zero_guard_trig_ifs` | KM, KN, KO, KP, KQ, KR, KS, NK | Same as `trig_ifs` but returns `0.0` when any guard input is `NULL` or `0`. Mirrors Excel's `IFS(input=0, 0, …)` pattern that prevents bogus IV/HV/percentile rules on zero-impVol securities.
`trig_ifs_dma` | MU (50-DMA), MW (200-DMA), MY (52-Wk Low), MZ (52-Wk High) | Volatility-scaled comparator: scores by where `price` sits in `[MA - hi·vol, MA - lo·vol, MA, MA + lo·vol, MA + hi·vol]`. Local function `_eval_trig_ifs_dma` — does not go through `eval_atomic_rule` because the comparator is on a *function of two values*, not a single ratio.
`negate` | JO, JR, JU, LI, LL, LM, LX, MJ, MO, MP, MR, MT | `out = -1 * twin_value`. Twin DB column name passed as `input`.
`passthru` | QH, QI | `out = row[source_key]`. Used for raw `hist_td` slope mirrors.
`sign_zero_neg` | JG, JH (and JI as approximation pending AN sourcing) | `0 → -1`, otherwise `sign(x)`.
`cond_passthru` | JJ planned (`AX=1 ? AW : 0`) | `out = row[val_key] if row[flag_key]==1 else 0`. Pending AX/AW sourcing.
`composite` | JS, JT, KD, KG, KH, KT, LB, LK, LW, MC, MF, MI, MQ, MS, MV, MX, NA, NB, all Pass-2 entries | Arbitrary Python lambda `f(row, out) -> value`. Sees both raw inputs (`row`) and already-computed outputs (`out`). Used for IFS/AND/OR over JF–NP siblings.

### Trig sheet lookup conventions

The Excel formula uses `XLOOKUP(<key>$1, Trig!$B$4:$B$144, …)` where `<key>$1` is **either**:

- the **source-data column's row-1 header** (e.g. `XLOOKUP(AX$1, …)` → MA!AX1 = "BBThresh_CO_Days" → matches Trig col B "BBThresh_CO_Days"), or
- the **output column's own row-1 header** (e.g. `XLOOKUP(JW$1, …)` → MA!JW1 = "BRR% Rule") when one source feeds multiple rule variants (BRR% Rule, BRR% LRR, BRR% R2 all read EE but use different thresholds).

The loader (`etl/load_raw.py::load_trig_rules`) mirrors Trig col L into both `rule_name` AND `ma_column_name` in `ref_trig_atomic_rule`. The COLUMN_SPECS table in this deriver simply names the rule by `rule_name`.

`!`-prefixed names in Trig col L are renamed to `not_` form in the workbook
(2026-05-27); see CLAUDE.md "common errors" if you see legacy `!Trade Rule`
strings — run `python -m etl.refresh_ref --table ref_trig_atomic_rule`.

---

## QE..QT block

Excel col | DB column | How populated
---|---|---
QE | `trade_trend_sd_rule` | `_derive_trend_trade_rules_impl` Pass 1 (existing).
QF | `tn_td_rule_action` | Pass-3 SQL: `ref_param_lookup` `table_name='tn_td_rule'` keyed by QE.
QG | `tn_td_rule_desc` | Pass-3 SQL (same join, `.description` col).
QH | `a_bb_bot_slope` | Pass-1 passthru from `hist_td.a_bb_bot_slope`.
QI | `a_bb_top_slope` | Pass-1 passthru from `hist_td.a_bb_top_slope`.
QJ | `bb_rng_strk_rule` | `_derive_trend_trade_rules_impl` Pass 1.
QK | `bb_rng_strk_action` | Pass-3 SQL: `table_name='bb_range'` keyed by QJ.
QL | `bb_rng_strk_desc` | Pass-3 SQL.
QM | `bull_rr_action` | `_derive_trend_trade_rules_impl` Pass 1.
QN | `not_bull_rr_action` | `_derive_trend_trade_rules_impl` Pass 1.
QO | `risk_rng_longs_action` | Pass-3 SQL: conditional XLOOKUP via QJ/QM/QN.
QP | `rr_bull_bear` | Pass-3 SQL: `'B'` if QJ≥2, `'!B'` if QJ≥0, else NULL.
QQ | `rr_desc` | Pass-3 SQL: description matching QO branch.
QR | `td_tn_bb_rr_action` | `_derive_trend_trade_rules_impl` Pass 2.
QS | `td_tn_bb_action_desc` | Pass-3 SQL: `table_name='td_tn_bb_rr_action'`.
QT | `td_tn_bb_action_seq` | Pass-3 SQL: same row, `.seq` column.

If `ref_param_lookup` is missing the `td_tn_bb_rr_action` table_name slot, QS/QT come out NULL — that's expected pre-seed, fix by adding rows to the Parm tab in the workbook and re-running `python -m etl.refresh_ref --table ref_param_lookup`.

---

## Idempotency

```python
DELETE FROM drv_cat_atomic_input WHERE as_of_date = :d
INSERT INTO drv_cat_atomic_input (...) VALUES (...)  -- executemany in 500-row batches
```

Then `_derive_trend_trade_rules_impl` runs its two `UPDATE`s, then Pass-3
runs its UPDATE. Every step is `DELETE…INSERT` or `UPDATE`-with-`SET`, so
re-running for date D yields identical rows — convention #3.

---

## Gaps & deferred columns

The first cut covers ~80% of JF–NP. The following columns are intentionally deferred until source data is wired up; they'll come back as `NULL`:

DB column | Excel col | Blocker
---|---|---
`bb_threshold` | JJ | AX/AW (BB threshold flag + value) not yet sourced from hist_td (lives in raw bb_streak struct).
`bbthresh_co_days`, `bbthresh_co_days2` | JK, JL | AX = days-count extracted from string col AU; needs hist_td loader extension.
`trade_cross_over`, `trend_cross_over` | JM, JP | Needs EF/J/I/BZ (prev close + today's high/low + 3D close) from drv_quote (EF), hist_y (J, I), and BZ intermediate (already computed). Wirable in next iteration.
`bbhighlow_sd_rule`, `bbhighlow_days_rule` | LN, LO | AO/AM need a_bb_high_low / a_bb_high_low_days passthrough (already in hist_td — just plumb through).
`bbstreak_days_rule*` | LS–LV | AZ days component of BB streak; same loader gap as JK.
`bbhighdays`, `bblowdays` | LY, LZ | AQ/AR extracted from BB streak struct.
`trr_idx`, `mrr_idx`, `lrr_idx` | KI, KJ, KK | ES/ET/EU need DQ/DM/DR (SD-normalized risk-range indices) which aren't sourced yet.
`up_resistance`, `down_resistance` | NC, ND | Needs CG/CH/BA/EH/EI/AC composite — wirable as `composite` lambda once EH/EI guaranteed populated.
`vs_price`, `vs_volume_spike`, `vs_volatility`, `vs_days`, `vs_lt_outlook_rule` | NF–NJ | FH = string "NN.NN.NN.NN" not currently parsed to four numeric FI/FK/FL/FM cols.
`short_term_oulook_if_lt_bullish/_bearish` | NN, NO | Composite over NK/NL/NM — wirable once those resolve cleanly.

Asymmetric scoring is also a known minor divergence: `NL Current Volume Rule` in Excel uses `-1/4` multiplier on the negative side. The current deriver uses the standard symmetric `trig_ifs`. Score sign is correct; magnitude differs by ¼ in the negative tail. Track in `tests/test_cat_parity.py` (future).

---

## Adding a new output column

1. Confirm the source values exist in `hist_td` / `hist_tw` / `drv_quote` (or add them to `WORKING_SET_SQL` if not).
2. If the formula is a Trig-IFS, confirm the rule lives in `ref_trig_atomic_rule` (col L of Trig in the workbook). If not, add a row to Trig and run `python -m etl.refresh_ref --table ref_trig_atomic_rule`.
3. Append the spec tuple to `COLUMN_SPECS_PASS1` (or `COLUMN_SPECS_PASS2` if it reads other JF–NP outputs).
4. Add the column to `db/baseline.sql` (within the `ADD COLUMN IF NOT EXISTS` block).
5. Run `python -m db.init_db` to apply DDL.
6. Re-derive: `python -c "from etl.derive import derive_all; from db.session import SessionLocal; from datetime import date; s=SessionLocal(); derive_all(s, date(2026,4,30)); s.commit()"`
7. Verify with the parity script (see below).

---

## Parity-check procedure

The workbook `Tickers 2026-04-30.xlsx` is the reference. To verify a row:

```python
from openpyxl import load_workbook
wb = load_workbook('Tickers 2026-04-30.xlsx', data_only=True)
ws = wb['MA']
# For each symbol on row R, compare:
#   wb.MA[R][JN] (excel)  vs  drv_cat_atomic_input.trade_rule (deriver)
```

A `scripts/parity_drv_cat_atomic_input.py` follow-up is planned in `tests/test_cat_parity.py`. Until then, the inline `_probe_api.py` style scripts at repo root are fine.

Acceptable parity threshold: exact match on `jump`-mode rules; ±0.01 tolerance on `linear`/`sigmoid` to absorb float-precision drift.

---

## File map

File | Role
---|---
`etl/derive_cat_atomic_input.py` | This deriver — COLUMN_SPECS + helpers + entrypoints.
`etl/derive.py::_derive_trend_trade_rules_impl` | QE/QJ/QM/QN/QR (unchanged).
`etl/derive.py::eval_atomic_rule` | Shared evaluator (jump/linear/sigmoid).
`db/baseline.sql` (lines ~1318–1459, ~2204–2237) | Table DDL + idempotent ALTER block.
`docs/ma_columns_v2.csv` | Per-MA-column lineage doc (header, source sheet, Excel formula).
`docs/rules_logic.md` | Composite + group resolver (consumes this table).
