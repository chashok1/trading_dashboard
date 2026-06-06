"""Firing-based outcome ETL (Phase 4).

Validates each rule FIRING against how the stock actually performed afterward —
independent of user_action_log (which is empty / column-drifted). ADDITIVE: only
writes the drv_rule_outcome table; never touches rules, param sets, or derives.

Forward returns
    Per (tos_symbol, as_of_date), the 5- and 20-trading-day forward % change of
    drv_ma.last_price, via LEAD over each symbol's date-ordered prices. The most
    recent ~20 dates have no 20d label yet (excluded) — correct.

Rows written
    composite : one per (composite_rule_code, symbol, date) where drv_trig.triggered.
                action_code = BUY/SELL from the code prefix; hit by direction vs
                ref_settings thresholds.
    atomic    : one per (atomic_rule_id, symbol, date) where the rule's feature
                column in drv_cat_atomic_input is non-null — so the tuner can fit a
                threshold across the full feature range. hit = fwd_20d_pct > 0
                (placeholder; the sweep tuner uses fwd_20d_pct directly, not hit).

Run:
    python -m etl.compute_firing_outcomes              # populate (idempotent upsert)
    python -m etl.compute_firing_outcomes --truncate   # clear table first
    python -m etl.compute_firing_outcomes --atomic-only / --composite-only
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
log = logging.getLogger("etl.compute_firing_outcomes")

BUY_PREFIX = r'^\d+-(B|BS|BR|BW|BM|BMN)-'


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
    """Materialize _fwd(tos_symbol, as_of_date, fwd5, fwd20) for all derived dates."""
    s.execute(text("DROP TABLE IF EXISTS _fwd"))
    s.execute(text("""
        CREATE TEMP TABLE _fwd AS
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
    s.execute(text("CREATE INDEX ON _fwd (tos_symbol, as_of_date)"))
    n = s.execute(text("SELECT COUNT(*) FROM _fwd WHERE fwd20 IS NOT NULL")).scalar()
    log.info("_fwd built: %s rows with a 20d forward return", n)
    return n


def _composite_outcomes(s, settings):
    buy_thr = settings.get("outcome_hit_threshold_buy", 0.5)
    sell_thr = settings.get("outcome_hit_threshold_sell", -0.5)
    res = s.execute(text(f"""
        INSERT INTO drv_rule_outcome
            (rule_id, rule_kind, as_of_date, tos_symbol, action_code, fwd_5d_pct, fwd_20d_pct, hit)
        SELECT t.composite_rule_code, 'composite', t.as_of_date, t.tos_symbol,
               CASE WHEN t.composite_rule_code ~ '{BUY_PREFIX}' THEN 'BUY' ELSE 'SELL' END,
               f.fwd5, f.fwd20,
               CASE WHEN t.composite_rule_code ~ '{BUY_PREFIX}' THEN (f.fwd20 >= :buy)
                    ELSE (f.fwd20 <= :sell) END
        FROM drv_trig t
        JOIN _fwd f ON f.tos_symbol = t.tos_symbol AND f.as_of_date = t.as_of_date
        WHERE t.triggered = TRUE AND f.fwd20 IS NOT NULL
        ON CONFLICT (rule_id, as_of_date, tos_symbol) DO UPDATE SET
            rule_kind = EXCLUDED.rule_kind, action_code = EXCLUDED.action_code,
            fwd_5d_pct = EXCLUDED.fwd_5d_pct, fwd_20d_pct = EXCLUDED.fwd_20d_pct, hit = EXCLUDED.hit
    """), {"buy": buy_thr, "sell": sell_thr})
    log.info("composite outcomes upserted: %s", res.rowcount)


def _valid_columns(s) -> set:
    return set(s.execute(text("""
        SELECT column_name FROM information_schema.columns WHERE table_name='drv_cat_atomic_input'
    """)).scalars().all())


def _atomic_feature_cols(s, valid) -> dict:
    rows = s.execute(text("""
        SELECT a.atomic_rule_id, c.column_name
        FROM ref_trig_atomic_rule a
        JOIN ref_ma_columns c
          ON c.column_name = a.rule_name AND c.drv_cat_table = 'drv_cat_atomic_input'
        WHERE a.deprecated_at IS NULL
    """)).all()
    out = {}
    for rid, col in rows:
        if col in valid and rid not in out:
            out[rid] = col
    return out


def _atomic_outcomes(s):
    valid = _valid_columns(s)
    feats = _atomic_feature_cols(s, valid)
    log.info("atomic rules resolved to feature columns: %d", len(feats))
    total = 0
    for rid, col in sorted(feats.items()):
        res = s.execute(text(f"""
            INSERT INTO drv_rule_outcome
                (rule_id, rule_kind, as_of_date, tos_symbol, action_code, fwd_5d_pct, fwd_20d_pct, hit)
            SELECT :rid, 'atomic', ci.as_of_date, ci.tos_symbol, NULL, f.fwd5, f.fwd20, (f.fwd20 > 0)
            FROM drv_cat_atomic_input ci
            JOIN _fwd f ON f.tos_symbol = ci.tos_symbol AND f.as_of_date = ci.as_of_date
            WHERE ci."{col}" IS NOT NULL AND f.fwd20 IS NOT NULL
            ON CONFLICT (rule_id, as_of_date, tos_symbol) DO UPDATE SET
                fwd_5d_pct = EXCLUDED.fwd_5d_pct, fwd_20d_pct = EXCLUDED.fwd_20d_pct, hit = EXCLUDED.hit
        """), {"rid": str(rid)})
        total += res.rowcount or 0
    log.info("atomic outcomes upserted: %s rows across %d rules", total, len(feats))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--truncate", action="store_true", help="Clear drv_rule_outcome first")
    p.add_argument("--atomic-only", action="store_true")
    p.add_argument("--composite-only", action="store_true")
    args = p.parse_args()

    with session_scope() as s:
        if args.truncate:
            s.execute(text("TRUNCATE drv_rule_outcome"))
            log.info("drv_rule_outcome truncated")
        settings = _settings(s)
        _build_fwd_returns(s)
        if not args.atomic_only:
            _composite_outcomes(s, settings)
        if not args.composite_only:
            _atomic_outcomes(s)
        s.commit()
        n = s.execute(text("SELECT COUNT(*) FROM drv_rule_outcome")).scalar()
        log.info("drv_rule_outcome now has %s rows", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
