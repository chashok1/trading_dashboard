# AGENT_WORK — Developer pointer

`/dev-cycle` starts here. Implement the task spec below, log to `DEV_HANDOFF.md`,
end with `ALL_DONE`. No commits — Ashok commits from Windows.

## Active task

- **agent-tasks/TASK_95_hedgeye_unify_on_loader.md** — Unify the 5 tab-backed
  Hedgeye feeds (RR / IIchg / ETFchg / PS / call) on the EXISTING file loader: the
  email path renders each into the workbook-format file the loader already
  understands, drops it in the watched source dir, and the normal scheduler → loader
  → derive flow ingests it. Removes the duplicate direct-insert for those feeds;
  email-only feeds (RTA/stance/top5/notes/nowcast) stay direct. Adds `source_kind`
  (file|email) + precedence (a real file wins, so no double-loads) and the same file
  feeds Ashok's Excel `Tickers` workbook. Read the spec for the verified file
  conventions, the IIchg confirmation note, and "How to verify."

## Queued (do NOT start yet — specs to follow)

- **TASK_96** — `v_ingest_log` view unioning `meta_file_processed` + `meta_hedgeye_msg`.
- **TASK_97** — feed catalog: canonical `feed_code` + `v_feed_catalog` view.

## Done last round

- **TASK_94** — "Macro Week Summary Notes" reclassified to `macro_week_summary`
  (`note_repo`); zero `unknown` rows. `DEV_HANDOFF.md` ended `ALL_DONE`.
