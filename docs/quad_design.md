# Quad regime → MACRO — design

How the macro **quad regime** becomes a single **MACRO** signal per stock on the
Actionable screen. Authoritative design + implementation reference.

**Key tables:** `ref_quad_periods` (period distributions), `ref_quad_outlook`
(Bullish/Bearish/Neutral per category × quad), `drv_macro_score` (output).
**Deriver:** `etl/derive_macro.py` → wired into `derive_all()` after `drv_ma`.

---

## Principles

1. **Overlay, not standalone.** MACRO decides when to press a bottom-up call and
   when to back off — never a buy/sell on its own.
2. **Technical is master.** MACRO never flips the action; it adjusts conviction and
   flags conflicts. It may lean the call only when Technical is neutral/absent.
3. **One `MACRO` column** in SA/BM/HOLD/STM/SS vocabulary + `actionDisplay()` colors.
4. **One regime band** (Month | Quarter | Favoring + breadth + action split) above the grid.
5. **Both horizons use identical per-stock calculation** — same membership aggregation,
   same ramp/lead logic; only the input weights differ (distribution vs one-hot).
6. All weights/windows/thresholds live in `ref_settings`, tunable against outcomes.

---

## Data model

**`ref_quad_periods`** — one row per month and one per quarter:

| Column | Monthly rows | Quarterly rows |
|---|---|---|
| `period_type` | `'month'` | `'quarter'` |
| `quad` | argmax of distribution | fixed top-level quad |
| `quad1_pct … quad4_pct` | probability weights (sum ≈ 100) | NULL (one-hot implied) |
| `start_date / end_date` | month boundary | quarter boundary |

Seeded from `db/seeds_quad_periods.sql`. If HQds tab gains a pct column,
`etl/load_raw.py::load_hqds` can populate it instead.

**`ref_quad_outlook`** — unchanged, already exists:
`(category, sub_category)` × `quad1..quad4` = Bullish / Neutral / Bearish.
Categories in use: `Equity Sectors`, `Asset Class`, `Equity Style`.

**`drv_macro_score`** — output table (idempotent DELETE+INSERT per derive date):
`as_of_date, tos_symbol, month_now_net, month_next_net, month_weight, monthly_score,
qtr_now_net, qtr_next_net, qtr_weight, quarterly_score, macronet, macro_action`

---

## Pipeline

![MacroNet formula pipeline](diagrams/macronet_formula.svg)

---

## Stage 1–2 — per-stock membership net score

A symbol is a **bundle of memberships**, each `(category, sub_category, weight)`:

| Membership | Category | Weight | Source |
|---|---|---|---|
| Sector | `Equity Sectors` | **×2** | `drv_ma.sector` |
| Asset class | `Asset Class` | **×1** | `drv_ma.asset_class` |
| Style factors | `Equity Style` | **×0.5 each** | classified from fundamentals |

**Style classification thresholds** (in `etl/derive_macro.py::_classify_style`):

| Style tag | Condition |
|---|---|
| High Beta | `beta ≥ 1.5` |
| Low Beta | `beta ≤ 0.7` |
| Defensives | sector ∈ Consumer Staples, Health Care, Utilities, Real Estate |
| Cyclical | sector ∈ Industrials, Materials, Energy, Consumer Discretionary, Financials |
| Value | `0 < P/E ≤ 15` |
| Secular | `P/E > 30` |
| Dividend | `div_yield > 2%` |
| Momentum | `RSI > 65` |
| Small Caps | `market_cap < $2B` |
| Mid Caps | `$2B ≤ market_cap < $10B` |

For each membership, stance against a quad distribution:
```
stance = Σ_k  (quad_k_pct / 100) × outlook(quad_k)     +1 / 0 / −1
```

Aggregate:
```
net = sector×2 + asset_class×1 + Σ(style×0.5)
```

---

## Stage 3 — two horizons, same formula, different input weights

**Both monthly and quarterly** run identical Stage 1–2 logic. The only difference is
how the quad distribution is expressed:

| Horizon | Distribution input | Ramp tunables |
|---|---|---|
| Monthly | `quad1_pct … quad4_pct` from `ref_quad_periods` | `quad_month_ramp_begin_days` = 12, `quad_month_lead_days` = 5 |
| Quarterly | one-hot: 100% on active quad, 0% on others | `quad_qtr_ramp_begin_days` = 20, `quad_qtr_lead_days` = 10 |

Each horizon computes a score for **now** and **next** period, then blends by a
ramp keyed to trading days to period-end:

```
next_weight = clamp( (ramp_begin − days_to_end) / (ramp_begin − lead_days), 0, 1 )

M = (1 − next_weight) · month_now_net  +  next_weight · month_next_net
Q = (1 − next_weight) · qtr_now_net    +  next_weight · qtr_next_net
```

Three zones for each: fully current → linear ramp → fully next (anticipating the
market pricing the next period before the boundary).

### Combine

```
MacroNet = 0.80 · M  +  0.20 · Qtr
```

(`quad_horizon_weight_mo` / `quad_horizon_weight_qtr` — reweighted from the
original 0.65/0.35 on 2026-07-06. Quarterly is a pure one-hot score with no
distribution smoothing, so its raw variance runs ~2x monthly's; at 0.65/0.35
quarterly's *effective* pull on the blend actually exceeded monthly's despite
its smaller nominal weight, contradicting this section's own stated intent.
0.80/0.20 restores monthly as the dominant signal in practice, not just in
name — re-derive both this ratio and the Stage 4 thresholds together if either
changes, since they're calibrated against each other's output distribution.)

Monthly overweights quarterly because it carries full probability distribution +
anticipation ramp. Quarterly is the same calc but with cruder one-hot input.

---

## Stage 4 — threshold map → action

`MacroNet` is mapped to the standard action vocabulary via `ref_settings` keys
(`macro_thr_*`; legacy `macronet_threshold_*` names still work as a fallback):

| Key | Current value | Action |
|---|---|---|
| `macro_thr_bm` | 0.62 | MacroNet ≥ → **BM** |
| `macro_thr_bs` | 0.276 | MacroNet ≥ → **BS** |
| `macro_thr_stm` | −0.736 | MacroNet ≤ → **STM** |
| `macro_thr_sa` | −0.88 | MacroNet ≤ → **SA** |

Recalibrated 2026-07-06 by percentile against the live `drv_macro_score`
distribution (target ~3% BM, ~12% BS, ~70% HOLD, ~12% STM, ~3% SA) — re-check
after any change to the monthly/quarterly weights below, since re-weighting
shifts the whole distribution and the percentile targets need re-deriving
against it (see `etl/derive_macro.py::to_action` / `api/routers/dash.py::_macronet_to_vocab`).

**Sign-agreement override (2026-07-06, asymmetric by design):** when the
month (`M`) and quarter (`Qtr`) components agree on direction, the result
never lands in HOLD:

- **Both positive** → floored to BS, still reaching BM if the blend clears
  `macro_thr_bm` (score-driven, same as the disagreement case below).
- **Both negative** → always **SA**, regardless of magnitude. Any negative
  agreement between the two independent horizons is treated as a full sell
  signal — deliberately not scaled down to STM even when both components
  are only mildly negative. This is an intentional asymmetry (confirmed with
  the user 2026-07-06): the buy side stays score-gated, the sell side does
  not.

HOLD stays reachable only when the two horizons disagree (e.g. a
mildly-bullish month against a bearish quarter, as with XLRE) or when a
component is exactly zero.

---

## Stage 5 — precedence: Technical is master

MACRO is an overlay — it never overrides the Technical action.

| Bottom-up ↓ \ Macro → | Bullish | Neutral | Bearish |
|---|---|---|---|
| **Buy** | PRESS LONG | Long | **CONFLICT — trim/skip** |
| **Neutral** | Watch-long | — | Watch-short |
| **Sell** | Dip — don't short | Short | PRESS short / exit |

---

## Stage 6 — presentation

- **MACRO column** on Actionable grid: shows `macro_action` badge + raw `macronet`
  score in small faded label (e.g. `BM 1.88`). Rendered by `macroCellHtml()` in
  `web/actionable.js`. Sortable via `data-key="macro_value"`.
- **Regime band** (`#macroBand`): Month | Quarter | Favoring | ↑↓ breadth | action split.
  Loaded by `loadMacroBand()` in `web/actionable.js`.
- **Tooltip** on MACRO cell (`_macroTooltip()` in `web/actionable.js`, lazy-loaded
  via `GET /api/actionable/macro-detail`): full breakdown — "How to act" directive,
  Month (current/next quad + probability distribution + blended net), Category
  Drivers (every sector/asset-class/style membership with its weight and
  Bullish/Bearish/Neutral outlook), Quarter (locked-in quad + score), and the
  `MacroNet = a×Qtr + b×M = ... → vocab` formula line.

---

## Tunable params (`ref_settings`)

| Key | Default | Meaning |
|---|---|---|
| `quad_month_ramp_begin_days` | 12 | days before month-end ramp starts |
| `quad_month_lead_days` | 5 | days before month-end weight hits 100% next |
| `quad_qtr_ramp_begin_days` | 20 | days before quarter-end ramp starts |
| `quad_qtr_lead_days` | 10 | days before quarter-end weight hits 100% next |
| `quad_horizon_weight_mo` | 0.80 | Monthly weight in MacroNet |
| `quad_horizon_weight_qtr` | 0.20 | Quarterly weight in MacroNet |
| `macro_thr_bm` | 0.62 | MacroNet ≥ → BM |
| `macro_thr_bs` | 0.276 | MacroNet ≥ → BS |
| `macro_thr_stm` | −0.736 | MacroNet ≤ → STM |
| `macro_thr_sa` | −0.88 | MacroNet ≤ → SA |

Stance map: Bullish +1 · Neutral 0 · Bearish −1.

---

## Implementation files

| File | Role |
|---|---|
| `etl/derive_macro.py` | Per-symbol MacroNet deriver; writes `drv_macro_score` |
| `etl/derive.py::derive_all` | Wires in `_derive_macro_impl` after `drv_ma` |
| `db/baseline.sql` | `drv_macro_score` table + index |
| `db/seeds_quad_periods.sql` | Seeds monthly quad distributions |
| `api/routers/dash.py` | LEFT JOINs `drv_macro_score`; prefers it over API-time calc |
| `web/actionable.js` | `macroCellHtml()` renders MACRO column; `loadMacroBand()` for band |
| `docs/diagrams/macronet_formula.svg` | Full pipeline visualization |
