from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    # Get latest Y date and symbols
    y_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_y")).first()[0]
    print(f"Y date: {y_date}\n")

    # Check specific symbols
    test_symbols = ['^VXD', '^VXN', '^GVZ', '^MOVE', '^OVX', '^VOLQ', '^VVIX', '^VXD']

    print("Y symbol -> RRT lookup -> tos_ticker:\n")
    for sym in test_symbols:
        # Check if symbol exists in Y
        y_exists = s.execute(text("""
            SELECT COUNT(*) FROM hist_y WHERE symbol = :sym AND snapshot_date = :d
        """), {"sym": sym, "d": y_date}).first()[0]

        # Check RRT mapping
        rrt_row = s.execute(text("""
            SELECT y_ticker, tos_ticker FROM ref_rrt WHERE y_ticker = :sym
        """), {"sym": sym}).first()

        if rrt_row:
            print(f"  {sym:15} -> RRT found -> tos_ticker: {rrt_row[1]}")
        else:
            print(f"  {sym:15} -> RRT NOT FOUND")

        print(f"             Y has this symbol: {y_exists > 0}\n")
