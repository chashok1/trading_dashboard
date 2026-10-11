# AGENT_WORK — Developer master pointer

> **THE ONLY ACTIVE TASK IS TASK_133.**
> Every other task in this repository is closed. Do not start, resume, revisit,
> or "finish off" anything else.

**Active task:** `agent-tasks/TASK_133_dashboard_cockpit.md`
**Design reference:** `docs/dashboard_cockpit_design.md`
**Created:** 2026-08-01 by Cowork · replaces all prior work pointers

---

## Scope — exclusive

Work on **`agent-tasks/TASK_133_dashboard_cockpit.md` and nothing else.**

**Ignore entirely:**

- `AGENT_WORK_1.md` … `AGENT_WORK_38.md` — historical per-item logs, all closed
- `agent-tasks/TASK_89` … `TASK_132` — all delivered and committed
- `AGENT_RESULT_*.md`, `TEST_REPORT_*.md` — past verification rounds
- `COWORK_IMPL_LOG.md`, `REPROCESS_REPORT.md`, `PERIOD_METRICS_IMPLEMENTATION.md`
- `DEV_HANDOFF_ARCHIVE_TASK132.md` — the previous handoff, kept for reference only

Those files are history. They are not a backlog. If something in them looks unfinished,
**leave it** — it is out of scope and raising it is not part of this task.

Do not open files under `_trash_2026-05-12/`, `_backups/`, or the root-level throwaway
scripts (`_audit.py`, `_chk.py`, `_fix*.py`, `_peek.py`, `_probe_api.py`, `_trig.py`, …).

---

## What to do

Read `agent-tasks/TASK_133_dashboard_cockpit.md` in full, then implement it in phase
order (1 → 8).

**This spec is decision-complete. Do not stop to ask questions.** Where it is silent on
an implementation detail, choose the option most consistent with the existing codebase,
implement it, and record the choice in `DEV_HANDOFF.md`.

| Phase | Scope | Blocks |
|---|---|---|
| 1 | Bug fixes + switch on data already being fetched (MOVE zone, hot/cold mismatch, `REF_MAPS`, HY spread, 2s10s) | — |
| 2 | Reference tables + seeds (`ref_risk_gauge`, `ref_level_watch`, `ref_gauge_transmission`, `ref_market_pattern`) | 3, 6 |
| 3 | `drv_market_stat` — Yang–Zhang realized vol, VRP, breadth, **Risk Dial** | 6 |
| 4 | New feeds — ToS internals (`hist_internals`), KOSPI, VVIX, ETH, Cboe RVOL | — |
| 5 | `drv_category_perf` — time-weighted returns by sector / asset class / style | 6 |
| 6 | `api/routers/cockpit.py` — risk-dial, events, factor-scorecard, shortlist | 7 |
| 7 | Frontend — rebuild `/` as the six-band cockpit, retire the ticker grid | — |
| 8 | Docs + tests | — |

Each phase is independently verifiable and commit-ready. **If you run out of time,
stop at a phase boundary** and write `PHASE_<n>_DONE` in `DEV_HANDOFF.md` rather than
`ALL_DONE`.

**Phase 3 is the one that matters most.** The Risk Dial is the screen's whole reason
for existing — it turns market context into a size multiplier on AMT$. It needs no new
data. If only one phase ships, make it that one (after Phase 2, which it depends on).

---

## Hard rules

- **No questions.** The spec is final.
- **No commits, no pushes.** The user commits from Windows.
- **No scope creep.** TASK_133 only — see the exclusion list above.
- **No Actionable-screen refactor.** Read `web/actionable.js::_regimeVerdictHtml()` for
  reference — it is a working 8-gauge prototype of the Risk Dial — but leave it alone.
- **No invented causes in user-facing text.** State what moved and what it co-moves
  with, never why. Standing user instruction: "never hallucinate."
- **Do not build:** agricultural futures, full SPX dealer GEX, paid economic consensus
  feeds, news APIs, StockCharts scraping, Cboe put/call CSVs. Each was evaluated and
  rejected — reasons are in TASK_133 Phase 4.
- Repo conventions apply: idempotent derives · schema in `db/baseline.sql` ·
  **SQL ≤ 965 bytes** · `tos_symbol` not raw `symbol` in `drv_*` · SQLAlchemy +
  psycopg v3 only.
- **Verify large edits** — `node --check` for JS, `python3 -c "import ast; ast.parse(...)"`
  for Python. Large edits can land truncated even when the tool reports success.

---

## Three checks that must not be skipped

These are the places where a plausible-looking implementation is silently wrong:

1. **Realized vol units** (Phase 3.1). `rv21` for SPX should sit roughly 8–25 in a
   normal regime. Three-digit or sub-1 values mean a units bug — log-return vs percent,
   or a missing `sqrt(252)`. Cross-check against Cboe `RVOL` once Phase 4 lands.

2. **TWR against a no-trade category** (Phase 5.2). Pick a category with no trades in
   the window; its time-weighted return must equal `V_end/V_start − 1` **exactly**.
   Paste the comparison into `DEV_HANDOFF.md`. If it does not match, the flow mapping
   is wrong — fix it before moving on.

3. **Portfolio reconciliation** (Phase 5). The `asset_class` axis market-value total
   must reconcile to `/api/portfolio/summary` (market + cash). If it does not, the
   category mapping is dropping holdings — and a scorecard that quietly loses part of
   the book is worse than no scorecard.

---

## Log

Start `DEV_HANDOFF.md` fresh (it has been reset for this task). Record: files changed,
decisions made where the spec was silent, risks found, and the evidence for the three
checks above. End with `ALL_DONE` (or `PHASE_<n>_DONE`).

Testing is **on request only** — do not hand off to the tester agent, and do not run
any earlier task's verification checklist. The spec's "How to verify" section is
reference until the user explicitly asks for a test round.
