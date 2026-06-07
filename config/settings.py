"""
Central settings - loads from .env via pydantic-settings.
Never hardcodes the password; reads PG_PASSWORD from environment.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Postgres
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "trading"
    pg_user: str = "postgres"
    pg_password: str = ""

    # Files / paths
    tickers_file: str = ""
    loadfiles_file: str = ""
    etl_working_dir: str = str(PROJECT_ROOT / "etl" / "working")

    # Retention
    default_retention_days: int = 365

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Notifications (optional; all default to off / unconfigured)
    notify_toast: bool = False           # Windows toast on load/error
    notify_email: bool = False           # SMTP notifications
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email_to: str = ""

    # Macro feed (FRED) — free API key from
    # https://fred.stlouisfed.org/docs/api/api_key.html
    fred_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def sqlalchemy_url(self) -> str:
        # psycopg (v3) driver URL
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


settings = Settings()
