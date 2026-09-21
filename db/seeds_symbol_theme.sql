-- db/seeds_symbol_theme.sql — TASK_143: ref_symbol_theme, ~90 rows.
-- Symbols confirmed live against hist_rr/hist_etf/hist_ps (latest snapshot
-- as of 2026-09-21: RR 2026-09-18, ETF 2026-09-20, PS 2026-09-18). `symbol`
-- is each source's OWN symbol column (hist_rr.symbol / hist_etf.symbol /
-- hist_ps.ticker) — the natural join key; several RR members have a NULL
-- tos_symbol (IGV, OIH, RSP), so tos_symbol cannot be used as the key here.
-- quad_category/quad_sub_category are the ref_quad_outlook(category,
-- sub_category) key this member's theme maps to. Stocks (SSS, CALL) are
-- deliberately NOT seeded here — they map to themes via ref_sector at
-- derive time (etl/derive_sss_breadth.py).
INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
-- Rates up (RR yields — outlook BULLISH already means "yield up", no inversion)
('UST2Y', 'RR', 'Rates up', 1, FALSE, NULL, NULL),
('UST10Y', 'RR', 'Rates up', 1, FALSE, NULL, NULL),
('UST30Y', 'RR', 'Rates up', 1, FALSE, NULL, NULL),
('PFIX', 'ETF', 'Rates up', 1, FALSE, NULL, NULL),
('PFIX', 'PS', 'Rates up', 1, FALSE, NULL, NULL),
-- Duration (long-bond proxies)
('TLT', 'ETF', 'Duration', 1, FALSE, 'Fixed Income', 'Long Bond'),
('ZROZ', 'ETF', 'Duration', 1, FALSE, 'Fixed Income', 'Long Bond'),
-- Credit
('HYG', 'RR', 'Credit', 1, FALSE, 'Fixed Income', 'HY Credit'),
('LQD', 'RR', 'Credit', 1, FALSE, 'Fixed Income', 'IG Credit'),
('LQD', 'ETF', 'Credit', 1, FALSE, 'Fixed Income', 'IG Credit'),
('JOJO', 'ETF', 'Credit', 1, FALSE, 'Fixed Income', 'HY Credit'),
-- USD (FX crosses quoted vs USD are inverted)
('USD', 'RR', 'USD', 1, FALSE, 'Asset Class', 'USD'),
('EUR/USD', 'RR', 'USD', 1, TRUE, 'Asset Class', 'USD'),
('GBP/USD', 'RR', 'USD', 1, TRUE, 'Asset Class', 'USD'),
('CAD/USD', 'RR', 'USD', 1, TRUE, 'Asset Class', 'USD'),
('DBMF', 'ETF', 'USD', 1, FALSE, 'Asset Class', 'USD'),
('DBMF', 'PS', 'USD', 1, FALSE, 'Asset Class', 'USD')
ON CONFLICT (symbol, source_code, theme) DO NOTHING;

INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
-- Volatility
('VIX', 'RR', 'Volatility', 1, FALSE, NULL, NULL),
-- Cash / short FI
('BUXX', 'ETF', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
('CLOX', 'ETF', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
('CLOZ', 'ETF', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
('BUXX', 'PS', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
('CLOX', 'PS', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
('CLOZ', 'PS', 'Cash/short FI', 1, FALSE, 'Fixed Income', 'Treasury Bills'),
-- Large caps
('SPX', 'RR', 'Large caps', 1, FALSE, 'Asset Class', 'Equities'),
('COMPQ', 'RR', 'Large caps', 1, FALSE, 'Asset Class', 'Equities'),
('MSFT', 'RR', 'Large caps', 1, FALSE, 'Asset Class', 'Equities'),
-- Small caps
('RUT', 'RR', 'Small caps', 1, FALSE, 'Equity Style', 'Small Caps'),
('IWM', 'ETF', 'Small caps', 1, FALSE, 'Equity Style', 'Small Caps'),
-- Breadth
('RSP', 'RR', 'Breadth', 1, FALSE, NULL, NULL),
-- Momentum
('SPMO', 'RR', 'Momentum', 1, FALSE, 'Equity Style', 'Momentum'),
('PRN', 'ETF', 'Momentum', 1, FALSE, 'Equity Style', 'Momentum'),
('JOET', 'ETF', 'Momentum', 1, FALSE, 'Equity Style', 'Momentum'),
-- Defensives
('XLU', 'RR', 'Defensives', 1, FALSE, 'Equity Sectors', 'Utilities'),
('XLP', 'RR', 'Defensives', 1, FALSE, 'Equity Sectors', 'Consumer Staples'),
('XLU', 'ETF', 'Defensives', 1, FALSE, 'Equity Sectors', 'Utilities')
ON CONFLICT (symbol, source_code, theme) DO NOTHING;

INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
-- Cyclicals
('XLY', 'RR', 'Cyclicals', 1, FALSE, 'Equity Sectors', 'Consumer Discretionary'),
('XLF', 'RR', 'Cyclicals', 1, FALSE, 'Equity Sectors', 'Financials'),
('XLRE', 'RR', 'Cyclicals', 1, FALSE, 'Equity Sectors', 'Real Estate'),
('XLI', 'ETF', 'Cyclicals', 1, FALSE, 'Equity Sectors', 'Industrials'),
-- Healthcare
('XLV', 'RR', 'Healthcare', 1, FALSE, 'Equity Sectors', 'Health Care'),
('XLV', 'ETF', 'Healthcare', 1, FALSE, 'Equity Sectors', 'Health Care'),
('FXH', 'ETF', 'Healthcare', 1, FALSE, 'Equity Sectors', 'Health Care'),
-- Tech/software
('XLK', 'RR', 'Tech/software', 1, FALSE, 'Equity Sectors', 'Information Technology'),
('IGV', 'RR', 'Tech/software', 1, FALSE, 'Equity Sectors', 'Information Technology'),
('IGV', 'ETF', 'Tech/software', 1, FALSE, 'Equity Sectors', 'Information Technology'),
-- Semis
('NVDA', 'RR', 'Semis', 1, FALSE, 'Equity Sectors', 'Information Technology'),
('DRAM', 'RR', 'Semis', 1, FALSE, 'Equity Sectors', 'Information Technology'),
('SMH', 'ETF', 'Semis', 1, FALSE, 'Equity Sectors', 'Information Technology'),
-- Energy
('XLE', 'RR', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy'),
('WTIC', 'RR', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy'),
('BRENT', 'RR', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy'),
('OIH', 'RR', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy'),
('XLE', 'ETF', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy'),
('XLE', 'PS', 'Energy', 1, FALSE, 'Equity Sectors', 'Energy')
ON CONFLICT (symbol, source_code, theme) DO NOTHING;

INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
-- Precious metals
('GOLD', 'RR', 'Precious metals', 1, FALSE, 'Asset Class', 'Gold'),
('SILVER', 'RR', 'Precious metals', 1, FALSE, 'Asset Class', 'Gold'),
('GDX', 'RR', 'Precious metals', 1, FALSE, 'Asset Class', 'Gold'),
('AAAU', 'ETF', 'Precious metals', 1, FALSE, 'Asset Class', 'Gold'),
('AAAU', 'PS', 'Precious metals', 1, FALSE, 'Asset Class', 'Gold'),
-- Industrial metals
('COPPER', 'RR', 'Industrial metals', 1, FALSE, 'Asset Class', 'Commodities'),
-- Ags
('CORN', 'ETF', 'Ags', 1, FALSE, 'Asset Class', 'Commodities'),
('CORN', 'PS', 'Ags', 1, FALSE, 'Asset Class', 'Commodities'),
-- Crypto
('BITCOIN', 'RR', 'Crypto', 1, FALSE, 'Asset Class', 'Crypto'),
('IBIT', 'ETF', 'Crypto', 1, FALSE, 'Asset Class', 'Crypto'),
('ETHA', 'ETF', 'Crypto', 1, FALSE, 'Asset Class', 'Crypto'),
('IBIT', 'PS', 'Crypto', 1, FALSE, 'Asset Class', 'Crypto'),
('ETHA', 'PS', 'Crypto', 1, FALSE, 'Asset Class', 'Crypto'),
-- Developed intl
('DAX', 'RR', 'Developed intl', 1, FALSE, NULL, NULL),
('NIKK', 'RR', 'Developed intl', 1, FALSE, NULL, NULL),
('EWG', 'ETF', 'Developed intl', 1, FALSE, NULL, NULL),
('EWA', 'ETF', 'Developed intl', 1, FALSE, NULL, NULL),
('EWL', 'ETF', 'Developed intl', 1, FALSE, NULL, NULL),
-- Emerging
('SSEC', 'RR', 'Emerging', 1, FALSE, NULL, NULL),
('EWZ', 'ETF', 'Emerging', 1, FALSE, NULL, NULL),
('COLO', 'ETF', 'Emerging', 1, FALSE, NULL, NULL),
('INDA', 'ETF', 'Emerging', 1, FALSE, NULL, NULL),
('QAT', 'ETF', 'Emerging', 1, FALSE, NULL, NULL),
('EWZ', 'PS', 'Emerging', 1, FALSE, NULL, NULL),
('COLO', 'PS', 'Emerging', 1, FALSE, NULL, NULL)
ON CONFLICT (symbol, source_code, theme) DO NOTHING;
