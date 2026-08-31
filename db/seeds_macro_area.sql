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

-- Top 9 / Major Markets --
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
  ('top9', 'Major Markets', 'IWM',   'dual',    60)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-07-04: HYG/LQD removed from Major Markets/top9 (per request) -- they
-- now live only in Credit below, not duplicated. DELETE (not just dropping
-- the INSERT above) so this also cleans up rows a prior init_db run already
-- seeded; safe to re-run (no-op once the rows are gone).
DELETE FROM ref_macro_area
WHERE area_key = 'top9' AND member_symbol IN ('HYG', 'LQD');

-- TASK_115: fix a pre-existing typo found during the tape-coverage audit —
-- drv_rr/hist_rr's actual tos_symbol for the 2Y yield is 'DGS2:FRED' (matches
-- /api/rr-bar's Rates group), not 'DGS2'. The bare 'DGS2' row never resolved
-- any rr/technicals data. Must run BEFORE the INSERT below (which seeds
-- 'DGS2:FRED' directly on fresh installs); NOT EXISTS guard + WHERE make
-- re-running this UPDATE a clean no-op once the rename has happened once.
UPDATE ref_macro_area SET member_symbol = 'DGS2:FRED'
WHERE area_key = 'rates_duration' AND member_symbol = 'DGS2'
  AND NOT EXISTS (
    SELECT 1 FROM ref_macro_area
    WHERE area_key = 'rates_duration' AND member_symbol = 'DGS2:FRED'
  );

-- Rates & Duration (MOVE moved out to Volatility, HYG/LQD moved out to
-- Major Markets per request; area_key kept as 'rates_duration' internally) --
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('rates_duration', 'Rates & Duration', 'DGS2:FRED','curve', 10),
  ('rates_duration', 'Rates & Duration', 'TNX:CGI',  'curve', 20),
  ('rates_duration', 'Rates & Duration', 'TYX:CGI',  'curve', 30),
  ('rates_duration', 'Rates & Duration', 'TLT',      'dual',  40),
  ('rates_duration', 'Rates & Duration', 'IEF',      'dual',  50)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Credit (TASK_115: dedicated rail section. HYG/LQD were briefly duplicated
-- in Major Markets/top9 too -- same precedent as $DXY/UUP in top9+usd_
-- currency -- but removed from top9 on 2026-07-04 per request, so Credit is
-- now their only home). Matches /api/rr-bar's 'Credit' group exactly.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order)
VALUES
  ('credit', 'Credit', 'HYG', 'dual', 10),
  ('credit', 'Credit', 'LQD', 'dual', 20)
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

-- 2026-07-04: friendly per-member labels for the cryptic (non-stock/ETF)
-- symbols only -- futures (/XX), $-prefixed index tickers, FRED/CGI-suffixed
-- treasury yields, and foreign indices. Stock/ETF rows above keep their
-- label = the area name (repeated), same as before -- macro_areas.js only
-- treats a member's label as a real override when it differs from the
-- area's own label (member.label !== area.label), so those rows still fall
-- back to displaying their own ticker (already readable). UPDATE, not
-- re-INSERT with DO UPDATE, so this file's existing "DO NOTHING preserves
-- hand customisations" convention for the INSERTs above stays intact.
UPDATE ref_macro_area SET label = 'Dollar'          WHERE area_key = 'top9' AND member_symbol = '$DXY';
UPDATE ref_macro_area SET label = 'S&P 500'         WHERE area_key = 'top9' AND member_symbol = 'SPX';
UPDATE ref_macro_area SET label = 'Nasdaq'          WHERE area_key = 'top9' AND member_symbol = '$COMP';
UPDATE ref_macro_area SET label = 'Russell 2000'    WHERE area_key = 'top9' AND member_symbol = 'RUT';
UPDATE ref_macro_area SET label = 'Dow'             WHERE area_key = 'top9' AND member_symbol = '$DJI';

UPDATE ref_macro_area SET label = '2Y Treasury'     WHERE area_key = 'rates_duration' AND member_symbol = 'DGS2:FRED';
UPDATE ref_macro_area SET label = '10Y Treasury'    WHERE area_key = 'rates_duration' AND member_symbol = 'TNX:CGI';
UPDATE ref_macro_area SET label = '30Y Treasury'    WHERE area_key = 'rates_duration' AND member_symbol = 'TYX:CGI';

UPDATE ref_macro_area SET label = 'WTI'             WHERE area_key = 'commodities_credit' AND member_symbol = '/CL';
UPDATE ref_macro_area SET label = 'Brent'           WHERE area_key = 'commodities_credit' AND member_symbol = '/BZ';
UPDATE ref_macro_area SET label = 'Gold'            WHERE area_key = 'commodities_credit' AND member_symbol = '/GC';
UPDATE ref_macro_area SET label = 'Copper'          WHERE area_key = 'commodities_credit' AND member_symbol = '/HG';
UPDATE ref_macro_area SET label = 'Nat Gas'         WHERE area_key = 'commodities_credit' AND member_symbol = '/NG';
UPDATE ref_macro_area SET label = 'Silver'          WHERE area_key = 'commodities_credit' AND member_symbol = '/SI';

UPDATE ref_macro_area SET label = 'Dollar'          WHERE area_key = 'usd_currency' AND member_symbol = '$DXY';
UPDATE ref_macro_area SET label = 'British Pound'   WHERE area_key = 'usd_currency' AND member_symbol = '/6B';
UPDATE ref_macro_area SET label = 'Canadian Dollar' WHERE area_key = 'usd_currency' AND member_symbol = '/6C';
UPDATE ref_macro_area SET label = 'Euro'            WHERE area_key = 'usd_currency' AND member_symbol = '/6E';
UPDATE ref_macro_area SET label = 'Japanese Yen'    WHERE area_key = 'usd_currency' AND member_symbol = '/6J';

UPDATE ref_macro_area SET label = 'Shanghai'        WHERE area_key = 'country_etfs' AND member_symbol = '$SSEC';
UPDATE ref_macro_area SET label = 'Germany'         WHERE area_key = 'country_etfs' AND member_symbol = 'GDAXI:DE';
UPDATE ref_macro_area SET label = 'Japan'           WHERE area_key = 'country_etfs' AND member_symbol = 'N225:JP';

UPDATE ref_macro_area SET label = 'Bitcoin'         WHERE area_key = 'crypto' AND member_symbol = '/BTC';

-- 2026-08-24: IBIT/MSTR/BITO removed from Crypto, ETHA added -- user:
-- "remove IBIT, MSTR, BITO and add ETHA". DELETE (same convention as the
-- 2026-07-04 HYG/LQD removal above), then INSERT ETHA (iShares Ethereum
-- Trust ETF) with role='dual' (real tradable ETF, same as the rows it
-- replaces) at sort_order 20, IBIT's old slot.
DELETE FROM ref_macro_area
WHERE area_key = 'crypto' AND member_symbol IN ('IBIT', 'MSTR', 'BITO');

INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('crypto', 'Crypto', 'ETHA', 'dual', 20)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-24: UUP and RSP removed from Major Markets/top9 (per request,
-- after discussing $DXY-vs-UUP's index/tradable-proxy distinction --
-- user decided to just keep the raw index rows for Dollar/S&P 500, no
-- ETF-proxy row for either). RSP itself was only added earlier the same
-- session (never committed) -- reverted outright rather than insert-then-
-- delete. UUP predates this session, so DELETE (same convention as the
-- 2026-07-04 HYG/LQD removal above) -- safe to re-run, no-op once gone.
DELETE FROM ref_macro_area
WHERE area_key = 'top9' AND member_symbol IN ('UUP', 'RSP');

-- 2026-08-24: Platinum, Palladium, Corn, Wheat, Soybeans added to
-- Commodities -- user asked what else to track, explicitly "no tradable
-- proxies" (no ETF/dual row like GLD/SLV), so all 5 are role='rr_only'
-- raw futures, same as WTI/Brent/Gold/Copper/Nat Gas/Silver above.
-- ("I need all 5 you mentioned" -- Platinum/Corn landed first in a
-- smaller follow-up, Palladium/Wheat/Soybeans added here to complete the
-- set.) sort_order 65-69 slots them right after Silver (60), before the
-- GLD/SLV dual rows (70/80).
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('commodities_credit', 'Platinum',  '/PL', 'rr_only', 65),
  ('commodities_credit', 'Palladium', '/PA', 'rr_only', 66),
  ('commodities_credit', 'Corn',      '/ZC', 'rr_only', 67),
  ('commodities_credit', 'Wheat',     '/ZW', 'rr_only', 68),
  ('commodities_credit', 'Soybeans',  '/ZS', 'rr_only', 69)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- Corn landed at sort_order 66 from its own earlier (smaller) insert
-- above, before Palladium/Wheat/Soybeans joined it -- the ON CONFLICT DO
-- NOTHING above doesn't touch that existing row's sort_order, so it now
-- collides with Palladium's 66. Explicit fix-up, idempotent (no-op once
-- Corn is already at 67).
UPDATE ref_macro_area SET sort_order = 67
WHERE area_key = 'commodities_credit' AND member_symbol = '/ZC';

-- 2026-08-24: UUP also removed from USD & Currency (usd_currency) -- user:
-- "remove UUP" (follow-up to removing it from Major Markets/top9 earlier
-- the same session, same $DXY-index-vs-ETF-proxy reasoning, now applied
-- consistently to its other appearance). DELETE, same convention as
-- above.
DELETE FROM ref_macro_area
WHERE area_key = 'usd_currency' AND member_symbol = 'UUP';

-- 2026-08-24: 2Y Treasury removed from Rates & Duration -- user: "remove
-- 2year treasury".
DELETE FROM ref_macro_area
WHERE area_key = 'rates_duration' AND member_symbol = 'DGS2:FRED';

-- 2026-08-24: IWM removed from Major Markets/top9 -- user: "remove IWM".
DELETE FROM ref_macro_area
WHERE area_key = 'top9' AND member_symbol = 'IWM';

-- 2026-08-24: $DXY (labeled "Dollar") removed from Major Markets/top9 --
-- user: "remove Dollar from major markets". Still lives in USD & Currency
-- (usd_currency) below, so Dollar tracking isn't lost, just no longer
-- duplicated into Major Markets.
DELETE FROM ref_macro_area
WHERE area_key = 'top9' AND member_symbol = '$DXY';

-- 2026-08-24: SPY removed from Major Markets/top9 -- user: "remove SPY
-- from major markets". SPX (the raw index row) stays, same
-- index-vs-ETF-proxy precedent as the earlier UUP/RSP removal.
DELETE FROM ref_macro_area
WHERE area_key = 'top9' AND member_symbol = 'SPY';

-- 2026-08-24: GLD and SLV removed from Commodities (commodities_credit) --
-- user: "remove GLD and SLV from commodities". Raw futures /GC (Gold) and
-- /SI (Silver) stay, same raw-index-over-ETF-proxy precedent as the
-- SPY/UUP removals above.
DELETE FROM ref_macro_area
WHERE area_key = 'commodities_credit' AND member_symbol IN ('GLD', 'SLV');

-- 2026-08-25: RSP added back to Major Markets/top9 -- user: "add RSP back
-- to major markets" (Invesco S&P 500 Equal Weight ETF). It was briefly
-- here and reverted the same session on 2026-08-24 (see the UUP/RSP
-- DELETE above); this is a fresh, deliberate re-add. role='dual' (real
-- tradable ETF, same as SPY/QQQ before it), sort_order 40 -- SPY's old
-- slot, vacant since SPY was removed from top9 the same day.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('top9', 'Major Markets', 'RSP', 'dual', 40)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-27: EWY (iShares MSCI South Korea ETF) added to Country ETFs --
-- user asked for "an appropriate symbol" after a question about KOSPI
-- coverage (which has no TOS/hist_rr symbol at all, only a Yahoo-only feed
-- via etl/fetch_yahoo_history.py's ^KS11 -- not usable here, this table
-- needs a drv_technicals/drv_rr symbol). EWY is the direct South-Korea
-- analogue of the existing EEM/EWZ/EWG/EWM rows -- role='dual', sort_order
-- 80, right after EWM.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('country_etfs', 'Country ETFs', 'EWY', 'dual', 80)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-27: GLD, SLV, and ETF proxies for Platinum/Palladium/Corn/Wheat/
-- Soybeans added (back) to Commodities, role='dual' -- reverses the
-- 2026-08-24 "no tradable proxies" call (both the GLD/SLV DELETE above and
-- the deliberate rr_only-only choice for the 5 newer commodities) after the
-- user explicitly confirmed the reversal, having been shown the prior
-- decision first: "why i don't see trade and trend for platinum,
-- palladium, wheat, soy beens, com?" -> confirmed reversing GLD/SLV too,
-- for a consistent panel (every commodity gets Trade/Trend, not a mix).
-- Raw futures rows (/GC, /SI, /PL, /PA, /ZC, /ZW, /ZS) stay -- same
-- futures-plus-ETF-proxy pattern as WTI/Brent/Copper/Nat-Gas keep for
-- themselves already (rr_only only, no proxy exists/was asked for there).
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('commodities_credit', 'Commodities', 'GLD',  'dual', 100),
  ('commodities_credit', 'Commodities', 'SLV',  'dual', 101),
  ('commodities_credit', 'Commodities', 'PPLT', 'dual', 102),
  ('commodities_credit', 'Commodities', 'PALL', 'dual', 103),
  ('commodities_credit', 'Commodities', 'CORN', 'dual', 104),
  ('commodities_credit', 'Commodities', 'WEAT', 'dual', 105),
  ('commodities_credit', 'Commodities', 'SOYB', 'dual', 106)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-27 follow-up: the /PL, /PA, /ZC, /ZW, /ZS futures rows above are
-- now a redundant no-Trade/Trend duplicate of their own PPLT/PALL/CORN/
-- WEAT/SOYB dual row (added moments earlier, same commit) -- user: "remove
-- the commodities with no trade/trend from the panel" -> clarified to mean
-- specifically these 5 (not every rr_only row -- WTI/Brent/Gold/Copper/
-- Nat-Gas/Silver futures rows are unaffected; Gold and Silver deliberately
-- keep BOTH their futures row and their GLD/SLV dual row, same as before
-- this whole change). Each of these 5 now has ONLY its dual ETF-proxy row.
DELETE FROM ref_macro_area
WHERE area_key = 'commodities_credit' AND member_symbol IN ('/PL', '/PA', '/ZC', '/ZW', '/ZS');

-- 2026-08-27: new area 'sector_etfs' -- the 11 GICS sector SPDR ETFs as
-- their own full rail panel (role='dual', same as every other ETF row in
-- this file), distinct from the separate breadth-based Sectors roll-up
-- (which reads drv_technicals per-stock, not this table). Symbol->sector
-- mapping and sort order match api/routers/macro_areas.py::_SECTOR_ETF /
-- _GICS_DISPLAY exactly. User: "add a SECTORS panel in the middle with
-- corresponding ETFs (starts with X) similar to other panels."
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('sector_etfs', 'Sectors', 'XLK',  'dual', 10),   -- Information Technology
  ('sector_etfs', 'Sectors', 'XLF',  'dual', 20),   -- Financials
  ('sector_etfs', 'Sectors', 'XLV',  'dual', 30),   -- Health Care
  ('sector_etfs', 'Sectors', 'XLY',  'dual', 40),   -- Consumer Discretionary
  ('sector_etfs', 'Sectors', 'XLC',  'dual', 50),   -- Communication Services
  ('sector_etfs', 'Sectors', 'XLI',  'dual', 60),   -- Industrials
  ('sector_etfs', 'Sectors', 'XLP',  'dual', 70),   -- Consumer Staples
  ('sector_etfs', 'Sectors', 'XLE',  'dual', 80),   -- Energy
  ('sector_etfs', 'Sectors', 'XLU',  'dual', 90),   -- Utilities
  ('sector_etfs', 'Sectors', 'XLRE', 'dual', 100),  -- Real Estate
  ('sector_etfs', 'Sectors', 'XLB',  'dual', 110)   -- Materials
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-31: NIB (cocoa ETN) and WOOD (lumber/timber ETF) added to
-- Commodities, role='dual' -- same ETF-proxy pattern as GLD/SLV/PPLT/PALL/
-- CORN/WEAT/SOYB above (no raw futures counterpart added -- no Cocoa/Lumber
-- rr_only rows exist yet, unlike WTI/Gold/etc. which keep both). User:
-- "add NIB and WOOD to the watchlist -> dashboard -> middle panels -> col 5
-- -> Commodities".
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('commodities_credit', 'Commodities', 'NIB',  'dual', 107),
  ('commodities_credit', 'Commodities', 'WOOD', 'dual', 108)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-31 follow-up: NIB removed -- user confirmed it's delisted. No
-- confidently-verified live cocoa ETF/ETN proxy exists to swap in, so
-- cocoa is dropped from the panel for now (same precedent as the 2026-08-24
-- "no tradable proxy" GLD/SLV removal above -- re-add if/when a real proxy
-- is confirmed). WOOD is unaffected.
DELETE FROM ref_macro_area
WHERE area_key = 'commodities_credit' AND member_symbol = 'NIB';

-- 2026-08-31 follow-up: URA (Global X Uranium ETF) added to Commodities,
-- role='dual' -- same ETF-proxy pattern as GLD/SLV/PPLT/WOOD above. Already
-- confirmed live in hist_td/hist_tl/hist_y before adding (avoids a repeat
-- of the NIB delisting surprise). User asked for uranium symbol + chose
-- URA over URNM/both.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order) VALUES
  ('commodities_credit', 'Commodities', 'URA', 'dual', 109)
ON CONFLICT (area_key, member_symbol) DO NOTHING;

-- 2026-08-31 follow-up: reorder so URA displays right below SLV -- user:
-- "display it below SLV". Bump PPLT/PALL/CORN/WEAT/SOYB down one slot
-- (descending order, though sort_order has no uniqueness constraint) to
-- open 102 for URA; WOOD (108) is unaffected/unchanged.
UPDATE ref_macro_area SET sort_order = 107 WHERE area_key = 'commodities_credit' AND member_symbol = 'SOYB';
UPDATE ref_macro_area SET sort_order = 106 WHERE area_key = 'commodities_credit' AND member_symbol = 'WEAT';
UPDATE ref_macro_area SET sort_order = 105 WHERE area_key = 'commodities_credit' AND member_symbol = 'CORN';
UPDATE ref_macro_area SET sort_order = 104 WHERE area_key = 'commodities_credit' AND member_symbol = 'PALL';
UPDATE ref_macro_area SET sort_order = 103 WHERE area_key = 'commodities_credit' AND member_symbol = 'PPLT';
UPDATE ref_macro_area SET sort_order = 102 WHERE area_key = 'commodities_credit' AND member_symbol = 'URA';
