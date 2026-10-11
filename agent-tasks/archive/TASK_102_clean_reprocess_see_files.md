# TASK_102 — Clean reprocess so the Archive files actually get generated

**Type:** reset + reprocess + verify (DB + app). **Author:** Cowork. **Owner:** Developer.
**Goal (Ashok):** prove the new emit / unify-on-loader code works *before* real files
arrive Monday — reprocess the Hedgeye emails from a clean slate and SEE the workbook
files appear in the Archive folders, then flow into the DB and the Actionable panel.
Deleting test data/files is explicitly authorized — but **back up first** (see below).

## Test window
Use the backfill range already in the mailbox: **2026-06-24 → 2026-06-26**. Do all
deletes scoped to this window / the 5 file-backed feeds only.

## Step 1 — Back up (reversible), then clear the blocking state

The reason files aren't generated: the emails are already in the ledger (processed under
the old direct-insert pipeline) and/or real files already sit in the Archive (precedence
skip). Clear both, but preserve anything real.

1. **Back up the real Archive files** for the 5 feeds (don't destroy Ashok's exports):
   move any existing `RR/IIChange/ETFChange/PS/call` files for 6/24–6/26 out of their
   watched `source_dir` into a backup folder (e.g. `…\_backup_test_102\`). This both
   protects them AND lets the precedence check pass so emit will write.
2. **Clear the email ledger** for the 5 file-backed feeds so the emails reprocess:
   ```sql
   DELETE FROM meta_hedgeye_msg
    WHERE email_type IN ('risk_range','investing_ideas','etf_changes',
                         'portfolio_solutions','the_call');
   ```
3. **Clear meta_file_processed** rows for those feeds (so the loader re-ingests the
   regenerated files):
   ```sql
   DELETE FROM meta_file_processed
    WHERE UPPER(file_type) IN ('RR','IICHANGE','ETFCHANGE','PS','CALL')
      AND file_date BETWEEN '2026-06-24' AND '2026-06-26';
   ```
4. **(Optional, for a truly clean view) clear the raw rows** for the window so you can
   watch them repopulate (authorized by Ashok for this test; scoped + reversible via
   re-ingest). `pg_dump` these tables first if you want a safety net:
   ```sql
   DELETE FROM hist_rr      WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26';
   DELETE FROM hist_rta     WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26';
   DELETE FROM hist_iichg   WHERE event_date    BETWEEN '2026-06-24' AND '2026-06-26';
   DELETE FROM hist_etfchg  WHERE event_date    BETWEEN '2026-06-24' AND '2026-06-26';
   DELETE FROM hist_ps      WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26';
   DELETE FROM hist_call    WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26';
   ```

## Step 2 — Confirm prerequisites

- `SELECT file_type, source_dir, enabled FROM ref_load_files
   WHERE UPPER(file_type) IN ('RR','IICHANGE','ETFCHANGE','PS','CALL');`
  → every feed has a real, writable `source_dir` and `enabled=TRUE`. Fix IIChange if its
  row/path is missing (it never had real files). Create the folder if absent.
- `ref_settings`: `hedgeye_enabled=true`, IMAP creds present.
- Start the scheduler (so emitted files get auto-loaded) **and** the app.

## Step 3 — Reprocess and WATCH the files appear

```
python -m etl.hedgeye_fetch --backfill 2026-06-24
```
- Watch the log for `emit: wrote …` lines (one per feed/date written).
- **Confirm the actual files now exist** in each Archive folder, e.g.
  `…\RR\Archive\RR 2026-06-26.xlsx`, `…\IIChange\Archive\IIChange 2026-06-26.xlsx`,
  `…\ETFChange\Archive\…`, `…\PS\Archive\…`, `…\Call\Archive\call 2026-06-26.csv`.
  **List the folder contents in the handoff as proof.**
- Confirm the scheduler then loads them: `meta_file_processed` shows the new files with
  `source_kind='email'`; `hist_rr/rta/iichg/etfchg/ps/call` repopulate for the window.

## Step 4 — Verify it surfaces in the UI

- After load + derive, the Hedgeye panel on `/actionable` shows the reprocessed data.
  If it's empty because the data date is newer than the screen's anchor date, apply the
  date fix from **TASK_101** (show latest Hedgeye data, don't pin to an older anchor).
- Spot-check `/symbol-hedgeye?sym=…`, `/digest`, `/notes` render the reprocessed content.

## Step 5 — Restore

Leave the regenerated email files in place (they're valid). If you moved Ashok's real
exports to the backup folder and they should win, note it — but for THIS test the point
is to see emit produce files, so generated files staying is fine. Document what was moved
so Ashok can restore Monday if needed.

## Done criteria

Ledger/processed state cleared; reprocess run; **workbook files visibly generated in the
Archive folders** (folder listing in the handoff); loader ingests them (`source_kind=
'email'`); raw tables repopulate; Actionable panel + screens show the data. Log to
`DEV_HANDOFF.md` with the folder listings + row counts, end `ALL_DONE`. No commits.
