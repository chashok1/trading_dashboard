"""
Diagnostic: did the Schwab cash row land in hist_cs after the loader fix?

Run from project root:
    python debug_cs_cash.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    latest = c.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_cs"
    )).scalar()
    print(f"Latest hist_cs snapshot: {latest}")

    print("\n=== Cash rows in latest snapshot (Cash & Cash Investments OR security_type) ===")
    rows = c.execute(text("""
        SELECT account, symbol, description, security_type, market_value
          FROM hist_cs
         WHERE snapshot_date = :d
           AND (
               COALESCE(symbol,'') = 'Cash & Cash Investments'
               OR COALESCE(security_type,'') = 'Cash and Money Market'
           )
         ORDER BY account, market_value DESC NULLS LAST
    """), {"d": latest}).all()
    if not rows:
        print("  (NO cash rows found — loader didn't insert them, or file_type isn't CS)")
    for r in rows:
        sym = (r.symbol or '')[:30]
        desc = (r.description or '')[:40]
        st = (r.security_type or '')[:30]
        print(f"  acct={r.account!r:18}  symbol={sym!r:30}  "
              f"security_type={st!r:30}  mv={r.market_value}  desc={desc!r}")

    print("\n=== Per-account cash totals (what the Cash tile will show) ===")
    rows = c.execute(text("""
        SELECT account,
               SUM(CASE
                   WHEN COALESCE(symbol,'') = 'Cash & Cash Investments'
                     OR COALESCE(security_type,'') = 'Cash and Money Market'
                   THEN market_value ELSE 0 END) AS cash,
               SUM(market_value) AS total_mv,
               COUNT(*) AS row_count
          FROM hist_cs
         WHERE snapshot_date = :d
         GROUP BY account
         ORDER BY account
    """), {"d": latest}).all()
    for r in rows:
        print(f"  acct={r.account!r:30}  cash={r.cash}  total_mv={r.total_mv}  rows={r.row_count}")

    print("\n=== Recent CS load runs ===")
    runs = c.execute(text("""
        SELECT run_id, file_type, target_tab, rows_inserted, rows_skipped,
               started_at, finished_at
          FROM meta_etl_run
         WHERE file_type = 'CS'
         ORDER BY started_at DESC
         LIMIT 5
    """)).all()
    for r in runs:
        print(f"  run={r.run_id}  ins={r.rows_inserted}  skp={r.rows_skipped}  "
              f"start={r.started_at}  end={r.finished_at}")
