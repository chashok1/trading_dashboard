-- =============================================================================
-- 05_seed_ref.sql
-- One-time/idempotent seed for tables that come from constant lists.
-- The bulk of the reference data (Sctr, RRT, Desc, holidays, econ-indicator
-- dates, calendar events, quad outlooks, parm, ismh) is loaded from the
-- Tickers workbook by the Python initial-load script (see
--   etl/tickers_initial_load.py)
-- because those rows live in the spreadsheet and may grow over time.
-- This file just seeds the few constants that don't change.
-- =============================================================================

-- The 31 calendar-event categories that come from Data!R + Data!W..CC.
-- We don't need to seed rows; the loader will INSERT (category, event_date) pairs.
-- This block exists so the categories are documented in DB.
COMMENT ON TABLE ref_calendar_event IS
    'Categories sourced from Tickers Data tab headers: '
    'Vix Expiration, Fed Meeting, FMOC Minutes, Beige Book, Monthly Exp, Qtly Exp, '
    'CPI YOY, CPI MoM, CPI Core MoM, CPI Core YoY, PPI, PCE, GDP, Durable Goods, '
    'Factory Orders, ISM Mfg, ISM Svcs, ADP NFP, NFP, Unemp Rate, JOLTS, UM Cons, '
    'NAHB, Building Permits, MoM Building Permits, New Home Sales, '
    'Pending Home Sales, Existing Home Sales, Retail Sales, Wholesale Inventories, '
    'Jackson hole fed speech';
