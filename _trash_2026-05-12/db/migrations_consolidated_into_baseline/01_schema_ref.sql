-- =============================================================================
-- 01_schema_ref.sql
-- Reference / lookup tables (low-volume, change rarely).
-- All statements idempotent (CREATE TABLE IF NOT EXISTS).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ref_sector  <- Sctr tab
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_sector (
    ticker            TEXT PRIMARY KEY,
    description       TEXT,
    industry          TEXT,
    sp500             CHAR(1),
    nasdaq            CHAR(1),
    dow               CHAR(1),
    russell           CHAR(1),
    vehicle_type      TEXT,
    asset_class       TEXT,
    sub_asset_class   TEXT,
    equity_sector     TEXT,
    growth            TEXT,
    valuation         TEXT,
    price_action      TEXT,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_rrt  <- RRT tab (RR-name / Y / TOS ticker mapping)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_rrt (
    rr_name      TEXT PRIMARY KEY,
    y_ticker     TEXT,
    tos_ticker   TEXT,
    reverse      CHAR(1),
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_rule_desc  <- Desc tab
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_rule_desc (
    rule_code    TEXT PRIMARY KEY,
    description  TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_holiday  <- Data!O:P
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_holiday (
    holiday_date DATE PRIMARY KEY,
    description  TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_econ_indicator  <- Data!B:M
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_econ_indicator (
    indicator_date    DATE NOT NULL,
    indicator         TEXT NOT NULL,
    url               TEXT,
    days              INTEGER,
    ol                TEXT,
    from_date         DATE,
    to_date           DATE,
    effective_today   CHAR(1),
    show_on_dashboard CHAR(1),
    incl              CHAR(1),
    show_flag         CHAR(1),
    expected          TEXT,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (indicator_date, indicator)
);

-- ---------------------------------------------------------------------------
-- ref_fed_blackout  <- Data!T:U  (Fed Blackout start, End)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_fed_blackout (
    start_date  DATE PRIMARY KEY,
    end_date    DATE,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_calendar_event  <- Data!R + Data!W..CC (skip blank cols)
-- One row per (category, event_date). Header is the category.
-- Categories: Vix Expiration, Fed Meeting, FMOC Minutes, Beige Book,
--   Monthly Exp, Qtly Exp, CPI YOY, CPI MoM, CPI Core MoM, CPI Core YoY,
--   PPI, PCE, GDP, Durable Goods, Factory Orders, ISM Mfg, ISM Svcs,
--   ADP NFP, NFP, Unemp Rate, JOLTS, UM Cons, NAHB,
--   Building Permits, MoM Building Permits, New Home Sales,
--   Pending Home Sales, Existing Home Sales, Retail Sales,
--   Wholesale Inventories, Jackson hole fed speech
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_calendar_event (
    category    TEXT NOT NULL,
    event_date  DATE NOT NULL,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (category, event_date)
);
CREATE INDEX IF NOT EXISTS ix_ref_calendar_event_date ON ref_calendar_event(event_date);

-- ---------------------------------------------------------------------------
-- ref_quad_outlook  <- HQuad tab
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_quad_outlook (
    category       TEXT NOT NULL,
    sub_category   TEXT NOT NULL,
    ticker         TEXT,
    eco_sensitivity TEXT,
    quad1          TEXT,
    quad2          TEXT,
    quad3          TEXT,
    quad4          TEXT,
    m_outlook      TEXT,
    m_score        NUMERIC,
    q_outlook      TEXT,
    q_score        NUMERIC,
    loaded_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (category, sub_category)
);

-- ---------------------------------------------------------------------------
-- ref_quad_periods  <- HQds tab (monthly + quarterly)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_quad_periods (
    period_type  TEXT NOT NULL,    -- 'monthly' or 'quarterly'
    start_date   DATE NOT NULL,
    end_date     DATE,
    quad         TEXT,
    label        TEXT,             -- e.g. "Q1 2026" or "2026-01-01"
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (period_type, start_date)
);

-- ---------------------------------------------------------------------------
-- ref_param  <- Parm tab (parameter lookups)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_param (
    sheet       TEXT NOT NULL,
    param_name  TEXT NOT NULL,
    value       TEXT,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (sheet, param_name)
);

-- The Miss tab does NOT have a ref_* table. It is purely derived data
-- (missing stock symbols from MA), populated by derive_missing_symbols()
-- into drv_missing_symbols (see 06_schema_drv.sql).

-- ---------------------------------------------------------------------------
-- ref_ismh  <- ISMH tab (ISM PMI history; refreshed periodically like Data)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_ismh (
    for_month                TEXT NOT NULL,
    index_name               TEXT NOT NULL,
    series_index_cur_month   NUMERIC,
    series_index_prior_month NUMERIC,
    pct_point_change         NUMERIC,
    direction                TEXT,
    rate_of_change           TEXT,
    trend_months             NUMERIC,
    loaded_at                TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (for_month, index_name)
);
CREATE INDEX IF NOT EXISTS ix_ref_ismh_index ON ref_ismh(index_name);

-- ---------------------------------------------------------------------------
-- ref_load_files  <- LoadFiles.xlsx (drives ETL scheduler)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_load_files (
    source_dir   TEXT NOT NULL,
    file_type    TEXT NOT NULL,     -- "PSRk", "TOSL", "fidelity", ...
    target_tab   TEXT NOT NULL,     -- maps to history table name
    week_day     TEXT NOT NULL,     -- "FRI", "MON", "WKDAY", "SUN"
    file_time    TIME,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (file_type, week_day, file_time)
);
