# AGENT_WORK — Developer pointer

`/dev-cycle` starts here. Implement the task spec below, log to `DEV_HANDOFF.md`,
end with `ALL_DONE`. No commits — Ashok commits from Windows.

## Active task

- **agent-tasks/TASK_99_iichange_match_etfchange.md** — Make the emitted IIChange file
  byte-for-byte identical to the ETFChange file (sheet `Data Sheet`; headers `Date`,
  ` Description`, ` Ticker`, ` Outlook`, ` Action` with leading spaces). Rewrite
  `render_investing_ideas` in `emit.py` (mirror `render_etf_changes`), update its unit
  tests, and confirm `load_iichg` still ingests it. **Do this before the TASK_95 tester
  round** so the tester verifies the corrected format.

## Queued (in order)

- **agent-tasks/TASK_98_ingest_log_screen.md** — Ingest Log dashboard screen over the
  existing `/api/ingest-log`. Independent, low risk.
- **agent-tasks/TASK_97_feed_catalog.md** — additive `feed_code` + `v_feed_catalog`.
  **Gate:** only after TASK_95 is verified (`AGENT_RESULT_95.md` = `DONE`). IIChange
  format is now settled (TASK_99), so that part of the gate is resolved.

## Status of related work

- **TASK_95** (unify on loader) — developer done; tester round pending. After TASK_99
  lands, run the tester (`AGENT_TASK.md` → `TASK_95_verify.md`).
- **TASK_96** (ingest-log view + API) — `ALL_DONE`.

## Done earlier

- **TASK_94** — Macro Week Summary reclassified (`ALL_DONE`).
- **TASK_93** — Hedgeye pipeline (tester `DONE`).
