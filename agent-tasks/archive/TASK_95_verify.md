# TASK_95 — Verification checklist (tester round)

Verify against the **live** Postgres + a **running scheduler** on Windows. Pre-req:
`DEV_HANDOFF.md` ends `ALL_DONE` (it does). Write evidence to `AGENT_RESULT_95.md`,
ending `DONE` or `FAILED: <blocks>`.

## A. Unit + schema (fast, no scheduler)

1. `pytest tests/test_hedgeye_emit.py -q` → 37 passed.
2. `pytest tests/test_hedgeye_emit.py tests/test_hedgeye_dispatch_adapter.py tests/test_hedgeye_classify.py tests/test_hedgeye_parsers.py -q` → 89 passed.
3. Full `pytest tests/` → no NEW failures vs the pre-existing baseline.
4. Schema: `meta_file_processed.source_kind` column exists; `meta_file_origin` table exists.

## B. Live integration (scheduler running, hedgeye enabled)

Restart the server/scheduler first (etl/ changed). Then
`python -m etl.hedgeye_fetch --backfill 2026-06-26`.

5. For each in-scope feed with an email that day, a file is written to its
   `source_dir` (RR/IIChange/ETFChange/PS → `…\Archive\<TYPE> 2026-06-26.xlsx`;
   call → `…\Call\Archive\call 2026-06-26.csv`).
6. The scheduler picks each up and loads it into the right `hist_*` table
   (`hist_rr/hist_iichg/hist_etfchg/hist_ps/hist_call`). Confirm row counts > 0.
7. `SELECT file_type, source_kind FROM meta_file_processed WHERE file_date='2026-06-26';`
   → the 5 emitted feeds show `source_kind='email'`; an ordinary feed (e.g. TOSD) shows `file`.

## C. The high-risk checks (focus here)

8. **IIChange now mirrors ETFChange exactly (per TASK_99).** The emitted
   `IIChange …xlsx` must have the same sheet (`Data Sheet`) and headers (`Date`,
   ` Description`, ` Ticker`, ` Outlook`, ` Action`, leading spaces) as a real
   ETFChange file — diff the two; only the data should differ. Then validate the load:
   `hist_iichg` rows produced via the rendered file match what the TASK_93 direct-insert
   produced (same `symbol`, `outlook`, `change_str`/action), and the investing-ideas
   **add** AND the MDB-style **remove** both land with action populated.
   (Pre-req: TASK_99 done first.)
9. **Scheduler watches the IIChange dir.** Confirm `C:\Ashok\Investing\Stocks\IIChange\Archive`
   is registered/watched (file_type `IIChange` in `ref_load_files`) — emit creates the
   folder, but the watcher must load from it.
10. **call date fallback.** Confirm the rendered `call …csv` (header `Date`, `M/D/YYYY`)
    loads dates correctly via the `Imported Date`→`Date` fallback in `load_raw.py`
    (`hist_call.snapshot_date` populated, not NULL).
11. **Precedence — real file wins.** With a real RR file already present in `RR\Archive`
    for a date, re-run backfill → log shows precedence skip for RR, `hist_rr` count
    unchanged, no second file written.
12. **Derive ran.** After the scheduler loads the files, `drv_*` / `drv_actionable` for
    2026-06-26 reflect the new rows (derive fired via the loader, not the email path).

## D. Out-of-scope unchanged

13. Real-Time Alert email → `hist_rta` via direct insert; `hist_call_top5`,
    `hist_hedgeye_stance`, `note_repo`, macro nowcast still populate directly; idempotent
    on re-run.

## Verdict

`DONE` only if A–D pass. Any mismatch in C8/C10/C12 → `FAILED: <block>` with the
offending rows quoted. No commits — Ashok commits from Windows.
