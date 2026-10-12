-- TASK_150: sources whose REMOVE/REDUCE showed no edge (SSS/RR/ETF sells,
-- n = 683-1,613). A sell backed ONLY by these gets low_confidence (annotation
-- only; consolidated_action never changes). Comma-separated source_code list.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
    ('lowconf_sell_sources', 'SSS,RR,ETF',
     'TASK_150: comma-separated source_code list whose sells measured no edge - a sell backed only by these is flagged LOW CONF (annotate only)')
ON CONFLICT (setting_name) DO NOTHING;
