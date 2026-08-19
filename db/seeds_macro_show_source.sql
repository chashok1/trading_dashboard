-- =============================================================================
-- seeds_macro_show_source.sql                                       2026-08-19
-- Adds Hedgeye "The Macro Show" daily bullish/bearish stance list
-- (hist_hedgeye_stance) as an outlook source feeding drv_outlook_action /
-- the Actionable Sources column. Previously informational-only (the
-- "Macro Show" tile in the Hedgeye action panel, web/hedgeye_panel.js) --
-- never reached the rules engine, grid Sources column, or drilldown popup.
--
-- MACROSHOW is an independent actionable source, same classifier shape as
-- RTA's long side (_action_macro_show in etl/derive_outlook_action.py):
-- bullish -> ADD/INCREASE, bearish -> REMOVE if held else silent (long-only
-- book). Unlike TOP5, it does NOT bypass the Technical-confirmation gate
-- (etl/derive_actionable.py bypass_technical) -- it's a broad daily macro
-- call, not a live per-symbol trigger, so its ADD/INCREASE still needs
-- Technical (RR) to agree for high-confidence display. Ranked lowest in
-- SOURCE_ORDER (etl/derive_actionable.py) so it never overrides a
-- dedicated per-symbol source.
--
-- lookback_days=5 mirrors RTA/SSSCHG -- a mention stays active through a
-- weekend without a trading-calendar table.
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

-- NOTE: seeds_rta_source.sql, seeds_sss_change_source.sql, and
-- seeds_top5_source.sql each also widen this same constraint -- keep this
-- list a superset of every seed file's values.
ALTER TABLE ref_outlook_source DROP CONSTRAINT IF EXISTS ref_outlook_source_base_weight_method_check;
ALTER TABLE ref_outlook_source ADD CONSTRAINT ref_outlook_source_base_weight_method_check
    CHECK (base_weight_method IN ('outlook_modifier','rank','rank_pct_delta','rta_alert','top5_alert','sss_change_alert','stance_alert'));

INSERT INTO ref_outlook_source
    (source_code, source_table, investment_priority, base_weight_method,
     base_weight_param, position_category, loads_prior_day_data,
     lookback_days, notes)
VALUES
    ('MACROSHOW', 'hist_hedgeye_stance', 11, 'stance_alert', NULL, 'RR', FALSE, 5,
     'Hedgeye Macro Show bullish/bearish stance — independent actionable source, normal Technical gate, lowest SOURCE_ORDER priority')
ON CONFLICT (source_code) DO UPDATE SET
    source_table          = EXCLUDED.source_table,
    investment_priority   = EXCLUDED.investment_priority,
    base_weight_method     = EXCLUDED.base_weight_method,
    position_category      = EXCLUDED.position_category,
    loads_prior_day_data   = EXCLUDED.loads_prior_day_data,
    lookback_days          = EXCLUDED.lookback_days,
    notes                  = EXCLUDED.notes;

COMMIT;
