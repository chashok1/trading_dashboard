-- =============================================================================
-- 29_drop_drv_etf.sql
-- Retire drv_etf. ETF outlook now lives on hist_etf (db/26+27).
-- Idempotent.
-- =============================================================================

DROP TABLE IF EXISTS drv2_etf CASCADE;
DROP TABLE IF EXISTS drv_etf CASCADE;

DO $$ BEGIN

  IF to_regclass('meta_data_table') IS NOT NULL THEN

    DELETE FROM meta_data_table WHERE table_name IN ('drv_etf', 'drv2_etf');

  END IF;

END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name IN ('drv_etf', 'drv2_etf');
  END IF;
END $$;

DO $$
BEGIN
  RAISE NOTICE 'drv_etf dropped (if present).';
END$$;
