-- =====================================================
-- baseline.sql  (consolidated 2026-05-12)
-- Self-contained schema for a fresh PostgreSQL 17 database.
-- Represents the state after applying historical migrations 01..35.
-- See db/01_*.sql .. db/35_*.sql for the original migration history.
-- =====================================================
--
-- Usage
-- -----
-- For a brand-new database run this file exactly once:
--     psql -d trading_dashboard -f db/baseline.sql
-- The file is idempotent (CREATE ... IF NOT EXISTS / CREATE OR REPLACE /
-- INSERT ... ON CONFLICT DO NOTHING) so it is safe to re-run.
--
-- The numbered migration files (db/01_*.sql .. db/35_*.sql) remain in
-- place for historical reference and for upgrading older databases that
-- have not yet absorbed the equivalent changes.
--
-- Layout of this file:
--   1. Reference tables (ref_*)
--   2. History tables (hist_*)
--   3. Meta tables (meta_*)
--   4. Derived tables (drv_*)
--   5. Param / lookup tables
--   6. Rule engine v2 tables
--   7. Composite member / rule group tables
--   8. Actionable / data-filter tables
--   9. Views and functions
--  10. Reference seeds and COMMENTs
-- =====================================================


-- =====================================================
-- 1. Reference tables (ref_*)
-- =====================================================

-- -----------------------------------------------------
-- ref_sector  <- Sctr tab
-- -----------------------------------------------------
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

-- -----------------------------------------------------
-- ref_rrt  <- RRT tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_rrt (
    rr_name      TEXT PRIMARY KEY,
    y_ticker     TEXT,
    tos_ticker   TEXT,
    reverse      CHAR(1),
    contracts    CHAR(1),
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- ref_rule_desc  <- Desc tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_rule_desc (
    rule_code    TEXT PRIMARY KEY,
    description  TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- ref_holiday  <- Data!O:P
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_holiday (
    holiday_date DATE PRIMARY KEY,
    description  TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- ref_econ_indicator  <- Data!B:M
-- -----------------------------------------------------
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

-- -----------------------------------------------------
-- ref_fed_blackout  <- Data!T:U
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_fed_blackout (
    start_date  DATE PRIMARY KEY,
    end_date    DATE,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- ref_calendar_event  <- Data!R + Data!W..CC
-- Categories: Vix Expiration, Fed Meeting, FMOC Minutes, Beige Book,
--   Monthly Exp, Qtly Exp, CPI YOY, CPI MoM, CPI Core MoM, CPI Core YoY,
--   PPI, PCE, GDP, Durable Goods, Factory Orders, ISM Mfg, ISM Svcs,
--   ADP NFP, NFP, Unemp Rate, JOLTS, UM Cons, NAHB,
--   Building Permits, MoM Building Permits, New Home Sales,
--   Pending Home Sales, Existing Home Sales, Retail Sales,
--   Wholesale Inventories, Jackson hole fed speech
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_calendar_event (
    category    TEXT NOT NULL,
    event_date  DATE NOT NULL,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (category, event_date)
);
CREATE INDEX IF NOT EXISTS ix_ref_calendar_event_date ON ref_calendar_event(event_date);

-- -----------------------------------------------------
-- ref_quad_outlook  <- HQuad tab
-- -----------------------------------------------------
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

-- -----------------------------------------------------
-- ref_quad_periods  <- HQds tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_quad_periods (
    period_type  TEXT NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE,
    quad         TEXT,
    label        TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (period_type, start_date)
);

-- -----------------------------------------------------
-- ref_param  <- Parm tab (simple param lookups)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_param (
    sheet       TEXT NOT NULL,
    param_name  TEXT NOT NULL,
    value       TEXT,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (sheet, param_name)
);

-- -----------------------------------------------------
-- ref_ismh  <- ISMH tab
-- -----------------------------------------------------
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

-- -----------------------------------------------------
-- ref_load_files  <- LoadFiles.xlsx (drives ETL scheduler)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_load_files (
    source_dir   TEXT NOT NULL,
    file_type    TEXT NOT NULL,
    target_tab   TEXT NOT NULL,
    week_day     TEXT NOT NULL,
    file_time    TIME NOT NULL DEFAULT '00:00:00',
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (file_type, week_day, file_time)
);

-- 2026-05-17: existing DBs were created with PRIMARY KEY (file_type, week_day,
-- file_time). That composite PK was designed for hypothetical "same file_type
-- scheduled at multiple times" rows, but in practice every file_type has
-- exactly one schedule slot â€” and the composite PK prevents inline editing of
-- file_time / week_day via the Ref Data UI (ref.js renders PK columns as
-- read-only <td>). Migrate to PRIMARY KEY (file_type) so the Ref Data UI can
-- edit file_time and week_day in place.
--
-- Safe to re-run: dedups duplicate file_types first (keeping the most recent),
-- then swaps the constraint. The dedup is a no-op if no duplicates exist.
DO $do$
BEGIN
    -- Step 1: dedup any rows that would conflict with PRIMARY KEY (file_type).
    -- ROW_NUMBER over (file_type, loaded_at DESC) keeps the most recent row
    -- per file_type. Uses ctid (the row physical identifier) as a delete key
    -- so we don't depend on MAX(ctid) â€” which only works on PG 14+ and was
    -- the cause of confusion in the 2026-05-17 hand-off.
    DELETE FROM ref_load_files WHERE ctid IN (
        SELECT ctid FROM (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY file_type
                       ORDER BY loaded_at DESC NULLS LAST, ctid DESC
                   ) AS rn
            FROM ref_load_files
        ) d WHERE d.rn > 1
    );
    -- Step 2: drop the old PK if it's the composite version, leave it alone
    -- if it's already file_type only (so re-runs are idempotent).
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'ref_load_files'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND kcu.column_name = 'file_time'
    ) THEN
        ALTER TABLE ref_load_files DROP CONSTRAINT ref_load_files_pkey;
        ALTER TABLE ref_load_files ADD PRIMARY KEY (file_type);
    END IF;
END
$do$;

-- 2026-05-19: REVERT the 2026-05-17 single-column PK. We need multiple schedule
-- slots per file_type again (e.g., TOSL and YFiles run optionally several
-- times per day after 16:00). The 2026-05-17 migration above stays put for
-- historical / chronological completeness â€” this block is the explicit undo.
--
-- Tradeoff: the Ref Data UI (ref.js) renders PK columns as read-only, so
-- with the composite PK back, editing week_day or file_time of an existing
-- row requires delete + re-add via the UI. That was the pre-2026-05-17
-- behavior and it's acceptable for schedule rows.
--
-- Safe to re-run: each step is idempotent.
DO $do$
BEGIN
    -- Step 1: backfill any NULL file_time so the composite PK doesn't reject
    -- existing rows.
    UPDATE ref_load_files SET file_time = '00:00:00' WHERE file_time IS NULL;

    -- Step 2: ensure file_time is NOT NULL (composite PK requires it).
    ALTER TABLE ref_load_files ALTER COLUMN file_time SET NOT NULL;

    -- Step 3: if current PK does NOT include file_time, swap to composite.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'ref_load_files'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND kcu.column_name = 'file_time'
    ) THEN
        ALTER TABLE ref_load_files DROP CONSTRAINT IF EXISTS ref_load_files_pkey;
        ALTER TABLE ref_load_files
            ADD PRIMARY KEY (file_type, week_day, file_time);
    END IF;
END
$do$;

ALTER TABLE IF EXISTS ref_load_files
    ADD COLUMN IF NOT EXISTS optional BOOLEAN DEFAULT FALSE;

ALTER TABLE IF EXISTS ref_load_files
    ADD COLUMN IF NOT EXISTS rows_should_match BOOLEAN DEFAULT TRUE;

-- target_table: the actual DB table that this file_type loads into.
-- Stored explicitly so the UI can deep-link from the schedule/ETL grids
-- into the Ref Data table picker.
ALTER TABLE IF EXISTS ref_load_files
    ADD COLUMN IF NOT EXISTS target_table TEXT;

-- Backfill target_table for existing rows based on target_tab.
-- Hist tabs follow the convention 'hist_' || lower(target_tab); known ref
-- tabs are mapped explicitly. The 'ref_tickers' file_type drives the
-- whole-workbook ref refresh and has no single target -> leave NULL.
UPDATE ref_load_files
   SET target_table = CASE
       WHEN LOWER(target_tab) = 'sctr'           THEN 'ref_sector'
       WHEN LOWER(target_tab) = 'rrt'            THEN 'ref_rrt'
       WHEN LOWER(target_tab) = 'desc'           THEN 'ref_rule_desc'
       WHEN LOWER(target_tab) = 'ismh'           THEN 'ref_ismh'
       WHEN LOWER(target_tab) = 'miss'           THEN 'drv_missing_symbols'
       WHEN LOWER(target_tab) IN ('ref_load_files','loadfiles') THEN 'ref_load_files'
       WHEN LOWER(file_type)  = 'ref_tickers'    THEN NULL
       ELSE 'hist_' || LOWER(target_tab)
   END
 WHERE target_table IS NULL;

-- -----------------------------------------------------
-- 2026-05-17: Seed CST + FT rows so they show on File Monitor "today's
-- schedule" immediately, without requiring an edit to LoadFiles.xlsx.
--
-- Schedule: SUN 16:00 (transaction CSVs are downloaded once a week).
-- optional=TRUE so the schedule shows them as "optional" instead of
-- "overdue" when a particular Sunday has no new download yet.
--
-- ON CONFLICT DO NOTHING preserves any manual edits made via the Ref
-- Data UI or via LoadFiles.xlsx.
-- -----------------------------------------------------
-- Clean up any earlier placeholder rows (from prior baseline) so re-runs
-- of init_db can move them to the new schedule cleanly.
DELETE FROM ref_load_files
 WHERE file_type IN ('CST', 'FT')
   AND source_dir = 'TODO_EDIT_VIA_REF_DATA_UI';

INSERT INTO ref_load_files
    (source_dir, file_type, target_tab, week_day, file_time,
     enabled, optional, rows_should_match, target_table)
VALUES
    ('C:\Ashok\Investing\Stocks\CST\Archive', 'CST',
     'cs_transactions', 'SUN', TIME '16:00:00',
     TRUE, TRUE, FALSE, 'hist_cst'),
    ('C:\Ashok\Investing\Stocks\FT\Archive',  'FT',
     'f_transactions',  'SUN', TIME '16:00:00',
     TRUE, TRUE, FALSE, 'hist_ft')
-- PK is composite (file_type, week_day, file_time) again as of 2026-05-19;
-- ON CONFLICT target must match.
ON CONFLICT (file_type, week_day, file_time) DO NOTHING;

-- -----------------------------------------------------
-- ref_ma_columns  <- 641 MA columns registry
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_ma_columns (
    column_name              TEXT PRIMARY KEY,
    excel_header            TEXT NOT NULL,
    excel_col_letter        TEXT NOT NULL,
    excel_col_idx           INT NOT NULL,
    pipeline_stage          TEXT NOT NULL,
    concept                 TEXT NOT NULL,
    drv_cat_table           TEXT NOT NULL,
    drv2_table              TEXT,
    color_island_id         INT,
    pg_type                 TEXT NOT NULL DEFAULT 'NUMERIC',
    source_kind             TEXT NOT NULL DEFAULT 'passthrough',
    source_table            TEXT,
    source_expr             TEXT,
    excel_formula           TEXT,
    exposed_to_rules        BOOLEAN DEFAULT FALSE,
    exposed_to_dashboard    BOOLEAN DEFAULT TRUE,
    display_label           TEXT,
    notes                   TEXT,
    loaded_at               TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_cat     ON ref_ma_columns(drv_cat_table);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_stage   ON ref_ma_columns(pipeline_stage);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_drv2    ON ref_ma_columns(drv2_table);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_concept ON ref_ma_columns(concept);

-- -----------------------------------------------------
-- ref_settings (rule-engine v2 outcome ETL configuration)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_settings (
    setting_name   TEXT PRIMARY KEY,
    setting_value  TEXT NOT NULL,
    description    TEXT,
    updated_at     TIMESTAMPTZ DEFAULT now()
);


-- =====================================================
-- 2. History tables (hist_*)
-- =====================================================

-- -----------------------------------------------------
-- hist_y  <- Y tab (Yahoo)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_y (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    tos_symbol       TEXT,
    sequence         INTEGER NOT NULL DEFAULT 0,
    export_date      DATE,
    export_time      TEXT,
    company_name     TEXT,
    last_price       NUMERIC,
    change_amt       NUMERIC,
    change_pct       NUMERIC,
    open_price       NUMERIC,
    high_price       NUMERIC,
    low_price        NUMERIC,
    short_ratio      NUMERIC,
    float_str        TEXT,
    shares_out_str   TEXT,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_y_symbol ON hist_y(symbol, snapshot_date);
CREATE INDEX IF NOT EXISTS ix_hist_y_tos_symbol ON hist_y(tos_symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_tl  <- TL tab (TOS Latest)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_tl (
    snapshot_date        DATE NOT NULL,
    symbol               TEXT NOT NULL,
    sequence             INTEGER NOT NULL,
    export_date          DATE,
    export_time          TEXT,
    last_price           NUMERIC,
    net_chng             NUMERIC,
    change_pct           NUMERIC,
    open_price           NUMERIC,
    high_price           NUMERIC,
    low_price            NUMERIC,
    volume               BIGINT,
    rsi                  NUMERIC,
    imp_volatility_raw   NUMERIC,
    loaded_at            TIMESTAMP NOT NULL DEFAULT now(),
    source_file          TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_tl_symbol ON hist_tl(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_td  <- TD tab (TOS Daily)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_td (
    snapshot_date       DATE NOT NULL,
    symbol              TEXT NOT NULL,
    sequence            INTEGER NOT NULL,
    export_date         DATE,
    export_time         TEXT,
    last_price          NUMERIC,
    net_chng            NUMERIC,
    change_pct          NUMERIC,
    open_price          NUMERIC,
    high_price          NUMERIC,
    low_price           NUMERIC,
    rsi                 NUMERIC,
    historical_vol      NUMERIC,
    imp_volatility      NUMERIC,
    a_trend_value       NUMERIC,
    a_trade_value       NUMERIC,
    a_bb_bottom         NUMERIC,
    a_bb_top            NUMERIC,
    a_bb_streak         NUMERIC,
    a_bb_high_low       NUMERIC,
    a_bb_high_low_days  NUMERIC,
    a_iv_percentile     NUMERIC,
    a_hv_percentile     NUMERIC,
    a_bb_top_slope      NUMERIC,
    a_bb_bot_slope      NUMERIC,
    loaded_at           TIMESTAMP NOT NULL DEFAULT now(),
    source_file         TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_td_symbol ON hist_td(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_tw  <- TW tab (TOS Weekly)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_tw (
    snapshot_date       DATE NOT NULL,
    symbol              TEXT NOT NULL,
    sequence            INTEGER NOT NULL,
    export_date         DATE,
    export_time         TEXT,
    last_price          NUMERIC,
    change_pct          NUMERIC,
    sector              TEXT,
    beta                NUMERIC,
    standard_dev        NUMERIC,
    fcf_per_share       NUMERIC,
    high_52             NUMERIC,
    low_52              NUMERIC,
    sma_20              NUMERIC,
    sma_50              NUMERIC,
    sma_200             NUMERIC,
    a_macdays_streak    NUMERIC,
    a_macd_brr1         NUMERIC,
    a_macdh_d_brr1      NUMERIC,
    volume              BIGINT,
    a_volume_spike      NUMERIC,
    volume_avg_10d      NUMERIC,
    volume_avg_3m       NUMERIC,
    volume_rate_change  NUMERIC,
    a_perf_2m           NUMERIC,
    a_perf_2wk          NUMERIC,
    a_perf_3d           NUMERIC,
    a_3mn_high          NUMERIC,
    a_3mn_low           NUMERIC,
    a_3mn_high_low      NUMERIC,
    a_3wk_high_low      NUMERIC,
    a_earnings_days     NUMERIC,
    market_cap_str      TEXT,
    loaded_at           TIMESTAMP NOT NULL DEFAULT now(),
    source_file         TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_tw_symbol ON hist_tw(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_to  <- TO tab (TOS Other - fundamentals)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_to (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    sequence         INTEGER NOT NULL DEFAULT 0,
    market_cap_num   NUMERIC,
    export_date      DATE,
    export_time      TEXT,
    beta             NUMERIC,
    market_cap_str   TEXT,
    ltd_to_capital   NUMERIC,
    pe_ratio         NUMERIC,
    pb_ratio         NUMERIC,
    roe              NUMERIC,
    eps              NUMERIC,
    div_yield        NUMERIC,
    sector           TEXT,
    fcf_per_share    NUMERIC,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_to_symbol ON hist_to(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_call  <- call tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_call (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    outlook          TEXT,
    outlook_modifier TEXT,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_call_symbol ON hist_call(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_etf  <- etf tab
-- (outlook/outlook_modifier added by 26; outlook_modifier dropped by 35;
--  include_flag never made it to final state.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_etf (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    sector           TEXT,
    date_added       DATE,
    recent_price     NUMERIC,
    brr              NUMERIC,
    trr              NUMERIC,
    asset_class      TEXT,
    outlook          TEXT,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_etf_symbol  ON hist_etf(symbol, snapshot_date);
CREATE INDEX IF NOT EXISTS ix_hist_etf_outlook ON hist_etf(outlook) WHERE outlook IS NOT NULL;

-- -----------------------------------------------------
-- hist_ii  <- II tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ii (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    outlook          TEXT,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_ii_symbol ON hist_ii(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_sss  <- SSS tab (Signal Strength Summary)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_sss (
    snapshot_date         DATE NOT NULL,
    symbol                TEXT NOT NULL,
    days_on               INTEGER,
    signal_date           DATE,
    prior_close           NUMERIC,
    last_close            NUMERIC,
    pct_delta             NUMERIC,
    sector                TEXT,
    analyst               TEXT,
    anlst_best_idea_rank  TEXT,
    loaded_at             TIMESTAMP NOT NULL DEFAULT now(),
    source_file           TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_sss_symbol ON hist_sss(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_rr  <- RR tab (Risk Range)
-- (Many columns dropped by 35.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_rr (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
    tos_symbol       TEXT,
    last_price       NUMERIC,
    buy_trade        NUMERIC,
    sell_trade       NUMERIC,
    name             TEXT,
    outlook          TEXT,
    market_close     TIMESTAMP,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_rr_symbol ON hist_rr(symbol, snapshot_date);
CREATE INDEX IF NOT EXISTS ix_hist_rr_tos_symbol ON hist_rr(tos_symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_f  <- F tab (Fidelity holdings)
-- (Several P/L columns dropped by 35.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_f (
    snapshot_date    DATE NOT NULL,
    account_number   TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    qty              NUMERIC,
    current_value    NUMERIC,
    export_date      DATE,
    account_name     TEXT,
    description      TEXT,
    last_price       NUMERIC,
    last_price_change NUMERIC,
    today_gl_dollar  NUMERIC,
    today_gl_pct     NUMERIC,
    total_gl_dollar  NUMERIC,
    total_gl_pct     NUMERIC,
    pct_of_account   NUMERIC,
    cost_basis_total NUMERIC,
    avg_cost_basis   NUMERIC,
    type             TEXT,
    sold_date        DATE,
    shares_sold      NUMERIC,
    realized_gain_dollar NUMERIC,
    realized_gain_pct NUMERIC,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, account_number, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_f_symbol ON hist_f(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_cs  <- CS tab (Charles Schwab holdings)
-- (Several P/L columns dropped by 35.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_cs (
    snapshot_date     DATE NOT NULL,
    account           TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    qty               NUMERIC,
    imported_date     DATE,
    description       TEXT,
    price             NUMERIC,
    price_chng_dollar NUMERIC,
    price_chng_pct    NUMERIC,
    market_value      NUMERIC,
    day_chng_dollar   NUMERIC,
    day_chng_pct      NUMERIC,
    cost_basis        NUMERIC,
    gain_dollar       NUMERIC,
    gain_pct          NUMERIC,
    reinvest          TEXT,
    reinvest_cap_gains TEXT,
    security_type     TEXT,
    sold_date         DATE,
    shares_sold       NUMERIC,
    realized_gain_dollar NUMERIC,
    realized_gain_pct NUMERIC,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    source_file       TEXT,
    PRIMARY KEY (snapshot_date, account, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_cs_symbol ON hist_cs(symbol, snapshot_date);

-- -----------------------------------------------------
-- hist_cst  <- Schwab transaction CSV exports
-- One row per trade (Buy/Sell). Idempotent via PK dedup.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_cst (
    account       TEXT    NOT NULL,
    trade_date    DATE    NOT NULL,
    action        TEXT    NOT NULL,
    symbol        TEXT    NOT NULL DEFAULT '',
    description   TEXT,
    quantity      NUMERIC,
    price         NUMERIC,
    fees          NUMERIC,
    amount        NUMERIC,
    source_file   TEXT,
    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (account, trade_date, action, symbol, quantity, price)
);
CREATE INDEX IF NOT EXISTS ix_hist_cst_date ON hist_cst(trade_date, account);

-- -----------------------------------------------------
-- hist_ft  <- Fidelity Accounts_History.csv
-- One row per Fidelity activity record. Idempotent via PK dedup.
--
-- The Fidelity export bundles a lot of activity kinds into the same `Action`
-- text column: "YOU BOUGHTâ€¦", "YOU SOLDâ€¦", "PURCHASE INTO CORE ACCOUNTâ€¦",
-- "DIVIDEND RECEIVEDâ€¦", etc.  The loader extracts a normalized `kind` into
-- `action_kind` (BUY / SELL / DIV / INT / CASH / OTHER) so downstream
-- consumers (FIFO realized gain, the Activity tab) don't have to text-parse
-- every row.  The raw `action` text is preserved verbatim for audit.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ft (
    account            TEXT    NOT NULL,
    account_number     TEXT,
    trade_date         DATE    NOT NULL,        -- Fidelity "Run Date"
    settlement_date    DATE,                    -- Fidelity "Settlement Date"
    action             TEXT    NOT NULL,        -- raw Fidelity Action text
    action_kind        TEXT    NOT NULL DEFAULT 'OTHER', -- BUY|SELL|DIV|INT|CASH|OTHER
    symbol             TEXT    NOT NULL DEFAULT '',
    description        TEXT,
    type               TEXT,                    -- Fidelity "Type" col (Cash/Margin)
    price              NUMERIC,
    quantity           NUMERIC,                 -- signed: + for buys, - for sells
    commission         NUMERIC,
    fees               NUMERIC,
    accrued_interest   NUMERIC,
    amount             NUMERIC,                 -- signed
    source_file        TEXT,
    loaded_at          TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (account, trade_date, action, symbol, quantity, price)
);
CREATE INDEX IF NOT EXISTS ix_hist_ft_date ON hist_ft(trade_date, account);
CREATE INDEX IF NOT EXISTS ix_hist_ft_sym  ON hist_ft(symbol, trade_date);
CREATE INDEX IF NOT EXISTS ix_hist_ft_kind ON hist_ft(action_kind, trade_date);

-- -----------------------------------------------------
-- drv_realized_gain - FIFO-matched realized gain per sell event.
-- One row per sell event in {hist_cst, hist_ft}; the
-- `lots_consumed` JSONB column carries the per-lot detail (buy_date, shares,
-- cost_per_share) so audits can drill into how the gain was computed.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_realized_gain (
    source             TEXT NOT NULL,           -- 'CS' or 'F'
    account            TEXT NOT NULL,
    symbol             TEXT NOT NULL,
    sell_date          DATE NOT NULL,
    shares_sold        NUMERIC NOT NULL,
    sell_proceeds      NUMERIC,                 -- net of fees / commission
    cost_basis         NUMERIC,                 -- sum of matched buy lot costs
    realized_gain      NUMERIC,                 -- proceeds - cost_basis
    realized_gain_pct  NUMERIC,
    holding_days_avg   NUMERIC,                 -- avg holding period (weighted by shares)
    is_long_term       BOOLEAN,                 -- TRUE iff every matched lot held > 365 days
    lots_consumed      JSONB,                   -- [{buy_date, shares, cost_per_share, src_file}, ...]
    computed_at        TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (source, account, symbol, sell_date, shares_sold)
);
CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_sym  ON drv_realized_gain(symbol, sell_date);
CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_date ON drv_realized_gain(sell_date);
CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_acct ON drv_realized_gain(account, sell_date);

-- -----------------------------------------------------
-- hist_etfchg  <- etfchg tab
-- (action / chg / wt / date2 / wt2 / ma_ref / imported_date dropped by 35.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_etfchg (
    event_date    DATE NOT NULL,
    symbol        TEXT NOT NULL,
    description   TEXT,
    outlook       TEXT,
    change_str    TEXT,
    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),
    source_file   TEXT,
    PRIMARY KEY (event_date, symbol)
);

-- -----------------------------------------------------
-- hist_iichg  <- IIchg tab
-- (action / chg / miss / mos / imported_date dropped by 35.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_iichg (
    event_date    DATE NOT NULL,
    symbol        TEXT NOT NULL,
    outlook       TEXT,
    description   TEXT,
    change_str    TEXT,
    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),
    source_file   TEXT,
    PRIMARY KEY (event_date, symbol)
);

-- -----------------------------------------------------
-- hist_ps  <- ps tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ps (
    snapshot_date    DATE NOT NULL,
    ticker           TEXT NOT NULL,
    rank             NUMERIC,
    wk_ago           NUMERIC,
    mn_ago           NUMERIC,
    date_added       DATE,
    asset_class      TEXT,
    position_sizing  TEXT,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, ticker)
);


-- =====================================================
-- 3. Meta tables (meta_*)
-- =====================================================

-- -----------------------------------------------------
-- meta_etl_run
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_etl_run (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    file_path     TEXT,
    file_type     TEXT,
    target_tab    TEXT,
    rows_read     INTEGER,
    rows_inserted INTEGER,
    rows_skipped  INTEGER,
    skip_reasons  JSONB,
    status        TEXT,
    error_msg     TEXT
);
CREATE INDEX IF NOT EXISTS ix_meta_etl_run_started ON meta_etl_run(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_meta_etl_run_file    ON meta_etl_run(file_path);

-- -----------------------------------------------------
-- meta_file_processed
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_file_processed (
    file_path     TEXT PRIMARY KEY,
    file_mtime    REAL NOT NULL,
    file_type     TEXT,
    target_tab    TEXT,
    file_date     DATE,
    processed_at  TIMESTAMP NOT NULL DEFAULT now(),
    last_run_id   BIGINT REFERENCES meta_etl_run(run_id) ON DELETE SET NULL
);
ALTER TABLE IF EXISTS meta_file_processed
    DROP COLUMN IF EXISTS file_hash;

-- -----------------------------------------------------
-- meta_cleanup_policy
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_cleanup_policy (
    table_name      TEXT PRIMARY KEY,
    date_column     TEXT NOT NULL,
    retention_days  INTEGER NOT NULL DEFAULT 365,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- meta_cleanup_history
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_cleanup_history (
    cleanup_id          BIGSERIAL PRIMARY KEY,
    table_name          TEXT NOT NULL,
    deleted_before_date DATE NOT NULL,
    rows_deleted        INTEGER NOT NULL,
    run_at              TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meta_cleanup_history_table ON meta_cleanup_history(table_name, run_at DESC);

-- -----------------------------------------------------
-- meta_derived_run
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_derived_run (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    as_of_date    DATE NOT NULL,
    target_table  TEXT NOT NULL,
    rows_built    INTEGER,
    status        TEXT,
    error_msg     TEXT,
    parent_run_id BIGINT REFERENCES meta_etl_run(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_meta_derived_run_date ON meta_derived_run(as_of_date, target_table);

-- -----------------------------------------------------
-- meta_scheduler_log
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_scheduler_log (
    log_id        BIGSERIAL PRIMARY KEY,
    logged_at     TIMESTAMP NOT NULL DEFAULT now(),
    message       TEXT NOT NULL,
    log_level     TEXT DEFAULT 'INFO',
    file_name     TEXT
);
CREATE INDEX IF NOT EXISTS ix_meta_scheduler_log_logged_at ON meta_scheduler_log(logged_at DESC);

-- Add file_name column to existing installs
ALTER TABLE IF EXISTS meta_scheduler_log
    ADD COLUMN IF NOT EXISTS file_name TEXT;

-- -----------------------------------------------------
-- meta_warning - per-screen UI warnings (notification bar)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_warning (
    id          BIGSERIAL PRIMARY KEY,
    screen      TEXT      NOT NULL,
    as_of_date  DATE,
    symbol      TEXT,
    severity    TEXT      NOT NULL DEFAULT 'warning',
    code        TEXT,
    message     TEXT      NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meta_warning_screen
    ON meta_warning(screen, as_of_date);


-- =====================================================
-- 4. Derived tables (drv_*)
-- (Only the tables still alive after migrations 28-34.)
-- =====================================================

-- -----------------------------------------------------
-- drv_tl - RETIRED 2026-05-20. Its two columns (vlm_projected and the
-- imp_volatility NaN/NULL cleaning) were pure per-row functions of hist_tl
-- with a single consumer (drv_ma); both are now computed inline in the
-- `tl` CTE of etl/derive.py::_derive_ma_impl. DROP is idempotent: a no-op
-- on fresh installs, removes the legacy table on existing databases.
-- -----------------------------------------------------
DROP TABLE IF EXISTS drv_tl CASCADE;

-- -----------------------------------------------------
-- drv_td - per-row derivations from TD
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_td (
    snapshot_date     DATE NOT NULL,
    symbol            TEXT NOT NULL,
    sequence          INTEGER NOT NULL,
    bb_bot_15d        NUMERIC,
    bb_bot_7d         NUMERIC,
    bb_bot_3d         NUMERIC,
    bb_bot_prev       NUMERIC,
    bb_top_15d        NUMERIC,
    bb_top_7d         NUMERIC,
    bb_top_3d         NUMERIC,
    bb_top_prev       NUMERIC,
    iv_percentile     NUMERIC,
    hv_percentile     NUMERIC,
    range_compression NUMERIC,
    d_rsi             NUMERIC,
    d_rsi3            NUMERIC,
    d_rsi7            NUMERIC,
    d_rsi_direction   NUMERIC,
    d_hv              NUMERIC,
    d_hv3             NUMERIC,
    d_hv7             NUMERIC,
    d_hv_direction    NUMERIC,
    d_iv              NUMERIC,
    d_iv3             NUMERIC,
    d_iv7             NUMERIC,
    d_iv_direction    NUMERIC,
    d_ivp3            NUMERIC,
    d_ivp7            NUMERIC,
    d_ivp_direction   NUMERIC,
    d_ivp_max10       NUMERIC,
    d_iv_to_hv        NUMERIC,
    d_vlt_rule_code   TEXT,
    d_vlt_caution     TEXT,
    computed_at       TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id     BIGINT,
    PRIMARY KEY (snapshot_date, symbol, sequence),
    FOREIGN KEY (snapshot_date, symbol, sequence)
        REFERENCES hist_td(snapshot_date, symbol, sequence)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_td_symbol ON drv_td(symbol, snapshot_date);

-- -----------------------------------------------------
-- drv_tw - per-row derivations from TW
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_tw (
    snapshot_date              DATE NOT NULL,
    symbol                     TEXT NOT NULL,
    sequence                   INTEGER NOT NULL,
    fcf                        NUMERIC,
    sma_20_d                   NUMERIC,
    sma_50_d                   NUMERIC,
    sma_200_d                  NUMERIC,
    w_volume                   BIGINT,
    avg_vlm_10d_d              NUMERIC,
    avg_vlm_3m_d               NUMERIC,
    vlm_rate_change_d          NUMERIC,
    w_vlm_expn_ratio           NUMERIC,
    w_prior_day_vlm_expn_ratio NUMERIC,
    change_pct_d               NUMERIC,
    last_price_d               NUMERIC,
    w_price_wk_ago             NUMERIC,
    w_pct_change_wk            NUMERIC,
    w_vlm_rule_desc            TEXT,
    a_macd_brr                 NUMERIC,
    a_macdh_d_brr              NUMERIC,
    earnings_days_d            NUMERIC,
    computed_at                TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id              BIGINT,
    PRIMARY KEY (snapshot_date, symbol, sequence),
    FOREIGN KEY (snapshot_date, symbol, sequence)
        REFERENCES hist_tw(snapshot_date, symbol, sequence)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_tw_symbol ON drv_tw(symbol, snapshot_date);

-- -----------------------------------------------------
-- drv_sss - per-row derivations from SSS
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_sss (
    snapshot_date     DATE NOT NULL,
    symbol            TEXT NOT NULL,
    rank_hl           NUMERIC,
    unranked          TEXT,
    signal            NUMERIC,
    anlst_best_idea   TEXT,
    rank              NUMERIC,
    total             NUMERIC,
    signal_sign       NUMERIC,
    is_latest         CHAR(1),
    latest_symbol     TEXT,
    removed_date      DATE,
    miss_ma           TEXT,
    tos_lookup        TEXT,
    ma_lookup         TEXT,
    y_lookup          TEXT,
    vlkup             TEXT,
    computed_at       TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id     BIGINT,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date, symbol)
        REFERENCES hist_sss(snapshot_date, symbol) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_sss_symbol ON drv_sss(symbol, snapshot_date);

-- -----------------------------------------------------
-- drv_quote - latest-source-wins consolidation of common quote fields.
-- For each (as_of_date, symbol) we merge candidate rows from hist_y,
-- hist_tl, hist_td. Per field, the row with the highest loaded_at and a
-- non-NULL value wins; NULL falls through to the next-latest source.
-- Built by etl/derive.py::derive_quote, idempotent per as_of_date.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_quote (
    as_of_date      DATE NOT NULL,
    symbol          TEXT NOT NULL,
    last_price      NUMERIC,
    net_chng        NUMERIC,
    pct_change      NUMERIC,
    open_price      NUMERIC,
    high_price      NUMERIC,
    low_price       NUMERIC,
    rsi             NUMERIC,
    imp_volatility  NUMERIC,
    derived_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_quote_symbol ON drv_quote(symbol);

-- -----------------------------------------------------
-- drv_ma - master aggregation per (as_of_date, symbol)
-- (Migration 16 rolled back the experimental JG..NO atomic-input columns;
--  those live in drv_cat_atomic_input.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_ma (
    as_of_date         DATE NOT NULL,
    symbol             TEXT NOT NULL,
    description        TEXT,
    sector             TEXT,
    asset_class        TEXT,
    sub_asset_class    TEXT,
    equity_sector      TEXT,
    tl_date            DATE,
    last_price         NUMERIC,
    rsi                NUMERIC,
    imp_volatility     NUMERIC,
    volume             BIGINT,
    vlm_projected      NUMERIC,
    td_date            DATE,
    iv_percentile      NUMERIC,
    hv_percentile      NUMERIC,
    range_compression  NUMERIC,
    d_iv_to_hv         NUMERIC,
    d_vlt_caution      TEXT,
    a_trend_value      NUMERIC,
    a_trade_value      NUMERIC,
    a_bb_top           NUMERIC,
    a_bb_bottom        NUMERIC,
    a_bb_streak        NUMERIC,
    tw_date            DATE,
    a_macd_brr         NUMERIC,
    a_macdh_d_brr      NUMERIC,
    earnings_days      NUMERIC,
    sma_20             NUMERIC,
    sma_50             NUMERIC,
    sma_200            NUMERIC,
    market_cap_str     TEXT,
    beta               NUMERIC,
    pe_ratio           NUMERIC,
    eps                NUMERIC,
    div_yield          NUMERIC,
    rr_date            DATE,
    rr_buy_trade       NUMERIC,
    rr_sell_trade      NUMERIC,
    rr_outlook         TEXT,
    rr_brr             NUMERIC,
    call_outlook       TEXT,
    call_modifier      TEXT,
    call_weight        NUMERIC,
    etf_outlook        TEXT,
    etf_brr            NUMERIC,
    etf_trr            NUMERIC,
    ii_outlook         TEXT,
    ii_weight          NUMERIC,
    SSS_signal         NUMERIC,
    SSS_signal_sign    NUMERIC,
    SSS_rank_hl        NUMERIC,
    held_qty_fid       NUMERIC,
    held_qty_cs        NUMERIC,
    pct_brr            NUMERIC,
    macdh_direction    NUMERIC,
    macd_direction     NUMERIC,
    bb_direction       NUMERIC,
    bbthresh_crossover NUMERIC,
    trade_cross_over   NUMERIC,
    trade_rule         NUMERIC,
    trend_cross_over   NUMERIC,
    trend_rule         NUMERIC,
    trend_trade_dep_rule NUMERIC,
    trade_trend_relation NUMERIC,
    trade_trend_relation_neg NUMERIC,
    brr_pct_dir        NUMERIC,
    trend_below_trr    NUMERIC,
    lrr_above_trade    NUMERIC,
    ivrule             NUMERIC,
    three_m_long       NUMERIC,
    perf1d_sd_neg      NUMERIC,
    perf_sd_rule       NUMERIC,
    perf_sd_rule_neg   NUMERIC,
    perf3d_rule_neg    NUMERIC,
    bb_bull_rule       NUMERIC,
    bb_bull_puts       NUMERIC,
    macd_and_h_rule    NUMERIC,
    macd_and_h_rule_puts NUMERIC,
    overbought_neg     NUMERIC,
    outlook_3wk_neg    NUMERIC,
    outlook_3wk_days_neg NUMERIC,
    bull_rule          NUMERIC,
    bull_rule_neg      NUMERIC,
    perfourbull_rule   NUMERIC,
    perfourbull_rule_neg NUMERIC,
    dma_50_crossover   NUMERIC,
    dma_200_crossover  NUMERIC,
    trade_close_to_brr NUMERIC,
    trade_close_to_trr NUMERIC,
    up_resistance      NUMERIC,
    down_resistance    NUMERIC,
    vs_lt_outlook_rule NUMERIC,
    short_term_outlook_bullish NUMERIC,
    short_term_outlook_bearish NUMERIC,
    overbought         NUMERIC,
    computed_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id      BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_ma_symbol ON drv_ma(symbol, as_of_date);

-- -----------------------------------------------------
-- drv_dash - mirrors Dash tab
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_dash (
    as_of_date       DATE NOT NULL,
    section          TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    description      TEXT,
    last_price       NUMERIC,
    a_trend_value    NUMERIC,
    a_trade_value    NUMERIC,
    pct_brr          NUMERIC,
    rr_outlook       TEXT,
    rr_brr           NUMERIC,
    call_outlook     TEXT,
    sector           TEXT,
    asset_class      TEXT,
    threshold_low    NUMERIC,
    threshold_high   NUMERIC,
    zone_signal      TEXT,
    computed_at      TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id    BIGINT,
    PRIMARY KEY (as_of_date, section, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_dash_date ON drv_dash(as_of_date);

-- -----------------------------------------------------
-- drv_stks - per-symbol actionable rollup
-- (Migration 10 added triggered_atomic_ids / triggered_composite_ids /
--  triggered_group_ids columns.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_stks (
    as_of_date              DATE NOT NULL,
    symbol                  TEXT NOT NULL,
    description             TEXT,
    sector                  TEXT,
    asset_class             TEXT,
    last_price              NUMERIC,
    a_trend_value           NUMERIC,
    a_trade_value           NUMERIC,
    pct_brr                 NUMERIC,
    rr_outlook              TEXT,
    rr_brr                  NUMERIC,
    call_outlook            TEXT,
    call_modifier           TEXT,
    etf_outlook             TEXT,
    ii_outlook              TEXT,
    SSS_signal_sign         NUMERIC,
    iv_percentile           NUMERIC,
    rsi                     NUMERIC,
    earnings_days           NUMERIC,
    market_cap_str          TEXT,
    composite_outlook       NUMERIC,
    composite_label         TEXT,
    triggered_atomic_ids    JSONB,
    triggered_composite_ids JSONB,
    triggered_group_ids     JSONB,
    computed_at             TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id           BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_stks_date ON drv_stks(as_of_date);

-- -----------------------------------------------------
-- drv_dash_summary - one row per as_of_date
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_dash_summary (
    as_of_date          DATE PRIMARY KEY,
    total_symbols       INTEGER,
    n_bullish           INTEGER,
    n_bearish           INTEGER,
    n_neutral           INTEGER,
    avg_brr             NUMERIC,
    n_in_zone           INTEGER,
    n_out_of_zone       INTEGER,
    n_above_trend       INTEGER,
    n_below_trend       INTEGER,
    next_econ_event     TEXT,
    next_econ_event_dt  DATE,
    next_holiday        TEXT,
    next_holiday_dt     DATE,
    computed_at         TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id       BIGINT
);

-- -----------------------------------------------------
-- drv_missing_symbols
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_missing_symbols (
    as_of_date    DATE NOT NULL,
    symbol        TEXT NOT NULL,
    found_in      TEXT,
    computed_at   TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_missing_date ON drv_missing_symbols(as_of_date);

-- -----------------------------------------------------
-- drv_cat_atomic_input - the rule-engine atomic-input layer.
-- (Sole survivor of the drv_cat_* sweep in migrations 33 and 34.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_cat_atomic_input (
    as_of_date         DATE NOT NULL,
    symbol             TEXT NOT NULL,
    macdh_direction                          NUMERIC,
    macd_direction                           NUMERIC,
    bb_direction                             NUMERIC,
    bb_threshold                             NUMERIC,
    bbthresh_co_days                         NUMERIC,
    bbthresh_co_days2                        NUMERIC,
    trade_cross_over                         NUMERIC,
    trade_rule                               NUMERIC,
    not_trade_rule                           NUMERIC,
    "!trade_rule"                            NUMERIC,
    trend_cross_over                         NUMERIC,
    trend_rule                               NUMERIC,
    "!trend_rule"                            NUMERIC,
    not_trend_rule                           NUMERIC,
    trend_trade_dep_rule                     NUMERIC,
    trtn_relation                            NUMERIC,
    "!trtn_relation"                         NUMERIC,
    not_trtn_relation                        NUMERIC,
    trade_trend_sd_rule                      NUMERIC,
    brrpct_rule                              NUMERIC,
    brrpct_lrr                               NUMERIC,
    brrpct_r2                                NUMERIC,
    brrpct_lrr2                              NUMERIC,
    brrpct_trr                               NUMERIC,
    brrpct_puts                              NUMERIC,
    brrpct_trr_puts                          NUMERIC,
    brrpct_dir                               NUMERIC,
    high_trr                                 NUMERIC,
    low_lrr                                  NUMERIC,
    trend_below_trr                          NUMERIC,
    lrr_above_trade                          NUMERIC,
    trr_idx                                  NUMERIC,
    mrr_idx                                  NUMERIC,
    lrr_idx                                  NUMERIC,
    hvabsolute                               NUMERIC,
    ivabsolute                               NUMERIC,
    ivpercentile                             NUMERIC,
    ivpercentile_puts                        NUMERIC,
    hvpercentile                             NUMERIC,
    hvpercentile_puts                        NUMERIC,
    ivhv                                     NUMERIC,
    ivhv_puts                                NUMERIC,
    ivrule                                   NUMERIC,
    rsi_rule                                 NUMERIC,
    rsi_top                                  NUMERIC,
    rsi_puts                                 NUMERIC,
    c_3m_low_rule                            NUMERIC,
    "3m_low_rule"                            NUMERIC,
    "3m_low_days_rule"                       NUMERIC,
    c_3m_low_days_rule                       NUMERIC,
    c_3mn_high_rule                          NUMERIC,
    "3mn_high_rule"                          NUMERIC,
    c_3mn_high_days_rule                     NUMERIC,
    "3mn_high_days_rule"                     NUMERIC,
    c_3m_long                                NUMERIC,
    "3m_long"                                NUMERIC,
    perf3mn_sd_rule                          NUMERIC,
    perf2m_sd_rule                           NUMERIC,
    perf3wk_sd_rule                          NUMERIC,
    perf2wk_sd_rule                          NUMERIC,
    perf3d_sd_rule                           NUMERIC,
    perf1d_sd_rule                           NUMERIC,
    not_perf1d_sd                            NUMERIC,
    "!perf1d_sd"                             NUMERIC,
    perf3d_sd_1off                           NUMERIC,
    perf_sd_rule                             NUMERIC,
    "!perf_sd_rule"                          NUMERIC,
    not_perf_sd_rule                         NUMERIC,
    "!perf3d_rule"                           NUMERIC,
    not_perf3d_rule                          NUMERIC,
    bbhighlow_sd_rule                        NUMERIC,
    bbhighlow_days_rule                      NUMERIC,
    bbstreak_rule                            NUMERIC,
    bbstreakrule1                            NUMERIC,
    bbstreak_rule2                           NUMERIC,
    bbstreak_days_rule                       NUMERIC,
    bbstreak_days_rule2                      NUMERIC,
    bbstreak_days_rule3                      NUMERIC,
    bbstreak_days_rule4                      NUMERIC,
    bb_bull_rule                             NUMERIC,
    bb_bull_puts                             NUMERIC,
    bbhighdays                               NUMERIC,
    bblowdays                                NUMERIC,
    macd_rule                                NUMERIC,
    macdh_rule                               NUMERIC,
    macd_and_h_rule                          NUMERIC,
    macd_brr_puts                            NUMERIC,
    macdh_brr_puts                           NUMERIC,
    macd_and_h_rule_puts                     NUMERIC,
    macdh_days                               NUMERIC,
    macdh_days2                              NUMERIC,
    overbought                               NUMERIC,
    "!overbought"                            NUMERIC,
    not_overbought                           NUMERIC,
    c_3mn_outlook                            NUMERIC,
    "3mn_outlook"                            NUMERIC,
    "3mn_outlook_days"                       NUMERIC,
    c_3mn_outlook_days                       NUMERIC,
    "3wk_outlook"                            NUMERIC,
    c_3wk_outlook                            NUMERIC,
    c_3wk_outlook_days                       NUMERIC,
    "3wk_outlook_days"                       NUMERIC,
    "!3wk_ol"                                NUMERIC,
    not_3wk_ol                               NUMERIC,
    "!3wk_ol_days"                           NUMERIC,
    not_3wk_ol_days                          NUMERIC,
    bull                                     NUMERIC,
    not_bull                                 NUMERIC,
    "!bull"                                  NUMERIC,
    perforbull                               NUMERIC,
    not_perforbull                           NUMERIC,
    "!perforbull"                            NUMERIC,
    "50_dma_rule"                            NUMERIC,
    c_50_dma_rule                            NUMERIC,
    "50_dma_crossover"                       NUMERIC,
    c_50_dma_crossover                       NUMERIC,
    c_200_dma_rule                           NUMERIC,
    "200_dma_rule"                           NUMERIC,
    c_200_dma_crossover                      NUMERIC,
    "200_dma_crossover"                      NUMERIC,
    c_52_wk_low_rule                         NUMERIC,
    "52_wk_low_rule"                         NUMERIC,
    "52_wk_high_rule"                        NUMERIC,
    c_52_wk_high_rule                        NUMERIC,
    brrtrade                                 NUMERIC,
    trrtrade                                 NUMERIC,
    up_resistance                            NUMERIC,
    down_resistance                          NUMERIC,
    earnings                                 NUMERIC,
    vs_price                                 NUMERIC,
    vs_volume_spike                          NUMERIC,
    vs_volatility                            NUMERIC,
    vs_days                                  NUMERIC,
    vs_lt_outlook_rule                       NUMERIC,
    current_price_sd_rule                    NUMERIC,
    current_volume_rule                      NUMERIC,
    current_volatility_rule                  NUMERIC,
    short_term_oulook_if_lt_bullish          NUMERIC,
    short_term_oulook_if_lt_bearish          NUMERIC,
    source_run_id      BIGINT,
    computed_at        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (as_of_date, symbol)
);


-- =====================================================
-- 5. Param / lookup tables
-- =====================================================

-- -----------------------------------------------------
-- ref_param_lookup - multi-column lookup tables
-- (see comments in 07_schema_param.sql for table_name discriminators)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_param_lookup (
    table_name   TEXT NOT NULL,
    code         TEXT NOT NULL,
    short_name   TEXT,
    action       TEXT,
    seq          NUMERIC,
    description  TEXT,
    extra1       TEXT,
    extra2       TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, code)
);
CREATE INDEX IF NOT EXISTS ix_ref_param_lookup_action ON ref_param_lookup(action);

-- -----------------------------------------------------
-- ref_asset_allocation - Parm AF-AK
-- (units + maintain_min_position added by 21_actionable.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_asset_allocation (
    category               TEXT PRIMARY KEY,
    min_pct                NUMERIC,
    max_pct                NUMERIC,
    min_dollar             NUMERIC,
    max_dollar             NUMERIC,
    units                  NUMERIC,
    maintain_min_position  BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at              TIMESTAMP NOT NULL DEFAULT now()
);


-- =====================================================
-- 6. Rule engine v2 tables (atomic + composite + outcome)
-- =====================================================

-- -----------------------------------------------------
-- ref_trig_atomic_rule
-- (Post 10..13: name_a/name_b/ma_source_sheet dropped, rule_name added,
--  category/intent_text/scoring_mode/score_params/deprecated_at added.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_atomic_rule (
    atomic_rule_id    INTEGER PRIMARY KEY,
    rule_name         TEXT,
    brkeout_from      NUMERIC,
    brkeout_to        NUMERIC,
    wt_below          NUMERIC,
    wt_between        NUMERIC,
    wt_above          NUMERIC,
    ma_column_name    TEXT,
    notes             TEXT,
    category          TEXT,
    intent_text       TEXT,
    scoring_mode      TEXT NOT NULL DEFAULT 'jump',
    score_params      JSONB,
    deprecated_at     TIMESTAMPTZ,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now()
);

-- -----------------------------------------------------
-- ref_trig_composite_mapping
-- (10 added category/intent_text/precondition_expr/deprecated_at;
--  19 added member_kind/data_*/nested_composite_code/member_multiplier
--  and made atomic_rule_id nullable.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_composite_mapping (
    composite_rule_code   TEXT NOT NULL,
    atomic_rule_id        INTEGER,
    weight_override       NUMERIC,
    category              TEXT,
    intent_text           TEXT,
    precondition_expr     TEXT,
    deprecated_at         TIMESTAMPTZ,
    member_kind           TEXT NOT NULL DEFAULT 'atomic',
    data_column           TEXT,
    data_brkeout_from     NUMERIC,
    data_brkeout_to       NUMERIC,
    data_wt_below         NUMERIC,
    data_wt_between       NUMERIC,
    data_wt_above         NUMERIC,
    data_scoring_mode     TEXT DEFAULT 'jump',
    data_score_params     JSONB,
    nested_composite_code TEXT,
    member_multiplier     NUMERIC,
    loaded_at             TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (composite_rule_code, atomic_rule_id),
    FOREIGN KEY (atomic_rule_id) REFERENCES ref_trig_atomic_rule(atomic_rule_id) ON DELETE CASCADE,
    CONSTRAINT member_kind_value_check CHECK (
        member_kind IN ('atomic', 'data', 'composite')
    ),
    CONSTRAINT member_kind_shape_check CHECK (
        (member_kind = 'atomic'    AND atomic_rule_id IS NOT NULL
                                   AND data_column IS NULL
                                   AND nested_composite_code IS NULL) OR
        (member_kind = 'data'      AND data_column IS NOT NULL
                                   AND atomic_rule_id IS NULL
                                   AND nested_composite_code IS NULL) OR
        (member_kind = 'composite' AND nested_composite_code IS NOT NULL
                                   AND atomic_rule_id IS NULL
                                   AND data_column IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_ref_trig_composite_atom ON ref_trig_composite_mapping(atomic_rule_id);
CREATE INDEX IF NOT EXISTS ix_composite_mapping_nested
    ON ref_trig_composite_mapping(nested_composite_code)
    WHERE nested_composite_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_composite_mapping_kind ON ref_trig_composite_mapping(member_kind);

-- -----------------------------------------------------
-- drv_trig - per-stock per-composite-rule scores
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_trig (
    as_of_date          DATE NOT NULL,
    symbol              TEXT NOT NULL,
    composite_rule_code TEXT NOT NULL,
    score               NUMERIC,
    triggered           BOOLEAN,
    n_atomic_hit        INTEGER,
    computed_at         TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id       BIGINT,
    PRIMARY KEY (as_of_date, symbol, composite_rule_code)
);
CREATE INDEX IF NOT EXISTS ix_drv_trig_symbol    ON drv_trig(symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_trig_rule      ON drv_trig(composite_rule_code, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_trig_triggered ON drv_trig(as_of_date, triggered) WHERE triggered = TRUE;

-- -----------------------------------------------------
-- drv_rule_outcome - forward-return audit per rule fire
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_rule_outcome (
    rule_id        TEXT NOT NULL,
    rule_kind      TEXT NOT NULL,
    as_of_date     DATE NOT NULL,
    symbol         TEXT NOT NULL,
    action_code    TEXT,
    fwd_5d_pct     NUMERIC,
    fwd_20d_pct    NUMERIC,
    hit            BOOLEAN,
    computed_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (rule_id, as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_rule_outcome_date    ON drv_rule_outcome(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_rule_outcome_rule_id ON drv_rule_outcome(rule_id);

-- drv_cs_realized_gain - Realized P&L from Schwab sales
-- For each sell on as_of_date, computes realized gain using prior-day avg cost
CREATE TABLE IF NOT EXISTS drv_cs_realized_gain (
    as_of_date         DATE    NOT NULL,
    account            TEXT    NOT NULL,
    symbol             TEXT    NOT NULL,
    realized_gain      NUMERIC,
    shares_sold        NUMERIC,
    avg_cost_per_share NUMERIC,
    proceeds           NUMERIC,
    computed_at        TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, account, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_cs_realized_gain_date ON drv_cs_realized_gain(as_of_date);


-- =====================================================
-- 7. Rule group tables (composite-of-composites)
-- =====================================================

-- -----------------------------------------------------
-- ref_trig_rule_group
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_rule_group (
    rule_group_code VARCHAR(50) PRIMARY KEY,
    group_type      VARCHAR(20) NOT NULL DEFAULT 'action',
    action_label    VARCHAR(20),
    priority        INT,
    category        VARCHAR(50),
    intent_text     TEXT,
    deprecated_at   TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT action_label_check CHECK (
        (group_type = 'action'  AND action_label IS NOT NULL) OR
        (group_type = 'logical' AND action_label IS NULL)
    )
);

-- -----------------------------------------------------
-- ref_trig_group_member
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_group_member (
    rule_group_code VARCHAR(50) NOT NULL,
    member_code     VARCHAR(50) NOT NULL,
    member_type     VARCHAR(20) NOT NULL,
    logic_operator  VARCHAR(5)  NOT NULL DEFAULT 'AND',
    sequence        INT NOT NULL,
    FOREIGN KEY (rule_group_code) REFERENCES ref_trig_rule_group(rule_group_code) ON DELETE CASCADE,
    PRIMARY KEY (rule_group_code, member_code, sequence),
    CONSTRAINT logic_operator_check CHECK (logic_operator IN ('AND', 'OR'))
);


-- =====================================================
-- 8. Actionable / data-filter / user-log tables
-- =====================================================

-- -----------------------------------------------------
-- ref_data_filter_logic
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_data_filter_logic (
    table_name   TEXT PRIMARY KEY,
    filter_type  TEXT NOT NULL,
    date_column  TEXT,
    window_days  INTEGER,
    description  TEXT,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT filter_type_check CHECK (
        filter_type IN ('EXACT_MATCH','LATEST_BEFORE','LATEST_ON_OR_BEFORE',
                        'WINDOW_14_DAYS','WINDOW_30_DAYS','WINDOW_90_DAYS',
                        'WINDOW_180_DAYS','WINDOW_365_DAYS','NO_FILTER')
    )
);

-- 2026-05-17: Existing DBs created against the old 6-value CHECK still have
-- the narrower constraint. Drop+recreate so the new transaction policies fit.
ALTER TABLE IF EXISTS ref_data_filter_logic
    DROP CONSTRAINT IF EXISTS filter_type_check;
ALTER TABLE IF EXISTS ref_data_filter_logic
    ADD CONSTRAINT filter_type_check CHECK (
        filter_type IN ('EXACT_MATCH','LATEST_BEFORE','LATEST_ON_OR_BEFORE',
                        'WINDOW_14_DAYS','WINDOW_30_DAYS','WINDOW_90_DAYS',
                        'WINDOW_180_DAYS','WINDOW_365_DAYS','NO_FILTER')
    );

-- -----------------------------------------------------
-- ref_my_stocks - user's watchlist
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_my_stocks (
    symbol     TEXT       PRIMARY KEY,
    added_at   TIMESTAMP  NOT NULL DEFAULT now(),
    active     CHAR(1)    NOT NULL DEFAULT 'Y',
    notes      TEXT
);

-- -----------------------------------------------------
-- ref_outlook_source - 8 sources from Requirements matrix
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_outlook_source (
    source_code          TEXT        PRIMARY KEY,
    source_table         TEXT        NOT NULL,
    investment_priority  INTEGER     NOT NULL,
    base_weight_method   TEXT        NOT NULL CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta')),
    base_weight_param    NUMERIC,
    position_category    TEXT,
    show_in_actionable   BOOLEAN     NOT NULL DEFAULT TRUE,
    deprecated_at        TIMESTAMP,
    notes                TEXT,
    -- For sparse sources (e.g. CALL): use the per-symbol most-recent prior
    -- snapshot within this many days as `prev` instead of the single
    -- global MAX(date < as_of_date). NULL = old behavior (global prev).
    lookback_days        INTEGER,
    loads_prior_day_data BOOLEAN     NOT NULL DEFAULT FALSE,
    loaded_at            TIMESTAMP   NOT NULL DEFAULT now()
);

-- Add loaded_at + lookback_days + loads_prior_day_data columns if missing (for existing deployments)
ALTER TABLE IF EXISTS ref_outlook_source
ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMP NOT NULL DEFAULT now();
ALTER TABLE IF EXISTS ref_outlook_source
ADD COLUMN IF NOT EXISTS lookback_days INTEGER;
ALTER TABLE IF EXISTS ref_outlook_source
ADD COLUMN IF NOT EXISTS loads_prior_day_data BOOLEAN NOT NULL DEFAULT FALSE;

-- -----------------------------------------------------
-- drv_outlook_action - per (date, symbol, source) granular result
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_outlook_action (
    as_of_date     DATE       NOT NULL,
    symbol         TEXT       NOT NULL,
    source_code    TEXT       NOT NULL REFERENCES ref_outlook_source(source_code),
    base_weight    NUMERIC,
    prev_weight    NUMERIC,
    prev_date      DATE,
    weight_delta   NUMERIC,
    held_today     BOOLEAN    NOT NULL,
    action         TEXT,
    action_reason  TEXT,
    category       TEXT,
    analyst_rank   TEXT,
    computed_at    TIMESTAMP  NOT NULL DEFAULT now(),
    source_run_id  BIGINT,
    PRIMARY KEY (as_of_date, symbol, source_code),
    CONSTRAINT ck_drv_outlook_action_action
        CHECK (action IS NULL OR action IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD'))
);
-- analyst_rank added 2026-05 (SSS Analyst Best Idea Rank, display-only)
ALTER TABLE IF EXISTS drv_outlook_action
ADD COLUMN IF NOT EXISTS analyst_rank TEXT;
-- source_snapshot_date added 2026-05-26: actual hist_* row date for the
-- per-source action. For periodic sources this equals as_of_date, but for
-- CALL/RR/sparse it captures the real data load date (see derive_outlook_action.py).
ALTER TABLE IF EXISTS drv_outlook_action
ADD COLUMN IF NOT EXISTS source_snapshot_date DATE;
CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_date ON drv_outlook_action(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_sym  ON drv_outlook_action(symbol, as_of_date);

-- -----------------------------------------------------
-- drv_actionable - unified decision per (date, symbol)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_actionable (
    as_of_date              DATE NOT NULL,
    symbol                  TEXT NOT NULL,
    description             TEXT,
    sector                  TEXT,
    consolidated_action     TEXT,
    winning_source          TEXT,
    winning_priority        INTEGER,
    position_category       TEXT,
    target_min_dollar       NUMERIC,
    target_max_dollar       NUMERIC,
    units_dollar            NUMERIC,
    maintain_min            BOOLEAN,
    suggested_target_dollar NUMERIC,
    held_today              BOOLEAN NOT NULL,
    current_position_dollar NUMERIC,
    in_my_list              BOOLEAN NOT NULL,
    rules_engine_fires      JSONB,
    source_actions          JSONB,
    suppressed_reason       TEXT,
    computed_at             TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id           BIGINT,
    PRIMARY KEY (as_of_date, symbol),
    CONSTRAINT ck_drv_actionable_consolidated
        CHECK (consolidated_action IS NULL OR consolidated_action IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD'))
);
CREATE INDEX IF NOT EXISTS ix_drv_actionable_action ON drv_actionable(as_of_date, consolidated_action);
CREATE INDEX IF NOT EXISTS ix_drv_actionable_mylist ON drv_actionable(in_my_list) WHERE in_my_list IS TRUE;

-- 2026-05-17: rule-group attribution column.
ALTER TABLE IF EXISTS drv_actionable
ADD COLUMN IF NOT EXISTS triggered_group_ids JSONB;

-- -----------------------------------------------------
-- user_action_log - forensic snapshot of user decisions.
-- (Collision between 10's first definition and 21's full one was patched
--  by 22; this is the fully merged final schema.)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS user_action_log (
    id                         BIGSERIAL PRIMARY KEY,
    user_id                    TEXT NOT NULL DEFAULT 'default',
    acted_at                   TIMESTAMP NOT NULL DEFAULT now(),
    as_of_date                 DATE NOT NULL,
    symbol                     TEXT NOT NULL,
    action_code                TEXT,
    user_action                TEXT,
    user_action_target         TEXT,
    snooze_until               DATE,
    user_notes                 TEXT,
    notes                      TEXT,
    consolidated_action        TEXT,
    winning_source             TEXT,
    winning_priority           INTEGER,
    position_category          TEXT,
    target_min_dollar          NUMERIC,
    target_max_dollar          NUMERIC,
    units_dollar               NUMERIC,
    maintain_min               BOOLEAN,
    suggested_target_dollar    NUMERIC,
    held_at_action             BOOLEAN,
    position_dollar_at_action  NUMERIC,
    in_my_list                 BOOLEAN,
    triggered_rules            JSONB,
    source_actions             JSONB,
    rules_engine_fires         JSONB,
    source_raw_snapshot        JSONB,
    user_email                 TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_action_log_user_action_check
        CHECK (user_action IS NULL OR user_action IN ('DONE','SKIPPED','SNOOZED','OVERRIDDEN'))
);

-- action_code / triggered_rules were NOT NULL in migration 10's first
-- definition of this table; the merged schema above makes both optional.
-- Existing DBs created from 10 still carry the old constraints, which break
-- the Actionable Suppress INSERT (it supplies neither column). DROP NOT NULL
-- is a no-op on an already-nullable column, so this is safe to re-run.
ALTER TABLE user_action_log ALTER COLUMN action_code     DROP NOT NULL;
ALTER TABLE user_action_log ALTER COLUMN triggered_rules DROP NOT NULL;

CREATE INDEX IF NOT EXISTS ix_user_action_log_symbol_date ON user_action_log(symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_user_action_log_date        ON user_action_log(as_of_date);
CREATE INDEX IF NOT EXISTS ix_user_action_log_date_sym    ON user_action_log(as_of_date, symbol);
CREATE INDEX IF NOT EXISTS ix_user_action_log_acted       ON user_action_log(acted_at DESC);


-- =====================================================
-- 9. Views and functions
-- =====================================================

-- -----------------------------------------------------
-- v_dash(p_as_of_date)
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_dash(p_as_of_date DATE)
RETURNS SETOF drv_dash LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_dash WHERE as_of_date = p_as_of_date
    ORDER BY section, symbol;
$$;

-- -----------------------------------------------------
-- v_stks(p_as_of_date)
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_stks(p_as_of_date DATE)
RETURNS SETOF drv_stks LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_stks WHERE as_of_date = p_as_of_date ORDER BY symbol;
$$;

-- -----------------------------------------------------
-- v_ma(p_as_of_date)
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_ma(p_as_of_date DATE)
RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_ma WHERE as_of_date = p_as_of_date ORDER BY symbol;
$$;

-- -----------------------------------------------------
-- v_dash_summary(p_as_of_date)
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_dash_summary(p_as_of_date DATE)
RETURNS SETOF drv_dash_summary LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_dash_summary WHERE as_of_date = p_as_of_date;
$$;

-- -----------------------------------------------------
-- v_symbol_history(p_symbol) - all snapshots for a single symbol from drv_ma
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_symbol_history(p_symbol TEXT)
RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$
    SELECT * FROM drv_ma WHERE symbol = p_symbol ORDER BY as_of_date DESC;
$$;

-- -----------------------------------------------------
-- v_available_dates - distinct as_of_dates with drv_dash/drv_stks rows
-- -----------------------------------------------------
CREATE OR REPLACE VIEW v_available_dates AS
    SELECT DISTINCT as_of_date FROM drv_dash
    UNION
    SELECT DISTINCT as_of_date FROM drv_stks
    ORDER BY 1 DESC;

-- -----------------------------------------------------
-- v_outlook_changes(p_as_of_date) - per-symbol outlook-change roll-up
--
-- One row per symbol that had at least one actionable change in
-- drv_outlook_action on the given date. The dominant_action column
-- prioritizes REMOVE > REDUCE > ADD > INCREASE so the Dashboard banner
-- can show a single tag per symbol.
--
-- For periodic sources (ETF/II), actions are valid for the entire period
-- (week), so this query maps the requested date to the period's snapshot date:
-- - ETF (SUN): if queried date is Sun-Sat, use that week's Sunday snapshot
-- - II (MON): if queried date is Mon-Sun, use that week's Monday snapshot
-- - Others (RR, CALL, etc.): use the queried date as-is
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_outlook_changes(p_as_of_date DATE)
RETURNS TABLE (
    symbol            TEXT,
    n_sources_changed INTEGER,
    sources           TEXT[],
    actions           TEXT[],
    dominant_action   TEXT,
    held_today        BOOLEAN,
    total_delta       NUMERIC,
    reasons           TEXT[]
) LANGUAGE sql STABLE AS $$
    WITH source_snapshot_dates AS (
        -- For each source, determine the effective snapshot date to query.
        -- Periodic sources (ETF/II/SSS/PS) have actions valid for their period (week),
        -- so we map any queried date to that period's snapshot date.
        SELECT DISTINCT source_code,
               CASE
                   -- ETF: weekly; rows keyed on the week's latest snapshot
                   -- date - take the newest period on/before p_as_of_date.
                   WHEN source_code = 'ETF' THEN
                       (SELECT MAX(as_of_date) FROM drv_outlook_action doa1
                        WHERE doa1.source_code = 'ETF'
                          AND as_of_date <= p_as_of_date)
                   -- II: weekly; rows keyed on the week's latest snapshot
                   -- date - take the newest period on/before p_as_of_date.
                   WHEN source_code = 'II' THEN
                       (SELECT MAX(as_of_date) FROM drv_outlook_action doa2
                        WHERE doa2.source_code = 'II'
                          AND as_of_date <= p_as_of_date)
                   -- SSS: weekly; rows keyed on the week's latest snapshot
                   -- date - take the newest period on/before p_as_of_date.
                   WHEN source_code = 'SSS' THEN
                       (SELECT MAX(as_of_date) FROM drv_outlook_action doa3
                        WHERE doa3.source_code = 'SSS'
                          AND as_of_date <= p_as_of_date)
                   -- PS: weekly; PS rows are keyed on the week's latest
                   -- snapshot date (any weekday), so take the newest PS
                   -- period on/before p_as_of_date - no day-of-week filter.
                   WHEN source_code = 'PS' THEN
                       (SELECT MAX(as_of_date) FROM drv_outlook_action doa4
                        WHERE doa4.source_code = 'PS'
                          AND as_of_date <= p_as_of_date)
                   -- Others (RR, CALL, etc.): use queried date as-is
                   ELSE p_as_of_date
               END AS effective_date
        FROM drv_outlook_action
    ),
    ranked AS (
        SELECT doa.symbol, doa.source_code, doa.action, doa.action_reason, doa.weight_delta, doa.held_today,
               CASE doa.action
                   WHEN 'REMOVE'   THEN 1
                   WHEN 'REDUCE'   THEN 2
                   WHEN 'ADD'      THEN 3
                   WHEN 'INCREASE' THEN 4
                   ELSE 9
               END AS prio
        FROM drv_outlook_action doa
        JOIN source_snapshot_dates ssd ON doa.source_code = ssd.source_code
        WHERE doa.as_of_date = ssd.effective_date
          AND doa.action IS NOT NULL
          AND doa.action <> 'HOLD'
    ),
    dominant AS (
        SELECT DISTINCT ON (symbol) symbol, action AS dominant_action
        FROM ranked ORDER BY symbol, prio, source_code
    )
    SELECT r.symbol,
           COUNT(*)::int                AS n_sources_changed,
           array_agg(r.source_code
                     ORDER BY r.prio, r.source_code) AS sources,
           array_agg(r.action
                     ORDER BY r.prio, r.source_code) AS actions,
           d.dominant_action,
           bool_or(r.held_today)        AS held_today,
           SUM(COALESCE(r.weight_delta, 0)) AS total_delta,
           array_agg(r.action_reason
                     ORDER BY r.prio, r.source_code) AS reasons
    FROM ranked r
    JOIN dominant d USING (symbol)
    GROUP BY r.symbol, d.dominant_action
    ORDER BY n_sources_changed DESC, r.symbol;
$$;

-- -----------------------------------------------------
-- v_rule_performance - rolling 180-day rule efficacy summary
-- (kept for backward compat; new code should use v_rule_performance_window).
-- -----------------------------------------------------
CREATE OR REPLACE VIEW v_rule_performance AS
SELECT
    rule_id,
    rule_kind,
    COUNT(*)                                                    AS sample_size,
    ROUND(AVG(CASE WHEN hit     THEN 1 ELSE 0 END)::numeric, 4) AS hit_rate,
    ROUND(AVG(CASE WHEN NOT hit THEN 1 ELSE 0 END)::numeric, 4) AS false_positive_rate,
    ROUND(AVG(fwd_5d_pct)::numeric, 4)                          AS avg_fwd_5d,
    ROUND(AVG(fwd_20d_pct)::numeric, 4)                         AS avg_fwd_20d,
    MIN(as_of_date)                                             AS first_seen,
    MAX(as_of_date)                                             AS last_seen
FROM drv_rule_outcome
WHERE as_of_date >= CURRENT_DATE - INTERVAL '180 days'
GROUP BY rule_id, rule_kind;

-- -----------------------------------------------------
-- v_rule_performance_window(p_window_days, p_from, p_to)
--   window scoring + median fwd return; either bounds can be NULL
--   (p_from defaults to CURRENT_DATE - p_window_days; p_to defaults to today)
-- -----------------------------------------------------
CREATE OR REPLACE FUNCTION v_rule_performance_window(
    p_window_days INTEGER DEFAULT 180,
    p_from        DATE    DEFAULT NULL,
    p_to          DATE    DEFAULT NULL
) RETURNS TABLE (
    rule_id              TEXT,
    rule_kind            TEXT,
    sample_size          INTEGER,
    hit_rate             NUMERIC,
    false_positive_rate  NUMERIC,
    avg_fwd_5d           NUMERIC,
    avg_fwd_20d          NUMERIC,
    median_fwd_5d        NUMERIC,
    median_fwd_20d       NUMERIC,
    first_seen           DATE,
    last_seen            DATE
) LANGUAGE sql STABLE AS $$
    WITH bounds AS (
        SELECT
            COALESCE(p_to,   CURRENT_DATE)                                AS hi,
            COALESCE(p_from, CURRENT_DATE - (p_window_days || ' days')::interval) AS lo
    )
    SELECT
        o.rule_id,
        o.rule_kind,
        COUNT(*)::int                                               AS sample_size,
        ROUND(AVG(CASE WHEN o.hit THEN 1 ELSE 0 END)::numeric, 4)   AS hit_rate,
        ROUND(AVG(CASE WHEN NOT o.hit THEN 1 ELSE 0 END)::numeric, 4) AS false_positive_rate,
        ROUND(AVG(o.fwd_5d_pct)::numeric, 4)                        AS avg_fwd_5d,
        ROUND(AVG(o.fwd_20d_pct)::numeric, 4)                       AS avg_fwd_20d,
        ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY o.fwd_5d_pct)::numeric, 4) AS median_fwd_5d,
        ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY o.fwd_20d_pct)::numeric, 4) AS median_fwd_20d,
        MIN(o.as_of_date)                                           AS first_seen,
        MAX(o.as_of_date)                                           AS last_seen
    FROM drv_rule_outcome o, bounds b
    WHERE o.as_of_date >= b.lo AND o.as_of_date <= b.hi
    GROUP BY o.rule_id, o.rule_kind;
$$;


-- =====================================================
-- 10. Reference seeds and COMMENTs
-- =====================================================

-- -----------------------------------------------------
-- ref_calendar_event categories (documentation only)
-- -----------------------------------------------------
COMMENT ON TABLE ref_calendar_event IS
    'Categories sourced from Tickers Data tab headers: '
    'Vix Expiration, Fed Meeting, FMOC Minutes, Beige Book, Monthly Exp, Qtly Exp, '
    'CPI YOY, CPI MoM, CPI Core MoM, CPI Core YoY, PPI, PCE, GDP, Durable Goods, '
    'Factory Orders, ISM Mfg, ISM Svcs, ADP NFP, NFP, Unemp Rate, JOLTS, UM Cons, '
    'NAHB, Building Permits, MoM Building Permits, New Home Sales, '
    'Pending Home Sales, Existing Home Sales, Retail Sales, Wholesale Inventories, '
    'Jackson hole fed speech';

-- -----------------------------------------------------
-- meta_cleanup_policy seeds
-- (drv_ssl/drv_sss policies omitted: those tables were retired by 28.)
-- -----------------------------------------------------
INSERT INTO meta_cleanup_policy (table_name, date_column, retention_days, enabled, notes) VALUES
    ('hist_y',        'snapshot_date', 365,  TRUE,  'Yahoo daily quotes'),
    ('hist_tl',       'snapshot_date', 365,  TRUE,  'TOS Latest'),
    ('hist_td',       'snapshot_date', 365,  TRUE,  'TOS Daily'),
    ('hist_tw',       'snapshot_date', 365,  TRUE,  'TOS Weekly'),
    ('hist_to',       'snapshot_date', 730,  TRUE,  'TOS Other (fundamentals - 2 years)'),
    ('hist_rr',       'snapshot_date', 365,  TRUE,  'Risk Range'),
    ('hist_call',     'snapshot_date', 365,  TRUE,  'Call signals'),
    ('hist_etf',      'snapshot_date', 730,  TRUE,  'ETF outlook (2 years)'),
    ('hist_etfchg',   'event_date',    1825, TRUE,  'ETF change events (5 years)'),
    ('hist_ii',       'snapshot_date', 730,  TRUE,  'Investment Ideas (2 years)'),
    ('hist_iichg',    'event_date',    1825, TRUE,  'II change events (5 years)'),
    ('hist_sss',      'snapshot_date', 365,  TRUE,  'Signal Strength Summary'),
    ('hist_ps',       'snapshot_date', 730,  TRUE,  'Price strength rank'),
    ('hist_f',        'snapshot_date', 1825, TRUE,  'Fidelity holdings (5 years)'),
    ('hist_cs',       'snapshot_date', 1825, TRUE,  'Schwab holdings (5 years)'),
    ('meta_scheduler_log', 'logged_at', 30,   TRUE,  'Scheduler output logs (30 days)')
ON CONFLICT (table_name) DO NOTHING;

-- -----------------------------------------------------
-- ref_settings seeds (outcome ETL configuration)
-- -----------------------------------------------------
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('outcome_fwd_window_5d',      '5',    'Days forward for 5-day outcome window'),
    ('outcome_fwd_window_20d',     '20',   'Days forward for 20-day outcome window'),
    ('outcome_hit_threshold_buy',  '0.5',  'Minimum % return to count as hit for BM actions'),
    ('outcome_hit_threshold_sell', '-0.5', 'Maximum % return to count as hit for SA/STM/SS actions'),
    ('outcome_hold_threshold',     '1.0',  'Maximum abs % return to count as hit for HOLD actions'),
    ('dash_threshold_low_pct',     '-10',  'drv_dash zone_signal=Y when pct_brr <= this'),
    ('dash_threshold_high_pct',    '10',   'drv_dash zone_signal=N when pct_brr >= this'),
    ('outcomes_compute_hour',      '22',   'Local hour (0-23) the scheduler runs compute_outcomes'),
    ('staleness_lookback_days',    '30',   'Days back the auto-heal scans drv_actionable for staleness')
ON CONFLICT (setting_name) DO NOTHING;

-- -----------------------------------------------------
-- ref_outlook_source seeds (8 sources from Requirements matrix).
-- ETF source_table reflects the final state from migration 27 (hist_etf,
-- after the hist_etf.outlook column was added in 26).
-- -----------------------------------------------------
INSERT INTO ref_outlook_source
    (source_code, source_table, investment_priority, base_weight_method, base_weight_param, position_category, loads_prior_day_data, notes)
VALUES
    ('RR',     'hist_rr',     2, 'outlook_modifier', NULL, 'RR',   TRUE,  'Risk Range outlook'),
    ('CALL',   'hist_call',   1, 'outlook_modifier', NULL, 'Call', FALSE, 'Manual call sheet'),
    ('ETF',    'hist_etf',    1, 'outlook_modifier', NULL, 'etf',  FALSE, 'ETF entries (outlook now on hist_etf)'),
    ('ETFCHG', 'hist_etfchg', 1, 'outlook_modifier', NULL, 'etf',  FALSE, 'ETF change events'),
    ('II',     'hist_ii',     1, 'outlook_modifier', NULL, 'II',   FALSE, 'Investment Ideas'),
    ('IICHG',  'hist_iichg',  1, 'outlook_modifier', NULL, 'II',   FALSE, 'II change events'),
    ('SSS',    'hist_sss',    2, 'rank_pct_delta',     2, 'Sig',  FALSE, 'Signal Strength Summary'),
    ('PS',     'hist_ps',     1, 'rank',               3, 'PS',   FALSE, 'Price Strength Rank')
ON CONFLICT (source_code) DO NOTHING;

-- -----------------------------------------------------
-- ref_data_filter_logic seeds
-- (Entries for retired tables drv_ssl/drv_sss/drv_etf/drv_call/drv_ii/drv_ps,
--  drv_tl, and the drv_cat_* sweep are intentionally omitted.)
-- -----------------------------------------------------
INSERT INTO ref_data_filter_logic (table_name, filter_type, date_column, window_days, description) VALUES
    ('hist_y',             'EXACT_MATCH',         'snapshot_date', NULL, 'Yahoo quote snapshot - one row per day'),
    ('hist_tl',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Latest intra-day quotes'),
    ('hist_td',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Daily snapshot'),
    ('hist_tw',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Weekly snapshot'),
    ('drv_td',             'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_td'),
    ('drv_tw',             'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_tw'),
    ('hist_to',            'LATEST_BEFORE',       'snapshot_date', NULL, 'TOS Other / fundamentals - most recent edition before as-of'),
    ('hist_rr',            'LATEST_BEFORE',       'snapshot_date', NULL, 'Risk Range - weekly update'),
    ('hist_f',             'LATEST_BEFORE',       'snapshot_date', NULL, 'Fidelity holdings'),
    ('hist_cs',            'LATEST_BEFORE',       'snapshot_date', NULL, 'Schwab holdings'),
    ('hist_etf',           'LATEST_BEFORE',       'snapshot_date', NULL, 'ETF entries'),
    ('hist_ii',            'LATEST_BEFORE',       'snapshot_date', NULL, 'Investment Ideas'),
    ('hist_ps',            'LATEST_BEFORE',       'snapshot_date', NULL, 'Price Strength Rank'),
    ('hist_sss',           'LATEST_BEFORE',       'snapshot_date', NULL, 'Signal Strength Summary'),
    ('hist_etfchg',        'LATEST_BEFORE',       'event_date',    NULL, 'ETF change events'),
    ('hist_iichg',         'LATEST_BEFORE',       'event_date',    NULL, 'II change events'),
    ('hist_call',          'WINDOW_30_DAYS',      'snapshot_date', 30,   'Manual call sheet - 30-day rolling window'),
    ('drv_sss',            'LATEST_ON_OR_BEFORE', 'snapshot_date', NULL, 'Derived SSS - same-day allowed'),
    ('drv_outlook_action',   'EXACT_MATCH',         'as_of_date',    NULL, 'Per-source action per (date, symbol)'),
    ('drv_actionable',       'EXACT_MATCH',         'as_of_date',    NULL, 'Unified actionable decision per (date, symbol)'),
    ('user_action_log',      'LATEST_ON_OR_BEFORE', 'as_of_date',    NULL, 'User decisions; latest per snapshot'),
    ('hist_cst', 'WINDOW_30_DAYS',      'trade_date',    30,   'Schwab transaction history - rolling 30 days'),
    ('hist_ft',  'WINDOW_365_DAYS',     'trade_date',    365,  'Fidelity transaction history - rolling 1 year (extend as needed)'),
    ('drv_cs_realized_gain', 'EXACT_MATCH',         'as_of_date',    NULL, 'Realized P&L from Schwab sales')
ON CONFLICT (table_name) DO NOTHING;

-- =====================================================
-- End of baseline.sql
-- =====================================================


