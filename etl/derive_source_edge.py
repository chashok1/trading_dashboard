"""derive_source_edge — nightly recompute of (1) the Trade Mode "weak buy
source" list and (2) ref_source_precedence.measured_rank (TASK_123, TASK_140)
from v_source_edge_scorecard.

ref_settings.trade_mode_weak_buy_sources drives the WEAK SRC pill
(web/actionable.js::_isWeakSourceBuy) — previously a static value seeded
once in db/baseline.sql ('PS,ETF,II'). This recomputes it: a source is
"weak" when its buy-family (ADD+INCREASE) n-weighted 20-day forward edge
is negative with at least 30 samples — the same n>=30 "promising" floor
v_rule_scorecard uses for statistical relevance. Sources with fewer than
30 buy samples are left out of the set entirely (neither flagged nor
cleared), same as v_rule_scorecard leaving them 'unproven' rather than
guessing off a thin sample.

TASK_140: `recompute_source_precedence` writes the same n-weighted buy-family
edge into `ref_source_precedence` for the six outlook sources the winner
contest ranks (RR/SSS/CALL/II/PS/ETF) — `measured_rank` (4..9, best edge
first) for sources with n>=30, else NULL (keep `static_rank`, never guess off
a thin sample). Read by `etl/derive_actionable.py::_order()` only when
`ref_settings.source_order_mode = 'measured'` — default 'static' is
unaffected by this function ever running.

Wired into etl.scheduler.run_nightly_outcomes() (fires once/day).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_source_edge")

_MIN_N = 30

# The six outlook sources the winner-contest re-rank applies to (TASK_140).
# Static ranks occupy 4..9 today (PS=4, ETF=5, RR=6, SSS=7, II=8, CALL=9) —
# measured_rank is emitted in the same numeric band so it never collides
# with the Hedgeye same-day-trigger tiers (RTA=1/TOP5=2/SSSCHG=3) or the
# bottom tiers (RTAINFO=10/MACROSHOW=11).
_RANKED_SOURCES = ("RR", "SSS", "CALL", "II", "PS", "ETF")
_RANK_BAND_START = 4


def recompute_source_precedence(session: Session) -> dict:
    """Recompute and persist ref_source_precedence.measured_rank/buy_edge_20d/n
    for the six outlook sources. Returns {source_code: measured_rank or None}
    for logging. Never touches ref_settings.source_order_mode — that switch
    is a user decision."""
    rows = session.execute(text("""
        SELECT source_code,
               SUM(n) AS n,
               SUM(n * edge_20d) / NULLIF(SUM(n), 0) AS buy_edge_20d
        FROM v_source_edge_scorecard
        WHERE action IN ('ADD', 'INCREASE') AND source_code = ANY(:srcs)
        GROUP BY source_code
    """), {"srcs": list(_RANKED_SOURCES)}).mappings().all()
    by_src = {r["source_code"]: r for r in rows}

    qualifying = sorted(
        (s for s in _RANKED_SOURCES
         if by_src.get(s) and by_src[s]["n"] is not None
         and by_src[s]["n"] >= _MIN_N and by_src[s]["buy_edge_20d"] is not None),
        key=lambda s: by_src[s]["buy_edge_20d"], reverse=True,
    )
    measured_rank = {s: _RANK_BAND_START + i for i, s in enumerate(qualifying)}

    result = {}
    for s in _RANKED_SOURCES:
        r = by_src.get(s)
        n = int(r["n"]) if r and r["n"] is not None else None
        edge = float(r["buy_edge_20d"]) if r and r["buy_edge_20d"] is not None else None
        rank = measured_rank.get(s)
        result[s] = rank
        session.execute(text("""
            INSERT INTO ref_source_precedence
                (source_code, static_rank, measured_rank, buy_edge_20d, n, updated_at)
            VALUES (:s, :static_rank, :rank, :edge, :n, now())
            ON CONFLICT (source_code) DO UPDATE SET
                measured_rank = EXCLUDED.measured_rank,
                buy_edge_20d  = EXCLUDED.buy_edge_20d,
                n             = EXCLUDED.n,
                updated_at    = now()
        """), {"s": s, "static_rank": _STATIC_FALLBACK.get(s, 99),
               "rank": rank, "edge": edge, "n": n})

    log.info("source_precedence recomputed: %s", result)
    return result


# Fallback static_rank only used if a row doesn't already exist (the seed
# file normally guarantees it does) — mirrors SOURCE_ORDER's values for the
# six ranked sources so an ON CONFLICT insert never needs it in practice.
_STATIC_FALLBACK = {"PS": 4, "ETF": 5, "RR": 6, "SSS": 7, "II": 8, "CALL": 9}


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
