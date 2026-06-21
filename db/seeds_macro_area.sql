-- =====================================================
-- seeds_macro_area.sql — area->member map for the Macro read card (TASK_78).
-- Applied by db/init_db.py after baseline.sql creates ref_macro_area.
-- Idempotent: ON CONFLICT DO NOTHING (existing customisations survive re-run).
--
-- role codes:
--   dual     = member has drv_technicals rows (TRADE/TREND available)
--   rr_only  = member only in drv_rr (futures / foreign indices)
--   gauge    = volatility gauge -- zone only, no Long/Short stance
--   curve    = yield / curve member -- skip rr_pos (x10 scale mismatch)
-- =====================================================

-- USD -----------------------------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('usd', 'USD', '$DXY', 'rr_only', 10),
  ('usd', 'USD', 'UUP',  'dual',    20)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- US equities / breadth -----------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('us_equities', 'US Equities', 'SPX',   'rr_only', 10),
  ('us_equities', 'US Equities', '$COMP', 'rr_only', 20),
  ('us_equities', 'US Equities', 'RUT',   'rr_only', 30),
  ('us_equities', 'US Equities', 'SPY',   'dual',    40),
  ('us_equities', 'US Equities', 'QQQ',   'dual',    50),
  ('us_equities', 'US Equities', 'IWM',   'dual',    60)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Volatility (gauge only) ---------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('volatility', 'Volatility', 'VIX', 'gauge', 10)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Rates / curve -------------------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('rates', 'Rates / Duration', 'DGS2',    'curve', 10),
  ('rates', 'Rates / Duration', 'TNX:CGI', 'curve', 20),
  ('rates', 'Rates / Duration', 'TYX:CGI', 'curve', 30),
  ('rates', 'Rates / Duration', 'TLT',     'dual',  40),
  ('rates', 'Rates / Duration', 'IEF',     'dual',  50)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Credit (risk-on / risk-off) -----------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('credit', 'Credit', 'HYG', 'dual', 10),
  ('credit', 'Credit', 'LQD', 'dual', 20)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Commodities ---------------------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('commodities', 'Commodities', '/CL', 'rr_only', 10),
  ('commodities', 'Commodities', '/BZ', 'rr_only', 20),
  ('commodities', 'Commodities', '/GC', 'rr_only', 30),
  ('commodities', 'Commodities', '/HG', 'rr_only', 40),
  ('commodities', 'Commodities', '/NG', 'rr_only', 50),
  ('commodities', 'Commodities', '/SI', 'rr_only', 60),
  ('commodities', 'Commodities', 'GLD', 'dual',    70),
  ('commodities', 'Commodities', 'SLV', 'dual',    80)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Crypto --------------------------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('crypto', 'Crypto', '/BTC', 'rr_only', 10),
  ('crypto', 'Crypto', 'IBIT', 'dual',    20),
  ('crypto', 'Crypto', 'MSTR', 'dual',    30),
  ('crypto', 'Crypto', 'BITO', 'dual',    40)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Global equities -----------------------------------------------------
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('global', 'Global Equities', '$SSEC',    'rr_only', 10),
  ('global', 'Global Equities', 'GDAXI:DE', 'rr_only', 20),
  ('global', 'Global Equities', 'N225:JP',  'rr_only', 30),
  ('global', 'Global Equities', 'EEM',      'dual',    40),
  ('global', 'Global Equities', 'EWZ',      'dual',    50),
  ('global', 'Global Equities', 'EWG',      'dual',    60),
  ('global', 'Global Equities', 'EWM',      'dual',    70)
ON CONFLICT (area_key, member_symbol) DO NOTHING;
