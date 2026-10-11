# TASK_96 — Unified ingest-log view (`v_ingest_log`)

**Type:** implementation (DB view + optional read API). **Author:** Cowork.
**Owner:** Developer agent. **Depends on:** TASK_95 (adds `meta_file_processed.source_kind`).

## Why

Today "what got ingested?" lives in two places with different shapes:
`meta_file_processed` (every file load) and `meta_hedgeye_msg` (every email).
Ashok wants **one list** showing everything processed — file or email — in one
chronological view he can query (and later surface on a screen).

This is read-only: a view over existing ledgers. No data migration, low risk. It only
requires `meta_file_processed.source_kind` to exist (TASK_95 added it).

## The view

Add to `db/baseline.sql` (idempotent `CREATE OR REPLACE VIEW`):

```sql
CREATE OR REPLACE VIEW v_ingest_log AS
-- file loads: real files AND email-rendered files (source_kind distinguishes them)
SELECT
    'file_load'                    AS channel,
    COALESCE(source_kind, 'file')  AS source_kind,
    file_path                      AS source_ref,
    file_type                      AS feed,
    target_tab,
    file_date                      AS data_date,
    'loaded'                       AS status,
    processed_at
FROM meta_file_processed
UNION ALL
-- emails: email-only direct feeds + the email receipt for tab-backed feeds
SELECT
    'email'                        AS channel,
    'email'                        AS source_kind,
    message_id                     AS source_ref,
    email_type                     AS feed,
    NULL                           AS target_tab,
    NULL::date                     AS data_date,
    status,
    processed_at
FROM meta_hedgeye_msg;
```

### Lineage note (document this, don't try to "fix" it)

A **tab-backed** Hedgeye email (risk_range / investing_ideas / etf_changes /
portfolio_solutions / the_call) intentionally appears **twice**: once under
`channel='email'` (the email arrived + was classified) and once under
`channel='file_load'` with `source_kind='email'` (the file it produced was loaded).
That's the full lineage, by design. For "what actually landed in tables," filter
`WHERE channel='file_load'`. For "what emails arrived," filter `WHERE channel='email'`.

## Steps

1. Add the view to `db/baseline.sql`; `python -m db.init_db`.
2. (Optional, recommended) Read API: `GET /api/ingest-log?date=&channel=&feed=` in
   `api/routers/monitor.py` → `SELECT … FROM v_ingest_log` ordered by `processed_at DESC`,
   with simple optional filters. No new screen in this task (note it as a follow-up).
3. Add a CLAUDE.md Lookup row: "Unified ingest log (file + email) → `v_ingest_log`
   (db/baseline.sql); API `/api/ingest-log`."

## How to verify

- `SELECT channel, source_kind, count(*) FROM v_ingest_log GROUP BY 1,2 ORDER BY 1,2;`
  → file_load/file (real files), file_load/email (TASK_95 rendered files),
  email/email (Hedgeye messages).
- `SELECT * FROM v_ingest_log WHERE data_date='2026-06-26' ORDER BY processed_at DESC;`
  → shows the day's file loads; tab-backed feeds also appear under `channel='email'`.
- A tab-backed feed (e.g. RR) for a day appears in BOTH channels; an email-only feed
  (real_time_alert) appears only under `channel='email'`; an ordinary file (TOSD) only
  under `channel='file_load'` with `source_kind='file'`.
- If the API is added: `GET /api/ingest-log?date=2026-06-26` returns the same rows;
  filters `channel`/`feed` work.
- Full `pytest tests/` → no regressions.

## Done criteria

`v_ingest_log` returns the unioned file + email ledger with `channel`/`source_kind`
distinguishing origin; lineage documented; (optional) `/api/ingest-log` works; CLAUDE.md
Lookup row added. Log to `DEV_HANDOFF.md`, end `ALL_DONE`. No commits — Ashok commits
from Windows.

## Out of scope

An ingest-log UI screen (follow-up); the feed catalog (TASK_97).
