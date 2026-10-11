# TASK_118 — SELL-side signal quality: downweight reactive sells + backtest sell-into-strength

## Context (from docs/audit/loss_diagnosis_2026-07.md)

All 30 SELL-direction composite rules with fires>=20 have negative `edge_20d`
(price recovers after they fire). Realized losses (-$16.7k) dwarf unrealized
(-$3.9k): the user has been selling at local bottoms on these signals. BUY
rules (34/34 positive edge) are fine — do not touch the BUY side.

One-regime caveat applies: downweight/demote, do NOT delete or rewrite the
sell rules' thresholds.

## Part A — Downweight unproven SELL rules in the actionable surface

Goal: a row whose only sell evidence comes from negative-edge rules must not
headline as a confident SELL.

1. Define "unproven sell rule": composite in `v_rule_scorecard` with
   `direction = SELL`, `fires >= 500`, `edge_20d < 0`. Materialize as a small
   view `v_unproven_sell_rules` in `db/baseline.sql` (derived from the
   scorecard — no hardcoded rule lists, so it self-updates as history grows).
2. In `etl/derive_actionable.py`: when the consolidated/final sell-side
   evidence for a symbol comes ONLY from unproven sell rules (no source-driven
   REMOVE/REDUCE, no proven rule), set a new `drv_actionable.low_confidence`
   BOOLEAN (add column in `db/baseline.sql`; keep derive idempotent). Do not
   change `consolidated_action` itself — this is a confidence annotation.
3. `web/actionable.js`: `low_confidence` sell rows render the ACTION badge in
   a muted/outline style with a "LOW CONF" sub-label, and the Final Call
   confidence badge shows Low. (Sort demotion is TASK_120's job — just expose
   the flag on the row payload here.)

## Part B — Backtest sell-into-strength candidates (report only, NOT wired in)

Mirror of the proven `52-BS-BRR` buy-at-LRR logic. Define and score, do not
activate.

Candidates (evaluate for held-relevant universe, whole history in
`drv_rule_outcome`'s date range):

- **S1 — At/above TRR**: last_price >= TRR (`hist_rr.sell_trade`), i.e. the
  existing `>=T` condition, scored standalone.
- **S2 — TRR + momentum roll**: S1 AND `macdh_direction` negative
  (`hist_tw.a_macdh_d_brr` sign, as in the QM/QN paths).
- **S3 — RR band down-shift**: TRR lowered vs prior `hist_rr` snapshot by more
  than 2% while price is in the upper half of the band.

Method: compute fires + forward 5d/20d returns from `drv_ma.last_price`
(same convention as `etl/compute_firing_outcomes.py`; an ad hoc script under
`tests/acceptance/` or a `--candidates` mode on compute_firing_outcomes is
fine). Direction-adjust: SELL wants price DOWN after firing.

Deliverable: `docs/audit/sell_candidates_2026-07.md` — per candidate: fires,
edge_20d, win_rate, verdict vs the existing reactive rules' -1.2..-2.7 edges.
Recommend (text only) which, if any, deserve to become real composites.

## Files expected to change

- `db/baseline.sql` — `v_unproven_sell_rules` view + `drv_actionable.low_confidence`
- `etl/derive_actionable.py` — confidence annotation
- `web/actionable.js` — badge styling + row payload flag
- `api/routers/dash.py` — include `low_confidence` in /api/actionable payload
- NEW `docs/audit/sell_candidates_2026-07.md`
- `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db` idempotent; `SELECT count(*) FROM v_unproven_sell_rules;` > 0.
2. Re-derive latest anchor; some rows have `low_confidence = true`; a row with
   a source-driven REMOVE (e.g. dropped from a Hedgeye list) has it FALSE.
3. /actionable shows muted LOW CONF badge on a flagged row; normal badge on others.
4. `docs/audit/sell_candidates_2026-07.md` has real numbers for S1–S3.
5. No BUY-side rule, threshold, or weight changed (`git diff` inspection).
