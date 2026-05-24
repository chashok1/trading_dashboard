#!/usr/bin/env python3
"""Fix titles by direct byte replacement."""

from pathlib import Path

files = {
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trace.html'): b'Symbol Trace',
    Path(r'C:\Ashok\Invest\Projects\trading-dashboard\web\trig.html'): b'Trigger Rules',
}

for file_path, title_name in files.items():
    with open(file_path, 'rb') as f:
        content = f.read()

    # Find and replace the title
    # Pattern: <title>NAME [corrupt] Trading Dashboard</title>
    title_start = content.find(b'<title>' + title_name)
    title_end = content.find(b'</title>', title_start)

    if title_start >= 0 and title_end >= 0:
        # Extract the part to replace
        old_title = content[title_start:title_end+8]

        # Create new title (using UTF-8 encoded em-dash: \xe2\x80\x94)
        if b'Symbol Trace' in title_name:
            new_title = b'<title>Symbol Trace \xe2\x80\x94 Trading Dashboard</title>'
        else:
            new_title = b'<title>Trigger Rules \xe2\x80\x94 Trading Dashboard</title>'

        # Replace
        content = content[:title_start] + new_title + content[title_end+8:]

        with open(file_path, 'wb') as f:
            f.write(content)

        print(f"[FIXED] {file_path.name}")
    else:
        print(f"[ERROR] {file_path.name} - title not found")

print("\n[OK] Done")
