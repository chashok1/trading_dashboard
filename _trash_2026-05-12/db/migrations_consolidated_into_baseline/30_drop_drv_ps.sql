-- =============================================================================
-- 30_drop_drv_ps.sql
-- Retire drv_ps. No downstream readers; hist_psrk has rank+asset_class.
-- Idempotent.
-- =============================================================================

DROP TABLE IF EXISTS drv2_ps CASCADE;
DROP TABLE IF EXISTS drv_ps CASCADE;

DO $$ BEGIN

  IF to_regclass('meta_data_table') IS NOT NULL THEN

    DELETE FROM meta_data_table WHERE table_name IN ('drv_ps', 'drv2_ps');

  END IF;

END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name IN ('drv_ps', 'drv2_ps');
  END IF;
END $$;

DO $$
BEGIN
  RAISE NOTICE 'drv_ps dropped (if present).';
END$$;
