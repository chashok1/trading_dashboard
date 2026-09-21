"""
etl/derive_sss_breadth.py — TASK_144: drv_sss_breadth (SSS sector breadth,
rows AND analyst books, side by side) + a small, honest sector-label
normalizer for hist_sss.sector.

Design: docs/market_state_factor_sss_design.md (Addendum B/§3).
Display + measurement only — never touches derive_actionable.py/ref_trig_*.

Data-quality finding (TASK_144 step 1, see DEV_HANDOFF.md for the full
`SELECT DISTINCT sector, analyst FROM hist_sss` capture): hist_sss.sector is
NOT clean. Of 137 distinct raw strings on the live DB, ~90 are OCR/parse-
noise variants of ~18 real sector names (e.g. "ConswmerStaples",
"Afrertals", "dInduseais"), and a handful are outright header/footer text
that leaked into the sector column as data (e.g. "r of strengthlisted
dayssince..."). A static hand-typed map would need dozens of entries and
would still miss the next new typo, so `_normalize_sss_sector` instead
fuzzy-matches the alpha-only, lower-cased raw string against a small
canonical sector list (stdlib difflib, no new dependency) — anything below
the match-ratio cutoff (0.72, chosen empirically: every genuine-but-
corrupted variant tested at >=0.6, every header/footer leak tested at
<=0.5) buckets to 'Unclassified' rather than guessing wrong. This is the
SAME normalizer etl/derive_market_read.py imports for the SSS column of the
theme grid (single source of truth for "what sector is this row").
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap, position_ceiling
from etl.db import replace_for_date

log = logging.getLogger(__name__)

CANON_SECTORS = [
    "Consumer Staples", "Energy", "Financials", "Healthcare", "Industrials",
    "Materials", "Retail", "REITs", "Restaurants", "Software", "Global Tech",
    "Cannabis", "Digital Assets", "Gaming Lodging Leisure", "Communications",
    "Health Policy", "Policy", "Small Caps",
]
_CANON_COMPACT = {c: re.sub(r"[^a-zA-Z]", "", c).lower() for c in CANON_SECTORS}
_MATCH_CUTOFF = 0.72


def _normalize_sss_sector(raw: Optional[str]) -> Optional[str]:
    """Best-effort canonical sector name, or None (-> 'Unclassified' bucket)
    when the raw string doesn't confidently match anything. See module
    docstring for the cutoff rationale."""
    if not raw:
        return None
    compact = re.sub(r"[^a-zA-Z]", "", raw).lower()
    if len(compact) < 3:
        return None
    best, best_score = None, 0.0
    for canon, canon_compact in _CANON_COMPACT.items():
        score = SequenceMatcher(None, compact, canon_compact).ratio()
        if score > best_score:
            best_score, best = score, canon
    return best if best_score >= _MATCH_CUTOFF else None


_RANK_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def _parse_rank(raw: Optional[str]) -> tuple:
    """Returns (kind, rank, book_size). kind in {'ranked','bench','km',None}."""
    if not raw:
        return (None, None, None)
    s = str(raw).strip()
    su = s.upper()
    if su == "BENCH":
        return ("bench", None, None)
    if su == "KMSIGNAL":
        return ("km", None, None)
    m = _RANK_RE.match(s)
    if m:
        return ("ranked", int(m.group(1)), int(m.group(2)))
    return (None, None, None)


def _median(vals: list) -> Optional[float]:
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return float(vals[mid]) if n % 2 == 1 else (vals[mid - 1] + vals[mid]) / 2.0


def _derive_sss_breadth_impl(session: Session, as_of_date: date, run_id) -> int:
    # SSS is a weekly Hedgeye email feed that can lead the TOSD anchor (same
    # convention as the Hedgeye panel's effective_date, CLAUDE.md Lookup) on
    # the LIVE anchor; on a HISTORICAL re-derive the ceiling stays at
    # as_of_date to prevent look-ahead bias in the 13/26-week medians (same
    # pattern as etl/_derive_common.py::position_ceiling).
    ceiling = position_ceiling(session, as_of_date)
    d = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_sss WHERE snapshot_date <= :t"
    ), {"t": ceiling}).scalar()
    if d is None:
        return replace_for_date(session, "drv_sss_breadth", "as_of_date", as_of_date, [])

    cur_rows = session.execute(text(
        "SELECT symbol, sector, analyst, days_on, pct_delta, anlst_best_idea_rank "
        "FROM hist_sss WHERE snapshot_date = :d"
    ), {"d": d}).mappings().all()

    # --- last 26 distinct weekly snapshots (for medians + book carry-forward) ---
    hist_dates = session.execute(text(
        "SELECT DISTINCT snapshot_date FROM hist_sss WHERE snapshot_date <= :d "
        "ORDER BY snapshot_date DESC LIMIT 26"
    ), {"d": d}).scalars().all()
    hist_rows = session.execute(text(
        "SELECT snapshot_date, sector, anlst_best_idea_rank FROM hist_sss "
        "WHERE snapshot_date = ANY(:dates)"
    ), {"dates": list(hist_dates)}).mappings().all()

    # per-date, per-sector: row count + max ranked denominator (if any)
    by_date_sector: dict = {}
    for r in hist_rows:
        sec = _normalize_sss_sector(r["sector"]) or "Unclassified"
        key = (r["snapshot_date"], sec)
        entry = by_date_sector.setdefault(key, {"n_rows": 0, "book_size": None})
        entry["n_rows"] += 1
        kind, _rank, book = _parse_rank(r["anlst_best_idea_rank"])
        if kind == "ranked" and book is not None:
            entry["book_size"] = max(entry["book_size"] or 0, book)
        # also roll into _TOTAL
        tkey = (r["snapshot_date"], "_TOTAL")
        tentry = by_date_sector.setdefault(tkey, {"n_rows": 0, "book_size": None})
        tentry["n_rows"] += 1
        if kind == "ranked" and book is not None:
            tentry["book_size"] = max(tentry["book_size"] or 0, book)

    all_sectors = sorted({sec for (_dt, sec) in by_date_sector.keys()})
    n_rows_series: dict = {sec: [] for sec in all_sectors}
    for dt in hist_dates:
        for sec in all_sectors:
            n_rows_series[sec].append(by_date_sector.get((dt, sec), {}).get("n_rows", 0))

    def book_carry_forward(sec: str) -> tuple:
        """Most recent (date, book_size) among hist_dates (desc order) that
        actually had a ranked row for this sector, or (None, None)."""
        for dt in hist_dates:
            entry = by_date_sector.get((dt, sec))
            if entry and entry["book_size"] is not None:
                return dt, entry["book_size"]
        return None, None

    # --- adds/removes in the trailing week (hist_sss_change has no sector
    # column, so this is a _TOTAL-only count, not per-sector) ---
    chg = session.execute(text(
        "SELECT action, COUNT(*) AS c FROM hist_sss_change "
        "WHERE snapshot_date BETWEEN :lo AND :hi GROUP BY action"
    ), {"lo": d - timedelta(days=7), "hi": d}).fetchall()
    adds_total = sum(c for a, c in chg if a and "add" in a.lower())
    removes_total = sum(c for a, c in chg if a and
                         ("remove" in a.lower() or "drop" in a.lower()))

    # --- current-snapshot detail per sector ---
    by_sector_cur: dict = {}
    for r in cur_rows:
        sec = _normalize_sss_sector(r["sector"]) or "Unclassified"
        by_sector_cur.setdefault(sec, []).append(r)

    rows_out = []
    for sec in sorted(set(all_sectors) | set(by_sector_cur.keys()) | {"_TOTAL"}):
        members = by_sector_cur.get(sec, []) if sec != "_TOTAL" else cur_rows
        n_rows = len(members)
        n_ranked = n_bench = n_km = 0
        ranked_members = []
        strengths = []
        days_ons = []
        for r in members:
            kind, rank, book = _parse_rank(r["anlst_best_idea_rank"])
            if kind == "ranked":
                n_ranked += 1
                ranked_members.append((rank, r["symbol"]))
            elif kind == "bench":
                n_bench += 1
            elif kind == "km":
                n_km += 1
            if r["pct_delta"] is not None:
                strengths.append(float(r["pct_delta"]))
            if r["days_on"] is not None:
                days_ons.append(float(r["days_on"]))

        if sec == "_TOTAL":
            # Sum of the OTHER sectors' own book_size (each already resolved
            # via its own carry-forward below) -- NOT a pooled MAX across
            # every analyst's differently-scaled rank denominator, which
            # would be meaningless (Software's "/6" and Retail's "/23" are
            # two different analysts' own idea-list sizes). Computed as a
            # second pass after this loop; placeholder here.
            book_size, book_size_asof = None, None
        else:
            cur_entry = by_date_sector.get((d, sec), {})
            book_size = cur_entry.get("book_size")
            book_size_asof = d if book_size is not None else None
            if book_size is None:
                book_size_asof, book_size = book_carry_forward(sec)

        top3 = [{"rank": rk, "symbol": sym}
                for rk, sym in sorted(ranked_members, key=lambda t: t[0])[:3]]

        series = n_rows_series.get(sec, [])
        n_rows_med13 = _median(series[:13])
        n_rows_med26 = _median(series[:26])

        rows_out.append({
            "as_of_date": as_of_date,
            "snapshot_date": d,
            "sector": sec,
            "n_rows": n_rows,
            "n_ranked": n_ranked,
            "n_bench": n_bench,
            "n_km": n_km,
            "book_size": book_size,
            "book_size_asof": book_size_asof,
            "top3": top3,
            "avg_strength": (round(sum(strengths) / len(strengths) * 100, 1)
                              if strengths else None),
            "median_days_on": _median(days_ons),
            "n_rows_med13": n_rows_med13,
            "n_rows_med26": n_rows_med26,
            "adds": adds_total if sec == "_TOTAL" else None,
            "removes": removes_total if sec == "_TOTAL" else None,
        })

    total_book = sum(r["book_size"] for r in rows_out
                      if r["sector"] != "_TOTAL" and r["book_size"] is not None)
    for r in rows_out:
        if r["sector"] == "_TOTAL":
            r["book_size"] = total_book if total_book else None
            r["book_size_asof"] = d  # sum of each sector's own as-of date; d = the roll-up date

    return replace_for_date(session, "drv_sss_breadth", "as_of_date", as_of_date, rows_out)


derive_sss_breadth = _wrap("drv_sss_breadth", _derive_sss_breadth_impl)
