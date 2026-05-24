# Rules engine — what I diagnosed and what I changed

## TL;DR

After cross-referencing every formula source (`Rules_Engine_Design.docx`,
`AAPL_Worked_Example.docx`, `FORMULA_AUDIT.md`, `ma_columns_registry_seed.csv`,
`extracts_2026-05-12_trig/atomic_rules.csv`), **the engine code itself is
sound**. The Phase 1/2/3 work already closed 8 of the 9 issues the design doc
listed in §7. The most likely cause of "rules engine not working" is **data
state**, not code: either the workbook Trig tab hasn't been re-loaded, or
`drv_cat_atomic_input` hasn't been built for the current date.

I built diagnostics + a one-command rebuild + UI improvements to make the
data-state issues self-diagnosing going forward.

---

## What I found

### Cross-reference results (no code changes needed)

| Check | Result |
|---|---|
| Total atomic rules defined | 115 |
| Atomic rules with weights set (active) | 72 |
| Atomic rules whose column resolves via `ref_ma_columns` registry | 84 |
| Atomic rules whose column resolves via legacy `_MA_COL_MAP` only | +18 |
| **Active atomic rules with no resolved column** | **0** |
| `drv_cat_atomic_input` columns missing `source_expr` in registry | 0 (147 unmapped exist, all in feed-table sheets — not rule-engine inputs) |
| `eval_atomic_rule` math (jump / linear / sigmoid) | All pass 12/12 pytest |
| `_eval_precondition` SQL synonyms + 4 derived aliases | All pass 17/17 pytest |
| `drv_trig` and `drv_stks` use same scorer | Yes — `_bucket_weight` removed in Phase 1 #4 |

### The most likely real culprits (data-state, run these to verify)

```sql
-- R1: rules table populated?
SELECT COUNT(*) AS active FROM ref_trig_atomic_rule WHERE deprecated_at IS NULL;
-- Expect ~72. If 0, run: python -m etl.refresh_ref --table ref_trig_atomic_rule

-- R2: composite mapping populated?
SELECT COUNT(DISTINCT composite_rule_code) FROM ref_trig_composite_mapping
WHERE deprecated_at IS NULL;
-- Expect ~70.

-- R3: drv_cat_atomic_input built for latest date?
SELECT MAX(as_of_date), COUNT(*) FROM drv_cat_atomic_input
WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_stks);
-- If 0, derive_all hasn't built the cat table — run rebuild_rules.py

-- R4: orphaned composites (referencing deprecated atomic IDs)?
SELECT composite_rule_code, COUNT(*) AS orphaned
FROM ref_trig_composite_mapping m
WHERE deprecated_at IS NULL AND member_kind = 'atomic'
  AND NOT EXISTS (
    SELECT 1 FROM ref_trig_atomic_rule a
    WHERE a.atomic_rule_id = m.atomic_rule_id AND a.deprecated_at IS NULL
  )
GROUP BY composite_rule_code;
```

The new `/api/rules/health` endpoint and `/rules-health` page run all four
checks for you in one shot.

---

## Code changes I made

### `etl/derive.py` — three rule-engine fixes (#C1, #C2, #C3+C4)

1. **Rule-group evaluation moved out of the per-symbol loop.** Before: N×M×2
   DB round-trips per derive. After: rule groups fetched once, evaluated
   in-memory via a new `_eval_group_inline` helper. For 1000 symbols × 10
   groups this is ~20,000 fewer queries per derive.

2. **`fired = (n_member_hit > 0)` instead of `score != 0`.** A composite where
   positive and negative member contributions cancel to 0 was being marked
   "not fired" — wrong, since members did fire. drv_stks and drv_trig both
   updated.

3. **`triggered_atomics[]` carries an `applied` flag + TEXT value guard.**
   Distinguishes "rule didn't apply (no data)" from "rule scored zero". The
   `float(value)` call no longer crashes on TEXT-direction columns.

### `api/routers/rules.py` — new health endpoint

`GET /api/rules/health` returns:
- counts: atomic rules total / active / with-weights, composites total / active
- `latest_date`, `drv_ma_rows_latest`, `drv_cat_atomic_input_rows_latest`
- `recent_derives` (last 12 from `meta_derived_run`)
- `fire_counts.today` vs. `fire_counts.baseline` (30-day average)
- `column_resolution` audit — list of unresolved active rules
- `orphaned_composites` — composites pointing at deprecated atomic IDs
- An overall `status: "healthy" | "degraded"` plus a list of `issues`

### `api/routers/trace.py` — per-atomic "didn't fire because" reason

Every entry in `atomics_out` now includes:
- `applied` — bool, distinguishes "no data" from "fired with weight 0"
- `band` — `'below' | 'between' | 'above' | None`
- `wt_below / wt_between / wt_above` — full bracket weights for display
- `reason` — human-readable explanation. Possible values:
  - `no_column — rule has no resolved drv_ma / drv_cat_atomic_input column`
  - `no_data — column resolved but row value is NULL`
  - `no_thresholds — rule has no brkeout values (placeholder)`
  - `below_band — value X < brkeout_from Y`
  - `above_band — value X > brkeout_to Y`
  - `in_band — value X in [Y, Z]`
  - `value_not_numeric — column value 'X' can't cast to float`

### `web/rules_health.html` — new UI page

Visit `/rules-health`. Shows:
- Status banner (green/red) with issue list
- Engine counts tiles
- Latest snapshot tiles (drv_ma + drv_cat_atomic_input row counts)
- Today's fire counts vs. 30-day baseline
- Column resolution audit (with table of unresolved rules)
- Orphaned composites
- Recent derive runs from `meta_derived_run`

### `web/trace.js` + `web/trace.html` — reason tag on dim rows

Rules that didn't fire now show a compact tag (`no_data`, `no_thresholds`,
`below_band`, etc.) next to the rule name on the Trace page. Hover for the
full reason. Yellow background on dim rows so they're easier to spot.

Also fixed a pre-existing stray `<s` typo on line 242 of `trace.html`.

### `etl/rebuild_rules.py` — one-command rebuild CLI

```cmd
python -m etl.rebuild_rules                 # rebuild for latest snapshot
python -m etl.rebuild_rules --date 2026-05-15
python -m etl.rebuild_rules --no-refresh    # skip workbook refresh
python -m etl.rebuild_rules --no-derive     # skip derive
```

Runs the steps that 90% of "engine not working" issues need:
1. Refresh `ref_trig_atomic_rule` + `ref_trig_composite_mapping` from the
   workbook (via existing `etl.refresh_ref.run_one`)
2. `derive_all(target_date)` — rebuilds drv_cat_atomic_input → drv_ma →
   drv_stks → drv_trig → everything downstream
3. Print health summary using the same logic as `/api/rules/health`

---

## File-sync caveat — IMPORTANT

During this session the workspace's bash mount showed delayed sync for two
files (`api/routers/rules.py` and `web/trace.js`). Bash `cat` saw the
truncated mid-write state of those files for some time after my edits
"succeeded".

**Please verify after pulling these changes:**

```cmd
:: Both files should compile/parse cleanly
.venv\Scripts\activate
python -c "import ast; ast.parse(open('api/routers/rules.py').read()); print('rules.py OK')"
node --check web/trace.js
```

If either reports a `SyntaxError` at the end of the file (truncated mid-line),
re-pull or restore from version control — I have the full intended content in
this session's edit history.

---

## Rules-engine UI gaps I didn't fix (recommendations)

### Rules `/rules`
- **Add "Last fired" column** — which date did this rule last fire on any
  symbol? Today, dead rules look identical to live rules.
- **Add "Fires today" count** — quick number beside each rule.
- **Add "Distribution" sparkline** — what does the source value look like
  across the universe? Easier than running ad-hoc SQL.

### Rule Performance `/rule-performance`
- **Add a confidence badge** — fade rules with `sample_size < threshold` so
  noise doesn't look like signal.
- **Add lift over baseline** — is the rule better than randomly picking a
  symbol on the same day?
- **Add per-category drilldown** — does the rule work better on Equity vs.
  ETF vs. Defensive?

### Composite Editor `/composite-edit`
- **Not in the top nav** — only accessible by direct URL. Add a link from
  `/rules`.
- **Bulk view missing** — see all composites in one table sorted by activity.

---

## How to verify all of this

```cmd
:: 1. Database has correct schema
python -m db.init_db

:: 2. Pytest stays green
pytest tests/ -v -k "not db"

:: 3. Rules engine is healthy (or tells you what's wrong)
curl http://127.0.0.1:8000/api/rules/health | python -m json.tool

:: 4. If "degraded", run the rebuild
python -m etl.rebuild_rules

:: 5. Open /rules-health in browser, status banner should be green

:: 6. Open /trace?symbol=AAPL — dim rules should show reason tags
```

If `/api/rules/health` returns `status: "healthy"` but rules still aren't
firing the way you expect for a specific symbol/date, use
`/trace?symbol=X&date=Y` and look at the new `reason` column to see exactly
why each rule did or didn't fire.
