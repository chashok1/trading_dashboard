"""Watch/notify feature -- ref_watch check + digest logic.

See db/baseline.sql's own comment on ref_watch for the full design. Two
entry points, both called (via thin maybe_* wrappers) from
etl/scheduler.py's main loop:

  check_watches()      -- every ~minute: evaluate ACTIVE, not-yet-triggered
                           watches against the latest price/LRR/TRR/Trade/
                           Trend reading; flips triggered_at/triggered_reason
                           the first time a condition is met. Idempotent --
                           harmless to call repeatedly.
  send_watch_digest()  -- once/day near close: composes ONE combined email
                           of everything still triggered-and-unreviewed via
                           etl.notify.send_email. No-ops (returns False) if
                           nothing qualifies -- including when you've
                           already reviewed everything in-app before this
                           runs.

Deliberately NOT part of derive_all()/drv_actionable -- this is same-day
ephemeral state, not a historical annotation.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from etl.db import session_scope

log = logging.getLogger(__name__)


def _crossed(baseline_price, baseline_level, now_price, now_level) -> bool:
    """True if now_price sits on the OPPOSITE side of now_level from where
    baseline_price sat relative to baseline_level -- a genuine crossing,
    not just "currently past the level" (which would fire immediately for
    a level the price was already beyond when the watch was created).
    Missing data on either side (baseline never captured, or the level
    isn't published for this symbol) can't be evaluated -- returns False."""
    if baseline_price is None or baseline_level is None or now_price is None or now_level is None:
        return False
    was_above = baseline_price >= baseline_level
    now_above = now_price >= now_level
    return was_above != now_above


def check_watches() -> int:
    """Evaluate every ACTIVE, not-yet-triggered watch against the latest
    known price/LRR/TRR/Trade-line/Trend-line for its symbol. Returns the
    count newly triggered this pass."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT w.id, w.baseline_price, w.baseline_lrr, w.baseline_trr,
                   w.baseline_trade, w.baseline_trend, w.trigger_pct, w.trigger_pct_dir, w.trigger_lrr,
                   w.trigger_trr, w.trigger_trade, w.trigger_trend, w.trigger_price,
                   q.last_price, dr.lrr, dr.trr, mt.a_trade_value, mt.a_trend_value
            FROM ref_watch w
            LEFT JOIN LATERAL (
                SELECT last_price FROM drv_quote
                WHERE tos_symbol = w.tos_symbol ORDER BY as_of_date DESC LIMIT 1
            ) q ON TRUE
            LEFT JOIN LATERAL (
                SELECT lrr, trr FROM drv_rr
                WHERE tos_symbol = w.tos_symbol ORDER BY as_of_date DESC LIMIT 1
            ) dr ON TRUE
            LEFT JOIN LATERAL (
                SELECT a_trade_value, a_trend_value FROM drv_technicals
                WHERE tos_symbol = w.tos_symbol ORDER BY as_of_date DESC LIMIT 1
            ) mt ON TRUE
            WHERE w.status = 'ACTIVE' AND w.triggered_at IS NULL
        """)).mappings().all()

        n = 0
        for r in rows:
            last = r["last_price"]
            if last is None:
                continue
            reason = None
            if r["trigger_pct"] is not None and r["baseline_price"]:
                pct = (float(last) - float(r["baseline_price"])) / float(r["baseline_price"]) * 100
                # Direction-specific (2026-09-02, user: "% move should be
                # specific direction either up or down") -- UP only fires on
                # a rally of at least trigger_pct, DOWN only on a drop of at
                # least trigger_pct; a move the wrong way never fires.
                if r["trigger_pct_dir"] == "UP" and pct >= float(r["trigger_pct"]):
                    reason = f"+{pct:.1f}% from ${float(r['baseline_price']):.2f}"
                elif r["trigger_pct_dir"] == "DOWN" and pct <= -float(r["trigger_pct"]):
                    reason = f"{pct:.1f}% from ${float(r['baseline_price']):.2f}"
            if reason is None and r["trigger_lrr"] and _crossed(r["baseline_price"], r["baseline_lrr"], last, r["lrr"]):
                reason = f"crossed LRR (${float(r['lrr']):.2f})"
            if reason is None and r["trigger_trr"] and _crossed(r["baseline_price"], r["baseline_trr"], last, r["trr"]):
                reason = f"crossed TRR (${float(r['trr']):.2f})"
            if reason is None and r["trigger_trade"] and _crossed(r["baseline_price"], r["baseline_trade"], last, r["a_trade_value"]):
                reason = f"crossed Trade line (${float(r['a_trade_value']):.2f})"
            if reason is None and r["trigger_trend"] and _crossed(r["baseline_price"], r["baseline_trend"], last, r["a_trend_value"]):
                reason = f"crossed Trend line (${float(r['a_trend_value']):.2f})"
            if reason is None and r["trigger_price"] is not None and _crossed(
                r["baseline_price"], float(r["trigger_price"]), last, float(r["trigger_price"])
            ):
                reason = f"crossed ${float(r['trigger_price']):.2f}"
            if reason:
                s.execute(text(
                    "UPDATE ref_watch SET triggered_at = now(), triggered_reason = :reason WHERE id = :id"
                ), {"reason": reason, "id": r["id"]})
                n += 1
        if n:
            log.info("watch: %d watch(es) newly triggered", n)
        return n


def _get_digest_hour(default: int = 15) -> int:
    try:
        with session_scope() as s:
            row = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = 'watch_digest_hour'"
            )).first()
            return int(row[0]) if row and row[0] else default
    except Exception:
        return default


def send_watch_digest() -> bool:
    """Compose and send ONE combined email of every watch that's triggered
    and not yet reviewed/emailed. Returns True if an email was actually
    sent (False if nothing qualifies, or send_email itself no-ops because
    NOTIFY_EMAIL/SMTP isn't configured)."""
    try:
        from etl.notify import send_email

        with session_scope() as s:
            rows = s.execute(text("""
                SELECT id, tos_symbol, triggered_reason, note
                FROM ref_watch
                WHERE status = 'ACTIVE' AND triggered_at IS NOT NULL
                  AND reviewed_at IS NULL AND emailed_at IS NULL
                ORDER BY tos_symbol
            """)).mappings().all()
            if not rows:
                # Nothing unreviewed to report -- this is also how "already
                # went through it in the evening" suppresses the email: a
                # PATCH {reviewed:true} from the panel clears rows out of
                # this WHERE clause before this job ever runs.
                return False

            def _line(r):
                tail = f" — {r['note']}" if r["note"] else ""
                return f"{r['tos_symbol']}: {r['triggered_reason']}{tail}"

            plain = "Watched symbols that triggered today:\n\n" + "\n".join(_line(r) for r in rows)
            html = ("<p>Watched symbols that triggered today:</p><ul>"
                    + "".join(f"<li><b>{r['tos_symbol']}</b>: {r['triggered_reason']}"
                              + (f" — {r['note']}" if r["note"] else "") + "</li>" for r in rows)
                    + "</ul>")
            sent = send_email(f"Watch digest — {len(rows)} symbol(s) triggered", plain, html)
            if sent:
                ids = [r["id"] for r in rows]
                s.execute(text("UPDATE ref_watch SET emailed_at = now() WHERE id = ANY(:ids)"), {"ids": ids})
            return sent
    except Exception:
        log.exception("watch: send_watch_digest crashed")
        return False
