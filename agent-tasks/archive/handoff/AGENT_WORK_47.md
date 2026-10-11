# AGENT_WORK — Developer master pointer

> **TASK_138–142 are COMPLETE** (`AGENT_WORK_45.md`, `AGENT_WORK_46.md`,
> `DEV_HANDOFF.md` → `ALL_DONE`, reviewed by Cowork 2026-09-21). Do not reopen.
> **This batch releases TASK_143 → 147, all at once — the "Market Read" build.**
> Work them in dependency order below; nothing is gated on a verdict this time.

**Created:** 2026-09-21 by Cowork
**Design of record:** `docs/market_state_factor_sss_design.md` — §1–§4 are the
analysis, the **Addendum A–H** is what was decided (A–H win where they differ).
**Acceptance reference:** `docs/mockups/market_read_one_picture_mockup.html`
(real values, hand-computed from the Sep 2026 files; the build reproduces them).

---

## Order

```
  TASK_143  Theme map · drv_source_breadth · drv_theme_stance · /api/market-read
     │
     ├──► TASK_144  drv_sss_breadth (rows + books) · CALL long/short split
     │        │
     │        ├──► TASK_145  UI on / — breadth strip, theme grid, sector cards,
     │        │              Quad Rotation tiles retired
     │        │
     │        └──► TASK_146  Risk Dial positioning gauges (shipped INACTIVE)
     │                       + freshness cap
     │
     └──────────► TASK_147  Validation views + report + nightly refresh
```

143 first (everything reads it). 144 next. Then 145 / 146 / 147 in any order
or in parallel — they touch different files.

---

## Why this batch exists (one paragraph)

The dashboard already loads four Hedgeye lists daily/weekly — RR (a complete
macro board with a stance per symbol), ETF Pro (a factor stance list), PS (its
conviction ranking), SSS (sector breadth with analyst book sizes) — and nothing
aggregates them over time or maps them to themes. Read by hand from the files
on 2026-09-21: all four de-risked together Sep 8–14; SSS rows fell 47% while
analysts' ranked books fell 5%; the lists disagree with the Q2-blend quad on
six growth-sensitive themes. None of that is visible on any screen today. The
existing synthesis renderer (`macro_areas.js::renderLegacyCard`) is dead code.

---

## Standing constraints

1. **Display + measurement only.** No task in this batch touches
   `derive_actionable.py`, `ref_trig_*`, `SOURCE_ORDER`, `ref_settings`
   decision switches (`source_order_mode`, `unproven_sell_mode`), or
   `ref_risk_gauge.is_active` for existing gauges. A theme stance may
   influence an action only after TASK_147's scorecard is positive on ≥ 30
   samples, and only through the switch-gated path 140/141 established.
2. **New Risk Dial gauges ship `is_active = FALSE`** with a 30-date
   before/after budget table in the handoff. The user activates.
3. **Quad is never hard-coded.** `quad_says` comes from the same monthly-
   weighted stance the Quad Rotation tiles use. The mockup's "Q3" wording is
   superseded (Addendum F).
4. **Reuse, don't reimplement**: quad-rotation breadth query
   (`api/routers/dash.py::get_quad_rotation`), `/api/quad/band-factors`
   stance logic, `drv_category_perf` for positions, `ref_freshness_contract`
   for every new table, `run_nightly_outcomes()` for every new refresh.
5. **Every new computed table gets a freshness-contract row in the same task**
   (`docs/agent_handoff_workflow.md`, TASK_142 rule). A task that adds a table
   without one is not done.
6. Stay on the Baseline param profile. No commits or pushes — the user
   commits from Windows.
7. Log each task under its own heading in `DEV_HANDOFF.md`; `ALL_DONE` only
   when all five pass their "How to verify" blocks, else `PARTIAL: <tasks>`.

---

## Carried from the last batch — read before starting

- **TASK_139** flipped two non-gating assumptions: `rr_bull_bear` (B/!B) is
  no longer trustworthy, and SS/high vs SS/mixed reversed. The new window
  is still the same up-trend (SPX +3.0%, VIX ~16.5) — A5 remains unproven.
  Nothing in this batch depends on either signal.
- **TASK_141** found that `low_confidence` never co-occurs with a
  REMOVE/REDUCE winner because no active rule group emits those labels —
  the unproven SELL rules reach the user through `trig_action` / Technical
  (`rr_action`), not the consolidated winner. Parked for Cowork to re-scope;
  **out of scope here.**
- **TASK_140** `'measured'` mode changes 16 of 1,078 actions; still OFF,
  awaiting the user's decision.

---

## Out of scope (still parked)

Hysteresis / minimum-hold · edge-weighted winner ties · conviction/vol sizing
· disagreement scoring · staleness decay on periodic sources · RR playbook
gate swap · re-targeting SELL suppression at `trig_action` (new, from 141).

---

## Reporting

`DEV_HANDOFF.md`, one heading per task, ending `ALL_DONE`. **No test round is
pending** (`AGENT_TASK.md` → NO TEST ROUND); run each task's "How to verify"
yourself as part of implementation, do not invoke the tester.
