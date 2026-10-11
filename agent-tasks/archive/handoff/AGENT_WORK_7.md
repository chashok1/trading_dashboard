# AGENT_WORK — Developer pointer

`/dev-cycle` starts here. Implement the task spec below, log to `DEV_HANDOFF.md`,
end with `ALL_DONE`. No commits — Ashok commits from Windows.

## Active task

- **agent-tasks/TASK_96_ingest_log_view.md** — Add `v_ingest_log`, a read-only view
  unioning `meta_file_processed` (file loads, incl. TASK_95 email-rendered files via
  `source_kind`) and `meta_hedgeye_msg` (emails) into one chronological "what got
  ingested" list, with a `channel`/`source_kind` to tell file vs email apart.
  Optional `/api/ingest-log` endpoint. Low risk — read-only over existing ledgers;
  only needs the `source_kind` column TASK_95 already added.

## Status of related work

- **TASK_95** (unify tab-backed feeds on the loader) — developer done (`ALL_DONE`),
  **tester round not yet run** (`AGENT_TASK.md` → `TASK_95_verify.md`). TASK_96 is
  independent of TASK_95's runtime behavior (only its schema), so it can proceed, but
  TASK_95 still needs verifying before it's trusted in production.

## Queued (spec to follow)

- **TASK_97** — feed catalog: canonical `feed_code` + `v_feed_catalog` view.

## Done last rounds

- **TASK_94** — Macro Week Summary reclassified (`ALL_DONE`).
- **TASK_93** — Hedgeye pipeline (tester `DONE`).
