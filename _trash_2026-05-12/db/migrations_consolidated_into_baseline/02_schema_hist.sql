-- =============================================================================
-- 02_schema_hist.sql
-- History tables (append-only, one row per snapshot_date / symbol).
-- All statements idempotent. PKs include snapshot_date so dupes are skipped.
-- All include loaded_at + source_file for traceability.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- hist_y  <- Y tab (Yahoo)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_y (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
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

-- ---------------------------------------------------------------------------
-- hist_tl  <- TL tab (TOS Latest) - RAW columns only (cols I-T).
-- Derived cols A,B,C,D,G,H live in drv_tl (06_schema_drv.sql).
-- E,F are duplicates of I,J - dropped.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_tl (
    snapshot_date        DATE NOT NULL,        -- from I (Export Date)
    symbol               TEXT NOT NULL,        -- from K (Symbol)
    sequence             INTEGER NOT NULL,     -- from J (Export Time as HHMM int)
    export_date          DATE,                 -- raw I
    export_time          TEXT,                 -- raw J as text
    last_price           NUMERIC,              -- L
    net_chng             NUMERIC,              -- M
    change_pct           NUMERIC,              -- N
    open_price           NUMERIC,              -- O
    high_price           NUMERIC,              -- P
    low_price            NUMERIC,              -- Q
    volume               BIGINT,               -- R (raw exchange volume)
    rsi                  NUMERIC,              -- S
    imp_volatility_raw   NUMERIC,              -- T (may be string "NaN" - cleaned in drv_tl)
    loaded_at            TIMESTAMP NOT NULL DEFAULT now(),
    source_file          TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_tl_symbol ON hist_tl(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_td  <- TD tab (TOS Daily) - RAW columns only (cols AM-BI).
-- Derived cols A-AL (BB bands family, IV/HV percentiles, RSI variants,
-- d_hv/d_iv families, d_vlt_*) live in drv_td (06_schema_drv.sql).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_td (
    snapshot_date       DATE NOT NULL,         -- from AM (Export Date)
    symbol              TEXT NOT NULL,         -- from AO (Symbol)
    sequence            INTEGER NOT NULL,      -- from AN (Export Time)
    export_date         DATE,                  -- raw AM
    export_time         TEXT,                  -- raw AN
    last_price          NUMERIC,               -- AP
    net_chng            NUMERIC,               -- AQ
    change_pct          NUMERIC,               -- AR
    open_price          NUMERIC,               -- AS
    high_price          NUMERIC,               -- AT
    low_price           NUMERIC,               -- AU
    rsi                 NUMERIC,               -- AV
    historical_vol      NUMERIC,               -- AW
    imp_volatility      NUMERIC,               -- AX
    a_trend_value       NUMERIC,               -- AY (raw export)
    a_trade_value       NUMERIC,               -- AZ
    a_bb_bottom         NUMERIC,               -- BA
    a_bb_top            NUMERIC,               -- BB
    a_bb_streak         NUMERIC,               -- BC
    a_bb_high_low       NUMERIC,               -- BD
    a_bb_high_low_days  NUMERIC,               -- BE
    a_iv_percentile     NUMERIC,               -- BF
    a_hv_percentile     NUMERIC,               -- BG
    a_bb_top_slope      NUMERIC,               -- BH
    a_bb_bot_slope      NUMERIC,               -- BI
    loaded_at           TIMESTAMP NOT NULL DEFAULT now(),
    source_file         TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_td_symbol ON hist_td(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_tw  <- TW tab (TOS Weekly) - RAW columns only (cols Y-BC).
-- Derived cols A-X (W_Vlm projection, W_Vlm_Expn_Ratio, W_%Change_Wk,
-- W_Vlm_RuleDesc, A_MACD_BRR, A_MACDH_D_BRR, EarningsDays, etc.)
-- live in drv_tw (06_schema_drv.sql).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_tw (
    snapshot_date       DATE NOT NULL,         -- from Y (Export Date)
    symbol              TEXT NOT NULL,         -- from AA (Symbol)
    sequence            INTEGER NOT NULL,      -- from Z (Export Time)
    export_date         DATE,                  -- raw Y
    export_time         TEXT,                  -- raw Z
    last_price          NUMERIC,               -- AB
    change_pct          NUMERIC,               -- AC
    sector              TEXT,                  -- AD
    beta                NUMERIC,               -- AE
    standard_dev        NUMERIC,               -- AF
    fcf_per_share       NUMERIC,               -- AG
    high_52             NUMERIC,               -- AH
    low_52              NUMERIC,               -- AI
    sma_20              NUMERIC,               -- AJ
    sma_50              NUMERIC,               -- AK
    sma_200             NUMERIC,               -- AL
    a_macdays_streak    NUMERIC,               -- AM
    a_macd_brr1         NUMERIC,               -- AN
    a_macdh_d_brr1      NUMERIC,               -- AO
    volume              BIGINT,                -- AP (raw exchange volume)
    a_volume_spike      NUMERIC,               -- AQ
    volume_avg_10d      NUMERIC,               -- AR
    volume_avg_3m       NUMERIC,               -- AS
    volume_rate_change  NUMERIC,               -- AT
    a_perf_2m           NUMERIC,               -- AU
    a_perf_2wk          NUMERIC,               -- AV
    a_perf_3d           NUMERIC,               -- AW
    a_3mn_high          NUMERIC,               -- AX
    a_3mn_low           NUMERIC,               -- AY
    a_3mn_high_low      NUMERIC,               -- AZ
    a_3wk_high_low      NUMERIC,               -- BA
    a_earnings_days     NUMERIC,               -- BB
    market_cap_str      TEXT,                  -- BC
    loaded_at           TIMESTAMP NOT NULL DEFAULT now(),
    source_file         TEXT,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
CREATE INDEX IF NOT EXISTS ix_hist_tw_symbol ON hist_tw(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_to  <- TO tab (TOS Other - fundamentals)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- hist_call  <- call tab (RAW imported cols S-V only).
-- Derived cols A-R (key, weight, entry/cont actions, lookups) live in drv_call.
-- DROP removed 2026-05-10: it emptied this table on every db.init_db run, and
-- combined with the _already_loaded() skip in tickers_initial_load to leave
-- hist_call empty until meta_etl_run was manually cleared.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_call (
    snapshot_date    DATE NOT NULL,         -- from S (Imported Date)
    symbol           TEXT NOT NULL,         -- from T (Symbol)
    outlook          TEXT,                  -- from U (Outlook)  e.g. BULLISH/BEARISH
    outlook_modifier TEXT,                  -- from V (Outlook Modifier) e.g. long/short
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_call_symbol ON hist_call(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_etf  <- etf tab (RAW imported cols R-AA only).
-- Derived cols A-Q (key, weight, entry/cont actions, change, lookups) -> drv_etf.
-- DROP removed 2026-05-10 — see hist_call note above.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_etf (
    snapshot_date    DATE NOT NULL,         -- from R (Imported Date)
    symbol           TEXT NOT NULL,         -- from T (Ticker)
    sector           TEXT,                  -- from S
    date_added       DATE,                  -- from U
    recent_price     NUMERIC,               -- from V
    brr              NUMERIC,               -- from W
    trr              NUMERIC,               -- from X
    asset_class      TEXT,                  -- from Y
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_etf_symbol ON hist_etf(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_ii  <- II tab (RAW imported cols O-T only).
-- Derived cols A-N (key, weight, entry/cont actions, change) -> drv_ii.
-- DROP removed 2026-05-10 — see hist_call note above.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ii (
    snapshot_date    DATE NOT NULL,         -- from O (Imported Date)
    symbol           TEXT NOT NULL,         -- from Q (Ticker)
    outlook          TEXT,                  -- from P
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_ii_symbol ON hist_ii(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_ssh  <- ssH tab (RAW imported cols S-AB only).
-- Derived cols A-R (key, ranks, signal, signal_sign, lookups) -> drv_ssh.
-- DROP removed 2026-05-10 — see hist_call note above.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ssh (
    snapshot_date         DATE NOT NULL,    -- from S (Imported Date)
    symbol                TEXT NOT NULL,    -- from U (Ticker)
    days_on               INTEGER,          -- from T
    signal_date           DATE,             -- from V
    prior_close           NUMERIC,          -- from W
    last_close            NUMERIC,          -- from X
    pct_delta             NUMERIC,          -- from Y
    sector                TEXT,             -- from Z
    analyst               TEXT,             -- from AA
    anlst_best_idea_rank  TEXT,             -- from AB
    loaded_at             TIMESTAMP NOT NULL DEFAULT now(),
    source_file           TEXT,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_ssh_symbol ON hist_ssh(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_rr  <- RR tab (Risk Range)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_rr (
    snapshot_date    DATE NOT NULL,
    symbol           TEXT NOT NULL,
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

-- (hist_call moved above; raw cols only.)

-- ---------------------------------------------------------------------------
-- hist_f  <- F tab (Fidelity holdings)
-- ---------------------------------------------------------------------------
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
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, account_number, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_f_symbol ON hist_f(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- hist_cs  <- CS tab (Charles Schwab holdings)
-- ---------------------------------------------------------------------------
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
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    source_file       TEXT,
    PRIMARY KEY (snapshot_date, account, symbol)
);
CREATE INDEX IF NOT EXISTS ix_hist_cs_symbol ON hist_cs(symbol, snapshot_date);

-- (hist_etf moved above; raw cols only.)

-- ---------------------------------------------------------------------------
-- hist_etfchg  <- etfchg tab
-- HISTORY of per-stock weekly UPDATES to entries originally in hist_etf.
-- Same shape/cadence as hist_etf; tracks subsequent changes (action, weight
-- delta) to a stock that was previously entered.
-- ---------------------------------------------------------------------------
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

-- (hist_ii moved above; raw cols only.)

-- ---------------------------------------------------------------------------
-- hist_iichg  <- IIchg tab
-- HISTORY of per-stock weekly UPDATES to entries originally in hist_ii.
-- Same shape/cadence as hist_ii; tracks subsequent changes to an Investment
-- Idea that was previously entered.
-- ---------------------------------------------------------------------------
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

-- (hist_ssh moved above; raw cols only.)

-- ssL and sss are DERIVED tables - see drv_ssl and drv_sss in 06_schema_drv.sql
-- (Signal Strength Last-week and Signal Strength Series are computed from
-- hist_ssh, not loaded directly from raw sources.)

-- ---------------------------------------------------------------------------
-- hist_psrk  <- psRk tab (price strength rank)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_psrk (
    snapshot_date    DATE NOT NULL,
    ticker           TEXT NOT NULL,
    rank             NUMERIC,
    wk_ago           NUMERIC,
    mn_ago           NUMERIC,
    date_added       DATE,
    asset_class      TEXT,
    minimum          NUMERIC,
    maximum          NUMERIC,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, ticker)
);

-- ---------------------------------------------------------------------------
-- hist_ps5  <- ps5 tab (5-day lookback)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_ps5 (
    snapshot_date    DATE NOT NULL,
    ticker           TEXT NOT NULL,
    day1             NUMERIC,
    day2             NUMERIC,
    day3             NUMERIC,
    day4             NUMERIC,
    day5             NUMERIC,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, ticker)
);

-- ---------------------------------------------------------------------------
-- hist_pstn  <- psTn tab (trend lookback)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_pstn (
    snapshot_date    DATE NOT NULL,
    ticker           TEXT NOT NULL,
    today            NUMERIC,
    one_day_ago      NUMERIC,
    one_week_ago     NUMERIC,
    one_month_ago    NUMERIC,
    three_months_ago NUMERIC,
    loaded_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_file      TEXT,
    PRIMARY KEY (snapshot_date, ticker)
);

-- ISMH is REFERENCE data (periodically updated, similar to Data tab)
-- - see ref_ismh in 01_schema_ref.sql.
