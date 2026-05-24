import os
from pathlib import Path

print("FILE FORMAT CHECK")
print("=" * 80)

folders = {
    'Call': r'C:\Ashok\Investing\Stocks\Call\Archive',
    'Schwab (registered)': r'C:\Ashok\Investing\Stocks\Schwab\Archive',
    'Schwab (actual)': r'C:\Ashok\Investing\Stocks\CS\Archive',
}

for name, path_str in folders.items():
    p = Path(path_str)
    if p.exists():
        xlsx_files = list(p.glob('*.xlsx'))
        csv_files = list(p.glob('*.csv'))
        print(f"\n{name}:")
        print(f"  Path: {path_str}")
        print(f"  Excel files (.xlsx): {len(xlsx_files)}")
        print(f"  CSV files (.csv): {len(csv_files)}")
        
        if csv_files:
            print(f"  CSV files found:")
            for f in sorted(csv_files)[:5]:
                print(f"    - {f.name}")
    else:
        print(f"\n{name}:")
        print(f"  Path: {path_str}")
        print(f"  DOES NOT EXIST")
