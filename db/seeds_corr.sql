-- =====================================================
-- seeds_corr.sql -- USD correlation asset catalog (TASK_79).
-- Applied by db/init_db.py after baseline.sql creates ref_corr_asset.
-- Idempotent: ON CONFLICT DO NOTHING.
--
-- source_spec JSONB: ordered priority list, first source that has data wins.
--   "histy:<sym>"     => look in hist_y WHERE symbol=<sym> (weekdays; TASK_90)
--   "tos:<sym>"       => look in drv_quote WHERE tos_symbol = <sym>
--   "yfinance:<sym>"  => look in hist_quote_daily WHERE source='yfinance' AND symbol=<sym>
--
-- USD, SPX, Brent, Gold, Bitcoin prefer histy (loaded daily by YFiles run, always
-- current) with yfinance as long-history fallback using the SAME ticker symbol.
-- CRB (DBC) is yfinance-only (not in hist_y).
-- =====================================================

INSERT INTO ref_corr_asset
    (asset_key, label, source_spec, is_usd_base, sort_order, enabled)
VALUES
  ('usd',     '$USD Index', '["histy:^NYICDX","yfinance:^NYICDX"]',       TRUE,  0,  TRUE),
  ('spx',     'S&P',        '["histy:^SPX","yfinance:^SPX"]',             FALSE, 10, TRUE),
  ('brent',   'Brent',      '["histy:BZ=F","yfinance:BZ=F"]',             FALSE, 20, TRUE),
  ('crb',     'CRB',        '["yfinance:DBC"]',                           FALSE, 60, TRUE),
  ('gold',    'Gold',       '["histy:GC=F","yfinance:GC=F"]',             FALSE, 40, TRUE),
  ('bitcoin', 'Bitcoin',    '["histy:BTC-USD","yfinance:BTC-USD"]',       FALSE, 50, TRUE)
ON CONFLICT (asset_key) DO UPDATE SET
    source_spec = EXCLUDED.source_spec,
    label       = EXCLUDED.label;
