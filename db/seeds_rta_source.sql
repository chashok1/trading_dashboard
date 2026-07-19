-- =============================================================================
-- seeds_rta_source.sql                                              2026-07-14
-- Adds Real-Time Alert (hist_rta) as an outlook source feeding drv_outlook_action
-- / the Actionable Sources column.
--
-- Split into two source_codes because RTA carries two very different signal
-- types on the same table:
--   RTA     — long-book alerts (side='long': Buy/Sell/Sell-SOME). Real,
--             actionable triggers. investment_priority puts it ahead of
--             every other source in SOURCE_ORDER (etl/derive_actionable.py)
--             so a same-day RTA alert on a held position always headlines.
--   RTAINFO — short-book alerts (side='short': Short/Cover/Cover-SOME).
--             This portfolio is long-only, so these are informational
--             sentiment only (etl/derive_outlook_action.py always emits
--             HOLD for them) — ranked lowest so they never mask a real
--             signal from another source.
--
-- lookback_days=5 (calendar) approximates "3 trading days" — an alert stays
-- active through a weekend without a trading-calendar table.
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

-- Widen the base_weight_method CHECK for existing databases (baseline.sql's
-- CREATE TABLE IF NOT EXISTS won't re-run on an already-created table).
-- NOTE: seeds_top5_source.sql and seeds_sss_change_source.sql each also
-- widen this same constraint -- every file's list must include every value
-- any seed file uses (a superset), or whichever runs last in db.init_db's
-- alphabetical glob order re-narrows it and breaks rows the others inserted.
ALTER TABLE ref_outlook_source DROP CONSTRAINT IF EXISTS ref_outlook_source_base_weight_method_check;
ALTER TABLE ref_outlook_source ADD CONSTRAINT ref_outlook_source_base_weight_method_check
    CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta','rta_alert','top5_alert','sss_change_alert'));

INSERT INTO ref_outlook_source
    (source_code, source_table, investment_priority, base_weight_method,
     base_weight_param, position_category, loads_prior_day_data,
     lookback_days, notes)
VALUES
    ('RTA',     'hist_rta', 0, 'rta_alert', NULL, 'RR', FALSE, 5,
     'Real-Time Alert, long-book (Buy/Sell/Sell-SOME) — highest precedence, same-day trigger'),
    ('RTAINFO', 'hist_rta', 9, 'rta_alert', NULL, 'RR', FALSE, 5,
     'Real-Time Alert, short-book (Short/Cover/Cover-SOME) — informational only, always HOLD')
ON CONFLICT (source_code) DO UPDATE SET
    source_table          = EXCLUDED.source_table,
    investment_priority   = EXCLUDED.investment_priority,
    base_weight_method     = EXCLUDED.base_weight_method,
    position_category      = EXCLUDED.position_category,
    loads_prior_day_data   = EXCLUDED.loads_prior_day_data,
    lookback_days          = EXCLUDED.lookback_days,
    notes                  = EXCLUDED.notes;

COMMIT;
