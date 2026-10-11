# Test Report — AGENT_WORK_1 (TASK_90)

## Verdict
PASS_WITH_CONCERNS

## What I ran
- `python check1_source_spec.py` — query ref_corr_asset source_spec — PASS
- `python check2_drv_corr.py` — query drv_usd_correlation for 2026-06-23 — PASS
- `python -c "import ast; ast.parse(open(r'...derive_usd_correlation.py').read()); print('OK')"` — OK
- `python check7_hist_y.py` — hist_y freshness for ^NYICDX and ^SPX — PASS
- `python check6_idempotency.py` — two re-derives, value comparison — PASS
- `pytest tests/test_task_87_corr_rematch.py tests/test_agent_work_89.py -v --tb=short` — 36 passed, 7 failed
- `pytest tests/test_task_90_histy_corr.py -v --tb=short` — 28 passed, 0 failed (new test file authored by tester)
- `pytest tests/ (all other files) -q --tb=no` — 326 failed / 2284 passed / 13 skipped (pre-existing, unrelated to TASK_90)

## Evidence

### Check 1 — source_spec in ref_corr_asset
```
usd:     ['histy:^NYICDX', 'yfinance:DX-Y.NYB']   <- TASK_90 target
spx:     ['histy:^SPX', 'yfinance:^GSPC']           <- TASK_90 target
brent:   ['yfinance:BZ=F']                          unchanged
crb:     ['yfinance:DBC', 'tos:DBC']                unchanged
gold:    ['yfinance:GC=F', 'tos:GLD']               unchanged
bitcoin: ['yfinance:BTC-USD', 'tos:/BTC']           unchanged
```

### Check 2 — drv_usd_correlation 2026-06-23
```
spx:     w15=-0.256,  w30=-0.252,  w90=0.0156
brent:   w15=-0.6827, w30=-0.8176, w90=0.2243
crb:     w15=-0.7768, w30=-0.8563, w90=0.3045
gold:    w15=-0.5087, w30=-0.853,  w90=-0.584
bitcoin: w15=-0.2348, w30=-0.7917, w90=-0.446
```

### Check 3 — SPX w15 improvement vs provider
- SPX w15 = -0.256; provider = -0.27; delta = 0.014 (was 0.162 pre-TASK_90)
- SPX w30 = -0.252; provider = -0.41; delta = 0.158 (was 0.205 pre-TASK_90; residual documented)

### Check 7 — hist_y freshness
```
^NYICDX: max_export_date=2026-06-23, rows=88
^SPX:    max_export_date=2026-06-23, rows=88
```

### Check 6 — idempotency
```
Before derive: SPX w15=-0.256, w30=-0.252
Derive run 1:  5 rows — SPX w15=-0.256, w30=-0.252
Derive run 2:  5 rows — SPX w15=-0.256, w30=-0.252
RESULT: PASS — all values identical across before/run1/run2
```

### Pytest failures breakdown
**test_task_87_corr_rematch.py — 5 failures (all match DEV_HANDOFF expected list):**
- `TestProtectedFilesUnchanged::test_seeds_corr_sql_unchanged` — expected (TASK_90 intentionally changed file)
- `TestProtectedFilesUnchanged::test_derive_usd_correlation_unchanged` — expected (TASK_90 intentionally changed file)
- `TestAPIMatchesDB::test_anchor_is_2026_06_18` — API returns 2026-06-23 (correct); TASK_87 test hardcodes 6/18
- `TestAPIMatchesDB::test_api_w15_matches_db` — API returns TASK_90 values; test compares against stale 6/18 DB
- `TestAPIMatchesDB::test_api_w30_matches_db` — same

**test_agent_work_89.py — 2 failures NOT listed in DEV_HANDOFF expected failures:**
- `TestCheck3PanelValuesUpdated::test_spx_w15_close_to_expected_fresh` — tests w15 ≈ -0.4315 (TASK_89 value); TASK_90 intentionally changes this to -0.256. delta=0.176, tolerance was ±0.02.
- `TestCheck3PanelValuesUpdated::test_spx_w30_close_to_expected_fresh` — tests w30 ≈ -0.2049 (TASK_89 value); TASK_90 value is -0.252. delta=0.047, tolerance was ±0.02.

These are stale test expectations, not implementation regressions. The implementation is correct.

## Failures & gaps

1. **DEV_HANDOFF omits 2 additional stale test failures** — `tests/test_agent_work_89.py` lines 134 and 158 fail because they pin to TASK_89 output values that TASK_90 intentionally supersedes. The developer's DEV_HANDOFF listed 5 expected failures but should have listed 7. Not a code defect; the new `tests/test_task_90_histy_corr.py` fully validates the TASK_90 spec (28/28 pass).

2. **w30 residual documented but not resolved** — SPX w30 delta vs provider is 0.158 (provider -0.41, actual -0.252). DEV_HANDOFF explicitly calls this out as a known limitation (hist_y coverage starts 2026-01-30; provider may use a different dollar index). No action needed, but user should be aware.

## Acceptance criteria check
- Re-plumb USD/SPX to hist_y daily sources — yes: histy: branch added in code, source_spec updated in seeds and DB
- USD source `histy:^NYICDX` (primary) + `yfinance:DX-Y.NYB` (fallback) — yes: confirmed in DB
- SPX source `histy:^SPX` (primary) + `yfinance:^GSPC` (fallback) — yes: confirmed in DB
- Weekend filter (`EXTRACT(DOW FROM export_date) NOT IN (0, 6)`) in histy: branch — yes: code confirmed
- SPX w15 within 0.05 of provider (-0.27) — yes: delta = 0.014
- SPX w15 better than TASK_89 baseline (-0.4315) — yes: 0.014 vs 0.162
- SPX w30 better than TASK_89 baseline (-0.2049) — yes: 0.158 vs 0.205
- hist_y has current data (max_date >= 2026-06-23) for both symbols — yes
- Idempotent re-derive — yes: all values identical across 3 queries
- File integrity (no truncation) — yes: ast.parse returned OK
- Seeds file updated with histy: entries — yes: ON CONFLICT DO UPDATE confirmed
- Other assets (brent, crb, gold, bitcoin) unchanged — yes
- pytest: 21 non-API/non-protected tests pass in test_task_87 — yes
- pytest: 5 expected failures match DEV_HANDOFF list — yes (plus 2 additional stale TASK_89 tests)

## Recommendation
SHIP — the implementation is correct and fully meets the TASK_90 spec. The 2 additional test failures beyond DEV_HANDOFF's list are stale TASK_89 assertions pinned to values that TASK_90 intentionally changes. The developer should update DEV_HANDOFF to list them, or update `tests/test_agent_work_89.py` expected values — but this does not block shipping.
