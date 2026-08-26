"""
Optional notification hooks.

Two channels, both off by default — they only fire when the corresponding flag
in `.env` is set:

  NOTIFY_TOAST=1                     # Windows toast popups (best-effort)
  NOTIFY_EMAIL=1
  SMTP_HOST=smtp.example.com
  SMTP_PORT=587
  SMTP_USER=user@example.com
  SMTP_PASSWORD=...
  NOTIFY_EMAIL_TO=alerts@example.com

SMTP_PASSWORD may be left unset if HEDGEYE_IMAP_PASSWORD is already
configured for the same account (2026-08-25, user-directed: "use the same
key for password") — config/settings.py's model_post_init falls back to
it automatically, since a Gmail App Password isn't scoped to one protocol.

Public API: `notify(title, message, level='info')`.  All exceptions are
swallowed and logged — a notification failure must NEVER crash the scheduler.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Literal

from config.settings import settings

log = logging.getLogger("etl.notify")

Level = Literal["info", "warn", "error"]


def _toast(title: str, message: str, level: Level) -> None:
    """Best-effort Windows toast. Falls back silently if libs missing."""
    try:
        # Prefer winotify (modern, async), fall back to win10toast (legacy)
        try:
            from winotify import Notification  # type: ignore
            n = Notification(app_id="TradingDashboard",
                             title=title, msg=message,
                             duration="short")
            n.show()
            return
        except ImportError:
            pass
        from win10toast import ToastNotifier  # type: ignore
        ToastNotifier().show_toast(title, message, duration=4, threaded=True)
    except Exception as e:
        log.debug("toast failed (%s)", e)


def _email(title: str, message: str, level: Level) -> None:
    """Best-effort SMTP send. Returns silently if any required setting is empty."""
    if not (settings.smtp_host and settings.notify_email_to):
        log.debug("email skipped (SMTP_HOST or NOTIFY_EMAIL_TO empty)")
        return
    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_user or settings.notify_email_to
        msg["To"] = settings.notify_email_to
        msg["Subject"] = f"[trading-dashboard:{level}] {title}"
        msg.set_content(message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except Exception as e:
        log.warning("email notification failed: %s", e)


def send_email(subject: str, plain_body: str, html_body: str | None = None) -> bool:
    """Send a full-length email -- unlike notify(), subject/body are not
    truncated (notify() caps title/message for toast+short-alert use).
    2026-08-25: added for scheduled jobs that need a real report (e.g.
    etl/export_trade_mode.py's nightly digest), not just a status ping.
    Gated the same way as notify()'s email channel -- caller should check
    settings.notify_email first if it wants to skip work when disabled;
    this function only checks the SMTP/recipient settings themselves.
    Returns True on send, False if skipped (settings empty) or failed."""
    if not (settings.smtp_host and settings.notify_email_to):
        log.debug("send_email skipped (SMTP_HOST or NOTIFY_EMAIL_TO empty)")
        return False
    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_user or settings.notify_email_to
        msg["To"] = settings.notify_email_to
        msg["Subject"] = subject
        msg.set_content(plain_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception as e:
        log.warning("send_email failed (%s): %s", subject, e)
        return False


def notify(title: str, message: str, level: Level = "info") -> None:
    """Send a notification through every enabled channel.

    `level` is purely advisory — it shows up in the email subject and is
    available for future per-channel filtering. Toast level is fixed.
    """
    title = str(title)[:120]
    message = str(message)[:1000]
    if settings.notify_toast:
        _toast(title, message, level)
    if settings.notify_email:
        _email(title, message, level)


__all__ = ["notify", "send_email"]
