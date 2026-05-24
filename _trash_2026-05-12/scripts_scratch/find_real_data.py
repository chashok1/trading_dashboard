#!/usr/bin/env python
"""Find symbols with actual outlook data to test group firing."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()

    # Find symbols with non-null outlook values
    with_data = s.execute(text(f"""
        SELECT symbol, rr_brr, call_outlook, etf_outlook, ii_outlook, ssh_signal_sign
        FROM drv_ma
        WHERE as_of_date = '{latest_date}'
        AND (rr_brr IS NOT NULL OR call_outlook IS NOT NULL OR etf_outlook IS NOT NULL)
        LIMIT 10
    """)).fetchall()

    if not with_data:
        print("No symbols with outlook data found")
        # Check for symbols with ANY non-null data
        all_data = s.execute(text(f"""
            SELECT COUNT(*) FROM drv_ma WHERE as_of_date = '{latest_date}'
        """)).scalar()

        null_checks = s.execute(text(f"""
            SELECT
                COUNT(CASE WHEN rr_brr IS NOT NULL THEN 1 END) as rr_count,
                COUNT(CASE WHEN call_outlook IS NOT NULL THEN 1 END) as call_count,
                COUNT(CASE WHEN etf_outlook IS NOT NULL THEN 1 END) as etf_count,
                COUNT(CASE WHEN ii_outlook IS NOT NULL THEN 1 END) as ii_count,
                COUNT(CASE WHEN ssh_signal_sign IS NOT NULL THEN 1 END) as ssh_count
            FROM drv_ma WHERE as_of_date = '{latest_date}'
        """)).fetchone()

        print(f"Total symbols: {all_data}")
        if null_checks:
            print(f"Symbols with non-null values:")
            print(f"  rr_brr: {null_checks[0]}")
            print(f"  call_outlook: {null_checks[1]}")
            print(f"  etf_outlook: {null_checks[2]}")
            print(f"  ii_outlook: {null_checks[3]}")
            print(f"  ssh_signal_sign: {null_checks[4]}")
    else:
        print(f"Found {len(with_data)} symbols with outlook data:")
        for row in with_data:
            print(f"\n  {row[0]}:")
            print(f"    rr_brr: {row[1]}")
            print(f"    call_outlook: {row[2]}")
            print(f"    etf_outlook: {row[3]}")
            print(f"    ii_outlook: {row[4]}")
            print(f"    ssh_signal_sign: {row[5]}")

        # Check what's in drv_stks for these symbols
        symbol_list = [f"'{row[0]}'" for row in with_data]
        symbols_str = ','.join(symbol_list)

        print(f"\n\nIn drv_stks for these {len(with_data)} symbols:")
        counts = s.execute(text(f"""
            SELECT
                COUNT(CASE WHEN triggered_group_ids IS NOT NULL THEN 1 END) as with_groups,
                COUNT(CASE WHEN triggered_composite_ids IS NOT NULL THEN 1 END) as with_composites,
                COUNT(CASE WHEN triggered_atomic_ids IS NOT NULL THEN 1 END) as with_atomics
            FROM drv_stks
            WHERE symbol IN ({symbols_str}) AND as_of_date = '{latest_date}'
        """)).fetchone()

        if counts:
            print(f"  Symbols with triggered groups: {counts[0]}/{len(with_data)}")
            print(f"  Symbols with triggered composites: {counts[1]}/{len(with_data)}")
            print(f"  Symbols with triggered atomics: {counts[2]}/{len(with_data)}")
