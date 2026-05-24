"""
Show ALL distinct symbols / security_types in hist_cs for IRA 892's latest snapshot.
Reveals what label Schwab is using for cash in your data.

Run from project root:
    python debug_cs_symbols.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    print("=== Every row for IRA 892 (latest snapshot) ===")
    rows = c.execute(text("""
        SELECT symbol, description, security_type,
               market_value, qty, price
          FROM hist_cs
         WHERE account ILIKE '%892%'
           AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs
                                 WHERE account ILIKE '%892%')
         ORDER BY market_value DESC NULLS LAST
    """)).all()
    print(f"  total rows: {len(rows)}\n")
    for r in rows:
        sym  = (r.symbol or '')[:35]
        st   = (r.security_type or '')[:30]
        desc = (r.description or '')[:35]
        print(f"  symbol={sym!r:37s}  st={st!r:32s}  "
              f"qty={r.qty}  price={r.price}  mv={r.market_value}")
        print(f"     desc={desc!r}")

    print("\n=== Loader's most recent run for CS — read vs inserted vs skipped ===")
    run = c.execute(text("""
        SELECT * FROM meta_etl_run
         WHERE file_type='CS'
         ORDER BY started_at DESC LIMIT 1
    """)).mappings().first()
    if run:
        for k, v in run.items():
            print(f"  {k}: {v}")
