-- TASK_106/F5: tunable conviction-proven-edge threshold. Was hardcoded as
-- 0.5 in web/actionable.js::_hasPositiveEdge; now read from ref_settings via
-- GET /api/actionable/settings. Idempotent (ON CONFLICT DO NOTHING) — safe to
-- re-run `python -m db.init_db`.
INSERT INTO ref_settings (setting_name, setting_value, description) VALUES
  ('conviction_proven_edge_min', '0.5',
   'Actionable: min rule edge_20d (v_rule_scorecard) for _hasPositiveEdge / Proven conviction filter')
ON CONFLICT (setting_name) DO NOTHING;
