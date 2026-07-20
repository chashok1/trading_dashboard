"""
TASK_128/129/130/131 — Calibrate the TOS BBTop/BBBottom ThinkScript bands
against the Hedgeye risk ranges published in hist_rr (buy_trade / sell_trade).

Builds a per-(snapshot_date, tos_symbol) calibration dataset for every ticker
that appears in BOTH hist_rr and hist_td, reports the current a_bb_top /
a_bb_bottom baseline error, grid-searches three small price/volatility-only
model families (A/B/C — TASK_128) plus a full price+volume+volatility model
(D — TASK_129, coordinate descent), then a 2-fold walk-forward-CV-gated
Family E adding inverse-VIX coupling, vol-level width, downside semi-dev,
directional volume (TASK_130) and a continuous PVV-style price/volume/vol-ROC
composite (TASK_131, replacing TASK_130's discrete classify_pvv label) for a
closer TOS-expressible fit, and prints the final report (chosen family,
params, ablation log, worst tickers, per-ticker overrides). See
docs/tos_rr_calibration.md for the narrative writeup.

Date alignment: hist_rr(D) is published pre-open using D-1's close, so every
feature here is anchored on the latest hist_td close STRICTLY BEFORE D
(pandas merge_asof direction='backward', allow_exact_matches=False) — the
same semantics as etl/derive.py::_derive_rr_impl's BB-fallback lateral join
(`hist_td.snapshot_date < :d`). Volume (hist_tl.volume) is joined onto the
same (tos_symbol, snapshot_date) anchor row, so it shares the identical
as-of-D alignment as the price/volatility features.

Scope: only symbols present in hist_td (equities/ETFs/indices on the TD tab)
can be calibrated — futures/FX/commodity tickers in hist_rr (e.g. /CL, /GC,
/BTC) have no hist_td close series and are excluded (they are also excluded
from the BB fallback in derive.py for the same reason). Volume (hist_tl) and
implied vol (hist_td.imp_volatility) are missing for indices (VIX, SPX,
N225:JP, ...) and some symbols; every volume/IV ratio here is NaN-guarded to
a neutral (1.0) multiplier so those symbols degrade gracefully instead of
being dropped.

Usage:
    python -m etl.calibrate_tos_rr                       # full grid + coordinate-descent search + report
    python -m etl.calibrate_tos_rr --start 2026-05-01     # restrict history
    python -m etl.calibrate_tos_rr --report               # rescore FITTED_TOP/FITTED_BOT (+ overrides) only (fast)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np      # noqa: E402
import pandas as pd     # noqa: E402
from sqlalchemy import text  # noqa: E402

from etl.db import session_scope     # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.calibrate_tos_rr")

# ---------------------------------------------------------------------------
# TASK_128 fitted params (Family A: classic Bollinger Band, mid = EMA(n),
# band = mid +/- k*StDev(n)). Kept as the price-only baseline / ablation
# checkpoint that TASK_129's Family D coordinate descent starts from.
# ---------------------------------------------------------------------------
FITTED_A = {
    "family": "A",       # classic BB: mid(n) +/- k * StDev(close, n)
    "mid": "ema",
    "n": 10,
    "k_top": 1.72,
    "k_bot": 1.86,
}

# ---------------------------------------------------------------------------
# TASK_129 fitted params (Family D: full price + volume + volatility model).
# Selected by fit_family_d()'s coordinate descent (see docs/
# tos_rr_calibration.md for the ablation table and selection process). These
# constants are hand-transcribed into TOS/BBTop.txt / BBBottom.txt as `input`
# defaults — keep them in sync.
#   mid'  = EMA(n) + c_t*RelVol(f,s)*(close-EMA(n)) + c_m*(EMA(mf)-EMA(ms))
#   sigma = w*StDev(close,n) + (1-w)*close*IV/15.87*sqrt(h)   [IV NaN -> w=1]
#   band  = mid' +/- k*(1+c_v*(RelVol(f,s)-1))*(1+c_iv*(IV/HV-1))*sigma
# ---------------------------------------------------------------------------
FITTED_TOP_D = {
    "family": "D", "n": 10, "fs": (3, 15), "mom_fs": (12, 26), "h": 3,
    "c_t": 0.25, "c_m": 0.5, "w": 0.75, "c_v": 0.0, "c_iv": -0.5, "k": 1.3,
}
FITTED_BOT_D = {
    "family": "D", "n": 10, "fs": (3, 15), "mom_fs": (5, 20), "h": 3,
    "c_t": 0.5, "c_m": 0.25, "w": 0.75, "c_v": -0.25, "c_iv": -0.25, "k": 1.42,
}

# --- TASK_130: VIX coupling + vol-level + semi-dev + directional-volume grids --
VIX_NV_LIST = [10, 15, 20]                     # VIX own EMA/StDev window (reuses N_LIST cols)
VIX_KV_GRID = [1.0, 1.5, 2.0]                  # VIX proxy-range width multiplier
M_LEVEL_LIST = [10, 20, 42]                    # vol-LEVEL rolling-avg window (lever B)
SEMI_N_LIST = [10, 15, 20]                     # downside semi-deviation window (lever C, BOTTOM only)
C_SD_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]        # semi-dev blend weight (0=pure StDev, 1=pure semi-dev)
W_DV_LIST = [10, 15, 20]                       # directional-volume averaging window (lever D)
FOLD_DAYS = 14                                  # each of the 2 walk-forward CV folds is 14 calendar days
FOLD_TOL = 0.02                                 # non-regression tolerance (median APE pp) for the fold gate
C_S_GRID = np.array([-1.0, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0])  # PVV-level mid-tilt coefficient (lever F1)
C_NARROW_GRID = np.array([0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0])  # bullish-low-vol width-narrow coeff (lever F2,
                                                                 # non-negative only -- this lever narrows, never widens
PVV_Z_WINDOW = 20          # rolling-std window for the price/volume/vol ROC z-scores (matches PVV's
                           # own 20d rolling-sigma convention, docs/pvv_logic.md)
PVV_Z_MIN_OBS = 10
PVV_Z_CLIP = 3.0           # z-score clamp (matches derive_pvv's outlier-resistance intent)
PVV_NARROW_FLOOR = 0.3     # width-narrow multiplier floor -- prevents the band collapsing to ~0

# ---------------------------------------------------------------------------
# TASK_130 fitted params (Family E: Family D + inverse-VIX coupling (A),
# vol-LEVEL width law (B), downside semi-deviation (C, BOTTOM only), and
# directional volume (D) -- see fit_family_e()'s 2-fold walk-forward-gated
# coordinate descent, warm-started from FITTED_TOP_D/FITTED_BOT_D. See
# docs/tos_rr_calibration.md TASK_130 section for the ablation table (both
# CV folds), fitted VIX-coupling signs, and per-asset-class notes. These
# constants are hand-transcribed into TOS/BBTop.txt / BBBottom.txt as
# `input` defaults -- keep them in sync.
#   mid'   = EMA(n) + c_t*RelVol(f,s)*(close-EMA(n)) + c_m*(EMA(mf)-EMA(ms))
#   sigmaR = (1-c_sd)*StDev(n) + c_sd*semidev(n_sd)*sqrt(2)   [c_sd=0 -> StDev(n)]
#   sigma  = w*sigmaR + (1-w)*close*IV/15.87*sqrt(h)          [IV NaN -> w=1]
#   mid'  += c_s*pvvLevel*sigma   (lever F1 -- continuous price/vol/vol-ROC composite, TASK_131)
#   width  = k*(1+c_v*(RelVol-1))*(1+c_iv*(IV/HV-1))*(1+c_lvl*(V/avg(V,m)-1))
#              *(1+c_dv*(dirVol-1))*(1-c_narrow*pvvNarrow) * sigma   (lever F2, TASK_131)
#   band   = mid' +/- width +/- c_vix*vixTerm*sigma   [+ for TOP, - for BOTTOM]
# ---------------------------------------------------------------------------
# TOP: none of levers A/B/C/D passed the 2-fold CV gate (each individually
# improved TRAIN but failed to generalize to both folds -- see
# docs/tos_rr_calibration.md) -- TOP stays IDENTICAL to Family D (TASK_129),
# satisfying the "must not regress TOP" requirement by construction.
FITTED_TOP = dict(FITTED_TOP_D, family="E", c_vix=0.0, nv=VIX_NV_LIST[0], kv=VIX_KV_GRID[0],
                   c_lvl=0.0, m_lvl=M_LEVEL_LIST[0], c_sd=0.0, n_sd=SEMI_N_LIST[0],
                   c_dv=0.0, w_dv=W_DV_LIST[0], c_s=0.0, c_narrow=0.0)
# BOTTOM: lever A (VIX coupling, nv=20/kv=1.0/c_vix=-0.5) and lever B
# (vol-level width, m=20/c_lvl=-0.25) both passed the 2-fold CV gate; C
# (semi-dev) and D (directional volume) did not generalize -- see
# docs/tos_rr_calibration.md for the full ablation (both CV folds) and an
# honest discussion of the fitted VIX/vol-level SIGNS (both came out
# opposite the naive economic-intuition direction; validated out-of-sample
# on this dataset, but flagged for monitoring).
FITTED_BOT = dict(FITTED_BOT_D, family="E", c_vix=-0.5, nv=20, kv=1.0,
                   c_lvl=-0.25, m_lvl=20, c_sd=0.0, n_sd=SEMI_N_LIST[0],
                   c_dv=0.0, w_dv=W_DV_LIST[0], c_s=0.0, c_narrow=0.0)
# Per-ticker k overrides (TASK_130 lowered bar to >=0.5pp gain, cap 8 symbols)
# -- fit_per_ticker_overrides() on the 8 worst Family-E tickers.
OVERRIDES: dict[str, dict[str, float]] = {
    "VIX": {"k_top": 1.44, "k_bot": 1.28},
    "ORCL": {"k_bot": 1.22},
    "NFLX": {"k_bot": 2.04},
}

N_LIST = [10, 15, 20, 21, 26]
K_GRID = np.round(np.arange(0.3, 4.01, 0.02), 2)
C_GRID = np.array([-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
HOLDOUT_DAYS = 14  # leave-last-2-weeks-out CV split

# --- TASK_129: volume + IV/HV feature grids -----------------------------------
FS_LIST = [(3, 15), (5, 20), (10, 30)]        # RelVol fast/slow window pairs
MOM_FS_LIST = [(5, 20), (8, 26), (12, 26)]    # price-momentum EMA fast/slow pairs
H_LIST = [3, 5, 10]                            # IV-implied-move horizon (days)
W_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]           # realized-vs-IV sigma blend weight


# --- data loading -----------------------------------------------------------

def _rr_reverse_scale(session) -> float:
    row = dict(session.execute(text(
        "SELECT setting_name, CAST(setting_value AS NUMERIC) FROM ref_settings "
        "WHERE setting_name = 'rr_reverse_scale'"
    )).fetchall())
    return float(row.get("rr_reverse_scale", 10))


def load_targets(session, start: date | None, end: date | None) -> pd.DataFrame:
    """hist_rr buy_trade/sell_trade, reverse-symbol-scaled to TOS display units."""
    rr_scale = _rr_reverse_scale(session)
    df = pd.read_sql(text("""
        SELECT rr.snapshot_date, rr.tos_symbol, rr.buy_trade, rr.sell_trade, rrt.reverse
        FROM hist_rr rr
        LEFT JOIN (
            SELECT DISTINCT ON (tos_ticker) tos_ticker, reverse
            FROM ref_rrt ORDER BY tos_ticker, loaded_at DESC
        ) rrt ON rrt.tos_ticker = rr.tos_symbol
        WHERE rr.tos_symbol IS NOT NULL
          AND rr.buy_trade IS NOT NULL AND rr.buy_trade <> 0
          AND rr.sell_trade IS NOT NULL AND rr.sell_trade <> 0
          AND (CAST(:start AS DATE) IS NULL OR rr.snapshot_date >= CAST(:start AS DATE))
          AND (CAST(:end AS DATE) IS NULL OR rr.snapshot_date <= CAST(:end AS DATE))
    """), session.bind, params={"start": start, "end": end})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    is_rev = df["reverse"] == "Y"
    df["buy_t"] = np.where(is_rev, df["buy_trade"] * rr_scale, df["buy_trade"])
    df["sell_t"] = np.where(is_rev, df["sell_trade"] * rr_scale, df["sell_trade"])
    return df


def load_td_series(session, symbols: list[str], end: date | None) -> pd.DataFrame:
    """Full EOD close/vol series (max sequence per day) for the given symbols."""
    if not symbols:
        return pd.DataFrame(columns=["tos_symbol", "snapshot_date", "close",
                                      "historical_vol", "imp_volatility",
                                      "a_bb_top", "a_bb_bottom"])
    df = pd.read_sql(text("""
        SELECT DISTINCT ON (tos_symbol, snapshot_date)
            tos_symbol, snapshot_date, last_price AS close,
            historical_vol, imp_volatility, a_bb_top, a_bb_bottom
        FROM hist_td
        WHERE tos_symbol = ANY(:syms)
          AND (CAST(:end AS DATE) IS NULL OR snapshot_date <= CAST(:end AS DATE))
        ORDER BY tos_symbol, snapshot_date, sequence DESC
    """), session.bind, params={"syms": symbols, "end": end})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df.sort_values(["tos_symbol", "snapshot_date"]).reset_index(drop=True)


def load_volume_series(session, symbols: list[str], end: date | None) -> pd.DataFrame:
    """EOD volume (max sequence per day) from hist_tl for the given symbols.
    Missing for futures/indices — left as NaN, neutralized downstream."""
    if not symbols:
        return pd.DataFrame(columns=["tos_symbol", "snapshot_date", "volume"])
    df = pd.read_sql(text("""
        SELECT DISTINCT ON (tos_symbol, snapshot_date)
            tos_symbol, snapshot_date, volume
        FROM hist_tl
        WHERE tos_symbol = ANY(:syms)
          AND (CAST(:end AS DATE) IS NULL OR snapshot_date <= CAST(:end AS DATE))
        ORDER BY tos_symbol, snapshot_date, sequence DESC
    """), session.bind, params={"syms": symbols, "end": end})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def load_and_merge(start: date | None, end: date | None) -> pd.DataFrame:
    """Full pipeline: targets + td + volume -> features -> anchor-merged frame."""
    with session_scope() as s:
        targets = load_targets(s, start, end)
        symbols = sorted(targets["tos_symbol"].unique().tolist())
        td = load_td_series(s, symbols, end)
        vol = load_volume_series(s, symbols, end)
    td = td.merge(vol, on=["tos_symbol", "snapshot_date"], how="left")
    feat = compute_features(td)
    merged = anchor_merge(targets, feat)
    vix_feat = extract_vix_feat(feat)
    return merge_vix(merged, vix_feat)


# --- feature engineering -----------------------------------------------------

def _clamp(x, lo: float = 0.5, hi: float = 2.0):
    return np.clip(x, lo, hi)


def compute_features(td: pd.DataFrame, n_list: list[int] = N_LIST,
                      fs_list: list[tuple[int, int]] = FS_LIST,
                      mom_list: list[tuple[int, int]] = MOM_FS_LIST,
                      h_list: list[int] = H_LIST) -> pd.DataFrame:
    """Rolling SMA/EMA/StDev(sample)/Highest/Lowest per symbol (price), RelVol
    fast/slow ratios + EMA momentum spreads (volume/price-momentum), IV/HV
    ratio + IV-implied move per horizon (volatility). All volume/IV ratios
    are clamped to [0.5, 2.0] and NaN-filled to a neutral 1.0 so symbols with
    no volume or IV history (indices, futures-adjacent tickers) degrade to
    the price/realized-vol-only terms instead of blowing up or being dropped."""
    g = td.groupby("tos_symbol")["close"]
    frames = [td[["tos_symbol", "snapshot_date", "close", "volume",
                   "historical_vol", "imp_volatility",
                   "a_bb_top", "a_bb_bottom"]]]
    std_by_n: dict[int, pd.Series] = {}
    for n in n_list:
        std_by_n[n] = g.transform(lambda x, n=n: x.rolling(n, min_periods=n).std(ddof=1))
        frames.append(pd.DataFrame({
            f"sma_{n}": g.transform(lambda x, n=n: x.rolling(n, min_periods=n).mean()),
            f"ema_{n}": g.transform(lambda x, n=n: x.ewm(span=n, adjust=False, min_periods=n).mean()),
            f"std_{n}": std_by_n[n],
            f"hi_{n}":  g.transform(lambda x, n=n: x.rolling(n, min_periods=n).max()),
            f"lo_{n}":  g.transform(lambda x, n=n: x.rolling(n, min_periods=n).min()),
        }))

    # volume leg: RelVol = Avg(vol,f)/Avg(vol,s), clamped + neutral-filled
    gv = td.groupby("tos_symbol")["volume"]
    for f, s in fs_list:
        vf = gv.transform(lambda x, f=f: x.rolling(f, min_periods=f).mean())
        vs = gv.transform(lambda x, s=s: x.rolling(s, min_periods=s).mean())
        rv = (vf / vs).replace([np.inf, -np.inf], np.nan)
        frames.append(pd.DataFrame({f"relvol_{f}_{s}": _clamp(rv.fillna(1.0))}))

    # price momentum: EMA(f) - EMA(s)
    for f, s in mom_list:
        ef = g.transform(lambda x, f=f: x.ewm(span=f, adjust=False, min_periods=f).mean())
        es = g.transform(lambda x, s=s: x.ewm(span=s, adjust=False, min_periods=s).mean())
        frames.append(pd.DataFrame({f"mom_{f}_{s}": (ef - es).fillna(0.0)}))

    # volatility leg: IV/HV ratio (neutral 1.0 when IV missing/zero HV) +
    # IV-implied per-horizon move (close*IV/sqrt(252), NaN when IV missing)
    ivhv = (td["imp_volatility"] / td["historical_vol"]).replace([np.inf, -np.inf], np.nan)
    frames.append(pd.DataFrame({"ivhv_ratio": _clamp(ivhv.fillna(1.0))}))
    for h in h_list:
        frames.append(pd.DataFrame({
            f"ivimp_{h}": td["close"] * td["imp_volatility"] / 15.87 * np.sqrt(h)
        }))

    # --- TASK_130 lever B: vol-LEVEL ratio (own imp_volatility, fallback
    # close-derived HV via std_10/close*Sqrt(252)) vs its own rolling average
    # over m -- level-dependent width law (high abs vol widens, low narrows),
    # distinct from the ratio-only ivhv_ratio term above. -----------------------
    std10 = std_by_n.get(10, next(iter(std_by_n.values())))
    hv_fallback = std10 / td["close"] * np.sqrt(252)
    vlevel_raw = td["imp_volatility"].fillna(hv_fallback)
    gvl = vlevel_raw.groupby(td["tos_symbol"])
    for m in M_LEVEL_LIST:
        avg_m = gvl.transform(lambda x, m=m: x.rolling(m, min_periods=m).mean())
        ratio = (vlevel_raw / avg_m).replace([np.inf, -np.inf], np.nan)
        frames.append(pd.DataFrame({f"vlevel_{m}": _clamp(ratio.fillna(1.0))}))

    # --- TASK_130 lever C: downside semi-deviation -- sqrt(rolling mean of
    # Min(0, close-close[1])^2) over n -- targets the asymmetry Hedgeye bakes
    # into buy_trade (BOTTOM band only). Fallback: std_n of the matching
    # window when too little history (neutral -- no asymmetry signal yet). ----
    diff = g.transform(lambda x: x.diff())
    negdiff = diff.clip(upper=0.0)
    gnd = negdiff.groupby(td["tos_symbol"])
    for n in SEMI_N_LIST:
        semi = np.sqrt(gnd.transform(lambda x, n=n: (x ** 2).rolling(n, min_periods=n).mean()))
        std_fallback = std_by_n.get(n)
        semi = semi if std_fallback is None else semi.fillna(std_fallback)
        frames.append(pd.DataFrame({f"semidev_{n}": semi}))

    # --- TASK_130 lever D: directional volume -- up-day vs down-day average
    # volume over trailing w. dnup = down/up (BOTTOM tilt: down-vol dominance
    # pulls the band lower); updn = up/down (TOP tilt: up-vol dominance pushes
    # the band higher). Both clamped [0.5,2.0], neutral-filled to 1.0. --------
    is_up = (diff > 0).astype(float)
    is_down = (diff < 0).astype(float)
    up_vol = td["volume"] * is_up
    down_vol = td["volume"] * is_down
    g_upvol, g_downvol = up_vol.groupby(td["tos_symbol"]), down_vol.groupby(td["tos_symbol"])
    g_isup, g_isdown = is_up.groupby(td["tos_symbol"]), is_down.groupby(td["tos_symbol"])
    for w in W_DV_LIST:
        up_avg = (g_upvol.transform(lambda x, w=w: x.rolling(w, min_periods=w).sum())
                  / g_isup.transform(lambda x, w=w: x.rolling(w, min_periods=w).sum()).replace(0, np.nan))
        dn_avg = (g_downvol.transform(lambda x, w=w: x.rolling(w, min_periods=w).sum())
                  / g_isdown.transform(lambda x, w=w: x.rolling(w, min_periods=w).sum()).replace(0, np.nan))
        dnup = (dn_avg / up_avg).replace([np.inf, -np.inf], np.nan)
        updn = (up_avg / dn_avg).replace([np.inf, -np.inf], np.nan)
        frames.append(pd.DataFrame({f"dnup_{w}": _clamp(dnup.fillna(1.0)),
                                     f"updn_{w}": _clamp(updn.fillna(1.0))}))

    # --- TASK_131 lever F (replaces TASK_130's discrete classify_pvv label):
    # continuous price-ROC x volume-ROC/volatility-ROC composite. Each leg is
    # z-scored against its own trailing rolling sigma (same 20d window as
    # before; volume ROC baseline still matches PVV's 20d avg EOD volume, IV
    # ROC still falls back to historical_vol) instead of being discretized
    # to up/down/flat -- a continuous signal carries more information than
    # the 8-bucket classify_pvv() label for a coordinate-descent fit. Two
    # derived features:
    #   pvv_level  (signed, mid-tilt, lever F1) = price z-score, amplified
    #     when volume is elevated (confirms whichever direction price is
    #     already moving) and damped when IV/HV is rising (less trust in a
    #     vol-expanding regime).
    #   pvv_narrow (>=0, width-narrow, lever F2) = bullish-AND-volume-
    #     confirmed-AND-vol-contracting strength (product of three clamped
    #     fractions -- an AND-gate, zero unless all three align), applied as
    #     a width multiplier that can only narrow the band (see C_NARROW_GRID
    #     / PVV_NARROW_FLOOR), never widen it -- targets the user's stated
    #     "bullish-low-vol confirmation narrows the range" observation. -----
    p_roc = g.transform(lambda x: x.pct_change())
    p_roc_std = p_roc.groupby(td["tos_symbol"]).transform(
        lambda x: x.rolling(PVV_Z_WINDOW, min_periods=PVV_Z_MIN_OBS).std())
    vol_avg20 = gv.transform(lambda x: x.rolling(20, min_periods=10).mean())
    v_roc = (td["volume"] / vol_avg20 - 1).replace([np.inf, -np.inf], np.nan)
    v_roc_std = v_roc.groupby(td["tos_symbol"]).transform(
        lambda x: x.rolling(PVV_Z_WINDOW, min_periods=PVV_Z_MIN_OBS).std())
    ivsrc = td["imp_volatility"].fillna(td["historical_vol"])
    vol_roc = ivsrc.groupby(td["tos_symbol"]).transform(lambda x: x.pct_change())
    vol_roc_std = vol_roc.groupby(td["tos_symbol"]).transform(
        lambda x: x.rolling(PVV_Z_WINDOW, min_periods=PVV_Z_MIN_OBS).std())
    p_z = _zscore(p_roc, p_roc_std)
    v_z = _zscore(v_roc, v_roc_std)
    vol_z = _zscore(vol_roc, vol_roc_std)

    confirm_mult = np.clip(1 + 0.3 * v_z, 0.4, 1.6)
    vol_damp = 1 + 0.3 * np.clip(vol_z, 0, PVV_Z_CLIP)
    pvv_level = np.clip(p_z * confirm_mult / vol_damp, -PVV_Z_CLIP, PVV_Z_CLIP)

    bull = np.clip(p_z, 0, PVV_Z_CLIP) / PVV_Z_CLIP
    vconf = np.clip(v_z, 0, PVV_Z_CLIP) / PVV_Z_CLIP
    lowvol = np.clip(-vol_z, 0, PVV_Z_CLIP) / PVV_Z_CLIP
    pvv_narrow = bull * vconf * lowvol

    frames.append(pd.DataFrame({"pvv_level": pvv_level, "pvv_narrow": pvv_narrow}))

    return pd.concat(frames, axis=1)


def _zscore(roc: pd.Series, std: pd.Series, clip: float = PVV_Z_CLIP) -> pd.Series:
    """ROC / its own trailing rolling sigma, clamped +/-clip, 0 when the ROC
    or sigma is unavailable (insufficient history, zero sigma) -- the
    continuous analogue of derive_pvv._direction()'s flat-band threshold."""
    z = (roc / std).replace([np.inf, -np.inf], np.nan)
    return z.clip(-clip, clip).fillna(0.0)


def extract_vix_feat(feat: pd.DataFrame, n_list: list[int] = N_LIST) -> pd.DataFrame:
    """VIX's own close + ema_n/std_n columns (already computed by
    compute_features for every symbol incl. VIX), renamed + isolated for the
    cross-symbol (inverse) coupling merge in merge_vix()."""
    cols = {"snapshot_date": "snapshot_date", "close": "vix_close"}
    cols.update({f"ema_{n}": f"vix_ema_{n}" for n in n_list})
    cols.update({f"std_{n}": f"vix_std_{n}" for n in n_list})
    vix = feat[feat["tos_symbol"] == "VIX"][list(cols.keys())].rename(columns=cols)
    return vix.sort_values("snapshot_date").reset_index(drop=True)


def merge_vix(merged: pd.DataFrame, vix_feat: pd.DataFrame) -> pd.DataFrame:
    """Attach VIX's anchor-aligned close/ema/std to every row (any symbol,
    any date) via a date-only backward asof merge -- same 'strictly before D'
    semantics as the primary per-symbol anchor, so the VIX term is read off
    the same information set the equity's own features use. Returns a frame
    re-sorted by snapshot_date (merge_asof requirement) with a fresh index --
    callers must use the returned frame from this point on, not positionally
    align it against the pre-merge `merged`."""
    if vix_feat.empty:
        out = merged.sort_values("snapshot_date").reset_index(drop=True).copy()
        out["vix_close"] = np.nan
        return out
    return pd.merge_asof(merged.sort_values("snapshot_date").reset_index(drop=True), vix_feat,
                          on="snapshot_date", direction="backward",
                          allow_exact_matches=False)


def anchor_merge(targets: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
    """Align each hist_rr row at D to the latest feature row strictly before D
    (matches derive.py's `hist_td.snapshot_date < :d` BB-fallback lateral)."""
    t = targets.sort_values("snapshot_date").reset_index(drop=True)
    f = feat.sort_values("snapshot_date").reset_index(drop=True)
    merged = pd.merge_asof(t, f, by="tos_symbol", on="snapshot_date",
                            direction="backward", allow_exact_matches=False)
    need = ["close", "a_bb_top", "a_bb_bottom"] + [
        f"{p}_{n}" for p in ("sma", "ema", "std", "hi", "lo") for n in N_LIST
    ]
    return merged.dropna(subset=need).reset_index(drop=True)


# --- metrics -----------------------------------------------------------------

def _ape(pred, actual) -> pd.Series:
    return (pred - actual).abs() / actual * 100


def _metrics(pred, actual) -> tuple[float, float, int]:
    ape = _ape(pred, actual)
    return float(ape.median()), float((ape <= 2).mean() * 100), int(len(ape))


def baseline_report(merged: pd.DataFrame) -> None:
    top_med, top_pct, n = _metrics(merged["a_bb_top"], merged["sell_t"])
    bot_med, bot_pct, _ = _metrics(merged["a_bb_bottom"], merged["buy_t"])
    width_ratio = ((merged["a_bb_top"] - merged["a_bb_bottom"])
                   / (merged["sell_t"] - merged["buy_t"])).median()
    mid_off = (((merged["a_bb_top"] + merged["a_bb_bottom"]) / 2
                - (merged["sell_t"] + merged["buy_t"]) / 2)
               / ((merged["sell_t"] + merged["buy_t"]) / 2) * 100).median()
    print(f"\n=== BASELINE (current a_bb_top/a_bb_bottom) n={n} ===")
    print(f"  TOP    median APE={top_med:.3f}%  pct<=2%={top_pct:.1f}%")
    print(f"  BOTTOM median APE={bot_med:.3f}%  pct<=2%={bot_pct:.1f}%")
    print(f"  width ratio (BB/RR) median={width_ratio:.3f}   mid offset median={mid_off:.3f}%")


def worst_tickers(merged: pd.DataFrame, pred_top, pred_bot, k=5) -> pd.DataFrame:
    m = merged.copy()
    m["ape_top"] = _ape(pred_top, m["sell_t"])
    m["ape_bot"] = _ape(pred_bot, m["buy_t"])
    by = m.groupby("tos_symbol").agg(
        n=("ape_top", "size"), med_top=("ape_top", "median"), med_bot=("ape_bot", "median"),
    )
    by["worst"] = by[["med_top", "med_bot"]].max(axis=1)
    return by.sort_values("worst", ascending=False).head(k)


# --- grid search: family A (classic BB) --------------------------------------

def _grid_A(df, mid_kind, n, target_col, sign, k_grid=K_GRID):
    mid = df[f"{mid_kind}_{n}"].to_numpy()
    std = df[f"std_{n}"].to_numpy()
    actual = df[target_col].to_numpy()
    pred = mid[:, None] + sign * k_grid[None, :] * std[:, None]
    ape = np.abs(pred - actual[:, None]) / actual[:, None] * 100
    med = np.median(ape, axis=0)
    pct2 = (ape <= 2).mean(axis=0) * 100
    j = np.lexsort((med, -pct2))[0]
    return float(k_grid[j]), float(med[j]), float(pct2[j])


def grid_search_family_a(df, target_col, sign, n_list=N_LIST):
    """Family A: mid(n) +/- k*StDev(n), mid in {sma, ema}. Returns best-first list
    of (mid, n, k, median_ape, pct_within_2)."""
    out = []
    for mid_kind in ("sma", "ema"):
        for n in n_list:
            k, med, pct2 = _grid_A(df, mid_kind, n, target_col, sign)
            out.append((mid_kind, n, k, med, pct2))
    out.sort(key=lambda r: (-r[4], r[3]))
    return out


# --- grid search: family B (Donchian blend) ----------------------------------

def _grid_B(df, n_don, m_std, target_col, sign, k_grid=None):
    k_grid = k_grid if k_grid is not None else np.round(np.arange(0.1, 2.51, 0.05), 2)
    donmid = ((df[f"hi_{n_don}"] + df[f"lo_{n_don}"]) / 2).to_numpy()
    std = df[f"std_{m_std}"].to_numpy()
    actual = df[target_col].to_numpy()
    pred = donmid[:, None] + sign * k_grid[None, :] * std[:, None]
    ape = np.abs(pred - actual[:, None]) / actual[:, None] * 100
    med = np.median(ape, axis=0)
    pct2 = (ape <= 2).mean(axis=0) * 100
    j = np.lexsort((med, -pct2))[0]
    return float(k_grid[j]), float(med[j]), float(pct2[j])


def grid_search_family_b(df, target_col, sign, n_list=N_LIST):
    """Family B: midpoint(Highest/Lowest(n)) +/- k*StDev(m). Returns best-first
    list of (n_don, m_std, k, median_ape, pct_within_2)."""
    out = []
    for n_don in n_list:
        for m_std in n_list:
            k, med, pct2 = _grid_B(df, n_don, m_std, target_col, sign)
            out.append((n_don, m_std, k, med, pct2))
    out.sort(key=lambda r: (-r[4], r[3]))
    return out


# --- grid search: family C (vol-scaled classic BB) ---------------------------

def _iv_term(df, c):
    ratio = (df["imp_volatility"] / df["historical_vol"]).replace([np.inf, -np.inf], np.nan)
    return (1 + c * (ratio - 1)).fillna(1.0).to_numpy()


def _grid_C(df, mid_kind, n, target_col, sign, k_grid=K_GRID, c_grid=C_GRID):
    mid = df[f"{mid_kind}_{n}"].to_numpy()
    std = df[f"std_{n}"].to_numpy()
    actual = df[target_col].to_numpy()
    best = None
    for c in c_grid:
        term = _iv_term(df, c)
        eff = term[:, None] * k_grid[None, :]
        pred = mid[:, None] + sign * eff * std[:, None]
        ape = np.abs(pred - actual[:, None]) / actual[:, None] * 100
        med = np.median(ape, axis=0)
        pct2 = (ape <= 2).mean(axis=0) * 100
        j = np.lexsort((med, -pct2))[0]
        cand = (float(c), float(k_grid[j]), float(med[j]), float(pct2[j]))
        if best is None or (cand[3], -cand[2]) > (best[3], -best[2]):
            best = cand
    return best  # (c, k, median_ape, pct_within_2)


def grid_search_family_c(df, target_col, sign, n_list=N_LIST):
    """Family C: k*(1 + c*(iv/hv - 1)) * StDev(n), applied to mid(n). IV NaN ->
    term=1. Returns best-first list of (mid, n, c, k, median_ape, pct_within_2)."""
    out = []
    for mid_kind in ("sma", "ema"):
        for n in n_list:
            c, k, med, pct2 = _grid_C(df, mid_kind, n, target_col, sign)
            out.append((mid_kind, n, c, k, med, pct2))
    out.sort(key=lambda r: (-r[5], r[4]))
    return out


# --- family D (TASK_129): full price + volume + volatility model -------------

def predict_full(df: pd.DataFrame, p: dict, sign: int) -> pd.Series:
    """Family D prediction.
    mid'  = EMA(n) + c_t*RelVol(f,s)*(close-EMA(n)) + c_m*(EMA(mf)-EMA(ms))
    sigma = w*StDev(close,n) + (1-w)*close*IV/15.87*sqrt(h)  [IV NaN -> w=1 for that row]
    band  = mid' + sign * k*(1+c_v*(RelVol(f,s)-1))*(1+c_iv*(IV/HV-1))*sigma
    """
    n, (f, s), (mf, ms), h = p["n"], p["fs"], p["mom_fs"], p["h"]
    mid = df[f"ema_{n}"]
    close = df["close"]
    relvol = df[f"relvol_{f}_{s}"]
    mom = df[f"mom_{mf}_{ms}"]
    mid_p = mid + p["c_t"] * relvol * (close - mid) + p["c_m"] * mom

    ivimp = df[f"ivimp_{h}"]
    w_eff = np.where(ivimp.isna(), 1.0, p["w"])
    sigma = w_eff * df[f"std_{n}"] + (1 - w_eff) * ivimp.fillna(0.0)

    vol_mult = _clamp(1 + p["c_v"] * (relvol - 1))
    ivhv_mult = _clamp(1 + p["c_iv"] * (df["ivhv_ratio"] - 1))
    return mid_p + sign * p["k"] * vol_mult * ivhv_mult * sigma


def _better(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """a, b = (pct<=2%, median_ape). True if a beats b (higher pct2, tie-break
    lower median)."""
    return (a[0], -a[1]) > (b[0], -b[1])


def fit_family_d(train: pd.DataFrame, target_col: str, sign: int,
                  base_n: int, base_k: float, init: dict | None = None,
                  step_prefix: str = "") -> tuple[dict, list]:
    """Coordinate-descent fit of the full PVV model (Family D) for one band.
    Starts from Family A's (n, k) price/volatility backbone (or `init`, for a
    warm-started second refinement pass), adds volume tilt, momentum tilt,
    IV-blended sigma, and volume/IV width multipliers one leg at a time —
    keeping each addition only if it improves the train (pct<=2%, median
    APE) score — then a local joint refinement pass. If both volume
    coefficients (c_t, c_v) land at 0, forces the least-cost non-zero c_v so
    the shipped formula always has an active volume term (spec requirement
    1). Returns (final params, ablation log)."""
    p = dict(init) if init is not None else dict(
        n=base_n, fs=FS_LIST[1], mom_fs=MOM_FS_LIST[0], h=H_LIST[1],
        c_t=0.0, c_m=0.0, w=1.0, c_v=0.0, c_iv=0.0, k=base_k)
    log: list = []

    def score(pp: dict) -> tuple[float, float]:
        pred = predict_full(train, pp, sign)
        med, pct2, _ = _metrics(pred, train[target_col])
        return (pct2, med)

    def record(step: str) -> None:
        pct2, med = score(p)
        log.append((step_prefix + step, med, pct2, dict(p)))

    record("0 P-only backbone (Family A carryover)" if init is None
           else "R2-0 warm-started from round-1 optimum")

    # step 1: volume tilt on midpoint
    best = (score(p), p["fs"], p["c_t"])
    for fs in FS_LIST:
        for c_t in C_GRID:
            cand = dict(p, fs=fs, c_t=float(c_t))
            s = score(cand)
            if _better(s, best[0]):
                best = (s, fs, float(c_t))
    if _better(best[0], score(p)):
        p["fs"], p["c_t"] = best[1], best[2]
    record("1 +volume tilt: c_t*RelVol*(close-mid)")

    # step 2: momentum tilt
    best = (score(p), p["mom_fs"], p["c_m"])
    for mfs in MOM_FS_LIST:
        for c_m in C_GRID:
            cand = dict(p, mom_fs=mfs, c_m=float(c_m))
            s = score(cand)
            if _better(s, best[0]):
                best = (s, mfs, float(c_m))
    if _better(best[0], score(p)):
        p["mom_fs"], p["c_m"] = best[1], best[2]
    record("2 +momentum tilt: c_m*(EMA_f-EMA_s)")

    # step 3: realized/IV sigma blend
    best = (score(p), p["h"], p["w"])
    for h in H_LIST:
        for w in W_GRID:
            cand = dict(p, h=h, w=w)
            s = score(cand)
            if _better(s, best[0]):
                best = (s, h, w)
    if _better(best[0], score(p)):
        p["h"], p["w"] = best[1], best[2]
    record("3 +IV-blended sigma: w*StDev + (1-w)*IV-implied")

    # step 4: width volume multiplier
    best = (score(p), p["c_v"])
    for c_v in C_GRID:
        cand = dict(p, c_v=float(c_v))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(c_v))
    if _better(best[0], score(p)):
        p["c_v"] = best[1]
    record("4 +width volume mult: 1+c_v*(RelVol-1)")

    # step 5: width IV/HV multiplier
    best = (score(p), p["c_iv"])
    for c_iv in C_GRID:
        cand = dict(p, c_iv=float(c_iv))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(c_iv))
    if _better(best[0], score(p)):
        p["c_iv"] = best[1]
    record("5 +width IV/HV mult: 1+c_iv*(IV/HV-1)")

    # step 6: re-fit k with all legs active
    best = (score(p), p["k"])
    for k in K_GRID:
        cand = dict(p, k=float(k))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(k))
    p["k"] = best[1]
    record("6 re-fit k (all legs active)")

    # step 7: local joint refinement — re-sweep n, then re-fit c_t/c_v/k
    best = (score(p), p["n"])
    for n in N_LIST:
        cand = dict(p, n=n)
        s = score(cand)
        if _better(s, best[0]):
            best = (s, n)
    if _better(best[0], score(p)):
        p["n"] = best[1]
    record("7a local refine: re-sweep n")

    best = (score(p), p["c_t"])
    for c_t in C_GRID:
        cand = dict(p, c_t=float(c_t))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(c_t))
    if _better(best[0], score(p)):
        p["c_t"] = best[1]
    record("7b local refine: re-fit c_t")

    best = (score(p), p["c_v"])
    for c_v in C_GRID:
        cand = dict(p, c_v=float(c_v))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(c_v))
    if _better(best[0], score(p)):
        p["c_v"] = best[1]
    record("7c local refine: re-fit c_v")

    best = (score(p), p["k"])
    for k in K_GRID:
        cand = dict(p, k=float(k))
        s = score(cand)
        if _better(s, best[0]):
            best = (s, float(k))
    p["k"] = best[1]
    record("7d local refine: re-fit k")

    # requirement 1: volume leg must be active in the final formula — if the
    # coordinate descent zeroed both volume coefficients, force the
    # least-cost non-zero width-volume multiplier instead of dropping the leg.
    if p["c_t"] == 0.0 and p["c_v"] == 0.0:
        best_nz = None
        for c_v in C_GRID[C_GRID != 0.0]:
            cand = dict(p, c_v=float(c_v))
            s = score(cand)
            if best_nz is None or _better(s, best_nz[0]):
                best_nz = (s, float(c_v))
        p["c_v"] = best_nz[1]
        record("8 forced non-zero volume term (req. 1)")
        best = (score(p), p["k"])
        for k in K_GRID:
            cand = dict(p, k=float(k))
            s = score(cand)
            if _better(s, best[0]):
                best = (s, float(k))
        p["k"] = best[1]
        record("9 re-fit k after forced volume term")

    return p, log


# --- family E (TASK_130): + inverse-VIX coupling + vol-level + semi-dev + ----
# --- directional volume, warm-started from Family D, 2-fold-CV-gated --------

def _vix_term(df: pd.DataFrame, nv: int, kv: float, sign: int) -> pd.Series:
    """Inverse-VIX coupling term (lever A): TOP uses VIX's downside room
    (close/vixBot - 1), BOTTOM uses VIX's upside room (vixTop/close - 1) --
    per the user's stated inversion rule (VIX range top -> equity bottom,
    VIX range bottom -> equity top). Neutral (0) when this row's own VIX
    close is missing for the anchor date, or for VIX's own rows (coupling a
    symbol to itself is meaningless -- the ThinkScript equivalent is a
    GetSymbol()=="VIX" guard)."""
    vix_close = df["vix_close"]
    ema, std = df[f"vix_ema_{nv}"], df[f"vix_std_{nv}"]
    if sign > 0:
        term = vix_close / (ema - kv * std) - 1
    else:
        term = (ema + kv * std) / vix_close - 1
    neutral = vix_close.isna() | (df["tos_symbol"] == "VIX")
    return term.where(~neutral, 0.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def predict_full_v2(df: pd.DataFrame, p: dict, sign: int) -> pd.Series:
    """Family E (TASK_130) prediction -- Family D's mid'/sigma backbone plus
    lever A (inverse VIX coupling, additive), lever B (vol-LEVEL width
    multiplier), lever C (downside semi-dev blended into sigma, BOTTOM band
    only -- c_sd stays 0 for TOP), lever D (directional-volume width
    multiplier, down/up-tilted for BOTTOM vs up/down-tilted for TOP), lever F
    (PVV-style signed tape skew, additive midpoint tilt). See FITTED_TOP/
    FITTED_BOT's docstring above for the formula."""
    n, (f, s), (mf, ms), h = p["n"], p["fs"], p["mom_fs"], p["h"]
    mid = df[f"ema_{n}"]
    close = df["close"]
    relvol = df[f"relvol_{f}_{s}"]
    mom = df[f"mom_{mf}_{ms}"]
    mid_p = mid + p["c_t"] * relvol * (close - mid) + p["c_m"] * mom

    c_sd = p.get("c_sd", 0.0)
    if c_sd == 0.0:
        sigma_r = df[f"std_{n}"]
    else:
        sigma_r = (1 - c_sd) * df[f"std_{n}"] + c_sd * df[f"semidev_{p['n_sd']}"] * np.sqrt(2)

    ivimp = df[f"ivimp_{h}"]
    w_eff = np.where(ivimp.isna(), 1.0, p["w"])
    sigma = w_eff * sigma_r + (1 - w_eff) * ivimp.fillna(0.0)

    # lever F1 (TASK_131): continuous PVV-style price/volume/vol-ROC
    # composite, sigma-scaled additive mid tilt (shifts both band edges
    # together -- "level" tilt, same mechanism as TASK_130's discrete skew).
    mid_p = mid_p + p.get("c_s", 0.0) * df["pvv_level"] * sigma

    vol_mult = _clamp(1 + p["c_v"] * (relvol - 1))
    ivhv_mult = _clamp(1 + p["c_iv"] * (df["ivhv_ratio"] - 1))
    vlevel_mult = _clamp(1 + p.get("c_lvl", 0.0)
                          * (df[f"vlevel_{p.get('m_lvl', M_LEVEL_LIST[0])}"] - 1))
    dv_col = (f"dnup_{p.get('w_dv', W_DV_LIST[0])}" if sign < 0
              else f"updn_{p.get('w_dv', W_DV_LIST[0])}")
    dv_mult = _clamp(1 + p.get("c_dv", 0.0) * (df[dv_col] - 1))
    # lever F2 (TASK_131): bullish-low-vol-confirmed width narrow -- c_narrow
    # is grid-searched non-negative only (C_NARROW_GRID), so this multiplier
    # can only shrink width, never grow it; floored so the band can't collapse.
    narrow_mult = np.clip(1 - p.get("c_narrow", 0.0) * df["pvv_narrow"], PVV_NARROW_FLOOR, 1.0)

    width = p["k"] * vol_mult * ivhv_mult * vlevel_mult * dv_mult * narrow_mult * sigma
    vix_term = _vix_term(df, p.get("nv", VIX_NV_LIST[0]), p.get("kv", VIX_KV_GRID[0]), sign)
    return mid_p + sign * width + sign * p.get("c_vix", 0.0) * vix_term * sigma


def _split_folds(merged: pd.DataFrame, fold_days: int = FOLD_DAYS):
    """2-fold walk-forward CV split (TASK_130 guardrail): TRAIN = data older
    than both folds; FOLD1 = the fold_days window immediately preceding the
    most recent fold_days; FOLD2 = the most recent fold_days (== TASK_129's
    held-out TEST window). Each lever is fit once on TRAIN and must not
    regress either fold -- see _fold_gate()."""
    max_d = merged["snapshot_date"].max()
    f2_start = max_d - pd.Timedelta(days=fold_days)
    f1_start = max_d - pd.Timedelta(days=2 * fold_days)
    train = merged[merged["snapshot_date"] <= f1_start]
    fold1 = merged[(merged["snapshot_date"] > f1_start) & (merged["snapshot_date"] <= f2_start)]
    fold2 = merged[merged["snapshot_date"] > f2_start]
    return train, fold1, fold2


def _fold_gate(cand_p: dict, cur_p: dict, predict_fn, target_col: str, sign: int,
               train: pd.DataFrame, fold1: pd.DataFrame, fold2: pd.DataFrame,
               tol: float = FOLD_TOL) -> bool:
    """TASK_130 overfitting guardrail: accept a candidate params dict only if
    (1) it actually improves TRAIN median APE, (2) it does not regress
    median APE by more than `tol` percentage points on EITHER CV fold, and
    (3) the fold-to-fold gain spread does not exceed ~2x the train gain
    (memorization signature) -- a lever is kept only if it helps on both
    folds, not just one."""
    def med(df, p):
        return _metrics(predict_fn(df, p, sign), df[target_col])[0]
    train_gain = med(train, cur_p) - med(train, cand_p)
    if train_gain <= 0:
        return False
    f1_gain = med(fold1, cur_p) - med(fold1, cand_p)
    f2_gain = med(fold2, cur_p) - med(fold2, cand_p)
    if f1_gain < -tol or f2_gain < -tol:
        return False
    return abs(f1_gain - f2_gain) <= 2 * train_gain


def fit_family_e(train: pd.DataFrame, fold1: pd.DataFrame, fold2: pd.DataFrame,
                  target_col: str, sign: int, init: dict, is_bottom: bool,
                  step_prefix: str = "") -> tuple[dict, list]:
    """Coordinate-descent fit of Family E (TASK_130/131) for one band, warm-
    started from Family D's (TASK_129) fitted params (`init`). Adds levers
    A (inverse VIX coupling), B (vol-level width), C (downside semi-dev,
    BOTTOM only), D (directional volume), F1 (continuous PVV-style mid
    tilt), F2 (bullish-low-vol width narrow, TASK_131) one at a time, then a
    local k refinement -- each step gated by _fold_gate() (2-fold
    walk-forward CV): a lever is only kept if it improves TRAIN and does not
    regress either fold beyond a small tolerance, with fold-spread capped
    at 2x the train gain. Returns (final params, ablation log) where each
    log row is (step, train_med, train_pct2, f1_med, f1_pct2, f2_med,
    f2_pct2, params)."""
    p = dict(init, c_vix=0.0, nv=VIX_NV_LIST[0], kv=VIX_KV_GRID[0],
              c_lvl=0.0, m_lvl=M_LEVEL_LIST[0],
              c_sd=0.0, n_sd=SEMI_N_LIST[0],
              c_dv=0.0, w_dv=W_DV_LIST[0], c_s=0.0, c_narrow=0.0)
    log: list = []

    def score(pp, df):
        pred = predict_full_v2(df, pp, sign)
        med, pct2, _ = _metrics(pred, df[target_col])
        return (pct2, med)

    def record(step):
        t_pct2, t_med = score(p, train)
        f1_pct2, f1_med = score(p, fold1)
        f2_pct2, f2_med = score(p, fold2)
        log.append((step_prefix + step, t_med, t_pct2, f1_med, f1_pct2, f2_med, f2_pct2, dict(p)))

    record("0 warm start (Family D optimum)")

    def _try_step(label: str, grid_fn) -> None:
        """Pick the TRAIN-best candidate AMONG those that already pass the
        2-fold CV gate (not: pick the train-best candidate, then gate-check
        only that one) -- otherwise a train-optimal-but-overfit candidate can
        mask a nearby candidate that both improves train and generalizes."""
        nonlocal p
        best = None  # (train_score, cand)
        for cand in grid_fn():
            if not _fold_gate(cand, p, predict_full_v2, target_col, sign, train, fold1, fold2):
                continue
            s = score(cand, train)
            if best is None or _better(s, best[0]):
                best = (s, cand)
        if best is not None:
            p = best[1]
            record(f"{label} accepted")
        else:
            record(f"{label} rejected (no candidate passed the fold gate)")

    _try_step("A +inverse VIX coupling",
               lambda: (dict(p, nv=nv, kv=kv, c_vix=float(c_vix))
                        for nv in VIX_NV_LIST for kv in VIX_KV_GRID for c_vix in C_GRID))
    _try_step("B +vol-level width mult",
               lambda: (dict(p, m_lvl=m, c_lvl=float(c_lvl))
                        for m in M_LEVEL_LIST for c_lvl in C_GRID))
    if is_bottom:
        _try_step("C +downside semi-dev (BOTTOM only)",
                   lambda: (dict(p, n_sd=n_sd, c_sd=float(c_sd))
                            for n_sd in SEMI_N_LIST for c_sd in C_SD_GRID))
    _try_step("D +directional volume width mult",
               lambda: (dict(p, w_dv=w, c_dv=float(c_dv))
                        for w in W_DV_LIST for c_dv in C_GRID))
    _try_step("F1 +PVV composite mid-tilt (continuous)",
               lambda: (dict(p, c_s=float(c_s)) for c_s in C_S_GRID))
    _try_step("F2 +PVV bullish-low-vol width narrow",
               lambda: (dict(p, c_narrow=float(c_narrow)) for c_narrow in C_NARROW_GRID))
    _try_step("G re-fit k (all accepted legs active)",
               lambda: (dict(p, k=float(k)) for k in K_GRID))

    return p, log


def predict_full_overridden(df: pd.DataFrame, base_p: dict, sign: int,
                             overrides: dict, predict_fn=predict_full) -> pd.Series:
    """predict_fn(), with per-symbol k overrides applied on top."""
    pred = predict_fn(df, base_p, sign)
    key = "k_top" if sign > 0 else "k_bot"
    for sym, ov in overrides.items():
        if key not in ov:
            continue
        mask = df["tos_symbol"] == sym
        if not mask.any():
            continue
        p2 = dict(base_p, k=ov[key])
        pred = pred.where(~mask, predict_fn(df, p2, sign))
    return pred


def fit_per_ticker_overrides(merged: pd.DataFrame, top_p: dict, bot_p: dict,
                              symbols: list[str], min_gain: float = 0.5,
                              max_symbols: int = 8, predict_fn=predict_full) -> dict:
    """Per-symbol k_top/k_bot re-fit (full history, not train/test-split —
    this is a targeted local correction, not a CV-fit). Kept only if it
    improves that symbol's median APE by >= min_gain percentage points
    (TASK_130 lowered the bar from 1.0pp to 0.5pp, cap raised 6->8 symbols)."""
    candidates = []
    for sym in symbols:
        sub = merged[merged["tos_symbol"] == sym]
        if len(sub) < 10:
            continue
        base_top = _metrics(predict_fn(sub, top_p, +1), sub["sell_t"])[0]
        base_bot = _metrics(predict_fn(sub, bot_p, -1), sub["buy_t"])[0]
        best_kt, best_top = top_p["k"], base_top
        for k in K_GRID:
            m = _metrics(predict_fn(sub, dict(top_p, k=float(k)), +1), sub["sell_t"])[0]
            if m < best_top:
                best_top, best_kt = m, float(k)
        best_kb, best_bot = bot_p["k"], base_bot
        for k in K_GRID:
            m = _metrics(predict_fn(sub, dict(bot_p, k=float(k)), -1), sub["buy_t"])[0]
            if m < best_bot:
                best_bot, best_kb = m, float(k)
        entry, gain = {}, 0.0
        if base_top - best_top >= min_gain:
            entry["k_top"] = best_kt
            gain = max(gain, base_top - best_top)
        if base_bot - best_bot >= min_gain:
            entry["k_bot"] = best_kb
            gain = max(gain, base_bot - best_bot)
        if entry:
            candidates.append((gain, sym, entry))
    candidates.sort(key=lambda r: -r[0])
    return {sym: entry for _, sym, entry in candidates[:max_symbols]}


# --- orchestration ------------------------------------------------------------

def _split_train_test(merged: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS):
    cutoff = merged["snapshot_date"].max() - pd.Timedelta(days=holdout_days)
    return merged[merged["snapshot_date"] <= cutoff], merged[merged["snapshot_date"] > cutoff]


def run_calibration(start: date | None, end: date | None) -> pd.DataFrame:
    merged = load_and_merge(start, end)
    baseline_report(merged)

    train, test = _split_train_test(merged)
    print(f"\nCV split: train={len(train)} test(last {HOLDOUT_DAYS}d)={len(test)} "
          f"cutoff={train['snapshot_date'].max().date()}")

    print("\n--- Family A (classic BB) grid search, top 3 by band (fit on train) ---")
    top_a = grid_search_family_a(train, "sell_t", +1)
    bot_a = grid_search_family_a(train, "buy_t", -1)
    print("  TOP  (mid, n, k, train_med%, train_pct<=2%):", top_a[:3])
    print("  BOT  (mid, n, k, train_med%, train_pct<=2%):", bot_a[:3])

    print("\n--- Family B (Donchian blend) grid search, best by band (fit on train) ---")
    top_b = grid_search_family_b(train, "sell_t", +1)
    bot_b = grid_search_family_b(train, "buy_t", -1)
    print("  TOP  (n_don, m_std, k, train_med%, train_pct<=2%):", top_b[0])
    print("  BOT  (n_don, m_std, k, train_med%, train_pct<=2%):", bot_b[0])

    print("\n--- Family C (vol-scaled BB) grid search, best by band (fit on train) ---")
    top_c = grid_search_family_c(train, "sell_t", +1)
    bot_c = grid_search_family_c(train, "buy_t", -1)
    print("  TOP  (mid, n, c, k, train_med%, train_pct<=2%):", top_c[0])
    print("  BOT  (mid, n, c, k, train_med%, train_pct<=2%):", bot_c[0])

    print(f"\n=== FITTED_A (family A, TASK_128 baseline) ===")
    print(f"  mid={FITTED_A['mid']} n={FITTED_A['n']} k_top={FITTED_A['k_top']} k_bot={FITTED_A['k_bot']}")

    print("\n--- Family D (TASK_129: full price+volume+volatility) coordinate descent ---")
    top_d1, top_log1 = fit_family_d(train, "sell_t", +1, FITTED_A["n"], FITTED_A["k_top"])
    bot_d1, bot_log1 = fit_family_d(train, "buy_t", -1, FITTED_A["n"], FITTED_A["k_bot"])
    # round 2: warm-started coordinate descent from round 1's optimum — keeps
    # squeezing the local joint refinement until it stops improving.
    top_d2, top_log2 = fit_family_d(train, "sell_t", +1, FITTED_A["n"], FITTED_A["k_top"],
                                     init=top_d1, step_prefix="R2 ")
    bot_d2, bot_log2 = fit_family_d(train, "buy_t", -1, FITTED_A["n"], FITTED_A["k_bot"],
                                     init=bot_d1, step_prefix="R2 ")

    def _pp(df, p, sign, col):
        med, pct2, _ = _metrics(predict_full(df, p, sign), df[col])
        return (pct2, med)

    top_d = top_d2 if _better(_pp(train, top_d2, +1, "sell_t"), _pp(train, top_d1, +1, "sell_t")) else top_d1
    bot_d = bot_d2 if _better(_pp(train, bot_d2, -1, "buy_t"), _pp(train, bot_d1, -1, "buy_t")) else bot_d1
    top_log, bot_log = top_log1 + top_log2, bot_log1 + bot_log2
    print("  TOP ablation (train):")
    for step, med, pct2, _pp in top_log:
        print(f"    {step:48s} med={med:.3f}%  pct<=2%={pct2:.1f}%")
    print("  BOTTOM ablation (train):")
    for step, med, pct2, _pp in bot_log:
        print(f"    {step:48s} med={med:.3f}%  pct<=2%={pct2:.1f}%")
    print("\n  TOP final params:   ", top_d)
    print("  BOTTOM final params:", bot_d)

    print("\n=== Family D final report (no overrides) ===")
    print_final_report_d(merged, train, test, top_d, bot_d, {})

    # --- TASK_130: Family E -- inverse VIX coupling + vol-level + semi-dev +
    # directional volume, warm-started from Family D, 2-fold-walk-forward-CV
    # gated coordinate descent. ------------------------------------------------
    print("\n--- Family E (TASK_130: +VIX coupling +vol-level +semi-dev +dir-vol) ---")
    train_e, fold1_e, fold2_e = _split_folds(merged)
    print(f"  CV split: train={len(train_e)} fold1={len(fold1_e)} fold2={len(fold2_e)} "
          f"(fold_days={FOLD_DAYS} each) train_cutoff={train_e['snapshot_date'].max().date()}")

    top_e, top_log_e = fit_family_e(train_e, fold1_e, fold2_e, "sell_t", +1, top_d, is_bottom=False)
    bot_e, bot_log_e = fit_family_e(train_e, fold1_e, fold2_e, "buy_t", -1, bot_d, is_bottom=True)

    def _print_log(label, log):
        print(f"  {label} ablation (train / fold1 / fold2):")
        for step, t_med, t_pct2, f1_med, f1_pct2, f2_med, f2_pct2, _pp in log:
            print(f"    {step:42s} train med={t_med:.3f}% pct<=2%={t_pct2:.1f}%   "
                  f"f1 med={f1_med:.3f}% pct<=2%={f1_pct2:.1f}%   "
                  f"f2 med={f2_med:.3f}% pct<=2%={f2_pct2:.1f}%")

    _print_log("TOP", top_log_e)
    _print_log("BOTTOM", bot_log_e)
    print("\n  TOP final params (Family E):   ", top_e)
    print("  BOTTOM final params (Family E):", bot_e)

    print("\n=== Family E final report (no overrides) ===")
    print_final_report_e(merged, train_e, fold1_e, fold2_e, top_e, bot_e, {})

    print("\n--- Per-ticker override search (worst Family-E tickers) ---")
    pred_top_all = predict_full_v2(merged, top_e, +1)
    pred_bot_all = predict_full_v2(merged, bot_e, -1)
    worst = worst_tickers(merged, pred_top_all, pred_bot_all, k=8)
    overrides = fit_per_ticker_overrides(merged, top_e, bot_e, list(worst.index),
                                          predict_fn=predict_full_v2)
    print(f"  Candidates checked: {list(worst.index)}")
    print(f"  Overrides kept (>=0.5pp gain, max 8): {overrides}")

    if overrides:
        print("\n=== Family E final report (with overrides) ===")
        print_final_report_e(merged, train_e, fold1_e, fold2_e, top_e, bot_e, overrides)

    return merged


def print_final_report_d(merged: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame,
                          top_p: dict, bot_p: dict, overrides: dict) -> None:
    for label, df in (("TRAIN", train), ("TEST", test), ("ALL (full hist_rr history)", merged)):
        pred_top = predict_full_overridden(df, top_p, +1, overrides)
        pred_bot = predict_full_overridden(df, bot_p, -1, overrides)
        t_med, t_pct, n_rows = _metrics(pred_top, df["sell_t"])
        b_med, b_pct, _ = _metrics(pred_bot, df["buy_t"])
        print(f"  [{label}] n={n_rows}  TOP med={t_med:.3f}% pct<=2%={t_pct:.1f}%   "
              f"BOT med={b_med:.3f}% pct<=2%={b_pct:.1f}%")

    pred_top_all = predict_full_overridden(merged, top_p, +1, overrides)
    pred_bot_all = predict_full_overridden(merged, bot_p, -1, overrides)
    print("\n  Worst 5 tickers (Family D fitted params, full history):")
    print(worst_tickers(merged, pred_top_all, pred_bot_all)[["n", "med_top", "med_bot"]])

    ok_top = _metrics(pred_top_all, merged["sell_t"])
    ok_bot = _metrics(pred_bot_all, merged["buy_t"])
    print("\n  Target (median<=1.0%, pct<=2%>=70%; stretch >=80%; "
          "never below TASK_128: TOP 0.97%/72.1%, BOT 1.14%/63.8%):")
    print(f"    TOP:    {'PASS' if ok_top[0] <= 1.0 and ok_top[1] >= 70 else 'MISS'} "
          f"(median={ok_top[0]:.2f}%, pct<=2%={ok_top[1]:.1f}%)")
    print(f"    BOTTOM: {'PASS' if ok_bot[0] <= 1.0 and ok_bot[1] >= 70 else 'MISS'} "
          f"(median={ok_bot[0]:.2f}%, pct<=2%={ok_bot[1]:.1f}%)")


def print_final_report_e(merged: pd.DataFrame, train: pd.DataFrame, fold1: pd.DataFrame,
                          fold2: pd.DataFrame, top_p: dict, bot_p: dict, overrides: dict) -> None:
    """TASK_130 report: TRAIN / FOLD1 / FOLD2 / ALL breakdown (Family E)."""
    for label, df in (("TRAIN", train), ("FOLD1", fold1), ("FOLD2", fold2),
                       ("ALL (full hist_rr history)", merged)):
        pred_top = predict_full_overridden(df, top_p, +1, overrides, predict_fn=predict_full_v2)
        pred_bot = predict_full_overridden(df, bot_p, -1, overrides, predict_fn=predict_full_v2)
        t_med, t_pct, n_rows = _metrics(pred_top, df["sell_t"])
        b_med, b_pct, _ = _metrics(pred_bot, df["buy_t"])
        print(f"  [{label}] n={n_rows}  TOP med={t_med:.3f}% pct<=2%={t_pct:.1f}%   "
              f"BOT med={b_med:.3f}% pct<=2%={b_pct:.1f}%")

    pred_top_all = predict_full_overridden(merged, top_p, +1, overrides, predict_fn=predict_full_v2)
    pred_bot_all = predict_full_overridden(merged, bot_p, -1, overrides, predict_fn=predict_full_v2)
    print("\n  Worst 5 tickers (Family E fitted params, full history):")
    print(worst_tickers(merged, pred_top_all, pred_bot_all)[["n", "med_top", "med_bot"]])

    ok_top = _metrics(pred_top_all, merged["sell_t"])
    ok_bot = _metrics(pred_bot_all, merged["buy_t"])
    print("\n  Target (TASK_130): BOTTOM median<=0.75%, pct<=2%>=78%; "
          "TOP must not regress below TASK_129 (0.70%/80%):")
    print(f"    TOP:    {'PASS' if ok_top[0] <= 0.70 and ok_top[1] >= 80 else 'MISS/WATCH'} "
          f"(median={ok_top[0]:.3f}%, pct<=2%={ok_top[1]:.1f}%)")
    print(f"    BOTTOM: {'PASS' if ok_bot[0] <= 0.75 and ok_bot[1] >= 78 else 'MISS'} "
          f"(median={ok_bot[0]:.3f}%, pct<=2%={ok_bot[1]:.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--report", action="store_true",
                     help="Skip the grid/coordinate-descent search; just rescore "
                          "FITTED_TOP/FITTED_BOT (+ OVERRIDES) (fast).")
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    if args.report:
        merged = load_and_merge(start, end)
        baseline_report(merged)
        train, fold1, fold2 = _split_folds(merged)
        print_final_report_e(merged, train, fold1, fold2, FITTED_TOP, FITTED_BOT, OVERRIDES)
    else:
        run_calibration(start, end)


if __name__ == "__main__":
    main()
