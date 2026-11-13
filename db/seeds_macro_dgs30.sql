-- 2026-11-13, user: the Yield curve panel shows the 30Y. Load its FRED history with: python -m etl.fetch_macro --series DGS30 --full
-- (the nightly fetch then keeps it current). Until then the panel falls back to the stored 30Y quotes.
INSERT INTO ref_macro_series (series_id, label, grp, unit, sort_order, enabled)
VALUES ('DGS30', '30Y Treasury', 'rates', '%', 30, TRUE)
ON CONFLICT (series_id) DO NOTHING;
