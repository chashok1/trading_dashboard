-- seeds_commodity_industrial.sql -- 2026-11-11, user-directed: the "Industrial & Ag" Macro Rail panel is split in two.
--   Industrial (new area 'commodities_industrial'): CRB Index, Copper, CPER, URA, WOOD.
--   Ag (stays 'commodities_ag'): Corn, Wheat, Soybeans, Coffee, Sugar, Live Cattle + CORN / WEAT / SOYB ETFs.
-- Apply AFTER seeds_macro_area.sql and seeds_commodity_ag.sql (those still list the old single panel). Idempotent.
INSERT INTO ref_macro_area (area_key, label, member_symbol, role, sort_order, enabled, pinned) VALUES
  ('commodities_industrial', 'CRB Index',   'TRCCRBTR', 'rr_only', 5,  TRUE, FALSE),
  ('commodities_industrial', 'Copper',      '/HG',      'rr_only', 10, TRUE, FALSE),
  ('commodities_industrial', 'Industrial',  'CPER',     'dual',    15, TRUE, FALSE),
  ('commodities_industrial', 'Industrial',  'URA',      'dual',    20, TRUE, FALSE),
  ('commodities_industrial', 'Industrial',  'WOOD',     'dual',    60, TRUE, FALSE)
ON CONFLICT (area_key, member_symbol) DO UPDATE SET
  label = EXCLUDED.label, role = EXCLUDED.role, sort_order = EXCLUDED.sort_order, enabled = TRUE;

DELETE FROM ref_macro_area WHERE area_key = 'commodities_ag' AND member_symbol IN ('TRCCRBTR', '/HG', 'CPER', 'URA', 'WOOD');
UPDATE ref_macro_area SET label = 'Ag' WHERE area_key = 'commodities_ag' AND role = 'dual';

-- The Copper area-driver rule reads its rail row from the Industrial panel now.
UPDATE ref_driver_area SET rail_area_key = 'commodities_industrial' WHERE rail_area_key = 'commodities_ag';
