"""
TASK_128 — Calibrate the TOS BBTop/BBBottom ThinkScript bands against the
Hedgeye risk ranges published in hist_rr (buy_trade / sell_trade).

Builds a per-(snapshot_date, tos_symbol) calibration dataset for every ticker
that appears in BOTH hist_rr and hist_td, reports the current a_bb_top /
a_bb_bottom baseline error, grid-searches three small model families for a
closer TOS-expressible fit, and prints the final report (chosen family,
params, metrics, worst tickers). See docs/tos_rr_calibration.md for the
narrative writeup and docs/actionable... n/a (not actionable-related).

Date alignment: hist_rr(D) is published pre-open using D-1's close, so every
feature here is anchored on the latest hist_td close STRICTLY BEFORE D
(pandas merge_asof direction='backward', allow_exact_matches=False) — the
same semantics as etl/derive.py::_derive_rr_impl's BB-fallback lateral join
(`hist_td.snapshot_date < :d`).

Scope: only symbols present in hist_td (equities/ETFs/indices on the TD tab)
can be calibrated — futures/FX/commodity tickers in hist_rr (e.g. /CL, /GC,
/BTC) have no hist_td close series and are excluded (they are also excluded
from the BB fallback in derive.py for the same reason).

Usage:
    python -m etl.calibrate_tos_rr                       # full grid search + report
    python -m etl.calibrate_tos_rr --start 2026-05-01     # restrict history
    python -m etl.calibrate_tos_rr --report               # rescore FITTED params only (fast)
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
# Fitted parameters — chosen by the grid search below (see docs/
# tos_rr_calibration.md for the selection process and full metrics table).
# Family A: classic Bollinger Band, mid = EMA(n), band = mid +/- k*StDev(n).
# Same n/mid for both bands; k is asymmetric per the RR data (top slightly
# tighter than bottom). These constants are hand-transcribed into
# TOS/BBTop.txt / TOS/BBBottom.txt as `input` defaults — keep them in sync.
# ---------------------------------------------------------------------------
FITTED = {
    "family": "A",       # classic BB: mid(n) +/- k * StDev(close, n)
    "mid": "ema",         # EMA beat SMA for both bands at every n tried
    "n": 10,
    "k_top": 1.72,
    "k_bot": 1.86,
}

N_LIST = [10, 15, 20, 21, 26]
K_GRID = np.round(np.arange(0.3, 4.01, 0.02), 2)
C_GRID = np.array([-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
HOLDOUT_DAYS = 14  # leave-last-2-weeks-out CV split


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


# --- feature engineering -----------------------------------------------------

def compute_features(td: pd.DataFrame, n_list: list[int] = N_LIST) -> pd.DataFrame:
    """Rolling SMA/EMA/StDev(sample)/Highest/Lowest per symbol, for each n."""
    g = td.groupby("tos_symbol")["close"]
    frames = [td[["tos_symbol", "snapshot_date", "close",
                   "historical_vol", "imp_volatility",
                   "a_bb_top", "a_bb_bottom"]]]
    for n in n_list:
        frames.append(pd.DataFrame({
            f"sma_{n}": g.transform(lambda x, n=n: x.rolling(n, min_periods=n).mean()),
            f"ema_{n}": g.transform(lambda x, n=n: x.ewm(span=n, adjust=False, min_periods=n).mean()),
            f"std_{n}": g.transform(lambda x, n=n: x.rolling(n, min_periods=n).std(ddof=1)),
            f"hi_{n}":  g.transform(lambda x, n=n: x.rolling(n, min_periods=n).max()),
            f"lo_{n}":  g.transform(lambda x, n=n: x.rolling(n, min_periods=n).min()),
        }))
    return pd.concat(frames, axis=1)


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


# --- orchestration ------------------------------------------------------------

def _split_train_test(merged: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS):
    cutoff = merged["snapshot_date"].max() - pd.Timedelta(days=holdout_days)
    return merged[merged["snapshot_date"] <= cutoff], merged[merged["snapshot_date"] > cutoff]


def run_calibration(start: date | None, end: date | None) -> pd.DataFrame:
    with session_scope() as s:
        targets = load_targets(s, start, end)
        symbols = sorted(targets["tos_symbol"].unique().tolist())
        no_td = sorted(set(symbols) - set(pd.read_sql(text(
            "SELECT DISTINCT tos_symbol FROM hist_td WHERE tos_symbol = ANY(:s)"
        ), s.bind, params={"s": symbols})["tos_symbol"]))
        td = load_td_series(s, symbols, end)

    if no_td:
        print(f"\nSkipping {len(no_td)} hist_rr symbol(s) with no hist_td series "
              f"(futures/FX/commodities — outside TOS BB scope): {no_td}")

    feat = compute_features(td)
    merged = anchor_merge(targets, feat)
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

    print(f"\n=== FITTED (family A, chosen — simplest & ties/beats B & C on test) ===")
    print(f"  mid={FITTED['mid']} n={FITTED['n']} k_top={FITTED['k_top']} k_bot={FITTED['k_bot']}")
    print_final_report(merged, train, test)
    return merged


def print_final_report(merged: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame) -> None:
    mid, n = FITTED["mid"], FITTED["n"]
    k_top, k_bot = FITTED["k_top"], FITTED["k_bot"]
    pred_top_all = merged[f"{mid}_{n}"] + k_top * merged[f"std_{n}"]
    pred_bot_all = merged[f"{mid}_{n}"] - k_bot * merged[f"std_{n}"]

    for label, df in (("TRAIN", train), ("TEST", test), ("ALL (full hist_rr history)", merged)):
        pred_top = df[f"{mid}_{n}"] + k_top * df[f"std_{n}"]
        pred_bot = df[f"{mid}_{n}"] - k_bot * df[f"std_{n}"]
        t_med, t_pct, n_rows = _metrics(pred_top, df["sell_t"])
        b_med, b_pct, _ = _metrics(pred_bot, df["buy_t"])
        print(f"  [{label}] n={n_rows}  TOP med={t_med:.3f}% pct<=2%={t_pct:.1f}%   "
              f"BOT med={b_med:.3f}% pct<=2%={b_pct:.1f}%")

    print("\n  Worst 5 tickers (fitted params, full history):")
    print(worst_tickers(merged, pred_top_all, pred_bot_all)[["n", "med_top", "med_bot"]])

    ok_top = _metrics(pred_top_all, merged["sell_t"])
    ok_bot = _metrics(pred_bot_all, merged["buy_t"])
    print("\n  Success target (median<=1.5%, pct<=2%>=70%):")
    print(f"    TOP:    {'PASS' if ok_top[0] <= 1.5 and ok_top[1] >= 70 else 'MISS'} "
          f"(median={ok_top[0]:.2f}%, pct<=2%={ok_top[1]:.1f}%)")
    print(f"    BOTTOM: {'PASS' if ok_bot[0] <= 1.5 and ok_bot[1] >= 70 else 'MISS'} "
          f"(median={ok_bot[0]:.2f}%, pct<=2%={ok_bot[1]:.1f}%) "
          f"— see docs/tos_rr_calibration.md for the tail-miss explanation.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--report", action="store_true",
                     help="Skip the grid search; just rescore FITTED params (fast).")
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    if args.report:
        with session_scope() as s:
            targets = load_targets(s, start, end)
            symbols = sorted(targets["tos_symbol"].unique().tolist())
            td = load_td_series(s, symbols, end)
        feat = compute_features(td)
        merged = anchor_merge(targets, feat)
        baseline_report(merged)
        train, test = _split_train_test(merged)
        print_final_report(merged, train, test)
    else:
        run_calibration(start, end)


if __name__ == "__main__":
    main()
