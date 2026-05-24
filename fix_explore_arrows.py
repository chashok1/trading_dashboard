#!/usr/bin/env python3
"""Fix corrupted arrow characters in explore.html."""

file_path = r'C:\Ashok\Invest\Projects\trading-dashboard\web\explore.html'

# Read file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace corrupted sequences with proper Unicode arrows
# Using raw bytes/escape sequences
replacements = {
    'â†': '←',  # â† -> ←
}

# Also try direct string replacements
content = content.replace('Prev</button>', 'Prev</button>', 1)  # placeholder
lines = content.split('\n')
fixed_lines = []

for line in lines:
    if 'inlinePrevBtn' in line and 'Prev' in line:
        # Replace the button text
        line = '                    <button id="inlinePrevBtn">← Prev</button>'
    elif 'inlineNextBtn' in line and 'Next' in line:
        line = '                    <button id="inlineNextBtn">Next →</button>'
    elif 'prevBtn' in line and 'Previous' in line:
        line = '                <button id="prevBtn">← Previous</button>'
    elif 'nextBtn' in line and 'Next' in line and 'Previous' not in line:
        line = '                <button id="nextBtn">Next →</button>'
    fixed_lines.append(line)

content = '\n'.join(fixed_lines)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] Fixed arrow characters in explore.html')
