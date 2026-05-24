#!/usr/bin/env python3
"""Fix double dashes in trace.html and trig.html."""

from pathlib import Path

files_to_fix = {
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trace.html'):
        ('Symbol Trace —" — Trading Dashboard', 'Symbol Trace — Trading Dashboard'),
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trig.html'):
        ('Trigger Rules —" — Trading Dashboard', 'Trigger Rules — Trading Dashboard'),
}

for file_path, (bad, good) in files_to_fix.items():
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if bad in content:
        content = content.replace(bad, good)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[FIXED] {file_path.name}")
    else:
        print(f"[CHECK] {file_path.name} - pattern not found")

print("\n[OK] Done")
