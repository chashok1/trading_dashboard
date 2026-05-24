-- =============================================================================
-- 21_actionable.sql
-- Actionable Stocks: per-source outlook-weight pipeline + resolver + user log.
-- All statements are idempotent; safe to re-run.
-- See docs/Actionable_Stocks_Design.docx for full spec.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1) Modify existing ref_asset_allocation
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE ref_asset_allocation
    ADD COLUMN IF NOT EXISTS units                 NUMERIC,
    ADD COLUMN IF NOT EXISTS maintain_min_position BOOLEAN NOT NULL DEFAULT FALSE;

-- Seed: PS and etf categories must protect their floor
UPDATE ref_asset_allocation
SET    maintain_min_position = TRUE
WHERE  category IN ('PS', 'etf');

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) ref_my_stocks (user's watchlist; always shown in actionable grid)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ref_my_stocks (
    symbol     TEXT       PRIMARY KEY,
    added_at   TIMESTAMP  NOT NULL DEFAULT now(),
    active     CHAR(1)    NOT NULL DEFAULT 'Y',
    notes      TEXT
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3) ref_outlook_source (encodes Requirements.xlsx Sheet1 matrix)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ref_outlook_source (
    source_code          TEXT        PRIMARY KEY,
    source_table         TEXT        NOT NULL,
    investment_priority  INTEGER     NOT NULL,
    base_weight_method   TEXT        NOT NULL CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta')),
    base_weight_param    NUMERIC,
    position_category    TEXT,
    show_in_actionable   BOOLEAN     NOT NULL DEFAULT TRUE,
    deprecated_at        TIMESTAMP,
    notes                TEXT
);

-- Seed: 8 sources from the Requirements matrix
INSERT INTO ref_outlook_source
  (source_code, source_table, investment_priority, base_weight_method, base_weight_param, position_category, notes)
VALUES
  ('RR',     'hist_rr',     2, 'outlook_modifier', NULL, 'RR',   'Risk Range outlook'),
  ('CALL',   'hist_call',   1, 'outlook_modifier', NULL, 'Call', 'Manual call sheet'),
  ('ETF',    'drv_etf',     1, 'outlook_modifier', NULL, 'etf',  'ETF entries (drv has derived outlook)'),
  ('ETFCHG', 'hist_etfchg', 1, 'outlook_modifier', NULL, 'etf',  'ETF change events'),
  ('II',     'hist_ii',     1, 'outlook_modifier', NULL, 'II',   'Investment Ideas'),
  ('IICHG',  'hist_iichg',  1, 'outlook_modifier', NULL, 'II',   'II change events'),
  ('SSH',    'hist_ssh',    2, 'rank_pct_delta',     2, 'Sig',  'Signal Strength High'),
  ('PSRK',   'hist_psrk',   1, 'rank',               3, 'PS',   'Price Strength Rank')
ON CONFLICT (source_code) DO UPDATE SET
  source_table        = EXCLUDED.source_table,
  investment_priority = EXCLUDED.investment_priority,
  base_weight_method  = EXCLUDED.base_weight_method,
  base_weight_param   = EXCLUDED.base_weight_param,
  position_category   = EXCLUDED.position_category,
  notes               = EXCLUDED.notes;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4) drv_outlook_action (per-(date, symbol, source) granular result)
-- ─────────────────────────────────────────────────────────────────────────────
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
    computed_at    TIMESTAMP  NOT NULL DEFAULT now(),
    source_run_id  BIGINT,
    PRIMARY KEY (as_of_date, symbol, source_code)
);
CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_date ON drv_outlook_action(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_outlook_action_sym  ON drv_outlook_action(symbol, as_of_date);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5) drv_actionable (one row per symbol; the unified decision)
-- ─────────────────────────────────────────────────────────────────────────────
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
    PRIMARY KEY (as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_actionable_action ON drv_actionable(as_of_date, consolidated_action);
CREATE INDEX IF NOT EXISTS ix_drv_actionable_mylist ON drv_actionable(in_my_list) WHERE in_my_list IS TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6) user_action_log (forensic snapshot of decisions)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_action_log (
    id                         BIGSERIAL PRIMARY KEY,
    user_id                    TEXT NOT NULL DEFAULT 'default',
    acted_at                   TIMESTAMP NOT NULL DEFAULT now(),
    as_of_date                 DATE NOT NULL,
    symbol                     TEXT NOT NULL,
    user_action                TEXT NOT NULL CHECK (user_action IN ('DONE','SKIPPED','SNOOZED','OVERRIDDEN')),
    user_action_target         TEXT,
    snooze_until               DATE,
    user_notes                 TEXT,
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
    source_actions             JSONB NOT NULL,
    rules_engine_fires         JSONB,
    source_raw_snapshot        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_user_action_log_date_sym ON user_action_log(as_of_date, symbol);
CREATE INDEX IF NOT EXISTS ix_user_action_log_acted    ON user_action_log(created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 7) Register the new data tables in ref_data_filter_logic so /explore
--    treats them with sensible date filters
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO ref_data_filter_logic (table_name, filter_type, date_column, description)
VALUES
  ('drv_outlook_action', 'EXACT_MATCH',         'as_of_date', 'Per-source action per (date, symbol)'),
  ('drv_actionable',     'EXACT_MATCH',         'as_of_date', 'Unified actionable decision per (date, symbol)'),
  ('user_action_log',    'LATEST_ON_OR_BEFORE', 'as_of_date', 'User decisions; latest per snapshot')
ON CONFLICT (table_name) DO NOTHING