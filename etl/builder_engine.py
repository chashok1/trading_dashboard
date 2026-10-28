"""Portfolio Builder build engine (PURE: no database, no clock).

build_positions(ctx, req) turns prepared data (fund measures, Quad mix, account holdings,
presets) plus the user's choices into a proposed model: mix by asset class, area split,
funds, whole shares, one-line reasons. The DB side (loading ctx, accepting, listing) is in
etl/builder_data.py. The Builder never trades and never changes the Actionable Final Call.

ctx / req shapes are documented in docs/portfolio_builder_logic.md.
"""
from __future__ import annotations

import math
from typing import Optional

from etl.derive_model_portfolio import (
    PB_PARAMS, BUCKETS, STANDARD_FUND, BUCKET_OUTLOOK, FLAVOURS, RECIPES,
    area_stance, chip_of, fill_areas, pick_in_area, rank_scored, score_fund,
    inverse_swing_weights, apply_caps, normalise_mix, quad_tilt_mix, risk_dial_trim,
    enforce_floors, whole_shares, positions_for_bucket, final_call_side, outlook_key,
)

CHIP_WORD = {"B": "is favoured", "H": "is neutral", "S": "is a Sell area", "-": "has no Quad view"}
EQ_RULES = ("low_vol", "low_beta", "momentum")
FI_RULES = ("core", "low_vol")


def _pct(x, d=0):
    return "%.*f%%" % (d, x * 100.0)


def _usd(x):
    return "$" + format(int(round(x)), ",")


def _passes_flavour(fund: dict, flavour: str) -> bool:
    tags = FLAVOURS.get(flavour or "all")
    if not tags:
        return True
    have = {str(t).lower() for t in (fund.get("styles") or [])}
    return any(t.lower() in have for t in tags)


def _rule_line(rule: str, f: dict) -> str:
    if rule in ("low_vol", "core") and f.get("vol63") is not None:
        return "Swings %.0f%% a year" % (f["vol63"] * 100)
    if rule == "low_beta" and f.get("beta") is not None:
        return "Moves %.2f x the market (beta)" % f["beta"]
    if rule == "momentum" and f.get("mom") is not None:
        return "6-month return %+.1f%%, above its Trend line" % (f["mom"] * 100)
    return RECIPES.get(rule, {}).get("label", rule)


def _src_line(f: dict) -> list:
    return ["In Hedgeye lists: %s" % ", ".join(f["sources"])] if f.get("sources") else []


def _outlook_of(ctx: dict, cat, sub):
    return (ctx.get("outlook") or {}).get(outlook_key(cat, sub))


def quad_summary(q: Optional[dict]) -> Optional[dict]:
    """JSON-safe view of the horizon Quad mix (month tuples become 'YYYY-MM')."""
    if not q:
        return None
    return {"shares": q.get("shares"), "coverage_pct": q.get("coverage_pct"), "note": q.get("note"), "blend": q.get("blend"),
            "check_label": q.get("check_label"),
            "months": [["%04d-%02d" % ym, w] for ym, w in (q.get("weighted") or [])]}


def bucket_stances(ctx: dict, override: Optional[list]) -> dict:
    shares = (ctx.get("quad") or {}).get("shares")
    out = {}
    for b, (cat, sub) in BUCKET_OUTLOOK.items():
        out[b] = area_stance(_outlook_of(ctx, cat, sub), shares, override)
    return out


def target_mix(ctx: dict, req: dict, stances: dict) -> dict:
    """Preset / current / custom -> {bucket: pct, Cash: pct}. Quad-tilted preset applies the tilt."""
    key = req.get("preset") or "balanced"
    cur = dict((ctx.get("account") or {}).get("current_mix") or {})
    if key == "current":
        mix = {b: cur.get(b, 0.0) for b in BUCKETS}
        mix["Cash"] = cur.get("Cash", 0.0)
        return normalise_mix(mix)
    if key == "custom":
        return normalise_mix(req.get("mix") or {})
    pr = (ctx.get("presets") or {}).get(key)
    if not pr:
        pr = (ctx.get("presets") or {}).get("balanced") or {"mix": {"Equities": 60, "Fixed Income": 30, "Cash": 10}}
    mix = {k: float(v) for k, v in (pr.get("mix") or {}).items()}
    mix.setdefault("Cash", 100.0 - sum(v for k, v in mix.items() if k != "Cash"))
    if pr.get("quad_tilt"):
        mix = quad_tilt_mix(mix, stances, float(pr["quad_tilt"]))
    return normalise_mix(mix)


CHECKS = {"low_beta": "Low beta", "quad": "Quad check"}


def apply_checks(cands: list, checks: list, ctx: dict, override, shares_mix) -> tuple:
    """Validation filters on the pick pool. low_beta: beta at or under the promise (0.8). quad: its area is not a
    Sell area for the Quad mix of the period (no Quad view = passes). Returns (kept, [(fund, reason)])."""
    keep, failed = [], []
    for f in cands:
        why = None
        if "low_beta" in checks:
            b = f.get("beta")
            if b is None:
                why = "Low beta check: not enough price history for a beta"
            elif b > PB_PARAMS["beta_promise"]:
                why = "Low beta check: beta %.2f is above %.1f" % (b, PB_PARAMS["beta_promise"])
        if why is None and "quad" in checks:
            st = area_stance(_outlook_of(ctx, f.get("outlook_cat"), f.get("outlook_sub")), shares_mix, override)
            if st is not None and chip_of(st) == "S":
                why = "Quad check: its area (%s) is a Sell area for your Quad mix" % f.get("area")
        (failed if why else keep).append((f, why) if why else f)
    return keep, failed


def pool_trim_mix(mix: dict, have: set) -> tuple:
    """Source pool: a bucket with no names in the pool cannot be filled. Drop it and spread its share over the
    buckets that can (Cash share unchanged). Returns (mix, [dropped buckets])."""
    cash = mix.get("Cash", 0.0)
    live = {b: v for b, v in mix.items() if b != "Cash" and b in have and v > 0}
    dropped = [b for b, v in mix.items() if b != "Cash" and v > 0 and b not in have]
    total = sum(v for b, v in mix.items() if b != "Cash")
    if not dropped:
        return mix, []
    if not live:
        return {"Cash": cash + total}, dropped
    k = total / sum(live.values())
    out = {b: v * k for b, v in live.items()}
    out["Cash"] = cash
    return out, dropped


def build_positions(ctx: dict, req: dict) -> dict:
    p = PB_PARAMS
    acct = ctx.get("account") or {}
    holdings = acct.get("holdings") or {}
    funds = ctx.get("funds") or {}
    notes: list = []
    amount = float(req.get("amount") or acct.get("value") or 0.0)
    out = {"amount": amount, "positions": [], "skipped": [], "unavailable": [], "buckets": {}, "notes": notes,
           "quad": quad_summary(ctx.get("quad")), "mix_current": acct.get("current_mix") or {}}
    if amount <= 0:
        notes.append("Amount is 0: nothing to build.")
        return out
    override = [int(q) for q in (req.get("quad_override") or [])] or None
    quad = ctx.get("quad") or {}
    if quad.get("note"):
        notes.append(quad["note"])
    if quad.get("shares") is None and not override:
        notes.append("No Quad mix for your period: pick a Quad button, or areas keep their base share.")
    stances = bucket_stances(ctx, override)
    out["bucket_stance"] = {b: {"stance": s, "chip": chip_of(s)} for b, s in stances.items()}
    mix0 = target_mix(ctx, req, stances)
    manual = bool(req.get("manual"))     # hand-picked build: the user chose every name, nothing is picked for them
    manual_picks = [x for x in (req.get("picks") or []) if x.get("sym")] if manual else []
    pool_mode = bool(req.get("sources")) and not manual
    checks = [c for c in (req.get("checks") or []) if c in CHECKS]
    out["pool_mode"] = pool_mode
    out["checks"] = checks
    if pool_mode:
        have = {f.get("bucket") for f in funds.values() if f.get("eligible")}
        mix0, dropped = pool_trim_mix(mix0, have)
        if dropped:
            notes.append("No names in your sources for %s: that share went to the other buckets." % ", ".join(dropped))
    out["mix_target"] = mix0

    # kept holdings: counted at today's value, never traded, never picked again
    kept = [s for s in (ctx.get("kept") or []) if s in holdings]
    kept_by_bucket: dict = {}
    for s in kept:
        b = holdings[s].get("bucket") or "Unmapped"
        kept_by_bucket[b] = kept_by_bucket.get(b, 0.0) + float(holdings[s].get("value") or 0.0)
    floors = {b: v / amount * 100.0 for b, v in kept_by_bucket.items() if b in BUCKETS}
    mult = ctx.get("risk_mult")
    mix = dict(mix0)
    out["risk"] = {"applied": False, "multiplier": mult, "label": ctx.get("risk_label")}
    if req.get("use_risk_dial", True):
        if mult is None:
            notes.append("Risk Dial unavailable, full size.")
        elif mult < 1.0:
            mix = risk_dial_trim(mix, mult, floors)
            out["risk"]["applied"] = True
    mix = normalise_mix(enforce_floors(mix, floors))
    out["mix_final"] = mix
    for b, fl in floors.items():
        if mix0.get(b, 0.0) < fl - 1e-9:
            notes.append("Kept holdings already put %s at %.0f%%, %.0f points over target." % (b, fl, fl - mix0.get(b, 0.0)))

    skip_sells = bool(req.get("skip_sells", True))
    flavour = req.get("flavour") or "all"
    kept_set = set(kept)
    # The Final Call is information only when building: it never removes or swaps a name (today's calls are temporary).
    # sell_syms stays as an always-empty set so the pick helpers keep their signature.
    sell_syms: set = set()
    sell_syms -= kept_set
    shares_mix = quad.get("shares")
    picks_dollars: dict = {}        # sym -> {dollars, bucket, area, why, detail, sleeve}
    cash_extra = 0.0

    def add_pick(sym, dollars, bucket, area, why, detail, rule=None):
        if dollars <= 0:
            return
        d = picks_dollars.setdefault(sym, {"dollars": 0.0, "bucket": bucket, "area": area, "why": why, "detail": detail, "rule": rule})
        d["dollars"] += dollars

    def note_skips(skipped, area, replaced_by):
        for s in skipped:
            f = funds.get(s["sym"]) or {}
            out["skipped"].append({"sym": s["sym"], "area": area, "final_code": f.get("final_code"),
                                   "reason": s["reason"], "replaced_by": replaced_by})

    for bucket in BUCKETS:
        pct = mix.get(bucket, 0.0)
        kept_d = kept_by_bucket.get(bucket, 0.0)
        if pct <= 0 and kept_d <= 0:
            continue
        bdollars = max(pct / 100.0 * amount, kept_d)
        cfg = (req.get("buckets") or {}).get(bucket) or {}
        info = {"dollars": bdollars, "pct": pct, "kept_dollars": kept_d, "stance": stances.get(bucket),
                "chip": chip_of(stances.get(bucket)), "areas": [], "notes": [], "message": None}
        out["buckets"][bucket] = info
        if manual:
            info["split"] = "manual"
            buy = max(0.0, bdollars - kept_d)
            mine = [x for x in manual_picks if x.get("bucket") == bucket and x["sym"] not in kept_set]
            if buy <= 0 or not mine:
                if buy > 0:
                    cash_extra += buy
                    info["notes"].append("No stocks picked yet: this share stays in Cash.")
                continue
            ok = []
            for x in mine:
                f = funds.get(x["sym"])
                if not f:
                    out["skipped"].append({"sym": x["sym"], "area": bucket, "final_code": None,
                                           "reason": "not available today", "replaced_by": None})
                else:
                    ok.append(x)
            explicit = {x["sym"]: max(0.0, float(x["pct"])) / 100.0 for x in ok if x.get("pct") is not None}
            auto = [x["sym"] for x in ok if x.get("pct") is None]
            ex_sum = sum(explicit.values())
            if ex_sum > 1.0 + 1e-9:     # allowed: the picks simply put more money in the class than its target (shown red)
                info["notes"].append("Your %s percentages add to %.0f%%: more than the class has, so it goes over target." % (bucket, ex_sum * 100.0))
            w = dict(explicit)
            for sym in auto:
                w[sym] = max(0.0, 1.0 - ex_sum) / len(auto)
            used = sum(w.values())
            if used < 0.999:
                cash_extra += buy * (1.0 - used)
                info["notes"].append("%.0f%% of %s is not given to any stock: it stays in Cash." % ((1.0 - used) * 100.0, bucket))
            for sym, wt in w.items():
                f = funds[sym]
                add_pick(sym, buy * wt, bucket, f.get("area") or bucket, "Picked by you",
                         ["Picked by you", "%s of %s" % (_pct(wt, 1), bucket)] + _src_line(f), "manual")
            continue
        cands = [dict(sym=s, **{k: v for k, v in f.items() if k != "sym"}) for s, f in funds.items()
                 if f.get("bucket") == bucket and f.get("eligible") and s not in kept_set]
        if bucket == "Equities":
            cands = [f for f in cands if _passes_flavour(f, flavour)]
        if checks:
            cands, failed = apply_checks(cands, checks, ctx, override, shares_mix)
            for f_, why_ in failed:
                out["skipped"].append({"sym": f_["sym"], "area": f_.get("area"), "final_code": f_.get("final_code"),
                                       "reason": why_, "replaced_by": None, "kind": "check"})
        split = cfg.get("split") or (("recipe" if pool_mode else "area") if bucket in ("Equities", "Fixed Income") else
                                     ("recipe" if pool_mode else "standard"))
        info["split"] = split

        if bucket in STANDARD_FUND and not pool_mode:
            sym = STANDARD_FUND[bucket]
            f = funds.get(sym)
            buy = max(0.0, bdollars - kept_d)
            if buy <= 0:
                info["notes"].append("Kept holdings fill this bucket.")
            elif not f or not f.get("eligible"):
                cash_extra += buy
                info["notes"].append("%s is not available today: %s goes to Cash." % (sym, _usd(buy)))
            elif sym in sell_syms:
                cash_extra += buy
                out["skipped"].append({"sym": sym, "area": bucket, "final_code": f.get("final_code"),
                                       "reason": "Final Call sells it", "replaced_by": None})
                info["notes"].append("%s has a Sell call: %s goes to Cash." % (sym, _usd(buy)))
            else:
                add_pick(sym, buy, bucket, bucket, "Standard %s fund" % bucket,
                         ["Standard fund for %s (one fund, no recipe)" % bucket, "%s of the account" % _pct(pct / 100.0, 1)])
            continue

        if split == "area":
            rule = cfg.get("pick") or ("low_vol" if bucket == "Equities" else "core")
            if (bucket == "Equities" and rule not in EQ_RULES) or (bucket == "Fixed Income" and rule not in FI_RULES):
                rule = "low_vol" if bucket == "Equities" else "core"
            by_area: dict = {}
            for f in cands:
                by_area.setdefault(f["area"], []).append(f)
            area_meta: dict = {}
            for s, f in funds.items():
                if f.get("bucket") == bucket and f.get("area") not in area_meta:
                    area_meta[f["area"]] = (f.get("outlook_cat"), f.get("outlook_sub"))
            kept_area: dict = {}
            for s in kept:
                if (holdings[s].get("bucket") or "Unmapped") == bucket:
                    a = holdings[s].get("area") or ("Broad US" if bucket == "Equities" else bucket)
                    kept_area[a] = kept_area.get(a, 0.0) + float(holdings[s].get("value") or 0.0)
            names = list(area_meta.keys())
            for a in kept_area:
                if a not in names:
                    names.append(a)
            area_in = []
            for a in names:
                cat, sub = area_meta.get(a, (None, None))
                st = area_stance(_outlook_of(ctx, cat, sub), shares_mix, override)
                area_in.append({"name": a, "stance": st, "eligible": bool(by_area.get(a)), "kept_dollars": kept_area.get(a, 0.0)})
            res = fill_areas(area_in, bucket, bdollars, cfg.get("locked") or {})
            info["message"] = res.get("message")
            if res.get("unallocated", 0) > 0.0005:
                cash_extra += res["unallocated"] * bdollars
            for r in res["rows"]:
                row = {k: r[k] for k in ("name", "stance", "chip", "base", "auto_fill", "fill", "locked", "kept_dollars", "buy_dollars", "notes")}
                row["dollars"] = r["fill"] * bdollars
                row["outlook"] = _outlook_of(ctx, *area_meta.get(r["name"], (None, None)))
                row["funds"] = []
                info["areas"].append(row)
                if r["buy_dollars"] <= 0:
                    continue
                fl = by_area.get(r["name"]) or []
                n_funds = len(fl) if rule == "core" else (
                    2 if (r["name"] in p["two_fund_areas"] and r["fill"] >= p["broad_two_fund_share"]) else 1)
                picks, skipped, pnote = pick_in_area(fl, rule, n_funds, sell_syms)
                if not picks:
                    cash_extra += r["buy_dollars"]
                    row["notes"].append(((pnote or "None qualifies") + ": %s goes to Cash") % _usd(r["buy_dollars"]))
                    note_skips(skipped, r["name"], None)
                    continue
                note_skips(skipped, r["name"], picks[0]["sym"])
                for pk in picks:
                    f = funds[pk["sym"]]
                    row["funds"].append(pk["sym"])
                    sharetxt = _pct(r["fill"], 1)
                    why = "%s %s; %s" % (r["name"], CHIP_WORD.get(r["chip"], "is neutral"), _rule_line(rule, f).lower())
                    detail = ["Area %s: Macro %s (stance %s)" % (r["name"], r["chip"], "n/a" if r["stance"] is None else "%+.2f" % r["stance"]),
                              "%s of %s; fund pick rule: %s" % (sharetxt, bucket, RECIPES[rule]["label"]),
                              _rule_line(rule, f)]
                    if shares_mix and not override:
                        detail.append("Quad mix over your period: " + ", ".join("Q%d %d%%" % (i + 1, round(x * 100)) for i, x in enumerate(shares_mix) if x >= 0.005))
                    if override:
                        detail.append("Assumed Quad " + " & ".join(str(q) for q in override))
                    add_pick(pk["sym"], r["buy_dollars"] * pk["weight"], bucket, r["name"], why, detail + _src_line(f), rule)
            for r in res["rows"]:
                if r.get("notes"):
                    info["notes"].extend("%s: %s" % (r["name"], n) for n in r["notes"] if n not in info["notes"])
            continue

        # recipe / core / low_vol split across all funds of the bucket
        rule = cfg.get("recipe") or ("momentum" if bucket == "Equities" else ("core" if split == "core" else "low_vol"))
        if split in ("core", "low_vol"):
            rule = split
        buy = max(0.0, bdollars - kept_d)
        n_want = positions_for_bucket(bucket, int(cfg.get("n") or p["default_positions"].get(bucket, 3)), bdollars)
        scored = []
        for f in cands:
            ok, sc, ex = score_fund(rule, f)
            if ok:
                scored.append({"sym": f["sym"], "score": sc, "vol63": f.get("vol63")})
        ranked = rank_scored(scored)
        chosen, skipped_here = [], []
        for r in ranked:
            if r["sym"] in sell_syms:
                skipped_here.append({"sym": r["sym"], "reason": "Final Call sells it"})
            elif len(chosen) < n_want:
                chosen.append(r)
        if len(chosen) < n_want:
            info["notes"].append("Only %d fund(s) qualified (asked for %d)." % (len(chosen), n_want))
        if not chosen or buy <= 0:
            if chosen == [] and buy > 0:
                cash_extra += buy
                info["notes"].append("No fund qualifies: %s goes to Cash." % _usd(buy))
            note_skips(skipped_here, bucket, None)
            continue
        note_skips(skipped_here, bucket, chosen[0]["sym"])
        w = inverse_swing_weights({r["sym"]: r["vol63"] for r in chosen})
        bfrac = max(bdollars / amount, 1e-9)
        area_of = {r["sym"]: funds[r["sym"]]["area"] for r in chosen} if bucket == "Equities" else None
        w = apply_caps(w, p["fund_cap"] / bfrac, area_of, p["area_cap"] if area_of else None, p["min_weight"])
        used = sum(w.values())
        if used < 0.999:
            cash_extra += buy * (1 - used)
        for sym, wt in w.items():
            f = funds[sym]
            detail = ["Recipe: %s (%s)" % (RECIPES[rule]["label"], RECIPES[rule]["text"]), _rule_line(rule, f),
                      "Weight %s of %s: %s" % (_pct(wt, 1), bucket, "calmer funds get more")]
            add_pick(sym, buy * wt, bucket, f["area"], "%s: %s" % (RECIPES[rule]["label"], _rule_line(rule, f).lower()), detail + _src_line(f), rule)
        info["areas"] = []

    # kept positions
    positions = []
    for s in kept:
        h = holdings[s]
        f = funds.get(s) or {}
        positions.append({"sym": s, "bucket": h.get("bucket") or "Unmapped", "area": h.get("area") or f.get("area"),
                          "dollars": float(h.get("value") or 0), "price": h.get("price"), "shares": h.get("qty"),
                          "value": float(h.get("value") or 0), "is_kept": True,
                          "why": "Kept as is (your list)", "why_detail": ["Kept as is (your list)", "Counts toward its bucket at today's value", "Never traded by the Builder"],
                          "final_code": f.get("final_code"), "final_side": final_call_side(f.get("final_code")), "rule": None})
    for sym, d in picks_dollars.items():
        f = funds[sym]
        price = f.get("price")
        sh = whole_shares(d["dollars"], price)
        val = sh * (price or 0.0)
        if sh <= 0:
            cash_extra += d["dollars"]
            out["notes"].append("%s: %s is less than one share: goes to Cash." % (sym, _usd(d["dollars"])))
            continue
        positions.append({"sym": sym, "bucket": d["bucket"], "area": d["area"], "dollars": d["dollars"], "price": price,
                          "shares": sh, "value": val, "is_kept": False, "why": d["why"], "why_detail": d["detail"],
                          "final_code": f.get("final_code"), "final_side": final_call_side(f.get("final_code")), "rule": d["rule"],
                          "sources": f.get("sources")})
    total_val = sum(x["value"] for x in positions)
    for x in positions:
        x["weight"] = x["value"] / amount
        x["held_value"] = float((holdings.get(x["sym"]) or {}).get("value") or 0.0)
        if x["final_side"] == "sell" and not x["is_kept"]:
            x["conflict"] = True
    positions.sort(key=lambda x: (BUCKETS.index(x["bucket"]) if x["bucket"] in BUCKETS else 99, -x["value"]))
    out["positions"] = positions
    cash = max(0.0, amount - total_val)
    out["cash"] = {"dollars": cash, "pct": cash / amount * 100.0,
                   "note": "Cash earns 0% in v1"}
    out["invested"] = total_val
    out["unavailable"] = [{"sym": s, "bucket": f.get("bucket"), "reason": f.get("reason") or "not eligible"}
                          for s, f in funds.items() if not f.get("eligible") and f.get("reason") != "Benchmark only"]
    # held, not in model
    in_model = {x["sym"] for x in positions}
    out["held_not_in_model"] = sorted(
        [{"sym": s, "value": float(h.get("value") or 0), "bucket": h.get("bucket")}
         for s, h in holdings.items() if s not in in_model and not h.get("is_cash")],
        key=lambda r: -r["value"])
    return out


# ---------------------------------------------------------------------------
# vs your account: gaps, trades, taxable gain line (account holdings only, no scaling)
# ---------------------------------------------------------------------------
def vs_account(model: list, holdings: dict, kept: set, account_type: Optional[str]) -> dict:
    """model: [{sym, value, price, area, bucket}] ; holdings: {sym: {value, qty, price, cost, bucket, is_cash}}.
    Never suggests selling a holding the model does not include (it says 'Held, not in model')."""
    t = (account_type or "OTHER").upper()
    show_tax = t == "TAXABLE"
    paper_only = t == "401K"
    rows, gain, loss = [], 0.0, 0.0
    msyms = {m["sym"]: m for m in model}
    for s in sorted(set(msyms) | {h for h, v in holdings.items() if not v.get("is_cash")}):
        m, h = msyms.get(s), holdings.get(s) or {}
        mv = float(m["value"]) if m else None
        hv = float(h.get("value") or 0.0)
        price = (m or {}).get("price") or h.get("price")
        row = {"sym": s, "area": (m or {}).get("area") or h.get("area"), "model": mv, "hold": hv, "gap": None, "trade": "", "tax": None,
               "kept": s in kept}
        if s in kept:
            row["trade"] = "Kept"
        elif m is None:
            row["trade"] = "Held, not in model"
        else:
            row["gap"] = mv - hv
            if paper_only:
                row["trade"] = "Plan funds only, use as a guide"
            elif price and abs(row["gap"]) >= price:
                sh = int(abs(row["gap"]) // price)
                row["trade"] = ("Buy %d sh" if row["gap"] > 0 else "Sell %d sh") % sh
            else:
                row["trade"] = "Close enough"
        if show_tax and s not in kept and hv > 0 and h.get("cost") is not None:
            frac = 1.0 if m is None else (min(1.0, max(0.0, -row["gap"] / hv)) if row["gap"] is not None and row["gap"] < 0 else 0.0)
            g = (hv - float(h["cost"])) * frac
            if frac > 0:
                row["tax"] = g
                if g >= 0:
                    gain += g
                else:
                    loss += g
        rows.append(row)
    both = sum(min(r["model"] or 0.0, r["hold"]) for r in rows if r["model"] is not None)
    mtot = sum(r["model"] or 0.0 for r in rows)
    return {"rows": rows, "match_pct": (both / mtot * 100.0) if mtot else None,
            "tax": {"gain": gain, "loss": loss} if show_tax else None, "paper_only": paper_only}


def drift_table(target: dict, model_now: dict, account_now: dict, amber: float = None) -> list:
    """Per bucket: target / model now / account now (all in %) and account minus target, amber flag."""
    amber = PB_PARAMS["drift_amber_pts"] if amber is None else amber
    out = []
    for b in BUCKETS + ["Cash"]:
        t, m, a = target.get(b, 0.0), model_now.get(b, 0.0), account_now.get(b, 0.0)
        if not (t or m or a):
            continue
        gap = a - t
        out.append({"bucket": b, "target": t, "model": m, "account": a, "gap": gap, "amber": abs(gap) >= amber})
    return out


# ---------------------------------------------------------------------------
# Back-test ("what would have happened"): replay the same build on past dates, using only
# data up to each start date. Uses hist closes (drv_quote + hist_quote_daily if it has data).
# Not replayed (history not kept): Final Call skip, Hedgeye outlooks, style flavours, kept holdings.
# ---------------------------------------------------------------------------
def _min_index_for(req: dict) -> int:
    """Smallest start index (0-based, in the SPY calendar) that has enough history for the chosen pick rules."""
    from etl.derive_model_portfolio import RECIPES
    need = PB_PARAMS["vol_min_obs"]
    for b, cfg in (req.get("buckets") or {}).items():
        rule = cfg.get("pick") if cfg.get("split", "area") == "area" else (cfg.get("recipe") or cfg.get("split"))
        if rule in RECIPES:
            need = max(need, RECIPES[rule]["min_days"] - 1)
    if not (req.get("buckets") or {}).get("Equities"):
        # the default Equities recipe is Momentum in a source pool, Low volatility otherwise
        need = max(need, RECIPES["momentum" if req.get("sources") else "low_vol"]["min_days"] - 1)
    return need


def backtest(closes: dict, trend: dict, base_funds: dict, base_ctx: dict, req: dict, horizon: str) -> dict:
    """closes {sym: {date: close}} incl. SPY; trend {sym: {date: trend}}; base_funds = ctx['funds'] (meta only);
    base_ctx carries outlook, presets, quad_inputs {monthly, quarterly}. Returns periods + honest counts."""
    from etl.derive_model_portfolio import (
        swings, beta_vs_spy, momentum, above_trend, horizon_quad_mix, series_stats,
    )
    spy = closes.get("SPY") or {}
    cal = sorted(spy)
    n = len(cal)
    h = PB_PARAMS["horizon_trading_days"].get(horizon, 63)
    hd = PB_PARAMS["horizon_days"].get(horizon, 91)
    step = PB_PARAMS["backtest_step"]
    first = _min_index_for(req)
    pool = bool(req.get("sources"))
    area_mode = any((cfg.get("split") or ("recipe" if pool else "area")) == "area" for b, cfg in (req.get("buckets") or {"Equities": {}}).items()
                    if b in ("Equities", "Fixed Income")) or (not req.get("buckets") and not pool)
    quad_needed = area_mode or "quad" in (req.get("checks") or [])
    qin = base_ctx.get("quad_inputs") or {}
    out = {"periods": [], "skipped_quad": 0, "calendar_days": n, "horizon": horizon, "area_mode": quad_needed}
    if n < first + h + 1:
        out.update(summary=_bt_summary([], horizon, out))
        return out
    starts = []
    i = n - 1 - h
    while i >= first:
        starts.append(i)
        i -= step
    starts.reverse()
    notional = 10000.0
    for i in starts:
        t = cal[i]
        dates_t = cal[: i + 1]
        funds_t = {}
        for sym, f in base_funds.items():
            c = closes.get(sym) or {}
            if not f.get("listed", True) or t not in c:
                funds_t[sym] = dict(f, eligible=False, reason="no close that day")
                continue
            series = [c[d_] for d_ in sorted(c) if d_ <= t]
            beta_v, _w = beta_vs_spy(c, spy, dates_t) if sym != "SPY" else (1.0, 0)
            funds_t[sym] = dict(f, eligible=True, reason=None, price=c[t], vol63=swings(series), beta=beta_v, mom=momentum(series),
                                above_trend=above_trend(c[t], (trend.get(sym) or {}).get(t)), hedgeye={}, styles=[], final_code=None)
        quad = horizon_quad_mix(t, hd, qin.get("monthly") or {}, qin.get("quarterly") or {}, None, None)
        if quad_needed and not req.get("quad_override") and (quad["shares"] is None or quad["coverage_pct"] < PB_PARAMS["quad_min_cover_pct"]):
            out["skipped_quad"] += 1
            continue
        if quad_needed and quad["shares"] is not None and not any(ym in (qin.get("monthly") or {}) for ym, _w in quad["weighted"]):
            out["quarter_only"] = out.get("quarter_only", 0) + 1
        ctx_t = {"D": t, "funds": funds_t, "outlook": base_ctx.get("outlook") or {}, "quad": quad, "risk_mult": None,
                 "presets": base_ctx.get("presets") or {}, "kept": [],
                 "account": {"value": notional, "holdings": {}, "cash": notional, "current_mix": {"Cash": 100.0}}}
        req_t = dict(req, amount=notional, use_risk_dial=False, skip_sells=False)
        res = build_positions(ctx_t, req_t)
        pos = res["positions"]
        if len(pos) < 3:
            continue
        cash = res["cash"]["dollars"]
        path, spy_path = [], []
        last_px = {x["sym"]: x["price"] for x in pos}
        for k in range(1, h + 1):
            dk = cal[i + k]
            for x in pos:
                px = (closes.get(x["sym"]) or {}).get(dk)
                if px:
                    last_px[x["sym"]] = px
            path.append(sum(x["shares"] * last_px[x["sym"]] for x in pos) + cash)
            spy_path.append(notional * spy[dk] / spy[t])
        st_ = series_stats(path, spy_path, notional)
        out["periods"].append({"start_idx": i, "start": t.isoformat(), "end": cal[i + h].isoformat(), "ret": st_["ret"],
                               "spy_ret": st_["spy_ret"], "excess": st_["ret"] - st_["spy_ret"], "worst_drop": st_["worst_drop"],
                               "calmer": (st_["swings"] < st_["spy_swings"]) if (st_["swings"] is not None and st_["spy_swings"] is not None) else None,
                               "positions": len(pos)})
    out["summary"] = _bt_summary(out["periods"], horizon, out)
    return out


def _bt_summary(periods: list, horizon: str, out: dict) -> dict:
    h = PB_PARAMS["horizon_trading_days"].get(horizon, 63)
    chosen, last = [], None
    for p_ in periods:
        if last is None or p_["start_idx"] >= last + h:
            chosen.append(p_)
            last = p_["start_idx"]
    s = {"periods_total": len(periods), "periods": len(chosen), "beat_spy": sum(1 for p_ in chosen if p_["excess"] > 0),
         "calmer": sum(1 for p_ in chosen if p_["calmer"]), "calmer_known": sum(1 for p_ in chosen if p_["calmer"] is not None),
         "avg_excess": (sum(p_["excess"] for p_ in periods) / len(periods)) if periods else None,
         "worst_excess": min((p_["excess"] for p_ in periods), default=None), "message": None,
         "bars": [{"start": p_["start"], "model": p_["ret"], "spy": p_["spy_ret"]} for p_ in chosen]}
    if not chosen:
        s["message"] = ("Not enough Quad history" if out.get("skipped_quad") else "Not enough history yet")
    elif len(chosen) < PB_PARAMS["backtest_min_periods"]:
        s["message"] = "Too few periods to mean much"
    if out.get("area_mode") and out.get("quarter_only"):
        s["quad_note"] = ("%d period(s) used the quarter's declared Quad: the monthly Quad mix was not stored before Sep 2026. " % out["quarter_only"]) + s.get("quad_note", "")
    if out.get("area_mode") and out.get("skipped_quad"):
        s["quad_note"] = s.get("quad_note", "") + "'By area' needs the stored monthly Quad mix: %d past period(s) skipped for lack of it." % out["skipped_quad"]
    return s
