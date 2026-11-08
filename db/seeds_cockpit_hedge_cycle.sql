-- 2026-11-05: Risk Dial "hedge cycle" gauges (event hedges building -> rally from hedge removal -> fuel used up).
-- Idea from the SpotGamma-style note: relief rallies after an event are partly forced buying as protection is sold back, and that
-- buying is temporary. Help text is in seeds_risk_gauge_help.sql. Thresholds below are tunable in ref_settings.
INSERT INTO ref_risk_gauge (gauge_key, label, weight, is_active, category, notes) VALUES
    ('event_hedging',       'Event hedges building',            2, TRUE, 'vol', 'Hedge cycle stage 1: protection being bought ahead of an event.'),
    ('hedge_removal_rally', 'Rally from hedge removal',         2, TRUE, 'vol', 'Hedge cycle stage 2: VIX collapses while SPX rises, so part of the rally is forced buying.'),
    ('rally_fuel_spent',    'Hedge-removal buying used up',     1, TRUE, 'vol', 'Hedge cycle stage 3: after a hedge-removal rally VIX stops falling and SPX has not made a new high.')
ON CONFLICT (gauge_key) DO NOTHING;

INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('rd_hedge_event_days',   '5',  'event_hedging gauge: a scheduled event within this many calendar days counts as "event ahead".'),
    ('rd_hedge_event_cats',   'Fed Meeting,CPI MoM,NFP,PCE,Jackson hole fed speech', 'event_hedging gauge: ref_calendar_event categories that count as a major event (comma separated).'),
    ('rd_hedge_event_always_cats', 'Fed Meeting,CPI MoM,NFP', 'event_hedging gauge: events in this list fire it with just VIX9D above VIX (no extra rise needed). Comma separated, must also be in rd_hedge_event_cats.'),
    ('rd_hedge_9d_rise_pct',  '40', 'event_hedging gauge: VIX9D rise over 5 sessions (%%) that fires it with or without an event.'),
    ('rd_hedge_event_rise_pct', '10', 'event_hedging gauge: with an event ahead and VIX9D above VIX, VIX9D must also be up this much (%%) over 5 sessions.'),
    ('rd_hedge_vix_drop_pct', '15', 'hedge_removal_rally gauge: one-day VIX fall (%%) that, with SPX up, fires it.'),
    ('rd_hedge_fuel_days',    '5',  'rally_fuel_spent gauge: sessions after a hedge-removal rally during which it can fire.')
ON CONFLICT (setting_name) DO NOTHING;
