from etl.db import session_scope
from sqlalchemy import text

tables = ['hist_tl', 'hist_td', 'hist_to', 'hist_tw', 'hist_call', 'hist_etf', 'hist_ii', 'hist_sss']

with session_scope() as session:
    print("TOS_Symbol Population Status (2026-05-27):\n")
    for table in tables:
        result = session.execute(text(f"""
            SELECT COUNT(*) total, COUNT(tos_symbol) with_tos, COUNT(CASE WHEN tos_symbol IS NULL THEN 1 END) null_tos
            FROM {table} WHERE snapshot_date = '2026-05-27'
        """)).fetchone()
        
        if result[0] > 0:
            pct = int(100 * result[1] / result[0]) if result[0] > 0 else 0
            print(f"{table:15s}: {result[0]:4d} rows, {result[1]:4d} with tos_symbol ({pct}%), {result[2]:4d} NULL")
        else:
            print(f"{table:15s}: No data for 2026-05-27")

    print("\nSample tos_symbol values:")
    for table in ['hist_tl', 'hist_call', 'hist_etf']:
        sample = session.execute(text(f"""
            SELECT symbol, tos_symbol FROM {table} 
            WHERE snapshot_date = '2026-05-27' AND tos_symbol IS NOT NULL
            LIMIT 2
        """)).fetchall()
        if sample:
            print(f"\n{table}:")
            for sym, tos_sym in sample:
                print(f"  {sym:15s} -> {tos_sym}")
