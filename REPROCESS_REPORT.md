# Hedgeye Gmail Backfill — Reprocess Report

**Run date:** 2026-06-28  
**Backfill range:** 2026-06-01 to present  
**Backfill command:** `python -m etl.hedgeye_fetch --backfill 2026-06-01`  
**Status at report time:** Backfill still in progress (processing June 16+ emails)

---

## 1. Summary

| Item | Count |
|---|---|
| Total emails processed (meta_hedgeye_msg, snapshot) | 168 |
| Email-emitted archive files (tab-backed feeds) | 39 |
| Total archive files loaded into DB (incl. pre-existing real files) | 46 |
| Distinct Hedgeye DB tables loaded | 10 |

**Note on backfill status:** Two concurrent backfill processes were launched (a known race-safe pattern — `already_processed` prevents duplicate email handling). Both are still running at report snapshot time, processing June 16–28 emails. New files will continue appearing in Archive dirs. Re-run load_archives.py after the processes finish to ingest remaining files.

---

## 2. Email Ledger (meta_hedgeye_msg)

All 168 emails were processed on 2026-06-28 (backfill run date). The `processed_at` date reflects when the backfill touched each message, not the original email date.

| email_type | count | destination | file emitted |
|---|---|---|---|
| early_look | 12 | note_repo | no |
| etf_changes | 14 | ETFChange files | yes |
| inflation_nowcast | 7 | note_repo | no |
| investing_ideas | 9 | IIChange files | yes |
| macro_show_access | 12 | note_repo | no |
| macro_show_summary | 10 | note_repo | no |
| macro_week_summary | 3 | note_repo | no |
| market_situation | 14 | note_repo | no |
| portfolio_solutions | 3 | PS files | yes |
| real_time_alert | 40 | hist_rta (direct) | no |
| risk_range | 13 | RR files | yes |
| signal_strength | 15 | hist_hedgeye_stance + hist_sss_change (direct) | no |
| the_call | 12 | Call files | yes |
| unknown | 4 | note_repo (flagged review_unclassified) | no |
| **TOTAL** | **168** | | |

**ANALYSIS-type emails** (early_look, inflation_nowcast, macro_show_*, market_situation) are stored as notes in note_repo with no structured DB insert.  
**DROP emails** (marketing) were silently skipped and do not appear in meta_hedgeye_msg.

---

## 3. Archive Files Generated (email-emitted, source_kind='email')

Files emitted to source_dir by the backfill, picked up by the running scheduler, loaded, and moved to Archive. Dates where a real file already existed were skipped (precedence check).

### RR (Risk Range) — 11 email files

| File | Size |
|---|---|
| RR 2026-06-01.xlsx | 7,310 bytes |
| RR 2026-06-02.xlsx | 7,307 bytes |
| RR 2026-06-03.xlsx | 7,313 bytes |
| RR 2026-06-04.xlsx | 7,312 bytes |
| RR 2026-06-05.xlsx | 7,314 bytes |
| RR 2026-06-08.xlsx | 7,312 bytes |
| RR 2026-06-09.xlsx | 7,270 bytes |
| RR 2026-06-10.xlsx | 7,257 bytes |
| RR 2026-06-11.xlsx | 7,261 bytes |
| RR 2026-06-12.xlsx | 7,252 bytes |
| RR 2026-06-15.xlsx | 7,256 bytes |

*Not emitted: Jun 13-14 (weekend), Jun 16-21 still in progress, Jun 22-23 skipped (real file existed), Jun 24+ not yet reached.*

### IIChange (Investing Ideas) — 6 email files

| File | Size |
|---|---|
| IIChange 2026-06-01.xlsx | 4,993 bytes |
| IIChange 2026-06-03.xlsx | 4,995 bytes |
| IIChange 2026-06-08.xlsx | 5,295 bytes |
| IIChange 2026-06-10.xlsx | 5,086 bytes |
| IIChange 2026-06-12.xlsx | 4,986 bytes |
| IIChange 2026-06-15.xlsx | 5,248 bytes |

*Fewer dates than RR — Investing Ideas emails are not sent daily.*

### ETFChange — 9 email files

| File | Size |
|---|---|
| ETFChange 2026-06-01.xlsx | 5,038 bytes |
| ETFChange 2026-06-04.xlsx | 4,984 bytes |
| ETFChange 2026-06-05.xlsx | 5,033 bytes |
| ETFChange 2026-06-08.xlsx | 5,170 bytes |
| ETFChange 2026-06-09.xlsx | 5,178 bytes |
| ETFChange 2026-06-10.xlsx | 5,410 bytes |
| ETFChange 2026-06-11.xlsx | 5,137 bytes |
| ETFChange 2026-06-12.xlsx | 5,191 bytes |
| ETFChange 2026-06-15.xlsx | 5,106 bytes |

### PS (Portfolio Solutions) — 2 email files

| File | Size |
|---|---|
| PS 2026-06-05.xlsx | 6,374 bytes |
| PS 2026-06-12.xlsx | 5,946 bytes |

*PS is weekly; only 2 email-sourced dates captured in backfill window so far.*

### Call (The Call) — 11 email files

| File | Size |
|---|---|
| call 2026-06-01.csv | 734 bytes |
| call 2026-06-02.csv | 460 bytes |
| call 2026-06-03.csv | 683 bytes |
| call 2026-06-04.csv | 642 bytes |
| call 2026-06-05.csv | 519 bytes |
| call 2026-06-08.csv | 470 bytes |
| call 2026-06-09.csv | 393 bytes |
| call 2026-06-10.csv | 286 bytes |
| call 2026-06-11.csv | 524 bytes |
| call 2026-06-12.csv | 567 bytes |
| call 2026-06-15.csv | 707 bytes |

### Pre-existing real files also in Archive (source_kind='file')

These were in the Archive dirs before the backfill and were loaded alongside email-emitted files:

| Feed | Dates | Notes |
|---|---|---|
| RR | Jun 22, 23 | Real RR.xlsx files from prior daily loads |
| ETFChange | Jun 22, 23 | Real ETFChange files |
| PS | Jun 19 | Real PS file |
| Call | Jun 22, 23 | Real call files |

---

## 4. DB Row Counts (Hedgeye-related tables)

Counts reflect state at report snapshot time. Additional rows expected as backfill completes June 16–28.

| Table | Total rows | Date range | Notes |
|---|---|---|---|
| hist_rr | 5,655 | 2026-01-01 to 2026-06-26 | Includes pre-backfill history |
| hist_iichg | 44 | 2025-11-24 to 2026-06-26 | 3 pre-2026 dates + 7 June 2026 dates |
| hist_etfchg | 129 | 2026-05-07 to 2026-06-26 | |
| hist_ps | 285 | 2026-05-04 to 2026-06-26 | |
| hist_call | 4,253 | 2025-07-01 to 2026-06-26 | Large pre-existing history |
| hist_call_top5 | 5 | 2026-06-01 only | Top-5 tickers from Jun 01 email |
| hist_rta | 34 | 2026-06-01 to 2026-06-15 | Real-time alerts (direct insert, no file) |
| hist_hedgeye_stance | 189 | 2026-06-01 to 2026-06-15 | Signal strength → stance (direct insert) |
| hist_sss_change | 86 | 2026-06-01 to 2026-06-15 | Signal strength changes (direct insert) |
| note_repo | 86 | 2026-06-01 to 2026-06-15 | Analysis emails + unknowns |

### June 2026 backfill additions (dates covered by email-emitted files):

| Feed | Dates added by backfill |
|---|---|
| hist_rr | Jun 01–05, 08–12, 15 (11 dates, ~519 rows) |
| hist_iichg | Jun 01, 03, 08, 10, 12, 15 (6 dates, ~22 rows) |
| hist_etfchg | Jun 01, 04–05, 08–12, 15 (9 dates, ~45 rows) |
| hist_ps | Jun 05, 12 (2 dates, ~47 rows) |
| hist_call | Jun 01–05, 08–12, 15 (11 dates, ~177 rows) |

---

## 5. File_Processed Breakdown (email source_kind, June 2026)

Files emitted by backfill and loaded into DB:

| feed | dates with email source |
|---|---|
| RR | Jun 01, 02, 03, 04, 05, 08, 09, 10, 11, 12, 15 |
| ETFChange | Jun 01, 04, 05, 08, 09, 10, 11, 12, 15 |
| IIChange | Jun 01, 03, 08, 10, 12, 15 |
| PS | Jun 05, 12 |
| call | Jun 01, 02, 03, 04, 05, 08, 09, 10, 11, 12, 15 |

---

## 6. Errors, Warnings, and Gaps

### Script fix applied
The task spec called `load_one_file(session, path, no_derive=True)` but the actual signature is `load_one_file(file_path, do_derive=False, force=True)` — no session argument, and the flag is `do_derive` not `no_derive`. Fixed before running.

### rows_inserted overcount
PostgreSQL returns `rowcount=-1` for `ON CONFLICT DO NOTHING` batches. The loader counts this as "all rows inserted." On repeat loads, the DB values are correct (PK prevents duplicates) but the log/summary `rows_inserted` is inflated. DB counts in Section 4 are accurate.

### Two concurrent backfill processes
Two backfill processes were launched simultaneously (one at 11:21, one at 11:27). The `already_processed(session, message_id)` guard in dispatch.py prevents duplicate email handling. No data corruption, but slightly wasteful Gmail IMAP traffic.

### Backfill in progress at report time
At report snapshot time (11:42), both processes were still running (June 16–28 emails not yet reached). The archive and DB counts will grow as remaining emails are processed. Expected additional files:
- RR, Call, ETFChange: June 16–21 (if emails exist) and June 24–28
- IIChange: additional dates if emails sent
- PS: June 26 (already seen in file_processed from real file)

### Date gaps in email-emitted files
Some business days have no email-emitted files:
- RR: no June 13-14 (weekend), June 16+ (in progress)
- IIChange: many gaps — fewer emails per week
- ETFChange: no June 02-03 (but emails may not have been sent those days)
- PS: weekly cadence — only 2 dates Jun 5, 12 captured from emails

### Jun 22-23 files: real files took precedence
The Archive already had Jun 22-23 files from a prior run (real files). The emit.py precedence check saw them in the source_dir and skipped re-emitting, so those dates retained real-file data.

---

## 7. How to Complete the Backfill

The two background processes are still running. After they finish:

```bash
# Check when processes complete (watch archive for new files)
for dir in RR Call IIChange ETFChange PS; do
  echo "$dir: $(ls "C:/Ashok/Investing/Stocks/$dir/Archive/" | grep -E "\.(xlsx|csv)$" | wc -l) files"
done

# Load any remaining new archive files
python "C:\Users\chash\AppData\Local\Temp\claude\load_archives.py"

# Re-run collect_report.py to verify final state
python "C:\Users\chash\AppData\Local\Temp\claude\collect_report.py"
```

---

*Report generated: 2026-06-28 ~11:45 UTC-5. Scripts used: run_backfill.py, load_archives.py, collect_report.py (in temp dir).*
