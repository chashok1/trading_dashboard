-- seeds_outlook_prior_day.sql
-- Mark RR as loading prior-day data (loaded 2026-05-20).
-- This allows derive_outlook_action to correctly handle comparison
-- when the current snapshot doesn't exist yet but yesterday's does.

UPDATE ref_outlook_source
SET loads_prior_day_data = TRUE
WHERE source_code = 'RR';
