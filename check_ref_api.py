from config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.sqlalchemy_url)

# List ref tables
with engine.connect() as conn:
    result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'ref_%' LIMIT 3"))
    tables = [r[0] for r in result]
    print('Available ref tables:')
    for t in tables:
        print(f'  - {t}')

# Try to count rows in a ref table
if tables:
    table = tables[0]
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
        count = result.scalar()
        print(f'\n{table}: {count} rows')

# Check if the API ref endpoint would work
print('\nChecking API /api/ref/tables endpoint...')
try:
    from api.routers.ref import list_ref_tables
    tables_list = list_ref_tables()
    print(f'API returned {len(tables_list)} ref tables')
    if tables_list:
        print(f'First table: {tables_list[0]}')
except Exception as e:
    print(f'API error: {e}')
