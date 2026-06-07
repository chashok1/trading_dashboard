"""Rule Engine endpoints: atomic, composite, performance, groups, dryrun."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from etl.db import safe_ident, session_scope

from api.models import (
    AtomicRuleCreateRequest, AtomicRuleUpdateRequest,
    CompositeRuleCreateRequest, CompositeRuleUpdateRequest,
)
from api._helpers import _resolve_date

router = APIRouter()


# -----------------------------------------------------------------------------
# Rule Engine v2 — Read-only API
# -----------------------------------------------------------------------------

@router.get("/api/rules/atomic", response_model=list[dict])
def list_atomic_rules(
    category: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """List atomic rules with optional filtering."""
    with session_scope() as s:
        sql = """SELECT atomic_rule_id, rule_name, brkeout_from, brkeout_to,
                        wt_below, wt_between, wt_above, neg_multiplier,
                        ma_column_name, source_column, source_table,
                        category, intent_text, scoring_mode, score_params, deprecated_at
                 FROM ref_trig_atomic_rule WHERE deprecated_at IS NULL"""
        params = {}
        if category:
            sql += " AND category = :cat"
            params["cat"] = category
        sql += " ORDER BY atomic_rule_id LIMIT :lim OFFSET :off"
        params["lim"] = limit
        params["off"] = offset

        rows = s.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]


@router.get("/api/rules/atomic/{rule_id}", response_model=dict)
def get_atomic_rule(rule_id: str):
    """Get a single atomic rule."""
    with session_scope() as s:
        row = s.execute(
            text("""SELECT atomic_rule_id as rule_id, rule_name,
                           brkeout_from, brkeout_to, wt_below, wt_between, wt_above,
                           ma_column_name, source_column, source_table, category,
                           intent_text, scoring_mode, score_params, deprecated_at
                    FROM ref_trig_atomic_rule WHERE atomic_rule_id = :rid"""),
            {"rid": rule_id}
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return dict(row)


@router.get("/api/rules/composite", response_model=list[dict])
def list_composite_rules(
    category: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """List composite rules (distinct rules only)."""
    with session_scope() as s:
        sql = "SELECT DISTINCT ON (composite_rule_code) composite_rule_code, category, intent_text, precondition_expr, deprecated_at, active FROM ref_trig_composite_mapping WHERE deprecated_at IS NULL"
        params = {}
        if category:
            sql += " AND category = :cat"
            params["cat"] = category
        sql += " ORDER BY composite_rule_code LIMIT :lim OFFSET :off"
        params["lim"] = limit
        params["off"] = offset

        rows = s.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]


@router.get("/api/rules/composite/{rule_id}", response_model=dict)
def get_composite_rule(rule_id: str):
    """Get a single composite rule."""
    with session_scope() as s:
        row = s.execute(
            text("""SELECT DISTINCT ON (composite_rule_code) composite_rule_code as rule_id,
                           category, intent_text, precondition_expr, deprecated_at,
                           evidence_cutoff
                    FROM ref_trig_composite_mapping WHERE composite_rule_code = :rid"""),
            {"rid": rule_id}
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return dict(row)


@router.get("/api/rules/composite/{rule_id}/atomics", response_model=list[dict])
def get_composite_rule_atomics(rule_id: str):
    """Get the atomic rules that feed into a composite rule."""
    with session_scope() as s:
        rows = s.execute(
            text("""SELECT a.atomic_rule_id, a.rule_name, a.category, a.scoring_mode,
                           a.brkeout_from, a.brkeout_to, a.wt_below, a.wt_between, a.wt_above,
                           m.weight_override, m.data_brkeout_from, m.active,
                           m.condition_operator,
                           COALESCE(m.member_role, 'gate') AS member_role, m.evidence_cutoff
                    FROM ref_trig_atomic_rule a
                    JOIN ref_trig_composite_mapping m ON a.atomic_rule_id = m.atomic_rule_id
                    WHERE m.composite_rule_code = :crc AND a.deprecated_at IS NULL
                    ORDER BY a.atomic_rule_id"""),
            {"crc": rule_id}
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/rules/health", response_model=dict)
def get_rules_engine_health():
    """One-shot health check for the rules engine.

    Surfaces the data-state diagnostics that would otherwise need 10 ad-hoc
    SQL queries: did the workbook load? does drv_cat_atomic_input have rows
    for the latest date? are any composites orphaned? when did the derive
    last succeed? how does today's fire-count compare to the 30-day baseline?

    Used by /rules-health page. Each block is independent — a failure in one
    is captured in `warnings` and the rest still return.
    """
    out: dict = {"warnings": []}
    with session_scope() as s:
        # 1. Rules table loaded?
        try:
            atomic_total = s.execute(text(
                "SELECT COUNT(*) FROM ref_trig_atomic_rule"
            )).scalar() or 0
            atomic_active = s.execute(text(
                "SELECT COUNT(*) FROM ref_trig_atomic_rule WHERE deprecated_at IS NULL"
            )).scalar() or 0
            atomic_with_weights = s.execute(text("""
                SELECT COUNT(*) FROM ref_trig_atomic_rule
                WHERE deprecated_at IS NULL AND (
                  brkeout_from IS NOT NULL OR brkeout_to IS NOT NULL OR
                  wt_below IS NOT NULL OR wt_between IS NOT NULL OR wt_above IS NOT NULL
                )
            """)).scalar() or 0
        except Exception as e:
            atomic_total = atomic_active = atomic_with_weights = -1
            out["warnings"].append(f"atomic rules: {e}")

        # 2. Composite mappings loaded?
        try:
            comp_total = s.execute(text(
                "SELECT COUNT(DISTINCT composite_rule_code) FROM ref_trig_composite_mapping"
            )).scalar() or 0
            comp_active = s.execute(text(
                "SELECT COUNT(DISTINCT composite_rule_code) FROM ref_trig_composite_mapping "
                "WHERE deprecated_at IS NULL"
            )).scalar() or 0
            comp_rows = s.execute(text(
                "SELECT COUNT(*) FROM ref_trig_composite_mapping WHERE deprecated_at IS NULL"
            )).scalar() or 0
        except Exception as e:
            comp_total = comp_active = comp_rows = -1
            out["warnings"].append(f"composite mappings: {e}")

        # 3. Orphaned composite members (atomic_rule_id no longer active)
        try:
            orphans = s.execute(text("""
                SELECT m.composite_rule_code, COUNT(*) AS n_orphaned
                FROM ref_trig_composite_mapping m
                WHERE m.deprecated_at IS NULL
                  AND m.member_kind = 'atomic'
                  AND m.atomic_rule_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM ref_trig_atomic_rule a
                    WHERE a.atomic_rule_id = m.atomic_rule_id
                      AND a.deprecated_at IS NULL
                  )
                GROUP BY m.composite_rule_code
                ORDER BY n_orphaned DESC LIMIT 20
            """)).mappings().all()
            out["orphaned_composites"] = [dict(r) for r in orphans]
        except Exception as e:
            out["orphaned_composites"] = []
            out["warnings"].append(f"orphan check: {e}")

        # 4. Latest snapshot date + drv_cat_atomic_input population
        try:
            latest_d = s.execute(text(
                "SELECT MAX(as_of_date) FROM drv_stks"
            )).scalar()
            cat_rows = 0
            ma_rows = 0
            if latest_d:
                try:
                    cat_rows = s.execute(text(
                        "SELECT COUNT(*) FROM drv_cat_atomic_input WHERE as_of_date = :d"
                    ), {"d": latest_d}).scalar() or 0
                except Exception:
                    cat_rows = -1
                try:
                    ma_rows = s.execute(text(
                        "SELECT COUNT(*) FROM drv_ma WHERE as_of_date = :d"
                    ), {"d": latest_d}).scalar() or 0
                except Exception:
                    ma_rows = -1
            out["latest_date"] = latest_d.isoformat() if latest_d else None
            out["drv_ma_rows_latest"] = ma_rows
            out["drv_cat_atomic_input_rows_latest"] = cat_rows
        except Exception as e:
            out["warnings"].append(f"date probe: {e}")

        # 5. Last successful / failed derive runs
        try:
            recent = s.execute(text("""
                SELECT target_table, status, as_of_date,
                       rows_built, started_at, error_msg
                FROM meta_derived_run
                ORDER BY started_at DESC LIMIT 12
            """)).mappings().all()
            out["recent_derives"] = [dict(r) for r in recent]
        except Exception as e:
            out["recent_derives"] = []
            out["warnings"].append(f"meta_derived_run: {e}")

        # 6. Fire counts today vs 30d avg
        try:
            today_fires = s.execute(text("""
                SELECT
                  SUM(jsonb_array_length(COALESCE(triggered_atomic_ids,    '[]'::jsonb))) AS n_atomic,
                  SUM(jsonb_array_length(COALESCE(triggered_composite_ids, '[]'::jsonb))) AS n_composite,
                  COUNT(*) FILTER (WHERE composite_label = 'BULLISH')                     AS n_bull,
                  COUNT(*) FILTER (WHERE composite_label = 'BEARISH')                     AS n_bear,
                  COUNT(*)                                                                AS n_symbols
                FROM drv_stks WHERE as_of_date = :d
            """), {"d": out.get("latest_date")}).mappings().first() or {}
            baseline = s.execute(text("""
                WITH d AS (
                  SELECT as_of_date,
                         SUM(jsonb_array_length(COALESCE(triggered_atomic_ids,    '[]'::jsonb))) AS n_atomic,
                         SUM(jsonb_array_length(COALESCE(triggered_composite_ids, '[]'::jsonb))) AS n_composite
                  FROM drv_stks
                  WHERE as_of_date >= CURRENT_DATE - INTERVAL '30 days'
                  GROUP BY as_of_date
                )
                SELECT AVG(n_atomic) AS avg_atomic, AVG(n_composite) AS avg_composite,
                       COUNT(*) AS n_dates
                FROM d
            """)).mappings().first() or {}
            out["fire_counts"] = {
                "today":    {k: int(v) if v is not None else 0 for k, v in dict(today_fires).items()},
                "baseline": {k: float(v) if v is not None else 0 for k, v in dict(baseline).items()},
            }
        except Exception as e:
            out["fire_counts"] = {}
            out["warnings"].append(f"fire counts: {e}")

        # 7. Column-resolution audit — how many atomic rules have a column?
        try:
            from etl.derive import _resolve_atomic_input_column
            col_map = _resolve_atomic_input_column(s)
            unresolved = s.execute(text("""
                SELECT atomic_rule_id, rule_name
                FROM ref_trig_atomic_rule
                WHERE deprecated_at IS NULL
                ORDER BY atomic_rule_id
            """)).mappings().all()
            unresolved_rules = [
                {"atomic_rule_id": r["atomic_rule_id"], "rule_name": r["rule_name"]}
                for r in unresolved
                if r["atomic_rule_id"] not in col_map
            ]
            out["column_resolution"] = {
                "resolved":   len(col_map),
                "unresolved": len(unresolved_rules),
                "unresolved_sample": unresolved_rules[:20],
            }
        except Exception as e:
            out["column_resolution"] = {}
            out["warnings"].append(f"column resolution: {e}")

    # Top-level summary tiles
    out["counts"] = {
        "atomic_rules_total":          atomic_total,
        "atomic_rules_active":         atomic_active,
        "atomic_rules_with_weights":   atomic_with_weights,
        "composites_total":            comp_total,
        "composites_active":           comp_active,
        "composite_mapping_rows":      comp_rows,
    }

    # Derive a single overall status
    issues = []
    if atomic_active <= 0:
        issues.append("ref_trig_atomic_rule is empty — workbook Trig tab not loaded")
    if comp_active <= 0:
        issues.append("ref_trig_composite_mapping is empty — workbook Trig tab not loaded")
    if out.get("drv_cat_atomic_input_rows_latest") == 0:
        issues.append("drv_cat_atomic_input has zero rows for the latest snapshot — derive_all hasn't built it")
    if out.get("drv_ma_rows_latest") == 0:
        issues.append("drv_ma has zero rows for the latest snapshot — load a workbook")
    if out.get("orphaned_composites"):
        issues.append(f"{len(out['orphaned_composites'])} composites reference deprecated/missing atomic rules")
    if out.get("column_resolution", {}).get("unresolved", 0) > 0:
        issues.append(f"{out['column_resolution']['unresolved']} active atomic rules can't resolve to a column")

    out["status"] = "healthy" if not issues else "degraded"
    out["issues"] = issues
    return out


@router.get("/api/rules/performance", response_model=list[dict])
def get_rule_performance(
    sort_by: Optional[str] = Query("hit_rate"),
    limit: int = Query(500, ge=1, le=5000),
    window: int = Query(180, ge=1, le=3650,
                        description="Rolling window in days (ignored if from/to set)"),
    from_date: Optional[str] = Query(None, alias="from",
                                     description="YYYY-MM-DD (overrides window)"),
    to_date: Optional[str] = Query(None, alias="to",
                                   description="YYYY-MM-DD (default today)"),
    min_n: int = Query(0, ge=0, le=10000,
                       description="Filter out rows where sample_size < this"),
):
    """Get rule performance metrics with configurable window and median.

    Calls v_rule_performance_window(p_window_days, p_from, p_to). Backwards-
    compatible with the original /api/rules/performance — defaults match the
    old 180-day view, but now you can pass ?window=20&min_n=5, or
    ?from=2026-01-01&to=2026-04-30 for an explicit window.

    Response item shape adds: median_fwd_5d, median_fwd_20d, first_seen, last_seen.
    """
    valid_sorts = {"hit_rate", "sample_size", "rule_id", "avg_fwd_5d",
                   "avg_fwd_20d", "median_fwd_5d", "median_fwd_20d"}
    if sort_by not in valid_sorts:
        sort_by = "hit_rate"
    safe_ident(sort_by, valid_sorts)  # defensive — sort_by is allow-listed above

    f_d = None
    t_d = None
    if from_date:
        try:
            f_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "from must be YYYY-MM-DD")
    if to_date:
        try:
            t_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "to must be YYYY-MM-DD")

    with session_scope() as s:
        sql = (
            f"SELECT * FROM v_rule_performance_window(:w, :fd, :td) "
            f"WHERE sample_size >= :min_n "
            f"ORDER BY {sort_by} DESC NULLS LAST LIMIT :lim"
        )
        rows = s.execute(text(sql),
                         {"w": window, "fd": f_d, "td": t_d,
                          "min_n": min_n, "lim": limit}).mappings().all()
        return [dict(r) for r in rows]


@router.get("/api/rules/scorecard", response_model=list[dict])
def get_rule_scorecard(
    min_fires: int = Query(30, ge=0, le=100000,
                           description="Only rules with at least this many fires"),
    limit: int = Query(500, ge=1, le=5000),
):
    """Direction-adjusted composite rule scorecard (Phase 4).

    Reads v_rule_scorecard: `edge_20d` is the average 20d forward return IN THE
    RULE'S FAVOR (SELL sign flipped), so >0 = the signal was right on average.
    No wall-clock window — covers all loaded outcome history. Diagnostic only
    while history is shallow / single-regime; see docs/rule_tuning_and_outcomes.md.
    """
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT rule_id, direction, fires, edge_20d, win_rate, raw_avg_fwd20,
                   first_seen, last_seen
            FROM v_rule_scorecard
            WHERE fires >= :mf
            ORDER BY edge_20d DESC NULLS LAST
            LIMIT :lim
        """), {"mf": min_fires, "lim": limit}).mappings().all()
        return [dict(r) for r in rows]


@router.get("/api/rules/my-actions", response_model=dict)
def get_my_actions(limit: int = Query(200, ge=1, le=2000)):
    """Personal action track record (Phase 4): your DONE actions joined to the
    stock's forward return (v_user_action_performance). Distinct from the rule
    scorecard. Empty until you log actions on the Actionable screen.
    Returns {summary, recent[]}.
    """
    with session_scope() as s:
        recent = s.execute(text("""
            SELECT id, acted_at, as_of_date, tos_symbol, user_action,
                   consolidated_action, fwd_5d_pct, fwd_20d_pct
            FROM v_user_action_performance
            ORDER BY acted_at DESC NULLS LAST
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
        summ = s.execute(text("""
            SELECT COUNT(*)                                          AS n_actions,
                   COUNT(*) FILTER (WHERE fwd_20d_pct IS NOT NULL)   AS n_scored,
                   ROUND(AVG(fwd_20d_pct)::numeric, 2)               AS avg_fwd_20d,
                   ROUND(AVG(fwd_5d_pct)::numeric, 2)                AS avg_fwd_5d
            FROM v_user_action_performance
        """)).mappings().first()
        return {"summary": dict(summ) if summ else {}, "recent": [dict(r) for r in recent]}


@router.post("/api/rules/atomic", response_model=dict, status_code=201)
def create_atomic_rule(body: AtomicRuleCreateRequest):
    """Create a new atomic rule."""
    with session_scope() as s:
        existing = s.execute(
            text("SELECT 1 FROM ref_trig_atomic_rule WHERE atomic_rule_id = :rid"),
            {"rid": body.rule_id}
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Rule {body.rule_id} already exists")
        s.execute(text("""
            INSERT INTO ref_trig_atomic_rule
              (atomic_rule_id, rule_name, category, intent_text, ma_column_name,
               source_column, source_table, scoring_mode, score_params,
               brkeout_from, brkeout_to, wt_below, wt_between, wt_above, neg_multiplier)
            VALUES
              (:rid, :rname, :cat, :intent, :macol,
               :sc, :st, :mode, :params::jsonb, :bf, :bt,
               :wb, :wbt, :wa, :nm)
        """), {
            "rid": body.rule_id, "rname": body.rule_name, "cat": body.category,
            "intent": body.intent_text, "macol": body.ma_column_name,
            "sc": body.source_column,
            "st": body.source_table,
            "mode": body.scoring_mode,
            "params": json.dumps(body.score_params) if body.score_params else None,
            "bf": body.brkeout_from, "bt": body.brkeout_to,
            "wb": body.wt_below, "wbt": body.wt_between, "wa": body.wt_above,
            "nm": body.neg_multiplier,
        })
        s.commit()
    return {"ok": True, "rule_id": body.rule_id}


@router.put("/api/rules/atomic/{rule_id}", response_model=dict)
def update_atomic_rule(rule_id: str, body: AtomicRuleUpdateRequest):
    """Update an existing atomic rule."""
    with session_scope() as s:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["rule_id"] = rule_id
        if "score_params" in updates and updates["score_params"] is not None:
            updates["score_params"] = json.dumps(updates["score_params"])
        result = s.execute(
            text(f"UPDATE ref_trig_atomic_rule SET {set_clause} WHERE atomic_rule_id = :rule_id AND deprecated_at IS NULL"),
            updates
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found or deprecated")
        s.commit()
    return {"ok": True, "updated": result.rowcount}


@router.post("/api/rules/atomic/{rule_id}/dryrun", response_model=dict)
def atomic_rule_dryrun(rule_id: str, body: dict):
    """Preview the impact of an atomic-rule edit BEFORE saving.

    Body shape (all optional — fields not provided fall back to current values):
      {
        "brkeout_from": number|null, "brkeout_to": number|null,
        "wt_below": number|null, "wt_between": number|null, "wt_above": number|null,
        "scoring_mode": "jump|linear|sigmoid"|null,
        "score_params": {}|null,
        "sample_symbol": "AAPL",     # optional, defaults to AAPL
        "as_of_date":    "YYYY-MM-DD" # optional, defaults to latest drv_ma date
      }

    Response shape:
      {
        "rule_id": str, "sample_symbol": str, "as_of_date": str,
        "before": {"value": <num|null>, "weight": <num>, "fired": <bool>},
        "after":  {"value": <num|null>, "weight": <num>, "fired": <bool>},
        "affected_symbols_estimate": <int|null>,  # how many symbols changed fire-state on as_of_date
        "note": str
      }
    """
    from etl.derive import eval_atomic_rule

    sym = (body.get("sample_symbol") or "AAPL").upper().strip()
    as_of = body.get("as_of_date")

    with session_scope() as s:
        # Resolve current rule definition
        current = s.execute(text("""
            SELECT atomic_rule_id, rule_name, ma_column_name,
                   brkeout_from, brkeout_to, wt_below, wt_between, wt_above,
                   neg_multiplier, scoring_mode, score_params
            FROM ref_trig_atomic_rule
            WHERE atomic_rule_id = :rid AND deprecated_at IS NULL
        """), {"rid": rule_id}).mappings().first()
        if not current:
            raise HTTPException(404, f"Rule {rule_id} not found or deprecated")

        # Resolve sample date
        if as_of:
            try:
                snap = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(400, "as_of_date must be YYYY-MM-DD")
        else:
            row = s.execute(text("SELECT MAX(as_of_date) AS d FROM drv_ma")).mappings().first()
            snap = row["d"] if row and row["d"] else date.today()

        # Resolve the value the rule reads from drv_ma / drv_cat_atomic_input
        ma_dict = dict(s.execute(text(
            "SELECT * FROM drv_ma WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
        ), {"d": snap, "sym": sym}).mappings().first() or {})
        try:
            ai_dict = dict(s.execute(text(
                "SELECT * FROM drv_cat_atomic_input WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym}).mappings().first() or {})
        except Exception:
            ai_dict = {}

        # Column resolution: prefer ref_ma_columns mapping by rule_name,
        # fall back to ma_column_name parsing.
        value = None
        col_src = None
        if current["rule_name"]:
            try:
                reg = s.execute(text("""
                    SELECT excel_header, column_name, drv_cat_table
                    FROM ref_ma_columns
                    WHERE excel_header = :h
                    ORDER BY CASE WHEN drv_cat_table='drv_cat_atomic_input' THEN 0 ELSE 1 END
                    LIMIT 1
                """), {"h": current["rule_name"]}).mappings().first()
                if reg:
                    col_src = (reg["drv_cat_table"], reg["column_name"])
            except Exception:
                pass
        if not col_src and current["ma_column_name"] and "." in current["ma_column_name"]:
            tbl, _, col = current["ma_column_name"].partition(".")
            col_src = (tbl, col)
        if col_src:
            tbl, col = col_src
            if tbl == "drv_cat_atomic_input":
                value = ai_dict.get(col)
            else:
                value = ma_dict.get(col)

        before_w = eval_atomic_rule(value, dict(current))
        before = {"value": value, "weight": float(before_w), "fired": before_w != 0}

        # Apply proposed overrides — anything not given falls back to current.
        proposed = dict(current)
        for k in ("brkeout_from", "brkeout_to",
                  "wt_below", "wt_between", "wt_above",
                  "scoring_mode", "score_params"):
            if k in body and body[k] is not None:
                proposed[k] = body[k]

        after_w = eval_atomic_rule(value, proposed)
        after = {"value": value, "weight": float(after_w), "fired": after_w != 0}

        # Affected symbols estimate — count how many symbols would change fire-state
        # on `snap` if we replaced this rule. Cheap upper bound: read the column for
        # all drv_ma rows and re-score, count flips.
        affected = None
        if col_src:
            try:
                tbl, col = col_src
                if tbl == "drv_ma":
                    rows = s.execute(text(
                        f'SELECT tos_symbol, "{col}" AS v FROM drv_ma WHERE as_of_date = :d'
                    ), {"d": snap}).mappings().all()
                else:
                    rows = s.execute(text(
                        f'SELECT tos_symbol, "{col}" AS v FROM {tbl} WHERE as_of_date = :d'
                    ), {"d": snap}).mappings().all()
                flips = 0
                for r in rows:
                    b = eval_atomic_rule(r["v"], dict(current))
                    a = eval_atomic_rule(r["v"], proposed)
                    if (b != 0) != (a != 0):
                        flips += 1
                affected = flips
            except Exception:
                affected = None

        note_parts = []
        for k in ("brkeout_from", "brkeout_to",
                  "wt_below", "wt_between", "wt_above", "scoring_mode"):
            if k in body and body[k] != current[k]:
                note_parts.append(f"{k}: {current[k]} → {body[k]}")
        note = "; ".join(note_parts) if note_parts else "no changes proposed"

        return {
            "rule_id": rule_id,
            "sample_symbol": sym,
            "as_of_date": snap.isoformat(),
            "before": before,
            "after": after,
            "affected_symbols_estimate": affected,
            "note": note,
        }


@router.delete("/api/rules/atomic/{rule_id}", response_model=dict)
def deprecate_atomic_rule(rule_id: str):
    """Soft-delete (deprecate) an atomic rule."""
    with session_scope() as s:
        result = s.execute(
            text("UPDATE ref_trig_atomic_rule SET deprecated_at = now() WHERE atomic_rule_id = :rid AND deprecated_at IS NULL"),
            {"rid": rule_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found or already deprecated")
        s.commit()
    return {"ok": True, "deprecated": rule_id}


@router.post("/api/rules/composite", response_model=dict, status_code=201)
def create_composite_rule(body: CompositeRuleCreateRequest):
    """Create a new composite rule.

    A composite is a set of (composite_rule_code, atomic_rule_id) mapping rows.
    POST creates the *first* set; if the code already has any mapping rows
    (including soft-deprecated), return 409 — use PUT /api/rules/composite/{id}
    to update an existing one and PUT /{id}/members to replace its member list.
    """
    if not body.atomic_rule_ids:
        raise HTTPException(status_code=400, detail="At least one atomic_rule_id required")
    with session_scope() as s:
        exists = s.execute(
            text("SELECT 1 FROM ref_trig_composite_mapping WHERE composite_rule_code = :code LIMIT 1"),
            {"code": body.rule_code}
        ).first()
        if exists:
            raise HTTPException(
                status_code=409,
                detail=f"Composite rule {body.rule_code} already exists — use PUT to update",
            )
        # Validate referenced atomic rules exist (and aren't deprecated)
        existing_atomics = {
            r[0] for r in s.execute(
                text("SELECT atomic_rule_id FROM ref_trig_atomic_rule "
                     "WHERE atomic_rule_id = ANY(:ids) AND deprecated_at IS NULL"),
                {"ids": list(body.atomic_rule_ids)}
            ).fetchall()
        }
        missing = [a for a in body.atomic_rule_ids if a not in existing_atomics]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown or deprecated atomic_rule_id(s): {missing}",
            )
        for atom_id in body.atomic_rule_ids:
            s.execute(text("""
                INSERT INTO ref_trig_composite_mapping
                  (composite_rule_code, atomic_rule_id, category, intent_text, precondition_expr)
                VALUES (:code, :atom, :cat, :intent, :pre)
            """), {
                "code": body.rule_code, "atom": atom_id,
                "cat": body.category, "intent": body.intent_text,
                "pre": body.precondition_expr,
            })
        s.commit()
    return {"ok": True, "rule_code": body.rule_code, "n_members": len(body.atomic_rule_ids)}


@router.put("/api/rules/composite/{rule_id}", response_model=dict)
def update_composite_rule(rule_id: str, body: CompositeRuleUpdateRequest):
    """Update category/intent/precondition on all mapping rows for a composite rule."""
    with session_scope() as s:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["rule_id"] = rule_id
        result = s.execute(
            text(f"UPDATE ref_trig_composite_mapping SET {set_clause} WHERE composite_rule_code = :rule_id AND deprecated_at IS NULL"),
            updates
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Composite rule {rule_id} not found or deprecated")
        s.commit()
    return {"ok": True, "updated": result.rowcount}


@router.put("/api/rules/composite/{rule_id}/active", response_model=dict)
def set_composite_active(rule_id: str, body: dict):
    """Enable or disable a composite rule. Body: {"active": true|false}"""
    active = bool(body.get("active", True))
    with session_scope() as s:
        result = s.execute(
            text("UPDATE ref_trig_composite_mapping SET active = :a WHERE composite_rule_code = :rid AND deprecated_at IS NULL"),
            {"a": active, "rid": rule_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Composite rule {rule_id} not found")
        s.commit()
    return {"ok": True, "rule_id": rule_id, "active": active}


@router.delete("/api/rules/composite/{rule_id}", response_model=dict)
def deprecate_composite_rule(rule_id: str):
    """Soft-delete (deprecate) all mapping rows for a composite rule."""
    with session_scope() as s:
        result = s.execute(
            text("UPDATE ref_trig_composite_mapping SET deprecated_at = now() WHERE composite_rule_code = :rid AND deprecated_at IS NULL"),
            {"rid": rule_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Composite rule {rule_id} not found or already deprecated")
        s.commit()
    return {"ok": True, "deprecated": rule_id}


# -----------------------------------------------------------------------------
# Composite editor — replace members + dry-run
# -----------------------------------------------------------------------------

@router.put("/api/rules/composite/{rule_id}/members", response_model=dict)
def replace_composite_members(rule_id: str, body: dict):
    """Replace the full member list for a composite (transactional).

    Composite members come in three kinds:
      - 'atomic'    — reference an existing atomic rule (default; legacy behavior)
      - 'data'      — inline scoring rule against a drv_cat column
      - 'composite' — nest another composite (parent ← child(score))

    Body shape:
      {
        "members": [
          # ATOMIC member:
          {"kind": "atomic", "atomic_rule_id": int,
           "weight_override": number|null},

          # DATA member (no shared atomic rule definition):
          {"kind": "data", "data_column": "drv_cat_atomic_input.bb_top",
           "brkeout_from": 0, "brkeout_to": 5,
           "wt_below": -1, "wt_between": 1, "wt_above": 2,
           "scoring_mode": "jump", "score_params": {}|null,
           "weight_override": number|null},

          # COMPOSITE member (nest another composite):
          {"kind": "composite", "nested_composite_code": "BM-Momentum-Up",
           "weight_override": number|null}
        ],
        "category": str|null, "intent_text": str|null, "precondition_expr": str|null
      }

    The migration db/baseline.sql must be applied for the
    'data' and 'composite' kinds to persist.  If those columns don't exist yet,
    the endpoint falls back to writing only 'atomic' members and returns a
    warning in the response.
    """
    members = body.get("members") or []
    if not isinstance(members, list):
        raise HTTPException(status_code=400, detail="members must be a list")

    # Validate each member by kind
    seen_atomic = set(); seen_nested = set(); seen_data = set()
    for i, m in enumerate(members):
        kind = (m.get("kind") or "atomic").lower()
        if kind not in ("atomic", "data", "composite"):
            raise HTTPException(status_code=400,
                detail=f"member[{i}] kind must be atomic | data | composite")
        if kind == "atomic":
            atom_id = m.get("atomic_rule_id")
            if atom_id is None:
                raise HTTPException(status_code=400, detail=f"member[{i}] kind=atomic needs atomic_rule_id")
            if atom_id in seen_atomic:
                raise HTTPException(status_code=400, detail=f"duplicate atomic_rule_id {atom_id}")
            seen_atomic.add(atom_id)
        elif kind == "data":
            col = m.get("data_column")
            if not col:
                raise HTTPException(status_code=400, detail=f"member[{i}] kind=data needs data_column")
            if col in seen_data:
                raise HTTPException(status_code=400, detail=f"duplicate data_column {col}")
            seen_data.add(col)
        elif kind == "composite":
            nest = m.get("nested_composite_code")
            if not nest:
                raise HTTPException(status_code=400, detail=f"member[{i}] kind=composite needs nested_composite_code")
            if nest == rule_id:
                raise HTTPException(status_code=400, detail="composite cannot reference itself")
            if nest in seen_nested:
                raise HTTPException(status_code=400, detail=f"duplicate nested_composite_code {nest}")
            seen_nested.add(nest)

    category = body.get("category")
    intent   = body.get("intent_text")
    pre      = body.get("precondition_expr")
    evidence_cutoff = body.get("evidence_cutoff")  # composite-level; None = watch never blocks

    warnings = []

    with session_scope() as s:
        # Detect whether the migration is applied
        mig_applied = bool(s.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='ref_trig_composite_mapping' AND column_name='member_kind'
        """)).first())
        # Gate/WATCH role columns (added 2026-06-03) — detected separately so a
        # partial migration can't break inserts.
        has_role_cols = bool(s.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='ref_trig_composite_mapping' AND column_name='member_role'
        """)).first())

        # Hard-delete current mappings; we want a clean replace
        s.execute(text(
            "DELETE FROM ref_trig_composite_mapping WHERE composite_rule_code = :rid"
        ), {"rid": rule_id})

        for i, m in enumerate(members):
            kind = (m.get("kind") or "atomic").lower()
            if not mig_applied and kind != "atomic":
                warnings.append(
                    f"member[{i}] kind={kind} skipped — apply db/baseline.sql"
                )
                continue
            if mig_applied:
                op = m.get("condition_operator") or None
                if op and op not in (">=", "<=", ">", "<", "="):
                    op = None
                role = (m.get("member_role") or "gate").lower()
                if role not in ("gate", "watch"):
                    role = "gate"
                role_cols = ", member_role, evidence_cutoff" if has_role_cols else ""
                role_vals = ", :mrole, :ecut" if has_role_cols else ""
                s.execute(text(f"""
                    INSERT INTO ref_trig_composite_mapping
                      (composite_rule_code, member_kind,
                       atomic_rule_id, weight_override,
                       data_column, data_brkeout_from, data_brkeout_to,
                       data_wt_below, data_wt_between, data_wt_above,
                       data_scoring_mode, data_score_params,
                       nested_composite_code, member_multiplier,
                       category, intent_text, precondition_expr,
                       condition_operator{role_cols})
                    VALUES
                      (:rid, :kind,
                       :atom, :wo,
                       :dc, :dlo, :dhi,
                       :dwb, :dwbt, :dwa,
                       :dmode, CAST(:dparams AS JSONB),
                       :nest, :mult,
                       :cat, :intent, :pre,
                       :cop{role_vals})
                """), {
                    "rid":    rule_id,
                    "kind":   kind,
                    "atom":   m.get("atomic_rule_id") if kind == "atomic" else None,
                    "wo":     m.get("weight_override"),
                    "dc":     m.get("data_column") if kind == "data" else None,
                    "dlo":    m.get("brkeout_from") if kind == "data" else None,
                    "dhi":    m.get("brkeout_to")   if kind == "data" else None,
                    "dwb":    m.get("wt_below")     if kind == "data" else None,
                    "dwbt":   m.get("wt_between")   if kind == "data" else None,
                    "dwa":    m.get("wt_above")     if kind == "data" else None,
                    "dmode":  (m.get("scoring_mode") or "jump") if kind == "data" else None,
                    "dparams": json.dumps(m.get("score_params")) if (kind == "data" and m.get("score_params") is not None) else None,
                    "nest":   m.get("nested_composite_code") if kind == "composite" else None,
                    "mult":   m.get("member_multiplier"),
                    "cat":    category,
                    "intent": intent,
                    "pre":    pre,
                    "cop":    op,
                    "mrole":  role,
                    "ecut":   evidence_cutoff,
                })
            else:
                # Pre-migration legacy schema — atomic only
                s.execute(text("""
                    INSERT INTO ref_trig_composite_mapping
                      (composite_rule_code, atomic_rule_id, weight_override,
                       category, intent_text, precondition_expr)
                    VALUES (:rid, :atom, :wo, :cat, :intent, :pre)
                """), {
                    "rid":    rule_id,
                    "atom":   m["atomic_rule_id"],
                    "wo":     m.get("weight_override"),
                    "cat":    category,
                    "intent": intent,
                    "pre":    pre,
                })
        s.commit()
    return {
        "ok": True,
        "rule_code": rule_id,
        "members_written": len(members) - len(warnings),
        "schema_extended": mig_applied,
        "warnings": warnings,
    }


@router.post("/api/rules/composite/{rule_id}/dryrun", response_model=dict)
def composite_dryrun(rule_id: str, body: dict):
    """Project the composite's score for a sample symbol BEFORE vs AFTER applying
    proposed member edits — without persisting anything.

    Body shape:
      {
        "members": [{"atomic_rule_id": int, "weight_override": number|null}, ...],
        "precondition_expr": str|null,
        "sample_symbol": "AAPL",     # optional, defaults to AAPL
        "as_of_date":    "YYYY-MM-DD" # optional, defaults to latest
      }

    Response shape:
      {
        "sample_symbol": "AAPL",
        "as_of_date":    "2026-05-07",
        "before": {"score": <num|null>, "fired": <bool>, "n_atomic_hit": <int>},
        "after":  {"score": <num|null>, "fired": <bool>, "n_atomic_hit": <int>,
                   "precondition_passed": <bool>},
        "affected_symbols_estimate": <int|null>,
        "note": <str>
      }
    """
    sym = (body.get("sample_symbol") or "AAPL").upper().strip()
    as_of = body.get("as_of_date")
    proposed_members = body.get("members") or []
    proposed_pre     = body.get("precondition_expr") or None

    # Lazy import to avoid heavyweight at module import time
    from etl.derive import _eval_precondition, eval_atomic_rule

    with session_scope() as s:
        if as_of:
            try:
                snap = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="as_of_date must be YYYY-MM-DD")
        else:
            row = s.execute(text(
                "SELECT MAX(as_of_date) AS d FROM drv_stks"
            )).mappings().first()
            snap = row["d"] if row and row["d"] else date.today()

        # ---- BEFORE: read snapshot from drv_stks for the existing composite
        before = {"score": None, "fired": False, "n_atomic_hit": 0}
        stks_row = s.execute(text("""
            SELECT triggered_composite_ids, triggered_atomic_ids
            FROM drv_stks
            WHERE as_of_date = :d AND symbol = :sym
            LIMIT 1
        """), {"d": snap, "sym": sym}).mappings().first()
        if stks_row and stks_row["triggered_composite_ids"]:
            for c in stks_row["triggered_composite_ids"]:
                if c.get("rule_id") == rule_id:
                    before["score"] = float(c.get("score") or 0)
                    before["fired"] = before["score"] != 0
                    break

        # Existing member set, for "what changed" note
        existing = s.execute(text("""
            SELECT atomic_rule_id, weight_override
            FROM ref_trig_composite_mapping
            WHERE composite_rule_code = :rid AND deprecated_at IS NULL
            ORDER BY atomic_rule_id
        """), {"rid": rule_id}).mappings().all()
        existing_ids = {r["atomic_rule_id"] for r in existing}

        # ---- AFTER: re-evaluate the proposed composite for the sample symbol
        # 1. fetch drv_ma + drv_cat_atomic_input for the sample symbol
        try:
            ma_dict = dict(s.execute(text(
                "SELECT * FROM drv_ma WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym}).mappings().first() or {})
        except Exception:
            ma_dict = {}
        try:
            ai_dict = dict(s.execute(text(
                "SELECT * FROM drv_cat_atomic_input WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
            ), {"d": snap, "sym": sym}).mappings().first() or {})
        except Exception:
            ai_dict = {}

        # 2. Precondition check on the row
        pre_passed = True
        if proposed_pre:
            pre_passed = bool(_eval_precondition(proposed_pre, ma_dict))

        if not pre_passed:
            after = {"score": None, "fired": False, "n_atomic_hit": 0,
                     "precondition_passed": False,
                     "by_kind": {"atomic": 0, "data": 0, "composite": 0}}
        else:
            # 3. Score each proposed member by its kind
            #    'atomic'    — read column, eval rule
            #    'data'      — inline rule defined right on the member
            #    'composite' — pull score from drv_stks.triggered_composite_ids
            atomic_members  = [m for m in proposed_members if (m.get("kind") or "atomic") == "atomic"]
            data_members    = [m for m in proposed_members if m.get("kind") == "data"]
            nested_members  = [m for m in proposed_members if m.get("kind") == "composite"]

            atom_ids = [m["atomic_rule_id"] for m in atomic_members
                        if m.get("atomic_rule_id") is not None]
            atomics = []
            if atom_ids:
                atomics = s.execute(text("""
                    SELECT atomic_rule_id, rule_name, ma_column_name,
                           brkeout_from, brkeout_to,
                           wt_below, wt_between, wt_above,
                           scoring_mode, score_params
                    FROM ref_trig_atomic_rule
                    WHERE atomic_rule_id = ANY(:ids) AND deprecated_at IS NULL
                """), {"ids": atom_ids}).mappings().all()

            # Resolve column for each atomic via ref_ma_columns (same algo as derive)
            rule_names = [a["rule_name"] for a in atomics if a.get("rule_name")]
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
            # Fallback to ma_column_name parsing
            for a in atomics:
                if a["rule_name"] not in col_lookup and a["ma_column_name"] and "." in a["ma_column_name"]:
                    tbl, _, col = a["ma_column_name"].partition(".")
                    col_lookup[a["rule_name"]] = (tbl, col)

            override_map = {m["atomic_rule_id"]: m.get("weight_override")
                            for m in atomic_members}

            score = 0.0
            n_hit = 0
            by_kind = {"atomic": 0.0, "data": 0.0, "composite": 0.0}

            # ---- atomic members ----
            for a in atomics:
                src = col_lookup.get(a["rule_name"])
                value = None
                if src:
                    tbl, col = src
                    if tbl == "drv_cat_atomic_input":
                        value = ai_dict.get(col)
                    else:
                        value = ma_dict.get(col)
                w = eval_atomic_rule(value, dict(a))
                ovr = override_map.get(a["atomic_rule_id"])
                if ovr is not None and w != 0:
                    w = float(ovr)
                if w != 0:
                    n_hit += 1
                score += w
                by_kind["atomic"] += w

            # ---- data members (inline scoring against a drv_cat column) ----
            for dm in data_members:
                col_path = dm.get("data_column") or ""
                # Resolve "table.col" or bare col → drv_cat_atomic_input
                if "." in col_path:
                    tbl, _, col = col_path.partition(".")
                else:
                    tbl, col = "drv_cat_atomic_input", col_path
                if tbl == "drv_ma":
                    value = ma_dict.get(col)
                elif tbl == "drv_cat_atomic_input":
                    value = ai_dict.get(col)
                else:
                    # Read on demand for other drv_cat_* tables
                    try:
                        row = s.execute(text(
                            f'SELECT "{col}" AS v FROM {tbl} '
                            "WHERE as_of_date=:d AND tos_symbol=:sym LIMIT 1"
                        ), {"d": snap, "sym": sym}).mappings().first()
                        value = row["v"] if row else None
                    except Exception:
                        value = None
                inline_rule = {
                    "brkeout_from":  dm.get("brkeout_from"),
                    "brkeout_to":    dm.get("brkeout_to"),
                    "wt_below":      dm.get("wt_below"),
                    "wt_between":    dm.get("wt_between"),
                    "wt_above":      dm.get("wt_above"),
                    "scoring_mode":  dm.get("scoring_mode") or "jump",
                    "score_params":  dm.get("score_params"),
                }
                w = eval_atomic_rule(value, inline_rule)
                ovr = dm.get("weight_override")
                if ovr is not None and w != 0:
                    w = float(ovr)
                if w != 0:
                    n_hit += 1
                score += w
                by_kind["data"] += w

            # ---- composite members (nested) ----
            #   pull each child's score from drv_stks.triggered_composite_ids
            #   for this (date, symbol). Single-level lookup — full recursion
            #   with cycle detection happens in the derive layer (follow-up).
            child_scores = {}
            if stks_row and stks_row["triggered_composite_ids"]:
                for c in stks_row["triggered_composite_ids"]:
                    cid = c.get("rule_id")
                    if cid:
                        child_scores[cid] = float(c.get("score") or 0)
            for nm in nested_members:
                code = nm.get("nested_composite_code")
                child_score = child_scores.get(code, 0.0)
                mult = nm.get("weight_override")
                contrib = float(mult) * child_score if mult is not None else child_score
                if contrib != 0:
                    n_hit += 1
                score += contrib
                by_kind["composite"] += contrib

            after = {"score": float(score), "fired": score != 0,
                     "n_atomic_hit": n_hit, "precondition_passed": True,
                     "by_kind": {k: float(v) for k, v in by_kind.items()}}

        # Diff note vs existing
        existing_atom_ids = {r["atomic_rule_id"] for r in existing if r["atomic_rule_id"] is not None}
        proposed_atom_ids = {m["atomic_rule_id"] for m in proposed_members
                             if m.get("kind", "atomic") == "atomic" and m.get("atomic_rule_id") is not None}
        added   = sorted(proposed_atom_ids - existing_atom_ids)
        removed = sorted(existing_atom_ids - proposed_atom_ids)
        n_data = sum(1 for m in proposed_members if m.get("kind") == "data")
        n_nest = sum(1 for m in proposed_members if m.get("kind") == "composite")
        note_parts = []
        if added:   note_parts.append(f"+{len(added)} atomic")
        if removed: note_parts.append(f"-{len(removed)} atomic")
        if n_data:  note_parts.append(f"{n_data} data members")
        if n_nest:  note_parts.append(f"{n_nest} nested composites")
        if proposed_pre and proposed_pre.strip():
            note_parts.append("precondition set")
        note = ", ".join(note_parts) if note_parts else "no membership change"

        # Affected-symbols estimate from drv_trig
        try:
            affected = s.execute(text("""
                SELECT COUNT(DISTINCT tos_symbol) AS n FROM drv_trig
                WHERE composite_rule_code = :rid AND as_of_date = :d
            """), {"rid": rule_id, "d": snap}).scalar()
        except Exception:
            affected = None

        return {
            "rule_code": rule_id,
            "sample_symbol": sym,
            "as_of_date": snap.isoformat(),
            "before": before,
            "after":  after,
            "affected_symbols_estimate": int(affected) if affected is not None else None,
            "added_atomic_ids":   added,
            "removed_atomic_ids": removed,
            "note": note,
        }


# =============================================================================
# Rule Groups (hierarchical composition of composites and nested groups)
# =============================================================================

@router.get("/api/rules/groups", response_model=list[dict])
def get_rule_groups():
    """List all rule groups with their members."""
    try:
        from etl.rule_groups import get_all_rule_groups
        with session_scope() as s:
            groups = get_all_rule_groups(s)
        return groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/rules/groups/{group_code}", response_model=dict)
def get_rule_group_detail(group_code: str):
    """Return one rule group with its full member list."""
    try:
        from etl.rule_groups import get_rule_group
        with session_scope() as s:
            grp = get_rule_group(s, group_code)
        if not grp:
            raise HTTPException(status_code=404, detail=f"Rule group {group_code!r} not found")
        return grp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Rule-group create / update / delete / test
# -----------------------------------------------------------------------------

@router.post("/api/rules/groups", response_model=dict, status_code=201)
def create_rule_group(payload: dict):
    """Create a new rule group with members."""
    code = (payload.get("rule_group_code") or "").strip()
    if not code:
        raise HTTPException(400, "rule_group_code required")
    group_type = payload.get("group_type") or "action"
    if group_type not in ("action", "logical"):
        raise HTTPException(400, "group_type must be 'action' or 'logical'")
    action_label = payload.get("action_label") or None
    if group_type == "action" and not action_label:
        raise HTTPException(400, "action_label required when group_type='action'")
    if group_type == "logical" and action_label:
        raise HTTPException(400, "action_label must be null when group_type='logical'")
    members = payload.get("members") or []
    if not members:
        raise HTTPException(400, "at least one member required")

    with session_scope() as s:
        exists = s.execute(text(
            "SELECT 1 FROM ref_trig_rule_group WHERE rule_group_code = :c"
        ), {"c": code}).first()
        if exists:
            raise HTTPException(409, f"group {code!r} already exists")

        s.execute(text("""
            INSERT INTO ref_trig_rule_group
              (rule_group_code, group_type, action_label, priority, category, intent_text)
            VALUES (:code, :gt, :al, :pr, :cat, :it)
        """), {
            "code": code, "gt": group_type, "al": action_label,
            "pr": payload.get("priority"), "cat": payload.get("category"),
            "it": payload.get("intent_text"),
        })
        for i, m in enumerate(members, start=1):
            s.execute(text("""
                INSERT INTO ref_trig_group_member
                  (rule_group_code, member_code, member_type, logic_operator, sequence)
                VALUES (:c, :mc, :mt, :op, :seq)
            """), {
                "c": code, "mc": m["member_code"],
                "mt": m.get("member_type", "composite"),
                "op": m.get("logic_operator", "AND"),
                "seq": i,
            })
        s.commit()
    return {"ok": True, "rule_group_code": code, "n_members": len(members)}


@router.put("/api/rules/groups/{group_code}", response_model=dict)
def update_rule_group(group_code: str, payload: dict):
    """Update a rule group's metadata + replace its members."""
    with session_scope() as s:
        exists = s.execute(text(
            "SELECT 1 FROM ref_trig_rule_group WHERE rule_group_code = :c AND deprecated_at IS NULL"
        ), {"c": group_code}).first()
        if not exists:
            raise HTTPException(404, f"group {group_code!r} not found")

        group_type = payload.get("group_type") or "action"
        action_label = payload.get("action_label") or None
        if group_type == "action" and not action_label:
            raise HTTPException(400, "action_label required when group_type='action'")
        if group_type == "logical" and action_label:
            raise HTTPException(400, "action_label must be null when group_type='logical'")

        s.execute(text("""
            UPDATE ref_trig_rule_group SET
              group_type = :gt, action_label = :al, priority = :pr,
              category = :cat, intent_text = :it
            WHERE rule_group_code = :c
        """), {
            "c": group_code, "gt": group_type, "al": action_label,
            "pr": payload.get("priority"), "cat": payload.get("category"),
            "it": payload.get("intent_text"),
        })
        s.execute(text(
            "DELETE FROM ref_trig_group_member WHERE rule_group_code = :c"
        ), {"c": group_code})
        members = payload.get("members") or []
        for i, m in enumerate(members, start=1):
            s.execute(text("""
                INSERT INTO ref_trig_group_member
                  (rule_group_code, member_code, member_type, logic_operator, sequence)
                VALUES (:c, :mc, :mt, :op, :seq)
            """), {
                "c": group_code, "mc": m["member_code"],
                "mt": m.get("member_type", "composite"),
                "op": m.get("logic_operator", "AND"),
                "seq": i,
            })
        s.commit()
    return {"ok": True, "rule_group_code": group_code, "n_members": len(members)}


@router.delete("/api/rules/groups/{group_code}", response_model=dict)
def deprecate_rule_group(group_code: str):
    """Soft-delete (deprecate) a rule group. Members stay for history."""
    with session_scope() as s:
        result = s.execute(text("""
            UPDATE ref_trig_rule_group
            SET deprecated_at = now()
            WHERE rule_group_code = :c AND deprecated_at IS NULL
            RETURNING rule_group_code
        """), {"c": group_code}).first()
        if not result:
            raise HTTPException(404, f"group {group_code!r} not found or already deprecated")
        s.commit()
    return {"ok": True, "rule_group_code": group_code, "deprecated": True}


@router.get("/api/rules/groups/{group_code}/test", response_model=dict)
def test_rule_group(group_code: str, date: Optional[str] = Query(None)):
    """
    Evaluate a rule group against the snapshot for :date.
    """
    d = _resolve_date(date)
    with session_scope() as s:
        grp = s.execute(text("""
            SELECT rule_group_code, group_type, action_label, priority
            FROM ref_trig_rule_group
            WHERE rule_group_code = :c AND deprecated_at IS NULL
        """), {"c": group_code}).mappings().first()
        if not grp:
            raise HTTPException(404, f"group {group_code!r} not found")

        members = s.execute(text("""
            SELECT member_code, member_type, logic_operator, sequence
            FROM ref_trig_group_member
            WHERE rule_group_code = :c
            ORDER BY sequence
        """), {"c": group_code}).mappings().all()
        if not members:
            return {"triggered": False, "action": grp["action_label"],
                    "priority": grp["priority"], "sample_triggered_count": 0,
                    "sample_symbols": [], "_note": "group has no members"}

        rows = s.execute(text("""
            SELECT tos_symbol, triggered_composite_ids
            FROM drv_stks
            WHERE as_of_date = :d
        """), {"d": d}).mappings().all()

        triggered_symbols = []
        for r in rows:
            fired_codes = set()
            for t in (r["triggered_composite_ids"] or []):
                code = t.get("rule_id") if isinstance(t, dict) else None
                if code:
                    fired_codes.add(code)
            result = None
            for m in members:
                hit = m["member_code"] in fired_codes
                op = m["logic_operator"]
                if result is None:
                    result = hit
                elif op == "AND":
                    result = result and hit
                else:
                    result = result or hit
            if result:
                triggered_symbols.append(r["tos_symbol"])

        return {
            "triggered": len(triggered_symbols) > 0,
            "action": grp["action_label"],
            "priority": grp["priority"],
            "sample_triggered_count": len(triggered_symbols),
            "sample_symbols": triggered_symbols[:50],
        }


# =============================================================================
# Parameter sets (Phase 3/4 — docs/rule_engine_redesign.md)
# Manage the tunable-parameter overlays produced by etl/ml_tune_thresholds.py.
# =============================================================================
@router.get("/api/rules/param-sets", response_model=list[dict])
def list_param_sets():
    """List all parameter sets with value/target counts. Empty if unused."""
    with session_scope() as s:
        try:
            rows = s.execute(text("""
                SELECT ps.param_set_id, ps.label, ps.provenance, ps.is_active,
                       ps.notes, ps.created_at,
                       COUNT(pv.param_set_id)        AS n_values,
                       COUNT(DISTINCT pv.target_id)  AS n_targets
                FROM ref_trig_param_set ps
                LEFT JOIN ref_trig_param_value pv ON pv.param_set_id = ps.param_set_id
                GROUP BY ps.param_set_id
                ORDER BY ps.is_active DESC, ps.created_at DESC
            """)).mappings().all()
        except Exception:
            return []   # tables not migrated yet
        return [dict(r) for r in rows]


@router.get("/api/rules/param-sets/{set_id}", response_model=dict)
def get_param_set(set_id: int):
    """Header + all values for one parameter set (atomic values carry rule_name)."""
    with session_scope() as s:
        hdr = s.execute(text(
            "SELECT * FROM ref_trig_param_set WHERE param_set_id = :i"
        ), {"i": set_id}).mappings().first()
        if not hdr:
            raise HTTPException(status_code=404, detail=f"param set {set_id} not found")
        vals = s.execute(text("""
            SELECT pv.target_kind, pv.target_id, pv.param_name, pv.param_value,
                   a.rule_name
            FROM ref_trig_param_value pv
            LEFT JOIN ref_trig_atomic_rule a
              ON pv.target_kind = 'atomic' AND a.atomic_rule_id::text = pv.target_id
            WHERE pv.param_set_id = :i
            ORDER BY pv.target_id, pv.param_name
        """), {"i": set_id}).mappings().all()
        return {"set": dict(hdr), "values": [dict(v) for v in vals]}


@router.post("/api/rules/param-sets/{set_id}/activate", response_model=dict)
def activate_param_set(set_id: int):
    """Make this the active set (deactivates any other). Re-derive to apply."""
    with session_scope() as s:
        if not s.execute(text("SELECT 1 FROM ref_trig_param_set WHERE param_set_id = :i"),
                         {"i": set_id}).first():
            raise HTTPException(status_code=404, detail=f"param set {set_id} not found")
        s.execute(text("UPDATE ref_trig_param_set SET is_active = FALSE WHERE is_active = TRUE"))
        s.execute(text("UPDATE ref_trig_param_set SET is_active = TRUE WHERE param_set_id = :i"),
                  {"i": set_id})
        s.commit()
    return {"ok": True, "active": set_id,
            "note": "Run `python -m etl.rebuild_rules` to apply to derived tables."}


@router.post("/api/rules/param-sets/{set_id}/deactivate", response_model=dict)
def deactivate_param_set(set_id: int):
    """Deactivate this set; engine reverts to base ref_trig_atomic_rule values."""
    with session_scope() as s:
        s.execute(text("UPDATE ref_trig_param_set SET is_active = FALSE WHERE param_set_id = :i"),
                  {"i": set_id})
        s.commit()
    return {"ok": True, "note": "Engine now uses base values. Run rebuild_rules to apply."}


@router.delete("/api/rules/param-sets/{set_id}", response_model=dict)
def delete_param_set(set_id: int):
    """Delete a parameter set and its values (cascade)."""
    with session_scope() as s:
        s.execute(text("DELETE FROM ref_trig_param_set WHERE param_set_id = :i"), {"i": set_id})
        s.commit()
    return {"ok": True, "deleted": set_id}


# =============================================================================
# BASE-* sub-composites — list for the composite editor's base picker (Phase 2)
# =============================================================================
@router.get("/api/rules/base-composites", response_model=list[dict])
def list_base_composites():
    """BASE-* composites with a member summary, for the editor's base picker."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT m.composite_rule_code AS code, m.intent_text, m.category,
                   m.member_role, m.data_brkeout_from, m.condition_operator,
                   a.rule_name
            FROM ref_trig_composite_mapping m
            LEFT JOIN ref_trig_atomic_rule a ON a.atomic_rule_id = m.atomic_rule_id
            WHERE m.composite_rule_code LIKE 'BASE-%' AND m.deprecated_at IS NULL
            ORDER BY m.composite_rule_code, m.atomic_rule_id
        """)).mappings().all()
    out: dict = {}
    for r in rows:
        c = out.setdefault(r["code"], {"code": r["code"], "intent_text": r["intent_text"],
                                       "category": r["category"], "members": []})
        if r["rule_name"]:
            c["members"].append({"rule_name": r["rule_name"], "role": r["member_role"],
                                 "threshold": r["data_brkeout_from"],
                                 "operator": r["condition_operator"]})
    return list(out.values())


# =============================================================================
# Clone a composite to a new code (authoring convenience)
# =============================================================================
@router.post("/api/rules/composite/{rule_id}/clone", response_model=dict)
def clone_composite(rule_id: str, body: dict):
    """Duplicate every member row of a composite under a new code."""
    new_code = (body.get("new_code") or "").strip()
    if not new_code:
        raise HTTPException(status_code=400, detail="new_code required")
    if new_code == rule_id:
        raise HTTPException(status_code=400, detail="new_code must differ from source")
    with session_scope() as s:
        src = s.execute(text("""
            SELECT * FROM ref_trig_composite_mapping
            WHERE composite_rule_code = :c AND deprecated_at IS NULL
        """), {"c": rule_id}).mappings().all()
        if not src:
            raise HTTPException(status_code=404, detail=f"composite {rule_id} not found")
        if s.execute(text("""
            SELECT 1 FROM ref_trig_composite_mapping
            WHERE composite_rule_code = :c AND deprecated_at IS NULL LIMIT 1
        """), {"c": new_code}).first():
            raise HTTPException(status_code=409, detail=f"composite {new_code} already exists")
        for m in src:
            s.execute(text("""
                INSERT INTO ref_trig_composite_mapping
                  (composite_rule_code, member_kind, member_role, atomic_rule_id,
                   nested_composite_code, weight_override, data_column,
                   data_brkeout_from, data_brkeout_to, data_wt_below, data_wt_between,
                   data_wt_above, data_scoring_mode, data_score_params, member_multiplier,
                   condition_operator, category, intent_text, precondition_expr,
                   evidence_cutoff, active)
                VALUES
                  (:c, :kind, :role, :aid, :nest, :wo, :dc, :dlo, :dhi, :dwb, :dwbt,
                   :dwa, :dmode, CAST(:dparams AS JSONB), :mult, :cop, :cat, :intent,
                   :pre, :ecut, :active)
            """), {
                "c": new_code, "kind": m["member_kind"], "role": m.get("member_role", "gate"),
                "aid": m["atomic_rule_id"], "nest": m["nested_composite_code"],
                "wo": m["weight_override"], "dc": m["data_column"],
                "dlo": m["data_brkeout_from"], "dhi": m["data_brkeout_to"],
                "dwb": m["data_wt_below"], "dwbt": m["data_wt_between"], "dwa": m["data_wt_above"],
                "dmode": m["data_scoring_mode"],
                "dparams": json.dumps(m["data_score_params"]) if m["data_score_params"] is not None else None,
                "mult": m["member_multiplier"], "cop": m["condition_operator"],
                "cat": m["category"], "intent": m["intent_text"], "pre": m["precondition_expr"],
                "ecut": m.get("evidence_cutoff"), "active": m.get("active", True),
            })
        s.commit()
    return {"ok": True, "new_code": new_code, "members": len(src)}
