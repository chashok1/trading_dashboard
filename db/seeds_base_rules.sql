-- =============================================================================
-- seeds_base_rules.sql                                              2026-06-03
--
-- PHASE 2 of the rule-engine redesign (docs/rule_engine_redesign.md).
--
-- Defines reusable BASE-* sub-composites that leaf composites can nest instead of
-- re-listing the same atomic members. Coverage measured against Tickers
-- 2026-04-30.xlsx (composites sharing >=2 of the base's members):
--     BASE-Bull-Context  28 | BASE-Bull-Trend 27 | BASE-Bear-Context 26
--     BASE-Vol-Regime    24 | BASE-RR-Position  4
--
-- Design notes:
--   * BASE members are internal GATES (the base fires when all its members pass).
--     How a LEAF treats a nested base — gate vs WATCH — is set on the leaf's
--     nested-composite member, not here. So one base can be a hard gate in one
--     leaf and corroborating evidence in another.
--   * Thresholds are the dominant per-member value observed in the workbook.
--     condition_operator is explicit (bull bases >=, bear bases <=) because the
--     BASE-* codes don't match the BUY/SELL prefix the auto-operator keys on.
--   * weight_override = 10 (the gate weight) so a base member behaves identically
--     to the flat leaf gate member it replaces — including the val=0 / threshold=0
--     case, where override=10 keeps the gate-hit (returns 10) instead of returning
--     the raw 0 (which the `w != 0` gate test would read as "not hit").
--   * atomic_rule_id values are the workbook row numbers (the loader's PK).
--
-- BASE-* composites are EXEMPT from the workbook pruning pass (etl/load_raw.py),
-- so they survive Trig-tab reloads.
--
-- Idempotent. FK-safe: members whose atomic rule isn't loaded yet are skipped
-- (INSERT ... SELECT ... JOIN ref_trig_atomic_rule). Run AFTER the workbook load:
--     python -m etl.tickers_initial_load      (loads atomic rules)
--     psql -d trading -f db/seeds_base_rules.sql
--     python -m etl.rebuild_rules
-- =============================================================================

BEGIN;

-- Clean replace of all BASE-* definitions (idempotent).
DELETE FROM ref_trig_composite_mapping WHERE composite_rule_code LIKE 'BASE-%';

-- (composite_code, atomic_rule_id, threshold, operator, category, intent)
WITH base_members (composite_rule_code, atomic_rule_id, data_brkeout_from, condition_operator, category, intent_text) AS (
    VALUES
    -- BASE-Bull-Context — bullish regime gate (used by ~28 leaf composites)
    ('BASE-Bull-Context', 112,  0::numeric, '>=', 'context', 'Bullish regime: long-term outlook + 3-day perf confirm'),
    ('BASE-Bull-Context',  60,  3::numeric, '>=', 'context', 'Bullish regime: long-term outlook + 3-day perf confirm'),
    ('BASE-Bull-Context',  58,  0::numeric, '>=', 'context', 'Bullish regime: long-term outlook + 3-day perf confirm'),
    -- BASE-Bull-Trend — bullish trend structure (used by ~27)
    ('BASE-Bull-Trend',    12,  0::numeric, '>=', 'trend',   'Bullish structure: trade + trend rules and MACD-H up'),
    ('BASE-Bull-Trend',    15,  2::numeric, '>=', 'trend',   'Bullish structure: trade + trend rules and MACD-H up'),
    ('BASE-Bull-Trend',     5,  1::numeric, '>=', 'trend',   'Bullish structure: trade + trend rules and MACD-H up'),
    -- BASE-Bear-Context — bearish regime gate (used by ~26)
    ('BASE-Bear-Context', 112, -2::numeric, '<=', 'context', 'Bearish regime: weak outlook + RSI/MACD-H puts'),
    ('BASE-Bear-Context',  47, -2::numeric, '<=', 'context', 'Bearish regime: weak outlook + RSI/MACD-H puts'),
    ('BASE-Bear-Context',  81, -2::numeric, '<=', 'context', 'Bearish regime: weak outlook + RSI/MACD-H puts'),
    -- BASE-Vol-Regime — volatility regime (used by ~24; usually WATCH in leaves)
    ('BASE-Vol-Regime',    42,  3::numeric, '>=', 'volatility', 'Volatility regime: IV/HV ratio + IV rule'),
    ('BASE-Vol-Regime',    44,  0::numeric, '>=', 'volatility', 'Volatility regime: IV/HV ratio + IV rule'),
    -- BASE-RR-Position — reward/risk position (weakest cluster, ~4; review)
    ('BASE-RR-Position',   22,  3::numeric, '>=', 'rr', 'Reward/risk position vs LRR/TRR bands'),
    ('BASE-RR-Position',   27, -1::numeric, '<=', 'rr', 'Reward/risk position vs LRR/TRR bands'),
    ('BASE-RR-Position',   32,  1::numeric, '>=', 'rr', 'Reward/risk position vs LRR/TRR bands')
)
INSERT INTO ref_trig_composite_mapping
    (composite_rule_code, atomic_rule_id, member_kind, member_role,
     data_brkeout_from, condition_operator, weight_override,
     category, intent_text, active)
SELECT bm.composite_rule_code, bm.atomic_rule_id, 'atomic', 'gate',
       bm.data_brkeout_from, bm.condition_operator, 10,
       bm.category, bm.intent_text, TRUE
FROM base_members bm
JOIN ref_trig_atomic_rule a ON a.atomic_rule_id = bm.atomic_rule_id
WHERE a.deprecated_at IS NULL;

-- Report
DO $$
DECLARE n_base INTEGER; n_mem INTEGER;
BEGIN
    SELECT COUNT(DISTINCT composite_rule_code), COUNT(*) INTO n_base, n_mem
    FROM ref_trig_composite_mapping WHERE composite_rule_code LIKE 'BASE-%';
    RAISE NOTICE 'seeds_base_rules: % BASE composites, % members inserted', n_base, n_mem;
END $$;

COMMIT;
