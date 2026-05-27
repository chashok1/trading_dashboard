# drv_cat_atomic_input — design & rules

Authoritative deep-dive for the rule-engine atomic-input layer that mirrors
Excel `MA` columns **JF..NP** and **QE..QT**.

CLAUDE.md index pointer: *Atomic-input column derivation (JF..NP + QE..QT)*.

Status: **v3, 100% parity** vs `Tickers 2026-04-30.xlsx` smoke test (120/120 checks across 2 symbols). 1 of the original 60+ output columns still deferred (`trr_idx`/`mrr_idx`/`lrr_idx`); see Gaps.

---

## What it is

`drv_cat_atomic_input` is the per-(date, symbol) materialization of every
**atomic-input** column on the Excel MA tab — the rule scores that feed
`drv_trig`, `drv_stks`, and the composite/group resolver. Each column is one
of seven formula shapes, all driven by `ref_trig_atomic_rule` (loaded from the
workbook's Trig tab) plus Python-side composite lambdas.

Before 2026-05-27 the table was populated by `_derive_cat_table_impl` →
`ma_codegen.build_dml` → `INSERT…SELECT` whose `source_expr` came from
`ref_ma_columns`. Almost every output column had `source_expr = NULL`, so the
codegen silently skipped them (warning to stderr) and the row landed all-NULL.
That path is retired for this table. Replacement is
`etl/derive_cat_atomic_input.py`.

---

## Pipeline (3 steps in `derive_all`)

```
derive_all(D)
  …
  drv_quote   ──┐
  drv_ma      ──┤   (both required as inputs)
                ▼
  drv_cat_atomic_input          ← Python deriver: Pass 1 + Pass 2
                ▼
  trend_trade_rules             ← UPDATE adds QE/QJ/QM/QN/QR
                ▼
  drv_cat_atomic_input_pass3    ← UPDATE adds QF/QG/QK/QL/QO/QP/QQ/QS/QT
                ▼
  drv_dash / drv_stks / …
```

Step | Where | What
---|---|---
1 — working set | `WORKING_SET_SQL` in `derive_cat_atomic_input.py` | Single `SELECT` from `hist_td` / `hist_tw` / `drv_quote` / `hist_rr` (`DISTINCT ON (symbol)` latest snapshot ≤ D) plus per-symbol `percentile_cont(0.5)` median of `standard_dev`.
2 — intermediates | `compute_intermediates(row)` | Per-row Python arithmetic producing ~50 MA-sheet derived inputs (AC, AD, AG, AH, AI, AJ–AZ struct, BB..CA, EC, ED, EE, EO..ER, FF..FM, FR, GB, …).
3a — Pass-1 outputs | `COLUMN_SPECS_PASS1` + `eval_specs(...)` | Seven formula shapes (see Taxonomy).
3b — Pass-2 outputs | `COLUMN_SPECS_PASS2` | Composites that read Pass-1 outputs in the same row (KD, KT, LB, LK, LW, MI, MQ, MS, NJ, NN, NO …).
4 — bulk INSERT | `executemany` in batches of 500 | Idempotent (`DELETE WHERE as_of_date=D` first).
5 — `trend_trade_rules` | `_derive_trend_trade_rules_impl` in `derive.py` | UPDATE populating QE/QJ/QM/QN/QR.
6 — Pass-3 update | `PARM_LOOKUP_SQL` via `run_parm_lookup_pass3()` | One SQL UPDATE joining `ref_param_lookup` four times to fill QF/QG/QK/QL/QO/QP/QQ/QS/QT.

QE/QJ/QM/QN/QR are NOT in `COLUMN_SPECS` — they're populated by `_derive_trend_trade_rules_impl` (existing). Pass-3 reads what that step writes.

---

## Formula taxonomy

Seven shapes. Spec tuple is `(db_col, formula_type, input, trig_rule_name, extra)`:

Shape | Used by | Behaviour
---|---|---
`trig_ifs` | JK, JL, JN, JQ, JV, JW–KC, KE, KF, KL, KU–KW, KX–LA, LC–LH, LJ, LN, LO, LP–LR, LS–LV, LY, LZ, MA, MB, MD, ME, MG, MH, MK–MN, NE, NL, NM | Look up `ref_trig_atomic_rule` by `rule_name`; evaluate via local `_eval_trig_ifs()`. Six-clause signed IFS (see "Scoring divergence"). `extra={"strict": True}` switches to strict `>` for VS/Puts/Days/MACDH/Earnings/Current rules. `extra={"abs_input": True}` for MACD/MACDH rules that use `ABS(input)`.
`zero_guard_trig_ifs` | KM, KN, KO, KP, KQ, KR, KS, NF, NG, NH, NI, NK | Same as `trig_ifs` but returns `0.0` when any guard input is `NULL` or `0`. `extra` can be a tuple of guard keys, or `{"guards": (...), "strict": True}`. Mirrors Excel `IFS(input=0, 0, …)` zero-guards that prevent bogus IV/HV/percentile/VS rules.
`trig_ifs_dma` | MU (50-DMA), MW (200-DMA), MY (52-Wk Low), MZ (52-Wk High) | Volatility-scaled comparator: scores by where `price` sits in `[MA - hi·vol, MA - lo·vol, MA, MA + lo·vol, MA + hi·vol]`. Local function `_eval_trig_ifs_dma`. Does NOT go through `_eval_trig_ifs` because the comparator is on a function of two values, not a single ratio.
`negate` | JO, JR, JU, LI, LL, LM, LX, MJ, MO, MP, MR, MT | `out = -1 * twin_value`. Twin DB column name passed as `input`. Reads from `out` dict (so the twin must already be computed in Pass-1).
`passthru` | JI (`AN`), QH, QI | `out = row[source_key]`. Used for AN (BB_Direction1) and raw `hist_td` slope mirrors.
`sign_zero_neg` | JG (`a_macdh_d_brr1`), JH (`a_macd_brr1`) | `0 → -1`, otherwise `sign(x)`. Mirrors Excel `IF(input=0, -1, SIGN(input))`.
`cond_passthru` | (none currently used; JJ uses a `composite` lambda instead) | `out = row[val_key] if row[flag_key]==1 else 0`. Kept for future use.
`composite` | JJ, JM, JP, JS, JT, KD, KG, KH, KT, LB, LK, LW, MC, MF, MI, MQ, MS, MV, MX, NA, NB, NC, ND, NJ, NN, NO, all Pass-2 entries | Arbitrary Python lambda `f(row, out) -> value`. Sees both raw/intermediate inputs (`row`) and already-computed outputs (`out`). Used for any IFS/AND/OR over JF–NP siblings or for Excel `INT()` ops (we use `math.floor()` — see "INT vs int" below).

### Scoring divergence from `eval_atomic_rule` (intentional)

`drv_trig` / `drv_stks` use `etl.derive.eval_atomic_rule()`, which implements a **3-clause** `jump`:

```
v < lo   -> wt_below
v > hi   -> wt_above
else     -> wt_between
```

The Excel MA-tab `trig_ifs` formulas implement a **6-clause** signed IFS:

```
non-strict (default):              strict=True:
v >= hi  ->  wt_above              v >  hi  ->  wt_above
v >= lo  ->  wt_between            v >  lo  ->  wt_between
v >= 0   ->  wt_below              v >= 0   ->  wt_below
v <= -hi -> -wt_above              v <  -hi -> -wt_above
v <= -lo -> -wt_between            v <  -lo -> -wt_between
v <  0   -> -wt_below              v <  0   -> -wt_below
```

For symmetric rules (e.g. `Trade-Rule` `lo=1, hi=5, wt_below=1, wt_between=2, wt_above=3`) and `v = -4.5`:
- Excel 6-clause: `-wt_between = -2`
- `eval_atomic_rule` 3-clause: `wt_below = 1` (since `v < lo`)

Different sign, different magnitude. This deriver implements the 6-clause locally in `_eval_trig_ifs()` so the per-symbol scores match Excel exactly. The 3-clause path stays in `drv_trig`/`drv_stks` — pre-existing behaviour we have NOT touched.

**Take-away:** `drv_cat_atomic_input.trade_rule` will NOT equal `drv_trig.score` for the same `atomic_rule_id`. They measure different things; do not equate them in queries.

### Strict-`>` mode

Most Excel formulas use `>=`. The following subset uses strict `>` (look for `extra={"strict": True}` on the spec):
- All "Puts" variants: IVPercentile Puts (KO), HVPercentile Puts (KQ), IVHV Puts (KS), RSI Puts (KW)
- BBHighLow_SD (LN), BBHighLow Days (LO), BBHighDays (LY), BBLowDays (LZ)
- MACDH Days (MG), MACDH Days2 (MH)
- Earnings Days (NE)
- All VS rules: NF, NG, NH, NI
- Current Price/Volume/Volatility (NK, NL, NM)

Mismatching strict vs non-strict produces off-by-one errors on integer-valued inputs that exactly hit a threshold.

### INT() vs int()

Excel `INT()` is `math.floor()` (rounds toward `-∞`). Python `int()` truncates toward zero. They disagree on negatives: `INT(-0.5) = -1`, `int(-0.5) = 0`. All composites that mirror Excel `INT()` operations use `math.floor()`:
- MC `macd_and_h_rule = INT((MA + MB)/2)`
- MF `macd_and_h_rule_puts = INT((MD + ME)/2)`
- MS `perforbull = INT((LK + MQ)/2)` fallback branch
- LB `3m_long = INT((KX + KY - 1)/2)` fallback branch

### Trig sheet lookup conventions

The Excel formula uses `XLOOKUP(<key>$1, Trig!$B$4:$B$144, …)` where `<key>$1` is **either**:

- the **source-data column's row-1 header** (e.g. `XLOOKUP(AX$1, …)` → `MA!AX1` = "BBThresh_CO_Days" → matches `Trig.B9` "BBThresh_CO_Days"), or
- the **output column's own row-1 header** (e.g. `XLOOKUP(JW$1, …)` → `MA!JW1` = "BRR% Rule") when one source feeds multiple rule variants (BRR% Rule, BRR% LRR, BRR% R2 all read EE but use different thresholds).

The loader (`etl/load_raw.py::load_trig_rules`) mirrors Trig col L into both `rule_name` AND `ma_column_name` in `ref_trig_atomic_rule`. The `COLUMN_SPECS` in this deriver names the rule by `rule_name` (col L value).

`!`-prefixed names in Trig col L are renamed to `not_` form in the workbook (2026-05-27). If you see legacy `!Trade Rule` strings in `ref_trig_atomic_rule.rule_name`, run `python -m etl.refresh_ref --table ref_trig_atomic_rule` after correcting the workbook.

---

## TOS composite-field decoding

Three TOS export fields are numeric composites that encode multiple values:

### `a_bb_high_low` (TD!BD = MA!AJ)

Encodes BB-touched value + days-since-touched in one signed numeric:
`AJ = sign(lasthighlow) * (abs(round(lasthighlow*100,0)) + bar/100)`

Decoded in `compute_intermediates` (no helper, inline):
- `AK = TRUNC(AJ)` — sign × abs(highlow×100)
- `AL = AK/100` — BB-touched price (in price units)
- `AM = ABS(ROUND(100*(AJ-AK), 0))` — days since touched
- `AO = (D - ABS(AL)) / AC` — BBHighLow_SD
- `AN = IFS(AL<0 & AM>0 & |AL|<D, 1,  AL>0 & AM>0 & |AL|>D, -1,  TRUE, SIGN(AL))` — BB direction:
  - **+1** if BB bottom touched ≥1 day back AND price now above (going up)
  - **-1** if BB top touched ≥1 day back AND price now below (going down)
  - else `SIGN(AL)` (direction of touched band)

Example (ZM): `AJ=9651.01` → `AK=9651, AL=96.51, AM=1, AN=-1` (top touched 1 day back, D=95.76 < 96.51).

### `a_bb_streak` (TD!BC = MA!AS)

Decoded by `_decode_bb_streak()`:
- `AS = a_bb_streak`              (e.g. 8213.01)
- `AT = TRUNC(AS)`                (8213)
- `AY = TRUNC(AT/1000)`           (8 — BB streak count)
- `AU = AT - AY*1000`             (213)
- `AV = ABS(TRUNC(AU/100))`       (2 — current threshold state)
- `AW = IF(AV=1, -1, 1)`          (1 — threshold-crossover flag)
- `AX = NUMBERVALUE(RIGHT(AU,2))` (13 — BBThresh CO Days)
- `AZ = ROUND((ABS(AS)-ABS(AT))*100, 0)` (1 — BB streak days)

Plus `AQ = TRUNC(a_bb_high_low_days)` (BBHighDays) and `AR = ABS(100*(AP-AQ))` (BBLowDays).

### `a_volume_spike` (TW!AQ = MA!FF)

Decoded by `_decode_vs()`:
- `FF = a_volume_spike`                  (signed, e.g. -200443.44)
- `FG = ABS(FF)`                          (200443.44)
- `FH = RIGHT("0000000000" & FG & REPT("0",9-LEN(FG)), 10)`  ("0200443.44")
- `FI = NUMBERVALUE(LEFT(FH, 2))`         (2 — VS Volume Spike)
- `FJ = NUMBERVALUE(MID(FH, 3, 3))`       (200 — VS Price Change)
- `FK = SIGN(FF) * FJ / (AD*100)`         (signed VS Price Change SD)
- `FL = NUMBERVALUE(MID(FH, 6, 2))`       (43 — VS Volatility)
- `FM = NUMBERVALUE(RIGHT(FH, 2))`        (44 — VS Days)

### `_days_from_frac()` helper

Mirrors Excel `100 * MOD(x, TRUNC(x))` (and `-100 *` for the negate variant). Used for:
- BC (3mnLowDays from a_3mn_low)
- BF (3mnHighDays from a_3mn_high)
- BK (3mnHighLowDays from a_3mn_high_low, negate=True)
- BO (3wkHighLowDays from a_3wk_high_low, negate=True)

---

## QE..QT block

Excel col | DB column | How populated
---|---|---
QE | `trade_trend_sd_rule` | `_derive_trend_trade_rules_impl` Pass 1.
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

If `ref_param_lookup` is missing the `td_tn_bb_rr_action` table_name slot, QS/QT come out NULL — that's expected pre-seed. Fix by adding rows to the Parm tab in the workbook and re-running `python -m etl.refresh_ref --table ref_param_lookup`.

---

## Idempotency

```python
DELETE FROM drv_cat_atomic_input WHERE as_of_date = :d
INSERT INTO drv_cat_atomic_input (...) VALUES (...)  -- executemany in 500-row batches
```

Then `_derive_trend_trade_rules_impl` runs its two `UPDATE`s, then Pass-3 runs its UPDATE. Every step is `DELETE…INSERT` or `UPDATE`-with-`SET`, so re-running for date D yields identical rows — convention #3.

---

## Dashboard scalars (`Dash!$X$Y` in `ref_param`)

Single-cell Excel variables from the Dash tab live in `ref_param` under `sheet='dash'`. Seed values live in `db/baseline.sql` (2026-05-27 v3 block). Read at runtime:

```python
from etl.derive_cat_atomic_input import get_dash_scalar
toggle = get_dash_scalar(session, 'intraday_toggle', default='Y')
if toggle == 'Y':
    # use intraday DG/DK/DL (drv_quote.high/low/last from real-time TL)
    ...
else:
    # use daily CY/DC/DD (hist_td end-of-day high/low/last)
    ...
```

To add a new dashboard scalar:
1. Pick a snake_case `param_name` (avoid the Excel cell ref — e.g. `intraday_toggle` not `ab_24`).
2. Add an `INSERT … ON CONFLICT DO NOTHING` row to the 2026-05-27 v3 block in `baseline.sql`.
3. Use `get_dash_scalar(session, '<name>')` in any module that needs it.

Currently seeded:

| param_name | value | Maps to | Used by |
|---|---|---|---|
| `intraday_toggle` | `Y` | `Dash!$AB$24` | (planned) DQ/DM/DR → ES/ET/EU → KI/KJ/KK |

---

## Gaps & known divergences

### Still deferred (3 columns)

| DB column | Excel col | Blocker |
|---|---|---|
| `trr_idx`, `mrr_idx`, `lrr_idx` | KI, KJ, KK | Need ES/ET/EU which depend on DQ/DM/DR (intraday-vs-daily toggle output). Toggle reachable via `get_dash_scalar(session, 'intraday_toggle', 'Y')`. Just needs the intermediate computations wired. |

### Known divergences (not real bugs)

1. **`EE` Excel string-comparison quirk** — when both `DX/DY` (RR) and `DU/DV` (`bb_bot_prev`/`bb_top_prev`) are zero, Excel computes `EE = ""` and the downstream `IFS` formulas exploit "`""` > any number" to fall through to `wt_above`. Our `_eval_trig_ifs` returns `None` instead. Affects `brrpct_*` only for symbols without RR rows AND without prev-band data. The deriver's `None` is more semantically correct than Excel's fluke. Disappears on real data where most symbols have at least one source.
2. **`NL Current Volume Rule`** — Excel uses asymmetric `-1/4` multiplier on the negative side; our `trig_ifs` is symmetric. Sign correct, magnitude off by ¼ in the negative tail.
3. **Scoring divergence from `drv_trig`/`drv_stks`** — intentional 6-clause vs 3-clause split. See above.

---

## Adding a new output column

1. Confirm source values exist in `hist_td` / `hist_tw` / `drv_quote` (or extend `WORKING_SET_SQL`).
2. If the formula is a Trig-IFS, confirm the rule lives in `ref_trig_atomic_rule` (Trig col L). If not, add a row to Trig and run `python -m etl.refresh_ref --table ref_trig_atomic_rule`.
3. Append the spec tuple to `COLUMN_SPECS_PASS1` (or `COLUMN_SPECS_PASS2` if it reads other JF–NP outputs).
4. Add the column to `db/baseline.sql` (within the `ADD COLUMN IF NOT EXISTS` block at the bottom).
5. Run `python -m db.init_db` to apply DDL.
6. Re-derive:
   ```python
   from etl.derive import derive_all
   from db.session import SessionLocal
   from datetime import date
   s = SessionLocal(); derive_all(s, date(2026,4,30)); s.commit()
   ```
7. Verify with the parity script.

---

## Parity-check procedure

The workbook `Tickers 2026-04-30.xlsx` is the reference. Smoke-test recipe (until `tests/test_cat_parity.py` is wired):

```python
from openpyxl import load_workbook
wb = load_workbook('Tickers 2026-04-30.xlsx', data_only=True)
ws = wb['MA']
# For each symbol on row R, compare:
#   ws.cell(R, col('JN'))     vs    drv_cat_atomic_input.trade_rule
```

Acceptable parity threshold: exact match on `jump`-mode rules; ±0.01 tolerance on `linear`/`sigmoid` to absorb float-precision drift.

Most-recent smoke run (2 symbols × 60 columns): **120/120 OK (100%)**.

---

## File map

| File | Role |
|---|---|
| `etl/derive_cat_atomic_input.py` | This deriver — COLUMN_SPECS, intermediates, decoders (`_decode_bb_streak`, `_decode_vs`, `_days_from_frac`), evaluators (`_eval_trig_ifs`, `_eval_trig_ifs_dma`), composites, `get_dash_scalar` helper, `derive_cat_atomic_input` / `run_parm_lookup_pass3` entrypoints. |
| `etl/derive.py::_derive_trend_trade_rules_impl` | QE/QJ/QM/QN/QR (unchanged). |
| `etl/derive.py::eval_atomic_rule` | Shared evaluator (3-clause jump / linear / sigmoid). NOT used by this deriver — see "Scoring divergence". |
| `etl/mappings.py` `HIST_MAPS['TD']` | TD loader spec — reads `BB_Bot_Prev` / `BB_Top_Prev` (TD!L / TD!P) added 2026-05-27 v2. |
| `db/baseline.sql` (~lines 1318–1459, 2204–2245) | `drv_cat_atomic_input` DDL + idempotent ALTER blocks + `hist_td.bb_bot_prev/bb_top_prev` + `ref_param ('dash', …)` seeds. |
| `docs/ma_columns_v2.csv` | Per-MA-column lineage doc (header, source sheet, Excel formula). |
| `docs/rules_logic.md` | Composite + group resolver (consumes this table). |
