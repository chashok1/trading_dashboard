#!/usr/bin/env python3
"""Fix all corrupted UTF-8 characters in HTML files."""

import glob
from pathlib import Path

web_dir = Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web')
html_files = list(web_dir.glob('*.html'))

print(f"Processing {len(html_files)} HTML files...\n")

# Map of corrupted sequences to proper characters
replacements = {
    'â€': '—',      # em-dash
    'â†': '←',      # left arrow
    'âœ•': 'x',     # close button - simple x
}

total_fixes = 0

for file_path in sorted(html_files):
    with open(file_path, 'r', encoding='utf-8') as f:
        original = f.read()

    content = original
    fixes = []

    for bad, good in replacements.items():
        if bad in content:
            content = content.replace(bad, good)
            fixes.append(bad)
            total_fixes += 1

    if fixes:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[FIXED] {file_path.name}")

print(f"\n[OK] Fixed {total_fixes} corrupted sequences across {len(html_files)} files")
