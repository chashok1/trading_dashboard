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
-- 2026-09-30, user-directed ("you should only use closing prices"): yfinance
-- daily closes come FIRST; histy (TOS/Y-file snapshots, which can be intraday
-- or a repeat of the prior day) is only a fallback for dates Yahoo lacks.
-- Bitcoin uses BTC=F (CME futures, weekday closes) so a 15-row window is 15
-- market days, matching the reference numbers. CRB (DBC), Oil (WTI, CL=F) and
-- Gold (GLD) are yfinance-only: these are the series that reproduce the
-- reference correlations (Brent BZ=F and gold futures GC=F did not).
-- =====================================================

INSERT INTO ref_corr_asset
    (asset_key, label, source_spec, is_usd_base, sort_order, enabled)
VALUES
  ('usd',     '$USD Index', '["yfinance:^NYICDX","histy:^NYICDX"]',       TRUE,  0,  TRUE),
  ('spx',     'S&P',        '["yfinance:^SPX","histy:^SPX"]',             FALSE, 10, TRUE),
  ('brent',   'Oil (WTI)',  '["yfinance:CL=F"]',                        FALSE, 20, TRUE),
  ('crb',     'Commodities (DBC)', '["yfinance:DBC"]',                   FALSE, 60, TRUE),
  ('gold',    'Gold (GLD)', '["yfinance:GLD"]',                         FALSE, 40, TRUE),
  ('bitcoin', 'Bitcoin',    '["yfinance:BTC=F","histy:BTC=F"]',       FALSE, 50, TRUE)
ON CONFLICT (asset_key) DO UPDATE SET
    source_spec = EXCLUDED.source_spec,
    label       = EXCLUDED.label;
