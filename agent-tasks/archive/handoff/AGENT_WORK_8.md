# AGENT_WORK — Developer pointer

`/dev-cycle` starts here. Implement the task spec below, log to `DEV_HANDOFF.md`,
end with `ALL_DONE`. No commits — Ashok commits from Windows.

## Active task

- **agent-tasks/TASK_98_ingest_log_screen.md** — Add the Ingest Log dashboard screen
  (`web/ingest_log.html` + `.js`, `/ingest-log` page route, nav link) over the
  existing `GET /api/ingest-log` from TASK_96. Mirror the File Monitor screen. Filters
  for channel/feed/date; flag email-origin rows. Read-only, low risk; the API already
  exists.

## Queued — do NOT start until its gate is met

- **agent-tasks/TASK_97_feed_catalog.md** — Additive `feed_code` on both registries +
  `v_feed_catalog` view (one feed, both filename + subject recognizers). **Gate:**
  implement only AFTER TASK_95 is verified (`AGENT_RESULT_95.md` = `DONE`) and the
  IIChange format is confirmed against a real sample — both can still change feed
  definitions this catalogs.

## Status of related work

- **TASK_95** (unify on loader) — developer done (`ALL_DONE`); tester round still not
  run (`AGENT_TASK.md` → `TASK_95_verify.md`). Real open item.
- **TASK_96** (ingest-log view + API) — `ALL_DONE`.

## Done earlier

- **TASK_94** — Macro Week Summary reclassified (`ALL_DONE`).
- **TASK_93** — Hedgeye pipeline (tester `DONE`).
