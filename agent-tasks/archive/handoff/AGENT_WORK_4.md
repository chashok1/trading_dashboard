# AGENT_WORK — developer pointer

Current round: **TASK_93 — Wire up & run the Hedgeye email pipeline**.

Read `agent-tasks/TASK_93_hedgeye_pipeline.md` and implement it. The deterministic core
(`etl/hedgeye/`, `etl/hedgeye_fetch.py`), DDL (`db/hedgeye_schema.sql`,
`db/seeds_hedgeye.sql`) and unit tests are already written by Cowork — your job is DB
apply, existing-table column reconciliation, IMAP credentials, live run + backfill, and
scheduling. Log progress to `DEV_HANDOFF.md`, ending `ALL_DONE`.

When done, the tester round is `agent-tasks/TASK_93_hedgeye_verify.md` — point
`AGENT_TASK.md` at it (it currently references the prior TASK_91 round) and the tester
writes `AGENT_RESULT_93.md`.

No commits — Ashok commits from Windows.
