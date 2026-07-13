# TASK_121 — Infer user actions from CS/F position deltas (no manual logging)

## Context

`user_action_log` has 1 row and the user does not want to log actions
manually. But CS and F position files already record what he actually did:
qty deltas between consecutive snapshots ARE his trades. Diagnosis section C
used a crude version of this (`v_user_action_performance`, 10-day window).
Make transaction-inferred actions the official personal track record.

## Goal

An ETL step that turns position deltas into inferred trade rows, matched to
the recommendation active that day, powering the Performance screen's "Your
actions" panel across all loaded history.

1. `db/baseline.sql`: new table `drv_inferred_action`
   (`as_of_date, tos_symbol, account, source_feed` [CS|F], `qty_delta`,
   `est_dollar` [qty_delta × that day's price], `inferred_action` [BUY|SELL],
   `rec_action` [drv_actionable.consolidated_action active that date, nullable],
   `stance` [FOLLOWED | CONTRADICTED | NO_SIGNAL],
   `fwd_5d_pct`, `fwd_20d_pct`, PK `(as_of_date, tos_symbol, account)`).
2. New `etl/derive_inferred_actions.py` (wired into `derive_all` cascade or
   nightly step — developer's call, document it): for each consecutive pair of
   snapshots per (account, tos_symbol) in `hist_cs` and `hist_f`:
   - qty decrease → SELL, increase → BUY; ignore deltas whose est_dollar <
     a `ref_settings.inferred_action_min_dollar` (default 100) to skip
     dividend-reinvest noise;
   - guard against splits: if |qty ratio| is near a clean split ratio while
     market_value is ~unchanged, skip and log a warning (reuse any existing
     handling from `etl/mark_sales.py` / `drv_cs_realized_gain` where possible);
   - stance: FOLLOWED if inferred direction matches rec_action family
     (BUY↔ADD/INCREASE, SELL↔REDUCE/REMOVE), CONTRADICTED if opposite,
     NO_SIGNAL if no actionable row / HOLD;
   - forward returns from `drv_ma.last_price` (same convention as
     compute_firing_outcomes; leave NULL until enough forward history).
   Idempotent per date-range rebuild.
3. Repoint `v_user_action_performance` (or add `v_inferred_action_performance`
   and switch the API) so `GET /api/rules/my-actions` aggregates from
   `drv_inferred_action`: by stance and by action family — n, avg fwd_5d/20d,
   total est_dollar. Keep the old view readable for comparison.
4. `web/rule_performance.js` "Your actions" panel: show the stance split —
   headline numbers "When you FOLLOWED the system: avg X% (n) · when you
   CONTRADICTED it: avg Y% (n)" above the existing table.

## Files expected to change

- `db/baseline.sql`, NEW `etl/derive_inferred_actions.py`, wiring in
  `etl/derive.py`/scheduler, `api/routers/rules.py`,
  `web/rule_performance.js`, `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db`; run the new derive over full history;
   `SELECT stance, count(*), round(avg(fwd_20d_pct),2) FROM
   drv_inferred_action GROUP BY stance;` returns plausible rows spanning
   Feb→now (hundreds, not 10 days).
2. Spot-check 3 known sales from `drv_cs_realized_gain` — each has a matching
   SELL row with sensible est_dollar and stance.
3. A dividend-reinvest-sized delta (< min_dollar) produces no row.
4. /rule-performance "Your actions" shows the FOLLOWED vs CONTRADICTED
   headline; `/api/rules/my-actions` returns the new shape.
5. Re-running the derive for the same range does not duplicate rows.
