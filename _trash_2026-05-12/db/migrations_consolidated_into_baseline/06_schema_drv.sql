-- =============================================================================
-- 06_schema_drv.sql
-- Derived (calculated) tables. Populated by Python in step 2 of the loader.
-- Two flavors:
--   (a) Per-row derivations: drv_tl / drv_td / drv_tw / drv_ssh
--       Same grain as their hist_* parent.
--   (b) Cross-table aggregates: drv_ma / drv_dash / drv_stks / drv_dash_summary
--       One row per (as_of_date, symbol) or per (as_of_date) for summary.
-- All include computed_at + source_run_id for traceability.
-- =============================================================================

-- =============================================================================
-- (a) Per-row derived tables
-- =============================================================================

-- ---------------------------------------------------------------------------
-- drv_tl  - per-row derivations from TL (formula columns A,B,C,D,G,H)
-- Same PK as hist_tl. One row per raw hist_tl row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_tl (
    snapshot_date         DATE NOT NULL,
    symbol                TEXT NOT NULL,
    sequence              INTEGER NOT NULL,
    -- derived numeric
    vlm_projected         NUMERIC,        -- G: full-day projected volume from R+sequence
    imp_volatility_clean  NUMERIC,        -- H: NaN -> 0, else raw T
    -- traceability
    computed_at           TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id         BIGINT,
    PRIMARY KEY (snapshot_date, symbol, sequence),
    FOREIGN KEY (snapshot_date, symbol, sequence)
        REFERENCES hist_tl(snapshot_date, symbol, sequence)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_tl_symbol ON drv_tl(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- drv_td  - per-row derivations from TD (formula columns A-AL)
-- Holds the BB band family, IV/HV percentiles, RSI variants,
-- d_hv*, d_iv*, d_ivp*, range_compression, d_iv_to_hv, d_vlt_*.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_td (
    snapshot_date     DATE NOT NULL,
    symbol            TEXT NOT NULL,
    sequence          INTEGER NOT NULL,
    -- BB band family (I-P)
    bb_bot_15d        NUMERIC,
    bb_bot_7d         NUMERIC,
    bb_bot_3d         NUMERIC,
    bb_bot_prev       NUMERIC,
    bb_top_15d        NUMERIC,
    bb_top_7d         NUMERIC,
    bb_top_3d         NUMERIC,
    bb_top_prev       NUMERIC,
    -- percentiles & compression (Q-S)
    iv_percentile     NUMERIC,
    hv_percentile     NUMERIC,
    range_compression NUMERIC,
    -- RSI variants (T-W)
    d_rsi             NUMERIC,
    d_rsi3            NUMERIC,
    d_rsi7            NUMERIC,
    d_rsi_direction   NUMERIC,
    -- HV history (X-AA)
    d_hv              NUMERIC,
    d_hv3             NUMERIC,
    d_hv7             NUMERIC,
    d_hv_direction    NUMERIC,
    -- IV history (AB-AE)
    d_iv              NUMERIC,
    d_iv3             NUMERIC,
    d_iv7             NUMERIC,
    d_iv_direction    NUMERIC,
    -- IV percentile track (AF-AI)
    d_ivp3            NUMERIC,
    d_ivp7            NUMERIC,
    d_ivp_direction   NUMERIC,
    d_ivp_max10       NUMERIC,
    -- ratios + caution rules (AJ-AL)
    d_iv_to_hv        NUMERIC,
    d_vlt_rule_code   TEXT,
    d_vlt_caution     TEXT,
    -- traceability
    computed_at       TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id     BIGINT,
    PRIMARY KEY (snapshot_date, symbol, sequence),
    FOREIGN KEY (snapshot_date, symbol, sequence)
        REFERENCES hist_td(snapshot_date, symbol, sequence)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_td_symbol ON drv_td(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- drv_tw  - per-row derivations from TW (formula columns A-X)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_tw (
    snapshot_date              DATE NOT NULL,
    symbol                     TEXT NOT NULL,
    sequence                   INTEGER NOT NULL,
    -- derived numerics
    fcf                        NUMERIC,    -- G  - typically =AG (fcf_per_share)
    sma_20_d                   NUMERIC,    -- H  - typically =AJ
    sma_50_d                   NUMERIC,    -- I  - typically =AK
    sma_200_d                  NUMERIC,    -- J  - typically =AL
    w_volume                   BIGINT,     -- K  - rolled-up weekly vol
    avg_vlm_10d_d              NUMERIC,    -- L
    avg_vlm_3m_d               NUMERIC,    -- M
    vlm_rate_change_d          NUMERIC,    -- N
    w_vlm_expn_ratio           NUMERIC,    -- O  - K / L
    w_prior_day_vlm_expn_ratio NUMERIC,    -- P
    change_pct_d               NUMERIC,    -- Q
    last_price_d               NUMERIC,    -- R
    w_price_wk_ago             NUMERIC,    -- S
    w_pct_change_wk            NUMERIC,    -- T
    w_vlm_rule_desc            TEXT,       -- U
    a_macd_brr                 NUMERIC,    -- V
    a_macdh_d_brr              NUMERIC,    -- W
    earnings_days_d            NUMERIC,    -- X
    -- traceability
    computed_at                TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id              BIGINT,
    PRIMARY KEY (snapshot_date, symbol, sequence),
    FOREIGN KEY (snapshot_date, symbol, sequence)
        REFERENCES hist_tw(snapshot_date, symbol, sequence)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_tw_symbol ON drv_tw(symbol, snapshot_date);

-- ---------------------------------------------------------------------------
-- drv_ssh  - per-row Excel-derived columns from the ssH tab (Signal Strength
-- current week). Holds rank/signal computations and lookups.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS drv_ssh CASCADE;
CREATE TABLE IF NOT EXISTS drv_ssh (
    snapshot_date     DATE NOT NULL,
    symbol            TEXT NOT NULL,
    rank_hl           NUMERIC,             -- D
    unranked          TEXT,                -- E
    signal            NUMERIC,             -- F
    anlst_best_idea   TEXT,                -- G
    rank              NUMERIC,             -- H
    total             NUMERIC,             -- I
    signal_sign       NUMERIC,             -- J
    is_latest         CHAR(1),             -- K
    latest_symbol     TEXT,                -- L
    removed_date      DATE,                -- M
    miss_ma           TEXT,                -- N
    tos_lookup        TEXT,                -- O
    ma_lookup         TEXT,                -- P
    y_lookup          TEXT,                -- Q
    vlkup             TEXT,                -- R
    computed_at       TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id     BIGINT,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date, symbol)
        REFERENCES hist_ssh(snapshot_date, symbol) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_drv_ssh_symbol ON drv_ssh(symbol, snapshot_date);

-- =============================================================================
-- (b) Cross-table aggregate derived tables
-- =============================================================================

-- ---------------------------------------------------------------------------
-- drv_ma  - master aggregation per (as_of_date, symbol).
-- For each symbol holds the latest record from each history+derived source
-- where snapshot_date <= as_of_date.
-- This is the central wide table that drv_dash and drv_stks read from.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_ma (
    as_of_date         DATE NOT NULL,
    symbol             TEXT NOT NULL,
    -- identity / classification
    description        TEXT,
    sector             TEXT,
    asset_class        TEXT,
    sub_asset_class    TEXT,
    equity_sector      TEXT,
    -- latest TL
    tl_date            DATE,
    last_price         NUMERIC,
    rsi                NUMERIC,
    imp_volatility     NUMERIC,
    volume             BIGINT,
    vlm_projected      NUMERIC,                -- from drv_tl
    -- latest TD (derived)
    td_date            DATE,
    iv_percentile      NUMERIC,
    hv_percentile      NUMERIC,
    range_compression  NUMERIC,
    d_iv_to_hv         NUMERIC,
    d_vlt_caution      TEXT,
    -- latest TD (raw)
    a_trend_value      NUMERIC,
    a_trade_value      NUMERIC,
    a_bb_top           NUMERIC,
    a_bb_bottom        NUMERIC,
    a_bb_streak        NUMERIC,
    -- latest TW (derived)
    tw_date            DATE,
    a_macd_brr         NUMERIC,
    a_macdh_d_brr      NUMERIC,
    earnings_days      NUMERIC,
    sma_20             NUMERIC,
    sma_50             NUMERIC,
    sma_200            NUMERIC,
    market_cap_str     TEXT,
    beta               NUMERIC,
    -- latest TO
    pe_ratio           NUMERIC,
    eps                NUMERIC,
    div_yield          NUMERIC,
    -- latest RR
    rr_date            DATE,
    rr_buy_trade       NUMERIC,
    rr_sell_trade      NUMERIC,
    rr_outlook         TEXT,
    rr_brr             NUMERIC,
    -- latest call
    call_outlook       TEXT,
    call_modifier      TEXT,
    call_weight        NUMERIC,
    -- latest etf
    etf_outlook        TEXT,
    etf_brr            NUMERIC,
    etf_trr            NUMERIC,
    -- latest ii
    ii_outlook         TEXT,
    ii_weight          NUMERIC,
    -- latest ssh
    ssh_signal         NUMERIC,
    ssh_signal_sign    NUMERIC,
    ssh_rank_hl        NUMERIC,
    -- holdings
    held_qty_fid       NUMERIC,
    held_qty_cs        NUMERIC,
    -- final calc (mirrors Dash V column)
    pct_brr            NUMERIC,
    -- 41 derived indicator columns
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
    -- traceability
    computed_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id      BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_ma_symbol ON drv_ma(symbol, as_of_date);

-- ---------------------------------------------------------------------------
-- drv_dash  - mirrors Dash tab. One row per (as_of_date, section, symbol).
-- Section ∈ {Volatility, Index, Sector, Commodity, Stock, Treasury, FX}
-- Adds X (lower threshold), Y (upper threshold), zone_signal (Y/N/W).
-- ---------------------------------------------------------------------------
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
    threshold_low    NUMERIC,                 -- X col on Dash
    threshold_high   NUMERIC,                 -- Y col on Dash
    zone_signal      TEXT,                    -- Z col: 'Y' below low, 'N' above high, 'W' between
    computed_at      TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id    BIGINT,
    PRIMARY KEY (as_of_date, section, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_dash_date ON drv_dash(as_of_date);

-- ---------------------------------------------------------------------------
-- drv_stks  - mirrors Stks tab. Per-symbol actionable rollup.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_stks (
    as_of_date         DATE NOT NULL,
    symbol             TEXT NOT NULL,
    description        TEXT,
    sector             TEXT,
    asset_class        TEXT,
    last_price         NUMERIC,
    a_trend_value      NUMERIC,
    a_trade_value      NUMERIC,
    pct_brr            NUMERIC,
    rr_outlook         TEXT,
    rr_brr             NUMERIC,
    call_outlook       TEXT,
    call_modifier      TEXT,
    etf_outlook        TEXT,
    ii_outlook         TEXT,
    ssh_signal_sign    NUMERIC,
    iv_percentile      NUMERIC,
    rsi                NUMERIC,
    earnings_days      NUMERIC,
    market_cap_str     TEXT,
    -- aggregated outlook (e.g. -3..+3) computed across rr/call/etf/ii/ssh
    composite_outlook  NUMERIC,
    composite_label    TEXT,
    computed_at        TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id      BIGINT,
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_stks_date ON drv_stks(as_of_date);

-- ---------------------------------------------------------------------------
-- drv_dash_summary  - top-of-dashboard KPI cards, one row per as_of_date.
-- ---------------------------------------------------------------------------
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

-- =============================================================================
-- (c) Trig (rule-engine) tables - two-phase approach.
--   Phase 1 (now): load rule definitions + composite mappings into ref tables.
--   Phase 2 (later): populate drv_trig with per-stock per-composite-rule scores.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ref_trig_atomic_rule - one row per atomic rule (Trig rows 4-118).
-- These are the building blocks. Each rule reads one MA column, compares
-- it against Brkeout-From and Brkeout-To thresholds, assigns a weight.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_atomic_rule (
    atomic_rule_id    INTEGER PRIMARY KEY,    -- row number in Trig (4..118)
    name_a            TEXT,                    -- col A "Value Column" name
    name_b            TEXT,                    -- col B "(1) Column" name
    brkeout_from      NUMERIC,                 -- col C
    brkeout_to        NUMERIC,                 -- col D
    wt_below          NUMERIC,                 -- col E (Wt - Bw (1) & (2))
    wt_between        NUMERIC,                 -- col F (Wt - Bw (2) & (3))
    wt_above          NUMERIC,                 -- col G (Wt - Abv (3))
    ma_source_sheet   TEXT,                    -- col K typically 'MA'
    ma_column_name    TEXT,                    -- col L e.g. 'MACDH Direction'
    notes             TEXT,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_trig_composite_mapping - which atomic rules feed which composite rule.
-- Composite rule codes match ref_rule_desc.rule_code (e.g. '899-SA-Trend-Breaks').
-- One row per (composite_rule_code, atomic_rule_id) where the cell has a 1.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_trig_composite_mapping (
    composite_rule_code  TEXT NOT NULL,        -- header text from Trig row 1 (cols O,Q,S,...)
    atomic_rule_id       INTEGER NOT NULL,
    weight_override      NUMERIC,              -- value from the +1 col (P,R,T,...) if present
    loaded_at            TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (composite_rule_code, atomic_rule_id),
    FOREIGN KEY (atomic_rule_id) REFERENCES ref_trig_atomic_rule(atomic_rule_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ref_trig_composite_atom
    ON ref_trig_composite_mapping(atomic_rule_id);

-- ---------------------------------------------------------------------------
-- drv_trig - per-stock per-composite-rule scores.
-- Phase 1: created empty. Phase 2: populated by derive.py.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drv_trig (
    as_of_date          DATE NOT NULL,
    symbol              TEXT NOT NULL,
    composite_rule_code TEXT NOT NULL,
    score               NUMERIC,             -- summed weight across participating atomic rules
    triggered           BOOLEAN,             -- score >= threshold(rule)
    n_atomic_hit        INTEGER,             -- how many atomic rules contributed a non-zero weight
    computed_at         TIMESTAMP NOT NULL DEFAULT now(),
    source_run_id       BIGINT,
    PRIMARY KEY (as_of_date, symbol, composite_rule_code)
);
CREATE INDEX IF NOT EXISTS ix_drv_trig_symbol      ON drv_trig(symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_trig_rule        ON drv_trig(composite_rule_code, as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_trig_triggered   ON drv_trig(as_of_date, triggered) WHERE triggered = TRUE;

-- ---------------------------------------------------------------------------
-- meta_derived_run - tracks each rebuild of derived tables.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_derived_run (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    as_of_date    DATE NOT NULL,
    target_table  TEXT NOT NULL,        -- 'drv_tl','drv_td','drv_tw','drv_ssh','drv_ma','drv_dash','drv_stks','drv_dash_summary','drv_trig'
    rows_built    INTEGER,
    status        TEXT,                 -- 'running' | 'success' | 'error'
    error_msg     TEXT,
    parent_run_id BIGINT REFERENCES meta_etl_run(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_meta_derived_run_date
    ON meta_derived_run(as_of_date, target_table);
