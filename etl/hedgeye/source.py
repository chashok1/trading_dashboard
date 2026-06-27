"""
Email source abstraction — headless, read-only access to the Hedgeye inbox.

Two providers (config-selectable):
  - imap      : standard IMAP + app-password (works for Gmail with IMAP enabled).
  - gmail_api : Gmail REST API with an OAuth token (stub; wire in the developer task).

Both yield etl.hedgeye.parsers.Email objects. Re-fetch by message_id supports
backfill (Gmail is the archive; we keep only message_id locally).
"""
from __future__ import annotations

import email as _email
import imaplib
from datetime import datetime, timezone
from email.header import decode_header, make_header
from typing import Iterator, Optional

from .parsers import Email


def _decode(s) -> str:
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _bodies(msg) -> tuple[str, str]:
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get("Content-Disposition"):
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
    return plain, html


def _to_email(msg, message_id: str) -> Email:
    plain, html = _bodies(msg)
    dt = None
    try:
        dt = _email.utils.parsedate_to_datetime(msg.get("Date"))
    except Exception:
        dt = datetime.now(timezone.utc)
    return Email(
        message_id=message_id,
        subject=_decode(msg.get("Subject")),
        sender=_decode(msg.get("From")),
        received=dt,
        plaintext=plain,
        html=html,
    )


class ImapSource:
    """Minimal read-only IMAP reader."""

    def __init__(self, host: str, user: str, password: str, mailbox: str = "INBOX"):
        self.host, self.user, self.password, self.mailbox = host, user, password, mailbox
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    def __enter__(self):
        self._conn = imaplib.IMAP4_SSL(self.host)
        self._conn.login(self.user, self.password)
        self._conn.select(self.mailbox, readonly=True)
        return self

    def __exit__(self, *exc):
        try:
            self._conn.logout()
        except Exception:
            pass

    def iter_since(self, since: Optional[datetime], from_addr: str = "hedgeye.com"
                   ) -> Iterator[Email]:
        crit = ["FROM", from_addr]
        if since:
            crit += ["SINCE", since.strftime("%d-%b-%Y")]
        typ, data = self._conn.search(None, *crit)
        if typ != "OK":
            return
        for num in data[0].split():
            typ, msg_data = self._conn.fetch(num, "(RFC822 BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            if typ != "OK":
                continue
            raw = next((d[1] for d in msg_data if isinstance(d, tuple)), None)
            if not raw:
                continue
            msg = _email.message_from_bytes(raw)
            mid = (msg.get("Message-ID") or num.decode()).strip()
            yield _to_email(msg, mid)

    def fetch_one(self, message_id: str) -> Optional[Email]:
        typ, data = self._conn.search(None, "HEADER", "Message-ID", message_id)
        if typ != "OK" or not data[0]:
            return None
        num = data[0].split()[0]
        typ, msg_data = self._conn.fetch(num, "(RFC822)")
        raw = next((d[1] for d in msg_data if isinstance(d, tuple)), None)
        return _to_email(_email.message_from_bytes(raw), message_id) if raw else None


def open_source(cfg) -> "ImapSource":
    if cfg.provider == "imap":
        if not (cfg.imap_host and cfg.imap_user and cfg.imap_password):
            raise RuntimeError("IMAP host/user/password not configured (see etl.hedgeye.config)")
        return ImapSource(cfg.imap_host, cfg.imap_user, cfg.imap_password, cfg.mailbox)
    raise NotImplementedError(
        "gmail_api provider is a stub — wire OAuth token fetch in the developer task")
