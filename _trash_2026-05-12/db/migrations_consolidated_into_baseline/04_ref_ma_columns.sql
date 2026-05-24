-- Registry table for all 641 MA columns
-- Seed from docs/ma_columns_v2.csv
-- Captures both axes: pipeline_stage (left-to-right in MA) and concept (trading domain)

CREATE TABLE IF NOT EXISTS ref_ma_columns (
  column_name              TEXT PRIMARY KEY,         -- snake_case, unique across project
  excel_header            TEXT NOT NULL,            -- original Excel cell text
  excel_col_letter        TEXT NOT NULL,            -- 'JG' etc.
  excel_col_idx           INT NOT NULL,             -- 1-based column index
  pipeline_stage          TEXT NOT NULL,            -- 'lookup_identity' | 'lookup_data' | 'derived_features'
                                                    -- | 'separator' | 'atomic_input' | 'composite'
                                                    -- | 'rule_summary' | 'decision' | 'holdings'
  concept                 TEXT NOT NULL,            -- 'bollinger' | 'rsi' | 'macd' | 'ivhv' | 'volume' | ...
  drv_cat_table           TEXT NOT NULL,            -- e.g. 'drv_cat_bollinger' (= 'drv_cat_' || concept)
  drv2_table              TEXT,                     -- e.g. 'drv2_td' (NULL if pure cross-source)
  color_island_id         INT,                      -- reset whenever same color is >4 cols away
  pg_type                 TEXT NOT NULL DEFAULT 'NUMERIC',  -- 'NUMERIC' | 'TEXT' | 'DATE' | 'BOOLEAN'
  source_kind             TEXT NOT NULL DEFAULT 'passthrough',  -- 'passthrough' | 'lookup' | 'arithmetic'
                                                    -- | 'conditional' | 'aggregate' | 'static_input'
                                                    -- | 'array_formula' | 'cross_source'
  source_table            TEXT,                     -- Postgres source table for the value
  source_expr             TEXT,                     -- SQL fragment that produces the value
  excel_formula           TEXT,                     -- original Excel formula (for audit / debug)
  exposed_to_rules        BOOLEAN DEFAULT false,    -- atomic_input columns are TRUE
  exposed_to_dashboard    BOOLEAN DEFAULT true,     -- whether /api/stks should expose it
  display_label           TEXT,                     -- pretty label for UI ("BB Top (15d)")
  notes                   TEXT,
  loaded_at               TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_cat   ON ref_ma_columns(drv_cat_table);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_stage ON ref_ma_columns(pipeline_stage);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_drv2  ON ref_ma_columns(drv2_table);
CREATE INDEX IF NOT EXISTS ix_ref_ma_columns_concept ON ref_ma_columns(concept);
