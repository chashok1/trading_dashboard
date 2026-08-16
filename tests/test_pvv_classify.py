"""
Tests for etl.derive_pvv — pure-Python classification and decision logic.

Covers:
  - classify_pvv: all 9 rows of the signal-code table (docs/pvv_logic.md §3)
  - classify_pvv_3m: the 5-row Price/Vol-only variant used by the 3m bucket
  - decide_pvv: the outlook x sig_today decision matrix (docs/pvv_logic.md
    §4, 2026-08-16 revision) — RR outlook decides WHAT, sig_today decides
    WHEN, at_lrr gates the two price-up rows (dip-buyer philosophy)

Pure-Python, no DB — runs with no setup.

Run:
    pytest tests/test_pvv_classify.py -v
"""
from __future__ import annotations

import pytest

from etl.derive_pvv import classify_pvv, classify_pvv_3m, decide_pvv


# ─── classify_pvv: the 9-row signal-code table ─────────────────────────────
_SIG_CASES = [
    ("up",   "up",   "down", "STRONG_BULL"),
    ("up",   "up",   "up",   "OVEREXT_BULL"),
    ("up",   "down", "down", "WEAK_BULL"),
    ("up",   "down", "up",   "BEAR_DIV"),
    ("down", "up",   "up",   "STRONG_BEAR"),
    ("down", "up",   "down", "MILD_BEAR"),
    ("down", "down", "down", "DRIFT"),
    ("down", "down", "up",   "BEAR_LEAN"),
    ("flat", "up",   "down", "NEUTRAL"),   # flat price -> NEUTRAL regardless of v/vol
]


@pytest.mark.parametrize("p_dir,v_dir,vol_dir,expected", _SIG_CASES)
def test_classify_pvv_signal_table(p_dir, v_dir, vol_dir, expected):
    assert classify_pvv(p_dir, v_dir, vol_dir) == expected


def test_classify_pvv_insufficient_data_is_na():
    assert classify_pvv(None, "up", "down") == "NA"
    assert classify_pvv("up", None, "down") == "NA"
    assert classify_pvv("up", "up", None) == "NA"
    assert classify_pvv(None, None, None) == "NA"


def test_classify_pvv_volume_flat_resolves_down():
    # Volume 'flat' -> resolves toward 'down' (unconfirmed)
    assert classify_pvv("up", "flat", "down") == classify_pvv("up", "down", "down")
    assert classify_pvv("up", "flat", "down") == "WEAK_BULL"


def test_classify_pvv_vol_flat_resolves_down():
    # Volatility 'flat' -> resolves toward 'down' (calm)
    assert classify_pvv("up", "up", "flat") == classify_pvv("up", "up", "down")
    assert classify_pvv("up", "up", "flat") == "STRONG_BULL"


# ─── classify_pvv_3m: Price/Vol-only variant ───────────────────────────────
_SIG_3M_CASES = [
    ("up",   "down", "STRONG_BULL"),
    ("up",   "up",   "OVEREXT_BULL"),
    ("down", "up",   "STRONG_BEAR"),
    ("down", "down", "DRIFT"),
    ("flat", "up",   "NEUTRAL"),
]


@pytest.mark.parametrize("p_dir,vol_dir,expected", _SIG_3M_CASES)
def test_classify_pvv_3m(p_dir, vol_dir, expected):
    assert classify_pvv_3m(p_dir, vol_dir) == expected


def test_classify_pvv_3m_insufficient_data_is_na():
    assert classify_pvv_3m(None, "up") == "NA"
    assert classify_pvv_3m("up", None) == "NA"


def test_classify_pvv_3m_vol_flat_resolves_down():
    assert classify_pvv_3m("up", "flat") == "STRONG_BULL"
    assert classify_pvv_3m("down", "flat") == "DRIFT"


# ─── decide_pvv: outlook x sig_today decision matrix (2026-08-16 revision) ──
# docs/pvv_logic.md §4. at_lrr defaults False -- only STRONG_BULL/WEAK_BULL
# under a Bullish outlook read it (dip-buyer gate); every other cell ignores it.
_MATRIX_CASES = [
    # sig_today,      outlook,     at_lrr,  expected
    ("STRONG_BULL",   "Bullish",   False,   "NO_ACTION"),
    ("STRONG_BULL",   "Bullish",   True,    "BUY_LRR"),
    ("STRONG_BULL",   "Bearish",   False,   "TRIM"),
    ("STRONG_BULL",   "Neutral",   False,   "NO_ACTION"),
    ("WEAK_BULL",     "Bullish",   False,   "NO_ACTION"),
    ("WEAK_BULL",     "Bullish",   True,    "BUY_LRR"),
    ("WEAK_BULL",     "Bearish",   False,   "TRIM"),
    ("WEAK_BULL",     "Neutral",   False,   "NO_ACTION"),
    ("OVEREXT_BULL",  "Bullish",   False,   "TRIM"),
    ("OVEREXT_BULL",  "Bearish",   False,   "TRIM"),
    ("OVEREXT_BULL",  "Neutral",   False,   "NO_ACTION"),
    ("BEAR_DIV",      "Bullish",   False,   "NO_ACTION"),
    ("BEAR_DIV",      "Bearish",   False,   "TRIM"),
    ("BEAR_DIV",      "Neutral",   False,   "NO_ACTION"),
    ("NEUTRAL",       "Bullish",   False,   "NO_ACTION"),
    ("NEUTRAL",       "Bearish",   False,   "AVOID"),
    ("NEUTRAL",       "Neutral",   False,   "NO_ACTION"),
    ("NA",            "Bullish",   False,   "NO_ACTION"),
    ("NA",            "Bearish",   False,   "AVOID"),
    ("NA",            "Neutral",   False,   "NO_ACTION"),
    ("DRIFT",         "Bullish",   False,   "BUY_DIP"),
    ("DRIFT",         "Bearish",   False,   "AVOID"),
    ("DRIFT",         "Neutral",   False,   "NO_ACTION"),
    ("MILD_BEAR",     "Bullish",   False,   "BUY_WATCH"),
    ("MILD_BEAR",     "Bearish",   False,   "REDUCE"),
    ("MILD_BEAR",     "Neutral",   False,   "NO_ACTION"),
    ("BEAR_LEAN",     "Bullish",   False,   "BUY_DIP"),
    ("BEAR_LEAN",     "Bearish",   False,   "REDUCE"),
    ("BEAR_LEAN",     "Neutral",   False,   "NO_ACTION"),
    ("STRONG_BEAR",   "Bullish",   False,   "SELL_WATCH"),
    ("STRONG_BEAR",   "Bearish",   False,   "SELL"),
    ("STRONG_BEAR",   "Neutral",   False,   "NO_ACTION"),
]


@pytest.mark.parametrize("sig_today,outlook,at_lrr,expected", _MATRIX_CASES)
def test_decide_pvv_matrix(sig_today, outlook, at_lrr, expected):
    assert decide_pvv(sig_today, outlook, at_lrr) == expected


@pytest.mark.parametrize("sig_today", [s for s, _, _, _ in _MATRIX_CASES])
def test_decide_pvv_null_outlook_is_no_action(sig_today):
    # Missing/NULL outlook (e.g. BB-fallback rows) -> NO_ACTION regardless
    # of sig_today, same as Neutral. (2026-08-16: previously WATCH.)
    assert decide_pvv(sig_today, None) == "NO_ACTION"


def test_decide_pvv_dip_buyer_gate_off_lrr_is_no_action():
    # User philosophy: "I only want to buy the dips" -- a same-day price-up
    # reading alone is no longer a buy trigger unless price is at LRR.
    assert decide_pvv("STRONG_BULL", "Bullish", at_lrr=False) == "NO_ACTION"
    assert decide_pvv("WEAK_BULL", "Bullish", at_lrr=False) == "NO_ACTION"


def test_decide_pvv_dip_buyer_gate_at_lrr_is_buy():
    assert decide_pvv("STRONG_BULL", "Bullish", at_lrr=True) == "BUY_LRR"
    assert decide_pvv("WEAK_BULL", "Bullish", at_lrr=True) == "BUY_LRR"


def test_decide_pvv_at_lrr_ignored_outside_the_two_gated_rows():
    # at_lrr only matters for STRONG_BULL/WEAK_BULL + Bullish -- every other
    # cell ignores it entirely.
    assert decide_pvv("OVEREXT_BULL", "Bullish", at_lrr=True) == "TRIM"
    assert decide_pvv("DRIFT", "Bullish", at_lrr=True) == "BUY_DIP"
    assert decide_pvv("STRONG_BEAR", "Bearish", at_lrr=True) == "SELL"


def test_decide_pvv_strong_bear_bullish_is_sell_watch():
    # Replaces the old "knife guard" WATCH: a heavy-volume selloff under a
    # bullish outlook now surfaces as an explicit sell-watch flag rather
    # than being silently suppressed.
    assert decide_pvv("STRONG_BEAR", "Bullish") == "SELL_WATCH"


def test_decide_pvv_sell_the_rip():
    # Bearish outlook + any up-tape sig_today consolidates to TRIM.
    for sig_today in ("STRONG_BULL", "WEAK_BULL", "OVEREXT_BULL", "BEAR_DIV"):
        assert decide_pvv(sig_today, "Bearish") == "TRIM"


@pytest.mark.parametrize("raw,expected", [
    ("bullish", "TRIM"), ("BULLISH", "TRIM"), (" Bullish ", "TRIM"),
])
def test_decide_pvv_case_insensitive_bullish_overext(raw, expected):
    # OVEREXT_BULL ignores at_lrr, so it's a stable code to check case-
    # insensitive outlook parsing against.
    assert decide_pvv("OVEREXT_BULL", raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("bearish", "TRIM"), ("BEARISH", "TRIM"), (" Bearish\n", "TRIM"),
])
def test_decide_pvv_case_insensitive_bearish(raw, expected):
    assert decide_pvv("STRONG_BULL", raw) == expected


def test_decide_pvv_unrecognized_outlook_is_no_action():
    # Any string that isn't exactly Bullish/Bearish/Neutral (after trim/
    # case-fold) falls to the Neutral/NULL column -- e.g. a BB-fallback
    # gradation like "Mild Bullish" that shouldn't reach decide_pvv in
    # practice (derive_pvv runs before the QE second pass fills those),
    # but the pure function stays defensive regardless.
    assert decide_pvv("STRONG_BULL", "Mild Bullish") == "NO_ACTION"
