"""
Configuration for the Hedgeye feed pipeline.

All tunables live in ref_settings (DB) with .env fallback for secrets, so the
LLM model and email provider are swappable without code changes. Defaults here
keep the deterministic pipeline runnable with the LLM lane OFF.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from sqlalchemy import text
    from etl.db import session_scope
except Exception:  # importable in pure-test contexts without a DB
    session_scope = None
    text = None


# ref_settings keys (created by db/seeds_hedgeye.sql) -------------------------
KEYS = {
    "enabled": "hedgeye_enabled",
    "poll_sec": "hedgeye_poll_interval_sec",
    "poll_morning_sec": "hedgeye_poll_interval_morning_sec",
    "poll_biz_sec": "hedgeye_poll_interval_biz_sec",
    "poll_off_sec": "hedgeye_poll_interval_off_sec",
    "poll_morning_start_min": "hedgeye_poll_morning_start_min",
    "poll_morning_end_min": "hedgeye_poll_morning_end_min",
    "poll_biz_end_min": "hedgeye_poll_biz_end_min",
    "provider": "hedgeye_email_provider",          # imap | gmail_api
    "imap_host": "hedgeye_imap_host",
    "imap_user": "hedgeye_imap_user",
    "mailbox": "hedgeye_mailbox",                  # default INBOX
    "image_dir": "hedgeye_image_dir",              # configurable archive folder
    "hefiles_dir": "hedgeye_hefiles_dir",          # HEFiles output directory
    "msr_dir": "hedgeye_msr_dir",                  # MSR image archive (30-day rolling)
    # optional LLM enrichment (off by default)
    "llm_enabled": "hedgeye_llm_enabled",
    "llm_provider": "hedgeye_llm_provider",
    "llm_endpoint": "hedgeye_llm_endpoint",        # set for local/self-hosted
    "llm_model": "hedgeye_llm_model",
    "llm_prompt_version": "hedgeye_llm_prompt_version",
    "llm_cost_cap": "hedgeye_llm_cost_cap",
}

DEFAULTS = {
    "enabled": "false",
    "poll_sec": "900",
    "poll_morning_sec": "300",
    "poll_biz_sec": "900",
    "poll_off_sec": "3600",
    "poll_morning_start_min": "360",
    "poll_morning_end_min": "630",
    "poll_biz_end_min": "960",
    "provider": "imap",
    "mailbox": "INBOX",
    "image_dir": "etl/working/hedgeye_charts",
    "hefiles_dir": r"C:\Ashok\Investing\Stocks\HEFiles",
    "msr_dir": r"C:\Ashok\Investing\Stocks\MSR",
    "llm_enabled": "false",
}

# secrets come from .env only (never ref_settings)
SECRET_ENV = {
    "imap_password": "HEDGEYE_IMAP_PASSWORD",
    "gmail_token": "HEDGEYE_GMAIL_TOKEN",
    "llm_api_key": "HEDGEYE_LLM_API_KEY",
}


@dataclass
class Settings:
    enabled: bool
    poll_sec: int
    provider: str
    imap_host: Optional[str]
    imap_user: Optional[str]
    imap_password: Optional[str]
    mailbox: str
    image_dir: str
    hefiles_dir: str
    msr_dir: str
    llm_enabled: bool


def _get(name: str) -> Optional[str]:
    if session_scope is None:
        return None
    try:
        with session_scope() as s:
            return s.execute(
                text("SELECT setting_value FROM ref_settings WHERE setting_name=:k"),
                {"k": name},
            ).scalar()
    except Exception:
        return None


def get(key: str) -> Optional[str]:
    val = _get(KEYS.get(key, key))
    if val is None:
        val = DEFAULTS.get(key)
    return val


def secret(key: str) -> Optional[str]:
    return os.environ.get(SECRET_ENV.get(key, key))


def load() -> Settings:
    return Settings(
        enabled=(get("enabled") or "false").lower() == "true",
        poll_sec=int(get("poll_sec") or 240),
        provider=get("provider") or "imap",
        imap_host=get("imap_host"),
        imap_user=get("imap_user"),
        imap_password=secret("imap_password"),
        mailbox=get("mailbox") or "INBOX",
        image_dir=get("image_dir") or DEFAULTS["image_dir"],
        hefiles_dir=get("hefiles_dir") or DEFAULTS["hefiles_dir"],
        msr_dir=get("msr_dir") or DEFAULTS["msr_dir"],
        llm_enabled=(get("llm_enabled") or "false").lower() == "true",
    )
