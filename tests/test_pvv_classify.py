"""
Tests for etl.derive_pvv — pure-Python classification and decision logic.

Covers:
  - classify_pvv: all 9 rows of the signal-code table (docs/pvv_logic.md §3)
  - classify_pvv_3m: the 5-row Price/Vol-only variant used by the 3m bucket
  - decide_pvv: the 9x3 outlook x sig_today decision matrix (docs/pvv_logic.md
    §4, TASK_127) — RR outlook decides WHAT, sig_today decides WHEN

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


# ─── decide_pvv: outlook x sig_today 9x3 matrix (TASK_127) ────────────────
# docs/pvv_logic.md §4 / agent-tasks/TASK_127_pvv_outlook_decision.md §2.
_MATRIX_CASES = [
    # sig_today,      outlook,     expected
    ("STRONG_BULL",   "Bullish",   "BUY"),
    ("STRONG_BULL",   "Bearish",   "TRIM"),
    ("STRONG_BULL",   "Neutral",   "WATCH"),
    ("WEAK_BULL",     "Bullish",   "BUY"),
    ("WEAK_BULL",     "Bearish",   "TRIM"),
    ("WEAK_BULL",     "Neutral",   "WATCH"),
    ("OVEREXT_BULL",  "Bullish",   "TRIM"),
    ("OVEREXT_BULL",  "Bearish",   "TRIM"),
    ("OVEREXT_BULL",  "Neutral",   "WATCH"),
    ("BEAR_DIV",      "Bullish",   "WATCH"),
    ("BEAR_DIV",      "Bearish",   "TRIM"),
    ("BEAR_DIV",      "Neutral",   "WATCH"),
    ("NEUTRAL",       "Bullish",   "WATCH"),
    ("NEUTRAL",       "Bearish",   "AVOID"),
    ("NEUTRAL",       "Neutral",   "WATCH"),
    ("NA",            "Bullish",   "WATCH"),
    ("NA",            "Bearish",   "AVOID"),
    ("NA",            "Neutral",   "WATCH"),
    ("DRIFT",         "Bullish",   "BUY_DIP"),
    ("DRIFT",         "Bearish",   "AVOID"),
    ("DRIFT",         "Neutral",   "WATCH"),
    ("MILD_BEAR",     "Bullish",   "BUY_DIP"),
    ("MILD_BEAR",     "Bearish",   "REDUCE"),
    ("MILD_BEAR",     "Neutral",   "WATCH"),
    ("BEAR_LEAN",     "Bullish",   "BUY_DIP"),
    ("BEAR_LEAN",     "Bearish",   "REDUCE"),
    ("BEAR_LEAN",     "Neutral",   "WATCH"),
    ("STRONG_BEAR",   "Bullish",   "WATCH"),   # knife guard — no BUY_DIP
    ("STRONG_BEAR",   "Bearish",   "SELL"),
    ("STRONG_BEAR",   "Neutral",   "WATCH"),
]


@pytest.mark.parametrize("sig_today,outlook,expected", _MATRIX_CASES)
def test_decide_pvv_matrix(sig_today, outlook, expected):
    assert decide_pvv(sig_today, outlook) == expected


@pytest.mark.parametrize("sig_today", [s for s, _, _ in _MATRIX_CASES])
def test_decide_pvv_null_outlook_is_watch(sig_today):
    # Missing/NULL outlook (e.g. BB-fallback rows) -> WATCH regardless of
    # sig_today, same as Neutral.
    assert decide_pvv(sig_today, None) == "WATCH"


def test_decide_pvv_knife_guard_bullish_strong_bear():
    # Deliberate: bullish outlook + STRONG_BEAR sig_today does NOT fire
    # BUY_DIP -- it waits at WATCH rather than catching a falling knife.
    assert decide_pvv("STRONG_BEAR", "Bullish") == "WATCH"


def test_decide_pvv_sell_the_rip():
    # Bearish outlook + any up-tape sig_today consolidates to TRIM.
    for sig_today in ("STRONG_BULL", "WEAK_BULL", "OVEREXT_BULL", "BEAR_DIV"):
        assert decide_pvv(sig_today, "Bearish") == "TRIM"


@pytest.mark.parametrize("raw,expected", [
    ("bullish", "BUY"), ("BULLISH", "BUY"), (" Bullish ", "BUY"),
    ("bearish", "TRIM"), ("BEARISH", "TRIM"), (" Bearish\n", "TRIM"),
])
def test_decide_pvv_case_insensitive_trim(raw, expected):
    assert decide_pvv("STRONG_BULL", raw) == expected


def test_decide_pvv_unrecognized_outlook_is_watch():
    # Any string that isn't exactly Bullish/Bearish/Neutral (after trim/
    # case-fold) falls to the Neutral/NULL column -- e.g. a BB-fallback
    # gradation like "Mild Bullish" that shouldn't reach decide_pvv in
    # practice (derive_pvv runs before the QE second pass fills those),
    # but the pure function stays defensive regardless.
    assert decide_pvv("STRONG_BULL", "Mild Bullish") == "WATCH"
