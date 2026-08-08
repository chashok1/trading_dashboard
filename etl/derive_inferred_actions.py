"""derive_inferred_actions — TASK_121: infer BUY/SELL trades from CS/F
position-snapshot deltas. NOT a manual log: qty deltas between consecutive
hist_cs / hist_f snapshots per (account, tos_symbol) ARE the user's real
trades (see docs memory: feedback loop must use hist_f/hist_cs position
diffs, never manual ACT-button logging).

For each consecutive snapshot pair per source (CS=hist_cs, F=hist_f):
  - qty decrease -> SELL, qty increase -> BUY;
  - deltas whose |est_dollar| < ref_settings.inferred_action_min_dollar
    (default 100) are skipped (dividend-reinvest noise);
  - a delta whose qty ratio sits near a clean split multiple (2x, 3x, ...)
    while the position's dollar value is ~unchanged is treated as a stock
    split, not a trade -> skipped + a warning logged;
  - stance vs that date's drv_actionable.consolidated_action:
      FOLLOWED     - inferred direction matches the recommendation's family
                     (BUY<->ADD/INCREASE, SELL<->REDUCE/REMOVE)
      CONTRADICTED - inferred direction opposes the recommendation's family
      NO_SIGNAL    - no actionable row / recommendation was HOLD or none
  - fwd_5d_pct / fwd_20d_pct from drv_ma.last_price (same LEAD-based
    convention as etl/compute_firing_outcomes.py); NULL until enough
    forward history exists.

Idempotent per date range: DELETE WHERE as_of_date IN <recomputed dates>
then INSERT.

Two modes:
  - incremental (default): diffs only the newest 2 snapshots per source —
    cheap, safe to call from derive_all() on every load.
  - full_history=True: diffs every consecutive snapshot pair in history —
    for the one-time backfill: `python -m etl.derive_inferred_actions --full`.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_inferred_actions")

# Buy-side / sell-side action families for stance classification.
_BUY_FAMILY  = {"ADD", "INCREASE", "BS", "BM", "BMN"}
_SELL_FAMILY = {"REMOVE", "REDUCE", "SA", "SS", "STM", "OVER_MAX", "SO"}

# How many calendar days to look back from the trade date for the nearest
# drv_actionable recommendation (mirrors etl/derive_position_action.py).
_ACTIONABLE_LOOKBACK_DAYS = 5

# Common whole-number split ratios (and their reciprocals) to guard against.
_SPLIT_RATIOS = (2, 3, 4, 5, 7, 10, 20)


def _is_probable_split(qty_ratio: Optional[float], value_ratio: Optional[float]) -> bool:
    """True when the qty change looks like a stock split, not a trade:
    the qty ratio is near a clean split multiple while the position's
    dollar value barely moved (within 5%)."""
    if qty_ratio is None or value_ratio is None:
        return False
    if abs(value_ratio - 1.0) > 0.05:
        return False
    for r in _SPLIT_RATIOS:
        if abs(qty_ratio - r) < 0.02 * r or abs(qty_ratio - (1.0 / r)) < 0.02 * (1.0 / r):
            return True
    return False


def _ref_setting(session: Session, name: str, default: str) -> str:
    row = session.execute(
        text("SELECT setting_value FROM ref_settings WHERE setting_name = :n"),
        {"n": name},
    ).first()
    return row[0] if row and row[0] is not None else default


def _snapshot_dates(session: Session, table: str) -> list[date]:
    rows = session.execute(
        text(f"SELECT DISTINCT snapshot_date FROM {table} ORDER BY snapshot_date")
    ).fetchall()
    return [r[0] for r in rows]


_SRC_CFG = {
    "CS": dict(table="hist_cs", acct="account", qty="qty",
               price="price", val="market_value"),
    "F":  dict(table="hist_f", acct="account_number", qty="qty",
               price="last_price", val="current_value"),
}


def _diff_pair(session: Session, source_feed: str, prev_d: date, curr_d: date) -> list[dict]:
    """Diff one consecutive snapshot pair for one source; returns raw deltas
    (qty_delta, est_dollar, prev/curr qty+val) per (account, tos_symbol)."""
    c = _SRC_CFG[source_feed]
    sql = text(f"""
        WITH prev AS (
            SELECT {c['acct']} AS account, COALESCE(tos_symbol, symbol) AS sym,
                   {c['qty']} AS qty, {c['val']} AS val, {c['price']} AS price
            FROM {c['table']} WHERE snapshot_date = :prev
              AND {c['acct']} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        ),
        curr AS (
            SELECT {c['acct']} AS account, COALESCE(tos_symbol, symbol) AS sym,
                   {c['qty']} AS qty, {c['val']} AS val, {c['price']} AS price
            FROM {c['table']} WHERE snapshot_date = :curr
              AND {c['acct']} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        )
        SELECT COALESCE(p.account, c.account) AS account,
               COALESCE(p.sym, c.sym)         AS sym,
               COALESCE(p.qty, 0)             AS prev_qty,
               COALESCE(c.qty, 0)             AS curr_qty,
               p.val AS prev_val, c.val AS curr_val,
               COALESCE(c.price, p.price)     AS price
        FROM prev p FULL OUTER JOIN curr c
             ON c.account = p.account AND c.sym = p.sym
    """)
    return [dict(r) for r in session.execute(
        sql, {"prev": prev_d, "curr": curr_d}
    ).mappings().all()]


def _stance(inferred_action: str, rec_action: Optional[str]) -> str:
    if not rec_action:
        return "NO_SIGNAL"
    ca = rec_action.upper()
    if inferred_action == "BUY":
        if ca in _BUY_FAMILY:  return "FOLLOWED"
        if ca in _SELL_FAMILY: return "CONTRADICTED"
    else:
        if ca in _SELL_FAMILY: return "FOLLOWED"
        if ca in _BUY_FAMILY:  return "CONTRADICTED"
    return "NO_SIGNAL"


def _batch_rec_actions(session: Session, syms: list[str], curr_d: date) -> dict[str, Optional[str]]:
    """One query per snapshot pair (not per row): nearest drv_actionable
    consolidated_action within the lookback window, per symbol."""
    if not syms:
        return {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (tos_symbol) tos_symbol, consolidated_action
        FROM drv_actionable
        WHERE tos_symbol = ANY(:syms) AND as_of_date BETWEEN :lo AND :hi
        ORDER BY tos_symbol, as_of_date DESC
    """), {
        "syms": syms,
        "lo": curr_d - timedelta(days=_ACTIONABLE_LOOKBACK_DAYS),
        "hi": curr_d,
    }).fetchall()
    return {r[0]: r[1] for r in rows}


def _build_rows_for_pair(session: Session, source_feed: str, prev_d: date,
                         curr_d: date, min_dollar: float) -> list[dict]:
    deltas = []
    for d in _diff_pair(session, source_feed, prev_d, curr_d):
        sym = (d["sym"] or "").strip().upper()
        account = d["account"]
        if not sym or not account:
            continue
        prev_qty = float(d["prev_qty"] or 0)
        curr_qty = float(d["curr_qty"] or 0)
        qty_delta = curr_qty - prev_qty
        if qty_delta == 0:
            continue
        price = float(d["price"]) if d["price"] is not None else None
        if price is None or price <= 0:
            continue
        est_dollar = qty_delta * price
        if abs(est_dollar) < min_dollar:
            continue
        qty_ratio = (curr_qty / prev_qty) if prev_qty else None
        prev_val = float(d["prev_val"]) if d["prev_val"] is not None else None
        curr_val = float(d["curr_val"]) if d["curr_val"] is not None else None
        value_ratio = (curr_val / prev_val) if (prev_val and curr_val is not None) else None
        if _is_probable_split(qty_ratio, value_ratio):
            log.warning("derive_inferred_actions: %s/%s %s qty %s->%s looks "
                        "like a split (value ~unchanged) — skipped",
                        source_feed, account, sym, prev_qty, curr_qty)
            continue
        deltas.append((sym, account, qty_delta, est_dollar))
    if not deltas:
        return []
    rec_map = _batch_rec_actions(session, sorted({sym for sym, *_ in deltas}), curr_d)
    rows = []
    for sym, account, qty_delta, est_dollar in deltas:
        inferred_action = "BUY" if qty_delta > 0 else "SELL"
        rec_action = rec_map.get(sym)
        stance = _stance(inferred_action, rec_action)
        rows.append({
            "d": curr_d, "sym": sym, "acct": account, "src": source_feed,
            "qd": round(qty_delta, 6), "est": round(est_dollar, 2),
            "ia": inferred_action, "rec": rec_action, "st": stance,
        })
    return rows


def _write_forward_returns(session: Session, dates: list[date]) -> None:
    """Backfill fwd_5d_pct/fwd_20d_pct on the rows just written, using the
    same LEAD-over-drv_ma.last_price convention as compute_firing_outcomes."""
    if not dates:
        return
    session.execute(text("DROP TABLE IF EXISTS _fwd_ia"))
    session.execute(text("""
        CREATE TEMP TABLE _fwd_ia AS
        WITH px AS (
            SELECT tos_symbol, as_of_date, last_price,
                   LEAD(last_price, 5)  OVER w AS p5,
                   LEAD(last_price, 20) OVER w AS p20
            FROM drv_ma WHERE last_price IS NOT NULL
            WINDOW w AS (PARTITION BY tos_symbol ORDER BY as_of_date)
        )
        SELECT tos_symbol, as_of_date,
               CASE WHEN last_price > 0 AND p5  IS NOT NULL
                    THEN (p5  - last_price) / last_price * 100 END AS fwd5,
               CASE WHEN last_price > 0 AND p20 IS NOT NULL
                    THEN (p20 - last_price) / last_price * 100 END AS fwd20
        FROM px
    """))
    session.execute(text("CREATE INDEX ON _fwd_ia (tos_symbol, as_of_date)"))
    session.execute(text("""
        UPDATE drv_inferred_action ia
        SET fwd_5d_pct = f.fwd5, fwd_20d_pct = f.fwd20
        FROM _fwd_ia f
        WHERE f.tos_symbol = ia.tos_symbol AND f.as_of_date = ia.as_of_date
          AND ia.as_of_date = ANY(:dates)
    """), {"dates": dates})


def _write_rows(session: Session, rows: list[dict]) -> int:
    """Idempotent bulk write: one DELETE covering every recomputed date, one
    INSERT, one forward-return backfill pass — not per snapshot pair, so a
    full-history run doesn't pay per-pair temp-table/DELETE overhead 400+
    times over."""
    if not rows:
        return 0
    dates = sorted({r["d"] for r in rows})
    session.execute(
        text("DELETE FROM drv_inferred_action WHERE as_of_date = ANY(:dates)"),
        {"dates": dates},
    )
    session.execute(text("""
        INSERT INTO drv_inferred_action
            (as_of_date, tos_symbol, account, source_feed, qty_delta,
             est_dollar, inferred_action, rec_action, stance)
        VALUES (:d, :sym, :acct, :src, :qd, :est, :ia, :rec, :st)
        ON CONFLICT (as_of_date, tos_symbol, account) DO UPDATE SET
            source_feed = EXCLUDED.source_feed, qty_delta = EXCLUDED.qty_delta,
            est_dollar = EXCLUDED.est_dollar, inferred_action = EXCLUDED.inferred_action,
            rec_action = EXCLUDED.rec_action, stance = EXCLUDED.stance
    """), rows)
    _write_forward_returns(session, dates)
    return len(rows)


def _derive_impl(session: Session, full_history: bool) -> int:
    min_dollar = float(_ref_setting(session, "inferred_action_min_dollar", "100"))
    all_rows: list[dict] = []
    for source_feed in ("CS", "F"):
        table = _SRC_CFG[source_feed]["table"]
        snaps = _snapshot_dates(session, table)
        if len(snaps) < 2:
            continue
        pairs = list(zip(snaps[:-1], snaps[1:])) if full_history else [(snaps[-2], snaps[-1])]
        for prev_d, curr_d in pairs:
            all_rows.extend(_build_rows_for_pair(session, source_feed, prev_d, curr_d, min_dollar))
    return _write_rows(session, all_rows)


def derive_inferred_actions(session: Session, as_of_date: Optional[date] = None,
                            parent_run_id: Optional[int] = None,
                            full_history: bool = False) -> int:
    from etl._derive_common import _open_drv_run, _close_drv_run
    run_date = as_of_date or date.today()
    run_id = _open_drv_run(session, "drv_inferred_action", run_date, parent_run_id)
    try:
        n = _derive_impl(session, full_history)
        _close_drv_run(session, run_id, rows_built=n)
        log.info("drv_inferred_action: %d rows (full_history=%s)", n, full_history)
        return n
    except Exception as exc:
        log.exception("derive_inferred_actions failed: %s", exc)
        try:
            _close_drv_run(session, run_id, rows_built=0, status="error", error_msg=str(exc)[:500])
        except Exception:
            pass
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full", action="store_true",
                  help="Diff every consecutive snapshot pair in history (one-time backfill)")
    args = p.parse_args()
    from etl.db import session_scope
    from etl._logging import setup_logging
    setup_logging()
    with session_scope() as s:
        n = derive_inferred_actions(s, full_history=args.full)
        s.commit()
        print(f"drv_inferred_action: {n} rows written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
