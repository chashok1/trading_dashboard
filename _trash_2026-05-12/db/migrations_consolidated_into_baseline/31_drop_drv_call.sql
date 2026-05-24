-- =============================================================================
-- 31_drop_drv_call.sql
-- Retire drv_call. drv_dash reads hist_call.outlook + ref_param weight inline.
-- Idempotent.
-- =============================================================================

DROP TABLE IF EXISTS drv2_call CASCADE;
DROP TABLE IF EXISTS drv_call CASCADE;

DO $$ BEGIN

  IF to_regclass('meta_data_table') IS NOT NULL THEN

    DELETE FROM meta_data_table WHERE table_name IN ('drv_call', 'drv2_call');

  END IF;

END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name IN ('drv_call', 'drv2_call');
  END IF;
END $$;

DO $$
BEGIN
  RAISE NOTICE 'drv_call dropped (if present).';
END$$;
