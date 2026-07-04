-- =====================================================
-- seeds_econ_calendar.sql — FRED release_id -> category catalog for the
-- econ calendar fetch (etl/fetch_econ_calendar.py).
-- Applied automatically by db/init_db.py.
-- Idempotent: ON CONFLICT DO UPDATE so edits here propagate on re-run.
-- Tune freely: add/remove rows, flip enabled, rename categories. Then:
--     python -m db.init_db
--     python -m etl.fetch_econ_calendar --force
--
-- Category names match the existing workbook-sourced ref_calendar_event
-- rows so both sources land in the same list with no frontend changes.
-- Not every current ref_calendar_event category has a FRED release_id —
-- ISM Mfg/Svcs, U.S. Michigan Consumer Sentiment, NAHB, Durable Goods,
-- Factory Orders, Wholesale Inventories, Pending Home Sales, and the
-- market-structure dates (Fed Meeting, FOMC Minutes, Beige Book, options/
-- futures expiration, Jackson Hole) are not tracked as FRED "releases" —
-- those stay workbook-only until/unless another source is added.
-- =====================================================

INSERT INTO ref_econ_release (release_id, category, release_name, enabled) VALUES
    (50,  'NFP',                 'Employment Situation',              TRUE),
    (50,  'Unemp Rate',          'Employment Situation',              TRUE),
    (194, 'ADP NFP',             'ADP National Employment Report',    TRUE),
    (10,  'CPI YOY',             'Consumer Price Index',              TRUE),
    (10,  'CPI MoM',             'Consumer Price Index',              TRUE),
    (10,  'CPI Core YoY',        'Consumer Price Index',              TRUE),
    (10,  'CPI Core MoM',        'Consumer Price Index',              TRUE),
    (46,  'PPI',                 'Producer Price Index',              TRUE),
    (192, 'JOLTS',               'Job Openings and Labor Turnover Survey', TRUE),
    (53,  'GDP',                 'Gross Domestic Product',            TRUE),
    (54,  'PCE',                 'Personal Income and Outlays',       TRUE),
    (9,   'Retail Sales',        'Advance Monthly Sales for Retail and Food Services', TRUE),
    (291, 'Existing Home Sales', 'Existing Home Sales',               TRUE),
    (97,  'New Home Sales',      'New Residential Sales',             TRUE),
    (148, 'Building Permits',    'Housing Units Authorized By Building Permits', TRUE),
    (148, 'MoM Building Permits','Housing Units Authorized By Building Permits', TRUE)
ON CONFLICT (release_id, category) DO UPDATE SET
    release_name = EXCLUDED.release_name,
    enabled      = EXCLUDED.enabled;

-- Tunable throttle window for etl/fetch_econ_calendar.py (minutes). Release
-- calendars are announced months ahead and essentially never change day to
-- day, so this defaults much longer than the macro *value* fetch above.
-- DO NOTHING so your tuned value survives re-running db.init_db; change it with
--   UPDATE ref_settings SET setting_value='720' WHERE setting_name='econ_calendar_fetch_min_interval_min';
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('econ_calendar_fetch_min_interval_min', '1440',
     'Min minutes between FRED release-calendar fetches (etl/fetch_econ_calendar.py throttle); --force overrides')
ON CONFLICT (setting_name) DO NOTHING;
