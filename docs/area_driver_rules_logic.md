# Area Driver Rules (TASK_149)

For each market area (Gold, Silver, Copper, Oil, Bitcoin, Large caps, Small caps, Tech, Bonds, Credit, Intl/EM; Precious metals is a roll-up) read the area's drivers and give one verdict. Then flag holdings and buy candidates in that area. **Advisory only**: nothing here changes `consolidated_action` / `trig_action`. Design: `docs/mockups/area_driver_rules_design.html`.

## Verdicts
Headwind (down arrow), Tailwind (up arrow), Turning (diamond), Stretched (warning), Unclear (circle), Quiet (silent). Strongest fired rule wins: headwind > stretched > turning > tailwind.

## Flow (all inside `derive_all`)
1. `etl/derive_cross_asset_rules.py` evaluates every active rule into `drv_cross_asset_signal` (existing `BONDS_USD_TRR_GOLD_LRR` is `mode='actionable'` and unchanged; new rules are `mode='advisory'`). `derive_actionable.py` folds only `mode='actionable'` rows with a `target_symbol`.
2. `etl/derive_area_verdicts.py::derive_area_verdicts` (after `derive_actionable`) -> `drv_area_verdict`.
3. `derive_driver_exposure` -> `drv_driver_exposure` (needs held + position $ from `drv_actionable`).

## Rules and legs
Rules and legs are data: `ref_cross_asset_rule` / `ref_cross_asset_rule_leg` (seeds `db/seeds_area_driver.sql`, editable in /ref). Leg check types: `rr_position`, `outlook` (originals); `outlook_dir` (UP/DOWN/NOT_UP/NOT_DOWN, case-insensitive: BULL substring = up, BEAR = down), `outlook_flip` (UP_TO_DOWN/DOWN_TO_UP within `lookback_days` drv_rr dates), `delta` (series change over N days vs `threshold_value`; series in `ref_driver_series`, e.g. real yield = `DGS10 - T10YIE`), `zone` (investable/chop/elevated/not_investable/not_elevated), `gauge` (Risk Dial gauge fired), `level` (last price vs highest active `ref_level_watch` row; TNX x10 scale), `rule_fired` (another rule fired; evaluated in a second pass). `leg_group` + `group_op='or'` = any member passes. Read text = passed leg phrases joined by "and" (co-movement only, never causes).

Vol zones: one helper, `api/_helpers.py::vol_zone`, used by the rails and the derive.

## Gate, unclear, warning
`ref_driver_area.gate_*`: dollar-link gate on `drv_usd_correlation.w30` (gold/silver/copper `<= -0.3`, bitcoin `|r| >= 0.3`). Silver borrows gold's gate until the `silver` series (`SI=F`) has data. A failed gate = Unclear. Missing/stale input (a leg that cannot be read and no leg that definitely failed; corr older than 5 days; macro series older than 7 days) = Unclear plus ONE `meta_warning` (screen `actionable`, code `AREA_DRIVER_STALE`).

## Switches (`ref_settings`)
`area_verdict_confirm_days` (default 0 = off; 2 = a changed verdict must hold two derive dates), `area_verdict_new_days` (3, "new" dot).

## Exposure (which stocks)
`ref_gauge_transmission` with `gauge_key = area_key`: axes `sub_asset_class`, `sector`, `asset_class` (from `drv_technicals`), `theme` (`ref_symbol_theme`), `symbol` (manual override; `exclude` removes, `inverted` flips headwind/tailwind; stretched/turning are skipped for inverted stocks). `ref_driver_area.macro_area_key` adds the direct tier (dual members of that `ref_macro_area` area). Tier order: override, direct, class, theme.

## Surfaces
- `GET /api/cockpit/area-verdicts`: areas, rule legs, linked stocks, roll-ups, rail map, `$ headwind` total (distinct held stocks in Headwind areas, inverted excluded).
- Dashboard `/`: tiles `#areaVerdictCard` (centre column under the Macro Week strip), `web/area_verdicts.js`; rail pills via `decorateRails()` (rows carry `data-sym`).
- Actionable: `/api/actionable` rows carry `driver_flags[]`; `_signalReasons` adds one line per flagged area for held rows and buy candidates (headwind/stretched = caution, tailwind = confirm; swapped on sells); chip "In headwind area (N)".

## Not built (out of scope)
Scorecard/validation views, email digest, moving the hard-coded JS warnings into rules, optional quad confirm leg.
