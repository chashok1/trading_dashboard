-- 2026-11-21: Risk Dial calendar gauges -- options expiration (monthly / quarterly) and the user's chosen economic events.
-- They replace the OPEX/events panel that used to sit on the dashboard's right side. Informational only: weight 0, so they
-- never change the risk budget. Dates come from ref_calendar_event; windows are tunable in ref_settings.
INSERT INTO ref_risk_gauge (gauge_key, label, weight, is_active, category, notes) VALUES
    ('opex_monthly',   'Monthly options expiration',   0, TRUE, 'macro', 'Calendar warning, informational only (weight 0).'),
    ('opex_quarterly', 'Quarterly options expiration', 0, TRUE, 'macro', 'Calendar warning (triple witching), informational only (weight 0).'),
    ('econ_events',    'Economic events ahead',        0, TRUE, 'macro', 'Calendar warning for the event types chosen in the E.IND picker, informational only (weight 0).')
ON CONFLICT (gauge_key) DO NOTHING;

INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('rd_opex_monthly_days', '3', 'opex_monthly gauge: warn this many calendar days before a monthly options expiration (3rd Friday, Thursday if a holiday).'),
    ('rd_opex_qtly_days',    '5', 'opex_quarterly gauge: warn this many calendar days before a quarterly (Mar/Jun/Sep/Dec) options expiration.'),
    ('rd_events_days',       '5', 'econ_events gauge: warn this many calendar days before any event type chosen in the E.IND picker (dashboard_calendar_types).')
ON CONFLICT (setting_name) DO NOTHING;

UPDATE ref_risk_gauge SET
    help = E'A monthly options expiration is coming up.\n- Fires when: the 3rd Friday of a non-quarter month (Thursday if Friday is a holiday) is within 3 days (setting rd_opex_monthly_days).\n- Why it matters: Dealer hedging around big option strikes can pin prices before expiration and release them after, so moves can look odd.',
    how_helps = 'Heads-up only. It does not change the risk score or any recommendation.'
WHERE gauge_key = 'opex_monthly';

UPDATE ref_risk_gauge SET
    help = E'A quarterly (triple witching) options expiration is coming up.\n- Fires when: the March, June, September or December options expiration is within 5 days (setting rd_opex_qtly_days).\n- Why it matters: Stock options, index options and futures all expire together, so volume is heavy and prices can swing around the expiry.',
    how_helps = 'Heads-up only. It does not change the risk score or any recommendation.'
WHERE gauge_key = 'opex_quarterly';

UPDATE ref_risk_gauge SET
    help = E'One of the economic events you chose to watch is coming up.\n- Fires when: an event type picked in the E.IND gear (Fed meeting, CPI, jobs, ...) falls within 5 days (setting rd_events_days).\n- Why it matters: Scheduled releases can move the whole market on the day, and prices often wait for them.',
    how_helps = 'Heads-up only. It does not change the risk score or any recommendation.'
WHERE gauge_key = 'econ_events';
