# AGENT_WORK — Developer master pointer

> **THE ONLY ACTIVE TASK IS TASK_134.**
> TASK_133 is complete and verified (`TEST_REPORT_40.md` → SHIP). Do not reopen it.

**Active task:** `agent-tasks/TASK_134_cockpit_visual_and_fixes.md`
**Design reference:** `docs/dashboard_cockpit_design.md`
**Prior work:** `DEV_HANDOFF.md` (TASK_133 round 2), `TEST_REPORT_39.md`, `TEST_REPORT_40.md`
**Created:** 2026-08-01 by Cowork

---

## Scope — exclusive

Work on **`agent-tasks/TASK_134_cockpit_visual_and_fixes.md` and nothing else.**

**Ignore entirely:** `AGENT_WORK_1.md` … `AGENT_WORK_40.md`, `agent-tasks/TASK_89` …
`TASK_133`, all `AGENT_RESULT_*.md` and `TEST_REPORT_*.md` (read-only reference),
`COWORK_IMPL_LOG.md`, `_trash_2026-05-12/`, `_backups/`, root-level `_*.py` scripts.

Those files are history, not a backlog. If something in them looks unfinished, leave it.

---

## What TASK_134 is

TASK_133 shipped correct data and correct layout. The screen **reads flat**, because
Band 1 hardcoded a foreign palette instead of using this app's design tokens, and
because gauge severity is not encoded at all.

| Part | Scope |
|---|---|
| **A** | Visual system — replace every raw hex with `styles.css` `:root` tokens; move the cockpit CSS out of `index.html`; fix the hierarchy so the number leads; encode gauge weight as severity; colour bands 2–6 |
| **B** | Content bugs — **B.3 first: Band 2 must only report genuine Hedgeye risk-range symbols** (`drv_rr.source = 'RR'`, not the BB fallback covering the whole universe); plus multi-leg gauge details naming only the leg that fired, and headline/multiplier agreement |
| **C** | Three deferred follow-ups — surface the transaction-feed gaps in Band 6, close the `REF_MAPS` landmine, verify the MOVE zone |

**Hard constraint: no calculation, threshold, or derive-logic changes.** If an edit
would move a number, it is out of scope. `python -m etl.derive` twice must still produce
byte-identical `drv_*` rows.

---

## The one rule that fixes the look

**No raw hex anywhere in the cockpit styles.** This app already has a deliberate palette
in `web/styles.css` `:root` — `--bull`, `--bear`, `--warn`, `--ok`, `--accent`,
`--text-1/2/3`, `--border`, and the full `--act-*` action ramp. Every other screen uses
it. The cockpit used none of it, which is exactly why it looks like a different product
bolted on.

If a role is missing, add the token to `:root` and use it. Never inline a literal.

---

## Hard rules

- **No questions.** Where the spec is silent, match existing app conventions and note
  the choice in `DEV_HANDOFF.md`.
- **No commits, no pushes.** The user commits from Windows.
- **Do not touch `web/actionable.js` / `web/actionable.html`.** They carry an unrelated
  uncommitted diff (sector/style filter chips) that is the user's own in-progress work.
  Both prior test reports confirmed it is not agent-introduced. Leave it alone.
- **No chart library, no dark mode.** Bars and rails are `<div>`s with a width; the app
  has no theme toggle and a half-supported one is worse than none.
- Repo conventions apply: **SQL ≤ 965 bytes** · schema in `db/baseline.sql` ·
  `tos_symbol` not raw `symbol` in `drv_*` · SQLAlchemy + psycopg v3 only.
- Verify large edits — `node --check` for JS, `python3 -c "import ast; ast.parse(...)"`
  for Python. Truncation is silent.

---

## Start with B.3

The user's most specific complaint. Band 2 is showing events for symbols like ATRO and
PNDRY, which have **no Hedgeye risk range** — `_risk_range_events` queries `drv_rr`
without filtering on `source`, so the `'BB'` fallback rows (TOS Bollinger bands, derived
for the entire ~1,000-symbol universe) all emit events alongside the ~55 genuine `'RR'`
instruments. One-line filter, large improvement. Do it first.

---

## Two checks that must not be skipped

1. **`REF_MAPS` (Part C.2)** — before deleting line 556, record `ref_sector`, `ref_rrt`
   and `ref_rule_desc` row counts. Reload the workbook, record them again. **Paste both
   in `DEV_HANDOFF.md`.** If any count *drops*, restore the line and stop.

2. **Nothing moved (Part A/B constraint)** — `python -m etl.derive` twice for the anchor
   date; `drv_market_stat`, `drv_category_perf`, `drv_market_event` byte-identical apart
   from `derived_at`. This is the guard that the visual pass didn't quietly change a
   calculation.

---

## Context worth carrying

`DEV_HANDOFF.md` Part A found two real, ongoing data gaps, independently confirmed by
`TEST_REPORT_40.md`:

- Schwab `Rollover_IRA …892` — `hist_cst` has loaded nothing since **2026-06-02**
- Fidelity `261408079` — `hist_ft` has **zero rows, ever**; the account holds AAPL,
  MSFT, META, NFLX

These are data-source problems the user must fix upstream, not code bugs. Part C.1 is
about making the screen **say so** instead of quietly showing weakened numbers.

---

## Log

Append to `DEV_HANDOFF.md` (do not overwrite the TASK_133 sections — add a new
`# Dev Handoff — TASK_134` heading below them). Record files changed, decisions made
where the spec was silent, and the evidence for the two checks above. End with
`ALL_DONE` (or `PART_<X>_DONE`).

Testing is **on request only** — do not hand off to the tester agent.
