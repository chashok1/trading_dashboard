from config.settings import settings
from etl.db import get_engine
from sqlalchemy.orm import Session
from sqlalchemy import text

engine = get_engine()
session = Session(engine)

try:
    tables = ["hist_call", "hist_etf", "hist_ii", "hist_ssh", "hist_rr"]
    for table in tables:
        dates = session.execute(text(f'SELECT DISTINCT snapshot_date FROM {table} ORDER BY snapshot_date DESC LIMIT 5')).scalars().all()
        count = session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
        print(f'{table}: {count} rows, recent dates: {dates}')

finally:
    session.close()
