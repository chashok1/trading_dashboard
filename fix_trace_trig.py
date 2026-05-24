#!/usr/bin/env python3
"""Fix trace and trig titles with exact byte patterns."""

from pathlib import Path

files_to_fix = [
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trace.html'),
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trig.html'),
]

for file_path in files_to_fix:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # The pattern is: — " — (em-dash, right double quote, space, em-dash)
    # We want to replace it with just: —

    # Replace em-dash + right-double-quote + space + em-dash with single em-dash
    bad = '— " —'  # em-dash, quote, space, em-dash
    good = ' —'

    if bad in content:
        content = content.replace(bad, good)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[FIXED] {file_path.name}")
    else:
        # Try alternative pattern
        print(f"[CHECK] {file_path.name}")

print("\n[OK] Done")
