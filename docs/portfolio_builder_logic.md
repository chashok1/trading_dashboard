# Portfolio Builder logic

Screen `/builder`. Specs: `DESIGN_SPEC_9.md` (measures, recipes, storage, marks, back-test, warnings), `DESIGN_SPEC_10.md`
(accounts, asset-allocation mix), `DESIGN_SPEC_11.md` (area split). Where they disagree, 11 beats 10 beats 9.
The Builder **never trades and never changes the Actionable Final Call**.

## Flow
Account -> how long (1/3/6/12 months) -> mix by asset class -> split each bucket (by area, or by recipe) -> accept and freeze.
Buckets are the Portfolio pie's: Equities, Fixed Income, Gold, Commodities, Crypto, Currency (pie "FX"), Cash (the rest).
Unmapped holdings are shown in the "current" bar but can never be a target.

## Files
| Piece | File |
|---|---|
| Every tunable number (GUESS values), measures, recipes, area stance + fill, mix, caps, alerts, promise check (PURE) | `etl/derive_model_portfolio.py` (`PB_PARAMS`) |
| Nightly `drv_pb_score` + `derive_model_marks` step (in `derive_all` after the symbol-tier step) | same file, bottom |
| Build engine `build_positions(ctx, req)`, `vs_account`, `drift_table`, `backtest` (PURE) | `etl/builder_engine.py` |
| Read-only loaders (funds + measures, Quad mix, accounts, holdings, presets, back-test runner) | `etl/builder_data.py` |
| Accept/freeze, daily marks, list, detail, review, warnings, keep list | `etl/builder_store.py` |
| API | `api/routers/builder.py` (`/api/builder/*`) |
| Page | `web/builder.html`, `web/builder.js`; nav item in `web/_common.js`; route in `api/routers/pages.py` |
| Tables | `db/baseline.sql` (end of file); fund list + presets `db/seeds_portfolio_builder.sql` |
| Tests | `tests/test_model_portfolio.py` (pure functions, no DB) |

## Source pool + validation checks (2026-10-27)
Optional: tick Hedgeye lists (PS, GOANY, II, CALL, ETF, SSS, RR) and the pick pool becomes their bullish names (stocks and ETFs together)
instead of `ref_pb_universe`. Request keys: `sources`, `checks`.
- Pool = `drv_source_standing` on-list rows, bullish per `builder_data.source_bullish` (PS/GOANY on list; II/ETF/RR/CALL outlook Bullish/Long or CALL weight > 0; SSS signal_sign > 0). Bucket/area from the Portfolio-pie maps. Unmapped asset class = not available. SPY is added as benchmark-only (never picked) so freeze can track against it.
- Pool mode splits every bucket by recipe (default Equities Momentum, Fixed Income Core); a bucket with no pool names is dropped and its share spread over the others (Cash share unchanged: `pool_trim_mix`).
- **Checks** (`builder_engine.apply_checks`, filters, shown under "Removed by your check"): `low_beta` = beta must be <= 0.8; `quad` = drop names whose area is a Sell area for the period's Quad mix (no Quad view passes).
- **Compare** (`POST /api/builder/compare`, `builder_data.compare_variants`): as picked / +Low beta / +Quad / +Both side by side, each with a back-test.
- **Back-test is information only**: it never removes or changes a pick. For source pools it uses TODAY's list membership (past membership not kept), so it flatters.
- Not done: nightly `drv_pb_score` does not score pool names (only the fixed list); end-of-period review re-uses the stored `sources`.

## Numbers (all in `PB_PARAMS`, none scattered)
$5M median daily traded value; swings = stdev of last 63 daily returns x sqrt(252) (needs 55); beta = cov/var vs SPY over 126 returns
(fallback 63, needs 55); momentum = close(t-21)/close(t-126)-1 (needs 127 closes); low-beta floor 0.2; Momentum +5 points for an RR/ETF
Bullish; fund cap 20% of the account; sector cap 40% of the bucket; 3% minimum weight; area fill = base x (1 + k x stance), k = 1; chip band
+/-0.25; minimum areas 3 (Equities) / 2 (Fixed Income); area floor 3%; Broad US / Foreign get 2 funds from 15% of the bucket; Quad tilt 0.25
(also `ref_pb_mix_preset.quad_tilt`); WATCH blend 25%, TRANSITION blend 50%; drift amber 5 points; drop warning 10%; 3 stale days; split
flag +/-40% in a day; beta promise 0.8; household over-concentration note 20%.

## Rules in one place
- **Quad mix over the holding period** = `derive_macro.window_weights` + `build_effective_distribution` with the window set to the period
  (30/91/182/365 days). Months with no monthly row use the quarter's declared Quad (one-hot). Under 50% coverage: a note. WATCH /
  TRANSITION from `drv_quad_check` blends toward `target_quad`.
- **Area stance** = sum of (Quad share x outlook) from `ref_quad_outlook` (Bullish +1, Neutral 0, Bearish -1). Quad buttons override:
  one Quad = that outlook, several = AND (+1 if Bullish in all, -1 if Bearish in any). Chip B/H/S at +/-0.25. Macro and Quad are never added.
- **Fill** (`fill_areas`): equal base share per eligible area, Sell areas to zero, minimum areas revived at half base, user locks kept,
  40% cap, 3% floor, kept holdings counted first (excess taken off the other unlocked areas).
- **Inside an area** (`pick_in_area`): Low volatility / Low beta / Momentum (Equities), Core / Low volatility (Fixed Income); next-ranked fund
  replaces a Final Call Sell; no qualifying fund -> that area's money stays unspent and goes to Cash with the reason.
- **Mix**: preset (or current / custom), Quad-tilted preset applies +/-25% by bucket stance and keeps Cash, Risk Dial multiplies Equities,
  Commodities and Crypto and moves the difference to Cash, never below the kept floor.
- **Kept holdings** (`ref_account_keep`): keep their shares, count toward their bucket, never traded, never picked again.
- **Final Call skip REMOVED 2026-10-27** (user: calls are temporary, info only when building). The call still shows per name (and a Conflict badge), never removes or swaps a name. Old rule text: `drv_actionable.final_code` in {SA, SS, STM, SO, SW, SWW, REMOVE, REDUCE} is a Sell; buy family {BM, BS, BMN, BW, BSW, INCREASE, ADD}.
- **Freeze**: shares bought at the accept-day price (re-priced by the derive on the start date until the next derive date), whole shares,
  leftover to cash. One PENDING/RUNNING model per account; a new one closes the old one ("replaced"). Whole book = preview only.
- **Daily marks** (`drv_model_mark`, `drv_model_position_mark`): value = shares x close + cash; missing close carried forward and counted
  stale; SPY line = same dollars in SPY; "vs account" = the account's holdings at the start left untouched (price move only, not a TWR).
- **Alerts** (alert only): drop 10%, Quad TRANSITION, Risk Dial NOT INVESTABLE, a holding's Final Call turns Sell (all opt-in), plus always-on
  stale price (3 days) and possible split (+/-40% in a day). Each fires once, shows until dismissed, one `meta_warning` row (screen `builder`).
- **Promise check** and **end-of-period review** (roll over / change recipe / close; opens on the end date, never runs by itself).
- **Back-test**: every 21st trading day back, only data up to each start date. Final Call skip, Hedgeye outlooks, flavours and kept holdings
  are not replayed. Counts shown are non-overlapping periods; under 6 = "Too few periods to mean much"; none = "Not enough history yet" /
  "Not enough Quad history". Uses `hist_quote_daily` automatically if it ever has data (Yahoo backfill not built).

## Tables
`ref_pb_universe`, `ref_pb_mix_preset`, `ref_accounts.account_type`, `ref_account_keep`, `drv_pb_score`, `user_model_portfolio`,
`user_model_position` (write-once), `drv_model_mark`, `drv_model_position_mark`. `drv_*` tables use `tos_symbol` and are idempotent per
`as_of_date`.

## Apply
`python -m db.init_db`, then apply `db/seeds_portfolio_builder.sql`, set each account's type on Ref Data, restart the server (`etl/` is not
hot-reloaded), then re-derive (e.g. `python -m etl.backfill_derives` or the next load).
