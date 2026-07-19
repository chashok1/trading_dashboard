"""derive_source_edge — nightly recompute of the Trade Mode "weak buy
source" list from v_source_edge_scorecard (TASK_123).

ref_settings.trade_mode_weak_buy_sources drives the WEAK SRC pill
(web/actionable.js::_isWeakSourceBuy) — previously a static value seeded
once in db/baseline.sql ('PS,ETF,II'). This recomputes it: a source is
"weak" when its buy-family (ADD+INCREASE) n-weighted 20-day forward edge
is negative with at least 30 samples — the same n>=30 "promising" floor
v_rule_scorecard uses for statistical relevance. Sources with fewer than
30 buy samples are left out of the set entirely (neither flagged nor
cleared), same as v_rule_scorecard leaving them 'unproven' rather than
guessing off a thin sample.

Wired into etl.scheduler.run_nightly_outcomes() (fires once/day).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_source_edge")

_MIN_N = 30


def recompute_weak_buy_sources(session: Session) -> str:
    """Recompute and persist ref_settings.trade_mode_weak_buy_sources.

    Returns the new comma-separated source_code list (may be empty).
    """
    rows = session.execute(text("""
        SELECT source_code,
               SUM(n) AS n,
               SUM(n * edge_20d) / NULLIF(SUM(n), 0) AS buy_edge_20d
        FROM v_source_edge_scorecard
        WHERE action IN ('ADD', 'INCREASE')
        GROUP BY source_code
    """)).fetchall()

    weak = sorted(
        r.source_code for r in rows
        if r.n is not None and r.n >= _MIN_N
        and r.buy_edge_20d is not None and r.buy_edge_20d < 0
    )
    weak_str = ",".join(weak)

    session.execute(text("""
        INSERT INTO ref_settings (setting_name, setting_value, description, updated_at)
        VALUES ('trade_mode_weak_buy_sources', :val,
                'Trade Mode: comma-separated source_code list with negative '
                'n-weighted 20d buy edge (n>=30). Auto-recomputed nightly '
                'from v_source_edge_scorecard — see etl/derive_source_edge.py.',
                now())
        ON CONFLICT (setting_name) DO UPDATE SET
            setting_value = EXCLUDED.setting_value,
            description   = EXCLUDED.description,
            updated_at    = now()
    """), {"val": weak_str})

    log.info("weak_buy_sources recomputed: %s", weak_str or "(none)")
    return weak_str
