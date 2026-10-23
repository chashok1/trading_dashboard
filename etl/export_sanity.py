"""Post-load sanity check on TOS exports (TOSD / TOSL).

A bad export (2026-10-22 TOSD: low/high = 0 for 600 of 639 symbols) silently
corrupts derives (a 0 low fakes "low below LRR"). After a TOSD/TOSL load this
counts zero low/high rows in the newest (export_date, sequence) batch and, when
the share is abnormal, records ONE warning in meta_warning (screen
'export-sanity', shown by the topbar badge). A later clean check for the same
date clears it. Never raises: a failed check must not break the load.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from etl.warnings import add_warning, clear_screen_warnings

log = logging.getLogger(__name__)

SCREEN = "export-sanity"
CODE = "zero_low_export"
THRESHOLD = 0.10  # normal days run ~1%; the bad 10/22 file was 94%
_TABLE = {"TOSD": "hist_td", "TOSL": "hist_tl"}


def check_zero_lows(session, file_type: str) -> dict | None:
    table = _TABLE.get(file_type.upper())
    if table is None:
        return None
    try:
        d, seq = session.execute(text(
            f"SELECT export_date, sequence FROM {table} "
            f"ORDER BY export_date DESC, sequence DESC LIMIT 1"
        )).one()
        n, bad = session.execute(text(
            f"SELECT count(*), "
            f"count(*) FILTER (WHERE COALESCE(low_price,0)=0 OR COALESCE(high_price,0)=0) "
            f"FROM {table} WHERE export_date=:d AND sequence=:q"
        ), {"d": d, "q": seq}).one()
        clear_screen_warnings(session, SCREEN, d)
        if n and bad / n > THRESHOLD:
            add_warning(
                session, SCREEN, as_of_date=d, severity="error", code=CODE,
                message=(f"{file_type} {d}: {bad} of {n} symbols have a zero "
                         f"low/high - bad export. Delete that date's {table} rows "
                         f"(sequence {seq}), re-export from TOS, reload, then re-derive."))
            log.warning("%s %s: %d/%d zero low/high rows", file_type, d, bad, n)
        return {"date": d, "rows": n, "bad": bad}
    except Exception:
        log.exception("export sanity check failed (continuing)")
        return None
