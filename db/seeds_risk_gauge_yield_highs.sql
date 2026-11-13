-- 2026-11-13, user: "Yields at a watched level" covers the 10Y, 2Y and 30Y. Idempotent; run AFTER seeds_risk_gauge_help.sql / _how.sql.
-- 30Y watch levels (x10 scale like TNX:CGI: 50 = 5.0%). The 2Y 4.5% / 5.0% levels are in etl/derive_risk_dial.py (_YIELD_EXTRA_LEVELS).
INSERT INTO ref_level_watch (tos_symbol, level_value, tolerance, label, is_active) VALUES
    ('TYX:CGI', 50.00, 1.00, '30Y at 5% (x10-scaled)',   TRUE),
    ('TYX:CGI', 55.00, 1.00, '30Y at 5.5% (x10-scaled)', TRUE),
    ('TYX:CGI', 60.00, 1.00, '30Y at 6% (x10-scaled)',   TRUE)
ON CONFLICT (tos_symbol, level_value) DO NOTHING;

-- Popup text. Reference highs: daily closes (ref_record_level / FRED), checked 2026-11-13; the 10Y list also has recent cycle highs.
UPDATE ref_risk_gauge SET help = E'The 2-year, 10-year or 30-year Treasury yield is at a level you are watching or near the top of its range.\n- Fires when: Any of them is within about 0.1 point of a watched level (2Y and 10Y: 4.0%, 4.5%, 5.0%; 30Y: 5.0%, 5.5%, 6.0%), or in the top 15% of its own risk range.\n- Why it matters: Fast or high yields raise borrowing costs and pressure stock prices.\n- Reference highs (closing yield): 2Y all-time high 16.95% (Sep 8, 1981). 10Y all-time high 15.84% (Sep 30, 1981); then 6.79% (Jan 21, 2000), 5.26% (Jun 12, 2007), 4.98% (Oct 19, 2023), 5.31% (Oct 5, 2026). 30Y all-time high 15.21% (Oct 26, 1981).'
WHERE gauge_key = 'yield_level_watch';
