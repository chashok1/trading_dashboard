-- =============================================================================
-- 03_schema_meta.sql
-- Meta tables for ETL run tracking, dedupe, retention.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- meta_etl_run  - one row per ETL invocation (per file)
-- ---------------------------------------------------------------------------
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
    status        TEXT,        -- 'running' | 'success' | 'error'
    error_msg     TEXT
);
CREATE INDEX IF NOT EXISTS ix_meta_etl_run_started ON meta_etl_run(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_meta_etl_run_file ON meta_etl_run(file_path);

-- ---------------------------------------------------------------------------
-- meta_file_processed - prevents re-processing identical files
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_file_processed (
    file_path     TEXT PRIMARY KEY,
    file_hash     TEXT NOT NULL,
    file_type     TEXT,
    target_tab    TEXT,
    file_date     DATE,        -- date parsed from filename "{type} YYYY-MM-DD.xlsx"
    processed_at  TIMESTAMP NOT NULL DEFAULT now(),
    last_run_id   BIGINT REFERENCES meta_etl_run(run_id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- meta_cleanup_policy - per-table retention rules
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_cleanup_policy (
    table_name      TEXT PRIMARY KEY,
    date_column     TEXT NOT NULL,           -- column name to use as cutoff
    retention_days  INTEGER NOT NULL DEFAULT 365,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- meta_cleanup_history - audit of every cleanup run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_cleanup_history (
    cleanup_id          BIGSERIAL PRIMARY KEY,
    table_name          TEXT NOT NULL,
    deleted_before_date DATE NOT NULL,
    rows_deleted        INTEGER NOT NULL,
    run_at              TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meta_cleanup_history_table ON meta_cleanup_history(table_name, run_at DESC);

-- ---------------------------------------------------------------------------
-- Seed default cleanup policies for every history table.
-- ---------------------------------------------------------------------------
INSERT INTO meta_cleanup_policy (table_name, date_column, retention_days, enabled, notes) VALUES
    ('hist_y',        'snapshot_date', 365, TRUE,  'Yahoo daily quotes'),
    ('hist_tl',       'snapshot_date', 365, TRUE,  'TOS Latest'),
    ('hist_td',       'snapshot_date', 365, TRUE,  'TOS Daily'),
    ('hist_tw',       'snapshot_date', 365, TRUE,  'TOS Weekly'),
    ('hist_to',       'snapshot_date', 730, TRUE,  'TOS Other (fundamentals - 2 years)'),
    ('hist_rr',       'snapshot_date', 365, TRUE,  'Risk Range'),
    ('hist_call',     'snapshot_date', 365, TRUE,  'Call signals'),
    ('hist_etf',      'snapshot_date', 730, TRUE,  'ETF outlook (2 years)'),
    ('hist_etfchg',   'event_date',    1825,TRUE,  'ETF change events (5 years)'),
    ('hist_ii',       'snapshot_date', 730, TRUE,  'Investment Ideas (2 years)'),
    ('hist_iichg',    'event_date',    1825,TRUE,  'II change events (5 years)'),
    ('hist_ssh',      'snapshot_date', 365, TRUE,  'Signal Strength current week (raw cols only)'),
    ('hist_call',     'snapshot_date', 365, TRUE,  'Call signals (raw cols only)'),
    ('hist_etf',      'snapshot_date', 730, TRUE,  'ETF entries (raw cols only - 2y)'),
    ('hist_ii',       'snapshot_date', 730, TRUE,  'Investment Ideas (raw cols only - 2y)'),
    ('hist_psrk',     'snapshot_date', 730, TRUE,  'Price strength rank'),
    ('hist_ps5',      'snapshot_date', 365, TRUE,  '5-day lookback'),
    ('hist_pstn',     'snapshot_date', 365, TRUE,  'Trend lookback'),
    ('hist_f',        'snapshot_date', 1825,TRUE,  'Fidelity holdings (5 years)'),
    ('hist_cs',       'snapshot_date', 1825,TRUE,  'Schwab holdings (5 years)')
ON CONFLICT (table_name) DO NOTHING;
