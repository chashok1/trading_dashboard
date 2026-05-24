-- =============================================================================
-- 35_drop_hist_columns.sql
-- Drop unused hist_* columns per the audit. Idempotent (DROP COLUMN IF EXISTS).
-- See docs/ma_jg_no_audit.md and the Tier-2 audit for rationale.
-- =============================================================================

-- ---- hist_rr (14 cols) ----
ALTER TABLE hist_rr
    DROP COLUMN IF EXISTS y_ticker,
    DROP COLUMN IF EXISTS tos_ticker,
    DROP COLUMN IF EXISTS is_latest,
    DROP COLUMN IF EXISTS latest_symbol,
    DROP COLUMN IF EXISTS weight,
    DROP COLUMN IF EXISTS prev_dt,
    DROP COLUMN IF EXISTS prev_wt,
    DROP COLUMN IF EXISTS modifier,
    DROP COLUMN IF EXISTS entry,
    DROP COLUMN IF EXISTS entry_wt,
    DROP COLUMN IF EXISTS cont,
    DROP COLUMN IF EXISTS cont_wt,
    DROP COLUMN IF EXISTS reverse,
    DROP COLUMN IF EXISTS brr;

-- ---- hist_f (13 cols) ----
ALTER TABLE hist_f
    DROP COLUMN IF EXISTS ignore_flag,
    DROP COLUMN IF EXISTS price_paid,
    DROP COLUMN IF EXISTS prev_qty,
    DROP COLUMN IF EXISTS prev_val,
    DROP COLUMN IF EXISTS new_leg,
    DROP COLUMN IF EXISTS leg_id,
    DROP COLUMN IF EXISTS qty_diff,
    DROP COLUMN IF EXISTS snapshot_pl,
    DROP COLUMN IF EXISTS running_pl,
    DROP COLUMN IF EXISTS leg_status,
    DROP COLUMN IF EXISTS leg_pl,
    DROP COLUMN IF EXISTS final_status,
    DROP COLUMN IF EXISTS final_pl;

-- ---- hist_cs (14 cols) ----
ALTER TABLE hist_cs
    DROP COLUMN IF EXISTS ignore_flag,
    DROP COLUMN IF EXISTS price_paid,
    DROP COLUMN IF EXISTS cost,
    DROP COLUMN IF EXISTS prev_qty,
    DROP COLUMN IF EXISTS prev_val,
    DROP COLUMN IF EXISTS new_leg,
    DROP COLUMN IF EXISTS leg_id,
    DROP COLUMN IF EXISTS qty_diff,
    DROP COLUMN IF EXISTS snapshot_pl,
    DROP COLUMN IF EXISTS running_pl,
    DROP COLUMN IF EXISTS leg_status,
    DROP COLUMN IF EXISTS leg_pl,
    DROP COLUMN IF EXISTS final_status,
    DROP COLUMN IF EXISTS final_pl;

-- ---- hist_etf (2 cols) ----
ALTER TABLE hist_etf
    DROP COLUMN IF EXISTS include_flag,
    DROP COLUMN IF EXISTS outlook_modifier;     -- redundant duplicate of outlook

-- ---- hist_etfchg (7 cols) ----
ALTER TABLE hist_etfchg
    DROP COLUMN IF EXISTS action,
    DROP COLUMN IF EXISTS chg,
    DROP COLUMN IF EXISTS wt,
    DROP COLUMN IF EXISTS date2,
    DROP COLUMN IF EXISTS wt2,
    DROP COLUMN IF EXISTS ma_ref,
    DROP COLUMN IF EXISTS imported_date;

-- ---- hist_ii (1 col) ----
ALTER TABLE hist_ii
    DROP COLUMN IF EXISTS include_flag;

-- ---- hist_iichg (5 cols) ----
ALTER TABLE hist_iichg
    DROP COLUMN IF EXISTS action,
    DROP COLUMN IF EXISTS chg,
    DROP COLUMN IF EXISTS miss,
    DROP COLUMN IF EXISTS mos,
    DROP COLUMN IF EXISTS imported_date;

-- ---- Clean stale ref_ma_columns rows whose source_expr now points at vanished cols ----
DO $$ BEGIN
  IF to_regclass('ref_ma_columns') IS NOT NULL THEN
    UPDATE ref_ma_columns
       SET source_expr = NULL, source_table = NULL
     WHERE source_expr IS NOT NULL
       AND (
            source_expr LIKE 'rr.%'        AND source_expr ~ '\.(modifier|brr|entry|entry_wt|cont|cont_wt|weight|reverse|prev_dt|prev_wt|y_ticker|tos_ticker|is_latest|latest_symbol)$'
         OR source_expr LIKE 'etfchg.%'    AND source_expr ~ '\.(action|chg|wt|date2|wt2|ma_ref|imported_date)$'
         OR source_expr LIKE 'iichg.%'     AND source_expr ~ '\.(action|chg|miss|mos|imported_date)$'
         OR source_expr = 'etf.outlook_modifier'
         OR source_expr = 'etf.include_flag'
         OR source_expr = 'ii.include_flag'
       );
  END IF;
END $$;

DO $$
DECLARE total INT; cleared INT;
BEGIN
  SELECT COUNT(*) INTO total FROM ref_ma_columns;
  SELECT COUNT(*) INTO cleared FROM ref_ma_columns
   WHERE source_expr IS NULL OR source_expr = '';
  RAISE NOTICE '35_drop_hist_columns: total=% rows in ref_ma_columns, % now have null source_expr', total, cleared;
END$$;
