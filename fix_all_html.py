#!/usr/bin/env python3
"""Fix corrupted characters in all HTML files."""

import glob
from pathlib import Path

web_dir = Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web')
html_files = list(web_dir.glob('*.html'))

print(f"Processing {len(html_files)} HTML files...\n")

# Track changes
changes_made = {}

for file_path in html_files:
    with open(file_path, 'r', encoding='utf-8') as f:
        original_content = f.read()

    content = original_content
    file_changes = []

    # Replace corrupted em-dash
    if 'â€' in content:
        content = content.replace('â€', '—')
        file_changes.append('em-dash')

    # Replace corrupted left arrow
    if 'â†' in content:
        content = content.replace('â†', '←')
        file_changes.append('left-arrow')

    # Replace corrupted right arrow (with various encoding issues)
    if 'â†' in content:
        # Try to replace the right arrow variant
        content = content.replace('â†', '→')
        if 'â†' not in content:
            file_changes.append('right-arrow')

    # Write back if changes were made
    if file_changes:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        changes_made[file_path.name] = file_changes
        print(f"[OK] {file_path.name}: {', '.join(file_changes)}")

if changes_made:
    print(f'\n[OK] Fixed {len(changes_made)} files')
else:
    print('[INFO] No corrupted characters found')
