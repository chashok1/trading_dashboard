# Cross-Asset Rules

Multi-symbol RR-position rules the ordinary atomic-rule engine can't express — atomic rules (`ref_trig_atomic_rule` → composite → rule group) only ever evaluate a row's **own** fields (`drv_cat_atomic_input`). A rule like *"Bonds and US Dollar at TRR, Gold at LRR → buy Gold"* needs three **other** symbols' RR reads to fire a signal on a fourth. 2026-09-01, user request.

## Schema

- **`ref_cross_asset_rule`** — one row per rule: `rule_code` (PK), `description`, `target_symbol`, `target_action` (consolidated_action vocabulary — `ADD`/`INCREASE`/`REDUCE`/`REMOVE`/`HOLD`), `is_active`. Editable via `/ref`.
- **`ref_cross_asset_rule_leg`** — one row per leg of a rule: `rule_code` (FK), `leg_symbol`, `leg_group` (nullable), `weight` (default 1), plus either:
  - an **`rr_position`** check (`check_type='rr_position'`, the original kind): `comparison` (`>=`/`<=`) + `rr_threshold_pct`, or
  - an **`outlook`** check (`check_type='outlook'`, 2026-09-24): `outlook_value` (e.g. `'BULLISH'`) — compares the leg symbol's `drv_rr.outlook` tag instead of an RR-position threshold. `comparison`/`rr_threshold_pct` are nullable and unused for this check type.

  `is_veto` (default `FALSE`) flips a check's effect — see Veto checks below. `UNIQUE(rule_code, leg_symbol, check_type)`, so the same symbol can carry both an `rr_position` leg and an `outlook` leg in one rule (e.g. `TNX:CGI` has one of each in the seeded rule).
- **`drv_cross_asset_signal`** — derived (idempotent `DELETE WHERE as_of_date=D` → INSERT), one row per active rule per date: `fired`, `veto_active` (2026-09-24 — see below), `target_symbol`, `target_action`, `detail` JSONB (one entry per check — `rr_position`: `{symbol, check_type, comparison, threshold_pct, rr_pct, passed, is_veto, members}`; `outlook`: `{symbol, check_type, outlook_value, outlook, passed, is_veto, members}` — `outlook` is the single combined reading for a 1-member check, `null` for a blended one; `members` is present only for a blended check).

## Leg evaluation

A rule's legs group into **checks**: a leg with `leg_group IS NULL` is its own standalone check; legs sharing the same `(rule_code, leg_group)` blend into **one** check. How they blend depends on `check_type`:

- **`rr_position`**: members' `rr_pos()` values combine via a `weight`-weighted average (members must share the same `comparison`/`rr_threshold_pct`), then compared against the threshold. Each leg's reading uses `api._helpers.rr_pos(last_price, lrr, trr)` — the same `[0, 1]`-scale formula `ref_macro_area`'s own HOT/COLD read uses (`macro_area_hot_pct`/`macro_area_cold_pct` in `ref_settings`, default 0.85/0.15). `rr_threshold_pct` is stored 0–100 (e.g. `85` = "at TRR", `15` = "at LRR") and divided by 100 before comparing.
- **`outlook`**: members combine via a **categorical AND** instead — every member's own `drv_rr.outlook` must equal the check's `outlook_value` for the check to pass. A weighted average doesn't make sense for a BULLISH/BEARISH/NEUTRAL tag.

A **normal** check (`is_veto=FALSE`) must pass for the rule to fire — same AND-across-checks logic as before.

### Veto checks (2026-09-24)

A check marked `is_veto=TRUE` inverts its role: instead of being required to fire, **all** of a rule's veto checks passing **blocks** it from firing, even when every normal check has passed.

```
fired       = (every normal check passes) AND NOT veto_active
veto_active = (rule has >=1 veto check) AND (every veto check passes)
```

A rule with no veto legs behaves exactly as before (`veto_active` always `FALSE`). The dashboard panel (`web/cross_asset_panel.js`) shows a distinct "⛔ BLOCKED" badge when `veto_active` is true and `fired` is false — different from the plain gray "watching" state, since the setup is otherwise fully formed and only the veto is holding it back.

## Seeded rule

`BONDS_USD_TRR_GOLD_LRR` — "Bonds (10Y+30Y Treasury yield, 70/30 blend) and US Dollar ($DXY) at TRR while Gold (/GC) is at LRR (blocked if 10Y+30Y yields and $DXY are all still BULLISH-outlook) — buy Gold".

Normal (`rr_position`) legs:
- **Bonds** = `TNX:CGI` (10Y, weight 0.7) + `TYX:CGI` (30Y, weight 0.3), same `leg_group='bonds_yield'`, blended and compared once against `>=85`. **Not** `TLT`/`IEF` (bond *price* ETFs) — an earlier version of this rule used those, but the user's actual rule concept (confirmed against their Hedgeye RR email — UST30Y/UST10Y/UST2Y yield levels, matching `TYX:CGI`/`TNX:CGI`/`DGS2:FRED` in `hist_rr` exactly) is Treasury **yield** risk range, not bond price. "Yield at TRR" is a mean-reversion setup (yields expected to roll over) — coherent with USD at TRR also rolling over and Gold at LRR bouncing, all pointing the same bullish-gold direction; no comparison inversion needed vs. the original wording, just the right symbols. 2Y (`DGS2:FRED`) deliberately excluded — it's dominated by near-term Fed rate-path expectations, a different driver than the long-duration/real-yield story that ties to Gold; 10Y is weighted higher than 30Y as the more standard single benchmark for the gold/real-yields relationship.
- **USD** = `$DXY` (the dedicated `rr_only` USD member in `ref_macro_area`), standalone, `>=85`.
- **Gold condition** = `/GC` (the dedicated `rr_only` Gold member — the condition leg, cleanest single-instrument RR read), standalone, `<=15`.
- **Target/buy symbol** = `GLD` — the ETF this app already treats as canonical Gold elsewhere (`_ASSET_CLASS_ETF["Gold"]`, Quad Rotation panel).

Veto (`outlook`) legs, 2026-09-24, user-directed ("if both bonds and dollar is bullish, it shouldn't recommend buy"): the RR-position setup above is a mean-reversion bet (yields/USD expected to roll over) — if the everyday BULLISH/BEARISH/NEUTRAL outlook tag on those same instruments still reads BULLISH, the trend hasn't actually turned yet, so the buy call is withheld.
- **Bonds bullish** = `TNX:CGI` + `TYX:CGI`, same `leg_group='bonds_bullish_veto'` (categorical AND — **both** must read BULLISH, not a weighted blend like the RR-position leg above), `outlook_value='BULLISH'`, `is_veto=TRUE`.
- **Dollar bullish** = `$DXY`, standalone, `outlook_value='BULLISH'`, `is_veto=TRUE`.

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
