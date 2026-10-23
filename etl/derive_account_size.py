"""Per-account min / max / unit sizes (TASK_151; DESIGN_SPEC_3 P1).

For every trading account (ref_accounts.size_mult > 0, active) and every
symbol with a sizing category in drv_actionable:

    account min/max/unit = category pct x account value x size_mult

rounded to the nearest $1,000 (exactly $500 rounds up; anything above $0
never goes below $1,000). Raw and rounded amounts are both stored, plus the
account's own held dollars in the symbol and an over-max flag.

ADDITIVE ONLY: nothing here touches drv_actionable, the Final Call,
suggested_target_dollar or target_min/max_dollar (household sizing).

Account value = latest position-file total per account on or before the
position ceiling (Schwab hist_cs.market_value, Fidelity hist_f.current_value,
cash and money market included). An account whose latest file is more than
5 trading days old gets no rows. Neutral / Other categories carry 0 pct, so
their sizes are $0.

Idempotent: DELETE WHERE as_of_date=D then INSERT. tos_symbol only.
Runs in derive_all right after derive_actionable.
"""
import logging
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import position_ceiling

log = logging.getLogger(__name__)

_HOUSEHOLD_BASE = Decimal("400000")   # the old fixed base behind units_pct
_STALE_TRADING_DAYS = 5
_ONE_K = Decimal("1000")


def round_to_k(x: Decimal) -> Decimal:
    """Nearest $1,000, .5 rounds up; any positive amount is at least $1,000."""
    if x is None or x <= 0:
        return Decimal(0)
    r = ((x / _ONE_K) + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR) * _ONE_K
    return r if r >= _ONE_K else _ONE_K


def _dec(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal(0)


def _load_accounts(session: Session) -> dict:
    """{short_name: {'mult': Decimal, 'cs': [acct...], 'f': [acct...]}} for active
    trading accounts. Rows sharing a short name (two HSA labels) are one account."""
    out: dict = {}
    for r in session.execute(text("""
        SELECT account_number, short_name, source, size_mult
        FROM ref_accounts
        WHERE is_active AND size_mult > 0 AND short_name IS NOT NULL
          AND account_number <> '85911'
    """)).fetchall():
        a = out.setdefault(r[1], {"mult": Decimal(0), "cs": [], "f": []})
        a["mult"] = max(a["mult"], _dec(r[3]))
        (a["cs"] if r[2] == "CS" else a["f"]).append(r[0])
    return out


def _account_snapshot(session: Session, acct: dict, ceil: date, anchor: date):
    """Return (value_date, total, {tos_symbol: dollars}) or None if no fresh file."""
    if acct["cs"]:
        tbl, acol, vcol, accts = "hist_cs", "account", "market_value", acct["cs"]
    elif acct["f"]:
        tbl, acol, vcol, accts = "hist_f", "account_number", "current_value", acct["f"]
    else:
        return None
    snap = session.execute(text(
        f"SELECT MAX(snapshot_date) FROM {tbl} "
        f"WHERE {acol} = ANY(:a) AND snapshot_date <= :c"),
        {"a": accts, "c": ceil}).scalar()
    if snap is None:
        return None
    # trading days between the file and the anchor (hist_td export dates)
    gap = session.execute(text(
        "SELECT COUNT(DISTINCT export_date) FROM hist_td "
        "WHERE export_date > :s AND export_date <= :d"),
        {"s": snap, "d": anchor}).scalar() or 0
    if gap > _STALE_TRADING_DAYS:
        return None
    rows = session.execute(text(
        f"SELECT tos_symbol, SUM({vcol}) FROM {tbl} "
        f"WHERE {acol} = ANY(:a) AND snapshot_date = :s GROUP BY tos_symbol"),
        {"a": accts, "s": snap}).fetchall()
    held = {r[0]: _dec(r[1]) for r in rows if r[0]}
    total = sum((_dec(r[1]) for r in rows), Decimal(0))
    return snap, total, held


def household_alloc(session: Session, as_of_date: date) -> dict:
    """{CATEGORY_UPPER: {'min_dollar','max_dollar','units'}} = per-account sizes
    (same formula and $1,000 rounding as drv_account_size) summed over the active
    trading accounts. The household sizing in derive_actionable compares ALL-account
    holdings, so its floor/max/unit must be the all-account sum, not one account's
    size (ref_asset_allocation's dollar columns are single-account scale).
    Categories with a zero sum are omitted so the caller keeps its old values."""
    accounts = _load_accounts(session)
    ceil = position_ceiling(session, as_of_date)
    totals = []
    for acct in accounts.values():
        snap = _account_snapshot(session, acct, ceil, as_of_date)
        if snap is not None:
            totals.append(snap[1] * acct["mult"])
    out: dict = {}
    for r in session.execute(text(
            "SELECT category, min_pct, max_pct, units_pct, units FROM ref_asset_allocation")).fetchall():
        units_pct = r[3] if r[3] is not None else (
            _dec(r[4]) / _HOUSEHOLD_BASE if r[4] is not None else Decimal(0))
        mn = sum((round_to_k(b * _dec(r[1])) for b in totals), Decimal(0))
        mx = sum((round_to_k(b * _dec(r[2])) for b in totals), Decimal(0))
        un = sum((round_to_k(b * _dec(units_pct)) for b in totals), Decimal(0))
        if mx > 0:
            out[str(r[0] or "").strip().upper()] = {
                "min_dollar": float(mn), "max_dollar": float(mx), "units": float(un)}
    return out


def _derive_account_size_impl(session: Session, as_of_date: date, run_id=None) -> int:
    d = as_of_date
    session.execute(text("DELETE FROM drv_account_size WHERE as_of_date = :d"), {"d": d})

    accounts = _load_accounts(session)
    alloc = {}
    for r in session.execute(text(
            "SELECT category, min_pct, max_pct, units_pct, units FROM ref_asset_allocation")).fetchall():
        units_pct = r[3] if r[3] is not None else (
            _dec(r[4]) / _HOUSEHOLD_BASE if r[4] is not None else Decimal(0))
        alloc[str(r[0] or "").strip().upper()] = (_dec(r[1]), _dec(r[2]), _dec(units_pct))

    ceil = position_ceiling(session, d)
    syms = session.execute(text(
        "SELECT tos_symbol, position_category FROM drv_actionable "
        "WHERE as_of_date = :d AND position_category IS NOT NULL"), {"d": d}).fetchall()

    out = []
    for short, acct in accounts.items():
        snap = _account_snapshot(session, acct, ceil, d)
        if snap is None:
            log.warning("derive_account_size %s: no fresh position file for %s (no rows)", d, short)
            continue
        vdate, total, held = snap
        mult = acct["mult"]
        for sym, cat in syms:
            pct = alloc.get(str(cat).strip().upper())
            if pct is None:
                continue
            base = total * mult
            mn, mx, un = base * pct[0], base * pct[1], base * pct[2]
            rmx = round_to_k(mx)
            h = held.get(sym, Decimal(0))
            out.append({
                "d": d, "sym": sym, "acct": short, "cat": cat, "val": total, "mult": mult,
                "vd": vdate, "mnr": mn, "mxr": mx, "unr": un,
                "mn": round_to_k(mn), "mx": rmx, "un": round_to_k(un),
                "held": h, "over": bool(rmx > 0 and h > rmx),
            })
    if out:
        session.execute(text("""
            INSERT INTO drv_account_size
              (as_of_date, tos_symbol, account_short, category, account_value, size_mult,
               value_date, min_raw, max_raw, unit_raw, min_dollar, max_dollar, unit_dollar,
               held_dollar, over_max)
            VALUES
              (:d, :sym, :acct, :cat, :val, :mult, :vd, :mnr, :mxr, :unr, :mn, :mx, :un,
               :held, :over)
        """), out)
    session.commit()
    log.info("derive_account_size @ %s: %d rows (%d accounts)", d, len(out), len(accounts))
    return len(out)


def derive_account_size(session: Session, as_of_date: date,
                        parent_run_id: Optional[int] = None) -> int:
    """derive_all() call-site signature (session, as_of_date, parent_run_id)."""
    return _derive_account_size_impl(session, as_of_date)
