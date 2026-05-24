#!/usr/bin/env python
"""Check count of derived indicator rules (no From/To thresholds)."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    # Get all atomic rules
    all_rules = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
    """)).scalar()

    # Get threshold-based rules (with From/To)
    threshold_rules = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
        AND brkeout_from IS NOT NULL
    """)).scalar()

    # Get derived indicator rules (no From/To)
    derived_rules = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
        AND (brkeout_from IS NULL OR brkeout_from IS NULL)
    """)).scalar()

    print(f"Total atomic rules: {all_rules}")
    print(f"Threshold-based rules (with From/To): {threshold_rules}")
    print(f"Derived indicator rules (no From/To): {derived_rules}")
    print(f"\nExpected total: 113")
    print(f"Actual total: {threshold_rules + derived_rules}")

    # Show some examples of derived rules
    print(f"\nSample derived indicator rules:")
    samples = s.execute(text("""
        SELECT atomic_rule_id, rule_name, ma_column_name FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
        AND brkeout_from IS NULL
        ORDER BY atomic_rule_id
        LIMIT 10
    """)).fetchall()

    for rule_id, name, col in samples:
        print(f"  {rule_id}: {name} -> {col}")
