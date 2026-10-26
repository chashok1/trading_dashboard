"""
etl/derive_signal_winrate.py -- TASK_154 / TASK_155: nightly "win %" per technical rule.

For every numbered Technical rule (Step 1: S1-a..S1-d, 1a, 1b, 1d, 1e; Step 2: 2a..2f; Step 3: 3a, 3x, 3f, 3h, 3k, 3p, tr) work out,
over all history, how often the stock was UP / DOWN 1, 2, 3, 4 (main, short term) and 10, 15 (reference only) trading days later.
Display only: the Action popup shows it next to the rule that fired. It never changes consolidated_action, trig_action or any rule.

TASK_155 (2026-10-25): the history is REBUILT FROM RAW DATA with the same classifier the live derive uses (etl/technical_rules.py),
not from stored codes (stored bull_rr_action / trend_trade_rule before the redesign follow older definitions). Raw inputs:
prices drv_quote, LRR/TRR drv_rr, Trade / Trend lines hist_td, SD hist_tw, MACDH drv_cat_atomic_input, bands drv_tn_td_bb_rr.

Result lives in drv_signal_winrate (replaced wholesale each run -- it is a history statistic,
not a per-as_of_date derive, so the "DELETE WHERE as_of_date=D" convention does not apply).
Percentages count SIGNALS (a stock firing on several days counts several times).
Splits (3-day horizon only): out:* (outlook), pos:* (which lines), flag:above|below (Above / Below Trade+Trend), band:rise|flat|fall.

Runs nightly from etl/scheduler.py; by hand: python -m etl.derive_signal_winrate
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

from etl.db import get_engine, session_scope
from etl.technical_rules import LRR_ZONE, classify as classify_rules

log = logging.getLogger(__name__)

HORIZONS = (1, 2, 3, 4, 10, 15)
SPLIT_HORIZON = 3
MIN_SIGNALS = 30          # below this a percentage is not shown ("few"); also the "thin" stock floor
UP_TAG, DOWN_TAG = 55.0, 45.0
STALE_DATE_SHARE = 0.9
# Same defaults as etl/derive.py::_derive_trend_trade_rules_impl (overridden from ref_settings in _params()).
SD_TOL = 0.5              # trend_trade_sd_tolerance
LRR_BREAK_ATR = 1.5       # lrr_break_atr_mult
ATR_FALLBACK = 1.34       # ATR runs ~1.34 x SD when a symbol has no ATR
MEDIAN_SD_WINDOW = "30D"  # sd_median_window_days

_Q = {
    "base": """select r.as_of_date d, r.tos_symbol s, r.bb_rng_strk_rule qj,
        q.last_price px, q.high_price hi, q.low_price lo
    from drv_tn_td_bb_rr r join drv_quote q on q.as_of_date=r.as_of_date and q.tos_symbol=r.tos_symbol
    where q.last_price>0""",
    "rr": "select as_of_date d, tos_symbol s, lrr, trr, outlook ol from drv_rr where lrr is not null",
    "ai": "select as_of_date d, tos_symbol s, macdh_direction mh from drv_cat_atomic_input",
    "td": """select distinct on (tos_symbol, export_date) export_date d, tos_symbol s, a_trade_value tv, a_trend_value tn
    from hist_td where a_trade_value is not null order by tos_symbol, export_date, sequence desc""",
    "tw": """select distinct on (tos_symbol, export_date) export_date d, tos_symbol s, standard_dev sd
    from hist_tw where standard_dev is not null order by tos_symbol, export_date, sequence desc""",
}


def apply_stale_fix(df: pd.DataFrame) -> pd.DataFrame:
    """Drop dates where >90% of stocks repeat the prior price (weekend / holiday / feed not refreshed),
    then blank any stock-day whose price equals that stock's previous kept day. Needs columns d, s, px.
    The un-blanked price is kept in px_raw (used for look-back features such as "price 2 days ago")."""
    df = df.sort_values(["s", "d"]).reset_index(drop=True)
    same = df["px"] == df.groupby("s")["px"].shift(1)
    share = df.assign(_s=same).groupby("d")["_s"].mean()
    bad = set(share[share > STALE_DATE_SHARE].index)
    df = df[~df["d"].isin(bad)].copy().reset_index(drop=True)
    df["px_raw"] = df["px"]
    same = df["px"] == df.groupby("s")["px"].shift(1)
    df.loc[same, "px"] = np.nan
    return df


def tag_for(pct_up, pct_down) -> str | None:
    """'mostly UP' (up share of up+down >= 55%), 'mostly DOWN' (<= 45%) or 'even'. None when unknown."""
    if pct_up is None or pct_down is None or pd.isna(pct_up) or pd.isna(pct_down):
        return None
    tot = pct_up + pct_down
    if tot <= 0:
        return None
    share = pct_up / tot * 100.0
    return "mostly UP" if share >= UP_TAG else ("mostly DOWN" if share <= DOWN_TAG else "even")


def _params(engine) -> dict:
    """Rule tunables from ref_settings (same settings the live derive reads); defaults above when missing."""
    p = {"sd_tol": SD_TOL, "lrr_atr": LRR_BREAK_ATR, "lrr_zone": LRR_ZONE, "win": MEDIAN_SD_WINDOW}
    names = {"trend_trade_sd_tolerance": "sd_tol", "lrr_break_atr_mult": "lrr_atr", "range_lrr_zone_pct": "lrr_zone"}
    try:
        with engine.connect() as c:
            rows = c.execute(text("select setting_name, setting_value from ref_settings where setting_name in "
                                  "('trend_trade_sd_tolerance','lrr_break_atr_mult','range_lrr_zone_pct','sd_median_window_days')")).fetchall()
        for n, v in rows:
            if n in names:
                p[names[n]] = abs(float(v))
            elif n == "sd_median_window_days":
                p["win"] = f"{int(float(v))}D"
    except Exception:
        log.warning("signal winrate: could not read ref_settings, using defaults", exc_info=True)
    return p


def _load(engine, win: str = MEDIAN_SD_WINDOW) -> pd.DataFrame:
    with engine.connect() as c:
        D = {k: pd.read_sql(text(v), c) for k, v in _Q.items()}
    for k in D:
        D[k]["d"] = pd.to_datetime(D[k]["d"])
    df = D["base"]
    for k in ("rr", "ai", "td"):
        df = df.merge(D[k].drop_duplicates(["d", "s"]), on=["d", "s"], how="left")
    df = df.drop_duplicates(["s", "d"])
    df["px"] = df["px"].astype(float)
    # hist_tw is a WEEKLY export: like the live derive, use the latest weekly SD on or before each day, and the median of the weekly SDs
    # in the last N days (the rules use the smaller of the two).
    tw = D["tw"].drop_duplicates(["d", "s"]).sort_values(["s", "d"]).reset_index(drop=True)
    tw["sd"] = tw["sd"].astype(float)
    tw["sd_med"] = tw.set_index("d").groupby("s")["sd"].rolling(win, min_periods=1).median().to_numpy()
    df = pd.merge_asof(df.sort_values("d"), tw.sort_values("d")[["d", "s", "sd", "sd_med"]], on="d", by="s", direction="backward")
    return df


def trend_trade_code(df: pd.DataFrame, sd_tol: float = SD_TOL) -> pd.Series:
    """The Step 1 base category (trend_trade_rule), rebuilt from raw prices -- mirrors the CASE in etl/derive.py Pass 1.
    -2 below both, -1 Trade below Trend and price < 1 ATR above Trade, 4/3 above both (4 = extended), 2 between lines,
    0 rising dip, 5 neutral dip, 1 below Trade. NaN when the Trade / Trend line or the SD is missing."""
    px, tv, tn, sdm = df["px"], df["tv"], df["tn"], df["sdm"]
    good = sdm > 0
    trend_sd = pd.Series(np.where(px == tn, 0.1, np.where(good, (px - tn) / sdm.where(good), np.nan)), index=df.index)
    trade_sd = ((px - tv) / sdm.where(good))
    tt_sd = ((tv - tn) / sdm.where(good))
    atr_e = df["atr"].fillna(ATR_FALLBACK * sdm)
    near_dip = (trend_sd > -sd_tol) & (trade_sd < -sd_tol) & (trade_sd >= -1) & df["up"] & (px >= df["tvmin5"])
    conds = [
        (trend_sd < -sd_tol) & (trade_sd < -sd_tol),
        (tt_sd < 0) & (atr_e > 0) & ((px - tv) / atr_e < 1),
        (trend_sd > -sd_tol) & (trade_sd > -sd_tol) & ((tt_sd > 2) | (np.fmax(trend_sd, trade_sd) > 4)),
        (trend_sd > -sd_tol) & (trade_sd > -sd_tol),
        (trend_sd < -sd_tol) & (trade_sd > -sd_tol),
        near_dip & (df["mh"] > 0),
        near_dip,
    ]
    code = pd.Series(np.select([c.fillna(False) for c in conds], [-2, -1, 4, 3, 2, 0, 5], default=1), index=df.index).astype(float)
    return code.where(tv.notna() & tn.notna() & px.notna() & sdm.notna())


def _prepare(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    params = params or {"sd_tol": SD_TOL, "lrr_atr": LRR_BREAK_ATR, "lrr_zone": LRR_ZONE, "win": MEDIAN_SD_WINDOW}
    df = apply_stale_fix(df)
    dates = sorted(df["d"].unique())
    df["di"] = df["d"].map({d: i for i, d in enumerate(dates)})
    for col in ("px", "px_raw", "hi", "lo", "lrr", "trr", "tv", "tn", "sd"):
        df[col] = df[col].astype(float)
    g = df.groupby("s")
    df["pc"], df["pc2"], df["pc3"] = g["px_raw"].shift(1), g["px_raw"].shift(2), g["px_raw"].shift(3)
    df["ph"] = g["hi"].shift(1)
    tr = np.maximum(df["hi"] - df["lo"], np.maximum((df["hi"] - df["pc"]).abs(), (df["lo"] - df["pc"]).abs()))
    df["atr"] = tr.groupby(df["s"]).transform(lambda x: x.rolling(14, min_periods=10).mean())
    # SD used by the rules = the smaller of the latest weekly SD and its median over the last N days (as in the live derive)
    df["sdm"] = np.fmin(df["sd"], df["sd_med"]).fillna(df["atr"] / ATR_FALLBACK)
    # hist_tw (SD) only exists for part of the history; where it is missing use ATR / 1.34 (ATR runs ~1.34 x the SD) so those days still count
    # Trade-line features: lowest of the PREVIOUS 5 lines (today excluded), lowest of 5 incl. today (rising-dip test), fell below Trade in the last 3 days
    df["tvmin5prev"] = df.groupby("s")["tv"].transform(lambda x: x.shift(1).rolling(5, min_periods=3).min())
    df["tvmin5"] = df.groupby("s")["tv"].transform(lambda x: x.rolling(5, min_periods=3).min())
    fell = pd.Series(False, index=df.index)
    for k in (1, 2):   # 2026-10-26, user: the last 3 days include today, so only the 2 days before today can be the "at or above" day
        fell |= (g["px_raw"].shift(k) >= g["tv"].shift(k)).fillna(False)
    df["fell3"] = fell
    df["up"] = (df["px"] > df["pc"]).fillna(False)
    df["below5"] = (df["px"] < df["tvmin5prev"]).fillna(False)
    rng = df["trr"] - df["lrr"]
    zt = (df["lo"] <= df["lrr"] + params["lrr_zone"] * rng).where(rng > 0)
    df["zone_today"] = zt.fillna(False).astype(bool)
    zf = zt.astype(float)
    zg = zf.groupby(df["s"])
    df["zone_recent"] = ((zg.shift(1) == 1) | (zg.shift(2) == 1) | (zg.shift(3) == 1))
    df["trr_up5"] = (df["trr"] >= 1.02 * g["trr"].shift(5)).fillna(False)
    atr_e = df["atr"].fillna(ATR_FALLBACK * df["sdm"])
    df["brk"] = ((df["lrr"] - df["px"]) / atr_e.where(atr_e > 0) > params["lrr_atr"]).fillna(False)
    df["qe"] = trend_trade_code(df, params["sd_tol"])
    df["bx"] = ((df["qe"] == 1) & (df["px"] > df["pc"]) & (df["pc"] > df["pc2"]) & (df["pc2"] > df["pc3"])
                & (df["px"] > df["ph"]) & ~df["brk"])
    piv = df.pivot(index="di", columns="s", values="px")
    for h in HORIZONS:
        r = ((piv.shift(-h) / piv - 1) * 100).clip(-50, 50).stack().rename(f"r{h}").reset_index()
        df = df.merge(r, on=["di", "s"], how="left")
    return df


def classify(df: pd.DataFrame, lrr_zone: float = LRR_ZONE) -> dict:
    """{rule id: boolean mask}. Step 1 / Step 3 ids come straight from etl/technical_rules.classify (the live classifier);
    a bounce-exception stock that skips the Trade-line sell is "1d"."""
    res = classify_rules(df, lrr_zone=lrr_zone)
    qe, qj = df["qe"], df["qj"].fillna(0)
    valid = df["px"].notna()
    lab = {}
    for sid in ("S1-a", "S1-b", "S1-c", "S1-d", "1a", "1b", "1d", "1e"):
        lab[sid] = res["s1_id"] == sid
    p2 = qe.notna() & ~qe.isin([0, 5])           # stocks that go through the band gate and Step 3
    lab["2a"] = p2 & (qj >= 3)
    lab["2b"] = p2 & (qj == 2)
    lab["2c"] = p2 & (qj == 1)
    lab["2d"] = p2 & (qj == 0)
    lab["2e"] = p2 & (qj == -1)
    lab["2f"] = p2 & (qj <= -2)
    for sid in ("3a", "3x", "3f", "3h", "3k", "3p", "tr"):
        lab[sid] = res["s3_id"] == sid
    out = {k: (v.fillna(False).astype(bool) & valid) for k, v in lab.items()}
    out["_flag_above"] = pd.Series(res["flag"] == "above", index=df.index)
    return out


def _outlook_group(o) -> str:
    if not isinstance(o, str):
        return "none"
    o = o.lower()
    return "bull" if "bull" in o else ("bear" if "bear" in o else ("neu" if "neutral" in o else "none"))


def _stat(sub: pd.DataFrame, h: int) -> dict:
    v = sub[f"r{h}"].dropna()
    n = int(len(v))
    return {"n_signals": int(len(sub)), "n_stocks": int(sub["s"].nunique()), "n_followup": n,
            "pct_up": float((v > 0).mean() * 100) if n else None,
            "pct_down": float((v < 0).mean() * 100) if n else None}


def build_rows(df: pd.DataFrame, lrr_zone: float = LRR_ZONE) -> list[dict]:
    df = df.copy()
    df["og"] = df["ol"].map(_outlook_group)
    out = []
    masks = classify(df, lrr_zone)
    above = masks.pop("_flag_above")
    qj = df["qj"].fillna(0)
    for sid, m in masks.items():
        sub = df[m]
        if sub.empty:
            continue
        for h in HORIZONS:
            out.append({"step_id": sid, "horizon_days": h, "split_key": "all", **_stat(sub, h)})
        splits = {"out:bull": sub["og"] == "bull", "out:bear": sub["og"] == "bear", "out:neu": sub["og"] == "neu",
                  "pos:both": sub["qe"].isin([3, 4]), "pos:trend_only": sub["qe"] == 1, "pos:trade_only": sub["qe"] == 2,
                  "flag:above": above[sub.index], "flag:below": ~above[sub.index]}
        if sid[0] == "3" or sid == "tr":
            splits.update({"band:rise": qj[sub.index] >= 2, "band:flat": (qj[sub.index] >= 0) & (qj[sub.index] < 2), "band:fall": qj[sub.index] < 0})
        for key, sm in splits.items():
            ss = sub[sm]
            if len(ss):
                out.append({"step_id": sid, "horizon_days": SPLIT_HORIZON, "split_key": key, **_stat(ss, SPLIT_HORIZON)})
    return out


SCREEN = "dashboard"          # shows in the top-bar warnings feed (GET /api/warnings)
MIN_DAYS = 60                 # fewer real trading days than this = history too short to trust
MAX_LAG_DAYS = 7              # newest history older than this vs the newest derive date = stale


def _set_warnings(items: list[tuple[str, str, str]]) -> None:
    """Replace this job's dashboard warnings with ``items`` = [(code, severity, message)].
    Own session so a failed run can still record why; never raises (the job must not die on its own reporting)."""
    try:
        from etl.warnings import add_warning
        with session_scope() as s:
            s.execute(text("DELETE FROM meta_warning WHERE screen = :s AND code LIKE 'signal_winrate%'"), {"s": SCREEN})
            for code, sev, msg in items:
                add_warning(s, SCREEN, msg, severity=sev, code=code)
    except Exception:
        log.exception("signal winrate: could not record dashboard warnings")


def _data_checks(df: pd.DataFrame, rows: list[dict], newest_derive) -> list[tuple[str, str, str]]:
    """Non-fatal data-quality problems worth showing on the dashboard."""
    out = []
    days = int(df["d"].nunique())
    if days < MIN_DAYS:
        out.append(("signal_winrate_short_history", "warning",
                    f"Step win % uses only {days} real trading days (needs {MIN_DAYS}+): numbers may be unreliable"))
    last = df["d"].max()
    if newest_derive is not None and (pd.Timestamp(newest_derive) - last).days > MAX_LAG_DAYS:
        out.append(("signal_winrate_stale", "warning",
                    f"Step win % history ends {last.date()}, behind the latest data {pd.Timestamp(newest_derive).date()}"))
    steps = {r["step_id"] for r in rows if r["split_key"] == "all" and r["horizon_days"] == SPLIT_HORIZON}
    few = {r["step_id"] for r in rows if r["split_key"] == "all" and r["horizon_days"] == SPLIT_HORIZON
           and r["n_signals"] < MIN_SIGNALS}
    if steps and len(few) > len(steps) / 2:
        out.append(("signal_winrate_sparse", "warning",
                    f"Step win %: {len(few)} of {len(steps)} steps have fewer than {MIN_SIGNALS} past signals"))
    return out


def compute_rows(engine=None):
    """(prepared history frame, rows) -- read-only; run() writes them. Also handy for a dry run."""
    engine = engine or get_engine()
    params = _params(engine)
    df = _prepare(_load(engine, params["win"]), params)
    if df.empty:
        raise ValueError("no price/step history found (drv_tn_td_bb_rr joined to drv_quote is empty)")
    rows = build_rows(df, params["lrr_zone"])
    if not rows:
        raise ValueError("no step statistics were produced from the history")
    return df, rows


def run() -> dict:
    """Recompute drv_signal_winrate from scratch (idempotent). Returns a small summary dict.

    Any failure is recorded as a dashboard warning (and re-raised for the scheduler to log); the old table
    contents stay because the delete + insert is one transaction. Data-quality problems become warnings too."""
    try:
        df, rows = compute_rows()
        hist_from, hist_to = df["d"].min().date(), df["d"].max().date()
        for r in rows:
            r["history_from"], r["history_to"] = hist_from, hist_to
        with session_scope() as s:
            newest = s.execute(text("SELECT MAX(as_of_date) FROM drv_tn_td_bb_rr")).scalar()
            s.execute(text("DELETE FROM drv_signal_winrate"))
            s.execute(text(
                "INSERT INTO drv_signal_winrate (step_id, horizon_days, split_key, n_signals, n_stocks,"
                " n_followup, pct_up, pct_down, history_from, history_to) VALUES (:step_id, :horizon_days,"
                " :split_key, :n_signals, :n_stocks, :n_followup, :pct_up, :pct_down, :history_from,"
                " :history_to)"), rows)
    except Exception as e:
        log.exception("signal winrate: failed")
        _set_warnings([("signal_winrate_failed", "error",
                        f"Step win % job failed: {type(e).__name__}: {str(e)[:200]} (popup shows the last good numbers)")])
        raise
    _set_warnings(_data_checks(df, rows, newest))
    summary = {"rows": len(rows), "steps": len({r["step_id"] for r in rows}),
               "days": int(df["d"].nunique()), "from": str(hist_from), "to": str(hist_to)}
    log.info("signal winrate: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
