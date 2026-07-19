"""derive_actionable — resolver: most-aggressive wins + sizing + suppression.

Reads drv_outlook_action (all sources for a date) + drv_stks (rules engine)
+ ref_my_stocks + ref_asset_allocation + holdings, and produces one row per
symbol in drv_actionable.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import position_ceiling

log = logging.getLogger("etl.derive_actionable")

ACTION_RANK  = {"REMOVE": 4, "REDUCE": 3, "INCREASE": 2, "ADD": 1, "HOLD": 0}
# RTA (long-book, same-day trigger) ranks highest — a real-time alert on a
# held position should always headline over a standing weekly/monthly list.
# RTAINFO (short-book, informational-only HOLD) and TOP5 (Hedgeye's daily
# Top-5 list, also informational-only HOLD) rank lowest so they never mask
# a real signal from another source.
SOURCE_ORDER = {"RTA": 1, "PS": 2, "ETF": 3, "RR": 4, "SSS": 5, "II": 6,
                "CALL": 7, "RTAINFO": 8, "TOP5": 9}

# Final-call strength scale (mirrors JS _FC_SCALE in actionable.js).
_FC_SCALE: dict[str, int] = {
    "SA": -3, "REMOVE": -3,
    "SS": -2, "STM": -2, "REDUCE": -2,
    "OVER_MAX": -1,
    "HOLD": 0, "NONE": 0,
    "BS": 2, "INCREASE": 2, "BMN": 2, "ADD": 2, "BM": 2,
}

# Canonical action-code → (label, code, side) — mirrors actions.js _MAP.
_ACTION_DISPLAY: dict[str, tuple[str, str, str]] = {
    "REMOVE":   ("SELL ALL",     "SA",   "sell"),
    "SA":       ("SELL ALL",     "SA",   "sell"),
    "REDUCE":   ("SELL SOME",    "SS",   "sell"),
    "SS":       ("SELL SOME",    "SS",   "sell"),
    "STM":      ("SELL TRIM",    "STM",  "sell"),
    "OVER_MAX": ("SELL OVERAGE", "SO",   "sell"),
    "SO":       ("SELL OVER",    "SO",   "sell"),
    "INCREASE": ("BUY SOME",     "BS",   "buy"),
    "BS":       ("BUY SOME",     "BS",   "buy"),
    "BM":       ("BUY MORE",     "BM",   "buy"),
    "ADD":      ("BUY TO MIN",   "BMN",  "buy"),
    "BMN":      ("BUY TO MIN",   "BMN",  "buy"),
    "HOLD":     ("HOLD",         "HOLD", "neutral"),
    "N":        ("NEUTRAL",      "N",    "neutral"),
    "NONE":     ("None",         "",     "neutral"),
}


def _action_display(code: Optional[str]) -> tuple[str, str, str]:
    """Return (label, code, side) for an action code (case-insensitive)."""
    if not code:
        return ("None", "", "neutral")
    return _ACTION_DISPLAY.get(str(code).upper(),
                               (str(code), "", "neutral"))


def _compute_final_call(
    consolidated_action: Optional[str],
    rr_action: Optional[str],
    held_today: bool,
    current_position_dollar: float,
    target_max_dollar: Optional[float],
    stop_breached: bool = False,
    bypass_technical: bool = False,
) -> dict:
    """Python port of JS finalCall() in web/actionable.js.

    bypass_technical (winning_source == 'RTA'): a Real-Time Alert is itself
    a live, same-day trigger — it doesn't need Technical (rr_action) to also
    confirm the entry point the way a standing weekly/monthly source does.
    Only applies to the buy side (src_is_buy); RTA sells still go through
    REMOVE's existing Technical-agnostic exit gate (step 1) or REDUCE's
    normal Technical-confirmation path, unchanged.

    Returns dict with keys: final_action, final_code, final_side,
    fc_strength, fc_confidence, fc_feasible.
    """
    ca  = (consolidated_action or "").upper()
    rra = (rr_action           or "").upper()

    # ── 0. No recommendation at all ──────────────────────────────────────
    if not ca or ca == "NONE":
        lbl, code, side = _action_display("HOLD")
        return {
            "final_action": lbl, "final_code": code, "final_side": side,
            "fc_strength": 0, "fc_confidence": "none", "fc_feasible": False,
        }

    # ── TASK_119: stop breach downgrade ──────────────────────────────────
    # A held position trading below its stop can never headline as an
    # effective ADD/INCREASE — downgrade to HOLD (caller sets
    # suppressed_reason='STOP BREACHED'; the original stays in
    # source_actions so the user still sees what the system would have
    # said). Takes priority over the at-Max / gate checks below. Breach ≠
    # auto-sell — REMOVE/REDUCE/HOLD rows are left untouched here, just
    # flagged via drv_actionable.stop_breached.
    if stop_breached and ca in ("ADD", "INCREASE"):
        lbl, code, side = _action_display("HOLD")
        return {
            "final_action": lbl, "final_code": code, "final_side": side,
            "fc_strength": 0, "fc_confidence": "gate", "fc_feasible": True,
        }

    # ── Helper classifiers ──────────────────────────────────────────────
    # Over-max: held position exceeds category ceiling (not REMOVE)
    at_max = False
    if ca != "REMOVE" and held_today and target_max_dollar and target_max_dollar > 0:
        if current_position_dollar > target_max_dollar:
            at_max = True

    is_held    = held_today

    src_is_exit   = ca in ("REMOVE", "SA")
    src_is_reduce = ca in ("REDUCE", "SS", "STM")
    src_is_buy    = ca in ("INCREASE", "BS", "BM", "ADD", "BMN")
    src_is_add    = ca in ("ADD", "BMN")

    tech_is_sell   = rra in ("SS", "STM", "SO", "REDUCE", "SA", "REMOVE")
    tech_is_buy    = rra in ("BS", "BM", "INCREASE")
    tech_is_buy_min = rra in ("BMN", "ADD")

    # ── 1. Strategic gate: SELL ALL / REMOVE or over-max ────────────────
    if src_is_exit or at_max:
        exit_strength = _FC_SCALE.get("OVER_MAX", -1) if at_max else _FC_SCALE.get("SA", -3)
        exit_code = "OVER_MAX" if at_max else "SA"
        lbl, code, side = _action_display(exit_code)
        if not is_held and not at_max:
            hold_lbl, hold_code, hold_side = _action_display("HOLD")
            return {
                "final_action": hold_lbl, "final_code": hold_code,
                "final_side": hold_side, "fc_strength": 0,
                "fc_confidence": "gate", "fc_feasible": False,
            }
        return {
            "final_action": lbl, "final_code": code, "final_side": side,
            "fc_strength": exit_strength, "fc_confidence": "gate", "fc_feasible": True,
        }

    # ── 2. Don't-initiate guard ──────────────────────────────────────────
    if not is_held and not src_is_buy:
        hold_lbl, hold_code, hold_side = _action_display("HOLD")
        return {
            "final_action": hold_lbl, "final_code": hold_code,
            "final_side": hold_side, "fc_strength": 0,
            "fc_confidence": "gate", "fc_feasible": True,
        }

    fc_label: str
    fc_code: str
    fc_side: str
    fc_strength: int
    confidence: str

    # ── RTA bypass: a live trigger resolves the buy on its own, no Technical
    # confirmation required. Only reached when src_is_buy (sells are exempt).
    if bypass_technical and src_is_buy:
        if not is_held and src_is_add:
            fc_lbl, fc_code, fc_side = _action_display("BMN")
            fc_strength = _FC_SCALE.get("BMN", 2)
        else:
            buy_code = "BM" if ca in ("BM", "INCREASE", "BS") else "BS"
            fc_lbl, fc_code, fc_side = _action_display(buy_code)
            fc_strength = _FC_SCALE.get(buy_code, 2)
        return {
            "final_action": fc_lbl, "final_code": fc_code, "final_side": fc_side,
            "fc_strength": fc_strength, "fc_confidence": "high", "fc_feasible": True,
        }

    if tech_is_sell:
        if not is_held:
            fc_lbl, fc_code, fc_side = _action_display("HOLD")
            fc_strength = 0
            confidence = "mixed"
        elif src_is_reduce:
            fc_lbl, fc_code, fc_side = _action_display("SS")
            fc_strength = _FC_SCALE.get("SS", -2)
            confidence = "high"
        else:
            fc_lbl, fc_code, fc_side = _action_display("SS")
            fc_strength = _FC_SCALE.get("SS", -2)
            confidence = "mixed"
    elif tech_is_buy or tech_is_buy_min:
        if src_is_reduce:
            fc_lbl, fc_code, fc_side = _action_display("HOLD")
            fc_strength = 0
            confidence = "mixed"
        elif at_max:
            fc_lbl, fc_code, fc_side = _action_display("HOLD")
            fc_strength = 0
            confidence = "gate"
        elif not is_held and src_is_add:
            fc_lbl, fc_code, fc_side = _action_display("BMN")
            fc_strength = _FC_SCALE.get("BMN", 2)
            confidence = "high"
        else:
            buy_code = "BM" if (rra in ("BM",) or ca in ("BM", "INCREASE", "BS")) else "BS"
            fc_lbl, fc_code, fc_side = _action_display(buy_code)
            fc_strength = _FC_SCALE.get(buy_code, 2)
            confidence = "high" if src_is_buy else "mixed"
    else:
        # Technical neutral
        if not is_held and src_is_add:
            fc_lbl, fc_code, fc_side = _action_display("BMN")
            fc_strength = _FC_SCALE.get("BMN", 2)
            confidence = "gate"
        elif src_is_reduce:
            fc_lbl, fc_code, fc_side = _action_display("HOLD")
            fc_strength = 0
            confidence = "mixed"
        else:
            fc_lbl, fc_code, fc_side = _action_display("HOLD")
            fc_strength = 0
            confidence = "gate"

    return {
        "final_action": fc_lbl, "final_code": fc_code, "final_side": fc_side,
        "fc_strength": fc_strength, "fc_confidence": confidence, "fc_feasible": True,
    }


def _open_drv_run(session, target, as_of_date, parent_run_id=None):
    row = session.execute(text("""
        INSERT INTO meta_derived_run (as_of_date, target_table, status, parent_run_id)
        VALUES (:d, :t, 'running', :prid) RETURNING run_id
    """), {"d": as_of_date, "t": target, "prid": parent_run_id}).first()
    return row[0] if row else 0


def _close_drv_run(session, run_id, *, rows_built=0, status="success", error_msg=None):
    if not run_id:
        return
    session.execute(text("""
        UPDATE meta_derived_run SET rows_built=:rb, status=:st, error_msg=:em
        WHERE run_id = :rid
    """), {"rb": rows_built, "st": status, "em": error_msg, "rid": run_id})


def _load_holdings_with_dollars(session, as_of_date):
    """Return {symbol: total_dollar_value}.

    Uses position_ceiling so weekend/holiday position exports (snapshot_date > D)
    are included on the live anchor but excluded on historical re-derives."""
    ceil = position_ceiling(session, as_of_date)
    rows = session.execute(text("""
        WITH fid AS (
            SELECT tos_symbol, SUM(qty) AS qty, SUM(current_value) AS val
            FROM hist_f
            WHERE snapshot_date = (
                SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :ceil
            )
            GROUP BY tos_symbol
        ),
        cs AS (
            SELECT tos_symbol, SUM(qty) AS qty, SUM(market_value) AS val
            FROM hist_cs
            WHERE snapshot_date = (
                SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :ceil
            )
            GROUP BY tos_symbol
        )
        SELECT COALESCE(fid.tos_symbol, cs.tos_symbol) AS tos_symbol,
               COALESCE(fid.val, 0) + COALESCE(cs.val, 0) AS dollar
        FROM fid FULL OUTER JOIN cs ON cs.tos_symbol = fid.tos_symbol
    """), {"ceil": ceil}).fetchall()
    return {r[0]: float(r[1] or 0) for r in rows}


def _derive_actionable_impl(session: Session, as_of_date: date, run_id: int) -> int:
    # Load reference data
    # asset_alloc is keyed by UPPER-CASED, trimmed category so the lookup is
    # case-insensitive (row category 'Call' matches ref_asset_allocation 'CAll').
    asset_alloc = {}
    for r in session.execute(text("""
        SELECT category, min_dollar, max_dollar, units, maintain_min_position
        FROM ref_asset_allocation
    """)).fetchall():
        asset_alloc[str(r[0] or "").strip().upper()] = {
            "min_dollar": float(r[1]) if r[1] is not None else 0.0,
            "max_dollar": float(r[2]) if r[2] is not None else 0.0,
            "units":      float(r[3]) if r[3] is not None else 0.0,
            "maintain":   bool(r[4]),
        }

    def _alloc_key(cat):
        return str(cat).strip().upper() if cat else ""
    alloc_has = lambda cat: _alloc_key(cat) in asset_alloc

    # Hedgeye's PS/ETF feeds use finer-grained asset_class labels than the
    # coarse ref_asset_allocation buckets actually configured (Equities,
    # Fixed Income, Foreign Currency) — map the near-synonyms onto those
    # buckets so they size against the existing envelope instead of falling
    # back to the generic PS/ETF one. Exact matches (e.g. literal "Equities")
    # bypass this map untouched since alloc_has() already finds them.
    _ASSET_CLASS_ALIAS = {
        "domestic equities":          "Equities",
        "global equities":            "Equities",
        "international equities":     "Equities",
        "emerging markets equities":  "Equities",
        "domestic fixed income":      "Fixed Income",
        "us fixed income":            "Fixed Income",
        "foreign currencies":         "Foreign Currency",
    }

    def _norm_asset_class(cat):
        if not cat:
            return cat
        return _ASSET_CLASS_ALIAS.get(str(cat).strip().lower(), cat)

    my_stocks = {r[0] for r in session.execute(
        text("SELECT tos_symbol FROM ref_my_stocks WHERE active = 'Y'")
    ).fetchall()}

    holdings = _load_holdings_with_dollars(session, as_of_date)

    # Task 8: load stop-level settings from ref_settings.
    def _ref_setting(name, default):
        try:
            row = session.execute(
                text("SELECT setting_value FROM ref_settings WHERE setting_name = :n"),
                {"n": name}
            ).first()
            return row[0] if row and row[0] is not None else default
        except Exception:
            return default

    stop_mode = _ref_setting("stop_mode", "trade_line_or_pct")
    try:
        stop_pct = float(_ref_setting("stop_pct", "0.08"))
    except (TypeError, ValueError):
        stop_pct = 0.08

    # Load EOD trade-line (a_trade_value) and live last_price per symbol.
    _trade_val: dict[str, float] = {}
    try:
        for r in session.execute(text("""
            SELECT tos_symbol, a_trade_value
            FROM drv_technicals WHERE as_of_date = :d
              AND a_trade_value IS NOT NULL
        """), {"d": as_of_date}).fetchall():
            if r[1] is not None:
                _trade_val[r[0]] = float(r[1])
    except Exception:
        pass

    _last_price: dict[str, float] = {}
    try:
        for r in session.execute(text("""
            SELECT tos_symbol, last_price
            FROM drv_quote WHERE as_of_date = :d
              AND last_price IS NOT NULL
        """), {"d": as_of_date}).fetchall():
            if r[1] is not None:
                _last_price[r[0]] = float(r[1])
    except Exception:
        pass

    def _compute_stop(sym, consolidated_action):
        """Compute stop_level for a symbol.
        For BUY-family (INCREASE/ADD) and held positions: apply stop formula.
        For SELL-family: same level annotated as 'exit below' in UI.
        Returns None if no price data available."""
        price = _last_price.get(sym)
        if price is None or price <= 0:
            return None
        pct_floor = price * (1.0 - stop_pct)
        if stop_mode == "trade_line_or_pct":
            trade = _trade_val.get(sym)
            if trade is not None and trade > 0:
                return max(trade, pct_floor)
            return pct_floor
        # Fallback: pct-only
        return pct_floor

    # BuySell action → numeric score map for trig_action computation.
    # Populated from ref_param_lookup where table_name='buysell', extra1=numeric score.
    # e.g. SA→-10, STM→-9, SS→-8, BM→10, BS→9, BMN→8. Gracefully empty if not loaded.
    buysell_scores: dict[str, float] = {}
    # BuySell code → seq for priority_rank (mirrors JS state.buysellSeq).
    buysell_seq: dict[str, float] = {}
    try:
        for r in session.execute(text(
            "SELECT code, extra1, seq FROM ref_param_lookup"
            " WHERE table_name = 'buysell'"
        )).fetchall():
            try:
                if r[1] is not None:
                    buysell_scores[str(r[0])] = float(r[1])
                if r[2] is not None:
                    buysell_seq[str(r[0]).upper()] = float(r[2])
            except (TypeError, ValueError):
                pass
    except Exception:
        pass

    # TASK_118 Part A: rule-scorecard direction/confidence per composite id, +
    # the self-updating "unproven sell rule" set (v_unproven_sell_rules:
    # SELL, fires>=500, edge_20d<0). Used to flag low_confidence rows whose
    # only sell-side evidence is a rule with a demonstrated negative edge —
    # BUY-side scoring/thresholds are untouched, this is read-only annotation.
    rule_scorecard: dict[str, dict] = {}
    try:
        for r in session.execute(text(
            "SELECT rule_id, direction, confidence FROM v_rule_scorecard"
        )).mappings().all():
            rule_scorecard[r["rule_id"]] = {
                "direction": r["direction"], "confidence": r["confidence"],
            }
    except Exception:
        log.warning("v_rule_scorecard load failed (low_confidence stays False)", exc_info=True)

    unproven_sell_ids: set[str] = set()
    try:
        for r in session.execute(text(
            "SELECT rule_id FROM v_unproven_sell_rules"
        )).fetchall():
            unproven_sell_ids.add(r[0])
    except Exception:
        log.warning("v_unproven_sell_rules load failed (low_confidence stays False)", exc_info=True)

    # Load td_tn_bb_action_desc (the rr_action for finalCall) from drv_tn_td_bb_rr.
    rr_action_map: dict[str, str] = {}
    try:
        for r in session.execute(text("""
            SELECT tos_symbol, td_tn_bb_action_desc
            FROM drv_tn_td_bb_rr WHERE as_of_date = :d
              AND td_tn_bb_action_desc IS NOT NULL
        """), {"d": as_of_date}).fetchall():
            if r[0] and r[1]:
                rr_action_map[r[0]] = r[1]
    except Exception:
        pass

    # Per-symbol asset_class for sources that bucket by it (PS + ETF/ETFCHG).
    # Keyed by tos_symbol (normalized) — fixes ticker/symbol vs tos_symbol bug.
    asset_class_ps: dict[str, str] = {}
    for r in session.execute(text("""
        SELECT DISTINCT ON (COALESCE(tos_symbol, ticker))
               COALESCE(tos_symbol, ticker) AS sym, asset_class
        FROM hist_ps
        WHERE asset_class IS NOT NULL AND asset_class <> ''
          AND snapshot_date <= :d
        ORDER BY COALESCE(tos_symbol, ticker), snapshot_date DESC
    """), {"d": as_of_date}).fetchall():
        if r[0] and r[1]: asset_class_ps[r[0]] = r[1]

    asset_class_etf: dict[str, str] = {}
    for r in session.execute(text("""
        SELECT DISTINCT ON (COALESCE(tos_symbol, symbol))
               COALESCE(tos_symbol, symbol) AS sym, asset_class
        FROM hist_etf
        WHERE asset_class IS NOT NULL AND asset_class <> ''
          AND snapshot_date <= :d
        ORDER BY COALESCE(tos_symbol, symbol), snapshot_date DESC
    """), {"d": as_of_date}).fetchall():
        if r[0] and r[1]: asset_class_etf[r[0]] = r[1]

    def _category_for(sym, win_src, fallback):
        """Resolve ref_asset_allocation lookup key.
        PS     → hist_ps.asset_class (must map to a row, else fallback)
        ETF    → hist_etf.asset_class (must map to a row, else fallback)
        ETFCHG → 1) 'ETFCHG' row if present
                 2) hist_etf.asset_class for the symbol (must map to a row)
                 3) 'ETF' row if present
                 4) fallback
        else  → fallback (ref_outlook_source.position_category)

        A symbol's asset_class is used only when it actually maps to a
        ref_asset_allocation row. A present-but-unmapped class falls through
        to the fallback (and logs a warning) instead of silently sizing to $0."""
        def _use_ac(ac):
            # Return ac (post-alias) if it maps to an allocation row; else warn + None.
            if not ac:
                return None
            ac = _norm_asset_class(ac)
            if alloc_has(ac):
                return ac
            log.warning("derive_actionable: %s asset_class %r for %s has no "
                        "ref_asset_allocation row; using fallback %r",
                        win_src, ac, sym, fallback)
            try:
                from etl.warnings import add_warning
                add_warning(session, "actionable",
                            f"{sym}: {win_src} asset_class '{ac}' has no "
                            f"ref_asset_allocation row — sized via fallback "
                            f"'{fallback}'",
                            as_of_date=as_of_date, symbol=sym,
                            code="UNMAPPED_ASSET_CLASS")
            except Exception:
                log.exception("add_warning failed (continuing)")
            return None
        if win_src == "PS":
            hit = _use_ac(asset_class_ps.get(sym))
            if hit: return hit
        elif win_src == "ETF":
            hit = _use_ac(asset_class_etf.get(sym))
            if hit: return hit
        elif win_src == "ETFCHG":
            if alloc_has("ETFCHG"): return "ETFCHG"
            hit = _use_ac(asset_class_etf.get(sym))
            if hit: return hit
            if alloc_has("ETF"): return "ETF"
        return fallback

    # Source priority lookup for tie-breaking and fallback category
    src_priority = {}
    src_category = {}
    for r in session.execute(text("""
        SELECT source_code, investment_priority, position_category
        FROM ref_outlook_source
    """)).fetchall():
        src_priority[r[0]] = int(r[1])
        src_category[r[0]] = r[2]

    # Load all per-source actions for this date.
    # Periodic sources (ETF/II/SSS/PS) store actions with their period's snapshot date,
    # not the current derive date. Map to their effective snapshot dates like v_outlook_changes does.
    source_dates_sql = text("""
        WITH source_snapshot_dates AS (
            SELECT DISTINCT source_code,
                   CASE
                       WHEN source_code = 'ETF' THEN
                           (SELECT MAX(as_of_date) FROM drv_outlook_action doa1
                            WHERE doa1.source_code = 'ETF'
                              AND as_of_date <= :d)
                       WHEN source_code = 'II' THEN
                           (SELECT MAX(as_of_date) FROM drv_outlook_action doa2
                            WHERE doa2.source_code = 'II'
                              AND as_of_date <= :d)
                       WHEN source_code = 'SSS' THEN
                           (SELECT MAX(as_of_date) FROM drv_outlook_action doa3
                            WHERE doa3.source_code = 'SSS'
                              AND as_of_date <= :d)
                       WHEN source_code = 'PS' THEN
                           (SELECT MAX(as_of_date) FROM drv_outlook_action doa4
                            WHERE doa4.source_code = 'PS'
                              AND as_of_date <= :d)
                       WHEN source_code = 'RR' THEN
                           (SELECT MAX(as_of_date) FROM drv_outlook_action doa5
                            WHERE doa5.source_code = 'RR'
                              AND as_of_date <= :d)
                       ELSE :d
                   END AS effective_date
            FROM (SELECT DISTINCT source_code FROM drv_outlook_action) sources
        )
        SELECT doa.tos_symbol, doa.source_code, doa.base_weight, doa.prev_weight, doa.prev_date,
               doa.weight_delta, doa.held_today, doa.action, doa.action_reason, doa.category,
               doa.analyst_rank, doa.as_of_date, doa.source_snapshot_date
        FROM drv_outlook_action doa
        JOIN source_snapshot_dates ssd ON doa.source_code = ssd.source_code
        WHERE doa.as_of_date = ssd.effective_date
        ORDER BY doa.tos_symbol, doa.source_code
    """)
    all_actions = session.execute(source_dates_sql, {"d": as_of_date}).mappings().all()

    # Group by symbol
    by_sym: dict[str, list[dict]] = {}
    for r in all_actions:
        by_sym.setdefault(r["tos_symbol"], []).append(dict(r))

    # Augment with my_stocks symbols that have no actions today
    for sym in my_stocks:
        by_sym.setdefault(sym, [])

    # Drv_stks (rules engine fires) keyed by tos_symbol
    stks = {}
    for r in session.execute(text("""
        SELECT tos_symbol, description, sector, asset_class, triggered_composite_ids
        FROM drv_stks
        WHERE as_of_date = :d
    """), {"d": as_of_date}).mappings().all():
        stks[r["tos_symbol"]] = dict(r)

    # Load action-type rule groups so we can fold rule-engine signals into the
    # actionable mix alongside the outlook-source signals.  A group fires for
    # a symbol when its member composites (per the AND/OR logic) all fire on
    # that symbol's drv_stks.triggered_composite_ids list.  Groups with
    # group_type='action' contribute a candidate action; group_type='logical'
    # groups are evaluated only as nested members of action groups.
    action_groups = session.execute(text("""
        SELECT rule_group_code, action_label, priority, category
        FROM ref_trig_rule_group
        WHERE deprecated_at IS NULL
          AND group_type = 'action'
          AND action_label IS NOT NULL
    """)).mappings().all()
    from etl.rule_groups import eval_rule_group  # lazy import — avoids cycle

    # Wipe today
    session.execute(text("DELETE FROM drv_actionable WHERE as_of_date = :d"), {"d": as_of_date})
    from etl.warnings import clear_screen_warnings
    clear_screen_warnings(session, "actionable", as_of_date)

    insert_sql = text("""
        INSERT INTO drv_actionable
          (as_of_date, tos_symbol, description, sector,
           consolidated_action, winning_source, winning_priority,
           position_category, asset_class, source_asset_class,
           target_min_dollar, target_max_dollar,
           units_dollar, maintain_min, suggested_target_dollar,
           held_today, current_position_dollar, in_my_list,
           rules_engine_fires, source_actions, suppressed_reason,
           triggered_group_ids, trig_action,
           stop_level, source_run_id,
           final_action, final_code, final_side,
           fc_strength, fc_confidence, fc_feasible, priority_rank,
           stop_breached, low_confidence)
        VALUES
          (:d, :sym, :desc, :sect,
           :ca, :ws, :wp,
           :cat, :ac, :sac, :tmin, :tmax,
           :unit, :mm, :stgt,
           :held, :curr, :iml,
           CAST(:fires AS JSONB), CAST(:srca AS JSONB), :supp,
           CAST(:groups AS JSONB), :trig,
           :stop, :rid,
           :f_action, :f_code, :f_side,
           :f_strength, :f_confidence, :f_feasible, :f_priority,
           :stop_breached, :low_confidence)
    """)

    rows_written = 0
    batch: list[dict] = []
    for sym, src_actions in by_sym.items():
        # ─── Evaluate rule groups against this symbol's fired composites ───
        # Build composite_results = {composite_code: True} from drv_stks.
        fired_composites = set()
        stk_fires = (stks.get(sym, {}) or {}).get("triggered_composite_ids") or []
        for t in stk_fires:
            if isinstance(t, dict):
                cid = t.get("rule_id")
                if cid:
                    fired_composites.add(cid)
        composite_results = {c: True for c in fired_composites}

        # ─── TASK_118 Part A: low_confidence annotation ────────────────────
        # True when this symbol's ONLY sell-side evidence is a fired composite
        # in v_unproven_sell_rules — no source (PS/ETF/RR/SSS/II/CALL) emitted
        # a REMOVE/REDUCE, and no fired SELL composite is proven. Diagnostic
        # flag only; does not touch consolidated_action or any BUY-side logic.
        fired_sell_composites = [
            c for c in fired_composites
            if rule_scorecard.get(c, {}).get("direction") == "SELL"
        ]
        has_proven_sell = any(
            rule_scorecard.get(c, {}).get("confidence") == "proven"
            for c in fired_sell_composites
        )
        has_unproven_sell = any(c in unproven_sell_ids for c in fired_sell_composites)
        source_driven_sell = any(
            a["action"] in ("REMOVE", "REDUCE") for a in src_actions
        )
        low_confidence = has_unproven_sell and not has_proven_sell and not source_driven_sell

        triggered_groups: list[dict] = []  # for the JSONB column + trig_action
        group_candidates: list[dict] = []  # synthetic actions for consolidated_action
        for g in action_groups:
            grp_code = g["rule_group_code"]
            label    = g["action_label"]
            grp_prio = g["priority"]
            try:
                fired, action, _ = eval_rule_group(session, grp_code,
                                                   composite_results, {})
            except Exception as e:
                log.warning("rule group %s eval failed for %s: %s", grp_code, sym, e)
                continue
            if not fired:
                continue
            triggered_groups.append({
                "rule_group_code": grp_code,
                "action": action or label,
                "priority": grp_prio,
                "category": g.get("category"),
            })
            # Only groups with consolidated-action vocab feed the winner sort.
            # BuySell-vocab groups (SA, SS, BM, …) contribute to trig_action only.
            if label not in ACTION_RANK:
                continue
            # Treat each fired group as a synthetic per-source action so the
            # existing tie-break logic still applies. Use a 'RULES:' source
            # prefix and the group's priority (which is *lower=stronger* by
            # convention) so groups can outrank outlook sources when intended.
            group_candidates.append({
                "action":       action or label,
                "source_code":  f"RULES:{grp_code}",
                "_group_prio":  grp_prio if grp_prio is not None else 500,
            })

        # ─── Compute trig_action from fired rule groups (BuySell vocabulary) ───
        # For each fired group, look up its action_label in the BuySell score
        # map (SA=-10, STM=-9, SS=-8, BMN=8, BS=9, BM=10 etc.).
        # Bearish wins: if any negative scores, take the group with the min score.
        # Otherwise take the group with the max (most bullish) score.
        trig_action = None
        if triggered_groups and buysell_scores:
            scored = [
                (g["action"], buysell_scores[g["action"]])
                for g in triggered_groups
                if g.get("action") and g["action"] in buysell_scores
            ]
            if scored:
                neg = [(a, s) for a, s in scored if s < 0]
                pos = [(a, s) for a, s in scored if s > 0]
                if neg:
                    trig_action = min(neg, key=lambda x: x[1])[0]
                elif pos:
                    trig_action = max(pos, key=lambda x: x[1])[0]

        # ─── Pick the winning action ───
        # Held symbol  → fixed source order PS>ETF>RR>SSS>II>CALL.
        # Not-held     → latest update wins; tie on date → source order.
        # Rule-group candidates keep their group priority and rank after the six sources.
        _held_now = holdings.get(sym, 0.0) > 0

        for gc in group_candidates:
            gc["_update_date"] = as_of_date    # rule groups fire on the current derive date

        def _order(a):
            if "_group_prio" in a:
                return a["_group_prio"]
            return SOURCE_ORDER.get(a["source_code"], 99)

        def _upd_ord(a):                       # higher = more recent
            d = a.get("_update_date") or a.get("source_snapshot_date") or a.get("as_of_date")
            return d.toordinal() if d else 0

        candidates = [a for a in src_actions if a["action"] in ACTION_RANK] + group_candidates
        winning_source = None
        winning_priority = None
        consolidated = None
        if candidates:
            if _held_now:
                candidates.sort(key=_order)                            # source order
            else:
                candidates.sort(key=lambda a: (-_upd_ord(a), _order(a)))  # latest update, tie→order
            winner = candidates[0]
            consolidated = winner["action"]
            winning_source = winner["source_code"]
            winning_priority = _order(winner)

        # ─── Decide category for sizing ───
        # For PS / ETF / ETFCHG winners, the lookup key is the per-symbol
        # asset_class (Defensive / Offensive / etc.), NOT the literal 'PS' or 'etf'.
        category = None
        if winning_source:
            category = _category_for(sym, winning_source, src_category.get(winning_source))
        else:
            # No action fired — pick the lowest-priority source that covered this symbol
            cover = [a for a in src_actions if a["category"]]
            if cover:
                cover.sort(key=lambda a: src_priority.get(a["source_code"], 999))
                fallback_src = cover[0]["source_code"]
                category = _category_for(sym, fallback_src, cover[0]["category"])
        params = asset_alloc.get(_alloc_key(category), {}) if category else {}
        target_min  = params.get("min_dollar")
        target_max  = params.get("max_dollar")
        units       = params.get("units")
        maintain_min = params.get("maintain", False)

        # ─── Current state ───
        held_dollar = holdings.get(sym, 0.0)
        held_today  = held_dollar > 0
        in_my_list  = sym in my_stocks

        # ─── Compute suggested target dollar (+ position-aware suppression) ───
        # Suppression checks: REMOVE on non-held, ADD on already-established,
        # INCREASE on at-ceiling, REDUCE on at-floor. Each marks the row with a
        # suppressed_reason; the action itself is preserved so the user can see
        # what the system would have recommended.
        suppressed = None
        suggested = held_dollar
        if consolidated == "REMOVE":
            if not held_today:
                suppressed = "NOT HELD — nothing to remove"
                suggested = 0
            else:
                suggested = 0
        elif consolidated == "ADD":
            # ADD is for opening a new (or near-zero) position. If already
            # established at/above the category floor, treat as INCREASE-or-skip.
            if held_today and target_min is not None and held_dollar >= target_min:
                suppressed = f"ALREADY ESTABLISHED — held ${held_dollar:,.0f} ≥ floor ${target_min:,.0f}"
                suggested = held_dollar
            else:
                suggested = target_min if target_min is not None else None
        elif consolidated == "INCREASE":
            if not held_today:
                # INCREASE with no position -> establish the base position
                # (MIN) plus one unit block - catch-up. Applies to all sources.
                suggested = (target_min or 0) + (units or 0)
                if target_max is not None and suggested > target_max:
                    suggested = target_max
            elif target_max is not None and held_dollar >= target_max:
                suppressed = f"AT CEILING — held ${held_dollar:,.0f} ≥ max ${target_max:,.0f}"
                suggested = held_dollar
            elif units is not None and target_max is not None:
                suggested = min(held_dollar + units, target_max)
            elif units is not None:
                suggested = held_dollar + units
        elif consolidated == "REDUCE":
            if maintain_min and target_min is not None:
                if held_dollar <= target_min:
                    suppressed = f"AT FLOOR — held ${held_dollar:,.0f} ≤ min ${target_min:,.0f}"
                    suggested = held_dollar
                else:
                    suggested = max(target_min, held_dollar - (units or 0))
            else:
                suggested = max(0, held_dollar - (units or held_dollar))
        # HOLD / None / NULL: suggested stays at held_dollar

        # ─── Suppress edge cases ───
        # Keep the row when any source emitted a real action (ADD/REMOVE/
        # INCREASE/REDUCE) even if none won the consolidated slot (e.g. a
        # not-held PS REMOVE that was excluded from the winner contest).
        has_other_signal = any(
            a["action"] in ("REMOVE", "REDUCE", "INCREASE", "ADD")
            for a in src_actions
        )
        if (not consolidated and not in_my_list and not held_today
                and not has_other_signal):
            # Skip entirely — nothing interesting
            continue

        # ─── Build display payloads ───
        rules_fires = (stks.get(sym, {}) or {}).get("triggered_composite_ids") or []
        source_actions_payload = []
        for a in sorted(src_actions, key=lambda x: src_priority.get(x["source_code"], 999)):
            source_actions_payload.append({
                "source":      a["source_code"],
                "action":      a["action"],
                "weight":      float(a["base_weight"]) if a["base_weight"] is not None else None,
                "prev_weight": float(a["prev_weight"]) if a["prev_weight"] is not None else None,
                "prev_date":   a["prev_date"].isoformat() if a["prev_date"] else None,
                "weight_delta": float(a["weight_delta"]) if a["weight_delta"] is not None else None,
                "reason":      a["action_reason"],
                "held_today":  bool(a.get("held_today") or False),
                "analyst_rank": a.get("analyst_rank"),
                "snapshot_date": (a["source_snapshot_date"] or a["as_of_date"]).isoformat() if (a["source_snapshot_date"] or a["as_of_date"]) else None,
            })

        # Capture the actual source asset_class (from hist_ps, hist_etf, or drv_ma)
        source_ac = None
        if winning_source == "PS":
            source_ac = asset_class_ps.get(sym)
        elif winning_source in ("ETF", "ETFCHG"):
            source_ac = asset_class_etf.get(sym)
        # For other sources (RR, SSS, II, etc.), asset_class comes from drv_ma lookup

        # Task 8: compute stop_level for BUY-family, held, and SELL-family rows.
        _show_stop = (
            held_today
            or consolidated in ("INCREASE", "ADD", "REMOVE", "REDUCE")
        )
        stop_level_val = _compute_stop(sym, consolidated) if _show_stop else None

        # ─── TASK_119: stop-consistency flag ───────────────────────────────
        # A held position whose latest price is below stop_level is always
        # flagged. ADD/INCREASE also get suppressed_reason overridden so the
        # user sees why the effective action was downgraded to HOLD.
        stop_breached = False
        if held_today and stop_level_val is not None:
            _price_now = _last_price.get(sym)
            if _price_now is not None and float(_price_now) < float(stop_level_val):
                stop_breached = True
                if consolidated in ("ADD", "INCREASE"):
                    suppressed = "STOP BREACHED"

        # ─── TASK_53: Compute final_call + priority_rank at derive time ───
        rr_act = rr_action_map.get(sym)
        fc = _compute_final_call(
            consolidated_action=consolidated,
            rr_action=rr_act,
            held_today=held_today,
            current_position_dollar=held_dollar,
            target_max_dollar=target_max,
            stop_breached=stop_breached,
            bypass_technical=(winning_source == "RTA"),
        )
        # priority_rank mirrors JS _computePriority: seq * 1e6 + |amt|.
        # amt = suggested - held for buys; held for sells; 0 otherwise.
        if suggested is not None and held_dollar is not None:
            _amt = abs(float(suggested) - float(held_dollar))
        else:
            _amt = 0.0
        fc_code_upper = (fc["final_code"] or "").upper()
        if fc_code_upper == "SO":  # OVER_MAX synthetic maps to SO for seq lookup
            _seq_key = "SO"
        else:
            _seq_key = fc_code_upper
        _seq = buysell_seq.get(_seq_key, -1.0) if fc["fc_feasible"] else -1.0
        priority_rank = _seq * 1e6 + _amt

        stk = stks.get(sym, {})
        batch.append({
            "d":     as_of_date,
            "sym":   sym,
            "desc":  stk.get("description"),
            "sect":  stk.get("sector"),
            "ca":    consolidated,
            "ws":    winning_source,
            "wp":    winning_priority,
            "cat":   category,
            "ac":    category,
            "sac":   source_ac,
            "tmin":  target_min,
            "tmax":  target_max,
            "unit":  units,
            "mm":    maintain_min,
            "stgt":  suggested,
            "held":  held_today,
            "curr":  held_dollar,
            "iml":   in_my_list,
            "fires": json.dumps(rules_fires) if rules_fires else None,
            "srca":  json.dumps(source_actions_payload),
            "supp":  suppressed,
            "groups": json.dumps(triggered_groups) if triggered_groups else None,
            "trig":  trig_action,
            "stop":  stop_level_val,
            "rid":   run_id,
            "f_action":     fc["final_action"],
            "f_code":       fc["final_code"],
            "f_side":       fc["final_side"],
            "f_strength":   fc["fc_strength"],
            "f_confidence": fc["fc_confidence"],
            "f_feasible":   fc["fc_feasible"],
            "f_priority":   priority_rank,
            "stop_breached":   stop_breached,
            "low_confidence":  low_confidence,
        })
        rows_written += 1

    # Single executemany — previous version did one INSERT per symbol.
    if batch:
        session.execute(insert_sql, batch)

    # TASK_57: populate drv_category_totals once per derive (idempotent).
    # Read back from drv_actionable now that it's been flushed so we can
    # aggregate without holding the full Python batch in memory again.
    try:
        session.execute(
            text("DELETE FROM drv_category_totals WHERE as_of_date = :d"),
            {"d": as_of_date}
        )
        cat_rows = session.execute(text("""
            SELECT a.position_category,
                   SUM(COALESCE(a.current_position_dollar, 0)) AS total_dollar,
                   r.min_dollar, r.max_dollar
            FROM drv_actionable a
            LEFT JOIN ref_asset_allocation r
                   ON UPPER(r.category) = UPPER(a.position_category)
            WHERE a.as_of_date = :d
              AND a.position_category IS NOT NULL
            GROUP BY a.position_category, r.min_dollar, r.max_dollar
        """), {"d": as_of_date}).mappings().all()
        if cat_rows:
            totals_batch = []
            for cr in cat_rows:
                held = float(cr["total_dollar"] or 0)
                mn   = float(cr["min_dollar"]) if cr["min_dollar"] is not None else None
                mx   = float(cr["max_dollar"]) if cr["max_dollar"] is not None else None
                if mn is not None and held < mn:
                    band = "BELOW_MIN"
                elif mx is not None and held > mx:
                    band = "ABOVE_MAX"
                else:
                    band = "WITHIN"
                totals_batch.append({
                    "as_of_date":        as_of_date,
                    "position_category": cr["position_category"],
                    "total_dollar":      held,
                    "drift_band":        band,
                })
            session.execute(
                text("""
                    INSERT INTO drv_category_totals
                        (as_of_date, position_category, total_dollar, drift_band)
                    VALUES (:as_of_date, :position_category, :total_dollar, :drift_band)
                """),
                totals_batch
            )
    except Exception as _ct_err:
        log.warning("drv_category_totals failed (non-fatal): %s", _ct_err)

    return rows_written


def derive_actionable(session: Session, as_of_date: date,
                      parent_run_id: Optional[int] = None) -> int:
    rid = _open_drv_run(session, "drv_actionable", as_of_date, parent_run_id)
    try:
        n = _derive_actionable_impl(session, as_of_date, rid)
        _close_drv_run(session, rid, rows_built=n)
        log.info("drv_actionable @ %s: %d rows", as_of_date, n)
        return n
    except Exception as e:
        _close_drv_run(session, rid, rows_built=0, status="error", error_msg=str(e)[:500])
        raise
