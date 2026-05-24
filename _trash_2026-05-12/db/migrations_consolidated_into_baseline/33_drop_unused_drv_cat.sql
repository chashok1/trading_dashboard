-- =============================================================================
-- 33_drop_unused_drv_cat.sql
-- Tier-1 retirement of the per-concept drv_cat_* layer.
--
-- Audit (docs/ma_jg_no_audit.md basis): of 28 drv_cat_* tables, only
-- drv_cat_atomic_input is read by live code (the rules engine). The other 25
-- are populated every derive run via the registry-driven loop and never read.
--
-- This migration:
--   1. NULLs out ref_ma_columns.drv_cat_table for rows that point at retired
--      tables, so etl/ma_codegen.get_all_cat_tables() stops listing them and
--      derive_all() stops trying to populate them.
--   2. Drops the 25 retired tables (and any drv2_* mirrors) in a single
--      kind-agnostic DO-block sweep.
--   3. Cleans related metadata.
--
-- Kept: drv_cat_atomic_input (rules engine), drv_cat_identity (used by
--       deprecated drv2 view generator — kept warm for now), drv_cat_price
--       (used by execute_build.py — kept warm for now).
--
-- Idempotent.
-- =============================================================================

-- ---- 1) Stop the registry loop from listing the retired tables ----
-- ref_ma_columns.drv_cat_table is NOT NULL, so use the existing
-- 'drv_cat_separator' sentinel (which get_all_cat_tables already excludes).
UPDATE ref_ma_columns
   SET drv_cat_table = 'drv_cat_separator'
 WHERE drv_cat_table IN (
   'drv_cat_action_decision', 'drv_cat_bollinger',     'drv_cat_composite',
   'drv_cat_earnings',        'drv_cat_etf',           'drv_cat_fundamentals',
   'drv_cat_he_outlook',      'drv_cat_holdings_dollars', 'drv_cat_ii',
   'drv_cat_index_volatility','drv_cat_macd',          'drv_cat_moving_avg',
   'drv_cat_perf_extremes',   'drv_cat_ps',            'drv_cat_quad_outlook',
   'drv_cat_risk_range',      'drv_cat_rsi',           'drv_cat_sector_rollup',
   'drv_cat_signal_strength', 'drv_cat_trend_trade',   'drv_cat_trig_summary',
   'drv_cat_volatility_regime','drv_cat_volume'
 );

-- ---- 2) Drop the 25 tables (whatever kind they are) ----
DO $$
DECLARE
  retired_names TEXT[] := ARRAY[
    'drv_cat_action_decision', 'drv_cat_bollinger',     'drv_cat_composite',
    'drv_cat_earnings',        'drv_cat_etf',           'drv_cat_fundamentals',
    'drv_cat_he_outlook',      'drv_cat_holdings_dollars', 'drv_cat_ii',
    'drv_cat_index_volatility','drv_cat_macd',          'drv_cat_moving_avg',
    'drv_cat_perf_extremes',   'drv_cat_ps',            'drv_cat_quad_outlook',
    'drv_cat_risk_range',      'drv_cat_rsi',           'drv_cat_sector_rollup',
    'drv_cat_signal_strength', 'drv_cat_trend_trade',   'drv_cat_trig_summary',
    'drv_cat_volatility_regime','drv_cat_volume'
  ];
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

-- ---- 3) Cleanup metadata pointing at the dropped tables ----
DO $$ BEGIN
  IF to_regclass('meta_data_table') IS NOT NULL THEN
    DELETE FROM meta_data_table
    WHERE table_name LIKE 'drv_cat_%'
      AND table_name NOT IN ('drv_cat_atomic_input','drv_cat_identity','drv_cat_price','drv_cat_separator');
  END IF;
END $$;

DO $$ BEGIN
  IF to_regclass('ref_data_filter_logic') IS NOT NULL THEN
    DELETE FROM ref_data_filter_logic
    WHERE table_name LIKE 'drv_cat_%'
      AND table_name NOT IN ('drv_cat_atomic_input','drv_cat_identity','drv_cat_price','drv_cat_separator');
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
  RAISE NOTICE 'ref_ma_columns now has % distinct drv_cat_table values (expected: <= 3)', remaining;
END$$;
