"""PS 'rank degraded' REDUCE is a warning only (shown, never counted), like SSS weight-fell."""
from etl.derive_actionable import _is_warning_only

PS = {"source_code": "PS", "action": "REDUCE", "action_reason": "rank degraded 17->19"}


def test_ps_rank_degraded_is_warning_only_whatever_technical_says():
    for rr in ("BS", None, "SS"):
        assert _is_warning_only(PS, rr)


def test_ps_drop_from_list_still_counts():
    assert not _is_warning_only({"source_code": "PS", "action": "REMOVE", "action_reason": "dropped from list"}, None)


def test_other_reduces_still_count():
    assert not _is_warning_only({"source_code": "ETF", "action": "REDUCE", "action_reason": "rank degraded 3->5"}, None)
