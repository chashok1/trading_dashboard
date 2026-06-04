"""
One-command rebuild for the rules engine.

When the engine "isn't working", 90% of the time the actual cause is:
  1. The workbook Trig tab was edited but never re-loaded (ref_trig_atomic_rule stale)
  2. The cat-table derivation didn't run for the latest date (drv_cat_atomic_input empty)
  3. Both — workbook edited AND derive never ran

This script does both in the correct order and prints a health summary at the end.

Usage:
    python -m etl.rebuild_rules                 # rebuild for latest snapshot date
    python -m etl.rebuild_rules --date 2026-05-15
    python -m etl.rebuild_rules --no-refresh    # skip ref reload, just re-derive
    python -m etl.rebuild_rules --no-derive     # skip derive, just refresh refs

The script is safe to run repeatedly — every step is idempotent.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Make `python -m etl.rebuild_rules` work even if PYTHONPATH isn't set
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from config.settings import settings  # noqa: E402
from etl.db import session_scope  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.rebuild_rules")


def _step_refresh_refs() -> dict:
    """Refresh ref_trig_atomic_rule and ref_trig_composite_mapping from the workbook."""
    log.info("STEP 1/3 — refresh ref_trig_* from workbook")
    result = {}
    if not settings.tickers_file or not Path(settings.tickers_file).exists():
        log.warning("  TICKERS_FILE not set or missing — skipping refresh "
                    "(set in .env or pass --no-refresh to silence this)")
        return {"_skipped": "TICKERS_FILE missing"}
    try:
        from etl.refresh_ref import run_one, REFRESH_HANDLERS
    except Exception as e:
        log.warning("  could not import etl.refresh_ref: %s", e)
        return {"_skipped": str(e)}

    for tbl in ("ref_trig_atomic_rule", "ref_trig_composite_mapping"):
        if tbl not in REFRESH_HANDLERS:
            log.info("  %s: no refresh handler registered — skipping", tbl)
            result[tbl] = "no_handler"
            continue
        try:
            read, ins, skp = run_one(tbl, settings.tickers_file)
            log.info("  %s: %d read, %d inserted, %d skipped", tbl, read, ins, skp)
            result[tbl] = {"read": read, "inserted": ins, "skipped": skp}
        except Exception as e:
            log.warning("  %s refresh failed: %s", tbl, e)
            result[tbl] = f"FAIL: {e}"

    # Normalise atomic rule names → drv_cat_atomic_input column names
    # (workbook uses human names; canonical identity is the column name)
    # _EXTRA maps workbook rule_name → column_name where excel_header differs
    # Workbook human names that don't match ref_ma_columns.excel_header exactly
    _EXTRA = {
        "VS Price Rule":        "vs_price",
        "VS Volume Spike Rule": "vs_volume_spike",
        "VS Volatility Rule":   "vs_volatility",
        "Current Price Rule":   "current_price_sd_rule",
        "Bull Rule":            "bull",
        "!Bull Rule":           "not_bull",
        "PerfOrBull Rule":      "perforbull",
        "!PerfOrBull Rule":     "not_perforbull",
        "BBThresh Crossover":   "bb_threshold",
        "BBThresh CO Days2":    "bbthresh_co_days2",
        "Trade Trend Relation": "trtn_relation",
        "!Trade Trend Relation":"not_trtn_relation",
        "BRR% Rule":            "brrpct_rule",
        "BRR% LRR":             "brrpct_lrr",
        "BRR% R2":              "brrpct_r2",
        "BRR% LRR2":            "brrpct_lrr2",
        "BRR% TRR":             "brrpct_trr",
        "BRR% Puts":            "brrpct_puts",
        "BRR% TRR Puts":        "brrpct_trr_puts",
        "BRR% Dir Rule":        "brrpct_dir",
        "High above TRR":       "high_trr",
        "Low below LRR":        "low_lrr",
        "HVAbsolute":           "hvabsolute",
        "IVPercentile":         "ivpercentile",
        "IVPercentile Puts":    "ivpercentile_puts",
        "HVPercentile":         "hvpercentile",
        "HVPercentile Puts":    "hvpercentile_puts",
        "IVHV Rule (modified)": "ivrule",
        "IVHV Puts (modified)": "ivhv_puts",
        "RSI Rule":             "rsi_rule",
        "RSI Top":              "rsi_top",
        "RSI Puts":             "rsi_puts",
        "3mn-High-Dyas Rule":   "3mn_high_days_rule",
        "3mn Long Rule":        "3m_long",
        "Perf3wk SD Rule":      "perf3wk_sd_rule",
        "Perf2wk SD Rule":      "perf2wk_sd_rule",
        "!Perf1D SD Rule":      "not_perf1d_sd",
        "Perf3D 1Off Rule":     "perf3d_sd_1off",
        "BBStreak Rule1":       "bbstreakrule1",
        "BBStreak Days Up Rule":"bbstreak_days_rule2",
        "BBStreak Days Up Rule2":"bbstreak_days_rule4",
        "!3wk Outlook":         "not_3wk_ol",
        "!3wk Outlook Days":    "not_3wk_ol_days",
        "Trade Close to BRR":   "brrtrade",
        "Trade Close to TRR":   "trrtrade",
        "Earnings Days":        "earnings",
    }
    try:
        with session_scope() as s:
            n = s.execute(text("""
                UPDATE ref_trig_atomic_rule a
                SET rule_name      = r.column_name,
                    ma_column_name = 'drv_cat_atomic_input.' || r.column_name
                FROM ref_ma_columns r
                WHERE r.excel_header = a.rule_name
                  AND r.drv_cat_table = 'drv_cat_atomic_input'
                  AND a.deprecated_at IS NULL
            """)).rowcount
            for wb_name, col_name in _EXTRA.items():
                s.execute(text("""
                    UPDATE ref_trig_atomic_rule
                    SET rule_name      = :col,
                        ma_column_name = 'drv_cat_atomic_input.' || :col
                    WHERE rule_name = :wb AND deprecated_at IS NULL
                """), {"wb": wb_name, "col": col_name})
                n += 1
            s.commit()
        log.info("  rule_name normalised: %d rules → drv_cat_atomic_input column names", n)
    except Exception as e:
        log.warning("  rule_name normalisation failed: %s", e)

    # Backfill condition_operator for composite members where it is NULL.
    # BUY rule codes → >=, SELL rule codes → <=.
    # Explicit per-member overrides (already set) are left unchanged.
    try:
        with session_scope() as s:
            nb = s.execute(text(r"""
                UPDATE ref_trig_composite_mapping
                SET condition_operator = '>='
                WHERE condition_operator IS NULL
                  AND deprecated_at IS NULL
                  AND composite_rule_code ~ '^\d+-(B|BS|BR|BW|BM|BMN)-'
            """)).rowcount
            ns = s.execute(text(r"""
                UPDATE ref_trig_composite_mapping
                SET condition_operator = '<='
                WHERE condition_operator IS NULL
                  AND deprecated_at IS NULL
                  AND composite_rule_code ~ '^\d+-(SA|SS|STM|SW|SH)-'
            """)).rowcount
            s.commit()
        log.info("  condition_operator backfilled: %d BUY (>=), %d SELL (<=)", nb, ns)
    except Exception as e:
        log.warning("  condition_operator backfill failed: %s", e)

    return result


def _resolve_target_date(arg_date: str | None) -> date:
    """Pick the as_of_date to derive for."""
    if arg_date:
        try:
            return datetime.strptime(arg_date, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit(f"--date must be YYYY-MM-DD, got {arg_date!r}")
    with session_scope() as s:
        d = s.execute(text("""
            SELECT MAX(d) FROM (
              SELECT MAX(snapshot_date) AS d FROM hist_tl
              UNION ALL SELECT MAX(snapshot_date) FROM hist_td
              UNION ALL SELECT MAX(snapshot_date) FROM hist_rr
              UNION ALL SELECT MAX(as_of_date)   FROM drv_ma
            ) u
        """)).scalar()
    if not d:
        raise SystemExit("No data in hist_* / drv_ma — load a workbook first.")
    log.info("Target date (latest snapshot): %s", d)
    return d


def _step_derive(target: date) -> dict:
    """Run derive_all(target) to rebuild drv_cat_atomic_input + drv_ma + drv_stks + drv_trig."""
    log.info("STEP 2/3 — derive_all(%s)", target)
    from etl.derive import derive_all
    with session_scope() as s:
        counts = derive_all(s, target)
    interesting = {
        k: v for k, v in counts.items()
        if k in ("drv_ma", "drv_cat_atomic_input", "drv_stks", "drv_trig",
                 "drv_dash", "drv_outlook_action", "drv_actionable")
    }
    for k, v in interesting.items():
        log.info("  %-26s %s", k, v)
    return counts


def _step_health() -> dict:
    """Hit the same logic /api/rules/health uses and print a summary."""
    log.info("STEP 3/3 — health summary")
    from api.routers.rules import get_rules_engine_health  # reuse the endpoint logic
    h = get_rules_engine_health()
    log.info("  status:                       %s", h["status"])
    if h.get("issues"):
        for i in h["issues"]:
            log.warning("    issue: %s", i)
    c = h.get("counts", {})
    log.info("  atomic_rules (active/total):  %s / %s",
             c.get("atomic_rules_active"), c.get("atomic_rules_total"))
    log.info("  atomic_rules with weights:    %s", c.get("atomic_rules_with_weights"))
    log.info("  composites (active/total):    %s / %s",
             c.get("composites_active"), c.get("composites_total"))
    log.info("  latest snapshot:              %s", h.get("latest_date"))
    log.info("  drv_ma rows for latest:       %s", h.get("drv_ma_rows_latest"))
    log.info("  drv_cat_atomic_input rows:    %s", h.get("drv_cat_atomic_input_rows_latest"))
    fc = h.get("fire_counts", {})
    if fc.get("today"):
        log.info("  fires today (atomic/comp):    %s / %s",
                 fc["today"].get("n_atomic"), fc["today"].get("n_composite"))
    return h


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="YYYY-MM-DD — defaults to latest snapshot")
    p.add_argument("--no-refresh", action="store_true",
                   help="Skip step 1 (workbook → ref_trig_* refresh)")
    p.add_argument("--no-derive", action="store_true",
                   help="Skip step 2 (derive_all)")
    args = p.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD is empty in .env"); return 2

    if not args.no_refresh:
        _step_refresh_refs()
    else:
        log.info("STEP 1/3 — refresh skipped (--no-refresh)")

    if not args.no_derive:
        target = _resolve_target_date(args.date)
        _step_derive(target)
    else:
        log.info("STEP 2/3 — derive skipped (--no-derive)")

    h = _step_health()
    return 0 if h["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
