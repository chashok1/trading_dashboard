#!/usr/bin/env python3
import sys

# Read the HTML file
with open('web/portfolio.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Unicode curly quotes with ASCII straight quotes
# Left double quote (U+201C) -> "
# Right double quote (U+201D) -> "
# Left single quote (U+2018) -> '
# Right single quote (U+2019) -> '
fixed = content.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

# Write back
with open('web/portfolio.html', 'w', encoding='utf-8') as f:
    f.write(fixed)

print('Fixed: Replaced Unicode curly quotes with ASCII straight quotes')
