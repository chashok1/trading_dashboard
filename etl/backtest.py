"""
Replay the rules engine over historical snapshots.

Reads pre-computed drv_stks + drv_ma rows and produces, for each rule:
  - fire_count  — number of (date, symbol) where the rule fired
  - hit_rate_5d / hit_rate_20d
  - avg_fwd_5d / avg_fwd_20d, median_fwd_5d / median_fwd_20d
  - sample_size_5d / sample_size_20d

This is a SIGNAL backtest, not a position backtest. It tells you whether a
rule, when it fired historically, was followed by a forward move in the
direction the rule implies — not what would have happened if you sized into
the position.

Usage:
    python -m etl.backtest                              # all rules, last 180 days
    python -m etl.backtest --rule-code BM-Momentum-Up   # one composite
    python -m etl.backtest --rule-id 123                # one atomic
    python -m etl.backtest --from 2026-01-01 --to 2026-04-30
    python -m etl.backtest --window 60                  # forward window override
    python -m etl.backtest --json out.json              # write JSON instead of printing
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import text

# Make `python -m etl.backtest` work even if PYTHONPATH isn't set
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from etl.db import session_scope  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.backtest")


def _hit_for(direction: str, fwd: Optional[float], threshold: float) -> Optional[bool]:
    """direction: 'bull' (need return >= threshold) or 'bear' (return <= -threshold)."""
    if fwd is None:
        return None
    if direction == "bull":
        return fwd >= threshold
    return fwd <= -threshold


def _forward_return(session, symbol: str, as_of: date, days: int) -> Optional[float]:
    start = session.execute(text(
        "SELECT last_price FROM drv_ma WHERE symbol=:s AND as_of_date=:d LIMIT 1"
    ), {"s": symbol, "d": as_of}).scalar()
    if not start:
        return None
    target = session.execute(text("""
        SELECT MIN(as_of_date) FROM drv_ma
        WHERE as_of_date > :d AND symbol = :s
          AND as_of_date >= :d + (:dd || ' days')::interval
    """), {"d": as_of, "s": symbol, "dd": str(days)}).scalar()
    if not target:
        return None
    end = session.execute(text(
        "SELECT last_price FROM drv_ma WHERE symbol=:s AND as_of_date=:d LIMIT 1"
    ), {"s": symbol, "d": target}).scalar()
    if not end or float(start) == 0:
        return None
    return ((float(end) - float(start)) / float(start)) * 100.0


def _direction_for_rule(rule_id: str, kind: str, session) -> str:
    """Infer 'bull' or 'bear' from the rule definition.

    Simple heuristic: if any composite rule code starts with SA/STM/SS/REMOVE
    or category contains 'sell/bear/down', treat as bear. BM/ADD/INCREASE or
    'buy/bull/up' → bull. Default bull.
    """
    if kind == "atomic":
        row = session.execute(text("""
            SELECT category FROM ref_trig_atomic_rule WHERE atomic_rule_id::text = :rid
        """), {"rid": rule_id}).first()
        cat = (row[0] if row else "") or ""
    else:
        row = session.execute(text("""
            SELECT MAX(category) FROM ref_trig_composite_mapping
            WHERE composite_rule_code = :rid
        """), {"rid": rule_id}).first()
        cat = (row[0] if row else "") or ""
    blob = f"{rule_id} {cat}".lower()
    bear_kw = ("sa-", "stm", "ss-", "remove", "reduce", "sell", "bear", "down")
    if any(k in blob for k in bear_kw):
        return "bear"
    return "bull"


def backtest(
    rule_code: Optional[str] = None,
    rule_id: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    windows: tuple[int, ...] = (5, 20),
    hit_threshold_pct: float = 0.5,
) -> dict:
    """Run the backtest. Returns a dict keyed by rule_id."""
    to_date = to_date or date.today()
    from_date = from_date or (to_date - timedelta(days=180))

    log.info("backtest %s → %s, windows=%s, threshold=±%.2f%%",
             from_date, to_date, windows, hit_threshold_pct)

    out: dict = {}
    with session_scope() as s:
        # Build the fire-events list: (date, symbol, rule_id, kind)
        events: list[dict] = []
        if rule_id is not None:
            # Atomic rule events from drv_stks.triggered_atomic_ids
            rows = s.execute(text("""
                SELECT as_of_date, symbol,
                       jsonb_path_query(triggered_atomic_ids,
                                        '$ ? (@.rule_id == $rid)',
                                        jsonb_build_object('rid', :rid::int)) AS hit
                FROM drv_stks
                WHERE as_of_date BETWEEN :f AND :t
            """), {"f": from_date, "t": to_date, "rid": int(rule_id)}).fetchall()
            for r in rows:
                if r[2] is not None:
                    events.append({"d": r[0], "s": r[1],
                                   "rid": str(rule_id), "kind": "atomic"})
        elif rule_code is not None:
            # One composite
            rows = s.execute(text("""
                SELECT as_of_date, symbol
                FROM drv_trig
                WHERE composite_rule_code = :rc
                  AND triggered = TRUE
                  AND as_of_date BETWEEN :f AND :t
            """), {"rc": rule_code, "f": from_date, "t": to_date}).fetchall()
            for r in rows:
                events.append({"d": r[0], "s": r[1],
                               "rid": rule_code, "kind": "composite"})
        else:
            # All composites in window
            rows = s.execute(text("""
                SELECT as_of_date, symbol, composite_rule_code
                FROM drv_trig
                WHERE triggered = TRUE AND as_of_date BETWEEN :f AND :t
            """), {"f": from_date, "t": to_date}).fetchall()
            for r in rows:
                events.append({"d": r[0], "s": r[1],
                               "rid": r[2], "kind": "composite"})

        log.info("found %d fire events", len(events))

        # Aggregate per rule_id
        per_rule: dict = {}
        for ev in events:
            rid = ev["rid"]
            kind = ev["kind"]
            slot = per_rule.setdefault(rid, {
                "rule_id": rid, "kind": kind,
                "fire_count": 0,
                **{f"fwd_{w}": [] for w in windows},
            })
            slot["fire_count"] += 1
            for w in windows:
                fwd = _forward_return(s, ev["s"], ev["d"], w)
                if fwd is not None:
                    slot[f"fwd_{w}"].append(fwd)

        # Direction + summarize
        for rid, slot in per_rule.items():
            direction = _direction_for_rule(rid, slot["kind"], s)
            slot["direction"] = direction
            for w in windows:
                vals = slot.pop(f"fwd_{w}")
                n = len(vals)
                hits = sum(1 for v in vals if _hit_for(direction, v, hit_threshold_pct))
                slot[f"sample_size_{w}d"] = n
                slot[f"hit_rate_{w}d"]    = round(hits / n, 4) if n else None
                slot[f"avg_fwd_{w}d"]     = round(sum(vals) / n, 4) if n else None
                if vals:
                    s_sorted = sorted(vals)
                    mid = len(s_sorted) // 2
                    med = s_sorted[mid] if len(s_sorted) % 2 else \
                        (s_sorted[mid - 1] + s_sorted[mid]) / 2
                    slot[f"median_fwd_{w}d"] = round(med, 4)
                else:
                    slot[f"median_fwd_{w}d"] = None
            out[rid] = slot

    return {
        "from_date": from_date.isoformat(),
        "to_date":   to_date.isoformat(),
        "windows":   list(windows),
        "hit_threshold_pct": hit_threshold_pct,
        "rules":     out,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rule-code", help="Composite rule code to test (omit for all)")
    p.add_argument("--rule-id",   help="Atomic rule id to test (overrides --rule-code)")
    p.add_argument("--from", dest="from_date", help="YYYY-MM-DD (default: 180 days ago)")
    p.add_argument("--to",   dest="to_date",   help="YYYY-MM-DD (default: today)")
    p.add_argument("--window", type=int, action="append",
                   help="Forward window in days. Pass multiple times for multiple windows. "
                        "Default: 5 and 20.")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="Minimum |fwd %%| to count as hit. Default 0.5")
    p.add_argument("--json", help="Write result as JSON to this path instead of printing")
    args = p.parse_args()

    fd = datetime.strptime(args.from_date, "%Y-%m-%d").date() if args.from_date else None
    td = datetime.strptime(args.to_date,   "%Y-%m-%d").date() if args.to_date   else None
    windows = tuple(args.window) if args.window else (5, 20)

    result = backtest(
        rule_code=args.rule_code, rule_id=args.rule_id,
        from_date=fd, to_date=td,
        windows=windows, hit_threshold_pct=args.threshold,
    )

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, default=str))
        print(f"wrote {args.json}")
        return 0

    print(f"\nBacktest {result['from_date']} → {result['to_date']} "
          f"(threshold ±{result['hit_threshold_pct']}%)")
    fmt = "{:<28} {:>6} {:>6} {:>8} {:>8} {:>9} {:>9}"
    print(fmt.format("rule_id", "kind", "fires",
                     "hit5d", "hit20d", "avg5d", "avg20d"))
    print("-" * 80)
    for rid, slot in sorted(result["rules"].items(),
                            key=lambda kv: -(kv[1].get("hit_rate_5d") or 0)):
        print(fmt.format(
            rid[:28], slot["kind"][:6], slot["fire_count"],
            (str(slot["hit_rate_5d"])  if slot["hit_rate_5d"]  is not None else "-"),
            (str(slot["hit_rate_20d"]) if slot["hit_rate_20d"] is not None else "-"),
            (str(slot["avg_fwd_5d"])   if slot["avg_fwd_5d"]   is not None else "-"),
            (str(slot["avg_fwd_20d"])  if slot["avg_fwd_20d"]  is not None else "-"),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
