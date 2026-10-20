"""Every Risk Dial gauge has hover help in db/seeds_risk_gauge_help.sql (pure file check, no DB)."""
import re
from pathlib import Path

from etl.derive_risk_dial import GAUGES

SEED = Path(__file__).resolve().parent.parent / "db" / "seeds_risk_gauge_help.sql"


def _seeded():
    txt = SEED.read_text(encoding="utf-8")
    return dict(re.findall(r"SET help = E'(.*?)' WHERE gauge_key = '([^']+)';", txt, flags=re.S))[::-1] if False else \
        {k: h for h, k in re.findall(r"SET help = E'(.*?)' WHERE gauge_key = '([^']+)';", txt, flags=re.S)}


def test_every_gauge_has_help():
    seeded = _seeded()
    missing = [k for k, _ in GAUGES if k not in seeded]
    assert not missing, f"gauges without hover help: {missing}"


def test_help_is_bulleted_what_fires_why():
    bs_n = chr(92) + "n"   # the seed file holds the SQL escape: a backslash followed by n
    for k, h in _seeded().items():
        assert bs_n + "- Fires when:" in h and bs_n + "- Why it matters:" in h, k
