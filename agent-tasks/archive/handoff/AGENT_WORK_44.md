# AGENT_WORK — Developer master pointer

> **THE ONLY ACTIVE TASK IS TASK_137.**
> TASK_133, 134 and 136 are complete (`DEV_HANDOFF.md` → `ALL_DONE`). Do not reopen them.
> TASK_135 exists but is **NOT active** — do not start it unless this file says so.

**Active task:** `agent-tasks/TASK_137_shortlist_exclude_so.md`
**Created:** 2026-08-01 by Cowork

---

## What it is

A **one-line change.** The Shortlist is showing `SO` ("Sell Overage") rows. `SO` is a
position-sizing action — it fires because a holding drifted above its category ceiling,
not because the market said anything — so it does not belong among the three
edge-validated trades.

Add one condition to `_SHORTLIST_SQL` in `api/routers/cockpit.py`:

```sql
AND COALESCE(a.final_code, '') <> 'SO'
```

and update the comment above it so nobody re-admits it later.

---

## Scope — exclusive and deliberately tiny

The user's instruction was explicit: **"Don't show this in shortlist. Don't need to touch
anything else."**

Do **not** add a footer count, a link, an "over category max" note, or any other
compensating UI. Do not adjust other action codes, the 3-row cap, the sort, or
`web/app.js`. Nothing under `etl/`, `db/`, `web/` or `tests/`.

One line in one file. Resist scope creep — this is the whole task.

**Ignore entirely:** `AGENT_WORK_1.md` … `AGENT_WORK_40.md`, `agent-tasks/TASK_89` …
`TASK_136`, all `AGENT_RESULT_*.md` and `TEST_REPORT_*.md`, `COWORK_IMPL_LOG.md`,
`_trash_2026-05-12/`, `_backups/`, root-level `_*.py` scripts. History, not a backlog.

---

## Hard rules

- **No questions.** The change is fully specified.
- **No tests.** Do not write, extend or run anything under `tests/`. Do not hand off to
  the tester agent. This overrides repo convention #18 — the user asks for tests
  explicitly when they want them.
- **No commits, no pushes.** The user commits from Windows.
- **Do not touch `web/actionable.js` / `web/actionable.html`** — they carry an unrelated
  uncommitted diff that is the user's own in-progress work.

---

## Log

Append a short `# Dev Handoff — TASK_137` section to `DEV_HANDOFF.md` below the existing
ones — do not overwrite prior sections. End with `ALL_DONE`.
