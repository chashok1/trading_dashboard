# TASK_94 — Reclassify "Macro Week Summary Notes" (new weekly Hedgeye product)

**Type:** DB reclassification (code already written). **Author:** Cowork.
**Owner:** Developer agent (has Postgres + can run `etl.hedgeye_fetch`).
**Depends on:** TASK_93 (Hedgeye pipeline, shipped & verified).
**Design:** `docs/hedgeye_feeds_design.md`.

## Background

During TASK_93 verification, one email landed in the UNKNOWN lane — the system
working as designed (it surfaced a brand-new product instead of dropping it).
The email is **"Macro Week Summary Notes | June 26th, 2026"** — a *weekly* Friday
recap, distinct from the daily "THE MACRO SHOW: Summary Notes." Its body is only a
table of contents + a "click here for the full notes" link (Macro Dashboard,
Weekly Commentary, Monthly Quad Forecast all live behind the link — nothing
structured in the email itself). So it classifies as a **weekly ANALYSIS pointer →
`note_repo`**, email_type `macro_week_summary`.

## What Cowork already wrote (review, don't rewrite)

Cowork added the one classifier row in the prior session:
- `etl/hedgeye/classify.py` — `macro_week_summary` route (subject match
  `^Macro Week Summary Notes`, weekly cadence, target `note_repo`, ANALYSIS lane).
- `db/seeds_hedgeye.sql` — matching `ref_hedgeye_email_type` seed row.

Confirm both edits are present and correct before running. If the subject regex
needs tightening so it does NOT also catch the daily "THE MACRO SHOW: Summary
Notes," fix it in `classify.py` (the daily must keep routing to its existing type).

## Steps (developer — DB access required)

1. **Confirm code is in place.** `grep -n macro_week_summary etl/hedgeye/classify.py
   db/seeds_hedgeye.sql` → both should show the new route/seed.

2. **Re-seed the router table:**
   ```
   psql -d trading -f db/seeds_hedgeye.sql
   ```
   Confirm: `SELECT * FROM ref_hedgeye_email_type WHERE email_type='macro_week_summary';`

3. **Clear the logged UNKNOWN** so the idempotency check (`meta_hedgeye_msg`) doesn't
   skip the re-run:
   ```sql
   DELETE FROM note_repo
     WHERE message_id IN (SELECT message_id FROM meta_hedgeye_msg WHERE email_type='unknown');
   DELETE FROM meta_hedgeye_msg WHERE email_type='unknown';
   ```

4. **Re-run the backfill** for the affected day:
   ```
   python -m etl.hedgeye_fetch --backfill 2026-06-26
   ```

5. **Verify** it reclassified and nothing else regressed (see below).

## How to verify

- `SELECT email_type, status, count(*) FROM meta_hedgeye_msg GROUP BY 1,2 ORDER BY 1;`
  → a `macro_week_summary | ok | 1` row appears; **zero** `unknown` rows remain.
- `SELECT note_date, left(title,60) FROM note_repo WHERE note_date='2026-06-26'
   ORDER BY 1 DESC;` → the Macro Week Summary note is present (notes count rises from
   9 → 10 for 6/26; nothing else changed).
- Daily "THE MACRO SHOW: Summary Notes" still routes to its existing type (not
  swallowed by the new weekly regex) — confirm its rows are untouched.
- Idempotent: re-run `python -m etl.hedgeye_fetch --backfill 2026-06-26` → counts
  unchanged.
- `pytest tests/test_hedgeye_classify.py -q` → green (add a classify test for the
  new weekly subject if not already covered).

## Done criteria

`macro_week_summary` row in `ref_hedgeye_email_type`; the 6/26 email reclassified out
of UNKNOWN into `note_repo`; zero `unknown` rows; daily summary-notes routing intact;
idempotent on re-run; `pytest tests/test_hedgeye_classify.py` green. Log progress to
`DEV_HANDOFF.md`, ending `ALL_DONE`. No commits — Ashok commits from Windows.
