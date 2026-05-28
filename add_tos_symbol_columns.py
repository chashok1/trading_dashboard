from etl.db import session_scope
from sqlalchemy import text

tables_to_update = [
    'hist_tl', 'hist_td', 'hist_tw', 'hist_to',
    'hist_call', 'hist_etf', 'hist_ii', 'hist_sss'
]

with session_scope() as session:
    for table in tables_to_update:
        try:
            session.execute(text(f"ALTER TABLE {table} ADD COLUMN tos_symbol TEXT"))
            session.commit()
            print(f"Added tos_symbol to {table}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"{table}: tos_symbol already exists")
            else:
                print(f"ERROR {table}: {e}")
                session.rollback()

    # Create indexes
    for table in tables_to_update:
        try:
            session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_tos_symbol ON {table}(tos_symbol, snapshot_date)"))
            session.commit()
            print(f"Created index on {table}.tos_symbol")
        except Exception as e:
            print(f"Index error {table}: {e}")
            session.rollback()

    print("\nDone!")
