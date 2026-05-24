from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text
from datetime import date

with session_scope() as s:
    today = date.today()
    print(f"Today's date: {today}\n")

    # Check what dates are in drv_ma (the main derived table)
    print("Dates available in drv_ma (dashboard data):")
    result = s.execute(text("""
        SELECT DISTINCT as_of_date
        FROM drv_ma
        ORDER BY as_of_date DESC
        LIMIT 5
    """)).fetchall()

    if result:
        for row in result:
            is_today = "[TODAY]" if row[0] == today else ""
            print(f"  {row[0]} {is_today}")
    else:
        print("  [NO DATA IN drv_ma]")

    # Check raw data (hist_*)
    print(f"\nRaw files available for today ({today}):")
    raw_result = s.execute(text(f"""
        SELECT DISTINCT table_name, COUNT(DISTINCT symbol) as symbols
        FROM (
            SELECT 'hist_call' as table_name, symbol FROM hist_call WHERE snapshot_date = '{today}'
            UNION ALL
            SELECT 'hist_cs', symbol FROM hist_cs WHERE snapshot_date = '{today}'
            UNION ALL
            SELECT 'hist_y', symbol FROM hist_y WHERE snapshot_date = '{today}'
            UNION ALL
            SELECT 'hist_tl', symbol FROM hist_tl WHERE snapshot_date = '{today}'
        ) t
        GROUP BY table_name
        ORDER BY table_name
    """)).fetchall()

    if raw_result:
        for table, count in raw_result:
            print(f"  {table}: {count} symbols")
    else:
        print("  [NO RAW DATA FOR TODAY]")

    # Check if derive was run for today
    print(f"\nDerived runs for today ({today}):")
    derive_result = s.execute(text(f"""
        SELECT target_table, status, rows_built
        FROM meta_derived_run
        WHERE as_of_date = '{today}'
        ORDER BY started_at DESC
    """)).fetchall()

    if derive_result:
        for table, status, rows in derive_result:
            print(f"  {table}: {status} ({rows} rows)")
    else:
        print("  [NO DERIVE RUNS TODAY]")

    print(f"\nPROBLEM: If no data shows, either:")
    print(f"  1. Today's files haven't been loaded yet")
    print(f"  2. Derive hasn't been run for today")
    print(f"\nSOLUTION: Run derive for today")
    print(f"  python -c \"from etl.derive import derive_all; from etl.db import session_scope; from datetime import date; s = session_scope().__enter__(); derive_all(s, date.today())\"")
