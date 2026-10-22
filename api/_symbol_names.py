"""Short (3-char where possible) display names for index / future / FX symbols.

Read from ref_symbol_short_name (keyed by tos_symbol), cached for a minute; DEFAULTS is the
fallback if the table is missing or the DB is unreachable. Display only -- never a lookup key.
"""
import re
import time

from sqlalchemy import text

from etl.db import session_scope

DEFAULTS: dict[str, str] = {
    "$COMP": "NDQ", "RUT": "RUS", "$SSEC": "SHA", "GDAXI:DE": "DAX", "N225:JP": "NKY",
    "/HG": "CPR", "/GC": "GLD", "/SI": "SLV", "/CL": "OIL", "/BZ": "BRT", "/NG": "GAS",
    "/BTC": "BTC", "/6E": "EUR", "/6J": "JPY", "/6B": "GBP", "/6C": "CAD",
    "$DXY": "DXY", "TNX:CGI": "10Y",
    "/ZC": "CRN", "/ZS": "SOY", "/ZW": "WHT", "/KC": "COF", "/SB": "SUG", "/LE": "CTL",
    "/PL": "PLT", "/PA": "PAL", "/NKD": "NKY", "$DJI": "DJI", "HSI:HK": "HSI",
    "DGS2:FRED": "2Y", "TYX:CGI": "30Y", "MOVE:GIF": "MOV",
    "GVZ:CGI": "GVZ", "OVX:CGI": "OVX", "VXN:CGI": "VXN",
}
_TTL = 60.0
_cache: tuple[float, dict[str, str]] | None = None


def short_names() -> dict[str, str]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _TTL:
        return _cache[1]
    names = dict(DEFAULTS)
    try:
        with session_scope() as s:
            names.update({r[0]: r[1] for r in s.execute(text("SELECT tos_symbol, short_name FROM ref_symbol_short_name"))})
    except Exception:
        pass
    _cache = (now, names)
    return names


def short_name(sym: str, default: str) -> str:
    names = short_names()
    if sym in names:
        return names[sym]
    # A month contract (/CL[H26]) reuses its base symbol's name.
    return names.get(re.sub(r"\[[^\]]*\]$", "", sym), default)
