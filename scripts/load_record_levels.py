"""One-off / refreshable loader for ref_record_level (all-time high/low, daily closes).

Sources: FRED series already in hist_macro (yields, WTI) and Yahoo full daily
history (everything else). Read-only downloads; only writes ref_record_level.

    python scripts/load_record_levels.py            # fetch + upsert + print
    python scripts/load_record_levels.py --dry-run  # fetch + print only
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from etl.db import session_scope  # noqa: E402

# key, label, unit, yahoo ticker
YAHOO = [
    ("spx", "S&P 500", "index", "^GSPC"),
    ("ndx", "Nasdaq 100", "index", "^NDX"),
    ("rut", "Russell 2000", "index", "^RUT"),
    ("dji", "Dow Jones", "index", "^DJI"),
    ("vix", "VIX", "index", "^VIX"),
    ("move", "MOVE (bond vol)", "index", "^MOVE"),
    ("dxy", "US Dollar Index", "index", "DX-Y.NYB"),
    ("gold", "Gold (futures)", "usd", "GC=F"),
    ("silver", "Silver (futures)", "usd", "SI=F"),
    ("btc", "Bitcoin", "usd", "BTC-USD"),
    ("us30y", "30-year yield", "pct", "^TYX"),
]
# key, label, unit, hist_macro series_id
FRED = [
    ("us2y", "2-year yield", "pct", "DGS2"),
    ("us10y", "10-year yield", "pct", "DGS10"),
    ("us3m", "3-month yield", "pct", "DGS3MO"),
    ("wti", "WTI oil (spot)", "usd", "DCOILWTICO"),
]


def _extremes(dates, vals):
    pairs = [(d, float(v)) for d, v in zip(dates, vals) if v is not None and v == v]
    hi = max(pairs, key=lambda p: p[1])
    lo = min(pairs, key=lambda p: p[1])
    return hi, lo, pairs[0][0], pairs[-1][0]


def collect(session):
    import yfinance as yf

    out = []
    for key, label, unit, tkr in YAHOO:
        try:
            h = yf.Ticker(tkr).history(period="max", auto_adjust=False)
            h = h[h["Close"].notna()]
            hi, lo, d0, d1 = _extremes([d.date() for d in h.index], h["Close"].tolist())
            out.append((key, label, unit, hi, lo, d0, d1, f"yahoo:{tkr}"))
        except Exception as e:  # noqa: BLE001
            print(f"!! {key} ({tkr}) failed: {e}")
    for key, label, unit, sid in FRED:
        rows = session.execute(text(
            "SELECT obs_date, value FROM hist_macro WHERE series_id=:s AND value IS NOT NULL "
            "ORDER BY obs_date"), {"s": sid}).fetchall()
        if rows:
            hi, lo, d0, d1 = _extremes([r[0] for r in rows], [r[1] for r in rows])
            out.append((key, label, unit, hi, lo, d0, d1, f"fred:{sid}"))
    return out


def main():
    dry = "--dry-run" in sys.argv
    with session_scope() as s:
        res = collect(s)
        for key, label, unit, hi, lo, d0, d1, src in res:
            print(f"{key:7} {label:20} HIGH {hi[1]:>12,.2f} on {hi[0]} | LOW {lo[1]:>12,.2f} on {lo[0]} "
                  f"| {d0}..{d1} | {src}")
            if not dry:
                s.execute(text("""
                    INSERT INTO ref_record_level
                        (market_key,label,unit,high_value,high_date,low_value,low_date,
                         history_start,history_end,source,updated_at)
                    VALUES (:k,:l,:u,:hv,:hd,:lv,:ld,:d0,:d1,:src,now())
                    ON CONFLICT (market_key) DO UPDATE SET
                        label=EXCLUDED.label, unit=EXCLUDED.unit,
                        high_value=EXCLUDED.high_value, high_date=EXCLUDED.high_date,
                        low_value=EXCLUDED.low_value, low_date=EXCLUDED.low_date,
                        history_start=EXCLUDED.history_start, history_end=EXCLUDED.history_end,
                        source=EXCLUDED.source, updated_at=now()
                """), {"k": key, "l": label, "u": unit, "hv": hi[1], "hd": hi[0], "lv": lo[1],
                       "ld": lo[0], "d0": d0, "d1": d1, "src": src})
    print("dry run, nothing written" if dry else f"written: {len(res)} markets")


if __name__ == "__main__":
    main()
