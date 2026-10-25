"""
etl/derive_signal_winrate.py -- TASK_154: nightly "win %" per technical step.

For every numbered Technical situation (1a..1g, 2a..2f, 3a..3s) work out, over all
history in drv_tn_td_bb_rr, how often the stock was UP / DOWN 1, 2, 3, 4 (main, short term)
and 10, 15 (reference only) trading days later. Display only: the Action popup shows it next
to the step that fired. It never changes consolidated_action, trig_action or any rule.

Result lives in drv_signal_winrate (replaced wholesale each run -- it is a history statistic,
not a per-as_of_date derive, so the "DELETE WHERE as_of_date=D" convention does not apply).
Percentages count SIGNALS (a stock firing on several days counts several times).

Ported from the prototype backtest: 1b, 1d and 3a are rebuilt from raw prices because the
stored flags (lrr_idx_eff, bounce_exempt, trend_trade_rule 0/5) exist only for recent days.

Runs nightly from etl/scheduler.py; by hand: python -m etl.derive_signal_winrate
"""
from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd
from sqlalchemy import text

from etl.db import get_engine, session_scope

log = logging.getLogger(__name__)

HORIZONS = (1, 2, 3, 4, 10, 15)
SPLIT_HORIZON = 3
MIN_SIGNALS = 30          # below this a percentage is not shown ("few"); also the "thin" stock floor
UP_TAG, DOWN_TAG = 55.0, 45.0
STALE_DATE_SHARE = 0.9

_Q = {
    "base": """select r.as_of_date d, r.tos_symbol s, r.trend_trade_rule qe, r.bb_rng_strk_rule qj,
        r.bull_rr_action qm, r.not_bull_rr_action qn,
        q.last_price px, q.high_price hi, q.low_price lo
    from drv_tn_td_bb_rr r join drv_quote q on q.as_of_date=r.as_of_date and q.tos_symbol=r.tos_symbol
    where q.last_price>0""",
    "rr": "select as_of_date d, tos_symbol s, lrr, outlook ol from drv_rr where lrr is not null",
    "ai": "select as_of_date d, tos_symbol s, perf1d_sd_rule p1, macdh_direction mh from drv_cat_atomic_input",
    "td": """select distinct on (tos_symbol, export_date) export_date d, tos_symbol s, a_trade_value tv
    from hist_td where a_trade_value is not null order by tos_symbol, export_date, sequence desc""",
    "tw": """select distinct on (tos_symbol, export_date) export_date d, tos_symbol s, standard_dev sd
    from hist_tw where standard_dev is not null order by tos_symbol, export_date, sequence desc""",
}


def apply_stale_fix(df: pd.DataFrame) -> pd.DataFrame:
    """Drop dates where >90% of stocks repeat the prior price (weekend / holiday / feed not refreshed),
    then blank any stock-day whose price equals that stock's previous kept day. Needs columns d, s, px."""
    df = df.sort_values(["s", "d"]).reset_index(drop=True)
    same = df["px"] == df.groupby("s")["px"].shift(1)
    share = df.assign(_s=same).groupby("d")["_s"].mean()
    bad = set(share[share > STALE_DATE_SHARE].index)
    df = df[~df["d"].isin(bad)].copy().reset_index(drop=True)
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


def _load(engine) -> pd.DataFrame:
    with engine.connect() as c:
        D = {k: pd.read_sql(text(v), c) for k, v in _Q.items()}
    for k in D:
        D[k]["d"] = pd.to_datetime(D[k]["d"])
    df = D["base"]
    for k in ("rr", "ai", "td", "tw"):
        df = df.merge(D[k].drop_duplicates(["d", "s"]), on=["d", "s"], how="left")
    df = df.drop_duplicates(["s", "d"])
    df["px"] = df["px"].astype(float)
    return df


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = apply_stale_fix(df)
    dates = sorted(df["d"].unique())
    df["di"] = df["d"].map({d: i for i, d in enumerate(dates)})
    for col in ("px", "hi", "lo", "lrr", "tv", "sd"):
        df[col] = df[col].astype(float)
    g = df.groupby("s")
    df["pc"], df["pc2"], df["pc3"] = g["px"].shift(1), g["px"].shift(2), g["px"].shift(3)
    df["ph"] = g["hi"].shift(1)
    tr = np.maximum(df["hi"] - df["lo"], np.maximum((df["hi"] - df["pc"]).abs(), (df["lo"] - df["pc"]).abs()))
    df["atr"] = tr.groupby(df["s"]).transform(lambda x: x.rolling(14, min_periods=10).mean())
    df["tv_min5"] = df.groupby("s")["tv"].transform(lambda x: x.rolling(5, min_periods=3).min())
    df["trade_sd"] = (df["px"] - df["tv"]) / df["sd"]
    piv = df.pivot(index="di", columns="s", values="px")
    for h in HORIZONS:
        r = ((piv.shift(-h) / piv - 1) * 100).clip(-50, 50).stack().rename(f"r{h}").reset_index()
        df = df.merge(r, on=["di", "s"], how="left")
    return df


def classify(df: pd.DataFrame) -> dict:
    """{step_id: boolean mask}. Same rules as the prototype backtest (1b/1d/3a rebuilt from prices)."""
    qe, qj = df["qe"], df["qj"]
    brk20 = (df["lrr"] - df["px"]) / df["atr"] > 2.0
    upclose = (df["px"] > df["pc"]) & (df["pc"] > df["pc2"]) & (df["pc2"] > df["pc3"])
    bounce = (qe == 1) & upclose & (df["px"] > df["ph"]) & ~brk20
    dip_b = ((qe == 1) & (df["trade_sd"] >= -1) & (df["trade_sd"] < -0.5)
             & (df["p1"] > 0) & (df["px"] >= df["tv_min5"]))
    lab = {
        "1a": qe.isin([3, 4]),
        "1b": dip_b & (df["mh"] > 0) & ~bounce,
        "1c": (qe == 1) & ~bounce & ~dip_b,
        "1d": bounce,
        "1e": qe == 2,
        "1f": qe == -1,
        "1g": qe == -2,
    }
    p1 = qe.isin([3, 4]) | bounce          # reached step 2/3
    lab["2a"] = p1 & qj.isin([3, 4])
    lab["2b"] = p1 & (qj == 2)
    lab["2c"] = p1 & (qj == 1)
    lab["2d"] = p1 & (qj == 0)
    lab["2e"] = p1 & (qj == -1)
    lab["2f"] = p1 & (qj <= -2)
    lab["3a"] = p1 & brk20
    ok = p1 & ~brk20
    bull, flat, fall = ok & (qj >= 2), ok & qj.isin([0, 1]), ok & (qj < 0)
    for nm, k in zip("bcdefghi", (6, 5, 4, 3, 2, 7, 1, -1)):
        lab[f"3{nm}"] = bull & (df["qm"] == k)
    for nm, k in zip("jklmn", (5, -1, 4, 3, 2)):
        lab[f"3{nm}"] = flat & (df["qn"] == k)
    for nm, k in zip("opqrs", (5, -1, 4, 3, 2)):
        lab[f"3{nm}"] = fall & (df["qn"] == k)
    return {k: v.fillna(False) for k, v in lab.items()}


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


def build_rows(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["og"] = df["ol"].map(_outlook_group)
    out = []
    for sid, m in classify(df).items():
        sub = df[m]
        if sub.empty:
            continue
        for h in HORIZONS:
            out.append({"step_id": sid, "horizon_days": h, "split_key": "all", **_stat(sub, h)})
        splits = {"out:bull": sub["og"] == "bull", "out:bear": sub["og"] == "bear", "out:neu": sub["og"] == "neu",
                  "pos:both": sub["qe"].isin([3, 4]), "pos:trend_only": sub["qe"] == 1, "pos:trade_only": sub["qe"] == 2}
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


def run() -> dict:
    """Recompute drv_signal_winrate from scratch (idempotent). Returns a small summary dict.

    Any failure is recorded as a dashboard warning (and re-raised for the scheduler to log); the old table
    contents stay because the delete + insert is one transaction. Data-quality problems become warnings too."""
    try:
        engine = get_engine()
        df = _prepare(_load(engine))
        if df.empty:
            raise ValueError("no price/step history found (drv_tn_td_bb_rr joined to drv_quote is empty)")
        rows = build_rows(df)
        if not rows:
            raise ValueError("no step statistics were produced from the history")
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
