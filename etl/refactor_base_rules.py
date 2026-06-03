"""
Phase 2 — refactor leaf composites to nest BASE-* sub-composites.

For each leaf composite that contains ALL atomic members of a BASE-* rule, this
replaces that cluster of atomic members with a single nested-composite member
referencing the BASE. The nested member inherits the role the cluster had (gate
if every replaced member was a gate, else watch), so firing behavior is
preserved while the member list shrinks.

SAFETY:
  * Default is DRY-RUN. Changes are applied inside a transaction, the real
    derive_stks is re-run for the target date, drv_stks fire counts are compared
    before/after, and the transaction is ROLLED BACK. Nothing is written.
  * Pass --apply to commit. A JSON backup of every rewritten leaf's original
    member list is written to db/backups/ first, for manual rollback.

Prereqs: db/seeds_base_rules.sql has been applied (BASE-* composites exist) and
drv_cat_atomic_input / atomic rules are current for the target date.

Usage:
    python -m etl.refactor_base_rules                      # dry-run, latest date
    python -m etl.refactor_base_rules --date 2026-04-30
    python -m etl.refactor_base_rules --only 449-B-TN-TD-LRR-UP-MACD
    python -m etl.refactor_base_rules --min-overlap 3      # require >=3 shared (full subset still required)
    python -m etl.refactor_base_rules --apply              # COMMIT the rewrite
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from config.settings import settings  # noqa: E402
from etl.db import session_scope  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.refactor_base_rules")


def _load_composites(s):
    """Return {code: {"members": [rowdict...], "meta": {...}}} for active mappings."""
    rows = s.execute(text("""
        SELECT composite_rule_code, COALESCE(member_kind,'atomic') AS member_kind,
               atomic_rule_id, nested_composite_code, weight_override,
               data_brkeout_from, condition_operator,
               COALESCE(member_role,'gate') AS member_role,
               category, intent_text, precondition_expr, evidence_cutoff
        FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL
        ORDER BY composite_rule_code, atomic_rule_id
    """)).mappings().all()
    comps: dict = {}
    for r in rows:
        c = comps.setdefault(r["composite_rule_code"], {"members": [], "meta": {}})
        c["members"].append(dict(r))
        if not c["meta"]:
            c["meta"] = {
                "category": r["category"], "intent_text": r["intent_text"],
                "precondition_expr": r["precondition_expr"],
                "evidence_cutoff": r["evidence_cutoff"],
            }
    return comps


def _base_member_ids(comps):
    """{base_code: set(atomic_rule_id)} for BASE-* composites."""
    out = {}
    for code, c in comps.items():
        if code.startswith("BASE-"):
            ids = {m["atomic_rule_id"] for m in c["members"]
                   if m["member_kind"] == "atomic" and m["atomic_rule_id"] is not None}
            if ids:
                out[code] = ids
    return out


def _plan_leaf(code, c, base_ids, min_overlap):
    """Return (new_members, replacements) or None if no base fully matches."""
    atomic_ids = {m["atomic_rule_id"] for m in c["members"]
                  if m["member_kind"] == "atomic" and m["atomic_rule_id"] is not None}
    by_id = {m["atomic_rule_id"]: m for m in c["members"]
             if m["member_kind"] == "atomic"}
    replaced_ids: set = set()
    nested_to_add = []
    replacements = []
    # Greedy: apply each base whose members are a full subset and not yet consumed.
    for base, ids in sorted(base_ids.items(), key=lambda kv: -len(kv[1])):
        if len(ids) < min_overlap:
            continue
        if ids.issubset(atomic_ids) and not (ids & replaced_ids):
            roles = {by_id[i]["member_role"] for i in ids}
            nested_role = "gate" if roles == {"gate"} else "watch"
            nested_to_add.append((base, nested_role))
            replacements.append({"base": base, "role": nested_role,
                                 "replaced_atomic_ids": sorted(ids)})
            replaced_ids |= ids
    if not nested_to_add:
        return None
    # New member list: keep members not consumed, append nested base refs.
    new_members = []
    for m in c["members"]:
        if m["member_kind"] == "atomic" and m["atomic_rule_id"] in replaced_ids:
            continue
        new_members.append(m)
    for base, role in nested_to_add:
        new_members.append({"member_kind": "composite", "nested_composite_code": base,
                            "member_role": role, "weight_override": None})
    return new_members, replacements


def _write_members(s, code, new_members, meta):
    """Replace a leaf composite's member rows (transactional; caller controls commit)."""
    s.execute(text("DELETE FROM ref_trig_composite_mapping WHERE composite_rule_code = :c"),
              {"c": code})
    for m in new_members:
        s.execute(text("""
            INSERT INTO ref_trig_composite_mapping
              (composite_rule_code, member_kind, member_role,
               atomic_rule_id, nested_composite_code,
               data_brkeout_from, condition_operator, weight_override,
               category, intent_text, precondition_expr, evidence_cutoff, active)
            VALUES
              (:c, :kind, :role, :aid, :nest, :thr, :op, :wo,
               :cat, :intent, :pre, :ecut, TRUE)
        """), {
            "c": code, "kind": m["member_kind"], "role": m.get("member_role", "gate"),
            "aid":  m.get("atomic_rule_id") if m["member_kind"] == "atomic" else None,
            "nest": m.get("nested_composite_code") if m["member_kind"] == "composite" else None,
            "thr":  m.get("data_brkeout_from"),
            "op":   m.get("condition_operator"),
            "wo":   m.get("weight_override"),
            "cat":  meta.get("category"), "intent": meta.get("intent_text"),
            "pre":  meta.get("precondition_expr"), "ecut": meta.get("evidence_cutoff"),
        })


def _fire_counts(s, target):
    """{composite_code: n_symbols_fired} from drv_stks for the date."""
    rows = s.execute(text("""
        SELECT t->>'rule_id' AS code, COUNT(*) AS n
        FROM drv_stks, jsonb_array_elements(triggered_composite_ids) AS t
        WHERE as_of_date = :d
        GROUP BY t->>'rule_id'
    """), {"d": target}).mappings().all()
    return {r["code"]: r["n"] for r in rows}


def _resolve_date(arg_date):
    if arg_date:
        return datetime.strptime(arg_date, "%Y-%m-%d").date()
    with session_scope() as s:
        d = s.execute(text("SELECT MAX(as_of_date) FROM drv_stks")).scalar()
    if not d:
        raise SystemExit("No drv_stks rows — run a derive first.")
    return d


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="YYYY-MM-DD (default: latest drv_stks date)")
    p.add_argument("--only", action="append", help="Restrict to these leaf codes (repeatable)")
    p.add_argument("--min-overlap", type=int, default=2,
                   help="Min base members for a match (full subset still required)")
    p.add_argument("--apply", action="store_true", help="COMMIT the rewrite (default: dry-run)")
    args = p.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD empty in .env"); return 2

    target = _resolve_date(args.date)
    log.info("Target date: %s   mode: %s", target, "APPLY" if args.apply else "DRY-RUN")

    from etl.derive import derive_stks

    with session_scope() as s:
        comps = _load_composites(s)
        base_ids = _base_member_ids(comps)
        if not base_ids:
            log.error("No BASE-* composites found — apply db/seeds_base_rules.sql first.")
            return 1
        log.info("BASE rules: %s", {b: sorted(ids) for b, ids in base_ids.items()})

        # Build the plan
        plans = {}
        for code, c in comps.items():
            if code.startswith("BASE-"):
                continue
            if args.only and code not in args.only:
                continue
            planned = _plan_leaf(code, c, base_ids, args.min_overlap)
            if planned:
                plans[code] = planned
        if not plans:
            log.info("No leaf composites match a BASE rule (full subset). Nothing to do.")
            return 0

        log.info("=== Proposed rewrites (%d leaves) ===", len(plans))
        for code, (new_members, repls) in plans.items():
            before_n = len(comps[code]["members"])
            after_n = len(new_members)
            tags = ", ".join(f"{r['base']}({r['role']})←{r['replaced_atomic_ids']}" for r in repls)
            log.info("  %-34s %d → %d members   nest: %s", code, before_n, after_n, tags)

        # Backup originals (always, so --apply is reversible)
        backup_dir = Path(__file__).resolve().parent.parent / "db" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = {code: comps[code]["members"] for code in plans}
        backup_path = backup_dir / f"refactor_base_rules_{stamp}.json"
        backup_path.write_text(json.dumps(backup, default=str, indent=2))
        log.info("Original member lists backed up → %s", backup_path)

        # Snapshot BEFORE, apply, re-derive, snapshot AFTER
        before = _fire_counts(s, target)
        for code, (new_members, _repls) in plans.items():
            _write_members(s, code, new_members, comps[code]["meta"])
        s.flush()
        derive_stks(s, target)
        after = _fire_counts(s, target)

        log.info("=== Firing diff (symbols fired per composite) ===")
        codes = sorted(set(before) | set(after) | set(plans))
        n_changed = 0
        for code in codes:
            b, a = before.get(code, 0), after.get(code, 0)
            if b != a:
                n_changed += 1
                log.info("  %-34s %4d → %4d   (%+d)", code, b, a, a - b)
        if n_changed == 0:
            log.info("  No change in fire counts — refactor is firing-equivalent. ✓")
        else:
            log.warning("  %d composites changed fire counts — review before --apply.", n_changed)

        if args.apply:
            s.commit()
            log.info("APPLIED and committed. Run `python -m etl.rebuild_rules` to propagate "
                     "to drv_actionable etc.")
        else:
            s.rollback()
            log.info("DRY-RUN — rolled back. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
