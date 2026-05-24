from etl.db import session_scope
from sqlalchemy import text

rr_symbols_to_check = [
    '000001.SS', '2YY=F', 'BTC-USD', 'BZ=F', 'CADUSD=X', 'CL=F', 'EURUSD=X',
    'GBPUSD=X', 'GC=F', 'HG=F', 'JPYUSD=X', 'NG=F', 'SI=F', '^GDAXI', '^IXIC',
    '^N225', '^NYICDX', '^RUT', '^SPX', '^TNX', '^TYX', '^VIX'
]

with session_scope() as s:
    print("Checking RRT mappings for RR symbols:\n")

    missing = []
    found = []

    for symbol in rr_symbols_to_check:
        # Check if symbol exists in ref_rrt as rr_name
        row = s.execute(text("""
            SELECT rr_name, tos_ticker, contracts
            FROM ref_rrt
            WHERE rr_name = :symbol
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
        print(f"\nMissing RR symbols that need RRT mapping:")
        for sym in missing:
            print(f"  {sym}")
