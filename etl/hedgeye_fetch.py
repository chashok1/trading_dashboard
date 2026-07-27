"""
Hedgeye email feed — headless poller (a *pull* feed, like etl/fetch_macro.py).

Polls the Hedgeye inbox, classifies each message (no LLM), parses the structured
ones into hist_* tables and routes prose into note_repo, recording every message
in meta_hedgeye_msg for idempotency. Marketing + DROP types are skipped; unknown
research emails are stored as a note and flagged for review (never lost).

Run on a timer (Windows Task Scheduler / the app's scheduled tasks) or fold the
poll into etl/scheduler.py. Not in the watched-file path.

    python -m etl.hedgeye_fetch --once                 # one pass, then exit
    python -m etl.hedgeye_fetch --loop                 # poll forever
    python -m etl.hedgeye_fetch --backfill 2026-06-01  # reprocess from a date (re-fetch by id)
    python -m etl.hedgeye_fetch --dry-run              # classify only, no DB writes

Gmail is the archive: we keep only message_id; backfill re-pulls bodies from the
mailbox and re-runs the (possibly updated) parsers.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

from etl._logging import setup_logging
from etl.hedgeye import classify
from etl.hedgeye.classify import parser_for
from etl.hedgeye import config as cfgmod
from etl.hedgeye.source import open_source

setup_logging()
log = logging.getLogger("hedgeye_fetch")

_ET = ZoneInfo("America/New_York")
_MARKET_OPEN_H  = 7   # 7:30 AM ET — first Hedgeye emails arrive ~8 AM
_MARKET_OPEN_M  = 30
_MARKET_CLOSE_H = 17  # 5:30 PM ET — after-close window done
_MARKET_CLOSE_M = 30


def _load_holidays() -> set:
    """Return set of date objects from ref_holiday (best-effort; empty on error)."""
    try:
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            rows = s.execute(text("SELECT holiday_date FROM ref_holiday")).fetchall()
            return {r[0] for r in rows}
    except Exception:
        return set()


def _poll_interval_sec(cfg, holidays: set) -> int:
    """Return seconds to sleep before the next poll pass.

    Weekend or market holiday → twice a day (43200 s).
    Weekday outside 7:30 AM–5:30 PM ET → once an hour (3600 s).
    Otherwise → cfg.poll_sec (tunable via ref_settings, default 240 s).
    """
    now = datetime.now(_ET)
    if now.weekday() >= 5 or now.date() in holidays:
        return 43200  # twice a day
    market_open  = now.replace(hour=_MARKET_OPEN_H,  minute=_MARKET_OPEN_M,  second=0)
    market_close = now.replace(hour=_MARKET_CLOSE_H, minute=_MARKET_CLOSE_M, second=0)
    if now < market_open or now >= market_close:
        return 3600   # once an hour after hours
    return cfg.poll_sec


_DEFAULT_LOOKBACK = timedelta(days=2)
_RESUME_BUFFER = timedelta(hours=1)  # overlap so a message can't fall in the gap between polls


def resume_since() -> datetime:
    """Watermark for the next poll: last processed email's received_at (minus a
    safety buffer), so a poll after any outage resumes where it left off instead
    of a fixed rolling window. Falls back to the default lookback if no messages
    have been processed yet (or the query fails).

    If any message is stuck in status='error' (see record_ledger in a per-email
    failure), the watermark floors at the OLDEST such message instead of the
    newest success — otherwise a later message succeeding would push the
    watermark past the still-unresolved failure and it would stop being retried."""
    try:
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            floor = s.execute(text(
                "SELECT MIN(received_at) FROM meta_hedgeye_msg WHERE status <> 'ok'")).scalar()
            if floor is None:
                floor = s.execute(text(
                    "SELECT MAX(received_at) FROM meta_hedgeye_msg WHERE status = 'ok'")).scalar()
        if floor is not None:
            return floor - _RESUME_BUFFER
    except Exception:
        log.exception("resume_since: failed to read meta_hedgeye_msg watermark; using default lookback")
    return datetime.now(timezone.utc) - _DEFAULT_LOOKBACK


def _trigger_derive() -> None:
    """After writing Hedgeye data, re-derive for the current anchor date."""
    try:
        from etl.db import session_scope
        from etl.derive import get_anchor_date, derive_all
        with session_scope() as s:
            d = get_anchor_date(s)
            if d is None:
                log.debug("derive trigger: no anchor date yet — skipping")
                return
            log.info("derive trigger: running derive_all for %s", d)
            derive_all(s, d)
        log.info("derive trigger: done for %s", d)
    except Exception:
        log.exception("derive trigger after hedgeye load failed (non-fatal)")


def _process_pass(cfg, since, dry_run: bool) -> int:
    from etl.db import session_scope
    from etl.hedgeye.dispatch import dispatch, already_processed, record_ledger
    n = 0
    # Track whether any email-only (direct-insert) data landed.
    # Tab-backed feeds now derive via the loader — no derive needed here.
    direct_inserts = 0
    with open_source(cfg) as src:
        for email in src.iter_since(since):
            try:
                et = classify(email)
                if et.destination == "DROP":
                    continue
                with session_scope() as s:
                    if already_processed(s, email.message_id):
                        continue
                    parser = parser_for(et)
                    parsed = parser(email) if parser else _note_only(email, et)
                    if dry_run:
                        log.info("[dry] %-22s %s", et.name, email.subject[:70])
                        continue
                    summary = dispatch(s, email, et.name, parsed, cfg)
                    log.info(
                        "%-22s %s -> tables=%s files=%s",
                        et.name, email.subject[:60],
                        summary["tables"], summary.get("files", {}),
                    )
                    direct_inserts += sum(summary.get("tables", {}).values())
                    n += 1
            except Exception as e:  # noqa: BLE001
                # One bad message must not block everything after it in this pass.
                # Record it as an unresolved failure so resume_since() keeps
                # retrying it (and doesn't advance the watermark past it) instead
                # of silently dropping it.
                log.exception(
                    "hedgeye: failed processing %s (%s) — will retry next poll",
                    email.message_id, (email.subject or "")[:60])
                if not dry_run:
                    try:
                        with session_scope() as s2:
                            record_ledger(s2, email, "error", "error", {"error": str(e)[:500]})
                    except Exception:
                        log.exception("hedgeye: failed to record error ledger for %s", email.message_id)
    # Only trigger derive when email-only feeds inserted rows directly.
    # Tab-backed feeds derive via the scheduler after it picks up the file.
    if direct_inserts > 0 and not dry_run:
        _trigger_derive()
    return n


def _note_only(email, et):
    """ANALYSIS types without a structured parser, and UNKNOWN, become a note."""
    from etl.hedgeye.parsers import Parsed, _note
    p = Parsed(et.name)
    src = "unknown" if et.destination == "UNKNOWN" else et.name
    p.notes.append(_note(email, src, email.subject))
    if et.destination == "UNKNOWN":
        p.flags.append("review_unclassified")
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Hedgeye email feed poller")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--backfill", metavar="YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load()
    if not cfg.enabled and not args.dry_run:
        log.warning("hedgeye_enabled=false in ref_settings; exiting (use --dry-run to test)")
        return

    if args.backfill:
        since = datetime.fromisoformat(args.backfill).replace(tzinfo=timezone.utc)
        log.info("backfill since %s", since.date())
        _process_pass(cfg, since, args.dry_run)
        return

    if args.loop:
        holidays = _load_holidays()
        next_holiday_refresh = 86400  # refresh holiday set once a day
        while True:
            try:
                since = resume_since()
                got = _process_pass(cfg, since, args.dry_run)
                log.info("pass done: %d processed", got)
            except Exception:  # noqa: BLE001
                log.exception("poll pass failed")
            interval = _poll_interval_sec(cfg, holidays)
            log.debug("next poll in %ds", interval)
            time.sleep(interval)
            next_holiday_refresh -= interval
            if next_holiday_refresh <= 0:
                holidays = _load_holidays()
                next_holiday_refresh = 86400
    else:
        _process_pass(cfg, resume_since(), args.dry_run)


if __name__ == "__main__":
    main()
