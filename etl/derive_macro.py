"""
MacroNet per-symbol score: MacroNet = (1 - q)*M_window + q*Qtr

M_window = sliding look-ahead window over the monthly quad calendar. The
window [D, D+H) (H = quad_lookahead_days, default 60 calendar days) is
projected onto ref_quad_periods' monthly rows; overlap-day fractions (with
optional exponential decay) produce a normalized weight per month. Each
month's own quad distribution feeds the standard Stage 1-2 membership
aggregation (sector x2 + asset_class x1 + styles x0.5); the per-month
stances are then weight-blended into one M_window per symbol. This replaces
the old month now/next ramp blend entirely -- the window itself is the
"days passed in month" ramp, sliding one day at a time (TASK_126).

Qtr = one-hot stance for the *current* quarter only (no next-quarter ramp
blend -- the quarterly ramp/lead params are retired alongside the monthly
ones; see window_weights()/_derive_macro_impl() and TASK_126 spec section 3).

Both legs use the same membership aggregation:
    net = sector×2 + asset_class×1 + Σ(style×0.5)

Results written to drv_macro_score (idempotent DELETE+INSERT). Full design:
docs/quad_design.md (Stage 3), agent-tasks/TASK_126_quad_lookahead_window.md.
"""

import calendar as _cal
import json
import logging
from datetime import date, timedelta

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
    """Score one symbol's membership bundle against a quad distribution
    (quad_pcts = fractions 0..1, index 0..3 = quad1..quad4)."""
    total = 0.0
    for cat, sub, wt in memberships:
        texts = outlook_map.get((cat, sub))
        if not texts:
            continue
        stance = sum(quad_pcts[i] * _stance(texts[i]) for i in range(4))
        total += wt * stance
    return total


def _onehot(quad_val):
    """Convert 'Quad N' or bare int/str N to one-hot [q1,q2,q3,q4]."""
    s = str(quad_val).strip()
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
    """p: a row/object with quad1_pct..quad4_pct. Returns fractions 0..1."""
    pcts = [float(getattr(p, f'quad{i+1}_pct') or 0) for i in range(4)]
    total = sum(pcts) or 1.0
    return [x / total for x in pcts]


def _dominant_quad_num(pcts_frac, declared_quad=None):
    """Argmax quad number (1-4) from fractions, falling back to the declared
    'Quad N' string when the distribution is missing/all-zero."""
    if pcts_frac and any(pcts_frac):
        return max(range(4), key=lambda i: pcts_frac[i]) + 1
    if declared_quad:
        s = str(declared_quad).strip()
        for tok in s.split():
            try:
                return int(tok)
            except ValueError:
                continue
        try:
            return int(s[-1])
        except (ValueError, IndexError):
            pass
    return None


def _effective_quad_label(p) -> str | None:
    """Argmax of quad1_pct..quad4_pct, falling back to the declared `quad`
    column when the distribution is missing/all-zero. Mirrors
    api/routers/dash.py::_effective_quad_col so the sparkline popup never
    disagrees with the MACRO tooltip about which quad a month's own
    distribution actually favors (ref_quad_periods.quad can be stale/
    inconsistent with its own quad1_pct..quad4_pct — the distribution wins)."""
    raw = [float(getattr(p, f'quad{i+1}_pct') or 0) for i in range(4)]
    if any(raw):
        best = max(range(4), key=lambda i: raw[i])
        return f"Quad {best + 1}"
    return p.quad


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


# =============================================================================
# Sliding look-ahead window — pure functions (TASK_126, unit-testable w/o DB)
# =============================================================================

def _day_weight(days_from_d: int, decay_hl: float) -> float:
    """Per-day weight inside the window. No decay (decay_hl<=0/None) -> 1.0
    for every day (flat window). Otherwise exponential half-life decay."""
    if not decay_hl or decay_hl <= 0:
        return 1.0
    return 0.5 ** (days_from_d / decay_hl)


def window_weights(d: date, months: list, h: int, decay_hl: float = 0):
    """Sliding look-ahead window [d, d+h) projected onto monthly periods.

    `months`: iterable of (year, period_num) tuples the caller has quad data
    for (may be a superset of the window -- non-overlapping months are
    dropped). `h`: window length in calendar days. `decay_hl`: optional
    half-life (days) for within-window day weighting; 0/None = flat (no
    decay, matches the spec's default-off behavior).

    Returns (weighted, coverage_pct):
      - weighted: [((year, period_num), weight), ...] sorted nearest-month
        first, weights normalized to sum to 1.0 over the *covered* portion
        of the window (empty list if zero coverage).
      - coverage_pct: % of the window's day-weight mass actually covered by
        `months`, out of 100. < 50 signals the caller should fall back to a
        current-month one-hot (see _derive_macro_impl).
    """
    window_end = d + timedelta(days=h)
    full_mass = sum(_day_weight(t, decay_hl) for t in range(h)) or 1.0

    raw = []  # (year, period_num, mass, dist_days_from_d)
    for (yr, pnum) in months:
        m_start = date(yr, pnum, 1)
        m_end = date(yr, pnum, _cal.monthrange(yr, pnum)[1]) + timedelta(days=1)  # exclusive
        ov_start = max(d, m_start)
        ov_end = min(window_end, m_end)
        if ov_end <= ov_start:
            continue
        mass = 0.0
        day = ov_start
        while day < ov_end:
            mass += _day_weight((day - d).days, decay_hl)
            day += timedelta(days=1)
        if mass > 0:
            raw.append((yr, pnum, mass, (m_start - d).days))

    covered_mass = sum(r[2] for r in raw)
    coverage_pct = round(min(100.0, covered_mass / full_mass * 100.0), 2)
    if covered_mass <= 0:
        return [], 0.0

    raw.sort(key=lambda r: r[3])
    weighted = [((r[0], r[1]), r[2] / covered_mass) for r in raw]
    return weighted, coverage_pct


def _month_key_label(ym: tuple) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


_SIGN_EPS = 1e-6  # treat stances smaller than this as exact zero (float noise
                   # from summing bullish/bearish membership legs that should
                   # cancel exactly, e.g. 5.5e-17, not a real "positive" tilt)


def _sign(v, eps: float = _SIGN_EPS) -> int:
    if v is None or abs(v) < eps:
        return 0
    return 1 if v > 0 else -1


def build_effective_distribution(weighted: list, pcts_by_month: dict) -> list:
    """eff_quad_k = Σ_m w_m × quad_k_pct(m) (fraction, index 0..3 = quad1..4).
    Months missing from `pcts_by_month` (shouldn't happen -- window_weights
    only returns months the caller supplied pcts for) contribute 0."""
    eff = [0.0, 0.0, 0.0, 0.0]
    for ym, w in weighted:
        pcts = pcts_by_month.get(ym)
        if not pcts:
            continue
        for i in range(4):
            eff[i] += w * pcts[i]
    return eff


def tracking_tag(technical_dir: float | None, weighted: list,
                  stance_by_month: dict, quad_by_month: dict) -> str | None:
    """First month (nearest-first) whose stance sign matches the symbol's
    current technical direction. None if no technical direction (neutral) or
    no month in the window agrees (UI shows a "fighting the quad path" cue)."""
    tdir = _sign(technical_dir)
    if tdir == 0:
        return None
    for ym, _w in weighted:
        sdir = _sign(stance_by_month.get(ym))
        if sdir == 0:
            continue
        if sdir == tdir:
            q = quad_by_month.get(ym)
            qlabel = f" (Quad {q})" if q else ""
            return f"{_month_key_label(ym)}{qlabel}"
    return None


def near_far_split(weighted: list, stance_by_month: dict):
    """Nearest month's own stance vs the weight-renormalized stance of the
    rest of the window. `far` is None when the window has only one month."""
    if not weighted:
        return None, None
    near_ym = weighted[0][0]
    near = stance_by_month.get(near_ym)
    rest = weighted[1:]
    rest_mass = sum(w for _ym, w in rest)
    if not rest or rest_mass <= 0:
        return near, None
    far = sum(w * stance_by_month.get(ym, 0.0) for ym, w in rest) / rest_mass
    return near, far


def to_action(macronet: float, near: float | None, far: float | None,
              thr_bm: float, thr_bs: float, thr_stm: float, thr_sa: float):
    """MacroNet -> vocab, with the sign-agreement override redefined on the
    window (near vs weighted-far). Returns (vocab, override_tag)."""
    if near is not None and far is not None:
        ns, fs = _sign(near), _sign(far)
        if ns > 0 and fs > 0:
            return ('BM' if macronet >= thr_bm else 'BS'), 'BS'
        if ns < 0 and fs < 0:
            return 'SA', 'SA'
    if macronet >= thr_bm:
        return 'BM', 'none'
    if macronet >= thr_bs:
        return 'BS', 'none'
    if macronet <= thr_sa:
        return 'SA', 'none'
    if macronet <= thr_stm:
        return 'STM', 'none'
    return 'HOLD', 'none'


def _load_settings(session):
    rows = session.execute(text(
        "SELECT setting_name, setting_value FROM ref_settings"
        " WHERE setting_name LIKE 'quad_%'"
        "    OR setting_name LIKE 'macronet_%'"
        "    OR setting_name LIKE 'macro_thr_%'"
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

    h = _int('quad_lookahead_days', 60)
    decay_hl = _float('quad_lookahead_decay_hl', 0)
    q = _float('quad_horizon_weight_qtr', 0.05)
    # Thresholds — use same setting names as API _macronet_to_vocab (macro_thr_*)
    # with fallback to legacy macronet_threshold_* settings.
    thr_bm  = _float('macro_thr_bm',  _float('macronet_threshold_sa',  1.5))
    thr_bs  = _float('macro_thr_bs',  _float('macronet_threshold_bm',  0.5))
    thr_stm = _float('macro_thr_stm', _float('macronet_threshold_stm', -0.5))
    thr_sa  = _float('macro_thr_sa',  _float('macronet_threshold_ss',  -1.5))

    cur_mo_y, cur_mo_n = as_of_date.year, as_of_date.month
    cur_qtr_y, cur_qtr_n = as_of_date.year, (as_of_date.month - 1) // 3 + 1

    qtr_now = session.execute(text(
        "SELECT period_type, year, period_num, quad,"
        " quad1_pct, quad2_pct, quad3_pct, quad4_pct"
        " FROM ref_quad_periods"
        " WHERE period_type='quarterly' AND year=:y AND period_num=:n"
    ), {'y': cur_qtr_y, 'n': cur_qtr_n}).fetchone()

    # All monthly rows with distribution data — used both for the window
    # calc and the per-month sparkline (monthly_scores_json), unchanged.
    all_monthly = session.execute(text(
        "SELECT year, period_num, quad, label,"
        " quad1_pct, quad2_pct, quad3_pct, quad4_pct"
        " FROM ref_quad_periods WHERE period_type='monthly'"
        " AND (quad1_pct IS NOT NULL OR quad2_pct IS NOT NULL"
        "   OR quad3_pct IS NOT NULL OR quad4_pct IS NOT NULL)"
        " ORDER BY year, period_num"
    )).fetchall()

    if not all_monthly or not qtr_now:
        log.info("derive_macronet: no quad period rows for %s — skipping", as_of_date)
        return 0

    _all_monthly_pcts = [_norm_pcts(p) for p in all_monthly]
    pcts_by_month = {(p.year, p.period_num): pcts
                      for p, pcts in zip(all_monthly, _all_monthly_pcts)}
    quad_by_month = {(p.year, p.period_num): _dominant_quad_num(pcts, p.quad)
                      for p, pcts in zip(all_monthly, _all_monthly_pcts)}
    months_available = list(pcts_by_month.keys())

    weighted, coverage_pct = window_weights(as_of_date, months_available, h, decay_hl)
    fallback = False
    if coverage_pct < 50.0:
        fallback = True
        cur_key = (cur_mo_y, cur_mo_n)
        if cur_key in pcts_by_month:
            weighted = [(cur_key, 1.0)]
        elif weighted:
            # keep whatever little coverage exists rather than nothing
            weighted = [(weighted[0][0], 1.0)]
        else:
            log.info("derive_macronet: zero window coverage for %s — skipping", as_of_date)
            return 0

    qtr_now_pcts = _onehot(qtr_now.quad)

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

    # Load symbols with fundamentals + technical-direction fields via drv_ma
    sym_rows = session.execute(text("""
        SELECT tos_symbol, sector, asset_class,
               beta, pe_ratio, eps, div_yield, market_cap_str, rsi,
               last_price, sma_50
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

        # Per-month stances for every month in the window (§2)
        stance_by_month = {
            ym: _membership_net(memberships, outlook_map, pcts_by_month[ym])
            for ym, _w in weighted
        }
        M_window = sum(w * stance_by_month[ym] for ym, w in weighted)

        Qtr = _membership_net(memberships, outlook_map, qtr_now_pcts)

        macronet = round((1.0 - q) * M_window + q * Qtr, 4)

        near, far = near_far_split(weighted, stance_by_month)
        vocab, override_tag = to_action(macronet, near, far, thr_bm, thr_bs, thr_stm, thr_sa)

        # Technical direction: sign(last_price - sma_50) — simplest existing
        # trend field already exposed via drv_ma at this point in the derive
        # cascade (drv_actionable/trig_action don't exist yet here). See
        # docs/quad_design.md / DEV_HANDOFF for the choice rationale.
        tech_dir = None
        try:
            if r.last_price is not None and r.sma_50 not in (None, 0):
                tech_dir = float(r.last_price) - float(r.sma_50)
        except (TypeError, ValueError):
            tech_dir = None
        tracking = tracking_tag(tech_dir, weighted, stance_by_month, quad_by_month)

        eff_frac = build_effective_distribution(weighted, pcts_by_month)
        eff_pct = {f"q{i+1}": round(eff_frac[i] * 100, 1) for i in range(4)}

        # Per-month agreement flag (same sign-comparison tracking_tag() uses
        # internally, but exposed for every month in the window instead of
        # just the first match) -- lets the UI show a checkmark/x per month
        # rather than only naming the single nearest confirming one.
        # None = no technical direction to compare against at all (not a
        # disagreement, just nothing to check); True/False = that month's
        # stance does/doesn't share the technical direction's sign.
        tdir_sign = _sign(tech_dir)
        months_detail = [
            {
                "m": _month_key_label(ym),
                "quad": quad_by_month.get(ym),
                "w": round(w, 4),
                "stance": round(stance_by_month[ym], 4),
                "agrees": (_sign(stance_by_month[ym]) == tdir_sign) if tdir_sign != 0 else None,
            }
            for ym, w in weighted
        ]

        detail = {
            "h": h,
            "coverage_pct": coverage_pct,
            "fallback": fallback,
            "months": months_detail,
            "eff": eff_pct,
            "near_vs_far": {
                "near": round(near, 4) if near is not None else None,
                "far": round(far, 4) if far is not None else None,
                "override": override_tag,
            },
            "tracking": tracking,
        }

        # Per-month scores for all available periods (sparkline data) —
        # unchanged, still Stage 1-2 stance vs each individual month.
        monthly_scores = []
        for p, pcts in zip(all_monthly, _all_monthly_pcts):
            net_m = _membership_net(memberships, outlook_map, pcts)
            _fallback_lbl = f"{_cal.month_abbr[p.period_num]}-{str(p.year)[2:]}"
            _lbl = p.label if (p.label and len(str(p.label)) < 20) else _fallback_lbl
            monthly_scores.append({
                'label':      _lbl,
                'year':       p.year,
                'period_num': p.period_num,
                'quad':       _effective_quad_label(p),
                'score':      round(net_m, 4),
                'is_current': (p.year == cur_mo_y and p.period_num == cur_mo_n),
                'q1': float(p.quad1_pct or 0),
                'q2': float(p.quad2_pct or 0),
                'q3': float(p.quad3_pct or 0),
                'q4': float(p.quad4_pct or 0),
            })

        out.append({
            'as_of_date':    as_of_date,
            'tos_symbol':    r.tos_symbol,
            'month_now_net': None,
            'month_next_net': None,
            'month_weight':  None,
            'monthly_score': round(M_window, 4),
            'qtr_now_net':   round(Qtr, 4),
            'qtr_next_net':  None,
            'qtr_weight':    None,
            'quarterly_score': round(Qtr, 4),
            'macronet':           macronet,
            'macro_action':       vocab,
            'monthly_scores_json': json.dumps(monthly_scores),
            'detail':             json.dumps(detail),
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
           qtr_weight, quarterly_score, macronet, macro_action,
           monthly_scores_json, detail)
        VALUES
          (:as_of_date, :tos_symbol, :month_now_net, :month_next_net,
           :month_weight, :monthly_score, :qtr_now_net, :qtr_next_net,
           :qtr_weight, :quarterly_score, :macronet, :macro_action,
           :monthly_scores_json, :detail)
    """), out)
    session.commit()
    log.info("derive_macronet: %d symbols scored for %s (window h=%d, coverage=%.1f%%)",
              len(out), as_of_date, h, coverage_pct)
    return len(out)
