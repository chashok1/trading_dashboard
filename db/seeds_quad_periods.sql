-- seeds_quad_periods.sql
-- Monthly quad probability distribution (quad1_pct..quad4_pct), captured from the
-- "U.S. Monthly Quad Forecast" chart (2026-06-21).
-- Each row sums to 100; `quad` is the argmax (dominant).
-- Keyed by (period_type, year, period_num) — standard calendar months/quarters.
-- ON CONFLICT updates quad + percentages so re-running the seed is safe.

INSERT INTO ref_quad_periods
  (period_type, year, period_num, quad, label,
   quad1_pct, quad2_pct, quad3_pct, quad4_pct)
VALUES
  ('monthly', 2026,  5, 'Quad 1', 'May-26',  0, 76,  0, 24),
  ('monthly', 2026,  6, 'Quad 4', 'Jun-26', 50,  2,  3, 45),
  ('monthly', 2026,  7, 'Quad 3', 'Jul-26', 14,  6, 25, 55),
  ('monthly', 2026,  8, 'Quad 1', 'Aug-26', 20, 25, 30, 25),
  ('monthly', 2026,  9, 'Quad 1', 'Sep-26', 45, 37,  8, 10),
  ('monthly', 2026, 10, 'Quad 2', 'Oct-26', 25, 30, 25, 20),
  ('monthly', 2026, 11, 'Quad 1', 'Nov-26', 40, 33, 12, 15),
  ('monthly', 2026, 12, 'Quad 2', 'Dec-26', 34, 42, 13, 11),
  ('monthly', 2027,  1, 'Quad 2', 'Jan-27',  5, 50, 41,  4),
  ('monthly', 2027,  2, 'Quad 4', 'Feb-27', 27,  3,  7, 63),
  ('monthly', 2027,  3, 'Quad 1', 'Mar-27', 63,  7,  3, 27),
  ('monthly', 2027,  4, 'Quad 1', 'Apr-27', 54,  6,  4, 36)
ON CONFLICT (period_type, year, period_num) DO UPDATE SET
  quad      = EXCLUDED.quad,
  quad1_pct = EXCLUDED.quad1_pct,
  quad2_pct = EXCLUDED.quad2_pct,
  quad3_pct = EXCLUDED.quad3_pct,
  quad4_pct = EXCLUDED.quad4_pct;
