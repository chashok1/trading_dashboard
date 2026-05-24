-- =============================================================================
-- 09_views.sql
-- Thin SELECT views over the populated drv_* tables.
-- All real work happens in Python (etl/derive.py); these views just expose
-- the derived data to FastAPI in a stable shape.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- v_dash(p_as_of_date)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION v_dash(p_as_of_date DATE)
RETURNS SETOF drv_dash LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_dash WHERE as_of_date = p_as_of_date
    ORDER BY section, symbol;
$$;

-- ---------------------------------------------------------------------------
-- v_stks(p_as_of_date)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION v_stks(p_as_of_date DATE)
RETURNS SETOF drv_stks LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_stks WHERE as_of_date = p_as_of_date ORDER BY symbol;
$$;

-- ---------------------------------------------------------------------------
-- v_ma(p_as_of_date)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION v_ma(p_as_of_date DATE)
RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_ma WHERE as_of_date = p_as_of_date ORDER BY symbol;
$$;

-- ---------------------------------------------------------------------------
-- v_dash_summary(p_as_of_date)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION v_dash_summary(p_as_of_date DATE)
RETURNS SETOF drv_dash_summary LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_dash_summary WHERE as_of_date = p_as_of_date;
$$;

-- ---------------------------------------------------------------------------
-- v_available_dates - distinct as_of_dates that have at least drv_dash rows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_available_dates AS
    SELECT DISTINCT as_of_date FROM drv_dash
    UNION
    SELECT DISTINCT as_of_date FROM drv_stks
    ORDER BY 1 DESC;

-- ---------------------------------------------------------------------------
-- v_symbol_history(p_symbol) - all snapshots for a single symbol from drv_ma
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION v_symbol_history(p_symbol TEXT)
RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_ma WHERE symbol = p_symbol ORDER BY as_of_date DESC;
$$;
