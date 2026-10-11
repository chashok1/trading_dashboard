"""Cross-asset rules: multi-symbol RR-position conditions the ordinary
atomic-rule engine can't express -- atomic rules only ever evaluate a row's
OWN fields (see docs/rules_logic.md), so a rule like "Bonds and US dollar at
TRR and Gold is at LRR, then buy gold" (needs 3 OTHER symbols' RR reads to
fire a signal on a 4th) has nowhere to live there. 2026-09-01, user request.

Rules + their legs live in ref_cross_asset_rule(_leg) -- editable via /ref
like any other tunable ref table, designed to hold more rules than just the
one seeded so far. A rule fires when EVERY one of its normal CHECKS passes
AND no veto check blocks it (see veto paragraph below) -- a "check" is
either one standalone leg (leg_group IS NULL) or a blend of every leg
sharing the same leg_group. For an 'rr_position' check_type (the original
kind) that blend is a WEIGHTED AVERAGE (2026-09-01, user request -- "may be
use 10y more weighted?" -- e.g. 10Y+30Y Treasury yield blended 70/30 so a
strong 10Y can carry a slightly-lagging 30Y over the line, instead of
requiring both independently), and the check's value -- a single leg's own
rr_pos(), or the group's weighted average -- is api._helpers.rr_pos()'s
[0, 1] scale, the same formula ref_macro_area's own HOT/COLD read already
uses (see macro_area_hot_pct/macro_area_cold_pct in ref_settings), compared
against comparison ('>=' or '<=') + rr_threshold_pct. Grouped legs must
share the same comparison/rr_threshold_pct (the group's one shared
condition).

2026-09-24, user-directed ("if both bonds and dollar is bullish, it
shouldn't recommend buy") -- 'outlook' check_type legs, a different
dimension entirely: the app's everyday BULLISH/BEARISH/NEUTRAL outlook tag
(drv_rr.outlook), not an RR-position threshold. A group of outlook legs
blends via a CATEGORICAL AND instead (every member's own outlook must equal
outlook_value) -- a weighted average makes no sense for a category. Any
check (standalone or grouped) can be marked is_veto=TRUE: instead of being
required for the rule to fire, ALL of a rule's veto checks passing BLOCKS
it -- fired = (every normal check passes) AND NOT (every veto check
passes AND there is at least one veto check). A rule with no veto legs
behaves exactly as before.

Wired into derive_all() (etl/derive.py) right before the Actionable Stocks
pipeline -- needs only drv_quote + drv_rr (already built earlier in the
cascade), and its output (drv_cross_asset_signal) is read by
derive_actionable.py right where that function builds each symbol's
candidate list, so a fired rule can inject a synthetic action the same way
a fired rule GROUP already does (see derive_actionable.py's
group_candidates).

Idempotent: DELETE FROM drv_cross_asset_signal WHERE as_of_date=D, then
INSERT one row per active rule (fired or not -- the dashboard panel wants to
show "how close" a not-yet-fired rule is, not just the fired ones).
2026-10-11 TASK_149 (area driver rules): the same engine now also evaluates
ADVISORY area-verdict rules (mode='advisory', verdict + area_key set, no
target_symbol). They add check types outlook_dir / outlook_flip / delta / zone
/ gauge / level / rule_fired (see NEW_CHECK_TYPES) and an OR-group option
(leg_group + group_op='or'). Advisory rows are written to
drv_cross_asset_signal like any rule but derive_actionable.py folds ONLY
mode='actionable' rows, so they can never reach consolidated_action /
trig_action. etl/derive_area_verdicts.py turns them into drv_area_verdict.
"""

import json
import logging
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api._helpers import load_vol_thresholds, rr_pos, vol_zone

log = logging.getLogger(__name__)

# Check types added by TASK_149 (area driver rules). Evaluated by
# _eval_new_check() below; 'rr_position' / 'outlook' keep their original code
# path untouched so BONDS_USD_TRR_GOLD_LRR behaves exactly as before.
NEW_CHECK_TYPES = {"outlook_dir", "outlook_flip", "delta", "zone", "gauge", "level", "rule_fired"}

# hist_macro / quote data older than this (calendar days) counts as stale.
_STALE_DAYS = 7


def _leg_rr_pos(symbol: str, rr_map: dict, q_map: dict):
    """RR position (0..1, None if data's missing) for one leg symbol,
    reusing the shared rr_pos() formula -- same scale ref_macro_area's own
    HOT/COLD read and the Actionable RR column's % badge both use."""
    rr = rr_map.get(symbol)
    last = q_map.get(symbol)
    if not rr or last is None:
        return None
    lrr = rr.get("lrr")
    trr = rr.get("trr")
    if lrr is None or trr is None:
        return None
    return rr_pos(float(last), float(lrr), float(trr))


def outlook_bucket(outlook) -> Optional[str]:
    """'UP' | 'DOWN' | 'FLAT' | None. Outlook values are mixed case
    (BULLISH/Bullish/Mild Bullish/Light Bullish, BEARISH..., Neutral, ii also
    Long/Short) so this is a case-insensitive substring read."""
    if outlook is None:
        return None
    u = str(outlook).upper()
    if "BULL" in u or u == "LONG":
        return "UP"
    if "BEAR" in u or u == "SHORT":
        return "DOWN"
    return "FLAT"


def _tri_and(vals: list) -> Optional[bool]:
    if any(v is False for v in vals):
        return False
    if any(v is None for v in vals):
        return None
    return True


def _tri_or(vals: list) -> Optional[bool]:
    if any(v is True for v in vals):
        return True
    if any(v is None for v in vals):
        return None
    return False


class _Ctx:
    """Lazy, per-run lookups for the TASK_149 check types (one query each,
    only when some rule actually uses that type)."""

    def __init__(self, session: Session, d: date, legs_all: list, rr_map: dict, q_map: dict):
        self.s, self.d, self.rr_map, self.q_map = session, d, rr_map, q_map
        self.legs_all = legs_all
        self._hist = None
        self._series = {}
        self._vt = None
        self._gauges = None
        self._levels = None
        self.fired_by_rule: dict = {}

    # -- outlook history (flip) ---------------------------------------
    def outlook_hist(self, symbol: str, n: int):
        """Outlook buckets for the last n+1 drv_rr dates (newest first), or None."""
        if self._hist is None:
            syms = list({l["leg_symbol"] for l in self.legs_all if l["check_type"] == "outlook_flip"})
            nmax = max([int(l["lookback_days"] or 5) for l in self.legs_all
                        if l["check_type"] == "outlook_flip"] or [5])
            dates = [r[0] for r in self.s.execute(text(
                "SELECT DISTINCT as_of_date FROM drv_rr WHERE as_of_date <= :d "
                "ORDER BY as_of_date DESC LIMIT :n"), {"d": self.d, "n": nmax + 1}).all()]
            self._hist = {}
            if syms and dates:
                for r in self.s.execute(text(
                        "SELECT tos_symbol, as_of_date, outlook FROM drv_rr "
                        "WHERE tos_symbol = ANY(:syms) AND as_of_date = ANY(:ds)"),
                        {"syms": syms, "ds": dates}).all():
                    self._hist.setdefault(r[0], {})[r[1]] = outlook_bucket(r[2])
            self._hist["__dates__"] = dates
        dates = self._hist["__dates__"][: n + 1]
        by_date = self._hist.get(symbol, {})
        return [by_date.get(dt) for dt in dates]

    # -- derived macro series (delta) ----------------------------------
    def _load_series(self, sid: str):
        if sid not in self._series:
            rows = self.s.execute(text(
                "SELECT obs_date, value FROM hist_macro WHERE series_id = :sid "
                "AND obs_date <= :d AND obs_date >= :lo AND value IS NOT NULL "
                "ORDER BY obs_date"),
                {"sid": sid, "d": self.d, "lo": self.d - timedelta(days=75)}).all()
            self._series[sid] = [(r[0], float(r[1])) for r in rows]
        return self._series[sid]

    def _series_at(self, sid: str, asof: date, max_age: int):
        best = None
        for od, v in self._load_series(sid):
            if od <= asof:
                best = (od, v)
        if best is None or (asof - best[0]).days > max_age:
            return None
        return best[1]

    def series_value(self, series_key: str, asof: date, max_age: int):
        row = self.s.execute(text(
            "SELECT expr FROM ref_driver_series WHERE series_key = :k"), {"k": series_key}).first()
        if not row:
            return None
        toks = row[0].split()
        vals = [self._series_at(toks[i], asof, max_age) for i in range(0, len(toks), 2)]
        if any(v is None for v in vals):
            return None
        out = vals[0]
        for op, v in zip(toks[1::2], vals[1:]):
            out = out - v if op == "-" else out + v
        return out

    # -- vol zones -----------------------------------------------------
    def zone(self, symbol: str):
        if self._vt is None:
            self._vt = load_vol_thresholds(self.s)
        vt = self._vt.get(symbol)
        if not vt:
            return None, None
        last = self.q_map.get(symbol)
        return vol_zone(last, vt["low"], vt["high"]), last

    # -- risk dial gauges ------------------------------------------------
    def gauge(self, key: str):
        if self._gauges is None:
            row = self.s.execute(text(
                "SELECT gauges_fired FROM drv_market_stat WHERE as_of_date = :d"), {"d": self.d}).first()
            self._gauges = {g.get("key"): g.get("fired") for g in (row[0] or [])} if row and row[0] else {}
        return self._gauges.get(key)

    # -- watched levels --------------------------------------------------
    def top_level(self, symbol: str):
        if self._levels is None:
            self._levels = {r[0]: float(r[1]) for r in self.s.execute(text(
                "SELECT tos_symbol, MAX(level_value) FROM ref_level_watch "
                "WHERE is_active GROUP BY tos_symbol")).all()}
        return self._levels.get(symbol)


def _arrow(bucket: str) -> str:
    return {"UP": "▲", "DOWN": "▼"}.get(bucket, "~")


def _eval_new_leg(leg: dict, ctx: _Ctx) -> dict:
    """One TASK_149 leg -> {passed: True|False|None, phrase, ...detail}. None =
    input missing/stale (the area then reads Unclear, never silently quiet)."""
    ct, sym = leg["check_type"], leg["leg_symbol"]
    lab = leg.get("leg_label") or sym
    res = {"symbol": sym, "label": lab, "check_type": ct, "passed": None, "phrase": None}

    if ct == "outlook_dir":
        b = outlook_bucket((ctx.rr_map.get(sym) or {}).get("outlook"))
        want = (leg["outlook_value"] or "").upper()
        res["outlook"] = b
        if b is None:
            return res
        ok = {"UP": b == "UP", "DOWN": b == "DOWN",
              "NOT_UP": b != "UP", "NOT_DOWN": b != "DOWN"}.get(want, False)
        res["passed"] = ok
        res["phrase"] = (f"{lab} not {_arrow('UP' if want == 'NOT_UP' else 'DOWN')}"
                         if want.startswith("NOT_") else f"{lab} {_arrow(b)}")
    elif ct == "outlook_flip":
        n = int(leg["lookback_days"] or 5)
        hist = ctx.outlook_hist(sym, n)
        cur, prior = hist[0], hist[1:]
        res["lookback_days"] = n
        if cur is None:
            return res
        frm, to = ((leg["outlook_value"] or "UP_TO_DOWN").upper().split("_TO_") + ["DOWN"])[:2]
        res["passed"] = (cur == to) and (frm in prior)
        res["phrase"] = f"{lab} flipped {_arrow(frm)}→{_arrow(to)} (within {n}d)"
    elif ct == "delta":
        n = int(leg["lookback_days"] or 20)
        cur = ctx.series_value(sym, ctx.d, _STALE_DAYS)
        past = ctx.series_value(sym, ctx.d - timedelta(days=math.ceil(n * 7 / 5)), 30)
        res["lookback_days"] = n
        if cur is None or past is None:
            return res
        delta = cur - past
        thr = float(leg["threshold_value"] or 0)
        res.update(value=round(cur, 3), prior=round(past, 3), delta=round(delta, 3), threshold=thr)
        res["passed"] = delta >= thr if leg["comparison"] == ">=" else delta <= thr
        res["phrase"] = f"{lab} {'up' if delta >= 0 else 'down'} {abs(delta):.2f} over {n}d"
    elif ct == "zone":
        zone, last = ctx.zone(sym)
        res["zone"], res["last"] = zone, float(last) if last is not None else None
        if zone is None:
            return res
        want = leg["outlook_value"]
        res["passed"] = {"not_investable": zone != "investable",
                         "not_elevated": zone != "elevated"}.get(want, zone == want)
        res["phrase"] = f"{lab} {zone} ({float(last):g})"
    elif ct == "gauge":
        fired = ctx.gauge(sym)
        res["fired"] = fired
        if fired is None:
            return res
        res["passed"] = bool(fired)
        res["phrase"] = f"{lab}"
    elif ct == "level":
        last = ctx.q_map.get(sym)
        thr = leg["threshold_value"]
        thr = float(thr) if thr is not None else ctx.top_level(sym)
        if last is None or thr is None:
            return res
        last = float(last)
        res.update(last=last, level=thr)
        res["passed"] = last >= thr
        scale = 10.0 if sym.endswith(":CGI") and sym.startswith(("TNX", "TYX")) else 1.0
        res["phrase"] = (f"{lab} {last / scale:g}"
                         f"{'%' if scale != 1 else ''} above {thr / scale:g}{'%' if scale != 1 else ''}")
    elif ct == "rule_fired":
        fired = ctx.fired_by_rule.get(sym)
        res["fired"] = fired
        if fired is None:
            return res
        res["passed"] = bool(fired)
        res["phrase"] = lab
    return res


def _eval_new_check(members: list, ctx: _Ctx) -> dict:
    """A check = one standalone leg or a leg_group; group_op 'or' passes when
    ANY member passes, otherwise ALL members must (tri-state: None = missing)."""
    ev = [_eval_new_leg(m, ctx) for m in members]
    op = (members[0].get("group_op") or "and").lower()
    passed = _tri_or([e["passed"] for e in ev]) if op == "or" else _tri_and([e["passed"] for e in ev])
    phrases = [e["phrase"] for e in ev if e["passed"] and e["phrase"]]
    return {"passed": passed, "members": ev, "phrases": phrases, "group_op": op}


def _derive_cross_asset_rules_impl(session: Session, as_of_date: date) -> int:
    rules = session.execute(text("""
        SELECT rule_code, description, target_symbol, target_action,
               area_key, verdict, severity, mode, read_text
        FROM ref_cross_asset_rule
        WHERE is_active = TRUE
        ORDER BY rule_code
    """)).mappings().all()

    session.execute(text(
        "DELETE FROM drv_cross_asset_signal WHERE as_of_date = :d"
    ), {"d": as_of_date})

    if not rules:
        session.commit()
        return 0

    legs_by_rule: dict = {}
    all_legs: list = []
    for leg in session.execute(text("""
        SELECT rule_code, leg_symbol, comparison, rr_threshold_pct, weight, leg_group,
               check_type, outlook_value, is_veto,
               lookback_days, threshold_value, leg_label, group_op
        FROM ref_cross_asset_rule_leg
        ORDER BY rule_code, sort_order
    """)).mappings().all():
        legs_by_rule.setdefault(leg["rule_code"], []).append(dict(leg))
        all_legs.append(dict(leg))

    # Every leg symbol across every rule, fetched in two queries (not one
    # per leg) -- cheap even as more rules get added. outlook (2026-09-24)
    # feeds check_type='outlook' legs -- same drv_rr row rr/lrr/trr already
    # come from, no extra query.
    all_leg_symbols = {leg["leg_symbol"] for legs in legs_by_rule.values() for leg in legs}
    if all_leg_symbols:
        rr_rows = session.execute(text("""
            SELECT tos_symbol, lrr, trr, outlook FROM drv_rr
            WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
        """), {"d": as_of_date, "syms": list(all_leg_symbols)}).mappings().all()
        rr_map = {r["tos_symbol"]: dict(r) for r in rr_rows}
        q_rows = session.execute(text("""
            SELECT tos_symbol, last_price FROM drv_quote
            WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
        """), {"d": as_of_date, "syms": list(all_leg_symbols)}).mappings().all()
        q_map = {r["tos_symbol"]: r["last_price"] for r in q_rows}
    else:
        rr_map, q_map = {}, {}

    ctx = _Ctx(session, as_of_date, all_legs, rr_map, q_map)

    # Rules that reference another rule's result (check_type 'rule_fired')
    # are evaluated after every rule that doesn't (one level of nesting).
    def _needs_rule(code):
        return any(l["check_type"] == "rule_fired" for l in legs_by_rule.get(code, []))
    ordered = sorted(rules, key=lambda r: (_needs_rule(r["rule_code"]), r["rule_code"]))

    out = []
    for rule in ordered:
        code = rule["rule_code"]
        legs = legs_by_rule.get(code, [])

        # Group legs into "checks": standalone (leg_group IS NULL, one leg
        # each) or blended (every leg sharing a real leg_group value). A
        # veto leg's leg_group (e.g. 'bonds_bullish_veto') is always
        # distinct from any normal leg's group, so this grouping naturally
        # keeps veto checks separate from normal checks without needing
        # is_veto in the key. dict preserves insertion order (sort_order,
        # already ordered by the query above) so checks come out in the
        # same order legs were defined.
        checks: dict = {}
        for i, leg in enumerate(legs):
            key = leg["leg_group"] or f"__solo_{i}"
            checks.setdefault(key, []).append(leg)

        detail = []
        phrases: list = []
        all_pass = bool(checks)
        any_false = False      # a normal check definitively failed
        any_missing = False    # a normal check could not be read (input missing)
        veto_checks_exist = False
        veto_all_pass = True
        for members in checks.values():
            check_type = members[0]["check_type"]
            is_veto = bool(members[0]["is_veto"])
            missing = False

            if check_type in NEW_CHECK_TYPES:
                r = _eval_new_check(members, ctx)
                passed = r["passed"] is True
                missing = r["passed"] is None
                label = " + ".join(m["leg_symbol"] for m in members)
                detail.append({
                    "symbol": label,
                    "check_type": check_type,
                    "group_op": r["group_op"] if len(members) > 1 else None,
                    "passed": passed,
                    "missing": missing,
                    "is_veto": is_veto,
                    "members": r["members"],
                })
                if passed and not is_veto:
                    phrases.extend(r["phrases"])
            elif check_type == "outlook":
                # Categorical AND -- every member's own outlook must equal
                # its outlook_value (a weighted average makes no sense for
                # a BULLISH/BEARISH/NEUTRAL tag, unlike the rr_position
                # blend below). Compared case-insensitively (TASK_149).
                member_detail = []
                passed = True
                for leg in members:
                    outlook = (rr_map.get(leg["leg_symbol"]) or {}).get("outlook")
                    leg_passed = (outlook is not None and leg["outlook_value"] is not None
                                  and str(outlook).upper() == str(leg["outlook_value"]).upper())
                    member_detail.append({
                        "symbol": leg["leg_symbol"],
                        "outlook": outlook,
                    })
                    if outlook is None:
                        missing = True
                    if not leg_passed:
                        passed = False
                label = " + ".join(m["leg_symbol"] for m in members) if len(members) > 1 else members[0]["leg_symbol"]
                detail.append({
                    "symbol": label,
                    "check_type": "outlook",
                    "outlook_value": members[0]["outlook_value"],
                    # single-member checks expose their one outlook reading
                    # directly (same convenience rr_pct gives rr_position
                    # checks); a multi-member categorical AND has no single
                    # combined value, so this stays None and the per-member
                    # reads live in `members` instead.
                    "outlook": member_detail[0]["outlook"] if len(members) == 1 else None,
                    "passed": passed,
                    "is_veto": is_veto,
                    "members": member_detail if len(members) > 1 else None,
                })
            else:
                comparison = members[0]["comparison"]
                thr_pct = float(members[0]["rr_threshold_pct"])
                thr_frac = thr_pct / 100.0

                member_detail = []
                weighted_sum, weight_total = 0.0, 0.0
                any_missing_leg = False
                for leg in members:
                    pos = _leg_rr_pos(leg["leg_symbol"], rr_map, q_map)
                    w = float(leg["weight"])
                    member_detail.append({
                        "symbol": leg["leg_symbol"],
                        "weight": w,
                        "rr_pct": round(pos * 100, 1) if pos is not None else None,
                    })
                    if pos is None:
                        any_missing_leg = True
                    else:
                        weighted_sum += w * pos
                        weight_total += w

                blended_pos = (weighted_sum / weight_total) if (weight_total and not any_missing_leg) else None
                if blended_pos is None:
                    passed = False
                    missing = True
                elif comparison == ">=":
                    passed = blended_pos >= thr_frac
                else:
                    passed = blended_pos <= thr_frac

                label = " + ".join(m["leg_symbol"] for m in members) if len(members) > 1 else members[0]["leg_symbol"]
                detail.append({
                    "symbol": label,
                    "check_type": "rr_position",
                    "comparison": comparison,
                    "threshold_pct": thr_pct,
                    "rr_pct": round(blended_pos * 100, 1) if blended_pos is not None else None,
                    "passed": passed,
                    "is_veto": is_veto,
                    "members": member_detail if len(members) > 1 else None,
                })
                if passed and not is_veto and rule["mode"] == "advisory":
                    lab = members[0].get("leg_label") or members[0]["leg_symbol"]
                    phrases.append(f"{lab} at {round(blended_pos * 100)}% of range")

            if is_veto:
                veto_checks_exist = True
                if not passed:
                    veto_all_pass = False
            elif not passed:
                all_pass = False
                if missing:
                    any_missing = True
                else:
                    any_false = True

        veto_active = veto_checks_exist and veto_all_pass
        fired = all_pass and not veto_active
        ctx.fired_by_rule[code] = fired if not (any_missing and not any_false and not fired) else None
        read_text = None
        if fired and rule["mode"] == "advisory":
            tmpl = rule["read_text"] or "{legs}"
            read_text = tmpl.replace("{legs}", " and ".join(phrases))
        out.append({
            "as_of_date":    as_of_date,
            "rule_code":     code,
            "fired":         fired,
            "veto_active":   veto_active,
            "target_symbol": rule["target_symbol"],
            "target_action": rule["target_action"],
            "description":   rule["description"],
            "detail":        json.dumps(detail),
            "mode":          rule["mode"],
            "area_key":      rule["area_key"],
            "verdict":       rule["verdict"],
            "severity":      rule["severity"],
            "read_text":     read_text,
            "data_missing":  bool(any_missing and not any_false and not fired),
        })

    session.execute(text("""
        INSERT INTO drv_cross_asset_signal
          (as_of_date, rule_code, fired, veto_active, target_symbol, target_action, description, detail,
           mode, area_key, verdict, severity, read_text, data_missing)
        VALUES
          (:as_of_date, :rule_code, :fired, :veto_active, :target_symbol, :target_action, :description,
           CAST(:detail AS JSONB), :mode, :area_key, :verdict, :severity, :read_text, :data_missing)
    """), out)
    session.commit()
    log.info("derive_cross_asset_rules: %d rule(s) evaluated for %s (%d fired)",
              len(out), as_of_date, sum(1 for r in out if r["fired"]))
    return len(out)


def derive_cross_asset_rules(session: Session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all()'s call-site signature (session, as_of_date, parent_run_id)
    -- parent_run_id unused, this derive is cheap/simple enough not to need
    its own meta_derived_run tracking beyond what _safe() already logs."""
    return _derive_cross_asset_rules_impl(session, as_of_date)
