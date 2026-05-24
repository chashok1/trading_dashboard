#!/usr/bin/env python3
"""Fix double dashes using regex."""

import re
from pathlib import Path

files_to_fix = [
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trace.html'),
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trig.html'),
]

for file_path in files_to_fix:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find title and fix any double dashes or corrupted patterns
    # Pattern: <title>SomeText [dashes/chars] — Trading Dashboard</title>
    pattern = r'<title>(.+?)[—\-"]+\s*—\s*Trading Dashboard</title>'
    match = re.search(pattern, content)

    if match:
        title_text = match.group(1).strip()
        new_title = f'<title>{title_text} — Trading Dashboard</title>'
        content = re.sub(pattern, new_title, content)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[FIXED] {file_path.name}")
    else:
        print(f"[CHECK] {file_path.name} - no match")

print("\n[OK] Done")
