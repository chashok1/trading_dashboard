"""Market-date resolution for position snapshot files (Schwab CS, Fidelity F).

A positions file exported after hours / before the next open belongs to the
last market session, not to the calendar day it was downloaded. Example: a
file downloaded at 12:20 AM on 10/1 carries "10/01/2026" in its Date column
but holds the 9/30 close.

Rule (user, 2026-10-01): a file downloaded before 9:30 AM ET on a trading
day, or any time on a weekend/holiday, belongs to the previous trading day.
Anything downloaded 9:30 AM ET or later on a trading day belongs to that day
(intraday and after-hours). Applies to the LATEST market day only -- an old
file being re-loaded is never shifted, and never replaces existing rows.

Pure helpers (market_date_for, resolve_snapshot_date) take everything as
arguments so they are unit-testable without a DB.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta
from time import monotonic
from typing import Iterable, Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

MARKET_TZ = "America/New_York"
MARKET_OPEN = time(9, 30)
FRESH_DOWNLOAD_HOURS = 24          # older files are treated as backfill: never shifted
WARNING_SCREEN = "ingest"


def _is_session(d: date, holidays: set) -> bool:
    return d.weekday() < 5 and d not in holidays


# ---------------------------------------------------------------------------
# Market calendar -- THE single "is the market open" answer (2026-11-26).
# Full-day closures: ref_holiday. Early (1:00 PM ET) closes: ref_early_close.
# Each helper takes the calendar as an optional argument so it is testable
# without a DB; leave it out to read the saved tables (cached for 1 hour).
# ---------------------------------------------------------------------------

REGULAR_CLOSE = time(16, 0)
CALENDAR_TTL_SEC = 3600
CALENDAR_WARN_DAYS = 120   # warn this long before a saved list runs out
_cal_cache: Optional[tuple] = None   # (loaded_at_monotonic, holidays, early_closes)


def market_calendar() -> tuple[set, dict]:
    """(holiday dates, {early-close date: close time}). A table that cannot be
    read counts as empty (weekday-only behaviour) and is retried next call."""
    global _cal_cache
    if _cal_cache and monotonic() - _cal_cache[0] < CALENDAR_TTL_SEC:
        return _cal_cache[1], _cal_cache[2]
    holidays, early, complete = set(), {}, True
    try:
        from etl.db import session_scope
        with session_scope() as s:
            holidays = {r[0] for r in s.execute(text(
                "SELECT holiday_date FROM ref_holiday")).all()}
    except Exception:
        complete = False
        log.warning("market calendar: could not read ref_holiday", exc_info=True)
    try:
        from etl.db import session_scope
        with session_scope() as s:
            early = {r[0]: r[1] for r in s.execute(text(
                "SELECT close_date, close_time FROM ref_early_close")).all()}
    except Exception:
        complete = False
        log.warning("market calendar: could not read ref_early_close", exc_info=True)
    if complete:
        _cal_cache = (monotonic(), holidays, early)
    return holidays, early


def is_trading_day(d: Optional[date] = None,
                   holidays: Optional[Iterable[date]] = None) -> bool:
    """True when the market trades on `d` (default: today, ET)."""
    d = d or _now_et().date()
    hol = market_calendar()[0] if holidays is None else set(holidays)
    return _is_session(d, hol)


def close_time(d: Optional[date] = None, early: Optional[dict] = None) -> time:
    """Regular-session closing time (ET) for `d`: 16:00 unless an early close."""
    d = d or _now_et().date()
    early = market_calendar()[1] if early is None else early
    return early.get(d, REGULAR_CLOSE)


def calendar_expiry_warnings(today: Optional[date] = None,
                             holidays: Optional[Iterable[date]] = None,
                             early: Optional[dict] = None) -> list[str]:
    """One message per saved list whose last date is under CALENDAR_WARN_DAYS
    away (or that is empty). Nothing fetches these dates; they are typed in."""
    today = today or _now_et().date()
    if holidays is None or early is None:
        saved_hol, saved_early = market_calendar()
        holidays = saved_hol if holidays is None else holidays
        early = saved_early if early is None else early
    out = []
    for name, table, dates in (("Market holiday", "ref_holiday", holidays),
                               ("Early-close", "ref_early_close", early)):
        last = max(dates, default=None)
        if last is None:
            out.append(f"{name} list is empty: add dates to {table}.")
        elif (last - today).days < CALENDAR_WARN_DAYS:
            out.append(f"{name} list ends {last:%m/%d/%Y}: add the next year's "
                       f"NYSE dates to {table}.")
    return out


def previous_trading_day(d: date, holidays: Optional[Iterable[date]] = None) -> date:
    """The last trading day strictly before `d`."""
    hol = market_calendar()[0] if holidays is None else set(holidays)
    d -= timedelta(days=1)
    while not _is_session(d, hol):
        d -= timedelta(days=1)
    return d


def is_market_open(now_et: Optional[datetime] = None,
                   holidays: Optional[Iterable[date]] = None,
                   early: Optional[dict] = None) -> bool:
    """True during the regular session. `now_et` is an ET clock (naive or aware)."""
    now_et = now_et or _now_et()
    d = now_et.date()
    if not is_trading_day(d, holidays):
        return False
    return MARKET_OPEN <= now_et.time().replace(tzinfo=None) < close_time(d, early)


def add_trading_days(d: date, n: int, holidays: Optional[Iterable[date]] = None) -> date:
    """`d` plus `n` trading sessions (n >= 0); TOS earnings-day counts are trading days."""
    hol = set(holidays or ())
    while n > 0:
        d += timedelta(days=1)
        if _is_session(d, hol):
            n -= 1
    return d


def live_session_shift(d: date, latest: Optional[date], today: date,
                       holidays: Optional[Iterable[date]] = None) -> int:
    """Trading sessions that have started since data date `d`, ONLY when `d` is the latest data date.

    2026-11-11, user: on the live (latest) data date, an event/earnings dated on or before the data date has already
    happened once the calendar has moved on, while one dated today is still ahead (day in progress). A past date picked
    keeps exact matching (0). Weekend/holiday today counts no new session."""
    if latest is None or d < latest or today <= d:
        return 0
    hol = set(holidays or ())
    n, x = 0, d
    while x < today:
        x += timedelta(days=1)
        if _is_session(x, hol):
            n += 1
    return n


def market_date_for(ts_et: datetime, holidays: Optional[Iterable[date]] = None,
                    open_time: time = MARKET_OPEN) -> date:
    """Market date a file downloaded at `ts_et` (ET wall clock) belongs to."""
    hol = set(holidays or ())
    d = ts_et.date()
    if _is_session(d, hol) and ts_et.time() >= open_time:
        return d
    d -= timedelta(days=1)
    while not _is_session(d, hol):
        d -= timedelta(days=1)
    return d


def resolve_snapshot_date(inside_date: date, download_et: datetime, now_et: datetime,
                          latest_loaded: Optional[date],
                          holidays: Optional[Iterable[date]] = None,
                          open_time: time = MARKET_OPEN) -> date:
    """Date to file this snapshot under.

    Shift only when ALL hold: the file is a fresh download (< 24 h old), its
    inside date is the calendar day it was downloaded (the "Date" cell is just
    the export day), the download time maps to an earlier market date, and no
    snapshot later than that market date is already stored (latest day only).
    """
    if now_et - download_et > timedelta(hours=FRESH_DOWNLOAD_HOURS):
        return inside_date
    if inside_date != download_et.date():
        return inside_date
    resolved = market_date_for(download_et, holidays, open_time)
    if resolved >= inside_date:
        return inside_date
    if latest_loaded is not None and latest_loaded > resolved:
        return inside_date
    return resolved


# ---------------------------------------------------------------------------
# DB-facing helpers
# ---------------------------------------------------------------------------

def _to_et(epoch: float) -> datetime:
    """Epoch seconds -> naive ET wall clock (falls back to local time)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(epoch, ZoneInfo(MARKET_TZ)).replace(tzinfo=None)
    except Exception:
        return datetime.fromtimestamp(epoch)


def _now_et() -> datetime:
    import time as _t
    return _to_et(_t.time())


def _holidays(session) -> set:
    try:
        rows = session.execute(text(
            "SELECT holiday_date FROM ref_holiday WHERE holiday_date >= :lo"
        ), {"lo": date.today() - timedelta(days=30)}).all()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _name_date(path: str) -> Optional[date]:
    import re
    m = re.search(r'(\d{4})[-_/](\d{1,2})[-_/](\d{1,2})', os.path.basename(path))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _set_warning(session, feed: str, message: Optional[str]) -> None:
    """Replace this feed's file-date warning (message=None just clears it)."""
    code = f"file_date_{feed}"
    session.execute(text(
        "DELETE FROM meta_warning WHERE screen = :s AND code = :c"
    ), {"s": WARNING_SCREEN, "c": code})
    if message:
        from etl.warnings import add_warning
        add_warning(session, WARNING_SCREEN, message, code=code)


def drop_closed_day_rows(session, records: list, source_path: str,
                         skip_reasons: dict,
                         holidays: Optional[Iterable[date]] = None) -> list:
    """TOSD only (hist_td sets the dashboard's day): leave out rows whose export
    date is a weekend or holiday, so that date can never become the anchor.
    Counts them in `skip_reasons` and raises/clears the status-bar warning.
    Rows with no export date are passed through unchanged."""
    hol = market_calendar()[0] if holidays is None else set(holidays)
    keep, closed = [], []
    for r in records:
        d = r.get("export_date")
        if d and not _is_session(d, hol):
            closed.append(d)
        else:
            keep.append(r)
    message = None
    if closed:
        days = ", ".join(f"{d:%m/%d}" for d in sorted(set(closed)))
        reason = f"market closed on {days} (weekend/holiday)"
        skip_reasons[reason] = skip_reasons.get(reason, 0) + len(closed)
        message = (f"{os.path.basename(source_path)}: {len(closed)} rows not loaded, "
                   f"{reason}. The dashboard stays on the last trading day.")
        log.warning(message)
    _set_warning(session, "TOSD", message)
    return keep


def apply_position_date_policy(session, table: str, feed: str,
                               records: list, source_path: str) -> dict:
    """Re-date `records` (hist_cs / hist_f rows) in place when the file was
    downloaded outside the session it is named for, and raise/clear the
    file-date warning for this feed on the status bar.

    Returns {'shifted': bool, 'inside': date|None, 'name': date|None,
             'resolved': date|None, 'replace': bool}. `replace` is True when
    the file is the newest data for the latest market day and may replace
    that day's rows (caller deletes then inserts).
    """
    info = {"shifted": False, "inside": None, "name": None, "resolved": None,
            "replace": False}
    dates = {r.get("snapshot_date") for r in records if r.get("snapshot_date")}
    if len(dates) != 1:
        return info                      # empty / multi-date file: leave as-is
    inside = next(iter(dates))
    name_d = _name_date(source_path)
    try:
        mtime = os.path.getmtime(source_path)
    except OSError:
        return info
    download_et = _to_et(mtime)
    safe_table = {"hist_cs": "hist_cs", "hist_f": "hist_f"}[table]
    latest_loaded = session.execute(text(
        f"SELECT MAX(snapshot_date) FROM {safe_table}")).scalar()
    resolved = resolve_snapshot_date(inside, download_et, _now_et(),
                                     latest_loaded, _holidays(session))
    info.update(inside=inside, name=name_d, resolved=resolved)

    if resolved != inside:
        for r in records:
            r["snapshot_date"] = resolved
        info["shifted"] = True

    fname = os.path.basename(source_path)
    problems = []
    if name_d and name_d != inside:
        problems.append(f"file name says {name_d:%m/%d} but the data inside says {inside:%m/%d}")
    if info["shifted"]:
        problems.append(f"downloaded {download_et:%m/%d %I:%M %p} ET (before market open), "
                        f"so filed under {resolved:%m/%d}")
    if problems:
        _set_warning(session, feed,
                     f"{fname}: " + "; ".join(problems) + ". Rename or re-download if this is wrong.")
        log.warning("%s: file-date issue: %s", fname, "; ".join(problems))
    else:
        _set_warning(session, feed, None)

    # Replace rule: latest market day only, and only if this file was
    # downloaded after at least one row already stored for that day was
    # loaded (MIN, not MAX: a partial earlier load of this same file can leave
    # a recent MAX while older stale rows are still there).
    if latest_loaded is None or resolved >= latest_loaded:
        oldest = session.execute(text(
            f"SELECT MIN(loaded_at) FROM {safe_table} WHERE snapshot_date = :d"),
            {"d": resolved}).scalar()
        info["replace"] = bool(oldest is not None and download_et > oldest.replace(tzinfo=None))
    return info
