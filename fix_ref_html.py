#!/usr/bin/env python3
"""Fix corrupted characters in ref.html."""

file_path = r'C:\Ashok\Invest\Projects\trading-dashboard\web\ref.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix all corrupted characters
fixed = False
for i, line in enumerate(lines):
    if '<title>' in line and 'Ref Table Maintenance' in line:
        lines[i] = '    <title>Ref Table Maintenance — Trading Dashboard</title>\n'
        print(f"Fixed title on line {i+1}")
        fixed = True
    elif 'prevBtn' in line and 'Previous' in line:
        lines[i] = '                <button id="prevBtn">← Previous</button>\n'
        print(f"Fixed prevBtn on line {i+1}")
        fixed = True
    elif 'nextBtn' in line and 'Next' in line:
        lines[i] = '                <button id="nextBtn">Next →</button>\n'
        print(f"Fixed nextBtn on line {i+1}")
        fixed = True

if fixed:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('[OK] Fixed corrupted characters in ref.html')
else:
    print('[INFO] No corrupted characters found in ref.html')
