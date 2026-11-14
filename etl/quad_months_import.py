"""Parse pasted monthly-quad text and upsert it into ref_quad_periods.

Pasted format (tab or space separated, header optional):
    Month  Qud  Q1  Q2  Q3  Q4
    26-Oct 2    52% 0%  0%  48%
Percents are stored as whole numbers (52, not 0.52), label like 'Oct-26'.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import text

_MON = re.compile(r"^(\d{2})-([A-Za-z]{3})$")
_MON_REV = re.compile(r"^([A-Za-z]{3})-(\d{2})$")


def _month(tok: str):
    m = _MON.match(tok)
    if m:
        yy, mon = m.group(1), m.group(2)
    else:
        m = _MON_REV.match(tok)
        if not m:
            return None
        mon, yy = m.group(1), m.group(2)
    try:
        num = datetime.strptime(mon.title(), "%b").month
    except ValueError:
        return None
    return 2000 + int(yy), num, f"{mon.title()}-{yy}"


def parse(raw: str):
    """Return (rows, errors). Rows: dicts ready for upsert."""
    rows, errors = [], []
    for i, line in enumerate((raw or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        toks = line.replace("%", " ").split()
        if toks[0].lower() == "month":
            continue
        if len(toks) != 6:
            errors.append(f"Line {i}: expected 6 columns, got {len(toks)}: {line}")
            continue
        mo = _month(toks[0])
        if not mo:
            errors.append(f"Line {i}: bad month '{toks[0]}' (use 26-Oct)")
            continue
        try:
            quad = int(toks[1])
            pcts = [float(t) for t in toks[2:]]
        except ValueError:
            errors.append(f"Line {i}: non-numeric value: {line}")
            continue
        if quad not in (1, 2, 3, 4):
            errors.append(f"Line {i}: quad must be 1-4, got {quad}")
            continue
        if any(p < 0 or p > 100 for p in pcts):
            errors.append(f"Line {i}: percent outside 0-100")
            continue
        if abs(sum(pcts) - 100) > 2:
            errors.append(f"Line {i}: percents add to {sum(pcts):g}, not ~100")
            continue
        year, num, label = mo
        rows.append(dict(year=year, num=num, label=label, quad=f"Quad {quad}",
                         q1=pcts[0], q2=pcts[1], q3=pcts[2], q4=pcts[3]))
    return rows, errors


_PCTS = ("quad1_pct", "quad2_pct", "quad3_pct", "quad4_pct")


def _fetch(session, keys):
    """Current monthly rows for the given (year, num) keys -> {key: dict}."""
    out = {}
    for r in session.execute(text(
            "SELECT year, period_num, quad, label, quad1_pct, quad2_pct, quad3_pct, quad4_pct"
            " FROM ref_quad_periods WHERE period_type='monthly'")):
        if (r[0], r[1]) in keys:
            v = {"quad": r[2], "label": r[3]}
            for i, c in enumerate(_PCTS):
                v[c] = float(r[4 + i]) if r[4 + i] is not None else None
            out[(r[0], r[1])] = v
    return out


def _new_vals(r):
    return {"quad": r["quad"], "label": r["label"], "quad1_pct": r["q1"],
            "quad2_pct": r["q2"], "quad3_pct": r["q3"], "quad4_pct": r["q4"]}


def diff(session, rows):
    """Per-row status vs the table: list of dicts (year, num, new, old, status)."""
    cur = _fetch(session, {(r["year"], r["num"]) for r in rows})
    out = []
    for r in rows:
        k = (r["year"], r["num"])
        new, old = _new_vals(r), cur.get(k)
        if old is None:
            st = "new"
        elif all(old[c] == new[c] for c in _PCTS) and old["quad"] == new["quad"]:
            st = "same"
        else:
            st = "changed"
        out.append({"year": k[0], "num": k[1], "new": new, "old": old, "status": st})
    return out


def _upsert(session, year, num, v):
    session.execute(text(
        "INSERT INTO ref_quad_periods (period_type, year, period_num, quad, label,"
        " quad1_pct, quad2_pct, quad3_pct, quad4_pct, loaded_at)"
        " VALUES ('monthly', :year, :num, :quad, :label, :q1, :q2, :q3, :q4, now())"
        " ON CONFLICT (period_type, year, period_num) DO UPDATE SET"
        " quad=EXCLUDED.quad, label=EXCLUDED.label, quad1_pct=EXCLUDED.quad1_pct,"
        " quad2_pct=EXCLUDED.quad2_pct, quad3_pct=EXCLUDED.quad3_pct,"
        " quad4_pct=EXCLUDED.quad4_pct, loaded_at=now()"),
        dict(year=year, num=num, quad=v["quad"], label=v["label"], q1=v["quad1_pct"],
             q2=v["quad2_pct"], q3=v["quad3_pct"], q4=v["quad4_pct"]))


def apply(session, diffs, pasted_text):
    """Write new/changed rows and log the import. Returns log id (None if nothing changed)."""
    todo = [d for d in diffs if d["status"] != "same"]
    if not todo:
        return None
    for d in todo:
        _upsert(session, d["year"], d["num"], d["new"])
    return session.execute(text(
        "INSERT INTO meta_quad_import_log (pasted_text, n_new, n_changed, changes)"
        " VALUES (:t, :n, :c, CAST(:j AS jsonb)) RETURNING id"),
        dict(t=pasted_text, n=sum(d["status"] == "new" for d in todo),
             c=sum(d["status"] == "changed" for d in todo), j=json.dumps(todo))).scalar()


def history(session, limit=30):
    return [{"id": r[0], "imported_at": r[1].isoformat(), "n_new": r[2], "n_changed": r[3],
             "undone_at": r[4].isoformat() if r[4] else None}
            for r in session.execute(text(
                "SELECT id, imported_at, n_new, n_changed, undone_at FROM meta_quad_import_log"
                " ORDER BY id DESC LIMIT :n"), {"n": limit})]


def get_import(session, imp_id):
    r = session.execute(text(
        "SELECT id, imported_at, changes, undone_at FROM meta_quad_import_log WHERE id=:i"),
        {"i": imp_id}).first()
    if not r:
        return None
    return {"id": r[0], "imported_at": r[1].isoformat(), "changes": r[2],
            "undone_at": r[3].isoformat() if r[3] else None}


def undo(session, imp_id):
    """Restore the rows from before import imp_id. Returns (ok, message)."""
    imp = get_import(session, imp_id)
    if not imp:
        return False, "Import not found"
    if imp["undone_at"]:
        return False, "Already undone"
    ch = imp["changes"]
    keys = {(c["year"], c["num"]) for c in ch}
    later = session.execute(text(
        "SELECT id, changes FROM meta_quad_import_log WHERE id > :i AND undone_at IS NULL"),
        {"i": imp_id}).all()
    for lid, lch in later:
        if keys & {(c["year"], c["num"]) for c in lch}:
            return False, f"Import #{lid} changed some of the same months later - undo #{lid} first"
    cur = _fetch(session, keys)
    for c in ch:
        row = cur.get((c["year"], c["num"]))
        if row is None or any(row[k] != c["new"][k] for k in c["new"]):
            return False, f"{c['new']['label']} was edited after this import - not undoing"
    for c in ch:
        if c["old"] is None:
            session.execute(text("DELETE FROM ref_quad_periods WHERE period_type='monthly'"
                                 " AND year=:y AND period_num=:n"), {"y": c["year"], "n": c["num"]})
        else:
            _upsert(session, c["year"], c["num"], c["old"])
    session.execute(text("UPDATE meta_quad_import_log SET undone_at=now() WHERE id=:i"), {"i": imp_id})
    return True, f"Undone: {len(ch)} month(s) restored"
