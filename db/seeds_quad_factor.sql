-- =====================================================
-- seeds_quad_factor.sql -- Quad market check factors (design: DESIGN_SPEC_8.md; Hedgeye Early Look 2026-10-19 "Macro Grind").
-- Idempotent (ON CONFLICT DO NOTHING, so edits made later survive a re-run). Every statement is <= 965 bytes.
-- ALL bands and weights are GUESSES, chosen so a normal two-week wiggle reads as flat. Bands: price/basket in %, relative in
-- points, fred_change in basis points. "3W" ~ Hedgeye's TRADE duration, "3M" ~ TREND duration.
-- direction = sign applied to the move checks; trend_direction = sign applied to the trend check (HY: spread up = growth down, but
-- HYG above its trend = growth up). weight 0 = shown in the list but does not vote (the dollar: Hedgeye is long USD *in* Quad 2).
-- =====================================================

-- Family 1: risk & liquidity (Hedgeye: "in #Quad2 long Bitcoin and QQQ together; in #Quad4 both get killed";
-- "in #Quad4 bond yields break TRADE and TREND")
INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,band_3w,band_3m,trend_source,trend_symbol,weight,min_checks,sort_order) VALUES
 ('qqq','QQQ',1,'growth',1,1,'price','QQQ',1,2,'technicals','QQQ',1,2,10),
 ('btc','Bitcoin',1,'growth',1,1,'price','/BTC',3,6,'rr_outlook','/BTC',1,2,20),
 ('y10','10Y yield',1,'growth',1,1,'fred_change','DGS10',10,20,'rr_outlook','TNX:CGI',1,2,30),
 ('y2','2Y yield',1,'growth',1,1,'fred_change','DGS2',10,20,'rr_outlook','DGS2:FRED',1,2,35)
ON CONFLICT (factor_key) DO NOTHING;

INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,band_3w,band_3m,trend_source,trend_symbol,weight,min_checks,sort_order,notes) VALUES
 ('usd','US Dollar',1,'inflation',-1,-1,'price','$DXY',0.5,1,'rr_outlook','$DXY',0,2,40,
  'Shown only. Hedgeye stayed long USD in Quad 2 (and Bitcoin trades with it), so a firm dollar does not discriminate between Quad 2 and 4.')
ON CONFLICT (factor_key) DO NOTHING;

-- Family 2: inflation & commodities (Hedgeye: commodities crash in Quad 4; CRB / WTI / XLE trending up = inflation accelerating)
INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,band_3w,band_3m,trend_source,trend_symbol,weight,min_checks,sort_order,notes) VALUES
 ('basket','Commodity basket (CRB stand-in)',2,'inflation',1,1,'basket','/CL,/BZ,/NG,/HG,/GC,/SI,/ZC,/ZW,/ZS',1,2,'technicals','GSG',1,2,50,
  'Equal-weight average of the futures we track (the CRB itself is not tracked); symbols without enough history are skipped.'),
 ('wti','WTI oil',2,'inflation',1,1,'price','/CL',2,4,'rr_outlook','/CL',1,2,60,NULL),
 ('xle','Energy stocks (XLE)',2,'inflation',1,1,'price','XLE',1,2,'technicals','XLE',1,2,70,NULL),
 ('be10','10Y breakeven',2,'inflation',1,1,'fred_change','T10YIE',5,10,'none',NULL,1,2,80,NULL)
ON CONFLICT (factor_key) DO NOTHING;

-- Family 3: growth, credit & cyclicals (Hedgeye: short the Credit Cycle -- HYG, PSP -- and Cyclicals -- XLI; shorts working)
INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,band_3w,band_3m,trend_source,trend_symbol,weight,min_checks,sort_order) VALUES
 ('hy','HY credit spread',3,'growth',-1,1,'fred_change','BAMLH0A0HYM2',10,20,'technicals','HYG',1,2,90),
 ('cyc','Cyclicals vs defensives',3,'growth',1,1,'relative','XLI,XLY,XLF,XLB',1,2,'none',NULL,1,2,100)
ON CONFLICT (factor_key) DO NOTHING;

UPDATE ref_quad_factor SET minus_symbols = 'XLU,XLP,XLV' WHERE factor_key = 'cyc' AND minus_symbols IS NULL;

INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,minus_symbols,band_3w,band_3m,trend_source,weight,min_checks,sort_order) VALUES
 ('cug','Copper vs gold',3,'growth',1,1,'relative','/HG','/GC',1,2,'none',1,2,110),
 ('small','Small caps vs S&P',3,'growth',1,1,'relative','IWM','SPX',1,2,'none',0.5,2,120)
ON CONFLICT (factor_key) DO NOTHING;

INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,trend_source,weight,min_checks,sort_order,notes) VALUES
 ('claims','Jobless claims',3,'growth',-1,1,'claims','ICSA','none',0.5,1,130,
  '4-week average vs 13-week average of initial claims: five percent or more above = growth down, five percent or more below = growth up.')
ON CONFLICT (factor_key) DO NOTHING;

-- Risk Dial: growth signals breaking the Quad. Ships INACTIVE until the forward-return test is run (see DESIGN_SPEC_8.md).
INSERT INTO ref_risk_gauge (gauge_key, label, weight, is_active, category, notes) VALUES
    ('quad_growth_break', 'Growth signals breaking the Quad', 2, FALSE, 'macro',
     'Fires when the dashboard Quad is 1 or 2 and the market growth meter is at or below -20 for the confirm days (drv_quad_check). Inactive until tested.')
ON CONFLICT (gauge_key) DO NOTHING;

-- 2026-10-19: the real CRB index (TOS symbol TRCCRBTR). Hedgeye reads it directly ("CRB Index up 11.7 percent over three months").
-- The futures basket stays as a backup at half weight until the CRB has history.
INSERT INTO ref_quad_factor
 (factor_key,label,family,meter,direction,trend_direction,kind,symbols,band_3w,band_3m,trend_source,trend_symbol,weight,min_checks,sort_order,notes) VALUES
 ('crb','CRB Index',2,'inflation',1,1,'price','TRCCRBTR',1,2,'technicals','TRCCRBTR',1,2,45,
  'Thomson Reuters / CoreCommodity CRB Total Return (TOS TRCCRBTR). Missing until the symbol is on a TOS watchlist and has been exported.')
ON CONFLICT (factor_key) DO NOTHING;

UPDATE ref_quad_factor SET weight = 0.5 WHERE factor_key = 'basket' AND weight = 1;

