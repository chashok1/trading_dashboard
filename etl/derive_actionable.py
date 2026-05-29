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

log = logging.getLogger("etl.derive_actionable")

ACTION_RANK = {"REMOVE": 4, "REDUCE": 3, "INCREASE": 2, "ADD": 1, "HOLD": 0}


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
    """Return {symbol: total_dollar_value}."""
    rows = session.execute(text("""
        WITH fid AS (
            SELECT tos_symbol, SUM(qty) AS qty, SUM(current_value) AS val
            FROM hist_f
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            GROUP BY tos_symbol
        ),
        cs AS (
            SELECT tos_symbol, SUM(qty) AS qty, SUM(market_value) AS val
            FROM hist_cs
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            GROUP BY tos_symbol
        )
        SELECT COALESCE(fid.tos_symbol, cs.tos_symbol) AS tos_symbol,
               COALESCE(fid.val, 0) + COALESCE(cs.val, 0) AS dollar
        FROM fid FULL OUTER JOIN cs ON cs.tos_symbol = fid.tos_symbol
    """), {"d": as_of_date}).fetchall()
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

    my_stocks = {r[0] for r in session.execute(
        text("SELECT symbol FROM ref_my_stocks WHERE active = 'Y'")
    ).fetchall()}

    holdings = _load_holdings_with_dollars(session, as_of_date)

    # Per-symbol asset_class for sources that bucket by it (PS + ETF/ETFCHG).
    # Loaded once into a dict keyed by symbol — value is asset_class on/before as_of.
    asset_class_ps: dict[str, str] = {}
    for r in session.execute(text("""
        SELECT DISTINCT ON (ticker) ticker, asset_class
        FROM hist_ps
        WHERE asset_class IS NOT NULL AND asset_class <> ''
          AND snapshot_date <= :d
        ORDER BY ticker, snapshot_date DESC
    """), {"d": as_of_date}).fetchall():
        if r[1]: asset_class_ps[r[0]] = r[1]

    asset_class_etf: dict[str, str] = {}
    for r in session.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, asset_class
        FROM hist_etf
        WHERE asset_class IS NOT NULL AND asset_class <> ''
          AND snapshot_date <= :d
        ORDER BY symbol, snapshot_date DESC
    """), {"d": as_of_date}).fetchall():
        if r[1]: asset_class_etf[r[0]] = r[1]

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
            # Return ac if it maps to an allocation row; else warn + None.
            if not ac:
                return None
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
        by_sym.setdefault(r["symbol"], []).append(dict(r))

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
           position_category, asset_class, source_asset_class, target_min_dollar, target_max_dollar,
           units_dollar, maintain_min, suggested_target_dollar,
           held_today, current_position_dollar, in_my_list,
           rules_engine_fires, source_actions, suppressed_reason,
           triggered_group_ids,
           source_run_id)
        VALUES
          (:d, :sym, :desc, :sect,
           :ca, :ws, :wp,
           :cat, :ac, :sac, :tmin, :tmax,
           :unit, :mm, :stgt,
           :held, :curr, :iml,
           CAST(:fires AS JSONB), CAST(:srca AS JSONB), :supp,
           CAST(:groups AS JSONB),
           :rid)
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

        triggered_groups: list[dict] = []  # for the JSONB column
        group_candidates: list[dict] = []  # synthetic actions, ranked below
        for g in action_groups:
            grp_code = g["rule_group_code"]
            label    = g["action_label"]
            grp_prio = g["priority"]
            if label not in ACTION_RANK:
                continue
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
            # Treat each fired group as a synthetic per-source action so the
            # existing tie-break logic still applies. Use a 'RULES:' source
            # prefix and the group's priority (which is *lower=stronger* by
            # convention) so groups can outrank outlook sources when intended.
            group_candidates.append({
                "action":       action or label,
                "source_code":  f"RULES:{grp_code}",
                "_group_prio":  grp_prio if grp_prio is not None else 500,
            })

        # ─── Pick the winning action ───
        # Outlook-source candidates + synthetic rule-group candidates compete
        # in a single sort: (-ACTION_RANK, priority ASC). Group priority comes
        # from ref_trig_rule_group.priority; outlook priority from
        # ref_outlook_source.investment_priority. Both are "lower = wins".
        # SSS INCREASE/REDUCE are informational only — they may appear under
        # Other Sources but never become the consolidated (main) action.
        # SSS ADD/REMOVE stay eligible.
        # CALL always loses to other sources: it's demoted to Other Sources
        # if any other source has an action (CALL only wins if it's the only source).

        # Check if any non-CALL source exists in src_actions (before filtering informational)
        other_sources_present = any(a["source_code"] != "CALL" for a in src_actions)

        outlook_candidates = [
            a for a in src_actions
            if a["action"] in ACTION_RANK
            and not (a["source_code"] == "SSS"
                     and a["action"] in ("INCREASE", "REDUCE"))
        ]
        # If other sources exist, exclude CALL from being a winner
        if other_sources_present:
            outlook_candidates = [a for a in outlook_candidates if a["source_code"] != "CALL"]

        candidates = list(outlook_candidates) + group_candidates
        winning_source = None
        winning_priority = None
        consolidated = None
        if candidates:
            def _prio(a):
                if "_group_prio" in a:
                    return a["_group_prio"]
                return src_priority.get(a["source_code"], 999)
            candidates.sort(key=lambda a: (-ACTION_RANK[a["action"]], _prio(a)))
            winner = candidates[0]
            consolidated = winner["action"]
            winning_source = winner["source_code"]
            winning_priority = _prio(winner)

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
        # INCREASE/REDUCE) even if none won the consolidated slot — e.g. SSS
        # INCREASE/REDUCE, which are demoted to Other Sources only.
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
            "rid":   run_id,
        })
        rows_written += 1

    # Single executemany — previous version did one INSERT per symbol.
    if batch:
        session.execute(insert_sql, batch)

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
