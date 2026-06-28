"""
TASK_106 acceptance-criteria tests — description extraction + Call outlook/modifier.

Pure-Python, no DB, no network.
Tests are additive to test_hedgeye_parsers.py and cover exactly the three fixes
described in DEV_HANDOFF.md / AGENT_WORK_16.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from etl.hedgeye.parsers import (
    Email,
    parse_etf_changes,
    parse_investing_ideas,
    parse_the_call,
)

TS = datetime(2026, 6, 24, 15, 0, tzinfo=timezone.utc)


def _email(subject, plaintext, html=""):
    return Email(
        message_id="<task106@h>",
        subject=subject,
        sender="info@hedgeye.com",
        received=TS,
        plaintext=plaintext,
        html=html,
    )


# ---------------------------------------------------------------------------
# Fix 1 — parse_etf_changes: description from text before (TICKER)
# ---------------------------------------------------------------------------

class TestEtfChangesDescription:

    def test_description_populated_for_add(self):
        """Company name before (TICKER) is extracted as description on add."""
        pt = (
            "We are ADDING Long:\n\n"
            "Japan (DBJP) - (0 - 0)\n"
            "International Dividend (VYMI) - (0 - 0)\n\n"
            "How to Use ETF Pro Plus Updates:\n"
        )
        p = parse_etf_changes(_email("ETF Pro Change", pt))
        rows = {r["symbol"]: r for r in p.tables["hist_etfchg"]}
        assert rows["DBJP"]["description"] == "Japan"
        assert rows["VYMI"]["description"] == "International Dividend"

    def test_description_populated_for_remove(self):
        """Company name is extracted even on remove actions."""
        pt = (
            "We are REMOVING Long:\n\n"
            "Quantum Tech (QTUM) - (149.0 - 175.0)\n"
            "Cybersecurity (BUG) - (32.97 - 35.76)\n\n"
            "How to Use ETF Pro Plus Updates:\n"
        )
        p = parse_etf_changes(_email("ETF Pro Change", pt))
        rows = {r["symbol"]: r for r in p.tables["hist_etfchg"]}
        assert rows["QTUM"]["description"] == "Quantum Tech"
        assert rows["BUG"]["description"] == "Cybersecurity"

    def test_description_none_when_ticker_starts_line(self):
        """If nothing precedes (TICKER) on the line, description is None."""
        pt = (
            "We are ADDING Short:\n\n"
            "(ARGT) - trailing text\n\n"
            "How to Use ETF Pro Plus Updates:\n"
        )
        p = parse_etf_changes(_email("ETF Pro Change", pt))
        rows = p.tables["hist_etfchg"]
        assert rows[0]["description"] is None

    def test_description_real_world_sample(self):
        """Jun-24 real-world sample: Argentina, Japan, International Dividend."""
        pt = (
            "We are ADDING Long:\n\n"
            "Japan (DBJP)\n"
            "International Dividend (VYMI)\n\n"
            "We are REMOVING Long:\n\n"
            "Argentina (ARGT)\n\n"
            "How to Use ETF Pro Plus Updates:\n"
        )
        p = parse_etf_changes(_email("ETF Pro Change", pt))
        rows = {r["symbol"]: r for r in p.tables["hist_etfchg"]}
        assert rows["DBJP"]["description"] == "Japan"
        assert rows["VYMI"]["description"] == "International Dividend"
        assert rows["ARGT"]["description"] == "Argentina"
        assert all(r["description"] is not None for r in rows.values())

    def test_no_null_description_in_batch(self):
        """All rows in a typical batch must have non-None description."""
        pt = (
            "We are ADDING Long:\n\n"
            "Gasoline Futures (UGA)\n\n"
            "How to Use ETF Pro Plus Updates:\n"
        )
        p = parse_etf_changes(_email("ETF Pro Change", pt))
        null_count = sum(1 for r in p.tables["hist_etfchg"] if not r["description"])
        assert null_count == 0, f"Expected 0 null descriptions, got {null_count}"


# ---------------------------------------------------------------------------
# Fix 2 — parse_investing_ideas: description from subject between Add/Remove and (TICKER)
# ---------------------------------------------------------------------------

class TestInvestingIdeasDescription:

    def test_description_extracted_from_add_subject(self):
        """'Add AGILITI (AGTI) to LONG Side' → description = 'AGILITI'."""
        p = parse_investing_ideas(_email(
            "Add AGILITI (AGTI) to LONG Side",
            "We are ADDING the following to Investing Ideas:\n\nLong:\n\nAGTI\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] == "AGILITI"

    def test_description_extracted_from_remove_subject(self):
        """'Remove iShares (EWJ) from LONG Side' → description = 'iShares'."""
        p = parse_investing_ideas(_email(
            "Remove iShares (EWJ) from LONG Side",
            "We are REMOVING the following from Investing Ideas:\n\nLong:\n\nEWJ\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] == "iShares"

    def test_description_multiword(self):
        """Multi-word company name is fully captured."""
        p = parse_investing_ideas(_email(
            "Add ResMed Inc. (RMD) to SHORT Side",
            "We are ADDING the following to Investing Ideas:\n\nShort:\n\nRMD\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] == "ResMed Inc."

    def test_description_real_world_mongodb(self):
        """Jun-24 real-world sample: Remove Long MongoDB Inc. (MDB)."""
        p = parse_investing_ideas(_email(
            "Remove Long MongoDB Inc. (MDB) from LONG Side",
            "We are REMOVING the following from Investing Ideas:\n\nLong:\n\nMDB\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] == "Long MongoDB Inc."
        assert r["symbol"] == "MDB"
        assert r["action"] == "remove"

    def test_description_real_world_carnival(self):
        """Jun-25 real-world sample: Add Carnival Corporation Ltd. (CCL)."""
        p = parse_investing_ideas(_email(
            "Add Carnival Corporation Ltd. (CCL) to LONG Side",
            "We are ADDING the following to Investing Ideas:\n\nLong:\n\nCCL\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] == "Carnival Corporation Ltd."
        assert r["symbol"] == "CCL"
        assert r["action"] == "add"

    def test_description_none_when_no_add_remove_prefix(self):
        """When (TICKER) in subject but no Add/Remove prefix, description is None."""
        # Subject has the ticker paren but no 'Add'/'Remove' keyword before it,
        # so the description regex doesn't match → description is None.
        p = parse_investing_ideas(_email(
            "Investing Ideas Update (AAPL) on LONG Side",
            "We are ADDING the following to Investing Ideas:\n\nLong:\n\nAAPL\n",
        ))
        r = p.tables["hist_iichg"][0]
        assert r["description"] is None


# ---------------------------------------------------------------------------
# Fix 3 — parse_the_call: outlook = BULLISH/BEARISH/NEUTRAL + outlook_modifier
# ---------------------------------------------------------------------------

class TestTheCallOutlook:

    def _call_rows(self, pt):
        p = parse_the_call(_email("The Call @ Hedgeye | 6/24/2026", pt))
        return {r["symbol"]: r for r in p.tables["hist_call"]}

    def test_longs_emit_bullish(self):
        """Symbols in LONGS: section get outlook=BULLISH."""
        rows = self._call_rows(
            "HEDGEYE POSITIONS\nLONGS: AAPL, MSFT\nSHORTS: TSLA\nNEUTRAL: GOOG\n"
        )
        assert rows["AAPL"]["outlook"] == "BULLISH"
        assert rows["MSFT"]["outlook"] == "BULLISH"

    def test_shorts_emit_bearish(self):
        """Symbols in SHORTS: section get outlook=BEARISH."""
        rows = self._call_rows(
            "HEDGEYE POSITIONS\nLONGS: AAPL\nSHORTS: TSLA, META\nNEUTRAL:\n"
        )
        assert rows["TSLA"]["outlook"] == "BEARISH"
        assert rows["META"]["outlook"] == "BEARISH"

    def test_neutral_emits_neutral(self):
        """Symbols in NEUTRAL: section get outlook=NEUTRAL."""
        rows = self._call_rows(
            "HEDGEYE POSITIONS\nLONGS:\nSHORTS:\nNEUTRAL: FDXF\n"
        )
        assert rows["FDXF"]["outlook"] == "NEUTRAL"

    def test_no_lowercase_outlooks(self):
        """Outlook values must never be 'long', 'short', or 'neutral' (lowercase)."""
        rows = self._call_rows(
            "HEDGEYE POSITIONS\nLONGS: KDP, CASY\nSHORTS: MSTR\nNEUTRAL: FDXF\n"
        )
        for sym, r in rows.items():
            assert r["outlook"] in ("BULLISH", "BEARISH", "NEUTRAL"), (
                f"Symbol {sym} has bad outlook: {r['outlook']!r}"
            )

    def test_outlook_modifier_long_bench(self):
        """'long bench' keyword in body line with (SYM): triggers modifier."""
        pt = (
            "HEDGEYE POSITIONS\n"
            "LONGS: AAPL, MSFT\n"
            "SHORTS: TSLA\n\n"
            "Sector Summary:\n"
            "(MSFT): This is our long bench position in Technology.\n"
        )
        rows = self._call_rows(pt)
        assert rows["MSFT"]["outlook_modifier"] == "long bench"
        assert rows["AAPL"]["outlook_modifier"] is None  # no keyword for AAPL

    def test_outlook_modifier_short_bench(self):
        """'short bench' keyword is correctly detected."""
        pt = (
            "HEDGEYE POSITIONS\n"
            "LONGS: AAPL\n"
            "SHORTS: TSLA\n\n"
            "(TSLA): short bench candidate.\n"
        )
        rows = self._call_rows(pt)
        assert rows["TSLA"]["outlook_modifier"] == "short bench"

    def test_outlook_modifier_best_idea_long(self):
        """'best idea long' modifier is detected."""
        pt = (
            "HEDGEYE POSITIONS\n"
            "LONGS: NVDA\n"
            "SHORTS:\n\n"
            "(NVDA): Our best idea long in semis.\n"
        )
        rows = self._call_rows(pt)
        assert rows["NVDA"]["outlook_modifier"] == "best idea long"

    def test_outlook_modifier_best_idea_short(self):
        """'best idea short' modifier is detected."""
        pt = (
            "HEDGEYE POSITIONS\n"
            "LONGS:\n"
            "SHORTS: TSLA\n\n"
            "(TSLA): best idea short for the quarter.\n"
        )
        rows = self._call_rows(pt)
        assert rows["TSLA"]["outlook_modifier"] == "best idea short"

    def test_top5_side_stays_lowercase(self):
        """hist_call_top5.side must remain lowercase ('long'/'short')."""
        pt = (
            "HEDGEYE POSITIONS\n"
            "LONGS: BJRI\nSHORTS: MSTR\n\n"
            "Top 5 Most Actionable Stock Ideas\n\n"
            "BJ's Restaurants, Inc. (BJRI): Comp acceleration story.\n\n"
            "MicroStrategy (MSTR): Overvalued crypto proxy.\n"
        )
        p = parse_the_call(_email("The Call @ Hedgeye | 6/24/2026", pt))
        top5 = {r["symbol"]: r for r in p.tables["hist_call_top5"]}
        assert top5["BJRI"]["side"] == "long"
        assert top5["MSTR"]["side"] == "short"

    def test_real_world_jun24_sample(self):
        """Simulate the Jun-24 call: 18 positions, all BULLISH/BEARISH/NEUTRAL."""
        pt = (
            "06/24/2026 04:34 PM EDT The Call @ Hedgeye | Replay & Summary | 6/24/2026\n\n"
            "HEDGEYE POSITIONS\n"
            "LONGS: KDP, CASY, MUSA, HLT, MGM, BJRI, SOXS, SRS, RH, DKNG, CCJ, NNE\n"
            "SHORTS: MSTR, MCD, THC, AAPL, NVDA\n"
            "NEUTRAL: FDXF\n\n"
            "(KDP): long bench pick for Q2.\n"
        )
        p = parse_the_call(_email("The Call @ Hedgeye | 6/24/2026", pt))
        call_rows = p.tables["hist_call"]
        assert len(call_rows) == 18
        bad = [r for r in call_rows if r["outlook"] not in ("BULLISH", "BEARISH", "NEUTRAL")]
        assert bad == [], f"Non-standard outlooks found: {[(r['symbol'], r['outlook']) for r in bad]}"
        kdp = next(r for r in call_rows if r["symbol"] == "KDP")
        assert kdp["outlook_modifier"] == "long bench"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
