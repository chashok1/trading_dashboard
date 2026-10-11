# Test Report — AGENT_WORK_39 (TASK_133 Dashboard Cockpit, Phases 1/2/3/5)

## Verdict
PASS_WITH_CONCERNS

## What I ran
- `python -c "SELECT 1"` via `etl.db.session_scope` — DB reachable.
- Direct SQL: `SELECT MIN/MAX/AVG(rv21), COUNT(*) FROM drv_market_stat` — reproduced independently.
- Direct SQL + import of `etl.derive_category_perf` internals (`_trading_calendar`, `_load_positions_and_flows`, `_build_category_map`, `_build_series`) to independently reconstruct the Phase 5.2 no-trade-category window from raw `hist_cs`/`hist_f`/`hist_cst`/`hist_ft` rows (not trusting the stored `drv_category_perf` row).
- `uvicorn api.main:app` on a scratch port (8010, then 8011) — hit `/api/portfolio/summary`, `/api/marketbar`, `/api/macro-areas`, `/api/macro` live; process killed after use.
- `python -c "import ast; ast.parse(...)"` on all 5 new + 4 modified `.py` files; `node --check web/market_bar.js`.
- `python -m db.init_db` — full baseline + all seed files including `db/seeds_cockpit.sql`.
- Re-ran `derive_market_stat`/`derive_category_perf` twice each for the anchor date (2026-07-31), diffing stored rows before/after each pass.
- Ran the full `derive_all()` cascade once for the anchor date end-to-end.
- `git status`, `git log -3`, `git diff --stat -- web/actionable.js`.

## Evidence

**1. rv21 sanity (Phase 3.1)** — independently queried, not copy-pasted from handoff:
```
count rows=114, non-null rv21=95
MIN=9.0597  MAX=19.5093  AVG=14.8022   date range 2026-02-02..2026-07-31
```
Matches the handoff's numbers exactly and sits inside the spec's 8–25 band. Spot-checked last 10 days: rv10/rv21/rv63 all two-digit, vix/vrp plausible (16–20 / 1.5–7.4). No units-bug signature (no three-digit or sub-1 values).

**2. TWR-no-trade-category exact match (Phase 5.2)** — reproduced from raw tables, not from the stored `drv_category_perf` row:
```
by_date (asset_class='Unmapped'), 2026-07-23 .. 2026-07-31:
  465982.90, 464349.09, 464891.93, 461501.52, 459855.62, 480434.18
naive V_end/V_start-1 = 0.031012468483285538
chain-linked product-1  = 0.031012468483285538   diff = 0.0
```
Matches the handoff and the stored row (`twr_1w=0.0310124684832855`) exactly. **However**, I found the tested category's actual composition is bigger and messier than the handoff describes:
- Handoff says the tested category is "the NON40O26D/M/P + CRAK positions." In fact the "Unmapped" asset_class bucket on this date also includes **DESK, IPAY, NOBL, VYM, and FXH** (verified: summing all 8 symbols' 07-31 values reproduces the stored $480,434.18 exactly; summing only the 4 named symbols does not).
- Within the "confirmed zero Buy/Sell" window, **FXH (held every day 07-23→07-30, ~$7.4–7.7k) disappears entirely from the 07-31 snapshot, while CRAK/DESK/IPAY/NOBL appear for the first time ever** (no row anywhere, ever, in `hist_cs`/`hist_f` before 07-31) — with **zero** rows in `hist_cst`/`hist_ft` for any of these 5 symbols (checked with no action/date filter at all, not just Buy/Sell). This is a real composition swap worth ~$20k+ that the flow-tracking logic has no record of.
- The TWR-vs-naive identity is guaranteed by algebra for *any* window where every day's netflow is 0 (it's a pure telescoping product), regardless of *why* the flow is 0. So this "exact match" is real but doesn't by itself prove the flow-attribution logic is correct in general — it happens to pass on a window that (unbeknownst to the handoff's own description) contains an untracked position swap. This doesn't disprove Bug A/B were real fixes (verified separately, see check 3), but the mandatory check's description should be corrected and the untracked-swap risk called out.

**3. Portfolio reconciliation (Phase 5)** — hit the live API, not just SQL:
```
GET /api/portfolio/summary?date=2026-07-31 -> market_value=1,062,188.62  cash_value=407,579.48  (sum=1,469,768.10)
SELECT SUM(market_value) FROM drv_category_perf WHERE axis='asset_class' AND as_of_date='2026-07-31' -> 1,469,768.10
```
Exact match, independently confirmed (8 category rows: Unmapped, Equities, Cash, Fixed Income, Gold, Commodities, USD=0, FX=0).

**4. Parse / schema checks**
```
ast.parse OK: etl/derive_risk_dial.py, etl/derive_market_stat.py, etl/derive_category_perf.py,
              etl/fetch_cboe.py, etl/fetch_yahoo_history.py, api/_helpers.py,
              api/routers/macro_areas.py, etl/mappings.py, etl/derive.py
node --check OK: web/market_bar.js
python -m db.init_db  -> "All DDL applied successfully." (incl. seeds_cockpit.sql)
ref_risk_gauge=15 (14 active), ref_level_watch=9, ref_gauge_transmission=55, ref_market_pattern=8
```
New tables (`ref_risk_gauge`, `ref_level_watch`, `ref_gauge_transmission`, `ref_market_pattern`,
`drv_market_stat`, `drv_market_event`, `drv_category_perf`, `hist_internals`) all created cleanly;
row counts match the handoff's "14 of 15 seeded gauges" claim exactly.

**5. No commits / actionable.js untouched**
```
git log --oneline -3  -> same 3 commits as before the session (8fb4a91 top, unchanged)
git status  -> only the files listed in DEV_HANDOFF.md's "Files changed" section are modified/untracked
git diff --stat -- web/actionable.js  -> empty (no changes)
```

**6. Idempotency**
```
derive_market_stat(2026-07-31) run #1 vs run #2: stored row (rv10/21/63, vix, vrp, vrp_z,
  risk_budget, risk_label, gauges_fired JSONB, detail JSONB) byte-identical.
derive_category_perf(2026-07-31) run #1 vs run #2: all 31 category rows
  (axis, category, market_value, weight_pct, twr_1w, twr_1m, verdict, flows_confidence)
  byte-identical.
Full derive_all() cascade for the anchor date: cascade_status='SUCCESS', failed_steps=[],
  drv_market_stat=1, drv_category_perf=31 — matches row counts from the isolated re-runs.
```
Also confirmed Phase 1 fixes live via the running app (not just diff-reading):
`MOVE` marketbar tile now returns `vol_low=100.0/vol_high=120.0` (non-null);
`/api/macro-areas` area objects now carry `hot_pct=0.85/cold_pct=0.15` (server-canonical value, matches spec's verification line exactly); `T10Y2Y` and `BAMLH0A0HYM2` both present with current data in `/api/macro`; marketbar `HY`→HYG price re-labeled, `HYOAS` credit-spread tile live at 2.84%.

## Failures & gaps
- `etl/derive_category_perf.py::_derive_category_perf_impl` / `DEV_HANDOFF.md` "Evidence #2" — the mandatory Phase 5.2 write-up under-describes the tested category (omits DESK/IPAY/NOBL/VYM/FXH, names only NON40O26D/M/P+CRAK) and the tested 1-week window silently contains an untracked ~$20k position swap (FXH exits, 4 new tickers appear) with zero rows in `hist_cst`/`hist_ft` at all — not just outside the Buy/Sell filter. The numeric "exact match" still holds (verified independently), but it's guaranteed by construction for any zero-netflow window and doesn't demonstrate what the write-up implies. Recommend: (a) correct the write-up, and (b) investigate why these 5 symbols move on/off the books with no flow record at all — if this pattern recurs elsewhere, `drv_category_perf`'s TWR for other categories/windows could be silently misattributing non-market position changes as return, beyond the already-disclosed dividend/reinvestment gap in Decision 15.
- Phase 3 backfill is 114 trading days vs. the spec's ≥300-day target and the Cboe RVOL cross-check could not run (feed stale since 2025-02-21) — both already disclosed by the developer as data-availability limits, not code defects. Flagging only because they mean `vrp_z`'s distribution is thin until more real history accumulates.

## Acceptance criteria check
- Phase 1 (MOVE zone, hot/cold 0.85/0.15, REF_MAPS documented not fixed, HYOAS/T2S10 switched on) — met: verified live via running app + DB, not just diff.
- Phase 2 (4 new ref tables + seeds) — met: schema applies cleanly, seed row counts as claimed.
- Phase 3 (drv_market_stat + Risk Dial, rv21 sanity 8–25) — met: independently reproduced identical stats; backfill scope limited by available history (disclosed).
- Phase 5 (drv_category_perf, TWR-no-trade exact match, portfolio reconciliation) — met numerically (both independently reproduced exact matches), with a documentation-accuracy and data-quality concern on the 5.2 check as detailed above.
- No commits, `web/actionable.js` untouched — met.
- Idempotency of new derives — met.

## Recommendation
SHIP, with two follow-ups before fully trusting the factor scorecard:
1. Correct the Phase 5.2 write-up in `DEV_HANDOFF.md` to name the actual tested category composition (8 symbols, not 4).
2. Investigate the CRAK/DESK/IPAY/NOBL-appear / FXH-disappear pattern (zero flow rows in `hist_cst`/`hist_ft` for any of them, ever) before relying on `drv_category_perf` TWR numbers for categories that touch these symbols — it may be legitimate (option assignment, corporate action, spin-off) but is currently silently treated as pure organic return with no trace in `detail`.
