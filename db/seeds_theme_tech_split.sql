-- 2026-10-16, user-directed: make the Themes grid and the area-verdict tiles use the same names, and add the two
-- tech-split verdict areas (Big tech & hardware, Quantum & speculative) to the grid as theme rows.
-- Symbols are the Hedgeye-list symbols that match each area's own definition in seeds_area_tech_split.sql
-- (Big tech: sector Information Technology + sub-asset-class Technology; Quantum: Quantum/AI). The Crypto-class
-- symbols (IBIT, ETHA) that area also lists are NOT repeated here -- they already sit in the Crypto theme.
INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
    ('AAPL', 'RR',  'Big tech & hardware',   1, FALSE, 'Equity Sectors', 'Information Technology'),
    ('MSFT', 'RR',  'Big tech & hardware',   1, FALSE, 'Equity Sectors', 'Information Technology'),
    ('XLK',  'RR',  'Big tech & hardware',   1, FALSE, 'Equity Sectors', 'Information Technology'),
    ('XLK',  'ETF', 'Big tech & hardware',   1, FALSE, 'Equity Sectors', 'Information Technology'),
    ('XLK',  'PS',  'Big tech & hardware',   1, FALSE, 'Equity Sectors', 'Information Technology'),
    ('QTUM', 'ETF', 'Quantum & speculative', 1, FALSE, 'Equity Sectors', 'Information Technology')
ON CONFLICT (symbol, source_code, theme) DO NOTHING;

-- Verdict-area names -> grid theme names (cosmetic).
UPDATE ref_driver_area SET label = 'Tech/software', short_label = 'Tech/software' WHERE area_key = 'tech_sw';
UPDATE ref_driver_area SET label = 'Semis',         short_label = 'Semis'         WHERE area_key = 'tech_semis';
UPDATE ref_driver_area SET label = 'Energy',        short_label = 'Energy'        WHERE area_key = 'oil';
UPDATE ref_driver_area SET label = 'Crypto',        short_label = 'Crypto'        WHERE area_key = 'bitcoin';
UPDATE ref_driver_area SET label = 'Duration',      short_label = 'Duration'      WHERE area_key = 'bonds';
UPDATE ref_driver_area SET short_label = 'Large caps' WHERE area_key = 'large_caps';
UPDATE ref_driver_area SET short_label = 'Small caps' WHERE area_key = 'small_caps';
UPDATE ref_driver_area SET label = 'Industrial metals' WHERE area_key = 'copper';   -- 2026-10-16: matches the grid theme; the tile keeps its short 'Copper'

-- 2026-10-16, user-directed: Gold as its own theme (Precious metals stays as the wider theme). Same Hedgeye-list
-- symbols that Precious metals already carries for gold (the silver row is left out).
INSERT INTO ref_symbol_theme (symbol, source_code, theme, weight, inverted, quad_category, quad_sub_category) VALUES
    ('GOLD', 'RR',  'Gold', 1, FALSE, 'Asset Class', 'Gold'),
    ('GDX',  'RR',  'Gold', 1, FALSE, 'Asset Class', 'Gold'),
    ('AAAU', 'ETF', 'Gold', 1, FALSE, 'Asset Class', 'Gold'),
    ('AAAU', 'PS',  'Gold', 1, FALSE, 'Asset Class', 'Gold')
ON CONFLICT (symbol, source_code, theme) DO NOTHING;
