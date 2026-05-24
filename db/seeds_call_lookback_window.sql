-- =============================================================================
-- seeds_call_lookback_window.sql                        2026-05-12
-- For sparse sources (CALL), the "previous snapshot" must be looked up
-- per-symbol within a recency window — a single global MAX(date < :d) is
-- meaningless when different calls land on different dates.
--
-- Adds the column if missing, then sets CALL.lookback_days = 30 per
-- the Requirements.xlsx spec ("take 30 days data before the dashboard date").
-- The action-mapping logic in etl/derive_outlook_action.py is unchanged —
-- only the lookup of `prev_weight` / `prev_date` changes for sources whose
-- lookback_days is set.
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

ALTER TABLE IF EXISTS ref_outlook_source
    ADD COLUMN IF NOT EXISTS lookback_days INTEGER;

UPDATE ref_outlook_source
   SET lookback_days = 30
 WHERE source_code = 'CALL'
   AND (lookback_days IS NULL OR lookback_days <> 30);

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT lookback_days INTO n FROM ref_outlook_source WHERE source_code = 'CALL';
    RAISE NOTICE 'CALL.lookback_days = %', COALESCE(n::text, '<NULL>');
END $$;

COMMIT;
