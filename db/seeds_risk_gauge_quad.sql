-- 2026-11-21, user-directed: two Quad market-check gauges go live.
--  quad_growth_break (growth meter at or below -20 for 2 dates while the Quad expects growth up): switched ON, weight 2.
--  quad_transition (market check's transition label is TRANSITION, risk 60+): new, weight 1 (smaller so the two do not double-count).
-- Runs after seeds_risk_gauge_help.sql (sorted order), so the help text below wins over its "(Inactive for now.)" wording.
INSERT INTO ref_risk_gauge (gauge_key, label, weight, is_active, category, notes) VALUES
    ('quad_transition', 'Market no longer supports the Quad', 1, TRUE, 'macro',
     'Fires when the Quad market check label is TRANSITION (transition risk 60+, confirmed for the confirm days) against the dashboard 60-day Quad.')
ON CONFLICT (gauge_key) DO NOTHING;

UPDATE ref_risk_gauge SET is_active = TRUE, weight = 2 WHERE gauge_key = 'quad_growth_break' AND is_active = FALSE;

UPDATE ref_risk_gauge SET
    help = E'Market signals say growth is slowing even though the Quad expects growth to rise.\n- Fires when: The Quad is 1 or 2 and the market growth meter is at or below -20 for 2 days.\n- Why it matters: It is an early sign the Quad is about to change.',
    how_helps = 'Growth may be turning down. Review positions that depend on the Quad staying up.'
WHERE gauge_key = 'quad_growth_break';

UPDATE ref_risk_gauge SET
    help = E'Prices no longer support the Quad the dashboard is in.\n- Fires when: The Quad market check shows transition risk of 60 or more for 2 dates in a row (growth or inflation has turned against the Quad).\n- Why it matters: The market may be moving to a different Quad. It also catches an inflation-led break that the growth gauge misses.',
    how_helps = 'The regime may be changing. Review positions built for the current Quad.'
WHERE gauge_key = 'quad_transition';

-- 2026-11-21, user-directed: lists_quad_conflict switched ON at weight 1 (an independent, list-based confirmation of the price-based Quad gauges above).
UPDATE ref_risk_gauge SET is_active = TRUE, weight = 1 WHERE gauge_key = 'lists_quad_conflict' AND is_active = FALSE;
UPDATE ref_risk_gauge SET help = replace(help, ' (Inactive.)', '') WHERE gauge_key = 'lists_quad_conflict';
