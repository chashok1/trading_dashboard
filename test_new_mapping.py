from etl.db import session_scope
from sqlalchemy import text
from datetime import datetime

with session_scope() as s:
    # Get latest dates
    tl_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_tl")).first()[0]
    y_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_y")).first()[0]
    rr_date = s.execute(text("SELECT MAX(snapshot_date) FROM hist_rr")).first()[0]

    print("=== TL SYMBOLS (mapped via tos_ticker) ===\n")
    tl_rows = s.execute(text("""
        SELECT DISTINCT COALESCE(r.tos_ticker, h.symbol)
        FROM hist_tl h
        LEFT JOIN ref_rrt r ON h.symbol = r.tos_ticker
        WHERE h.snapshot_date = :d
        ORDER BY COALESCE(r.tos_ticker, h.symbol)
    """), {"d": tl_date}).fetchall()
    tl_symbols = sorted(set(r[0] for r in tl_rows if r[0]))
    print(f"TL count: {len(tl_symbols)}\n")
    # Show only relevant ones
    for sym in tl_symbols:
        if any(x in str(sym) for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS']):
            print(f"  {sym}")

    print("\n=== Y SYMBOLS (mapped via y_ticker) ===\n")
    y_rows = s.execute(text("""
        SELECT DISTINCT COALESCE(r.tos_ticker, h.symbol)
        FROM hist_y h
        LEFT JOIN ref_rrt r ON h.symbol = r.y_ticker
        WHERE h.snapshot_date = :d
        ORDER BY COALESCE(r.tos_ticker, h.symbol)
    """), {"d": y_date}).fetchall()
    y_symbols = sorted(set(r[0] for r in y_rows if r[0]))
    print(f"Y count: {len(y_symbols)}\n")
    for sym in y_symbols:
        if any(x in str(sym) for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS']):
            print(f"  {sym}")

    print("\n=== RR SYMBOLS (mapped via rr_name) ===\n")
    rr_rows = s.execute(text("""
        SELECT DISTINCT COALESCE(r.tos_ticker, h.symbol)
        FROM hist_rr h
        LEFT JOIN ref_rrt r ON h.symbol = r.rr_name
        WHERE h.snapshot_date = :d
        ORDER BY COALESCE(r.tos_ticker, h.symbol)
    """), {"d": rr_date}).fetchall()
    rr_symbols = sorted(set(r[0] for r in rr_rows if r[0]))
    print(f"RR count: {len(rr_symbols)}\n")
    for sym in rr_symbols:
        if any(x in str(sym) for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS', 'BTC']):
            print(f"  {sym}")

    print("\n=== MISSING FROM Y (not in TL) ===\n")
    y_missing = sorted(set(y_symbols) - set(tl_symbols))
    if y_missing:
        for sym in y_missing:
            if any(x in str(sym) for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS']):
                print(f"  {sym}")
    else:
        print("  (none)")

    print("\n=== MISSING FROM RR (not in TL) ===\n")
    rr_missing = sorted(set(rr_symbols) - set(tl_symbols))
    if rr_missing:
        for sym in rr_missing:
            if any(x in str(sym) for x in ['GVZ', 'INDU', 'MOVE', 'OVX', 'VOLQ', 'VVIX', 'VXD', 'VXN', 'BSESN', 'NYXBT', 'BBBY', 'CALY', 'COLO', 'CRIT', 'FRED', 'DXY', 'FKU', 'JPY', 'THS', 'BTC']):
                print(f"  {sym}")
    else:
        print("  (none)")
