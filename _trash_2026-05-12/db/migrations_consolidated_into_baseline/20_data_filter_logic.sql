-- =============================================================================
-- 20_data_filter_logic.sql
-- Registry of how each data table is filtered when displayed on /explore (DB Data).
-- Single source of truth for filter rules — add a row here when introducing a
-- new history/derived table to make it browseable from the Data Explorer.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ref_data_filter_logic (
    table_name   TEXT PRIMARY KEY,
    filter_type  TEXT NOT NULL,   -- See CHECK below
    date_column  TEXT,            -- NULL only when filter_type = 'NO_FILTER'
    window_days  INTEGER,         -- Required when filter_type IN ('WINDOW_30_DAYS','WINDOW_14_DAYS')
    description  TEXT,            -- Free-form note explaining why this filter is right
    loaded_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT filter_type_check CHECK (
      filter_type IN ('EXACT_MATCH','LATEST_BEFORE','LATEST_ON_OR_BEFORE',
                      'WINDOW_30_DAYS','WINDOW_14_DAYS','NO_FILTER')
    )
);

-- Seed: keep this in sync with new tables added to the ETL.
INSERT INTO ref_data_filter_logic (table_name, filter_type, date_column, window_days, description) VALUES
  ('hist_y',       'EXACT_MATCH',         'snapshot_date', NULL, 'Yahoo quote snapshot — one row per day'),
  ('hist_tl',      'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Latest intra-day quotes'),
  ('hist_td',      'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Daily snapshot'),
  ('hist_tw',      'EXACT_MATCH',         'snapshot_date', NULL, 'TOS Weekly snapshot'),
  ('drv_tl',       'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_tl'),
  ('drv_td',       'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_td'),
  ('drv_tw',       'EXACT_MATCH',         'snapshot_date', NULL, 'Derived from hist_tw'),
  ('hist_to',      'LATEST_BEFORE',       'snapshot_date', NULL, 'TOS Other / fundamentals — most recent edition before as-of'),
  ('hist_rr',      'LATEST_BEFORE',       'snapshot_date', NULL, 'Risk Range — weekly update'),
  ('hist_f',       'LATEST_BEFORE',       'snapshot_date', NULL, 'Fidelity holdings'),
  ('hist_cs',      'LATEST_BEFORE',       'snapshot_date', NULL, 'Schwab holdings'),
  ('hist_etf',     'LATEST_BEFORE',       'snapshot_date', NULL, 'ETF entries'),
  ('hist_ii',      'LATEST_BEFORE',       'snapshot_date', NULL, 'Investment Ideas'),
  ('hist_psrk',    'LATEST_BEFORE',       'snapshot_date', NULL, 'Price Strength Rank'),
  ('hist_ssh',     'LATEST_BEFORE',       'snapshot_date', NULL, 'Signal Strength High'),
  ('hist_etfchg',  'LATEST_BEFORE',       'event_date',    NULL, 'ETF change events'),
  ('hist_iichg',   'LATEST_BEFORE',       'event_date',    NULL, 'II change events'),
  ('hist_call',    'WINDOW_30_DAYS',      'snapshot_date', 30,   'Manual call sheet — 30-day rolling window'),
  ('drv_ssh',      'LATEST_ON_OR_BEFORE', 'snapshot_date', NULL, 'Derived SSH — same-day allowed')
ON CONFLICT (table_name) DO UPDATE SET
  filter_type = EXCLUDED.filter_type,
  date_column = EXCLUDED.date_column,
  window_days = EXCLUDED.window_days,
  description = EXCLUDED.description,
  loaded_at   = now();
