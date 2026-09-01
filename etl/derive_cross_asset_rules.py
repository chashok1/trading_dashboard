"""Cross-asset rules: multi-symbol RR-position conditions the ordinary
atomic-rule engine can't express -- atomic rules only ever evaluate a row's
OWN fields (see docs/rules_logic.md), so a rule like "Bonds and US dollar at
TRR and Gold is at LRR, then buy gold" (needs 3 OTHER symbols' RR reads to
fire a signal on a 4th) has nowhere to live there. 2026-09-01, user request.

Rules + their legs live in ref_cross_asset_rule(_leg) -- editable via /ref
like any other tunable ref table, designed to hold more rules than just the
one seeded so far. A rule fires when EVERY one of its CHECKS passes -- a
"check" is either one standalone leg (leg_group IS NULL) or a weighted
blend of every leg sharing the same leg_group (2026-09-01, user request --
"may be use 10y more weighted?" -- e.g. 10Y+30Y Treasury yield blended
70/30 so a strong 10Y can carry a slightly-lagging 30Y over the line,
instead of requiring both independently). Either way the check's value --
a single leg's own rr_pos(), or a group's weighted average of its
members' rr_pos() -- is api._helpers.rr_pos()'s [0, 1] scale, the same
formula ref_macro_area's own HOT/COLD read already uses (see
macro_area_hot_pct/macro_area_cold_pct in ref_settings), compared against
comparison ('>=' or '<=') + rr_threshold_pct. Grouped legs must share the
same comparison/rr_threshold_pct (the group's one shared condition).

Wired into derive_all() (etl/derive.py) right before the Actionable Stocks
pipeline -- needs only drv_quote + drv_rr (already built earlier in the
cascade), and its output (drv_cross_asset_signal) is read by
derive_actionable.py right where that function builds each symbol's
candidate list, so a fired rule can inject a synthetic action the same way
a fired rule GROUP already does (see derive_actionable.py's
group_candidates).

Idempotent: DELETE FROM drv_cross_asset_signal WHERE as_of_date=D, then
INSERT one row per active rule (fired or not -- the dashboard panel wants to
show "how close" a not-yet-fired rule is, not just the fired ones)."""
import json
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from api._helpers import rr_pos

log = logging.getLogger(__name__)


def _leg_rr_pos(symbol: str, rr_map: dict, q_map: dict):
    """RR position (0..1, None if data's missing) for one leg symbol,
    reusing the shared rr_pos() formula -- same scale ref_macro_area's own
    HOT/COLD read and the Actionable RR column's % badge both use."""
    rr = rr_map.get(symbol)
    last = q_map.get(symbol)
    if not rr or last is None:
        return None
    lrr = rr.get("lrr")
    trr = rr.get("trr")
    if lrr is None or trr is None:
        return None
    return rr_pos(float(last), float(lrr), float(trr))


def _derive_cross_asset_rules_impl(session: Session, as_of_date: date) -> int:
    rules = session.execute(text("""
        SELECT rule_code, description, target_symbol, target_action
        FROM ref_cross_asset_rule
        WHERE is_active = TRUE
        ORDER BY rule_code
    """)).mappings().all()

    session.execute(text(
        "DELETE FROM drv_cross_asset_signal WHERE as_of_date = :d"
    ), {"d": as_of_date})

    if not rules:
        session.commit()
        return 0

    legs_by_rule: dict = {}
    for leg in session.execute(text("""
        SELECT rule_code, leg_symbol, comparison, rr_threshold_pct, weight, leg_group
        FROM ref_cross_asset_rule_leg
        ORDER BY rule_code, sort_order
    """)).mappings().all():
        legs_by_rule.setdefault(leg["rule_code"], []).append(dict(leg))

    # Every leg symbol across every rule, fetched in two queries (not one
    # per leg) -- cheap even as more rules get added.
    all_leg_symbols = {leg["leg_symbol"] for legs in legs_by_rule.values() for leg in legs}
    if all_leg_symbols:
        rr_rows = session.execute(text("""
            SELECT tos_symbol, lrr, trr FROM drv_rr
            WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
        """), {"d": as_of_date, "syms": list(all_leg_symbols)}).mappings().all()
        rr_map = {r["tos_symbol"]: dict(r) for r in rr_rows}
        q_rows = session.execute(text("""
            SELECT tos_symbol, last_price FROM drv_quote
            WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
        """), {"d": as_of_date, "syms": list(all_leg_symbols)}).mappings().all()
        q_map = {r["tos_symbol"]: r["last_price"] for r in q_rows}
    else:
        rr_map, q_map = {}, {}

    out = []
    for rule in rules:
        code = rule["rule_code"]
        legs = legs_by_rule.get(code, [])

        # Group legs into "checks": standalone (leg_group IS NULL, one leg
        # each) or blended (every leg sharing a real leg_group value,
        # combined via weighted average). dict preserves insertion order
        # (sort_order, already ordered by the query above) so checks come
        # out in the same order legs were defined.
        checks: dict = {}
        for i, leg in enumerate(legs):
            key = leg["leg_group"] or f"__solo_{i}"
            checks.setdefault(key, []).append(leg)

        detail = []
        all_pass = bool(checks)
        for members in checks.values():
            comparison = members[0]["comparison"]
            thr_pct = float(members[0]["rr_threshold_pct"])
            thr_frac = thr_pct / 100.0

            member_detail = []
            weighted_sum, weight_total = 0.0, 0.0
            any_missing = False
            for leg in members:
                pos = _leg_rr_pos(leg["leg_symbol"], rr_map, q_map)
                w = float(leg["weight"])
                member_detail.append({
                    "symbol": leg["leg_symbol"],
                    "weight": w,
                    "rr_pct": round(pos * 100, 1) if pos is not None else None,
                })
                if pos is None:
                    any_missing = True
                else:
                    weighted_sum += w * pos
                    weight_total += w

            blended_pos = (weighted_sum / weight_total) if (weight_total and not any_missing) else None
            if blended_pos is None:
                passed = False
            elif comparison == ">=":
                passed = blended_pos >= thr_frac
            else:
                passed = blended_pos <= thr_frac
            if not passed:
                all_pass = False

            label = " + ".join(m["leg_symbol"] for m in members) if len(members) > 1 else members[0]["leg_symbol"]
            detail.append({
                "symbol": label,
                "comparison": comparison,
                "threshold_pct": thr_pct,
                "rr_pct": round(blended_pos * 100, 1) if blended_pos is not None else None,
                "passed": passed,
                "members": member_detail if len(members) > 1 else None,
            })
        out.append({
            "as_of_date":    as_of_date,
            "rule_code":     code,
            "fired":         all_pass,
            "target_symbol": rule["target_symbol"],
            "target_action": rule["target_action"],
            "description":   rule["description"],
            "detail":        json.dumps(detail),
        })

    session.execute(text("""
        INSERT INTO drv_cross_asset_signal
          (as_of_date, rule_code, fired, target_symbol, target_action, description, detail)
        VALUES
          (:as_of_date, :rule_code, :fired, :target_symbol, :target_action, :description, CAST(:detail AS JSONB))
    """), out)
    session.commit()
    log.info("derive_cross_asset_rules: %d rule(s) evaluated for %s (%d fired)",
              len(out), as_of_date, sum(1 for r in out if r["fired"]))
    return len(out)


def derive_cross_asset_rules(session: Session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all()'s call-site signature (session, as_of_date, parent_run_id)
    -- parent_run_id unused, this derive is cheap/simple enough not to need
    its own meta_derived_run tracking beyond what _safe() already logs."""
    return _derive_cross_asset_rules_impl(session, as_of_date)
