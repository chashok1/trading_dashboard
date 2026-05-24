#!/usr/bin/env python3
"""Fix extra quote characters in HTML titles."""

from pathlib import Path

web_dir = Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web')

fixes = {
    'cockpit.html': ('Action Cockpit —" Trading Dashboard', 'Action Cockpit — Trading Dashboard'),
    'actionable.html': ('Actionable Stocks —" Trading Dashboard', 'Actionable Stocks — Trading Dashboard'),
    'rule_performance.html': ('Rule Performance —" Trading Dashboard', 'Rule Performance — Trading Dashboard'),
    'dbstats.html': ('Database Stats —" Trading Dashboard', 'Database Stats — Trading Dashboard'),
}

for filename, (bad_title, good_title) in fixes.items():
    file_path = web_dir / filename

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if bad_title in content:
        content = content.replace(bad_title, good_title)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[FIXED] {filename}")
    else:
        print(f"[OK] {filename} already fixed")

print("\n[OK] All titles fixed")
