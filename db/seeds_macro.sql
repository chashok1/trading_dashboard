-- =====================================================
-- seeds_macro.sql — FRED series catalog for the macro feed
-- Applied automatically by db/init_db.py (runs all db/*.sql in order;
-- "seeds_macro" sorts after "baseline" so ref_macro_series exists first).
-- Idempotent: ON CONFLICT DO UPDATE so edits here propagate on re-run.
-- Tune freely: add/remove rows, flip enabled, reorder. Then:
--     python -m db.init_db
--     python -m etl.fetch_macro
-- All series are free from https://fred.stlouisfed.org (one free API key).
-- =====================================================

INSERT INTO ref_macro_series (series_id, label, grp, unit, sort_order, enabled) VALUES
    -- Rates & yield curve --------------------------------------------------
    ('DGS10',        '10Y Treasury',        'rates',     '%',     10, TRUE),
    ('DGS2',         '2Y Treasury',         'rates',     '%',     20, TRUE),
    ('DGS3MO',       '3M Treasury',         'rates',     '%',     30, TRUE),
    ('T10Y2Y',       '10Y-2Y spread',       'rates',     '%',     40, TRUE),
    ('DFF',          'Fed funds (eff)',     'rates',     '%',     50, TRUE),
    -- Inflation ------------------------------------------------------------
    ('CPIAUCSL',     'CPI (headline)',      'inflation', 'index', 10, TRUE),
    ('CPILFESL',     'Core CPI',            'inflation', 'index', 20, TRUE),
    ('PCEPILFE',     'Core PCE',            'inflation', 'index', 30, TRUE),
    ('T10YIE',       '10Y breakeven',       'inflation', '%',     40, TRUE),
    -- Jobs & growth --------------------------------------------------------
    ('UNRATE',       'Unemployment',        'jobs',      '%',     10, TRUE),
    ('PAYEMS',       'Nonfarm payrolls',    'jobs',      'k',     20, TRUE),
    ('ICSA',         'Initial claims',      'jobs',      'count', 30, TRUE),
    -- Risk & financial conditions -----------------------------------------
    ('VIXCLS',       'VIX',                 'risk',      'index', 10, FALSE),
    ('BAMLH0A0HYM2', 'HY credit spread',    'risk',      '%',     20, TRUE),
    ('NFCI',         'Fin conditions (NFCI)','risk',     'index', 30, TRUE),
    -- Equity indexes (EOD level; ~1 day lag) ------------------------------
    ('SP500',        'S&P 500',             'index',     'index', 10, FALSE),
    ('NASDAQCOM',    'Nasdaq Composite',    'index',     'index', 20, FALSE),
    ('DJIA',         'Dow Jones',           'index',     'index', 30, FALSE),
    ('RU2000PR',     'Russell 2000',        'index',     'index', 40, FALSE), -- retired FRED id (HTTP 400)
    -- Dollar & commodities -------------------------------------------------
    ('DTWEXBGS',     'Trade-wtd USD',       'fx_cmdty',  'index', 10, FALSE),
    ('DCOILWTICO',   'WTI crude',           'fx_cmdty',  '$',     20, FALSE)
ON CONFLICT (series_id) DO UPDATE SET
    label      = EXCLUDED.label,
    grp        = EXCLUDED.grp,
    unit       = EXCLUDED.unit,
    sort_order = EXCLUDED.sort_order,
    enabled    = EXCLUDED.enabled;

-- Tunable throttle window for etl/fetch_macro.py (minutes). The fetcher refuses
-- to call FRED if a real run started within this window (override with --force).
-- DO NOTHING so your tuned value survives re-running db.init_db; change it with
--   UPDATE ref_settings SET setting_value='120' WHERE setting_name='macro_fetch_min_interval_min';
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('macro_fetch_min_interval_min', '360',
     'Min minutes between FRED macro fetches (etl/fetch_macro.py throttle); --force overrides')
ON CONFLICT (setting_name) DO NOTHING;
