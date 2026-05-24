#!/usr/bin/env python3

# Read as binary
with open('web/portfolio.html', 'rb') as f:
    content = f.read()

# UTF-8 encoded quote characters:
# Left double quote (U+201C) = b'\xe2\x80\x9c'
# Right double quote (U+201D) = b'\xe2\x80\x9d'
# Left single quote (U+2018) = b'\xe2\x80\x98'
# Right single quote (U+2019) = b'\xe2\x80\x99'

# Replace with ASCII straight quotes (byte 34 = ")
content = content.replace(b'\xe2\x80\x9c', b'"')  # Left double
content = content.replace(b'\xe2\x80\x9d', b'"')  # Right double
content = content.replace(b'\xe2\x80\x98', b"'")  # Left single
content = content.replace(b'\xe2\x80\x99', b"'")  # Right single

# Write back as binary
with open('web/portfolio.html', 'wb') as f:
    f.write(content)

print('Fixed all Unicode quotes to ASCII')
