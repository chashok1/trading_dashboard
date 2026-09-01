# Cross-Asset Rules

Multi-symbol RR-position rules the ordinary atomic-rule engine can't express — atomic rules (`ref_trig_atomic_rule` → composite → rule group) only ever evaluate a row's **own** fields (`drv_cat_atomic_input`). A rule like *"Bonds and US Dollar at TRR, Gold at LRR → buy Gold"* needs three **other** symbols' RR reads to fire a signal on a fourth. 2026-09-01, user request.

## Schema

- **`ref_cross_asset_rule`** — one row per rule: `rule_code` (PK), `description`, `target_symbol`, `target_action` (consolidated_action vocabulary — `ADD`/`INCREASE`/`REDUCE`/`REMOVE`/`HOLD`), `is_active`. Editable via `/ref`.
- **`ref_cross_asset_rule_leg`** — one row per leg of a rule: `rule_code` (FK), `leg_symbol`, `comparison` (`>=`/`<=`), `rr_threshold_pct`, `weight` (default 1), `leg_group` (nullable). A rule fires when **every check** passes — see Leg evaluation below.
- **`drv_cross_asset_signal`** — derived (idempotent `DELETE WHERE as_of_date=D` → INSERT), one row per active rule per date: `fired`, `target_symbol`, `target_action`, `detail` JSONB (one entry per check: `{symbol, comparison, threshold_pct, rr_pct, passed, members}` — `symbol`/`rr_pct` are the check's own label/combined value; `members` is present only for a blended check, listing each underlying leg's own `{symbol, rr_pct, weight}` — powers the dashboard panel's "how close" read even when not fired).

## Leg evaluation

A rule's legs group into **checks**: a leg with `leg_group IS NULL` is its own standalone check; legs sharing the same `(rule_code, leg_group)` blend into **one** check — their `rr_pos()` values combine via a `weight`-weighted average (legs in a group must share the same `comparison`/`rr_threshold_pct`, the group's one shared condition). A rule fires when **every** check passes.

Each leg's own reading uses `api._helpers.rr_pos(last_price, lrr, trr)` — the same `[0, 1]`-scale formula `ref_macro_area`'s own HOT/COLD read uses (`macro_area_hot_pct`/`macro_area_cold_pct` in `ref_settings`, default 0.85/0.15). `rr_threshold_pct` is stored 0–100 (e.g. `85` = "at TRR", `15` = "at LRR") and divided by 100 before comparing against either a single leg's value or a group's blended value.

## Seeded rule

`BONDS_USD_TRR_GOLD_LRR` — "Bonds (10Y+30Y Treasury yield, 70/30 blend) and US Dollar ($DXY) at TRR while Gold (/GC) is at LRR — buy Gold".

- **Bonds** = `TNX:CGI` (10Y, weight 0.7) + `TYX:CGI` (30Y, weight 0.3), same `leg_group='bonds_yield'`, blended and compared once against `>=85`. **Not** `TLT`/`IEF` (bond *price* ETFs) — an earlier version of this rule used those, but the user's actual rule concept (confirmed against their Hedgeye RR email — UST30Y/UST10Y/UST2Y yield levels, matching `TYX:CGI`/`TNX:CGI`/`DGS2:FRED` in `hist_rr` exactly) is Treasury **yield** risk range, not bond price. "Yield at TRR" is a mean-reversion setup (yields expected to roll over) — coherent with USD at TRR also rolling over and Gold at LRR bouncing, all pointing the same bullish-gold direction; no comparison inversion needed vs. the original wording, just the right symbols. 2Y (`DGS2:FRED`) deliberately excluded — it's dominated by near-term Fed rate-path expectations, a different driver than the long-duration/real-yield story that ties to Gold; 10Y is weighted higher than 30Y as the more standard single benchmark for the gold/real-yields relationship.
- **USD** = `$DXY` (the dedicated `rr_only` USD member in `ref_macro_area`), standalone, `>=85`.
- **Gold condition** = `/GC` (the dedicated `rr_only` Gold member — the condition leg, cleanest single-instrument RR read), standalone, `<=15`.
- **Target/buy symbol** = `GLD` — the ETF this app already treats as canonical Gold elsewhere (`_ASSET_CLASS_ETF["Gold"]`, Quad Rotation panel).

## Derive + wiring

`etl/derive_cross_asset_rules.py::derive_cross_asset_rules(session, as_of_date)` — wired into `derive_all()` (`etl/derive.py`) right after `drv_dash_summary`, before the Actionable Stocks pipeline. Needs only `drv_quote`/`drv_rr` (already built earlier in the cascade); its output must exist before `derive_actionable.py` runs.

`etl/derive_actionable.py` reads `drv_cross_asset_signal` (fired rows only) keyed by `target_symbol`, and folds a fired rule into that symbol's candidate list the same way a fired **rule group** already is (`group_candidates`):

- Appended to `triggered_groups` → visible in the `triggered_group_ids` JSONB column, tagged `"cross_asset": true` to distinguish from a real rule-group firing.
- If `target_action` is in `ACTION_RANK` (the `consolidated_action` vocabulary), appended to `group_candidates` with `source_code = f"CROSS:{rule_code}"` and a fixed weak priority (`CROSS_ASSET_PRIORITY = 60`) — below every real outlook source and action rule group (all `<=10` in practice), so a fired cross-asset rule only wins `consolidated_action` on a symbol nothing else has an opinion on; it never overrides a real per-symbol signal. These rules are cross-market context, not the target symbol's own technicals/fundamentals.
- **Not** folded into `trig_action` (BuySell vocabulary — SA/STM/SS/BMN/BS/BM) — cross-asset rules speak the `consolidated_action` vocabulary only.

## Dashboard panel

`web/cross_asset_panel.js` renders into `#crossAssetBody` (`web/index.html`, `.dial-changed-col`, directly below the Mkt Situation panel) — reads `GET /api/cockpit/cross-asset-signals` (`api/routers/cockpit.py`), a thin read over `drv_cross_asset_signal` (no re-derivation). Shows every active rule, not just fired ones, so a not-yet-fired rule's "how close" state (each leg's RR% vs its threshold) stays visible — designed to hold more rules as they get added, not just this one.

## Adding a new rule

1. Insert a row into `ref_cross_asset_rule` (+ its legs into `ref_cross_asset_rule_leg`) via `/ref`, or a migration.
2. Re-derive (`derive_all`) — no code change needed for a new rule using the same leg/threshold shape.
