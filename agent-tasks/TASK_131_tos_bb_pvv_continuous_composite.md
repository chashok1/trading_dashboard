# TASK_131 — continuous PVV composite, replacing lever F's discrete label

Implemented directly (not handed to the developer subagent — user asked for
direct implementation in this session).

## Goal

TASK_130's lever F (PVV-style tape skew) was rejected by the 2-fold CV gate
for both bands, using `etl.derive_pvv.classify_pvv()`'s discrete 8-bucket
label. Test the hypothesis that discretization was the reason it found no
signal: replace it with a continuous price-ROC x volume-ROC/volatility
composite that (a) shifts both band edges together (a "level" mid-tilt, same
mechanism as the old lever F) and (b) narrows the band spread specifically
under bullish + volume-confirmed + contracting-vol conditions (a mechanism
TASK_130's lever F never had), then refit under the same 2-fold walk-forward
CV gate (`_fold_gate()`, unchanged from TASK_130).

## Outcome

- **Lever F1 (continuous mid-tilt)**: rejected for both bands — no candidate
  passed the fold gate.
- **Lever F2 (bullish-low-vol width narrow)**: rejected for TOP; for BOTTOM,
  technically cleared the CV gate at `c_narrow=0.3` (train 0.814%→0.813%,
  **zero** movement on either fold), but moves the full-history metric by
  <0.0001pp (0.8373% either way) — a noise-level gate-pass, not real signal.
  Per the spec's mandatory complexity-cap guardrail ("if two configs are
  within 0.03pp, take the simpler one"), deployed **inactive** (`c_narrow=0.0`).
- **Final deployed formula is numerically identical to TASK_130's** — TOP
  0.700%/80.8%, BOTTOM 0.837%/77.9% (still short of the ≤0.75%/≥78% BOTTOM
  target, same documented shortfall as TASK_130).
- Conclusion: this independently confirms TASK_130's finding via a different
  feature representation — the price/volume/vol-ROC signal in this dataset,
  discretized or continuous, carries no material out-of-sample information
  beyond what Family D's existing `c_t`/`c_iv` terms already capture.

Full ablation, the F2 gate-vs-effect comparison, and fitted params: see
`docs/tos_rr_calibration.md` §"TASK_131 — continuous PVV composite, replacing
lever F's discrete label".

## Files changed

`etl/calibrate_tos_rr.py` (removed `classify_pvv`/`_direction` import; new
`_zscore()` helper; `pvv_level`/`pvv_narrow` features replace `pvv_skew`;
`predict_full_v2` mid-tilt now uses `pvv_level`, width gains a `narrow_mult`
factor; `fit_family_e()`'s single "F" step split into "F1"/"F2"; `C_S_GRID`
reused for F1, new `C_NARROW_GRID` for F2), `TOS/BBTop.txt` /
`TOS/BBBottom.txt` (ThinkScript equivalent of the continuous composite,
`cNarrow` input added, both wired in but inactive), `docs/tos_rr_calibration.md`.
No change to `etl/derive.py`, `drv_rr`, or schema.

## Verified

- `python -m etl.calibrate_tos_rr` (full run) and `--report` (fast rescore)
  both reproduce TOP 0.700%/80.8%, BOTTOM 0.837%/77.9% on the full
  `hist_rr` history.
- Both `TOS/*.txt` files read back complete (not truncated) after editing.
- No remaining references to `classify_pvv`/`_pvv_direction`/`pvv_skew` in
  `etl/calibrate_tos_rr.py` (grepped clean, doc-comments only mention the
  old name for context).

No commits made — user commits from Windows.
