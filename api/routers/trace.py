"""Symbol trace endpoint + user-action logger."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from etl.db import session_scope

from api.models import UserActionRequest

router = APIRouter()


# -----------------------------------------------------------------------------
# User actions  (Cockpit "Took action" / "Skip" buttons)
# -----------------------------------------------------------------------------

@router.post("/api/actions", response_model=dict)
def log_user_action(request: UserActionRequest):
    """Log a user action and snapshot the current triggered rules.

    Cockpit submits the meta-code `'ACTED'` (user took some action) or `'SKIP'`
    (user dismissed). For compute_outcomes to score `ACTED`, we resolve it here
    to the system's recommended action_code from drv_actionable.consolidated_action
    for that (symbol, as_of_date). The original confirmation state is recorded
    in user_action ('DONE' / 'SKIPPED') for audit.
    """
    with session_scope() as s:
        stks_row = s.execute(
            text("""
                SELECT triggered_atomic_ids, triggered_composite_ids
                FROM drv_stks
                WHERE as_of_date = :d AND tos_symbol = :sym
                LIMIT 1
            """),
            {"d": request.as_of_date, "sym": request.symbol}
        ).mappings().first()

        triggered = []
        if stks_row and stks_row["triggered_atomic_ids"]:
            triggered.extend(stks_row["triggered_atomic_ids"])
        if stks_row and stks_row["triggered_composite_ids"]:
            triggered.extend(stks_row["triggered_composite_ids"])

        raw_code = (request.action_code or "").upper().strip()

        # Resolve meta-codes to scorable codes
        if raw_code == "ACTED":
            confirmation = "DONE"
            consolidated = s.execute(
                text("""
                    SELECT consolidated_action FROM drv_actionable
                    WHERE as_of_date = :d AND tos_symbol = :sym
                    LIMIT 1
                """),
                {"d": request.as_of_date, "sym": request.symbol}
            ).scalar()
            # Fall back to 'ACTED' if no recommendation exists; compute_outcomes
            # has an ACTED-specific scoring branch.
            scoring_code = consolidated or "ACTED"
        elif raw_code == "SKIP":
            confirmation = "SKIPPED"
            scoring_code = "SKIP"
        else:
            # Direct codes (SA/STM/SS/BM/HOLD or REMOVE/REDUCE/INCREASE/ADD)
            confirmation = "DONE"
            scoring_code = raw_code

        result = s.execute(
            text("""
                INSERT INTO user_action_log
                  (as_of_date, symbol, action_code, user_action,
                   triggered_rules, notes)
                VALUES (:d, :sym, :code, :ua,
                   CAST(:rules AS JSONB), :notes)
                RETURNING id, created_at
            """),
            {
                "d": request.as_of_date,
                "sym": request.symbol,
                "code": scoring_code,
                "ua": confirmation,
                "rules": json.dumps(triggered),
                "notes": request.notes,
            }
        ).mappings().first()

        s.commit()
        return {"ok": True, "id": result["id"],
                "created_at": result["created_at"].isoformat()}


# -----------------------------------------------------------------------------
# Symbol Trace — per-rule evaluation for one (date, symbol)
# -----------------------------------------------------------------------------

@router.get("/api/trace/{sym}", response_model=dict)
def get_symbol_trace(sym: str, as_of: Optional[str] = Query(None, alias="date")):
    """Return the full per-rule trace for one ticker (used by /trace page).

    Response shape (consumed by web/trace.js):
      {
        "symbol": str, "as_of_date": "YYYY-MM-DD",
        "summary": {description, sector, asset_class, last_price,
                    composite_outlook, composite_label,
                    n_composite_fired, n_composite_total,
                    n_atomic_fired,  n_atomic_total},
        "composites": [ { code, fired, score, label, n_atomics, n_fired }, ... ],
        "atomics":    [ { id, rule_name, ma_column, value,
                          brkeout_from, brkeout_to, scoring_mode, weight,
                          fired, category, rolls_into[] }, ... ]
      }
    """
    from etl.derive import eval_atomic_rule, _eval_precondition

    sym_u = sym.upper().strip()
    with session_scope() as s:
        # ---- 1. Resolve snapshot date ---------------------------------------
        if as_of:
            try:
                snap = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        else:
            row = s.execute(text("SELECT MAX(as_of_date) AS d FROM drv_stks")).mappings().first()
            snap = row["d"] if row and row["d"] else date.today()

        # ---- 2. Summary row (drv_ma + drv_stks) -----------------------------
        summary_row = s.execute(text("""
            SELECT m.symbol, m.description, m.sector, m.asset_class, m.last_price,
                   st.composite_outlook, st.composite_label,
                   st.triggered_atomic_ids, st.triggered_composite_ids
            FROM drv_ma m
            LEFT JOIN drv_stks st
              ON st.as_of_date = m.as_of_date AND st.tos_symbol = m.tos_symbol
            WHERE m.as_of_date = :d AND m.symbol = :sym
        """), {"d": snap, "sym": sym_u}).mappings().first()
        if not summary_row:
            raise HTTPException(status_code=404,
                                detail=f"No drv_ma row for symbol={sym_u!r} on {snap}")

        # Pre-computed scores from drv_stks (preferred — matches batch derive)
        precomputed_atomic = {}
        for t in (summary_row["triggered_atomic_ids"] or []):
            rid = t.get("rule_id")
            if rid is not None:
                precomputed_atomic[rid] = t  # {rule_id, weight, value}
        precomputed_composite = {}
        for t in (summary_row["triggered_composite_ids"] or []):
            code = t.get("rule_id")
            if code is not None:
                precomputed_composite[code] = t  # {rule_id, score}

        # ---- 3. Value-source rows (ma + ai) ---------------------------------
        try:
            ma_row = dict(s.execute(text(
                "SELECT * FROM drv_ma WHERE as_of_date=:d AND symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym_u}).mappings().first() or {})
        except Exception:
            ma_row = {}
        try:
            ai_row = dict(s.execute(text(
                "SELECT * FROM drv_cat_atomic_input WHERE as_of_date=:d AND symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym_u}).mappings().first() or {})
        except Exception:
            ai_row = {}

        # ---- 4. Atomic rule definitions -------------------------------------
        atomic_rules = s.execute(text("""
            SELECT atomic_rule_id, rule_name, ma_column_name,
                   brkeout_from, brkeout_to,
                   wt_below, wt_between, wt_above,
                   scoring_mode, score_params, category, intent_text
            FROM ref_trig_atomic_rule
            WHERE deprecated_at IS NULL
            ORDER BY atomic_rule_id
        """)).mappings().all()

        # ---- 5. Composite mappings + composite metadata ---------------------
        # Try the extended-schema query first (member_kind / data_*); fall back
        # to the legacy atomic-only shape if the migration hasn't run.
        try:
            mappings = s.execute(text("""
                SELECT composite_rule_code, COALESCE(member_kind, 'atomic') AS member_kind,
                       atomic_rule_id, weight_override,
                       data_column, data_brkeout_from, data_brkeout_to,
                       data_wt_below, data_wt_between, data_wt_above,
                       data_scoring_mode, data_score_params,
                       nested_composite_code, member_multiplier,
                       precondition_expr
                FROM ref_trig_composite_mapping
                WHERE deprecated_at IS NULL
                ORDER BY composite_rule_code, atomic_rule_id
            """)).mappings().all()
        except Exception:
            mappings = s.execute(text("""
                SELECT composite_rule_code, atomic_rule_id, weight_override,
                       precondition_expr
                FROM ref_trig_composite_mapping
                WHERE deprecated_at IS NULL
                ORDER BY composite_rule_code, atomic_rule_id
            """)).mappings().all()

        # Composite display labels live in ref_rule_desc
        try:
            desc_rows = s.execute(text("""
                SELECT rule_code, description FROM ref_rule_desc
            """)).mappings().all()
            comp_label = {r["rule_code"]: r["description"] for r in desc_rows}
        except Exception:
            comp_label = {}

        # ---- 6. Index composites + build rolls_into -------------------------
        composite_index: dict = {}
        rolls_into: dict = {}
        for m in mappings:
            code = m["composite_rule_code"]
            if code not in composite_index:
                composite_index[code] = {
                    "precondition": m.get("precondition_expr") if "precondition_expr" in m.keys() else None,
                    "members": [],
                }
            kind = (m.get("member_kind") if "member_kind" in m.keys() else None) or "atomic"
            atom_id = m.get("atomic_rule_id")
            if kind == "atomic":
                composite_index[code]["members"].append({
                    "kind": "atomic",
                    "atom_id": atom_id,
                    "override": m.get("weight_override"),
                })
                if atom_id is not None:
                    rolls_into.setdefault(atom_id, []).append(code)
            elif kind == "data":
                composite_index[code]["members"].append({
                    "kind": "data",
                    "column":       m.get("data_column"),
                    "brkeout_from": m.get("data_brkeout_from"),
                    "brkeout_to":   m.get("data_brkeout_to"),
                    "wt_below":     m.get("data_wt_below"),
                    "wt_between":   m.get("data_wt_between"),
                    "wt_above":     m.get("data_wt_above"),
                    "scoring_mode": m.get("data_scoring_mode") or "jump",
                    "score_params": m.get("data_score_params"),
                    "override":     m.get("weight_override"),
                })
            elif kind == "composite":
                composite_index[code]["members"].append({
                    "kind": "composite",
                    "child":    m.get("nested_composite_code"),
                    "override": m.get("weight_override"),
                })

        # ---- 7. Resolve column source for each atomic rule ------------------
        # Mirrors etl.derive._resolve_atomic_input_column: prefer
        # ref_ma_columns(drv_cat_atomic_input) → any registry hit → FQN parse.
        rule_names = [a["rule_name"] for a in atomic_rules if a.get("rule_name")]
        col_lookup: dict = {}
        if rule_names:
            try:
                reg = s.execute(text("""
                    SELECT excel_header, column_name, drv_cat_table
                    FROM ref_ma_columns
                    WHERE excel_header = ANY(:names)
                    ORDER BY CASE WHEN drv_cat_table='drv_cat_atomic_input' THEN 0 ELSE 1 END
                """), {"names": rule_names}).mappings().all()
                for r in reg:
                    col_lookup.setdefault(r["excel_header"],
                                          (r["drv_cat_table"], r["column_name"]))
            except Exception:
                pass
        for a in atomic_rules:
            if a["rule_name"] in col_lookup:
                continue
            ma_col = a.get("ma_column_name") or ""
            if "." in ma_col:
                tbl, _, col = ma_col.partition(".")
                col_lookup[a["rule_name"]] = (tbl, col)

        # ---- 8. Evaluate atomic rules ---------------------------------------
        atomics_out = []
        atomic_score = {}    # atom_id -> weight (for composite roll-up)
        atomic_value = {}    # atom_id -> raw value
        n_atomic_fired = 0   # incremented when weight != 0
        for a in atomic_rules:
            src = col_lookup.get(a["rule_name"])
            value = None
            ma_col_display = a.get("ma_column_name") or ""
            if src:
                tbl, col = src
                ma_col_display = f"{tbl}.{col}"
                if tbl == "drv_cat_atomic_input":
                    value = ai_row.get(col)
                elif tbl == "drv_ma":
                    value = ma_row.get(col)
                else:
                    # Other drv_cat_* table — read on demand
                    try:
                        rrow = s.execute(text(
                            f'SELECT "{col}" AS v FROM {tbl} '
                            "WHERE as_of_date=:d AND symbol=:sym LIMIT 1"
                        ), {"d": snap, "sym": sym_u}).mappings().first()
                        value = rrow["v"] if rrow else None
                    except Exception:
                        value = None

            try:
                weight = float(eval_atomic_rule(value, dict(a)))
            except Exception:
                weight = 0.0
            if weight != 0:
                n_atomic_fired += 1

            atomic_score[a["atomic_rule_id"]] = weight
            try:
                atomic_value[a["atomic_rule_id"]] = float(value) if value is not None else None
            except (TypeError, ValueError):
                atomic_value[a["atomic_rule_id"]] = None

            try:
                v_out = float(value) if value is not None else None
            except (TypeError, ValueError):
                v_out = value if isinstance(value, str) else None

            try:
                bf = float(a["brkeout_from"]) if a.get("brkeout_from") is not None else None
            except (TypeError, ValueError):
                bf = None
            try:
                bt = float(a["brkeout_to"]) if a.get("brkeout_to") is not None else None
            except (TypeError, ValueError):
                bt = None

            # Human-readable reason — explain WHY this rule fired or didn't.
            #   no_column           : rule has no column resolution at all
            #   no_data             : column resolved but row value is NULL
            #   value_not_numeric   : value is text and rule mode requires float
            #   below_band          : v < brkeout_from → wt_below (which may be 0)
            #   in_band             : brkeout_from ≤ v ≤ brkeout_to → wt_between
            #   above_band          : v > brkeout_to → wt_above
            #   no_thresholds       : rule has no brkeout values set (placeholder)
            applied = value is not None
            band = None
            reason = ""
            if not src:
                reason = "no_column — rule has no resolved drv_ma / drv_cat_atomic_input column"
            elif value is None:
                reason = "no_data — column resolved but row value is NULL"
            else:
                try:
                    vnum = float(value)
                    has_thresh = (bf is not None) or (bt is not None)
                    if not has_thresh:
                        reason = "no_thresholds — rule has no brkeout values (placeholder)"
                    elif bf is not None and vnum < bf:
                        band = "below"
                        reason = f"below_band — value {vnum:g} < brkeout_from {bf:g}"
                    elif bt is not None and vnum > bt:
                        band = "above"
                        reason = f"above_band — value {vnum:g} > brkeout_to {bt:g}"
                    else:
                        band = "between"
                        lo = f"{bf:g}" if bf is not None else "-∞"
                        hi = f"{bt:g}" if bt is not None else "+∞"
                        reason = f"in_band — value {vnum:g} in [{lo}, {hi}]"
                except (TypeError, ValueError):
                    reason = f"value_not_numeric — column value {value!r} can't cast to float"

            # Extract weights for display
            try: wb = float(a.get("wt_below"))   if a.get("wt_below")   is not None else None
            except (TypeError, ValueError): wb = None
            try: wbt = float(a.get("wt_between")) if a.get("wt_between") is not None else None
            except (TypeError, ValueError): wbt = None
            try: wa = float(a.get("wt_above"))   if a.get("wt_above")   is not None else None
            except (TypeError, ValueError): wa = None

            atomics_out.append({
                "id":            a["atomic_rule_id"],
                "rule_name":     a.get("rule_name"),
                "ma_column":     ma_col_display,
                "value":         v_out,
                "applied":       applied,
                "brkeout_from":  bf,
                "brkeout_to":    bt,
                "wt_below":      wb,
                "wt_between":    wbt,
                "wt_above":      wa,
                "band":          band,    # 'below' | 'between' | 'above' | None
                "scoring_mode":  a.get("scoring_mode") or "jump",
                "weight":        weight,
                "fired":         weight != 0,
                "reason":        reason,
                "category":      a.get("category"),
                "rolls_into":    sorted(rolls_into.get(a["atomic_rule_id"], [])),
            })

        # ---- 9. Evaluate composite rules ------------------------------------
        # Single-pass (no topo): for nested composites, read the child's
        # pre-computed score from drv_stks where possible. Cycle-safe full
        # recursion is the derive layer's job.
        composites_out = []
        n_composite_fired = 0
        for code in sorted(composite_index.keys()):
            info = composite_index[code]

            # Precondition gate against the ma_row
            pre = info.get("precondition")
            if pre and ma_row and not _eval_precondition(pre, ma_row):
                composites_out.append({
                    "code":      code,
                    "fired":     False,
                    "score":     0.0,
                    "label":     comp_label.get(code, ""),
                    "n_atomics": len(info["members"]),
                    "n_fired":   0,
                })
                continue

            score = 0.0
            n_member_fired = 0
            for member in info["members"]:
                kind = member["kind"]
                w = 0.0
                if kind == "atomic":
                    aid = member["atom_id"]
                    w = float(atomic_score.get(aid, 0.0)) if aid is not None else 0.0
                    ovr = member.get("override")
                    if ovr is not None and w != 0:
                        w = float(ovr)
                elif kind == "data":
                    col_path = member.get("column") or ""
                    if "." in col_path:
                        tbl, _, col = col_path.partition(".")
                    else:
                        tbl, col = "drv_cat_atomic_input", col_path
                    val = ma_row.get(col) if ma_row else None
                    thr = member.get("threshold")
                    if val is not None and thr is not None:
                        try:
                            if float(val) >= float(thr):
                                w = float(member.get("weight") or 1.0)
                        except (TypeError, ValueError):
                            pass
                elif kind == "composite":
                    # nested composite — read child score from drv_stks if available
                    child_code = member.get("child_code")
                    child_score = 0.0
                    if child_code and stks_row:
                        for cc in (stks_row.get("triggered_composite_ids") or []):
                            if isinstance(cc, dict) and cc.get("rule_id") == child_code:
                                child_score = float(cc.get("score") or 1.0)
                                break
                    w = child_score * float(member.get("weight") or 1.0)
                else:
                    w = 0.0
                if w:
                    n_member_fired += 1
                score += w

            composites_out.append({
                "code":      code,
                "fired":     score > 0,
                "score":     score,
                "label":     comp_label.get(code, ""),
                "n_atomics": len(info["members"]),
                "n_fired":   n_member_fired,
            })
            if score > 0:
                n_composite_fired += 1

        # ---- 7. Outlook attribution from drv_outlook_action -----------------
        # Per-source actions for this (symbol, date) — what changed and why.
        outlook_rows = s.execute(text("""
            SELECT source_code, base_weight, prev_weight, prev_date,
                   weight_delta, held_today, action, action_reason, category
            FROM drv_outlook_action
            WHERE as_of_date = :d AND tos_symbol = :sym
            ORDER BY source_code
        """), {"d": snap, "sym": sym_u}).mappings().all()
        outlook_actions = [dict(r) for r in outlook_rows]
        outlook_changed = any(
            (r.get("action") in ("REMOVE", "REDUCE", "INCREASE", "ADD"))
            for r in outlook_actions
        )

        # ---- 8. Consolidated decision from drv_actionable -------------------
        actionable_row = s.execute(text("""
            SELECT consolidated_action, winning_source, winning_priority,
                   position_category, suggested_target_dollar,
                   current_position_dollar, held_today, in_my_list,
                   suppressed_reason, triggered_group_ids
            FROM drv_actionable
            WHERE as_of_date = :d AND tos_symbol = :sym
            LIMIT 1
        """), {"d": snap, "sym": sym_u}).mappings().first()
        actionable = dict(actionable_row) if actionable_row else None

        return {
            "symbol":    sym,
            "as_of":     snap.isoformat(),
            "atomics":   atomics_out,
            "composites": composites_out,
            "outlook":   {
                "changed":  outlook_changed,
                "actions":  outlook_actions,
                "n_sources_changed": sum(
                    1 for r in outlook_actions
                    if r.get("action") in ("REMOVE", "REDUCE", "INCREASE", "ADD")
                ),
            },
            "actionable": actionable,
            "summary":   {
                "n_atomics":          len(atomics_out),
                "n_atomics_fired":    n_atomic_fired,
                "n_composites":       len(composites_out),
                "n_composites_fired": n_composite_fired,
            },
        }
