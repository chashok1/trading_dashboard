-- =====================================================
-- seeds_macro_area.sql — area->member map for the Macro side-panel sections.
-- Applied by db/init_db.py after baseline.sql creates ref_macro_area.
-- Idempotent: ON CONFLICT DO NOTHING (existing customisations survive re-run).
--
-- Each area_key now renders as its OWN side-panel section (broken out one
-- row per member, same as Volatility always did) rather than being rolled
-- up into a single aggregate row inside one big "Macro" panel. $DXY/UUP are
-- deliberately duplicated across 'top9' and 'usd_currency' (by request).
--
-- role codes:
--   dual     = member has drv_technicals rows (TRADE/TREND available)
--   rr_only  = member only in drv_rr (futures / foreign indices)
--   gauge    = volatility gauge -- zone only, no Long/Short stance
--   curve    = yield / curve member -- skip rr_pos (x10 scale mismatch)
-- =====================================================

-- Volatility (gauge only; one row per index) — GVZ/OVX have no
-- ref_vol_threshold row yet, so their zone shows "—" until one is added.
-- MOVE:GIF (bond-market vol) moved in from Rates & Credit per request — it
-- already has a ref_vol_threshold row (100/120), so its zone works today.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('volatility', 'S&P Vol',    'VIX',     'gauge', 10),
  ('volatility', 'Nasdaq Vol', 'VXN:CGI', 'gauge', 20),
  ('volatility', 'Dow Vol',    'VXD',     'gauge', 30),
  ('volatility', 'Russell Vol','RVX',     'gauge', 40),
  ('volatility', 'Gold Vol',   'GVZ:CGI', 'gauge', 50),
  ('volatility', 'Oil Vol',    'OVX:CGI', 'gauge', 60),
  ('volatility', 'Bond Vol',   'MOVE:GIF','gauge', 70)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Top 9 / Major Markets (HYG/LQD moved in from Rates & Credit per request) --
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('top9', 'Major Markets', '$DXY',  'rr_only', 5),
  ('top9', 'Major Markets', 'UUP',   'dual',    8),
  ('top9', 'Major Markets', 'SPX',   'rr_only', 10),
  ('top9', 'Major Markets', '$COMP', 'rr_only', 20),
  ('top9', 'Major Markets', 'RUT',   'rr_only', 30),
  ('top9', 'Major Markets', '$DJI',  'rr_only', 35),
  ('top9', 'Major Markets', 'SPY',   'dual',    40),
  ('top9', 'Major Markets', 'QQQ',   'dual',    50),
  ('top9', 'Major Markets', 'IWM',   'dual',    60),
  ('top9', 'Major Markets', 'HYG',   'dual',    210),
  ('top9', 'Major Markets', 'LQD',   'dual',    220)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Rates & Duration (MOVE moved out to Volatility, HYG/LQD moved out to
-- Major Markets per request; area_key kept as 'rates_duration' internally) --
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('rates_duration', 'Rates & Duration', 'DGS2',     'curve', 10),
  ('rates_duration', 'Rates & Duration', 'TNX:CGI',  'curve', 20),
  ('rates_duration', 'Rates & Duration', 'TYX:CGI',  'curve', 30),
  ('rates_duration', 'Rates & Duration', 'TLT',      'dual',  40),
  ('rates_duration', 'Rates & Duration', 'IEF',      'dual',  50)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Commodities (Credit moved out to Rates & Credit per request) ----------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('commodities_credit', 'Commodities', '/CL', 'rr_only', 10),
  ('commodities_credit', 'Commodities', '/BZ', 'rr_only', 20),
  ('commodities_credit', 'Commodities', '/GC', 'rr_only', 30),
  ('commodities_credit', 'Commodities', '/HG', 'rr_only', 40),
  ('commodities_credit', 'Commodities', '/NG', 'rr_only', 50),
  ('commodities_credit', 'Commodities', '/SI', 'rr_only', 60),
  ('commodities_credit', 'Commodities', 'GLD', 'dual',    70),
  ('commodities_credit', 'Commodities', 'SLV', 'dual',    80)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- USD & Currency ($DXY/UUP duplicated from Top 9 by request) -----------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('usd_currency', 'USD & Currency', '$DXY', 'rr_only', 10),
  ('usd_currency', 'USD & Currency', 'UUP',  'dual',    20),
  ('usd_currency', 'USD & Currency', '/6B',  'rr_only', 30),
  ('usd_currency', 'USD & Currency', '/6C',  'rr_only', 40),
  ('usd_currency', 'USD & Currency', '/6E',  'rr_only', 50),
  ('usd_currency', 'USD & Currency', '/6J',  'rr_only', 60)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Country ETFs (raw foreign indices on top, then the ETFs) -------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('country_etfs', 'Country ETFs', '$SSEC',    'rr_only', 10),
  ('country_etfs', 'Country ETFs', 'GDAXI:DE', 'rr_only', 20),
  ('country_etfs', 'Country ETFs', 'N225:JP',  'rr_only', 30),
  ('country_etfs', 'Country ETFs', 'EEM',      'dual',    40),
  ('country_etfs', 'Country ETFs', 'EWZ',      'dual',    50),
  ('country_etfs', 'Country ETFs', 'EWG',      'dual',    60),
  ('country_etfs', 'Country ETFs', 'EWM',      'dual',    70)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Crypto (now its own standalone panel, unchanged membership) ----------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('crypto', 'Crypto', '/BTC', 'rr_only', 10),
  ('crypto', 'Crypto', 'IBIT', 'dual',    20),
  ('crypto', 'Crypto', 'MSTR', 'dual',    30),
  ('crypto', 'Crypto', 'BITO', 'dual',    40)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Remaining: rrTape3's Tech + ETFs categories, not covered by any area
-- above and not duplicating the Sectors panel's own ETF-proxy rows.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('remaining', 'Tech & ETFs', 'AAPL',  'dual', 10),
  ('remaining', 'Tech & ETFs', 'AMZN',  'dual', 20),
  ('remaining', 'Tech & ETFs', 'GOOGL', 'dual', 30),
  ('remaining', 'Tech & ETFs', 'META',  'dual', 40),
  ('remaining', 'Tech & ETFs', 'MSFT',  'dual', 50),
  ('remaining', 'Tech & ETFs', 'NFLX',  'dual', 60),
  ('remaining', 'Tech & ETFs', 'NVDA',  'dual', 70),
  ('remaining', 'Tech & ETFs', 'ORCL',  'dual', 80),
  ('remaining', 'Tech & ETFs', 'TSLA',  'dual', 90),
  ('remaining', 'Tech & ETFs', 'DRAM',  'dual', 100),
  ('remaining', 'Tech & ETFs', 'GDX',   'dual', 110),
  ('remaining', 'Tech & ETFs', 'IAK',   'dual', 120),
  ('remaining', 'Tech & ETFs', 'ITA',   'dual', 130),
  ('remaining', 'Tech & ETFs', 'PINK',  'dual', 140),
  ('remaining', 'Tech & ETFs', 'SPMO',  'dual', 150),
  ('remaining', 'Tech & ETFs', 'URA',   'dual', 160)
ON CONFLICT (area_key, member_symbol) DO NOTHING;
