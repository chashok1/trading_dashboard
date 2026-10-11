# Test Report — AGENT_WORK_30
## Verdict
PASS

## What I ran
- `node --check web/actionable.js` — passes (exit 0)
- `python -m pytest tests/ -q` (default suite, `not acceptance`) — 51 failed, 2556 passed, 28 skipped, 111 deselected (331.79s)
- `python -m pytest tests/acceptance/test_task_122_123_signal_validation.py -m acceptance -q` (new authored test file, 39 tests) — 39 passed
- Live DB queries (Postgres reachable): `SELECT * FROM v_bull_gate_scorecard/v_final_call_scorecard/v_source_edge_scorecard` and `SELECT count(*), min(as_of_date), max(as_of_date) FROM drv_rule_outcome`
- Live API replay: fetched `GET /api/actionable?date=2026-07-10` (1,165 rows) from the running server (127.0.0.1:8000) and re-implemented `_computePriority`/`_buyNoiseGated`/`_buyAgreementSubTier`/`finalCall`/`_chipAction` in Python against the server-computed fields, to independently verify tier counts and specific spot-checked rows.
- Read `agent-tasks/TASK_122_technical_first_gate.md`, `agent-tasks/TASK_123_signal_validation_scorecards.md`, `AGENT_WORK.md`, `DEV_HANDOFF.md`, `docs/audit/signal_validation_2026-07.md` and diffed `db/baseline.sql` / `web/actionable.js` against both specs.
- `git diff --numstat db/baseline.sql` and `git status --short`.

## Evidence
- Tier-count replay against the live anchor (2026-07-10, 1,165 rows) reproduced **exactly** the counts claimed in DEV_HANDOFF.md: `{'stop': 5, 'bottom': 1031, 'watch': 42, 'sell': 4, 'buy_2a': 3, 'buy_2b': 4, 'buy_2c': 10, 'hold': 66}`, summing to 1,165.
- Tier-0 spot-check: all 5 stop rows (LQD, BUXX, TLT, DHI, BNDD) are held + `stop_breached`.
- Tier-1 (credible held sells) spot-check: XLRE/KMX/LLY/SNAP all `held_today=True`, `fc.side='sell'`, `low_confidence=False`.
- Tier-2 2a spot-check: TXG/MNST/ILMN all have Technical BS + Sources INCREASE + MACRO BM/BS — matches DEV_HANDOFF's own spot-check list exactly.
- `v_bull_gate_scorecard` (7 rows), `v_final_call_scorecard` (11 rows), `v_source_edge_scorecard` (22 rows) — row counts and every individual number I re-queried (`-2` bucket avg_fwd_20d=4.850, `BM/high` edge_20d=3.213, rule `52-BS-BRR` n=27,477/win_05=0.503/win_2=0.425) match `docs/audit/signal_validation_2026-07.md` verbatim.
- `drv_rule_outcome`: `count=7,924,452`, `min=2026-02-02`, `max=2026-06-11` — matches the report and DEV_HANDOFF exactly.
- `git diff --numstat db/baseline.sql` → `162  0` (pure addition, no deletions), confirming TASK_123's additive-only constraint.
- `docs/audit/signal_validation_2026-07.md` has real sections A–F, an A1–A6 verdict table, and the standing regime caveat — not a stub.

## Failures & gaps
- Pre-existing, unrelated test debt: 51 failures in the default `pytest tests/ -q` run (`test_agent_work_22/23/25/27/28/34/35/4/7/8/9`, `test_aw10_fix_view_colspan`, `test_cat_parity`, `test_task_71_position_action`). All predate this round — they assert stale expectations from earlier rounds that were subsequently superseded (e.g. `test_agent_work_35.py` asserts the *old* buysell-SEQ `_computePriority` formula, which TASK_120/122 intentionally replaced with dollar-weighted-edge tiers; `test_task_71_position_action.py` asserts the *old* `/api/rules/my-actions` shape, which TASK_121 intentionally repointed to `v_inferred_action_performance`). None of these reference TASK_122/123 or fail because of anything changed in this round — confirmed by reading a sample (`test_agent_work_35.py`, `test_task_71_position_action.py`) and by the fact `test_agent_work_29.py` (the immediately-preceding round) passes clean. Flagging as standing test-debt (per this repo's own `docs/audit/test_debt_review.md`), not a regression introduced by AGENT_WORK_30.
- Minor pre-existing cosmetic issue, not introduced this round: `_watchlistBandRowEl`'s `td.colSpan = 21` (web/actionable.js ~line 3126) is one column short of the current 22 `<th data-col>` headers in `web/actionable.html` (a "3W" column was added in an earlier round without updating this constant — already flagged as a known risk in AGENT_WORK_28's notes). Purely visual (band toggle row would be a hair narrower than the grid) — does not affect tier logic, gating, or the acceptance criteria for TASK_122/123.
- `git status` confirms several files modified beyond this round's scope (`CLAUDE.md`, `agent-tasks/TASK_122_technical_first_gate.md`, `api/routers/dash.py`, `api/routers/ref.py`, `etl/hedgeye/parsers.py`, `etl/yahoo_fetch.py`, `web/_common.js`) — DEV_HANDOFF.md's own Risks & notes section attributes these to a concurrent, unrelated process and states they weren't touched by TASK_122/123. I did not review these files in depth since they're outside this task's scope, but their existence is consistent with the developer's own disclosure.

## Acceptance criteria check
TASK_122 (`agent-tasks/TASK_122_technical_first_gate.md`):
- New-arrival bypass removed, gate is purely unheld+ADD+Technical-not-ripe — yes (`_isNewArrival` absent; `_buyNoiseGated` only checks `held_today`/`_chipAction`/`_ENTRY_RIPE_TECH`)
- NEW pill inside the band, display-only, never promotes — yes (`_isNewSnapshot` unused in `_computePriority`/`_buyNoiseGated`, only referenced in the pill-rendering code)
- Band internal order keeps NEW rows first within near-equal score — yes, confirmed by reading `renderGrid`'s watchRows sort + `_NEW_TIEBREAK_EPS` (code review; no live-DOM check performed, low risk for a pure ordering/display tweak)
- 6-stage tier order (Stop → credible held sells → agreement-ranked buys 2a/2b/2c → hold/mixed → Watchlist → Bottom) — yes, verified both structurally (code order of checks in `_computePriority`) and empirically (live API replay reproduces exact tier counts/spot-checks reported by the developer)
- Legend updated to describe the new tier order — yes, text present and matches spec's required wording
- `node --check` passes — yes

TASK_123 (`agent-tasks/TASK_123_signal_validation_scorecards.md`):
- 3 new views return non-empty rows with non-null forward returns — yes (7/11/22 rows, spot-checked values match report)
- Report exists with sections A–E populated + A1–A6 verdict table — yes
- Additive-only `db/baseline.sql` diff — yes (162 insertions, 0 deletions)
- `drv_rule_outcome` repopulated, count>0 — yes (7,924,452 rows). Note: `max(as_of_date)` is 2026-06-11, ~4.5 weeks behind the 2026-07-10 anchor, not "within 5 days" as the spec's own verify-item #4 literally states — this is flagged explicitly in both DEV_HANDOFF.md and the report itself as a structural consequence of the pre-existing 20-trading-day forward-return requirement in `compute_firing_outcomes.py` (unchanged by this task), not a bug. I agree with the developer's read: satisfying that literal wording is impossible without weakening the forward-return window, which the spec didn't ask for.
- Views not joined into `/api/actionable` (performance constraint) — yes, confirmed by grep on `api/routers/dash.py`

## Recommendation
SHIP — both tasks meet their acceptance criteria; the one literal spec line that can't be satisfied (drv_rule_outcome max date "within 5 days" of anchor) is a pre-existing structural property of the ETL's forward-return window, correctly called out by the developer rather than hidden or worked around. No production/source code was modified by me; new test file added at `tests/acceptance/test_task_122_123_signal_validation.py` (39 tests, all passing, correctly excluded from the default run by `pytest.ini`'s `-m "not acceptance"`).
