# AGENT TASK 32 — apply + verify macro fetch throttle + manual refresh, commit

**You (VS Code agent), DB + internet (FRED) + Windows git.** Write results to
**`AGENT_RESULT_32.md`**. Builds on Task 31 (macro feed, already applied). This
round adds a rate-limit safety throttle, a tunable throttle setting in
`ref_settings`, a run log, and a manual-refresh endpoint. Code is on disk;
apply + verify + commit here. UI button is intentionally still deferred.

Run from project root with venv active:
`cd C:\Ashok\Invest\Projects\trading-dashboard` then `.venv\Scripts\activate`.

Files changed (on disk — do NOT rewrite):
- `db/baseline.sql` — NEW table `meta_macro_fetch` (fetch run log).
- `db/seeds_macro.sql` — seeds `ref_settings.macro_fetch_min_interval_min = '360'` (DO NOTHING).
- `etl/fetch_macro.py` — throttle (no-op if a real run started within the window),
  `--force` / `--min-interval`, logs each real run to `meta_macro_fetch`. Window
  precedence: `--min-interval`/arg → `ref_settings` → code default 360 (6h).
- `api/routers/macro.py` — `GET /api/macro` now returns `last_fetch`; new
  `POST /api/macro/refresh` (throttled; for the future Refresh button).
- `docs/macro_feed_logic.md`, `CLAUDE.md` — docs.

## Step 1 — apply schema + seed
```
python -m db.init_db
SELECT to_regclass('meta_macro_fetch');                                  -- not null
SELECT setting_value FROM ref_settings WHERE setting_name='macro_fetch_min_interval_min';  -- 360
```
Paste.

## Step 2 — verify the throttle (this is the key test)
```
:: baseline count
SELECT COUNT(*) FROM meta_macro_fetch;

:: (a) forced run -> should hit FRED, add exactly ONE meta row
python -m etl.fetch_macro --force
SELECT COUNT(*), MAX(started_at), MAX(status) FROM meta_macro_fetch;

:: (b) immediate plain run -> should print "throttled ... use --force" and add NO row
python -m etl.fetch_macro
SELECT COUNT(*) FROM meta_macro_fetch;   -- unchanged vs (a)

:: (c) short-window override proves tunability -> fetches again, +1 row
python -m etl.fetch_macro --min-interval 0
SELECT COUNT(*) FROM meta_macro_fetch;
```
Expect: (a) +1 row, status `ok` (or `partial` if a series fails); (b) NO new row +
a `throttled` log line; (c) +1 row. Paste the three counts + the throttled log line.

## Step 3 — endpoints (app auto-reloads on api/ change; else start uvicorn)
```
curl -s http://127.0.0.1:8000/api/macro
curl -s -X POST http://127.0.0.1:8000/api/macro/refresh
```
Expect: GET payload now has a `"last_fetch"` block (started_at/status/rows_inserted).
POST right after Step 2 should return `{"skipped":true,"reason":"throttled","age_min":...}`
(because it ran moments ago). Paste the `last_fetch` block + the POST response.

## Step 4 — commit
```
python -m py_compile etl\fetch_macro.py api\routers\macro.py && echo OK_compile
git add db/baseline.sql db/seeds_macro.sql etl/fetch_macro.py api/routers/macro.py docs/macro_feed_logic.md CLAUDE.md AGENT_TASK.md
git status --porcelain   :: confirm only these (+ AGENT_RESULT_32.md); .env must NOT appear
git commit -m "Macro feed: FRED fetch throttle (meta_macro_fetch + ref_settings) + last_fetch in GET /api/macro + POST /api/macro/refresh"
git log --oneline -2
```
(Delete `.git\index.lock`/`HEAD.lock` from Explorer first if present.)
Paste status + log.

## Verdict
(a) meta_macro_fetch exists + setting seeded ✓
(b) throttle proven: forced run logs, immediate plain run is a no-op, --min-interval 0 overrides ✓
(c) GET returns last_fetch, POST /refresh respects throttle ✓
(d) committed ✓
If the throttle does NOT skip on the immediate plain run, STOP and paste the
fetch_macro output + `SELECT * FROM meta_macro_fetch ORDER BY started_at DESC LIMIT 3;`.

Write `DONE` at the bottom of `AGENT_RESULT_32.md`.
