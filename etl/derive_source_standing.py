"""derive_source_standing — canonical per-source standing layer.

Builds drv_source_standing (one row per as_of_date / source_code / tos_symbol)
from the LATEST WHOLE LOAD <= D for each source. Only on_list=TRUE rows are
written; absence = removed. Wire into derive_all() BEFORE the action and signal
consumers (drv_outlooks, derive_outlook_action, derive_actionable).

Sources and rules:
  SSS  — latest hist_sss snapshot_date <= D; whole load; signal math applied
  ETF  — latest hist_etf snapshot <= D + etfchg patches; NEUTRAL excluded
  II   — latest hist_ii  snapshot <= D + iichg patches;  NEUTRAL excluded
  PS   — latest hist_ps  snapshot_date <= D; whole load; rank stored
  RR   — drv_rr WHERE as_of_date=D (already built); weight/outlook from hist_rr
  CALL — 30-day per-symbol window (the ONE exception to whole-load rule)

Behavior rules baked in (per user acceptance criteria):
  - SSS: whole-snapshot; no per-symbol carry-forward
  - SSS INCREASE/REDUCE actions remain demoted (no change here; handled downstream)
  - PS: REMOVE emitted even when not held (consolidated/final action suppresses it)
  - Default Actionable screen: held REMOVE on top; not-held REMOVE hidden (UI)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import (
    _wrap,
    _clean, _load_outlook_weights, _outlook_to_weight,  # TASK_56: consolidated
    normalize_change_str,  # D1: canonical change_str normalizer
    etf_ii_patch_outlook,  # D3: ETFCHG/IICHG add/remove-aware patch resolver
)

log = logging.getLogger("etl.derive_source_standing")

_TARGET = "drv_source_standing"


# ---------------------------------------------------------------------------
# SSS builder (Increment 1)
# ---------------------------------------------------------------------------

def _build_sss(session: Session, as_of_date: date, run_id: int) -> list[dict]:
    """Build SSS rows for drv_source_standing.

    Rule: latest whole hist_sss snapshot <= D.  The entire load at that date
    is used.  A symbol absent from that load has NO row (no carry-forward).
    Signals are computed from hist_sss columns (same math as derive_v2.py
    _derive_sss_v2_impl).
    """
    # Latest whole SSS snapshot date <= D
    snap_row = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_sss WHERE snapshot_date <= :d"
    ), {"d": as_of_date}).first()
    snap = snap_row[0] if snap_row else None
    if not snap:
        return []

    rows = session.execute(text("""
        SELECT tos_symbol, pct_delta, anlst_best_idea_rank
        FROM hist_sss
        WHERE snapshot_date = :snap
          AND tos_symbol IS NOT NULL
    """), {"snap": snap}).fetchall()

    out: list[dict] = []
    for r in rows:
        sym = r[0]
        if not sym:
            continue

        anlst_raw = (r[2] or "").strip()

        # H Rank
        if anlst_raw.lower() == "kmsignal":
            rank = 99
        elif anlst_raw.lower() == "bench":
            rank = 50
        else:
            try:
                rank = float(anlst_raw.split("/")[0]) if "/" in anlst_raw else None
            except ValueError:
                rank = None

        # E Unranked
        unranked = anlst_raw.lower() in ("kmsignal", "bench")

        # D Rank HL
        rank_hl = (rank if rank is not None else 0) if not unranked else 0

        # F Signal (pct_delta)
        signal = _clean(r[1])

        # J Signal Sign
        if signal > 0.5:
            sig_sign = 3
        elif signal > 0.25:
            sig_sign = 2
        elif signal > 0:
            sig_sign = 1
        else:
            sig_sign = -1

        out.append({
            "as_of_date":    as_of_date,
            "source_code":   "SSS",
            "tos_symbol":    sym,
            "snapshot_date": snap,
            "on_list":       True,
            "weight":        None,
            "rank":          rank,
            "raw_value":     signal,
            "signal_sign":   sig_sign,
            "rank_hl":       rank_hl,
            "outlook":       None,
            "modifier":      None,
            "source_run_id": run_id,
        })
    return out


# ---------------------------------------------------------------------------
# ETF + II builder (Increment 2)
# ---------------------------------------------------------------------------

# D1: _normalize_change_str removed — use normalize_change_str from _derive_common.


def _build_etf_ii(session: Session, as_of_date: date,
                  base_table: str, change_table: str,
                  source_code: str,
                  wt_map: dict[str, float], run_id: int) -> list[dict]:
    """Bundle-cap logic: latest hist_etf/hist_ii snapshot <= D + patches.

    NEUTRAL or absent = excluded (no row in drv_source_standing).
    """
    # Latest base snapshot <= D
    snap_row = session.execute(text(
        f"SELECT MAX(snapshot_date) FROM {base_table} "
        "WHERE snapshot_date <= :d"
    ), {"d": as_of_date}).first()
    snap = snap_row[0] if snap_row else None
    if not snap:
        return []

    # Base rows from snapshot
    base_rows = session.execute(text(
        f"SELECT tos_symbol, outlook FROM {base_table} "
        "WHERE snapshot_date = :snap AND tos_symbol IS NOT NULL"
    ), {"snap": snap}).fetchall()

    # Effective outlook per symbol (base + patches)
    effective: dict[str, tuple[str, date]] = {}
    for sym, outlook in base_rows:
        if sym:
            effective[sym] = (outlook, snap)

    # Apply intra-period patches (event_date > snap AND <= D)
    patch_rows = session.execute(text(
        f"SELECT tos_symbol, change_str, outlook, event_date "
        f"FROM {change_table} "
        "WHERE event_date > :snap AND event_date <= :d "
        "  AND tos_symbol IS NOT NULL "
        "ORDER BY event_date ASC"
    ), {"snap": snap, "d": as_of_date}).fetchall()

    for sym, change_str, patch_outlook, ev_date in patch_rows:
        if not sym:
            continue
        normalized = etf_ii_patch_outlook(change_str, patch_outlook)
        if normalized:
            # Patches override base; later patches override earlier
            effective[sym] = (normalized, ev_date)

    out: list[dict] = []
    for sym, (outlook, eff_date) in effective.items():
        if not outlook:
            continue
        if str(outlook).upper() == "NEUTRAL":
            continue
        w = _outlook_to_weight(outlook, None, wt_map)
        if w is None:
            continue
        out.append({
            "as_of_date":    as_of_date,
            "source_code":   source_code,
            "tos_symbol":    sym,
            "snapshot_date": eff_date,
            "on_list":       True,
            "weight":        w,
            "rank":          None,
            "raw_value":     None,
            "signal_sign":   None,
            "rank_hl":       None,
            "outlook":       outlook,
            "modifier":      None,
            "source_run_id": run_id,
        })
    return out


# ---------------------------------------------------------------------------
# PS builder (Increment 3)
# ---------------------------------------------------------------------------

def _build_ps(session: Session, as_of_date: date, run_id: int) -> list[dict]:
    """PS: latest whole hist_ps snapshot <= D.

    Emits a row for every symbol on that snapshot, including those that
    dropped from it (they will have no row here, so action path sees REMOVE).
    Only on_list=TRUE rows are written — symbols absent from the latest
    snapshot simply have no row.
    """
    snap_row = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_ps WHERE snapshot_date <= :d"
    ), {"d": as_of_date}).first()
    snap = snap_row[0] if snap_row else None
    if not snap:
        return []

    rows = session.execute(text(
        "SELECT tos_symbol, rank FROM hist_ps "
        "WHERE snapshot_date = :snap AND tos_symbol IS NOT NULL"
    ), {"snap": snap}).fetchall()

    out: list[dict] = []
    for sym, rank in rows:
        if not sym:
            continue
        out.append({
            "as_of_date":    as_of_date,
            "source_code":   "PS",
            "tos_symbol":    sym,
            "snapshot_date": snap,
            "on_list":       True,
            "weight":        None,
            "rank":          rank,
            "raw_value":     None,
            "signal_sign":   None,
            "rank_hl":       None,
            "outlook":       None,
            "modifier":      None,
            "source_run_id": run_id,
        })
    return out


# ---------------------------------------------------------------------------
# RR builder (Increment 4)
# ---------------------------------------------------------------------------

def _build_rr(session: Session, as_of_date: date,
              wt_map: dict[str, float], run_id: int) -> list[dict]:
    """RR: reads drv_rr WHERE as_of_date=D (already built by derive_rr).

    Joins the latest hist_rr outlook <= D per symbol.
    """
    rows = session.execute(text("""
        SELECT r.tos_symbol,
               h.outlook,
               h.snapshot_date AS snap
        FROM drv_rr r
        LEFT JOIN LATERAL (
            SELECT outlook, snapshot_date FROM hist_rr
            WHERE tos_symbol = r.tos_symbol
              AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        ) h ON TRUE
        WHERE r.as_of_date = :d
          AND r.tos_symbol IS NOT NULL
    """), {"d": as_of_date}).fetchall()

    out: list[dict] = []
    for sym, outlook, snap in rows:
        if not sym:
            continue
        w = _outlook_to_weight(outlook, None, wt_map)
        out.append({
            "as_of_date":    as_of_date,
            "source_code":   "RR",
            "tos_symbol":    sym,
            "snapshot_date": snap,
            "on_list":       True,
            "weight":        w,
            "rank":          None,
            "raw_value":     None,
            "signal_sign":   None,
            "rank_hl":       None,
            "outlook":       outlook,
            "modifier":      None,
            "source_run_id": run_id,
        })
    return out


# ---------------------------------------------------------------------------
# CALL builder (Increment 5) — window exception
# ---------------------------------------------------------------------------

def _build_call(session: Session, as_of_date: date,
                lookback_days: int,
                wt_map: dict[str, float], run_id: int) -> list[dict]:
    """CALL: 30-day per-symbol window (the only carry-forward exception).

    Most recent hist_call row per symbol within [D-lookback_days, D].
    """
    rows = session.execute(text("""
        WITH ranked AS (
            SELECT tos_symbol, outlook, outlook_modifier, snapshot_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY tos_symbol ORDER BY snapshot_date DESC
                   ) AS rk
            FROM hist_call
            WHERE snapshot_date <= :d
              AND snapshot_date >= :cutoff
              AND tos_symbol IS NOT NULL
        )
        SELECT tos_symbol, outlook, outlook_modifier, snapshot_date
        FROM ranked WHERE rk = 1
    """), {"d": as_of_date,
           "cutoff": as_of_date - timedelta(days=lookback_days)}).fetchall()

    out: list[dict] = []
    for sym, outlook, modifier, snap in rows:
        if not sym:
            continue
        w = _outlook_to_weight(outlook, modifier, wt_map)
        out.append({
            "as_of_date":    as_of_date,
            "source_code":   "CALL",
            "tos_symbol":    sym,
            "snapshot_date": snap,
            "on_list":       True,
            "weight":        w,
            "rank":          None,
            "raw_value":     None,
            "signal_sign":   None,
            "rank_hl":       None,
            "outlook":       outlook,
            "modifier":      modifier,
            "source_run_id": run_id,
        })
    return out


# ---------------------------------------------------------------------------
# Main deriver
# ---------------------------------------------------------------------------

def _derive_source_standing_impl(session: Session,
                                  as_of_date: date, run_id: int) -> int:
    """Build drv_source_standing for as_of_date (idempotent)."""
    # Delete current date's rows
    session.execute(
        text("DELETE FROM drv_source_standing WHERE as_of_date = :d"),
        {"d": as_of_date},
    )

    wt_map = _load_outlook_weights(session)

    # Collect rows from all sources
    all_rows: list[dict] = []

    # Increment 1 — SSS
    try:
        all_rows.extend(_build_sss(session, as_of_date, run_id))
    except Exception as e:
        log.warning("derive_source_standing SSS failed: %s", e)

    # Increment 2 — ETF
    try:
        all_rows.extend(_build_etf_ii(
            session, as_of_date,
            "hist_etf", "hist_etfchg", "ETF", wt_map, run_id))
    except Exception as e:
        log.warning("derive_source_standing ETF failed: %s", e)

    # Increment 2 — II
    try:
        all_rows.extend(_build_etf_ii(
            session, as_of_date,
            "hist_ii", "hist_iichg", "II", wt_map, run_id))
    except Exception as e:
        log.warning("derive_source_standing II failed: %s", e)

    # Increment 3 — PS
    try:
        all_rows.extend(_build_ps(session, as_of_date, run_id))
    except Exception as e:
        log.warning("derive_source_standing PS failed: %s", e)

    # Increment 4 — RR
    try:
        all_rows.extend(_build_rr(session, as_of_date, wt_map, run_id))
    except Exception as e:
        log.warning("derive_source_standing RR failed: %s", e)

    # Increment 5 — CALL (30-day window)
    try:
        all_rows.extend(_build_call(session, as_of_date, 30, wt_map, run_id))
    except Exception as e:
        log.warning("derive_source_standing CALL failed: %s", e)

    if not all_rows:
        return 0

    insert_sql = text("""
        INSERT INTO drv_source_standing
          (as_of_date, source_code, tos_symbol, snapshot_date, on_list,
           weight, rank, raw_value, signal_sign, rank_hl,
           outlook, modifier, source_run_id)
        VALUES
          (:as_of_date, :source_code, :tos_symbol, :snapshot_date, :on_list,
           :weight, :rank, :raw_value, :signal_sign, :rank_hl,
           :outlook, :modifier, :source_run_id)
        ON CONFLICT (as_of_date, source_code, tos_symbol) DO NOTHING
    """)
    for row in all_rows:
        session.execute(insert_sql, row)

    return len(all_rows)


derive_source_standing = _wrap(_TARGET, _derive_source_standing_impl)
