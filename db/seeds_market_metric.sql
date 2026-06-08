-- =====================================================
-- seeds_market_metric.sql — metric registry for the global market tape
-- Applied automatically by db/init_db.py (runs all db/*.sql in sorted order;
-- "seeds_market_metric" sorts after "baseline" so ref_market_metric exists first).
-- Idempotent: ON CONFLICT DO UPDATE so label/group/priority edits propagate.
-- To tune: edit rows here, then `python -m db.init_db`.
-- =====================================================

INSERT INTO ref_market_metric
    (metric_key, label, grp, source_priority, value_format, sort_order, enabled)
VALUES
    ('SPX',   'S&P 500',    'index',  '["tos:SPX","fred:SP500"]'::JSONB,       'index', 10,  TRUE),
    ('COMP',  'Nasdaq',     'index',  '["tos:$COMP","fred:NASDAQCOM"]'::JSONB,  'index', 20,  TRUE),
    ('DJI',   'Dow',        'index',  '["tos:$DJI","fred:DJIA"]'::JSONB,        'index', 30,  TRUE),
    ('RUT',   'Russell 2K', 'index',  '["tos:RUT"]'::JSONB,                     'index', 40,  TRUE),
    ('VIX',   'VIX',        'risk',   '["tos:VIX","fred:VIXCLS"]'::JSONB,       'level', 50,  TRUE),
    ('VXN',   'VXN',        'risk',   '["tos:VXN:CGI"]'::JSONB,                 'level', 55,  TRUE),
    ('US10Y', '10Y',        'rates',  '["fred:DGS10"]'::JSONB,                  'pct',   60,  TRUE),
    ('T2S10', '2s10s',      'rates',  '["fred:T10Y2Y"]'::JSONB,                 'pct',   70,  TRUE),
    ('DXY',   'Dollar',     'fx',     '["tos:$DXY","fred:DTWEXBGS"]'::JSONB,    'index', 80,  TRUE),
    ('WTI',   'Crude',      'cmdty',  '["tos:/CL","fred:DCOILWTICO"]'::JSONB,   'price', 90,  TRUE),
    ('HY',    'HY spread',  'credit', '["fred:BAMLH0A0HYM2"]'::JSONB,           'pct',   100, TRUE)
ON CONFLICT (metric_key) DO UPDATE SET
    label           = EXCLUDED.label,
    grp             = EXCLUDED.grp,
    source_priority = EXCLUDED.source_priority,
    value_format    = EXCLUDED.value_format,
    sort_order      = EXCLUDED.sort_order,
    enabled         = EXCLUDED.enabled;
