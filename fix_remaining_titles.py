#!/usr/bin/env python3
"""Fix remaining title issues in all HTML files."""

import re
from pathlib import Path

web_dir = Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web')

# Get all HTML files
html_files = list(web_dir.glob('*.html'))

fixed_count = 0

for file_path in sorted(html_files):
    with open(file_path, 'r', encoding='utf-8') as f:
        original = f.read()

    # Replace any title with pattern: <title>.*[^a-zA-Z0-9]+ Trading Dashboard</title>
    # that has extra characters after dashes
    pattern = r'<title>(.*?)[\s–—-]+["\s]*Trading Dashboard</title>'
    match = re.search(pattern, original)

    if match:
        title_content = match.group(1).strip()
        # Build proper title: content — Trading Dashboard
        new_title = f'<title>{title_content} — Trading Dashboard</title>'
        content = re.sub(pattern, new_title, original)

        if content != original:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[FIXED] {file_path.name}")
            fixed_count += 1

print(f"\n[OK] Fixed {fixed_count} files")
