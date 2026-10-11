-- =====================================================
-- seeds_area_driver.sql -- TASK_149 Area Driver Rules (design:
-- docs/mockups/area_driver_rules_design.html s3-4; logic:
-- docs/area_driver_rules_logic.md). GENERATED-STYLE seed, idempotent
-- (ON CONFLICT DO NOTHING, so /ref edits survive a re-run). Every statement
-- is <= 965 bytes. Rule thresholds are standard driver relationships, NOT
-- proven on this data -- all rules are mode='advisory'.
-- Leg check types: outlook_dir (UP|DOWN|NOT_UP|NOT_DOWN), outlook_flip
-- (UP_TO_DOWN|DOWN_TO_UP within lookback_days), delta (series change over
-- lookback_days vs threshold_value), zone, gauge, level (vs highest active
-- ref_level_watch row), rule_fired, rr_position (comparison + rr_threshold_pct).
-- =====================================================

-- Silver dollar-correlation series (feeds the Silver gate; until it has data
-- Silver borrows gold's gate).
INSERT INTO ref_corr_asset (asset_key, label, source_spec, is_usd_base, sort_order, enabled)
VALUES ('silver', 'Silver (SI=F)', '["yfinance:SI=F"]', FALSE, 45, TRUE)
ON CONFLICT (asset_key) DO NOTHING;

INSERT INTO ref_driver_series (series_key, label, expr) VALUES
    ('real_yld','Real yield (10Y less breakeven)','DGS10 - T10YIE'),
    ('t10yie','Breakeven inflation (10Y)','T10YIE'),
    ('hy_oas','High-yield spread','BAMLH0A0HYM2')
ON CONFLICT (series_key) DO NOTHING;

INSERT INTO ref_driver_area
 (area_key,label,short_label,signal_symbol,parent_key,group_key,sort_order,is_leaf,gate_asset,
  gate_fallback_asset,gate_cmp,gate_threshold,macro_area_key,rail_area_key,rail_symbol) VALUES
    ('precious_metals','Precious metals','Prec metals',NULL,NULL,'metals',5,FALSE,NULL,NULL,NULL,NULL,NULL,'commodities_metals',NULL),
    ('gold','Gold','Gold','/GC','precious_metals','metals',10,TRUE,'gold',NULL,'le',-0.3,NULL,'commodities_metals','/GC'),
    ('silver','Silver','Silver','/SI','precious_metals','metals',20,TRUE,'silver','gold','le',-0.3,NULL,'commodities_metals','/SI'),
    ('copper','Copper / commodities','Copper','/HG',NULL,'metals',30,TRUE,'crb',NULL,'le',-0.3,NULL,'commodities_ag','/HG'),
    ('oil','Oil & energy','Oil','/CL',NULL,'energy',40,TRUE,NULL,NULL,NULL,NULL,'commodities_energy','commodities_energy',NULL)
ON CONFLICT (area_key) DO NOTHING;
INSERT INTO ref_driver_area
 (area_key,label,short_label,signal_symbol,parent_key,group_key,sort_order,is_leaf,gate_asset,
  gate_fallback_asset,gate_cmp,gate_threshold,macro_area_key,rail_area_key,rail_symbol) VALUES
    ('bitcoin','Bitcoin / crypto','Bitcoin','/BTC',NULL,'risk',50,TRUE,'bitcoin',NULL,'abs_ge',0.3,'crypto','crypto',NULL),
    ('large_caps','Large caps','Lg caps','SPX',NULL,'risk',60,TRUE,NULL,NULL,NULL,NULL,NULL,'top9','SPX'),
    ('small_caps','Small caps','Sm caps','RUT',NULL,'risk',70,TRUE,NULL,NULL,NULL,NULL,NULL,'top9','RUT'),
    ('tech','Tech / long-duration growth','Tech','$COMP',NULL,'risk',80,TRUE,NULL,NULL,NULL,NULL,NULL,'top9','$COMP'),
    ('bonds','Bonds / duration','Bonds','TNX:CGI',NULL,'rates',90,TRUE,NULL,NULL,NULL,NULL,NULL,'rates_duration',NULL),
    ('credit','Credit','Credit','HYG',NULL,'rates',100,TRUE,NULL,NULL,NULL,NULL,'credit','credit',NULL)
ON CONFLICT (area_key) DO NOTHING;
INSERT INTO ref_driver_area
 (area_key,label,short_label,signal_symbol,parent_key,group_key,sort_order,is_leaf,gate_asset,
  gate_fallback_asset,gate_cmp,gate_threshold,macro_area_key,rail_area_key,rail_symbol) VALUES
    ('intl_em','Intl / EM','EM','EEM',NULL,'risk',110,TRUE,NULL,NULL,NULL,NULL,'country_etfs','country_etfs',NULL)
ON CONFLICT (area_key) DO NOTHING;

INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('GOLD_HEADWIND','Dollar up, 10Y or real yield up, gold down',NULL,NULL,'gold','headwind','warn','advisory','{legs}'),
    ('GOLD_TAILWIND','Dollar down, real yield down, gold up',NULL,NULL,'gold','tailwind','info','advisory','{legs}'),
    ('GOLD_TURNING','Dollar or 10Y just flipped down, gold in lower half of range',NULL,NULL,'gold','turning','info','advisory','{legs}'),
    ('SILVER_HEADWIND_GOLD','Gold headwind rule fires and silver is down',NULL,NULL,'silver','headwind','warn','advisory','{legs}'),
    ('SILVER_HEADWIND_IND','Silver and copper both down (industrial demand)',NULL,NULL,'silver','headwind','warn','advisory','{legs}'),
    ('SILVER_TAILWIND','Gold tailwind rule fires and silver is up',NULL,NULL,'silver','tailwind','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;
INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('SILVER_TURNING','Dollar, 10Y or copper just flipped in silver''s favour, silver in lower half',NULL,NULL,'silver','turning','info','advisory','{legs}'),
    ('COPPER_HEADWIND','Dollar up and copper down',NULL,NULL,'copper','headwind','warn','advisory','{legs}'),
    ('COPPER_TAILWIND','Dollar down and copper up',NULL,NULL,'copper','tailwind','info','advisory','{legs}'),
    ('COPPER_TURNING','Copper just flipped up while the dollar is not up',NULL,NULL,'copper','turning','info','advisory','{legs}'),
    ('OIL_HEADWIND','WTI, Brent and copper all down (demand slowing)',NULL,NULL,'oil','headwind','warn','advisory','{legs}'),
    ('OIL_TAILWIND','WTI and Brent up, oil vol not elevated',NULL,NULL,'oil','tailwind','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;
INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('OIL_STRETCHED','WTI at top of range with oil vol above calm',NULL,NULL,'oil','stretched','warn','advisory','{legs}'),
    ('BTC_HEADWIND','Bitcoin down with Nasdaq down or Nasdaq vol not calm',NULL,NULL,'bitcoin','headwind','warn','advisory','{legs}'),
    ('BTC_TAILWIND','Bitcoin and Nasdaq up, Nasdaq vol calm',NULL,NULL,'bitcoin','tailwind','info','advisory','{legs}'),
    ('BTC_STRETCHED','Bitcoin at top of range, Nasdaq vol not calm',NULL,NULL,'bitcoin','stretched','warn','advisory','{legs}'),
    ('LARGE_HEADWIND','S&P down with credit stress or elevated VIX firing',NULL,NULL,'large_caps','headwind','warn','advisory','{legs}'),
    ('LARGE_TAILWIND','S&P and HYG up, VIX calm',NULL,NULL,'large_caps','tailwind','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;
INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('LARGE_STRETCHED','S&P at top of its risk range (Risk Dial)',NULL,NULL,'large_caps','stretched','warn','advisory','{legs}'),
    ('SMALL_HEADWIND','Russell down with 10Y up or high-yield spread widening',NULL,NULL,'small_caps','headwind','warn','advisory','{legs}'),
    ('SMALL_TAILWIND','Russell up and 10Y down',NULL,NULL,'small_caps','tailwind','info','advisory','{legs}'),
    ('SMALL_TURNING','10Y just flipped down, Russell in lower half of range',NULL,NULL,'small_caps','turning','info','advisory','{legs}'),
    ('TECH_HEADWIND','Real yield rising with 10Y above your watched level',NULL,NULL,'tech','headwind','warn','advisory','{legs}'),
    ('TECH_TAILWIND','Real yield falling and Nasdaq up',NULL,NULL,'tech','tailwind','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;
INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('TECH_STRETCHED','Nasdaq vol not calm with Nasdaq at top of range',NULL,NULL,'tech','stretched','warn','advisory','{legs}'),
    ('BONDS_HEADWIND','10Y yield up with breakeven inflation rising',NULL,NULL,'bonds','headwind','warn','advisory','{legs}'),
    ('BONDS_TAILWIND','10Y yield down, bond vol not elevated',NULL,NULL,'bonds','tailwind','info','advisory','{legs}'),
    ('BONDS_TURNING','10Y yield just flipped down',NULL,NULL,'bonds','turning','info','advisory','{legs}'),
    ('CREDIT_HEADWIND','High-yield spread widening with VIX not calm',NULL,NULL,'credit','headwind','warn','advisory','{legs}'),
    ('CREDIT_TAILWIND','High-yield spread tightening and HYG up',NULL,NULL,'credit','tailwind','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;
INSERT INTO ref_cross_asset_rule
 (rule_code,description,target_symbol,target_action,area_key,verdict,severity,mode,read_text) VALUES
    ('CREDIT_STRETCHED','Credit widening while equities do not confirm (Risk Dial)',NULL,NULL,'credit','stretched','warn','advisory','{legs}'),
    ('EM_HEADWIND','Dollar up and EM equities down',NULL,NULL,'intl_em','headwind','warn','advisory','{legs}'),
    ('EM_TAILWIND','Dollar down and EM equities up',NULL,NULL,'intl_em','tailwind','info','advisory','{legs}'),
    ('EM_TURNING','Dollar just flipped down',NULL,NULL,'intl_em','turning','info','advisory','{legs}')
ON CONFLICT (rule_code) DO NOTHING;

INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('GOLD_HEADWIND','$DXY','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1),
    ('GOLD_HEADWIND','TNX:CGI','outlook_dir','UP','rates','or',NULL,NULL,NULL,NULL,'10Y',2),
    ('GOLD_HEADWIND','real_yld','delta',NULL,'rates','or',20,0.05,'>=',NULL,'Real yield',3),
    ('GOLD_HEADWIND','/GC','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Gold',4),
    ('GOLD_TAILWIND','$DXY','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1),
    ('GOLD_TAILWIND','real_yld','delta',NULL,NULL,NULL,20,-0.05,'<=',NULL,'Real yield',2),
    ('GOLD_TAILWIND','/GC','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Gold',3)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('GOLD_TURNING','$DXY','outlook_flip','UP_TO_DOWN','flip','or',5,NULL,NULL,NULL,'Dollar',1),
    ('GOLD_TURNING','TNX:CGI','outlook_flip','UP_TO_DOWN','flip','or',5,NULL,NULL,NULL,'10Y',2),
    ('GOLD_TURNING','/GC','rr_position',NULL,NULL,NULL,NULL,NULL,'<=',50,'Gold',3),
    ('SILVER_HEADWIND_GOLD','GOLD_HEADWIND','rule_fired',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Gold headwind rule fires',1),
    ('SILVER_HEADWIND_GOLD','/SI','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Silver',2),
    ('SILVER_HEADWIND_IND','/SI','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Silver',1),
    ('SILVER_HEADWIND_IND','/HG','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Copper',2)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('SILVER_TAILWIND','GOLD_TAILWIND','rule_fired',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Gold tailwind rule fires',1),
    ('SILVER_TAILWIND','/SI','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Silver',2),
    ('SILVER_TURNING','$DXY','outlook_flip','UP_TO_DOWN','flip','or',5,NULL,NULL,NULL,'Dollar',1),
    ('SILVER_TURNING','TNX:CGI','outlook_flip','UP_TO_DOWN','flip','or',5,NULL,NULL,NULL,'10Y',2),
    ('SILVER_TURNING','/HG','outlook_flip','DOWN_TO_UP','flip','or',5,NULL,NULL,NULL,'Copper',3),
    ('SILVER_TURNING','/SI','rr_position',NULL,NULL,NULL,NULL,NULL,'<=',50,'Silver',4),
    ('COPPER_HEADWIND','$DXY','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('COPPER_HEADWIND','/HG','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Copper',2),
    ('COPPER_TAILWIND','$DXY','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1),
    ('COPPER_TAILWIND','/HG','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Copper',2),
    ('COPPER_TURNING','/HG','outlook_flip','DOWN_TO_UP',NULL,NULL,5,NULL,NULL,NULL,'Copper',1),
    ('COPPER_TURNING','$DXY','outlook_dir','NOT_UP',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',2),
    ('OIL_HEADWIND','/CL','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'WTI',1),
    ('OIL_HEADWIND','/BZ','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Brent',2)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('OIL_HEADWIND','/HG','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Copper',3),
    ('OIL_TAILWIND','/CL','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'WTI',1),
    ('OIL_TAILWIND','/BZ','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Brent',2),
    ('OIL_TAILWIND','OVX:CGI','zone','not_elevated',NULL,NULL,NULL,NULL,NULL,NULL,'Oil vol',3),
    ('OIL_STRETCHED','/CL','rr_position',NULL,NULL,NULL,NULL,NULL,'>=',85,'WTI',1),
    ('OIL_STRETCHED','OVX:CGI','zone','not_investable',NULL,NULL,NULL,NULL,NULL,NULL,'Oil vol',2),
    ('BTC_HEADWIND','/BTC','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Bitcoin',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('BTC_HEADWIND','$COMP','outlook_dir','DOWN','risk','or',NULL,NULL,NULL,NULL,'Nasdaq',2),
    ('BTC_HEADWIND','VXN:CGI','zone','not_investable','risk','or',NULL,NULL,NULL,NULL,'Nasdaq vol',3),
    ('BTC_TAILWIND','/BTC','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Bitcoin',1),
    ('BTC_TAILWIND','$COMP','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Nasdaq',2),
    ('BTC_TAILWIND','VXN:CGI','zone','investable',NULL,NULL,NULL,NULL,NULL,NULL,'Nasdaq vol',3),
    ('BTC_STRETCHED','/BTC','rr_position',NULL,NULL,NULL,NULL,NULL,'>=',85,'Bitcoin',1),
    ('BTC_STRETCHED','VXN:CGI','zone','not_investable',NULL,NULL,NULL,NULL,NULL,NULL,'Nasdaq vol',2)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('LARGE_HEADWIND','SPX','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'S&P',1),
    ('LARGE_HEADWIND','credit_stress','gauge',NULL,'stress','or',NULL,NULL,NULL,NULL,'Credit stress',2),
    ('LARGE_HEADWIND','vix_elevated','gauge',NULL,'stress','or',NULL,NULL,NULL,NULL,'Equity vol elevated',3),
    ('LARGE_TAILWIND','SPX','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'S&P',1),
    ('LARGE_TAILWIND','HYG','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'HYG',2),
    ('LARGE_TAILWIND','VIX','zone','investable',NULL,NULL,NULL,NULL,NULL,NULL,'VIX',3),
    ('LARGE_STRETCHED','spx_top_range','gauge',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'S&P at top of risk range',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('SMALL_HEADWIND','RUT','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Russell 2000',1),
    ('SMALL_HEADWIND','TNX:CGI','outlook_dir','UP','rates','or',NULL,NULL,NULL,NULL,'10Y',2),
    ('SMALL_HEADWIND','hy_oas','delta',NULL,'rates','or',20,0.1,'>=',NULL,'High-yield spread',3),
    ('SMALL_TAILWIND','RUT','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Russell 2000',1),
    ('SMALL_TAILWIND','TNX:CGI','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'10Y',2),
    ('SMALL_TURNING','TNX:CGI','outlook_flip','UP_TO_DOWN',NULL,NULL,5,NULL,NULL,NULL,'10Y',1),
    ('SMALL_TURNING','RUT','rr_position',NULL,NULL,NULL,NULL,NULL,'<=',50,'Russell 2000',2)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('TECH_HEADWIND','real_yld','delta',NULL,NULL,NULL,20,0.05,'>=',NULL,'Real yield',1),
    ('TECH_HEADWIND','TNX:CGI','level',NULL,NULL,NULL,NULL,NULL,'>=',NULL,'10Y',2),
    ('TECH_TAILWIND','real_yld','delta',NULL,NULL,NULL,20,-0.05,'<=',NULL,'Real yield',1),
    ('TECH_TAILWIND','$COMP','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Nasdaq',2),
    ('TECH_STRETCHED','VXN:CGI','zone','not_investable',NULL,NULL,NULL,NULL,NULL,NULL,'Nasdaq vol',1),
    ('TECH_STRETCHED','$COMP','rr_position',NULL,NULL,NULL,NULL,NULL,'>=',85,'Nasdaq',2),
    ('BONDS_HEADWIND','TNX:CGI','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'10Y yield',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('BONDS_HEADWIND','t10yie','delta',NULL,NULL,NULL,20,0.03,'>=',NULL,'Breakeven inflation',2),
    ('BONDS_TAILWIND','TNX:CGI','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'10Y yield',1),
    ('BONDS_TAILWIND','MOVE:GIF','zone','not_elevated',NULL,NULL,NULL,NULL,NULL,NULL,'Bond vol',2),
    ('BONDS_TURNING','TNX:CGI','outlook_flip','UP_TO_DOWN',NULL,NULL,5,NULL,NULL,NULL,'10Y yield',1),
    ('CREDIT_HEADWIND','hy_oas','delta',NULL,NULL,NULL,20,0.1,'>=',NULL,'High-yield spread',1),
    ('CREDIT_HEADWIND','VIX','zone','not_investable',NULL,NULL,NULL,NULL,NULL,NULL,'VIX',2),
    ('CREDIT_TAILWIND','hy_oas','delta',NULL,NULL,NULL,20,-0.1,'<=',NULL,'High-yield spread',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;
INSERT INTO ref_cross_asset_rule_leg
 (rule_code,leg_symbol,check_type,outlook_value,leg_group,group_op,lookback_days,threshold_value,
  comparison,rr_threshold_pct,leg_label,sort_order) VALUES
    ('CREDIT_TAILWIND','HYG','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'HYG',2),
    ('CREDIT_STRETCHED','credit_equity_divergence','gauge',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Credit widening, equities not confirming',1),
    ('EM_HEADWIND','$DXY','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1),
    ('EM_HEADWIND','EEM','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'EM equities',2),
    ('EM_TAILWIND','$DXY','outlook_dir','DOWN',NULL,NULL,NULL,NULL,NULL,NULL,'Dollar',1),
    ('EM_TAILWIND','EEM','outlook_dir','UP',NULL,NULL,NULL,NULL,NULL,NULL,'EM equities',2),
    ('EM_TURNING','$DXY','outlook_flip','UP_TO_DOWN',NULL,NULL,5,NULL,NULL,NULL,'Dollar',1)
ON CONFLICT (rule_code, leg_symbol, check_type) DO NOTHING;

-- Exposure map (gauge_key = area_key). axis: asset_class | sector |
-- sub_asset_class (drv_technicals), theme (ref_symbol_theme), symbol (override).
-- inverted flips the verdict for that stock; exclude removes a stock.

INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('gold','sub_asset_class','Gold',FALSE,FALSE),
    ('gold','sub_asset_class','Gold Mining',FALSE,FALSE),
    ('gold','theme','Precious metals',FALSE,FALSE),
    ('gold','symbol','GLD',FALSE,FALSE),
    ('gold','symbol','NEM',FALSE,FALSE),
    ('gold','symbol','GDX',FALSE,FALSE),
    ('gold','symbol','SLV',FALSE,TRUE),
    ('silver','symbol','SLV',FALSE,FALSE),
    ('silver','symbol','SIL',FALSE,FALSE),
    ('silver','symbol','PSLV',FALSE,FALSE),
    ('copper','sub_asset_class','Industrial Metals',FALSE,FALSE),
    ('copper','theme','Industrial metals',FALSE,FALSE),
    ('copper','symbol','CPER',FALSE,FALSE),
    ('copper','symbol','COPX',FALSE,FALSE),
    ('copper','symbol','FCX',FALSE,FALSE),
    ('oil','sub_asset_class','Energy',FALSE,FALSE),
    ('oil','sub_asset_class','Energy (E&P)',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('oil','theme','Energy',FALSE,FALSE),
    ('oil','symbol','USO',FALSE,FALSE),
    ('oil','symbol','BNO',FALSE,FALSE),
    ('oil','symbol','XOP',FALSE,FALSE),
    ('bitcoin','asset_class','Crypto',FALSE,FALSE),
    ('bitcoin','sector','Digital Assets',FALSE,FALSE),
    ('bitcoin','theme','Crypto',FALSE,FALSE),
    ('bitcoin','symbol','MSTR',FALSE,FALSE),
    ('bitcoin','symbol','COIN',FALSE,FALSE),
    ('bitcoin','symbol','MARA',FALSE,FALSE),
    ('large_caps','sub_asset_class','Large Caps',FALSE,FALSE),
    ('large_caps','theme','Large caps',FALSE,FALSE),
    ('large_caps','symbol','SPY',FALSE,FALSE),
    ('large_caps','symbol','VOO',FALSE,FALSE),
    ('small_caps','sub_asset_class','Small Caps',FALSE,FALSE),
    ('small_caps','theme','Small caps',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('small_caps','symbol','IWM',FALSE,FALSE),
    ('small_caps','symbol','IJR',FALSE,FALSE),
    ('tech','sector','Information Technology',FALSE,FALSE),
    ('tech','theme','Tech/software',FALSE,FALSE),
    ('tech','theme','Semis',FALSE,FALSE),
    ('tech','sub_asset_class','Software',FALSE,FALSE),
    ('tech','sub_asset_class','Semiconductors',FALSE,FALSE),
    ('bonds','sub_asset_class','Long Bond',FALSE,FALSE),
    ('bonds','sub_asset_class','TIPS',FALSE,FALSE),
    ('bonds','theme','Duration',FALSE,FALSE),
    ('bonds','symbol','TLT',FALSE,FALSE),
    ('bonds','symbol','IEF',FALSE,FALSE),
    ('bonds','symbol','PFIX',TRUE,FALSE),
    ('bonds','symbol','TBT',TRUE,FALSE),
    ('credit','sub_asset_class','Leveraged Loans',FALSE,FALSE),
    ('credit','sub_asset_class','BDCs',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('credit','theme','Credit',FALSE,FALSE),
    ('credit','symbol','HYG',FALSE,FALSE),
    ('credit','symbol','LQD',FALSE,FALSE),
    ('credit','symbol','JNK',FALSE,FALSE),
    ('intl_em','sector','Country ETF',FALSE,FALSE),
    ('intl_em','theme','Emerging',FALSE,FALSE),
    ('intl_em','theme','Developed intl',FALSE,FALSE),
    ('intl_em','symbol','EEM',FALSE,FALSE),
    ('intl_em','symbol','FXI',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
