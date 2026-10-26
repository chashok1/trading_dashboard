"""Behaviour of the Technical rule classifier (etl/technical_rules.py, TASK_155). Pure Python, no DB.

One case per rule: Step 1 sells (S1-a, S1-b, S1-c), Step 3 (3a, 3x, 3f, 3h, 3k, 3p) and the precedence rule
"a Step 3 buy beats a Step 1 sell". Action codes: SA -10, STM -9, SS -8, BMN 8, BS 9, BM 10.
"""
import math

import pandas as pd

from etl.technical_rules import classify

# Range 90..110: price 100 is 50% of the way up. Low 99 stays out of the LRR zone (zone = up to 95).
DEFAULTS = dict(qe=4, qj=1, bx=False, px=100.0, hi=101.0, lo=99.0, lrr=90.0, trr=110.0, up=False,
                below5=False, fell3=False, zone_recent=False, trr_up5=False, brk=False)


def run(**kw):
    row = dict(DEFAULTS)
    row.update(kw)
    return classify(pd.DataFrame([row])).iloc[0]


def is_nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


# ---- Step 1 -----------------------------------------------------------------------------------------------------
def test_s1a_below_lowest_of_last_5_trade_lines_is_sell_all():
    r = run(qe=1, px=85.0, hi=88.0, lo=84.0, below5=True)
    assert r.s1_id == "S1-a" and r.s1_code == -10 and r.code == -10


def test_s1b_below_both_lines_is_sell_all():
    r = run(qe=-2, px=85.0, hi=88.0, lo=84.0)
    assert r.s1_id == "S1-b" and r.s1_code == -10 and r.code == -10


def test_s1c_fresh_fall_below_trade_is_sell_some():
    r = run(qe=1, px=85.0, hi=88.0, lo=84.0, fell3=True)
    assert r.s1_id == "S1-c" and r.s1_code == -8 and r.code == -8


def test_s1a_comes_before_s1c_when_both_match():
    assert run(qe=1, px=85.0, hi=88.0, lo=84.0, below5=True, fell3=True).s1_id == "S1-a"


# ---- Step 3 -----------------------------------------------------------------------------------------------------
def test_3a_support_broken_sell_to_min_above_and_sell_all_below():
    above = run(qe=4, brk=True, px=80.0, hi=85.0, lo=79.0)
    below = run(qe=2, brk=True, px=80.0, hi=85.0, lo=79.0)
    assert above.s3_id == "3a" and above.code == -9 and above.flag == "above"
    assert below.s3_id == "3a" and below.code == -10 and below.flag == "below"


def test_3x_bounce_at_lrr_buy_more_above_buy_to_min_below_buy_some_when_bands_fall():
    assert run(zone_recent=True).s3_id == "3x" and run(zone_recent=True).code == 10
    assert run(zone_recent=True, qe=2).code == 8          # below flag: Buy To Min
    assert run(zone_recent=True, qj=-1).code == 9         # falling bands, above flag: Buy Some
    assert is_nan(run(zone_recent=True, qj=-1, qe=2).code)   # falling bands, below flag: do nothing


def test_3x_needs_price_25_to_60_percent_up_the_range():
    r = run(zone_recent=True, px=108.0, hi=108.0)   # 90%: out of the 25-60 band
    assert r.s3_id != "3x"


def test_3f_fresh_touch_of_lrr_under_25_percent():
    above = run(px=92.0, hi=93.0, lo=91.0)
    below = run(px=92.0, hi=93.0, lo=91.0, qe=2)
    assert above.s3_id == "3f" and above.code == 8
    assert below.s3_id == "3f" and is_nan(below.code)    # below flag: do nothing


def test_3h_up_day_flat_bands_needs_no_trr_condition():
    r = run(up=True, qj=1)
    assert r.s3_id == "3h" and r.code == 8
    assert run(up=False, qj=1).s3_id != "3h"


def test_3h_up_day_rising_bands_needs_trr_up_2_percent():
    assert run(up=True, qj=2).s3_id != "3h"
    r = run(up=True, qj=2, trr_up5=True)
    assert r.s3_id == "3h" and r.code == 8


def test_3k_top_of_range_flat_bands_above_flag_is_sell_some():
    r = run(px=109.0, hi=110.0, lo=105.0)
    assert r.s3_id == "3k" and r.code == -8


def test_3k_is_triggered_by_the_days_high_alone():
    r = run(px=100.0, hi=110.0, lo=99.0)       # price 50%, but the high reached 100% of the range
    assert r.s3_id == "3k" and r.code == -8


def test_3p_top_of_range_falling_bands_is_sell_some():
    r = run(px=109.0, hi=110.0, lo=105.0, qj=-1)
    assert r.s3_id == "3p" and r.code == -8


# ---- Precedence -------------------------------------------------------------------------------------------------
def test_step3_buy_beats_step1_sell():
    r = run(qe=1, below5=True, zone_recent=True)     # S1-a sell, but 3x bounce buy for a below-flag stock
    assert r.s1_id == "S1-a" and r.s3_id == "3x"
    assert r.code == 8


def test_step1_sell_stands_when_step3_says_do_nothing():
    r = run(qe=1, fell3=True, px=92.0, hi=93.0, lo=91.0)   # 3f below flag = do nothing, S1-c still sells
    assert r.s3_id == "3f" and is_nan(r.s3_code)
    assert r.code == -8


def test_above_both_lines_with_no_rule_matching_is_no_signal():
    r = run()
    assert r.s1_id == "1a" and r.s3_id is None and is_nan(r.code)
