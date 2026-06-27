# TASK_97 — Feed catalog (one feed identity, two recognizers)

**Type:** implementation (additive schema + view). **Author:** Cowork. **Owner:** Developer.
**Depends on:** TASK_95 + TASK_99 (IIChange format settled).  **⚠ Sequence:** implement
**after TASK_99 lands** — the IIChange format is now fixed (= ETFChange), so the feed
definitions this catalogs are stable. **Testing is deferred to the end** (per Ashok), so
do NOT gate this on a TASK_95 tester round; proceed once TASK_99 is done. Final
verification happens in the batch round.

## Why

The same logical feed has two names in two registries: the file side calls it `RR`
(`ref_load_files.file_type`), the email side calls it `risk_range`
(`ref_hedgeye_email_type.email_type`). That split is the root of question 1 ("two ways
to classify the same data"). This task gives each feed **one canonical identity** with
**both** recognizers attached, without rewriting the loader — purely additive.

## Approach (additive — do NOT merge/drop the existing tables)

1. **Add `feed_code TEXT`** to both `ref_load_files` and `ref_hedgeye_email_type`
   (nullable; idempotent `ADD COLUMN IF NOT EXISTS` in `db/baseline.sql`).

2. **Populate `feed_code`** for the overlapping feeds (one canonical code each):

   | feed_code | file_type (ref_load_files) | email_type (ref_hedgeye_email_type) |
   |---|---|---|
   | `RISK_RANGE` | RR | risk_range |
   | `INVESTING_IDEAS` | IIChange | investing_ideas |
   | `ETF_CHANGES` | ETFChange | etf_changes |
   | `PORTFOLIO_SOLUTIONS` | PS | portfolio_solutions |
   | `THE_CALL` | call | the_call |

   File-only feeds (TOSD/TOSL/Y/…) get their own `feed_code` = the file_type (or a
   tidy uppercase form); email-only feeds (real_time_alert, hedgeye stance, top3,
   notes, nowcast, etc.) get a `feed_code` too. Seed these in `db/seeds_*.sql`
   (idempotent). Every data-bearing source ends up with exactly one `feed_code`.

3. **`v_feed_catalog` view** — one row per `feed_code`, exposing both recognizers and
   where each lands:
   ```sql
   CREATE OR REPLACE VIEW v_feed_catalog AS
   SELECT
       COALESCE(lf.feed_code, et.feed_code)        AS feed_code,
       lf.file_type,
       lf.source_dir,
       lf.target_tab,
       et.email_type,
       et.subject_re,
       et.destination,
       COALESCE(lf.enabled, TRUE) AND COALESCE(et.enabled, TRUE) AS enabled
   FROM ref_load_files lf
   FULL OUTER JOIN ref_hedgeye_email_type et ON lf.feed_code = et.feed_code;
   ```
   (Adjust columns to the real schemas; keep it a faithful join, file recognizer on
   one side, subject recognizer on the other.)

4. **CLAUDE.md Lookup row:** "Unified feed catalog (file + email recognizers) →
   `v_feed_catalog` (db/baseline.sql); `feed_code` on ref_load_files + ref_hedgeye_email_type."

## Explicitly NOT in scope

- Do **not** change the loader, `mappings.HIST_MAPS`, `classify.py`, or any ingest
  behavior. `feed_code`/`v_feed_catalog` are descriptive only — nothing reads them to
  route data yet. (A later task can migrate routing onto `feed_code` once this proves out.)
- No UI.

## How to verify

- `SELECT feed_code, file_type, email_type FROM v_feed_catalog ORDER BY feed_code;`
  → the 5 overlapping feeds show BOTH `file_type` and `email_type` on one row; file-only
  feeds show `email_type` NULL; email-only feeds show `file_type` NULL. No feed_code is
  NULL for any data-bearing source.
- Every `feed_code` is unique per logical feed (no two unrelated feeds share one).
- Ingest still works unchanged (run a normal file load + a Hedgeye backfill → same
  results as before; this task added nothing to the hot path).
- `pytest tests/` → no new failures.

## Done criteria

`feed_code` on both registries, populated for all data-bearing feeds; `v_feed_catalog`
returns one row per feed with both recognizers; ingest behavior unchanged; CLAUDE.md row
added. Log to `DEV_HANDOFF.md`, end `ALL_DONE`. No commits — Ashok commits from Windows.
