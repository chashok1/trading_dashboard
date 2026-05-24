#!/usr/bin/env python
"""Check what composites are actually firing in drv_stks."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()

    # Check how many symbols have triggered_composite_ids populated
    with_composites = s.execute(text(f"""
        SELECT COUNT(*) FROM drv_stks
        WHERE as_of_date = '{latest_date}' AND triggered_composite_ids IS NOT NULL
    """)).scalar()

    total = s.execute(text(f"""
        SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{latest_date}'
    """)).scalar()

    print(f"Date: {latest_date}")
    print(f"Total symbols: {total}")
    print(f"Symbols with triggered composites: {with_composites}")

    if with_composites > 0:
        print(f"\nComposites ARE firing!")

        # Show a sample
        sample = s.execute(text(f"""
            SELECT symbol, triggered_composite_ids FROM drv_stks
            WHERE as_of_date = '{latest_date}' AND triggered_composite_ids IS NOT NULL
            LIMIT 1
        """)).fetchone()

        if sample:
            symbol, composites = sample
            print(f"\nSample {symbol}: {composites}")
    else:
        print(f"\nNO composites are firing!")
        print("This means drv_stks derivation is not evaluating composites correctly")
        print("Check that atomic rules are being evaluated")

        # Check if atomic rules are firing
        with_atomics = s.execute(text(f"""
            SELECT COUNT(*) FROM drv_stks
            WHERE as_of_date = '{latest_date}' AND triggered_atomic_ids IS NOT NULL
        """)).scalar()

        print(f"\nSymbols with triggered atomic rules: {with_atomics}")

        if with_atomics > 0:
            sample = s.execute(text(f"""
                SELECT symbol, triggered_atomic_ids FROM drv_stks
                WHERE as_of_date = '{latest_date}' AND triggered_atomic_ids IS NOT NULL
                LIMIT 1
            """)).fetchone()
            print(f"Sample: {sample[0]}: {sample[1]}")
