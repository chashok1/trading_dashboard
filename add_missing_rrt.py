from etl.db import session_scope
from sqlalchemy import text

missing_symbols = {
    'BBBY': {'rr_name': 'BBBY', 'tos_ticker': '', 'contracts': ''},
    'CALY': {'rr_name': 'CALY', 'tos_ticker': '', 'contracts': ''},
    'COLO': {'rr_name': 'COLO', 'tos_ticker': '', 'contracts': ''},
    'CRIT': {'rr_name': 'CRIT', 'tos_ticker': '', 'contracts': ''},
    'DGS2:FRED': {'rr_name': 'DGS2-FRED', 'tos_ticker': '2-Year Treasury', 'contracts': ''},
    'DX=F': {'rr_name': 'DXY-FUT', 'tos_ticker': 'DXY', 'contracts': ''},
    'FKU': {'rr_name': 'FKU', 'tos_ticker': '', 'contracts': ''},
    'JPY=X': {'rr_name': 'JPY-USD', 'tos_ticker': 'JPYUSD', 'contracts': ''},
    'THS': {'rr_name': 'THS', 'tos_ticker': '', 'contracts': ''},
    '^DJI': {'rr_name': 'DJI', 'tos_ticker': '$INDU', 'contracts': ''},
    '^GVZ': {'rr_name': 'GVZ-IDX', 'tos_ticker': '$GVZ', 'contracts': ''},
    '^MOVE': {'rr_name': 'MOVE-IDX', 'tos_ticker': '$MOVE', 'contracts': ''},
    '^NYXBT': {'rr_name': 'NYXBT-IDX', 'tos_ticker': '', 'contracts': ''},
    '^OVX': {'rr_name': 'OVX-IDX', 'tos_ticker': '$OVX', 'contracts': ''},
    '^VOLQ': {'rr_name': 'VOLQ-IDX', 'tos_ticker': '$VOLQ', 'contracts': ''},
    '^VVIX': {'rr_name': 'VVIX-IDX', 'tos_ticker': '$VVIX', 'contracts': ''},
    '^VXD': {'rr_name': 'VXD-IDX', 'tos_ticker': '$VXD', 'contracts': ''},
    '^VXN': {'rr_name': 'VXN-IDX', 'tos_ticker': '$VXN', 'contracts': ''},
}

with session_scope() as s:
    inserted = 0
    skipped = 0

    for y_ticker, data in missing_symbols.items():
        rr_name = data['rr_name'] if data['rr_name'] else None
        tos_ticker = data['tos_ticker'] if data['tos_ticker'] else None
        contracts = data['contracts'] if data['contracts'] else None

        # Check if already exists
        existing = s.execute(text("""
            SELECT y_ticker FROM ref_rrt WHERE y_ticker = :y_ticker
        """), {'y_ticker': y_ticker}).first()

        if existing:
            print(f"[SKIP] {y_ticker} - already exists")
            skipped += 1
        else:
            s.execute(text("""
                INSERT INTO ref_rrt (rr_name, y_ticker, tos_ticker, contracts)
                VALUES (:rr_name, :y_ticker, :tos_ticker, :contracts)
            """), {
                'rr_name': rr_name,
                'y_ticker': y_ticker,
                'tos_ticker': tos_ticker,
                'contracts': contracts
            })
            print(f"[OK] Inserted {y_ticker}")
            inserted += 1

    s.commit()
    print(f"\n\nSummary:")
    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")
    print(f"Total: {inserted + skipped}")
