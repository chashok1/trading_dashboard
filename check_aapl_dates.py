#!/usr/bin/env python3
"""Check when AAPL last appears in the database."""
from etl.db import session_scope
from sqlalchemy import text

def check_aapl_dates():
    with session_scope() as session:
        # Check hist_f (Fidelity) dates for AAPL
        print("FIDELITY (hist_f) - AAPL positions by date:")
        f_dates = session.execute(text("""
            SELECT DISTINCT snapshot_date, SUM(qty) as total_qty
            FROM hist_f
            WHERE symbol = 'AAPL'
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            LIMIT 10
        """)).fetchall()

        for row in f_dates:
            print(f"  {row[0]}: {row[1]} shares")

        if not f_dates:
            print("  (No AAPL found in hist_f)")

        print("\nSCHWAB (hist_cs) - AAPL positions by date:")
        cs_dates = session.execute(text("""
            SELECT DISTINCT snapshot_date, SUM(qty) as total_qty
            FROM hist_cs
            WHERE symbol = 'AAPL'
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            LIMIT 10
        """)).fetchall()

        for row in cs_dates:
            print(f"  {row[0]}: {row[1]} shares")

        if not cs_dates:
            print("  (No AAPL found in hist_cs)")

if __name__ == "__main__":
    check_aapl_dates()
