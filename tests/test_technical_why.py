"""Plain-English Technical reason (etl/technical_why.py). Pure, no DB."""
from etl.technical_why import explain_technical


def _plain(t):
    """Text without the {r}/{g}/{/} highlight markers."""
    return t.replace("{r}", "").replace("{g}", "").replace("{/}", "")


def base(**kw):
    d = dict(trend_trade_rule=4, bb_rng_strk_rule=1, bb_desc="Early Buy",
             bull_rr_action=None, not_bull_rr_action=None, td_tn_bb_rr_action=-9,
             lrr_idx=0, last=330.32, low=325.81, lrr=328.0,
             trade_line=316.51, trend_line=307.0)
    d.update(kw)
    return d


def test_returns_why_and_verdict_on_two_lines():
    why, verdict = explain_technical(base(trend_trade_rule=-2)).split("\n")
    assert "below Trade" in _plain(why) and verdict.startswith("bearish")


def test_no_signal_returns_none():
    assert explain_technical(base(td_tn_bb_rr_action=None)) is None


def test_broken_support_is_named_when_price_is_still_below_lrr():
    txt = explain_technical(base(lrr_idx_raw=-1, lrr_idx_eff=-1, last=326.0))
    assert "below LRR" in _plain(txt) and "326.00" in txt and "328.00" in txt


def test_low_broke_but_price_recovered_means_support_held():
    txt = explain_technical(base(lrr_idx_raw=-1, lrr_idx_eff=0, last=330.32,
                                 not_bull_rr_action=3, td_tn_bb_rr_action=8))
    assert "typical daily move" not in txt
    assert "support held" in txt and "325.81" in txt and "330.32" in txt
    assert "above Trade and Trend" in txt


def test_bearish_trade_trend_read_wins_over_range_signal():
    txt = explain_technical(base(trend_trade_rule=1, last=63.61, trade_line=64.07,
                                 trend_line=47.62, lrr_idx=0, not_bull_rr_action=4))
    assert "below Trade" in _plain(txt) and "overrides" in txt
    assert "below LRR" not in _plain(txt)


def test_bearish_band_wins_over_range_signal():
    txt = explain_technical(base(bb_rng_strk_rule=-2, bb_desc="PrBrkdn", lrr_idx=0))
    assert "Bollinger" in txt and "PrBrkdn" in txt


def test_between_the_lines_is_neutral():
    assert "neutral zone" in explain_technical(base(trend_trade_rule=2))


def test_range_position_bull_and_not_bull_paths():
    bull = explain_technical(base(bb_rng_strk_rule=2, bull_rr_action=4, td_tn_bb_rr_action=9))
    notbull = explain_technical(base(bb_rng_strk_rule=1, not_bull_rr_action=5, td_tn_bb_rr_action=10))
    assert "touched LRR" in bull
    assert "MACD rising" in notbull


def test_shallow_dip_under_lrr_is_watch_not_support_held():
    txt = explain_technical(base(lrr_idx_raw=-1, lrr_idx_eff=0, last=327.0,
                                 not_bull_rr_action=3, td_tn_bb_rr_action=8))
    assert "watch" in txt and "support held" not in txt
