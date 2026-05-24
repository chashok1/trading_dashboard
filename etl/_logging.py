"""
Single, project-wide logging setup.

Every ETL entry point (etl/scheduler.py, etl/etl_load.py, etl/cleanup.py,
etl/tickers_initial_load.py, etl/refresh_ref.py, ...) calls
`setup_logging()` once at the top of its `main()` (or as the first statement
when run as a module). Module bodies should NOT call logging.basicConfig
themselves — the first call wins and subsequent ones are silently ignored,
so behavior used to depend on import order.

This module is import-safe (no side effects at import time).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


class DatabaseLoggingHandler(logging.Handler):
    """Custom handler that writes logs to meta_scheduler_log table for scheduler module."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name != "scheduler":
            return
        try:
            from etl.db import session_scope
            from sqlalchemy import text

            message = self.format(record)
            level = record.levelname
            file_name = getattr(record, 'file_name', None)

            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO meta_scheduler_log (logged_at, message, log_level, file_name)
                    VALUES (:logged_at, :message, :log_level, :file_name)
                """), {
                    "logged_at": datetime.now(),
                    "message": message,
                    "log_level": level,
                    "file_name": file_name
                })
                session.commit()
        except Exception:
            pass


def setup_logging(level: int | str | None = None,
                  *,
                  fmt: str = LOG_FMT,
                  date_fmt: str = DATE_FMT) -> None:
    """
    Idempotent root-logger configuration.

    First call wires StreamHandler + format + level. Subsequent calls are
    no-ops (so import-order surprises can't change format mid-run). Level
    can be overridden per call via the LOG_LEVEL env var.

    Examples:
        setup_logging()                 # INFO to stderr, "TS [LEVEL] name: msg"
        setup_logging("DEBUG")          # explicit level
        LOG_LEVEL=WARNING python -m etl.scheduler
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Resolve level
    raw = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")
    if isinstance(raw, str):
        resolved = getattr(logging, raw.upper(), logging.INFO)
    else:
        resolved = int(raw)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=date_fmt))

    root = logging.getLogger()
    # Clear pre-existing handlers so we don't double-log (e.g. when a parent
    # process or a third-party module set its own handler first).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(resolved)

    # Add database handler for scheduler logs ONLY if explicitly enabled.
    # Default: OFF.  The handler opens a new DB session per log message
    # (psycopg connection on Windows has cleanup issues at high rates);
    # this was implicated in silent native crashes in the scheduler.
    # Re-enable with `set TD_DB_LOG=1` in the environment.
    if os.environ.get("TD_DB_LOG", "0") == "1":
        db_handler = DatabaseLoggingHandler()
        db_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=date_fmt))
        scheduler_logger = logging.getLogger("scheduler")
        scheduler_logger.addHandler(db_handler)

    # Quiet the noisier third-party libraries unless explicitly requested.
    for noisy in ("urllib3", "sqlalchemy.engine.Engine", "watchdog"):
        logging.getLogger(noisy).setLevel(max(resolved, logging.WARNING))

    _CONFIGURED = True
