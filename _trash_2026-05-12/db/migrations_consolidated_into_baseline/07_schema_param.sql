-- =============================================================================
-- 07_schema_param.sql
-- Additional reference tables for the many sub-tables embedded in Parm.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ref_param_lookup - consolidated home for the multi-column lookup tables
-- that don't fit the simple (sheet, name -> value) ref_param shape.
--
-- table_name discriminator carries the source sub-table identity:
--   'w_vol_rule'        BS-BW rows 1-11
--   'vol_action'        BS-BW rows 13-23
--   'tn_td_rule'        BS-BW rows 25-31
--   'bull_rr_rule'      BS-BW rows 33-40
--   'nbull_rr_rule'     BS-BW rows 42-48
--   'bb_range'          BS-BX rows 50-59
--   'vol_score:vlm' / 'vol_score:price_zone' / 'vol_score:trend_context' /
--   'vol_score:momentum' / 'vol_score:volatility_regime' /
--   'vol_score:long_trend'                          BO-BQ stacked
--   'iv_action'         CC-CF
--   'scenario_action'   CI-CK
--   'final_label'       CM-CN
--   'buysell'           AM-AS
--   'trig_range'        BK-BM  (code=range_from, extra1=range_to)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_param_lookup (
    table_name   TEXT NOT NULL,
    code         TEXT NOT NULL,           -- the rule id / score / category code
    short_name   TEXT,
    action       TEXT,
    seq          NUMERIC,
    description  TEXT,
    extra1       TEXT,
    extra2       TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, code)
);
CREATE INDEX IF NOT EXISTS ix_ref_param_lookup_action
    ON ref_param_lookup(action);

-- ---------------------------------------------------------------------------
-- ref_asset_allocation - Parm AF-AK
-- Per asset-class category: min/max % of portfolio, min/max $, units.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_asset_allocation (
    category     TEXT PRIMARY KEY,
    min_pct      NUMERIC,
    max_pct      NUMERIC,
    min_dollar   NUMERIC,
    max_dollar   NUMERIC,
    units        NUMERIC,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- drv_missing_symbols - the "Miss" sub-section of the Miss tab.
-- Lists symbols that appear in some hist_* source but are NOT in drv_ma
-- for a given snapshot date. Useful for data-quality monitoring.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_missing_symbols (
    as_of_date    DATE NOT NULL,
    symbol        TEXT NOT NULL,
    found_in      TEXT,             -- comma-list of source tables that DO have this symbol
    computed_at   TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_missing_date ON drv_missing_symbols(as_of_date);
