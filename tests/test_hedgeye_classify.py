"""Unit tests for etl/hedgeye/classify.py — pure-Python, no DB."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from etl.hedgeye.classify import classify
from etl.hedgeye.parsers import Email

TS = datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc)


def _e(subject, sender="info@hedgeye.com", html=""):
    return Email(message_id="<m@h>", subject=subject, sender=sender, received=TS,
                 plaintext="", html=html)


@pytest.mark.parametrize("subject,expected", [
    ("RISK RANGE SIGNALS: JUNE 26, 2026", "risk_range"),
    ("**Real-Time Alert: Van Sciver Sell Signal (ROP) -KM", "real_time_alert"),
    ("Add ResMed Inc. (RMD) to SHORT Side", "investing_ideas"),
    ("UPDATE: 2 New ETF Pro Changes", "etf_changes"),
    ("Signal Strength Stocks: 80 Stocks (2 Added, 2 Removed)", "signal_strength"),
    ("PORTFOLIO SOLUTIONS: Weekly ETF Re-Rank (6/26/2026)", "portfolio_solutions"),
    ("The Call @ Hedgeye | Replay & Summary | 6/26/2026", "the_call"),
    ("THE MACRO SHOW: Summary Notes & Replay | Friday", "macro_show_summary"),
    ("Macro Week Summary Notes | June 26th, 2026", "macro_week_summary"),
    ("Hedgeye Monthly Inflation Nowcast", "inflation_nowcast"),
    ("EARLY LOOK: #Bag7 Getting #Quad4'd", "early_look"),
    ("MARKET SITUATION REPORT: June 26th 2026", "market_situation"),
    ("Quarterly Investment Outlook | 3Q 2026", "quarterly_outlook"),
])
def test_classify_known(subject, expected):
    assert classify(_e(subject)).name == expected


def test_drop_marketing_sender():
    assert classify(_e("Ends Tonight – $5,001 Off Macro Pro",
                       sender="hedgeye@hedgeye.com")).destination == "DROP"


def test_drop_access_and_momo():
    assert classify(_e("The Call @ Hedgeye | Access Here | 6/26/2026")).destination == "DROP"
    assert classify(_e("MOMO Tracker | Bag7 (-2.5%)")).destination == "DROP"


def test_unknown_falls_through():
    et = classify(_e("Some Brand New Hedgeye Product We Have Not Seen"))
    assert et.name == "unknown" and et.destination == "UNKNOWN"


def test_classify_by_header_asset_when_subject_odd():
    html = ('<img src="https://x/email_assets/headers/sectors/'
            'stock_alerts_800px.png" />')
    assert classify(_e("weird subject", html=html)).name == "real_time_alert"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
