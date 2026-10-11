# AGENT_WORK — Developer master pointer

> **THE ONLY ACTIVE TASK IS TASK_136.**
> TASK_133 and TASK_134 are complete (`DEV_HANDOFF.md` → `ALL_DONE`). Do not reopen them.
> TASK_135 exists but is **NOT active** — do not start it unless this file says so.

**Active task:** `agent-tasks/TASK_136_cockpit_grid_layout.md`
**Design reference:** `docs/dashboard_cockpit_design.md`
**Created:** 2026-08-01 by Cowork

---

## Scope — exclusive

Work on **`agent-tasks/TASK_136_cockpit_grid_layout.md` and nothing else.**

**Ignore entirely:** `AGENT_WORK_1.md` … `AGENT_WORK_40.md`, `agent-tasks/TASK_89` …
`TASK_135`, all `AGENT_RESULT_*.md` and `TEST_REPORT_*.md`, `COWORK_IMPL_LOG.md`,
`_trash_2026-05-12/`, `_backups/`, root-level `_*.py` scripts.

Those files are history, not a backlog. If something in them looks unfinished, leave it.

---

## What TASK_136 is

The Dashboard is a single-column stack — six full-width cards, one per row. On a wide
monitor each card stretches to ~1900px holding content that needs 400–600px, so the
screen is mostly empty and the morning read costs six scrolls.

Convert `.cockpit-bands` to a **12-column CSS grid**:

```
Regime strip                                    full width, thin
Risk Dial (4) │ What changed (4) │ Shortlist (4)
Factor scorecard                                full width
Housekeeping                                    full width, thin
```

Plus two content additions the recovered width pays for — five vs-Mkt delta columns on
the scorecard, and a pre-multiplied trade size on the shortlist. Both use fields the API
already returns.

---

## Hard rules

- **No questions.** Where the spec is silent, match existing app conventions and note
  the choice in `DEV_HANDOFF.md`.
- **No tests.** Do not write, extend, or run anything under `tests/`. Do not hand off to
  the tester agent. This overrides repo convention #18 — the user asks for tests
  explicitly when they want them.
- **No commits, no pushes.** The user commits from Windows.
- **Layout only.** No calculation, threshold, endpoint shape, or stored value may
  change. Nothing under `api/`, `etl/` or `db/` is touched.
- **Do not touch `web/actionable.js` / `web/actionable.html`.** They carry an unrelated
  uncommitted diff (sector/style filter chips) — the user's own in-progress work.
- **Do not reorder the sections in `index.html`.** DOM order is the single-column
  reading order; `grid-area` does the placement at wide widths.
- `node --check web/app.js` after large edits — truncation is silent. That is a
  file-integrity check, not a test, and still applies.

---

## Two things that will break the layout if missed

1. **`minmax(0, 1fr)` on the columns AND `min-width: 0` on `.cockpit-band`.** Grid
   tracks default to `min-content`; without both, the factor-scorecard table forces its
   track wider than its share and pushes the whole page sideways.

2. **The double scrollbar.** `main` is `flex: 1; overflow-y: auto` (styles.css ~796) and
   `body.dash-page .cockpit-bands` is also `flex: 1; overflow-y: auto` (line 832). Once
   `.cockpit-bands` is a grid it must not scroll independently — remove the flex/overflow
   from that `body.dash-page` rule and let `main` own the single scroll.

---

## Log

Append a `# Dev Handoff — TASK_136` section to `DEV_HANDOFF.md` below the existing ones —
do not overwrite prior sections. Record files changed and any decision made where the
spec was silent. End with `ALL_DONE`.
