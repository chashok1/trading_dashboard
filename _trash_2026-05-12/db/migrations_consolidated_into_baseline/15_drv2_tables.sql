-- =============================================================================
-- 15_drv2_tables.sql  (was the drv2_* materialization layer; RETIRED 2026-05-12)
-- The drv2_* layer was a per-source mirror of MA-tab-style projections. Every
-- production reader has been retired; the table+view shells are now dropped
-- regardless of whether they currently exist as VIEW or TABLE in this DB.
-- See etl/_archived/derive_drv2.py for the original derivation logic.
-- Idempotent.
-- =============================================================================

DO $$
DECLARE r RECORD;
BEGIN
  -- Drop every drv2_* object (table or view) in the current schema, in one pass.
  -- Using pg_class.relkind: 'r' = table, 'v' = view, 'm' = matview.
  FOR r IN
    SELECT n.nspname AS schema_name, c.relname AS obj, c.relkind
    FROM   pg_class c
    JOIN   pg_namespace n ON n.oid = c.relnamespace
    WHERE  c.relname LIKE 'drv2\_%' ESCAPE '\'
      AND  n.nspname = current_schema()
      AND  c.relkind IN ('r','v','m','f','p')
  LOOP
    IF r.relkind = 'v' THEN
      EXECUTE format('DROP VIEW IF EXISTS %I.%I CASCADE',         r.schema_name, r.obj);
    ELSIF r.relkind = 'm' THEN
      EXECUTE format('DROP MATERIALIZED VIEW IF EXISTS %I.%I CASCADE', r.schema_name, r.obj);
    ELSE
      EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE',        r.schema_name, r.obj);
    END IF;
    RAISE NOTICE '  dropped % %.%', r.relkind, r.schema_name, r.obj;
  END LOOP;
END$$;

-- Also clean up any remaining metadata pointing at the dropped objects.
DO $$ BEGIN
  IF to_regclass('meta_data_table') IS NOT NULL THEN
    DELETE FROM meta_data_table WHERE table_name LIKE 'drv2_%';
  END IF;
END $$;
DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic WHERE table_name LIKE 'drv2_%';
  END IF;
END $$;
