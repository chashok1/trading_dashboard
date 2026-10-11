-- Tech split (2026-10-11, user-directed): 'tech' becomes a parent; four leaf areas
-- share its rates rules (rules_from) and each is cancelled to Quiet when
-- Hedgeye is bullish on most covered members (hedgeye_cancels).
UPDATE ref_driver_area SET is_leaf = FALSE WHERE area_key = 'tech';
INSERT INTO ref_driver_area
 (area_key,label,short_label,signal_symbol,parent_key,group_key,sort_order,is_leaf,
  rules_from,hedgeye_cancels) VALUES
    ('tech_sw','Software & cybersecurity','SW/Cyber','IGV','tech','risk',81,TRUE,'tech',TRUE),
    ('tech_semis','Semiconductors','Semis','SMH','tech','risk',82,TRUE,'tech',TRUE),
    ('tech_big','Big tech & hardware','Big tech','XLK','tech','risk',83,TRUE,'tech',TRUE),
    ('tech_spec','Quantum & speculative','Quantum','QTUM','tech','risk',84,TRUE,'tech',TRUE)
ON CONFLICT (area_key) DO NOTHING;
DELETE FROM ref_gauge_transmission WHERE gauge_key = 'tech';
INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('tech_sw','sub_asset_class','Software',FALSE,FALSE),
    ('tech_sw','sub_asset_class','Software/AI',FALSE,FALSE),
    ('tech_sw','sub_asset_class','Cybersecurity',FALSE,FALSE),
    ('tech_sw','sub_asset_class','Cloud Computing',FALSE,FALSE),
    ('tech_sw','theme','Tech/software',FALSE,FALSE),
    ('tech_sw','symbol','IGV',FALSE,FALSE),
    ('tech_sw','symbol','PANW',FALSE,FALSE),
    ('tech_sw','symbol','DT',FALSE,FALSE),
    ('tech_sw','symbol','KVYO',FALSE,FALSE),
    ('tech_sw','symbol','ROP',FALSE,FALSE),
    ('tech_sw','symbol','FSLY',FALSE,FALSE),
    ('tech_sw','symbol','AKAM',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
INSERT INTO ref_gauge_transmission (gauge_key, axis, category, inverted, exclude) VALUES
    ('tech_semis','sub_asset_class','Semiconductors',FALSE,FALSE),
    ('tech_semis','theme','Semis',FALSE,FALSE),
    ('tech_semis','symbol','SMH',FALSE,FALSE),
    ('tech_semis','symbol','CAMT',FALSE,FALSE),
    ('tech_semis','symbol','POET',FALSE,FALSE),
    ('tech_spec','sub_asset_class','Quantum Tech',FALSE,FALSE),
    ('tech_spec','sub_asset_class','Quantum/AI',FALSE,FALSE),
    ('tech_spec','sub_asset_class','Mining/Tech',FALSE,FALSE),
    ('tech_spec','sub_asset_class','Blockchain/Tech',FALSE,FALSE),
    ('tech_spec','sub_asset_class','Crypto',FALSE,FALSE),
    ('tech_spec','sub_asset_class','AI',FALSE,FALSE),
    ('tech_spec','symbol','IONQ',FALSE,FALSE),
    ('tech_big','sector','Information Technology',FALSE,FALSE),
    ('tech_big','sub_asset_class','Technology',FALSE,FALSE)
ON CONFLICT (gauge_key, axis, category) DO NOTHING;
DELETE FROM drv_area_verdict WHERE area_key = 'tech';
DELETE FROM drv_driver_exposure WHERE area_key = 'tech';
