-- =============================================================================
-- seeds_top5_source.sql                                             2026-07-18
-- Adds Hedgeye's daily Top-5 most-actionable list (hist_call_top5) as an
-- outlook source feeding drv_outlook_action / the Actionable Sources column.
--
-- TOP5 is informational only, same pattern as RTAINFO (see
-- db/seeds_rta_source.sql): it never drives ADD/REMOVE/REDUCE, always
-- resolves to HOLD tagged with the day's long/short bias. Top-5 is drawn
-- from the same Hedgeye "Call" email that already feeds the CALL source's
-- own 30-day standing model -- adding it as a second scoring source risks
-- the two disagreeing on the same call, so it's kept as a visible badge
-- (which symbols made today's most-emphasized list) rather than a second
-- vote on the action. Ranked lowest in SOURCE_ORDER (etl/derive_actionable.py)
-- so it never masks a real signal from another source.
--
-- lookback_days=10: a symbol's most recent Top-5 appearance in the trailing
-- 10 days is what shows, so the badge persists briefly rather than
-- disappearing the day after it's no longer listed.
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

ALTER TABLE ref_outlook_source DROP CONSTRAINT IF EXISTS ref_outlook_source_base_weight_method_check;
ALTER TABLE ref_outlook_source ADD CONSTRAINT ref_outlook_source_base_weight_method_check
    CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta','rta_alert','top5_alert'));

INSERT INTO ref_outlook_source
    (source_code, source_table, investment_priority, base_weight_method,
     base_weight_param, position_category, loads_prior_day_data,
     lookback_days, notes)
VALUES
    ('TOP5', 'hist_call_top5', 10, 'top5_alert', NULL, 'Call', FALSE, 10,
     'Hedgeye Top 5 most-actionable list — informational only, always HOLD')
ON CONFLICT (source_code) DO UPDATE SET
    source_table          = EXCLUDED.source_table,
    investment_priority   = EXCLUDED.investment_priority,
    base_weight_method     = EXCLUDED.base_weight_method,
    position_category      = EXCLUDED.position_category,
    loads_prior_day_data   = EXCLUDED.loads_prior_day_data,
    lookback_days          = EXCLUDED.lookback_days,
    notes                  = EXCLUDED.notes;

COMMIT;
