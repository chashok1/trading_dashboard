"""Factor Weights -- pure calculation core (DESIGN_SPEC_13, build step 2/3).

Research only. Never changes the Final Call, never trades, never feeds a score.
No database access in this module: every function takes plain Python / numpy
values so it can be tested without Postgres. The nightly job that reads the
database and writes drv_factor_lab / drv_factor_weight is a separate step.

Judgement calls (all from DESIGN_SPEC_13, marked there as such):
  - a return above 100% over the horizon, or a one-day jump above 50%, is a data error
  - a start price equal to the 5-day price is a frozen price
  - an episode is a run of the same Final Call code; a gap above 5 trading days starts a new one
  - trust flags: >= 50 episodes, >= 20 stocks, 90% range not crossing zero, both halves agree
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

# ---- judgement-call constants (change here only) ---------------------------
MAX_HORIZON_RETURN = 1.00        # > +100% over the horizon -> data error
MAX_ONE_DAY_JUMP = 0.50          # > 50% in one day inside the window -> data error
EPISODE_GAP_DAYS = 5             # gap in trading days that starts a new episode
MIN_EPISODES = 50
MIN_STOCKS = 20
HORIZONS = (5, 10, 20)

NA = "n/a"


# ---- buckets ---------------------------------------------------------------
def bucket_by_cuts(value: Optional[float], cuts: Sequence[float], labels: Sequence[str]) -> str:
    """Return the label of the bucket `value` falls in.

    cuts are the upper edges, ascending; len(labels) == len(cuts) + 1.
    A value exactly on a cut-off goes to the LOWER bucket. None / NaN -> "n/a".
    """
    if len(labels) != len(cuts) + 1:
        raise ValueError("labels must be one longer than cuts")
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return NA
    for cut, label in zip(cuts, labels):
        if value <= cut:
            return label
    return labels[-1]


def bucket_range_position(price: Optional[float], lrr: Optional[float], trr: Optional[float],
                          lrr_zone_pct: float = 25.0, mid_pct: float = 60.0,
                          trr_zone_pct: float = 80.0) -> str:
    """Where price sits in its Risk Range (LRR..TRR). Cut-offs are the settings the grid uses."""
    if price is None or lrr is None or trr is None or trr <= lrr:
        return NA
    if price < lrr:
        return "Below LRR"
    if price > trr:
        return "Above TRR"
    pos = (price - lrr) / (trr - lrr) * 100.0
    return bucket_by_cuts(pos, [lrr_zone_pct, mid_pct, trr_zone_pct],
                          ["LRR zone", "Mid", "Upper", "TRR zone"])


def bucket_rsi(rsi: Optional[float], oversold: float = 30.0, overbought: float = 70.0) -> str:
    return bucket_by_cuts(rsi, [oversold, overbought], ["Oversold", "Neutral", "Overbought"])


def bucket_iv_percentile(p: Optional[float]) -> str:
    return bucket_by_cuts(p, [30.0, 70.0, 90.0], ["Low", "Mid", "Elevated", "Extreme"])


def bucket_sign(value: Optional[float], up: str = "Up", down: str = "Down") -> str:
    """MACD / MACDH style: > 0 is up, otherwise down. Exactly 0 goes to the lower bucket."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return NA
    return up if value > 0 else down


# ---- outcomes --------------------------------------------------------------
def forward_outcomes(closes: Sequence[Optional[float]], start: int,
                     horizons: Sequence[int] = HORIZONS) -> dict:
    """Forward returns from `closes[start]`.

    `closes` must already be aligned to the TRADING calendar (one entry per trading
    day, None where there is no clean price). Prices are never carried forward.
    Returns {"ret_5": x|None, ..., "skip_reason": str|None}.
    """
    out: dict = {f"ret_{h}": None for h in horizons}
    out["skip_reason"] = None
    p0 = closes[start] if 0 <= start < len(closes) else None
    if p0 is None or p0 <= 0:
        out["skip_reason"] = "no_start_price"
        return out
    # frozen price: identical to the 5-day price
    if start + 5 < len(closes) and closes[start + 5] is not None and closes[start + 5] == p0:
        out["skip_reason"] = "frozen_price"
        return out
    last = start
    for h in sorted(horizons):
        end = start + h
        if end >= len(closes):
            continue
        p1 = closes[end]
        if p1 is None or p1 <= 0:
            continue
        # one-day jump check across the path so far
        bad = False
        prev = p0
        for k in range(last + 1, end + 1):
            pk = closes[k]
            if pk is None or pk <= 0:
                continue
            if abs(pk / prev - 1.0) > MAX_ONE_DAY_JUMP:
                bad = True
                break
            prev = pk
        last = end
        ret = p1 / p0 - 1.0
        if bad or abs(ret) > MAX_HORIZON_RETURN:
            out["skip_reason"] = out["skip_reason"] or "data_error"
            continue
        out[f"ret_{h}"] = ret
    return out


def excess_return(ret: Optional[float], day_median_ret: Optional[float], side: str) -> Optional[float]:
    """Excess vs the day's MEDIAN stock, direction-adjusted: SELL flips the sign (a fall is good)."""
    if ret is None or day_median_ret is None:
        return None
    ex = ret - day_median_ret
    return -ex if side.upper() == "SELL" else ex


# ---- episodes --------------------------------------------------------------
def build_episodes(day_idx: Sequence[int], gap: int = EPISODE_GAP_DAYS) -> list[int]:
    """Episode number for each trading-day index of ONE stock holding ONE Final Call code.

    `day_idx` is sorted ascending. A gap of more than `gap` trading days starts a new episode.
    """
    ep, prev, out = 0, None, []
    for d in day_idx:
        if prev is not None and d - prev > gap:
            ep += 1
        out.append(ep)
        prev = d
    return out


# ---- weights ---------------------------------------------------------------
def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float, w: Optional[np.ndarray] = None) -> np.ndarray:
    """Weighted ridge. Intercept is fitted and NOT penalised. Returns coefficients (no intercept)."""
    n, k = X.shape
    w = np.ones(n) if w is None else w
    sw = w.sum()
    xm = (X * w[:, None]).sum(0) / sw
    ym = (y * w).sum() / sw
    Xc, yc = X - xm, y - ym
    A = (Xc * w[:, None]).T @ Xc + alpha * np.eye(k)
    b = (Xc * w[:, None]).T @ yc
    return np.linalg.solve(A, b)


def choose_alpha(X: np.ndarray, y: np.ndarray, order: np.ndarray,
                 alphas: Sequence[float] = (1.0, 10.0, 30.0, 100.0, 300.0)) -> float:
    """Pick the pull strength by fitting on the earlier half (by `order`) and scoring the later half."""
    idx = np.argsort(order)
    cut = len(idx) // 2
    tr, te = idx[:cut], idx[cut:]
    best, best_err = alphas[0], np.inf
    for a in alphas:
        beta = ridge_fit(X[tr], y[tr], a)
        pred = (X[te] - X[tr].mean(0)) @ beta + y[tr].mean()
        err = float(np.mean((y[te] - pred) ** 2))
        if err < best_err:
            best, best_err = a, err
    return best


def bootstrap_interval(X: np.ndarray, y: np.ndarray, stock_ids: np.ndarray, week_ids: np.ndarray,
                       alpha: float, reps: int = 500, seed: int = 7, level: float = 0.90):
    """90% range per coefficient. Resamples whole stocks AND whole calendar weeks (cluster bootstrap)."""
    rng = np.random.default_rng(seed)
    s_u, s_inv = np.unique(stock_ids, return_inverse=True)
    w_u, w_inv = np.unique(week_ids, return_inverse=True)
    betas = np.empty((reps, X.shape[1]))
    for r in range(reps):
        sc = np.bincount(rng.integers(0, len(s_u), len(s_u)), minlength=len(s_u))
        wc = np.bincount(rng.integers(0, len(w_u), len(w_u)), minlength=len(w_u))
        w = (sc[s_inv] * wc[w_inv]).astype(float)
        if w.sum() == 0:
            w = np.ones(len(y))
        betas[r] = ridge_fit(X, y, alpha, w)
    lo = np.quantile(betas, (1 - level) / 2, axis=0)
    hi = np.quantile(betas, 1 - (1 - level) / 2, axis=0)
    return lo, hi


def trust_flag(weight: float, lo: float, hi: float, n_episodes: int, n_stocks: int,
               w_early: Optional[float], w_late: Optional[float],
               contradicts_call: bool = False) -> str:
    """Plain-English flag for one factor/bucket row."""
    if n_episodes < MIN_EPISODES or n_stocks < MIN_STOCKS:
        return "Too few"
    if contradicts_call:
        return "Contradicts the call"
    if lo <= 0.0 <= hi:
        return "No effect"
    if w_early is None or w_late is None or np.sign(w_early) != np.sign(w_late) \
            or np.sign(w_early) != np.sign(weight):
        return "Unstable"
    return "Trust (helps)" if weight > 0 else "Trust (hurts)"


# ---- walk-forward test of a combined score ---------------------------------
def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def top_minus_bottom_fifth(pred: np.ndarray, actual: np.ndarray) -> float:
    n = len(pred)
    k = max(1, n // 5)
    order = np.argsort(pred)
    return float(actual[order[-k:]].mean() - actual[order[:k]].mean())


def walk_forward_pass(monthly: list[dict], min_months_ok: int = 4, last_n: int = 5,
                      reps: int = 500, seed: int = 11) -> dict:
    """Pass rule (DESIGN_SPEC_13 s.8).

    `monthly` = [{"pred": array, "actual": array}, ...] one entry per test month, oldest first.
    Pass when (1) rank correlation > 0 in at least `min_months_ok` of the last `last_n` months
    and (2) pooled top-fifth minus bottom-fifth has a 90% range above zero.
    """
    recent = monthly[-last_n:]
    corrs = [spearman(m["pred"], m["actual"]) for m in recent]
    n_ok = int(sum(1 for c in corrs if c == c and c > 0))
    enough_months = len(recent) >= min_months_ok
    pred = np.concatenate([m["pred"] for m in monthly]) if monthly else np.array([])
    act = np.concatenate([m["actual"] for m in monthly]) if monthly else np.array([])
    spread, lo = float("nan"), float("nan")
    if len(pred) >= 25:
        spread = top_minus_bottom_fifth(pred, act)
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(reps):
            i = rng.integers(0, len(pred), len(pred))
            boots.append(top_minus_bottom_fifth(pred[i], act[i]))
        lo = float(np.quantile(boots, 0.05))
    passed = bool(enough_months and n_ok >= min_months_ok and lo == lo and lo > 0)
    return {"passed": passed, "months_ok": n_ok, "months_tested": len(recent),
            "spread": spread, "spread_lo90": lo, "rank_corrs": corrs}
