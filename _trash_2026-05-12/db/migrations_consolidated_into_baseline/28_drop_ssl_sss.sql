-- =============================================================================
-- 28_drop_ssl_sss.sql
-- Retire drv_ssl + drv_sss. The actionable pipeline reads hist_ssh directly
-- via ref_outlook_source.source_code='SSH'; the ssL (week-lag) and sss
-- (signal-series) layers are no longer needed.
-- Idempotent.
-- =============================================================================

-- Also drop drv2 mirrors and meta-data registrations
DROP TABLE IF EXISTS drv2_ssl CASCADE;
DROP TABLE IF EXISTS drv2_sss CASCADE;
DROP TABLE IF EXISTS drv_ssl  CASCADE;
DROP TABLE IF EXISTS drv_sss  CASCADE;

DO $$ BEGIN

  IF to_regclass('meta_data_table') IS NOT NULL THEN

    DELETE FROM meta_data_table WHERE table_name IN ('drv_ssl','drv_sss','drv2_ssl','drv2_sss');

  END IF;

END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name IN ('drv_ssl','drv_sss','drv2_ssl','drv2_sss');
  END IF;
END $$;

DO $$
BEGIN
  RAISE NOTICE 'drv_ssl, drv_sss, drv2_ssl, drv2_sss dropped (if present).';
END$$;
