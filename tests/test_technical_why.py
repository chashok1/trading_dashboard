"""Plain-English Technical reason (etl/technical_why.py, TASK_155 rules). Pure, no DB."""
from etl.technical_rules import STEP_SIDE
from etl.technical_why import RULE_HELP, explain_technical


def _plain(t):
    """Text without the {r}/{g}/{/} highlight markers."""
    return t.replace("{r}", "").replace("{g}", "").replace("{/}", "")


def base(**kw):
    d = dict(trend_trade_rule=4, bb_rng_strk_rule=1, bb_desc="Early Buy",
             td_tn_bb_rr_action=-9, step1_id="1a", step3_id=None, rr_zone_score=None,
             lrr_idx=0, last=330.32, high=332.0, low=325.81, lrr=328.0, trr=340.0,
             trade_line=316.51, trend_line=307.0)
    d.update(kw)
    return d


def test_returns_why_and_verdict_on_two_lines():
    why, verdict = explain_technical(base(trend_trade_rule=-2, step1_id="S1-b", td_tn_bb_rr_action=-10)).split("\n")
    assert "below Trade" in _plain(why) and verdict.startswith("Below both lines") and "Sell All" in verdict


def test_no_signal_returns_none():
    assert explain_technical(base(td_tn_bb_rr_action=None)) is None


def test_broken_support_is_named_with_both_prices():
    txt = explain_technical(base(step3_id="3a", rr_zone_score=-9, last=326.0))
    assert "below LRR" in _plain(txt) and "326.00" in txt and "328.00" in txt
    assert "Support broken" in txt and "Sell to Min" in txt


def test_below_flag_support_break_is_sell_all():
    txt = explain_technical(base(trend_trade_rule=2, step1_id="1e", step3_id="3a", rr_zone_score=-10, td_tn_bb_rr_action=-10, last=326.0))
    assert "below Trade or Trend" in txt and "Sell All" in txt


def test_s1a_names_the_lowest_of_the_last_5_trade_lines():
    txt = explain_technical(base(trend_trade_rule=1, step1_id="S1-a", td_tn_bb_rr_action=-10, last=300.0, min_trade5_prev=305.5))
    why, verdict = txt.split("\n")
    assert "lowest of the last 5 Trade lines" in why and "305.50" in why and verdict.startswith("Below the lowest of the last 5 Trade lines")


def test_s1c_names_the_fresh_fall_and_sell_some():
    txt = explain_technical(base(trend_trade_rule=1, step1_id="S1-c", td_tn_bb_rr_action=-8, last=300.0, trade_line=316.51))
    assert "within the last 3 days" in txt and "Sell Some" in txt


def test_step3_buy_beats_step1_sell_is_said_in_the_verdict():
    d = base(trend_trade_rule=1, step1_id="S1-c", step3_id="3x", rr_zone_score=8, td_tn_bb_rr_action=8, tech_flag="below")
    why, verdict = explain_technical(d).split("\n")
    assert "Bounce at LRR" in verdict and "Buy To Min" in verdict and "beats the Trade/Trend sell" in verdict and "S1-c" not in verdict
    assert "LRR zone" in why


def test_step1_sell_with_step3_do_nothing_says_so():
    d = base(trend_trade_rule=1, step1_id="S1-a", step3_id="3f", rr_zone_score=None, td_tn_bb_rr_action=-10, tech_flag="below")
    verdict = explain_technical(d).split("\n")[1]
    assert verdict.startswith("Below the lowest of the last 5 Trade lines") and "do nothing" in verdict


def test_3f_buy_min_label_differs_from_buy_to_min():
    d = base(step3_id="3f", rr_zone_score=8, td_tn_bb_rr_action=8, low=329.0, last=330.0)
    assert "Buy Min" in explain_technical(d)


def test_3h_why_shows_the_trr_change_over_5_days():
    d = base(step3_id="3h", rr_zone_score=8, td_tn_bb_rr_action=8, trr=340.0, trr_5d_ago=330.0)
    assert "+3.0%" in explain_technical(d)


def test_top_of_range_sell_names_the_days_high_when_price_is_lower():
    d = base(step3_id="3k", rr_zone_score=-8, td_tn_bb_rr_action=-8, last=335.0, high=339.0)
    assert "day's high" in explain_technical(d) and "Sell Some" in explain_technical(d)


def test_rising_dip_is_buy_some_and_broken_support_overrides_it():
    buy = explain_technical(base(trend_trade_rule=0, step1_id="1b", td_tn_bb_rr_action=9))
    assert "rising dip" in buy
    sell = explain_technical(base(trend_trade_rule=0, step1_id="1b", td_tn_bb_rr_action=-9, last=320.0))
    assert "overrides" in sell and "below LRR" in _plain(sell)


def test_rows_saved_without_rule_ids_still_get_a_step1_reason():
    d = base(trend_trade_rule=-2, td_tn_bb_rr_action=-10)
    d.pop("step1_id")
    assert explain_technical(d).split("\n")[1].startswith("Below both lines")


def test_every_rule_the_classifier_can_produce_has_help_text():
    for sid in STEP_SIDE:
        assert sid in RULE_HELP, sid
        assert RULE_HELP[sid]["when"] and RULE_HELP[sid]["above"] and RULE_HELP[sid]["below"], sid
