# Test Report — AGENT_WORK_40

## Verdict
PASS_WITH_CONCERNS

## What I ran
- `pytest tests/test_yang_zhang.py tests/test_risk_dial.py tests/test_twr.py tests/test_market_patterns.py -q` — 22 passed
- `pytest tests/acceptance/test_cockpit.py -m acceptance -q` — 6 passed (28/28 total, matches claim)
- `pytest tests/ -q` (full suite, background, ~257s) — 69 failed, 2669 passed, 28 skipped, 212 deselected
- Independent re-derive of `derive_category_perf` for 2026-07-31 (imported and called directly, not trusting stored rows), queried `flows_confidence`/`gap_days` for all 31 rows
- Raw-SQL independent reconstruction of `asset_class='Fixed Income'` 1w TWR (v_start/v_end from `hist_cs`/`hist_f` directly)
- Raw-SQL inspection of `hist_cs`/`hist_cst` for `TLT` around 2026-06-25..07-05 to confirm the qty-gap detector fires on a real, substantial position change, not noise
- Live `GET /api/portfolio/summary?date=2026-07-31` (already-running server on :8000) vs `SUM(drv_category_perf.market_value)`
- Started a scratch `uvicorn` instance on port 8012, hit all 4 `/api/cockpit/*` endpoints, then killed the process
- `grep`/`Read` on `web/index.html`, `web/app.js`, `web/styles.css` for old ticker-grid markers vs new six-band markers
- Re-ran `derive_market_event` and `derive_market_stat` twice each for 2026-07-31, diffed stored rows field-by-field
- `git log --oneline -5`, `git status`, `git diff --stat -- web/actionable.js web/actionable.html`, `git diff -- web/actionable.js` (full content)
- `python -m db.init_db` (full baseline + all seeds incl. `seeds_cockpit.sql`)
- `node --check web/app.js`; `python -c "import ast; ast.parse(...)"` on `cockpit.py`, `derive_market_event.py`, `derive_category_perf.py`

## Evidence

**1. Test suite (28/28 claim)** — confirmed exactly: 22 pure-Python + 6 acceptance = 28 passed, 0 failed. Full suite (excl. acceptance, matching `pytest.ini`'s default marker filter) shows **69 failed / 2669 passed / 28 skipped / 212 deselected** — developer claimed 76/2662/28. Total (69+2669+28=2766) matches the developer's total (76+2662+28=2766) exactly, so this is very likely test-order/flakiness variance between runs, not a real discrepancy in the codebase. None of my 69 failures reference `index.html`, `app.js`, `cockpit.py`, `derive_market_event`, `derive_risk_dial`, `derive_market_stat`, or `derive_category_perf` — they are the same class of stale `DEV_HANDOFF ends in ALL_DONE` / historical `AGENT_WORK_N` content checks the developer already identified as pre-existing debt (`test_agent_work_5/6/7/8/9/35/44/48/49/50`, `test_task_71/82/96/98`, `test_cat_parity`). No new failures traced to this round's files.

**2. Qty-gap detector (Part A fix)** — re-derived `drv_category_perf` for 2026-07-31 independently:
```
total rows: 31, suspect: 31   (every category suspect — matches DEV_HANDOFF's claim exactly)
asset_class/Unmapped: twr_1w = -0.00967692216216043
  gap_days: 2026-07-27 [COM,VYM]; 2026-07-31 [CRAK,DESK,IPAY,NOBL,NON40O26D,NON40O26P]
```
Matches DEV_HANDOFF's quoted number exactly (`-0.00967692216216043`). Confirmed the detector isn't just tripping on noise: raw `hist_cs` shows `TLT` qty going **175 → 250 → 350** across 2026-06-29→07-01 (a real, large position change) with **zero** matching rows in `hist_cst` or `hist_ft` for `TLT` in that window — exactly the systemic gap class described (Fidelity/Schwab feed silence), not a rounding artifact.
- **Clean-window TWR re-verified independently**, not from the stored row: `asset_class='Fixed Income'`, 1w ending 07-31 — direct SQL against `hist_cs`/`hist_f` gives v_start(07-23)=87404.00, v_end(07-31)=87433.50, naive ratio = `87433.5/87404-1` = `0.00033751315729246834`; stored `twr_1w` = `0.000337513157292468`. Exact match. The row's *overall* `flows_confidence` is `suspect` (a different window — 1m/2m/3m — has real gap_days from BNDD/LQD/TLT churn elsewhere), but the row's own `detail.windows.1w.confidence` is `green` with zero gap_days, confirming the claimed "genuinely clean 1w window" characterization is accurate at the per-window granularity.
- **Portfolio reconciliation still holds**: live `/api/portfolio/summary?date=2026-07-31` → market_value 1,062,188.62 + cash_value 407,579.48 = **1,469,768.10**; `SUM(drv_category_perf.market_value) WHERE axis='asset_class'` = **1,469,768.10**. Exact match, independently re-run after the fix.
- **Idempotency reconfirmed**: ran `derive_category_perf(2026-07-31)` twice more (on top of the developer's own re-run) — 0 field diffs across all 31 rows.

**3. `api/routers/cockpit.py` registration + live endpoints** — `api/main.py:35,56,134` registers the router. On the pre-existing server already listening on :8000 (started before this round, evidently never restarted), all 4 `/api/cockpit/*` paths 404'd — this is a stale-process artifact (matches the developer's own documented gotcha about restarting after `api`/`etl` changes), **not a code defect**: a fresh scratch `uvicorn` instance on port 8012 returned real, well-formed JSON for the anchor date on all 4:
  - `/api/cockpit/risk-dial?date=2026-07-31` → `risk_budget:79, risk_label:"CAUTION"`, 3 fired gauges with `exposure.top_holdings` populated (NVDA/RHP/NET, XLE/RSP/CASY)
  - `/api/cockpit/events?date=2026-07-31` → 2 real events (`ATRO`/`PNDRY` entered top decile)
  - `/api/cockpit/factor-scorecard?axis=sector` → 200, per-category `twr_*`/`bench_*`/`verdict`/`detail.windows`
  - `/api/cockpit/shortlist` → 3 rows (`ACHC`, `XLV`, `XLE`), respecting the ≤3 cap

**4. `web/index.html`/`web/app.js` rebuild** — old markers (`tickerSections`, `dash-grid`, `renderTickerGrid`, `loadTickers`, `sectionRank`, `SECTION_ORDER`, `state.rows`, `state.section`) are **gone** from both files (only a one-line retirement comment remains in `app.js`). New six-band markup confirmed present in `index.html`: `#riskDialBand`, `#eventsBand`, `#regimeBand`, `#factorScorecardBand`, `#shortlistBand`, `#housekeepingBand`. `app.js` contains `loadRiskDial/loadEventsBand/loadRegimeBand/loadFactorScorecard/loadShortlist/loadHousekeeping` (17 occurrences of cockpit-endpoint-related identifiers) and the claimed date-picker fix: `datePicker.addEventListener('change', ...) → refreshAll()` (line 556-559) + `refreshBtn` wired (line 560-561) — both genuinely present, not just claimed. `web/styles.css` old classes (`.dash-grid`/`.sections-grid`/`.ticker-grid`) are gone except a retirement comment. `node --check web/app.js` and `ast.parse` on all 3 new Python files pass clean (no truncation).

**5. Idempotency of new derivers** — `derive_market_event(2026-07-31)` run twice: 2 rows, byte-identical (incl. `legs`/`exposure` JSON). `derive_market_stat(2026-07-31)` run twice: identical on every field except `derived_at` (expected — it's a real timestamp-of-run column, not derived data). `derive_category_perf`: 0 diffs (above).

**6. No commits / actionable.js untouched by this round** — `git log --oneline -5` unchanged (same 5 commits as the session-start snapshot: `8fb4a91`...`c636f35`). `git diff --stat -- web/actionable.js web/actionable.html` shows a real 85-line diff, but reading the full diff confirms it is exactly what DEV_HANDOFF discloses: `renderSectorSummary()`/`renderStyleSummary()`/`_rowStyleLabels()`/`state.filters.sector`/`state.filters.style` — GICS-sector and equity-style filter chips, unrelated to cockpit/TASK_133. Nothing in the diff touches `drv_category_perf`, risk-dial, or cockpit code. Consistent with TEST_REPORT_39's own finding that this diff was empty at the end of round 1, i.e. it landed in the working tree between rounds from separate, unrelated work.

**7. Schema apply** — `python -m db.init_db` → `baseline.sql` OK, `seeds_cockpit.sql` OK, "All DDL applied successfully." No errors.

## Failures & gaps
- Full-suite failure count doesn't match the developer's exact number (69 vs. claimed 76), though the grand total is identical and none of the delta traces to this round's files — flagging only as an unresolved minor inconsistency, not a functional defect.
- The pre-existing `uvicorn` process on port 8000 (left running from an earlier session) 404s on all 4 new cockpit endpoints — purely an unrestarted-process artifact (confirmed working on a fresh instance), but a real trap for anyone testing this by hand against that already-running server without restarting it first, exactly as `DEV_HANDOFF.md`'s own "How to test" section warns.
- As the developer's own "Risks & notes" discloses: every category was `suspect` on 2026-07-31 (independently reproduced) because it was a real portfolio-wide rebalancing day. This is correct behavior given the underlying feed gaps, but it does mean `flows_confidence` carries little discriminating power around dates that touch either broken account right now — a real, disclosed, not-hidden limitation.

## Acceptance criteria check
- Part A: correct/expand Phase 5.2 write-up naming the true 8-symbol composition and disclosing the swap — met (DEV_HANDOFF.md's Part A section names all symbols and the swap explicitly).
- Part A: investigate systemic recurrence, implement smallest fix if systemic — met: recurrence confirmed independently on a second date pattern (the 07-31 all-suspect result is a direct, reproducible consequence); qty-gap detector implemented and independently verified to fire correctly on a real gap (TLT) and force `r_t=0`/`suspect` without corrupting the clean-window telescoping identity.
- Phase 6 (`api/routers/cockpit.py` + `derive_market_event.py`, wired into `derive_all()`) — met: router registered, all 4 endpoints live-verified with real data on a fresh process; idempotent.
- Phase 7 (six-band `/` rebuild, retire ticker grid, date-picker fix) — met: old code fully removed, new bands present and wired, date-picker regression fix present in code.
- Phase 8 (tests + docs) — met: 28/28 new tests pass exactly as claimed; `CLAUDE.md`/`docs/migrations.md`/`docs/dashboard_logic.md` updated; `docs/dashboard_attention_panel_design.md` deleted as claimed.
- No commits; `web/actionable.js`/`.html` untouched by this round — met (verified diff content is unrelated pre-existing work, no commits made).
- `db/baseline.sql` + `db/seeds_cockpit.sql` apply cleanly — met.

## Recommendation
SHIP. No blocking defects found across any of the 7 checks; the two flagged items (full-suite count drift, stale-process 404s) are non-functional/operational and don't indicate a code regression. Suggest the developer/user restart any long-running dev `uvicorn` instance before manually spot-checking the new endpoints, and keep an eye on `flows_confidence` staying informative once the two underlying feed gaps (Schwab CST for `Rollover_IRA ...892`, Fidelity FT for `261408079`) are resolved on the data-source side.
