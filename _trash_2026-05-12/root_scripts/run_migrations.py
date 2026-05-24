#!/usr/bin/env python
"""Run database migrations in order."""
from config.settings import settings
from sqlalchemy import text, create_engine
from pathlib import Path
import re

engine = create_engine(settings.sqlalchemy_url)

def remove_comments(sql):
    """Remove SQL comments (-- style)."""
    lines = []
    for line in sql.split('\n'):
        # Find comment start
        comment_idx = line.find('--')
        if comment_idx >= 0:
            line = line[:comment_idx]
        if line.strip():
            lines.append(line)
    return '\n'.join(lines)

def split_sql_statements(sql):
    """Split SQL into statements, handling dollar-quoted strings."""
    statements = []
    current = []
    in_dollar_quote = False
    dollar_quote = None
    i = 0

    while i < len(sql):
        # Check for dollar quote start/end
        if sql[i:i+1] == '$':
            j = i + 1
            while j < len(sql) and sql[j] not in ('$', ' ', '\n'):
                j += 1
            if j < len(sql) and sql[j] == '$':
                potential_quote = sql[i:j+1]
                if not in_dollar_quote:
                    dollar_quote = potential_quote
                    in_dollar_quote = True
                    i = j + 1
                    current.append(potential_quote)
                    continue
                elif potential_quote == dollar_quote:
                    in_dollar_quote = False
                    dollar_quote = None
                    i = j + 1
                    current.append(potential_quote)
                    continue

        # Check for statement end (;)
        if sql[i] == ';' and not in_dollar_quote:
            current.append(';')
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(sql[i])

        i += 1

    # Add any remaining statement
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements

migrations = [
    "db/26_etf_outlook.sql",
    "db/27_etf_use_hist.sql",
    "db/28_drop_ssl_sss.sql"
]

for mig_file in migrations:
    print(f"\n{'='*60}")
    print(f"Running {mig_file}...")
    print('='*60)

    try:
        sql_content = Path(mig_file).read_text(encoding='utf-8')

        # Remove comments
        sql_content = remove_comments(sql_content)

        # Split by statements (handle dollar-quoted strings)
        statements = split_sql_statements(sql_content)

        for stmt in statements:
            if stmt.strip():
                print(f"Executing: {stmt[:60]}...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text(stmt))
                except Exception as e:
                    # Skip IF EXISTS or table not found errors
                    if "does not exist" in str(e) or "undefined" in str(e).lower():
                        print(f"  [SKIP] Table does not exist, skipping...")
                    else:
                        raise

        print(f"[OK] {mig_file} completed successfully")
    except Exception as e:
        print(f"[ERROR] {mig_file}: {e}")
        raise

print(f"\n{'='*60}")
print("[OK] All migrations completed successfully")
print('='*60)
