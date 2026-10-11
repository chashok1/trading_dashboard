"""Area driver rules, step 2 + 3 (TASK_149; docs/area_driver_rules_logic.md).

Step 1 lives in etl/derive_cross_asset_rules.py: it evaluates every
advisory rule into drv_cross_asset_signal. This module then

  * derive_area_verdicts  -> drv_area_verdict: one verdict per leaf area per
    date (headwind | tailwind | turning | stretched | unclear | quiet), after
    the dollar-correlation gate, the strongest-fired-rule pick, and the
    optional 2-day confirmation (ref_settings.area_verdict_confirm_days).
  * derive_driver_exposure -> drv_driver_exposure: which stocks sit in each
    non-quiet area (direct / class / theme / override tiers), with the
    inverted flip. Runs AFTER derive_actionable (needs held + position $).

Advisory only: nothing here touches consolidated_action / trig_action.
Idempotent: DELETE WHERE as_of_date=D then INSERT. tos_symbol throughout.
A stale/missing input makes the area 'unclear' and posts ONE meta_warning
(screen 'actionable', code AREA_DRIVER_STALE) -- market verdicts themselves
never go to the toolbar badge.
"""
import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Strongest first when several rules fire in one area.
VERDICT_RANK = {"headwind": 4, "stretched": 3, "turning": 2, "tailwind": 1}
FLIP = {"headwind": "tailwind", "tailwind": "headwind"}
_CORR_STALE_DAYS = 5
WARN_CODE = "AREA_DRIVER_STALE"


def _setting_int(session: Session, name: str, default: int) -> int:
    try:
        v = session.execute(text(
            "SELECT setting_value FROM ref_settings WHERE setting_name = :n"), {"n": name}).scalar()
        return int(float(v)) if v is not None else default
    except Exception:
        return default


def _load_corr(session: Session, d: date) -> dict:
    """asset_key -> w30 from the newest drv_usd_correlation date <= D (empty
    when that date is more than _CORR_STALE_DAYS old)."""
    cd = session.execute(text(
        "SELECT MAX(as_of_date) FROM drv_usd_correlation WHERE as_of_date <= :d"), {"d": d}).scalar()
    if cd is None or (d - cd).days > _CORR_STALE_DAYS:
        return {}
    return {r[0]: (float(r[1]) if r[1] is not None else None) for r in session.execute(text(
        "SELECT asset_key, w30 FROM drv_usd_correlation WHERE as_of_date = :d"), {"d": cd}).all()}


def _gate(area: dict, corr: dict) -> dict:
    """Dollar-link gate for one area. ok: True | False | None (no data)."""
    asset = area["gate_asset"]
    if not asset:
        return {"ok": True, "applies": False}
    used, w30 = asset, corr.get(asset)
    if w30 is None and area["gate_fallback_asset"]:
        used = area["gate_fallback_asset"]
        w30 = corr.get(used)
    thr = float(area["gate_threshold"])
    out = {"applies": True, "asset": used, "w30": w30, "cmp": area["gate_cmp"],
           "threshold": thr, "fallback": used != asset}
    if w30 is None:
        out["ok"] = None
    elif area["gate_cmp"] == "abs_ge":
        out["ok"] = abs(w30) >= thr
    else:
        out["ok"] = w30 <= thr
    return out


# Exposure tiers, most specific first (used to keep a stock in ONE child area).
_AXIS_RANK = {"symbol": 0, "direct": 0, "sub_asset_class": 1, "theme": 2, "sector": 3, "asset_class": 4}
_HE_BULL = ("bullish", "long")
_HE_BEAR = ("bearish", "short")
_HE_MIN_COVERED = 2


def _load_trans(session: Session, keys: list) -> dict:
    """area -> axis -> category -> (inverted, exclude)."""
    trans: dict = {}
    for r in session.execute(text("""
        SELECT gauge_key, axis, category, inverted, exclude FROM ref_gauge_transmission
        WHERE gauge_key = ANY(:k)"""), {"k": list(keys)}).all():
        trans.setdefault(r[0], {}).setdefault(r[1], {})[r[2]] = (bool(r[3]), bool(r[4]))
    return trans


def _load_themes(session: Session) -> dict:
    themes: dict = {}
    for sym, th, inv in session.execute(text(
            "SELECT symbol, theme, inverted FROM ref_symbol_theme")).all():
        themes.setdefault(sym, []).append((th, bool(inv)))
    return themes


def _match(tr: dict, direct, themes: dict, sym: str, sub, sector, asset):
    """(tier, inverted, axis) for one stock in one area, or None."""
    sym_row = tr.get("symbol", {}).get(sym)
    if sym_row and sym_row[1]:
        return None                                        # manual exclude
    if sym_row:
        return "override", sym_row[0], "symbol"
    if sym in direct:
        return "direct", False, "direct"
    for axis, val in (("sub_asset_class", sub), ("sector", sector), ("asset_class", asset)):
        hit = tr.get(axis, {}).get(val) if val else None
        if hit and not hit[1]:
            return "class", hit[0], axis
    for th, th_inv in themes.get(sym, []):
        hit = tr.get("theme", {}).get(th)
        if hit and not hit[1]:
            return "theme", hit[0] or th_inv, "theme"
    return None


def _he_breadth(session: Session, d: date, area_keys: list) -> dict:
    """area_key -> {bull, covered, bullish}: of the area's member stocks that have
    any Hedgeye source (drv_source_standing), how many lean bullish (same
    majority rule as the dashboard Book list). bullish = more than half, with
    at least _HE_MIN_COVERED covered."""
    if not area_keys:
        return {}
    parents = {r[0]: r[1] for r in session.execute(text(
        "SELECT area_key, parent_key FROM ref_driver_area "
        "WHERE enabled AND is_leaf AND rules_from IS NOT NULL")).all()}
    trans = _load_trans(session, list(parents))
    themes = _load_themes(session)
    standing: dict = {}
    for sym, src, outlook, sign, on_list in session.execute(text(
            "SELECT tos_symbol, source_code, outlook, signal_sign, on_list "
            "FROM drv_source_standing WHERE as_of_date = :d"), {"d": d}).all():
        standing.setdefault(sym, []).append((src, outlook, sign, on_list))

    def lean(sym):
        bull = bear = cov = 0
        for src, outlook, sign, on_list in standing.get(sym, ()):
            if src == "SSS":
                v = "bullish" if (sign or 0) > 0 else "bearish" if (sign or 0) < 0 else ""
            elif src in ("PS", "GOANY"):
                v = "bullish" if on_list else ""
            else:
                v = (outlook or "").strip().lower()
            if not v:
                continue
            cov += 1
            bull += v in _HE_BULL
            bear += v in _HE_BEAR
        if not cov:
            return None
        return "bull" if bull * 2 > cov else "bear" if bear * 2 > cov else "mixed"

    members: dict = {k: [] for k in area_keys}
    for sym, sector, sub, asset in session.execute(text(
            "SELECT tos_symbol, sector, sub_asset_class, asset_class FROM drv_technicals "
            "WHERE as_of_date = :d"), {"d": d}).all():
        best: dict = {}                                    # parent -> (rank, area)
        for k in parents:
            m = _match(trans.get(k, {}), (), themes, sym, sub, sector, asset)
            if not m or m[1]:
                continue
            rank = _AXIS_RANK[m[2]]
            par = parents[k]
            if par not in best or rank < best[par][0]:
                best[par] = (rank, k)
        for _, k in best.values():
            if k in members:
                members[k].append(sym)
    out = {}
    order = {"bull": 0, "mixed": 1, "bear": 2, None: 3}
    for k, syms in members.items():
        leans = [(x, lean(x)) for x in syms]
        covered = sum(1 for _, ln in leans if ln)
        bull = sum(1 for _, ln in leans if ln == "bull")
        out[k] = {"bull": bull, "covered": covered, "members": len(syms),
                  "bullish": covered >= _HE_MIN_COVERED and bull * 2 > covered,
                  "stocks": [{"s": x, "lean": ln}
                             for x, ln in sorted(leans, key=lambda t: (order[t[1]], t[0]))]}
    return out


def _derive_area_verdicts_impl(session: Session, as_of_date: date, run_id=None) -> int:
    d = as_of_date
    areas = [dict(r) for r in session.execute(text("""
        SELECT area_key, label, gate_asset, gate_fallback_asset, gate_cmp, gate_threshold,
               rules_from, hedgeye_cancels
        FROM ref_driver_area WHERE enabled AND is_leaf ORDER BY sort_order
    """)).mappings().all()]

    rules_by_area: dict = {}
    for r in session.execute(text("""
        SELECT rule_code, area_key, verdict, severity, read_text, fired, data_missing
        FROM drv_cross_asset_signal
        WHERE as_of_date = :d AND mode = 'advisory' AND verdict IS NOT NULL AND area_key IS NOT NULL
    """), {"d": d}).mappings().all():
        rules_by_area.setdefault(r["area_key"], []).append(dict(r))

    prev = {r["area_key"]: dict(r) for r in session.execute(text("""
        SELECT DISTINCT ON (area_key) area_key, verdict, raw_verdict, since_date
        FROM drv_area_verdict WHERE as_of_date < :d
        ORDER BY area_key, as_of_date DESC
    """), {"d": d}).mappings().all()}

    corr = _load_corr(session, d)
    he_breadth = _he_breadth(session, d, [a["area_key"] for a in areas if a["hedgeye_cancels"]])
    confirm = _setting_int(session, "area_verdict_confirm_days", 0)

    rows, unreadable = [], []
    for a in areas:
        key = a["area_key"]
        gate = _gate(a, corr)
        rules = rules_by_area.get(a["rules_from"] or key, [])
        fired = sorted((r for r in rules if r["fired"]),
                       key=lambda r: -VERDICT_RANK.get(r["verdict"], 0))
        missing = any(r["data_missing"] for r in rules if not r["fired"])
        data_missing = False
        read = None

        if gate["ok"] is False:
            raw = "unclear"
            read = (f"Dollar link not valid for {a['label']}: 30d correlation {gate['w30']:+.2f} "
                    f"(needs {'|r| >= ' if gate['cmp'] == 'abs_ge' else 'r <= '}"
                    f"{gate['threshold']:g}); driver rules set aside")
        elif gate["ok"] is None:
            raw, data_missing = "unclear", True
            read = "Dollar-correlation input missing or stale; driver rules set aside"
        elif fired:
            raw = fired[0]["verdict"]
            read = fired[0]["read_text"]
        elif missing:
            raw, data_missing = "unclear", True
            read = "A driver input is missing or stale; verdict unclear"
        else:
            raw = "quiet"
        he = he_breadth.get(key) if a["hedgeye_cancels"] else None
        if he and raw == "headwind":
            if he["bullish"]:
                he = {**he, "cancelled": True}
                raw = "quiet"
                read = (f"Rates headwind set aside: Hedgeye is bullish on {he['bull']} of "
                        f"{he['covered']} covered {a['label']} stocks")
        if data_missing:
            unreadable.append(a["label"])

        p = prev.get(key)
        verdict = raw
        if confirm >= 2 and p and raw != p["verdict"] and p["raw_verdict"] != raw:
            verdict = p["verdict"]  # one-day move: wait for a second day
        since = p["since_date"] if p and p["verdict"] == verdict else d
        rows.append({
            "as_of_date": d, "area_key": key, "verdict": verdict, "raw_verdict": raw,
            "prev_verdict": p["verdict"] if p else None, "since_date": since,
            "gate_ok": gate["ok"], "gate_detail": json.dumps({**gate, **({"he": he} if he else {})}),
            "fired_rules": json.dumps([{"rule_code": r["rule_code"], "verdict": r["verdict"],
                                        "severity": r["severity"], "read_text": r["read_text"]}
                                       for r in fired]),
            "read_text": read, "data_missing": data_missing,
        })

    session.execute(text("DELETE FROM drv_area_verdict WHERE as_of_date = :d"), {"d": d})
    if rows:
        session.execute(text("""
            INSERT INTO drv_area_verdict
              (as_of_date, area_key, verdict, raw_verdict, prev_verdict, since_date, gate_ok,
               gate_detail, fired_rules, read_text, data_missing)
            VALUES
              (:as_of_date, :area_key, :verdict, :raw_verdict, :prev_verdict, :since_date, :gate_ok,
               CAST(:gate_detail AS JSONB), CAST(:fired_rules AS JSONB), :read_text, :data_missing)
        """), rows)

    # ONE warning for the toolbar badge: the rules could not run. Only this
    # producer's own code is cleared (derive_actionable clears the rest).
    session.execute(text(
        "DELETE FROM meta_warning WHERE screen = 'actionable' AND as_of_date = :d AND code = :c"),
        {"d": d, "c": WARN_CODE})
    if unreadable:
        from etl.warnings import add_warning
        add_warning(session, "actionable",
                    "Area driver rules could not read stale or missing inputs for: "
                    + ", ".join(unreadable), as_of_date=d, code=WARN_CODE)
    session.commit()
    log.info("derive_area_verdicts @ %s: %d areas (%d unreadable)", d, len(rows), len(unreadable))
    return len(rows)


def _derive_driver_exposure_impl(session: Session, as_of_date: date, run_id=None) -> int:
    d = as_of_date
    session.execute(text("DELETE FROM drv_driver_exposure WHERE as_of_date = :d"), {"d": d})
    verdicts = {r["area_key"]: dict(r) for r in session.execute(text("""
        SELECT v.area_key, v.verdict, v.read_text, a.macro_area_key
        FROM drv_area_verdict v JOIN ref_driver_area a USING (area_key)
        WHERE v.as_of_date = :d AND v.verdict IN ('headwind','tailwind','turning','stretched')
    """), {"d": d}).mappings().all()}
    if not verdicts:
        session.commit()
        return 0

    # Every enabled area (not only the loud ones) so a quiet sibling with a more
    # specific match can claim the stock first.
    all_leaf = [r[0] for r in session.execute(text(
        "SELECT area_key FROM ref_driver_area WHERE enabled AND is_leaf")).all()]
    # Exclusive groups: only children that borrow their parent's rules (rules_from),
    # e.g. the Tech split. Gold/Silver keep linking the same stock to both.
    parent_of = {r[0]: r[1] for r in session.execute(text(
        "SELECT area_key, parent_key FROM ref_driver_area "
        "WHERE enabled AND is_leaf AND rules_from IS NOT NULL")).all()}
    trans = _load_trans(session, all_leaf)

    direct: dict = {}  # area -> set(symbol) from ref_macro_area dual members
    for area_key, v in verdicts.items():
        if v["macro_area_key"]:
            direct[area_key] = {r[0] for r in session.execute(text(
                "SELECT member_symbol FROM ref_macro_area "
                "WHERE area_key = :k AND enabled AND role = 'dual'"), {"k": v["macro_area_key"]}).all()}

    themes = _load_themes(session)

    uni = session.execute(text("""
        SELECT a.tos_symbol, a.held_today, a.current_position_dollar,
               t.asset_class, t.sector, t.sub_asset_class
        FROM drv_actionable a
        LEFT JOIN drv_technicals t ON t.as_of_date = a.as_of_date AND t.tos_symbol = a.tos_symbol
        WHERE a.as_of_date = :d
    """), {"d": d}).mappings().all()

    out = []
    for u in uni:
        sym = u["tos_symbol"]
        # Siblings under one parent: a stock belongs to its single most specific child.
        winner: dict = {}                                  # parent -> (rank, area)
        matches: dict = {}
        for area_key in all_leaf:
            m = _match(trans.get(area_key, {}), direct.get(area_key, ()), themes, sym,
                       u["sub_asset_class"], u["sector"], u["asset_class"])
            if not m:
                continue
            matches[area_key] = m
            par = parent_of.get(area_key)
            if par:
                rank = _AXIS_RANK[m[2]]
                if par not in winner or rank < winner[par][0]:
                    winner[par] = (rank, area_key)
        for area_key, v in verdicts.items():
            m = matches.get(area_key)
            if not m:
                continue
            par = parent_of.get(area_key)
            if par and winner[par][1] != area_key:
                continue
            tier, inv, _axis = m
            eff = v["verdict"]
            if inv:
                eff = FLIP.get(eff)
                if eff is None:
                    continue                               # stretched/turning don't invert
            out.append({
                "as_of_date": d, "tos_symbol": sym, "area_key": area_key,
                "area_verdict": v["verdict"], "verdict": eff, "tier": tier, "inverted": inv,
                "held": bool(u["held_today"]),
                "position_dollar": float(u["current_position_dollar"] or 0),
                "message": v["read_text"],
            })
    if out:
        session.execute(text("""
            INSERT INTO drv_driver_exposure
              (as_of_date, tos_symbol, area_key, area_verdict, verdict, tier, inverted, held,
               position_dollar, message)
            VALUES
              (:as_of_date, :tos_symbol, :area_key, :area_verdict, :verdict, :tier, :inverted, :held,
               :position_dollar, :message)
        """), out)
    session.commit()
    log.info("derive_driver_exposure @ %s: %d linked stock rows", d, len(out))
    return len(out)


def derive_area_verdicts(session: Session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all() call-site signature (session, as_of_date, parent_run_id)."""
    return _derive_area_verdicts_impl(session, as_of_date)


def derive_driver_exposure(session: Session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all() call-site signature (session, as_of_date, parent_run_id)."""
    return _derive_driver_exposure_impl(session, as_of_date)
