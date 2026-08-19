-- =============================================================================
-- seeds_top5_source.sql                                             2026-07-18
-- Adds Hedgeye's daily Top-5 most-actionable list (hist_call_top5) as an
-- outlook source feeding drv_outlook_action / the Actionable Sources column.
--
-- UPDATED 2026-08-19: TOP5 is now an independent actionable source (user
-- decision "TOP5 acts like RTA") — same classifier shape as RTA's long
-- side (_action_top5 in etl/derive_outlook_action.py): long bias ->
-- ADD/INCREASE, short bias -> REMOVE if held else silent. It also bypasses
-- the Technical-confirmation gate like RTA (etl/derive_actionable.py
-- bypass_technical). Top-5 is drawn from the same Hedgeye "Call" email
-- that already feeds the CALL source's own 30-day standing model, but the
-- two are treated as fully independent — no special tie-break, plain
-- SOURCE_ORDER (etl/derive_actionable.py) decides the winner if they
-- disagree same-day. Ranked just under RTA in SOURCE_ORDER.
--
-- lookback_days=10: a symbol's most recent Top-5 appearance in the trailing
-- 10 days is what shows, so the badge persists briefly rather than
-- disappearing the day after it's no longer listed.
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

-- NOTE: seeds_rta_source.sql, seeds_sss_change_source.sql, and
-- seeds_macro_show_source.sql each also widen this same constraint -- keep
-- this list a superset of every seed file's values.
ALTER TABLE ref_outlook_source DROP CONSTRAINT IF EXISTS ref_outlook_source_base_weight_method_check;
ALTER TABLE ref_outlook_source ADD CONSTRAINT ref_outlook_source_base_weight_method_check
    CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta','rta_alert','top5_alert','sss_change_alert','stance_alert'));

INSERT INTO ref_outlook_source
    (source_code, source_table, investment_priority, base_weight_method,
     base_weight_param, position_category, loads_prior_day_data,
     lookback_days, notes)
VALUES
    ('TOP5', 'hist_call_top5', 1, 'top5_alert', NULL, 'Call', FALSE, 10,
     'Hedgeye Top 5 most-actionable list — independent actionable source (acts like RTA), bypasses Technical gate')
ON CONFLICT (source_code) DO UPDATE SET
    source_table          = EXCLUDED.source_table,
    investment_priority   = EXCLUDED.investment_priority,
    base_weight_method     = EXCLUDED.base_weight_method,
    position_category      = EXCLUDED.position_category,
    loads_prior_day_data   = EXCLUDED.loads_prior_day_data,
    lookback_days          = EXCLUDED.lookback_days,
    notes                  = EXCLUDED.notes;

COMMIT;
