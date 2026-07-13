"""
Unit tests for etl/hedgeye/parsers.py — pure-Python, no DB, no network.
Fixtures are trimmed from the real 26-Jun-2026 Hedgeye emails.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from etl.hedgeye.parsers import (
    Email, parse_risk_range, parse_real_time_alert, parse_investing_ideas,
    parse_etf_changes, parse_signal_strength, parse_portfolio_solutions,
    parse_macro_show_summary, parse_the_call, parse_early_look,
    parse_market_situation, parse_inflation_nowcast, parse_quarterly_outlook,
    parse_macro_show_top3,
)

TS = datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc)


def _email(subject, plaintext, html="", sender="info@hedgeye.com", mid="<x@h>"):
    return Email(message_id=mid, subject=subject, sender=sender, received=TS,
                 plaintext=plaintext, html=html)


def test_risk_range():
    pt = (
        "06/26/2026 07:34 AM EDT RISK RANGE SIGNALS: JUNE 26, 2026\n\n"
        "TREND CHANGE:\nAAPL changed from Bullish to Bearish\n\n"
        "SPX (BULLISH)\nS&P 500 7,286 7,568 7,357\n\n"
        "XLK (NEUTRAL)\nTechnology Select Sector SPDR Fund 177 192 185\n\n"
        "AAPL (BEARISH)\nApple Inc. 270 293 275\n\n"
        "BITCOIN (BEARISH)\nBitcoin Spot Price 58,138 62,557 59,806 #OUTBUCKET\n"
        "XAR = Bullish (6/24/2026)\n"
    )
    p = parse_risk_range(_email("RISK RANGE SIGNALS: JUNE 26, 2026", pt))
    rr = p.tables["hist_rr"]
    assert len(rr) == 4                       # OutBucket line excluded
    spx = next(r for r in rr if r["symbol"] == "SPX")
    assert spx["outlook"] == "BULLISH"
    assert spx["buy_trade"] == 7286 and spx["sell_trade"] == 7568 and spx["last_price"] == 7357
    assert any("trend_change_printed" in w for w in p.warnings)


def test_rta_action():
    subj = "**Real-Time Alert: Van Sciver Sell Signal (#Quad4 Shorts): Roper (ROP) -KM"
    pt = (
        "06/26/2026 01:14 PM EDT\nshort SELL SIGNAL - SHORTING ROP $339.80\n\n"
        "Roper Technologies Inc.\nBeen waiting to start adding #Quad4 Shorts...\n\n"
        "Coaching Notes:\n\nGetting the greenlight today\n\nFirst man up was THC and now ROP\n\nKM\n\n"
        "Durations\ntrade trend tail\n"
    )
    p = parse_real_time_alert(_email(subj, pt))
    r = p.tables["hist_rta"][0]
    assert r["action"] == "SHORT" and r["symbol"] == "ROP" and r["price"] == 339.80
    assert r["side"] == "short" and r["analyst"] == "Van Sciver" and r["signal_kind"] == "Sell"
    assert r["dur_trade"] and r["dur_trend"] and r["dur_tail"]
    # intro prose before "Coaching Notes:" is captured too, company-name line dropped
    assert r["coaching_notes"].startswith("Been waiting to start adding #Quad4 Shorts...")
    assert "Roper Technologies Inc." not in r["coaching_notes"]
    assert "greenlight" in (r["coaching_notes"] or "")
    assert p.notes and p.notes[0]["source_type"] == "rta_coaching"


def test_rta_intro_text_no_coaching_list():
    # Real Jul-6-2026 URI alert shape: intro question, then a "Coaching
    # Notes:" ordered list with no numbering markers in plaintext.
    subj = "**Real-Time Alert: Van Sciver Buy Signal (Investable Bucket): United Rentals (URI) -KM"
    pt = (
        "07/06/2026 10:51 AM EDT\nlong   BUY SIGNAL URI $1,089.81\n\n"
        "United Rentals Inc.\n"
        "Looking for Longs with the VIX back in what we call The Investable Bucket?\n\n"
        "Coaching Notes:\n\n"
        "I'll I've sent you today are cover and buy signals, so directionally I am\n\n"
        "This \"bucket\" or regime for US stock market volatility is not friendly to bears\n\n"
        "We have 83 Signal Strength Longs on that product list to pick from don't forget,\n\nKM\n\n"
        "Durations\ntrade trend tail\n"
    )
    p = parse_real_time_alert(_email(subj, pt))
    r = p.tables["hist_rta"][0]
    assert r["symbol"] == "URI" and r["action"] == "BUY" and r["price"] == 1089.81
    assert r["coaching_notes"].startswith(
        "Looking for Longs with the VIX back in what we call The Investable Bucket?")
    assert "Signal Strength Longs" in r["coaching_notes"]


def test_rta_correction():
    p = parse_real_time_alert(_email(
        "**Real-Time Alert: fat finger (was supposed to be a sell!)",
        "06/26/2026 01:22 PM EDT\nfat finger, disregard previous\n"))
    assert "correction" in p.flags
    assert p.tables["hist_rta"][0]["is_correction"] is True


def test_investing_ideas():
    p = parse_investing_ideas(_email(
        "Add ResMed Inc. (RMD) to SHORT Side",
        "We are ADDING the following to Investing Ideas:\n\nShort:\n\nRMD\n"))
    r = p.tables["hist_iichg"][0]
    assert r["action"] == "add" and r["side"] == "short" and r["symbol"] == "RMD"


def test_etf_changes():
    pt = ("We are REMOVING Long:\n\nQuantum Tech (QTUM) - (149.0 - 175.0)\n\n"
          "Cybersecurity (BUG) - (32.97 - 35.76)\n\nHow to Use ETF Pro Plus Updates:\n")
    p = parse_etf_changes(_email("UPDATE: 2 New ETF Pro Changes", pt))
    rows = p.tables["hist_etfchg"]
    assert {r["symbol"] for r in rows} == {"QTUM", "BUG"}
    assert all(r["action"] == "remove" and r["side"] == "long" for r in rows)


def test_signal_strength():
    p = parse_signal_strength(_email(
        "Signal Strength Stocks: 80 Stocks (2 Added, 2 Removed)",
        "Added: RKT, BTI\n\nRemoved: ATZAF, RPBPF\n"))
    rows = p.tables["hist_sss_change"]
    assert len(rows) == 4
    assert {(r["action"], r["symbol"]) for r in rows} >= {("add", "RKT"), ("remove", "ATZAF")}


def test_portfolio_solutions_html_table():
    html = ("<table><tr><th>Rank</th><th>Ticker</th><th>1-Week Change</th></tr>"
            "<tr><td>1</td><td>FDRXX</td><td>0</td></tr>"
            "<tr><td>9</td><td>IAK</td><td>6</td></tr></table>")
    p = parse_portfolio_solutions(_email(
        "PORTFOLIO SOLUTIONS: Weekly ETF Re-Rank (6/26/2026)", "", html))
    rows = p.tables["hist_ps"]
    assert len(rows) == 2
    iak = next(r for r in rows if r["ticker"] == "IAK")
    assert iak["rank"] == 9


def test_macro_show_summary():
    pt = (
        "TL;DR - POSITIONS MENTIONED\n"
        "BULLISH: Health Care (XLV), Long-Duration Bonds (TLT), Japan, U.S. Dollar (USD)\n"
        "BEARISH: Bitcoin, Apple (AAPL), Gold\n\n"
        "MAIN SUMMARY\nQuad 4 Was the Lead Signal. Keith said risk-off.\n"
    )
    p = parse_macro_show_summary(_email("THE MACRO SHOW: Summary Notes & Replay", pt))
    rows = p.tables["hist_hedgeye_stance"]
    xlv = next(r for r in rows if r["label"].startswith("Health Care"))
    assert xlv["stance"] == "BULLISH" and xlv["tos_symbol"] == "XLV"
    jp = next(r for r in rows if r["label"] == "Japan")
    assert jp["tos_symbol"] == "EWJ"
    btc = next(r for r in rows if r["label"] == "Bitcoin")
    assert btc["stance"] == "BEARISH" and btc["tos_symbol"] == "BTC"
    assert p.notes[0]["quad"] == 4


def test_the_call():
    pt = (
        "HEDGEYE POSITIONS\n"
        "LONGS: BJRI, MGM, HLT\nSHORTS: MSTR, MCD, THC\nNEUTRAL: FDXF\n\n"
        "Top 5 Most Actionable Stock Ideas\n\n"
        "(Positioning based on Hedgeye Macro Signals and Signal Strength)\n\n"
        "BJ's Restaurants, Inc. (BJRI): One of the few showing comp acceleration.\n\n"
        "MGM Resorts International (MGM): Favorable transaction math.\n\n"
        "Hilton Worldwide Holdings Inc. (HLT): Solid RevPAR setup.\n"
    )
    p = parse_the_call(_email("The Call @ Hedgeye | Replay & Summary | 6/26/2026", pt))
    call = p.tables["hist_call"]
    assert {"BJRI", "MGM", "HLT"} <= {r["symbol"] for r in call}
    mstr = next(r for r in call if r["symbol"] == "MSTR")
    assert mstr["outlook"] == "BEARISH"
    top = p.tables["hist_call_top5"]
    assert [r["symbol"] for r in top] == ["BJRI", "MGM", "HLT"]
    assert top[0]["side"] == "long" and top[0]["rank"] == 1
    assert "acceleration" in top[0]["rationale_snippet"]


def test_the_call_grouped_ticker_commentary():
    # Commentary paragraphs sometimes group two+ names under one colon, e.g.
    # "Conagra Brands, Inc. (CAG) / Campbell Soup Company (CPB): text…" — each
    # ticker in the header must still get the shared commentary, not be dropped.
    pt = (
        "HEDGEYE POSITIONS\n"
        "LONGS: BJRI, MGM, HLT, EAT, SJM\nSHORTS: CAG, CPB\nNEUTRAL: FDXF\n\n"
        "Top 5 Most Actionable Stock Ideas\n\n"
        "(Positioning based on Hedgeye Macro Signals and Signal Strength)\n\n"
        "BJ's Restaurants, Inc. (BJRI): One of the few showing comp acceleration.\n\n"
        "MGM Resorts International (MGM): Favorable transaction math.\n\n"
        "Hilton Worldwide Holdings Inc. (HLT): Solid RevPAR setup.\n\n"
        "Brinker International, Inc. (EAT): Accelerating comp on the quarter.\n\n"
        "The J. M. Smucker Company (SJM): Newest long idea in Staples.\n\n"
        "Conagra Brands, Inc. (CAG) / Campbell Soup Company (CPB): Stated as moved off "
        "the short list due to pods and quads; respond better to lower interest rates; "
        "note: the position monitor still lists both on the Short Bench.\n\n"
        "Moody’s Corporation (MCO), S&P Global Inc. (SPGI), TransUnion (TRU): Rotated "
        "more favorably toward the bench / long-bench side; long.\n"
    )
    p = parse_the_call(_email("The Call @ Hedgeye | Replay & Summary | 7/6/2026", pt))
    commentary = [n for n in p.notes if n["source_type"] == "the_call_commentary"]
    cag_cpb = next(n for n in commentary if set(n["tickers"]) == {"CAG", "CPB"})
    assert "pods and quads" in cag_cpb["note_text"]
    mco_group = next(n for n in commentary if set(n["tickers"]) == {"MCO", "SPGI", "TRU"})
    assert "Rotated more favorably" in mco_group["note_text"]


def test_early_look():
    pt = (
        "06/26/2026 07:49 AM EDT #Bag7 Getting #Quad4'd\n\n"
        "Key Takeaways\n\nRetail-favorite risk is already breaking, down -13.1%.\n\n"
        "Russell 2000 printed an all-time high while #Bag7 names signal Bearish TREND.\n\n"
        "The Big Picture\n\nFor some of us Canadian fighters...\n"
    )
    p = parse_early_look(_email("EARLY LOOK: #Bag7 Getting #Quad4'd", pt))
    note = p.notes[0]
    assert note["source_type"] == "early_look" and note["quad"] == 4
    assert "Retail-favorite" in note["note_text"]


def test_macro_show_top3_numbered():
    pt = (
        "07/02/2026 08:42 AM EDT THE MACRO SHOW: July 2nd - Access Show, Slide Deck & Top 3 Things\n\n"
        "click here to access today's show\n\n"
        "Hedgeye's top 3 things\n\n"
        "1) KOSPI – The Doctor is prescribing meds for the Levered Longs (SOXL)\n\n"
        "2) RATES – To be clear, the catalyst for Bond Yields to go up is that they went straight down\n\n"
        "3) QQQ – Like the KOSPI, QQQ bounced to lower-Cycle-highs #Quad4\n\n"
        "Immediate-term @Hedgeye Risk Ranges : SP500 = 7300-7553; UST 10yr Yield = 4.31-4.51%\n\nKM\n\n"
        "Please visit https://app.hedgeye.com/feed_items/184257 for more information.\n"
    )
    p = parse_macro_show_top3(_email(
        "THE MACRO SHOW: July 2nd - Access Show, Slide Deck & Top 3 Things", pt))
    note = p.notes[0]
    assert note["source_type"] == "macro_show_top3"
    assert note["note_text"].startswith("1) KOSPI –")
    assert "2) RATES –" in note["note_text"] and "3) QQQ –" in note["note_text"]
    assert "Immediate-term" not in note["note_text"]
    assert not p.warnings


def test_macro_show_top3_unnumbered():
    # Hedgeye doesn't always number the <ol><li> items in plaintext — bare
    # "LABEL – text" paragraphs must still parse (not fall back to subject).
    pt = (
        "07/06/2026 08:40 AM EDT THE MACRO SHOW: July 6th - Access Show, Slide Deck & Top 3 Things\n\n"
        "click here to access today's show\n\n"
        "Hedgeye's top 3 things\n\n"
        "Was that already it for #Quad4 in July? Definitely not for some big Macro things…\n\n"
        "USD – Post a Counter @Hedgeye TREND correction of -0.5% week-over-week\n\n"
        "GOLD – Lots of client questions on why I haven't gone back to Long Gold\n\n"
        "QQQ – Down KOSPI, up QQQ futures is interesting, KOSPI's immediate-term TRADE Signal Level 8321\n\n"
        "Immediate-term @Hedgeye Risk Ranges : SP500 = 7300-7553; UST 10yr Yield = 4.31-4.51%\n\nKM\n\n"
        "Please visit https://app.hedgeye.com/feed_items/184257 for more information.\n"
    )
    p = parse_macro_show_top3(_email(
        "THE MACRO SHOW: July 6th - Access Show, Slide Deck & Top 3 Things", pt))
    note = p.notes[0]
    assert note["source_type"] == "macro_show_top3"
    assert note["note_text"] != note["subject"]
    assert note["note_text"].startswith("1) USD –")
    assert "2) GOLD –" in note["note_text"]
    assert "3) QQQ –" in note["note_text"]
    assert "immediate-term TRADE Signal Level 8321" in note["note_text"]  # not truncated
    assert not p.warnings


def test_macro_show_top3_falls_back_with_warning():
    pt = "07/06/2026 08:40 AM EDT THE MACRO SHOW: no top-3 section here at all\n"
    p = parse_macro_show_top3(_email("THE MACRO SHOW: no top-3 section here at all", pt))
    note = p.notes[0]
    assert note["note_text"] == note["subject"]
    assert any("falling back to subject" in w for w in p.warnings)


def test_market_situation_images():
    html = ('<p><img class="chart" src="https://cdn/x/gamma.png?e=1"/></p>'
            '<p><img class="chart" src="https://cdn/x/constituents.png?e=1"/></p>')
    pt = ("06/26/2026 06:30 AM EDT MARKET SITUATION REPORT\n\n"
          "SPX positioning continues to point toward negative gamma, suggesting higher "
          "volatility is likely across the index today.\n\n-Craig Peterson\n")
    p = parse_market_situation(_email("MARKET SITUATION REPORT: June 26th 2026", pt, html))
    assert p.images == ["https://cdn/x/gamma.png?e=1", "https://cdn/x/constituents.png?e=1"]
    assert p.notes[0]["source_type"] == "market_situation"


def test_inflation_nowcast():
    pt = ("Our base-case nowcast for June is +3.85% y/y, reflecting a -40 bp sequential "
          "deceleration. June CPI Release Date:  July 14th\n")
    p = parse_inflation_nowcast(_email("Hedgeye Monthly Inflation Nowcast", pt))
    row = p.tables["hist_macro"][0]
    assert row["series_id"] == "HE_CPI_NOWCAST" and row["value"] == 3.85
    assert "decelerating" in p.notes[0]["theme_tags"]


def test_quarterly_outlook():
    p = parse_quarterly_outlook(_email("Quarterly Investment Outlook | 3Q 2026", "Quad 4 ahead"))
    assert "quarterly_rule_review" in p.flags
    assert p.notes[0]["source_type"] == "quarterly_outlook"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
