-- TASK_151: per-account sizing seeds. Idempotent and never overwrites a
-- /ref edit: size_mult is only seeded while no account has a multiplier yet.
UPDATE ref_accounts SET size_mult = CASE short_name
        WHEN 'IRA' THEN 1 WHEN 'F-A' THEN 2 WHEN 'F-M' THEN 1 ELSE 0 END
 WHERE short_name IN ('IRA','F-A','F-M')
   AND NOT EXISTS (SELECT 1 FROM ref_accounts WHERE size_mult > 0);

UPDATE ref_asset_allocation SET units_pct = units / 400000
 WHERE units_pct IS NULL AND units IS NOT NULL;

INSERT INTO ref_freshness_contract
    (table_name, date_column, max_lag_days, maturity_lag_days, refreshed_by, screen, severity)
VALUES
    ('drv_account_size', 'as_of_date', 3, 0, 'derive_all', 'actionable', 'warning')
ON CONFLICT (table_name) DO NOTHING;
