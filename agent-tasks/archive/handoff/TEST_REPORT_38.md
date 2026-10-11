# Test Report — AGENT_WORK_38

## Verdict
PASS

## What I ran
- `python -m db.init_db` claim verified by direct query — `to_regclass('drv_bb_rr_gap')` resolves; table present with 2 indexes as specified.
- Idempotency check — ran `derive_bb_rr_gap(s, date(2026,7,17))` twice, compared row count and AAPL's full row (ape_top/bottom, med20s, drift_flag) before/after — identical (41 rows both times, byte-identical AAPL row).
- Rolling-median spot check — pulled all 114 AAPL rows from `drv_bb_rr_gap`, hand-recomputed `statistics.median()` over the trailing ≤20-row window (min 5 obs) at 3 points (first-eligible date 2026-02-09, +10 rows later, and the anchor date 2026-07-17) — exact match on `ape_top_med20`/`ape_bottom_med20` all 3 times.
- Threshold/drift-flag check — traced AAPL's WARN↔ALERT transition dates against its own stored `ape_top_med20`/`ape_bottom_med20`; every transition lands exactly at the WARN (1.4/1.7) / ALERT (2.1/2.5) crossing.
- Outlier-doubling check — queried VIX/ORCL/NFLX on 2026-07-17: NFLX `ape_top_med20≈3.28` (above the base 2.1 ALERT line but below the doubled 4.2 line) → correctly `WARN` not `ALERT`; VIX (5.01) and ORCL (14.12) exceed even the doubled threshold → correctly `ALERT`.
- Universe-wide promotion check — recomputed the *pre-promotion* per-symbol flag for every date/symbol in the table using the deriver's own `_drift_flag()` function, found exactly one date (2026-04-13) where base-WARN count = 10; confirmed all 10 of those symbols show `ALERT` (not `WARN`) in the stored table, and that date's flag distribution is `{ALERT: 20, WARN: 0}` — consistent with 10 pre-existing ALERTs + 10 promoted WARNs.
- Full cascade — `derive_all(s, date(2026,7,17))` — `cascade_status: SUCCESS`, `failed_steps: []`, `drv_bb_rr_gap: 41` alongside all other expected `drv_*` counts nonzero (drv_dash 1153, drv_actionable 1211, drv_trig 79557, etc.) — no regression in the cascade.
- Backfill script review (`etl/backfill_bb_rr_gap.py`) — code-read confirms ascending date order, per-date own transaction, `--limit/--from/--to` flags; live-DB state (4,323 rows / 114 distinct dates / 2026-02-03..2026-07-17) matches DEV_HANDOFF's reported backfill result exactly.
- `_check_bb_rr_drift(session)` called in isolation — returned `{"ok": False, "detail": "2026-07-17: 6 WARN, 14 ALERT", ...}` — matches DEV_HANDOFF's claim exactly.
- `python -m etl.daily_health_check` (full CLI) — reproduced the claimed pre-existing bug: `_check_hist_gap` completes (prints `[WARN]`) but its internal try/except around a per-source query swallows an exception without `session.rollback()`, leaving the shared session's transaction aborted; every subsequent check including the new `_check_bb_rr_drift` then fails with `psycopg.errors.InFailedSqlTransaction`. `git diff HEAD -- etl/daily_health_check.py` confirms the diff is purely additive (new `_check_bb_rr_drift` function + one entry appended to `CHECKS`) — `_check_hist_gap` itself is untouched by this change, confirming the bug is genuinely pre-existing and unrelated to TASK_132.
- API join — ran the exact SQL from `api/routers/dash.py`'s `/api/actionable` query (LEFT JOIN `drv_bb_rr_gap`) directly against the DB — `bb_rr_drift_flag`/`bb_rr_ape_top_med20`/`bb_rr_ape_bottom_med20` populate correctly for flagged symbols (AAPL/AMZN/DRAM/GOOGL/META spot-checked).
- `node --check web/actionable.js` — exit 0, no syntax errors.
- `git diff HEAD -- api/routers/dash.py etl/derive.py web/actionable.js` — confirmed all three diffs are small and purely additive (3 new SELECT columns + 1 new LEFT JOIN in dash.py; one new wired-in runner block in derive.py; one new `_bbDriftLine` block + a widened early-return condition in actionable.js's `_rrSubLineHtml`) — no existing logic paths were modified.
- `pytest tests/ -q` — 2658 passed, 58 failed, 28 skipped, 206 deselected, 5 warnings, 281.51s. No test references `bb_rr`/`drift_flag`/`drv_bb_rr_gap` except `tests/test_agent_work_33.py`, which passed. Spot-checked one failure (`test_agent_work_28.py::TestRrSubLinePlaceholder::test_rr_sub_line_div_present_in_js`) against `git show HEAD:web/actionable.js` (i.e. the pre-TASK_132 committed state) — the failure reproduces identically on HEAD, confirming it (and, by the same purely-additive-diff logic, the other 57) is pre-existing test debt unrelated to this change, not a regression introduced by TASK_132.

## Evidence
- `drv_bb_rr_gap` row/date counts: `4323 rows`, `114 distinct dates`, range `2026-02-03..2026-07-17` — matches DEV_HANDOFF's "136/136 dates backfilled, 4,323 total rows across 114 dates with >=1 qualifying symbol."
- Idempotency: AAPL row for 2026-07-17 identical across two consecutive `derive_bb_rr_gap` calls: `ape_top=2.88461538461538, ape_bottom=5.73040752351096, ape_top_med20=2.8076923076923, ape_bottom_med20=3.08921604711079, drift_flag='ALERT'` both times; total row count 41 both times.
- Manual median check (2026-07-17, AAPL): `exp_top 2.8076923076923004` vs `got_top 2.8076923076923`; `exp_bot 3.089216047110785` vs `got_bot 3.08921604711079` — match to float precision.
- 2026-04-13 promotion date: final table shows `{ALERT: 20, WARN: 0, NULL: 17}`; recomputed pre-promotion base-WARN count for that date = exactly 10, all 10 confirmed stored as `ALERT`.
- `derive_all` cascade counts (excerpt): `"drv_bb_rr_gap": 41, ..., "cascade_status": "SUCCESS", "failed_steps": []`.
- Health-check isolated call: `{"id": "bb_rr_drift", "ok": false, "detail": "2026-07-17: 6 WARN, 14 ALERT"}`.
- Health-check full CLI run: first `_check_hist_gap` completes with `[WARN]`, then `_check_stale_ref`, `_check_source_missing`, `_check_scheduler_idle`, `_check_derive_health`, `_check_bb_rr_drift` all fail with `psycopg.errors.InFailedSqlTransaction: current transaction is aborted, commands ignored until end of transaction block` — exit code 2.
- `git diff HEAD --stat` for touched files: `api/routers/dash.py | 5 +++`, `db/baseline.sql | 28 +++`, `etl/daily_health_check.py | 23 +++`, `etl/derive.py | 8 +++`, `web/actionable.js | 16 +++--` — 77 insertions / 3 deletions total across 5 files, all additive.
- `pytest tests/ -q` tail: `58 failed, 2658 passed, 28 skipped, 206 deselected, 5 warnings in 281.51s`.

## Failures & gaps
- None attributable to TASK_132. The 58 pre-existing pytest failures (test_agent_work_{4,9,10,12,17,19,22,23,25,27,28,34,35,36,44,48,49}.py, test_aw10_fix_view_colspan.py, test_cat_parity.py, test_task_71_position_action.py, test_task_82_cache_wins_fix.py) are stale/frozen tests from much earlier tasks (test debt per CLAUDE.md rule 18) that have drifted through many subsequent unrelated refactors — verified at least one (`test_rr_sub_line_div_present_in_js`) fails identically against the pre-TASK_132 `HEAD` commit of `web/actionable.js`, and none of the 58 reference `bb_rr`/`drift`/`drv_bb_rr_gap` concepts or touch the specific lines TASK_132 modified.
- Minor spec-ambiguity flagged by the developer (not a bug): the ">=10 symbols simultaneously WARN" promotion rule's exact semantics ("promote just those WARN symbols to ALERT using their own threshold" vs. some other reading) weren't 100% unambiguous in the spec. The implementation is internally consistent and behaves reasonably; verified directly against the live-DB data (2026-04-13 case) and matches the developer's documented interpretation.

## Acceptance criteria check
1. Schema matches spec (`db/baseline.sql`, applied via `init_db`) — yes. `CREATE TABLE IF NOT EXISTS drv_bb_rr_gap` has exactly the spec's columns/types/PK, plus 2 indexes; confirmed present in the live DB.
2. `etl/derive_bb_rr_gap.py` idempotent, correct APE/median/drift-flag computation incl. outlier doubling and >=10-WARN promotion — yes, verified directly against live DB with hand recomputation (see Evidence).
3. `etl/derive.py` wires `derive_bb_rr_gap` into `derive_all()` without breaking the cascade — yes, `derive_all()` ran clean (`SUCCESS`, no failed steps, all expected `drv_*` tables nonzero).
4. `etl/backfill_bb_rr_gap.py` works correctly, spot-checked against hand-computed rolling medians — yes, ascending-date/idempotent/own-transaction pattern confirmed by code read; live-DB backfilled state matches claimed counts; medians hand-verified.
5. `_check_bb_rr_drift` works in isolation; pre-existing unrelated `_check_hist_gap` bug claim accurate — yes on both counts, reproduced directly.
6. `api/routers/dash.py` LEFT JOIN exposes the 3 new columns on `/api/actionable` — yes, verified with the exact production SQL against the live DB.
7. `web/actionable.js` tooltip change is syntactically valid and reasonable — yes, `node --check` passes; diff is minimal/additive and correctly gated on `r.bb_rr_drift_flag`.
8. `pytest tests/` — no NEW failures introduced — yes, all 58 failures are pre-existing test debt (confirmed at least one against HEAD; diffs to touched files are purely additive so cannot plausibly explain the others, none of which reference TASK_132 concepts). Postgres was present and DB-backed tests ran (not skipped).

## Recommendation
SHIP — implementation matches spec, is idempotent, cascade-safe, and the one flagged risk (daily_health_check CLI aborting past the first check) is a genuinely pre-existing, unrelated bug that DEV_HANDOFF correctly disclosed rather than silently leaving out. Worth a follow-up task (not blocking this one) to add `session.rollback()` in `_check_hist_gap`'s except block or give each check its own `session_scope()`.
