# AGENT TASK 31 — apply + verify FRED macro feed (data layer), commit

**You (VS Code agent), DB + internet (FRED) + Windows git.** Write results to
**`AGENT_RESULT_31.md`**. This is an additive data-layer feature that is written
to disk but NOT yet applied/backfilled/committed (previous agent ran sandboxed,
no DB/FRED access). UI is intentionally out of scope.

Run from project root with venv active:
`cd C:\Ashok\Invest\Projects\trading-dashboard` then `.venv\Scripts\activate`.

Files changed (on disk — do NOT rewrite):
- `db/baseline.sql` — `ref_macro_series`, `hist_macro` tables + `v_macro_latest` view (appended at end).
- `db/seeds_macro.sql` — NEW, seeds ~20 FRED series.
- `etl/fetch_macro.py` — NEW, FRED pull → `hist_macro` (stdlib urllib).
- `config/settings.py` — `fred_api_key` field. `.env.example` — `FRED_API_KEY` docs.
- `api/routers/macro.py` — NEW `GET /api/macro`. `api/main.py` — registered `macro` router.
- `docs/macro_feed_logic.md` — NEW. `CLAUDE.md` — lookup row + 2026-06-07 note.

## Step 0 — FRED key
```
findstr /B /C:"FRED_API_KEY" .env
```
If empty: ask the user for their free FRED key (https://fred.stlouisfed.org/docs/api/api_key.html),
then `echo FRED_API_KEY=THEIR_KEY>> .env`. Never commit `.env` (gitignored). Do not invent a key.

## Step 1 — apply schema + seed
```
python -m db.init_db
SELECT to_regclass('hist_macro'), to_regclass('ref_macro_series'), to_regclass('v_macro_latest');  -- all not null
SELECT grp, COUNT(*) FROM ref_macro_series GROUP BY grp ORDER BY grp;   -- ~21 rows across 6 groups
```
Paste.

## Step 2 — backfill from FRED
```
python -m etl.fetch_macro --full
SELECT COUNT(*) rows, COUNT(DISTINCT series_id) series, MAX(obs_date) newest FROM hist_macro;
SELECT series_id, latest_value, latest_date, chg_pct FROM v_macro_latest ORDER BY grp, sort_order;
```
Paste the summary + the v_macro_latest rows. Expect ~21 series; daily ones
(DGS10, VIXCLS, SP500) within a few business days, monthly ones (CPI, UNRATE) older — normal.
Note any series that FAILED to fetch (run continues + exits non-zero); a retired
FRED id can be disabled in `db/seeds_macro.sql`.

## Step 3 — endpoint (start app if needed: `uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir api`)
```
curl -s http://127.0.0.1:8000/api/macro
```
Paste the `index` and `rates` groups from the response. Confirm server log shows
`router loaded: macro`. Expect `{"as_of":"YYYY-MM-DD","groups":{...}}` with populated values.

## Step 4 — commit
```
python -c "import ast; ast.parse(open(r'config\settings.py').read()); ast.parse(open(r'api\main.py').read()); print('OK')"
python -m py_compile etl\fetch_macro.py api\routers\macro.py && echo OK_compile
git add db/baseline.sql db/seeds_macro.sql etl/fetch_macro.py config/settings.py .env.example api/routers/macro.py api/main.py docs/macro_feed_logic.md CLAUDE.md AGENT_TASK.md
git status --porcelain   # confirm only these (+ AGENT_RESULT_31.md); .env must NOT appear
git commit -m "Add FRED macro feed: hist_macro + ref_macro_series + /api/macro (data layer)"
git log --oneline -2
```
(If `.git\index.lock`/`HEAD.lock` exists from a prior agent, delete via Explorer first.)
Paste status + log.

## Verdict
(a) tables+view exist & seeded; (b) hist_macro populated, v_macro_latest has values;
(c) /api/macro returns grouped tiles, console/log clean; (d) committed. If FRED auth
fails or a series 404s, STOP and paste the exact error + failing series ids.

Write `DONE` at the bottom of `AGENT_RESULT_31.md`.
