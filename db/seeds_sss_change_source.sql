-- =============================================================================
-- seeds_sss_change_source.sql                                       2026-07-19
-- Adds SSSCHG (Signal Strength Stocks change events, Gmail) as an outlook
-- source feeding drv_outlook_action / the Actionable Sources column.
--
-- hist_sss_change captures the daily "Signal Strength Stocks" email's
-- Added/Removed lines (etl/hedgeye/parsers.py::parse_signal_strength,
-- flagged delta_only) -- previously informational-only (Hedgeye action
-- panel), never reaching the rules engine. The file-based SSS source
-- (hist_sss, weekly SSS tab) already emits ADD/REMOVE symmetrically but
-- only catches changes between its own weekly snapshots -- a same-day
-- Gmail add/remove between snapshots was invisible to the engine.
--
-- SSSCHG is modeled on RTA: same-day event trigger, bypasses the Technical
-- gate on the buy side (etl/derive_actionable.py bypass_technical), same
-- top SOURCE_ORDER tier so it always overrides the (potentially stale)
-- weekly SSS source until SSS's next snapshot catches up (user decision
-- 2026-07-19).
-- Safe to run multiple times. Picked up by db.init_db (db/*.sql glob).
-- =============================================================================
BEGIN;

-- NOTE: seeds_rta_source.sql, seeds_top5_source.sql, and
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
    ('SSSCHG', 'hist_sss_change', 0, 'sss_change_alert', NULL, 'Sig', FALSE, 5,
     'Signal Strength Stocks change event (Gmail Added/Removed) — same precedence as RTA, same-day trigger')
ON CONFLICT (source_code) DO UPDATE SET
    source_table          = EXCLUDED.source_table,
    investment_priority   = EXCLUDED.investment_priority,
    base_weight_method     = EXCLUDED.base_weight_method,
    position_category      = EXCLUDED.position_category,
    loads_prior_day_data   = EXCLUDED.loads_prior_day_data,
    lookback_days          = EXCLUDED.lookback_days,
    notes                  = EXCLUDED.notes;

COMMIT;
