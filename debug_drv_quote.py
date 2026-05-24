"""
Verify drv_quote against the underlying sources.

For each symbol on a chosen date, print:
  - the resolved drv_quote row
  - the candidate row from hist_y, hist_tl, hist_td (latest each)
  - their loaded_at timestamps so we can confirm "latest loaded_at wins"

Run from project root:
    python debug_drv_quote.py            # uses MAX(as_of_date) in drv_quote
    python debug_drv_quote.py 2026-05-18 # explicit date
"""
import sys
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

# Pick date
date_arg = sys.argv[1] if len(sys.argv) > 1 else None

with eng.connect() as c:
    if date_arg is None:
        date_arg = c.execute(text(
            "SELECT MAX(as_of_date) FROM drv_quote"
        )).scalar()
    if date_arg is None:
        print("drv_quote is empty. Run `python -m etl.tickers_initial_load` "
              "or a derive cycle first.")
        sys.exit(1)
    print(f"=== drv_quote diagnostic for as_of_date = {date_arg} ===\n")

    # Pick a few interesting symbols: highest market value, plus a couple of named ones
    sample_syms = c.execute(text("""
        SELECT symbol FROM drv_quote
         WHERE as_of_date = :d
         ORDER BY symbol
         LIMIT 10
    """), {"d": date_arg}).all()
    syms = [r[0] for r in sample_syms]
    if not syms:
        print("No symbols in drv_quote for that date.")
        sys.exit(1)

    for sym in syms:
        print(f"--- symbol: {sym} ---")
        quote = c.execute(text("""
            SELECT * FROM drv_quote
             WHERE as_of_date = :d AND symbol = :s
        """), {"d": date_arg, "s": sym}).mappings().first()
        if not quote:
            print("  (no row)")
            continue
        # Print drv_quote
        for k in ('last_price','net_chng','pct_change','open_price',
                  'high_price','low_price','rsi','imp_volatility'):
            print(f"  drv_quote.{k:15} = {quote[k]}")

        # Pull candidate rows
        for src_tbl, sql_fields in (
            ('hist_y',
             "last_price, change_amt AS net_chng, change_pct AS pct_change, "
             "open_price, high_price, low_price, "
             "NULL::NUMERIC AS rsi, NULL::NUMERIC AS imp_volatility"),
            ('hist_tl',
             "last_price, net_chng, change_pct AS pct_change, "
             "open_price, high_price, low_price, "
             "rsi, imp_volatility_raw AS imp_volatility"),
            ('hist_td',
             "last_price, net_chng, change_pct AS pct_change, "
             "open_price, high_price, low_price, "
             "rsi, imp_volatility"),
        ):
            row = c.execute(text(f"""
                SELECT snapshot_date, sequence, loaded_at, {sql_fields}
                  FROM {src_tbl}
                 WHERE symbol = :s AND snapshot_date <= :d
                 ORDER BY snapshot_date DESC, loaded_at DESC, sequence DESC
                 LIMIT 1
            """), {"d": date_arg, "s": sym}).mappings().first()
            if row:
                print(f"  candidate from {src_tbl} (snap={row['snapshot_date']} "
                      f"loaded={row['loaded_at']} seq={row['sequence']}):")
                for k in ('last_price','net_chng','pct_change','open_price',
                          'high_price','low_price','rsi','imp_volatility'):
                    print(f"     {src_tbl}.{k:15} = {row[k]}")
            else:
                print(f"  no candidate in {src_tbl}")
        print()
