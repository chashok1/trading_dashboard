from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Check drv_quote for 2026-05-27
    result = session.execute(text("""
        SELECT COUNT(*) total, 
               COUNT(DISTINCT symbol) unique_symbols,
               MIN(symbol) min_sym, MAX(symbol) max_sym
        FROM drv_quote WHERE as_of_date = '2026-05-27'
    """)).fetchone()

    print(f"drv_quote (2026-05-27):")
    print(f"  Total rows: {result[0]}")
    print(f"  Unique symbols: {result[1]}")
    print(f"  Sample symbols: {result[2]} to {result[3]}")

    # Show samples
    sample = session.execute(text("""
        SELECT symbol, last_price FROM drv_quote WHERE as_of_date = '2026-05-27' LIMIT 5
    """)).fetchall()
    print(f"  Sample data:")
    for sym, price in sample:
        print(f"    {sym}: {price}")
