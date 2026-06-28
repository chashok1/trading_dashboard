# TASK_101 — Re-process Hedgeye emails + fix Actionable panel not showing data

**Type:** reprocess + diagnose + fix (DB + app). **Author:** Cowork. **Owner:** Developer.
**Symptom (Ashok):** Hedgeye data loaded and was visible, but the Hedgeye panel on
`/actionable` now shows nothing.

## Step 1 — Re-process the emails

Re-run ingestion and confirm rows land:
```
python -m etl.hedgeye_fetch --once          # or --backfill <earliest date>
```
Then record the dates the data is on:
```sql
SELECT 'rr'    t, MAX(snapshot_date) FROM hist_rr
UNION ALL SELECT 'rta',   MAX(snapshot_date) FROM hist_rta
UNION ALL SELECT 'top5',  MAX(snapshot_date) FROM hist_call_top5
UNION ALL SELECT 'stance',MAX(snapshot_date) FROM hist_hedgeye_stance
UNION ALL SELECT 'notes', MAX(note_date)     FROM note_repo;
SELECT MAX(export_date) AS anchor FROM hist_td;   -- the Actionable screen's default date
```

## Step 2 — Confirm the likely root cause (date alignment)

The panel (`web/hedgeye_panel.js`) calls `GET /api/actionable/hedgeye?date=<#datePicker>`,
which defaults to the **anchor** (`MAX(export_date)` from hist_td). In
`api/routers/hedgeye.py`:
- `alerts`  → `WHERE snapshot_date = :d` (exact)
- `trend_flips` → `WHERE as_of_date = :d` (exact)
- `top5` / `stance` → latest `snapshot_date <= :d`

So if the Hedgeye data's date is **newer than the anchor** (Hedgeye emails arrive daily/
intraday; the anchor only advances on a TOSD market-close load), every section is empty
and the panel hides itself (`hasAny === false → display:none`). Verify by hitting the
endpoint with both dates:
```
GET /api/actionable/hedgeye?date=<anchor>          # likely empty
GET /api/actionable/hedgeye?date=<hedgeye max date> # likely populated
```

## Step 3 — Fix

Decide and implement the right behavior (recommended: **show the most recent Hedgeye
data, don't pin it to an older anchor**):

- In `api/routers/hedgeye.py`, make `alerts` and `trend_flips` use a **window ending at
  the latest available data**, not an exact-date match — e.g. the latest activity within
  the last N days on/before the effective date, OR clamp the effective date up to
  `GREATEST(:d, MAX(hedgeye data date))`. Keep `top5`/`stance` latest-on-or-before.
- Make the response report the actual date each section came from (so the UI can label
  "as of …"), since it may differ from the screen date.
- Confirm the panel does not hide when data exists; if you keep hide-when-empty, ensure a
  populated response actually renders.

Pick the cleanest approach consistent with the periodic-feed carry-forward model in
`docs/derive_date_logic.md` (Hedgeye feeds are periodic ≤ D, like rr/call/etf).

## Step 3b — Why are no files generated in the Archive folders?

Ashok reports the email path isn't writing workbook files into the watched Archive dirs
(RR/IIChange/ETFChange/PS/call). `etl/hedgeye/emit.py::write_feed` skips writing in three
cases — determine which applies:

1. **Idempotency (most likely).** The original TASK_93 run recorded these emails in
   `meta_hedgeye_msg` but did NOT emit files. `hedgeye_fetch._process_pass` skips any
   `already_processed(message_id)`, so the emit step never runs on re-run. Check:
   ```sql
   SELECT email_type, count(*) FROM meta_hedgeye_msg GROUP BY 1 ORDER BY 1;
   ```
   To regenerate, clear the relevant ledger rows (and re-derive as needed), then
   `--backfill`:
   ```sql
   DELETE FROM meta_hedgeye_msg
    WHERE email_type IN ('risk_range','investing_ideas','etf_changes',
                         'portfolio_solutions','the_call');
   ```
   Then `python -m etl.hedgeye_fetch --backfill <date>` and watch for emit log lines
   (`emit: wrote …`).

2. **Precedence — real file already present.** `_file_exists_for_date` skips when an
   existing file matches that feed+date in `source_dir`. If Ashok already exported real
   files there, this is by design. Confirm by checking the folder vs the data date.

3. **source_dir not resolving.** `_get_source_dir` needs `ref_load_files.source_dir`
   for that `file_type` with `enabled=TRUE`. Check each — esp. `IIChange` (never had real
   files):
   ```sql
   SELECT file_type, source_dir, enabled FROM ref_load_files
    WHERE UPPER(file_type) IN ('RR','IICHANGE','ETFCHANGE','PS','CALL');
   ```
   Fix any missing/disabled row or wrong path. Confirm the folder exists + is writable.

Decide the intended behavior with Ashok's workflow in mind: the email file should be
generated when it's the source of that day's data (so it can feed the Excel workbook),
and skipped only when a real export already exists. Adjust the ledger-clear / precedence
logic accordingly and confirm files actually appear in the Archive folders after a run.

## Step 4 — Verify UI functionality

- `/actionable` → the Hedgeye panel (below the macro band) shows Top-5 / Alerts / RR
  flips / stance with the reprocessed data. No console errors; `hedgeye_panel.js` loaded.
- Symbol links in the panel open `/symbol-hedgeye?sym=…` and that dossier shows data.
- `/digest` (pre-open + weekly) and `/notes` render the reprocessed notes.
- Spot-check the other endpoints still return 200.

## Done criteria

Emails reprocessed; root cause confirmed; panel shows the current Hedgeye data on
`/actionable` (and the date logic no longer hides newer data behind an older anchor);
UI screens verified. Log to `DEV_HANDOFF.md`, end `ALL_DONE`. No commits — Ashok commits
from Windows.
