"""
MSR top-box "lights" — read which cell is lit in each of the 4 rows of the
"SPX Gamma Exposure" image (the first box of the Market Situation Report).

Rows (top→bottom) and their 3 cells (left→right):
  gamma_light   Positive / Neutral / Negative     (SPX Gamma Exposure)
  flow_light    Bullish  / Neutral / Bearish      (Systematic Flow Risk)
  pv_light      Long     / Neutral / Short        (PV Band Risk/Reward)
  alloc_light   Risk On  / Neutral / Risk Off     (Strategic Allocation)

Only the lit cell has a coloured background (the others are grey text), so no
OCR is needed. Layout-independent: the image width/margins vary between
emails, so rows are found from the ink bands, each row is split into
label + 3 cells by the gaps between them, and the cell holding saturated
pixels is the lit one. Returns None unless every row has exactly one lit cell.

Backfill the saved archive images:  python -m etl.hedgeye.msr_lights
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

log = logging.getLogger("hedgeye.msr_lights")

LIGHT_ROWS = ("gamma_light", "flow_light", "pv_light", "alloc_light")
LIGHT_LABELS = {
    "gamma_light": ("Positive", "Neutral", "Negative"),
    "flow_light": ("Bullish", "Neutral", "Bearish"),
    "pv_light": ("Long", "Neutral", "Short"),
    "alloc_light": ("Risk On", "Neutral", "Risk Off"),
}


def _runs(flags, min_gap: int) -> list[tuple[int, int]]:
    """(start, end) of True runs in a 1-D bool array, merging runs split by < min_gap."""
    import numpy as np
    idx = np.flatnonzero(flags)
    if idx.size == 0:
        return []
    out, start, prev = [], int(idx[0]), int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - prev >= min_gap:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    return out


def detect_lights(img_bytes: bytes) -> dict | None:
    """{'gamma_light': 'Negative', 'flow_light': 'Bearish', ...} or None if unreadable."""
    try:
        import numpy as np
        from PIL import Image
        a = np.asarray(Image.open(io.BytesIO(img_bytes)).convert("RGB")).astype(int)
    except Exception as e:
        log.warning("msr_lights: cannot open image: %s", e)
        return None
    h, w, _ = a.shape
    ink = a.min(axis=2) < 235                      # anything that is not near-white
    sat = (a.max(axis=2) - a.min(axis=2)) >= 60    # the coloured (lit) cell
    ink[:, ink.sum(axis=0) > 0.85 * h] = False     # drop the box border lines
    ink[ink.sum(axis=1) > 0.85 * w, :] = False
    bands = [b for b in _runs(ink.any(axis=1), max(2, int(0.012 * h))) if b[1] - b[0] >= 0.05 * h]
    if len(bands) != len(LIGHT_ROWS):
        return None
    out: dict = {}
    for key, (y0, y1) in zip(LIGHT_ROWS, bands):
        cl = [c for c in _runs(ink[y0:y1 + 1].any(axis=0), max(2, int(0.02 * w)))
              if c[1] - c[0] >= 0.02 * w]
        if len(cl) != 4:                           # row label + 3 cells
            return None
        lit = [i for i, (x0, x1) in enumerate(cl[1:])
               if sat[y0:y1 + 1, x0:x1 + 1].sum() > 0.05 * (y1 - y0 + 1) * (x1 - x0 + 1)]
        if len(lit) != 1:
            return None
        out[key] = LIGHT_LABELS[key][lit[0]]
    return out


_UPSERT = (
    "INSERT INTO hist_msr (snapshot_date, message_id, gamma_light, flow_light, pv_light, alloc_light) "
    "VALUES (:sd, :mid, :g, :f, :p, :a) "
    "ON CONFLICT (snapshot_date) DO UPDATE SET "
    "gamma_light=EXCLUDED.gamma_light, flow_light=EXCLUDED.flow_light, "
    "pv_light=EXCLUDED.pv_light, alloc_light=EXCLUDED.alloc_light"
)


def save_lights(session, snapshot_date, lights: dict, message_id: str | None = None) -> None:
    """Upsert the 4 lights for a day; never touches gamma_throttle / rvol_10day."""
    from sqlalchemy import text
    session.execute(text(_UPSERT), {
        "sd": snapshot_date, "mid": message_id, "g": lights["gamma_light"],
        "f": lights["flow_light"], "p": lights["pv_light"], "a": lights["alloc_light"],
    })


def backfill(msr_dir: str) -> int:
    """Read every saved 'MSR YYYY-MM-DD.png' in msr_dir and store its lights."""
    from datetime import date
    from etl.db import session_scope
    n = 0
    for f in sorted(Path(msr_dir).glob("MSR *.png")):
        m = re.fullmatch(r"MSR (\d{4}-\d{2}-\d{2})", f.stem)
        if not m:
            continue
        lights = detect_lights(f.read_bytes())
        if not lights:
            log.warning("msr_lights: %s unreadable, skipped", f.name)
            continue
        with session_scope() as s:
            save_lights(s, date.fromisoformat(m.group(1)), lights)
        n += 1
        log.info("msr_lights: %s -> %s", f.name, lights)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from etl.hedgeye import config as hcfg
    d = hcfg.DEFAULTS.get("msr_dir", "")
    try:
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            row = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = 'hedgeye_msr_dir'")).first()
            d = (row[0] if row and row[0] else d)
    except Exception:
        pass
    print(f"backfilled {backfill(d)} image(s) from {d}")
