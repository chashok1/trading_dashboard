-- Seeds for the GOANY source (Hedgeye 10 ETF Go-Anywhere Portfolio, 2026-10-07).
-- The email is rendered by etl/hedgeye/emit.py into "GOANY YYYY-MM-DD.xlsx" in
-- source_dir and loaded by etl/load_raw.py::load_goany, so File Monitor shows it
-- like the other file-backed feeds (ETL Runs + Today's Schedule).
-- WKDAY + optional: emails only arrive on days the portfolio changes.
-- Idempotent: safe to re-run. (LoadFiles.xlsx loads are insert-skip-duplicates,
-- so this DB-seeded row survives a workbook reload.)
INSERT INTO ref_load_files
    (source_dir, file_type, target_tab, week_day, file_time, enabled,
     optional, rows_should_match, target_table, feed_code)
SELECT 'C:\Ashok\Investing\Stocks\GOANY\Archive', 'GOANY', 'GOANY', 'WKDAY',
       TIME '10:30:00', TRUE, TRUE, FALSE, 'hist_goany', 'GO_ANYWHERE'
WHERE NOT EXISTS (SELECT 1 FROM ref_load_files WHERE LOWER(file_type) = 'goany');

-- mappings.py HIST_MAPS has no entry: the CUSTOM_HANDLERS['goany'] loader is used.
UPDATE ref_hedgeye_email_type SET feed_code = 'GO_ANYWHERE' WHERE email_type = 'go_anywhere';
