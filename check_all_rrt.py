from etl.db import session_scope
from sqlalchemy import text

rr_symbols = [
    '000001.SS', '2YY=F', 'BTC-USD', 'BZ=F', 'CADUSD=X', 'CL=F', 'EURUSD=X',
    'GBPUSD=X', 'GC=F', 'HG=F', 'JPYUSD=X', 'NG=F', 'SI=F', '^GDAXI', '^IXIC',
    '^N225', '^NYICDX', '^RUT', '^SPX', '^TNX', '^TYX', '^VIX'
]

with session_scope() as s:
    print("Checking RRT table for RR symbols (checking both rr_name and y_ticker columns):\n")

    found = 0
    missing = 0

    for sym in rr_symbols:
        row = s.execute(text("""
            SELECT rr_name, y_ticker, tos_ticker
            FROM ref_rrt
            WHERE rr_name = :sym OR y_ticker = :sym
        """), {'sym': sym}).first()

        if row:
            rr_name = row[0] or '—'
            y_ticker = row[1] or '—'
            tos_ticker = row[2] or '—'
            print(f"[OK] {sym:15} -> RR: {rr_name:15} Y: {y_ticker:15} TOS: {tos_ticker}")
            found += 1
        else:
            print(f"[XX] {sym:15} -> NOT FOUND")
            missing += 1

    print(f"\n\nSummary:")
    print(f"Found: {found}/{len(rr_symbols)}")
    print(f"Missing: {missing}/{len(rr_symbols)}")
