# TASK_106 — Actionable: API efficiency

Source: `docs/audit/actionable_screen_review.md` — F1, F2, F5, F7.
Prereq: TASK_105 done. Queue: 104 → 105 → **106** → 107 → 108 → 109 → 110.

Goal: one round-trip for bulk actions, lazy-load the heavy MACRO detail, make
the conviction threshold tunable, normalize the priority scale.

Files expected to change: `api/routers/dash.py`, `web/actionable.js`,
`db/seeds_*.sql` (one ref_settings row), `db/baseline.sql` if the seed
convention requires it.

## Items

1. **Bulk action endpoint (F1).** `POST /api/actionable/bulk-action` with
   `{symbols:[...], as_of_date, user_action, action_code?, user_notes?}`.
   Server loops the existing forensic-snapshot INSERT (same code path as
   `post_actionable_action` — factor the body into a helper, don't duplicate)
   in one transaction; returns `{ok, results:[{symbol, log_id}]}`. Client
   `bulkAction()` makes one call instead of N sequential `inlineAction`s;
   keep `inlineAction` for single-row buttons. Respect convention #7
   (SQL ≤ 965 bytes — parametrized insert per symbol, not one giant statement).
2. **Lazy MACRO detail (F2).** New `GET /api/actionable/macro-detail?symbol=&date=`
   returning `{macro_detail, macro_howto}`. In `get_actionable()`: stop
   computing/shipping `macro_detail` + `macro_howto` per row (skip the per-row
   `_compute_macro` detail work when derive-time `macro_action` exists; the
   new endpoint computes detail on demand). **Keep in the row payload**:
   `macro_value/conf/turn`, the three nets, `monthly_score`, `macronet`,
   `monthly_scores_json` (sparkline renders in the grid, not on hover).
   Client: `_buildMacroPopHtml` fetches lazily with a `Map` cache keyed
   `sym@date` (same pattern as `_srcDataCache` / `_rrDetailCache`); show a
   "loading…" popover state on first hover.
3. **Conviction threshold (F5).** Seed `ref_settings`
   (`conviction_proven_edge_min`, default `0.5`); surface to the client
   (implementer's choice — piggyback an existing bootstrap fetch or a small
   settings endpoint). `_hasPositiveEdge` reads it instead of hardcoded `0.5`.
4. **Priority scale (F7).** `_computePriority`: with `priority_rank` present
   use `pr * 1e6 + amt`; align the client fallback to the same scale
   (`seq * 1e6 + amt`, not `1e12`) so server- and client-ranked rows can't
   cross tiers when amt ≥ $1M.

## Guardrails

- `python -c "import ast; ast.parse(open('api/routers/dash.py').read())"`
  after edits; `node --check web/actionable.js` on Windows.
- `python -m db.init_db` idempotent after the seed; no other schema changes.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. Bulk-select 5 rows → Done → network tab shows ONE POST; DB:
   `SELECT tos_symbol, user_action FROM user_action_log WHERE as_of_date=:d ORDER BY acted_at DESC LIMIT 5;`
   → all 5 present with correct action_code.
2. `GET /api/actionable?date=<D>` response contains **no**
   `macro_detail`/`macro_howto` keys; payload size measurably smaller
   (compare content-length before/after). MACRO cell hover still shows the
   full breakdown; second hover on the same symbol makes no new request.
3. `UPDATE ref_settings SET setting_value='5.0' WHERE setting_name='conviction_proven_edge_min';`
   → reload → Proven conviction filter returns fewer/zero rows; restore to 0.5.
4. Default sort order unchanged vs pre-task for a date where all rows have
   `priority_rank` (spot-check top 10 symbols before/after).
5. `pytest tests/` — no new failures.
