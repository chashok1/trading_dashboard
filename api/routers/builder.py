"""Portfolio Builder API (DESIGN_SPEC_9/10/11). Thin layer over etl/builder_*.py.

The Builder never trades and never changes the Actionable Final Call. Every endpoint tolerates empty or
missing builder tables and says so under `problems` instead of failing.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import text

from api._helpers import _resolve_date, expected_market_close_date
from etl import builder_data as bd
from etl.builder_engine import build_positions
from etl.db import session_scope
from etl.derive_model_portfolio import (
    BUCKETS, FLAVOURS, PB_PARAMS, STANDARD_FUND,
)

router = APIRouter()


def _stale(d) -> bool:
    try:
        return d < expected_market_close_date()
    except Exception:
        return False


@router.get("/api/builder/accounts")
def get_accounts(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        out = bd.list_accounts(s, d)
    out["as_of"] = d.isoformat()
    out["data_stale"] = _stale(d)
    return out


@router.get("/api/builder/presets")
def get_presets():
    with session_scope() as s:
        problems: list = []
        pr = bd.presets(s, problems)
    return {"presets": pr, "problems": problems, "buckets": BUCKETS, "standard_funds": STANDARD_FUND,
            "horizons": list(PB_PARAMS["horizon_months"]), "flavours": {k: v for k, v in FLAVOURS.items()}}


@router.post("/api/builder/preview")
def post_preview(body: dict = Body(...), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    account = body.get("account") or "ALL"
    horizon = body.get("horizon") or "3M"
    with session_scope() as s:
        ctx = bd.load_context(s, d, account, horizon, sources=(None if body.get("manual") else body.get("sources")), **bd.manual_kwargs(body))
        res = build_positions(ctx, body)
        acct = ctx["account"]
        stale = _stale(d)
        res["account"] = {"name": account, "type": acct["type"], "value": acct["value"], "snap_date": acct["snap_date"],
                          "positions_stale": acct["stale"], "kept": ctx["kept"],
                          "holdings": [{"sym": k, "value": h["value"], "qty": h.get("qty"), "price": h.get("price"), "bucket": h["bucket"], "area": h["area"],
                                        "kept": k in set(ctx["kept"])} for k, h in sorted(acct["holdings"].items(), key=lambda kv: -kv[1]["value"])]}
        res["as_of"] = d.isoformat()
        res["data_stale"] = stale
        res["horizon"] = horizon
        res["problems"] = ctx["problems"]
        res["risk_label"] = ctx.get("risk_label")
        from etl.builder_engine import vs_account
        res["vs_account"] = vs_account([{"sym": x["sym"], "value": x["value"], "price": x["price"], "area": x["area"], "bucket": x["bucket"]}
                                        for x in res["positions"]], acct["holdings"], set(ctx["kept"]), acct["type"]) if account != "ALL" else None
        # presets with the live fund list size, so the UI can grey out empty buckets
        res["funds_available"] = sum(1 for f in ctx["funds"].values() if f["eligible"])
        # factor exposure of what was picked vs what the account holds now (percent of each side's invested money)
        pvals = {x["sym"]: float(x["value"]) for x in res["positions"]}
        hvals = {k: float(h["value"]) for k, h in acct["holdings"].items() if h.get("value")} if account != "ALL" else {}
        info = bd.name_info(s, d, sorted(set(pvals) | set(hvals)), ctx["problems"])
        for k, h in acct["holdings"].items():       # held names take the class the account side already resolved
            if k in info and h.get("bucket") in BUCKETS:
                info[k]["bucket"] = h["bucket"]
        for x in res["positions"]:      # the asset class you gave a name wins
            if x["sym"] in info and x.get("bucket") in BUCKETS:
                info[x["sym"]]["bucket"] = x["bucket"]
        res["outlooks"] = {k: v.get("outlook") for k, v in info.items() if v.get("outlook")}
        # percent of the WHOLE account (one basis, same as the plan check); no base for the whole-book preview
        base = float(acct.get("value") or 0.0) if account != "ALL" else None
        res["exposure"] = {"picked": bd.exposure(pvals, info, float(res.get("amount") or 0.0) or base), "held": bd.exposure(hvals, info, base)}
        # 2026-11-17: Max $ per stock (room left under every limit, warn-only) and a starting Buy $ for picks with a Buy call
        if account != "ALL" and body.get("plan"):
            try:
                from etl import plan_check as pc
                plan_picks = [x for x in (body["plan"].get("picks") or []) if x.get("sym")]
                picked = {str(x["sym"]).upper() for x in plan_picks}
                cands = [{"sym": str(x["sym"]).upper(), "bucket": x.get("bucket"), "amt": float(x.get("amt") or 0.0), "pick": True} for x in plan_picks]
                cands += [{"sym": k, "bucket": h.get("bucket"), "amt": 0.0, "pick": False} for k, h in acct["holdings"].items() if k not in picked and h.get("value")]
                # 2026-11-18: every name in the names list also gets a Max $ (info comes from the screen, no extra lookups)
                known = {c["sym"] for c in cands}
                for nm in (body.get("names") or [])[:800]:
                    sym = str(nm.get("sym") or "").upper()
                    if not sym or sym in known:
                        continue
                    known.add(sym)
                    if sym not in info:
                        info[sym] = {"bucket": nm.get("bucket"), "sector": nm.get("sector"), "beta": nm.get("beta"),
                                     "styles": nm.get("styles") or [], "quad": nm.get("quad") or []}
                    cands.append({"sym": sym, "bucket": nm.get("bucket"), "amt": 0.0, "pick": False})
                syms = [c["sym"] for c in cands]
                missing = [x for x in syms if x not in info]
                if missing:
                    info.update(bd.name_info(s, d, missing, ctx["problems"]))
                res["room"] = pc.room_for(body["plan"], {"value": acct["value"], "cash": acct.get("cash") or 0.0, "holdings": acct["holdings"]},
                                          cands, info, ps.style_groups(), ps.sizes_for(s, d, account, syms), None,
                                          ps.account_default_size(s, d, account))
                res["room_default"] = ps.account_default_size(s, d, account)
                res["room_meta"] = pc.cash_summary(body["plan"], {"value": acct["value"], "cash": acct.get("cash") or 0.0, "holdings": acct["holdings"]},
                                                   info, ps.style_groups())
            except Exception as e:      # never break the preview over the Max $ column
                res["room"] = {}
                res["problems"].append("Max $ could not be worked out: %s" % e)
    return res


@router.post("/api/builder/asset-class")
def post_asset_class(body: dict = Body(...)):
    """Remember the asset class you chose for a name that had none (ref_sector). A class already on file is never overwritten."""
    sym = (body.get("sym") or "").strip().upper()
    bucket = body.get("bucket")
    if not sym or bucket not in BUCKETS:
        raise HTTPException(status_code=400, detail="Give a symbol and one of the asset classes.")
    label = {"Currency": "FX"}.get(bucket, bucket)      # the label ref_sector uses for that class
    with session_scope() as s:
        s.execute(text("INSERT INTO ref_sector (ticker, asset_class) VALUES (:t, :a) "
                       "ON CONFLICT (ticker) DO UPDATE SET asset_class = EXCLUDED.asset_class "
                       "WHERE ref_sector.asset_class IS NULL"), {"t": sym, "a": label})
    return {"sym": sym, "bucket": bucket}


@router.get("/api/builder/sources")
def get_sources():
    """Hedgeye source lists the pick pool can be built from, and the validation checks."""
    from etl.builder_engine import CHECKS
    return {"sources": [{"code": "FUND", "label": "Fixed fund list"}, {"code": "HELD", "label": "Your holdings"}, {"code": "MINE", "label": "My stocks"}] +
                       [{"code": k, "label": v} for k, v in bd.SOURCE_LABELS.items()],
            "checks": [{"key": k, "label": v} for k, v in CHECKS.items()]}


@router.get("/api/builder/source-names")
def get_source_names(sources: str = Query(""), account: Optional[str] = Query(None), date: Optional[str] = Query(None)):
    """Every name on the ticked Hedgeye lists, with asset class and a Usable / reason status (information only)."""
    d = _resolve_date(date)
    problems: list = []
    codes = [c for c in sources.split(",") if c]
    with session_scope() as s:
        if "MINE" in codes:
            ps.my_stocks(s, d)       # stamps any of the user's stocks that Hedgeye now lists, so they leave My stocks
        names = bd.source_names(s, d, codes, problems, account)
    return {"names": names, "problems": problems}


# ---------------------------------------------------------------------------
# Plan per account, picks and the To do list (DESIGN_SPEC_16). The Builder never trades.
# ---------------------------------------------------------------------------
from etl import plan_store as ps  # noqa: E402


def _plan_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ps.PlanError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/builder/plan/saved")
def get_plan_saved(account: str = Query(...)):
    """The account's saved draft and active plan (cheap: no positions read). Used by the account box on the Build screen."""
    with session_scope() as s:
        row = ps.get_plan_row(s, account)
    state = "active" if row["active"] else ("draft" if row["draft"] else "none")
    return dict(row, state=state)


@router.post("/api/builder/plan/save-check")
def post_plan_save_check(body: dict = Body(...)):
    """Save & check: saves the named version and makes it the checked plan; returns where the account stands."""
    if not body.get("account"):
        raise HTTPException(status_code=400, detail="Choose an account.")
    d = _resolve_date(body.get("date"))
    with session_scope() as s:
        return _plan_call(ps.save_and_check, s, d, body["account"], body.get("plan") or {}, body.get("name"))


@router.post("/api/builder/plan/save-as")
def post_plan_save_as(body: dict = Body(...)):
    """Keep a named version without checking it."""
    if not body.get("account"):
        raise HTTPException(status_code=400, detail="Choose an account.")
    with session_scope() as s:
        return {"name": ps.save_version(s, body["account"], body.get("name"), body.get("plan") or {})}


@router.get("/api/builder/plan/versions")
def get_plan_versions(account: str = Query(...)):
    with session_scope() as s:
        return ps.list_versions(s, account)


@router.get("/api/builder/plan/version")
def get_plan_version(account: str = Query(...), name: str = Query(...)):
    with session_scope() as s:
        p = ps.get_version(s, account, name)
    if p is None:
        raise HTTPException(status_code=404, detail="No such saved plan.")
    return {"name": name, "plan": p}


@router.delete("/api/builder/plan")
def delete_plan(account: str = Query(...), name: Optional[str] = Query(None)):
    with session_scope() as s:
        ps.delete_plan(s, account, name)
    return {"ok": True}


@router.get("/api/builder/todo")
def get_todo(account: str = Query(...), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        out = ps.todo_page(s, d, account)
    out["as_of"] = d.isoformat()
    out["data_stale"] = _stale(d)
    return out


@router.get("/api/builder/acct-room")
def get_acct_room(account: str = Query(...), date: Optional[str] = Query(None)):
    """Actionable screen, one account: held $, Max $, Bucket $ and planned buy per symbol (see plan_store.acct_room_page)."""
    d = _resolve_date(date)
    with session_scope() as s:
        return ps.acct_room_page(s, d, account)


@router.post("/api/builder/done")
def post_done(body: dict = Body(...), date: Optional[str] = Query(None)):
    """Actionable Done with an amount: {account, symbol, side BUY|SELL, amount}. Counts today only, until the positions file shows it."""
    d = _resolve_date(date)
    with session_scope() as s:
        return _plan_call(ps.record_done, s, d, body.get("account"), body.get("symbol"), body.get("side"), body.get("amount"))


@router.delete("/api/builder/done")
def delete_done(account: str = Query(...), symbol: str = Query(...), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        ps.clear_done(s, d, account, symbol)
    return {"ok": True}


@router.get("/api/builder/plan-check")
def get_plan_check(date: Optional[str] = Query(None)):
    """Actionable screen: what each account's ACTIVE plan says about each symbol (pick, group, sell, over plan). Reads only."""
    d = _resolve_date(date)
    with session_scope() as s:
        return ps.plan_check_page(s, d)


@router.post("/api/builder/pick")
def post_pick(body: dict = Body(...)):
    with session_scope() as s:
        pid = _plan_call(ps.add_pick, s, body.get("account"), body.get("side"), body.get("members") or [],
                         body.get("amount") or 0, bool(body.get("ticked")))
    return {"id": pid}


@router.patch("/api/builder/pick/{pid}")
def patch_pick_ep(pid: int, body: dict = Body(...)):
    with session_scope() as s:
        ps.patch_pick(s, pid, body)
    return {"ok": True}


@router.delete("/api/builder/pick/{pid}")
def delete_pick_ep(pid: int):
    with session_scope() as s:
        ps.delete_pick(s, pid)
    return {"ok": True}


@router.get("/api/builder/my-stocks")
def get_my_stocks(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        rows = ps.my_stocks(s, d)
        live = [r["sym"] for r in rows if not r["moved_on"]]
        info = bd.name_info(s, d, live) if live else {}
        for r in rows:
            r["info"] = info.get(r["sym"])
        return {"stocks": rows}


@router.put("/api/builder/my-stocks/{sym}")
def put_my_stock(sym: str, body: Optional[dict] = Body(None), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        return _plan_call(ps.add_my_stock, s, d, sym, (body or {}).get("note"))


@router.delete("/api/builder/my-stocks/{sym}")
def delete_my_stock(sym: str):
    with session_scope() as s:
        ps.remove_my_stock(s, sym)
    return {"ok": True}
