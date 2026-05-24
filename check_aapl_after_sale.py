#!/usr/bin/env python3
"""Check if AAPL appears in snapshots after 2026-01-30."""
from etl.db import session_scope
from sqlalchemy import text

def check_aapl_after_sale():
    with session_scope() as session:
        print("AAPL in snapshots AFTER 2026-01-30 (sale date):\n")

        # Fidelity after sale
        f_after = session.execute(text("""
            SELECT snapshot_date, SUM(qty) as qty
            FROM hist_f
            WHERE symbol = 'AAPL' AND snapshot_date > '2026-01-30'
            GROUP BY snapshot_date
            ORDER BY snapshot_date
        """)).fetchall()

        if f_after:
            print(f"Fidelity AAPL after 2026-01-30: ({len(f_after)} snapshots)")
            for row in f_after[:5]:
                print(f"  {row[0]}: {row[1]} shares")
            if len(f_after) > 5:
                print(f"  ... and {len(f_after) - 5} more")
        else:
            print("Fidelity AAPL after 2026-01-30: NONE (correctly sold)")

        # Schwab after sale
        cs_after = session.execute(text("""
            SELECT snapshot_date, SUM(qty) as qty
            FROM hist_cs
            WHERE symbol = 'AAPL' AND snapshot_date > '2026-01-30'
            GROUP BY snapshot_date
            ORDER BY snapshot_date
        """)).fetchall()

        if cs_after:
            print(f"\nSchwab AAPL after 2026-01-30: ({len(cs_after)} snapshots)")
            for row in cs_after[:5]:
                print(f"  {row[0]}: {row[1]} shares")
            if len(cs_after) > 5:
                print(f"  ... and {len(cs_after) - 5} more")
        else:
            print("\nSchwab AAPL after 2026-01-30: NONE (correctly sold)")

        # Overall: do we have any AAPL after the sale?
        total_after = len(f_after) + len(cs_after)
        print(f"\nTotal AAPL snapshots after 2026-01-30: {total_after}")
        if total_after == 0:
            print("✓ CORRECT: AAPL is gone from all snapshots after the sale date")
        else:
            print("✗ ERROR: AAPL still appears in snapshots after the sale!")

if __name__ == "__main__":
    check_aapl_after_sale()
