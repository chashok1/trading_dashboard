"""
Dispatch — route a Parsed result to its destinations and record the ledger.

DATA lane    : insert_skip_duplicates into the hist_* tables (append-only,
               ON CONFLICT DO NOTHING — convention 1).
ANALYSIS/RULES: notes -> note_repo.
Images       : download to the configurable archive folder; path -> hist_media.
Ledger       : meta_hedgeye_msg(message_id, email_type, status) — idempotency.

This module performs the DB writes, so it only runs where Postgres is reachable
(the app host / developer + tester agents), never inside the Cowork sandbox.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from etl.db import insert_skip_duplicates
from etl.hedgeye.emit import FILE_LANES, write_feed

log = logging.getLogger("hedgeye.dispatch")


def _next_business_day(d: date) -> date:
    """Return d + 1 calendar day, advancing past any weekend."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d = d + timedelta(days=1)
    return d


def _prev_business_day(session, d: date) -> date:
    """Return the most recent business day before d, skipping weekends and ref_holiday entries."""
    try:
        rows = session.execute(text("SELECT holiday_date FROM ref_holiday")).fetchall()
        holidays = {r[0] for r in rows}
    except Exception:
        holidays = set()
    d = d - timedelta(days=1)
    while d.weekday() >= 5 or d in holidays:
        d = d - timedelta(days=1)
    return d


# No feed types currently use next-day date adjustment.
# RR emails use received date as file name; data inside is for the previous business day.
_NEXT_DAY_FEEDS: frozenset = frozenset()


def already_processed(session, message_id: str) -> bool:
    return bool(session.execute(
        text("SELECT 1 FROM meta_hedgeye_msg WHERE message_id=:m"),
        {"m": message_id}).first())


def record_ledger(session, email, email_type: str, status: str,
                  detail: Optional[dict] = None) -> None:
    session.execute(text(
        "INSERT INTO meta_hedgeye_msg "
        "(message_id, email_type, sender, subject, status, detail, processed_at) "
        "VALUES (:m,:t,:s,:subj,:st,:d, now()) "
        "ON CONFLICT (message_id) DO UPDATE SET "
        "email_type=EXCLUDED.email_type, status=EXCLUDED.status, "
        "detail=EXCLUDED.detail, processed_at=now()"),
        {"m": email.message_id, "t": email_type, "s": email.sender[:200],
         "subj": email.subject[:400], "st": status,
         "d": json.dumps(detail or {})})


def _write_notes(session, notes: list[dict]) -> None:
    rows = []
    for n in notes:
        rows.append({
            "message_id": n["message_id"], "note_date": n["note_date"],
            "source_type": n["source_type"], "gmail_link": n["gmail_link"],
            "analyst": n.get("analyst"), "tickers": n.get("tickers") or [],
            "theme_tags": n.get("theme_tags") or [], "quad": n.get("quad"),
            "signal_kind": n.get("signal_kind"), "note_text": n["note_text"],
            "subject": n.get("subject"), "status": n.get("status", "new"),
        })
    if rows:
        insert_skip_duplicates(session, "note_repo", rows)


def archive_images(urls: list[str], folder: str, email, max_n: int = 4) -> list[dict]:
    """Download up to max_n chart images to a positional-named file in `folder`."""
    out = []
    d = email.edt_date or datetime.now(timezone.utc).date()
    base = Path(folder) / email.message_id.strip("<>").replace("/", "_")[:60]
    base.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls[:max_n], 1):
        dest = base / f"chart_{d.isoformat()}_{i:02d}.png"
        try:
            urllib.request.urlretrieve(url, dest)
            out.append({"message_id": email.message_id, "seq": i,
                        "local_path": str(dest), "source_url": url,
                        "captured_at": datetime.now(timezone.utc)})
        except Exception as e:  # noqa: BLE001
            log.warning("image archive failed %s: %s", url, e)
    return out


def _save_hefiles_image(url: str, hefiles_dir: str, filename: str) -> None:
    """Download a single image URL and save it to hefiles_dir/{filename}."""
    try:
        dest = Path(hefiles_dir)
        dest.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=15) as resp:
            (dest / filename).write_bytes(resp.read())
        log.info("saved %s -> %s", filename, hefiles_dir)
    except Exception as e:
        log.warning("_save_hefiles_image failed %s: %s", filename, e)


def _adapt_rows(table: str, rows: list[dict]) -> list[dict]:
    """Map parser-emitted columns to live DB columns where names differ.

    hist_iichg / hist_etfchg: parser uses snapshot_date; DB PK uses event_date.
    hist_macro: strip message_id (not a hist_macro column); default source=HEDGEYE.
    All other tables: pass through unchanged (columns already match).
    """
    if not rows:
        return rows
    if table in ("hist_iichg", "hist_etfchg"):
        out = []
        for r in rows:
            nr = dict(r)
            if "snapshot_date" in nr:
                nr["event_date"] = nr.pop("snapshot_date")
            out.append(nr)
        return out
    if table == "hist_macro":
        out = []
        for r in rows:
            nr = {k: v for k, v in r.items() if k != "message_id"}
            nr.setdefault("source", "HEDGEYE")
            out.append(nr)
        return out
    return rows


def dispatch(session, email, email_type: str, parsed, cfg) -> dict:
    """Write everything for one parsed email. Returns a small summary dict.

    Tab-backed feeds (risk_range / investing_ideas / etf_changes /
    portfolio_solutions / the_call's hist_call rows) are routed via
    emit.write_feed() → file in source_dir → scheduler → loader → derive.
    Email-only feeds (hist_rta, hist_call_top5, hist_hedgeye_stance, etc.)
    continue with direct insert_skip_duplicates (unchanged).
    """
    summary = {"type": email_type, "tables": {}, "files": {},
               "notes": 0, "images": 0,
               "flags": parsed.flags, "warnings": parsed.warnings}

    feed_date = email.edt_date or email.received.date()
    if email_type in _NEXT_DAY_FEEDS:
        feed_date = _next_business_day(feed_date)
        if feed_date > date.today():
            log.info(
                "dispatch: %s feed_date=%s is in the future — skipping file emit",
                email_type, feed_date,
            )
            return summary

    # RR: data inside the file represents the previous business day (skipping weekends + holidays)
    if email_type == "risk_range":
        prev_day = _prev_business_day(session, feed_date)
        for rows in parsed.tables.values():
            for row in rows:
                row["snapshot_date"] = prev_day
                row["market_close"] = prev_day

    for table, rows in parsed.tables.items():
        if rows:
            if (email_type, table) in FILE_LANES:
                # Route via file → existing loader (no direct DB insert here)
                result = write_feed(session, email_type, feed_date, rows)
                summary["files"][table] = result or "skipped"
            else:
                adapted = _adapt_rows(table, rows)
                attempted, inserted = insert_skip_duplicates(
                    session, table, adapted
                )
                summary["tables"][table] = inserted

    if email_type == "portfolio_solutions":
        from etl.hedgeye import ps_grids
        grids = ps_grids.generate_from_email(email, feed_date)
        summary["files"].update(grids)

    if parsed.notes:
        _write_notes(session, parsed.notes)
        summary["notes"] = len(parsed.notes)

    if parsed.images:
        if email_type == "market_situation":
            from etl.hedgeye import msr_ocr
            summary["msr"] = msr_ocr.process_msr_images(
                parsed.images, feed_date, email.message_id, session,
                hefiles_dir=cfg.hefiles_dir,
            )
        elif email_type == "signal_strength" and parsed.images:
            _save_hefiles_image(
                parsed.images[0], cfg.hefiles_dir,
                f"SSS_{feed_date.isoformat()}.png",
            )
            summary["images"] = 1
        else:
            media = archive_images(parsed.images, cfg.image_dir, email)
            if media:
                insert_skip_duplicates(session, "hist_media", media)
                summary["images"] = len(media)

    # correction auto-reverse: cancel the prior open alert for this ticker
    if "correction" in parsed.flags:
        session.execute(text(
            "UPDATE hist_rta SET superseded = TRUE "
            "WHERE tos_symbol IS NOT NULL AND superseded IS NOT TRUE "
            "AND alert_ts < :ts AND alert_ts > :ts - interval '1 day' "
            "AND tos_symbol = (SELECT tos_symbol FROM hist_rta "
            "WHERE message_id=:m)"),
            {"ts": email.received, "m": email.message_id})

    record_ledger(session, email, email_type, "ok", summary)
    return summary
