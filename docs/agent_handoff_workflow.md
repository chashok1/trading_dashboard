# Agent Handoff Workflow (Cowork → Developer → Tester)

This is the standing process for changes in this repo. `CLAUDE.md` convention
#17 points here; it auto-loads every session so a fresh Cowork session follows
this without being re-told.

## Roles

- **Cowork (Claude desktop)** — orchestrator / architect by default.
  Investigates, traces the pipeline, plans, and **authors task specs**. By
  default Cowork does not edit code — but **if the user explicitly asks Cowork
  to write or fix code, it does so directly.** Cowork never runs DB queries
  regardless (no DB access — the sandbox cannot reach the local Postgres at
  `localhost:5432`); database work always goes to the developer. Cowork reviews
  results and reports to the user.
- **Developer agent (in VS Code)** — implements the task specs, runs the code,
  and has `psql` / database access. Logs its progress in `DEV_HANDOFF.md` and stops
  at `ALL_DONE`. Does not invoke the tester.
- **Tester agent (in VS Code)** — verifies the developer's work against a live
  Postgres + running app, and writes a pass/fail report. **Runs only when the user
  explicitly requests a test round — never by default.**

## The flow

1. **Cowork writes the task spec.** One file per task: `agent-tasks/TASK_<n>_<slug>.md`.
   Each spec includes the goal, the files expected to change, and a concrete
   **"How to verify"** section the tester will run. Cowork then creates
   **`AGENT_WORK.md`** in the project root — the developer's master pointer, and
   the file the `/dev-cycle` command reads to start. `AGENT_TASK.md` is the
   separate pointer the **tester** runs for the verification round.
2. **Developer agent implements.** Works through the task spec(s), edits code,
   runs migrations / derives via `psql` and `python -m ...`. Records every change
   (files changed, decisions, risks) in `DEV_HANDOFF.md`, ending the file with
   the literal marker `ALL_DONE` when finished. If not done, it does not write
   `ALL_DONE`. The developer does **not** hand off to the tester — it stops at
   `ALL_DONE` and reports back.
3. **Testing is on-request only.** Do **NOT** hand off to the tester by default.
   A tester round runs only when **the user explicitly asks for it**. When the user
   does ask, point the tester at `AGENT_TASK.md`; it runs the verification blocks
   and writes evidence to `AGENT_RESULT_<n>.md`, ending with `DONE` or
   `FAILED: <blocks>`. Pre-req gate: `DEV_HANDOFF.md` must end with `ALL_DONE`
   first, else the tester stops and reports. Until the user asks, the spec's
   "How to verify" section is just reference — nobody runs it automatically.
4. **Cowork reviews** the developer's `DEV_HANDOFF.md` (and `AGENT_RESULT_<n>.md`
   if a test round was requested), relays the outcome to the user, and plans the
   next task or fix.
5. **User commits.** No agent commits or pushes — the user commits from Windows
   after a task passes. (This overrides `CLAUDE.md` convention #13 within this
   flow.)

## File naming conventions

| File | Written by | Purpose |
|---|---|---|
| `agent-tasks/TASK_<n>_<slug>.md` | Cowork | One task spec; includes "How to verify" |
| `AGENT_WORK.md` | Cowork | Developer's master pointer — the file `/dev-cycle` reads to start |
| `AGENT_TASK.md` | Cowork | Tester's pointer to the verification round |
| `DEV_HANDOFF.md` | Developer | Running implementation notes; ends `ALL_DONE` |
| `AGENT_WORK_<n>.md` | Cowork/Developer | Detailed work item (legacy / per-item) |
| `AGENT_RESULT_<n>.md` | Tester | Verification evidence; ends `DONE` / `FAILED: <blocks>` |
| `TEST_REPORT_<n>.md` | Tester | Standalone test report |

Markers are load-bearing: `ALL_DONE` gates testing; `DONE` / `FAILED` gates the
user's commit. Keep numbering sequential with the latest existing files.

## What Cowork does by default (and the exceptions)

By default Cowork does NOT:

- Edit code in `etl/`, `api/`, `web/`, `db/`, etc. — **unless the user
  explicitly asks it to write or fix code**, in which case it does so directly.
- Commit or push (always the user, from Windows — no exception).

Cowork NEVER (no exception):

- Runs SQL / `psql` / derives against the database — it has no DB access, so
  database work always goes to the developer agent.

Cowork always CAN: write planning/analysis docs (e.g. `docs/*.md`,
`docs/audit/*.md`), task specs, and process documentation — none of which is
code.
