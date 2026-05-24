#!/usr/bin/env python3
"""Fix corrupted em-dash in explore.html title."""

file_path = r'C:\Ashok\Invest\Projects\trading-dashboard\web\explore.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix the title line
for i, line in enumerate(lines):
    if '<title>' in line and 'Explore' in line:
        lines[i] = '    <title>Explore — Trading Dashboard</title>\n'
        print(f"Fixed title on line {i+1}")

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('[OK] Fixed title characters in explore.html')
