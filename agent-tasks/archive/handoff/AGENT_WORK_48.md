# AGENT_WORK — Developer master pointer

**Created:** 2026-10-10 by Cowork
**This round: TASK_148 ONLY.** Do not work on, reopen, or "finish" any other
task — including TASK_145's outstanding browser check. Anything not in
Step 0 or `agent-tasks/TASK_148_macro_week_strip.md` is out of scope.

---

## Step 0 — Clean up previous task files (do this first)

Goal: the repo root and `agent-tasks/` show only the current round.
**Move, never delete** — most of these files are untracked by git, so a delete
is unrecoverable. Use `git mv` for tracked files, plain move for untracked ones.

| Move these | To |
|---|---|
| `agent-tasks/TASK_*.md` **except TASK_148** (TASK_89 → TASK_147, 61 tracked + 1 untracked) | `agent-tasks/archive/` |
| Root `AGENT_WORK_<n>.md` (47), `TEST_REPORT_<n>.md` (24), `AGENT_RESULT_<n>.md` (1) | `agent-tasks/archive/handoff/` |
| Root `DEV_HANDOFF.md` (current, ends `PARTIAL: TASK_145`) | `agent-tasks/archive/handoff/DEV_HANDOFF_ARCHIVE_TASK147.md` |
| Root `DEV_HANDOFF_ARCHIVE_TASK132.md`, `COWORK_IMPL_LOG.md`, `AGENT_RESULT_93.md` | `agent-tasks/archive/handoff/` |

Then:
1. Start a fresh, empty `DEV_HANDOFF.md` at the root (header only) for TASK_148.
2. Reset `AGENT_TASK.md` to: "NO TEST ROUND PENDING. Current work: TASK_148 — see `AGENT_WORK.md`."
3. Fix any live reference that pointed at a moved file — grep `CLAUDE.md`,
   `docs/`, `.claude/`, `agent-setup/` for `AGENT_WORK_`, `TEST_REPORT_`,
   `DEV_HANDOFF_ARCHIVE`, `agent-tasks/TASK_`. Update paths to the archive;
   don't rewrite history docs (`docs/migrations.md` entries may keep old names).
4. Add one line to `docs/agent_handoff_workflow.md`: finished task specs and
   handoff files are archived to `agent-tasks/archive/` at the start of each new round.

**Do NOT touch:**
- Any uncommitted code changes already in the working tree (`git status` shows
  modified `CLAUDE.md`, `etl/`, `docs/`… from earlier work) — leave them exactly as is.
- Root scripts, logs, `_trash_*`, `_backups` — separate cleanup, not this round.
- `AGENT_WORK.md`, `agent-tasks/TASK_148_macro_week_strip.md`, `docs/mockups/`.

Record in `DEV_HANDOFF.md` under `## Step 0 — Cleanup`: counts moved per row,
references fixed, and `git status --short` before/after.

---

## Step 1 — TASK_148

Spec: `agent-tasks/TASK_148_macro_week_strip.md`
Acceptance reference: `docs/mockups/macro_week_strip_mockup_v2.html`
(layout + rules; numbers illustrative). Ignore the v1 mockup.

- The user asked that **you choose the best implementation** — you have more
  context than Cowork. The spec fixes **what** and the verdict rules; the
  **how** is yours. Where spec and live code/data disagree, trust live and say so.
- Answer the spec's "Things Cowork could NOT verify" list first, from the DB.
- Display only — see the spec's Constraints.
- Spec references to older tasks (TASK_94, 133, 142) now live in `agent-tasks/archive/`.

---

## Reporting
`DEV_HANDOFF.md`: `## Step 0 — Cleanup`, then `## TASK_148 — Macro Week Strip`
(files changed, decisions, SQL used to check each chip, risks), then `## Status`
ending `ALL_DONE` or `PARTIAL: <what's left>`. Run the "How to verify" items
yourself. **No test round** — do not invoke the tester. No commits or pushes;
the user commits from Windows.
