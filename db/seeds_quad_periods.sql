-- seeds_quad_periods.sql
-- Monthly quad probability distribution (quad1_pct..quad4_pct), captured from the
-- "U.S. Monthly Quad Forecast" chart and confirmed by the user (2026-06-21).
-- Each row sums to 100; `quad` is the argmax (dominant) and matches the chart's
-- top-panel badge. Quarterly rows are untouched (they carry no distribution).
--
-- ON CONFLICT updates ONLY the percentages on existing rows (the quad/label/dates
-- from load_hqds are preserved).  For months not yet in the table, the full row
-- is inserted so the period is available for MacroNet even before the next HQds load.
--
-- PREREQ: requires the quad1_pct..quad4_pct columns (db/baseline.sql TASK_74).
--
-- Start-date convention: load_hqds uses mid-month boundaries (~10th/11th).
-- Confirmed from Q7: May-26=2026-05-11, Jun-26=2026-06-10, Jul-26=2026-07-11,
-- Aug-26=2026-08-11.  Sep-26 onwards are new rows using the same pattern.

-- Existing months: UPSERT pct only (start_date must match load_hqds rows exactly)
INSERT INTO ref_quad_periods
  (period_type, start_date, end_date, quad, label,
   quad1_pct, quad2_pct, quad3_pct, quad4_pct)
VALUES
  ('monthly','2026-05-11','2026-06-09','Quad 1','May-26',  0, 76,  0, 24),
  ('monthly','2026-06-10','2026-07-10','Quad 4','Jun-26', 50,  2,  3, 45),
  ('monthly','2026-07-11','2026-08-10','Quad 3','Jul-26', 14,  6, 25, 55),
  ('monthly','2026-08-11','2026-09-09','Quad 1','Aug-26', 20, 25, 30, 25)
ON CONFLICT (period_type, start_date) DO UPDATE SET
  quad1_pct = EXCLUDED.quad1_pct,
  quad2_pct = EXCLUDED.quad2_pct,
  quad3_pct = EXCLUDED.quad3_pct,
  quad4_pct = EXCLUDED.quad4_pct;

-- New months not yet in load_hqds: full insert (mid-month boundary pattern)
INSERT INTO ref_quad_periods
  (period_type, start_date, end_date, quad, label,
   quad1_pct, quad2_pct, quad3_pct, quad4_pct)
VALUES
  ('monthly','2026-09-10','2026-10-10','Quad 1','Sep-26', 45, 37,  8, 10),
  ('monthly','2026-10-11','2026-11-09','Quad 2','Oct-26', 25, 30, 25, 20),
  ('monthly','2026-11-10','2026-12-10','Quad 1','Nov-26', 40, 33, 12, 15),
  ('monthly','2026-12-11','2027-01-10','Quad 2','Dec-26', 34, 42, 13, 11),
  ('monthly','2027-01-11','2027-02-07','Quad 2','Jan-27',  5, 50, 41,  4),
  ('monthly','2027-02-08','2027-03-10','Quad 4','Feb-27', 27,  3,  7, 63),
  ('monthly','2027-03-11','2027-04-09','Quad 1','Mar-27', 63,  7,  3, 27),
  ('monthly','2027-04-10','2027-05-10','Quad 1','Apr-27', 54,  6,  4, 36)
ON CONFLICT (period_type, start_date) DO UPDATE SET
  quad1_pct = EXCLUDED.quad1_pct,
  quad2_pct = EXCLUDED.quad2_pct,
  quad3_pct = EXCLUDED.quad3_pct,
  quad4_pct = EXCLUDED.quad4_pct;
