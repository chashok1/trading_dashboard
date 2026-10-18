-- =====================================================
-- seeds_commodity_ag.sql — six farm/softs/livestock futures for the Macro rails.
-- Idempotent: ON CONFLICT DO NOTHING (existing customisations survive re-run).
--
-- Hedgeye's risk-range feed has none of these, so the rail rows show price,
-- day % and week % only (no risk-range bar / outlook colour). Prices are in
-- cents (corn 450 = $4.50/bu), shown as quoted.
-- =====================================================

-- TOS <-> Yahoo cross reference (also drives the Yahoo quote fetch).
INSERT INTO ref_rrt (rr_name, y_ticker, tos_ticker, reverse)
VALUES
  ('CORN',        'ZC=F', '/ZC', 'N'),
  ('WHEAT',       'ZW=F', '/ZW', 'N'),
  ('SOYBEANS',    'ZS=F', '/ZS', 'N'),
  ('COFFEE',      'KC=F', '/KC', 'N'),
  ('SUGAR',       'SB=F', '/SB', 'N'),
  ('LIVE_CATTLE', 'LE=F', '/LE', 'N')
ON CONFLICT DO NOTHING;

-- Sector reference rows (asset class drives the Quad 'Asset Class' stance).
INSERT INTO ref_sector (ticker, description, industry, sp500, nasdaq, dow,
  russell, vehicle_type, asset_class, sub_asset_class, equity_sector,
  growth, valuation, price_action)
VALUES
  ('ZC=F', 'Corn Futures; the U.S. benchmark for corn prices (cents per bushel).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Agriculture',
   'Materials', 'Cyclical', 'N/A', 'Momentum'),
  ('ZW=F', 'Wheat Futures; the U.S. benchmark for wheat prices (cents per bushel).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Agriculture',
   'Materials', 'Cyclical', 'N/A', 'Momentum'),
  ('ZS=F', 'Soybean Futures; the U.S. benchmark for soybean prices (cents per bushel).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Agriculture',
   'Materials', 'Cyclical', 'N/A', 'Momentum')
ON CONFLICT DO NOTHING;

INSERT INTO ref_sector (ticker, description, industry, sp500, nasdaq, dow,
  russell, vehicle_type, asset_class, sub_asset_class, equity_sector,
  growth, valuation, price_action)
VALUES
  ('KC=F', 'Coffee Futures; the global benchmark for arabica coffee (cents per pound).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Softs',
   'Materials', 'Cyclical', 'N/A', 'Momentum'),
  ('SB=F', 'Sugar No. 11 Futures; the global benchmark for raw sugar (cents per pound).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Softs',
   'Materials', 'Cyclical', 'N/A', 'Momentum'),
  ('LE=F', 'Live Cattle Futures; the U.S. benchmark for cattle prices (cents per pound).',
   'Commodities', 'N', 'N', 'N', 'N', 'Futures', 'Commodities', 'Livestock',
   'Materials', 'Cyclical', 'N/A', 'Momentum')
ON CONFLICT DO NOTHING;

-- Macro rail: existing farm group, right after Copper (sort 10), before the ETFs (20+).
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('commodities_ag', 'Corn',        '/ZC', 'rr_only', 11),
  ('commodities_ag', 'Wheat',       '/ZW', 'rr_only', 12),
  ('commodities_ag', 'Soybeans',    '/ZS', 'rr_only', 13),
  ('commodities_ag', 'Coffee',      '/KC', 'rr_only', 14),
  ('commodities_ag', 'Sugar',       '/SB', 'rr_only', 15),
  ('commodities_ag', 'Live Cattle', '/LE', 'rr_only', 16)
ON CONFLICT DO NOTHING;
