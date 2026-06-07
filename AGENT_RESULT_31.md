# AGENT RESULT 31 — FRED macro feed applied + verified

## Step 0 — FRED key
`FRED_API_KEY` found in `.env` (user-supplied).

## Step 1 — Schema + seed
```
Tables: ('hist_macro', 'ref_macro_series', 'v_macro_latest')
('fx_cmdty', 2)
('index', 4)
('inflation', 4)
('jobs', 3)
('rates', 5)
('risk', 3)
```
21 rows across 6 groups. All 3 objects exist.

## Step 2 — Backfill from FRED
```
hist_macro summary: (143359, 20, datetime.date(2026, 6, 5))
```
143,359 observations, 20 distinct series, newest 2026-06-05.

**Failed series:** `RU2000PR` — HTTP 400 (retired FRED id). Disabled in `db/seeds_macro.sql` (`enabled=FALSE`) and re-seeded via `init_db`.

v_macro_latest sample (index + rates groups):
- SP500: 7584.31 @ 2026-06-04 (+0.41%)
- NASDAQCOM: 26830.96 @ 2026-06-04 (−0.09%)
- DJIA: 51561.93 @ 2026-06-04 (+1.73%)
- DGS10: 4.47% @ 2026-06-04 (−0.45%)
- DGS2: 4.05% @ 2026-06-04 (−0.74%)
- T10Y2Y: 0.38% @ 2026-06-05 (−9.52%)
- DFF: 3.62% @ 2026-06-04

## Step 3 — Endpoint
`GET /api/macro` returns `{"as_of":"2026-06-05","groups":{...}}` with all 6 groups populated (index, rates, inflation, jobs, risk, fx_cmdty). RU2000PR excluded (disabled). Server running clean.

## Step 4 — Compile + commit
- `ast.parse` on `config/settings.py` + `api/main.py`: OK
- `py_compile` on `etl/fetch_macro.py` + `api/routers/macro.py`: OK_compile
- Committed: `Add FRED macro feed: hist_macro + ref_macro_series + /api/macro (data layer)`

## Verdict
(a) tables + view exist & seeded ✓  
(b) hist_macro populated (143,359 rows), v_macro_latest has values for 20/21 series ✓  
(c) /api/macro returns grouped tiles, server clean ✓  
(d) committed ✓  

Note: `RU2000PR` is a retired FRED series id (HTTP 400). Disabled in catalog — no replacement needed unless a valid Russell 2000 FRED id is identified.

DONE
