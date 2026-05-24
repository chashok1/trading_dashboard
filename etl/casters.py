"""
Type casters used by load_raw.py to coerce raw Excel cell values to DB types.
All casters return None for missing/invalid values rather than raising,
because Excel data is messy: '<empty>', 'NaN', '#N/A', blank strings, etc.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

import math
import pandas as pd


_BAD_TOKENS = {
    "", " ", "<empty>", "#N/A", "#REF!", "#VALUE!", "#NAME?",
    "#DIV/0!", "NaN", "nan", "None", "null",
}


def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if pd.isna(v):
        return True
    if isinstance(v, str) and v.strip() in _BAD_TOKENS:
        return True
    return False


def to_text(v) -> Optional[str]:
    if _is_blank(v):
        return None
    s = str(v).strip()
    return s or None


def to_char1(v) -> Optional[str]:
    s = to_text(v)
    if s is None:
        return None
    return s[:1].upper()


def to_int(v) -> Optional[int]:
    if _is_blank(v):
        return None
    try:
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        return int(float(v))
    except (TypeError, ValueError):
        return None


def to_bigint(v) -> Optional[int]:
    return to_int(v)


def to_numeric(v) -> Optional[float]:
    if _is_blank(v):
        return None
    try:
        if isinstance(v, str):
            v = v.replace("$", "").replace(",", "").replace("%", "").strip()
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def to_date(v) -> Optional[date]:
    if _is_blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        # Excel serial date (1900-based)
        try:
            return (datetime(1899, 12, 30) + pd.to_timedelta(int(v), unit="D")).date()
        except Exception:
            return None
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                continue
        try:
            ts = pd.to_datetime(v, errors="coerce")
            if pd.isna(ts):
                return None
            d = ts.date()
            return d if 1900 <= d.year <= 2100 else None
        except Exception:
            return None
    return None


def to_time(v) -> Optional[time]:
    if _is_blank(v):
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(v.strip(), fmt).time()
            except ValueError:
                continue
    return None


def excel_time_to_hhmm(v) -> Optional[int]:
    """
    Convert Excel time (e.g. '16:30:00' or 1630 or 0.6875) to integer HHMM.
    Used to derive the `sequence` column from "Export Time".
    """
    if _is_blank(v):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if 0 <= v < 1:
            # fractional day -> seconds -> HHMM
            total_min = int(round(v * 24 * 60))
            return (total_min // 60) * 100 + (total_min % 60)
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            return int(s)
        try:
            t = datetime.strptime(s, "%H:%M:%S").time()
            return t.hour * 100 + t.minute
        except ValueError:
            try:
                t = datetime.strptime(s, "%H:%M").time()
                return t.hour * 100 + t.minute
            except ValueError:
                return None
    if isinstance(v, time):
        return v.hour * 100 + v.minute
    return None
