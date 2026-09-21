-- =====================================================
-- seeds_freshness_contract.sql — TASK_142: which computed analytics tables
-- have a freshness contract, and who is supposed to keep them current.
-- Applied by db/init_db.py after baseline.sql creates ref_freshness_contract.
-- Idempotent: ON CONFLICT DO NOTHING (existing customisations survive re-run).
--
-- `maturity_lag_days` is the *expected* structural lag (e.g. a 20-trading-day
-- forward return needs 20 future days of price before it can exist at all) —
-- without it the check would fire every day. `ref_vlm_intraday_curve` has no
-- as_of_date; `updated_at` (a timestamp) is used instead — see baseline.sql.
-- =====================================================

INSERT INTO ref_freshness_contract
    (table_name, date_column, max_lag_days, maturity_lag_days, refreshed_by, screen, severity)
VALUES
    ('drv_rule_outcome',      'as_of_date', 3, 30, 'scheduler.run_nightly_outcomes', 'rule-performance', 'warning'),
    ('drv_factor_snapshot',   'as_of_date', 3, 30, 'scheduler.run_nightly_outcomes', 'rule-performance', 'warning'),
    ('drv_inferred_action',   'as_of_date', 3, 30, 'scheduler.run_nightly_outcomes', 'rule-performance', 'warning'),
    ('ref_vlm_intraday_curve','updated_at', 7, 0,  'scheduler.run_nightly_outcomes', 'actionable',       'warning'),
    ('drv_market_stat',       'as_of_date', 2, 0,  'derive_all',                     'actionable',       'warning'),
    ('drv_pvv',               'as_of_date', 3, 0,  'derive_all',                     'actionable',       'warning')
ON CONFLICT (table_name) DO NOTHING;
