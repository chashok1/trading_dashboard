"""
Backfill meta_hedgeye_msg.received_at from Gmail IMAP Date headers.

Fetches only BODY.PEEK[HEADER.FIELDS (DATE)] per message — no body download.
Run once after adding the received_at column.

    python -m etl.backfill_hedgeye_received_at
"""
from __future__ import annotations

import email as _email
import imaplib
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from etl.db import session_scope
from etl.hedgeye import config as cfg


def _parse_date(msg) -> datetime | None:
    try:
        return _email.utils.parsedate_to_datetime(msg.get("Date"))
    except Exception:
        return None


def run() -> None:
    c = cfg.load()
    if not (c.imap_host and c.imap_user and c.imap_password):
        print("IMAP not configured — check ref_settings and HEDGEYE_IMAP_PASSWORD in .env")
        return

    # Fetch all message_ids that still need received_at
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT message_id FROM meta_hedgeye_msg WHERE received_at IS NULL ORDER BY processed_at"
        )).fetchall()
    msg_ids = [r[0] for r in rows]
    print(f"{len(msg_ids)} rows need received_at backfill")
    if not msg_ids:
        return

    conn = imaplib.IMAP4_SSL(c.imap_host)
    conn.login(c.imap_user, c.imap_password)
    conn.select(c.mailbox, readonly=True)

    updated = 0
    skipped = 0
    for mid in msg_ids:
        try:
            typ, data = conn.search(None, "HEADER", "Message-ID", mid)
            if typ != "OK" or not data[0]:
                skipped += 1
                continue
            num = data[0].split()[0]
            typ, msg_data = conn.fetch(num, "(BODY.PEEK[HEADER.FIELDS (DATE)])")
            if typ != "OK":
                skipped += 1
                continue
            raw = next((d[1] for d in msg_data if isinstance(d, tuple)), None)
            if not raw:
                skipped += 1
                continue
            msg = _email.message_from_bytes(raw)
            recv = _parse_date(msg)
            if recv is None:
                skipped += 1
                continue
            with session_scope() as s:
                s.execute(text(
                    "UPDATE meta_hedgeye_msg SET received_at=:r WHERE message_id=:m"
                ), {"r": recv, "m": mid})
                s.commit()
            updated += 1
            if updated % 25 == 0:
                print(f"  {updated}/{len(msg_ids)} updated...")
        except Exception as e:
            print(f"  WARN {mid[:40]}: {e}")
            skipped += 1

    conn.logout()
    print(f"Done — updated {updated}, skipped {skipped} (not found in mailbox)")


if __name__ == "__main__":
    run()
