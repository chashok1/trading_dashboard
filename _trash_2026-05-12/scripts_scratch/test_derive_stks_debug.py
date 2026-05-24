#!/usr/bin/env python
"""Debug derivation by running a simplified version."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()
    print(f"Date: {latest_date}\n")

    # Get one row from drv_ma
    ma_row = s.execute(text(f"""
        SELECT symbol, rr_brr, call_outlook, etf_outlook, ii_outlook, ssh_signal_sign
        FROM drv_ma
        WHERE as_of_date = '{latest_date}'
        LIMIT 1
    """)).mappings().first()

    if not ma_row:
        print("No data in drv_ma")
        exit(1)

    print(f"Test symbol: {ma_row['symbol']}")
    print(f"  rr_brr: {ma_row['rr_brr']}")
    print(f"  call_outlook: {ma_row['call_outlook']}")
    print(f"  etf_outlook: {ma_row['etf_outlook']}")
    print(f"  ii_outlook: {ma_row['ii_outlook']}")
    print(f"  ssh_signal_sign: {ma_row['ssh_signal_sign']}\n")

    # Fetch atomic rules
    atomics = s.execute(text("""
        SELECT atomic_rule_id FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL LIMIT 5
    """)).fetchall()

    print(f"Sample atomic rules: {[a[0] for a in atomics]}\n")

    # Fetch composites
    composites = s.execute(text("""
        SELECT DISTINCT composite_rule_code FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL LIMIT 5
    """)).fetchall()

    print(f"Sample composites: {[c[0] for c in composites]}\n")

    # Fetch rule groups
    groups = s.execute(text("""
        SELECT rule_group_code FROM ref_trig_rule_group
        WHERE deprecated_at IS NULL AND rule_group_code LIKE 'GROUP-%'
    """)).fetchall()

    print(f"Auto-generated groups: {[g[0] for g in groups]}\n")

    # Check how many groups have members
    groups_with_members = s.execute(text("""
        SELECT COUNT(DISTINCT rule_group_code) FROM ref_trig_group_member
        WHERE rule_group_code LIKE 'GROUP-%' AND deprecated_at IS NULL
    """)).scalar()

    print(f"Groups with members: {groups_with_members}\n")

    print("So the data IS in the database.")
    print("The derivation code should be creating triggered_group_ids when groups fire.")
    print("\nRun this to force re-derive: python -m etl.derive_all for a specific date")
