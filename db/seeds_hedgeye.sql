-- Seeds for the Hedgeye feed pipeline. Idempotent (ON CONFLICT DO NOTHING/UPDATE).
-- Apply after db/hedgeye_schema.sql.

-- ref_settings defaults (secrets stay in .env, never here) -------------------
INSERT INTO ref_settings (setting_name, setting_value) VALUES
  ('hedgeye_enabled',            'false'),
  ('hedgeye_poll_interval_sec',  '240'),
  ('hedgeye_email_provider',     'imap'),
  ('hedgeye_imap_host',          'imap.gmail.com'),
  ('hedgeye_imap_user',          'chilukua14@gmail.com'),
  ('hedgeye_mailbox',            'INBOX'),
  ('hedgeye_image_dir',          'etl/working/hedgeye_charts'),
  ('hedgeye_hefiles_dir',        'C:\Ashok\Investing\Stocks\HEFiles'),
  ('hedgeye_msr_dir',            'C:\Ashok\Investing\Stocks\MSR'),
  ('hedgeye_llm_enabled',        'false')
ON CONFLICT (setting_name) DO NOTHING;

-- Macro series for the inflation nowcast --------------------------------------
-- grp/sort_order match ref_macro_series live schema (grp NOT NULL, no default).
INSERT INTO ref_macro_series (series_id, label, grp, sort_order, enabled)
VALUES ('HE_CPI_NOWCAST', 'Hedgeye Monthly Inflation Nowcast (y/y %)', 'inflation', 200, TRUE)
ON CONFLICT (series_id) DO NOTHING;

-- Classifier registry (mirrors etl/hedgeye/classify.EMAIL_TYPES) ---------------
INSERT INTO ref_hedgeye_email_type
  (email_type, destination, cadence, subject_re, asset_name, parser) VALUES
  ('the_call_access',     'DROP',     'daily',     '^The Call @ Hedgeye \| Access Here', NULL, NULL),
  ('momo_tracker',        'DROP',     'daily',     '^MOMO Tracker', NULL, NULL),
  ('macro_show_access',   'ANALYSIS', 'daily',     '^THE MACRO SHOW:.*Access Show', NULL, NULL),
  ('risk_range',          'DATA',     'daily',     '^RISK RANGE.*SIGNALS', NULL, 'risk_range'),
  ('real_time_alert',     'DATA',     'intraday',  'Real-Time Alert', 'stock_alerts_800px.png', 'real_time_alert'),
  ('etf_changes',         'DATA',     'intraday',  'ETF Pro Change', 'etf_pro_plus_1_800px.png', 'etf_changes'),
  ('investing_ideas',     'DATA',     'intraday',  '^(Add|Remove)\b.*\b(LONG|SHORT) Side', 'investing_ideas_800px.png', 'investing_ideas'),
  ('signal_strength',     'DATA',     'intraday',  '^Signal Strength Stocks', 'signal_strength_stocks_800px.png', 'signal_strength'),
  ('portfolio_solutions', 'DATA',     'weekly',    '^PORTFOLIO SOLUTIONS.*Re-Rank', NULL, 'portfolio_solutions'),
  ('the_call',            'DATA',     'daily',     '^The Call @ Hedgeye \| Replay', NULL, 'the_call'),
  ('macro_show_summary',  'DATA',     'daily',     '^THE MACRO SHOW:.*Summary Notes', NULL, 'macro_show_summary'),
  ('inflation_nowcast',   'DATA',     'monthly',   'Monthly Inflation Nowcast', 'macro_select_800px.png', 'inflation_nowcast'),
  ('early_look',          'ANALYSIS', 'daily',     '^EARLY LOOK', NULL, 'early_look'),
  ('market_situation',    'ANALYSIS', 'daily',     '^MARKET SITUATION REPORT', 'market_situation_report_800px.png', 'market_situation'),
  ('top3',                'ANALYSIS', 'daily',     'Top 3 Things', NULL, NULL),
  ('macro_week_summary',  'ANALYSIS', 'weekly',    '^Macro Week Summary Notes', NULL, NULL),
  ('quarterly_outlook',   'RULES',    'quarterly', 'Quarterly Investment Outlook', NULL, 'quarterly_outlook')
ON CONFLICT (email_type) DO UPDATE SET
  destination=EXCLUDED.destination, cadence=EXCLUDED.cadence,
  subject_re=EXCLUDED.subject_re, asset_name=EXCLUDED.asset_name, parser=EXCLUDED.parser;
