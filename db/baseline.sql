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

    loaded_at      TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (category, sub_category)

);



-- -----------------------------------------------------

-- ref_quad_periods  <- HQds tab

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_quad_periods (
    period_type  TEXT    NOT NULL,
    year         INT     NOT NULL,
    period_num   INT     NOT NULL,
    quad         TEXT,
    label        TEXT,
    quad1_pct    NUMERIC,
    quad2_pct    NUMERIC,
    quad3_pct    NUMERIC,
    quad4_pct    NUMERIC,
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY  (period_type, year, period_num)
);



-- -----------------------------------------------------

-- ref_param  <- Parm tab (simple param lookups)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_accounts (
    account_number   TEXT PRIMARY KEY,
    short_name       TEXT,
    custom_name      TEXT,
    source           TEXT,
    notes            TEXT
);

-- 2026-07-18: Portfolio screen account grouping (one group per account) —
-- lets the screen default to one group's accounts and switch to others,
-- instead of always aggregating everyone together.
ALTER TABLE IF EXISTS ref_accounts ADD COLUMN IF NOT EXISTS group_name TEXT;
-- Human-readable label for group_name, shown in the UI wherever the group
-- code (A1/A2/...) is displayed. group_name stays the stable join/filter
-- key; group_desc is free-text and can change without breaking anything.
ALTER TABLE IF EXISTS ref_accounts ADD COLUMN IF NOT EXISTS group_desc TEXT;
UPDATE ref_accounts SET group_desc = group_name || '-Desc' WHERE group_name IS NOT NULL;

INSERT INTO ref_accounts (account_number, source, group_name) VALUES
    ('85911', 'F', 'A2')
ON CONFLICT (account_number) DO UPDATE SET group_name = EXCLUDED.group_name;

UPDATE ref_accounts SET group_name = v.grp
  FROM (VALUES
    ('Designated_Bene_Individual ...100', 'A1'),
    ('Designated_Bene_Individual ...254', 'A4'),
    ('Rollover_IRA ...892',               'A1'),
    ('HSA_Brokerage ...311',              'A1'),
    ('249118149',                         'A1'),
    ('261408079',                         'A3')
  ) AS v(account_number, grp)
 WHERE ref_accounts.account_number = v.account_number;

INSERT INTO ref_settings (setting_name, setting_value, description)
VALUES ('default_portfolio_group', 'A1', 'Portfolio screen: account group shown by default on load')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-08-08: default account exclusion. is_active=FALSE means the account
-- is excluded from every rollup/derive/screen by default (dashboard,
-- Cockpit exposure/risk, category-perf, realized gains, inferred actions) —
-- raw hist_f/hist_cs loading and mark_sales processing are NOT affected,
-- only aggregation/display. Toggle via the /ref admin screen (ref_accounts
-- row), no code change needed.
ALTER TABLE IF EXISTS ref_accounts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
UPDATE ref_accounts SET is_active = FALSE WHERE account_number = '85911';

-- -----------------------------------------------------
-- ref_account_baseline — manual Total-value overrides used as a YTD/MTD
-- baseline fallback ONLY for accounts with no real hist_f/hist_cs snapshot
-- before the period start (e.g. a newly-tracked 401(k) with no Jan 1
-- position export). Never overrides a real snapshot delta — the API only
-- consults this when the account is otherwise missing from the baseline.
-- Values here are estimates (e.g. back-solved from a brokerage-reported
-- YTD% + known contributions), not real broker exports — do not treat as
-- authoritative history the way hist_* tables are.
-- 2026-07-18: added for Boeing 401(k) (85911), Jan 1 2026 value back-solved
-- from Fidelity's reported YTD 0.8% + $28,634.58 in 2026 contributions.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_account_baseline (
    account_number   TEXT    NOT NULL,
    as_of_date       DATE    NOT NULL,
    total_value      NUMERIC NOT NULL,
    note             TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (account_number, as_of_date)
);

-- -----------------------------------------------------
-- ref_account_cashflow — manually-recorded external cash flows (deposits/
-- withdrawals), for accounts where we have no automated transaction/transfer
-- feed to detect these (Schwab's hist_cst doesn't capture deposits/
-- transfers, only trades — same gap documented for hist_401k_contrib).
-- Positive amount = deposit, negative = withdrawal. `account` matches
-- hist_cs.account directly (CS) or hist_f.account_number (F) — the same key
-- convention used elsewhere for this account/source pair.
-- 2026-07-18: added Designated_Bene_Individual ...254 (C2) $2,500 deposit
-- 2025-01-23, the account's stated starting amount (predates all tracked
-- hist_cs snapshots, which begin 2025-09-26).
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_account_cashflow (
    source        TEXT    NOT NULL,        -- 'CS' or 'F'
    account       TEXT    NOT NULL,
    flow_date     DATE    NOT NULL,
    amount        NUMERIC NOT NULL,
    note          TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (source, account, flow_date, amount)
);

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

    tos_symbol           TEXT,

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

    tos_symbol          TEXT,

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

    tos_symbol          TEXT,

    sequence            INTEGER NOT NULL,

    export_date         DATE,

    export_time         TEXT,

    last_price          NUMERIC,

    change_pct          NUMERIC,

    standard_dev        NUMERIC,

    high_52             NUMERIC,

    low_52              NUMERIC,

    sma_20              NUMERIC,

    sma_50              NUMERIC,

    sma_200             NUMERIC,

    a_macdays_streak    NUMERIC,

    a_macd_brr          NUMERIC,

    a_macdh_d_brr       NUMERIC,

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

    loaded_at           TIMESTAMP NOT NULL DEFAULT now(),

    source_file         TEXT,

    PRIMARY KEY (snapshot_date, symbol, sequence)

);

CREATE INDEX IF NOT EXISTS ix_hist_tw_symbol ON hist_tw(symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_tw_tos_symbol ON hist_tw(tos_symbol, snapshot_date);



-- 2026-05-28: Drop unused/duplicate columns from hist_tw.

-- Consolidate on hist_to as the single source for beta, market_cap, sector, fcf_per_share.

-- Note: This requires TO file_type to be scheduled in ref_load_files.

ALTER TABLE IF EXISTS hist_tw DROP COLUMN IF EXISTS sector;

ALTER TABLE IF EXISTS hist_tw DROP COLUMN IF EXISTS beta;

ALTER TABLE IF EXISTS hist_tw DROP COLUMN IF EXISTS fcf_per_share;

ALTER TABLE IF EXISTS hist_tw DROP COLUMN IF EXISTS market_cap_str;

ALTER TABLE IF EXISTS hist_to DROP COLUMN IF EXISTS market_cap_num;



-- 2026-05-28: Drop bb_bot_prev and bb_top_prev from hist_td.

-- These columns were removed from schema (commit 2e176da) but still exist in DB as 100% NULL.

-- They are now computed as intermediates (DU/DV) in derive_cat_atomic_input, not stored.

ALTER TABLE IF EXISTS hist_td DROP COLUMN IF EXISTS bb_bot_prev;

ALTER TABLE IF EXISTS hist_td DROP COLUMN IF EXISTS bb_top_prev;



-- -----------------------------------------------------

-- hist_to  <- TO tab (TOS Other - fundamentals)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_to (

    snapshot_date    DATE NOT NULL,

    symbol           TEXT NOT NULL,

    tos_symbol       TEXT,

    sequence         INTEGER NOT NULL DEFAULT 0,

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

CREATE INDEX IF NOT EXISTS ix_hist_to_tos_symbol ON hist_to(tos_symbol, snapshot_date);



-- -----------------------------------------------------

-- hist_call  <- call tab

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_call (

    snapshot_date    DATE NOT NULL,

    symbol           TEXT NOT NULL,

    tos_symbol       TEXT,

    outlook          TEXT,

    outlook_modifier TEXT,

    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),

    source_file      TEXT,

    PRIMARY KEY (snapshot_date, symbol)

);

CREATE INDEX IF NOT EXISTS ix_hist_call_symbol ON hist_call(symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_call_tos_symbol ON hist_call(tos_symbol, snapshot_date);



-- -----------------------------------------------------

-- hist_etf  <- etf tab

-- (outlook/outlook_modifier added by 26; outlook_modifier dropped by 35;

--  include_flag never made it to final state.)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_etf (

    snapshot_date    DATE NOT NULL,

    symbol           TEXT NOT NULL,

    tos_symbol       TEXT,

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

CREATE INDEX IF NOT EXISTS ix_hist_etf_tos_symbol ON hist_etf(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_etf_outlook ON hist_etf(outlook) WHERE outlook IS NOT NULL;



-- -----------------------------------------------------

-- hist_ii  <- II tab

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_ii (

    snapshot_date    DATE NOT NULL,

    symbol           TEXT NOT NULL,

    tos_symbol       TEXT,

    outlook          TEXT,

    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),

    source_file      TEXT,

    PRIMARY KEY (snapshot_date, symbol)

);

CREATE INDEX IF NOT EXISTS ix_hist_ii_symbol ON hist_ii(symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_ii_tos_symbol ON hist_ii(tos_symbol, snapshot_date);



-- -----------------------------------------------------

-- hist_sss  <- SSS tab (Signal Strength Summary)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_sss (

    snapshot_date         DATE NOT NULL,

    symbol                TEXT NOT NULL,

    tos_symbol            TEXT,

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

CREATE INDEX IF NOT EXISTS ix_hist_sss_tos_symbol ON hist_sss(tos_symbol, snapshot_date);



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

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='hist_rr' AND column_name='description') THEN
        ALTER TABLE hist_rr RENAME COLUMN description TO name;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='hist_rr' AND column_name='outlook_modifier') THEN
        ALTER TABLE hist_rr RENAME COLUMN outlook_modifier TO outlook;
    END IF;
END $$;


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

-- 2026-07-18: hist_ft's natural-key dedup constraint keyed on `account`
-- (raw Fidelity text — "Rollover IRA" from one export, "249118149" from
-- another, for the SAME physical account), so the same trade loaded from two
-- overlapping Fidelity export files ("Accounts_History" vs
-- "History_for_Account_*") wasn't recognized as a duplicate and both copies
-- were inserted (188 duplicated trades found + removed, keeping the earliest
-- load of each). account_number is reliably populated and consistent across
-- exports — re-key the dedup constraint on that instead so this can't
-- recur. (The live table's PK was previously migrated to a surrogate `id`
-- BIGSERIAL with this as a plain UNIQUE constraint; DROP/CREATE here is
-- idempotent regardless of what the constraint was named.)
ALTER TABLE IF EXISTS hist_ft DROP CONSTRAINT IF EXISTS uq_hist_f_transactions_natural;
CREATE UNIQUE INDEX IF NOT EXISTS ux_hist_ft_natural_key
    ON hist_ft (account_number, trade_date, action, symbol, quantity, price);

-- -----------------------------------------------------
-- hist_401k_contrib  <- 401(k) "Contribution History" export (file_type F401K)
-- One row per (fund, transaction) line. Distinct from hist_ft: this report
-- has no ticker/price/account-number columns, just plan name + fund name +
-- transaction type + dollar amount + units. Exported ad hoc with overlapping
-- date ranges (e.g. re-exporting "since Jan 1" every month), so dedup is via
-- a natural-key unique index + ON CONFLICT, same pattern as hist_ft.
-- 2026-07-18: added to let YTD/MTD net out 401(k) contributions from the
-- Total-delta gain calc (currently misattributes contributions as gain).
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_401k_contrib (
    id                 BIGSERIAL PRIMARY KEY,
    plan_name          TEXT    NOT NULL,        -- "Plan name:" header line, e.g. "BOEING 401(K)"
    account_number     TEXT,                    -- resolved from hist_f.account_name at load time
    trade_date         DATE    NOT NULL,         -- "Date" column
    investment         TEXT    NOT NULL,         -- fund name, e.g. "TARGET DATE 2035"
    transaction_type   TEXT    NOT NULL,         -- "Contributions", etc.
    amount             NUMERIC,
    shares              NUMERIC,                 -- "Shares/Unit" column
    source_file        TEXT,
    loaded_at          TIMESTAMP NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_hist_401k_contrib_natural_key
    ON hist_401k_contrib (plan_name, trade_date, investment, transaction_type, amount, shares);
CREATE INDEX IF NOT EXISTS ix_hist_401k_contrib_acct ON hist_401k_contrib(account_number, trade_date);

INSERT INTO ref_load_files
    (source_dir, file_type, target_tab, week_day, file_time,
     enabled, optional, rows_should_match, target_table)
VALUES
    ('C:\Ashok\Investing\Stocks\F401K\Archive', 'F401K',
     '401k_contrib', 'SUN', TIME '16:00:00',
     TRUE, TRUE, FALSE, 'hist_401k_contrib')
ON CONFLICT (file_type, week_day, file_time) DO NOTHING;



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

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_sym  ON drv_realized_gain(symbol, sell_date);

CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_date ON drv_realized_gain(sell_date);

CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_acct ON drv_realized_gain(account, sell_date);



-- -----------------------------------------------------

-- hist_etfchg  <- etfchg tab

-- (action / chg / wt / date2 / wt2 / ma_ref / imported_date dropped by 35.)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_etfchg (

    event_date    DATE NOT NULL,

    symbol        TEXT NOT NULL,

    tos_symbol    TEXT,

    description   TEXT,

    outlook       TEXT,

    change_str    TEXT,

    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),

    source_file   TEXT,

    PRIMARY KEY (event_date, symbol)

);

ALTER TABLE hist_etfchg ADD COLUMN IF NOT EXISTS tos_symbol TEXT;


-- -----------------------------------------------------

-- hist_iichg  <- IIchg tab

-- (action / chg / miss / mos / imported_date dropped by 35.)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_iichg (

    event_date    DATE NOT NULL,

    symbol        TEXT NOT NULL,

    tos_symbol    TEXT,

    outlook       TEXT,

    description   TEXT,

    change_str    TEXT,

    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),

    source_file   TEXT,

    PRIMARY KEY (event_date, symbol)

);

ALTER TABLE hist_iichg ADD COLUMN IF NOT EXISTS tos_symbol TEXT;


-- -----------------------------------------------------

-- hist_ps  <- ps tab

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS hist_ps (

    snapshot_date    DATE NOT NULL,

    ticker           TEXT NOT NULL,

    tos_symbol       TEXT,

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

ALTER TABLE hist_ps ADD COLUMN IF NOT EXISTS tos_symbol TEXT;





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

ALTER TABLE IF EXISTS meta_file_processed

    ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'file';



-- -----------------------------------------------------

-- meta_file_origin  (email-rendered files registry)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS meta_file_origin (

    file_path   TEXT PRIMARY KEY,

    source_kind TEXT NOT NULL DEFAULT 'email',

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()

);



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

ALTER TABLE meta_warning ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'meta_warning' AND column_name = 'symbol') THEN
        UPDATE meta_warning SET tos_symbol = symbol WHERE tos_symbol IS NULL AND symbol IS NOT NULL;
        ALTER TABLE meta_warning DROP COLUMN symbol;
    END IF;
END $$;


-- =====================================================

-- 4. Derived tables (drv_*)

-- (Only the tables still alive after migrations 28-34.)

-- =====================================================



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

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_td_symbol ON drv_td(symbol, snapshot_date);



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

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_tw_symbol ON drv_tw(symbol, snapshot_date);



-- -----------------------------------------------------

-- drv_to - per-row derivations from TO (TOS Other - fundamentals)

-- 2026-05-28: Computes market_cap_num from hist_to.market_cap_str

-- Format: "71,783 M" → 71783000000 (value in dollars)

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS drv_to (

    snapshot_date     DATE NOT NULL,

    symbol            TEXT NOT NULL,

    sequence          INTEGER NOT NULL DEFAULT 0,

    market_cap_num    NUMERIC,

    computed_at       TIMESTAMP NOT NULL DEFAULT now(),

    source_run_id     BIGINT,

    PRIMARY KEY (snapshot_date, symbol, sequence),

    FOREIGN KEY (snapshot_date, symbol, sequence)

        REFERENCES hist_to(snapshot_date, symbol, sequence)

        ON DELETE CASCADE

);

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_to_symbol ON drv_to(symbol, snapshot_date);



-- -----------------------------------------------------

-- drv_source_standing — canonical per-source standing layer (2026-06-13)
-- One row per (as_of_date, source_code, tos_symbol). Only on_list=TRUE rows
-- are written (absence = removed). Built by etl/derive_source_standing.py
-- BEFORE the action and signal consumers. Idempotent per as_of_date.
-- Sources: SSS | ETF | II | PS | RR | CALL

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS drv_source_standing (

    as_of_date    DATE     NOT NULL,
    source_code   TEXT     NOT NULL,
    tos_symbol    TEXT     NOT NULL,
    snapshot_date DATE,
    on_list       BOOLEAN  NOT NULL DEFAULT TRUE,
    weight        NUMERIC,
    rank          NUMERIC,
    raw_value     NUMERIC,
    signal_sign   INTEGER,
    rank_hl       NUMERIC,
    outlook       TEXT,
    modifier      TEXT,
    source_run_id BIGINT,

    PRIMARY KEY (as_of_date, source_code, tos_symbol)

);

CREATE INDEX IF NOT EXISTS ix_drv_src_standing_date
    ON drv_source_standing(as_of_date, source_code);

CREATE INDEX IF NOT EXISTS ix_drv_src_standing_sym
    ON drv_source_standing(tos_symbol, as_of_date);



-- drv_sss RETIRED 2026-06-13 — table dropped; data now in drv_source_standing.

-- Migration: drop drv_sss if it still exists on older databases.

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_name = 'drv_sss' AND table_type = 'BASE TABLE') THEN
    DROP TABLE drv_sss CASCADE;
    RAISE NOTICE 'drv_sss dropped (retired 2026-06-13)';
  END IF;
END $$;



-- -----------------------------------------------------

-- drv_y - converted float and shares outstanding from hist_y strings

-- Converts hist_y.float_str and hist_y.shares_out_str from text to NUMERIC.
-- Built by etl/derive.py::derive_y, idempotent per snapshot_date.

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS drv_y (

    snapshot_date   DATE NOT NULL,

    tos_symbol      TEXT NOT NULL,

    float           NUMERIC,

    shares_out      NUMERIC,

    computed_at     TIMESTAMP NOT NULL DEFAULT now(),

    source_run_id   BIGINT,

    PRIMARY KEY (snapshot_date, tos_symbol)

);

CREATE INDEX IF NOT EXISTS ix_drv_y_date ON drv_y(snapshot_date);

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

    iv_to_hv_discount INTEGER,      -- (1 - IV/HV)*100: positive = IV cheap vs HV, negative = IV expensive

    export_date     DATE,

    export_time     TEXT,

    loaded_at       TIMESTAMP,

    source          TEXT,           -- feed that provided last_price: 'Y' | 'TL' | 'TD'

    derived_at      TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (as_of_date, symbol)

);

-- drv_quote.source added 2026-06-05 — which feed won last_price (debug 0 high/log etc.)
ALTER TABLE drv_quote ADD COLUMN IF NOT EXISTS source TEXT;
-- drv_quote.iv_to_hv renamed to iv_to_hv_discount 2026-06-17; formula changed to (1-IV/HV)*100
ALTER TABLE drv_quote ADD COLUMN IF NOT EXISTS iv_to_hv_discount INTEGER;
ALTER TABLE drv_quote DROP COLUMN IF EXISTS iv_to_hv;

-- drv_rr: derived risk range — hist_rr preferred, hist_td BB bands as fallback
CREATE TABLE IF NOT EXISTS drv_rr (
    as_of_date      DATE        NOT NULL,
    tos_symbol      TEXT        NOT NULL,
    lrr             NUMERIC,        -- Lower Risk Range (buy_trade or a_bb_bottom)
    trr             NUMERIC,        -- Top Risk Range  (sell_trade or a_bb_top)
    mrr             NUMERIC,        -- Midpoint (lrr + trr) / 2
    outlook         TEXT,           -- outlook from hist_rr (Bullish/Bearish/Neutral); NULL when BB fallback
    source          TEXT,           -- 'RR' or 'BB'
    source_run_id   BIGINT,
    derived_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol)
);

CREATE INDEX IF NOT EXISTS ix_drv_rr_sym ON drv_rr(tos_symbol, as_of_date);

ALTER TABLE drv_rr ADD COLUMN IF NOT EXISTS outlook TEXT;

-- Add export_date, export_time, and loaded_at columns if they don't exist (migration for existing tables)

DO $$

BEGIN

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                  WHERE table_name='drv_quote' AND column_name='export_date') THEN

    ALTER TABLE drv_quote ADD COLUMN export_date DATE;

  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                  WHERE table_name='drv_quote' AND column_name='export_time') THEN

    ALTER TABLE drv_quote ADD COLUMN export_time TEXT;

  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                  WHERE table_name='drv_quote' AND column_name='loaded_at') THEN

    ALTER TABLE drv_quote ADD COLUMN loaded_at TIMESTAMP;

  END IF;

END $$;



-- Drop snapshot_date column if it exists (was added outside baseline.sql, not used)

ALTER TABLE drv_quote DROP COLUMN IF EXISTS snapshot_date;



-- Add tos_symbol to drv_quote (migration for tos_symbol normalization)

DO $$

BEGIN

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                  WHERE table_name='drv_quote' AND column_name='tos_symbol') THEN

    ALTER TABLE drv_quote ADD COLUMN tos_symbol TEXT;

  END IF;

END $$;



-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_quote_symbol ON drv_quote(symbol);

CREATE INDEX IF NOT EXISTS ix_drv_quote_tos_symbol ON drv_quote(tos_symbol);



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

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_ma_symbol ON drv_ma(symbol, as_of_date);



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

ALTER TABLE drv_dash ADD COLUMN IF NOT EXISTS tos_symbol TEXT;


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

ALTER TABLE drv_stks ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

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

ALTER TABLE drv_missing_symbols ADD COLUMN IF NOT EXISTS tos_symbol TEXT;


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

    trend_cross_over                         NUMERIC,

    trend_rule                               NUMERIC,

    not_trend_rule                           NUMERIC,

    trend_trade_dep_rule                     NUMERIC,

    trtn_relation                            NUMERIC,

    not_trtn_relation                        NUMERIC,

    trade_trend_sd_rule                      NUMERIC,

    bb_rng_strk_rule                         NUMERIC,

    bull_rr_action                           NUMERIC,

    not_bull_rr_action                       NUMERIC,

    td_tn_bb_rr_action                       NUMERIC,

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

    "3m_low_rule"                            NUMERIC,

    "3m_low_days_rule"                       NUMERIC,

    "3mn_high_rule"                          NUMERIC,

    "3mn_high_days_rule"                     NUMERIC,

    "3m_long"                                NUMERIC,

    perf3mn_sd_rule                          NUMERIC,

    perf2m_sd_rule                           NUMERIC,

    perf3wk_sd_rule                          NUMERIC,

    perf2wk_sd_rule                          NUMERIC,

    perf3d_sd_rule                           NUMERIC,

    perf1d_sd_rule                           NUMERIC,

    not_perf1d_sd                            NUMERIC,

    perf3d_sd_1off                           NUMERIC,

    perf_sd_rule                             NUMERIC,

    not_perf_sd_rule                         NUMERIC,

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

    not_overbought                           NUMERIC,

    "3mn_outlook"                            NUMERIC,

    "3mn_outlook_days"                       NUMERIC,

    "3wk_outlook"                            NUMERIC,

    "3wk_outlook_days"                       NUMERIC,

    not_3wk_ol                               NUMERIC,

    not_3wk_ol_days                          NUMERIC,

    bull                                     NUMERIC,

    not_bull                                 NUMERIC,

    perforbull                               NUMERIC,

    not_perforbull                           NUMERIC,

    "50_dma_rule"                            NUMERIC,

    "50_dma_crossover"                       NUMERIC,

    "200_dma_rule"                           NUMERIC,

    "200_dma_crossover"                      NUMERIC,

    "52_wk_low_rule"                         NUMERIC,

    "52_wk_high_rule"                        NUMERIC,

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

-- td_tn_bb_rr_action: QR numeric value -> QS (action code) + QT (sort seq)
-- Source: Parm!AO (code), AQ (description/action), AR (seq). First match per code.
INSERT INTO ref_param_lookup (table_name, code, description, seq) VALUES
    ('td_tn_bb_rr_action', '-10', 'SA',  21),
    ('td_tn_bb_rr_action', '-9',  'STM', 20),
    ('td_tn_bb_rr_action', '-8',  'SS',  19),
    ('td_tn_bb_rr_action', '-7',  'SO',  12),
    ('td_tn_bb_rr_action', '-6',  'SW',  11),
    ('td_tn_bb_rr_action', '-5',  'SWW',  5),
    ('td_tn_bb_rr_action', '-1',  'SN',   3),
    ('td_tn_bb_rr_action', '0',   'N',    3),
    ('td_tn_bb_rr_action', '1',   'BN',   3),
    ('td_tn_bb_rr_action', '3',   'BC',  14),
    ('td_tn_bb_rr_action', '4',   'BRW',  5),
    ('td_tn_bb_rr_action', '5',   'BSW',  9),
    ('td_tn_bb_rr_action', '6',   'BW',  10),
    ('td_tn_bb_rr_action', '7',   'BR',  13),
    ('td_tn_bb_rr_action', '8',   'BMN', 15),
    ('td_tn_bb_rr_action', '9',   'BS',  16),
    ('td_tn_bb_rr_action', '10',  'BM',  18)
ON CONFLICT (table_name, code) DO NOTHING;


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

    active                BOOLEAN NOT NULL DEFAULT TRUE,

    condition_operator    VARCHAR(2),

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

ALTER TABLE ref_trig_composite_mapping ADD COLUMN IF NOT EXISTS condition_operator VARCHAR(2)
    CHECK (condition_operator IN ('>=','<=','>','<','='));

-- Gate / WATCH member roles (2026-06-03). A 'gate' member is mandatory (strict
-- AND, the legacy behavior); a 'watch' member is corroborating evidence that
-- contributes to score/display but does not by itself block firing. A composite
-- fires when ALL gates pass AND the watch evidence clears evidence_cutoff
-- (NULL cutoff = watch never blocks). evidence_cutoff is composite-level, stored
-- on every member row like the other shared composite metadata.
-- DEFAULT 'gate' on every existing row → zero behavior change until members are
-- reclassified (see db/migrate_member_watch_roles.sql). See docs/rule_engine_redesign.md.
ALTER TABLE ref_trig_composite_mapping ADD COLUMN IF NOT EXISTS member_role TEXT NOT NULL DEFAULT 'gate'
    CHECK (member_role IN ('gate','watch'));
ALTER TABLE ref_trig_composite_mapping ADD COLUMN IF NOT EXISTS evidence_cutoff NUMERIC;

-- Surrogate primary key (2026-06-03). The original PK (composite_rule_code,
-- atomic_rule_id) made atomic_rule_id implicitly NOT NULL, which blocked
-- 'data' and nested-'composite' members (both have atomic_rule_id = NULL).
-- Replace it with a surrogate mapping_id PK, and keep a NULL-permissive UNIQUE
-- on (composite_rule_code, atomic_rule_id) so the workbook loader's ON CONFLICT
-- upsert + dedup still work for atomic members. Postgres treats NULLs as
-- distinct, so the many (code, NULL) rows from non-atomic members are allowed.
-- Idempotent: the PK is dropped + re-added each run (nothing references it); the
-- unique index uses IF NOT EXISTS. Existing rows are all atomic (the old PK
-- forbade NULL), so they remain unique under the new index.
ALTER TABLE ref_trig_composite_mapping DROP CONSTRAINT IF EXISTS ref_trig_composite_mapping_pkey;
ALTER TABLE ref_trig_composite_mapping ADD COLUMN IF NOT EXISTS mapping_id BIGSERIAL;
ALTER TABLE ref_trig_composite_mapping ADD PRIMARY KEY (mapping_id);
ALTER TABLE ref_trig_composite_mapping ALTER COLUMN atomic_rule_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ctm_code_atomic
    ON ref_trig_composite_mapping(composite_rule_code, atomic_rule_id);

-- Backfill: BUY rules → >=, SELL rules → <=
UPDATE ref_trig_composite_mapping
SET condition_operator = '>='
WHERE condition_operator IS NULL
  AND composite_rule_code ~ '^\d+-(B|BS|BR|BW|BM|BMN)-';

UPDATE ref_trig_composite_mapping
SET condition_operator = '<='
WHERE condition_operator IS NULL
  AND composite_rule_code ~ '^\d+-(SA|SS|STM|SW|SH)-';

CREATE INDEX IF NOT EXISTS ix_ref_trig_composite_atom ON ref_trig_composite_mapping(atomic_rule_id);

CREATE INDEX IF NOT EXISTS ix_composite_mapping_nested

    ON ref_trig_composite_mapping(nested_composite_code)

    WHERE nested_composite_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_composite_mapping_kind ON ref_trig_composite_mapping(member_kind);



-- -----------------------------------------------------

-- ref_trig_param_set / ref_trig_param_value (Phase 3, 2026-06-03)

-- Separates rule STRUCTURE (ref_trig_*) from tunable PARAMETERS (thresholds,

-- weights, sigmoid k/x0). A parameter set is a named, versioned overlay applied

-- at scoring time (etl/param_sets.py, consumed by load_trig_rules). The active

-- set (is_active=TRUE) overrides the base values; with no active set the engine

-- uses the values stored directly on ref_trig_atomic_rule (zero change).

-- ML (etl/ml_tune_thresholds.py) proposes a new set, you backtest, then activate.

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_trig_param_set (

    param_set_id   SERIAL PRIMARY KEY,

    label          TEXT NOT NULL,

    provenance     TEXT,                 -- 'manual' | 'ml:<model>' | 'backtest'

    is_active      BOOLEAN NOT NULL DEFAULT FALSE,

    notes          TEXT,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()

);

-- At most one active set.

CREATE UNIQUE INDEX IF NOT EXISTS ux_param_set_active

    ON ref_trig_param_set(is_active) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS ref_trig_param_value (

    param_set_id   INTEGER NOT NULL REFERENCES ref_trig_param_set(param_set_id) ON DELETE CASCADE,

    target_kind    TEXT NOT NULL,        -- 'atomic' | 'composite_member' | 'composite'

    target_id      TEXT NOT NULL,        -- atomic_rule_id, or 'code|atomic_id', or composite code

    param_name     TEXT NOT NULL,        -- brkeout_from|brkeout_to|wt_below|wt_between|wt_above|x0|k|evidence_cutoff

    param_value    NUMERIC,

    PRIMARY KEY (param_set_id, target_kind, target_id, param_name)

);

-- ref_rrt seed: non-equity index/volatility instruments (2026-06-03)
INSERT INTO ref_rrt (rr_name, y_ticker, tos_ticker, reverse) VALUES
    ('GVZ',  '^GVZ',       '$GVZ',  'N'),
    ('INDU', '^DJI',       '$INDU', 'N'),
    ('MOVE', '^MOVE',      '$MOVE', 'N'),
    ('OVX',  '^OVX',       '$OVX',  'N'),
    ('VOLQ', '^VOLQ',      '$VOLQ', 'N'),
    ('VXN',  '^VXN',       '$VXN',  'N'),
    ('BTC',    'BTC=F',   '/BTC',    'N'),
    ('DXY',    'DX=F',    'DXY',    'N'),
    ('NYICDX', '^NYICDX', '$DXY',   'N'),
    ('JPYUSD', 'JPY=X',   'JPYUSD', 'N')
ON CONFLICT (rr_name) DO UPDATE
    SET y_ticker   = EXCLUDED.y_ticker,
        tos_ticker = EXCLUDED.tos_ticker;

UPDATE ref_rrt SET tos_ticker = '$SSEC'
WHERE rr_name = 'SSEC' AND (tos_ticker IS NULL OR tos_ticker = '');

CREATE INDEX IF NOT EXISTS ix_param_value_set ON ref_trig_param_value(param_set_id);



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

ALTER TABLE drv_trig ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_trig_symbol    ON drv_trig(symbol, as_of_date);

CREATE INDEX IF NOT EXISTS ix_drv_trig_rule      ON drv_trig(composite_rule_code, as_of_date);

CREATE INDEX IF NOT EXISTS ix_drv_trig_triggered ON drv_trig(as_of_date, triggered) WHERE triggered = TRUE;



-- -----------------------------------------------------

-- drv_rule_outcome - forward-return audit per rule fire

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS drv_rule_outcome (

    rule_id        TEXT NOT NULL,

    rule_kind      TEXT NOT NULL,

    as_of_date     DATE NOT NULL,

    tos_symbol     TEXT NOT NULL,

    action_code    TEXT,

    fwd_5d_pct     NUMERIC,

    fwd_20d_pct    NUMERIC,

    hit            BOOLEAN,

    computed_at    TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (rule_id, as_of_date, tos_symbol)

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

-- drv_macro_score: per-symbol MacroNet = 0.65*M + 0.35*Q
CREATE TABLE IF NOT EXISTS drv_macro_score (
    as_of_date      DATE        NOT NULL,
    tos_symbol      TEXT        NOT NULL,
    month_now_net   NUMERIC,
    month_next_net  NUMERIC,
    month_weight    NUMERIC,
    monthly_score   NUMERIC,
    qtr_now_net     NUMERIC,
    qtr_next_net    NUMERIC,
    qtr_weight      NUMERIC,
    quarterly_score NUMERIC,
    macronet             NUMERIC,
    macro_action         TEXT,
    monthly_scores_json  JSONB,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_macro_score_date
    ON drv_macro_score(as_of_date);





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

    tos_symbol TEXT       PRIMARY KEY,

    added_at   TIMESTAMP  NOT NULL DEFAULT now(),

    active     CHAR(1)    NOT NULL DEFAULT 'Y',

    notes      TEXT

);

-- Migrate from symbol PK to tos_symbol PK
DO $$
BEGIN
    -- If old schema still has symbol as PK, migrate
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'ref_my_stocks' AND column_name = 'symbol') THEN
        -- Populate tos_symbol from symbol
        UPDATE ref_my_stocks SET tos_symbol = symbol WHERE tos_symbol IS NULL;
        -- Drop old PK and symbol column
        ALTER TABLE ref_my_stocks DROP CONSTRAINT ref_my_stocks_pkey;
        ALTER TABLE ref_my_stocks DROP COLUMN symbol;
        -- Add new PK on tos_symbol
        ALTER TABLE ref_my_stocks ADD PRIMARY KEY (tos_symbol);
    END IF;
END $$;

-- Note: symbol remains as PK for backward compat; tos_symbol is the normalized key

-- -----------------------------------------------------

-- ref_outlook_source - 8 sources from Requirements matrix

-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_outlook_source (

    source_code          TEXT        PRIMARY KEY,

    source_table         TEXT        NOT NULL,

    investment_priority  INTEGER     NOT NULL,

    base_weight_method   TEXT        NOT NULL CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta','rta_alert')),

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

-- MIGRATED TO tos_symbol: CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_sym  ON drv_outlook_action(symbol, as_of_date);



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



-- 2026-05-26: asset_class column (resolved category used for min/max/units lookup).

ALTER TABLE IF EXISTS drv_actionable

ADD COLUMN IF NOT EXISTS asset_class TEXT;



-- 2026-05-26: source_asset_class column (actual asset class from source, e.g., Equities, Gold, Growth).

ALTER TABLE IF EXISTS drv_actionable

ADD COLUMN IF NOT EXISTS source_asset_class TEXT;

-- 2026-05-31: trig_action — best action from fired rule groups (SA/STM/SS/BM vocabulary).
-- Derived from drv_actionable.triggered_group_ids: most aggressive BuySell score wins
-- (most negative = most bearish; most positive if no bearish signals).

ALTER TABLE IF EXISTS drv_actionable

ADD COLUMN IF NOT EXISTS trig_action TEXT;


-- neg_multiplier: scales the negative-side zone thresholds in _eval_trig_ifs.
-- Default 1.0 = symmetric (negative side mirrors positive).
ALTER TABLE IF EXISTS ref_trig_atomic_rule
ADD COLUMN IF NOT EXISTS neg_multiplier NUMERIC NOT NULL DEFAULT 1.0;

-- neg_brkeout_from / neg_brkeout_to: explicit negative-side thresholds.
-- When set, _eval_trig_ifs uses these directly (not neg_multiplier * brkeout_*).
-- current_volume_rule uses 25/50 (= 100/200 * 0.25) per Excel formula.
ALTER TABLE IF EXISTS ref_trig_atomic_rule
ADD COLUMN IF NOT EXISTS neg_brkeout_from NUMERIC;

ALTER TABLE IF EXISTS ref_trig_atomic_rule
ADD COLUMN IF NOT EXISTS neg_brkeout_to NUMERIC;

UPDATE ref_trig_atomic_rule
SET neg_brkeout_from = 25, neg_brkeout_to = 50
WHERE rule_name = 'current_volume_rule';

-- source_column: table.column reference for the raw hist_* value this rule evaluates
-- (e.g. hist_td.brr_pct). Multiple rules sharing the same raw value use the same ref.
ALTER TABLE IF EXISTS ref_trig_atomic_rule
ADD COLUMN IF NOT EXISTS source_column TEXT;

ALTER TABLE IF EXISTS ref_trig_atomic_rule
ADD COLUMN IF NOT EXISTS source_table TEXT;

-- Seed source_column (label) from Excel column mapping. Re-runnable.
UPDATE ref_trig_atomic_rule AS r
SET source_column = v.col
FROM (VALUES
    ('BBThresh Crossover',                   'BB_Threshold_Crossover'),
    ('BBThresh CO Days',                     'BBThresh_CO_Days'),
    ('BBThresh CO Days2',                    'BBThresh_CO_Days'),
    ('Trade-Rule',                           'Trade_sd'),
    ('Trend-Rule',                           'Trend_sd'),
    ('Trade Trend SD Rule',                  'Trade_Trend_Sd'),
    ('BRR% Rule',                            'BRR%'),
    ('BRR% LRR',                             'BRR%'),
    ('BRR% R2',                              'BRR%'),
    ('BRR% LRR2',                            'BRR%'),
    ('BRR% TRR',                             'BRR%'),
    ('BRR% Puts',                            'BRR%'),
    ('BRR% TRR Puts',                        'BRR%'),
    ('High above TRR',                       'High TRR'),
    ('Low below LRR',                        'Low LRR'),
    ('TRR_Idx',                              'Sd TRR'),
    ('MRR_Idx',                              'Sd MRR'),
    ('LRR_Idx',                              'Sd LRR'),
    ('HVAbsolute',                           'D_HV'),
    ('IVAbsolute',                           'ImpVolatility'),
    ('IVPercentile',                         'IVPercentile'),
    ('IVPercentile Puts',                    'IVPercentile'),
    ('HVPercentile',                         'HVPercentile'),
    ('HVPercentile Puts',                    'HVPercentile'),
    ('IVHV Rule (modified)',                 'IVHV'),
    ('IVHV Puts (modified)',                 'IVHV'),
    ('RSI Rule',                             'RSI'),
    ('RSI Top',                              'RSI'),
    ('RSI Puts',                             'RSI'),
    ('3m-Low-Rule',                          '3mnLow_sd'),
    ('3m-Low-Days Rule',                     '3mnLowDays'),
    ('3mn-High-Rule',                        '3mnHigh_sd'),
    ('3mn-High-Dyas Rule',                   '3mnHighDays'),
    ('Perf3mn SD Rule',                      'Perf3M_sd'),
    ('Perf2M SD Rule',                       'Perf2M_sd'),
    ('Perf3wk SD Rule',                      'Perf3W_sd'),
    ('Perf2wk SD Rule',                      'Perf2Wk_sd'),
    ('Perf3D SD Rule',                       'Perf3D_sd'),
    ('Perf1D SD Rule',                       'Perf1D_sd'),
    ('Perf3D 1Off Rule',                     'Perf3D_sd'),
    ('BBHighLow_SD Rule',                    'BBHighLow_SD'),
    ('BBHighLow Days Rule',                  'BBHighLowDays'),
    ('BBStreak Rule',                        'BB_Streak'),
    ('BBStreak Rule1',                       'BBStreakRule1'),
    ('BBStreak Rule2',                       'BB_Streak'),
    ('BBStreak Days Rule',                   'BB_Streak_Days'),
    ('BBStreak Days Up Rule',                'BB_Streak_Days'),
    ('BBStreak Days Rule2',                  'BB_Streak_Days'),
    ('BBStreak Days Up Rule2',               'BB_Streak_Days'),
    ('BBHighDays',                           'BBHighDays'),
    ('BBLowDays',                            'BBLowDays'),
    ('MACD Rule',                            'MACD_BRR'),
    ('MACDH Rule',                           'MACDH_BRR'),
    ('MACD_BRR Puts',                        'MACD_BRR'),
    ('MACDH_BRR Puts',                       'MACDH_BRR'),
    ('MACDH Days',                           'A_MACDays_Streak'),
    ('MACDH Days2',                          'A_MACDays_Streak'),
    ('Overbought',                           'Overbought'),
    ('3mn Outlook',                          '3mn_stk_outlook_sd'),
    ('3mn Outlook Days',                     '3mnHighLowDays'),
    ('3wk Outlook',                          '3w_stk_outlook_sd'),
    ('3wk Outlook Days',                     '3wkHighLowDays'),
    ('50-DMA-Rule',                          '50 DMA'),
    ('200-DMA-Rule',                         '200 DMA'),
    ('52-Wk Low Rule',                       '52Low'),
    ('52-Wk High Rule',                      '52High'),
    ('Earnings Days',                        'EarningsDays'),
    ('VS Price Rule',                        'VS Price Change SD'),
    ('VS Volume Spike Rule',                 'VS Volume Spike'),
    ('VS Volatility Rule',                   'VS Volatility'),
    ('VS Days',                              'VS Days'),
    ('VS LT Outlook Rule',                   'VS LT Outlook Rule'),
    ('Current Price Rule',                   'Current Price SD Rule'),
    ('Current Volume Rule',                  'Current Volume Rule'),
    ('Current Volatility Rule',              'Current Volatility Rule'),
    ('Short Term Oulook (If LT Bullish)',    'Short Term Oulook (If LT Bullish)'),
    ('Short Term Oulook (If LT Bearish)',    'Short Term Oulook (If LT Bearish)')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

-- Set source_table + actual DB column name for rules with known DB locations.
-- These overwrite the Excel-label source_column with the real column name.
UPDATE ref_trig_atomic_rule AS r
SET source_table = 'drv_ma', source_column = v.col
FROM (VALUES
    ('200-DMA-Rule',            'sma_200'),
    ('50-DMA-Rule',             'sma_50'),
    ('RSI Rule',                'rsi'),
    ('RSI Top',                 'rsi'),
    ('RSI Puts',                'rsi'),
    ('IVPercentile',            'iv_percentile'),
    ('IVPercentile Puts',       'iv_percentile'),
    ('HVPercentile',            'hv_percentile'),
    ('HVPercentile Puts',       'hv_percentile'),
    ('IVAbsolute',              'imp_volatility'),
    ('IVHV Rule (modified)',    'd_iv_to_hv'),
    ('IVHV Puts (modified)',    'd_iv_to_hv'),
    ('MACD Rule',               'a_macd_brr'),
    ('MACDH Rule',              'a_macdh_d_brr'),
    ('MACD_BRR Puts',           'a_macd_brr'),
    ('MACDH_BRR Puts',          'a_macdh_d_brr'),
    ('BRR% Rule',               'pct_brr'),
    ('BRR% LRR',                'pct_brr'),
    ('BRR% R2',                 'pct_brr'),
    ('BRR% LRR2',               'pct_brr'),
    ('BRR% TRR',                'pct_brr'),
    ('BRR% Puts',               'pct_brr'),
    ('BRR% TRR Puts',           'pct_brr'),
    ('Earnings Days',           'earnings_days'),
    ('BBStreak Rule',           'a_bb_streak'),
    ('BBStreak Rule1',          'a_bb_streak'),
    ('BBStreak Rule2',          'a_bb_streak'),
    ('BBStreak Days Rule',      'a_bb_streak'),
    ('BBStreak Days Up Rule',   'a_bb_streak'),
    ('BBStreak Days Rule2',     'a_bb_streak'),
    ('BBStreak Days Up Rule2',  'a_bb_streak')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'drv_cat_atomic_input', source_column = v.col
FROM (VALUES
    ('BBThresh Crossover', 'bbthresh_crossover'),
    ('TRR_Idx',            'trr_idx'),
    ('MRR_Idx',            'mrr_idx'),
    ('LRR_Idx',            'lrr_idx')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'hist_tw', source_column = v.col
FROM (VALUES
    ('VS Price Rule',         'a_volume_spike'),
    ('VS Volume Spike Rule',  'a_volume_spike'),
    ('VS Volatility Rule',    'a_volume_spike'),
    ('VS Days',               'a_volume_spike'),
    ('VS LT Outlook Rule',    'a_volume_spike')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

-- v2: corrected source_table + source_column derived from full working-set analysis.
-- These override the partial/wrong seeds above. Each rule points to the actual
-- raw hist_*/drv_* column that is read into compute_intermediates().

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'hist_td', source_column = v.col
FROM (VALUES
    ('BBThresh Crossover',     'a_bb_streak'),
    ('BBThresh CO Days',       'a_bb_streak'),
    ('BBThresh CO Days2',      'a_bb_streak'),
    ('Trade-Rule',             'a_trade_value'),
    ('Trend-Rule',             'a_trend_value'),
    ('Trade Trend SD Rule',    'a_trade_value'),
    ('HVAbsolute',             'historical_vol'),
    ('IVPercentile',           'a_iv_percentile'),
    ('IVPercentile Puts',      'a_iv_percentile'),
    ('HVPercentile',           'a_hv_percentile'),
    ('HVPercentile Puts',      'a_hv_percentile'),
    ('BBHighLow_SD Rule',      'a_bb_high_low'),
    ('BBHighLow Days Rule',    'a_bb_high_low'),
    ('BBStreak Rule',          'a_bb_streak'),
    ('BBStreak Rule1',         'a_bb_streak'),
    ('BBStreak Rule2',         'a_bb_streak'),
    ('BBStreak Days Rule',     'a_bb_streak'),
    ('BBStreak Days Up Rule',  'a_bb_streak'),
    ('BBStreak Days Rule2',    'a_bb_streak'),
    ('BBStreak Days Up Rule2', 'a_bb_streak'),
    ('BBHighDays',             'a_bb_high_low_days'),
    ('BBLowDays',              'a_bb_high_low_days'),
    ('Perf3mn SD Rule',        'a_trend_value'),
    ('Perf3wk SD Rule',        'a_trade_value')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'hist_tw', source_column = v.col
FROM (VALUES
    ('200-DMA-Rule',          'sma_200'),
    ('50-DMA-Rule',           'sma_50'),
    ('52-Wk Low Rule',        'low_52'),
    ('52-Wk High Rule',       'high_52'),
    ('Earnings Days',         'a_earnings_days'),
    ('MACD Rule',             'a_macd_brr'),
    ('MACD_BRR Puts',         'a_macd_brr'),
    ('MACDH Rule',            'a_macdh_d_brr'),
    ('MACDH_BRR Puts',        'a_macdh_d_brr'),
    ('MACDH Days',            'a_macdays_streak'),
    ('MACDH Days2',           'a_macdays_streak'),
    ('3m-Low-Rule',           'a_3mn_low'),
    ('3m-Low-Days Rule',      'a_3mn_low'),
    ('3mn-High-Rule',         'a_3mn_high'),
    ('3mn-High-Dyas Rule',    'a_3mn_high'),
    ('Perf2M SD Rule',        'a_perf_2m'),
    ('Perf2wk SD Rule',       'a_perf_2wk'),
    ('Perf3D SD Rule',        'a_perf_3d'),
    ('Perf3D 1Off Rule',      'a_perf_3d'),
    ('3mn Outlook',           'a_3mn_high_low'),
    ('3mn Outlook Days',      'a_3mn_high_low'),
    ('3wk Outlook',           'a_3wk_high_low'),
    ('3wk Outlook Days',      'a_3wk_high_low')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'drv_quote', source_column = v.col
FROM (VALUES
    ('RSI Rule',                'rsi'),
    ('RSI Top',                 'rsi'),
    ('RSI Puts',                'rsi'),
    ('IVAbsolute',              'imp_volatility'),
    ('IVHV Rule (modified)',    'imp_volatility'),
    ('IVHV Puts (modified)',    'imp_volatility'),
    ('Perf1D SD Rule',          'net_chng'),
    ('Current Price Rule',      'net_chng'),
    ('Current Volatility Rule', 'imp_volatility')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule AS r
SET source_table = 'drv_rr', source_column = v.col
FROM (VALUES
    ('BRR% Rule',      'lrr'),
    ('BRR% LRR',       'lrr'),
    ('BRR% R2',        'lrr'),
    ('BRR% LRR2',      'lrr'),
    ('BRR% TRR',       'lrr'),
    ('BRR% Puts',      'lrr'),
    ('BRR% TRR Puts',  'lrr'),
    ('High above TRR', 'trr'),
    ('Low below LRR',  'lrr'),
    ('TRR_Idx',        'trr'),
    ('MRR_Idx',        'lrr'),
    ('LRR_Idx',        'lrr')
) AS v(rname, col)
WHERE r.rule_name = v.rname;

UPDATE ref_trig_atomic_rule
SET source_table = 'hist_tl', source_column = 'volume'
WHERE rule_name = 'Current Volume Rule';



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

    tos_symbol                 TEXT NOT NULL,

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



-- Add tos_symbol to user_action_log for consistency with tos_symbol migration

DO $$

BEGIN

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                  WHERE table_name = 'user_action_log' AND column_name = 'tos_symbol') THEN

        ALTER TABLE user_action_log ADD COLUMN tos_symbol TEXT;

    END IF;

END $$;



-- Populate tos_symbol from symbol for existing rows (only if symbol column exists)

DO $$

BEGIN

    IF EXISTS (SELECT 1 FROM information_schema.columns

               WHERE table_name = 'user_action_log' AND column_name = 'symbol') THEN

        UPDATE user_action_log SET tos_symbol = symbol WHERE tos_symbol IS NULL;

    END IF;

END $$;



-- Create indexes (only symbol-based if the column exists)

DO $$

BEGIN

    IF EXISTS (SELECT 1 FROM information_schema.columns

               WHERE table_name = 'user_action_log' AND column_name = 'symbol') THEN

        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_user_action_log_symbol_date ON user_action_log(symbol, as_of_date)';

        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_user_action_log_date_sym ON user_action_log(as_of_date, symbol)';

    END IF;

END $$;



CREATE INDEX IF NOT EXISTS ix_user_action_log_tos_symbol_date ON user_action_log(tos_symbol, as_of_date);

CREATE INDEX IF NOT EXISTS ix_user_action_log_date        ON user_action_log(as_of_date);

CREATE INDEX IF NOT EXISTS ix_user_action_log_date_tos_sym ON user_action_log(as_of_date, tos_symbol);

CREATE INDEX IF NOT EXISTS ix_user_action_log_acted       ON user_action_log(acted_at DESC);



-- =====================================================

-- Migration: Add tos_symbol to all hist and derived tables

-- Migrate user_action_log from symbol to tos_symbol
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_action_log' AND column_name = 'symbol') THEN
        UPDATE user_action_log SET tos_symbol = symbol WHERE tos_symbol IS NULL AND symbol IS NOT NULL;
        ALTER TABLE user_action_log DROP COLUMN symbol;
    END IF;
END $$;

-- =====================================================

DO $$

DECLARE

    hist_tables TEXT[] := ARRAY['hist_cs', 'hist_cst', 'hist_f', 'hist_ft'];

    drv_tables TEXT[] := ARRAY['drv_ma', 'drv_dash', 'drv_stks', 'drv_dash_summary',

                                'drv_trig', 'drv_rule_outcome', 'drv_actionable',

                                'drv_cat_atomic_input', 'drv_realized_gain', 'drv_cs_realized_gain',

                                'drv_td', 'drv_tw', 'drv_to', 'drv_outlook_action'];

    all_tables TEXT[];

    tbl TEXT;

BEGIN

    all_tables := hist_tables || drv_tables;

    FOREACH tbl IN ARRAY all_tables LOOP

        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = tbl AND table_type = 'BASE TABLE') THEN

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns

                          WHERE table_name = tbl AND column_name = 'tos_symbol') THEN

                EXECUTE 'ALTER TABLE ' || tbl || ' ADD COLUMN tos_symbol TEXT';

            END IF;

        END IF;

    END LOOP;

END $$;



-- Create indexes on tos_symbol for hist tables

CREATE INDEX IF NOT EXISTS ix_hist_cs_tos_symbol ON hist_cs(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_cst_tos_symbol ON hist_cst(tos_symbol, trade_date);



-- Create indexes on tos_symbol for main derived tables

-- drv_ma index: only valid when drv_ma is still a TABLE (pre-migration)
DO $$ BEGIN
  IF (SELECT relkind FROM pg_class WHERE relname='drv_ma') = 'r' THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_drv_ma_tos_symbol ON drv_ma(tos_symbol)';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_drv_dash_tos_symbol ON drv_dash(tos_symbol);

CREATE INDEX IF NOT EXISTS ix_drv_stks_tos_symbol ON drv_stks(tos_symbol);

CREATE INDEX IF NOT EXISTS ix_drv_cat_atomic_input_tos_symbol ON drv_cat_atomic_input(tos_symbol);

CREATE INDEX IF NOT EXISTS ix_drv_actionable_tos_symbol ON drv_actionable(tos_symbol);



-- =====================================================

-- [REMOVED STALE CODE] Migration block for symbol column removal already completed


-- Drop symbol column from all drv_* tables

DO $$

DECLARE

    drv_tables TEXT[] := ARRAY['drv_ma', 'drv_dash', 'drv_stks', 'drv_dash_summary',

                                'drv_trig', 'drv_rule_outcome', 'drv_actionable',

                                'drv_cat_atomic_input', 'drv_realized_gain', 'drv_cs_realized_gain',

                                'drv_td', 'drv_tw', 'drv_to', 'drv_outlook_action',

                                'drv_quote', 'drv_missing_symbols'];

    tbl TEXT;

BEGIN

    FOREACH tbl IN ARRAY drv_tables LOOP

        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = tbl AND table_type = 'BASE TABLE') THEN

            IF EXISTS (SELECT 1 FROM information_schema.columns

                      WHERE table_name = tbl AND column_name = 'symbol') THEN

                EXECUTE 'ALTER TABLE ' || tbl || ' DROP COLUMN symbol';

            END IF;

        END IF;

    END LOOP;

END $$;



-- [REMOVED] Stale PK migration code - tables are created with correct tos_symbol PKs



-- Recreate indexes on tos_symbol for all drv_* tables (originals on `symbol`

-- were cascade-dropped by the DROP COLUMN above)

CREATE INDEX IF NOT EXISTS ix_drv_realized_gain_tos_sym ON drv_realized_gain(tos_symbol, sell_date);

-- 2026-07-18: restore the natural-key unique constraint on drv_realized_gain
-- lost when `symbol` was renamed to `tos_symbol` (the DROP COLUMN ... CASCADE
-- above dropped the original PRIMARY KEY along with it; only a plain index
-- was ever recreated). derive_realized_gain()'s INSERT ... ON CONFLICT
-- (source, account, tos_symbol, sell_date, shares_sold) requires a matching
-- unique index/constraint to target — without one, every insert has failed
-- with "no unique or exclusion constraint matching the ON CONFLICT
-- specification", which is why this table has been silently empty (0 rows)
-- since the rename.
CREATE UNIQUE INDEX IF NOT EXISTS ux_drv_realized_gain_natural_key
    ON drv_realized_gain (source, account, tos_symbol, sell_date, shares_sold);

CREATE INDEX IF NOT EXISTS ix_drv_td_tos_symbol         ON drv_td(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_drv_tw_tos_symbol         ON drv_tw(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_drv_to_tos_symbol         ON drv_to(tos_symbol, snapshot_date);

-- ix_drv_sss_tos_symbol RETIRED 2026-06-13 (drv_sss table dropped)

CREATE INDEX IF NOT EXISTS ix_drv_quote_tos_symbol      ON drv_quote(tos_symbol);
CREATE INDEX IF NOT EXISTS ix_drv_quote_tos_symbol_date ON drv_quote(tos_symbol, as_of_date);

-- drv_ma index: only valid when drv_ma is still a TABLE (pre-migration)
DO $$ BEGIN
  IF (SELECT relkind FROM pg_class WHERE relname='drv_ma') = 'r' THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_drv_ma_tos_symbol ON drv_ma(tos_symbol, as_of_date)';
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_drv_trig_tos_symbol       ON drv_trig(tos_symbol, as_of_date);

CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_tos_sym ON drv_outlook_action(tos_symbol, as_of_date);



-- =====================================================

-- 9. Views and functions

-- =====================================================



-- -----------------------------------------------------

-- v_dash(p_as_of_date)

-- -----------------------------------------------------

CREATE OR REPLACE FUNCTION v_dash(p_as_of_date DATE)

RETURNS SETOF drv_dash LANGUAGE sql STABLE AS $$

    SELECT * FROM drv_dash WHERE as_of_date = p_as_of_date

    ORDER BY section, tos_symbol;

$$;



-- -----------------------------------------------------

-- v_stks(p_as_of_date)

-- -----------------------------------------------------

CREATE OR REPLACE FUNCTION v_stks(p_as_of_date DATE)

RETURNS SETOF drv_stks LANGUAGE sql STABLE AS $$

    SELECT * FROM drv_stks WHERE as_of_date = p_as_of_date ORDER BY tos_symbol;

$$;



-- -----------------------------------------------------

-- v_ma(p_as_of_date)

-- -----------------------------------------------------

CREATE OR REPLACE FUNCTION v_ma(p_as_of_date DATE)

RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$

    SELECT * FROM drv_ma WHERE as_of_date = p_as_of_date ORDER BY tos_symbol;

$$;



-- -----------------------------------------------------

-- v_dash_summary(p_as_of_date)

-- -----------------------------------------------------

CREATE OR REPLACE FUNCTION v_dash_summary(p_as_of_date DATE)

RETURNS SETOF drv_dash_summary LANGUAGE sql STABLE AS $$

    SELECT * FROM drv_dash_summary WHERE as_of_date = p_as_of_date;

$$;



-- -----------------------------------------------------

-- v_symbol_history(p_symbol) - all snapshots for a single tos_symbol from drv_ma

-- -----------------------------------------------------

CREATE OR REPLACE FUNCTION v_symbol_history(p_symbol TEXT)

RETURNS SETOF drv_ma LANGUAGE sql STABLE AS $$

    SELECT * FROM drv_ma WHERE tos_symbol = p_symbol ORDER BY as_of_date DESC;

$$;



-- -----------------------------------------------------

-- v_available_dates - distinct as_of_dates with drv_dash/drv_stks rows

-- -----------------------------------------------------

-- Capped at the anchor date D = MAX(export_date) FROM hist_td (TOSD market
-- close), so the latest available date — used as the default on every screen
-- (dates[0]) and by _resolve_date() — is always the anchor, never a stray
-- post-migration future-dated derive. COALESCE keeps it open when hist_td is
-- empty. See docs/derive_date_logic.md.
CREATE OR REPLACE VIEW v_available_dates AS

    SELECT as_of_date FROM (
        SELECT as_of_date FROM drv_dash
        UNION
        SELECT as_of_date FROM drv_stks
    ) u

    WHERE as_of_date <= COALESCE((SELECT MAX(export_date) FROM hist_td), as_of_date)

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

DROP FUNCTION IF EXISTS v_outlook_changes(DATE) CASCADE;

CREATE OR REPLACE FUNCTION v_outlook_changes(p_as_of_date DATE)

RETURNS TABLE (

    tos_symbol        TEXT,

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

        SELECT doa.tos_symbol, doa.source_code, doa.action, doa.action_reason, doa.weight_delta, doa.held_today,

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

        SELECT DISTINCT ON (tos_symbol) tos_symbol, action AS dominant_action

        FROM ranked ORDER BY tos_symbol, prio, source_code

    )

    SELECT r.tos_symbol,

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

    JOIN dominant d USING (tos_symbol)

    GROUP BY r.tos_symbol, d.dominant_action

    ORDER BY n_sources_changed DESC, r.tos_symbol;

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
-- v_rule_scorecard - DIRECTION-ADJUSTED composite rule efficacy (Phase 4).
-- edge_20d > 0  => the rule's signal was correct on average. BUY rules want the
-- stock to rise (+fwd_20d); SELL rules want it to fall (-fwd_20d), so edge_20d
-- flips the sign for SELL codes. Rank by edge_20d DESC = best rules first.
-- win_rate already uses the direction-aware `hit` column. BASE-* are infra, excluded.
-- n_fires / ci_low / ci_high: 95% CI = edge ± 1.96*stddev_samp/sqrt(n).
-- confidence: 'proven' n>=100 AND ci_low>0; 'promising' n>=30 AND edge>0;
--             else 'unproven'. Diagnostic — one market regime only.
-- -----------------------------------------------------
DROP VIEW IF EXISTS v_rule_scorecard CASCADE;
CREATE VIEW v_rule_scorecard AS
WITH base AS (
    SELECT rule_id, hit, fwd_20d_pct, as_of_date,
           CASE WHEN rule_id ~ '^\d+-(B|BS|BR|BW|BM|BMN|BSW|BC|BRW)-'
                THEN fwd_20d_pct ELSE -fwd_20d_pct END AS da
    FROM drv_rule_outcome
    WHERE rule_kind = 'composite' AND fwd_20d_pct IS NOT NULL
      AND rule_id NOT LIKE 'BASE-%'
),
agg AS (
    SELECT rule_id,
           COUNT(*)                          AS n,
           AVG(da)                           AS e,
           STDDEV_SAMP(da)                   AS sd,
           AVG(hit::int)                     AS wr,
           AVG(fwd_20d_pct)                  AS raw,
           MIN(as_of_date)                   AS fs,
           MAX(as_of_date)                   AS ls
    FROM base GROUP BY rule_id
)
SELECT
    rule_id,
    CASE WHEN rule_id ~ '^\d+-(B|BS|BR|BW|BM|BMN|BSW|BC|BRW)-'
         THEN 'BUY' ELSE 'SELL' END              AS direction,
    n                                             AS fires,
    n                                             AS n_fires,
    ROUND(e::numeric, 3)                          AS edge_20d,
    ROUND((e - 1.96*sd/NULLIF(SQRT(n),0))::numeric,3)
                                                  AS edge_20d_ci_low,
    ROUND((e + 1.96*sd/NULLIF(SQRT(n),0))::numeric,3)
                                                  AS edge_20d_ci_high,
    CASE
        WHEN n >= 100
             AND (e - 1.96*sd/NULLIF(SQRT(n),0)) > 0 THEN 'proven'
        WHEN n >= 30 AND e > 0                        THEN 'promising'
        ELSE 'unproven'
    END                                           AS confidence,
    ROUND(wr::numeric, 3)                         AS win_rate,
    ROUND(raw::numeric, 3)                        AS raw_avg_fwd20,
    fs AS first_seen, ls AS last_seen
FROM agg;


-- -----------------------------------------------------
-- v_atomic_rule_scorecard - raw forward-return efficacy per atomic rule.
-- No direction adjustment (atomic features aren't BUY/SELL).
-- Joins ref_trig_atomic_rule for rule_name/intent_text.
-- confidence: 'proven' n>=100 AND ci_low>0; 'promising' n>=30 AND avg>0.
-- -----------------------------------------------------
DROP VIEW IF EXISTS v_atomic_rule_scorecard CASCADE;
CREATE VIEW v_atomic_rule_scorecard AS
WITH agg AS (
    SELECT rule_id,
           COUNT(*)              AS n,
           AVG(fwd_20d_pct)      AS e,
           STDDEV_SAMP(fwd_20d_pct) AS sd,
           AVG(fwd_5d_pct)       AS e5,
           AVG(hit::int)         AS wr,
           MIN(as_of_date)       AS fs,
           MAX(as_of_date)       AS ls
    FROM drv_rule_outcome
    WHERE rule_kind = 'atomic' AND fwd_20d_pct IS NOT NULL
    GROUP BY rule_id
)
SELECT
    a.rule_id,
    r.rule_name,
    r.intent_text,
    a.n,
    ROUND(a.e5::numeric, 3)                          AS avg_fwd_5d,
    ROUND(a.e::numeric, 3)                           AS avg_fwd_20d,
    ROUND(a.wr::numeric, 3)                          AS win_rate,
    ROUND((a.e - 1.96*a.sd/NULLIF(SQRT(a.n),0))::numeric,3)
                                                     AS ci_low,
    ROUND((a.e + 1.96*a.sd/NULLIF(SQRT(a.n),0))::numeric,3)
                                                     AS ci_high,
    CASE
        WHEN a.n >= 100
             AND (a.e - 1.96*a.sd/NULLIF(SQRT(a.n),0)) > 0
             THEN 'proven'
        WHEN a.n >= 30 AND a.e > 0 THEN 'promising'
        ELSE 'unproven'
    END                                              AS confidence,
    a.fs AS first_seen, a.ls AS last_seen
FROM agg a
LEFT JOIN ref_trig_atomic_rule r ON r.atomic_rule_id::text = a.rule_id;


-- -----------------------------------------------------
-- v_user_action_performance - YOUR decisions vs what the stock then did.
-- One row per DONE action in user_action_log, joined to the 5d/20d forward
-- return of the symbol from that date (same LEAD-over-drv_ma basis as the rule
-- outcomes). This is the personal feedback loop — distinct from the rule
-- scorecard. Empty until you start logging actions on the Actionable screen;
-- recent dates won't have a 20d return until 20 trading days pass.
-- NOTE: superseded later in this file (after v_unified_track_record) by TASK_71
-- to include inferred-from-position actions. This definition is a placeholder
-- that works on a fresh DB before drv_position_action exists.
DROP VIEW IF EXISTS v_user_action_performance CASCADE;
CREATE OR REPLACE VIEW v_user_action_performance AS
WITH px AS (
    SELECT tos_symbol, as_of_date, last_price,
           LEAD(last_price, 5)  OVER w AS p5,
           LEAD(last_price, 20) OVER w AS p20
    FROM drv_ma
    WHERE last_price IS NOT NULL
    WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
),
fwd AS (
    SELECT tos_symbol, as_of_date,
           CASE WHEN last_price > 0 AND p5  IS NOT NULL
                THEN (p5  - last_price) / last_price * 100 END AS fwd5,
           CASE WHEN last_price > 0 AND p20 IS NOT NULL
                THEN (p20 - last_price) / last_price * 100 END AS fwd20
    FROM px
)
SELECT u.id, u.acted_at, u.as_of_date,
       u.tos_symbol,
       u.user_action, u.consolidated_action,
       NULL::TEXT      AS change_type,
       NULL::NUMERIC   AS shares_delta,
       'rule'::TEXT    AS attribution,
       'manual'::TEXT  AS source_kind,
       NULL::JSONB     AS attributed_rule_ids,
       ROUND(f.fwd5::numeric, 2)                   AS fwd_5d_pct,
       ROUND(f.fwd20::numeric, 2)                  AS fwd_20d_pct
FROM user_action_log u
LEFT JOIN fwd f
       ON f.tos_symbol = u.tos_symbol
      AND f.as_of_date = u.as_of_date
WHERE u.user_action = 'DONE';



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

            COALESCE(p_to,   (SELECT MAX(as_of_date) FROM drv_rule_outcome), CURRENT_DATE) AS hi,

            COALESCE(p_from, COALESCE((SELECT MAX(as_of_date) FROM drv_rule_outcome), CURRENT_DATE) - (p_window_days || ' days')::interval) AS lo

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

-- (drv_ssl/drv_sss cleanup policies omitted: drv_ssl retired by migration 28; drv_sss retired 2026-06-13.)

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

-- (Entries for retired tables drv_ssl/drv_sss/drv_etf/drv_call/drv_ii/drv_ps

--  and the drv_cat_* sweep are intentionally omitted.)

-- -----------------------------------------------------

INSERT INTO ref_data_filter_logic (table_name, filter_type, date_column, window_days, description) VALUES

    ('hist_y',             'EXACT_MATCH',         'snapshot_date', NULL, 'Yahoo quote snapshot - one row per day'),

    ('hist_tl',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Latest intra-day quotes'),

    ('hist_td',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Daily snapshot'),

    ('hist_tw',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Weekly snapshot'),

    ('drv_td',             'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_td'),

    ('drv_tw',             'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_tw'),

    ('hist_to',            'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Other / fundamentals - exact date match'),

    ('hist_rr',            'EXACT_MATCH',         'snapshot_date', NULL, 'Risk Range - weekly update'),

    ('hist_f',             'EXACT_MATCH',         'snapshot_date', NULL, 'Fidelity holdings'),

    ('hist_cs',            'EXACT_MATCH',         'snapshot_date', NULL, 'Schwab holdings'),

    ('hist_etf',           'EXACT_MATCH',         'snapshot_date', NULL, 'ETF entries'),

    ('hist_ii',            'EXACT_MATCH',         'snapshot_date', NULL, 'Investment Ideas'),

    ('hist_ps',            'EXACT_MATCH',         'snapshot_date', NULL, 'Price Strength Rank'),

    ('hist_sss',           'EXACT_MATCH',         'snapshot_date', NULL, 'Signal Strength Summary'),

    ('hist_psrk',          'EXACT_MATCH',         'snapshot_date', NULL, 'Price Strength Rank (PSRK format)'),

    ('hist_etfchg',        'LATEST_BEFORE',       'event_date',    NULL, 'ETF change events'),

    ('hist_iichg',         'LATEST_BEFORE',       'event_date',    NULL, 'II change events'),

    ('hist_call',          'EXACT_MATCH',         'snapshot_date', NULL, 'Manual call sheet - exact date match'),

    ('drv_source_standing','EXACT_MATCH',         'as_of_date',    NULL, 'Canonical per-source standing layer'),

    ('drv_outlook_action',   'EXACT_MATCH',         'as_of_date',    NULL, 'Per-source action per (date, symbol)'),

    ('drv_actionable',       'EXACT_MATCH',         'as_of_date',    NULL, 'Unified actionable decision per (date, symbol)'),

    ('user_action_log',      'LATEST_ON_OR_BEFORE', 'as_of_date',    NULL, 'User decisions; latest per snapshot'),

    ('hist_cst', 'WINDOW_30_DAYS',      'trade_date',    30,   'Schwab transaction history - rolling 30 days'),

    ('hist_ft',  'WINDOW_365_DAYS',     'trade_date',    365,  'Fidelity transaction history - rolling 1 year (extend as needed)'),

    ('drv_cs_realized_gain', 'EXACT_MATCH',         'as_of_date',    NULL, 'Realized P&L from Schwab sales')

ON CONFLICT (table_name) DO UPDATE SET filter_type = EXCLUDED.filter_type, description = EXCLUDED.description;





-- -----------------------------------------------------

-- 2026-05-27 cleanup: drop legacy "!..."-quoted duplicate columns in

-- drv_cat_atomic_input.  Each had a not_X twin already declared above;

-- the "!..." form was the original Excel header convention.  Idempotent.

-- -----------------------------------------------------

ALTER TABLE drv_cat_atomic_input

    DROP COLUMN IF EXISTS "!trade_rule",

    DROP COLUMN IF EXISTS "!trend_rule",

    DROP COLUMN IF EXISTS "!trtn_relation",

    DROP COLUMN IF EXISTS "!perf1d_sd",

    DROP COLUMN IF EXISTS "!perf_sd_rule",

    DROP COLUMN IF EXISTS "!perf3d_rule",

    DROP COLUMN IF EXISTS "!overbought",

    DROP COLUMN IF EXISTS "!3wk_ol",

    DROP COLUMN IF EXISTS "!3wk_ol_days",

    DROP COLUMN IF EXISTS "!bull",

    DROP COLUMN IF EXISTS "!perforbull";



-- -----------------------------------------------------

-- 2026-05-27: targets for MA-tab rule columns QE, QJ, QM, QN, QR.

-- drv_tn_td_bb_rr: Action/lookup columns computed by _derive_trend_trade_rules_impl
-- and PARM_LOOKUP_SQL.  Separated from drv_cat_atomic_input (which holds atomic
-- rule inputs JF..NP) to keep the two concerns distinct.
-- PK: (as_of_date, tos_symbol) — same pattern as all drv_* tables.

CREATE TABLE IF NOT EXISTS drv_tn_td_bb_rr (
    as_of_date             DATE    NOT NULL,
    tos_symbol             TEXT    NOT NULL,
    -- QE–QN computed by _derive_trend_trade_rules_impl Pass 1
    trend_trade_rule       INTEGER,          -- QE  CASE on trend_sd/trade_sd (1-4)
    a_bb_top_slope         NUMERIC,          -- QH  hist_td.a_bb_top_slope
    a_bb_bot_slope         NUMERIC,          -- QI  hist_td.a_bb_bot_slope
    bb_rng_strk_rule       NUMERIC,          -- QJ  BBRngStrkRule
    bull_rr_action         NUMERIC,          -- QM  BullRiskRng-Action
    not_bull_rr_action     NUMERIC,          -- QN  !BullRiskRng-Action
    -- QR computed by _derive_trend_trade_rules_impl Pass 2
    td_tn_bb_rr_action     NUMERIC,          -- QR  combined TD/TN/BB/RR action code
    -- QF/QG/QK/QL/QO-QR/QS/QT computed by PARM_LOOKUP_SQL
    tn_td_rule_action      NUMERIC,          -- QF  XLOOKUP(QE, tn_td_rule -> seq)
    tn_td_rule_desc        TEXT,             -- QG  XLOOKUP(QE, tn_td_rule -> desc)
    bb_rng_strk_action     NUMERIC,          -- QK  XLOOKUP(QJ, bb_range -> seq)
    bb_rng_strk_desc       TEXT,             -- QL  XLOOKUP(QJ, bb_range -> desc)
    risk_rng_longs_action  NUMERIC,          -- QO  conditional via QJ/QM/QN
    rr_bull_bear           TEXT,             -- QP  'B' / '!B'
    rr_desc                TEXT,             -- QQ  lookup description
    td_tn_bb_action_desc   TEXT,             -- QS  XLOOKUP(QR, td_tn_bb_rr_action -> desc)
    td_tn_bb_action_seq    NUMERIC,          -- QT  XLOOKUP(QR, td_tn_bb_rr_action -> seq)
    computed_at            TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id          BIGINT,
    PRIMARY KEY (as_of_date, tos_symbol)
);

-- Drop the same columns from drv_cat_atomic_input (they now live in drv_tn_td_bb_rr)
ALTER TABLE IF EXISTS drv_cat_atomic_input
    DROP COLUMN IF EXISTS bb_rng_strk_rule,
    DROP COLUMN IF EXISTS bull_rr_action,
    DROP COLUMN IF EXISTS not_bull_rr_action,
    DROP COLUMN IF EXISTS td_tn_bb_rr_action;



-- -----------------------------------------------------

-- 2026-05-27 (v2): JF–NP / QE–QT columns populated by the new

-- etl/derive_cat_atomic_input.py module.  See docs/drv_cat_atomic_input_logic.md.

-- Adds QH/QI (raw hist_td slopes, exposed for trace) and the seven QE–QT tail

-- Parm-lookup columns (action codes + descriptions + seq).  Idempotent.

-- -----------------------------------------------------

-- All QE-QT columns now live in drv_tn_td_bb_rr (see above).
-- Drop them from drv_cat_atomic_input if still present from older migrations.
ALTER TABLE IF EXISTS drv_cat_atomic_input
    DROP COLUMN IF EXISTS trend_trade_rule,
    DROP COLUMN IF EXISTS a_bb_bot_slope,
    DROP COLUMN IF EXISTS a_bb_top_slope,
    DROP COLUMN IF EXISTS tn_td_rule_action,
    DROP COLUMN IF EXISTS tn_td_rule_desc,
    DROP COLUMN IF EXISTS bb_rng_strk_action,
    DROP COLUMN IF EXISTS bb_rng_strk_desc,
    DROP COLUMN IF EXISTS risk_rng_longs_action,
    DROP COLUMN IF EXISTS rr_bull_bear,
    DROP COLUMN IF EXISTS rr_desc,
    DROP COLUMN IF EXISTS td_tn_bb_action_desc,
    DROP COLUMN IF EXISTS td_tn_bb_action_seq;



-- -----------------------------------------------------

-- 2026-05-27 (v2): REMOVED — bb_bot_prev/bb_top_prev no longer loaded from hist_td.

-- They're now computed in derive_cat_atomic_input from prior snapshot's a_bb_bottom/a_bb_top.

-- The ALTER TABLE that added these columns to hist_td has been removed; they're only in

-- drv_cat_atomic_input as derived output.



-- 2026-05-28: Drop bb_bot_prev/bb_top_prev from drv_td (they're moved to drv_cat_atomic_input

-- via derive_cat_atomic_input computation). drv_td no longer needs to store them.

ALTER TABLE IF EXISTS drv_td DROP COLUMN IF EXISTS bb_bot_prev;

ALTER TABLE IF EXISTS drv_td DROP COLUMN IF EXISTS bb_top_prev;



-- 2026-05-27 (v3): dashboard single-cell scalars seeded into ref_param

-- under sheet='dash'.  Pattern lets future derivers read scalars by name

-- via `SELECT value FROM ref_param WHERE sheet='dash' AND param_name=...`.

-- Covers Excel cells like Dash!$AB$24 (intraday-vs-daily toggle).

-- See docs/drv_cat_atomic_input_logic.md § Dashboard scalars.

-- Idempotent via ON CONFLICT DO NOTHING.

-- -----------------------------------------------------

INSERT INTO ref_param (sheet, param_name, value) VALUES

    ('dash', 'intraday_toggle', 'Y')           -- Dash!$AB$24: 'Y' = use intraday DG/DK/DL,

                                               -- 'N' = use daily CY/DC/DD.

ON CONFLICT (sheet, param_name) DO NOTHING;



-- 2026-05-28: Add tos_symbol to all hist_* tables for symbol normalization

-- Maps each table's symbol to TOS/thinkOrSwim symbol via RRT (ref_rrt).

-- COALESCE(tos_symbol, symbol) used throughout derive layer for consistency.

-- =====================================================

ALTER TABLE IF EXISTS hist_tl  ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_td  ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_tw  ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_to  ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_call ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_etf ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_ii  ADD COLUMN IF NOT EXISTS tos_symbol TEXT;

ALTER TABLE IF EXISTS hist_sss ADD COLUMN IF NOT EXISTS tos_symbol TEXT;



CREATE INDEX IF NOT EXISTS ix_hist_tl_tos_symbol ON hist_tl(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_tw_tos_symbol ON hist_tw(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_to_tos_symbol ON hist_to(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_call_tos_symbol ON hist_call(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_etf_tos_symbol ON hist_etf(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_ii_tos_symbol ON hist_ii(tos_symbol, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_hist_sss_tos_symbol ON hist_sss(tos_symbol, snapshot_date);



-- =====================================================

-- End of baseline.sql

-- =====================================================







-- =====================================================
-- drv_ma decomposition: 5 component tables (2026-05-31)
-- drv_ma TABLE is replaced by a compatibility VIEW below.
-- =====================================================

-- -----------------------------------------------------
-- drv_symbols — master ticker universe for a date
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_symbols (
    as_of_date   DATE NOT NULL,
    tos_symbol   TEXT NOT NULL,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_symbols_tos_symbol
    ON drv_symbols(tos_symbol, as_of_date);

-- -----------------------------------------------------
-- drv_technicals — price, technicals, MACD, SMAs
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_technicals (
    as_of_date        DATE    NOT NULL,
    tos_symbol        TEXT    NOT NULL,
    description       TEXT,
    sector            TEXT,
    asset_class       TEXT,
    sub_asset_class   TEXT,
    equity_sector     TEXT,
    tl_date           DATE,
    last_price        NUMERIC,
    rsi               NUMERIC,
    imp_volatility    NUMERIC,
    volume            BIGINT,
    vlm_projected     NUMERIC,
    td_date           DATE,
    iv_percentile     NUMERIC,
    hv_percentile     NUMERIC,
    range_compression NUMERIC,
    d_iv_to_hv        NUMERIC,
    d_vlt_caution     TEXT,
    a_trend_value     NUMERIC,
    a_trade_value     NUMERIC,
    a_bb_top          NUMERIC,
    a_bb_bottom       NUMERIC,
    a_bb_streak       NUMERIC,
    tw_date           DATE,
    a_macd_brr        NUMERIC,
    a_macdh_d_brr     NUMERIC,
    earnings_days     NUMERIC,
    sma_20            NUMERIC,
    sma_50            NUMERIC,
    sma_200           NUMERIC,
    source_run_id     BIGINT,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_technicals_tos_symbol
    ON drv_technicals(tos_symbol, as_of_date);

-- -----------------------------------------------------
-- drv_fundamentals — fundamental data
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_fundamentals (
    as_of_date    DATE    NOT NULL,
    tos_symbol    TEXT    NOT NULL,
    market_cap_str TEXT,
    beta          NUMERIC,
    pe_ratio      NUMERIC,
    eps           NUMERIC,
    div_yield     NUMERIC,
    source_run_id BIGINT,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_fundamentals_tos_symbol
    ON drv_fundamentals(tos_symbol, as_of_date);

-- -----------------------------------------------------
-- drv_outlooks — all outlook source signals
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_outlooks (
    as_of_date      DATE    NOT NULL,
    tos_symbol      TEXT    NOT NULL,
    rr_date         DATE,
    rr_buy_trade    NUMERIC,
    rr_sell_trade   NUMERIC,
    rr_outlook      TEXT,
    call_outlook    TEXT,
    call_modifier   TEXT,
    call_weight     NUMERIC,
    etf_outlook     TEXT,
    etf_brr         NUMERIC,
    etf_trr         NUMERIC,
    ii_outlook      TEXT,
    ii_weight       NUMERIC,
    SSS_signal      NUMERIC,
    SSS_signal_sign NUMERIC,
    SSS_rank_hl     NUMERIC,
    pct_brr         NUMERIC,
    source_run_id   BIGINT,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_outlooks_tos_symbol
    ON drv_outlooks(tos_symbol, as_of_date);

-- -----------------------------------------------------
-- drv_portfolio — holdings snapshot
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_portfolio (
    as_of_date    DATE    NOT NULL,
    tos_symbol    TEXT    NOT NULL,
    held_qty_fid  NUMERIC,
    held_qty_cs   NUMERIC,
    source_run_id BIGINT,
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_portfolio_tos_symbol
    ON drv_portfolio(tos_symbol, as_of_date);

-- =====================================================
-- Migrate drv_ma from TABLE to VIEW (2026-05-31)
-- On existing DBs: drops the old wide table and
-- replaces it with a JOIN view over the 5 components.
-- On fresh installs: the CREATE TABLE above already
-- ran; this DO block converts it to the view.
-- =====================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'drv_ma' AND c.relkind = 'r'
          AND n.nspname = 'public'
    ) THEN
        DROP TABLE drv_ma CASCADE;
    END IF;
END$$;

CREATE OR REPLACE VIEW drv_ma AS
SELECT
    s.as_of_date,
    s.tos_symbol,
    t.description,
    t.sector,
    t.asset_class,
    t.sub_asset_class,
    t.equity_sector,
    t.tl_date,
    t.last_price,
    t.rsi,
    t.imp_volatility,
    t.volume,
    t.vlm_projected,
    t.td_date,
    t.iv_percentile,
    t.hv_percentile,
    t.range_compression,
    t.d_iv_to_hv,
    t.d_vlt_caution,
    t.a_trend_value,
    t.a_trade_value,
    t.a_bb_top,
    t.a_bb_bottom,
    t.a_bb_streak,
    t.tw_date,
    t.a_macd_brr,
    t.a_macdh_d_brr,
    t.earnings_days,
    t.sma_20,
    t.sma_50,
    t.sma_200,
    f.market_cap_str,
    f.beta,
    f.pe_ratio,
    f.eps,
    f.div_yield,
    o.rr_date,
    o.rr_buy_trade,
    o.rr_sell_trade,
    o.rr_outlook,
    NULL::NUMERIC AS rr_brr,
    o.call_outlook,
    o.call_modifier,
    o.call_weight,
    o.etf_outlook,
    o.etf_brr,
    o.etf_trr,
    o.ii_outlook,
    o.ii_weight,
    o.SSS_signal,
    o.SSS_signal_sign,
    o.SSS_rank_hl,
    p.held_qty_fid,
    p.held_qty_cs,
    o.pct_brr,
    NULL::NUMERIC AS macdh_direction,
    NULL::NUMERIC AS macd_direction,
    NULL::NUMERIC AS bb_direction,
    NULL::NUMERIC AS bbthresh_crossover,
    NULL::NUMERIC AS trade_cross_over,
    NULL::NUMERIC AS trade_rule,
    NULL::NUMERIC AS trend_cross_over,
    NULL::NUMERIC AS trend_rule,
    NULL::NUMERIC AS trend_trade_dep_rule,
    NULL::NUMERIC AS trade_trend_relation,
    NULL::NUMERIC AS trade_trend_relation_neg,
    NULL::NUMERIC AS brr_pct_dir,
    NULL::NUMERIC AS trend_below_trr,
    NULL::NUMERIC AS lrr_above_trade,
    NULL::NUMERIC AS ivrule,
    NULL::NUMERIC AS three_m_long,
    NULL::NUMERIC AS perf1d_sd_neg,
    NULL::NUMERIC AS perf_sd_rule,
    NULL::NUMERIC AS perf_sd_rule_neg,
    NULL::NUMERIC AS perf3d_rule_neg,
    NULL::NUMERIC AS bb_bull_rule,
    NULL::NUMERIC AS bb_bull_puts,
    NULL::NUMERIC AS macd_and_h_rule,
    NULL::NUMERIC AS macd_and_h_rule_puts,
    NULL::NUMERIC AS overbought_neg,
    NULL::NUMERIC AS outlook_3wk_neg,
    NULL::NUMERIC AS outlook_3wk_days_neg,
    NULL::NUMERIC AS bull_rule,
    NULL::NUMERIC AS bull_rule_neg,
    NULL::NUMERIC AS perfourbull_rule,
    NULL::NUMERIC AS perfourbull_rule_neg,
    NULL::NUMERIC AS dma_50_crossover,
    NULL::NUMERIC AS dma_200_crossover,
    NULL::NUMERIC AS trade_close_to_brr,
    NULL::NUMERIC AS trade_close_to_trr,
    NULL::NUMERIC AS up_resistance,
    NULL::NUMERIC AS down_resistance,
    NULL::NUMERIC AS vs_lt_outlook_rule,
    NULL::NUMERIC AS short_term_outlook_bullish,
    NULL::NUMERIC AS short_term_outlook_bearish,
    NULL::NUMERIC AS overbought,
    NULL::TIMESTAMP AS computed_at,
    NULL::BIGINT AS source_run_id
FROM drv_symbols s
LEFT JOIN drv_technicals  t USING (as_of_date, tos_symbol)
LEFT JOIN drv_fundamentals f USING (as_of_date, tos_symbol)
LEFT JOIN drv_outlooks    o USING (as_of_date, tos_symbol)
LEFT JOIN drv_portfolio   p USING (as_of_date, tos_symbol);


-- =====================================================
-- MACRO FEED (FRED) — 2026-06-07
-- Economic data + EOD index levels pulled from the St. Louis Fed
-- FRED API (etl/fetch_macro.py). Independent of the per-symbol
-- derive pipeline (no tos_symbol / anchor machinery). Complements the
-- workbook-sourced ref_econ_indicator / ref_calendar_event (which hold
-- *which* events + expected values); this holds *observed* time series.
-- See docs/macro_feed_logic.md.
-- =====================================================

-- ref_macro_series — tunable catalog: which FRED series to pull + how to show.
-- Refresh labels/groups by editing db/seeds_macro.sql then `python -m db.init_db`.
CREATE TABLE IF NOT EXISTS ref_macro_series (
    series_id   TEXT PRIMARY KEY,                 -- FRED series id, e.g. DGS10
    label       TEXT NOT NULL,                    -- display label, e.g. "10Y Treasury"
    grp         TEXT NOT NULL,                    -- rates|inflation|jobs|risk|index|fx_cmdty
    unit        TEXT,                             -- display unit hint: %, index, $, k
    sort_order  INTEGER NOT NULL DEFAULT 100,     -- order within group
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_at   TIMESTAMP NOT NULL DEFAULT now()
);

-- hist_macro — raw observations, append-only (convention 1: ON CONFLICT DO NOTHING).
-- One row per (series_id, obs_date). value NULL when FRED reports "." (no data).
CREATE TABLE IF NOT EXISTS hist_macro (
    series_id   TEXT NOT NULL,
    obs_date    DATE NOT NULL,
    value       DOUBLE PRECISION,
    source      TEXT NOT NULL DEFAULT 'FRED',
    fetched_at  TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);
CREATE INDEX IF NOT EXISTS ix_hist_macro_date ON hist_macro(obs_date);

-- v_macro_latest — latest + prior non-null observation per enabled series,
-- with absolute and percent change. Consumed by GET /api/macro.
CREATE OR REPLACE VIEW v_macro_latest AS
WITH ranked AS (
    SELECT h.series_id, h.obs_date, h.value,
           ROW_NUMBER() OVER (PARTITION BY h.series_id
                              ORDER BY h.obs_date DESC) AS rn
    FROM hist_macro h
    WHERE h.value IS NOT NULL
)
SELECT s.series_id,
       s.label,
       s.grp,
       s.unit,
       s.sort_order,
       cur.value     AS latest_value,
       cur.obs_date  AS latest_date,
       prv.value     AS prior_value,
       prv.obs_date  AS prior_date,
       (cur.value - prv.value) AS chg_abs,
       CASE WHEN prv.value IS NULL OR prv.value = 0 THEN NULL
            ELSE (cur.value - prv.value) / abs(prv.value) * 100.0
       END AS chg_pct
FROM ref_macro_series s
LEFT JOIN ranked cur ON cur.series_id = s.series_id AND cur.rn = 1
LEFT JOIN ranked prv ON prv.series_id = s.series_id AND prv.rn = 2
WHERE s.enabled
ORDER BY s.grp, s.sort_order, s.series_id;

-- meta_macro_fetch — one row per real FRED fetch run (skipped/throttled runs are
-- NOT logged). Drives the fetch throttle (etl/fetch_macro.py refuses to call
-- FRED if the last run started within the throttle window) and the "last
-- fetched" stamp shown next to the manual Refresh button.
CREATE TABLE IF NOT EXISTS meta_macro_fetch (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    trigger       TEXT NOT NULL DEFAULT 'cli',   -- cli | api | scheduler
    status        TEXT NOT NULL,                 -- ok | partial | error
    series_ok     INTEGER NOT NULL DEFAULT 0,
    series_failed INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS ix_meta_macro_fetch_started
    ON meta_macro_fetch(started_at DESC);

-- =====================================================
-- ECON CALENDAR FEED (FRED release/dates) — 2026-07-02
-- Upcoming economic release *dates* pulled from FRED's release/dates API
-- (etl/fetch_econ_calendar.py). Complements the FRED value pull above (this
-- is *when*, not *what value*) and the workbook-sourced ref_calendar_event /
-- ref_econ_indicator loaders (etl/load_raw.py) — writes into the SAME
-- ref_calendar_event table (ON CONFLICT DO NOTHING on its (category,
-- event_date) PK), so both sources coexist harmlessly. Not every category in
-- ref_calendar_event has a FRED release_id (e.g. ISM, Michigan Consumer
-- Sentiment, NAHB, Fed Meeting/FOMC/Beige Book aren't in FRED's release
-- catalog) — those stay workbook-only. See ref_econ_release for the mapping.
-- =====================================================

-- ref_econ_release — tunable catalog: which FRED release_id maps to which
-- ref_calendar_event.category name(s). One release_id can cover several
-- categories that publish on the same date (e.g. release_id 10 = Consumer
-- Price Index covers "CPI YOY", "CPI MoM", "CPI Core YoY", "CPI Core MoM").
-- Add/remove rows here + `python -m db.init_db` — no code change needed.
CREATE TABLE IF NOT EXISTS ref_econ_release (
    release_id    INTEGER NOT NULL,        -- FRED release_id, e.g. 10 = Consumer Price Index
    category      TEXT NOT NULL,           -- ref_calendar_event.category to write
    release_name  TEXT,                    -- FRED release name, for reference/debugging
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_at     TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, category)
);

-- meta_econ_calendar_fetch — one row per real FRED release/dates fetch run
-- (skipped/throttled runs are NOT logged). Drives the fetch throttle
-- (etl/fetch_econ_calendar.py) and the "last fetched" stamp in File Monitor.
CREATE TABLE IF NOT EXISTS meta_econ_calendar_fetch (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMP NOT NULL DEFAULT now(),
    finished_at     TIMESTAMP,
    trigger         TEXT NOT NULL DEFAULT 'cli',   -- cli | api | scheduler
    status          TEXT NOT NULL,                 -- ok | partial | error
    releases_ok     INTEGER NOT NULL DEFAULT 0,
    releases_failed INTEGER NOT NULL DEFAULT 0,
    rows_inserted   INTEGER NOT NULL DEFAULT 0,
    note            TEXT
);
CREATE INDEX IF NOT EXISTS ix_meta_econ_calendar_fetch_started
    ON meta_econ_calendar_fetch(started_at DESC);

-- =====================================================
-- ref_market_metric — metric registry for the market tape
-- Source-agnostic: each row carries an ordered source_priority JSONB array
-- ("adapter:symbol" strings) so the resolver tries each left-to-right.
-- Seeded by db/seeds_market_metric.sql (applied by db/init_db.py).
-- =====================================================
-- =====================================================
-- cache_yahoo_quote — rolling Yahoo Finance quote cache (one row per symbol)
-- =====================================================
CREATE TABLE IF NOT EXISTS cache_yahoo_quote (
    tos_symbol         TEXT NOT NULL,
    y_ticker           TEXT NOT NULL,
    open_price         NUMERIC,
    high_price         NUMERIC,
    low_price          NUMERIC,
    last_price         NUMERIC,
    prev_close         NUMERIC,
    volume             BIGINT,
    fetched_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetch_status       TEXT DEFAULT 'ok',
    -- detail columns populated by after-market fetch_y_detail()
    company_name       TEXT,
    short_ratio        NUMERIC,
    float_shares       BIGINT,
    shares_outstanding BIGINT,
    detail_fetched_at  TIMESTAMPTZ,
    -- ref_sector gap-filling (TASK: quad-factor data-completeness audit) —
    -- same .info payload fetch_y_detail() already makes; just reading 3 more
    -- fields off it. Suggested values only — never auto-written to ref_sector.
    quote_type         TEXT,  -- Yahoo quoteType: EQUITY/ETF/INDEX/MUTUALFUND/...
    y_sector           TEXT,  -- Yahoo's own sector taxonomy (not ref_quad_outlook's)
    y_industry         TEXT,
    PRIMARY KEY (tos_symbol)
);
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS short_ratio NUMERIC;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS float_shares BIGINT;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS shares_outstanding BIGINT;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS detail_fetched_at TIMESTAMPTZ;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS quote_type TEXT;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS y_sector TEXT;
ALTER TABLE cache_yahoo_quote ADD COLUMN IF NOT EXISTS y_industry TEXT;

INSERT INTO ref_settings (setting_name, setting_value)
VALUES ('yahoo_fetch_interval_sec', '300')
ON CONFLICT (setting_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS ref_market_metric (
    metric_key      TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    grp             TEXT NOT NULL,
    source_priority JSONB NOT NULL DEFAULT '[]'::JSONB,
    value_format    TEXT NOT NULL DEFAULT 'price',
    sort_order      INT  NOT NULL DEFAULT 0,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2026-06-10 Task 6: hold-out validation columns on ref_trig_param_set.
-- train_edge / holdout_edge: mean fwd return on the respective split.
-- holdout_n: number of observations in the hold-out set.
-- validated: TRUE once a hold-out run has been performed.
ALTER TABLE IF EXISTS ref_trig_param_set
ADD COLUMN IF NOT EXISTS train_edge NUMERIC;

ALTER TABLE IF EXISTS ref_trig_param_set
ADD COLUMN IF NOT EXISTS holdout_edge NUMERIC;

ALTER TABLE IF EXISTS ref_trig_param_set
ADD COLUMN IF NOT EXISTS holdout_n INTEGER;

ALTER TABLE IF EXISTS ref_trig_param_set
ADD COLUMN IF NOT EXISTS validated BOOLEAN NOT NULL DEFAULT FALSE;

-- 2026-06-10 Task 8: stop_level on drv_actionable.
-- Computed from stop_mode ref_settings knob:
--   'trade_line_or_pct': MAX(a_trade_value, last_price * (1 - stop_pct))
-- Default stop_pct = 0.08 (8%). Both knobs editable via /ref screen.
ALTER TABLE IF EXISTS drv_actionable
ADD COLUMN IF NOT EXISTS stop_level NUMERIC;

INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('stop_mode', 'trade_line_or_pct',
     'Stop-loss computation mode: trade_line_or_pct = MAX(a_trade_value, price*(1-stop_pct))'),
    ('stop_pct',  '0.08',
     'Percentage below current price for the pct-floor leg of stop_level (default 8%)')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-10 Task 4: live pct_brr / zone / distances on drv_quote.
-- Computed from EOD a_trend_value/a_trade_value (drv_technicals) + live last_price.
-- is_intraday=TRUE when the quote is fresher than the anchor export_date.
ALTER TABLE IF EXISTS drv_quote ADD COLUMN IF NOT EXISTS pct_brr NUMERIC;
ALTER TABLE IF EXISTS drv_quote ADD COLUMN IF NOT EXISTS zone_signal TEXT;
ALTER TABLE IF EXISTS drv_quote ADD COLUMN IF NOT EXISTS dist_to_trend NUMERIC;
ALTER TABLE IF EXISTS drv_quote ADD COLUMN IF NOT EXISTS dist_to_trade NUMERIC;
ALTER TABLE IF EXISTS drv_quote ADD COLUMN IF NOT EXISTS is_intraday BOOLEAN;

-- 2026-06-10 Task 3: cascade_status on meta_derived_run.
-- Added to the existing table (no new table needed). Set only on the summary row
-- target_table='_cascade'; individual step rows leave it NULL.
-- Values: SUCCESS | PARTIAL | FAILED
ALTER TABLE IF EXISTS meta_derived_run
ADD COLUMN IF NOT EXISTS cascade_status TEXT;

-- -----------------------------------------------------
-- ref_vol_threshold — volatility regime thresholds
-- Below low  → Investable | low–high → Chop | above high → Not Investable
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_vol_threshold (
    tos_symbol  TEXT    PRIMARY KEY,
    low         NUMERIC NOT NULL,
    high        NUMERIC NOT NULL
);

-- 2026-06-17 TASK_54: canonical cash-detection function.
-- Encodes the union of F_IS_CASH + CS_IS_CASH rules in one place.
-- Used by portfolio/holdings queries to emit is_cash per row.
CREATE OR REPLACE FUNCTION is_cash(
    p_symbol       TEXT,
    p_security_type TEXT,
    p_description  TEXT
) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT (
        COALESCE(p_symbol, '') = 'SPAXX**'
        OR UPPER(COALESCE(p_symbol, '')) = 'PENDING ACTIVITY'
        OR UPPER(COALESCE(p_description, '')) LIKE '%HELD IN MONEY MARKET%'
        OR COALESCE(p_symbol, '') = 'Cash & Cash Investments'
        OR COALESCE(p_security_type, '') = 'Cash and Money Market'
    )
$$;

-- 2026-06-17 TASK_53: final_call columns on drv_actionable.
-- Persists the JS finalCall() decision tree result at derive time so the
-- browser reads pre-computed values instead of recomputing them.
-- final_action: plain-English label  (e.g. "SELL ALL", "BUY MORE")
-- final_code:   BuySell code         (e.g. "SA", "BM", "BS", "HOLD")
-- final_side:   'sell' | 'buy' | 'neutral'
-- fc_strength:  numeric strength (-3 .. +2)
-- fc_confidence:'high' | 'gate' | 'mixed' | 'none'
-- fc_feasible:  TRUE when an actionable recommendation exists
-- priority_rank: sort key (buysell seq * 1e6 + amt_dollars)
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS final_action    TEXT;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS final_code      TEXT;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS final_side      TEXT;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS fc_strength     NUMERIC;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS fc_confidence   TEXT;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS fc_feasible     BOOLEAN;
ALTER TABLE IF EXISTS drv_actionable ADD COLUMN IF NOT EXISTS priority_rank   NUMERIC;

-- 2026-06-17 TASK_57: category-totals snapshot.
-- Derived once per date from drv_actionable; /api/briefing reads it directly.
CREATE TABLE IF NOT EXISTS drv_category_totals (
    as_of_date        DATE    NOT NULL,
    position_category TEXT    NOT NULL,
    total_dollar      NUMERIC,
    drift_band        TEXT,   -- 'BELOW_MIN' | 'WITHIN' | 'ABOVE_MAX'
    PRIMARY KEY (as_of_date, position_category)
);

-- TASK_55: per-symbol rule-trace snapshot written at derive time by
-- _derive_stks_impl.  API endpoints (/api/trace, /api/rule-flow) read this
-- table instead of re-running ETL evaluation logic at request time.
-- payload JSONB: { atomics, composites, rule_groups }
CREATE TABLE IF NOT EXISTS drv_trace (
    as_of_date   DATE NOT NULL,
    tos_symbol   TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    derived_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, tos_symbol)
);

-- 2026-06-20 TASK_64: sd_median_window_days — rolling window for the true
-- percentile_cont(0.5) median of hist_tw.standard_dev used as AC denominator.
-- Both the Python engine (derive_cat_atomic_input) and the SQL twin
-- (_derive_trend_trade_rules_impl in derive.py) read this key at derive time.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('sd_median_window_days', '30',
     'Trailing calendar-day window for computing the rolling median SD (AC denominator). '
     'Both Python and SQL twin engines use this value.')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-20 TASK_64 Fix 5: BB-slope thresholds and reverse-symbol RR scales.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('bb_slope_hi',          '3',   'BBRngStrkRule high threshold (±3): top/bottom slope >= this → score ±4'),
    ('bb_slope_lo',          '2',   'BBRngStrkRule low threshold (±2): top/bottom slope >= this → score ±3'),
    ('rr_reverse_scale',     '10',  'Reverse-symbol LRR/TRR multiplier (yield×10 → TOS display units)'),
    ('rr_reverse_mid_scale', '5',   'Reverse-symbol MRR multiplier ((buy+sell)×5 = midpoint in display units)')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-20 TASK_64 Fix 6: new volume output columns on drv_tw.
-- vlm_3m_pct  : GB value (((volume - avg_3m)/avg_3m)*100) — was computed but discarded.
-- vlm_desc    : human-readable label for the w_vlm_rule_desc code (GF in Excel, Parm!BS/BT).
-- vlm_action  : buy/accumulate/avoid tag per the Vlm_Action lookup (GG in Excel, Parm!BS/BU).
ALTER TABLE IF EXISTS drv_tw ADD COLUMN IF NOT EXISTS vlm_3m_pct  NUMERIC;
ALTER TABLE IF EXISTS drv_tw ADD COLUMN IF NOT EXISTS vlm_desc    TEXT;
ALTER TABLE IF EXISTS drv_tw ADD COLUMN IF NOT EXISTS vlm_action  TEXT;

-- 2026-06-20 TASK_66: calibrated bull-probability model.
-- ref_bull_model stores fitted logistic-regression coefficients (one active row).
-- Each row = one training run. Only the row with is_active=TRUE is used at
-- derive time. History rows (is_active=FALSE) are retained for audit.
CREATE TABLE IF NOT EXISTS ref_bull_model (
    model_id         SERIAL PRIMARY KEY,
    trained_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active        BOOLEAN     NOT NULL DEFAULT FALSE,
    feature_names    JSONB       NOT NULL DEFAULT '[]',
    coefficients     JSONB       NOT NULL DEFAULT '{}',
    intercept        NUMERIC     NOT NULL DEFAULT 0,
    train_from_date  DATE,
    train_to_date    DATE,
    holdout_from_date DATE,
    holdout_to_date  DATE,
    holdout_auc      NUMERIC,
    holdout_n        INTEGER,
    calibration_table JSONB,
    notes            TEXT
);

-- Only one active model at a time (partial unique index).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ref_bull_model_active
    ON ref_bull_model (is_active)
    WHERE is_active = TRUE;

-- bull_prob / bull_agreement columns on drv_actionable (Phase C output).
-- bull_prob: 0-1 logistic probability symbol is up 20 days from now.
-- bull_agreement: fraction of contributing signals pointing the same direction.
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS bull_prob       NUMERIC;
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS bull_agreement  NUMERIC;

-- 2026-06-20 TASK_67: revertible bull-gate threshold config.
-- ref_threshold_override holds per-rule-key the original (Excel-relic) value,
-- the latest data-fitted value, and which one is currently active.
-- original_value is written ONCE at seed time and never overwritten (convention #1).
-- active_source: 'original' (default) | 'calculated'
-- Reverting = set active_source='original' — no recompute, no data loss.
CREATE TABLE IF NOT EXISTS ref_threshold_override (
    rule_key         TEXT    PRIMARY KEY,
    description      TEXT,
    original_value   NUMERIC NOT NULL,
    calculated_value NUMERIC,
    active_source    TEXT    NOT NULL DEFAULT 'original'
                            CHECK (active_source IN ('original','calculated')),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ref_threshold_fit_history: every fitting run appended here.
-- holdout_metric: mean fwd_20d_pct on the holdout set at the calculated threshold.
-- n: number of hold-out observations used.
CREATE TABLE IF NOT EXISTS ref_threshold_fit_history (
    id             SERIAL PRIMARY KEY,
    rule_key       TEXT    NOT NULL
                           REFERENCES ref_threshold_override(rule_key)
                           ON DELETE CASCADE,
    fitted_value   NUMERIC NOT NULL,
    fit_date       DATE    NOT NULL DEFAULT CURRENT_DATE,
    train_start    DATE,
    train_end      DATE,
    holdout_metric NUMERIC,
    n              INTEGER,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_thresh_fit_hist_key
    ON ref_threshold_fit_history(rule_key, fit_date DESC);

-- Seed original bull-gate thresholds (write-once; ON CONFLICT DO NOTHING).
-- Keys match the Python code in _bull_expr / _bb_bull_rule_expr / _perforbull_expr
-- in etl/derive_cat_atomic_input.py.
-- Batch 1: _bull_expr bullish arm + bearish arm
INSERT INTO ref_threshold_override (rule_key, description, original_value) VALUES
('bull.pos_hi.JN', 'BULL top: trade_rule >= this', 3),
('bull.pos_hi.JQ', 'BULL top: trend_rule >= this', 2),
('bull.pos_hi.JV', 'BULL top: trade_trend_sd_rule >= this', 2),
('bull.pos_hi.LZ', 'BULL top: bblowdays >= this', 3),
('bull.pos_lo.JN', 'BULL mid: trade_rule >= this', 2),
('bull.pos_lo.JQ', 'BULL mid: trend_rule >= this', 2),
('bull.pos_lo.JV', 'BULL mid: trade_trend_sd_rule >= this', 2),
('bull.pos_lo.LZ', 'BULL mid: bblowdays >= this', 2),
('bull.neg_hi.JN', 'BULL bear top: trade_rule <= this', -3),
('bull.neg_hi.JQ', 'BULL bear top: trend_rule <= this', -2),
('bull.neg_hi.JV', 'BULL bear top: trade_trend_sd <= this', -2),
('bull.neg_hi.LY', 'BULL bear top: bbhighdays >= this', 3)
ON CONFLICT (rule_key) DO NOTHING;

-- Batch 2: _bull_expr bearish mid + perforbull + bb_bull
INSERT INTO ref_threshold_override (rule_key, description, original_value) VALUES
('bull.neg_lo.JN', 'BULL bear mid: trade_rule <= this', -2),
('bull.neg_lo.JQ', 'BULL bear mid: trend_rule <= this', -2),
('bull.neg_lo.JV', 'BULL bear mid: trade_trend_sd <= this', -2),
('bull.neg_lo.LY', 'BULL bear mid: bbhighdays >= this', 2),
('perforbull.hi', 'PerfOrBull: LK or MQ >= this gives 3', 3),
('perforbull.lo', 'PerfOrBull: LK or MQ <= neg-this gives -3', 3),
('bb_bull.hi.LP', 'BB Bull: bbstreak_rule >= this gives 3', 3),
('bb_bull.hi.LS', 'BB Bull: bbstreak_days_rule >= this gives 3', 3),
('bb_bull.lo.LP', 'BB Bull: bbstreak_rule <= neg-this gives -3', 3),
('bb_bull.lo.LS', 'BB Bull: bbstreak_days_rule <= neg-this gives -3', 3)
ON CONFLICT (rule_key) DO NOTHING;

-- 2026-06-20 TASK_71: drv_position_action — inferred trades from transaction history.
-- Source: hist_cst (Schwab) + hist_ft (Fidelity) — real Buy/Sell events with quantities.
-- change_type: BUY | ADD | REDUCE | SELL_ALL
-- attribution: 'rule' (matched drv_actionable recommendation) | 'discretionary'
-- attributed_rule_ids: JSONB array of matched triggered_group_ids or source_actions keys
-- source: 'cst' (Schwab) | 'ft' (Fidelity)
-- Idempotent: DELETE WHERE as_of_date=D then INSERT.
CREATE TABLE IF NOT EXISTS drv_position_action (
    as_of_date          DATE    NOT NULL,
    tos_symbol          TEXT    NOT NULL,
    trade_date          DATE    NOT NULL,
    change_type         TEXT    NOT NULL
        CHECK (change_type IN ('BUY','ADD','REDUCE','SELL_ALL')),
    shares_delta        NUMERIC NOT NULL,
    dollar_delta        NUMERIC,
    inferred_action_code TEXT,
    attributed_rule_ids JSONB,
    attribution         TEXT    NOT NULL DEFAULT 'discretionary'
        CHECK (attribution IN ('rule','discretionary')),
    source              TEXT    NOT NULL DEFAULT 'unknown',
    computed_at         TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol, trade_date, source, change_type)
);
CREATE INDEX IF NOT EXISTS ix_drv_position_action_date
    ON drv_position_action(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_position_action_sym
    ON drv_position_action(tos_symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_position_action_attr
    ON drv_position_action(attribution, as_of_date);

-- v_unified_track_record: positions-primary; manual user_action_log overrides.
-- For each (tos_symbol, as_of_date) prefer the manual row (if user_action='DONE')
-- else use the inferred drv_position_action row.
-- source_kind: 'manual' | 'inferred'
CREATE OR REPLACE VIEW v_unified_track_record AS
WITH manual AS (
    SELECT tos_symbol, as_of_date,
           id AS manual_id,
           consolidated_action,
           user_action,
           acted_at,
           NULL::TEXT             AS change_type,
           NULL::NUMERIC          AS shares_delta,
           NULL::NUMERIC          AS dollar_delta,
           NULL::TEXT             AS inferred_action_code,
           NULL::JSONB            AS attributed_rule_ids,
           'rule'::TEXT           AS attribution,
           'manual'::TEXT         AS source_kind
    FROM user_action_log
    WHERE user_action = 'DONE'
),
inferred AS (
    SELECT tos_symbol, as_of_date,
           NULL::BIGINT           AS manual_id,
           NULL::TEXT             AS consolidated_action,
           NULL::TEXT             AS user_action,
           computed_at            AS acted_at,
           change_type,
           shares_delta,
           dollar_delta,
           inferred_action_code,
           attributed_rule_ids,
           attribution,
           'inferred'::TEXT       AS source_kind
    FROM drv_position_action
    WHERE NOT EXISTS (
        SELECT 1 FROM user_action_log u2
        WHERE u2.tos_symbol = drv_position_action.tos_symbol
          AND u2.as_of_date = drv_position_action.as_of_date
          AND u2.user_action = 'DONE'
    )
)
SELECT * FROM manual
UNION ALL
SELECT * FROM inferred;

-- 2026-06-20 TASK_71 (supersedes earlier definition): unified personal track record.
-- Includes manual DONE entries (from user_action_log) AND inferred-from-positions.
-- source_kind='manual'|'inferred'; attribution='rule'|'discretionary'.
-- MUST be defined after drv_position_action and v_unified_track_record exist.
DROP VIEW IF EXISTS v_user_action_performance CASCADE;
CREATE OR REPLACE VIEW v_user_action_performance AS
WITH px AS (
    SELECT tos_symbol, as_of_date, last_price,
           LEAD(last_price, 5)  OVER w AS p5,
           LEAD(last_price, 20) OVER w AS p20
    FROM drv_ma
    WHERE last_price IS NOT NULL
    WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
),
fwd AS (
    SELECT tos_symbol, as_of_date,
           CASE WHEN last_price > 0 AND p5  IS NOT NULL
                THEN (p5  - last_price) / last_price * 100 END AS fwd5,
           CASE WHEN last_price > 0 AND p20 IS NOT NULL
                THEN (p20 - last_price) / last_price * 100 END AS fwd20
    FROM px
)
SELECT u.manual_id        AS id,
       u.acted_at,
       u.as_of_date,
       u.tos_symbol,
       u.user_action,
       COALESCE(u.consolidated_action,
                u.inferred_action_code) AS consolidated_action,
       u.change_type,
       u.shares_delta,
       u.attribution,
       u.source_kind,
       u.attributed_rule_ids,
       ROUND(f.fwd5::numeric, 2)       AS fwd_5d_pct,
       ROUND(f.fwd20::numeric, 2)      AS fwd_20d_pct
FROM v_unified_track_record u
LEFT JOIN fwd f
       ON f.tos_symbol = u.tos_symbol
      AND f.as_of_date = u.as_of_date;

-- 2026-06-20 TASK_69: agreement_class on drv_actionable.
-- Derived from bull_prob direction vs consolidated_action direction.
-- Buckets: agree_bull / agree_bear / split_tech_bull / split_tech_bear / neutral
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS agreement_class TEXT;

-- v_agreement_scorecard: forward-return efficacy per agreement_class bucket.
-- Uses drv_rule_outcome as the forward-return source (same as v_rule_scorecard).
-- Joins drv_actionable to drv_rule_outcome on (tos_symbol, as_of_date).
-- avg_fwd_5d / avg_fwd_20d: raw mean (no direction adjustment).
-- win_rate: fraction with fwd_20d_pct > 0.
-- confidence: proven n>=50 AND avg>0; promising n>=20 AND avg>0; else unproven.
DROP VIEW IF EXISTS v_agreement_scorecard;
CREATE VIEW v_agreement_scorecard AS
WITH joined AS (
    SELECT a.agreement_class,
           o.fwd_5d_pct,
           o.fwd_20d_pct,
           (o.fwd_20d_pct > 0) AS win
    FROM drv_actionable a
    JOIN drv_rule_outcome o
      ON o.tos_symbol = a.tos_symbol
     AND o.as_of_date = a.as_of_date
    WHERE a.agreement_class IS NOT NULL
      AND o.fwd_20d_pct     IS NOT NULL
),
agg AS (
    SELECT agreement_class,
           COUNT(*)             AS n,
           AVG(fwd_5d_pct)      AS e5,
           AVG(fwd_20d_pct)     AS e20,
           STDDEV_SAMP(fwd_20d_pct) AS sd20,
           AVG(win::int)        AS wr
    FROM joined GROUP BY agreement_class
)
SELECT agreement_class, n,
    ROUND(e5::numeric,  3) AS avg_fwd_5d,
    ROUND(e20::numeric, 3) AS avg_fwd_20d,
    ROUND(wr::numeric,  3) AS win_rate,
    ROUND((e20-1.96*sd20/NULLIF(SQRT(n),0))::numeric,3) AS ci_low,
    ROUND((e20+1.96*sd20/NULLIF(SQRT(n),0))::numeric,3) AS ci_high,
    CASE WHEN n>=50 AND e20>0 THEN 'proven'
         WHEN n>=20 AND e20>0 THEN 'promising'
         ELSE 'unproven' END AS confidence
FROM agg ORDER BY avg_fwd_20d DESC NULLS LAST;

-- 2026-06-20 TASK_70: calibrated Final Call columns on drv_actionable.
-- Derived from bull_prob via probability bands (parallel path, evaluation-only).
-- final_action_cal: plain-English label  (e.g. "SELL ALL", "BUY MORE")
-- final_code_cal:   BuySell code         (e.g. "SA", "BM")
-- final_side_cal:   'buy' | 'sell' | 'neutral'
-- fc_strength_cal:  numeric on same _FC_SCALE as fc_strength (-3..+2)
-- All NULL when no active bull model. Do NOT alter existing final_* columns.
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS final_action_cal  TEXT;
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS final_code_cal    TEXT;
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS final_side_cal    TEXT;
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS fc_strength_cal   NUMERIC;

-- 2026-06-21: drop unused m_outlook/m_score/q_outlook/q_score from ref_quad_outlook.
-- These columns were populated from HQuad cols 9-12 but never queried.
-- New quad-outlook logic reads quad1..4 + ref_quad_periods instead.
ALTER TABLE IF EXISTS ref_quad_outlook DROP COLUMN IF EXISTS m_outlook;
ALTER TABLE IF EXISTS ref_quad_outlook DROP COLUMN IF EXISTS m_score;
ALTER TABLE IF EXISTS ref_quad_outlook DROP COLUMN IF EXISTS q_outlook;
ALTER TABLE IF EXISTS ref_quad_outlook DROP COLUMN IF EXISTS q_score;

-- 2026-06-21: MacroNet tunable parameters in ref_settings (TASK_74).
-- N_m/N_q: proximity ramp window (days); wm_max/wq_max: max next-period weight;
-- a/b: quarter vs month blend; thr_*: MacroNet → vocabulary thresholds.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_N_m',    '5',    'MacroNet: monthly proximity ramp window (days)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_N_q',    '15',   'MacroNet: quarterly proximity ramp window (days)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_wm_max', '0.75', 'MacroNet: max weight for next-month quad near boundary')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_wq_max', '0.50', 'MacroNet: max weight for next-quarter quad near boundary')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_a',      '0.65', 'MacroNet: quarter blend weight (a in a*Q + b*M)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_b',      '0.35', 'MacroNet: month blend weight (b in a*Q + b*M)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_thr_bm', '1.5',  'MacroNet threshold: >= this → BM (buy more)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_thr_bs', '0.5',  'MacroNet threshold: >= this → BS (buy some)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_thr_stm','-0.5', 'MacroNet threshold: <= this → STM (trim)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_thr_sa', '-1.5', 'MacroNet threshold: <= this → SA (sell all)')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-21: Phase 1 schema — monthly quad distribution columns (TASK_74).
-- Monthly rows: quad1_pct..quad4_pct sum to ~100; quarterly rows keep NULL.
ALTER TABLE ref_quad_periods
  ADD COLUMN IF NOT EXISTS quad1_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS quad2_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS quad3_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS quad4_pct NUMERIC;

-- 2026-06-21: Phase 1 tunable params — ramp/lead + horizon weights (TASK_74).
-- These replace the earlier macro_N_m/N_q/wm_max/wq_max naming.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_month_ramp_begin_days', '12',
   'MacroNet: days before month-end the next-month weight starts ramping')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_month_lead_days', '5',
   'MacroNet: days before month-end next-month weight hits 100%')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_horizon_weight_qtr', '0.65',
   'MacroNet: Quarter weight a in MacroNet = a*Qtr + b*M')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_horizon_weight_mo', '0.35',
   'MacroNet: Month weight b in MacroNet = a*Qtr + b*M')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-21 TASK_78: ref_macro_area — area→member map for Macro read card.
-- area_key: stable area identifier (usd, us_equities, volatility, rates, credit,
--           commodities, crypto, global_equities)
-- member_symbol: tos_symbol of the member (matches drv_rr.tos_symbol)
-- role: 'dual'=has technicals; 'rr_only'=RR+outlook only; 'gauge'=vol zone;
--       'curve'=yield/curve — skip rr_pos (yield×10 scale mismatch)
-- PK (area_key, member_symbol)
CREATE TABLE IF NOT EXISTS ref_macro_area (
    area_key       TEXT    NOT NULL,
    label          TEXT    NOT NULL,
    member_symbol  TEXT    NOT NULL,
    role           TEXT    NOT NULL DEFAULT 'dual'
        CHECK (role IN ('dual','rr_only','gauge','curve')),
    sort_order     INT     NOT NULL DEFAULT 0,
    enabled        BOOL    NOT NULL DEFAULT TRUE,
    PRIMARY KEY (area_key, member_symbol)
);

-- 2026-06-21 TASK_78: macro-area thresholds in ref_settings.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_area_hot_pct',  '0.85',
   'Macro read: rr_pos >= this is HOT (trim signal)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_area_cold_pct', '0.15',
   'Macro read: rr_pos <= this is COLD (add signal)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('macro_area_conv_min', '0.33',
   'Macro read: minimum conviction to show Long/Short (vs Neutral)')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-21 TASK_79: ref_corr_asset — USD correlation asset catalog.
-- source_spec JSONB: ordered priority list e.g. ["tos:$DXY","stooq:^dxy"]
-- is_usd_base: TRUE for the USD ($DXY) row; all others correlated against it.
CREATE TABLE IF NOT EXISTS ref_corr_asset (
    asset_key    TEXT    PRIMARY KEY,
    label        TEXT    NOT NULL,
    source_spec  JSONB   NOT NULL DEFAULT '[]',
    is_usd_base  BOOL    NOT NULL DEFAULT FALSE,
    sort_order   INT     NOT NULL DEFAULT 0,
    enabled      BOOL    NOT NULL DEFAULT TRUE
);

-- 2026-06-21 TASK_79: hist_quote_daily — Stooq keyless daily-close backfill.
-- Append-only; ON CONFLICT DO NOTHING (convention 1).
-- PK (source, symbol, obs_date): source='stooq'|'tos'; symbol is raw Stooq
-- symbol or tos_symbol as appropriate.
CREATE TABLE IF NOT EXISTS hist_quote_daily (
    source      TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    obs_date    DATE    NOT NULL,
    close       NUMERIC,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, symbol, obs_date)
);
CREATE INDEX IF NOT EXISTS ix_hist_quote_daily_sym
    ON hist_quote_daily(symbol, obs_date);

-- 2026-06-21 TASK_79: drv_usd_correlation — rolling Pearson r (5 windows)
-- + 52-wk rolling-30D stats block. Idempotent: DELETE+INSERT on as_of_date.
-- tos_symbol: same as asset_key (or $DXY for the base). Use tos_symbol
-- convention (rule 15) — this is the symbol that appears in our TOS data.
CREATE TABLE IF NOT EXISTS drv_usd_correlation (
    as_of_date      DATE    NOT NULL,
    asset_key       TEXT    NOT NULL,
    tos_symbol      TEXT,
    w15             NUMERIC,
    w30             NUMERIC,
    w90             NUMERIC,
    w120            NUMERIC,
    w180            NUMERIC,
    n15             INT,
    n30             INT,
    n90             INT,
    n120            INT,
    n180            INT,
    roll30_high     NUMERIC,
    roll30_low      NUMERIC,
    roll30_pct_pos  NUMERIC,
    roll30_pct_neg  NUMERIC,
    derived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, asset_key)
);
CREATE INDEX IF NOT EXISTS ix_drv_usd_corr_date
    ON drv_usd_correlation(as_of_date DESC);

-- 2026-06-21 TASK_79: correlation color thresholds in ref_settings.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('corr_green_min',    '0.50',
   'USD correlation: r >= this renders green (positive corr)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('corr_red_strong',   '-0.70',
   'USD correlation: r <= this renders strong-red (strong neg corr)')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('corr_red_mod',      '-0.50',
   'USD correlation: -0.70 < r <= this renders moderate-red')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-06-23: ref_quad_periods v2 — standard calendar PK (year, period_num).
-- For existing DBs: run db/migrate_quad_periods_v2.py to migrate and drop start/end cols.
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS year INT;
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS period_num INT;
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS quad1_pct NUMERIC;
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS quad2_pct NUMERIC;
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS quad3_pct NUMERIC;
ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS quad4_pct NUMERIC;

-- 2026-06-23: per-month MacroNet scores for all available periods.
ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS monthly_scores_json JSONB;

-- 2026-06-23: Quarterly MacroNet ramp params (separate from monthly).
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_qtr_ramp_begin_days', '20',
   'MacroNet: bdays before quarter-end next-quarter weight starts ramping')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_qtr_lead_days', '10',
   'MacroNet: bdays before quarter-end next-quarter weight hits 100%')
ON CONFLICT (setting_name) DO NOTHING;

-- =====================================================
-- 2026-06-26 TASK_93: Hedgeye email pipeline
-- (folded from db/hedgeye_schema.sql)
-- Design: docs/hedgeye_feeds_design.md
-- =====================================================

-- Idempotency ledger: one row per email ever seen (keeps message_id for re-fetch)
CREATE TABLE IF NOT EXISTS meta_hedgeye_msg (
    message_id    TEXT PRIMARY KEY,
    email_type    TEXT,
    sender        TEXT,
    subject       TEXT,
    status        TEXT,
    detail        JSONB,
    processed_at  TIMESTAMPTZ DEFAULT now(),
    received_at   TIMESTAMPTZ
);

-- Real-Time Alerts (action feed). PK = message_id (one alert per email).
CREATE TABLE IF NOT EXISTS hist_rta (
    message_id     TEXT PRIMARY KEY,
    alert_ts       TIMESTAMPTZ,
    snapshot_date  DATE,
    is_correction  BOOLEAN DEFAULT FALSE,
    superseded     BOOLEAN DEFAULT FALSE,
    analyst        TEXT,
    signal_kind    TEXT,
    action         TEXT,
    side           TEXT,
    symbol         TEXT,
    tos_symbol     TEXT,
    price          NUMERIC,
    dur_trade      BOOLEAN,
    dur_trend      BOOLEAN,
    dur_tail       BOOLEAN,
    coaching_notes TEXT,
    raw_subject    TEXT
);
CREATE INDEX IF NOT EXISTS ix_hist_rta_sym ON hist_rta (tos_symbol, alert_ts DESC);

-- The Call top-5 most actionable ideas per daily email.
CREATE TABLE IF NOT EXISTS hist_call_top5 (
    snapshot_date     DATE,
    message_id        TEXT,
    rank              INT,
    symbol            TEXT,
    tos_symbol        TEXT,
    side              TEXT,
    rationale_snippet TEXT,
    PRIMARY KEY (snapshot_date, tos_symbol)
);

-- Daily Macro Show Bullish/Bearish ticker list.
CREATE TABLE IF NOT EXISTS hist_hedgeye_stance (
    snapshot_date  DATE,
    message_id     TEXT,
    stance         TEXT,
    symbol         TEXT,
    tos_symbol     TEXT,
    label          TEXT,
    PRIMARY KEY (snapshot_date, label)
);

-- Signal Strength delta events.
CREATE TABLE IF NOT EXISTS hist_sss_change (
    snapshot_date  DATE,
    message_id     TEXT,
    action         TEXT,
    symbol         TEXT,
    tos_symbol     TEXT,
    PRIMARY KEY (snapshot_date, action, tos_symbol)
);

-- Notes repository (deterministic snippet only, not the email body).
CREATE TABLE IF NOT EXISTS note_repo (
    note_id      BIGSERIAL PRIMARY KEY,
    message_id   TEXT NOT NULL,
    note_date    DATE,
    source_type  TEXT,
    gmail_link   TEXT,
    analyst      TEXT,
    tickers      TEXT[]  DEFAULT '{}',
    theme_tags   TEXT[]  DEFAULT '{}',
    quad         INT,
    signal_kind  TEXT,
    note_text    TEXT,
    subject      TEXT,
    status       TEXT DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS ix_note_repo_tickers ON note_repo USING GIN (tickers);
CREATE INDEX IF NOT EXISTS ix_note_repo_date ON note_repo (note_date DESC);
-- note_text can run long (full commentary paragraphs); a plain btree UNIQUE on
-- (message_id, source_type, note_text) overflows Postgres's 2704-byte index row
-- cap. Dedup on an md5 hash of the text instead (fixed-width, same semantics).
ALTER TABLE note_repo DROP CONSTRAINT IF EXISTS note_repo_message_id_source_type_note_text_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_note_repo_dedup ON note_repo (message_id, source_type, md5(note_text));

-- Optional cached LLM enrichment output (display-only, non-authoritative).
CREATE TABLE IF NOT EXISTS llm_analysis (
    message_id      TEXT,
    model           TEXT,
    prompt_version  TEXT,
    schema_version  TEXT,
    json_output     JSONB,
    created_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (message_id, model, prompt_version)
);

-- Archived chart images.
CREATE TABLE IF NOT EXISTS hist_media (
    message_id   TEXT,
    seq          INT,
    local_path   TEXT,
    source_url   TEXT,
    captured_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (message_id, seq)
);

-- Interactive rule-building workspace.
CREATE TABLE IF NOT EXISTS rule_candidate (
    candidate_id      BIGSERIAL PRIMARY KEY,
    title             TEXT,
    hypothesis        TEXT,
    linked_note_ids   BIGINT[] DEFAULT '{}',
    proposed_rule_def JSONB,
    status            TEXT DEFAULT 'draft',
    promoted_rule_id  TEXT,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- Classifier registry (table-driven router).
CREATE TABLE IF NOT EXISTS ref_hedgeye_email_type (
    email_type   TEXT PRIMARY KEY,
    destination  TEXT,
    cadence      TEXT,
    subject_re   TEXT,
    asset_name   TEXT,
    parser       TEXT,
    enabled      BOOLEAN DEFAULT TRUE
);

-- Derived: day-over-day Risk Range TREND flips.
CREATE OR REPLACE VIEW drv_rr_trend_change AS
SELECT snapshot_date AS as_of_date, tos_symbol,
       prev_outlook AS from_trend, outlook AS to_trend
FROM (
    SELECT snapshot_date, tos_symbol, outlook,
           LAG(outlook) OVER (PARTITION BY tos_symbol ORDER BY snapshot_date) AS prev_outlook
    FROM hist_rr
) t
WHERE prev_outlook IS NOT NULL AND prev_outlook <> outlook;

-- Column extensions on existing tables for Hedgeye email feed data:
-- hist_iichg / hist_etfchg: add action (add|remove), side (long|short), message_id
ALTER TABLE hist_iichg ADD COLUMN IF NOT EXISTS action     TEXT;
ALTER TABLE hist_iichg ADD COLUMN IF NOT EXISTS side       TEXT;
ALTER TABLE hist_iichg ADD COLUMN IF NOT EXISTS message_id TEXT;

ALTER TABLE hist_etfchg ADD COLUMN IF NOT EXISTS action     TEXT;
ALTER TABLE hist_etfchg ADD COLUMN IF NOT EXISTS side       TEXT;
ALTER TABLE hist_etfchg ADD COLUMN IF NOT EXISTS message_id TEXT;

-- hist_call / hist_ps: add message_id for source tracing
ALTER TABLE hist_call ADD COLUMN IF NOT EXISTS message_id TEXT;
ALTER TABLE hist_ps   ADD COLUMN IF NOT EXISTS message_id TEXT;

-- meta_hedgeye_msg: add received_at (email Date header, when Hedgeye sent it)
ALTER TABLE meta_hedgeye_msg ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ;

-- =====================================================
-- v_ingest_log — unified chronological ingest ledger
-- Unions meta_file_processed (file loads, incl. email-
-- rendered tab-backed feeds) with meta_hedgeye_msg
-- (every email ever processed). channel + source_kind
-- distinguish origin:
--   channel='file_load', source_kind='file'  → real file
--   channel='file_load', source_kind='email' → tab-backed email file
--   channel='email',     source_kind='email' → email receipt
-- A tab-backed feed appears TWICE (both channels) by design.
-- For "what landed in tables" filter channel='file_load'.
-- For "what emails arrived"  filter channel='email'.
-- =====================================================
CREATE OR REPLACE VIEW v_ingest_log AS
SELECT
    'file_load'                    AS channel,
    COALESCE(source_kind, 'file')  AS source_kind,
    file_path                      AS source_ref,
    file_type                      AS feed,
    target_tab,
    file_date                      AS data_date,
    'loaded'                       AS status,
    processed_at
FROM meta_file_processed
UNION ALL
SELECT
    'email'                        AS channel,
    'email'                        AS source_kind,
    message_id                     AS source_ref,
    email_type                     AS feed,
    NULL                           AS target_tab,
    NULL::date                     AS data_date,
    status,
    processed_at
FROM meta_hedgeye_msg;

-- =====================================================
-- Feed catalog (TASK_97) — one feed identity, two recognizers.
-- Additive: each feed gets a canonical feed_code on BOTH registries;
-- v_feed_catalog joins them so each logical feed shows its filename
-- recognizer (ref_load_files) AND its subject recognizer
-- (ref_hedgeye_email_type) on one row. Descriptive only — nothing in
-- the ingest hot path reads feed_code yet. Seed values:
-- db/seeds_feed_code.sql (idempotent UPDATEs).
-- =====================================================
ALTER TABLE ref_load_files         ADD COLUMN IF NOT EXISTS feed_code TEXT;
ALTER TABLE ref_hedgeye_email_type ADD COLUMN IF NOT EXISTS feed_code TEXT;

CREATE OR REPLACE VIEW v_feed_catalog AS
SELECT
    COALESCE(lf.feed_code, et.feed_code)                     AS feed_code,
    lf.file_type,
    lf.source_dir,
    lf.target_tab,
    lf.week_day,
    lf.file_time,
    et.email_type,
    et.subject_re,
    et.cadence,
    et.destination,
    et.parser,
    COALESCE(lf.enabled, TRUE) AND COALESCE(et.enabled, TRUE) AS enabled
FROM ref_load_files lf
FULL OUTER JOIN ref_hedgeye_email_type et ON lf.feed_code = et.feed_code;

-- hist_msr — Market Situation Report: intraday gamma metrics (one row per day)
CREATE TABLE IF NOT EXISTS hist_msr (
    snapshot_date   DATE         NOT NULL PRIMARY KEY,
    gamma_throttle  NUMERIC(10,4),
    rvol_10day      NUMERIC(10,4),
    message_id      TEXT
);

-- =====================================================
-- 2026-07-12 TASK_119: stop_breached flag on drv_actionable.
-- TRUE when a held position's latest price is below its stop_level
-- (etl/derive_actionable.py::_compute_stop). ADD/INCREASE rows with this
-- flag are downgraded to an effective HOLD (suppressed_reason =
-- 'STOP BREACHED') so the surface never recommends adding below a stop.
-- REMOVE/REDUCE/HOLD rows keep their action, just flagged.
-- =====================================================
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS stop_breached BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS ix_drv_actionable_stop_breached
    ON drv_actionable(as_of_date) WHERE stop_breached IS TRUE;

-- =====================================================
-- 2026-07-12 TASK_118 Part A: SELL-side signal-quality annotation.
-- v_unproven_sell_rules self-updates from the direction-adjusted rule
-- scorecard — a SELL composite with a large sample (fires>=500) whose
-- historical edge is negative (price recovers after it fires). No
-- hardcoded rule list; BUY-side rules/thresholds are untouched.
-- low_confidence: TRUE when a symbol's only sell-side evidence comes from
-- these unproven rules (no source-driven REMOVE/REDUCE, no proven rule).
-- Annotation only — consolidated_action is never changed by this flag.
-- =====================================================
CREATE OR REPLACE VIEW v_unproven_sell_rules AS
SELECT rule_id, fires, edge_20d, win_rate, confidence
FROM v_rule_scorecard
WHERE direction = 'SELL' AND fires >= 500 AND edge_20d < 0;

ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS low_confidence BOOLEAN NOT NULL DEFAULT FALSE;

-- =====================================================
-- 2026-07-12 TASK_121: drv_inferred_action — trades inferred from CS/F
-- position-snapshot deltas (qty_delta), NOT manual logging. Diffed by
-- etl/derive_inferred_actions.py per consecutive (account, tos_symbol)
-- snapshot pair. stance compares the inferred direction against that
-- date's drv_actionable.consolidated_action family.
-- Idempotent per date range: DELETE WHERE as_of_date BETWEEN ... THEN INSERT.
-- =====================================================
CREATE TABLE IF NOT EXISTS drv_inferred_action (
    as_of_date      DATE    NOT NULL,
    tos_symbol      TEXT    NOT NULL,
    account         TEXT    NOT NULL,
    source_feed     TEXT    NOT NULL CHECK (source_feed IN ('CS','F')),
    qty_delta       NUMERIC NOT NULL,
    est_dollar      NUMERIC,
    inferred_action TEXT    NOT NULL CHECK (inferred_action IN ('BUY','SELL')),
    rec_action      TEXT,
    stance          TEXT    NOT NULL
        CHECK (stance IN ('FOLLOWED','CONTRADICTED','NO_SIGNAL')),
    fwd_5d_pct      NUMERIC,
    fwd_20d_pct     NUMERIC,
    computed_at     TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol, account)
);
CREATE INDEX IF NOT EXISTS ix_drv_inferred_action_date
    ON drv_inferred_action(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_inferred_action_stance
    ON drv_inferred_action(stance);
CREATE INDEX IF NOT EXISTS ix_drv_inferred_action_sym
    ON drv_inferred_action(tos_symbol, as_of_date);

INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('inferred_action_min_dollar', '100',
     'Minimum est_dollar for a CS/F qty delta to count as an inferred trade (filters dividend-reinvest noise)')
ON CONFLICT (setting_name) DO NOTHING;

-- Read path for /api/rules/my-actions (TASK_121). Kept as a thin passthrough
-- so it can be extended without touching the base table; the older
-- v_user_action_performance (transaction-log based, TASK_71) is left intact
-- for comparison.
CREATE OR REPLACE VIEW v_inferred_action_performance AS
SELECT as_of_date, tos_symbol, account, source_feed, qty_delta, est_dollar,
       inferred_action, rec_action, stance, fwd_5d_pct, fwd_20d_pct
FROM drv_inferred_action;

-- =====================================================
-- 2026-07-13 TASK_123: signal validation scorecards (read-only + additive).
-- Measures the unvalidated calibration assumptions from
-- docs/actionable_playbook.md §5 (A1 bull-gate ladder, A2/A3 Final Call
-- strength, A4 source precedence). Forward-return mechanism: LEAD(last_price,
-- 5/20) over drv_ma per tos_symbol, same row-offset convention as
-- etl/compute_firing_outcomes.py / v_user_action_performance above (NOT a
-- join to drv_rule_outcome, so every symbol/date with a bucketed value is
-- covered — not only symbols where some rule happened to fire that day).
-- Analyst views only; never joined into /api/actionable.
-- =====================================================

-- v_bull_gate_scorecard (assumption A1): two independent bucket breakdowns
-- unioned under a `dimension` discriminator — 'bull_ladder' buckets
-- drv_cat_atomic_input.bull (MQ ladder, -3..+3); 'rr_bull_bear' buckets
-- drv_tn_td_bb_rr.rr_bull_bear (QP, 'B'/'!B'). win_rate_20d = fraction with
-- fwd_20d_pct > 0 (no direction adjustment — bull is not itself a buy/sell
-- code, just a bullishness score).
DROP VIEW IF EXISTS v_bull_gate_scorecard CASCADE;
CREATE VIEW v_bull_gate_scorecard AS
WITH px AS (
    SELECT tos_symbol, as_of_date, last_price,
           LEAD(last_price, 5)  OVER w AS p5,
           LEAD(last_price, 20) OVER w AS p20
    FROM drv_ma
    WHERE last_price IS NOT NULL
    WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
),
fwd AS (
    SELECT tos_symbol, as_of_date,
           CASE WHEN last_price > 0 AND p5  IS NOT NULL
                THEN (p5  - last_price) / last_price * 100 END AS fwd5,
           CASE WHEN last_price > 0 AND p20 IS NOT NULL
                THEN (p20 - last_price) / last_price * 100 END AS fwd20
    FROM px
),
bull_b AS (
    SELECT 'bull_ladder'::text AS dimension, ci.bull::text AS bucket_value,
           f.fwd5, f.fwd20
    FROM drv_cat_atomic_input ci
    JOIN fwd f ON f.tos_symbol = ci.tos_symbol AND f.as_of_date = ci.as_of_date
    WHERE ci.bull IS NOT NULL AND f.fwd20 IS NOT NULL
),
rr_b AS (
    SELECT 'rr_bull_bear'::text AS dimension, r.rr_bull_bear AS bucket_value,
           f.fwd5, f.fwd20
    FROM drv_tn_td_bb_rr r
    JOIN fwd f ON f.tos_symbol = r.tos_symbol AND f.as_of_date = r.as_of_date
    WHERE r.rr_bull_bear IS NOT NULL AND f.fwd20 IS NOT NULL
),
u AS (SELECT * FROM bull_b UNION ALL SELECT * FROM rr_b)
SELECT dimension,
       bucket_value AS bull_bucket,
       COUNT(*)                                            AS n,
       ROUND(AVG(fwd5)::numeric, 3)                        AS avg_fwd_5d,
       ROUND(AVG(fwd20)::numeric, 3)                       AS avg_fwd_20d,
       ROUND((PERCENTILE_CONT(0.5)
              WITHIN GROUP (ORDER BY fwd20))::numeric, 3)  AS median_fwd_20d,
       ROUND(AVG((fwd20 > 0)::int)::numeric, 3)            AS win_rate_20d
FROM u
GROUP BY dimension, bucket_value;

-- v_final_call_scorecard (assumptions A2/A3): buckets drv_actionable's
-- final_code x fc_confidence. Direction-adjust via final_side (already
-- classified server-side by _compute_final_call — no regex needed): a sell
-- final call wants a negative fwd_20d, so edge_20d flips the sign; neutral
-- (HOLD/gate) rows are left unadjusted. raw_avg_fwd_20d is the un-flipped
-- mean for comparison, mirroring v_rule_scorecard's raw_avg_fwd20/edge_20d pair.
DROP VIEW IF EXISTS v_final_call_scorecard CASCADE;
CREATE VIEW v_final_call_scorecard AS
WITH px AS (
    SELECT tos_symbol, as_of_date, last_price,
           LEAD(last_price, 5)  OVER w AS p5,
           LEAD(last_price, 20) OVER w AS p20
    FROM drv_ma
    WHERE last_price IS NOT NULL
    WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
),
fwd AS (
    SELECT tos_symbol, as_of_date,
           CASE WHEN last_price > 0 AND p5  IS NOT NULL
                THEN (p5  - last_price) / last_price * 100 END AS fwd5,
           CASE WHEN last_price > 0 AND p20 IS NOT NULL
                THEN (p20 - last_price) / last_price * 100 END AS fwd20
    FROM px
),
b AS (
    SELECT a.final_code, a.fc_confidence, a.final_side, f.fwd5, f.fwd20,
           CASE WHEN a.final_side = 'sell' THEN -f.fwd20 ELSE f.fwd20 END AS da,
           CASE WHEN a.final_side = 'sell' THEN (f.fwd20 < 0)
                WHEN a.final_side = 'buy'  THEN (f.fwd20 > 0)
                ELSE (f.fwd20 > 0) END AS hit
    FROM drv_actionable a
    JOIN fwd f ON f.tos_symbol = a.tos_symbol AND f.as_of_date = a.as_of_date
    WHERE a.final_code IS NOT NULL AND f.fwd20 IS NOT NULL
)
SELECT final_code, fc_confidence,
       COUNT(*)                                     AS n,
       ROUND(AVG(fwd5)::numeric, 3)                 AS avg_fwd_5d,
       ROUND(AVG(fwd20)::numeric, 3)                AS raw_avg_fwd_20d,
       ROUND(AVG(da)::numeric, 3)                   AS edge_20d,
       ROUND((PERCENTILE_CONT(0.5)
              WITHIN GROUP (ORDER BY fwd20))::numeric, 3) AS median_fwd_20d,
       ROUND(AVG(hit::int)::numeric, 3)              AS win_rate_20d
FROM b
GROUP BY final_code, fc_confidence;

-- v_source_edge_scorecard (assumption A4): per-source-per-action forward
-- edge from drv_outlook_action. Buy-family (ADD/INCREASE) wants fwd up;
-- sell-family (REDUCE/REMOVE) wants fwd down; HOLD is left unadjusted.
-- Used to check the empirical ordering against the fixed SOURCE_ORDER
-- (PS=1, ETF=2, RR=3, SSS=4, II=5, CALL=6).
DROP VIEW IF EXISTS v_source_edge_scorecard CASCADE;
CREATE VIEW v_source_edge_scorecard AS
WITH px AS (
    SELECT tos_symbol, as_of_date, last_price,
           LEAD(last_price, 5)  OVER w AS p5,
           LEAD(last_price, 20) OVER w AS p20
    FROM drv_ma
    WHERE last_price IS NOT NULL
    WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
),
fwd AS (
    SELECT tos_symbol, as_of_date,
           CASE WHEN last_price > 0 AND p5  IS NOT NULL
                THEN (p5  - last_price) / last_price * 100 END AS fwd5,
           CASE WHEN last_price > 0 AND p20 IS NOT NULL
                THEN (p20 - last_price) / last_price * 100 END AS fwd20
    FROM px
),
b AS (
    SELECT oa.source_code, oa.action,
           CASE WHEN oa.action IN ('ADD','INCREASE') THEN f.fwd5
                WHEN oa.action IN ('REDUCE','REMOVE') THEN -f.fwd5
                ELSE f.fwd5 END AS da5,
           CASE WHEN oa.action IN ('ADD','INCREASE') THEN f.fwd20
                WHEN oa.action IN ('REDUCE','REMOVE') THEN -f.fwd20
                ELSE f.fwd20 END AS da20,
           CASE WHEN oa.action IN ('ADD','INCREASE') THEN (f.fwd20 > 0)
                WHEN oa.action IN ('REDUCE','REMOVE') THEN (f.fwd20 < 0)
                ELSE (f.fwd20 > 0) END AS hit
    FROM drv_outlook_action oa
    JOIN fwd f ON f.tos_symbol = oa.tos_symbol AND f.as_of_date = oa.as_of_date
    WHERE oa.action IS NOT NULL AND f.fwd20 IS NOT NULL
)
SELECT source_code, action,
       COUNT(*)                          AS n,
       ROUND(AVG(da5)::numeric, 3)       AS edge_5d,
       ROUND(AVG(da20)::numeric, 3)      AS edge_20d,
       ROUND(AVG(hit::int)::numeric, 3)  AS win_rate_20d
FROM b
GROUP BY source_code, action;

-- =====================================================
-- 2026-07-13 TASK_124: Trade Mode weak-source list (tunable, not hardcoded).
-- Sources that measured negative buy-edge in the TASK_123 signal validation
-- (docs/audit/signal_validation_2026-07.md) — a qualifying buy backed only by
-- one of these gets a "WEAK SRC" pill on the Actionable Trade Mode view
-- instead of being hidden. Comma-separated source_code list.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('trade_mode_weak_buy_sources', 'PS,ETF,II',
     'Trade Mode: comma-separated source_code list that measured negative buy-edge — tagged WEAK SRC instead of hidden')
ON CONFLICT (setting_name) DO NOTHING;

-- =====================================================
-- 2026-07-15 TASK_125: drv_pvv — Price/Volume/Volatility (Hedgeye-style ROC)
-- signal computed in 4 time buckets (today/5d/3w/3m), consolidated into one
-- decision (BUY/BUY_DIP/REDUCE/AVOID/SELL/TRIM/WATCH). Informational v1 —
-- NOT wired into drv_actionable/consolidated_action. See docs/pvv_logic.md.
-- Idempotent: DELETE WHERE as_of_date=D then INSERT (etl/derive_pvv.py).
-- =====================================================
CREATE TABLE IF NOT EXISTS drv_pvv (
    as_of_date  DATE NOT NULL,
    tos_symbol  TEXT NOT NULL,
    sig_today   TEXT,        -- signal code per bucket (see docs/pvv_logic.md §3)
    sig_5d      TEXT,
    sig_3w      TEXT,
    sig_3m      TEXT,
    decision    TEXT,        -- consolidated decision (see docs/pvv_logic.md §4)
    detail      JSONB,       -- per-bucket inputs for the UI tooltip (§5)
    derived_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_pvv_tos_symbol
    ON drv_pvv(tos_symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_pvv_decision
    ON drv_pvv(as_of_date, decision);

-- =====================================================
-- 2026-07-15 TASK_126: sliding look-ahead window over the monthly quad
-- calendar, replacing the month now/next ramp + quarterly one-hot blend in
-- etl/derive_macro.py. See docs/quad_design.md (Stage 3) +
-- agent-tasks/TASK_126_quad_lookahead_window.md.
-- =====================================================

-- `detail` JSONB: {h, coverage_pct, fallback, months:[{m,quad,w,stance}],
-- eff:{q1..q4}, near_vs_far:{near,far,override}, tracking}. Replaces the
-- month/quarter ramp breakdown previously recomputed live in dash.py.
ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS detail JSONB;

-- Deprecated (TASK_126): the ramp/lead blend these columns described is
-- retired — etl/derive_macro.py no longer populates them (INSERTs NULL).
-- Columns kept for backward compat (old rows, any external readers).
-- month_now_net / month_next_net / month_weight / qtr_next_net / qtr_weight
-- monthly_score now stores M_window; qtr_now_net == quarterly_score
-- (quarterly leg is a plain current-quarter one-hot, no next-quarter blend).
COMMENT ON COLUMN drv_macro_score.month_now_net IS
    'Deprecated (TASK_126) — ramp blend retired; NULL going forward.';
COMMENT ON COLUMN drv_macro_score.month_next_net IS
    'Deprecated (TASK_126) — ramp blend retired; NULL going forward.';
COMMENT ON COLUMN drv_macro_score.month_weight IS
    'Deprecated (TASK_126) — ramp blend retired; NULL going forward.';
COMMENT ON COLUMN drv_macro_score.qtr_next_net IS
    'Deprecated (TASK_126) — quarterly ramp blend retired; NULL going forward.';
COMMENT ON COLUMN drv_macro_score.qtr_weight IS
    'Deprecated (TASK_126) — quarterly ramp blend retired; NULL going forward.';
COMMENT ON COLUMN drv_macro_score.monthly_score IS
    'M_window (TASK_126) — sliding look-ahead window blend, was month now/next ramp.';

-- New tunables: look-ahead window length + optional decay half-life.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_lookahead_days', '60',
   'MacroNet: sliding look-ahead window length H in calendar days from anchor D')
ON CONFLICT (setting_name) DO NOTHING;
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('quad_lookahead_decay_hl', '0',
   'MacroNet: within-window day-weight decay half-life in days; 0 = flat/off')
ON CONFLICT (setting_name) DO NOTHING;

-- Quarterly weight minimized (was 0.20 pre-TASK_126, 0.35/0.65 before that);
-- monthly weight is now implicitly (1 - quad_horizon_weight_qtr) inside
-- etl/derive_macro.py — quad_horizon_weight_mo is no longer read there.
UPDATE ref_settings SET setting_value = '0.05'
    WHERE setting_name = 'quad_horizon_weight_qtr';

-- Threshold recalibration (TASK_126) — the window blend shifts the MacroNet
-- distribution vs the old ramp; re-percentiled against the live
-- drv_macro_score output the same way as the 2026-07-06 pass (target ~3%
-- BM, ~12% BS, ~70% HOLD, ~12% STM, ~3% SA). The near/far sign-agreement
-- override puts a structural floor under SA (~6.9% live — any month whose
-- nearest + weighted-rest both go negative forces SA regardless of the raw
-- score, same asymmetric-by-design rule as 2026-07-06); achieved live split
-- at these values: BM 2.4% / BS 17.3% / HOLD 65.0% / STM 8.3% / SA 6.9%
-- (see DEV_HANDOFF for the calibration run). Values below also correct
-- baseline.sql drift vs the live DB (the 2026-07-06 recalibration had only
-- ever been applied by hand, never migrated here — this UPDATE folds both
-- fixes into one idempotent step). See docs/quad_design.md.
UPDATE ref_settings SET setting_value = '1.25'  WHERE setting_name = 'macro_thr_bm';
UPDATE ref_settings SET setting_value = '1.05'  WHERE setting_name = 'macro_thr_bs';
UPDATE ref_settings SET setting_value = '-0.15' WHERE setting_name = 'macro_thr_stm';
UPDATE ref_settings SET setting_value = '-0.6'  WHERE setting_name = 'macro_thr_sa';

-- Retired (TASK_126): quad_month_ramp_begin_days / quad_month_lead_days /
-- quad_qtr_ramp_begin_days / quad_qtr_lead_days are no longer read by
-- etl/derive_macro.py (the sliding window supersedes the ramp/lead model).
-- Rows left in ref_settings — harmless, kept for audit/rollback reference.

-- =====================================================
-- 2026-07-20 TASK_132: daily TOS-band (BBTop/BBBottom) vs Hedgeye hist_rr
-- variance tracking + drift alert. See docs/tos_rr_calibration.md
-- "Ongoing monitoring" section and agent-tasks/TASK_132_bb_rr_variance_
-- tracking.md. Stored table (not a view) — the daily WARN/ALERT flag
-- evaluation and rolling medians have to run somewhere anyway; matches the
-- existing drv_rr pattern of duplicating hist_rr/hist_td for downstream use.
-- =====================================================
CREATE TABLE IF NOT EXISTS drv_bb_rr_gap (
    as_of_date       DATE NOT NULL,
    tos_symbol       TEXT NOT NULL,
    bb_top           NUMERIC,   -- hist_td.a_bb_top (latest snapshot < D, EOD seq)
    bb_bottom        NUMERIC,
    rr_sell          NUMERIC,   -- hist_rr.sell_trade for D (reverse-scaled)
    rr_buy           NUMERIC,   -- hist_rr.buy_trade  for D (reverse-scaled)
    ape_top          NUMERIC,   -- |bb_top - rr_sell| / rr_sell * 100 (NULL if either side missing)
    ape_bottom       NUMERIC,
    ape_top_med20    NUMERIC,   -- rolling <=20-trading-day median of ape_top (per symbol, min 5 obs)
    ape_bottom_med20 NUMERIC,
    drift_flag       TEXT,      -- NULL | 'WARN' | 'ALERT'
    source_run_id    BIGINT,
    derived_at       TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_bb_rr_gap_sym ON drv_bb_rr_gap(tos_symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_bb_rr_gap_flag ON drv_bb_rr_gap(as_of_date, drift_flag)
    WHERE drift_flag IS NOT NULL;

-- ref_rrt.tos_ticker is not unique -- some TOS tickers have multiple RRT
-- rows (e.g. $DXY: 'USD'/'NYICDX', /BTC: 'BITCOIN'/'BTCUSD'/'BTC'). The
-- actionable Symbol column joins on tos_ticker to show rr_name in place of
-- tos_symbol; without a tiebreaker that join fans out into duplicate grid
-- rows. `preferred_display` marks which row wins when a tos_ticker has more
-- than one. Editable via the generic /ref UI (single-col PK, no code change
-- needed there).
ALTER TABLE ref_rrt ADD COLUMN IF NOT EXISTS preferred_display BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('rsi_overbought', '70', 'Actionable don''t-buy warning: RSI >= this is overbought'),
  ('rsi_oversold',   '30', 'Actionable don''t-buy warning: RSI <= this is oversold'),
  ('vlm_rvol_avoid_threshold', '1.5',
   'Actionable don''t-buy warning: VLM flags a caution when rvol (current/10d-avg volume) '
   '>= this AND price is UP for the day (a "buying climax" — heavy volume on a pop). '
   'Direction flipped from the original down-day hypothesis 2026-08-01 after a factor '
   'backtest (v_factor_scorecard) showed high-RVOL-down-day beat baseline at every '
   'horizon, opposite of the original assumption.')
ON CONFLICT (setting_name) DO NOTHING;

-- -----------------------------------------------------
-- drv_factor_snapshot / v_factor_scorecard (2026-08-01) — per-symbol-day
-- factor bucket + forward return, so "does this factor actually predict the
-- stock's move" can be checked continuously instead of via one-off queries.
-- Populated by etl/compute_factor_outcomes.py (mirrors compute_firing_outcomes.py's
-- LEAD-over-drv_ma.last_price forward-return convention). Idempotent upsert,
-- one row per (as_of_date, tos_symbol); each factor's bucket column is NULL
-- when that factor's inputs aren't available for that symbol/day.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_factor_snapshot (
    as_of_date      DATE NOT NULL,
    tos_symbol      TEXT NOT NULL,
    rsi_bucket      TEXT,
    macdh_bucket    TEXT,
    rvol_bucket     TEXT,
    iv_bucket       TEXT,
    macro_action    TEXT,
    winning_source  TEXT,
    sector          TEXT,
    growth_style    TEXT,
    valuation_style TEXT,
    momentum_style  TEXT,
    fwd_5d_pct      NUMERIC,
    fwd_20d_pct     NUMERIC,
    source_run_id   BIGINT,
    derived_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_factor_snapshot_date ON drv_factor_snapshot(as_of_date);

-- v_factor_scorecard - unpivots drv_factor_snapshot's per-factor bucket columns
-- into one (factor, bucket) row per group, with the same raw (non-direction-
-- adjusted) forward-return efficacy stats as v_atomic_rule_scorecard: avg
-- fwd 5d/20d, win rate, 95% CI, confidence tier. A synthetic 'Baseline'
-- factor/'All stocks' bucket (one row per symbol-day, not one per factor) is
-- included so the UI can show each bucket's delta against it.
-- MACRO column sector/asset-class/style dots (2026-08-01) — per-membership
-- bullish(+1)/bearish(-1)/neutral(0) window-weighted stance, computed
-- alongside (and with the same weighting as) the combined macronet score in
-- etl/derive_macro.py, so these always agree with the tooltip's numbers.
-- style_stances is an array since a symbol can carry several independent
-- style tags (High/Low Beta, Cyclical/Defensive, Value/Secular, Dividend,
-- Momentum, Small/Mid Caps) that can disagree with each other — averaging
-- them into one number would hide a real split, so each is kept separate:
-- [{"label": "Momentum", "stance": 1.0}, {"label": "Cyclical", "stance": -1.0}, ...]
ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS sector_stance NUMERIC;
ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS asset_class_stance NUMERIC;
ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS style_stances JSONB;

DROP VIEW IF EXISTS v_factor_scorecard CASCADE;
CREATE VIEW v_factor_scorecard AS
WITH unpivoted AS (
    SELECT as_of_date, tos_symbol, 'RSI' AS factor, rsi_bucket AS bucket,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE rsi_bucket IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'MACDH momentum', macdh_bucket,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE macdh_bucket IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'RVOL + direction', rvol_bucket,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE rvol_bucket IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'IV percentile', iv_bucket,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE iv_bucket IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Macro quad action', macro_action,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE macro_action IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Winning source', winning_source,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE winning_source IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Sector', sector,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE sector IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Style: growth/cyclical', growth_style,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE growth_style IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Style: valuation', valuation_style,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE valuation_style IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Style: momentum', momentum_style,
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot WHERE momentum_style IS NOT NULL
    UNION ALL
    SELECT as_of_date, tos_symbol, 'Baseline', 'All stocks',
           fwd_5d_pct, fwd_20d_pct
    FROM drv_factor_snapshot
),
agg AS (
    SELECT factor, bucket,
           COUNT(*) FILTER (WHERE fwd_20d_pct IS NOT NULL) AS n,
           COUNT(DISTINCT tos_symbol)                      AS n_symbols,
           AVG(fwd_5d_pct)                                 AS avg5,
           AVG(fwd_20d_pct)                                AS avg20,
           STDDEV_SAMP(fwd_20d_pct)                         AS sd20,
           AVG((fwd_20d_pct > 0)::int)                     AS win_rate,
           MIN(as_of_date)                                 AS fs,
           MAX(as_of_date)                                 AS ls
    FROM unpivoted
    WHERE fwd_20d_pct IS NOT NULL
    GROUP BY factor, bucket
)
SELECT
    factor, bucket, n, n_symbols,
    ROUND(avg5::numeric, 3)  AS avg_fwd_5d,
    ROUND(avg20::numeric, 3) AS avg_fwd_20d,
    ROUND(win_rate::numeric, 3) AS win_rate,
    ROUND((avg20 - 1.96*sd20/NULLIF(SQRT(n),0))::numeric, 3) AS ci_low,
    ROUND((avg20 + 1.96*sd20/NULLIF(SQRT(n),0))::numeric, 3) AS ci_high,
    CASE
        WHEN n >= 100 AND (avg20 - 1.96*sd20/NULLIF(SQRT(n),0)) > 0 THEN 'proven'
        WHEN n >= 30 AND avg20 > 0 THEN 'promising'
        ELSE 'unproven'
    END AS confidence,
    fs AS first_seen, ls AS last_seen
FROM agg;


-- =====================================================
-- 2026-08-01 TASK_133: Dashboard Cockpit — reference tables (Phase 2),
-- self-computed market stats + Risk Dial (Phase 3), factor scorecard
-- (Phase 5), and cockpit API support tables (Phase 6). See
-- docs/dashboard_cockpit_design.md + agent-tasks/TASK_133_dashboard_cockpit.md.
-- =====================================================

-- Risk-dial gauge registry. Predicate logic is in etl/derive_risk_dial.py::GAUGES;
-- this table controls weight and on/off only.
CREATE TABLE IF NOT EXISTS ref_risk_gauge (
    gauge_key   text PRIMARY KEY,
    label       text    NOT NULL,
    weight      numeric NOT NULL DEFAULT 1,
    is_active   boolean NOT NULL DEFAULT TRUE,
    category    text,                 -- equity | vol | credit | rates | fx | commodity | breadth | positioning
    notes       text
);

-- Round-number price/yield levels the user considers meaningful.
CREATE TABLE IF NOT EXISTS ref_level_watch (
    id          serial PRIMARY KEY,
    tos_symbol  text    NOT NULL,
    level_value numeric NOT NULL,
    tolerance   numeric NOT NULL,     -- same units as level_value
    label       text,
    is_active   boolean NOT NULL DEFAULT TRUE,
    UNIQUE (tos_symbol, level_value)
);

-- Which parts of the book each fired gauge / pattern hits.
CREATE TABLE IF NOT EXISTS ref_gauge_transmission (
    id          serial PRIMARY KEY,
    gauge_key   text NOT NULL,        -- ref_risk_gauge.gauge_key OR ref_market_pattern.pattern_key
    axis        text NOT NULL,        -- 'sector' | 'asset_class' | 'style'
    category    text NOT NULL,
    UNIQUE (gauge_key, axis, category)
);

-- Named cross-asset co-movement patterns.
CREATE TABLE IF NOT EXISTS ref_market_pattern (
    pattern_key text PRIMARY KEY,
    label       text    NOT NULL,
    read_text   text    NOT NULL,     -- shown verbatim in the UI
    severity    text    NOT NULL DEFAULT 'warn',   -- 'severe' | 'warn' | 'info'
    is_active   boolean NOT NULL DEFAULT TRUE
);

-- Phase 3: self-computed market stats + Risk Dial. One row per as_of_date.
CREATE TABLE IF NOT EXISTS drv_market_stat (
    as_of_date              date PRIMARY KEY,
    -- realized vol + variance risk premium (SPX)
    rv10                    numeric,
    rv21                    numeric,
    rv63                    numeric,
    vix                     numeric,
    vrp                     numeric,
    vrp_z                   numeric,
    -- breadth, computed on this system's own universe
    pct_above_sma50         numeric,
    pct_above_sma200        numeric,
    pct_above_sma50_5d_chg  numeric,
    universe_n              integer,
    -- participation
    spy_rvol                numeric,
    -- market internals (Phase 4; NULL until the INT feed lands)
    adv_issues              numeric,
    dec_issues              numeric,
    up_volume               numeric,
    down_volume             numeric,
    trin                    numeric,
    vol_breadth             numeric,
    -- risk dial
    risk_budget             integer,
    risk_label              text,
    gauges_fired            jsonb,
    detail                  jsonb,
    derived_at              timestamp NOT NULL DEFAULT now()
);

-- Phase 6: market events (range breaks, trend flips, z-scores, patterns,
-- calendar/surprise). One row per event, event_seq assigned per as_of_date.
CREATE TABLE IF NOT EXISTS drv_market_event (
    as_of_date  date    NOT NULL,
    event_seq   integer NOT NULL,
    event_type  text    NOT NULL,   -- range_break | trend_flip | zscore | pattern | calendar | surprise
    severity    text    NOT NULL,   -- severe | warn | info
    tos_symbol  text,
    pattern_key text,
    title       text    NOT NULL,
    legs        jsonb,
    read_text   text,
    exposure    jsonb,
    PRIMARY KEY (as_of_date, event_seq)
);

-- Phase 5: factor scorecard — time-weighted returns by sector / asset class /
-- style, vs. proxy benchmark, vs. quad stance. One row per (date, axis, category).
CREATE TABLE IF NOT EXISTS drv_category_perf (
    as_of_date       date NOT NULL,
    axis             text NOT NULL,     -- 'sector' | 'asset_class' | 'style'
    category         text NOT NULL,
    market_value     numeric,
    weight_pct       numeric,
    -- 2026-08-08: sector/style are equity-only axes (see _categories_for's
    -- non-equity exclusion) but weight_pct's denominator stays total
    -- portfolio value (cash/bonds/etc included) for cross-axis consistency.
    -- weight_pct_equities re-bases the same market_value against total
    -- EQUITY value only (Asset Class's own "Equities" bucket) so sector/
    -- style weights read as a share of the equity sleeve, matching how
    -- sector allocation is normally quoted. NULL for axis='asset_class'
    -- (that axis IS the total-portfolio view by design).
    weight_pct_equities numeric,
    target_min       numeric,
    target_max       numeric,
    twr_1w  numeric, twr_3w  numeric, twr_1m  numeric, twr_2m  numeric, twr_3m numeric,
    bench_1w numeric, bench_3w numeric, bench_1m numeric, bench_2m numeric, bench_3m numeric,
    -- TASK_140: single-day columns. twr/bench_today = 1-day return ending D;
    -- twr/bench_yesterday = the ISOLATED 1-day return ending D-1 (not a
    -- 2-day cumulative window) -- see etl/derive_category_perf.py::_twr_window.
    twr_today numeric, twr_yesterday numeric,
    bench_today numeric, bench_yesterday numeric,
    -- 2026-08-08: calendar-boundary windows (first trading day of month/
    -- quarter/year through D), NOT a fixed trading-day count like twr_1m/etc
    -- above -- see etl/derive_category_perf.py::_window_days_since.
    twr_mtd numeric, twr_qtd numeric, twr_ytd numeric,
    bench_mtd numeric, bench_qtd numeric, bench_ytd numeric,
    bench_symbol     text,
    flows_confidence text,              -- 'green' | 'amber' | 'suspect'
    quad_stance      text,              -- BULLISH | NEUTRAL | BEARISH
    verdict          text,
    detail           jsonb,
    derived_at       timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, axis, category)
);
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS twr_today numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS twr_yesterday numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS bench_today numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS bench_yesterday numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS weight_pct_equities numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS twr_mtd numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS twr_qtd numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS twr_ytd numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS bench_mtd numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS bench_qtd numeric;
ALTER TABLE IF EXISTS drv_category_perf ADD COLUMN IF NOT EXISTS bench_ytd numeric;

-- Phase 4.1: ToS market internals (INT tab) — $ADVN/$DECN/$UVOL/$DVOL/$TRIN.
-- Deliberately NOT part of drv_symbols/hist_td universe (see CLAUDE.md
-- "Adding a new source-file type" + TASK_133 Phase 4.1) -- these are
-- market-wide breadth scalars, not tradeable symbols.
CREATE TABLE IF NOT EXISTS hist_internals (
    snapshot_date date    NOT NULL,
    symbol        text    NOT NULL,
    sequence      integer NOT NULL,
    export_date   date,
    export_time   text,
    last_value    numeric,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);

CREATE INDEX IF NOT EXISTS ix_drv_market_event_sym ON drv_market_event(tos_symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_category_perf_axis ON drv_category_perf(axis, as_of_date);

-- 2026-08-10 -- Dashboard Notes panel: free-text sticky notes with an
-- optional effective/expiration date window, rendered below the Mkt
-- Situation panel. effective_date NULL = shown immediately; expiration_date
-- NULL = never auto-expires (stays until manually deleted). A note is
-- "active" (shown by default) when today falls in
-- [effective_date, expiration_date] with either bound open-ended --
-- see api/routers/dash.py's dashboard-notes endpoints. Rows past their
-- expiration_date are NOT deleted, just filtered out of the default view,
-- so the history isn't lost (same DELETE-avoidance spirit as hist_*,
-- CLAUDE.md convention #1, even though this isn't a hist_ table).
-- User's worked example: "from date -> none (effective right away), to
-- date -> 8/13, note -> watch for CPI...".
CREATE TABLE IF NOT EXISTS user_dashboard_note (
    id              SERIAL PRIMARY KEY,
    note_text       TEXT NOT NULL,
    effective_date  DATE,
    expiration_date DATE,
    -- 2026-08-10 follow-up -- importance drives the panel's color-coded
    -- left-border stripe (high=red/medium=amber/low=gray, see
    -- web/dashboard_notes.js). sort_order is a float, not an integer, so
    -- drag-and-drop reordering only ever has to update the ONE moved row
    -- (new value = midpoint of its new neighbors' sort_order) instead of
    -- renumbering the whole list. User: "a way to move up or down by
    -- dragging the notes. and color it by importance (high, medium, low)."
    importance      TEXT NOT NULL DEFAULT 'medium'
                    CHECK (importance IN ('high', 'medium', 'low')),
    sort_order      DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
ALTER TABLE IF EXISTS user_dashboard_note ADD COLUMN IF NOT EXISTS importance TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE IF EXISTS user_dashboard_note DROP CONSTRAINT IF EXISTS user_dashboard_note_importance_check;
ALTER TABLE IF EXISTS user_dashboard_note ADD CONSTRAINT user_dashboard_note_importance_check
    CHECK (importance IN ('high', 'medium', 'low'));
ALTER TABLE IF EXISTS user_dashboard_note ADD COLUMN IF NOT EXISTS sort_order DOUBLE PRECISION NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_user_dashboard_note_dates ON user_dashboard_note(effective_date, expiration_date);
CREATE INDEX IF NOT EXISTS ix_user_dashboard_note_sort ON user_dashboard_note(sort_order);

-- =====================================================
-- 2026-08-10 -- Buy-signal advisory warnings (NOT a change to
-- consolidated_action/final_code -- annotation only, same spirit as
-- low_confidence above). etl/derive_actionable.py populates both.
-- warn_not_at_lrr: TRUE when a buy-tier row's low_lrr (ref_trig_atomic_rule
-- id=30, drv_cat_atomic_input.low_lrr, already-configured/tunable) != 3
-- (3 = at/below LRR; 1/2 = progressively clear of it). User: "I should only
-- buy a stock if above trade/trend and at LRR" -> "can we have them as
-- warnings in case of buys instead of adding a concrete rule?"
-- warn_added_this_leg: TRUE when a real Buy transaction (hist_cst.action=
-- 'Buy' / hist_ft.action_kind='BUY') already happened for this symbol
-- since the most recent date its price closed at/above TRR ("this leg").
-- Uses actual transaction imports, not app-logged actions, per user: "use
-- my actual buy imports (i am not using logged actions)".
-- =====================================================
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS warn_not_at_lrr BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS warn_added_this_leg BOOLEAN NOT NULL DEFAULT FALSE;

-- =====================================================
-- 2026-08-12 -- Stop-level logic replaced with Trade/Trend persistence
-- signal (etl/derive_actionable.py::_compute_stop_signal, was
-- _compute_stop). Old formula was a single blended $ price
-- (MAX(trade_line, price*(1-stop_pct))); replaced because a same-day dip
-- below the line was too easy to whipsaw. New logic requires the condition
-- to hold on each of the last 3 as_of_dates (drv_technicals history) before
-- firing, and reports which line broke instead of a price:
--   price below Trade line 3 days running   -> 'TD STM' (Sell To Min)
--   price below Trend line 3 days running   -> 'TN SA'  (Sell All, wins
--                                               over TD STM if both true --
--                                               Trend break is the more
--                                               severe condition)
--   price above Trade line 3 days running   -> 'TD BMN' (Buy Min)
--   otherwise / not enough history          -> NULL
-- stop_level (the old $ price) is retired -- always NULL going forward, left
-- in place for any historical rows/exports that still reference it.
-- stop_breached keeps its existing meaning (held row, ADD/INCREASE
-- downgrade+suppress) but is now driven by stop_signal IN ('TD STM','TN SA')
-- instead of last_price < stop_level.
-- =====================================================
ALTER TABLE IF EXISTS drv_actionable
    ADD COLUMN IF NOT EXISTS stop_signal TEXT;
