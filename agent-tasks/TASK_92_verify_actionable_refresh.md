# TASK_92 — Verify the intraday TOSL load refreshed the Actionable pipeline

**Type:** verification only (no code change unless a defect is found).
**Author:** Cowork. **Owner:** Developer agent (has Postgres + app).
**Context doc:** `docs/actionable_dataflow_analysis.md`.

## Goal

Ashok loaded an **intraday TOSL** file and wants proof that the Actionable
screen reflects the latest data. Confirm, at the DB level, that:

1. The load ran the `derive_all(D)` cascade for the current anchor `D`.
2. `drv_quote` carries the **fresh intraday price** for `D`
   (`is_intraday = TRUE`, recent `loaded_at`).
3. The **price-driven derived cells** re-computed (RR indices KI/KJ/KK,
   trend_sd/trade_sd, `drv_tn_td_bb_rr.td_tn_bb_action_desc`,
   `drv_actionable.stop_level`).
4. `drv_actionable` for `D` is **not stale** per `find_stale_actionable_dates`.
5. The EOD-anchored fields are **unchanged** (expected intraday) — i.e. confirm
   the system behaved correctly, not that everything moved.

Do **not** "fix" stale-looking EOD fields — intraday immobility is correct.
Only flag a defect if a *price-driven* field failed to refresh, or if the
cascade did not run.

## Steps / queries

Resolve the anchor first; everything keys off it.

```sql
-- A) Anchor date D and whether a new TOSD advanced it
SELECT MAX(export_date) AS anchor_d FROM hist_td;
SELECT MAX(export_date) AS latest_tosl, MAX(loaded_at) AS tosl_loaded_at FROM hist_tl;

-- B) Cascade ran for D? (most recent derive run)
SELECT as_of_date, MAX(finished_at) AS last_derive
FROM meta_derived_run
WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td)
GROUP BY as_of_date;

-- C) drv_quote fresh + intraday for D
SELECT COUNT(*) AS rows,
       SUM((is_intraday)::int) AS intraday_rows,
       MAX(loaded_at) AS quote_loaded_at,
       MAX(export_time) AS latest_export_time
FROM drv_quote
WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td);

-- D) Spot-check 3 liquid held names: price-driven cells present + sane
SELECT a.tos_symbol, q.last_price, q.pct_change, q.is_intraday,
       a.stop_level, rr.td_tn_bb_action_desc AS technical_action,
       ci.trr_idx, ci.mrr_idx, ci.lrr_idx          -- KI/KJ/KK
FROM drv_actionable a
LEFT JOIN drv_quote q
  ON q.tos_symbol = a.tos_symbol AND q.as_of_date = a.as_of_date
LEFT JOIN drv_tn_td_bb_rr rr
  ON rr.tos_symbol = a.tos_symbol AND rr.as_of_date = a.as_of_date
LEFT JOIN drv_cat_atomic_input ci
  ON ci.tos_symbol = a.tos_symbol AND ci.as_of_date = a.as_of_date
WHERE a.as_of_date = (SELECT MAX(export_date) FROM hist_td)
  AND a.tos_symbol IN ('AAPL','NVDA','MSFT')   -- adjust to names actually held
ORDER BY a.tos_symbol;

-- E) Staleness check (mirror the API)
--   python -c "from etl.db import session_scope; from etl.derive_freshness import find_stale_actionable_dates;
--              s=session_scope().__enter__(); print(find_stale_actionable_dates(s))"
```

Also hit the live endpoints against the running app:

```
GET /api/anchor-status            -> expect {is_stale, anchor_date, expected_close}
GET /api/actionable/freshness     -> expect {"stale": false} for the anchor date
GET /api/actionable               -> sample a row; confirm quote_is_intraday=true,
                                     pct_change populated, rr_action present
```

## How to verify (pass criteria)

- **PASS** when: anchor `D` resolves; `meta_derived_run` shows a derive at/after
  the TOSL `loaded_at`; `drv_quote` for `D` has `intraday_rows > 0` and a
  `quote_loaded_at` matching the load; the 3 spot-check names have non-null
  `last_price`, `pct_change`, `stop_level`, `technical_action`, and KI/KJ/KK;
  and `/api/actionable/freshness` returns `stale: false`.
- **Expected-and-correct (not a failure):** Trend/Trade lines, RSI, MACD/MACDH,
  weekly RVOL, the Sources/consolidated_action, P(↑20d), MACRO, and side-panel
  data are **unchanged** from the prior close (no new EOD/periodic file).
- **FAIL / defect** when: the cascade did not run after the load; `drv_quote`
  has no intraday rows for `D`; price-driven cells are NULL where a quote
  exists; or freshness reports `stale: true` (then run a re-derive and re-check).

Record the anchor `D`, the before/after of the spot-check table, the freshness
result, and the endpoint responses in `DEV_HANDOFF.md`. End with `ALL_DONE`.

## Constraints

- Follow `CLAUDE.md` + `docs/agent_handoff_workflow.md`. Cowork has no DB access.
- No commit — Ashok commits from Windows. No tester round unless he asks.
- **Column-name caveat:** `drv_cat_atomic_input` index columns may be named
  `trr_idx/mrr_idx/lrr_idx` or `KI/KJ/KK` per the MA codegen — if the names in
  query D don't resolve, look them up in
  `etl/derive_cat_atomic_input.py` and adjust; this is a read-only check.
