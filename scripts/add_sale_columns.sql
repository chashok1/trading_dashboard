-- Add sale tracking columns to hist_cs
ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS sold_date DATE;
ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS shares_sold NUMERIC;
ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS realized_gain_dollar NUMERIC;
ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS realized_gain_pct NUMERIC;

-- Add sale tracking columns to hist_f
ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS sold_date DATE;
ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS shares_sold NUMERIC;
ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS realized_gain_dollar NUMERIC;
ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS realized_gain_pct NUMERIC;
