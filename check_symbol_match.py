from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    # Get latest TL symbols
    tl_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_tl")).first()[0]
    print(f"TL date: {tl_date}\n")

    tl_symbols = s.execute(text("""
        SELECT DISTINCT symbol FROM hist_tl
        WHERE snapshot_date = :d
        ORDER BY symbol
    """), {"d": tl_date}).fetchall()

    tl_set = set(r[0] for r in tl_symbols if r[0])
    print(f"TL symbols ({len(tl_set)}):")
    for sym in sorted(tl_set):
        if any(x in sym for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS']):
            print(f"  {sym}")

    # Get latest Y symbols
    y_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_y")).first()[0]
    print(f"\nY date: {y_date}\n")

    y_symbols = s.execute(text("""
        SELECT DISTINCT symbol FROM hist_y
        WHERE snapshot_date = :d
        ORDER BY symbol
    """), {"d": y_date}).fetchall()

    y_set = set(r[0] for r in y_symbols if r[0])
    print(f"Y symbols ({len(y_set)}) - showing only the ones you mentioned:")
    for sym in sorted(y_set):
        if any(x in sym for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS']):
            print(f"  {sym}")

    # Check what's in RRT for these
    print("\n\nRRT mapping check for these symbols:")
    test_symbols = ['$GVZ', '$INDU', '$MOVE', '$OVX', '$VOLQ', '$VVIX', '$VXD', '$VXN', '^GVZ', '^INDU', '^MOVE', '^OVX', '^VOLQ', '^VVIX', '^VXD', '^VXN', '000001.SS', 'BBBY', 'CALY', 'COLO', 'CRIT', 'DGS2:FRED', 'DXY', 'FKU', 'JPY=X', 'THS', '^BSESN', '^NYXBT']

    for sym in sorted(test_symbols):
        row = s.execute(text("""
            SELECT rr_name, y_ticker, tos_ticker FROM ref_rrt
            WHERE y_ticker = :sym OR tos_ticker = :sym
        """), {"sym": sym}).first()

        if row:
            print(f"  {sym:20} -> RR: {row[0]:15} Y: {row[1]:15} TOS: {row[2]}")
        else:
            print(f"  {sym:20} -> NOT IN RRT")
