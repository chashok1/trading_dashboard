-- =====================================================
-- seeds_corr.sql -- USD correlation asset catalog (TASK_79).
-- Applied by db/init_db.py after baseline.sql creates ref_corr_asset.
-- Idempotent: ON CONFLICT DO NOTHING.
--
-- source_spec JSONB: ordered priority list, first source that has data wins.
--   "tos:<sym>"       => look in drv_quote WHERE tos_symbol = <sym>
--   "yfinance:<sym>"  => look in hist_quote_daily WHERE source='yfinance' AND symbol=<sym>
-- =====================================================

INSERT INTO ref_corr_asset
    (asset_key, label, source_spec, is_usd_base, sort_order, enabled)
VALUES
  ('usd',     '$USD Index', '["yfinance:DX-Y.NYB"]',              TRUE,  0,  TRUE),
  ('spx',     'S&P 500',    '["yfinance:^GSPC","tos:SPY"]',      FALSE, 10, TRUE),
  ('brent',   'Brent Oil',  '["yfinance:BZ=F"]',                 FALSE, 20, TRUE),
  ('crb',     'CRB (proxy)','["yfinance:DBC","tos:DBC"]',        FALSE, 30, TRUE),
  ('gold',    'Gold',       '["yfinance:GC=F","tos:GLD"]',       FALSE, 40, TRUE),
  ('bitcoin', 'Bitcoin',    '["yfinance:BTC-USD","tos:/BTC"]',   FALSE, 50, TRUE)
ON CONFLICT (asset_key) DO UPDATE SET
    source_spec = EXCLUDED.source_spec,
    label       = EXCLUDED.label;
