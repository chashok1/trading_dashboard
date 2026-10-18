"""
MacroNet per-symbol score: MacroNet = (1 - q)*M_window + q*Qtr

M_window = sliding look-ahead window over the monthly quad calendar. The
window [D, D+H) (H = quad_lookahead_days, default 60 calendar days) is
projected onto ref_quad_periods' monthly rows; overlap-day fractions (with
optional exponential decay) give a normalized weight per month. Each month's
own quad distribution feeds the membership aggregation below, and the
per-month stances are weight-blended into one M_window per symbol.

Qtr = one-hot stance for the current quarter. During the quarter's last
calendar month only, it fades linearly into the next quarter's one-hot stance
(see _quarter_fade_weight).

Both legs use the same membership aggregation:
    net = sector×2 + asset_class×1 + Σ(style×0.5)

The final tag comes from score cut-offs only (to_action); the old near/far
sign-agreement override was removed 2026-10-18.

Results written to drv_macro_score (idempotent DELETE+INSERT).
Full design: docs/quad_design.md.
"""

import calendar as _cal
import json
import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.warnings import add_warning, clear_screen_warnings

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

# Sector / sub_asset_class tags that deliberately get NO sector membership
# (skipped before the ref_quad_outlook lookup, so they never raise the
# missing-outlook warning). Gold/USD are already scored via 'Asset Class';
# Country ETF has no single quad view; 'Fixed Income' and 'Fixed Income
# Volatility' are catch-all/vol-gauge labels, not directional sub-categories.
_NO_SECTOR_MEMBERSHIP = {
    'Country ETF', 'Gold', 'USD', 'Fixed Income', 'Fixed Income Volatility',
}


def _stance(v):
    return _STANCE.get(v, 0.0)


def _outlook_key(cat, sub):
    """Case/whitespace-insensitive key into outlook_map, so a casing slip in
    the user-editable ref_quad_outlook table (e.g. 'Health care' vs 'Health
    Care') can't silently blank a category's stance. Genuinely absent
    categories are reported via the missing_outlook_keys warning."""
    if cat is None or sub is None:
        return None
    return (str(cat).strip().lower(), str(sub).strip().lower())


def _window_stance_for(cat, sub, outlook_map, weighted, pcts_by_month, missing=None):
    """Window-weighted stance for ONE (cat, sub) membership, same weighting as
    M_window but not summed with the symbol's other memberships (drives the
    MACRO column's sector/asset-class/style dots). Returns None if there is
    no ref_quad_outlook row; `missing`, if passed, collects that pair."""
    texts = outlook_map.get(_outlook_key(cat, sub))
    if not texts:
        if missing is not None and cat and sub:
            missing.add((cat, sub))
        return None
    total = 0.0
    for ym, w in weighted:
        pcts = pcts_by_month[ym]
        stance = sum(pcts[i] * _stance(texts[i]) for i in range(4))
        total += w * stance
    return round(total, 4)


# One-hot quad_pcts, index 0..3 = Quad 1..4, for the per-quad isolated
# stance (quad{N}_net).
_ONEHOT_QUADS = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _membership_net(memberships, outlook_map, quad_pcts, missing=None):
    """Score one symbol's membership bundle against a quad distribution
    (quad_pcts = fractions 0..1, index 0..3 = quad1..quad4). `missing`, if
    passed, collects any (cat, sub) pair with no ref_quad_outlook row."""
    total = 0.0
    for cat, sub, wt in memberships:
        texts = outlook_map.get(_outlook_key(cat, sub))
        if not texts:
            if missing is not None and cat and sub:
                missing.add((cat, sub))
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


def _quarter_bounds(y: int, qn: int):
    """(start_date, end_date) of calendar quarter qn (1-4) of year y."""
    start_month = (qn - 1) * 3 + 1
    end_month = start_month + 2
    end_day = _cal.monthrange(y, end_month)[1]
    return date(y, start_month, 1), date(y, end_month, end_day)


def _next_quarter(y: int, qn: int):
    return (y + 1, 1) if qn == 4 else (y, qn + 1)


def _quarter_fade_weight(as_of_date: date, qtr_end: date) -> float:
    """Next-quarter blend weight (0..1). 0 outside the quarter's last
    calendar month; inside it, linear by day-of-month: day 1 -> 0.0 (100%
    current quarter), last day of that month -> 1.0 (100% next quarter)."""
    if as_of_date.month != qtr_end.month or as_of_date.year != qtr_end.year:
        return 0.0
    dim = _cal.monthrange(as_of_date.year, as_of_date.month)[1]
    if dim <= 1:
        return 1.0
    return max(0.0, min(1.0, (as_of_date.day - 1) / (dim - 1)))


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

    # TOS reports market cap "0" for indices/futures/FX; treat it as no data
    # (otherwise SPX, VIX, /GC, ... would be tagged Small Caps).
    if mc:
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
    """MacroNet -> vocab, by score cut-offs only. The near/far sign-agreement
    override was removed (replay test 2026-10-18: it hurt in 6 of 6 setting
    combinations). near/far are still accepted (kept for the detail JSON) but
    no longer affect the tag; override_tag is always 'none'."""
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
    # Same macro_thr_* names the API uses; legacy macronet_threshold_* as fallback.
    thr_bm  = _float('macro_thr_bm',  _float('macronet_threshold_sa',  1.5))
    thr_bs  = _float('macro_thr_bs',  _float('macronet_threshold_bm',  0.5))
    thr_stm = _float('macro_thr_stm', _float('macronet_threshold_stm', -0.5))
    thr_sa  = _float('macro_thr_sa',  _float('macronet_threshold_ss',  -1.5))

    cur_mo_y, cur_mo_n = as_of_date.year, as_of_date.month
    cur_qtr_y, cur_qtr_n = as_of_date.year, (as_of_date.month - 1) // 3 + 1
    _qtr_start, qtr_end = _quarter_bounds(cur_qtr_y, cur_qtr_n)
    nxt_qtr_y, nxt_qtr_n = _next_quarter(cur_qtr_y, cur_qtr_n)

    qtr_now = session.execute(text(
        "SELECT period_type, year, period_num, quad,"
        " quad1_pct, quad2_pct, quad3_pct, quad4_pct"
        " FROM ref_quad_periods"
        " WHERE period_type='quarterly' AND year=:y AND period_num=:n"
    ), {'y': cur_qtr_y, 'n': cur_qtr_n}).fetchone()

    # Next quarter is always loaded for the tooltip; its weight (qtr_fade) is
    # 0 except in the current quarter's last calendar month.
    qtr_next = session.execute(text(
        "SELECT period_type, year, period_num, quad,"
        " quad1_pct, quad2_pct, quad3_pct, quad4_pct"
        " FROM ref_quad_periods"
        " WHERE period_type='quarterly' AND year=:y AND period_num=:n"
    ), {'y': nxt_qtr_y, 'n': nxt_qtr_n}).fetchone()
    qtr_fade = _quarter_fade_weight(as_of_date, qtr_end) if qtr_next is not None else 0.0

    # Monthly rows with distribution data: feeds the window and the
    # per-month sparkline (monthly_scores_json).
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
    qtr_next_pcts = _onehot(qtr_next.quad) if qtr_next is not None else None

    # Outlook lookup, keyed by the normalized _outlook_key.
    outlook_map = {
        _outlook_key(r.category, r.sub_category): [r.quad1, r.quad2, r.quad3, r.quad4]
        for r in session.execute(text(
            "SELECT category, sub_category, quad1, quad2, quad3, quad4"
            " FROM ref_quad_outlook"
        )).fetchall()
    }
    # (cat, sub) memberships with no ref_quad_outlook row; flushed to
    # meta_warning after the symbol loop.
    missing_outlook_keys: set = set()

    if not outlook_map:
        log.info("derive_macronet: ref_quad_outlook is empty — skipping")
        return 0

    sym_rows = session.execute(text("""
        SELECT tos_symbol, sector, asset_class, sub_asset_class,
               beta, pe_ratio, eps, div_yield, market_cap_str, rsi,
               last_price, sma_50
        FROM drv_ma
        WHERE as_of_date = :d
    """), {'d': as_of_date}).fetchall()

    # drv_ma joins ref_sector on ticker = tos_symbol, which misses index/
    # futures/FX symbols whose Yahoo ticker differs (SPX vs '^SPX', /GC vs
    # 'GC=F'). Bridge those via ref_rrt (tos_ticker -> y_ticker); DISTINCT ON
    # guards against duplicate y_ticker rows for one tos_ticker.
    bridge_rows = session.execute(text("""
        SELECT DISTINCT ON (rrt.tos_ticker)
               rrt.tos_ticker, rs.equity_sector, rs.asset_class, rs.sub_asset_class
        FROM ref_rrt rrt
        JOIN ref_sector rs ON rs.ticker = rrt.y_ticker
        WHERE rrt.tos_ticker IS NOT NULL
        ORDER BY rrt.tos_ticker, rrt.preferred_display DESC NULLS LAST, rrt.y_ticker
    """)).fetchall()
    bridge_map = {b.tos_ticker: b for b in bridge_rows}

    out = []
    for r in sym_rows:
        sector      = r.sector or ''
        asset_cls   = r.asset_class or ''
        sub_asset   = r.sub_asset_class
        if not sector and not asset_cls:
            b = bridge_map.get(r.tos_symbol)
            if b:
                # equity_sector is not taken from the bridge: for these rows
                # it is a placeholder default (FX -> Financials, indices ->
                # arbitrary GICS names). asset_class/sub_asset_class are
                # accurate and drive the Fixed Income redirect below.
                asset_cls = b.asset_class or ''
                sub_asset = b.sub_asset_class

        # Fixed Income instruments carry a placeholder "Financials" sector, so
        # score them against the dedicated 'Fixed Income' outlook category
        # (sub-categories match sub_asset_class: HY Credit, IG Credit, ...).
        # An unmatched sub_asset_class gets no sector membership.
        if asset_cls == 'Fixed Income':
            sector_cat, sector_sub = 'Fixed Income', (sub_asset or '')
            if sector_sub in _NO_SECTOR_MEMBERSHIP:
                sector_sub = ''
        elif sector in _NO_SECTOR_MEMBERSHIP:
            # Non-GICS pseudo-sectors (Country ETF/Gold/USD): no sector dot.
            sector_cat, sector_sub = 'Equity Sectors', ''
        else:
            sector_cat, sector_sub = 'Equity Sectors', sector

        memberships = (
            [(sector_cat, sector_sub, 2.0), ('Asset Class', asset_cls, 1.0)]
            + _classify_style(r.beta, r.pe_ratio, r.div_yield,
                              r.rsi, r.market_cap_str, sector)
        )

        stance_by_month = {
            ym: _membership_net(memberships, outlook_map, pcts_by_month[ym],
                                 missing=missing_outlook_keys)
            for ym, _w in weighted
        }
        M_window = sum(w * stance_by_month[ym] for ym, w in weighted)

        Qtr_cur = _membership_net(memberships, outlook_map, qtr_now_pcts,
                                   missing=missing_outlook_keys)
        Qtr_next = (_membership_net(memberships, outlook_map, qtr_next_pcts,
                                     missing=missing_outlook_keys)
                    if qtr_next_pcts is not None else None)
        Qtr = ((1.0 - qtr_fade) * Qtr_cur + qtr_fade * Qtr_next
               if Qtr_next is not None else Qtr_cur)

        macronet = round((1.0 - q) * M_window + q * Qtr, 4)

        # Per-quad isolated stance ("if Quad N were certain"): same memberships
        # as macronet, one-hot quad input. Feeds the Universe Q1-Q4 filter.
        quad_isolated = [
            round(_membership_net(memberships, outlook_map, _ONEHOT_QUADS[i]), 4)
            for i in range(4)
        ]

        near, far = near_far_split(weighted, stance_by_month)
        vocab, override_tag = to_action(macronet, near, far, thr_bm, thr_bs, thr_stm, thr_sa)

        # Technical direction = last_price - sma_50 (drv_actionable/trig_action
        # don't exist yet at this point in the derive cascade).
        tech_dir = None
        try:
            if r.last_price is not None and r.sma_50 not in (None, 0):
                tech_dir = float(r.last_price) - float(r.sma_50)
        except (TypeError, ValueError):
            tech_dir = None
        tracking = tracking_tag(tech_dir, weighted, stance_by_month, quad_by_month)

        eff_frac = build_effective_distribution(weighted, pcts_by_month)
        eff_pct = {f"q{i+1}": round(eff_frac[i] * 100, 1) for i in range(4)}

        # "agrees" per window month: None = no technical direction to compare;
        # True/False = the month's stance does/doesn't share its sign.
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

        # Technical direction vs the sign of the final macronet. None = no
        # direction or a flat score; True = they disagree.
        macronet_sign = _sign(macronet)
        tracking_conflict = (
            (tdir_sign != macronet_sign) if (tdir_sign != 0 and macronet_sign != 0) else None
        )

        # Same shape as the monthly `months` list; the next-quarter leg has
        # w = 0 until the last-month fade starts.
        quarter_window = {
            "cur": {
                "label": f"{cur_qtr_y}-Q{cur_qtr_n}",
                "quad": _dominant_quad_num(qtr_now_pcts, qtr_now.quad),
                "w": round(1.0 - qtr_fade, 4),
                "stance": round(Qtr_cur, 4),
            },
            "dtb": (qtr_end - as_of_date).days,
        }
        if Qtr_next is not None:
            quarter_window["next"] = {
                "label": f"{nxt_qtr_y}-Q{nxt_qtr_n}",
                "quad": _dominant_quad_num(qtr_next_pcts, qtr_next.quad),
                "w": round(qtr_fade, 4),
                "stance": round(Qtr_next, 4),
            }

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
            "tracking_conflict": tracking_conflict,
            "quarter_window": quarter_window,
        }

        # Sparkline data: stance vs each individual month.
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

        # Per-membership stances for the MACRO column dots. memberships[0] is
        # the sector, [1] the asset class, [2:] the style tags.
        sector_stance = _window_stance_for(
            sector_cat, sector_sub, outlook_map, weighted, pcts_by_month,
            missing=missing_outlook_keys) if sector_sub else None
        asset_class_stance = _window_stance_for(
            'Asset Class', asset_cls, outlook_map, weighted, pcts_by_month,
            missing=missing_outlook_keys) if asset_cls else None
        style_stances = []
        for cat, sub, _wt in memberships[2:]:
            st = _window_stance_for(cat, sub, outlook_map, weighted, pcts_by_month,
                                     missing=missing_outlook_keys)
            if st is not None:
                style_stances.append({'label': sub, 'stance': st})

        out.append({
            'as_of_date':    as_of_date,
            'tos_symbol':    r.tos_symbol,
            'month_now_net': None,
            'month_next_net': None,
            'month_weight':  None,
            'monthly_score': round(M_window, 4),
            'qtr_now_net':   round(Qtr_cur, 4),
            'qtr_next_net':  round(Qtr_next, 4) if Qtr_next is not None else None,
            'qtr_weight':    round(qtr_fade, 4),
            'quarterly_score': round(Qtr, 4),
            'macronet':           macronet,
            'macro_action':       vocab,
            'quad1_net':          quad_isolated[0],
            'quad2_net':          quad_isolated[1],
            'quad3_net':          quad_isolated[2],
            'quad4_net':          quad_isolated[3],
            'monthly_scores_json': json.dumps(monthly_scores),
            'detail':             json.dumps(detail),
            'sector_stance':      sector_stance,
            'asset_class_stance': asset_class_stance,
            'style_stances':      json.dumps(style_stances),
        })

    # Surface any (cat, sub) membership this run actually needed but found
    # no ref_quad_outlook row for at all (a genuine gap _outlook_key's
    # normalization can't paper over — e.g. a whole new sector/style with
    # no outlook row yet) — was previously a silent blank stance with no
    # trace anywhere. Same meta_warning mechanism the topbar badge already
    # polls (web/warning_badge.js -> GET /api/warnings), so it's visible
    # without having to know to look for it.
    clear_screen_warnings(session, "quad_outlook", as_of_date=as_of_date)
    for cat, sub in sorted(missing_outlook_keys):
        add_warning(
            session, "quad_outlook",
            f"No ref_quad_outlook row for '{cat}' / '{sub}' — quad stance "
            f"blank for this category. Add a row on the Ref Data screen "
            f"(ref_quad_outlook) with this exact category/sub_category.",
            as_of_date=as_of_date, code="missing_quad_outlook_row",
        )

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
           monthly_scores_json, detail,
           sector_stance, asset_class_stance, style_stances,
           quad1_net, quad2_net, quad3_net, quad4_net)
        VALUES
          (:as_of_date, :tos_symbol, :month_now_net, :month_next_net,
           :month_weight, :monthly_score, :qtr_now_net, :qtr_next_net,
           :qtr_weight, :quarterly_score, :macronet, :macro_action,
           :monthly_scores_json, :detail,
           :sector_stance, :asset_class_stance, :style_stances,
           :quad1_net, :quad2_net, :quad3_net, :quad4_net)
    """), out)
    session.commit()
    log.info("derive_macronet: %d symbols scored for %s (window h=%d, coverage=%.1f%%)",
              len(out), as_of_date, h, coverage_pct)
    return len(out)
