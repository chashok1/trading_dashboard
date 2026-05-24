from etl.db import session_scope
from sqlalchemy import text

symbols_to_check = [
    '000001.SS', 'BBBY', 'CALY', 'COLO', 'CRIT', 'DGS2:FRED', 'DX=F',
    'FKU', 'JPY=X', 'THS', '^BSESN', '^DJI', '^GVZ', '^MOVE', '^NYXBT',
    '^OVX', '^VOLQ', '^VVIX', '^VXD', '^VXN'
]

with session_scope() as s:
    print("Checking RRT mappings for these symbols:\n")

    missing = []
    found = []

    for symbol in symbols_to_check:
        # Check if symbol exists in ref_rrt as y_ticker
        row = s.execute(text("""
            SELECT rr_name, tos_ticker, contracts
            FROM ref_rrt
            WHERE y_ticker = :symbol
        """), {"symbol": symbol}).first()

        if row:
            rr_name = row[0] or '—'
            tos_ticker = row[1] or '—'
            contracts = row[2] or '—'
            found.append((symbol, rr_name, tos_ticker, contracts))
            print(f"[OK] {symbol:15} -> RR: {rr_name:15} TOS: {tos_ticker:15} Contracts: {contracts}")
        else:
            missing.append(symbol)
            print(f"[XX] {symbol:15} (NOT FOUND in ref_rrt)")

    print(f"\n\nSummary:")
    print(f"Found in RRT: {len(found)}")
    print(f"Missing from RRT: {len(missing)}")

    if missing:
        print(f"\nMissing symbols that need RRT mapping:")
        for sym in missing:
            print(f"  {sym}")
