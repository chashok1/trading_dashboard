"""Factor-driver outcome ETL — populates drv_factor_snapshot (v_factor_scorecard).

For each (tos_symbol, as_of_date) already on the Actionable screen, buckets
each candidate factor (RSI, MACDH momentum, RVOL+price-direction, IV
percentile, macro quad action, winning source, sector, growth/valuation/
momentum style) and records the 5d/20d forward return of the stock from that
date — same LEAD-over-drv_ma.last_price convention as compute_firing_outcomes.py.
Idempotent upsert: DELETE/INSERT is not used, ON CONFLICT DO UPDATE per
(as_of_date, tos_symbol) instead, since every factor's bucket for a row is
computed in the same pass.

Bucket thresholds for RSI/RVOL mirror the live Actionable "don't buy/buy"
warning icon (web/actionable.js::_signalReasons) via the same ref_settings
rows (rsi_overbought/rsi_oversold/vlm_rvol_avoid_threshold), so the factor
scorecard is checking the icon's own thresholds, not a different definition.

Run:
    python -m etl.compute_factor_outcomes              # populate (idempotent upsert)
    python -m etl.compute_factor_outcomes --truncate    # clear table first
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from etl.db import session_scope  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.compute_factor_outcomes")


def _settings(s) -> dict:
    rows = s.execute(text("SELECT setting_name, setting_value FROM ref_settings")).fetchall()
    out = {}
    for k, v in rows:
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def _build_fwd_returns(s):
    """Materialize _fwd_fac(tos_symbol, as_of_date, fwd5, fwd20) — same LEAD
    convention as compute_firing_outcomes.py's _fwd, separate temp table so
    the two ETLs never collide if run in the same session."""
    s.execute(text("DROP TABLE IF EXISTS _fwd_fac"))
    s.execute(text("""
        CREATE TEMP TABLE _fwd_fac AS
        WITH px AS (
            SELECT tos_symbol, as_of_date, last_price,
                   LEAD(last_price, 5)  OVER w AS p5,
                   LEAD(last_price, 20) OVER w AS p20
            FROM drv_ma
            WHERE last_price IS NOT NULL
            WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
        )
        SELECT tos_symbol, as_of_date,
               CASE WHEN last_price > 0 AND p5  IS NOT NULL
                    THEN (p5  - last_price) / last_price * 100 END AS fwd5,
               CASE WHEN last_price > 0 AND p20 IS NOT NULL
                    THEN (p20 - last_price) / last_price * 100 END AS fwd20
        FROM px
    """))
    s.execute(text("CREATE INDEX ON _fwd_fac (tos_symbol, as_of_date)"))
    n = s.execute(text("SELECT COUNT(*) FROM _fwd_fac WHERE fwd20 IS NOT NULL")).scalar()
    log.info("_fwd_fac built: %s rows with a 20d forward return", n)


def _populate_snapshot(s, settings):
    rsi_hi = settings.get("rsi_overbought", 70)
    rsi_lo = settings.get("rsi_oversold", 30)
    rvol_hi = settings.get("vlm_rvol_avoid_threshold", 1.5)

    res = s.execute(text(f"""
        INSERT INTO drv_factor_snapshot
            (as_of_date, tos_symbol, rsi_bucket, macdh_bucket, rvol_bucket,
             iv_bucket, macro_action, winning_source, sector, growth_style,
             valuation_style, momentum_style, pvv_decision,
             fwd_5d_pct, fwd_20d_pct)
        SELECT
            a.as_of_date, a.tos_symbol,
            CASE WHEN mt.rsi <= :rsi_lo THEN 'Oversold (<=' || :rsi_lo || ')'
                 WHEN mt.rsi >= :rsi_hi THEN 'Overbought (>=' || :rsi_hi || ')'
                 WHEN mt.rsi IS NOT NULL THEN 'Neutral' END AS rsi_bucket,
            CASE WHEN mt.a_macdh_d_brr > 0 THEN 'Strengthening (>0)'
                 WHEN mt.a_macdh_d_brr IS NOT NULL THEN 'Weakening (<=0)' END AS macdh_bucket,
            CASE WHEN tw.rvol >= :rvol_hi AND q.pct_change > 0 THEN 'High RVOL + up day'
                 WHEN tw.rvol >= :rvol_hi AND q.pct_change < 0 THEN 'High RVOL + down day'
                 WHEN tw.rvol IS NOT NULL THEN 'Normal/low RVOL' END AS rvol_bucket,
            CASE WHEN mt.iv_percentile >= 90 THEN 'Extreme (>=90)'
                 WHEN mt.iv_percentile >= 70 THEN 'Elevated (70-90)'
                 WHEN mt.iv_percentile <= 30 THEN 'Low (<=30)'
                 WHEN mt.iv_percentile IS NOT NULL THEN 'Mid (30-70)' END AS iv_bucket,
            ms.macro_action,
            a.winning_source,
            a.sector,
            rs.growth AS growth_style,
            rs.valuation AS valuation_style,
            rs.price_action AS momentum_style,
            pv.decision AS pvv_decision,
            f.fwd5, f.fwd20
        FROM drv_actionable a
        JOIN _fwd_fac f ON f.tos_symbol = a.tos_symbol AND f.as_of_date = a.as_of_date
        LEFT JOIN drv_technicals mt ON mt.tos_symbol = a.tos_symbol AND mt.as_of_date = a.as_of_date
        LEFT JOIN LATERAL (
            SELECT w_vlm_expn_ratio AS rvol
            FROM drv_tw WHERE tos_symbol = a.tos_symbol AND snapshot_date = a.as_of_date
            ORDER BY sequence DESC LIMIT 1
        ) tw ON TRUE
        LEFT JOIN drv_quote q ON q.tos_symbol = a.tos_symbol AND q.as_of_date = a.as_of_date
        LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = a.as_of_date
        LEFT JOIN ref_sector rs ON rs.ticker = a.tos_symbol
        LEFT JOIN drv_pvv pv ON pv.tos_symbol = a.tos_symbol AND pv.as_of_date = a.as_of_date
        WHERE f.fwd20 IS NOT NULL
        ON CONFLICT (as_of_date, tos_symbol) DO UPDATE SET
            rsi_bucket = EXCLUDED.rsi_bucket,
            macdh_bucket = EXCLUDED.macdh_bucket,
            rvol_bucket = EXCLUDED.rvol_bucket,
            iv_bucket = EXCLUDED.iv_bucket,
            macro_action = EXCLUDED.macro_action,
            winning_source = EXCLUDED.winning_source,
            sector = EXCLUDED.sector,
            growth_style = EXCLUDED.growth_style,
            valuation_style = EXCLUDED.valuation_style,
            momentum_style = EXCLUDED.momentum_style,
            pvv_decision = EXCLUDED.pvv_decision,
            fwd_5d_pct = EXCLUDED.fwd_5d_pct,
            fwd_20d_pct = EXCLUDED.fwd_20d_pct,
            derived_at = now()
    """), {"rsi_lo": rsi_lo, "rsi_hi": rsi_hi, "rvol_hi": rvol_hi})
    log.info("factor snapshot upserted: %s rows", res.rowcount)


def refresh_factor_outcomes(truncate: bool = False) -> dict:
    """Importable entrypoint (used by etl/scheduler.py's nightly job as well
    as the CLI below). Idempotent upsert of drv_factor_snapshot for every
    (tos_symbol, as_of_date) with a complete 20d forward return available."""
    with session_scope() as s:
        if truncate:
            s.execute(text("TRUNCATE drv_factor_snapshot"))
            log.info("drv_factor_snapshot truncated")
        settings = _settings(s)
        _build_fwd_returns(s)
        _populate_snapshot(s, settings)
        s.commit()
        n = s.execute(text("SELECT COUNT(*) FROM drv_factor_snapshot")).scalar()
        log.info("drv_factor_snapshot now has %s rows", n)
        return {"rows": n}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--truncate", action="store_true", help="Clear drv_factor_snapshot first")
    args = p.parse_args()
    refresh_factor_outcomes(truncate=args.truncate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
