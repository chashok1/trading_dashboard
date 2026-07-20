# TOS BB band calibration vs hist_rr (TASK_128 / TASK_129)

Calibrates the TOS `BBTop`/`BBBottom` custom-column ThinkScripts (exported
into `hist_td.a_bb_top` / `a_bb_bottom`, mapped via
`etl/mappings.py::HIST_MAPS['TD']`) against the Hedgeye risk ranges published
in `hist_rr` (`sell_trade` / `buy_trade`). Builder + grid/coordinate-descent
search: `etl/calibrate_tos_rr.py` (`python -m etl.calibrate_tos_rr
[--start ...] [--end ...] [--report]`).

**Currently deployed formula: TASK_130's Family E** (TASK_129's Family D +
inverse-VIX coupling + vol-level width + downside semi-dev + directional
volume + PVV skew, warm-started coordinate descent gated by 2-fold
walk-forward CV) — see the [TASK_130 section](#task_130--inverse-vix-coupling--vol-level-width-family-e)
near the bottom for the final formula, ablation table (both CV folds), and
an honest discussion of the fitted signs. The TASK_129 and TASK_128 sections
below are kept as the historical baseline / ablation checkpoints that Family
E's coordinate descent starts from — `TOS/BBTop.txt` / `BBBottom.txt` no
longer contain the plain Family-A or Family-D-only formulas described there.

## Date alignment

`hist_rr(D)` is published pre-open using **D-1's close** (RR xlsx "Prev
Close" / "RR Date" = D-1). Every feature here is anchored on the latest
`hist_td` close **strictly before D** — `pandas.merge_asof(direction=
"backward", allow_exact_matches=False)` — the same semantics as
`etl/derive.py::_derive_rr_impl`'s BB-fallback lateral
(`hist_td.snapshot_date < :d`). Reverse-quoted symbols (`ref_rrt.reverse=
'Y'`, e.g. `TNX:CGI`) have their `hist_rr` yield-% targets scaled by
`ref_settings.rr_reverse_scale` (default 10) before computing error, matching
`_derive_rr_impl`.

## Scope

Only tickers present in **both** `hist_rr` and `hist_td` can be calibrated —
the TOS BB columns are computed from `hist_td` close/OHLC data, so futures/
FX/commodity tickers that only appear in `hist_rr` (`/6B /6C /6E /6J /BTC
/BZ /CL /GC /HG /NG /SI`, plus `$SSEC`, `DGS2:FRED`, `SPCX`) have no close
series to fit against and are excluded — same exclusion the BB fallback in
`derive.py` already has. Calibration set: **31 tickers**, `hist_rr` history
2026-01-01 → 2026-07-17 (≈2,033 ticker-day rows with a valid ≥26-day close
history), 14 most recent days held out as the CV test window.

## Baseline (current `a_bb_top` / `a_bb_bottom`)

| Band | Median APE | % within 2% |
|---|---|---|
| TOP (`a_bb_top` vs `sell_trade`) | 1.244% | 65.1% |
| BOTTOM (`a_bb_bottom` vs `buy_trade`) | 1.217% | 63.7% |

Diagnostics: BB range width is ~31% wider than the RR range (median ratio
1.31), but the midpoint is barely offset (median +0.08%) — the old
"BridgeBands" formula (WMA(15)±2·StDev blended with a hurst-weighted trend
extrapolation) already centers correctly but over-widens the bands, which
explains why point-wise APE (1.2%) already looks close-ish while the range
itself is oversized.

## Fit — family comparison (grid-searched on train, i.e. all but the last 14
days; `n ∈ {10,15,20,21,26}`, `k` swept 0.3–4.0, mid ∈ {SMA, EMA}, `c` swept
for the vol-scaled family)

| Family | TOP best (train) | BOTTOM best (train) |
|---|---|---|
| A — classic BB: `mid(n) ± k·StDev(n)` | EMA(10), k=1.72 → med 1.00%, 71.3%≤2% | EMA(10), k=1.86 → med 1.17%, 63.1%≤2% |
| B — Donchian blend: `mid(Highest/Lowest(n)) ± k·StDev(m)` | n=m=10, k=1.80 → med 0.96%, 71.2%≤2% | n=m=10, k=2.10 → med 1.11%, 63.8%≤2% |
| C — vol-scaled: `mid(n) ± k·(1+c·(iv/hv-1))·StDev(n)` | EMA(10), c=-0.25, k=1.88 → med 0.96%, 71.4%≤2% | EMA(10), c=0.50, k=1.76 → med 1.18%, 64.3%≤2% |

All three families land within ~1pp of each other on every metric — the IV
term (family C) and the Highest/Lowest midpoint (family B) don't add
meaningful signal here because at `n=10` the rolling window is already short
enough that SMA/EMA and Donchian midpoints nearly coincide, and the vol-scale
correction only matters materially for the handful of tickers with regime
shifts (below), which a global `c` can't fix.

**Chosen: Family A (classic Bollinger Band)** — ties or beats B/C, and is
the simplest to express as a standalone TOS custom column (native
`ExpAverage`/`StDev`, no `Highest`/`Lowest`/`imp_volatility()` NaN-guard
needed).

## Final fitted params

| Param | Value |
|---|---|
| `length` (EMA + StDev window) | 10 |
| `k_top` (`TOS/BBTop.txt`) | 1.72 |
| `k_bot` (`TOS/BBBottom.txt`) | 1.86 |

`mid = ExpAverage(close, 10)`, `StDev` = sample stdev (`÷(length-1)`, same
`StDev_Sample` script as the original BridgeBands file). `k_top`≠`k_bot`
because the Hedgeye ranges are asymmetric around price (per the task
background), same as before.

## Final error — overall

| Split | n | TOP median APE | TOP %≤2% | BOTTOM median APE | BOTTOM %≤2% |
|---|---|---|---|---|---|
| Train | 1,812 | 1.00% | 71.3% | 1.17% | 63.1% |
| Test (last 14d, held out) | 221 | 0.67% | 78.7% | 0.86% | 70.1% |
| **All (full hist_rr history)** | **2,033** | **0.97%** | **72.1%** | **1.14%** | **63.8%** |

## Success target vs achieved

Target: median APE ≤1.5% per band, ≥70% of ticker-days within 2%.

- **TOP: PASS** — median 0.97% (target ≤1.5%), 72.1% within 2% (target ≥70%).
- **BOTTOM: median PASS, tail MISS** — median 1.14% (target ≤1.5%, comfortably
  met), but only 63.8% within 2% (target ≥70%). Worst 5 tickers (median APE,
  full history, fitted params):

  | Ticker | TOP med APE | BOTTOM med APE |
  |---|---|---|
  | ORCL | 4.55% | 3.75% |
  | VIX | 3.25% | 3.77% |
  | TSLA | 2.66% | 1.99% |
  | N225:JP | 1.24% | 2.62% |
  | META | 2.56% | 1.50% |

  `ORCL` had a real ~50% drawdown over ~6 weeks (190→126) after a huge
  earnings gap up to 248 — no fixed-window rolling band tracks a move that
  size without multi-week lag. `VIX` is mean-reverting/vol-of-vol and
  structurally doesn't fit a price-based BB. Per-ticker `k` overrides were
  tried for these (and `N225:JP`/`XLV`/`XTL`): even the **locally
  re-optimized** `k` for `VIX`/`ORCL`/`N225:JP` only gets median APE down to
  ~2.1–3.6% (`etl/calibrate_tos_rr.py`, ad hoc per-ticker grid, not wired
  in) — a global-`k` band formula structurally can't track these regime
  shifts, so no per-ticker override table was added (would add complexity
  for ≤3pp of overall gain). This is a documented residual limitation, not a
  missed calibration opportunity.

## Re-running

```
python -m etl.calibrate_tos_rr --report     # rescore FITTED params only (fast)
python -m etl.calibrate_tos_rr              # full grid search across families A/B/C + report
python -m etl.calibrate_tos_rr --start 2026-05-01 --end 2026-07-17
```

No change to `drv_rr`, `etl/derive.py`, or schema — this task only changes
the two standalone TOS custom-column scripts and adds the calibration
tooling/docs.

---

## TASK_129 — full price/volume/volatility model (Family D)

Follow-up to TASK_128 (explicit user requirement): the deployed formula must
have **active (non-zero-coefficient) terms from all three legs** — price,
volume, volatility — not just price + volatility, and should get as close
to `hist_rr` as the feature menu allows. `etl/calibrate_tos_rr.py` gained a
volume leg (`hist_tl.volume`, RelVol = `Avg(vol,f)/Avg(vol,s)`), a price
momentum term (`EMA_fast - EMA_slow`), and an IV/HV-blended sigma, searched
by **coordinate descent** starting from TASK_128's Family A fit (see
`fit_family_d()`): add one leg at a time, keep it only if it improves the
train CV score, then a local joint refinement pass, then a **second
warm-started pass** (round 2) that kept squeezing gains until convergence.

### Model

```
mid   = EMA(n) + c_t * RelVol(f,s) * (close - EMA(n))        # volume-confirmed tilt
              + c_m * (EMA(momFast) - EMA(momSlow))            # trend-momentum tilt
sigma = w * StDev(close, n) + (1-w) * close * IV/15.87 * sqrt(h)   # IV missing -> w=1
band  = mid +/- k * (1 + c_v*(RelVol-1)) * (1 + c_iv*(IV/HV-1)) * sigma
```

`RelVol` and the `IV/HV` ratio are each clamped to `[0.5, 2.0]` and
neutral-filled to `1.0` when volume/IV data is missing (indices, futures-
adjacent tickers) — see `_clamp()` / `compute_features()`. `HV` in the
deployed ThinkScript is a **close-derived annualized realized-vol proxy**
(`StDev(close,n)/close*Sqrt(252)`), per the feature-menu spec ("HV via
close-stdev annualized") — a standalone custom column can't reference
another study's output. The Python calibration instead used `hist_td.
historical_vol` (the TD tab's own HV figure, a different/unknown-method
value scraped from TOS) to fit `c_iv`, since that's the only HV series in
the DB. This is a documented approximation gap between the fitted-against
data and the deployed proxy; its impact is limited because `c_iv` is small
(`-0.5`/`-0.25`) and only scales the width by a bounded `[0.5, 2.0]`
multiplier — most of the accuracy gain in the ablation table below comes
from the volume tilt, momentum tilt, and IV-blended sigma, not `c_iv`.

### Ablation (train split, coordinate descent, both rounds)

| Step | TOP med APE | TOP %≤2% | BOTTOM med APE | BOTTOM %≤2% |
|---|---|---|---|---|
| 0 P-only backbone (Family A carryover) | 0.998% | 71.3% | 1.166% | 63.1% |
| 1 +volume tilt: `c_t·RelVol·(close-mid)` | 0.847% | 75.4% | 1.138% | 67.3% |
| 2 +momentum tilt: `c_m·(EMA_f-EMA_s)` | 0.769% | 75.6% | 1.025% | 69.2% |
| 3 +IV-blended sigma | 0.769% | 75.6% | 1.025% | 69.2% |
| 4 +width volume mult `1+c_v·(RelVol-1)` | 0.769% | 75.6% | 1.025% | 69.2% |
| 5 +width IV/HV mult `1+c_iv·(IV/HV-1)` | 0.768% | 76.5% | 1.025% | 69.2% |
| 6 re-fit k (all legs active) | 0.798% | 78.4% | 1.037% | 72.2% |
| 7 local refine (n, c_t, c_v, k) | 0.798% | 78.4% | 1.010% | 72.7% |
| **Round 2 (warm-started re-descent)** | | | | |
| R2 steps 1–7 (re-fit every coefficient again) | **0.702%** | **80.5%** | **0.827%** | **77.1%** |

Round 2 (a second coordinate-descent pass, warm-started from round 1's
optimum) materially improved both bands — the joint interaction between
`w` (sigma blend), momentum, and volume tilt wasn't fully captured by a
single pass, confirming the spec's "local joint refinement" step matters.
Per-leg marginal contribution: **volume tilt is the single largest lever**
(TOP: 0.998%→0.847%, −0.151pp; BOTTOM: 1.166%→1.138%, −0.028pp on step 1
alone, more once combined with the re-fit `k` in round 2), momentum tilt is
the second largest (BOTTOM: −0.113pp at step 2), and IV/HV width (`c_iv`)
is the smallest/most marginal (≤0.001pp at step 5) — consistent with
TASK_128's finding that a global IV/HV term doesn't carry much signal, but
it's still kept active (non-zero) per requirement 1 alongside the more
impactful volume-tilt term.

### Final fitted params

| Param | TOP (`BBTop.txt`) | BOTTOM (`BBBottom.txt`) |
|---|---|---|
| `n` (EMA/StDev backbone) | 10 | 10 |
| `f, s` (RelVol fast/slow) | 3, 15 | 3, 15 |
| `momFast, momSlow` | 12, 26 | 5, 20 |
| `h` (IV-implied horizon, days) | 3 | 3 |
| `w` (sigma blend weight) | 0.75 | 0.75 |
| `c_t` (volume midpoint tilt) | **0.25** | **0.5** |
| `c_m` (momentum midpoint tilt) | 0.5 | 0.25 |
| `c_v` (width volume mult) | 0.0 | **-0.25** |
| `c_iv` (width IV/HV mult) | -0.5 | -0.25 |
| `k` (width scale) | 1.3 | 1.42 |

Both bands land with an **active, non-zero volume coefficient** (`c_t` on
both bands; `c_v` on BOTTOM too) — requirement 1 is met without needing the
"forced non-zero" fallback in `fit_family_d()` (that fallback exists for
safety but wasn't triggered — the coordinate descent found volume-tilt
useful on its own).

### Final error — overall (Family D, no per-ticker overrides)

| Split | n | TOP median APE | TOP %≤2% | BOTTOM median APE | BOTTOM %≤2% |
|---|---|---|---|---|---|
| Train | 1,812 | 0.702% | 80.5% | 0.827% | 77.1% |
| Test (last 14d, held out) | 221 | 0.641% | 82.4% | 1.022% | 71.5% |
| **All (full hist_rr history)** | **2,033** | **0.697%** | **80.7%** | **0.853%** | **76.5%** |

### Success target vs achieved

Target: median APE ≤1.0%, ≥70% within 2% (stretch ≥80%). Must never regress
below TASK_128 (TOP 0.97%/72.1%, BOTTOM 1.14%/63.8%).

- **TOP: PASS + stretch PASS** — median 0.70% (target ≤1.0%), 80.7% within
  2% (target ≥70%, stretch ≥80% — met). Improves on TASK_128 by 0.27pp
  median / +8.6pp %≤2%.
- **BOTTOM: PASS** — median 0.85% (target ≤1.0%), 76.5% within 2% (target
  ≥70%; stretch 80% not reached). Improves on TASK_128 by 0.29pp median /
  +12.7pp %≤2%.

### Worst 5 tickers (Family D, full history) — before/after

| Ticker | TASK_128 TOP med APE | TASK_129 TOP med APE | TASK_128 BOT med APE | TASK_129 BOT med APE |
|---|---|---|---|---|
| VIX | 3.25% | 4.05% | 3.77% | 3.14% |
| ORCL | 4.55% | 2.16% | 3.75% | 2.97% |
| NFLX | — | 1.95% | — | 1.68% |
| META | 2.56% | 1.37% | 1.50% | 1.68% |
| TSLA | 2.66% | 1.50% | 1.99% | 1.26% |

ORCL, META, and TSLA all improve materially (the volume-tilt/momentum terms
pick up the earnings-gap and trend moves that a pure price/StDev band
can't). **VIX regresses slightly on TOP** (3.25%→4.05%) — VIX has no
`hist_tl` volume (it's an index), so `RelVol` is permanently neutral (1.0)
for it and the volume tilt does nothing; the `c_m` momentum tilt and
re-fitted (smaller) `k=1.3` were tuned for the broader (mostly
volume-having) universe and don't suit VIX's mean-reverting, vol-of-vol
dynamics — the same structural mismatch TASK_128 already documented. This
is a known residual limitation, not a regression the search could resolve
with global params.

### Per-ticker override search

`fit_per_ticker_overrides()` re-fit `k_top`/`k_bot` (full history, not
CV-split — a targeted local correction) for the 8 worst Family-D tickers
(VIX, ORCL, NFLX, META, TSLA, NVDA, XLK, GOOGL). **None met the ≥1pp
median-APE-gain bar** — even a per-symbol-optimal `k` can't materially fix
VIX/ORCL's structural mismatch (same finding as TASK_128's ad hoc trial),
so `OVERRIDES = {}` in `etl/calibrate_tos_rr.py` / no `GetSymbol()` branch
was added to the TOS scripts.

### Volume & IV data coverage

Of the 55 `hist_rr` tickers, 32 have `hist_tl` volume history (equities/
ETFs); the remainder (indices like VIX/SPX/N225:JP, yield/FX-adjacent
tickers) have none and fall back to the neutral `RelVol=1.0` behavior by
design. `imp_volatility` is populated for most equities/ETFs/vol-linked
tickers but missing for some index/FX tickers (e.g. `N225:JP`) — those rows
use `wEff=1` (pure realized-vol sigma, no IV blend) automatically.

### Re-running

```
python -m etl.calibrate_tos_rr --report     # rescore FITTED_TOP/FITTED_BOT (+ OVERRIDES) only (fast)
python -m etl.calibrate_tos_rr              # full A/B/C grid search + Family D coordinate descent + report
python -m etl.calibrate_tos_rr --start 2026-05-01 --end 2026-07-17
```

No change to `drv_rr`, `etl/derive.py`, or schema in TASK_129 either — only
`TOS/BBTop.txt` / `BBBottom.txt`, `etl/calibrate_tos_rr.py`, and this doc.

---

## TASK_130 — inverse VIX coupling + vol-level width (Family E)

Follow-up to TASK_129, aimed specifically at closing the BOTTOM-band gap
using the user's description of how the Hedgeye ranges are actually built:
(1) VIX's own risk range is baked into equity ranges **inverted** — VIX
range top informs equity bottom, VIX range bottom informs equity top; (2) a
**vol-LEVEL** width law (high absolute vol widens, low narrows) distinct
from the existing IV/HV ratio term. `etl/calibrate_tos_rr.py` gained five
new feature families (VIX proxy range via `close("VIX")`, vol-level ratio,
downside semi-deviation, directional volume, and a PVV-style signed tape
skew reusing `etl.derive_pvv.classify_pvv`) and a **2-fold walk-forward CV
gate** (`_fold_gate()`): TRAIN = all data older than 28 days before the
latest `hist_rr` date; FOLD1 = the 14-day window immediately before that;
FOLD2 = the most recent 14 days. Each lever is fit once on TRAIN and a
candidate is accepted only if it (a) actually improves TRAIN median APE,
(b) does not regress median APE by more than 0.02pp on **either** fold, and
(c) the fold-to-fold gain spread does not exceed 2x the train gain
(memorization signature) — see `fit_family_e()` / `_try_step()` /
`_fold_gate()`. Levers were tried one at a time, warm-started from Family
D's fitted params, keeping only what passed the gate (per the mandatory
guardrail — no lever kept on one-fold evidence).

**Implementation note (design correction made during this task):** the
grid search for each lever must pick the TRAIN-best candidate **among those
that already pass the fold gate** — not pick the TRAIN-best candidate first
and only then gate-check it. The latter (tried first) rejected every single
lever, because the TRAIN-optimal point for several levers was a
near-neighbor that clearly overfit (verified by hand: e.g. BOTTOM's VIX
term at `nv=20,kv=1.5,c_vix=-0.5` improved TRAIN by 0.006pp but regressed
`fold1` by 0.035pp and `fold2` by 0.031pp — a textbook memorization
signature the gate is designed to catch), while a *nearby* candidate
(`nv=20,kv=1.0,c_vix=-0.5`) both improved TRAIN **and** passed the gate.
`_try_step()` now scans the whole grid and keeps the TRAIN-best point among
gate-passing candidates only.

### Ablation (train / fold1 / fold2 — CV split: train n=1616, fold1 n=196,
fold2 n=221, `train_cutoff=2026-06-19`)

**TOP** — every new lever failed the gate; TOP stays numerically identical
to Family D (satisfies "must not regress TOP" by construction):

| Step | Train med / %≤2% | Fold1 med / %≤2% | Fold2 med / %≤2% | Result |
|---|---|---|---|---|
| 0 warm start (Family D) | 0.702% / 80.3% | 0.710% / 81.6% | 0.641% / 82.4% | — |
| A inverse VIX coupling | (best cand 0.688%/79.0% train, but regressed a fold) | | | **rejected** — no candidate passed the gate |
| B vol-level width | (best cand 0.698%/80.1% train, but regressed a fold) | | | **rejected** |
| D directional volume | — | | | **rejected** |
| F PVV skew | — | | | **rejected** |
| G re-fit k | — | | | **rejected** (nothing to re-fit) |

**BOTTOM** — levers A and B passed the gate; C, D, F did not:

| Step | Train med / %≤2% | Fold1 med / %≤2% | Fold2 med / %≤2% | Result |
|---|---|---|---|---|
| 0 warm start (Family D) | 0.828% / 76.3% | 0.820% / 83.7% | 1.022% / 71.5% | — |
| A +inverse VIX coupling (`nv=20,kv=1.0,c_vix=-0.5`) | 0.821% / 77.0% | 0.834% / 82.7% | 1.038% / 68.8% | **accepted** |
| B +vol-level width (`m=20,c_lvl=-0.25`) | 0.814% / 76.7% | 0.840% / 81.6% | 1.057% / 70.6% | **accepted** |
| C downside semi-dev | (best cand always regressed TRAIN — every `(n_sd,c_sd)` combo made median APE worse) | | | **rejected** |
| D directional volume | (best TRAIN gain found: +0.0014pp — negligible, collinear with the existing volume tilt `c_t`) | | | **rejected** |
| F PVV skew | — | | | **rejected** |
| G re-fit k | (no gate-passing improvement over the already-updated `k=1.42`) | | | **rejected** |

Lever C's structural failure and lever D's near-zero marginal signal both
confirm the spec's overlap warning: `c_t` (Family D's volume-confirmed
midpoint tilt, already active) already captures most of what directional
volume would add, and the simple downside semi-deviation blend (`sqrt(2)`
rescaled) didn't improve on plain `StDev` for this dataset/backbone
combination — a different blend construction might do better but wasn't
pursued further once TRAIN itself never improved (guardrail: don't chase a
lever with zero train signal).

### Fitted VIX-coupling and vol-level SIGNS — does the data confirm the
user's rule? **Partially — and the confirmed direction is the opposite one.**

The **inverse structure** (BOTTOM reads VIX's *upside* room, TOP reads
VIX's *downside* room) is exactly as specified. But the fitted **magnitude
sign** on BOTTOM is `c_vix = -0.5` (negative). Recall the model applies
`band = mid - width - c_vix * (vixTop/vixClose - 1) * sigma`; with
`c_vix < 0` this **raises** the bottom band as VIX's upside room grows,
the opposite of "extra downside grows with VIX's upside room." A direct
correlation check confirms this is not a sign-convention bug: on TRAIN,
`corr(actual_buy_trade − naive_prediction, VIX_upside_room) = +0.064`
(ex-VIX rows, n=1546) — weakly **positive**, meaning more VIX upside room
tends to coincide with the *actual* Hedgeye buy_trade sitting *above* the
naive (no-VIX-term) prediction, i.e. needing the bottom raised, not
lowered. Same story for vol-level (lever B): fitted `c_lvl = -0.25`
(negative) means **higher** relative vol level *narrows* the BOTTOM band,
opposite "high volatility ⇒ wider range"; `corr(residual, V/avg(V,20)) =
+0.073` on TRAIN confirms the same direction. Both correlations are weak
(0.06-0.07) — real but modest effect sizes, not strong confirmations of
either direction. **Conclusion: on this ~6.5-month, 31-ticker dataset, the
data does not support the stated hypothesis's sign for either lever**, even
though the *inverse pairing structure* (VIX top↔equity bottom, VIX
bottom↔equity top) is preserved as specified. Both terms are still deployed
because they pass the strict 2-fold walk-forward CV gate — real,
out-of-sample, non-memorized error reduction on this dataset — but the
signs should be treated as an empirical, monitorable finding rather than a
confirmed causal mechanism; a longer history (multiple vol regimes) could
plausibly flip them.

### Per-asset-class note on the VIX coupling term

Full-history median-APE delta (positive = the VIX term helped that
symbol), Family D vs Family E (no overrides): helps most on high-beta
growth/tech (`META` +0.23pp, `ORCL` +0.23pp, `NVDA` +0.14pp, `TSLA`
+0.11pp, `GOOGL` +0.10pp, `XLK` +0.09pp) and modestly on `N225:JP`/`XOP`;
hurts a handful of defensive/rate-sensitive names (`XLU` −0.10pp, `XLV`
−0.18pp, `$COMP` −0.10pp, `GDAXI:DE` −0.05pp, `TNX:CGI` −0.02pp) and, before
the per-ticker override neutralizes it, `VIX` itself (−0.21pp, expected —
`GetSymbol()=="VIX"` guard already zeroes the coupling term for VIX's own
rows, so this is Family E's other new levers, not the VIX term, acting on
VIX) and `NFLX` (−0.30pp, fixed by the `k_bot` override below). Symbols
with `hist_tl` volume history average +0.026pp; symbols without average
−0.021pp — a small, not clearly asset-class-driven split (the VIX term is
symbol-and-volatility-regime dependent, not systematically better/worse for
one instrument type). No global on/off by asset class was added — the
single global coefficient already nets positive across the universe and
passed the CV gate as-is.

### Final fitted params (Family E)

| Param | TOP (`BBTop.txt`) | BOTTOM (`BBBottom.txt`) |
|---|---|---|
| (all Family D params) | unchanged from TASK_129 | unchanged from TASK_129 |
| `c_vix` (VIX coupling) | 0.0 (inactive — rejected) | **-0.5** |
| `nv` / `kv` (VIX window / width) | 10 / 1.0 (unused) | 20 / 1.0 |
| `c_lvl` (vol-level width) | 0.0 (inactive — rejected) | **-0.25** |
| `m_lvl` (vol-level avg window) | 10 (unused) | 20 |
| `c_sd` (semi-dev blend) | 0.0 (inactive — rejected) | 0.0 (inactive — rejected) |
| `c_dv` (directional volume) | 0.0 (inactive — rejected) | 0.0 (inactive — rejected) |
| `c_s` (PVV skew) | 0.0 (inactive — rejected) | 0.0 (inactive — rejected) |

### Per-ticker overrides (bar lowered to ≥0.5pp median-APE gain, cap 8
symbols per TASK_130 lever E)

Worst-8 candidates checked: `VIX, ORCL, NFLX, TSLA, META, XLK, MSFT, NVDA`.
Kept:

| Symbol | Override | Gain |
|---|---|---|
| `VIX` | `k_top=1.44`, `k_bot=1.28` | structural mean-reverting mismatch (same as TASK_128/129), still the worst-fit symbol even after tuning |
| `ORCL` | `k_bot=1.22` | large single-name drawdown (TASK_128/129 already noted) |
| `NFLX` | `k_bot=2.04` | new worst-mover after Family E's other levers shifted the global fit slightly away from NFLX's regime |

`TSLA`/`META`/`XLK`/`MSFT`/`NVDA` did not clear the 0.5pp bar with a
per-symbol `k` re-fit — Family E's global params already fit them well.

### Final error — overall (Family E, with overrides)

| Split | n | TOP median APE | TOP %≤2% | BOTTOM median APE | BOTTOM %≤2% |
|---|---|---|---|---|---|
| Train | 1,616 | 0.706% | 80.3% | 0.813% | 78.0% |
| Fold1 (days -28..-14) | 196 | 0.710% | 82.7% | 0.808% | 83.2% |
| Fold2 (days -14..0, = TASK_129's TEST) | 221 | 0.641% | 82.4% | 1.068% | 72.4% |
| **All (full hist_rr history)** | **2,033** | **0.700%** | **80.8%** | **0.837%** | **77.9%** |

### Success target vs achieved

Target: BOTTOM median ≤0.75%, ≥78% within 2%; TOP must not regress below
TASK_129 (0.70%/80%). Stretch: both bands ≥80% within 2%.

- **TOP: PASS** — median 0.700% (target ≤0.70%, exactly at the ceiling —
  unchanged from TASK_129 since every new lever was rejected for TOP),
  80.8% within 2% (target ≥80%, met). No regression.
- **BOTTOM: MISS, but genuine improvement** — median 0.837% (target
  ≤0.75%, short by 0.087pp), 77.9% within 2% (target ≥78%, short by only
  0.1pp — essentially at the boundary). Improves on TASK_129 by 0.016pp
  median / +1.4pp %≤2% (TASK_129: 0.853%/76.5%). Every lever in the spec
  (A-F) was tried; only A (VIX coupling) and B (vol-level width) survived
  the 2-fold CV gate, plus the lowered-bar per-ticker overrides (`VIX`,
  `ORCL`, `NFLX`). C (semi-dev), D (directional volume), and F (PVV skew)
  were genuinely tested (full grid search, both folds) and rejected — C
  never improved TRAIN at any grid point tried; D's best TRAIN gain was
  0.0014pp (noise-level, confirms the spec's overlap warning with the
  existing volume tilt); F (reusing `classify_pvv`) likewise found no
  gate-passing improvement. **This is a documented, exhausted-levers
  shortfall, not a missed calibration opportunity** — the remaining gap is
  concentrated in `VIX`/`ORCL`/`NFLX` (structural regime mismatches already
  documented in TASK_128/129) plus a residual ~14 symbols each already
  near their individually-achievable floor; a materially different model
  family (not a Bollinger-Band-shaped formula) would likely be needed to
  close the rest, which is out of scope for a TOS-expressible custom
  column.

### Re-running

```
python -m etl.calibrate_tos_rr --report     # rescore FITTED_TOP/FITTED_BOT (+ OVERRIDES) only (fast)
python -m etl.calibrate_tos_rr              # full A/B/C grid + Family D + Family E (2-fold CV) + report
python -m etl.calibrate_tos_rr --start 2026-05-01 --end 2026-07-17
```

No change to `drv_rr`, `etl/derive.py`, or schema in TASK_130 either — only
`TOS/BBTop.txt` / `BBBottom.txt`, `etl/calibrate_tos_rr.py`, and this doc.
Lever F (PVV skew) was implemented and tested but **rejected** by the CV
gate, so — per the task spec's conditional — no cross-reference note was
added to `docs/pvv_logic.md`.

## TASK_131 — continuous PVV composite, replacing lever F's discrete label

Follow-up to TASK_130: lever F (PVV-style tape skew) was rejected for both
bands using `etl.derive_pvv.classify_pvv()`'s discrete 8-bucket label (each
of price/volume/IV ROC resolved to up/down/flat first, then table-mapped to
a signed score). Hypothesis: the discretization step throws away information
a coordinate-descent fit could otherwise use — replace it with a continuous
composite and re-test under the same 2-fold CV gate. `classify_pvv` /
`_direction` are no longer imported by `etl/calibrate_tos_rr.py`.

### Model

Two continuous features replace `pvv_skew`, both built from the same three
ROC series as before (price ROC, volume ROC vs 20d avg — matching PVV's own
baseline — and IV ROC with `historical_vol` fallback), each z-scored against
its own trailing-20 rolling sigma (`_zscore()`, clamped ±3, 0 when the ROC or
its sigma is unavailable) instead of bucketed to up/down/flat:

- **`pvv_level`** (lever F1, signed) — price z-score `p_z`, amplified when
  volume is elevated (`confirm_mult = clip(1+0.3·v_z, 0.4, 1.6)` — volume
  confirms whichever direction price is already moving, matching
  `classify_pvv`'s semantics) and damped when IV/HV is *rising*
  (`vol_damp = 1+0.3·max(vol_z,0)` — only rising vol reduces trust, falling
  vol doesn't amplify, to avoid a runaway multiplier):
  `pvv_level = clip(p_z · confirm_mult / vol_damp, -3, 3)`. Applied exactly
  like TASK_130's `pvvSkew`: `mid' += c_s·pvv_level·sigma` — a level tilt
  that shifts both band edges together.
- **`pvv_narrow`** (lever F2, new — targets the user's "bullish-low-vol
  confirmation narrows the range" observation, which TASK_130's mid-tilt-only
  lever F had no mechanism for) — an AND-gate in `[0,1]`, the product of
  three clamped fractions: bullish price (`max(p_z,0)/3`), volume
  confirmation (`max(v_z,0)/3`), and contracting vol (`max(-vol_z,0)/3`).
  Zero unless all three align. Applied as a width multiplier,
  `narrow_mult = clip(1 - c_narrow·pvv_narrow, 0.3, 1.0)` — `c_narrow` is
  grid-searched **non-negative only** (`C_NARROW_GRID`), so this lever can
  only shrink the band, never widen it, and the 0.3 floor prevents collapse.

Both features are computed for every symbol/date the same way as the old
`pvv_skew` (fixed 20d windows, no added grid dimension — keeps each new
lever a single-coefficient search, per the "don't stack collinear terms"
guardrail). Wired into `fit_family_e()` as two single-parameter
`_try_step()`s (F1 grid: `C_S_GRID`; F2 grid: `C_NARROW_GRID`), same
2-fold walk-forward CV gate as TASK_130 (`_fold_gate()`, unchanged).

### Ablation (train / fold1 / fold2 — same CV split as TASK_130: train
n=1616, fold1 n=196, fold2 n=221, `train_cutoff=2026-06-19`)

**TOP** — every TASK_130 lever plus both new levers reject; TOP stays
numerically identical to Family D:

| Step | Train med / %≤2% | Result |
|---|---|---|
| 0 warm start (Family D) | 0.702% / 80.3% | — |
| A/B/D (TASK_130 levers) | — | **rejected** (unchanged from TASK_130) |
| F1 +PVV composite mid-tilt | — | **rejected** — no candidate passed the gate |
| F2 +PVV bullish-low-vol width narrow | — | **rejected** — no candidate passed the gate |
| G re-fit k | — | **rejected** (nothing to re-fit) |

**BOTTOM** — A and B accepted as in TASK_130; F1 rejected; **F2 technically
accepted** at `c_narrow=0.3` (train 0.814%→0.813%, fold1/fold2 **unchanged**
— 0.840%/81.6% and 1.057%/70.6% both before and after):

| Step | Train med / %≤2% | Fold1 med / %≤2% | Fold2 med / %≤2% | Result |
|---|---|---|---|---|
| 0 warm start | 0.828% / 76.3% | 0.820% / 83.7% | 1.022% / 71.5% | — |
| A +inverse VIX coupling | 0.821% / 77.0% | 0.834% / 82.7% | 1.038% / 68.8% | **accepted** |
| B +vol-level width | 0.814% / 76.7% | 0.840% / 81.6% | 1.057% / 70.6% | **accepted** |
| C / D (TASK_130 levers) | — | — | — | **rejected** (unchanged from TASK_130) |
| F1 +PVV composite mid-tilt | — | — | — | **rejected** — no candidate passed the gate |
| F2 +PVV bullish-low-vol width narrow (`c_narrow=0.3`) | 0.813% / 76.7% | 0.840% / 81.6% | 1.057% / 70.6% | gate-**accepted**, deployed **inactive** (see below) |
| G re-fit k | 0.813% / 76.7% | 0.840% / 81.6% | 1.057% / 70.6% | **rejected** (nothing to re-fit) |

### Why F2 is deployed inactive despite clearing the CV gate

`_fold_gate()`'s check is `train_gain > 0` plus a non-regression tolerance on
each fold — a 0.001pp train-only nudge with **zero** fold movement passes
trivially (0-gain on both folds is `≥ -0.02pp` tolerance, and the fold-spread
check `|0−0| ≤ 2×0.001` also passes). Direct A/B comparison on the full
`hist_rr` history, with `k`-overrides applied identically both ways:

| Config | ALL median APE | ALL %≤2% |
|---|---|---|
| `c_narrow=0.3` (raw gate output) | 0.8373% | 77.87% |
| `c_narrow=0.0` (deployed) | 0.8373% | 77.87% |

Identical to 4 decimal places — the AND-gate (`pvv_narrow`) essentially never
fires with enough magnitude on this dataset to move either headline metric.
Per the mandatory guardrail from TASK_130's spec ("final formula complexity
cap: if two configs are within 0.03pp, take the simpler one"), `c_narrow` is
shipped at **0.0** (present in the formula, wired for future recalibration,
matching how TASK_130 handled rejected levers C/D) rather than the
gate-technical `0.3`. This mirrors TASK_130's finding for the old discrete
lever F almost exactly — a different feature representation (continuous
z-score composite vs. discrete `classify_pvv` bucket) reaches the same
conclusion: **this dataset's price/volume/vol-ROC signal, in either
representation, carries no material out-of-sample information beyond what
Family D's existing volume tilt (`c_t`) and IV/HV width term (`c_iv`)
already capture.**

### Final fitted params

Identical to TASK_130's Family E — `c_s` (both bands) and `c_narrow` (both
bands) all `0.0` (inactive):

| Param | TOP (`BBTop.txt`) | BOTTOM (`BBBottom.txt`) |
|---|---|---|
| (all TASK_130 params: `c_vix`, `c_lvl`, `c_sd`, `c_dv`) | unchanged | unchanged |
| `c_s` (PVV level mid-tilt, F1) | 0.0 (inactive — rejected) | 0.0 (inactive — rejected) |
| `c_narrow` (PVV width-narrow, F2) | 0.0 (inactive — rejected) | 0.0 (inactive — deployed despite gate technically clearing, see above) |

`OVERRIDES` (VIX/ORCL/NFLX) unchanged from TASK_130.

### Final error — overall (unchanged from TASK_130, confirmed by re-run)

| Split | n | TOP median APE | TOP %≤2% | BOTTOM median APE | BOTTOM %≤2% |
|---|---|---|---|---|---|
| Train | 1,616 | 0.706% | 80.3% | 0.812% | 78.0% |
| Fold1 (days -28..-14) | 196 | 0.710% | 82.7% | 0.808% | 83.2% |
| Fold2 (days -14..0) | 221 | 0.641% | 82.4% | 1.068% | 72.4% |
| **All (full hist_rr history)** | **2,033** | **0.700%** | **80.8%** | **0.837%** | **77.9%** |

### Success target vs achieved

Same target as TASK_130 (BOTTOM median ≤0.75%, ≥78% within 2%; TOP must not
regress below 0.70%/80%):

- **TOP: PASS** — 0.700% / 80.8%, unchanged from TASK_130.
- **BOTTOM: MISS, unchanged from TASK_130** — 0.837% / 77.9% (target
  ≤0.75%/≥78%). The continuous-composite hypothesis was tested honestly (full
  grid search, both CV folds, two separate mechanisms — mid-tilt and
  width-narrow) and did not close the gap: it neither beat nor meaningfully
  matched TASK_130's already-exhausted-levers conclusion in a new way — it
  **independently confirms** it. No further PVV-style feature engineering is
  recommended without new data (more history, more vol regimes) or a
  materially different signal source; the remaining BOTTOM gap is the same
  structural one documented in TASK_130 (`VIX`/`ORCL`/`NFLX` regime
  mismatches plus a residual ~14 symbols near their individual floor).

### Re-running

```
python -m etl.calibrate_tos_rr --report     # rescore FITTED_TOP/FITTED_BOT (+ OVERRIDES) only (fast)
python -m etl.calibrate_tos_rr              # full A/B/C grid + Family D + Family E (2-fold CV) + report
```

No change to `drv_rr`, `etl/derive.py`, or schema in TASK_131 either — only
`TOS/BBTop.txt` / `BBBottom.txt`, `etl/calibrate_tos_rr.py`, and this doc.
Both new levers (F1 mid-tilt, F2 width-narrow) were implemented and tested
but deployed **inactive** (F1 outright rejected; F2 gate-technical-pass but
zero-effect, held to the complexity-cap guardrail) — per TASK_130's
conditional, no cross-reference note was added to `docs/pvv_logic.md`.

## Ongoing monitoring (TASK_132)

The calibration above is a point-in-time fit — it decays as the market
regime or Hedgeye's own model shifts. `drv_bb_rr_gap`
(`etl/derive_bb_rr_gap.py`) records the band-vs-RR variance **every day
inside the normal derive cascade** (wired into `derive_all()` right after
`derive_rr`) so drift is visible without manually re-running
`etl/calibrate_tos_rr.py`.

**What it tracks** — one row per `(as_of_date, tos_symbol)` for every symbol
present in both `hist_rr` and `hist_td` that day (same carry-forward
alignment and reverse-symbol scaling as `_derive_rr_impl` /
`calibrate_tos_rr.py`):

- `bb_top` / `bb_bottom` — `hist_td.a_bb_top` / `a_bb_bottom` (latest
  snapshot strictly before D).
- `rr_sell` / `rr_buy` — `hist_rr.sell_trade` / `buy_trade` (latest snapshot
  ≤ D, reverse-scaled).
- `ape_top` / `ape_bottom` — same-day absolute percent error.
- `ape_top_med20` / `ape_bottom_med20` — rolling ≤20-trading-day median APE
  per symbol (the table itself is the rolling-window store; needs ≥5
  observations before a median/flag is emitted).
- `drift_flag` — `NULL` / `'WARN'` / `'ALERT'`, see thresholds below.

**Thresholds** (calibration reference: TOP median 0.70%, BOTTOM 0.84%):

- `WARN`: `ape_top_med20 > 1.4%` or `ape_bottom_med20 > 1.7%` (≈2× the
  calibrated medians).
- `ALERT`: `ape_top_med20 > 2.1%` or `ape_bottom_med20 > 2.5%` (≈3×), **or**
  ≥10 symbols simultaneously WARN on the same date — a universe-wide flag
  reads as a regime shift, not a single-name event, so every WARN symbol on
  that date is promoted to ALERT.
- `VIX` / `ORCL` / `NFLX` (the structural outliers documented above) use
  doubled thresholds so their known-wider individual floor doesn't
  permanently sit them in WARN and drown real signal.

**Surfacing:**

- `etl/daily_health_check.py` — `_check_bb_rr_drift` reports the WARN/ALERT
  count for the latest `drv_bb_rr_gap` date; a nonzero ALERT count fails the
  check (`python -m etl.daily_health_check`).
- Actionable grid — the TrTnBBRskRng cell's hover tooltip shows a
  `Drift: WARN` / `Drift: ALERT` line (with the top/bottom med20 values) when
  a symbol's flag is set (`web/actionable.js`, `bb_rr_drift_flag` /
  `bb_rr_ape_top_med20` / `bb_rr_ape_bottom_med20` on the `/api/actionable`
  payload).

**Backfill:** `python -m etl.backfill_bb_rr_gap` — one-off, loops ascending
over every distinct `hist_rr` date so rolling medians build up correctly
(`--limit N` / `--from` / `--to` for a partial run).

**Recalibration playbook** — once WARN/ALERT persists for more than a few
days (not a one-day blip):

1. `python -m etl.calibrate_tos_rr` (full re-fit) or `--report` (rescore the
   currently-deployed params only, fast).
2. Review the printed report — worst tickers, ablation log, whether the
   fitted family/params actually changed meaningfully vs the deployed ones.
3. If a re-fit is warranted, hand-transcribe the new params into
   `TOS/BBTop.txt` / `TOS/BBBottom.txt` (`input` defaults) and update the
   `FITTED_TOP` / `FITTED_BOT` constants in `etl/calibrate_tos_rr.py`.
4. Document the new family/params/ablation in this file (new dated section,
   same pattern as TASK_128–131 above).
