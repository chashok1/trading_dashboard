# TASK_129 (v2) — TOS BB bands: full PVV fit (price + volume + volatility)

## Goal

Follow-up to TASK_128 (explicit user requirement). The fitted
`TOS/BBTop.txt` / `BBBottom.txt` use price (EMA midpoint) and realized
volatility (StDev width) only. The user wants a **full price/volume/
volatility model with the richest feature set available** — volume rate of
change, relative volume, implied vol, historical vol, IV/HV ratio, etc. —
and the **closest achievable match** to `hist_rr`, not just a marginal
volume term.

**Hard requirements:**

1. Final ThinkScripts must contain **active (non-zero-coefficient) terms
   from all three legs**: price, volume, volatility.
2. **Targets** (full hist_rr history, both bands): median APE ≤ 1.0% and
   ≥ 70% of ticker-days within 2%. **Stretch:** ≥ 80% within 2%. Never
   regress a metric below TASK_128's fit (TOP 0.97%/72.1%, BOTTOM
   1.14%/63.8%). If a target is missed after honest exploration, document
   the best run and why (as TASK_128 did) — but exhaust the feature menu
   first, don't stop at the first improvement.
3. Everything must remain computable in a standalone TOS custom column:
   OHLCV, `imp_volatility()` (NaN-guard), close-derived realized vol.
   Guard every ratio (`IsNaN`, zero denominators) so volume-less/IV-less
   symbols (VIX, indices) degrade to neutral terms.

## Feature menu (DB source ↔ TOS equivalent)

| Leg | Feature | DB (anchored `< D`, EOD = max sequence) | TOS |
|---|---|---|---|
| Price | mid: EMA/SMA(n); momentum: close−mid, EMA_f−EMA_s, price ROC(h) | `hist_td.last_price` | native |
| Volume | RelVol = Avg(vol,f)/Avg(vol,s); volume ROC(h); volume z-score(n) | `hist_tl.volume` | `volume` + `IsNaN` guard |
| Volatility | realized: StDev(close,n); IV level & ROC(h); HV; IV/HV ratio; IV-implied daily move = close·IV/15.87 | `hist_td.imp_volatility`, `historical_vol` | `imp_volatility()`, HV via close-stdev annualized |

Clamp every multiplicative term to a sane range (e.g. [0.5, 2.0]) so one
bad print can't blow up a band.

## Model space (grid / coordinate search, CV = leave-last-14-days-out)

Compose from:

- **Midpoint:** `mid' = mid(n) + c_t·RelVol·(close − mid) + c_m·(EMA_f − EMA_s)`
  (volume-confirmed tilt + trend tilt; either c may fit to 0 — but not both
  volume terms in the whole model, see req. 1).
- **Width sigma blend:** `sigma = w·StDev(close, n) + (1−w)·close·IV/15.87·sqrt(h)`
  — blend realized and IV-implied vol; `w ∈ [0,1]` swept; IV NaN → w=1.
- **Width multipliers:** `k · (1 + c_v·(RelVol−1)) · (1 + c_iv·(IV/HV−1))`,
  separate `k_top` / `k_bot`; optionally separate `c`'s per side (Hedgeye
  ranges are asymmetric).
- Re-sweep `n`, `f`, `s`, `h`, `k_top`, `k_bot` jointly with the new terms —
  don't freeze TASK_128's length=10.

Search order: start from TASK_128's fit, add legs by coordinate descent
(fit one new coefficient at a time, keep what helps on CV), then a local
joint refinement. Report every step's CV score so the ablation is real.

**Per-ticker overrides are allowed this time** if global params leave
specific tickers (ORCL/VIX/TSLA-class) far off: a small `GetSymbol()`
branch table in the scripts (≤ ~6 symbols) overriding `k`/`c` values.
Only add a symbol if it improves that symbol's median APE by ≥ 1pp.

## Deliverables

- `etl/calibrate_tos_rr.py` — extended features + search as above;
  `--report` rescores stored `FITTED` (incl. any per-ticker overrides).
- `TOS/BBTop.txt` / `BBBottom.txt` — full PVV formula, fitted constants as
  `input`s, all guards, plot names still `bridge_band_top`/`bridge_band_bottom`.
- `docs/tos_rr_calibration.md` — new TASK_129 section: final formula,
  **ablation table** (P-only / P+Vol / P+Volume / all three / +overrides),
  final error vs targets, worst-5 tickers before/after, volume & IV data
  coverage note.
- `DEV_HANDOFF.md` — log, end `ALL_DONE`.

## How to verify (tester reference — run only on explicit request)

1. `python -m etl.calibrate_tos_rr --report` — metrics match docs; both
   bands meet median ≤1.0% & ≥70%≤2% (or the documented best-achieved with
   root-cause).
2. Scripts contain active price, volume, and volatility terms (non-zero
   fitted coefficients), with `IsNaN` guards; constants match `FITTED` and
   docs (including any `GetSymbol()` override branch).
3. Ablation table shows each leg's marginal CV contribution.
4. Spot check a high-RelVol day and a high-IV/HV day: hand-compute the band
   with terms on/off from `hist_td`/`hist_tl` and confirm direction/magnitude.
5. No change to `etl/derive.py`, `drv_rr`, or schema.

## Files expected to change

`TOS/BBTop.txt`, `TOS/BBBottom.txt`, `etl/calibrate_tos_rr.py`,
`docs/tos_rr_calibration.md`, `DEV_HANDOFF.md`. No schema change.

No commits — user commits from Windows.
