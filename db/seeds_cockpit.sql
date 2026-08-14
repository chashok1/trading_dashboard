-- =====================================================
-- seeds_cockpit.sql — TASK_133 Dashboard Cockpit reference seeds.
-- Applied automatically by db/init_db.py (runs all db/*.sql in sorted order).
-- Idempotent: ON CONFLICT DO UPDATE so edits here propagate on re-run.
-- To tune: edit rows here, then `python -m db.init_db`.
-- =====================================================

-- ---------------------------------------------------------------------------
-- 2.1 ref_risk_gauge — total active weight = 38 (+ volume_breadth_weak seeded
-- inactive, weight 2 -- flip to TRUE once hist_internals is flowing, per
-- Phase 4.1; active weight becomes 40 at that point).
-- 2026-08-14 -- sahm_rule added: FRED's SAHMREALTIME >=0.50pp (Claudia
-- Sahm's recession indicator -- 3-month avg UNRATE vs its own trailing-
-- 12-month low). New 'macro' category (none of the existing 8 fit a
-- labor-market recession signal); weight 3, top tier, given the rule's
-- historical reliability. User: "Implement Sahm rule (claudia sahm)
-- unemployment rises by 0.5% on 3 month average vs lowest in last 12
-- months."
-- 2026-08-14 -- short_vol_disc added: VIX9D vs rvol_10day, the short-dated
-- companion to vrp_gone (VIX vs RV21). Weight 1 (vs vrp_gone's 2) -- an
-- early/leading version of the same signal, not a duplicate of it.
-- short_vol_low added same day: VIX9D's own absolute level vs its typical
-- 10-30 range, low end only (<=12, weight 1) -- separate dimension from
-- short_vol_disc (relative to realized vol), no high-end/bullish gauge
-- (Risk Dial gauges only ever fire on caution conditions).
-- move_chop added same day: MOVE's own "chop zone" companion to
-- move_elevated, mirroring vix_chop -- ref_vol_threshold's MOVE:GIF low
-- (100) was seeded but unused by any gauge until now. User: "What do you
-- consider as high risk when bond volatility moves higher... since we are
-- using risk gauges what can we use?"
-- vix_spx_divergence added same day: VIX green (>0%) while SPX rallies
-- >=1.5% -- the normal inverse VIX/SPX relationship breaking down on a big
-- up-day, read as hedging demand into the rally. Weight 3 (matches the
-- other severity-3 gauges: spx_top_range, vix_elevated, move_elevated,
-- credit_stress) -- user's own framing ("Get out of the market") is
-- among the strongest conclusions of any gauge in this file. User: "if
-- VIX is green and SPY is up massively => Get out of the market."
-- ---------------------------------------------------------------------------
INSERT INTO ref_risk_gauge (gauge_key, label, weight, is_active, category, notes) VALUES
    ('spx_top_range',          'SPX at top of risk range',   3, TRUE,  'equity',      NULL),
    ('spx_bottom_range',       'SPX below risk range',       2, TRUE,  'equity',      NULL),
    ('vix_spx_divergence',     'VIX/SPX inverse relationship broken', 3, TRUE, 'equity', NULL),
    ('sahm_rule',               'Sahm Rule recession signal',  3, TRUE,  'macro',       NULL),
    ('vix_elevated',           'Equity vol elevated',        3, TRUE,  'vol',         NULL),
    ('vix_chop',               'Equity vol in chop zone',    1, TRUE,  'vol',         NULL),
    ('move_elevated',          'Bond vol elevated',          3, TRUE,  'vol',         NULL),
    ('move_chop',              'Bond vol in chop zone',      1, TRUE,  'vol',         NULL),
    ('credit_stress',          'Credit stress',               3, TRUE,  'credit',      NULL),
    ('yield_level_watch',      'Yields at a watched level',  2, TRUE,  'rates',       NULL),
    ('curve_inverting',        'Curve inverting fast',       1, TRUE,  'rates',       NULL),
    ('dollar_strong',          'Dollar at top of range',     2, TRUE,  'fx',          NULL),
    ('oil_shock',              'Oil shock',                   2, TRUE,  'commodity',   NULL),
    ('vrp_gone',               'Volatility discount gone',   2, TRUE,  'vol',         NULL),
    ('short_vol_disc',         'Short-dated vol discount gone', 1, TRUE, 'vol',       NULL),
    ('short_vol_low',          'Short-dated vol at low end of range', 1, TRUE, 'vol', NULL),
    ('gamma_negative',         'Dealer gamma negative',      2, TRUE,  'positioning', NULL),
    ('breadth_deteriorating',  'Breadth deteriorating',       2, TRUE,  'breadth',     NULL),
    ('gold_vol_elevated',      'Gold vol elevated',          1, TRUE,  'vol',         NULL),
    ('volume_breadth_weak',    'Up/down volume breadth weak', 2, FALSE, 'breadth',
        'Phase 4.1 -- needs hist_internals ($UVOL/$DVOL) flowing. Flip is_active to TRUE once confirmed.')
ON CONFLICT (gauge_key) DO UPDATE SET
    label = EXCLUDED.label, weight = EXCLUDED.weight,
    is_active = EXCLUDED.is_active, category = EXCLUDED.category, notes = EXCLUDED.notes;

-- ---------------------------------------------------------------------------
-- 2.2 ref_level_watch — units must match the instrument's stored scale.
-- TASK_133 finding (see DEV_HANDOFF.md): TNX:CGI is stored on a x10 index-
-- level scale in drv_rr/drv_quote (e.g. 45.9 for a 4.59% yield), NOT raw
-- percent -- confirmed against drv_rr.lrr/trr (45.9/47.1) and the majority
-- (TL/TD-sourced) drv_quote rows for TNX:CGI. Seed values below are on that
-- x10 scale (50.0/45.0/40.0 for 5.00%/4.50%/4.00%), tolerance x10 too (1.0).
-- DGS2:FRED's drv_quote is genuinely percent-scaled (source 'Y', ~4.1-4.2) so
-- its seed values are left at the literal percent scale from the spec.
-- VIX/$DXY//CL//GC are already on their natural display scale -- no adjustment.
-- ---------------------------------------------------------------------------
INSERT INTO ref_level_watch (tos_symbol, level_value, tolerance, label, is_active) VALUES
    ('TNX:CGI',   50.00, 1.00, '10Y at 5% (x10-scaled)',   TRUE),
    ('TNX:CGI',   45.00, 1.00, '10Y at 4.5% (x10-scaled)', TRUE),
    ('TNX:CGI',   40.00, 1.00, '10Y at 4% (x10-scaled)',   TRUE),
    ('DGS2:FRED',  4.00, 0.10, '2Y at 4%',                 TRUE),
    ('VIX',       20.00, 1.00, 'VIX 20',                   TRUE),
    ('VIX',       30.00, 1.50, 'VIX 30',                   TRUE),
    ('$DXY',     100.00, 1.00, 'DXY 100',                  TRUE),
    ('/CL',      100.00, 2.00, 'WTI $100',                 TRUE),
    ('/GC',     4000.00, 50.00,'Gold $4000',               TRUE)
ON CONFLICT (tos_symbol, level_value) DO UPDATE SET
    tolerance = EXCLUDED.tolerance, label = EXCLUDED.label, is_active = EXCLUDED.is_active;

-- ---------------------------------------------------------------------------
-- 2.3 ref_market_pattern — read_text states co-movement + historical read
-- only. Never asserts a cause (standing instruction: "never hallucinate").
-- ---------------------------------------------------------------------------
INSERT INTO ref_market_pattern (pattern_key, label, read_text, severity, is_active) VALUES
    ('yen_bid', 'Yen bid / carry unwind',
        'Carry trades unwinding. Momentum and high-beta longs are the exposed side.', 'severe', TRUE),
    ('dollar_wrecking_ball', 'Dollar wrecking ball',
        'Global tightening impulse. Commodities and non-US exposure pressured.', 'warn', TRUE),
    ('rates_shock', 'Rates shock',
        'Duration and long-duration equity repricing.', 'severe', TRUE),
    ('credit_leads_equity', 'Credit leading equity',
        'Credit moving before equity confirms. De-risk.', 'severe', TRUE),
    ('flight_to_quality', 'Flight to quality',
        'Classic risk-off. Defensives outperform.', 'warn', TRUE),
    ('vol_regime_break', 'Volatility regime break',
        'Volatility crossed a zone boundary today. Halve sizes on an upward break.', 'severe', TRUE),
    ('korea_semis', 'Korea -> US semis',
        'Overnight Korean chip read-through. Check SOXX / NVDA / AVGO before the open.', 'warn', TRUE),
    ('oil_squeeze', 'Oil supply squeeze',
        'Energy and inflation impulse.', 'warn', TRUE)
ON CONFLICT (pattern_key) DO UPDATE SET
    label = EXCLUDED.label, read_text = EXCLUDED.read_text,
    severity = EXCLUDED.severity, is_active = EXCLUDED.is_active;

-- ---------------------------------------------------------------------------
-- 2.4 ref_gauge_transmission — category strings verified against
-- SELECT DISTINCT sector FROM drv_ma / asset_class FROM drv_technicals
-- (TASK_133 investigation). 'Health care'/'Health Care' both exist in
-- drv_ma.sector (case variants) -- not used by any transmission row here so
-- not a concern; Style categories match etl/derive_macro.py::_classify_style
-- sub_category strings exactly (High Beta, Momentum, Secular, Small Caps, ...).
-- ---------------------------------------------------------------------------
INSERT INTO ref_gauge_transmission (gauge_key, axis, category) VALUES
    ('move_elevated',         'sector', 'Utilities'),
    ('move_elevated',         'sector', 'Real Estate'),
    ('move_elevated',         'sector', 'Information Technology'),
    ('rates_shock',           'sector', 'Utilities'),
    ('rates_shock',           'sector', 'Real Estate'),
    ('rates_shock',           'sector', 'Information Technology'),
    ('yield_level_watch',     'sector', 'Utilities'),
    ('yield_level_watch',     'sector', 'Real Estate'),
    ('yield_level_watch',     'sector', 'Information Technology'),
    ('move_elevated',         'style',  'Secular'),
    ('move_elevated',         'style',  'Low Beta'),
    ('move_elevated',         'style',  'Dividend'),
    ('rates_shock',           'style',  'Secular'),
    ('rates_shock',           'style',  'Low Beta'),
    ('rates_shock',           'style',  'Dividend'),
    ('credit_stress',         'sector', 'Financials'),
    ('credit_stress',         'sector', 'Consumer Discretionary'),
    ('credit_leads_equity',   'sector', 'Financials'),
    ('credit_leads_equity',   'sector', 'Consumer Discretionary'),
    ('credit_stress',         'style',  'High Beta'),
    ('credit_stress',         'style',  'Small Caps'),
    ('credit_leads_equity',   'style',  'High Beta'),
    ('credit_leads_equity',   'style',  'Small Caps'),
    ('dollar_strong',         'sector', 'Materials'),
    ('dollar_strong',         'sector', 'Energy'),
    ('dollar_strong',         'sector', 'Information Technology'),
    ('dollar_wrecking_ball',  'sector', 'Materials'),
    ('dollar_wrecking_ball',  'sector', 'Energy'),
    ('dollar_wrecking_ball',  'sector', 'Information Technology'),
    ('dollar_wrecking_ball',  'asset_class', 'Commodities'),
    ('dollar_wrecking_ball',  'asset_class', 'Gold'),
    ('oil_shock',             'sector', 'Energy'),
    ('oil_shock',             'sector', 'Industrials'),
    ('oil_shock',             'sector', 'Consumer Discretionary'),
    ('oil_squeeze',           'sector', 'Energy'),
    ('oil_squeeze',           'sector', 'Industrials'),
    ('oil_squeeze',           'sector', 'Consumer Discretionary'),
    ('yen_bid',               'style',  'Momentum'),
    ('yen_bid',               'style',  'High Beta'),
    ('yen_bid',               'style',  'Secular'),
    ('korea_semis',           'sector', 'Information Technology'),
    ('vix_elevated',          'style',  'High Beta'),
    ('vix_elevated',          'style',  'Momentum'),
    ('vix_elevated',          'style',  'Small Caps'),
    ('vol_regime_break',      'style',  'High Beta'),
    ('vol_regime_break',      'style',  'Momentum'),
    ('vol_regime_break',      'style',  'Small Caps'),
    ('vrp_gone',              'style',  'High Beta'),
    ('vrp_gone',              'style',  'Momentum'),
    ('vrp_gone',              'style',  'Small Caps'),
    ('short_vol_disc',        'style',  'High Beta'),
    ('short_vol_disc',        'style',  'Momentum'),
    ('short_vol_disc',        'style',  'Small Caps'),
    ('short_vol_low',         'style',  'High Beta'),
    ('short_vol_low',         'style',  'Momentum'),
    ('short_vol_low',         'style',  'Small Caps'),
    ('spx_top_range',         'style',  'High Beta'),
    ('spx_top_range',         'style',  'Momentum'),
    ('vix_spx_divergence',    'style',  'High Beta'),
    ('vix_spx_divergence',    'style',  'Momentum'),
    ('sahm_rule',             'style',  'High Beta'),
    ('sahm_rule',             'style',  'Momentum'),
    ('sahm_rule',             'style',  'Small Caps'),
    ('breadth_deteriorating', 'style',  'High Beta'),
    ('breadth_deteriorating', 'style',  'Momentum'),
    ('gold_vol_elevated',     'asset_class', 'Gold')
ON CONFLICT (gauge_key, axis, category) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Phase 4.3: ref_macro_series catalog rows for the two Cboe free-CSV series
-- (etl/fetch_cboe.py). ref_macro_series has no source column -- FRED and
-- Cboe series share the same catalog/hist_macro table, distinguished by
-- hist_macro.source ('FRED' vs 'CBOE'). VVIX already has a ref_vol_threshold
-- row (100/150) with no feed behind it until now; RVOL is the Phase 3.1
-- Yang-Zhang cross-check.
-- ---------------------------------------------------------------------------
INSERT INTO ref_macro_series (series_id, label, grp, unit, sort_order, enabled) VALUES
    ('VVIX', 'VVIX (vol-of-vol)',        'risk', 'index', 25, TRUE),
    ('RVOL', 'Cboe realized vol (RVOL)', 'risk', 'index', 26, TRUE)
ON CONFLICT (series_id) DO UPDATE SET
    label = EXCLUDED.label, grp = EXCLUDED.grp, unit = EXCLUDED.unit,
    sort_order = EXCLUDED.sort_order, enabled = EXCLUDED.enabled;
