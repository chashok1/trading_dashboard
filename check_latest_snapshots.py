#!/usr/bin/env python3
"""Check latest snapshot dates in database."""
from etl.db import session_scope
from sqlalchemy import text

def check_latest():
    with session_scope() as session:
        print("Latest snapshot dates in database:\n")

        # Fidelity overall
        f_latest = session.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f
        """)).scalar()
        print(f"Fidelity (hist_f) latest snapshot: {f_latest}")

        # Schwab overall
        cs_latest = session.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs
        """)).scalar()
        print(f"Schwab (hist_cs) latest snapshot: {cs_latest}")

        # Check for any snapshots after 2026-01-30
        print("\n--- Checking for data AFTER 2026-01-30 ---")

        f_after = session.execute(text("""
            SELECT COUNT(DISTINCT snapshot_date) FROM hist_f
            WHERE snapshot_date > '2026-01-30'
        """)).scalar()
        print(f"Fidelity rows with snapshot_date > 2026-01-30: {f_after}")

        cs_after = session.execute(text("""
            SELECT COUNT(DISTINCT snapshot_date) FROM hist_cs
            WHERE snapshot_date > '2026-01-30'
        """)).scalar()
        print(f"Schwab rows with snapshot_date > 2026-01-30: {cs_after}")

        # Show actual dates after 2026-01-30
        if f_after > 0:
            print("\nFidelity snapshot dates after 2026-01-30:")
            f_dates = session.execute(text("""
                SELECT DISTINCT snapshot_date FROM hist_f
                WHERE snapshot_date > '2026-01-30'
                ORDER BY snapshot_date
            """)).fetchall()
            for row in f_dates[:10]:
                print(f"  {row[0]}")

        if cs_after > 0:
            print("\nSchwab snapshot dates after 2026-01-30:")
            cs_dates = session.execute(text("""
                SELECT DISTINCT snapshot_date FROM hist_cs
                WHERE snapshot_date > '2026-01-30'
                ORDER BY snapshot_date
            """)).fetchall()
            for row in cs_dates[:10]:
                print(f"  {row[0]}")

if __name__ == "__main__":
    check_latest()
