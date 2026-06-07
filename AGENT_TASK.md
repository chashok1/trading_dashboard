# AGENT TASK 27 — make the Performance screen show the rule scorecard

**You (VS Code agent), DB + Windows git.** Write to **`AGENT_RESULT_27.md`**.

Why the screen was empty: `v_rule_performance_window` defaulted its date bounds to
`CURRENT_DATE` (wall clock), but the data is dated 2026 — so `as_of_date <= CURRENT_DATE`
excluded everything if the machine clock < data dates. Fixes made (code already on disk):
- `db/baseline.sql`: window view now anchors to `MAX(as_of_date) FROM drv_rule_outcome`
  (falls back to CURRENT_DATE); plus the existing `v_rule_scorecard`.
- `api/routers/rules.py`: new `GET /api/rules/scorecard` (reads v_rule_scorecard).
- `web/rule_performance.*`: the Performance screen now renders the direction-adjusted
  scorecard (edge_20d) with a caveat banner.

## Step 1 — apply DB changes
```
python -m db.init_db
```
Verify + confirm the wall-clock gap was the cause:
```sql
SELECT CURRENT_DATE AS clock, (SELECT MAX(as_of_date) FROM drv_rule_outcome) AS data_max;
SELECT COUNT(*) FROM v_rule_performance_window(180, NULL, NULL);   -- should now be > 0
SELECT COUNT(*) FROM v_rule_scorecard;                              -- composite rules
```
Paste. (If clock < data_max, that confirms the bug; the fix makes both return rows.)

## Step 2 — verify the endpoints (app auto-reloads on api/ changes)
```
curl -s "http://127.0.0.1:8000/api/rules/scorecard?min_fires=30&limit=5"
curl -s "http://127.0.0.1:8000/api/rules/performance?limit=5"
```
Both should return non-empty JSON. If `/api/rules/scorecard` 404s, the app didn't
reload — restart uvicorn (per start.bat / the `--reload-dir api` runner) and retry.
Paste a couple of rows from the scorecard response.

## Step 3 — confirm in the browser
Open `/rule-performance`, hard-refresh. Confirm the table now shows rows
(Rule / Dir / Fires / Edge 20d / Win % / Raw 20d / Span), sorted by Edge 20d.
One line: does it show data now?

## Step 4 — commit
```
git add db/baseline.sql api/routers/rules.py web/rule_performance.html web/rule_performance.js
git status --porcelain   # confirm only these 4 (+ no AGENT_/agent_/working)
git commit -m "Performance screen: direction-adjusted rule scorecard (/api/rules/scorecard, v_rule_scorecard); anchor v_rule_performance_window to data max date instead of wall clock (fixes empty screen)"
git log --oneline -2
```
Paste status + log.

## Verdict
State: (a) CURRENT_DATE vs data_max (was the wall-clock gap the cause?); (b) both
views now return rows; (c) scorecard endpoint returns data; (d) screen shows data;
(e) committed.

Write `DONE` at the bottom of `AGENT_RESULT_27.md`.
