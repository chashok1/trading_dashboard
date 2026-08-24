"""inspect_symbol - CLI dump of every indicator available for one symbol.

Read-only diagnostic tool: pulls the full Actionable row (same data the UI's
Action-column hover would consolidate from) plus the fired composite rules'
live scorecard stats, and prints everything grouped hierarchically. Nothing
here is filtered/curated -- it's the complete inventory, so a design pass can
pick from it deliberately instead of guessing what's available.

Usage:
    python -m etl.inspect_symbol CELH
    python -m etl.inspect_symbol CELH --date 2026-08-18
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import urllib.error
from typing import Any, Optional

from sqlalchemy import text

from etl.db import session_scope

API_BASE = "http://127.0.0.1:8000"


def _fetch_actionable_row(symbol: str, date: Optional[str]) -> Optional[dict]:
    url = f"{API_BASE}/api/actionable"
    if date:
        url += f"?date={date}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Could not reach {url} ({e}). Is the app server running "
            f"(start.bat / uvicorn)?"
        )
    rows = data.get("rows", data) if isinstance(data, dict) else data
    sym = symbol.upper()
    for row in rows:
        if (row.get("tos_symbol") or "").upper() == sym:
            return row
    return None


def _rule_side(rule_id: str) -> str:
    # Composite code convention: NNN-<ACTION>-... ; BS/BM/BMN/BW/B = buy-family,
    # SS/SA/STM/SO/SW = sell-family (see etl/derive_actionable.py ACTION_RANK /
    # web/actionable.js _MAP for the full vocab).
    parts = rule_id.split("-")
    code = parts[1] if len(parts) > 1 else ""
    if code in ("SS", "SA", "STM", "SO", "SW", "SWW"):
        return "SELL"
    if code in ("BS", "BM", "BMN", "BW", "B", "BR"):
        return "BUY"
    return code or "?"


def _scorecard_for(session, rule_ids: list[str]) -> dict[str, dict]:
    if not rule_ids:
        return {}
    rows = session.execute(text("""
        SELECT rule_id, n_fires, edge_20d, win_rate, confidence
        FROM v_rule_scorecard WHERE rule_id = ANY(:ids)
    """), {"ids": rule_ids}).fetchall()
    return {r[0]: {"n_fires": r[1], "edge_20d": r[2], "win_rate": r[3], "confidence": r[4]}
            for r in rows}


def _fmt(v: Any, kind: str = "") -> str:
    if v is None or v == "":
        return "-"
    if kind == "usd":
        try:
            return f"${float(v):,.2f}"
        except (TypeError, ValueError):
            return str(v)
    if kind == "pct":
        try:
            return f"{float(v):.1f}%"
        except (TypeError, ValueError):
            return str(v)
    if kind == "frac_pct":
        # win_rate / macro_conf are stored as a 0-1 fraction (e.g. 0.446 = 44.6%),
        # unlike iv_percentile/hv_percentile/vlm_3m_pct which are already 0-100.
        try:
            return f"{float(v) * 100:.1f}%"
        except (TypeError, ValueError):
            return str(v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.4g}"
    return str(v)


class Tree:
    """Minimal hierarchical console printer (box-drawing tree)."""

    def __init__(self):
        self.lines: list[str] = []

    def section(self, title: str):
        self.lines.append("")
        self.lines.append(title)

    def row(self, label: str, value: Any, kind: str = "", last: bool = False):
        branch = "`-" if last else "|-"
        self.lines.append(f"  {branch} {label}: {_fmt(value, kind)}")

    def sub(self, text_line: str, depth: int = 1, last: bool = False):
        indent = "  " * depth
        branch = "`-" if last else "|-"
        self.lines.append(f"{indent}{branch} {text_line}")

    def blank(self):
        self.lines.append("")

    def dump(self):
        print("\n".join(self.lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol", help="tos_symbol, e.g. CELH")
    ap.add_argument("--date", help="YYYY-MM-DD, default = latest available")
    args = ap.parse_args()

    row = _fetch_actionable_row(args.symbol, args.date)
    if row is None:
        raise SystemExit(f"{args.symbol.upper()} not found in /api/actionable"
                          f"{' for ' + args.date if args.date else ''}")

    t = Tree()
    sym = row.get("tos_symbol")
    t.lines.append(f"{sym} - {row.get('company_name') or row.get('description') or ''}")
    t.lines.append(f"as_of {row.get('as_of_date')} - {row.get('sector') or '?'} / "
                    f"{row.get('asset_class') or '?'} - price {_fmt(row.get('last_price'), 'usd')} "
                    f"({_fmt(row.get('net_chng'))}, {_fmt(row.get('pct_change'), 'pct')})")

    # ---- DECISION ----------------------------------------------------------
    t.section("DECISION")
    t.row("consolidated_action", row.get("consolidated_action"))
    t.row("winning_source", row.get("winning_source"))
    t.row("winning_priority", row.get("winning_priority"))
    t.row("final_action / final_code", f"{row.get('final_action')} / {row.get('final_code')}")
    t.row("final_side", row.get("final_side"))
    t.row("fc_confidence / fc_strength", f"{row.get('fc_confidence')} / {row.get('fc_strength')}")
    t.row("fc_feasible", row.get("fc_feasible"))
    t.row("trig_action", row.get("trig_action"))
    t.row("low_confidence", row.get("low_confidence"))
    t.row("suppressed_reason", row.get("suppressed_reason"), last=True)

    # ---- SIZING -------------------------------------------------------------
    t.section("SIZING")
    t.row("held_today / in_my_list", f"{_fmt(row.get('held_today'))} / {_fmt(row.get('in_my_list'))}")
    t.row("current_position_dollar", row.get("current_position_dollar"), "usd")
    t.row("suggested_target_dollar", row.get("suggested_target_dollar"), "usd")
    t.row("target_min / target_max", f"{_fmt(row.get('target_min_dollar'), 'usd')} - "
                                      f"{_fmt(row.get('target_max_dollar'), 'usd')}")
    t.row("units_dollar", row.get("units_dollar"), "usd")
    t.row("maintain_min", row.get("maintain_min"))
    t.row("position_category", row.get("position_category"))
    t.row("held_accounts", row.get("held_accounts"), last=True)

    # ---- SOURCES --------------------------------------------------------
    src = row.get("source_actions") or []
    if isinstance(src, str):
        try:
            src = json.loads(src)
        except json.JSONDecodeError:
            src = []
    t.section(f"SOURCES ({len(src)})")
    for i, s in enumerate(src):
        last = i == len(src) - 1
        t.sub(f"{s.get('source')}: {s.get('action')}, weight {_fmt(s.get('weight'))} "
              f"(d{_fmt(s.get('weight_delta'))}, prev {_fmt(s.get('prev_weight'))} "
              f"@ {_fmt(s.get('prev_date'))}) - \"{s.get('reason')}\" "
              f"[snap {_fmt(s.get('snapshot_date'))}]", last=last)
    if not src:
        t.sub("(none on file for this symbol/date)", last=True)

    # ---- TECHNICAL / RISK RANGE ------------------------------------------
    t.section("TECHNICAL / RISK RANGE")
    lrr, trr = row.get("lrr"), row.get("trr")
    pct_range = None
    try:
        if lrr is not None and trr is not None and float(trr) != float(lrr):
            pct_range = (float(row.get("last_price")) - float(lrr)) * 100.0 / (float(trr) - float(lrr))
    except (TypeError, ValueError):
        pass
    t.row("rr_action / rr_bull_bear", f"{row.get('rr_action')} / {row.get('rr_bull_bear')}")
    t.row("rr_outlook / rr_desc", f"{row.get('rr_outlook')} / {row.get('rr_desc')}")
    t.row("lrr / mrr / trr", f"{_fmt(lrr)} / {_fmt(row.get('mrr'))} / {_fmt(trr)}")
    t.row("% of range (computed)", f"{pct_range:.1f}%" if pct_range is not None else "-")
    t.row("quote_zone / quote_pct_brr / ma_pct_brr",
          f"{row.get('quote_zone')} / {_fmt(row.get('quote_pct_brr'))} / {_fmt(row.get('ma_pct_brr'))}")
    t.row("tn_td_desc", row.get("tn_td_desc"))
    t.row("stop_level / stop_signal / stop_breached",
          f"{_fmt(row.get('stop_level'), 'usd')} / {row.get('stop_signal')} / {_fmt(row.get('stop_breached'))}")
    t.row("range_compression", row.get("range_compression"))
    t.row("bb_desc", row.get("bb_desc"))
    t.row("bb_rr_drift_flag", row.get("bb_rr_drift_flag"))
    t.row("bb_rr_ape_top/bottom_med20",
          f"{_fmt(row.get('bb_rr_ape_top_med20'))} / {_fmt(row.get('bb_rr_ape_bottom_med20'))}", last=True)

    # ---- RULES ENGINE (fired composites + live scorecard) -----------------
    fires = row.get("rules_engine_fires") or []
    if isinstance(fires, str):
        try:
            fires = json.loads(fires)
        except json.JSONDecodeError:
            fires = []
    with session_scope() as s:
        scorecard = _scorecard_for(s, [f.get("rule_id") for f in fires if f.get("rule_id")])
    t.section(f"RULES ENGINE ({len(fires)} fired)")
    for i, f in enumerate(fires):
        last = i == len(fires) - 1
        rid = f.get("rule_id")
        side = _rule_side(rid)
        sc = scorecard.get(rid, {})
        line = (f"{rid}  [{side}]  score={_fmt(f.get('score'))}  "
                f"n_member_hit={_fmt(f.get('n_member_hit'))}")
        t.sub(line, last=last)
        if sc:
            t.sub(f"edge_20d={_fmt(sc.get('edge_20d'))}  win_rate={_fmt(sc.get('win_rate'), 'frac_pct')}  "
                  f"n_fires={_fmt(sc.get('n_fires'))}  confidence={sc.get('confidence')}",
                  depth=2, last=True)
        else:
            t.sub("(no scorecard row yet)", depth=2, last=True)
    if not fires:
        t.sub("(none fired today)", last=True)

    tgg = row.get("triggered_group_ids") or []
    if isinstance(tgg, str):
        try:
            tgg = json.loads(tgg)
        except json.JSONDecodeError:
            tgg = []
    if tgg:
        t.blank()
        t.lines.append("  triggered rule groups:")
        for i, g in enumerate(tgg):
            last = i == len(tgg) - 1
            t.sub(f"{g.get('rule_group_code')}  action={g.get('action')}  "
                  f"priority={g.get('priority')}  category={g.get('category')}", last=last)

    # ---- MACRO ---------------------------------------------------------
    t.section("MACRO")
    t.row("macro_value / macro_action", f"{row.get('macro_value')} / {row.get('macro_action')}")
    t.row("macro_conf / macro_conflict / macro_turn",
          f"{_fmt(row.get('macro_conf'), 'frac_pct')} / {row.get('macro_conflict')} / {row.get('macro_turn')}")
    t.row("macronet", row.get("macronet"))
    t.row("sector_stance / asset_class_stance",
          f"{row.get('sector_stance')} / {row.get('asset_class_stance')}")
    t.row("style_stances", row.get("style_stances"))
    t.row("quad_m / quad_q", f"{row.get('quad_m')} / {row.get('quad_q')}", last=True)

    # ---- PVV -------------------------------------------------------------
    t.section("PVV")
    t.row("pvv_decision", row.get("pvv_decision"))
    t.row("pvv_detail", row.get("pvv_detail"))
    t.row("d_iv_to_hv / d_vlt_caution", f"{row.get('d_iv_to_hv')} / {row.get('d_vlt_caution')}", last=True)

    # ---- VOLATILITY / MOMENTUM / VOLUME ------------------------------------
    t.section("VOLATILITY / MOMENTUM / VOLUME")
    t.row("rsi", row.get("rsi"))
    t.row("imp_volatility / hv", f"{_fmt(row.get('imp_volatility'))} / {_fmt(row.get('hv'))}")
    t.row("iv_percentile / hv_percentile",
          f"{_fmt(row.get('iv_percentile'), 'pct')} / {_fmt(row.get('hv_percentile'), 'pct')}")
    t.row("iv_ratio / iv_to_hv_discount", f"{_fmt(row.get('iv_ratio'))} / {_fmt(row.get('iv_to_hv_discount'))}")
    t.row("vlm_action / vlm_desc", f"{row.get('vlm_action')} / {row.get('vlm_desc')}")
    t.row("vlm_projected / vlm_3m_pct", f"{_fmt(row.get('vlm_projected'))} / {_fmt(row.get('vlm_3m_pct'), 'pct')}")
    t.row("rvol / rvol_prior", f"{_fmt(row.get('rvol'))} / {_fmt(row.get('rvol_prior'))}")
    t.row("volume / avg_10d / avg_3m",
          f"{_fmt(row.get('volume'))} / {_fmt(row.get('volume_avg_10d'))} / {_fmt(row.get('volume_avg_3m'))}")
    t.row("volume_rate_change / w_volume",
          f"{_fmt(row.get('volume_rate_change'))} / {_fmt(row.get('w_volume'))}")
    t.row("a_volume_spike", row.get("a_volume_spike"))
    t.row("a_macd_brr / a_macdh_d_brr", f"{row.get('a_macd_brr')} / {row.get('a_macdh_d_brr')}", last=True)

    # ---- CONVICTION / WARNINGS ---------------------------------------------
    t.section("CONVICTION / WARNINGS")
    t.row("conviction_hold / direction", f"{row.get('conviction_hold')} / {row.get('conviction_direction')}")
    t.row("conviction_note", row.get("conviction_note"))
    t.row("conviction_target_date", row.get("conviction_target_date"))
    t.row("warn_not_at_lrr / warn_added_this_leg",
          f"{_fmt(row.get('warn_not_at_lrr'))} / {_fmt(row.get('warn_added_this_leg'))}")
    t.row("earnings_days", row.get("earnings_days"), last=True)

    # ---- MODEL / FORECAST (mostly inactive per project notes) --------------
    t.section("MODEL / FORECAST")
    t.row("bull_prob / bull_agreement / agreement_class",
          f"{_fmt(row.get('bull_prob'))} / {_fmt(row.get('bull_agreement'))} / {row.get('agreement_class')}")
    t.row("monthly_score", row.get("monthly_score"))
    t.row("month_now_net / month_next_net / month_weight",
          f"{_fmt(row.get('month_now_net'))} / {_fmt(row.get('month_next_net'))} / {_fmt(row.get('month_weight'))}")
    t.row("quarterly_score", row.get("quarterly_score"))
    t.row("qtr_now_net / qtr_next_net / qtr_weight",
          f"{_fmt(row.get('qtr_now_net'))} / {_fmt(row.get('qtr_next_net'))} / {_fmt(row.get('qtr_weight'))}",
          last=True)

    # ---- CHANGE EVENTS ----------------------------------------------------
    t.section("CHANGE EVENTS")
    t.row("etfchg (date/outlook/desc)",
          f"{row.get('etfchg_date')} / {row.get('etfchg_outlook')} / {row.get('etfchg_desc')}")
    t.row("iichg (date/outlook/desc)",
          f"{row.get('iichg_date')} / {row.get('iichg_outlook')} / {row.get('iichg_desc')}", last=True)

    # ---- META ---------------------------------------------------------
    t.section("META")
    t.row("computed_at / source_run_id", f"{row.get('computed_at')} / {row.get('source_run_id')}")
    t.row("export_date / export_time / loaded_at",
          f"{row.get('export_date')} / {row.get('export_time')} / {row.get('loaded_at')}")
    t.row("quote_source / quote_is_intraday", f"{row.get('quote_source')} / {row.get('quote_is_intraday')}")
    t.row("open/high/low", f"{_fmt(row.get('open_price'), 'usd')} / {_fmt(row.get('high_price'), 'usd')} / "
                            f"{_fmt(row.get('low_price'), 'usd')}")
    t.row("last_user_action / snooze_until", f"{row.get('last_user_action')} / {row.get('snooze_until')}")
    t.row("priority_rank", row.get("priority_rank"), last=True)

    t.dump()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
