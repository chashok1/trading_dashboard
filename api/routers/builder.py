"""Portfolio Builder API (DESIGN_SPEC_9/10/11). Thin layer over etl/builder_*.py.

The Builder never trades and never changes the Actionable Final Call. Every endpoint tolerates empty or
missing builder tables and says so under `problems` instead of failing.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import text

from api._helpers import _resolve_date, expected_market_close_date
from etl import builder_data as bd
from etl import builder_store as bs
from etl.builder_engine import build_positions
from etl.db import session_scope
from etl.derive_model_portfolio import (
    BUCKETS, FLAVOURS, PB_PARAMS, RECIPES, STANDARD_FUND, BUCKET_OUTLOOK,
)

router = APIRouter()


def _stale(d) -> bool:
    try:
        return d < expected_market_close_date()
    except Exception:
        return False


def _fail(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/api/builder/recipes")
def get_recipes(date: Optional[str] = Query(None)):
    """Recipes plus readiness (needs N more days of price history)."""
    d = _resolve_date(date)
    with session_scope() as s:
        closes = bd.load_closes(s, ["SPY"], d)
    have = len(closes.get("SPY") or {})
    out = []
    for k, r in RECIPES.items():
        need = max(0, r["min_days"] - have)
        out.append({"key": k, "label": r["label"], "text": r["text"], "min_days": r["min_days"], "ready": need == 0,
                    "needs_more_days": need})
    return {"recipes": out, "history_days": have,
            "bucket_recipes": {"Equities": ["area", "low_vol", "low_beta", "momentum"], "Fixed Income": ["area", "core", "low_vol"]},
            "bucket_outlook": {k: list(v) for k, v in BUCKET_OUTLOOK.items()}}


def _accept_blocks(res: dict, ctx: dict, account: str, data_stale: bool) -> list:
    why = []
    if account == "ALL":
        why.append("Whole book is preview only: pick one account to freeze a model.")
    if data_stale:
        why.append("The data is behind market close.")
    if res["amount"] <= 0:
        why.append("The amount is 0.")
    if len([x for x in res["positions"] if not x["is_kept"]]) < 3:
        why.append("Fewer than 3 funds qualify.")
    return why


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
                          "running": bd.running_model(s, account) if account != "ALL" else None,
                          "holdings": [{"sym": k, "value": h["value"], "bucket": h["bucket"], "area": h["area"],
                                        "kept": k in set(ctx["kept"])} for k, h in sorted(acct["holdings"].items(), key=lambda kv: -kv[1]["value"])]}
        res["as_of"] = d.isoformat()
        res["data_stale"] = stale
        res["horizon"] = horizon
        res["end_date"] = bs.add_months(d, PB_PARAMS["horizon_months"].get(horizon, 3)).isoformat()
        res["accept_blocked"] = _accept_blocks(res, ctx, account, stale)
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
        res["exposure"] = {"picked": bd.exposure(pvals, info), "held": bd.exposure(hvals, info)}
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
    return {"sources": [{"code": "FUND", "label": "Fixed fund list"}, {"code": "HELD", "label": "Your holdings"}] +
                       [{"code": k, "label": v} for k, v in bd.SOURCE_LABELS.items()],
            "checks": [{"key": k, "label": v} for k, v in CHECKS.items()]}


@router.get("/api/builder/source-names")
def get_source_names(sources: str = Query(""), account: Optional[str] = Query(None), date: Optional[str] = Query(None)):
    """Every name on the ticked Hedgeye lists, with asset class and a Usable / reason status (information only)."""
    d = _resolve_date(date)
    problems: list = []
    codes = [c for c in sources.split(",") if c]
    with session_scope() as s:
        names = bd.source_names(s, d, codes, problems, account)
    return {"names": names, "problems": problems}


@router.post("/api/builder/compare")
def post_compare(body: dict = Body(...), date: Optional[str] = Query(None)):
    """Same source pool built as picked / +Low beta / +Quad check / +Both, side by side, with an information-only back-test."""
    d = _resolve_date(date)
    if not body.get("sources"):
        raise HTTPException(status_code=400, detail="Pick at least one source to compare.")
    with session_scope() as s:
        return bd.compare_variants(s, d, body.get("account") or "ALL", body.get("horizon") or "3M", body)


@router.post("/api/builder/backtest")
def post_backtest(body: dict = Body(...), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        return bd.run_backtest(s, d, body)


@router.post("/api/builder/portfolios")
def post_accept(body: dict = Body(...), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    name = body.pop("name", None)
    try:
        with session_scope() as s:
            return bs.accept(s, d, body, name, _stale(d))
    except bs.BuilderError as e:
        _fail(e)


@router.get("/api/builder/portfolios")
def get_portfolios(account: Optional[str] = Query(None), status: Optional[str] = Query(None)):
    with session_scope() as s:
        try:
            return bs.list_portfolios(s, account, status)
        except Exception as e:  # tables not created yet
            s.rollback()
            return {"portfolios": [], "totals": [], "grand": {"value": 0, "ret": None}, "shared_funds": {"funds": [], "over_note": []},
                    "problems": ["Model tables are missing: run python -m db.init_db (%s)" % type(e).__name__]}


@router.get("/api/builder/portfolios/{pid}")
def get_portfolio(pid: int, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        out = bs.detail(s, d, pid)
        if out is not None:
            syms = {x["sym"] for x in (out.get("positions") or [])} | {x["sym"] for x in ((out.get("vs_account") or {}).get("rows") or [])}
            out["outlooks"] = {k: v["outlook"] for k, v in bd.name_info(s, d, sorted(syms), []).items() if v.get("outlook")} if syms else {}
    if out is None:
        raise HTTPException(status_code=404, detail="Model portfolio not found")
    return out


@router.get("/api/builder/portfolios/{pid}/vs-account")
def get_vs_account(pid: int, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        out = bs.detail(s, d, pid)
    if out is None:
        raise HTTPException(status_code=404, detail="Model portfolio not found")
    return {"vs_account": out["vs_account"], "drift": out["drift"], "area_drift": out["area_drift"], "account_info": out["account_info"]}


@router.get("/api/builder/portfolios/{pid}/review-preview")
def get_review_preview(pid: int, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    try:
        with session_scope() as s:
            return bs.review_preview(s, d, pid)
    except bs.BuilderError as e:
        _fail(e)


@router.post("/api/builder/portfolios/{pid}/review")
def post_review(pid: int, body: dict = Body(...), date: Optional[str] = Query(None)):
    """action = roll | close ('change recipe' is done on the page: it opens Build new pre-filled)."""
    d = _resolve_date(date)
    try:
        with session_scope() as s:
            return bs.review_action(s, d, pid, body.get("action") or "", _stale(d), body.get("name"))
    except bs.BuilderError as e:
        _fail(e)


@router.patch("/api/builder/portfolios/{pid}/warnings")
def patch_warnings(pid: int, body: dict = Body(...)):
    try:
        with session_scope() as s:
            return bs.patch_warnings(s, pid, body.get("opt_in"), body.get("dismiss"))
    except bs.BuilderError as e:
        _fail(e)


@router.put("/api/builder/accounts/{short}/keep/{symbol}")
def put_keep(short: str, symbol: str, body: Optional[dict] = Body(None)):
    with session_scope() as s:
        bs.keep_add(s, short, symbol, (body or {}).get("note"))
        return {"kept": bd.keep_list(s, short)}


@router.delete("/api/builder/accounts/{short}/keep/{symbol}")
def delete_keep(short: str, symbol: str):
    with session_scope() as s:
        bs.keep_remove(s, short, symbol)
        return {"kept": bd.keep_list(s, short)}


@router.post("/api/builder/accounts/{short}/keep-lt")
def post_keep_lt(short: str, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        added = bs.keep_add_lt(s, short, d)
        return {"added": added, "kept": bd.keep_list(s, short)}


@router.get("/api/builder/sets")
def get_sets():
    with session_scope() as s:
        return {"sets": bs.set_list(s)}


@router.get("/api/builder/sets/{sid}")
def get_set(sid: int):
    try:
        with session_scope() as s:
            return bs.set_get(s, sid)
    except bs.BuilderError as e:
        _fail(e)


@router.put("/api/builder/sets")
def put_set(body: dict = Body(...)):
    try:
        with session_scope() as s:
            return bs.set_save(s, body.get("name"), body.get("account"), body.get("state") or {})
    except bs.BuilderError as e:
        _fail(e)


@router.delete("/api/builder/sets/{sid}")
def delete_set(sid: int):
    with session_scope() as s:
        bs.set_delete(s, sid)
        return {"sets": bs.set_list(s)}
