# TASK_130 — TOS BB bands: inverse VIX coupling + vol-level width; refine BOTTOM

## Goal

Refine the TASK_129 Family-D fit using the user's description of how the
Hedgeye ranges are actually constructed:

1. **Inverse VIX coupling** — VIX's risk range is baked into equity ranges
   *inverted*: the **top of VIX's range informs the bottom of SPX's range**,
   and the **bottom of VIX's range informs the top of SPX's range**.
2. **Vol-level width law** — high volatility ⇒ wider range; low volatility
   ⇒ narrower range (level-dependent, not just ratio-dependent).

Primary objective: close the BOTTOM band gap. **Targets (full history):**
BOTTOM median APE ≤ 0.75% and ≥ 78% within 2%; TOP must not regress
(median ≤ 0.70%, ≥ 80% within 2% maintained). Stretch: both bands ≥ 80%
within 2%. As before: document honestly if a target proves out of reach —
but only after exhausting the levers below.

## New levers (all ThinkScript-expressible)

- **A. VIX coupling (cross-symbol — `close("VIX")` works in a TOS custom
  column):** build VIX's own proxy range `vixMid ± kv·StDev(vixClose, nv)`
  from `close("VIX")`. Couple *inverted*:
  - BOTTOM extra downside grows with VIX's **upside room**
    (`vixTop/vixClose − 1`) — e.g.
    `bottom -= c_xb · (vixTop/vixClose − 1) · sigma` (functional form free,
    fitted; sign/direction must match the rule).
  - TOP extra upside grows with VIX's **downside room**
    (`vixClose/vixBot − 1`).
  - Guards: `IsNaN(close("VIX"))` → neutral; **skip for VIX itself**
    (`GetSymbol()` check) and fit a global on/off or coefficient per
    asset class if bonds/FX/commodity tickers reject the term (report which
    tickers the coupling helps vs hurts).
  - DB side: VIX closes come from `hist_td` (`tos_symbol='VIX'`), joined
    to every ticker-date with the same `< D` anchoring.
- **B. Vol-level width multiplier:** width × `(V / Average(V, m))^c` (or
  `1 + c·(V/avg − 1)` clamped), where V = own `imp_volatility()` (fallback:
  close-derived HV, then VIX). This is a *level* law on top of the existing
  IV/HV *ratio* term — high absolute vol widens, low narrows, per the user.
- **C. Downside semi-deviation (BOTTOM only):** replace/blend StDev with
  semi-dev of negative daily moves over n (fold over `Min(0, close −
  close[1])`) — targets the asymmetry Hedgeye bakes into buy_trade.
- **D. Directional volume:** split RelVol into up-day / down-day volume
  averages; down-volume drives the bottom tilt, up-volume the top tilt.
- **E. Per-ticker override bar lowered** to ≥ 0.5pp median-APE gain
  (was 1pp); ≤ 8 symbols via `GetSymbol()` branch.
- **F. PVV-signal skew (user pointer — reuse the project's own PVV rules,
  `docs/pvv_logic.md` §2–3 / `etl/derive_pvv.py`):** Hedgeye tilts the
  range with the tape. Compute the three PVV legs in-script per the
  existing rules — price ROC, volume ROC vs the 20d avg EOD volume (note:
  PVV's volume baseline is 20d — try `volSlowLen=20` for consistency), and
  IV ROC with HV fallback — resolve each to ↑/↓ (a simplified flat band is
  fine in ThinkScript, e.g. `|ROC| < k_flat · StDev(ROC series, 20)` via a
  fold, or sign-only), then map to a signed skew score
  `s ∈ [−1, +1]` following the §3 table's spirit (STRONG_BULL → +1,
  OVEREXT_BULL/WEAK_BULL → +0.5, NEUTRAL/DRIFT → 0, MILD_BEAR/BEAR_LEAN →
  −0.5, STRONG_BEAR → −1; exact weights fittable). Apply as
  `mid += c_s · s · sigma` and/or asymmetric band extension (bear skew
  extends bottom, bull skew extends top). In the calibrator, reuse
  `derive_pvv`'s classification semantics (volume-flat resolves ↓,
  vol-flat resolves ↓) so the Python fit and the ThinkScript agree.

Start from TASK_129's fitted params (warm start), coordinate descent as
before, adding levers A–F one at a time; keep only what improves CV.
Where levers overlap (F's volume ROC vs D's directional volume; B's vol
level vs F's vol leg), test them as alternatives first, combined second —
don't stack collinear terms that fit noise.

## Overfitting guardrails (mandatory)

- **Walk-forward CV, 2 folds** (e.g. hold out last 14d AND the 14d before
  it, fit on the rest, score each fold) — a lever is kept only if it helps
  on **both** folds, not just one.
- Report train/fold1/fold2/all metrics for every accepted lever in the
  ablation table. Reject any config whose fold spread exceeds ~2× the
  train gain (memorization signature).
- Final formula complexity cap: if two configs are within 0.03pp, take the
  simpler one.

## Deliverables

- `etl/calibrate_tos_rr.py` — VIX-coupling + vol-level + semi-dev +
  directional-volume features, 2-fold walk-forward scoring, updated
  `FITTED_TOP`/`FITTED_BOT`/`OVERRIDES`; `--report` rescores the new fit.
- `TOS/BBTop.txt` / `BBBottom.txt` — updated formulas, all constants as
  `input`s, `close("VIX")` + `IsNaN` guards, plot names unchanged.
- `docs/tos_rr_calibration.md` — TASK_130 section: which levers survived
  (esp. whether the data confirms the user's VIX-inversion rule — show the
  fitted signs), ablation with both folds, final params/error, worst-5
  before/after, per-asset-class note on the VIX term, and — if lever F
  survives — a note in `docs/pvv_logic.md` cross-referencing that the TOS
  bands now embed a PVV-style skew (keep the two docs consistent).
- `DEV_HANDOFF.md` — log, end `ALL_DONE`.

## How to verify (tester reference — run only on explicit request)

1. `python -m etl.calibrate_tos_rr --report` — BOTTOM ≤ 0.75% median &
   ≥ 78% ≤ 2% (or documented best-achieved + root cause); TOP not regressed.
2. Fitted VIX-coupling signs match the stated rule (VIX upside room →
   lower bottom; VIX downside room → higher top); term neutralizes for
   VIX itself and NaN symbols.
3. Ablation shows both CV folds for every accepted lever; no lever kept on
   one-fold evidence.
4. Spot check SPX on a high-VIX date and a low-VIX date: hand-compute the
   coupled band from `hist_td` and confirm the range widens/narrows with
   the vol level as the user described.
5. No change to `etl/derive.py`, `drv_rr`, or schema.

## Files expected to change

`TOS/BBTop.txt`, `TOS/BBBottom.txt`, `etl/calibrate_tos_rr.py`,
`docs/tos_rr_calibration.md`, `DEV_HANDOFF.md`. No schema change.

No commits — user commits from Windows.
