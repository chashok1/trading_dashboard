"""Watch 'Final Call turns Buy / Sell' condition: pure logic, no DB."""
from etl.derive_watch import call_state


def test_already_on_target_does_not_fire_until_it_leaves_and_returns():
    assert call_state("sell", "SELL", False) == (False, False)      # already Sell when the watch was made: not armed, no fire
    assert call_state("hold", "SELL", False) == (False, True)       # left Sell: now armed
    assert call_state("sell", "SELL", True) == (True, True)         # back on Sell after being armed: fires


def test_buy_and_sell_sides_are_separate():
    assert call_state("buy", "SELL", False) == (False, True)
    assert call_state(None, "BUY", True) == (False, True)           # no call = not on the target side
    assert call_state("buy", "BUY", True) == (True, True)
