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
                  (as_of_date, symbol, tos_symbol, action_code, user_action,
                   triggered_rules, notes)
                VALUES (:d, :sym, :sym, :code, :ua,
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
        "tos_symbol": str, "as_of_date": "YYYY-MM-DD",
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
            SELECT m.tos_symbol, m.description, m.sector, m.asset_class, m.last_price,
                   st.composite_outlook, st.composite_label,
                   st.triggered_atomic_ids, st.triggered_composite_ids
            FROM drv_ma m
            LEFT JOIN drv_stks st
              ON st.as_of_date = m.as_of_date AND st.tos_symbol = m.tos_symbol
            WHERE m.as_of_date = :d AND m.tos_symbol = :sym
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
                "SELECT * FROM drv_ma WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym_u}).mappings().first() or {})
        except Exception:
            ma_row = {}
        try:
            ai_row = dict(s.execute(text(
                "SELECT * FROM drv_cat_atomic_input WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
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
                    "kind":      "atomic",
                    "atom_id":   atom_id,
                    "threshold": m.get("data_brkeout_from"),
                    "override":  m.get("weight_override"),
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
                # All active rules source from drv_cat_atomic_input, which stores
                # pre-evaluated weights — pass through directly.
                weight = float(value) if value is not None else 0.0
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
            #   direct              : Direct-type rule — value is the pre-scored weight from drv_cat_atomic_input
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
                        reason = "direct — pre-scored in drv_cat_atomic_input, value is the weight"
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
            "tos_symbol": sym,
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


# -----------------------------------------------------------------------------
# Rule-Flow endpoint — full 5-tier trace for /rule-flow screen
# -----------------------------------------------------------------------------

@router.get("/api/rule-flow/{sym}", response_model=dict)
def get_rule_flow(sym: str, as_of: Optional[str] = Query(None, alias="date")):
    """Full data-flow trace across all 5 tiers for the /rule-flow diagnostic screen.

    Returns: indicators, atomics (with reason), composites (with member detail),
    rule_groups (with composite membership + fired status), and final output.
    """
    from etl.derive import eval_atomic_rule, _eval_precondition, _MA_COL_MAP

    sym_u = sym.upper().strip()
    with session_scope() as s:
        # 1. Resolve snapshot date
        if as_of:
            try:
                snap = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        else:
            row = s.execute(text("SELECT MAX(as_of_date) FROM drv_stks")).scalar()
            snap = row if row else date.today()

        # 2. drv_ma + drv_cat_atomic_input rows
        ma_row = dict(s.execute(text(
            "SELECT * FROM drv_ma WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
        ), {"d": snap, "sym": sym_u}).mappings().first() or {})
        if not ma_row:
            raise HTTPException(status_code=404,
                                detail=f"No data for {sym_u!r} on {snap}")
        ai_row = dict(s.execute(text(
            "SELECT * FROM drv_cat_atomic_input WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
        ), {"d": snap, "sym": sym_u}).mappings().first() or {})

        # 3. Indicators — non-null drv_cat_atomic_input values, skip metadata cols
        skip_cols = {"as_of_date", "tos_symbol", "computed_at", "source_run_id"}
        indicators = [
            {"name": k, "value": float(v) if isinstance(v, (int, float)) else v}
            for k, v in ai_row.items()
            if k not in skip_cols and v is not None
        ]

        # 4. Atomic rules
        atomic_rules = s.execute(text("""
            SELECT atomic_rule_id, rule_name, ma_column_name,
                   source_column, source_table,
                   brkeout_from, brkeout_to, wt_below, wt_between, wt_above,
                   scoring_mode, category
            FROM ref_trig_atomic_rule WHERE deprecated_at IS NULL
            ORDER BY atomic_rule_id
        """)).mappings().all()

        # 5. Composite mappings
        mappings = s.execute(text("""
            SELECT composite_rule_code, COALESCE(member_kind,'atomic') AS member_kind,
                   atomic_rule_id, weight_override,
                   data_column, nested_composite_code, precondition_expr
            FROM ref_trig_composite_mapping
            WHERE deprecated_at IS NULL
            ORDER BY composite_rule_code, atomic_rule_id
        """)).mappings().all()

        # 6. Column resolution (mirrors _resolve_atomic_input_column)
        rule_names = [a["rule_name"] for a in atomic_rules if a.get("rule_name")]
        col_lookup: dict = {}
        reg = s.execute(text("""
            SELECT excel_header, column_name, drv_cat_table FROM ref_ma_columns
            WHERE excel_header = ANY(:n)
            ORDER BY CASE WHEN drv_cat_table='drv_cat_atomic_input' THEN 0 ELSE 1 END
        """), {"n": rule_names}).mappings().all()
        for r in reg:
            col_lookup.setdefault(r["excel_header"], (r["drv_cat_table"], r["column_name"]))
        for a in atomic_rules:
            rn = a["rule_name"] or ""
            if rn in col_lookup:
                continue
            ma_col = a.get("ma_column_name") or ""
            if "." in ma_col:
                tbl, _, col = ma_col.partition(".")
                col_lookup[rn] = (tbl, col)
                continue
            legacy = _MA_COL_MAP.get(rn) or _MA_COL_MAP.get(ma_col)
            if legacy:
                col_lookup[rn] = ("drv_ma", legacy)

        # 7. Evaluate atomic rules
        atomic_score: dict = {}
        atomic_value: dict = {}
        atomic_reason: dict = {}
        atomics_out = []
        rolls_into: dict = {}
        for m in mappings:
            if m["member_kind"] == "atomic" and m["atomic_rule_id"] is not None:
                rolls_into.setdefault(m["atomic_rule_id"], []).append(m["composite_rule_code"])

        for a in atomic_rules:
            rid = a["atomic_rule_id"]
            rn  = a["rule_name"] or ""
            src = col_lookup.get(rn)
            value = None
            col_display = a.get("ma_column_name") or ""
            if src:
                tbl, col = src
                col_display = f"{tbl}.{col}"
                value = (ai_row if tbl == "drv_cat_atomic_input" else ma_row).get(col)

            try:
                weight = float(value) if value is not None else 0.0
            except Exception:
                weight = 0.0
            atomic_score[rid] = weight
            try:
                atomic_value[rid] = float(value) if value is not None else None
            except (TypeError, ValueError):
                atomic_value[rid] = None

            # Reason
            try: bf = float(a["brkeout_from"]) if a.get("brkeout_from") is not None else None
            except (TypeError, ValueError): bf = None
            try: bt = float(a["brkeout_to"]) if a.get("brkeout_to") is not None else None
            except (TypeError, ValueError): bt = None

            band = None
            if not src:
                reason = "no_column"
            elif value is None:
                reason = "no_data"
            else:
                try:
                    vn = float(value)
                    if bf is None and bt is None:
                        reason = "direct"
                    elif bf is not None and vn < bf:
                        band = "below"; reason = f"below_band ({vn:g} < {bf:g})"
                    elif bt is not None and vn > bt:
                        band = "above"; reason = f"above_band ({vn:g} > {bt:g})"
                    else:
                        band = "between"
                        lo = f"{bf:g}" if bf is not None else "-inf"
                        hi = f"{bt:g}" if bt is not None else "+inf"
                        reason = f"in_band ({vn:g} in [{lo},{hi}])"
                except (TypeError, ValueError):
                    reason = "not_numeric"
            atomic_reason[rid] = reason

            try: v_out = float(value) if value is not None else None
            except (TypeError, ValueError): v_out = None
            try: wb  = float(a["wt_below"])   if a.get("wt_below")   is not None else None
            except: wb = None
            try: wbt = float(a["wt_between"]) if a.get("wt_between") is not None else None
            except: wbt = None
            try: wa  = float(a["wt_above"])   if a.get("wt_above")   is not None else None
            except: wa = None

            atomics_out.append({
                "id": rid, "rule_name": rn, "ma_column": col_display,
                "value": v_out, "band": band, "reason": reason,
                "brkeout_from": bf, "brkeout_to": bt,
                "wt_below": wb, "wt_between": wbt, "wt_above": wa,
                "weight": weight, "fired": weight != 0,
                "category": a.get("category"),
                "rolls_into": sorted(set(rolls_into.get(rid, []))),
                "source_column": a.get("source_column"),
                "source_table":  a.get("source_table"),
                "source_value": None,  # filled below
            })

        atomic_by_id = {a["id"]: a for a in atomics_out}

        # 7b. Batch-fetch source_column values using explicit source_table
        _src_needed: dict = {}   # {tbl: set(cols)}
        _src_idx: dict = {}      # {rule_id: (tbl, col)}
        for a in atomics_out:
            sc = a.get("source_column")
            st = a.get("source_table")
            if sc and st:
                # Preferred: explicit source_table + source_column (bare DB column name)
                _src_needed.setdefault(st, set()).add(sc)
                _src_idx[a["id"]] = (st, sc)
            elif sc and "." in sc:
                # Legacy: table.column packed into source_column
                tbl, col = sc.split(".", 1)
                _src_needed.setdefault(tbl, set()).add(col)
                _src_idx[a["id"]] = (tbl, col)

        _src_vals: dict = {}     # {(tbl, col): value}
        for tbl, cols in _src_needed.items():
            is_hist = tbl.startswith("hist_")
            sym_col  = "symbol"        if is_hist else "tos_symbol"
            date_col = "snapshot_date" if is_hist else "as_of_date"
            op       = "<="            if is_hist else "="
            ord_cl   = f" ORDER BY {date_col} DESC LIMIT 1" if is_hist else " LIMIT 1"
            col_expr = ", ".join(f'"{c}"' for c in sorted(cols))
            sql = (f"SELECT {col_expr} FROM {tbl}"
                   f" WHERE {sym_col}=:sym AND {date_col}{op}:d{ord_cl}")
            if len(sql) > 960:
                continue
            try:
                with s.begin_nested():
                    row = s.execute(text(sql), {"sym": sym_u, "d": snap}).mappings().first()
                    if row:
                        for c, v in dict(row).items():
                            _src_vals[(tbl, c)] = v
            except Exception:
                pass

        for a in atomics_out:
            tc = _src_idx.get(a["id"])
            if tc:
                v = _src_vals.get(tc)
                try:
                    a["source_value"] = float(v) if v is not None else None
                except (TypeError, ValueError):
                    a["source_value"] = str(v) if v is not None else None

        # 8. Evaluate composites with member detail
        composite_index: dict = {}
        for m in mappings:
            code = m["composite_rule_code"]
            if code not in composite_index:
                composite_index[code] = {
                    "precondition": m.get("precondition_expr"),
                    "members": [],
                }
            composite_index[code]["members"].append(dict(m))

        composites_out = []
        composite_fired: dict = {}
        for code in sorted(composite_index.keys()):
            info = composite_index[code]
            pre  = info.get("precondition")
            if pre and ma_row and not _eval_precondition(pre, ma_row):
                composites_out.append({"code": code, "fired": False, "score": 0.0,
                                       "n_member_hit": 0, "precondition_blocked": True,
                                       "precondition": pre, "members": []})
                composite_fired[code] = False
                continue

            score = 0.0
            n_hit = 0
            members_out = []
            for m in info["members"]:
                kind = m.get("kind") or m.get("member_kind", "atomic")
                w = 0.0
                member_entry: dict = {"kind": kind}
                if kind == "atomic":
                    aid       = m.get("atom_id") or m.get("atomic_rule_id")
                    threshold = m.get("threshold")
                    ovr       = m.get("override") or m.get("weight_override")
                    val       = float(atomic_score.get(aid, 0.0)) if aid is not None else 0.0
                    if threshold is None:
                        condition_met = (val != 0)
                    else:
                        thr = float(threshold)
                        condition_met = (val >= thr) if thr >= 0 else (val <= thr)
                    w = float(ovr) if (condition_met and ovr is not None) else (val if condition_met else 0.0)
                    ar = atomic_by_id.get(aid, {})
                    member_entry.update({
                        "rule_id": aid, "rule_name": ar.get("rule_name"),
                        "value": val, "weight": w,
                        "condition_met": condition_met,
                        "threshold": threshold,
                        "fired": condition_met, "reason": atomic_reason.get(aid, ""),
                        "band": ar.get("band"),
                        "brkeout_from": ar.get("brkeout_from"),
                        "brkeout_to":   ar.get("brkeout_to"),
                    })
                elif kind == "data":
                    member_entry["column"] = m.get("data_column")
                elif kind == "composite":
                    child = m.get("nested_composite_code")
                    member_entry["child"] = child
                    w = 1.0 if composite_fired.get(child) else 0.0
                if w != 0:
                    n_hit += 1
                score += w
                members_out.append(member_entry)

            # Fires only when ALL members contribute (all conditions met)
            n_total = len(members_out)
            fired = n_total > 0 and n_hit == n_total
            composites_out.append({
                "code": code, "fired": fired, "score": score,
                "n_member_hit": n_hit, "precondition": pre,
                "precondition_blocked": False, "members": members_out,
            })
            composite_fired[code] = fired

        # 9. Rule groups
        group_rows = s.execute(text("""
            SELECT rule_group_code, group_type, action_label, priority, category, intent_text
            FROM ref_trig_rule_group WHERE deprecated_at IS NULL
            ORDER BY priority, rule_group_code
        """)).mappings().all()
        grp_members = s.execute(text("""
            SELECT rule_group_code, member_code, member_type, logic_operator, sequence
            FROM ref_trig_group_member ORDER BY rule_group_code, sequence
        """)).mappings().all()
        grp_member_index: dict = {}
        for gm in grp_members:
            grp_member_index.setdefault(gm["rule_group_code"], []).append(dict(gm))

        rule_groups_out = []
        for g in group_rows:
            code   = g["rule_group_code"]
            gmembs = grp_member_index.get(code, [])
            fired  = False
            member_results = []
            broke  = False
            for gm in gmembs:
                mc = gm["member_code"]
                mf = composite_fired.get(mc, False)
                member_results.append({
                    "code": mc, "operator": gm["logic_operator"],
                    "member_type": gm["member_type"], "fired": mf,
                })
                if gm["logic_operator"] == "AND" and not mf:
                    broke = True
                    break
            if not broke:
                ops = [gm["logic_operator"] for gm in gmembs]
                fired = any(r["fired"] for r in member_results) if "OR" in ops \
                        else all(r["fired"] for r in member_results)
            rule_groups_out.append({
                "code": code, "group_type": g["group_type"],
                "action_label": g.get("action_label"), "priority": g.get("priority"),
                "category": g.get("category"), "intent_text": g.get("intent_text"),
                "fired": fired, "members": member_results,
            })

        # 10a. Raw hist_* and drv_* values for side panels
        import math as _math
        def _ser(v):
            if v is None: return None
            if isinstance(v, bool): return v
            if isinstance(v, int): return v
            if isinstance(v, float):
                return None if _math.isnan(v) or _math.isinf(v) else v
            if hasattr(v, 'isoformat'): return v.isoformat()
            if isinstance(v, (list, dict)): return None
            try:
                fv = float(v)
                return None if _math.isnan(fv) or _math.isinf(fv) else fv
            except Exception: pass
            return str(v)

        _META_SKIP = {
            'snapshot_date', 'as_of_date', 'symbol', 'tos_symbol',
            'loaded_at', 'computed_at', 'source_run_id', 'sequence', 'account',
            'triggered_atomic_ids', 'triggered_composite_ids',
            'triggered_group_ids', 'source_actions',
        }

        hist_raw: dict = {}
        for _tbl in ('hist_td', 'hist_tw', 'hist_to', 'hist_tl', 'hist_y'):
            try:
                with s.begin_nested():
                    _row = s.execute(text(
                        f"SELECT * FROM {_tbl}"
                        f" WHERE symbol=:sym AND snapshot_date<=:d"
                        f" ORDER BY snapshot_date DESC LIMIT 1"
                    ), {"sym": sym_u, "d": snap}).mappings().first()
                    hist_raw[_tbl] = {
                        k: _ser(v) for k, v in (dict(_row) if _row else {}).items()
                        if k not in _META_SKIP and v is not None
                    }
            except Exception:
                hist_raw[_tbl] = {}

        drv_raw: dict = {}
        for _tbl in ('drv_symbols', 'drv_technicals', 'drv_fundamentals',
                     'drv_outlooks', 'drv_portfolio', 'drv_cat_atomic_input',
                     'drv_dash', 'drv_actionable', 'drv_quote', 'drv_rr'):
            try:
                with s.begin_nested():
                    _row = s.execute(text(
                        f"SELECT * FROM {_tbl}"
                        f" WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
                    ), {"d": snap, "sym": sym_u}).mappings().first()
                    drv_raw[_tbl] = {
                        k: _ser(v) for k, v in (dict(_row) if _row else {}).items()
                        if k not in _META_SKIP and v is not None
                    }
            except Exception:
                drv_raw[_tbl] = {}

        # 10. Final output from drv_actionable + buysell scores
        act = s.execute(text("""
            SELECT consolidated_action, trig_action, winning_source, winning_priority,
                   triggered_group_ids, source_actions, suppressed_reason
            FROM drv_actionable WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1
        """), {"d": snap, "sym": sym_u}).mappings().first()

        buysell = {r[0]: float(r[1]) for r in s.execute(text(
            "SELECT code, extra1 FROM ref_param_lookup"
            " WHERE table_name='buysell' AND extra1 IS NOT NULL"
        )).fetchall() if r[1] is not None and str(r[1]).replace('-','').replace('.','').isdigit()}

        return {
            "tos_symbol": sym_u,
            "as_of": snap.isoformat(),
            "summary": {
                "description":     ma_row.get("description"),
                "sector":          ma_row.get("sector"),
                "asset_class":     ma_row.get("asset_class"),
                "last_price":      float(ma_row["last_price"]) if ma_row.get("last_price") else None,
                "rsi":             float(ma_row["rsi"]) if ma_row.get("rsi") else None,
                "composite_label": s.execute(text(
                    "SELECT composite_label FROM drv_stks WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
                ), {"d": snap, "sym": sym_u}).scalar(),
                "n_atomic_fired":    sum(1 for a in atomics_out if a["fired"]),
                "n_atomic_total":    len(atomics_out),
                "n_composite_fired": sum(1 for c in composites_out if c["fired"]),
                "n_composite_total": len(composites_out),
                "n_group_fired":     sum(1 for g in rule_groups_out if g["fired"]),
                "n_group_total":     len(rule_groups_out),
            },
            "indicators":   indicators,
            "atomics":      atomics_out,
            "composites":   composites_out,
            "rule_groups":  rule_groups_out,
            "hist_raw":     hist_raw,
            "drv_raw":      drv_raw,
            "final": {
                "consolidated_action": act["consolidated_action"] if act else None,
                "trig_action":         act["trig_action"]         if act else None,
                "winning_source":      act["winning_source"]      if act else None,
                "suppressed_reason":   act["suppressed_reason"]   if act else None,
                "triggered_groups":    act["triggered_group_ids"] if act else [],
                "buysell_scores":      buysell,
            },
        }


@router.get("/api/rule-flow/{sym}/intermediates")
def get_rule_flow_intermediates(sym: str, as_of: Optional[str] = Query(None, alias="date")):
    """Return compute_intermediates output for one symbol — feeds the Data Flow panel."""
    import math as _math
    from datetime import date as _date
    from etl.derive_cat_atomic_input import get_symbol_intermediates
    from etl.db import session_scope

    sym_u = sym.upper().strip()
    if as_of:
        try:
            snap = _date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    else:
        with session_scope() as s:
            row = s.execute(text("SELECT MAX(as_of_date) FROM drv_stks")).scalar()
            snap = row if row else _date.today()

    def _ser(v):
        if v is None: return None
        if isinstance(v, bool): return v
        if isinstance(v, (int, float)):
            try:
                return None if _math.isnan(float(v)) or _math.isinf(float(v)) else round(float(v), 6)
            except Exception: return None
        if hasattr(v, "isoformat"): return v.isoformat()
        try:
            fv = float(v); return None if _math.isnan(fv) or _math.isinf(fv) else round(fv, 6)
        except Exception: pass
        return str(v)

    with session_scope() as s:
        row = get_symbol_intermediates(s, sym_u, snap)

    _SKIP = {"tos_symbol", "as_of_date", "source_run_id", "computed_at"}
    return {k: _ser(v) for k, v in row.items() if k not in _SKIP}
