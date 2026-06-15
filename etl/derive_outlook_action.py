"""derive_outlook_action — per-source action computation.

Reads ref_outlook_source. For each (symbol, source):
  1. Compute base_weight via base_weight_method
  2. Fetch prev_weight from most recent prior snapshot
  3. Apply snapshot-presence rules (REMOVE on drop, ADD on new)
  4. Apply held vs not-held action branching
  5. Write to drv_outlook_action

Wired into etl.derive.derive_all() AFTER derive_stks (needs nothing from drv_stks
itself, but logically belongs after the rules engine in the pipeline).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text, insert
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_outlook_action")


# ─────────────────────────────────────────────────────────────────────────────
# Inlined _wrap / run-tracking (mirror derive_v2.py pattern; avoid circ import)
# ─────────────────────────────────────────────────────────────────────────────

def _open_drv_run(session: Session, target: str, as_of_date: date,
                  parent_run_id: Optional[int] = None) -> int:
    row = session.execute(text(f"""
        INSERT INTO meta_derived_run (as_of_date, target_table, status, parent_run_id)
        VALUES ('{as_of_date}', '{target}', 'running', {parent_run_id})
        RETURNING run_id
    """)).first()
    return row[0] if row else 0


def _close_drv_run(session: Session, run_id: int, *, rows_built: int = 0,
                   status: str = "success", error_msg: Optional[str] = None) -> None:
    if not run_id:
        return
    session.execute(text(f"""
        UPDATE meta_derived_run SET rows_built={rows_built}, status='{status}', error_msg='{error_msg}'
        WHERE run_id = {run_id}
    """))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_outlook_weights(session: Session) -> dict[str, float]:
    """Lookup {OUTLOOK_TEXT_UPPER: weight} from ref_param sheet='outlook'."""
    rows = session.execute(text("""
        SELECT param_name, value FROM ref_param WHERE sheet = 'outlook'
    """)).fetchall()
    out: dict[str, float] = {}
    for name, val in rows:
        try:
            out[name.upper()] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            continue
    out.setdefault("BULLISH",  3.0)
    out.setdefault("BEARISH", -3.0)
    out.setdefault("NEUTRAL",  0.0)
    return out


def _resolve_outlook_weight(outlook: Optional[str], modifier: Optional[str],
                            wt_map: dict[str, float]) -> Optional[float]:
    if not outlook:
        return None
    base = wt_map.get(str(outlook).upper())
    if base is None:
        return 0.0
    if modifier and "bench" in str(modifier).lower():
        return base / 3.0
    return base


def _load_holdings(session: Session, as_of_date: date) -> set[str]:
    """Return the set of symbols where SUM(qty) > 0 across hist_f + hist_cs
    on or before as_of_date (using the latest snapshot per source)."""
    rows = session.execute(text(f"""
        WITH fid AS (
            SELECT tos_symbol, SUM(qty) AS qty
            FROM hist_f
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= '{as_of_date}')
            GROUP BY tos_symbol
        ),
        cs AS (
            SELECT tos_symbol, SUM(qty) AS qty
            FROM hist_cs
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= '{as_of_date}')
            GROUP BY tos_symbol
        )
        SELECT COALESCE(fid.tos_symbol, cs.tos_symbol) AS tos_symbol,
               COALESCE(fid.qty, 0) + COALESCE(cs.qty, 0) AS qty_total
        FROM fid FULL OUTER JOIN cs ON cs.tos_symbol = fid.tos_symbol
    """)).fetchall()
    return {r[0] for r in rows if r[1] and float(r[1]) > 0}


# ─────────────────────────────────────────────────────────────────────────────
# Per-source readers — return {symbol: weight_or_rank_payload}
# Each must return BOTH today's snapshot AND most recent prior snapshot.
# ─────────────────────────────────────────────────────────────────────────────

# Maps source_table -> the column that holds the outlook modifier (None = no modifier column)
_TABLE_MODIFIER_COL: dict[str, Optional[str]] = {
    "hist_call":   "outlook_modifier",
    "hist_etf":    None,    # hist_etf.outlook_modifier dropped — outlook is the only signal
    "hist_etfchg": None,
    "hist_ii":     None,
    "hist_iichg":  None,
    "hist_pk":     None,    # hist_pk (formerly hist_psrk) — no modifier column
    "hist_rr":     None,    # hist_rr.modifier dropped 2026-05-12 — RR outlook is the only signal
}


def _source_has_rows_in_window(session: Session, table: str, date_col: str,
                               as_of_date: date, lookback_days: int) -> bool:
    """
    True iff the source table has at least one row in the window
    `[as_of_date - lookback_days, as_of_date]`. Used by sparse sources
    (e.g. CALL) where exact-match on as_of_date misses live calls.
    """
    row = session.execute(
        text(f"""
            SELECT 1 FROM {table}
             WHERE {date_col} <= '{as_of_date}'
               AND {date_col} >= ('{as_of_date}'::date - ('{lookback_days}' || ' days')::interval)::date
             LIMIT 1
        """)).first()
    return row is not None


def _source_has_rows_for_date(session: Session, table: str, date_col: str,
                              as_of_date: date) -> bool:
    """
    True iff the source table has at least one row for `as_of_date`.

    Used to distinguish "source loaded but symbols dropped" (legitimate REMOVE)
    from "source not loaded for this date yet" (must NOT emit phantom REMOVEs).
    Without this guard, every symbol present in the most recent prior snapshot
    would be classified as REMOVE on dates where the source weren't refreshed,
    producing a flood of false 'dropped from snapshot' actions.
    """
    row = session.execute(
        text(f"SELECT 1 FROM {table} WHERE {date_col} = '{as_of_date}' LIMIT 1")).first()
    return row is not None


def _find_period_snapshots(session: Session, table: str, date_col: str,
                           as_of_date: date, period_dow: int) -> tuple[Optional[date], Optional[date]]:
    """
    Find current and previous period snapshot dates for periodic sources (ETF/II).

    period_dow: 0=Sunday (for ETF), 1=Monday (for II), etc.
    Returns: (current_period_snapshot_date, previous_period_snapshot_date)

    Example for ETF (period_dow=0, Sunday):
      - as_of_date = Wed 5/15 → current = Sun 5/10, previous = Sun 5/3
      - as_of_date = Sun 5/10 → current = Sun 5/10, previous = Sun 5/3
    """
    # Find the most recent snapshot on/before as_of_date with the target day-of-week
    current_row = session.execute(text(f"""
        SELECT MAX({date_col})
        FROM {table}
        WHERE {date_col} <= '{as_of_date}'
          AND EXTRACT(DOW FROM {date_col}) = {period_dow}
    """)).first()
    current_snap = current_row[0] if current_row and current_row[0] else None

    # Find the snapshot before that
    previous_snap = None
    if current_snap:
        prev_row = session.execute(text(f"""
            SELECT MAX({date_col})
            FROM {table}
            WHERE {date_col} < '{current_snap}'
              AND EXTRACT(DOW FROM {date_col}) = {period_dow}
        """)).first()
        previous_snap = prev_row[0] if prev_row and prev_row[0] else None

    return current_snap, previous_snap


_WEEKDAY_DOW = {'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6}


def _load_anchor_dow(session: Session, table: str, default_dow: int = 5) -> int:
    """Day-of-week (PG DOW: 0=Sun..6=Sat) anchoring a weekly source period,
    read from ref_load_files.week_day for the source's target_table. Falls
    back to default_dow when absent or not a specific weekday."""
    row = session.execute(text(
        "SELECT week_day FROM ref_load_files "
        "WHERE target_table = :tbl ORDER BY file_time LIMIT 1"
    ), {"tbl": table}).first()
    if row and row[0]:
        return _WEEKDAY_DOW.get(str(row[0]).strip().upper(), default_dow)
    return default_dow


def _find_week_period_snapshots(session: Session, table: str, date_col: str,
                                as_of_date: date, anchor_dow: int
                                ) -> tuple[Optional[date], Optional[date]]:
    """Latest snapshot in as_of_date's week and latest in the previous week.

    A "week" is bucketed on anchor_dow; week_start = as_of_date minus
    ((dow(as_of_date) - anchor_dow + 7) % 7) -- the same anchor formula
    api/routers/monitor.py uses for window_start. Either result may be None.
    """
    row = session.execute(text(f"""
        WITH anchor AS (
            SELECT (DATE '{as_of_date}'
                    - ((EXTRACT(DOW FROM DATE '{as_of_date}')::int
                        - {anchor_dow} + 7) % 7)) AS ws
        )
        SELECT
          (SELECT MAX({date_col}) FROM {table}, anchor
            WHERE {date_col} >= anchor.ws
              AND {date_col} <= DATE '{as_of_date}'),
          (SELECT MAX({date_col}) FROM {table}, anchor
            WHERE {date_col} >= anchor.ws - 7
              AND {date_col} <  anchor.ws)
    """)).first()
    return (row[0], row[1]) if row else (None, None)



# =============================================================================
# v2 effective-state helpers (2026-05-12)
# =============================================================================
# Each returns {symbol: weight} at a single date. Callers fetch (today,
# yesterday) and compare via _action_standing.

def _normalize_change_str_sql(col_expr: str) -> str:
    """SQL CASE that maps etfchg/iichg change_str into hist_etf-style outlook tokens."""
    return f"""CASE UPPER(COALESCE({col_expr},''))
            WHEN 'LONG'    THEN 'BULLISH'
            WHEN 'SHORT'   THEN 'BEARISH'
            WHEN 'NEUTRAL' THEN 'NEUTRAL'
            ELSE {col_expr}
        END"""


def _state_etf_ii(session: Session, base_table: str, change_table: str,
                  as_of_date: date, wt_map: dict[str, float]) -> dict:
    """Effective state at as_of_date for an ETF+ETFCHG-style pair.

    Bundle-capped (2026-05-12): only the LATEST hist_etf snapshot ≤ as_of_date
    is consulted as the baseline, plus any hist_etfchg patches between that
    snapshot and as_of_date. A symbol dropped from the latest snapshot is
    treated as gone — older snapshots are NOT consulted.

    Returns {symbol: weight}. Symbols whose latest effective outlook is
    NEUTRAL or NULL are excluded (Neutral = removed from list).
    """
    chg_norm = _normalize_change_str_sql("change_str")
    # BUNDLE-CAP RULE: only consult the LATEST hist_etf snapshot ≤ as_of_date
    # (the current "weekly bundle") plus any etfchg patches that arrived
    # AFTER that snapshot and on/before as_of_date. Rows from older
    # snapshots are intentionally ignored — a symbol dropped from the most
    # recent snapshot is gone, not "still BULLISH from two weeks ago".
    #
    # The caller invokes this helper twice (today and yesterday) and compares
    # the two effective states. On Mon-Sat both calls hit the same snapshot
    # so the diff surfaces intra-week etfchg patches. On Sunday the snapshot
    # rotates so today's bundle = new snapshot; yesterday's bundle = the
    # complete previous bundle. That produces the cross-bundle REMOVE/ADD
    # signals on rotation while still capturing intra-week add/remove cycles
    # day by day.
    rows = session.execute(
        text(f"""
            WITH latest_snap AS (
                SELECT MAX(snapshot_date) AS d FROM {base_table}
                 WHERE snapshot_date <= '{as_of_date}'
            ),
            bundle_base AS (
                SELECT symbol, outlook, snapshot_date AS d
                  FROM {base_table}
                 WHERE snapshot_date = (SELECT d FROM latest_snap)
            ),
            bundle_patches AS (
                SELECT symbol, ({chg_norm}) AS outlook, event_date AS d
                  FROM {change_table}
                 WHERE event_date > (SELECT d FROM latest_snap)
                   AND event_date <= '{as_of_date}'
                   AND change_str IS NOT NULL
            ),
            unified AS (
                SELECT * FROM bundle_base
                UNION ALL
                SELECT * FROM bundle_patches
            ),
            ranked AS (
                SELECT symbol, outlook, d,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY d DESC) AS rk
                  FROM unified
            )
            SELECT symbol, outlook FROM ranked WHERE rk = 1
        """)).fetchall()
    result: dict = {}
    for sym, outlook in rows:
        if not outlook:
            continue
        if str(outlook).upper() == "NEUTRAL":
            continue
        w = _resolve_outlook_weight(outlook, None, wt_map)
        if w is not None:
            result[sym] = w
    return result


def _state_etf_ii_tos(session: Session, base_table: str, change_table: str,
                      as_of_date: date, wt_map: dict[str, float]) -> dict:
    """Like _state_etf_ii but keys result on tos_symbol instead of raw symbol.

    Used to load the PREVIOUS period's effective state for comparison, so that
    held-detection and action classification use the normalized tos_symbol key.
    """
    chg_norm = _normalize_change_str_sql("change_str")
    rows = session.execute(
        text(f"""
            WITH latest_snap AS (
                SELECT MAX(snapshot_date) AS d FROM {base_table}
                 WHERE snapshot_date <= '{as_of_date}'
            ),
            bundle_base AS (
                SELECT COALESCE(tos_symbol, symbol) AS sym,
                       outlook, snapshot_date AS d
                  FROM {base_table}
                 WHERE snapshot_date = (SELECT d FROM latest_snap)
            ),
            bundle_patches AS (
                SELECT COALESCE(tos_symbol, symbol) AS sym,
                       ({chg_norm}) AS outlook, event_date AS d
                  FROM {change_table}
                 WHERE event_date > (SELECT d FROM latest_snap)
                   AND event_date <= '{as_of_date}'
                   AND change_str IS NOT NULL
            ),
            unified AS (
                SELECT * FROM bundle_base
                UNION ALL
                SELECT * FROM bundle_patches
            ),
            ranked AS (
                SELECT sym, outlook, d,
                       ROW_NUMBER() OVER (PARTITION BY sym ORDER BY d DESC) AS rk
                  FROM unified
            )
            SELECT sym, outlook FROM ranked WHERE rk = 1
        """)).fetchall()
    result: dict = {}
    for sym, outlook in rows:
        if not outlook:
            continue
        if str(outlook).upper() == "NEUTRAL":
            continue
        w = _resolve_outlook_weight(outlook, None, wt_map)
        if w is not None:
            result[sym] = w
    return result


def _state_dense(session: Session, table: str, date_col: str,
                 as_of_date: date, wt_map: dict[str, float]) -> dict:
    """Effective state at as_of_date for a dense source (exact-match on date)."""
    mod_col = _TABLE_MODIFIER_COL.get(table, None)
    mod_expr = f"COALESCE({mod_col}, '')" if mod_col else "''"
    # hist_rr uses tos_symbol instead of symbol
    sym_col = "tos_symbol" if table == "hist_rr" else "symbol"
    rows = session.execute(
        text(f"""
            SELECT {sym_col}, outlook, {mod_expr} AS modifier
              FROM {table}
             WHERE {date_col} = '{as_of_date}'
               AND {sym_col} IS NOT NULL
        """)).fetchall()
    return {r[0]: _resolve_outlook_weight(r[1], r[2], wt_map) for r in rows}


def _state_window(session: Session, table: str, date_col: str,
                  as_of_date: date, wt_map: dict[str, float],
                  lookback_days: int) -> dict:
    """Effective state at as_of_date for a sparse source (CALL).

    The symbol's most recent row within [as_of_date - lookback_days, as_of_date].
    Symbols with no row in window are absent — under v2 with
    suppress_disappearance=True, that produces no action (silent aging-out).
    """
    mod_col = _TABLE_MODIFIER_COL.get(table, None)
    mod_expr = f"COALESCE({mod_col}, '')" if mod_col else "''"
    rows = session.execute(
        text(f"""
            WITH ranked AS (
                SELECT symbol, outlook, {mod_expr} AS modifier,
                       {date_col} AS d,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol
                           ORDER BY {date_col} DESC
                       ) AS rk
                  FROM {table}
                 WHERE {date_col} <= '{as_of_date}'
                   AND {date_col} >= ('{as_of_date}'::date - ('{lookback_days}' || ' days')::interval)::date
            )
            SELECT symbol, outlook, modifier FROM ranked WHERE rk = 1
        """)).fetchall()
    return {r[0]: _resolve_outlook_weight(r[1], r[2], wt_map) for r in rows}


def _outlook_per_symbol_window_snapshots(
    session: Session, table: str, date_col: str, as_of_date: date,
    wt_map: dict[str, float], lookback_days: int,
) -> tuple[dict, dict, dict]:
    """
    Sparse-source variant of _outlook_modifier_snapshots.

    Semantics: a call stays "active" for `lookback_days` after its last row.
    So for each symbol we compute TWO most-recent rows within the window
    `[as_of_date - lookback_days, as_of_date]`:

      today_w[sym]  = weight of the most recent row (rk=1)
      prev_w[sym]   = weight of the row before that (rk=2), if any
      prev_date_by_sym[sym] = date of that rk=2 row

    If a symbol has only one row in the window (rk=1 only), prev_w[sym] is
    absent — the classifier will see (base=w, prev=None) and decide ADD.
    If a symbol has no row in the window at all, it's not in today_w —
    the classifier never sees it, so no spurious REMOVE fires just because
    the symbol wasn't refreshed.

    Action mapping is unchanged; only the lookup logic differs.

    Returns (today_w, prev_w, prev_date_by_sym).
    """
    mod_col = _TABLE_MODIFIER_COL.get(table, None)
    mod_expr = f"COALESCE({mod_col}, '')" if mod_col else "''"

    rows = session.execute(
        text(f"""
            WITH ranked AS (
                SELECT symbol, outlook, {mod_expr} AS modifier,
                       {date_col} AS d,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol
                           ORDER BY {date_col} DESC
                       ) AS rk
                FROM {table}
                WHERE {date_col} <= '{as_of_date}'
                  AND {date_col} >= ('{as_of_date}'::date - ('{lookback_days}' || ' days')::interval)::date
            )
            SELECT symbol, outlook, modifier, d, rk
              FROM ranked
             WHERE rk <= 2
             ORDER BY symbol, rk
        """)).fetchall()

    today_w: dict = {}
    prev_w: dict = {}
    prev_date_by_sym: dict = {}
    for r in rows:
        sym, outlook, modifier, d, rk = r[0], r[1], r[2], r[3], int(r[4])
        w = _resolve_outlook_weight(outlook, modifier, wt_map)
        if rk == 1:
            today_w[sym] = w
        elif rk == 2:
            prev_w[sym] = w
            prev_date_by_sym[sym] = d
    return today_w, prev_w, prev_date_by_sym


def _outlook_modifier_snapshots(session: Session, table: str, date_col: str,
                                as_of_date: date,
                                wt_map: dict[str, float]) -> tuple[dict, dict, Optional[date]]:
    """For tables with outlook + optional modifier column. Returns
    (today_weights: {sym: float}, prev_weights: {sym: float}, prev_date)."""
    mod_col = _TABLE_MODIFIER_COL.get(table, None)
    mod_expr = f"COALESCE({mod_col}, '')" if mod_col else "''"
    today = session.execute(
        text(f"""
            SELECT symbol, outlook, {mod_expr} AS modifier
            FROM {table}
            WHERE {date_col} = '{as_of_date}'
        """),
    ).fetchall()
    today_w = {r[0]: _resolve_outlook_weight(r[1], r[2], wt_map) for r in today}

    prev_date_row = session.execute(
        text(f"SELECT MAX({date_col}) FROM {table} WHERE {date_col} < '{as_of_date}'"),
    ).first()
    prev_date = prev_date_row[0] if prev_date_row else None
    prev_w: dict = {}
    if prev_date:
        prev = session.execute(
            text(f"""
                SELECT symbol, outlook, {mod_expr} AS modifier
                FROM {table}
                WHERE {date_col} = '{prev_date}'
            """),
        ).fetchall()
        prev_w = {r[0]: _resolve_outlook_weight(r[1], r[2], wt_map) for r in prev}
    return today_w, prev_w, prev_date


def _rank_snapshots(session: Session, table: str, date_col: str, rank_col: str,
                    key_col: str, as_of_date: date) -> tuple[dict, dict, Optional[date]]:
    """For tables with a numeric rank column.
    Returns (today_ranks: {sym: int}, prev_ranks: {sym: int}, prev_date)."""
    today = session.execute(
        text(f"SELECT {key_col} AS symbol, {rank_col} AS rk FROM {table} WHERE {date_col} = '{as_of_date}'"),
    ).fetchall()
    today_r = {r[0]: r[1] for r in today if r[1] is not None}

    prev_date_row = session.execute(
        text(f"SELECT MAX({date_col}) FROM {table} WHERE {date_col} < '{as_of_date}'"),
    ).first()
    prev_date = prev_date_row[0] if prev_date_row else None
    prev_r: dict = {}
    if prev_date:
        prev = session.execute(
            text(f"SELECT {key_col} AS symbol, {rank_col} AS rk FROM {table} WHERE {date_col} = '{prev_date}'"),
        ).fetchall()
        prev_r = {r[0]: r[1] for r in prev if r[1] is not None}
    return today_r, prev_r, prev_date


# ─────────────────────────────────────────────────────────────────────────────
# Action decision (per the design doc §4.2 / §4.3)
# ─────────────────────────────────────────────────────────────────────────────

def _action_outlook_modifier(base, prev, held: bool) -> tuple[Optional[str], str]:
    """Returns (action, reason)."""
    if base is None and prev is None:
        return None, "no data either snapshot"
    if base is None and prev is not None:
        return "REMOVE", "dropped from snapshot"
    if prev is None and base is not None:
        return "ADD", "new in snapshot"
    # both present
    if held:
        if base <= 0 and prev > 0:
            return "REMOVE", f"weight {prev:+g}→{base:+g} flipped non-positive while held"
        if base > 0 and prev <= 0:
            return "ADD", f"weight {prev:+g}→{base:+g} flipped positive (re-establishing)"
        if base > prev:
            return "INCREASE", f"weight {prev:+g}→{base:+g}"
        if base < prev:
            return "REDUCE", f"weight {prev:+g}→{base:+g}"
        return "HOLD", "weight unchanged"
    # not held — base-only
    if base is not None and base > 0:
        return "ADD", f"base outlook {base:+g}, not held"
    return None, "not held, no action"


def _action_standing(base, prev, held: bool = False,
                     drop_action: str = "REDUCE") -> tuple[Optional[str], str]:
    """Standing-list classifier (used by II, ETF, RR).

    Presence on the current list with a positive weight is a buy verdict
    every period, not just on first appearance. Held-vs-not is resolved
    downstream by derive_actionable suppression.

      base > 0                  -> ADD     (positive weight on the current list)
      base < 0                  -> REMOVE  (negative weight on the current list)
      base absent, prev present -> drop_action if held, else silent (dropped from list)
      otherwise                 -> silent

    drop_action defaults to "REDUCE".  Pass "REMOVE" for ETF so a symbol
    dropped from the ETF list while held triggers Sell All, not Sell Some.
    """
    if base is not None:
        try:
            b = float(base)
        except (TypeError, ValueError):
            return None, "non-numeric weight - no action"
        if b > 0:
            return "ADD", f"on list, weight {b:+g}"
        if b < 0:
            return "REMOVE", f"on list, weight {b:+g}"
        return None, "weight 0 - silent"
    if prev is not None:
        if held:
            try:
                return drop_action, f"dropped from list (was {float(prev):+g})"
            except (TypeError, ValueError):
                return drop_action, "dropped from list"
        else:
            return None, "dropped from list, not held"
    return None, "not on list"


def _action_rank(curr, prev, held: bool) -> tuple[Optional[str], str]:
    """Lower rank number = better.
    Returns (action, reason)."""
    if curr is None and prev is None:
        return None, "no data either snapshot"
    if curr is None and prev is not None:
        return "REMOVE" if held else None, "dropped from list"
    if prev is None and curr is not None:
        return "ADD", f"new on list at rank {curr}"
    # both present
    delta = float(curr) - float(prev)  # positive = rank degraded (number went up)
    if held:
        if delta < 0:
            return "INCREASE", f"rank improved {prev}→{curr}"
        if delta > 0:
            return "REDUCE", f"rank degraded {prev}→{curr}"
        return "HOLD", "rank unchanged"
    # not held - both snapshots present (curr-None cases handled above).
    # A rank improvement is still an INCREASE signal even with no position;
    # derive_actionable sizes a not-held INCREASE as MIN + Units (catch-up).
    if delta < 0:
        return "INCREASE", f"rank improved {prev}->{curr}, not held"
    return "ADD", f"on list at rank {curr}, not held"


def _action_sss_pct_delta(curr_pct, prev_pct, held: bool,
                          present_now: bool, present_prev: bool
                          ) -> tuple[Optional[str], str]:
    """SSS action from pct_delta only (the days-on rank no longer drives it).

    pct_delta = '% Delta Since Initial'. Compares the current weekly SSS
    snapshot to the previous one:
      - dropped from the list  -> REMOVE if held, else no action
      - new on the list        -> ADD
      - on the list both weeks -> pct_delta < 0  -> REMOVE
                                  pct_delta >= 0 -> week-over-week:
                                        rose  -> INCREASE
                                        fell  -> REDUCE
                                        equal -> HOLD
    """
    if not present_now and not present_prev:
        return None, "not on SSS list"
    if not present_now:
        if held:
            return "REMOVE", "dropped from SSS list"
        return None, "dropped from SSS list, not held"
    if not present_prev:
        return "ADD", "new on SSS list"
    # on the list both weeks
    try:
        cp = float(curr_pct) if curr_pct is not None else None
    except (TypeError, ValueError):
        cp = None
    if cp is None:
        return None, "no pct_delta value"
    if cp < 0:
        return "REMOVE", f"pct_delta {cp:+g} negative"
    try:
        pp = float(prev_pct) if prev_pct is not None else None
    except (TypeError, ValueError):
        pp = None
    if pp is None:
        return "HOLD", f"pct_delta {cp:+g}, no prior to compare"
    if cp > pp:
        return "INCREASE", f"pct_delta {pp:+g} -> {cp:+g} (rising)"
    if cp < pp:
        return "REDUCE", f"pct_delta {pp:+g} -> {cp:+g} (falling)"
    return "HOLD", f"pct_delta steady at {cp:+g}"


def _call_window_states(session: Session, table: str, date_col: str,
                        as_of_date: date, wt_map: dict[str, float],
                        lookback_days: int) -> dict:
    """Per-symbol CALL state for the standing-recommendation model.

    For every symbol with at least one row in
    [as_of_date - lookback_days, as_of_date], returns
        {symbol: (current_w, current_date, prior_diff_w, prior_diff_date)}
    where current_w is the weight of the most recent in-window row and
    prior_diff_w is the weight of the most recent older in-window row whose
    weight differs from current_w. prior_diff_w / prior_diff_date are None
    when every in-window row for the symbol carries the same weight.
    """
    mod_col = _TABLE_MODIFIER_COL.get(table, None)
    mod_expr = f"COALESCE({mod_col}, '')" if mod_col else "''"
    rows = session.execute(
        text(f"""
            SELECT symbol, outlook, {mod_expr} AS modifier, {date_col} AS d
              FROM {table}
             WHERE {date_col} <= '{as_of_date}'
               AND {date_col} >= ('{as_of_date}'::date
                                  - ('{lookback_days}' || ' days')::interval)::date
             ORDER BY symbol, {date_col} DESC
        """)).fetchall()
    out: dict = {}
    for sym, outlook, modifier, d in rows:
        w = _resolve_outlook_weight(outlook, modifier, wt_map)
        if sym not in out:
            out[sym] = [w, d, None, None]            # most recent row = current
        else:
            entry = out[sym]
            if entry[2] is None and w != entry[0]:   # first older differing weight
                entry[2] = w
                entry[3] = d
    return {sym: tuple(v) for sym, v in out.items()}


def _action_call_standing(current_w, prior_diff_w,
                          held: bool) -> tuple[Optional[str], str]:
    """Standing-recommendation classifier for CALL (sparse 30-day source).

    current_w    = weight of the most recent CALL row inside the 30-day window
    prior_diff_w = weight of the most recent in-window row whose weight differs
                   from current_w (None when the call has been flat all window)

    A positive call is a standing ADD/INCREASE until acted on; a non-positive
    call is a REMOVE while held. INCREASE/REDUCE surface only while a real
    weight change is still visible inside the window. INCREASE is emitted
    held-agnostically - derive_actionable sizes a not-held INCREASE as
    MIN + Units (catch-up).
    """
    if current_w is None:
        return None, "no CALL signal in window"
    try:
        cw = float(current_w)
    except (TypeError, ValueError):
        return None, "non-numeric CALL weight"
    if cw <= 0:
        if held:
            return "REMOVE", f"CALL weight {cw:+g} non-positive while held"
        return None, f"CALL weight {cw:+g} non-positive, not held"
    # cw > 0 - positive standing call
    pdw = None
    if prior_diff_w is not None:
        try:
            pdw = float(prior_diff_w)
        except (TypeError, ValueError):
            pdw = None
    if pdw is not None and pdw > 0:
        if cw > pdw:
            return "INCREASE", f"CALL weight {pdw:+g} -> {cw:+g}"
        if cw < pdw:
            if held:
                return "REDUCE", f"CALL weight {pdw:+g} -> {cw:+g} while held"
            return "ADD", f"CALL weight {pdw:+g} -> {cw:+g}, not held"
    return "ADD", f"CALL standing weight {cw:+g}"


# ─────────────────────────────────────────────────────────────────────────────
# Main derive function
# ─────────────────────────────────────────────────────────────────────────────

def _derive_outlook_action_impl(session: Session, as_of_date: date, run_id: int) -> int:
    # 0) prerequisites
    wt_map   = _load_outlook_weights(session)
    holdings = _load_holdings(session, as_of_date)

    sources = session.execute(text("""
        SELECT source_code, source_table, base_weight_method, position_category,
               lookback_days, loads_prior_day_data
        FROM ref_outlook_source
        WHERE deprecated_at IS NULL
        ORDER BY source_code
    """)).mappings().all()

    # 1) Wipe today
    session.execute(text(f"DELETE FROM drv_outlook_action WHERE as_of_date = '{as_of_date}'"))

    total_rows = 0
    insert_sql = text("""
        INSERT INTO drv_outlook_action
          (as_of_date, tos_symbol, source_code, base_weight, prev_weight, prev_date,
           weight_delta, held_today, action, action_reason, category,
           analyst_rank, source_run_id, source_snapshot_date)
        VALUES
          (:d, :sym, :sc, :base, :prev, :prev_d, :delta, :held, :act, :reason, :cat,
           :analyst_rank, :rid, :source_snap)
    """)

    for s in sources:
        sc        = s["source_code"]
        table     = s["source_table"]
        method    = s["base_weight_method"]
        category  = s["position_category"]

        # Determine date column for this table
        date_col = "event_date" if table in ("hist_etfchg", "hist_iichg") else "snapshot_date"
        key_col  = "ticker"    if table in ("hist_ps",) else "symbol"

        try:
            session.execute(text("SAVEPOINT sp_source"))
            if method == "outlook_modifier":
                # ── v2 routing (2026-05-12) ────────────────────────────────
                # ETF/II/RR -> standing-list classifier (_action_standing);
                # CALL -> standing-recommendation model (_action_call_standing).
                #   ETF/II — UNION their *chg patch tables
                #   CALL  — 30-day per-symbol window, aging-out silent
                #   RR    — dense exact-match on as_of_date
                yesterday = as_of_date - timedelta(days=1)
                _ETF_II_CHG = {"ETF": "hist_etfchg", "II": "hist_iichg"}

                if sc in _ETF_II_CHG:
                    # ETF/II: read current from drv_source_standing (bundle-cap,
                    # tos_symbol keyed). Previous from hist_*+chg with tos_symbol.
                    curr_etf_rows = session.execute(text("""
                        SELECT tos_symbol, weight, snapshot_date
                        FROM drv_source_standing
                        WHERE as_of_date = :d AND source_code = :sc
                    """), {"d": as_of_date, "sc": sc}).fetchall()

                    if not curr_etf_rows:
                        log.warning("source %s: no drv_source_standing rows at "
                                    "%s — skipping", sc, as_of_date)
                        session.execute(text("RELEASE SAVEPOINT sp_source"))
                        continue

                    curr_snap = curr_etf_rows[0][2]
                    today_w = {r[0]: r[1] for r in curr_etf_rows}

                    # Previous period: latest hist_etf/hist_ii snapshot before
                    # curr_snap (using tos_symbol for correct keying)
                    prev_snap_row = session.execute(text(
                        f"SELECT MAX(snapshot_date) FROM {table} "
                        "WHERE snapshot_date < :snap"
                    ), {"snap": curr_snap}).first()
                    prev_date = prev_snap_row[0] if prev_snap_row else None
                    prev_w: dict = {}
                    if prev_date:
                        # Use _state_etf_ii but remap symbol→tos_symbol via the
                        # tos_symbol column already populated in hist_* tables.
                        prev_w = _state_etf_ii_tos(
                            session, table, _ETF_II_CHG[sc],
                            prev_date, wt_map)
                    suppress = False
                elif sc == "CALL":
                    # CALL: read current from drv_source_standing (30-day window,
                    # tos_symbol keyed). Prior-diff detection via hist_call.
                    lb = int(s.get("lookback_days") or 30)
                    # Current CALL state from drv_source_standing
                    call_rows = session.execute(text("""
                        SELECT tos_symbol, weight, snapshot_date, modifier
                        FROM drv_source_standing
                        WHERE as_of_date = :d AND source_code = 'CALL'
                    """), {"d": as_of_date}).fetchall()
                    # Build call states {sym: (cur_w, cur_date, prior_diff_w, prior_diff_date)}
                    # by re-reading hist_call for the prior-diff detection only
                    cur_call_by_sym = {r[0]: (r[1], r[2]) for r in call_rows}
                    # Build prior-diff from hist_call for tos_symbol keyed symbols
                    prior_diff: dict = {}
                    if cur_call_by_sym:
                        cutoff = as_of_date - timedelta(days=lb)
                        hcall_rows = session.execute(text("""
                            WITH ranked AS (
                                SELECT COALESCE(tos_symbol, symbol) AS sym,
                                       outlook, outlook_modifier, snapshot_date,
                                       ROW_NUMBER() OVER (
                                           PARTITION BY COALESCE(tos_symbol, symbol)
                                           ORDER BY snapshot_date DESC
                                       ) AS rk
                                FROM hist_call
                                WHERE snapshot_date <= :d
                                  AND snapshot_date >= :cut
                                  AND COALESCE(tos_symbol, symbol) IS NOT NULL
                            )
                            SELECT sym, outlook, outlook_modifier, snapshot_date, rk
                            FROM ranked WHERE rk <= 2 ORDER BY sym, rk
                        """), {"d": as_of_date, "cut": cutoff}).fetchall()
                        for sym, outlook, modifier, snap, rk in hcall_rows:
                            w = _resolve_outlook_weight(outlook, modifier, wt_map)
                            if rk == 2:
                                cur_w = cur_call_by_sym.get(sym, (None, None))[0]
                                if cur_w != w:
                                    prior_diff[sym] = (w, snap)
                    call_batch = []
                    for csym, (cw, cd) in cur_call_by_sym.items():
                        chld = csym in holdings
                        pdw, pdd = prior_diff.get(csym, (None, None))
                        cact, creason = _action_call_standing(cw, pdw, chld)
                        if cact is None:
                            continue
                        cdelta = None
                        if cw is not None and pdw is not None:
                            try:
                                cdelta = float(cw) - float(pdw)
                            except (TypeError, ValueError):
                                cdelta = None
                        call_batch.append({
                            "d": as_of_date, "sym": csym, "sc": sc,
                            "base": cw, "prev": pdw, "prev_d": pdd,
                            "delta": cdelta, "held": chld, "act": cact,
                            "reason": creason, "cat": category, "rid": run_id,
                            "analyst_rank": None,
                            "source_snap": cd,
                        })
                    for crow in call_batch:
                        session.execute(insert_sql, crow)
                    total_rows += len(call_batch)
                    session.execute(text("RELEASE SAVEPOINT sp_source"))
                    continue
                else:
                    # RR (dense source). Read current from drv_source_standing
                    # (tos_symbol keyed). Previous from hist_rr with tos_symbol.
                    rr_rows = session.execute(text("""
                        SELECT tos_symbol, weight, snapshot_date
                        FROM drv_source_standing
                        WHERE as_of_date = :d AND source_code = 'RR'
                    """), {"d": as_of_date}).fetchall()

                    loads_prior = s.get("loads_prior_day_data", False)
                    comparison_date = as_of_date

                    if not rr_rows:
                        # Fallback: no standing rows — skip to avoid phantom REMOVEs
                        log.warning("source %s: no drv_source_standing rows at "
                                    "%s — skipping", sc, as_of_date)
                        session.execute(text("RELEASE SAVEPOINT sp_source"))
                        continue

                    today_w = {r[0]: r[1] for r in rr_rows}
                    curr_snap_rr = rr_rows[0][2]  # snapshot_date

                    # Previous: most recent hist_rr snapshot before curr_snap_rr
                    prev_date_row = session.execute(text(
                        "SELECT MAX(snapshot_date) FROM hist_rr "
                        "WHERE snapshot_date < :snap"
                    ), {"snap": curr_snap_rr}).first()
                    prev_date = prev_date_row[0] if prev_date_row else None
                    prev_w = _state_dense(
                        session, table, date_col, prev_date, wt_map
                    ) if prev_date else {}
                    suppress = False
                    curr_snap = curr_snap_rr  # used in action_date / source_snap below

                # Process actions for outlook_modifier sources (ETF/II, CALL, RR)
                action_date = curr_snap if sc in _ETF_II_CHG else as_of_date
                source_snap = curr_snap if sc in _ETF_II_CHG else comparison_date
                all_syms = set(today_w) | set(prev_w)
                batch = []
                for sym in all_syms:
                    base = today_w.get(sym)
                    prev = prev_w.get(sym)
                    held = sym in holdings
                    drop_act = "REMOVE" if sc == "ETF" else "REDUCE"
                    act, reason = _action_standing(base, prev, held, drop_act)
                    if act is None:
                        # No-op — skip writing the row entirely. Keeps
                        # drv_outlook_action focused on real signals.
                        continue
                    delta = None
                    if base is not None and prev is not None:
                        try:
                            delta = float(base) - float(prev)
                        except (TypeError, ValueError):
                            delta = None
                    batch.append({
                        "d": action_date, "sym": sym, "sc": sc,
                        "base": base, "prev": prev, "prev_d": prev_date,
                        "delta": delta, "held": held, "act": act,
                        "reason": reason, "cat": category, "rid": run_id,
                        "analyst_rank": None,
                        "source_snap": source_snap,
                    })
                if batch:
                    # Periodic sources (ETF/II/PS/SSS) key rows on the period
                    # snapshot date, not the derive date D, so the as_of_date=D
                    # wipe above misses them. Clear this source's rows for the
                    # date it is about to write before re-inserting, so a
                    # re-derive of any date in the period stays idempotent.
                    session.execute(text(
                        "DELETE FROM drv_outlook_action "
                        "WHERE source_code = :sc AND as_of_date = :d"
                    ), {"sc": sc, "d": batch[0]["d"]})
                    for row in batch:
                        session.execute(insert_sql, row)
                    total_rows += len(batch)

            elif method == "rank":
                # PS (weekly rank). Read current state from drv_source_standing
                # (whole-snapshot, tos_symbol keyed). Previous from hist_ps
                # with tos_symbol for correct comparison.
                curr_ps_rows = session.execute(text("""
                    SELECT tos_symbol, rank, snapshot_date
                    FROM drv_source_standing
                    WHERE as_of_date = :d AND source_code = 'PS'
                """), {"d": as_of_date}).fetchall()

                if not curr_ps_rows:
                    log.warning("source %s: no drv_source_standing rows for "
                                "PS at %s — skipping", sc, as_of_date)
                    session.execute(text("RELEASE SAVEPOINT sp_source"))
                    continue

                curr_snap = curr_ps_rows[0][2]  # snapshot_date
                today_r = {r[0]: r[1] for r in curr_ps_rows if r[1] is not None}

                # Previous snapshot: most recent hist_ps snapshot before curr_snap
                prev_snap_row = session.execute(text(f"""
                    SELECT MAX({date_col}) FROM {table}
                    WHERE {date_col} < :snap
                """), {"snap": curr_snap}).first()
                prev_date = prev_snap_row[0] if prev_snap_row else None
                prev_r: dict = {}
                if prev_date:
                    prev_rows = session.execute(text(f"""
                        SELECT tos_symbol, rank FROM {table}
                        WHERE {date_col} = :pd
                          AND tos_symbol IS NOT NULL
                          AND rank IS NOT NULL
                    """), {"pd": prev_date}).fetchall()
                    prev_r = {r[0]: r[1] for r in prev_rows}

                all_syms = set(today_r) | set(prev_r)
                batch = []
                for sym in all_syms:
                    curr = today_r.get(sym)
                    prev = prev_r.get(sym)
                    held = sym in holdings
                    act, reason = _action_rank(curr, prev, held)
                    # Behavior rule 3: PS drop emits REMOVE even when not held.
                    # _action_rank returns None for not-held drop; override for PS.
                    if act is None and curr is None and prev is not None:
                        act, reason = "REMOVE", "dropped from PS list (not held)"
                    # Skip if still no action (e.g. curr==prev==None)
                    if act is None:
                        continue
                    delta = None
                    if curr is not None and prev is not None:
                        try:
                            delta = float(curr) - float(prev)
                        except Exception:
                            delta = None
                    batch.append({
                        "d": curr_snap, "sym": sym, "sc": sc,
                        "base": curr, "prev": prev, "prev_d": prev_date,
                        "delta": delta, "held": held, "act": act,
                        "reason": reason, "cat": category, "rid": run_id,
                        "analyst_rank": None,
                        "source_snap": curr_snap,
                    })
                if batch:
                    session.execute(text(
                        "DELETE FROM drv_outlook_action "
                        "WHERE source_code = :sc AND as_of_date = :d"
                    ), {"sc": sc, "d": batch[0]["d"]})
                    for row in batch:
                        session.execute(insert_sql, row)
                    total_rows += len(batch)

            elif method == "rank_pct_delta":
                # SSS (weekly). Action is computed from pct_delta only;
                # anlst_best_idea_rank is display-only.
                # Reads current state from drv_source_standing (whole-snapshot,
                # tos_symbol keyed). Previous state from hist_sss with tos_symbol.
                # Guard: drv_source_standing must have SSS rows for as_of_date.
                curr_sss_rows = session.execute(text("""
                    SELECT tos_symbol, raw_value AS pd, rank AS arank,
                           snapshot_date
                    FROM drv_source_standing
                    WHERE as_of_date = :d AND source_code = 'SSS'
                """), {"d": as_of_date}).fetchall()

                if not curr_sss_rows:
                    log.warning("source %s: no drv_source_standing rows for "
                                "SSS at %s — skipping", sc, as_of_date)
                    session.execute(text("RELEASE SAVEPOINT sp_source"))
                    continue

                curr_snap = curr_sss_rows[0][3]  # snapshot_date from standing
                today = {r[0]: (r[1], r[2]) for r in curr_sss_rows}

                # Previous snapshot: most recent hist_sss snapshot before curr_snap
                prev_snap_row = session.execute(text(f"""
                    SELECT MAX({date_col}) FROM {table}
                    WHERE {date_col} < :snap
                """), {"snap": curr_snap}).first()
                prev_date = prev_snap_row[0] if prev_snap_row else None
                prev: dict = {}
                if prev_date:
                    prev_rows = session.execute(text(f"""
                        SELECT tos_symbol, pct_delta AS pd
                        FROM {table} WHERE {date_col} = :pd
                          AND tos_symbol IS NOT NULL
                    """), {"pd": prev_date}).fetchall()
                    prev = {r[0]: r[1] for r in prev_rows}

                all_syms = set(today) | set(prev)
                batch = []
                for sym in all_syms:
                    curr_pd, curr_arank = today.get(sym, (None, None))
                    prev_pd = prev.get(sym)
                    held = sym in holdings
                    act, reason = _action_sss_pct_delta(
                        curr_pd, prev_pd, held,
                        sym in today, sym in prev,
                    )
                    if act is None:
                        continue
                    delta = None
                    if curr_pd is not None and prev_pd is not None:
                        try:
                            delta = float(curr_pd) - float(prev_pd)
                        except (TypeError, ValueError):
                            delta = None
                    batch.append({
                        "d": curr_snap, "sym": sym, "sc": sc,
                        "base": curr_pd, "prev": prev_pd, "prev_d": prev_date,
                        "delta": delta, "held": held, "act": act,
                        "reason": reason, "cat": category, "rid": run_id,
                        "analyst_rank": curr_arank,
                        "source_snap": curr_snap,
                    })
                if batch:
                    # Periodic sources (ETF/II/PS/SSS) key rows on the period
                    # snapshot date, not the derive date D, so the as_of_date=D
                    # wipe above misses them. Clear this source's rows for the
                    # date it is about to write before re-inserting, so a
                    # re-derive of any date in the period stays idempotent.
                    session.execute(text(
                        "DELETE FROM drv_outlook_action "
                        "WHERE source_code = :sc AND as_of_date = :d"
                    ), {"sc": sc, "d": batch[0]["d"]})
                    for row in batch:
                        session.execute(insert_sql, row)
                    total_rows += len(batch)
            else:
                log.warning("unknown base_weight_method for %s: %s", sc, method)
            session.execute(text("RELEASE SAVEPOINT sp_source"))
        except Exception as e:
            session.execute(text("ROLLBACK TO SAVEPOINT sp_source"))
            log.warning("source %s failed (%s); continuing with others", sc, e)
    return total_rows


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def derive_outlook_action(session: Session, as_of_date: date,
                          parent_run_id: int | None) -> int:
    """Public wrapper. Returns row count inserted into drv_outlook_action."""
    rid = int(parent_run_id) if parent_run_id is not None else 0
    return _derive_outlook_action_impl(session, as_of_date, rid)


# ---------------------------------------------------------------------------
# compute_standing_verdicts — RETIRED 2026-06-13 (Increment 6 cleanup)
# No external callers. drv_source_standing is the canonical standing layer.
# ---------------------------------------------------------------------------
# (function removed)
