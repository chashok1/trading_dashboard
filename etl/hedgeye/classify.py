"""
Deterministic, no-LLM classifier — maps a Hedgeye email to its type/destination.

Classification keys (any one works; combined for robustness):
  1. subject regex
  2. header banner image asset name  (Email.header_asset)
  3. hedgeye-stock-symbols meta tag

This table mirrors how LoadFiles.xlsx drives the file loader: adding a future
Hedgeye product = one new EmailType row, no engine change. Unknown research
emails are never dropped — they fall through to UNKNOWN and are stored as a
note + flagged for review (see runner/dispatch).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .parsers import Email, PARSERS

RESEARCH_SENDER = "info@hedgeye.com"     # research; carries the Hedgeye label
MARKETING_SENDER = "hedgeye@hedgeye.com"  # promos -> drop


@dataclass(frozen=True)
class EmailType:
    name: str
    destination: str          # DATA | ANALYSIS | RULES | DROP | UNKNOWN
    cadence: str              # daily | intraday | weekly | monthly | quarterly | adhoc
    subject_re: Optional[str] = None
    asset: Optional[str] = None
    parser: Optional[str] = None   # key into parsers.PARSERS


# Order matters: most specific first. DROP rules sit early to short-circuit.
EMAIL_TYPES: list[EmailType] = [
    # ---- DROP ---------------------------------------------------------------
    EmailType("the_call_access", "DROP", "daily",
              subject_re=r"^The Call @ Hedgeye \| Access Here"),
    EmailType("momo_tracker", "DROP", "daily", subject_re=r"^MOMO Tracker"),
    EmailType("macro_show_access", "ANALYSIS", "daily",
              subject_re=r"^THE MACRO SHOW:.*Access Show", parser="macro_show_top3"),

    # ---- DATA ---------------------------------------------------------------
    EmailType("risk_range", "DATA", "daily",
              subject_re=r"^RISK RANGE.*SIGNALS", parser="risk_range"),
    EmailType("real_time_alert", "DATA", "intraday",
              subject_re=r"Real-Time Alert", asset="stock_alerts_800px.png",
              parser="real_time_alert"),
    EmailType("etf_weekly", "DATA", "weekly",
              subject_re=r"ETF Pro Plus.*New Weekly Report",
              parser="etf_weekly"),
    EmailType("etf_changes", "DATA", "intraday",
              subject_re=r"ETF Pro Change", asset="etf_pro_plus_1_800px.png",
              parser="etf_changes"),
    EmailType("ii_weekly", "DATA", "weekly",
              subject_re=r"Investing Ideas Newsletter",
              parser="ii_weekly"),
    EmailType("investing_ideas", "DATA", "intraday",
              subject_re=r"^(Add|Remove)\b.*\b(LONG|SHORT) Side",
              asset="investing_ideas_800px.png", parser="investing_ideas"),
    EmailType("signal_strength", "DATA", "intraday",
              subject_re=r"^Signal Strength Stocks", asset="signal_strength_stocks_800px.png",
              parser="signal_strength"),
    EmailType("portfolio_solutions", "DATA", "weekly",
              subject_re=r"^PORTFOLIO SOLUTIONS.*Re-Rank", parser="portfolio_solutions"),
    EmailType("the_call", "DATA", "daily",
              subject_re=r"^The Call @ Hedgeye \| Replay", parser="the_call"),
    EmailType("macro_show_summary", "DATA", "daily",
              subject_re=r"^THE MACRO SHOW:.*Summary Notes", parser="macro_show_summary"),
    EmailType("inflation_nowcast", "DATA", "monthly",
              subject_re=r"Monthly Inflation Nowcast", asset="macro_select_800px.png",
              parser="inflation_nowcast"),

    # ---- ANALYSIS / RULES ---------------------------------------------------
    EmailType("early_look", "ANALYSIS", "daily",
              subject_re=r"^EARLY LOOK", parser="early_look"),
    EmailType("market_situation", "ANALYSIS", "daily",
              subject_re=r"^MARKET SITUATION REPORT", asset="market_situation_report_800px.png",
              parser="market_situation"),
    EmailType("top3", "ANALYSIS", "daily",
              subject_re=r"Top 3 Things", parser=None),  # note-only
    EmailType("macro_week_summary", "ANALYSIS", "weekly",
              subject_re=r"^Macro Week Summary Notes", parser=None),  # TOC + link → note-only
    EmailType("quarterly_outlook", "RULES", "quarterly",
              subject_re=r"Quarterly Investment Outlook", parser="quarterly_outlook"),
]

UNKNOWN = EmailType("unknown", "UNKNOWN", "adhoc")


def classify(email: Email) -> EmailType:
    """Return the matching EmailType, or UNKNOWN. Marketing sender -> DROP."""
    sender = (email.sender or "").lower()
    if MARKETING_SENDER in sender and RESEARCH_SENDER not in sender:
        return EmailType("marketing", "DROP", "adhoc")

    subj = email.subject or ""
    asset = email.header_asset
    for et in EMAIL_TYPES:
        if et.subject_re and re.search(et.subject_re, subj, re.I):
            return et
        if et.asset and asset and et.asset == asset:
            return et
    return UNKNOWN


def parser_for(et: EmailType):
    return PARSERS.get(et.parser) if et.parser else None
