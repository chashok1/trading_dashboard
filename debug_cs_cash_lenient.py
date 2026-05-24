"""
Lenient match for any row that looks like cash.
Print the raw symbol with quotes so we can see whitespace / casing exactly.

Run from project root:
    python debug_cs_cash_lenient.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    print("=== Every IRA 892 row with the raw symbol (quoted) and its byte length ===")
    rows = c.execute(text("""
        SELECT symbol,
               LENGTH(symbol) AS sym_len,
               octet_length(symbol) AS sym_bytes,
               description,
               security_type,
               market_value
          FROM hist_cs
         WHERE account ILIKE '%892%'
           AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs
                                 WHERE account ILIKE '%892%')
         ORDER BY market_value DESC NULLS LAST
    """)).all()
    print(f"  total rows: {len(rows)}\n")
    for r in rows:
        print(f"  symbol={r.symbol!r}  len={r.sym_len}  bytes={r.sym_bytes}  "
              f"st={r.security_type!r}  mv={r.market_value}  desc={r.description!r}")

    print("\n=== Anything containing the word 'cash' (case-insensitive) ===")
    rows = c.execute(text("""
        SELECT account, symbol, description, security_type, market_value
          FROM hist_cs
         WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs)
           AND (
               LOWER(symbol) LIKE '%cash%'
               OR LOWER(description) LIKE '%cash%'
               OR LOWER(security_type) LIKE '%cash%'
               OR LOWER(security_type) LIKE '%money market%'
           )
    """)).all()
    for r in rows:
        print(f"  acct={r.account!r}  symbol={r.symbol!r}  "
              f"st={r.security_type!r}  mv={r.market_value}")
    if not rows:
        print("  (still nothing — the cash row was NOT inserted into the DB)")
