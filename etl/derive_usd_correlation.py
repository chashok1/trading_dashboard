"""
Derive drv_usd_correlation — TASK_79 / updated TASK_84.

Rolling Pearson correlation of USD raw price levels vs SPX / Brent / CRB /
Gold / Bitcoin across 15/30/90/120/180 trading-day windows, plus a
52-week rolling-30D stats block.

Methodology: Pearson of raw daily closes (price-levels), NOT daily returns.
This matches the provider methodology (bake-off: levels MAE ~0.087 vs
returns ~0.28).  Each window is the trailing-N aligned daily closes for
both USD and the asset — no differencing.

Price series: unified daily close per asset = coalesce(hist_y daily load,
yfinance hist_quote_daily). Source priority is spec-list order (first wins).
USD: histy:^NYICDX wins on recent dates; yfinance:DX-Y.NYB provides history.
SPX: histy:^SPX wins on recent dates; yfinance:^GSPC provides history.

Idempotent: DELETE WHERE as_of_date=D then INSERT.
Wire into derive_all() after drv_quote.
SQL <= 965 bytes (convention 7) — all heavy lifting done in Python.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("derive_usd_correlation")

WINDOWS = [15, 30, 90, 120, 180]
STATS_WINDOW_30 = 30    # rolling 30D corr
STATS_LOOKBACK  = 252   # 252 rolling-30D points for the 52-wk stats block

# FX sign convention (TASK_82 Part 3 — enforced here for any future FX asset):
#   /6E  EUR/USD  (~1.14) — INVERSE  to USD (up-dollar → down /6E)
#   /6B  GBP/USD  (~1.32) — INVERSE  to USD (up-dollar → down /6B)
#   /6C  CAD/USD  (~0.71) — INVERSE  to USD (up-dollar → down /6C)
#   /6J  USD/JPY  (~159)  — CO-DIRECTIONAL with USD (up-dollar → up /6J)
# None of these are currently in ref_corr_asset. If added, /6J returns must be
# NEGATED before computing Pearson r with USD, so its sign aligns with /6E/6B/6C
# (all becoming "foreign-per-USD" on an inverse basis relative to USD strength).


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Pearson r for two equal-length lists; None if undefined."""
    n = len(xs)
    if n < 2:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _load_price_series(session: Session, asset_key: str,
                       source_spec: list[str]) -> dict[date, float]:
    """Build {obs_date: close} for an asset using source_spec priority.

    TOS source:      drv_quote.last_price WHERE tos_symbol=<sym>.
    yfinance source: hist_quote_daily WHERE source='yfinance' AND symbol=<sym>.
    histy source:    hist_y.last_price WHERE symbol=<sym> (weekdays only).
    Earlier entries in source_spec win on date overlap (first wins).
    """
    merged: dict[date, float] = {}

    for spec in source_spec:
        if not isinstance(spec, str):
            continue
        if spec.startswith("tos:"):
            tos_sym = spec[4:]
            rows = session.execute(text("""
                SELECT as_of_date, last_price
                FROM drv_quote
                WHERE tos_symbol = :s AND last_price IS NOT NULL
                ORDER BY as_of_date
            """), {"s": tos_sym}).all()
            for obs_date, close in rows:
                if obs_date not in merged:
                    merged[obs_date] = float(close)
        elif spec.startswith("yfinance:"):
            yf_sym = spec[9:]
            rows = session.execute(text("""
                SELECT obs_date, close
                FROM hist_quote_daily
                WHERE source = 'yfinance' AND symbol = :s
                  AND close IS NOT NULL
                ORDER BY obs_date
            """), {"s": yf_sym}).all()
            for obs_date, close in rows:
                if obs_date not in merged:
                    merged[obs_date] = float(close)
        elif spec.startswith("histy:"):
            hy_sym = spec[6:]
            rows = session.execute(text("""
                SELECT export_date, last_price
                FROM hist_y
                WHERE symbol = :s AND last_price IS NOT NULL
                  AND EXTRACT(DOW FROM export_date) NOT IN (0, 6)
                ORDER BY export_date
            """), {"s": hy_sym}).all()
            for obs_date, close in rows:
                if obs_date not in merged:
                    merged[obs_date] = float(close)

    return merged


def _load_assets(session: Session) -> list[dict]:
    """Load enabled assets from ref_corr_asset."""
    rows = session.execute(text("""
        SELECT asset_key, label, source_spec, is_usd_base, sort_order
        FROM ref_corr_asset
        WHERE enabled = TRUE
        ORDER BY sort_order
    """)).mappings().all()
    result = []
    for r in rows:
        spec = r["source_spec"]
        if isinstance(spec, str):
            spec = json.loads(spec)
        elif spec is None:
            spec = []
        result.append({
            "asset_key": r["asset_key"],
            "label": r["label"],
            "source_spec": spec,
            "is_usd_base": r["is_usd_base"],
        })
    return result


def _derive_usd_correlation_impl(
    session: Session,
    as_of_date: date,
    parent_run_id=None,
) -> int:
    """Compute drv_usd_correlation for as_of_date. Returns rows inserted."""

    assets = _load_assets(session)
    if not assets:
        log.warning("derive_usd_correlation: no enabled assets in ref_corr_asset")
        return 0

    # Find the USD base asset
    usd_assets = [a for a in assets if a["is_usd_base"]]
    if not usd_assets:
        log.warning("derive_usd_correlation: no is_usd_base asset in ref_corr_asset")
        return 0
    usd_asset = usd_assets[0]

    # Load USD price series
    usd_prices = _load_price_series(session, usd_asset["asset_key"],
                                    usd_asset["source_spec"])
    if len(usd_prices) < 2:
        log.warning("derive_usd_correlation: insufficient USD price history")
        return 0

    # Idempotent: DELETE existing rows for this date
    session.execute(
        text("DELETE FROM drv_usd_correlation WHERE as_of_date = :d"),
        {"d": as_of_date}
    )

    rows_inserted = 0
    non_base = [a for a in assets if not a["is_usd_base"]]

    for asset in non_base:
        asset_prices = _load_price_series(session, asset["asset_key"],
                                          asset["source_spec"])
        if len(asset_prices) < 2:
            log.debug("derive_usd_correlation: skipping %s — insufficient history",
                      asset["asset_key"])
            continue

        # Common dates: all dates on or before as_of_date
        common = sorted(
            d for d in usd_prices if d in asset_prices and d <= as_of_date
        )
        if len(common) < 2:
            continue

        usd_seq   = [usd_prices[d]   for d in common]
        asset_seq = [asset_prices[d] for d in common]

        # Price-levels Pearson — use raw closes directly (no differencing).
        # Methodology: provider-style (TASK_84 bake-off: MAE ~0.087 vs returns ~0.28).
        n_prices = len(usd_seq)  # number of aligned daily closes

        # Rolling correlation windows (trailing N price levels ending at as_of_date)
        corr: dict[int, Optional[float]] = {}
        n_count: dict[int, Optional[int]] = {}
        for w in WINDOWS:
            if n_prices >= w:
                xs = usd_seq[-w:]
                ys = asset_seq[-w:]
                corr[w]   = _pearson(xs, ys)
                n_count[w] = w
            else:
                corr[w]   = _pearson(usd_seq, asset_seq) if n_prices >= 2 else None
                n_count[w] = n_prices if n_prices >= 2 else None

        # 52-wk rolling-30D stats block
        # Build series of rolling-30D price-levels Pearson for the last
        # STATS_LOOKBACK + STATS_WINDOW_30 prices so we get 252 rolling points.
        roll30_series: list[float] = []
        start_idx = max(0, n_prices - STATS_LOOKBACK - STATS_WINDOW_30)
        for i in range(start_idx + STATS_WINDOW_30, n_prices + 1):
            xs30 = usd_seq[i - STATS_WINDOW_30: i]
            ys30 = asset_seq[i - STATS_WINDOW_30: i]
            r30  = _pearson(xs30, ys30)
            if r30 is not None:
                roll30_series.append(r30)

        # Trim to last 252 points
        roll30_series = roll30_series[-STATS_LOOKBACK:]

        roll30_high    = max(roll30_series) if roll30_series else None
        roll30_low     = min(roll30_series) if roll30_series else None
        roll30_pct_pos: Optional[float] = None
        roll30_pct_neg: Optional[float] = None
        if roll30_series:
            roll30_pct_pos = sum(1 for v in roll30_series if v > 0) / len(roll30_series)
            roll30_pct_neg = sum(1 for v in roll30_series if v < 0) / len(roll30_series)

        # Resolve tos_symbol (first "tos:" entry in source_spec, if any)
        tos_sym: Optional[str] = None
        for spec in asset["source_spec"]:
            if isinstance(spec, str) and spec.startswith("tos:"):
                tos_sym = spec[4:]
                break

        session.execute(text("""
            INSERT INTO drv_usd_correlation
              (as_of_date, asset_key, tos_symbol,
               w15, w30, w90, w120, w180,
               n15, n30, n90, n120, n180,
               roll30_high, roll30_low, roll30_pct_pos, roll30_pct_neg)
            VALUES
              (:d, :ak, :ts,
               :w15, :w30, :w90, :w120, :w180,
               :n15, :n30, :n90, :n120, :n180,
               :rh, :rl, :rpp, :rpn)
        """), {
            "d":   as_of_date,
            "ak":  asset["asset_key"],
            "ts":  tos_sym,
            "w15": _r(corr.get(15)),
            "w30": _r(corr.get(30)),
            "w90": _r(corr.get(90)),
            "w120": _r(corr.get(120)),
            "w180": _r(corr.get(180)),
            "n15":  n_count.get(15),
            "n30":  n_count.get(30),
            "n90":  n_count.get(90),
            "n120": n_count.get(120),
            "n180": n_count.get(180),
            "rh":   _r(roll30_high),
            "rl":   _r(roll30_low),
            "rpp":  _r(roll30_pct_pos),
            "rpn":  _r(roll30_pct_neg),
        })
        rows_inserted += 1

    session.commit()
    log.info("derive_usd_correlation: %d rows for %s", rows_inserted, as_of_date)
    return rows_inserted


def _r(v: Optional[float]) -> Optional[float]:
    """Round to 4 dp for DB storage; None if NaN/inf."""
    if v is None:
        return None
    try:
        f = float(v)
        return round(f, 4) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def derive_usd_correlation(
    session: Session,
    as_of_date: date,
    parent_run_id=None,
) -> int:
    """Public entry point — called by derive_all()."""
    try:
        return _derive_usd_correlation_impl(session, as_of_date, parent_run_id)
    except Exception:
        log.exception("derive_usd_correlation: failed for %s", as_of_date)
        try:
            session.rollback()
        except Exception:
            pass
        return 0
