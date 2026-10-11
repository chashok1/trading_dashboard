# AGENT_WORK — Developer pointer

## Active task — TASK_102 (clean reprocess so Archive files get generated)

- **agent-tasks/TASK_102_clean_reprocess_see_files.md** — Ashok wants to SEE the emit /
  unify-on-loader code work before real files arrive Monday: reset the blocking state
  (email ledger + meta_file_processed + back up/move existing Archive files; optionally
  clear raw rows for 2026-06-24→26), reprocess `--backfill 2026-06-24`, and **confirm the
  workbook files actually appear in the Archive folders** (RR/IIChange/ETFChange/PS/call),
  then load → DB → Actionable panel. Deleting test data is authorized; back up first.
  Include the **TASK_101 panel date-fix** (show latest Hedgeye data, don't pin to an older
  anchor) in Step 4 so the UI shows the reprocessed data.
- Most likely blocker: emails already in `meta_hedgeye_msg` (processed under the old
  direct-insert pipeline) → emit never runs on re-run. Clearing the ledger + moving any
  existing Archive files (precedence) is what makes emit write.
- Developer MAY edit code (the panel date fix). Log to `DEV_HANDOFF.md` with folder
  listings as proof, end `ALL_DONE`. No commits — Ashok commits from Windows.

## Supersedes
- **TASK_101** (panel visibility) — its diagnosis + fix is absorbed into TASK_102 Step 4.

## Context
Full Hedgeye enhancement set is coded + dev-verified to load (see `COWORK_IMPL_LOG.md`).
This task proves the email→file→DB→UI path end-to-end on test data.
