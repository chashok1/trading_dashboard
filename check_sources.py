from etl.db import session_scope
from sqlalchemy import text

with session_scope() as sess:
    print("=" * 80)
    print("OUTLOOK SOURCES IN ref_outlook_source:")
    print("=" * 80)
    
    sources = sess.execute(text("""
        SELECT source_code, source_table, base_weight_method, deprecated_at
        FROM ref_outlook_source
        ORDER BY source_code;
    """)).fetchall()
    
    for row in sources:
        status = "DEPRECATED" if row[3] else "ACTIVE"
        print(f"  {row[0]:<10} -> {row[1]:<15} | {row[2]:<20} | {status}")
    
    print("\n" + "=" * 80)
    print("ACTUAL FILES IN Archive FOLDERS:")
    print("=" * 80)
    
    import os
    from pathlib import Path
    
    folders = {
        'CALL': r'C:\Ashok\Investing\Stocks\Call\Archive',
        'CS (Schwab)': r'C:\Ashok\Investing\Stocks\CS\Archive',
        'RR': r'C:\Ashok\Investing\Stocks\RR\Archive',
    }
    
    for name, path_str in folders.items():
        p = Path(path_str)
        if p.exists():
            files = sorted(list(p.glob('*')))[:3]
            print(f"\n  {name}:")
            for f in files:
                print(f"    {f.name}")