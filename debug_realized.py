"""
Simulate the fixed summary SQL so we can see what `realized_today_dollar` is
returning. If this prints $795.79 (or whatever your latest_cs date's total is)
but the UI shows $0, the API process is still running the OLD code.

Run from project root:
    python debug_realized.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    latest_cs = c.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= CURRENT_DATE"
    )).scalar()
    print(f"latest_cs snapshot_date = {latest_cs}")

    total = c.execute(text("""
        SELECT COALESCE(SUM(realized_gain), 0)
          FROM drv_cs_realized_gain
         WHERE as_of_date = :d
    """), {"d": latest_cs}).scalar()
    print(f"Sum(realized_gain) for {latest_cs} = ${float(total):.2f}")
    print("\nPer-row detail:")
    for r in c.execute(text("""
        SELECT account, symbol, shares_sold, realized_gain
          FROM drv_cs_realized_gain
         WHERE as_of_date = :d
         ORDER BY realized_gain DESC
    """), {"d": latest_cs}).all():
        print(f"  {r.account!r:35} {r.symbol!r:10} shares={r.shares_sold:>10}"
              f"  realized=${float(r.realized_gain):>10.2f}")

    print("\nPer-account aggregate (what cs_realized_by_acct CTE returns):")
    for r in c.execute(text("""
        SELECT account, SUM(realized_gain) AS realized_today_dollar
          FROM drv_cs_realized_gain
         WHERE as_of_date = :d
         GROUP BY account
         ORDER BY 2 DESC
    """), {"d": latest_cs}).all():
        print(f"  {r.account!r:35} ${float(r.realized_today_dollar):.2f}")
