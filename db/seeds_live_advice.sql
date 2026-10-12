-- TASK_152: live advice settings (etl/derive_live_advice.py) + freshness
-- contracts for the plan / live-check tables. Idempotent; never overwrites an edit.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('overmax_any_day_ratio',   '1.25', 'Live advice: held above this x max = trim back to max on any day (MUST)'),
    ('must_overmax_ratio',      '1.25', 'Live advice: over-max ratio above which a trim-to-max is required (MUST) rather than optional'),
    ('today_floor_dollar',      '1500', 'Live advice: an account order under this is not listed (tooltip: too small to list)'),
    ('today_must_budget',       '5',    'Live advice: Do-today display budget (overflow is shown, never dropped)'),
    ('today_consider_budget',   '8',    'Live advice: Consider list size; the rest is +N more'),
    ('today_buyidea_budget',    '5',    'Live advice: Buy ideas list size (Trade Mode buys, ranked by suggested dollars)'),
    ('must_sellall_sources',    'PS,II,CALL,RTA,SSSCHG,TOP5', 'Live advice: sources whose SELL ALL on a held stock is a required action'),
    ('rank_edge_buyback',       '1.2',  'Live advice: typical 5-day edge % used to rank Consider items (buy-back)'),
    ('rank_edge_dip',           '0.8',  'Live advice: typical 5-day edge % (dip buy)'),
    ('rank_edge_sellsome',      '0.5',  'Live advice: typical 5-day edge % (sell some)'),
    ('rank_edge_trim',          '0.4',  'Live advice: typical 5-day edge % (spike trim)'),
    ('rank_edge_trim_to_max',   '0.3',  'Live advice: typical 5-day edge % (trim to max, 1.0-1.25x)'),
    ('dont_sell_low_sd',        '1.5',  'Live advice: caution when a held stock with a sell path is this many SD below prior close'),
    ('sell_bounce_sd',          '0.5',  'Live advice: sell-the-bounce limit = price at first caution + this many SD'),
    ('sell_bounce_days',        '5',    'Live advice: sell-the-bounce limit is good for this many trading days'),
    ('note_gain_pct',           '20',   'Live advice: tooltip note when gain since cost is at least this pct'),
    ('note_sector_share_pct',   '35',   'Live advice: tooltip note when a held stock sector is at least this pct of the stock book'),
    ('trim_sd',                 '1.5',  'Live advice: spike trim at prior close + this many SD20'),
    ('live_trim_trr_min_sd',    '1.0',  'Live advice: top-of-range trim leg needs price up at least this many SD'),
    ('live_overmax_sd',         '1.0',  'Live advice: over-max trim leg fires when up at least this many SD'),
    ('trim_over_max_pos_pct',   '80',   'Live advice: over-max trim leg also fires at/above this pct of the risk range'),
    ('dip_strong_sd',           '1.5',  'Live advice: Strong dip buy (buy-side call last night) at prior close - this many SD'),
    ('dip_light_sd',            '2.0',  'Live advice: Light dip buy at prior close - this many SD'),
    ('buyback_sd',              '0.5',  'Live advice: buy-back line = your sell price - this many SD'),
    ('buyback_days',            '5',    'Live advice: buy-back window in trading days after your sale'),
    ('buyback_bounce_sd',       '0.25', 'Live advice: same-day buy-back needs price this many SD above the day low'),
    ('live_min_sd_pct',         '0.5',  'Live advice: SD20 under this pct = skip price rules (cash-like funds)'),
    ('live_sd_cap_mult',        '3',    'Live advice: SD20 above this x its 60-day median uses the median'),
    ('live_sd_min_moves',       '15',   'Live advice: fewer daily moves than this = no price rules'),
    ('live_price_stale_min',    '45',   'Live advice: a price older than this many minutes is stale (no new fires)'),
    ('chase_day_range_pct',     '80',   'Live advice: chase tag when price is in the top (100-x) pct of the day range'),
    ('chase_risk_range_pct',    '90',   'Live advice: chase tag when price is at/above this pct of the risk range'),
    ('plan_freeze_et',          '09:30','Live advice: the night plan is frozen from this ET time on its plan date')
ON CONFLICT (setting_name) DO NOTHING;

INSERT INTO ref_freshness_contract
    (table_name, date_column, max_lag_days, maturity_lag_days, refreshed_by, screen, severity)
VALUES
    ('hist_advice_plan', 'plan_date', 5, 0, 'derive_all (derive_live_advice.build_plan)', 'actionable', 'warning'),
    ('hist_advice_live', 'plan_date', 5, 0, 'yahoo_fetch.fetch_hourly_quotes (derive_live_advice.run_live_check)', 'actionable', 'warning')
ON CONFLICT (table_name) DO NOTHING;
