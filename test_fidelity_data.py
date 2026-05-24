#!/usr/bin/env python3

from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    max_date = s.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_f"
    )).scalar()
    print(f"Max date in hist_f: {max_date}")

    rows = s.execute(text("""
        SELECT account_number, COALESCE(account_name, account_number) AS account,
               symbol, type, current_value, today_gl_dollar, total_gl_dollar
        FROM hist_f
        WHERE snapshot_date = :d
        ORDER BY account_number, symbol
    """), {"d": max_date}).mappings().all()

    print(f"\nTotal rows for {max_date}: {len(rows)}")
    print("\nFidelity holdings:")
    for r in rows:
        print(f"  Acct: {r['account']:30} | Symbol: {r['symbol']:15} | Type: {r['type']:15} | Value: {r['current_value']:>10}")
