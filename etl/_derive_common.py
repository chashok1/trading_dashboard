"""
Shared helpers for the derive pipeline.

Extracted from etl/derive.py on 2026-05-12 so that both etl/derive.py and
etl/derive_v2.py can import them without creating a circular dependency.
(Previously, derive_v2 inlined its own copies because derive.py imported
from derive_v2 at the bottom of the file; that bottom-of-file monkeypatch
is now gone.)

Three building blocks:
  * _open_drv_run  — insert a meta_derived_run row with status='running'
  * _close_drv_run — update the row with rows_built, status, and any error
  * _wrap          — decorator that opens the run, calls the deriver, closes
                     the run, and propagates exceptions
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from etl.db import get_table

log = logging.getLogger("etl.derive")


def _open_drv_run(session: Session, target: str, as_of_date: date,
                  parent_run_id: Optional[int] = None) -> int:
    """Insert a meta_derived_run row and return its run_id."""
    table = get_table("meta_derived_run")
    rid = session.execute(
        table.insert().values(
            as_of_date=as_of_date,
            target_table=target,
            status="running",
            parent_run_id=parent_run_id,
        ).returning(table.c.run_id)
    ).scalar_one()
    return rid


def _close_drv_run(session: Session, run_id: int, *, rows_built: int = 0,
                   status: str = "success", error_msg: Optional[str] = None) -> None:
    """Update a meta_derived_run row with the final state."""
    if not run_id:
        return
    table = get_table("meta_derived_run")
    session.execute(
        table.update()
        .where(table.c.run_id == run_id)
        .values(
            finished_at=datetime.now(),
            rows_built=rows_built,
            status=status,
            error_msg=error_msg,
        )
    )


def _wrap(target: str, fn):
    """Decorator: open run, call fn, close run, propagate exceptions."""
    def runner(session: Session, as_of_date: date, parent_run_id: Optional[int] = None):
        rid = _open_drv_run(session, target, as_of_date, parent_run_id)
        try:
            n = fn(session, as_of_date, rid)
            _close_drv_run(session, rid, rows_built=n)
            log.info("%s @ %s: %d rows", target, as_of_date, n)
            return n
        except Exception as e:
            _close_drv_run(session, rid, rows_built=0, status="error",
                           error_msg=str(e)[:500])
            raise
    return runner
