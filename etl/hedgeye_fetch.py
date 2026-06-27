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

from dotenv import load_dotenv
load_dotenv()

from etl._logging import setup_logging
from etl.hedgeye import classify
from etl.hedgeye.classify import parser_for
from etl.hedgeye import config as cfgmod
from etl.hedgeye.source import open_source

setup_logging()
log = logging.getLogger("hedgeye_fetch")


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
    from etl.hedgeye.dispatch import dispatch, already_processed
    n = 0
    # Track whether any email-only (direct-insert) data landed.
    # Tab-backed feeds now derive via the loader — no derive needed here.
    direct_inserts = 0
    with open_source(cfg) as src:
        for email in src.iter_since(since):
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

    since = datetime.now(timezone.utc) - timedelta(days=2)
    if args.loop:
        while True:
            try:
                got = _process_pass(cfg, since, args.dry_run)
                log.info("pass done: %d processed", got)
            except Exception:  # noqa: BLE001
                log.exception("poll pass failed")
            time.sleep(cfg.poll_sec)
    else:
        _process_pass(cfg, since, args.dry_run)


if __name__ == "__main__":
    main()
