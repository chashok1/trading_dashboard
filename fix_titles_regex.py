#!/usr/bin/env python3
"""Fix title issues using regex to handle any character variants."""

import re
from pathlib import Path

web_dir = Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web')

files_to_fix = [
    ('cockpit.html', 'Action Cockpit'),
    ('actionable.html', 'Actionable Stocks'),
    ('rule_performance.html', 'Rule Performance'),
    ('dbstats.html', 'Database Stats'),
]

for filename, title_prefix in files_to_fix:
    file_path = web_dir / filename

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace title with pattern: prefix — [any char(s)] Trading Dashboard
    # Should become: prefix — Trading Dashboard
    pattern = f'<title>{title_prefix}.*?Trading Dashboard</title>'
    replacement = f'<title>{title_prefix} — Trading Dashboard</title>'

    new_content = re.sub(pattern, replacement, content)

    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[FIXED] {filename}")
    else:
        print(f"[OK] {filename} already correct")

print("\n[OK] All titles fixed")
