# AGENT_WORK — Developer pointer

## Active task — TASK_105 (fix PS blank columns + missing Jun 26 files for Call/ETF/II)

Four issues to fix, all in `etl/hedgeye/parsers.py` (and possibly dispatch/emit):

### Issue 1 — PS: all blank values for 1-WEEKCHANGE, 1-MONTHCHANGE, ENTRYDATE, ASSET CLASS, POSITIONSIZING
The PS 2026-06-26.xlsx file has rows but all those columns are blank/None.
`parse_portfolio_solutions` is likely extracting Rank+Ticker but not the remaining columns.
Fix: read the actual PS email HTML table and map all columns correctly.

### Issue 2 — Call: missing call 2026-06-26.csv (only Jun 24 exists)
`the_call` had 3 emails (Jun 24/25/26 per prior ledger dump) but only 1 file was emitted.
Fix: understand why Jun 25 and Jun 26 call emails weren't emitted and fix.

### Issue 3 — ETFChange: missing ETFChange 2026-06-26.xlsx (only Jun 24 exists)
`etf_changes` had 3 emails but only 1 file was emitted.

### Issue 4 — IIChange: missing IIChange 2026-06-26.xlsx (only Jun 24 exists)
`investing_ideas` had 3 emails but only 1 file was emitted.

## Root cause hypothesis for Issues 2/3/4
The Jun 25 and Jun 26 emails for call/ETF/II were likely processed by the scheduler
BEFORE the backfill cleared the ledger, going via direct insert (no file emit). Or the
precedence check found existing files in the Archive dir. Check:
1. What's in meta_hedgeye_msg for those email_types (are Jun 25/26 present?)
2. What's in the Archive dirs for those dates
3. Whether emit.write_feed ran but found existing files (precedence skip)

## Steps

1. Diagnose each issue by querying DB and checking Archive dirs
2. Fetch raw email bodies for PS to fix column mapping
3. Fix parsers.py for PS columns
4. Clear state (ledger + file_processed + hist rows) for all affected feeds/dates
5. Reprocess: `python -m etl.hedgeye_fetch --backfill 2026-06-24`
6. Manually load emitted files
7. Verify: ALL 5 feeds have files for ALL available dates; PS xlsx has all columns populated

Archive AGENT_WORK.md → AGENT_WORK_15.md. Log to DEV_HANDOFF.md, end ALL_DONE. No commits.
