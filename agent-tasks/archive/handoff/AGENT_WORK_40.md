# AGENT_WORK — Developer master pointer

**Active task:** `agent-tasks/TASK_133_dashboard_cockpit.md` (continuation)
**Created:** 2026-08-01 by Cowork, round 2
**Design reference:** `docs/dashboard_cockpit_design.md`
**Prior round:** `AGENT_WORK_39.md` / `DEV_HANDOFF.md` (phases 1,2,3,5 done, phase 4
partial) / `TEST_REPORT_39.md` (verdict: PASS_WITH_CONCERNS)

---

## What to do

Two parts. Do both.

### Part A — address the two follow-ups from TEST_REPORT_39.md

1. **Correct the Phase 5.2 writeup.** `DEV_HANDOFF.md`'s description of the
   no-trade-category TWR check under-describes the tested category and
   omits that its window contains an untracked position swap (CRAK/DESK/
   IPAY/NOBL appear, FXH disappears — zero rows in `hist_cst`/`hist_ft` for
   any of the 5 symbols in that window). Rewrite that section to name the
   actual 8-symbol category composition and disclose the swap.

2. **Investigate the position-swap pattern.** Determine why those symbols
   change with zero flow rows anywhere in `hist_cst`/`hist_ft` (in-kind
   transfer between accounts? corporate action/spin-off? ticker rename? a
   snapshot gap where positions were added directly to `hist_cs`/`hist_f`
   without a corresponding transaction row?). Check whether this pattern
   recurs elsewhere in `drv_category_perf`'s coverage — i.e. does
   `drv_category_perf` risk silently misattributing non-market position
   changes as return in other categories/windows too? If you find it's a
   systemic risk (not a one-off), propose and implement the smallest fix
   that prevents silent misattribution (e.g. detect a snapshot-to-snapshot
   qty appearance/disappearance with no matching flow row and either flag
   the row's return as suspect, or exclude that window from TWR rather than
   silently computing a number). If it's a one-off explainable by a real
   corporate action, document it and no code fix is needed. Record your
   finding and reasoning in `DEV_HANDOFF.md`.

### Part B — continue TASK_133 phases 6, 7, 8

Read `agent-tasks/TASK_133_dashboard_cockpit.md` in full for the phase specs.
`derive_all()` already has a placement comment marking where the Phase 6
deriver belongs.

| Phase | Scope |
|---|---|
| 6 | `api/routers/cockpit.py` — risk-dial, events, factor-scorecard, shortlist endpoints (+ `drv_market_event` if the spec calls for it) |
| 7 | Frontend — rebuild `/` as the six-band cockpit, retire the ticker grid |
| 8 | Docs + tests |

This spec is decision-complete. Do not stop to ask questions. Where it is
silent on an implementation detail, choose the option most consistent with
the existing codebase, implement it, and record the choice in
`DEV_HANDOFF.md`.

---

## Hard rules (unchanged from round 1)

- **No questions.** The spec is final.
- **No commits, no pushes.** The user commits from Windows.
- **No Actionable-screen refactor.** Read `web/actionable.js::_regimeVerdictHtml()`
  for reference — it is a working 8-gauge prototype of the Risk Dial — but
  leave it alone.
- **No invented causes in user-facing text.** State what moved and what it
  co-moves with, never why. Standing user instruction: "never hallucinate."
- **Do not build:** agricultural futures, full SPX dealer GEX, paid economic
  consensus feeds, news APIs, StockCharts scraping, Cboe put/call CSVs. Each
  was evaluated and rejected in round 1 — reasons are in TASK_133 Phase 4.
- Repo conventions apply: idempotent derives · schema in `db/baseline.sql` ·
  **SQL ≤ 965 bytes** · `tos_symbol` not raw `symbol` in `drv_*` · SQLAlchemy +
  psycopg v3 only.
- **Verify large edits** — `node --check` for JS, `python3 -c "import ast; ast.parse(...)"`
  for Python. Large edits can land truncated even when the tool reports success.

## If you run out of time

Stop at a phase boundary and write `PHASE_<n>_DONE` in `DEV_HANDOFF.md` rather
than `ALL_DONE`. Part A (the two follow-ups) takes priority over starting
Phase 7/8 if time is tight — a wrong scorecard number is worse than a missing
screen.

---

## Log

Record progress in `DEV_HANDOFF.md`: files changed, decisions made where the
spec was silent, risks found, and evidence for Part A's investigation. End
with `ALL_DONE` (or `PHASE_<n>_DONE`).

Testing is requested for this round — hand off to the tester agent when done
(this round's dev-cycle explicitly asked for it).
