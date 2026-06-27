"""
Deterministic, no-LLM parsers for each Hedgeye email type.

Every parser is a pure function ``parse(email: Email) -> Parsed`` operating on the
already-fetched message. No DB, no network — so they are trivially unit-tested
against saved samples (tests/test_hedgeye_parsers.py).

A parser returns a ``Parsed`` with:
  - tables  : {table_name: [row_dict, ...]}  -> DATA lane (insert_skip_duplicates)
  - notes   : [note_dict, ...]               -> note_repo (ANALYSIS / RULES lanes)
  - images  : [url, ...]                      -> archive to configurable folder
  - warnings: [str, ...]                      -> logged; e.g. RR trend-change QA mismatch
  - flags   : [str, ...]                      -> e.g. "correction", "quarterly_rule_review"

Decisions encoded here come from docs/hedgeye_feeds_design.md (Decision log).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Email container + result
# ---------------------------------------------------------------------------


@dataclass
class Email:
    message_id: str
    subject: str
    sender: str
    received: datetime           # delivery datetime (UTC ok)
    plaintext: str               # plaintextBody
    html: str = ""               # htmlBody (optional; needed for tables/images)

    # convenience -------------------------------------------------------------
    @property
    def edt_date(self) -> Optional[date]:
        """Date stamped inside the email body header (MM/DD/YYYY ... EDT)."""
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+\d{1,2}:\d{2}\s*[AP]M", self.plaintext)
        if m:
            mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(yy, mm, dd)
        return self.received.date() if self.received else None

    @property
    def meta_symbols(self) -> list[str]:
        m = re.search(r'hedgeye-stock-symbols"\s+content="([^"]*)"', self.html)
        if not m or not m.group(1).strip():
            return []
        return [s.strip().upper() for s in m.group(1).split(",") if s.strip()]

    @property
    def header_asset(self) -> str:
        """The header banner image filename, e.g. 'stock_alerts_800px.png'."""
        m = re.search(r"email_assets/headers/sectors/([a-z0-9_]+_800px\.png)", self.html)
        return m.group(1) if m else ""


@dataclass
class Parsed:
    email_type: str
    tables: dict[str, list[dict]] = field(default_factory=dict)
    notes: list[dict] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def add_rows(self, table: str, rows: list[dict]) -> None:
        if rows:
            self.tables.setdefault(table, []).extend(rows)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_QUAD = re.compile(r"#?Quad\s*([1-4])", re.I)
_TICKER_PAREN = re.compile(r"\(([A-Z][A-Z0-9.\-/]{0,9})\)")


def _num(tok: str) -> Optional[float]:
    tok = tok.strip().strip("#").replace(",", "")
    if not tok:
        return None
    try:
        return float(tok)
    except ValueError:
        return None


def _body_lines(text: str) -> list[str]:
    """Plaintext lines with the boilerplate header/footer trimmed."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("This research was prepared") or s.startswith("Having trouble"):
            continue
        if s.startswith("If you believe this has been sent") or s.startswith("© 20"):
            continue
        if s.startswith("Please visit https://") or s.startswith("<https://"):
            continue
        out.append(s)
    return out


def _quad(text: str) -> Optional[int]:
    m = _QUAD.search(text)
    return int(m.group(1)) if m else None


def _chart_image_urls(html: str) -> list[str]:
    return re.findall(r'img class="chart"\s+src="([^"]+)"', html)


def _note(email: Email, source_type: str, text: str, *, tickers=None,
          quad=None, theme_tags=None, analyst=None, signal_kind=None) -> dict:
    return {
        "message_id": email.message_id,
        "note_date": email.edt_date,
        "source_type": source_type,
        "gmail_link": f"https://mail.google.com/mail/u/0/#all/{email.message_id}",
        "analyst": analyst,
        "tickers": tickers or [],
        "theme_tags": theme_tags or [],
        "quad": quad if quad is not None else _quad(text),
        "signal_kind": signal_kind,
        "note_text": text.strip()[:4000],
        "status": "new",
        "subject": email.subject,
    }


class _TableExtractor(HTMLParser):
    """Collect HTML <table> structures as list-of-rows-of-cell-text."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            self.tables.append([])
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._depth:
            self._depth -= 1
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _html_tables(html: str) -> list[list[list[str]]]:
    p = _TableExtractor()
    try:
        p.feed(html or "")
    except Exception:
        return []
    return p.tables


# ---------------------------------------------------------------------------
# 1) Risk Range Signals -> hist_rr  (full 38-row table)
# ---------------------------------------------------------------------------

_RR_HEAD = re.compile(r"^(\S.*?)\s+\((BULLISH|BEARISH|NEUTRAL)\)$")
_RR_CHANGE = re.compile(
    r"^(\S+)\s+changed from (Bullish|Bearish|Neutral) to (Bullish|Bearish|Neutral)$", re.I)


def parse_risk_range(email: Email) -> Parsed:
    p = Parsed("risk_range")
    lines = _body_lines(email.plaintext)
    d = email.edt_date

    # cut at the OutBucket section
    body = []
    for ln in lines:
        if "#OUTBUCKET" in ln.upper() or ln.upper().startswith("THE #OUTBUCKET"):
            ln = ln.split("#OUTBUCKET")[0].strip()
            if ln:
                body.append(ln)
            break
        body.append(ln)

    # printed TREND CHANGE block -> transient QA only (not stored)
    printed_changes = {}
    for ln in body:
        m = _RR_CHANGE.match(ln)
        if m:
            printed_changes[m.group(1).upper()] = (m.group(2).title(), m.group(3).title())

    rows = []
    i = 0
    while i < len(body) - 1:
        m = _RR_HEAD.match(body[i])
        if m:
            sym = m.group(1).strip().upper()
            outlook = m.group(2).upper()
            nxt = body[i + 1]
            nums = [t for t in nxt.split() if _NUM.match(t.replace("#", ""))]
            if len(nums) >= 3:
                buy, sell, prev = (_num(nums[-3]), _num(nums[-2]), _num(nums[-1]))
                rows.append({
                    "snapshot_date": d, "market_close": d,
                    "symbol": sym, "tos_symbol": sym, "name": None,
                    "outlook": outlook, "buy_trade": buy, "sell_trade": sell,
                    "last_price": prev,
                })
                i += 2
                continue
        i += 1

    p.add_rows("hist_rr", rows)
    p.flags.append(f"rr_rows={len(rows)}")
    if printed_changes:
        # QA cross-check happens at dispatch time vs drv_rr_trend_change; transient
        p.warnings.append(f"trend_change_printed={len(printed_changes)} (QA only, not stored)")
    return p


# ---------------------------------------------------------------------------
# 2) Real-Time Alert -> hist_rta  (+ coaching note); corrections auto-reverse
# ---------------------------------------------------------------------------

_RTA_HEAD = re.compile(
    r"(?:^|\b)(BUY|SELL|COVER|SHORT)[\s\-]*(?:SIGNAL)?\b.*?\b([A-Z][A-Z0-9.\-]{0,9})\s+\$?([\d,]+\.?\d*)",
)
_RTA_SUBJ = re.compile(
    r"Real-Time Alert:\s*(?P<rest>.*)", re.I)
_CORRECTION_HINTS = ("fat finger", "my mistake", "read the next", "disregard", "ignore the")


def parse_real_time_alert(email: Email) -> Parsed:
    p = Parsed("real_time_alert")
    subj = email.subject
    low = (subj + " " + email.plaintext[:400]).lower()

    # correction / retraction: no actionable signal -> flag, do NOT fabricate a trade
    if any(h in low for h in _CORRECTION_HINTS):
        p.flags.append("correction")
        p.add_rows("hist_rta", [{
            "message_id": email.message_id, "alert_ts": email.received,
            "is_correction": True, "raw_subject": subj, "tos_symbol": None,
            "snapshot_date": email.edt_date,
        }])
        return p

    # subject: **Real-Time Alert: <Analyst> <Kind> Signal (<note>): <Name> (TICKER) -KM
    analyst = signal_kind = None
    ms = _RTA_SUBJ.search(subj)
    if ms:
        rest = ms.group("rest")
        mk = re.match(r"(?P<analyst>[A-Za-z .'/-]+?)\s+(?P<kind>(Buy|Sell|Cover|Sell-SOME|"
                      r"Cover-SOME|Macro[\w\- ]*))\s+Signal", rest, re.I)
        if mk:
            analyst = mk.group("analyst").strip()
            signal_kind = mk.group("kind").strip()

    # body headline: e.g. "SELL SIGNAL - SHORTING ROP $339.80"
    head_line = ""
    for ln in _body_lines(email.plaintext):
        if "SIGNAL" in ln.upper() and "$" in ln:
            head_line = ln
            break
    action = side = symbol = price = None
    mh = _RTA_HEAD.search(head_line.upper())
    if mh:
        action = mh.group(1)
        symbol = mh.group(2)
        price = _num(mh.group(3))
        side = "short" if action in ("SHORT", "COVER") else "long"
    if not symbol and email.meta_symbols:
        symbol = email.meta_symbols[0]

    # durations row: "trade trend tail" (active = present in body durations line)
    durations = {"trade": False, "trend": False, "tail": False}
    bl = _body_lines(email.plaintext)
    for idx, ln in enumerate(bl):
        if ln.lower() == "durations" and idx + 1 < len(bl):
            for k in durations:
                durations[k] = k in bl[idx + 1].lower()

    # coaching notes (ordered list after "Coaching Notes:")
    coaching = []
    grab = False
    for ln in bl:
        if ln.lower().startswith("coaching notes"):
            grab = True
            continue
        if grab:
            if ln in ("KM", "-KM") or ln.lower().startswith("please visit"):
                break
            coaching.append(ln)
    coaching_text = " | ".join(coaching)

    p.add_rows("hist_rta", [{
        "message_id": email.message_id, "alert_ts": email.received,
        "snapshot_date": email.edt_date, "is_correction": False,
        "analyst": analyst, "signal_kind": signal_kind,
        "action": action, "side": side,
        "symbol": symbol, "tos_symbol": symbol, "price": price,
        "dur_trade": durations["trade"], "dur_trend": durations["trend"],
        "dur_tail": durations["tail"], "coaching_notes": coaching_text or None,
        "raw_subject": subj,
    }])
    if coaching_text:
        p.notes.append(_note(email, "rta_coaching", coaching_text,
                             tickers=[symbol] if symbol else [], analyst=analyst,
                             signal_kind=signal_kind))
    return p


# ---------------------------------------------------------------------------
# 3) Investing Ideas Add/Remove -> hist_iichg (+ hist_ii state)
# ---------------------------------------------------------------------------

_II_SUBJ = re.compile(r"^(Add|Remove)\b.*?\bto?\s*(LONG|SHORT)\s*Side", re.I)


def parse_investing_ideas(email: Email) -> Parsed:
    p = Parsed("investing_ideas")
    subj = email.subject
    action = side = None
    ms = _II_SUBJ.search(subj)
    if ms:
        action = ms.group(1).lower()
        side = ms.group(2).lower()
    else:
        if re.match(r"^\s*Remove", subj, re.I):
            action = "remove"
        elif re.match(r"^\s*Add", subj, re.I):
            action = "add"
        m2 = re.search(r"\b(LONG|SHORT)\b", subj, re.I)
        if m2:
            side = m2.group(1).lower()

    # body confirms side via "Short:" / "Long:" headers; ticker from meta or subject
    if side is None:
        if re.search(r"\bShort:\b", email.plaintext):
            side = "short"
        elif re.search(r"\bLong:\b", email.plaintext):
            side = "long"

    symbols = email.meta_symbols
    if not symbols:
        m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", subj)
        if m:
            symbols = [m.group(1)]
    rows = [{
        "snapshot_date": email.edt_date, "message_id": email.message_id,
        "action": action, "side": side, "symbol": s, "tos_symbol": s,
    } for s in symbols]
    p.add_rows("hist_iichg", rows)
    return p


# ---------------------------------------------------------------------------
# 4) ETF Pro changes -> hist_etfchg  (add/remove only, no ranges)
# ---------------------------------------------------------------------------

_ETF_BLOCK = re.compile(r"We are (ADDING|REMOVING)\s+(Long|Short)", re.I)


def parse_etf_changes(email: Email) -> Parsed:
    p = Parsed("etf_changes")
    rows = []
    lines = _body_lines(email.plaintext)
    cur_action = cur_side = None
    for ln in lines:
        mb = _ETF_BLOCK.search(ln)
        if mb:
            cur_action = "add" if mb.group(1).upper() == "ADDING" else "remove"
            cur_side = mb.group(2).lower()
            continue
        if "How to Use" in ln:        # the explanatory block; stop collecting
            cur_action = cur_side = None
            continue
        if cur_action:
            m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", ln)
            if m:
                rows.append({
                    "snapshot_date": email.edt_date, "message_id": email.message_id,
                    "action": cur_action, "side": cur_side,
                    "symbol": m.group(1), "tos_symbol": m.group(1),
                })
    p.add_rows("hist_etfchg", rows)
    return p


# ---------------------------------------------------------------------------
# 5) Signal Strength Stocks -> hist_sss  (delta events only)
# ---------------------------------------------------------------------------


def parse_signal_strength(email: Email) -> Parsed:
    p = Parsed("signal_strength")
    rows = []
    for ln in _body_lines(email.plaintext):
        m = re.match(r"^(Added|Removed):\s*(.+)$", ln, re.I)
        if m:
            action = "add" if m.group(1).lower() == "added" else "remove"
            for sym in re.split(r"[,\s]+", m.group(2).strip()):
                sym = sym.strip().upper()
                if sym:
                    rows.append({
                        "snapshot_date": email.edt_date, "message_id": email.message_id,
                        "action": action, "symbol": sym, "tos_symbol": sym,
                    })
    p.add_rows("hist_sss_change", rows)
    p.flags.append("delta_only")
    return p


# ---------------------------------------------------------------------------
# 6) Portfolio Solutions weekly re-rank -> hist_ps  (full table from HTML)
# ---------------------------------------------------------------------------


def parse_portfolio_solutions(email: Email) -> Parsed:
    p = Parsed("portfolio_solutions")
    rows = []
    for tbl in _html_tables(email.html):
        if not tbl:
            continue
        header = [c.lower() for c in tbl[0]]
        if "rank" in header and "ticker" in header:
            idx = {name: header.index(name) for name in header}
            r_i = idx.get("rank"); t_i = idx.get("ticker")
            for cells in tbl[1:]:
                if len(cells) <= max(r_i, t_i):
                    continue
                rank = _num(cells[r_i])
                tick = cells[t_i].strip().upper()
                if tick and rank is not None:
                    rows.append({
                        "snapshot_date": email.edt_date, "message_id": email.message_id,
                        "rank": int(rank), "ticker": tick, "tos_symbol": tick,
                    })
            break
    p.add_rows("hist_ps", rows)
    if not rows:
        p.warnings.append("PS: no HTML rank table found")
    return p


# ---------------------------------------------------------------------------
# 7) Macro Show — Summary Notes -> hist_hedgeye_stance (+ note)
# ---------------------------------------------------------------------------

# minimal name->symbol map for non-ticker positions; extend in ref/config
STANCE_NAME_MAP = {
    "japan": "EWJ", "south korea": "EWY", "kospi": "EWY", "nasdaq": "QQQ",
    "bitcoin": "BTC", "commodities": "DBC", "gold": "GLD", "copper": "CPER",
    "germany": "EWG", "norway": "NORW", "malaysia": "EWM", "indonesia": "EIDO",
    "philippines": "EPHE", "israel": "EIS",
}


def _stance_items(segment: str) -> list[tuple[Optional[str], str]]:
    out = []
    for raw in segment.split(","):
        raw = raw.strip()
        if not raw:
            continue
        m = _TICKER_PAREN.search(raw)
        if m:
            out.append((m.group(1).upper(), raw))
        else:
            key = re.sub(r"[^a-z /]", "", raw.lower()).strip()
            sym = None
            for k, v in STANCE_NAME_MAP.items():
                if k in key:
                    sym = v
                    break
            out.append((sym, raw))
    return out


def parse_macro_show_summary(email: Email) -> Parsed:
    p = Parsed("macro_show_summary")
    text = email.plaintext
    rows = []
    for stance, pat in (("BULLISH", r"BULLISH:\s*(.+)"), ("BEARISH", r"BEARISH:\s*(.+)")):
        m = re.search(pat, text)
        if m:
            seg = m.group(1).splitlines()[0]
            for sym, label in _stance_items(seg):
                rows.append({
                    "snapshot_date": email.edt_date, "message_id": email.message_id,
                    "stance": stance, "symbol": sym, "tos_symbol": sym,
                    "label": label[:120],
                })
    p.add_rows("hist_hedgeye_stance", rows)

    # main summary snippet -> note
    snippet = ""
    m = re.search(r"MAIN SUMMARY\s*(.+)", text, re.S)
    if m:
        snippet = re.sub(r"\s+", " ", m.group(1))[:1500]
    p.notes.append(_note(email, "macro_show", snippet or email.subject,
                         tickers=[r["tos_symbol"] for r in rows if r["tos_symbol"]]))
    return p


# ---------------------------------------------------------------------------
# 8) The Call (Replay & Summary) -> hist_call (positions) + hist_call_top5
# ---------------------------------------------------------------------------


def parse_the_call(email: Email) -> Parsed:
    p = Parsed("the_call")
    text = email.plaintext

    # HEDGEYE POSITIONS: LONGS / SHORTS / NEUTRAL lines
    side_for = {}
    pos_rows = []
    for label, outlook in (("LONGS", "long"), ("SHORTS", "short"), ("NEUTRAL", "neutral")):
        m = re.search(rf"{label}:\s*(.+)", text)
        if m:
            for sym in re.split(r"[,\s]+", m.group(1).splitlines()[0].strip()):
                sym = sym.strip().upper()
                if re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", sym):
                    pos_rows.append({
                        "snapshot_date": email.edt_date, "message_id": email.message_id,
                        "symbol": sym, "tos_symbol": sym, "outlook": outlook,
                    })
                    side_for[sym] = outlook
    p.add_rows("hist_call", pos_rows)

    # Top 5 Most Actionable Stock Ideas: "Name (TICKER): rationale …"
    top_rows = []
    m = re.search(r"Top 5 Most Actionable Stock Ideas(.+)", text, re.S)
    if m:
        seg = m.group(1)
        marks = list(re.finditer(r"\(([A-Z][A-Z0-9.\-]{0,9})\):\s*", seg))
        for rank, mt in enumerate(marks[:5], 1):
            sym = mt.group(1).upper()
            start = mt.end()
            end = marks[rank].start() if rank < len(marks) else len(seg)
            rationale = re.sub(r"\s+", " ", seg[start:end]).strip()
            # drop a trailing next-idea name fragment if present
            rationale = re.split(r"\s+[A-Z][\w.&,'’ -]+\($", rationale)[0]
            top_rows.append({
                "snapshot_date": email.edt_date, "message_id": email.message_id,
                "rank": rank, "symbol": sym, "tos_symbol": sym,
                "side": side_for.get(sym, "long"),
                "rationale_snippet": rationale[:400],
            })
    p.add_rows("hist_call_top5", top_rows)
    return p


# ---------------------------------------------------------------------------
# 9) Early Look -> note_repo (Key Takeaways)
# ---------------------------------------------------------------------------


def parse_early_look(email: Email) -> Parsed:
    p = Parsed("early_look")
    text = email.plaintext
    take = ""
    m = re.search(r"Key Takeaways\s*(.+?)(?:The Big Picture|$)", text, re.S)
    if m:
        take = re.sub(r"\s+", " ", m.group(1)).strip()[:2000]
    tickers = sorted(set(_TICKER_PAREN.findall(text)))[:20] or email.meta_symbols
    q = _quad(email.subject + " " + text)
    p.notes.append(_note(email, "early_look", take or email.subject, tickers=tickers, quad=q))
    return p


# ---------------------------------------------------------------------------
# 10) Market Situation Report -> note + archive chart images
# ---------------------------------------------------------------------------


def parse_market_situation(email: Email) -> Parsed:
    p = Parsed("market_situation")
    # first substantive prose paragraph + author line
    paras = [ln for ln in _body_lines(email.plaintext)
             if len(ln) > 60 and "VIEW LARGER IMAGE" not in ln and "Click Here" not in ln]
    snippet = " ".join(paras[:3])[:1500]
    author = None
    ma = re.search(r"-\s*([A-Z][a-z]+ [A-Z][a-z]+)\s*$", email.plaintext.strip())
    if ma:
        author = ma.group(1)
    p.notes.append(_note(email, "market_situation", snippet or email.subject,
                         analyst=author, theme_tags=["dealer_positioning", "gamma"]))
    p.images = _chart_image_urls(email.html)
    return p


# ---------------------------------------------------------------------------
# 11) Monthly Inflation Nowcast -> macro series (+ note)
# ---------------------------------------------------------------------------


def parse_inflation_nowcast(email: Email) -> Parsed:
    p = Parsed("inflation_nowcast")
    text = email.plaintext
    m = re.search(r"nowcast for (\w+) is\s*([+-]?\d+\.?\d*)%\s*y/y", text, re.I)
    bp = re.search(r"([+-]?\d+)\s*bp\s+sequential", text, re.I)
    cpi = re.search(r"CPI Release Date:\s*([A-Za-z]+ \d{1,2})", text)
    value = _num(m.group(2)) if m else None
    seq_bp = _num(bp.group(1)) if bp else None
    direction = None
    if seq_bp is not None:
        direction = "accelerating" if seq_bp > 0 else "decelerating"
    if value is not None:
        p.add_rows("hist_macro", [{
            "series_id": "HE_CPI_NOWCAST", "obs_date": email.edt_date,
            "value": value, "message_id": email.message_id,
        }])
    p.notes.append(_note(
        email, "inflation", f"CPI nowcast {value}% y/y, {seq_bp} bp ({direction}); "
        f"CPI release {cpi.group(1) if cpi else '?'}", theme_tags=["inflation", direction or ""]))
    return p


# ---------------------------------------------------------------------------
# 12) Quarterly Investment Outlook -> note + quarterly_rule_review flag
# ---------------------------------------------------------------------------


def parse_quarterly_outlook(email: Email) -> Parsed:
    p = Parsed("quarterly_outlook")
    p.flags.append("quarterly_rule_review")
    p.notes.append(_note(email, "quarterly_outlook",
                         email.subject, quad=_quad(email.subject + " " + email.plaintext),
                         theme_tags=["quad", "regime"]))
    return p


# ---------------------------------------------------------------------------
# Registry: email_type -> parser
# ---------------------------------------------------------------------------

PARSERS: dict[str, Callable[[Email], Parsed]] = {
    "risk_range": parse_risk_range,
    "real_time_alert": parse_real_time_alert,
    "investing_ideas": parse_investing_ideas,
    "etf_changes": parse_etf_changes,
    "signal_strength": parse_signal_strength,
    "portfolio_solutions": parse_portfolio_solutions,
    "macro_show_summary": parse_macro_show_summary,
    "the_call": parse_the_call,
    "early_look": parse_early_look,
    "market_situation": parse_market_situation,
    "inflation_nowcast": parse_inflation_nowcast,
    "quarterly_outlook": parse_quarterly_outlook,
}
