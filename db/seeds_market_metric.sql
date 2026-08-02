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
    ('SPX',   'S&P',        'index',  '["tos:SPX","fred:SP500"]'::JSONB,       'index', 10,  TRUE),
    ('COMP',  'NDAQ',       'index',  '["tos:$COMP","fred:NASDAQCOM"]'::JSONB,  'index', 20,  TRUE),
    ('DJI',   'DOW',        'index',  '["tos:$DJI","fred:DJIA"]'::JSONB,        'index', 30,  TRUE),
    ('RUT',   'RUT',        'index',  '["tos:RUT"]'::JSONB,                     'index', 40,  TRUE),
    ('VIX',   'VIX',        'risk',   '["tos:VIX","fred:VIXCLS"]'::JSONB,       'level', 50,  TRUE),
    ('VXN',   'VXN',        'risk',   '["tos:VXN:CGI"]'::JSONB,                 'level', 55,  TRUE),
    ('VXD',   'VXD',        'risk',   '["tos:VXD"]'::JSONB,                     'level', 57,  TRUE),
    ('RVX',   'RVX',        'risk',   '["tos:RVX"]'::JSONB,                     'level', 58,  TRUE),
    ('US10Y', '10Y',        'rates',  '["fred:DGS10"]'::JSONB,                  'pct',   60,  TRUE),
    ('MOVE',  'MOVE',       'rates',  '["tos:MOVE:GIF"]'::JSONB,                'level', 65,  TRUE),
    ('T2S10', '2s10s',      'rates',  '["fred:T10Y2Y"]'::JSONB,                 'pct',   70,  TRUE),
    ('DXY',   'Dollar',     'fx',     '["tos:$DXY","fred:DTWEXBGS"]'::JSONB,    'index', 80,  TRUE),
    ('WTI',   'CRUDE',      'cmdty',  '["tos:/CL","fred:DCOILWTICO"]'::JSONB,   'price', 90,  TRUE),
    ('OVX',   'OVX',        'risk',   '["tos:OVX:CGI"]'::JSONB,                 'level', 92,  TRUE),
    ('GC',    'GOLD',       'cmdty',  '["tos:/GC"]'::JSONB,                     'price', 94,  TRUE),
    ('GVZ',   'GVZ',        'risk',   '["tos:GVZ:CGI"]'::JSONB,                 'level', 96,  TRUE),
    -- TASK_133 1.4: 'HY' used to be sourced from the BAMLH0A0HYM2 credit
    -- spread (mislabeled 'HY spread') but was disabled, so the tape showed
    -- nothing at all under this key. Re-pointed at the HYG ETF price it was
    -- actually meant to display (per _METRIC_TO_RR_SYMBOL['HY']='HYG' in
    -- api/routers/marketbar.py) and relabeled 'HYG' so it's honest about
    -- what it shows. The real credit-spread tile is the new HYOAS row below.
    ('HY',    'HYG',        'credit', '["tos:HYG"]'::JSONB,                     'price', 100, TRUE),
    -- HYOAS: the real ICE BofA US High-Yield OAS credit spread (already
    -- fetched daily into hist_macro). value_format kept as 'pct' (not a new
    -- 'bp' format) -- displays e.g. "3.42%"; higher = spread widening = worse
    -- (see INVERTED sets in web/market_bar.js + api/routers/macro_areas.py).
    ('HYOAS', 'HY Spread',  'credit', '["fred:BAMLH0A0HYM2"]'::JSONB,           'pct',   101, TRUE),
    -- 2026-07-04: mini-tape QQQ tile (added after BTC) had no existing
    -- marketbar/rr-bar row despite drv_quote already carrying real data for
    -- it (same 'dual' role as SPY/IWM in the side rail's top9 area).
    ('QQQ',   'QQQ',        'index',  '["tos:QQQ"]'::JSONB,                     'price', 45,  TRUE)
ON CONFLICT (metric_key) DO UPDATE SET
    label           = EXCLUDED.label,
    grp             = EXCLUDED.grp,
    source_priority = EXCLUDED.source_priority,
    value_format    = EXCLUDED.value_format,
    sort_order      = EXCLUDED.sort_order,
    enabled         = EXCLUDED.enabled;
