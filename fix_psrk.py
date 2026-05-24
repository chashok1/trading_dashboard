from etl.db import session_scope
from sqlalchemy import text

with session_scope() as sess:
    # Deprecate PSRK since there's no actual data for it
    sess.execute(text("""
        UPDATE ref_outlook_source 
        SET deprecated_at = now()
        WHERE source_code = 'PSRK';
    """))
    
    print("Deprecated PSRK source (no data available)")
    
    # Show remaining active sources
    print("\nActive outlook sources (after deprecation):")
    sources = sess.execute(text("""
        SELECT source_code, source_table, base_weight_method
        FROM ref_outlook_source
        WHERE deprecated_at IS NULL
        ORDER BY source_code;
    """)).fetchall()
    
    for row in sources:
        print(f"  {row[0]:<10} -> {row[1]:<15} | {row[2]}")