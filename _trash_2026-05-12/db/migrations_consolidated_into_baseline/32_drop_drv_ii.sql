-- =============================================================================
-- 32_drop_drv_ii.sql
-- Retire drv_ii. drv_dash reads hist_ii.outlook + ref_param weight inline.
-- Idempotent.
-- =============================================================================

DROP TABLE IF EXISTS drv2_ii CASCADE;
DROP TABLE IF EXISTS drv_ii CASCADE;

DO $$ BEGIN

  IF to_regclass('meta_data_table') IS NOT NULL THEN

    DELETE FROM meta_data_table WHERE table_name IN ('drv_ii', 'drv2_ii');

  END IF;

END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name IN ('drv_ii', 'drv2_ii');
  END IF;
END $$;

DO $$
BEGIN
  RAISE NOTICE 'drv_ii dropped (if present).';
END$$;
