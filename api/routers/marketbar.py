"""
Market tape endpoint.

GET /api/marketbar
  Returns the best available value for each enabled market metric, resolved
  from the registry (ref_market_metric) via pluggable source adapters
  (etl/marketbar.py).  Order: sort_order ASC.

Response shape:
  {
    "as_of": "2026-06-05",   # anchor date (MAX export_date FROM hist_td)
    "items": [
      {
        "metric_key":   "SPX",
        "label":        "S&P 500",
        "grp":          "index",
        "value":        5300.12,
        "chg":          -12.5,
        "chg_pct":      -0.24,
        "value_format": "index",
        "as_of":        "2026-06-05",
        "source":       "tos",
        "stale":        false,
        "rr_buy":       5100.0,    # optional – when hist_rr range available
        "rr_sell":      5600.0,
        "rr_outlook":   "Bullish"
      },
      ...
    ]
  }
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from etl.db import session_scope
from etl.marketbar import resolve_all

router = APIRouter(tags=["marketbar"])

# Maps marketbar metric_key → hist_rr tos_symbol (for range bar enrichment)
_METRIC_TO_RR_SYMBOL: dict[str, str] = {
    'SPX':  'SPX',
    'COMP': '$COMP',
    'RUT':  'RUT',
    'VIX':  'VIX',
    'WTI':  '/CL',
    'GC':   '/GC',
    'HY':   'HYG',
    'DXY':  '$DXY',
}

# Synthetic bar-1 items sourced directly from hist_rr
# (tos_symbol, metric_key, display_label, value_format)
_SYNTHETIC_BAR1 = [
    ('/BZ',       'BZ',    'Brent',   'price'),
]
_SYNTHETIC_KEYS = {mk for _, mk, _, _ in _SYNTHETIC_BAR1}
# synthetics that display % change — fetch pct_change from drv_quote
_SYNTHETIC_PCT_SYMS = {rr_sym for rr_sym, _, _, vfmt in _SYNTHETIC_BAR1 if vfmt == 'price'}

_HIST_RR_PREV_SQL = text(
    "SELECT tos_symbol, last_price FROM hist_rr WHERE snapshot_date="
    "(SELECT MAX(snapshot_date) FROM hist_rr WHERE snapshot_date<"
    "(SELECT MAX(snapshot_date) FROM hist_rr))"
)


def _hist_rr_pct(session) -> dict[str, float]:
    """Day-over-day % change from hist_rr for symbols that lack drv_quote pct_change."""
    cur = {r['tos_symbol']: float(r['last_price'])
           for r in session.execute(text(
               "SELECT tos_symbol, last_price FROM hist_rr "
               "WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM hist_rr)"
           )).mappings().all() if r['last_price'] is not None}
    prev = {r['tos_symbol']: float(r['last_price'])
            for r in session.execute(_HIST_RR_PREV_SQL).mappings().all()
            if r['last_price'] is not None}
    return {sym: round((c / prev[sym] - 1) * 100, 2)
            for sym, c in cur.items()
            if sym in prev and prev[sym] > 0}


@router.get("/api/marketbar")
def get_marketbar() -> dict:
    """Return the market tape: one resolved item per enabled metric, enriched with drv_rr ranges and drv_quote OHLC."""
    with session_scope() as s:
        items, anchor = resolve_all(s)
        # Range + outlook from drv_rr at anchor
        rr_lookup: dict[str, dict] = {
            r['tos_symbol']: {
                'buy':     float(r['lrr'])     if r['lrr']     is not None else None,
                'sell':    float(r['trr'])     if r['trr']     is not None else None,
                'outlook': r['outlook'],
            }
            for r in s.execute(text(
                "SELECT tos_symbol, lrr, trr, outlook FROM drv_rr "
                "WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_rr)"
            )).mappings().all()
        }
        # OHLC + pct_change from drv_quote at latest anchor
        ohlc_lookup: dict[str, dict] = {
            r['tos_symbol']: {
                'o':   float(r['open_price'])  if r['open_price']  is not None else None,
                'h':   float(r['high_price'])  if r['high_price']  is not None else None,
                'l':   float(r['low_price'])   if r['low_price']   is not None else None,
                'c':   float(r['last_price'])  if r['last_price']  is not None else None,
                'pct': float(r['pct_change'])  if r['pct_change']  is not None else None,
            }
            for r in s.execute(text(
                "SELECT tos_symbol, open_price, high_price, low_price, "
                "last_price, pct_change FROM drv_quote "
                "WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_quote)"
            )).mappings().all()
        }
        # hist_rr last_price: fallback for synthetic symbols not covered by drv_quote
        # (DGS2:FRED, TNX:CGI, TYX:CGI are FRED/index tickers only in hist_rr —
        # not in hist_tl/hist_td/hist_y — so drv_quote has no row for them).
        # HYG, LQD, /BZ, /BTC may appear in drv_quote; drv_quote price wins when present.
        # TODO follow-up: extend drv_quote feed to cover FRED/CGI rate tickers.
        hist_rr_price: dict[str, float | None] = {
            r['tos_symbol']: float(r['last_price']) if r['last_price'] is not None else None
            for r in s.execute(text(
                "SELECT tos_symbol, last_price FROM hist_rr "
                "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_rr)"
            )).mappings().all()
        }
        # Day-over-day pct from hist_rr — fallback for futures not in drv_quote
        rr_pct_fallback = _hist_rr_pct(s)

    # Enrich existing ref_market_metric items with rr range data + OHLC
    enriched = []
    for item in items:
        d = dict(item)
        if d.get('metric_key') in _SYNTHETIC_KEYS:
            continue  # will be replaced by synthetic below
        rr_sym = _METRIC_TO_RR_SYMBOL.get(d.get('metric_key', ''))
        rr = rr_lookup.get(rr_sym) if rr_sym else None
        if rr and rr['buy'] and rr['sell']:
            d['rr_buy']     = rr['buy']
            d['rr_sell']    = rr['sell']
            d['rr_outlook'] = rr['outlook']
        ohlc = ohlc_lookup.get(rr_sym) if rr_sym else None
        if ohlc:
            d['open']  = ohlc['o']
            d['high']  = ohlc['h']
            d['low']   = ohlc['l']
            d['close'] = ohlc['c']
        if d.get('chg_pct') is None and rr_sym:
            d['chg_pct'] = rr_pct_fallback.get(rr_sym)
        enriched.append(d)

    # Append synthetic items (rates + Brent + bonds).
    # Price: drv_quote (canonical) wins; hist_rr is fallback for symbols not in drv_quote.
    for rr_sym, metric_key, label, vfmt in _SYNTHETIC_BAR1:
        ohlc = ohlc_lookup.get(rr_sym)
        # Prefer drv_quote price; fall back to hist_rr for FRED/CGI tickers not in drv_quote
        last_price = (ohlc['c'] if ohlc and ohlc['c'] is not None
                      else hist_rr_price.get(rr_sym))
        price_source = 'drv_quote' if (ohlc and ohlc['c'] is not None) else 'hist_rr'
        if last_price is None:
            continue
        rr = rr_lookup.get(rr_sym)
        d: dict = {
            'metric_key':   metric_key,
            'label':        label,
            'grp':          'synthetic',
            'value':        last_price,
            'chg':          None,
            'chg_pct':      (ohlc['pct'] if (ohlc and ohlc['pct'] is not None)
                            else rr_pct_fallback.get(rr_sym)) if vfmt == 'price' else None,
            'value_format': vfmt,
            'as_of':        None,
            'source':       price_source,
            'stale':        False,
        }
        if rr and rr['buy'] and rr['sell']:
            d['rr_buy']     = rr['buy']
            d['rr_sell']    = rr['sell']
            d['rr_outlook'] = rr['outlook']
        if ohlc:
            d['open']  = ohlc['o']
            d['high']  = ohlc['h']
            d['low']   = ohlc['l']
            d['close'] = ohlc['c']
        enriched.append(d)

    return {
        "as_of": anchor.isoformat() if anchor else None,
        "items": enriched,
    }


# hist_rr tos_symbols covered by bar 1 — excluded from bar 2
_FIRST_BAR_RR = {
    'SPX', '$COMP', 'RUT', 'VIX', '$DXY',
    '/BZ', '/CL', '/GC',                 # Brent, WTI, Gold → bar 1
}

# Category + short label for each known RR symbol (bar 2 + bar 3)
_RR_META: dict[str, tuple[str, str]] = {
    '$SSEC':    ('Indexes',     'Shanghai'),
    'GDAXI:DE': ('Indexes',     'DAX'),
    'N225:JP':  ('Indexes',     'Nikkei'),
    '/6B':      ('FX',          'GBP/USD'),
    '/6C':      ('FX',          'CAD/USD'),
    '/6E':      ('FX',          'EUR/USD'),
    '/6J':      ('FX',          'USD/JPY'),
    '/CL':      ('Commodities', 'WTI'),
    '/GC':      ('Commodities', 'Gold'),
    '/BZ':      ('Commodities', 'Brent'),
    '/HG':      ('Commodities', 'Copper'),
    '/NG':      ('Commodities', 'Nat Gas'),
    '/SI':      ('Commodities', 'Silver'),
    '/BTC':     ('Crypto',      'Bitcoin'),
    'DGS2:FRED':('Rates',       '2Y'),
    'TNX:CGI':  ('Rates',       '10Y'),
    'TYX:CGI':  ('Rates',       '30Y'),
    'LQD':      ('Credit',      'IG Bond'),
    'HYG':      ('Credit',      'HY Bond'),
    'AAPL':     ('Tech',        'AAPL'),
    'AMZN':     ('Tech',        'AMZN'),
    'GOOGL':    ('Tech',        'GOOGL'),
    'META':     ('Tech',        'META'),
    'MSFT':     ('Tech',        'MSFT'),
    'NFLX':     ('Tech',        'NFLX'),
    'NVDA':     ('Tech',        'NVDA'),
    'ORCL':     ('Tech',        'ORCL'),
    'TSLA':     ('Tech',        'TSLA'),
    'DRAM':     ('ETFs',        'DRAM'),
    'GDX':      ('ETFs',        'GDX'),
    'IAK':      ('ETFs',        'IAK'),
    'ITA':      ('ETFs',        'ITA'),
    'PINK':     ('ETFs',        'PINK'),
    'SPMO':     ('ETFs',        'SPMO'),
    'URA':      ('ETFs',        'URA'),
    'XLE':      ('Sectors',     'XLE'),
    'XLF':      ('Sectors',     'XLF'),
    'XLK':      ('Sectors',     'XLK'),
    'XLP':      ('Sectors',     'XLP'),
    'XLRE':     ('Sectors',     'XLRE'),
    'XLU':      ('Sectors',     'XLU'),
    'XLY':      ('Sectors',     'XLY'),
}

_CATEGORY_ORDER = ['Rates', 'Commodities', 'ETFs', 'Sectors', 'Tech', 'Indexes', 'FX', 'Credit']

# Extended meta for the all-symbols (bar 3) endpoint — includes first-bar symbols
_RR_META_ALL: dict[str, tuple[str, str]] = {
    **_RR_META,
    'SPX':   ('Indexes', 'SPX'),
    '$COMP': ('Indexes', 'Nasdaq'),
    'RUT':   ('Indexes', 'Russell'),
    'VIX':   ('Risk',    'VIX'),
    '$DXY':  ('FX',      'DXY'),
}
_CATEGORY_ORDER_ALL = ['Indexes', 'Risk', 'FX', 'Commodities', 'Credit', 'Tech', 'ETFs']


def _build_rr_response(rows, meta: dict, cat_order: list,
                        exclude: set | None = None,
                        curated_only: bool = False,
                        rr_pct: dict | None = None) -> dict:
    """Shared builder for rr-bar endpoints.

    curated_only=True: skip any symbol not in meta (no 'Other' bucket).
    """
    groups: dict[str, list] = {cat: [] for cat in cat_order}
    other: list = []

    for row in rows:
        sym = row['tos_symbol'] or ''
        if exclude and sym in exclude:
            continue
        m = meta.get(sym)
        if curated_only and m is None:
            continue
        cat, label = m if m else ('Other', sym)

        q_price = float(row['q_price']) if row['q_price'] is not None else None
        pct     = (float(row['pct']) if row['pct'] is not None
                   else (rr_pct.get(sym) if rr_pct else None))

        buy  = float(row['buy_trade'])  if row['buy_trade']  is not None else None
        sell = float(row['sell_trade']) if row['sell_trade'] is not None else None

        item = {
            'symbol':    sym,
            'label':     label,
            'bar_price': q_price,
            'pct':       pct,
            'buy':       buy,
            'sell':      sell,
            'outlook':   row['outlook'] or 'Neutral',
            'name':      row.get('name') or sym,
            'open':      float(row['open_price'])  if row['open_price']  is not None else None,
            'high':      float(row['high_price'])  if row['high_price']  is not None else None,
            'low':       float(row['low_price'])   if row['low_price']   is not None else None,
            'close':     q_price,
        }
        if cat in groups:
            groups[cat].append(item)
        else:
            other.append(item)

    out = {k: v for k, v in groups.items() if v}
    if other:
        out['Other'] = other
    return {'groups': out}


_RR_SQL = text("""
    SELECT r.tos_symbol,
           h.name,
           r.lrr  AS buy_trade,
           r.trr  AS sell_trade,
           r.outlook,
           q.open_price, q.high_price, q.low_price,
           q.last_price AS q_price,
           q.pct_change AS pct
    FROM drv_rr r
    LEFT JOIN (
        SELECT DISTINCT ON (tos_symbol) tos_symbol, name
        FROM hist_rr ORDER BY tos_symbol, snapshot_date DESC
    ) h ON h.tos_symbol = r.tos_symbol
    LEFT JOIN drv_quote q
           ON q.tos_symbol = r.tos_symbol
          AND q.as_of_date = (SELECT MAX(as_of_date) FROM drv_quote)
    WHERE r.as_of_date = (SELECT MAX(as_of_date) FROM drv_rr)
    ORDER BY r.tos_symbol
""")


@router.get("/api/rr-bar")
def get_rr_bar() -> dict:
    """RR symbols grouped by category for the second market tape (curated list only)."""
    with session_scope() as s:
        rows = s.execute(_RR_SQL).mappings().all()
        pct_fb = _hist_rr_pct(s)
    return _build_rr_response(rows, _RR_META, _CATEGORY_ORDER,
                               exclude=_FIRST_BAR_RR, curated_only=True, rr_pct=pct_fb)


@router.get("/api/rr-bar-all")
def get_rr_bar_all() -> dict:
    """All hist_rr symbols for the third market tape (excludes bar-1 symbols)."""
    with session_scope() as s:
        rows = s.execute(_RR_SQL).mappings().all()
        pct_fb = _hist_rr_pct(s)
    return _build_rr_response(rows, _RR_META_ALL, _CATEGORY_ORDER_ALL,
                               exclude=_FIRST_BAR_RR, rr_pct=pct_fb)
