"""Per-screen UI warnings.

A small, shared store (table ``meta_warning``) for non-fatal problems that a
screen should surface to the user as a notification bar — e.g. a symbol whose
asset_class maps to no ref_asset_allocation row.

Design / conventions:
  * Each warning is tagged with a ``screen`` ('actionable', 'dashboard', ...)
    and optionally an ``as_of_date`` and ``symbol``.
  * Producers (derives, ETL) own their slice: call ``clear_screen_warnings``
    for (screen, as_of_date) at the start of a run, then ``add_warning`` as
    issues are found. This keeps warnings idempotent alongside the derives.
  * Screens read them via GET /api/warnings?screen=...&date=... and render a
    notification bar only when the result is non-empty.

To add warnings for a new screen: pick a stable ``screen`` string, clear +
add from that screen's producer, and call /api/warnings from its page.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

log = logging.getLogger(__name__)


def clear_screen_warnings(session, screen: str, as_of_date=None) -> None:
    """Delete a producer's existing warnings before it rewrites them.

    With ``as_of_date`` set, clears only that date's rows for the screen;
    otherwise clears the screen's date-less rows."""
    if as_of_date is None:
        session.execute(text(
            "DELETE FROM meta_warning WHERE screen = :s AND as_of_date IS NULL"
        ), {"s": screen})
    else:
        session.execute(text(
            "DELETE FROM meta_warning WHERE screen = :s AND as_of_date = :d"
        ), {"s": screen, "d": as_of_date})


def add_warning(session, screen: str, message: str, *, as_of_date=None,
                symbol: str | None = None, severity: str = "warning",
                code: str | None = None) -> None:
    """Record one warning for a screen. Severity: 'info' | 'warning' | 'error'."""
    session.execute(text("""
        INSERT INTO meta_warning
            (screen, as_of_date, tos_symbol, severity, code, message)
        VALUES (:s, :d, :sym, :sev, :code, :msg)
    """), {"s": screen, "d": as_of_date, "sym": symbol,
           "sev": severity, "code": code, "msg": message})


def get_warnings(session, screen: str | None = None, as_of_date=None) -> list[dict]:
    """Return warnings, optionally scoped to one screen.

    With ``as_of_date`` set, returns that date's rows plus any date-less rows.
    Without it, returns each screen's most-recent dated rows plus date-less
    rows — so the notification badge shows only the latest run's warnings."""
    where: list[str] = []
    params: dict = {}
    if screen is not None:
        where.append("w.screen = :s")
        params["s"] = screen
    if as_of_date is not None:
        where.append("(w.as_of_date = :d OR w.as_of_date IS NULL)")
        params["d"] = as_of_date
    else:
        where.append("(w.as_of_date IS NULL OR w.as_of_date = "
                     "(SELECT MAX(as_of_date) FROM meta_warning w2 "
                     "WHERE w2.screen = w.screen AND w2.as_of_date IS NOT NULL))")
    sql = ("SELECT id, screen, as_of_date, tos_symbol, severity, code, "
           "message, created_at FROM meta_warning w")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY screen, symbol NULLS FIRST, id"
    rows = session.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
