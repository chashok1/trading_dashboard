# TASK_126 — MACRO: sliding look-ahead window over the monthly quad calendar

## Goal

Replace the month now/next ramp + quarterly one-hot blend in
`etl/derive_macro.py` with a **sliding look-ahead window** over the monthly
quad calendar. Each day, the window (default 60 calendar days from D) is
projected onto `ref_quad_periods` monthly rows; the overlap fractions produce
**one effective quad distribution**, which feeds the existing Stage 1–2
membership calc unchanged. Same `drv_macro_score` / MACRO column — no new
score, no new column. Quarterly leg minimized. Days-passed-in-month behavior
is inherent (the window slides daily), so the old ramp params retire.

Design context: `docs/quad_design.md` (Stage 3 is what this task rewrites).

---

## 1. Window → effective distribution (`etl/derive_macro.py`)

```
window = [D, D + H)   calendar days, H = ref_settings quad_lookahead_days (default 60)
for each monthly row m in ref_quad_periods overlapping window:
    w_m = overlap_days(m, window) / H          # optional decay, see below
normalize Σ w_m = 1
eff_quad_k = Σ_m  w_m × quad_k_pct(m)          # k = 1..4  → one distribution
```

- **Decay** (optional, default off): `ref_settings quad_lookahead_decay_hl`
  (half-life in days, 0 = no decay). When set, weight each overlap day by
  `0.5^(days_from_D / hl)` before summing.
- **Calendar coverage**: if monthly rows don't extend through window end,
  truncate the window to available months and record `coverage_pct` in
  detail. If coverage < 50% → fall back to current-month one-hot and flag
  `fallback: true`.
- Implement as pure function
  `window_weights(d, months, h, decay_hl) -> [(month, w)]` — unit-testable
  without DB.

Effective distribution feeds the **existing** stance/net aggregation
(sector×2 + asset_class×1 + styles×0.5) exactly as today → `M_window`.

## 2. Per-month stances + tracking tag

Also compute stance_net per individual month in the window (same membership
calc vs that month's distribution) — needed for the tooltip and for:

- **tracking tag**: current technical direction (sign from the symbol's
  Technical action / trend as already exposed to actionable; pick the
  simplest existing field, document choice in DEV_HANDOFF) is compared to
  each month's stance sign, nearest month first. First month whose stance
  sign matches → `tracking = 'Aug (Quad 1)'`. No match → `tracking = null`
  (UI shows "fighting the quad path" marker when technical is non-neutral).

## 3. MacroNet combine + quarterly minimized

```
MacroNet = (1 − q) × M_window + q × Qtr      q = quad_horizon_weight_qtr, new default 0.05
```

- Quarterly leg calc unchanged, weight dropped 0.20 → **0.05** (seed update).
- **Sign-agreement override** (2026-07-06 rule) redefined on the window:
  components = stance of the **nearest month** vs the **weighted rest of the
  window**. Both negative → SA (unscaled, asymmetry preserved); both positive
  → floor BS, BM if blend clears `macro_thr_bm`. Disagreement / zero → HOLD
  reachable, as today.
- **Retire** `quad_month_ramp_begin_days`, `quad_month_lead_days`,
  `quad_qtr_ramp_begin_days`, `quad_qtr_lead_days` — delete reads from code;
  leave rows in ref_settings harmless or remove in seeds, dev's choice
  (note it).

## 4. `drv_macro_score` changes (db/baseline.sql)

- Keep: `as_of_date, tos_symbol, macronet, macro_action, quarterly_score`.
- `monthly_score` now stores `M_window`. `month_now_net / month_next_net /
  month_weight / qtr_now_net / qtr_next_net / qtr_weight` → stop populating
  (NULL) but keep columns for compat; mark deprecated in baseline comment.
- Add `detail JSONB`:

```json
{"h": 60, "coverage_pct": 100, "fallback": false,
 "months": [{"m":"2026-07","quad":3,"w":0.18,"stance":-1.2},
            {"m":"2026-08","quad":1,"w":0.52,"stance":2.1},
            {"m":"2026-09","quad":1,"w":0.30,"stance":2.1}],
 "eff": {"q1":58,"q2":10,"q3":27,"q4":5},
 "near_vs_far": {"near":-1.2,"far":2.1,"override":"none"},
 "tracking": "2026-08 (Quad 1)"}
```

## 5. Threshold recalibration

After the switch the MacroNet distribution shifts. Recalibrate `macro_thr_bm
/ bs / stm / sa` by percentile against the live drv_macro_score output
(targets ~3% BM, ~12% BS, ~70% HOLD, ~12% STM, ~3% SA — same method as
2026-07-06). Record old/new values in DEV_HANDOFF and update
`docs/quad_design.md` table.

## 6. Data prerequisite

`ref_quad_periods` must have monthly rows covering D → D+H (user has quad
data for coming months). Extend `db/seeds_quad_periods.sql` with the forward
months; if rows are missing at runtime the coverage fallback (§1) applies.

## 7. API + UI

- `GET /api/actionable/macro-detail` (lazy tooltip source): add month mix,
  eff distribution, near/far, tracking tag from `detail`.
- Tooltip (`_macroTooltip()` in `web/actionable.js`): replace Month/Quarter
  sections with: effective mix line ("Jul 18% · Aug 52% · Sep 30% → Q1 58%"),
  per-month table (month, quad, weight, stance), tracking line
  ("Tracking: Aug (Quad 1)" or "Fighting quad path"), formula line updated.
- Regime band (`loadMacroBand()`): replace "Month | Quarter" with the window
  mix summary + dominant forward quad; keep breadth + action split.
- `macroCellHtml()` badge unchanged.

## 8. New ref_settings keys (seeds)

| Key | Default | Meaning |
|---|---|---|
| `quad_lookahead_days` | 60 | look-ahead window H (calendar days) |
| `quad_lookahead_decay_hl` | 0 | decay half-life in days; 0 = off |
| `quad_horizon_weight_qtr` | 0.05 | was 0.20 |

## 9. Docs

- Rewrite Stage 3 of `docs/quad_design.md` (window formulation, worked
  example of the sliding mix across a month, retired params).
- Entry in `docs/migrations.md`.

## 10. Tests (convention #18)

- `tests/test_quad_window.py` — pure-Python: overlap weights across month
  boundaries, mid-month slide (early vs late July mix), decay, truncation +
  coverage, near/far split, tracking-tag selection. No DB.
- Acceptance (`tests/acceptance/`, marked): drv_macro_score has detail JSONB
  for anchor date; action distribution within sane band of percentile
  targets; macro-detail API returns months array.

## How to verify (tester reference — run only on explicit request)

1. `pytest tests/test_quad_window.py` → pass.
2. `psql`: `SELECT macro_action, COUNT(*) FROM drv_macro_score WHERE
   as_of_date=(SELECT MAX(export_date) FROM hist_td) GROUP BY 1;` →
   roughly 3/12/70/12/3 split.
3. `psql`: one symbol's `detail` — months weights sum ≈ 1, eff pcts sum ≈ 100,
   July weight < August weight (mid-July anchor).
4. macro-detail API returns month mix + tracking for a sampled symbol.
5. UI: MACRO tooltip shows mix + per-month table + tracking; regime band
   shows window summary.

## Files expected to change

`etl/derive_macro.py`, `db/baseline.sql`, `db/seeds_quad_periods.sql`,
`db/seeds_*.sql` (settings), `api/routers/dash.py`, `web/actionable.js`,
`docs/quad_design.md`, `docs/migrations.md`, `tests/test_quad_window.py`,
`tests/acceptance/...`.

No commits — user commits from Windows.
