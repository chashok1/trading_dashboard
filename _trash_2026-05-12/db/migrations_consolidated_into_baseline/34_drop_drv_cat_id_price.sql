-- =============================================================================
-- 34_drop_drv_cat_id_price.sql
-- Tier-2A retirement: the last two unused drv_cat_* tables.
--
-- drv_cat_identity — only reader was etl/generate_drv2_views.py, retired in
--   the drv2_* sweep (db/15_drv2_tables.sql now drops, not creates).
-- drv_cat_price    — only reader was etl/execute_build.py (one-time bootstrap).
--
-- After this migration, the live drv_cat_* layer is exactly one table:
-- drv_cat_atomic_input (the rules-engine input).
--
-- Idempotent.
-- =============================================================================

-- (1) Reassign any ref_ma_columns rows pointing at these to the sentinel
UPDATE ref_ma_columns
   SET drv_cat_table = 'drv_cat_separator'
 WHERE drv_cat_table IN ('drv_cat_identity', 'drv_cat_price');

-- (2) Drop the two tables (kind-agnostic, like the previous round)
DO $$
DECLARE
  retired_names TEXT[] := ARRAY['drv_cat_identity','drv_cat_price'];
  obj_name TEXT;
  r RECORD;
BEGIN
  FOREACH obj_name IN ARRAY retired_names LOOP
    FOR r IN
      SELECT n.nspname AS schema_name, c.relname AS obj, c.relkind
      FROM   pg_class c
      JOIN   pg_namespace n ON n.oid = c.relnamespace
      WHERE  c.relname = obj_name
        AND  n.nspname = current_schema()
        AND  c.relkind IN ('r','v','m','f','p')
    LOOP
      IF r.relkind = 'v' THEN
        EXECUTE format('DROP VIEW IF EXISTS %I.%I CASCADE', r.schema_name, r.obj);
      ELSIF r.relkind = 'm' THEN
        EXECUTE format('DROP MATERIALIZED VIEW IF EXISTS %I.%I CASCADE', r.schema_name, r.obj);
      ELSE
        EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', r.schema_name, r.obj);
      END IF;
      RAISE NOTICE '  dropped % %.%', r.relkind, r.schema_name, r.obj;
    END LOOP;
  END LOOP;
END$$;

-- (3) Cleanup metadata
DO $$ BEGIN
  IF to_regclass('meta_data_table') IS NOT NULL THEN
    DELETE FROM meta_data_table WHERE table_name IN ('drv_cat_identity','drv_cat_price');
  END IF;
END $$;

DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic
     WHERE table_name IN ('drv_cat_identity','drv_cat_price',
                          'drv_call','drv_etf','drv_ii','drv_ps','drv_ssl','drv_sss');
  END IF;
END $$;

DO $$
DECLARE remaining INT;
BEGIN
  SELECT COUNT(DISTINCT drv_cat_table)
    INTO remaining
    FROM ref_ma_columns
   WHERE drv_cat_table IS NOT NULL
     AND drv_cat_table <> 'drv_cat_separator';
  RAISE NOTICE 'ref_ma_columns active drv_cat_table values now: % (expected 1 — drv_cat_atomic_input)', remaining;
END$$;

-- (4) Stale ref_ma_columns.drv2_table values — drv2_* layer is retired,
--     so any non-null entries are dangling pointers. NULL them all.
UPDATE ref_ma_columns
   SET drv2_table = NULL
 WHERE drv2_table IS NOT NULL;
