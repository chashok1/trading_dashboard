"""One-off backfill: derive hist_rta.signal_kind from the already-stored
raw_subject for rows the parser missed before the analyst-prefix bug fix in
etl/hedgeye/parsers.py::parse_real_time_alert (2026-07-14).

Subjects without an analyst name (e.g. "Cover-SOME Signal (...): WING")
failed the old regex, leaving signal_kind NULL. No re-fetch from Gmail is
needed — raw_subject already has everything, so this is a pure derived-field
correction, not a raw-data overwrite (rule 1 in CLAUDE.md is about hist_*
payload columns, not re-deriving a parse miss from data already on the row).

Safe to re-run: only touches rows where signal_kind IS NULL.

Run:
    python -m etl.backfill_rta_signal_kind
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from etl.db import session_scope  # noqa: E402

# Mirrors the fixed regex in etl/hedgeye/parsers.py::parse_real_time_alert.
_RTA_SUBJ = re.compile(r"Real-Time Alert:\s*(?P<rest>.*)", re.I)
_RTA_KIND = re.compile(
    r"(?:(?P<analyst>[A-Za-z .'/-]+?)\s+)?(?P<kind>(Buy|Sell|Cover|Sell-SOME|"
    r"Cover-SOME|Macro[\w\- ]*))\s+Signal", re.I)


def _extract(raw_subject: str) -> tuple[str | None, str | None]:
    ms = _RTA_SUBJ.search(raw_subject or "")
    if not ms:
        return None, None
    mk = _RTA_KIND.match(ms.group("rest"))
    if not mk:
        return None, None
    analyst = mk.group("analyst").strip() if mk.group("analyst") else None
    kind = mk.group("kind").strip()
    return analyst, kind


def main() -> None:
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT message_id, raw_subject, analyst FROM hist_rta "
            "WHERE signal_kind IS NULL AND raw_subject IS NOT NULL"
        )).fetchall()
        n_updated = 0
        for message_id, raw_subject, analyst in rows:
            new_analyst, kind = _extract(raw_subject)
            if kind is None:
                print(f"SKIP (no match): {message_id} — {raw_subject!r}")
                continue
            s.execute(text(
                "UPDATE hist_rta SET signal_kind = :k, "
                "analyst = COALESCE(analyst, :a) WHERE message_id = :m"
            ), {"k": kind, "a": new_analyst, "m": message_id})
            n_updated += 1
        print(f"backfilled signal_kind on {n_updated}/{len(rows)} rows")


if __name__ == "__main__":
    main()
