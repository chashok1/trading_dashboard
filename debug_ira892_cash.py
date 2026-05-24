"""
Diagnostic: dump every row for IRA 892 in the latest hist_f and hist_cs snapshots.
Run from project root:
    python debug_ira892_cash.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    print("\n=== hist_f rows for IRA 892 (latest snapshot) ===")
    rows = c.execute(text("""
        SELECT snapshot_date,
               COALESCE(account_name, account_number) AS acct,
               symbol, description, type, current_value
          FROM hist_f
         WHERE COALESCE(account_name, account_number) ILIKE '%892%'
           AND snapshot_date = (
               SELECT MAX(snapshot_date) FROM hist_f
                WHERE COALESCE(account_name, account_number) ILIKE '%892%')
         ORDER BY current_value DESC NULLS LAST
    """)).all()
    if not rows:
        print("  (no Fidelity rows for IRA 892)")
    for r in rows:
        sym = r.symbol or ''
        desc = (r.description or '')[:40]
        typ = r.type or ''
        val = r.current_value
        print(f"  date={r.snapshot_date}  symbol={sym!r:18s}  "
              f"type={typ!r:30s}  val={val}  desc={desc!r}")

    print("\n=== hist_cs rows for IRA 892 (latest snapshot) ===")
    rows = c.execute(text("""
        SELECT snapshot_date, account, symbol, description,
               security_type, market_value
          FROM hist_cs
         WHERE account ILIKE '%892%'
           AND snapshot_date = (
               SELECT MAX(snapshot_date) FROM hist_cs
                WHERE account ILIKE '%892%')
         ORDER BY market_value DESC NULLS LAST
    """)).all()
    if not rows:
        print("  (no Schwab rows for IRA 892)")
    for r in rows:
        sym = r.symbol or ''
        desc = (r.description or '')[:40]
        st  = r.security_type or ''
        val = r.market_value
        print(f"  date={r.snapshot_date}  symbol={sym!r:30s}  "
              f"security_type={st!r:30s}  val={val}  desc={desc!r}")

    # And what my current F_IS_CASH / CS_IS_CASH would return for that account
    print("\n=== What my current cash-detection picks up for IRA 892 ===")
    f_cash = c.execute(text("""
        SELECT COALESCE(SUM(current_value), 0)
          FROM hist_f
         WHERE COALESCE(account_name, account_number) ILIKE '%892%'
           AND snapshot_date = (
               SELECT MAX(snapshot_date) FROM hist_f
                WHERE COALESCE(account_name, account_number) ILIKE '%892%')
           AND (
               COALESCE(symbol,'') = 'SPAXX**'
               OR UPPER(COALESCE(description,'')) LIKE '%HELD IN MONEY MARKET%'
           )
    """)).scalar()
    print(f"  F cash (current F_IS_CASH match): {f_cash}")

    cs_cash = c.execute(text("""
        SELECT COALESCE(SUM(market_value), 0)
          FROM hist_cs
         WHERE account ILIKE '%892%'
           AND snapshot_date = (
               SELECT MAX(snapshot_date) FROM hist_cs
                WHERE account ILIKE '%892%')
           AND (
               COALESCE(symbol,'') = 'Cash & Cash Investments'
               OR COALESCE(security_type,'') = 'Cash and Money Market'
           )
    """)).scalar()
    print(f"  CS cash (current CS_IS_CASH match): {cs_cash}")
