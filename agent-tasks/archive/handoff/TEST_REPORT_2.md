# Test Report — AGENT_WORK_2 (TASK_91)

## Verdict
PASS

## What I ran
- `python check_task91.py` (scratchpad) — queried ref_corr_asset and drv_usd_correlation for 2026-06-23
- `python check_idempotency.py` (scratchpad) — re-derived 2026-06-23 and compared before/after values
- `pytest tests/test_task_87_corr_rematch.py tests/test_task_90_histy_corr.py -v --tb=short` — 52 passed, 2 skipped, 0 failed in 5.07s
- `git diff HEAD -- etl/derive_usd_correlation.py` — confirms histy: branch present (added by TASK_90), TASK_91 made no further etl/ changes
- `git status --short` — confirms only seeds_corr.sql and test files are TASK_91 changes; all uncommitted per workflow

## Evidence

Check 1 — seeds_corr.sql source_spec values confirmed:
- USD: `["histy:^NYICDX","yfinance:^NYICDX"]` — PASS
- SPX: `["histy:^SPX","yfinance:^SPX"]` — PASS
- Brent: `["histy:BZ=F","yfinance:BZ=F"]` — PASS
- Gold: `["histy:GC=F","yfinance:GC=F"]` — PASS
- Bitcoin: `["histy:BTC-USD","yfinance:BTC-USD"]` — PASS
- CRB: `["yfinance:DBC"]` (no histy:) — PASS

Check 2 — ref_corr_asset in DB matches seeds exactly (verified via psycopg query)

Check 3 — drv_usd_correlation for 2026-06-23:
```
bitcoin   : w15=-0.2908  w30=-0.7952  w90=-0.4533
brent     : w15=-0.6845  w30=-0.8119  w90=0.2175
crb       : w15=-0.7768  w30=-0.8563  w90=0.3045
gold      : w15=-0.6329  w30=-0.8891  w90=-0.5936
spx       : w15=-0.2560  w30=-0.2520  w90=0.0156
```
- Gold w15=-0.633 recovered from -0.51 (pre-TASK_91); delta to provider (-0.70) narrowed from 0.19 to 0.067
- SPX w15=-0.256 not regressed (matches TASK_90 value)
- Brent w15=-0.685 (delta 0.016 vs provider -0.70; excellent)
- Bitcoin w15=-0.291 (delta 0.040 vs provider -0.33; good)

Check 4 — idempotency: re-derive returned 5 rows, all values byte-identical before/after

Check 5 — pytest: `52 passed, 2 skipped in 5.07s`
- 2 skipped are `test_api_w15_matches_db` / `test_api_w30_matches_db` in TASK_87; skip is by design (API anchor = 2026-06-23, fixture anchor = 2026-06-18, skip path triggered intentionally)

Check 6 — etl/derive_usd_correlation.py: git diff vs HEAD shows TASK_90's histy: branch addition (committed baseline is pre-TASK_90); TASK_91 made no additional etl/ changes. git status confirms only db/seeds_corr.sql and test files are TASK_91 modifications.

## Failures & gaps
None.

## Acceptance criteria check
- seeds_corr.sql: USD/SPX/Brent/Gold/Bitcoin have histy: primary; CRB yfinance-only — yes, confirmed in file and DB
- ref_corr_asset in DB matches seeds — yes, exact match verified
- Gold w15 recovered toward -0.70: -0.633 (was -0.51 pre-TASK_91), delta narrowed from 0.19 to 0.067 — yes
- SPX not regressed: w15=-0.256 (same as TASK_90 output) — yes
- Brent not regressed: w15=-0.685 (matches provider -0.70 within 0.016) — yes
- Bitcoin not regressed: w15=-0.291 (matches provider -0.33 within 0.040) — yes
- Idempotency: two derives produce identical results — yes
- pytest 52 passed / 2 skipped / 0 failed — yes, exact count matches expectation
- No etl/ code changed in TASK_91 (histy: branch pre-existed from TASK_90) — yes
- Seeds use ON CONFLICT DO UPDATE (applied idempotently by init_db) — yes

## Recommendation
SHIP
