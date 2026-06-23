"""
MacroNet per-symbol score: MacroNet = wt_mo*M + wt_qtr*Q

M = monthly score  — distribution-weighted stance, ramp/lead blended (now→next month)
Q = quarterly score — one-hot stance,              ramp/lead blended (now→next quarter)

Both horizons use the same membership aggregation:
    net = sector×2 + asset_class×1 + Σ(style×0.5)

Results written to drv_macro_score (idempotent DELETE+INSERT).
"""

import logging
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_STANCE = {
    'Bullish': 1.0, 'BULLISH': 1.0,
    'Bearish': -1.0, 'BEARISH': -1.0,
    'Neutral': 0.0, 'NEUTRAL': 0.0,
}

_DEFENSIVE_SECTORS = {
    'Consumer Staples', 'Health care', 'Health Care', 'Utilities', 'Real Estate',
}
_CYCLICAL_SECTORS = {
    'Industrials', 'Materials', 'Energy', 'Consumer Discretionary', 'Financials',
}


def _stance(v):
    return _STANCE.get(v, 0.0)


def _membership_net(memberships, outlook_map, quad_pcts):
    """Score one symbol's membership bundle against a quad distribution."""
    total = 0.0
    for cat, sub, wt in memberships:
        texts = outlook_map.get((cat, sub))
        if not texts:
            continue
        stance = sum(quad_pcts[i] * _stance(texts[i]) for i in range(4))
        total += wt * stance
    return total


def _ramp_weight(days_to_end, ramp_begin, lead_days):
    if days_to_end > ramp_begin:
        return 0.0
    if days_to_end <= lead_days:
        return 1.0
    return (ramp_begin - days_to_end) / max(ramp_begin - lead_days, 1)


def _bdays_to(anchor, end_dt):
    if end_dt <= anchor:
        return 0
    return max(0, len(pd.bdate_range(anchor, end_dt)) - 1)


def _onehot(quad_val):
    """Convert 'Quad N' or bare int/str N to one-hot [q1,q2,q3,q4]."""
    s = str(quad_val).strip()
    # Handle 'Quad 3', 'QUAD3', 'Q3', bare '3'
    for tok in s.split():
        try:
            q = int(tok)
            return [1.0 if i + 1 == q else 0.0 for i in range(4)]
        except ValueError:
            continue
    try:
        q = int(s[-1])
        return [1.0 if i + 1 == q else 0.0 for i in range(4)]
    except (ValueError, IndexError):
        return [0.25, 0.25, 0.25, 0.25]  # uniform fallback


def _norm_pcts(p):
    pcts = [float(getattr(p, f'quad{i+1}_pct') or 0) for i in range(4)]
    total = sum(pcts) or 1.0
    return [x / total for x in pcts]


def _classify_style(beta, pe_ratio, div_yield, rsi, market_cap_str, sector):
    """Return list of (category, sub_category, weight) style memberships."""
    tags = []

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    b, pe, dy, r, mc = _f(beta), _f(pe_ratio), _f(div_yield), _f(rsi), _f(market_cap_str)

    if b is not None:
        if b >= 1.5:
            tags.append(('Equity Style', 'High Beta', 0.5))
        elif b <= 0.7:
            tags.append(('Equity Style', 'Low Beta', 0.5))

    if sector in _DEFENSIVE_SECTORS:
        tags.append(('Equity Style', 'Defensives', 0.5))
    elif sector in _CYCLICAL_SECTORS:
        tags.append(('Equity Style', 'Cyclical', 0.5))

    if pe is not None and pe > 0:
        if pe < 15:
            tags.append(('Equity Style', 'Value', 0.5))
        elif pe > 30:
            tags.append(('Equity Style', 'Secular', 0.5))

    if dy is not None and dy > 0.02:
        tags.append(('Equity Style', 'Dividend', 0.5))

    if r is not None and r > 65:
        tags.append(('Equity Style', 'Momentum', 0.5))

    if mc is not None:
        if mc < 2e9:
            tags.append(('Equity Style', 'Small Caps', 0.5))
        elif mc < 10e9:
            tags.append(('Equity Style', 'Mid Caps', 0.5))

    return tags


def _load_settings(session):
    rows = session.execute(text(
        "SELECT setting_name, setting_value FROM ref_settings"
        " WHERE setting_name LIKE 'quad_%' OR setting_name LIKE 'macronet_%'"
    )).fetchall()
    return {r.setting_name: r.setting_value for r in rows}


def _derive_macro_impl(session: Session, as_of_date: date, run_id=None) -> int:
    cfg = _load_settings(session)

    def _int(k, default):
        try: return int(cfg[k])
        except (KeyError, ValueError, TypeError): return default

    def _float(k, default):
        try: return float(cfg[k])
        except (KeyError, ValueError, TypeError): return default

    ramp_mo_begin = _int('quad_month_ramp_begin_days', 12)
    lead_mo       = _int('quad_month_lead_days', 5)
    ramp_qtr_begin = _int('quad_qtr_ramp_begin_days', 20)
    lead_qtr       = _int('quad_qtr_lead_days', 10)
    wt_mo          = _float('quad_horizon_weight_mo', 0.65)
    wt_qtr         = _float('quad_horizon_weight_qtr', 0.35)
    thr_sa         = _float('macronet_threshold_sa', 1.5)
    thr_bm         = _float('macronet_threshold_bm', 0.5)
    thr_stm        = _float('macronet_threshold_stm', -0.5)
    thr_ss         = _float('macronet_threshold_ss', -1.5)

    def to_action(v):
        if v >= thr_sa:  return 'SA'
        if v >= thr_bm:  return 'BM'
        if v >= thr_stm: return 'HOLD'
        if v >= thr_ss:  return 'STM'
        return 'SS'

    # Load quad periods: current + next for both month and quarter
    periods = session.execute(text("""
        SELECT period_type, quad,
               quad1_pct, quad2_pct, quad3_pct, quad4_pct,
               start_date, end_date
        FROM ref_quad_periods
        WHERE (period_type='monthly' AND start_date <= :d AND end_date >= :d)
           OR (period_type='monthly' AND start_date > :d
               AND start_date <= :d + interval '45 days')
           OR (period_type='quarterly' AND start_date <= :d AND end_date >= :d)
           OR (period_type='quarterly' AND start_date > :d
               AND start_date <= :d + interval '120 days')
        ORDER BY period_type, start_date
    """), {'d': as_of_date}).fetchall()

    months   = [p for p in periods if p.period_type == 'monthly']
    quarters = [p for p in periods if p.period_type == 'quarterly']

    if not months or not quarters:
        log.info("derive_macronet: no quad period rows for %s — skipping", as_of_date)
        return 0

    mo_now   = months[0]
    mo_next  = months[1] if len(months) > 1 else months[0]
    qtr_now  = quarters[0]
    qtr_next = quarters[1] if len(quarters) > 1 else quarters[0]

    mo_now_pcts  = _norm_pcts(mo_now)
    mo_next_pcts = _norm_pcts(mo_next)
    qtr_now_pcts  = _onehot(qtr_now.quad)
    qtr_next_pcts = _onehot(qtr_next.quad)

    mo_days  = _bdays_to(as_of_date, mo_now.end_date)
    qtr_days = _bdays_to(as_of_date, qtr_now.end_date)
    mo_w     = _ramp_weight(mo_days, ramp_mo_begin, lead_mo)
    qtr_w    = _ramp_weight(qtr_days, ramp_qtr_begin, lead_qtr)

    # Outlook lookup map
    outlook_map = {
        (r.category, r.sub_category): [r.quad1, r.quad2, r.quad3, r.quad4]
        for r in session.execute(text(
            "SELECT category, sub_category, quad1, quad2, quad3, quad4"
            " FROM ref_quad_outlook"
        )).fetchall()
    }

    if not outlook_map:
        log.info("derive_macronet: ref_quad_outlook is empty — skipping")
        return 0

    # Load symbols with fundamentals via drv_ma view
    sym_rows = session.execute(text("""
        SELECT tos_symbol, sector, asset_class,
               beta, pe_ratio, eps, div_yield, market_cap_str, rsi
        FROM drv_ma
        WHERE as_of_date = :d
    """), {'d': as_of_date}).fetchall()

    out = []
    for r in sym_rows:
        sector    = r.sector or ''
        asset_cls = r.asset_class or ''

        memberships = (
            [('Equity Sectors', sector, 2.0), ('Asset Class', asset_cls, 1.0)]
            + _classify_style(r.beta, r.pe_ratio, r.div_yield,
                              r.rsi, r.market_cap_str, sector)
        )

        mo_now_net  = _membership_net(memberships, outlook_map, mo_now_pcts)
        mo_next_net = _membership_net(memberships, outlook_map, mo_next_pcts)
        qtr_now_net  = _membership_net(memberships, outlook_map, qtr_now_pcts)
        qtr_next_net = _membership_net(memberships, outlook_map, qtr_next_pcts)

        M = (1 - mo_w) * mo_now_net + mo_w * mo_next_net
        Q = (1 - qtr_w) * qtr_now_net + qtr_w * qtr_next_net
        macronet = wt_mo * M + wt_qtr * Q

        out.append({
            'as_of_date':    as_of_date,
            'tos_symbol':    r.tos_symbol,
            'month_now_net': round(mo_now_net, 4),
            'month_next_net': round(mo_next_net, 4),
            'month_weight':  round(mo_w, 4),
            'monthly_score': round(M, 4),
            'qtr_now_net':   round(qtr_now_net, 4),
            'qtr_next_net':  round(qtr_next_net, 4),
            'qtr_weight':    round(qtr_w, 4),
            'quarterly_score': round(Q, 4),
            'macronet':      round(macronet, 4),
            'macro_action':  to_action(macronet),
        })

    if not out:
        return 0

    session.execute(text(
        "DELETE FROM drv_macro_score WHERE as_of_date = :d"
    ), {'d': as_of_date})
    session.execute(text("""
        INSERT INTO drv_macro_score
          (as_of_date, tos_symbol, month_now_net, month_next_net,
           month_weight, monthly_score, qtr_now_net, qtr_next_net,
           qtr_weight, quarterly_score, macronet, macro_action)
        VALUES
          (:as_of_date, :tos_symbol, :month_now_net, :month_next_net,
           :month_weight, :monthly_score, :qtr_now_net, :qtr_next_net,
           :qtr_weight, :quarterly_score, :macronet, :macro_action)
    """), out)
    session.commit()
    log.info("derive_macronet: %d symbols scored for %s", len(out), as_of_date)
    return len(out)
