# TASK 65 — Per-individual-rule scorecard (atomic rules graded standalone)

**You: VS Code developer agent, psql + code.** Log progress in `DEV_HANDOFF.md`; end it
with `ALL_DONE`. **DO NOT COMMIT/PUSH** (user commits from Windows).

## Why (one line)
Composite rules are already graded by forward return (`v_rule_scorecard`), but the
**individual atomic rules are not surfaced** even though their outcomes are already
stored. We want to see each atomic rule's own edge so dead-weight rules can be cut and
strong ones trusted. Background: `docs/audit/bull_calc_analysis.md` §4–5 (P1).

## What already exists (do not rebuild)
- `etl/compute_firing_outcomes.py::_atomic_outcomes` already writes one row per
  `(atomic_rule_id, symbol, date)` into `drv_rule_outcome` with `rule_kind='atomic'`,
  `action_code=NULL`, `fwd_5d_pct`, `fwd_20d_pct`, `hit=(fwd20>0)`. **The data is there.**
- `v_rule_scorecard` (db/baseline.sql) is the pattern to mirror — but it filters/assumes
  composites and infers BUY/SELL direction from the rule_id prefix. Atomic rows have no
  action_code, so direction is **not** inferred the same way (see Decisions below).
- `/api/rules/scorecard` (api/routers/rules.py ~L372) + the Performance screen
  `web/rule_performance.*` are where composite scores are shown today.

## Goal — three small pieces

### 1. New view `v_atomic_rule_scorecard` (db/baseline.sql, next to v_rule_scorecard)
Per atomic rule, over all `drv_rule_outcome WHERE rule_kind='atomic'`:
- `rule_id`, plus `rule_name` / human label joined from `ref_trig_atomic_rule`
  (`atomic_rule_id = rule_id`); include the rule's description if a column exists.
- `n` = count of outcome rows.
- `avg_fwd_5d` = AVG(fwd_5d_pct), `avg_fwd_20d` = AVG(fwd_20d_pct).
- `win_rate` = AVG(hit::int) (share with fwd20 > 0).
- `confidence` tier mirroring v_rule_scorecard's thresholds: `proven` (n≥100 AND
  the 20d return is positive at the lower confidence bound), `promising` (n≥30 AND
  avg_fwd_20d>0), else `unproven`. Reuse v_rule_scorecard's CI math if present.

**Decisions (atomic ≠ composite):**
- No direction adjustment. Atomic features aren't inherently BUY/SELL, so report the
  **raw** avg forward return and raw win_rate. Do NOT sign-flip.
- Keep SQL ≤ 965 bytes per statement (convention #7); split if needed.

### 2. Endpoint `GET /api/rules/atomic-scorecard` (api/routers/rules.py)
Mirror the existing `/api/rules/scorecard` handler. Return all rows, default sort by
`avg_fwd_20d DESC`. No new params required (optional `?min_n=` filter is welcome).

### 3. Screen — add an "Individual rules" panel to `web/rule_performance.*`
A sortable table next to the existing composite scorecard: columns rule name, n,
avg 20d %, win rate, confidence (color the confidence tier the same way the composite
panel does). Default sort by edge (avg_fwd_20d) descending so the best/worst rules are
obvious. Reuse existing styles/helpers — no new color palette.

**Screen placement (intent):** the Performance screen is the *trust/research* screen,
not a daily-trade screen. This panel is where the user decides which signals to believe;
those beliefs then inform what they trust on the Actionable screen. Keep it on
`rule_performance`, beside the composite scorecard — do NOT put per-rule edge on the
Actionable screen.

## Stretch (optional — only if §1–3 are clean; otherwise leave for TASK 66)
**Strength buckets.** Today an atomic outcome is logged whenever the rule had a value,
not by *how strong* the reading was. To answer "is a strong signal better than a weak
one?", bucket each atomic rule's outcomes by the rule's own score level. The score is
the rule's feature column value in `drv_cat_atomic_input` (map via
`ref_trig_atomic_rule.rule_name → column`, same join `_atomic_feature_cols` uses).
If you do this, add it as a second view `v_atomic_rule_strength` (rule_id × score_bucket
→ n, avg_fwd_20d, win_rate); don't overload the §1 view.

## Files expected to change
- `db/baseline.sql` (new view; apply via `python -m db.init_db`)
- `api/routers/rules.py` (new endpoint)
- `web/rule_performance.html` + `web/rule_performance.js` (new panel)

## How to verify (tester reference — run only if user requests a test round)
1. `python -m db.init_db` applies cleanly; `SELECT * FROM v_atomic_rule_scorecard
   ORDER BY avg_fwd_20d DESC LIMIT 20;` returns one row per atomic rule with sane
   numbers (win_rate in 0..1, n>0).
2. Sanity: a rule's `n` equals `SELECT count(*) FROM drv_rule_outcome WHERE
   rule_kind='atomic' AND rule_id = <that rule>`.
3. Cross-check: `avg_fwd_20d` for one rule matches a manual `AVG(fwd_20d_pct)` over its
   rows.
4. `GET /api/rules/atomic-scorecard` returns the same rows as the view; default sorted
   by avg_fwd_20d desc.
5. Performance screen renders the new panel, sortable, confidence tiers colored; no
   console errors; existing composite panel unchanged.
6. Confirm **no rule logic changed** — this is read-only reporting over existing
   outcome data.
