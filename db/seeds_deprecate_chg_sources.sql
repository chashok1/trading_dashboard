-- =============================================================================
-- seeds_deprecate_chg_sources.sql                       2026-05-12
-- After the v2 derive rework, hist_etfchg and hist_iichg are consumed
-- through the ETF / II source's UNION lookup rather than as separate sources.
-- Mark them deprecated_at so the deriver skips them. The raw tables
-- (hist_etfchg, hist_iichg) remain populated as audit; only their
-- ref_outlook_source rows are retired.
-- Idempotent: re-runs leave the existing deprecated_at value alone.
-- =============================================================================
BEGIN;

UPDATE ref_outlook_source
   SET deprecated_at = now()
 WHERE source_code IN ('ETFCHG', 'IICHG')
   AND deprecated_at IS NULL;

DO $$
DECLARE
    n_etfchg INTEGER;
    n_iichg  INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_etfchg FROM ref_outlook_source
      WHERE source_code = 'ETFCHG' AND deprecated_at IS NOT NULL;
    SELECT COUNT(*) INTO n_iichg FROM ref_outlook_source
      WHERE source_code = 'IICHG'  AND deprecated_at IS NOT NULL;
    RAISE NOTICE 'ETFCHG deprecated rows: %, IICHG deprecated rows: %', n_etfchg, n_iichg;
END $$;

COMMIT;
