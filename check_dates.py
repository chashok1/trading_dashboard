from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    f_dates = s.execute(text(
        "SELECT snapshot_date FROM hist_f WHERE symbol='AAPL' ORDER BY snapshot_date DESC LIMIT 5"
    )).fetchall()
    cs_dates = s.execute(text(
        "SELECT snapshot_date FROM hist_cs WHERE symbol='AAPL' ORDER BY snapshot_date DESC LIMIT 5"
    )).fetchall()

    print("hist_f AAPL last 5 dates:")
    for r in f_dates:
        print(" ", r[0])

    print("hist_cs AAPL last 5 dates:")
    for r in cs_dates:
        print(" ", r[0])

    # Also check the overall latest date in each table
    f_max = s.execute(text("SELECT MAX(snapshot_date) FROM hist_f")).scalar()
    cs_max = s.execute(text("SELECT MAX(snapshot_date) FROM hist_cs")).scalar()
    print(f"\nhist_f max date (all symbols): {f_max}")
    print(f"hist_cs max date (all symbols): {cs_max}")
