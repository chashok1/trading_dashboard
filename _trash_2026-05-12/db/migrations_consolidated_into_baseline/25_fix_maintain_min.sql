-- =============================================================================
-- 25_fix_maintain_min.sql
-- The original 21_actionable.sql set maintain_min_position=TRUE WHERE
-- category IN ('PS','etf'), but ref_asset_allocation actually keys by
-- per-symbol asset_class for PS and ETF positions (no literal 'PS' or 'etf'
-- rows ever exist). This migration sets the flag on the actual asset-class
-- rows that came from hist_psrk and hist_etf.
-- Idempotent. Only sets, never clears.
-- =============================================================================

UPDATE ref_asset_allocation a
   SET maintain_min_position = TRUE
 WHERE category IN (
     SELECT DISTINCT asset_class FROM hist_psrk
       WHERE asset_class IS NOT NULL AND asset_class <> ''
     UNION
     SELECT DISTINCT asset_class FROM hist_etf
       WHERE asset_class IS NOT NULL AND asset_class <> ''
   );

DO $$
DECLARE total INT; flagged INT;
BEGIN
  SELECT COUNT(*), COUNT(*) FILTER (WHERE maintain_min_position)
    INTO total, flagged FROM ref_asset_allocation;
  RAISE NOTICE 'ref_asset_allocation: % / % rows have maintain_min_position=TRUE', flagged, total;
END$$;
