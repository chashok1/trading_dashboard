"""Hedgeye '10 ETF Go-Anywhere Portfolio' feed (GOANY) — behavior tests.

Pure-Python: no DB needed.
"""
from datetime import date, datetime, timezone

from etl.hedgeye.classify import classify
from etl.hedgeye.parsers import PARSERS, Email, parse_go_anywhere
from etl.derive_outlook_action import _action_membership

_HTML = """
<html><body>
<table><tr><td>WE ARE ADDING ETHA (Ethereum)</td><td>WE ARE REMOVING XLV (Healthcare)</td></tr></table>
<table><tr><th>Current Open Positions</th></tr></table>
<table>
 <thead><tr><th>#</th><th>Ticker</th><th>Name</th><th>Asset Class</th>
  <th>Entry Price</th><th>Total Return ‡</th><th>Date Added</th></tr></thead>
 <tbody>
  <tr><td>1</td><td>CLOZ</td><td>CLOs</td><td>fixed income</td><td>$25.89</td><td>+1.28%</td><td>07/16/26</td></tr>
  <tr><td>2</td><td>ETHA</td><td>Ethereum</td><td>commodities</td><td>$58.06</td><td>-0.06%</td><td>10/07/26</td></tr>
 </tbody>
</table>
<table><tr><td>Recently Closed Positions</td></tr></table>
<table>
 <thead><tr><th>Ticker</th><th>Name</th><th>Asset Class</th><th>Date Added</th>
  <th>Date Removed</th><th>Total Return ‡</th></tr></thead>
 <tbody>
  <tr><td>XLV</td><td>Healthcare</td><td>domestic equities</td><td>08/28/26</td><td>10/07/26</td><td>-0.57%</td></tr>
  <tr><td>AAAU</td><td>Gold ETF</td><td>foreign currency</td><td>02/28/25*</td><td>09/22/26</td><td>+51.12%</td></tr>
 </tbody>
</table>
</body></html>
"""


def _email(html=_HTML, subject="10 ETF Go-Anywhere Portfolio"):
    return Email(
        message_id="<m@x>", subject=subject, sender="Hedgeye <info@hedgeye.com>",
        received=datetime(2026, 10, 7, 14, 26, tzinfo=timezone.utc),
        plaintext="WE ARE ADDING ETHA (Ethereum) WE ARE REMOVING XLV (Healthcare)",
        html=html,
    )


def test_subject_is_classified_as_go_anywhere():
    et = classify(_email())
    assert et.name == "go_anywhere"
    assert et.parser in PARSERS


def test_parses_open_and_closed_rows():
    rows = parse_go_anywhere(_email()).tables["hist_goany"]
    open_rows = [r for r in rows if r["status"] == "open"]
    closed = [r for r in rows if r["status"] == "closed"]
    assert [r["symbol"] for r in open_rows] == ["CLOZ", "ETHA"]
    assert [r["symbol"] for r in closed] == ["XLV", "AAAU"]
    cloz = open_rows[0]
    assert cloz["slot_no"] == 1
    assert cloz["entry_price"] == 25.89
    assert cloz["total_return"] == 1.28
    assert cloz["date_added"] == date(2026, 7, 16)
    assert cloz["tos_symbol"] == "CLOZ"


def test_closed_row_dates_and_footnote_asterisk():
    closed = {r["symbol"]: r for r in parse_go_anywhere(_email()).tables["hist_goany"]
              if r["status"] == "closed"}
    assert closed["XLV"]["date_removed"] == date(2026, 10, 7)
    assert closed["XLV"]["total_return"] == -0.57
    assert closed["AAAU"]["date_added"] == date(2025, 2, 28)
    assert closed["AAAU"]["entry_price"] is None


def test_banner_is_kept_as_a_note_only():
    parsed = parse_go_anywhere(_email())
    assert any("ADDING ETHA" in n["note_text"] for n in parsed.notes)


def test_no_tables_gives_no_rows_and_a_warning():
    parsed = parse_go_anywhere(_email(html="<html><body>nothing</body></html>"))
    assert not parsed.tables.get("hist_goany")
    assert parsed.warnings


def test_membership_actions_behave_like_ps():
    # new on the list
    assert _action_membership(True, False, False)[0] == "ADD"
    # dropped -> REMOVE even when not held (PS rule)
    assert _action_membership(False, True, False)[0] == "REMOVE"
    assert _action_membership(False, True, True)[0] == "REMOVE"
    # still on the list
    assert _action_membership(True, True, True)[0] == "HOLD"
    assert _action_membership(True, True, False)[0] == "ADD"
