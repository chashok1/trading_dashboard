# Dev Handoff — AGENT_WORK_49 (TASK_149)

## Step 0
Done. `AGENT_WORK_48.md` and the old handoff moved to `agent-tasks/archive/handoff/` (`DEV_HANDOFF_ARCHIVE_TASK148.md`), `TASK_148_macro_week_strip.md` moved to `agent-tasks/archive/`. This round's pointer archived as `AGENT_WORK_49.md` (repo root). Nothing committed or pushed.

## TASK_149
No tests, no pytest, no browser run (per instruction). Sanity checks only, listed at the end.

### Files changed
- `db/baseline.sql` (appended block) — `ref_cross_asset_rule` +`area_key/verdict/read_text/severity/mode`, `target_symbol`/`target_action` nullable; `ref_cross_asset_rule_leg` +`lookback_days/threshold_value/leg_label/group_op` and wider `check_type` CHECK; `drv_cross_asset_signal` +`mode/area_key/verdict/severity/read_text/data_missing`; `ref_gauge_transmission` +`inverted/exclude`; new `ref_driver_series`, `ref_driver_area`, `drv_area_verdict`, `drv_driver_exposure`; two `ref_settings`; existing gold rule tagged `area_key='gold'`, `mode='actionable'`.
- `db/seeds_area_driver.sql` (new, every statement <= 965 bytes) — silver `ref_corr_asset` row (`SI=F`), 3 series, 12 areas, 33 advisory rules, their legs, exposure map.
- `db/seeds_freshness_contract.sql` — freshness rows for `drv_area_verdict`, `drv_driver_exposure` (derive_all).
- `etl/derive_cross_asset_rules.py` — engine extended: new check types, OR groups, tri-state "input missing", read-text build, second pass for `rule_fired`. Old `rr_position`/`outlook` path kept; only change there is the outlook compare is now case-insensitive and a `data_missing` flag.
- `etl/derive_area_verdicts.py` (new) — `derive_area_verdicts` (gate, strongest rule, optional 2-day confirm, since-date, one `meta_warning`) and `derive_driver_exposure`.
- `etl/derive.py` — both steps wired into `derive_all` right after `derive_actionable`.
- `etl/derive_actionable.py` — the one allowed change: cross-asset fold now `AND mode='actionable' AND target_symbol IS NOT NULL`.
- `api/_helpers.py` — shared `vol_zone()`; `api/routers/macro_areas.py` uses it (same thresholds, same result).
- `api/routers/cockpit.py` — new `GET /api/cockpit/area-verdicts`; existing `/api/cockpit/cross-asset-signals` filtered to `mode='actionable'` so the old panel does not show advisory rules.
- `api/routers/dash.py` — `/api/actionable` rows carry `driver_flags[]`.
- `web/area_verdicts.js` (new), `web/index.html`, `web/macro_areas.js` (`data-sym` on rail rows + `decorateRails()` call), `web/actionable.js` (`_signalReasons` lines, `headwind_only` filter, chip count), `web/actionable.html` (chip), `web/styles.css` (`.av-*`). Cache-busters bumped (index: styles, macro_areas, area_verdicts; actionable.js).
- `docs/area_driver_rules_logic.md` (new), `CLAUDE.md` (one Lookup row), `docs/migrations.md`.

### Decisions
- **Tile placement:** a new card `#areaVerdictCard` in the centre column directly under the Macro Week strip, as a wrapping row of chips (one or two lines). The ~206px Regime band was too narrow. Quiet areas collapse into "+N quiet"; "$X headwind" chip opens a list.
- **Rail pills:** Precious Metals header roll-up (counts), Gold (/GC) and Silver (/SI) row pills, Energy=Oil, Crypto=Bitcoin, Rates=Bonds, Credit, Country ETFs=Intl/EM headers, Major Markets rows SPX/$COMP/RUT, Industrial & Ag /HG row. No rail was split or rearranged. The Currency, Volatility, Cannabis and Sectors rails get nothing.
- **Gate lives on the area** (`ref_driver_area.gate_*`), not as a leg check type. Gold/Silver/Copper: `w30 <= -0.3`; Bitcoin: `|w30| >= 0.3` (per spec, even though no Bitcoin rule has a dollar leg). Silver borrows gold's gate until `silver` has data (the seed row only creates the series; I did not fetch SI=F: no network calls this round).
- **Delta dead-bands** (my choice, editable on the leg): real yield and 10Y breakeven change over 20d: +/-0.05 and +0.03 points; HY spread +/-0.10 points. "10Y above your 5% level" uses the highest active `ref_level_watch` row for TNX (50 on the x10 scale).
- Exposure tiers: override (symbol axis), direct (`macro_area_key` dual members), class (sub_asset_class, sector, asset_class), theme (`ref_symbol_theme`). Style axis not used (needs a beta calc per stock). Inverted: PFIX and TBT under Bonds; stretched/turning are skipped for inverted stocks.
- Warnings only for held rows or buy-side Final Calls. Headwind/Stretched = caution, Tailwind = confirm, Turning/Unclear silent; sells swap via the existing return.
- Outlook values are bucketed by substring (Mild/Light Bullish count as up, Long/Short too).

### Rule-by-rule notes
Rules exactly as design section 3, with these implementation points: Silver headwind = two rules (gold headwind fires + silver down; silver + copper down); Silver turning also checks /SI in lower half. Gold "buy at extreme" stays the old actionable rule, unchanged (output byte-identical on 2026-10-09, still blocked by the veto). Intl/EM uses EEM as the "area ETF". Large caps stretched = Risk Dial `spx_top_range`. Credit stretched = `credit_equity_divergence`. Oil: no gate (corr info only).

### Live verdicts, anchor date 2026-10-09
- Gold **Headwind** (Dollar up, 10Y up, real yield +0.29 over 20d, Gold down; corr -0.86 valid)
- Silver **Headwind** (gold rule fires, silver down; gate borrowed from gold)
- Copper **Unclear** (CRB 30d corr +0.11, needs <= -0.3)
- Oil **Tailwind** (WTI up, Brent up, OVX 48.9 = chop, which counts as not elevated)
- Bitcoin **Tailwind** (Bitcoin up, Nasdaq up, VXN 20.55 investable)
- Small caps **Headwind** (RUT down, 10Y up, HY spread +0.50 over 20d)
- Tech **Headwind** (real yield +0.29, 10Y 5.244% above 5%); $212k held, 70 linked stocks
- Credit **Stretched** (credit widening, equities not confirming); $154k held
- Large caps, Bonds, Intl/EM quiet. No stale-input warning posted.
- `$ headwind` = $211,606 (all of it Tech). 129 linked-stock rows, 118 Actionable rows have a flag.

### Risks and notes
- Seeds go in with `ON CONFLICT DO NOTHING`; tune thresholds in /ref, not in code.
- The Tech area links every Information Technology sector stock (70 today), so a Tech headwind puts a caution on all held/buy tech names. Narrow the `tech` rows in `ref_gauge_transmission` if that is too broad. Same for Oil (sector Energy, 33 stocks).
- First derive day: every area shows the "new" dot (no prior row). It clears after 3 days.
- `drv_area_verdict` rows exist only for 2026-10-09 (I ran the three steps by hand for that date). The normal cascade fills other dates.
- The "In headwind area" chip count is set when rows load; I could not see it in a browser.
- Not done (out of scope): scorecard/validation, email digest, moving old JS warnings into rules, optional quad confirm leg. Pre-existing and left alone: other places that compute vol zones in JS/risk dial (only the rails and the derive share the new helper).
- Silver correlation: run the correlation job once to pull `SI=F`; until then the Silver gate shows "borrowed".

### How to test (not run this round, per instruction)
- Apply schema: `python -m db.init_db` (already applied on the local DB).
- `etl/` changed: STOP the server, relaunch `start.bat`, THEN re-derive (the server does not hot-reload `etl/`).
- Sanity done: `ast.parse` on every changed Python file; `node --check` on `area_verdicts.js`, `macro_areas.js`, `actionable.js`; TestClient: `/` and `/actionable` return 200; `/api/cockpit/area-verdicts` 200 (28 KB, 11 areas); `/api/actionable?date=2026-10-09` 200 with `driver_flags`; `/api/cockpit/cross-asset-signals` 200 (old rule only); `/api/macro-areas` 200. Node smoke run of `area_verdicts.js` against the live JSON rendered the tiles and rail decoration without errors. Re-running the three derive steps gave the same counts (35 rules, 11 areas, 129 exposure rows).

## Status
ALL_DONE
