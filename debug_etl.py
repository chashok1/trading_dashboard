from config.settings import settings
from sqlalchemy import create_engine, text, inspect

engine = create_engine(settings.sqlalchemy_url)
inspector = inspect(engine)

print('meta_etl_run columns:')
for col in inspector.get_columns('meta_etl_run'):
    print(f'  {col["name"]}: {col["type"]}')

print('\nLast 5 ETL runs:')
with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM meta_etl_run ORDER BY started_at DESC LIMIT 5'))
    for row in result:
        print(f'  {row}')

print('\nLast 5 Derivations:')
with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM meta_derived_run ORDER BY started_at DESC LIMIT 5'))
    for row in result:
        print(f'  {row}')
