-- 2026-10-12: risk-range zone widths for the Technical "at LRR / at TRR / at midpoint" tests
-- (etl/derive_cat_atomic_input.py). Fractions of the LRR-TRR range. Idempotent; never overwrites an edit.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('range_lrr_zone_pct', '0.25', 'At LRR = the day low is in the bottom this fraction of the LRR-TRR range'),
    ('range_trr_zone_pct', '0.10', 'At TRR = the day high is in the top this fraction of the LRR-TRR range'),
    ('range_mid_zone_pct', '0.10', 'At midpoint = price is within +/- this fraction of the range around the middle')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-10-12: pullback size for the bull-path TRR-pullback buy (technical code 7, db/seeds_bull_rr_rule_7.sql).
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('range_pullback_pct', '0.10', 'TRR-pullback buy: price is at least this fraction of the LRR-TRR range below the day high')
ON CONFLICT (setting_name) DO NOTHING;

-- 2026-10-20, user (after a back-test, May-Oct 2026): a broken LRR support counts as a sell only when the close is
-- this many ATR below LRR. 1.5 bounced back too often; 2 is the first depth where it beat chance.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('lrr_break_atr_mult', '2', 'Broken LRR support = the close is more than this many ATR below LRR')
ON CONFLICT (setting_name) DO NOTHING;
