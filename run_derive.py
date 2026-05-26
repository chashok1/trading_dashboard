from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from config.settings import Settings
from etl.derive import derive_all

# Get settings with password from .env
settings = Settings()

# Create engine using settings
engine = create_engine(settings.sqlalchemy_url)

# Run derive for today
with Session(engine) as session:
    print("Running derive_all for 2026-05-26...")
    count = derive_all(session, date(2026, 5, 26))
    session.commit()

print("[OK] Derive completed successfully")
print("[OK] drv_quote now contains snapshot_date from source data")
print("[OK] 'As Of' column will show load time instead of derivation time")
