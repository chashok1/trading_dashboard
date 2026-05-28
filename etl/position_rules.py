"""
Position-rule resolver.

ONE function used by both Actionable (sizing math) and Portfolio (limit
display) so categorization stays consistent across screens.

For PS and ETF/ETFCHG sources the lookup category is the per-symbol
`asset_class` from hist_ps / hist_etf — NOT the literal 'PS' or 'etf'.
For every other source it's the source's `position_category` from
ref_outlook_source.

The resolver answers:
  resolve_symbol_category(session, symbol, as_of_date) -> str | None
  resolve_position_rule  (session, symbol, as_of_date) -> dict | None

Returned rule dict shape:
  {
    'category':              <str>,    # the resolved lookup key
    'min_dollar':            <num>,
    'max_dollar':            <num>,
    'units':                 <num>,
    'maintain_min_position': <bool>,
    'winning_source':        <str>,    # which ref_outlook_source won
    'asset_class_source':    <str>,    # 'hist_ps' / 'hist_etf' / None
  }

Both functions accept an optional `cache` dict so callers iterating over
many symbols can reuse a single dict across calls.
"""
from __future__ import annotations
from datetime import date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


# Sources whose ref_asset_allocation lookup key is the per-symbol
# asset_class from a hist_* column rather than ref_outlook_source.position_category.
_PER_SYMBOL_ASSET_CLASS_SOURCES = {
    "PS":     ("hist_ps", "ticker", "snapshot_date", "asset_class"),
    "ETF":    ("hist_etf",  "symbol", "snapshot_date", "asset_class"),
    # ETFCHG has no asset_class column on its own, so fall back to hist_etf
    "ETFCHG": ("hist_etf",  "symbol", "snapshot_date", "asset_class"),
}


# ---------------------------------------------------------------------------
# Step 1: pick the winning source for a symbol
# ---------------------------------------------------------------------------

def _winning_source(session: Session, symbol: str, as_of_date: date,
                    cache: Optional[dict] = None) -> Optional[str]:
    """Lowest investment_priority among ref_outlook_source rows where the symbol
    has data in the source's table on/before as_of_date.
    Reads drv_actionable first if a row exists for that snapshot — that's the
    authoritative answer once derive_actionable has run."""
    if cache is not None:
        ck = ("win", symbol, as_of_date)
        if ck in cache: return cache[ck]

    # Prefer the answer drv_actionable already computed
    row = session.execute(text("""
        SELECT winning_source FROM drv_actionable
        WHERE tos_symbol = :s AND as_of_date = :d
    """), {"s": symbol, "d": as_of_date}).first()
    if row and row[0]:
        if cache is not None: cache[ck] = row[0]
        return row[0]

    # Fall back: scan ref_outlook_source for the lowest-priority source
    # that actually has a row for this symbol on/before as_of_date.
    sources = session.execute(text("""
        SELECT source_code, source_table, investment_priority
        FROM ref_outlook_source
        WHERE deprecated_at IS NULL
        ORDER BY investment_priority ASC, source_code
    """)).fetchall()

    best: Optional[str] = None
    best_pri = 10**9
    for sc, tbl, pri in sources:
        date_col = "event_date" if tbl in ("hist_etfchg", "hist_iichg") else "snapshot_date"
        key_col  = "ticker"      if tbl in ("hist_ps",) else "symbol"
        try:
            hit = session.execute(text(f"""
                SELECT 1 FROM {tbl}
                WHERE {key_col} = :s AND {date_col} <= :d
                LIMIT 1
            """), {"s": symbol, "d": as_of_date}).first()
        except Exception:
            hit = None
        if hit and pri < best_pri:
            best, best_pri = sc, pri
    if cache is not None: cache[ck] = best
    return best


# ---------------------------------------------------------------------------
# Step 2: resolve lookup key (asset_class for PS/ETF/ETFCHG, else position_category)
# ---------------------------------------------------------------------------

def resolve_symbol_category(session: Session, symbol: str, as_of_date: date,
                            cache: Optional[dict] = None) -> Optional[str]:
    """The string we use to look up ref_asset_allocation.category."""
    if cache is not None:
        ck = ("cat", symbol, as_of_date)
        if ck in cache: return cache[ck]

    src = _winning_source(session, symbol, as_of_date, cache)
    if not src:
        if cache is not None: cache[ck] = None
        return None

    if src in _PER_SYMBOL_ASSET_CLASS_SOURCES:
        tbl, key_col, date_col, ac_col = _PER_SYMBOL_ASSET_CLASS_SOURCES[src]
        try:
            ac = session.execute(text(f"""
                SELECT {ac_col} FROM {tbl}
                WHERE {key_col} = :s AND {date_col} <= :d
                ORDER BY {date_col} DESC LIMIT 1
            """), {"s": symbol, "d": as_of_date}).scalar()
        except Exception:
            ac = None
        if ac:
            if cache is not None: cache[ck] = ac
            return ac
        # fall through to source's default category if asset_class missing

    cat = session.execute(text("""
        SELECT position_category FROM ref_outlook_source
        WHERE source_code = :sc
    """), {"sc": src}).scalar()
    if cache is not None: cache[ck] = cat
    return cat


# ---------------------------------------------------------------------------
# Step 3: load the actual rule row from ref_asset_allocation
# ---------------------------------------------------------------------------

def resolve_position_rule(session: Session, symbol: str, as_of_date: date,
                          cache: Optional[dict] = None) -> Optional[dict]:
    """Returns the rule dict for the symbol, or None if no rule applies."""
    cat = resolve_symbol_category(session, symbol, as_of_date, cache)
    if not cat:
        return None

    if cache is not None:
        rk = ("rule", cat)
        if rk in cache:
            rule = cache[rk]
        else:
            rule = _load_rule(session, cat)
            cache[rk] = rule
    else:
        rule = _load_rule(session, cat)

    if not rule:
        return None

    src = _winning_source(session, symbol, as_of_date, cache)
    ac_src = (
        _PER_SYMBOL_ASSET_CLASS_SOURCES[src][0]
        if src in _PER_SYMBOL_ASSET_CLASS_SOURCES
        else None
    )

    return {
        "category":              rule.get("category"),
        "min_dollar":            float(rule["min_dollar"]) if rule.get("min_dollar")   is not None else None,
        "max_dollar":            float(rule["max_dollar"]) if rule.get("max_dollar")   is not None else None,
        "units":                 float(rule["units"])      if rule.get("units")        is not None else None,
        "maintain_min_position": bool(rule.get("maintain_min_position")),
        "winning_source":        src,
        "asset_class_source":    ac_src,
    }


def _load_rule(session: Session, category: str) -> Optional[dict]:
    row = session.execute(text("""
        SELECT category, min_dollar, max_dollar, units, maintain_min_position
        FROM ref_asset_allocation
        WHERE category = :c
    """), {"c": category}).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Convenience: classify status of a current $ position against its rule
# ---------------------------------------------------------------------------

def classify_position_status(current_dollar: Optional[float],
                              rule: Optional[dict]) -> str:
    """Returns one of BELOW_MIN | WITHIN | ABOVE_MAX | AT_FLOOR | NO_LIMIT."""
    if not rule or current_dollar is None:
        return "NO_LIMIT"
    cd = float(current_dollar)
    mn = rule.get("min_dollar")
    mx = rule.get("max_dollar")
    if mn is not None and cd < mn:
        return "BELOW_MIN"
    if mx is not None and cd > mx:
        return "ABOVE_MAX"
    # at-floor edge: position equals min and maintain_min is on
    if mn is not None and rule.get("maintain_min_position") and abs(cd - mn) < 1e-6:
        return "AT_FLOOR"
    return "WITHIN"
