import os
from pathlib import Path

print("=" * 80)
print("FILE FOLDER CONTENTS - What's actually in the Archive folders")
print("=" * 80)

folders = {
    'Call': r'C:\Ashok\Investing\Stocks\Call\Archive',
    'RR': r'C:\Ashok\Investing\Stocks\RR\Archive',
    'II': r'C:\Ashok\Investing\Stocks\II\Archive',
    'ETF': r'C:\Ashok\Investing\Stocks\ETF\Archive',
    'PS': r'C:\Ashok\Investing\Stocks\PS\Archive',
    'ETFChange': r'C:\Ashok\Investing\Stocks\ETFChange\Archive',
    'Schwab': r'C:\Ashok\Investing\Stocks\Schwab\Archive',
}

for name, path_str in folders.items():
    p = Path(path_str)
    if p.exists():
        files = sorted(list(p.glob('*.xlsx')))
        print(f"\n[{name}] - {len(files)} files:")
        for f in files[-5:]:  # Last 5 files
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:<40} ({size_kb:>8.1f} KB)")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more files")
    else:
        print(f"\n[{name}] - FOLDER DOES NOT EXIST")
