from etl.db import session_scope
from sqlalchemy import text, inspect

with session_scope() as session:
    inspector = inspect(session.get_bind())
    
    print("=" * 100)
    print("SYMBOL COLUMN AUDIT - hist_* and drv_* tables")
    print("=" * 100)
    
    tables = [
        'hist_y', 'hist_tl', 'hist_td', 'hist_tw', 'hist_to', 'hist_rr',
        'hist_f', 'hist_cs', 'hist_call', 'hist_etf', 'hist_ii', 'hist_ps',
        'drv_ma', 'drv_quote', 'drv_stks', 'drv_dash', 'drv_dash_summary',
        'drv_trig', 'drv_actionable'
    ]
    
    print("\nTable Structure:")
    for tbl in tables:
        try:
            cols = inspector.get_columns(tbl)
            has_symbol = any(c['name'] == 'symbol' for c in cols)
            has_tos = any(c['name'] == 'tos_symbol' for c in cols)
            
            status = []
            if has_symbol:
                status.append("symbol")
            if has_tos:
                status.append("tos_symbol")
            
            col_str = ", ".join(status) if status else "NONE"
            print(f"  {tbl:30s}: {col_str}")
        except:
            pass
    
    print("\n" + "=" * 100)
    print("CRITICAL ISSUE DISCOVERED")
    print("=" * 100)
    
    print("""
drv_quote now returns tos_symbol from hist_y
drv_ma returns symbol from hist_tl/td/tw

When drv_ma joins with drv_quote:
  drv_ma.symbol (e.g. 'AAPL') 
  drv_quote.symbol (now could be 'AAPL' if tos_symbol mapped, or fallback to 'AAPL')

DANGER: If hist_y has a different ticker than hist_tl for same symbol,
        the join will fail or mismatch!

SOLUTION: Either revert drv_quote change, or ensure ALL symbol sources 
          (hist_tl, hist_td, hist_tw) ALSO use tos_symbol mapping.
    """)

