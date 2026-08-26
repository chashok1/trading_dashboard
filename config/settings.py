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
    # 2026-08-18, user-directed relocation: watchlist_base_dir is the single
    # reference point both other paths below hang off of -- read by
    # TOSDownloads/LoadWatchlists.py + ImportAdditions.py, which run from
    # this same machine but a separate location (outside this repo, same
    # convention as tickers_file/loadfiles_file above).
    # 2026-08-24, user-directed re-layout: base dir dropped "TOS " from its
    # name (now shared by TOS + per-account + Yahoo output, not TOS-only);
    # the old TOS-specific files + lists dirs moved one level down under a
    # new TOS/ subfolder so they sit alongside the new Accounts/TOS and
    # Accounts/Y dirs below.
    watchlist_base_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists"
    # WL<n>.csv + overflow.csv (etl/generate_watchlist_files.py) -- the full
    # per-watchlist symbol files LoadWatchlists.py imports.
    watchlist_files_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\TOS\Watchlists"
    # additions.csv + removals.csv -- the two housekeeping worklists, one
    # level up from watchlist_files_dir (user: "so it can be used for both
    # full list and additions and removals").
    watchlist_lists_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\TOS"
    # 2026-08-24: per-account watchlist output (nightly, all accounts), TOS
    # and Yahoo formats, both nested under watchlist_base_dir\Accounts.
    account_tos_watch_lists_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\Accounts\TOS"
    account_y_watch_lists_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\Accounts\Y"
    # 2026-08-24: per-source watchlist output (PS/ETF/II/RR/CALL/SSS), TOS
    # and Yahoo formats, both nested under watchlist_base_dir\Sources.
    source_tos_watch_lists_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\Sources\TOS"
    source_y_watch_lists_dir: str = r"C:\Ashok\Investing\Stocks\Watchlists\Sources\Y"

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
    # Own pydantic field (not etl/hedgeye/config.py's os.environ-based
    # secret()) so it's read straight from .env regardless of whether that
    # module's lazy load_dotenv() has run yet in this process -- see
    # model_post_init below ("use the same key for password").
    hedgeye_imap_password: str = ""

    # Macro feed (FRED) — free API key from
    # https://fred.stlouisfed.org/docs/api/api_key.html
    fred_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        # 2026-08-25, user-directed: "use the same key for password" --
        # SMTP_PASSWORD reuses HEDGEYE_IMAP_PASSWORD's value if SMTP_PASSWORD
        # itself is unset, so the Gmail App Password only has to be stored
        # once in .env. Gmail App Passwords aren't scoped per protocol --
        # the same one authenticates IMAP and SMTP for that account.
        if not self.smtp_password:
            self.smtp_password = self.hedgeye_imap_password

    @property
    def sqlalchemy_url(self) -> str:
        # psycopg (v3) driver URL
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


settings = Settings()
