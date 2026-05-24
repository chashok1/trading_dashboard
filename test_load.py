from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    count = s.execute(text("SELECT COUNT(*) FROM hist_tl WHERE snapshot_date = '2026-05-13'")).scalar()
    print(f'hist_tl rows for 2026-05-13: {count}')

    if count > 0:
        row = s.execute(text("SELECT symbol, last_price FROM hist_tl WHERE snapshot_date = '2026-05-13' LIMIT 1")).first()
        print(f'Sample row: {row}')
