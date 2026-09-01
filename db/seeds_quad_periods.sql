-- seeds_quad_periods.sql
-- Monthly quad probability distribution (quad1_pct..quad4_pct), captured from the
-- "U.S. Monthly Quad Forecast" chart (2026-06-21).
-- Each row sums to 100.
-- Keyed by (period_type, year, period_num) — standard calendar months/quarters.
-- ON CONFLICT updates label + percentages so re-running the seed is safe.
--
-- 2026-08-31: `quad` deliberately dropped (kept NULL) for period_type='monthly'
-- rows -- it was a hand-typed dominant-quad label that drifted out of sync
-- with its own quad1_pct..quad4_pct distribution on 4 of these 12 rows
-- (Aug-26 shown here as 'Quad 1' despite quad3_pct=30 being the actual max).
-- The read side (etl/derive_macro.py::_dominant_quad_num/_effective_quad_label,
-- api/routers/dash.py::_effective_quad_col, api/routers/health.py::_eff_quad)
-- already computes the dominant quad live from the pct columns and only
-- fell back to this column when pcts were missing/all-zero -- "the
-- distribution wins" per their docstrings -- so dropping the stale label
-- removes the only thing that could ever disagree with it. Quarterly rows
-- (loaded separately via etl/load_raw.py::load_hqds, not seeded in this
-- file) are unaffected -- quarterly `quad` is the fixed one-hot period
-- quad, not an argmax-of-distribution field, and stays authoritative.
INSERT INTO ref_quad_periods
  (period_type, year, period_num, quad, label,
   quad1_pct, quad2_pct, quad3_pct, quad4_pct)
VALUES
  ('monthly', 2026,  5, NULL, 'May-26',  0, 76,  0, 24),
  ('monthly', 2026,  6, NULL, 'Jun-26', 50,  2,  3, 45),
  ('monthly', 2026,  7, NULL, 'Jul-26', 14,  6, 25, 55),
  ('monthly', 2026,  8, NULL, 'Aug-26', 20, 25, 30, 25),
  ('monthly', 2026,  9, NULL, 'Sep-26', 45, 37,  8, 10),
  ('monthly', 2026, 10, NULL, 'Oct-26', 25, 30, 25, 20),
  ('monthly', 2026, 11, NULL, 'Nov-26', 40, 33, 12, 15),
  ('monthly', 2026, 12, NULL, 'Dec-26', 34, 42, 13, 11),
  ('monthly', 2027,  1, NULL, 'Jan-27',  5, 50, 41,  4),
  ('monthly', 2027,  2, NULL, 'Feb-27', 27,  3,  7, 63),
  ('monthly', 2027,  3, NULL, 'Mar-27', 63,  7,  3, 27),
  ('monthly', 2027,  4, NULL, 'Apr-27', 54,  6,  4, 36)
ON CONFLICT (period_type, year, period_num) DO UPDATE SET
  quad      = NULL,
  label     = EXCLUDED.label,
  quad1_pct = EXCLUDED.quad1_pct,
  quad2_pct = EXCLUDED.quad2_pct,
  quad3_pct = EXCLUDED.quad3_pct,
  quad4_pct = EXCLUDED.quad4_pct;
