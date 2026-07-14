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
# OutBucket section line: "Description (SYMBOL) = Bullish|Bearish|Neutral (date)"
_RR_OB_LINE = re.compile(
    r"^(.+?)\s+\(([A-Z][A-Z0-9./\-]{0,15})\)\s*=\s*(Bullish|Bearish|Neutral)",
    re.I,
)


def _parse_desc_prices(line: str):
    """Split 'Desc text 7,266 7,594 7,365' into (desc_str_or_None, [f,f,f]).

    Finds the last 3 numeric tokens and returns everything before them as the
    description.  Handles cases where the description itself contains numbers
    (e.g. 'S&P 500 7,266 7,568 7,357' → desc='S&P 500').
    """
    tokens = line.split()
    num_positions = [i for i, t in enumerate(tokens) if _NUM.match(t.replace("#", ""))]
    if len(num_positions) < 3:
        return None, []
    last3 = num_positions[-3:]
    prices = [_num(tokens[p]) for p in last3]
    desc = " ".join(tokens[: last3[0]]).strip() or None
    return desc, prices


def parse_risk_range(email: Email) -> Parsed:
    p = Parsed("risk_range")
    lines = _body_lines(email.plaintext)
    d = email.edt_date

    # Split body at the OutBucket explanatory section separator.
    # Lines before the separator: main signal table.
    # Lines after: OutBucket roster ("Description (SYM) = Outlook (date)").
    # Do NOT break early — we need the OutBucket section to get those symbols.
    # Strip the inline "#OUTBUCKET" tag from main-section price rows.
    body: list[str] = []
    outbucket_lines: list[str] = []
    in_outbucket = False
    for ln in lines:
        upper = ln.upper()
        if re.match(r"THE\s+#OUTBUCKET\s+ARE\s+THE\s+TICKERS", upper):
            in_outbucket = True
            continue
        if in_outbucket:
            outbucket_lines.append(ln)
            continue
        # main section: strip inline #OUTBUCKET tag from price lines
        if "#OUTBUCKET" in upper:
            ln = re.split(r"\s*#OUTBUCKET\b", ln, flags=re.I)[0].strip()
        if ln:
            body.append(ln)

    # printed TREND CHANGE block -> transient QA only (not stored)
    printed_changes = {}
    for ln in body:
        m = _RR_CHANGE.match(ln)
        if m:
            printed_changes[m.group(1).upper()] = (m.group(2).title(), m.group(3).title())

    rows = []

    # --- Main signal section: SYMBOL (OUTLOOK) / Description BUY SELL PREV ---
    i = 0
    while i < len(body) - 1:
        m = _RR_HEAD.match(body[i])
        if m:
            sym = m.group(1).strip().upper()
            outlook = m.group(2).upper()
            nxt = body[i + 1]
            desc, prices = _parse_desc_prices(nxt)
            if len(prices) >= 3:
                buy, sell, prev = prices[-3], prices[-2], prices[-1]
                rows.append({
                    "snapshot_date": d, "market_close": d,
                    "symbol": sym, "tos_symbol": sym, "name": desc,
                    "outlook": outlook, "buy_trade": buy, "sell_trade": sell,
                    "last_price": prev,
                })
                i += 2
                continue
        i += 1

    # --- OutBucket section: "Description (SYMBOL) = Outlook (date)" ---
    # These symbols have no price targets; emit zeros so they appear in the
    # output with their Description and Outlook populated.
    for ln in outbucket_lines:
        m = _RR_OB_LINE.match(ln)
        if m:
            desc = m.group(1).strip()
            sym = m.group(2).strip().upper()
            outlook = m.group(3).upper()
            rows.append({
                "snapshot_date": d, "market_close": d,
                "symbol": sym, "tos_symbol": sym, "name": desc,
                "outlook": outlook, "buy_trade": 0, "sell_trade": 0,
                "last_price": 0,
            })

    p.add_rows("hist_rr", rows)
    p.flags.append(f"rr_rows={len(rows)}")
    if printed_changes:
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
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(Inc|Incorporated|Corp|Corporation|Co|Company|Ltd|LLC|L\.P\.|LP|plc|N\.V\.|SA|AG)\.?$", re.I)


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
    bl = _body_lines(email.plaintext)
    head_line = ""
    head_idx = -1
    for idx, ln in enumerate(bl):
        if "SIGNAL" in ln.upper() and "$" in ln:
            head_line = ln
            head_idx = idx
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
    for idx, ln in enumerate(bl):
        if ln.lower() == "durations" and idx + 1 < len(bl):
            for k in durations:
                durations[k] = k in bl[idx + 1].lower()

    # intro prose between the headline and "Coaching Notes:", e.g.
    # "Looking for Longs with the VIX back in what we call The Investable
    # Bucket?" — skip a leading company-name line ("United Rentals Inc.").
    intro = []
    if head_idx >= 0:
        for ln in bl[head_idx + 1:]:
            if ln.lower().startswith("coaching notes"):
                break
            intro.append(ln)
        if intro and _COMPANY_SUFFIX_RE.search(intro[0]):
            intro = intro[1:]
    intro_text = " ".join(intro)

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
    coaching_text = " | ".join(([intro_text] if intro_text else []) + coaching)

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

_II_BLOCK_RE = re.compile(r"\b(ADDING|REMOVED|REMOVING)\b", re.I)
_II_SIDE_LINE_RE = re.compile(r"^(Long|Short)\s*:\s*$", re.I)
_II_STOP_RE = re.compile(r"Commentary from Real[- ]?Time[- ]?Alerts|Coaching Notes\s*:|How to Use", re.I)
_II_TICKER_LINE_RE = re.compile(r"^([A-Z][A-Z0-9.\-]{0,9})(?:\s*\([^)]*\))?$")
_II_DESC_RE = re.compile(r"(?:Add|Remove)\s+(.+?)\s*\(([A-Z][A-Z0-9.\-]{0,9})\)", re.I)


def parse_investing_ideas(email: Email) -> Parsed:
    """Body-driven, mirrors parse_etf_changes: tracks the current ADDING/REMOVED(ING)
    + Long/Short block state per line, so multi-symbol/multi-action emails (e.g.
    "3 Changes: Remove ROP, RBLX, Add Short PSKY") get each symbol's own action/side
    instead of one subject-derived action applied to every symbol in the email."""
    p = Parsed("investing_ideas")
    rows: list[dict] = []
    cur_action = cur_side = None
    for ln in _body_lines(email.plaintext):
        if _II_STOP_RE.search(ln):
            cur_action = cur_side = None
            continue
        mb = _II_BLOCK_RE.search(ln)
        if mb:
            cur_action = "add" if mb.group(1).upper() == "ADDING" else "remove"
            cur_side = None
            continue
        ms = _II_SIDE_LINE_RE.match(ln)
        if ms:
            cur_side = ms.group(1).lower()
            continue
        if cur_action and cur_side:
            mt = _II_TICKER_LINE_RE.match(ln)
            if mt:
                sym = mt.group(1)
                rows.append({
                    "snapshot_date": email.edt_date, "message_id": email.message_id,
                    "action": cur_action, "side": cur_side,
                    "symbol": sym, "tos_symbol": sym,
                    "description": None,
                })

    # Single-symbol emails carry a clean company name in the subject between
    # Add/Remove and (TICKER) — attach it. Skipped for multi-symbol emails
    # since one subject line can't describe several different tickers.
    if len(rows) == 1:
        m_desc = _II_DESC_RE.search(email.subject)
        if m_desc:
            rows[0]["description"] = m_desc.group(1).strip() or None

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
                desc = ln[:m.start()].strip() or None
                rows.append({
                    "snapshot_date": email.edt_date, "message_id": email.message_id,
                    "action": cur_action, "side": cur_side,
                    "symbol": m.group(1), "tos_symbol": m.group(1),
                    "description": desc,
                })
    p.add_rows("hist_etfchg", rows)
    return p


# ---------------------------------------------------------------------------
# 4b) ETF Pro Plus weekly report -> hist_etf (via FILE_LANES)
# ---------------------------------------------------------------------------

def _strip_dollar(val: str) -> Optional[float]:
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _parse_mdy(val: str) -> Optional[date]:
    try:
        return datetime.strptime(val.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def parse_etf_weekly(email: Email) -> Parsed:
    """ETF Pro Plus – New Weekly Report → hist_etf via file.

    HTML Table layout (col indices, 0-based):
      0=Description  1=Ticker  2=DateAdded  3=RecentPrice
      4=TrendLow(BRR)  5=TrendHigh(TRR)  6=AssetClass
    Section-header rows mid-table have col[1]=='TICKER' and col[0] in
    ('BULLISH','BEARISH') — used to track current outlook.
    """
    p = Parsed("etf_weekly")
    rows: list[dict] = []
    for tbl in _html_tables(email.html):
        if not tbl or len(tbl[0]) < 2:
            continue
        if tbl[0][1].strip().upper() != "TICKER":
            continue
        if tbl[0][0].strip().upper() not in ("BULLISH", "BEARISH"):
            continue

        current_outlook = tbl[0][0].strip().upper()
        # Opening section-header row (drives load_etf outlook tracking)
        rows.append({
            "snapshot_date": email.edt_date, "message_id": email.message_id,
            "symbol": None, "tos_symbol": None,
            "sector": current_outlook, "outlook": current_outlook,
            "date_added": None, "recent_price": None,
            "brr": None, "trr": None, "asset_class": None,
        })
        for cells in tbl[1:]:
            if len(cells) < 2:
                continue
            if cells[1].strip().upper() == "TICKER":
                # Mid-table section-header (BEARISH block)
                current_outlook = cells[0].strip().upper()
                rows.append({
                    "snapshot_date": email.edt_date, "message_id": email.message_id,
                    "symbol": None, "tos_symbol": None,
                    "sector": current_outlook, "outlook": current_outlook,
                    "date_added": None, "recent_price": None,
                    "brr": None, "trr": None, "asset_class": None,
                })
                continue
            if len(cells) < 7:
                continue
            ticker = cells[1].strip().upper()
            if not ticker:
                continue
            rows.append({
                "snapshot_date": email.edt_date, "message_id": email.message_id,
                "symbol": ticker, "tos_symbol": ticker,
                "sector": cells[0].strip() or None,
                "outlook": current_outlook,
                "date_added": _parse_mdy(cells[2]),
                "recent_price": _strip_dollar(cells[3]),
                "brr": _strip_dollar(cells[4]),
                "trr": _strip_dollar(cells[5]),
                "asset_class": cells[6].strip() or None,
            })
        break

    p.add_rows("hist_etf", rows)
    if not rows:
        p.warnings.append("ETF weekly: no table found")
    return p


# ---------------------------------------------------------------------------
# 4c) Investing Ideas Newsletter -> hist_ii (file) + per-stock notes
# ---------------------------------------------------------------------------

def parse_ii_weekly(email: Email) -> Parsed:
    """Investing Ideas Newsletter → two outputs:

    1. hist_ii rows (via FILE_LANES → II YYYY-MM-DD.xlsx):
       Parsed from 'Long: X, Y' / 'Short: A, B' lines at the top.

    2. note_repo rows (direct insert via dispatch):
       One note per ticker from the per-stock analysis blocks:
       TICKER / Sector / Sector Head / THESIS SUMMARY / WEEKEND UPDATE.
    """
    p = Parsed("ii_weekly")
    lines = _body_lines(email.plaintext)

    # --- Part 1: full position list ---
    long_tickers: list[str] = []
    short_tickers: list[str] = []
    for ln in lines:
        s = ln.strip()
        sl = s.lower()
        if sl.startswith("long:"):
            long_tickers = [t.strip().upper() for t in s[5:].split(",") if t.strip()]
        elif sl.startswith("short:"):
            short_tickers = [t.strip().upper() for t in s[6:].split(",") if t.strip()]

    if not long_tickers and not short_tickers:
        p.warnings.append("ii_weekly: no Long/Short lines found")
        return p

    ii_rows: list[dict] = []
    for tick in long_tickers:
        ii_rows.append({"snapshot_date": email.edt_date, "message_id": email.message_id,
                        "symbol": tick, "tos_symbol": tick, "outlook": "Long"})
    for tick in short_tickers:
        ii_rows.append({"snapshot_date": email.edt_date, "message_id": email.message_id,
                        "symbol": tick, "tos_symbol": tick, "outlook": "Short"})
    p.add_rows("hist_ii", ii_rows)

    # --- Part 2: per-stock analysis blocks ---
    all_tickers = set(long_tickers + short_tickers)
    outlook_map = {t: "Long" for t in long_tickers}
    outlook_map.update({t: "Short" for t in short_tickers})

    in_analysis = False
    cur_ticker: Optional[str] = None
    cur_analyst: Optional[str] = None
    cur_lines: list[str] = []

    def _flush():
        if cur_ticker and cur_lines:
            text = "\n".join(cur_lines).strip()
            if text:
                p.notes.append(_note(
                    email, "investing_ideas", text,
                    tickers=[cur_ticker],
                    analyst=cur_analyst,
                    signal_kind=f"{outlook_map.get(cur_ticker, '')} thesis+update",
                ))

    for ln in lines:
        s = ln.strip()
        if not s:
            if in_analysis and cur_ticker:
                cur_lines.append("")
            continue

        if "New Range Charts" in s:
            in_analysis = True
            continue

        if not in_analysis:
            continue

        if s.startswith("Please visit") or s.startswith("\xa9") or s.startswith("©"):
            break

        if s in all_tickers:
            _flush()
            cur_ticker = s
            cur_analyst = None
            cur_lines = []
            continue

        if cur_ticker:
            if s.startswith("Sector Head:"):
                cur_analyst = s[12:].strip()
            elif s.startswith("Sector:"):
                pass  # skip sector line; captured in analyst context if needed
            else:
                cur_lines.append(s)

    _flush()

    if not p.notes:
        p.warnings.append("ii_weekly: no per-stock analysis blocks found")
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
    p.images = _chart_image_urls(email.html)
    if not p.images:
        p.images = re.findall(r'<img[^>]+src="(https?://[^"]+)"', email.html)[:1]
    return p


# ---------------------------------------------------------------------------
# 6) Portfolio Solutions weekly re-rank -> hist_ps  (full table from HTML)
# ---------------------------------------------------------------------------

# Maps lowercased HTML header → hist_ps field key (for columns beyond rank/ticker).
# Hedgeye HTML uses: '1-Week Change', '1-Month Change', 'Entry Date',
#                    'Asset Class', 'Position Sizing'.
_PS_EXTRA_COL_MAP: dict[str, str] = {
    "1-week change":   "wk_ago",
    "1-week chg":      "wk_ago",
    "1wk chg":         "wk_ago",
    "1-weekchange":    "wk_ago",
    "1-month change":  "mn_ago",
    "1-month chg":     "mn_ago",
    "1mo chg":         "mn_ago",
    "1-monthchange":   "mn_ago",
    "entry date":      "date_added",
    "entrydate":       "date_added",
    "date added":      "date_added",
    "asset class":     "asset_class",
    "assetclass":      "asset_class",
    "position sizing": "position_sizing",
    "position size":   "position_sizing",
    "positionsizing":  "position_sizing",
    "sizing":          "position_sizing",
}


def parse_portfolio_solutions(email: Email) -> Parsed:
    p = Parsed("portfolio_solutions")
    rows = []
    for tbl in _html_tables(email.html):
        if not tbl:
            continue
        header = [c.lower().strip() for c in tbl[0]]
        if "rank" in header and "ticker" in header:
            r_i = header.index("rank")
            t_i = header.index("ticker")
            # Map extra HTML columns → dest keys using _PS_EXTRA_COL_MAP
            extra_idx: dict[str, int] = {}
            for hi, h in enumerate(header):
                dest = _PS_EXTRA_COL_MAP.get(h)
                if dest:
                    extra_idx.setdefault(dest, hi)
            for cells in tbl[1:]:
                if len(cells) <= max(r_i, t_i):
                    continue
                rank = _num(cells[r_i])
                tick = cells[t_i].strip().upper()
                if tick and rank is not None:
                    row: dict = {
                        "snapshot_date": email.edt_date,
                        "message_id":    email.message_id,
                        "rank":          int(rank),
                        "ticker":        tick,
                        "tos_symbol":    tick,
                    }
                    for dest_key, col_idx in extra_idx.items():
                        if col_idx < len(cells):
                            val = cells[col_idx].strip() if cells[col_idx] else None
                            row[dest_key] = val or None
                    rows.append(row)
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

_CALL_OUTLOOK = {"LONGS": "BULLISH", "SHORTS": "BEARISH", "NEUTRAL": "NEUTRAL"}
_CALL_SIDE = {"LONGS": "long", "SHORTS": "short", "NEUTRAL": "neutral"}
_CALL_MODIFIERS = ("best idea long", "best idea short", "long bench", "short bench")

# Each Top-5 rationale paragraph reliably ends with its own "long"/"short" tag
# (e.g. "...skewed negatively; short", "...back-half setup; active short") —
# a more reliable side signal than the day's HEDGEYE POSITIONS list, which a
# Top-5 idea isn't always a member of.
_TOP5_SIDE_TAIL_RE = re.compile(r"\b(long|short)\b\W*$", re.IGNORECASE)


def parse_the_call(email: Email) -> Parsed:
    p = Parsed("the_call")
    text = email.plaintext

    # Build modifier map: scan body for "(SYMBOL): ... modifier-keyword ..." lines.
    # Modifier keywords (case-insensitive): "long bench", "short bench",
    # "best idea long", "best idea short".
    modifier_map: dict[str, str] = {}
    for ln in _body_lines(text):
        lm = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\):", ln)
        if lm:
            sym_key = lm.group(1).upper()
            ln_lower = ln.lower()
            for kw in _CALL_MODIFIERS:
                if kw in ln_lower:
                    modifier_map[sym_key] = kw
                    break

    # Macro Commentary — general market-wide prose (Quad/FX/commodity framing),
    # not tied to one symbol. Stored like Early Look's Key Takeaways: one note,
    # full text, tagged with whatever tickers happen to appear in it.
    mc = re.search(r"Macro Commentary\s*(.+?)\s*Sector Summary", text, re.S)
    if mc:
        commentary = re.sub(r"\s+", " ", mc.group(1)).strip()
        if commentary:
            mc_tickers = sorted(set(_TICKER_PAREN.findall(commentary)))
            p.notes.append(_note(email, "the_call_macro", commentary[:2000], tickers=mc_tickers))

    # HEDGEYE POSITIONS: LONGS / SHORTS / NEUTRAL lines
    side_for = {}
    pos_rows = []
    for label, outlook in _CALL_OUTLOOK.items():
        m = re.search(rf"{label}:\s*(.+)", text)
        if m:
            line = m.group(1).splitlines()[0].strip()
            syms = []
            for sym in re.split(r"[,\s]+", line):
                sym = sym.strip().lstrip("$").upper()
                if re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", sym):
                    pos_rows.append({
                        "snapshot_date": email.edt_date, "message_id": email.message_id,
                        "symbol": sym, "tos_symbol": sym, "outlook": outlook,
                        "outlook_modifier": modifier_map.get(sym) or _CALL_SIDE[label],
                    })
                    side_for[sym] = _CALL_SIDE[label]  # lowercase for top5 side column
                    syms.append(sym)
            if syms:
                # One note per section; all its symbols point to the same note_text.
                p.notes.append(_note(email, "the_call_positions",
                                     f"HEDGEYE POSITIONS — {label}: {line}",
                                     tickers=syms))
    p.add_rows("hist_call", pos_rows)

    # Top 5 Most Actionable (Stock) Ideas, then per-symbol sector/policy
    # commentary for the rest of the email. Each entry is its own blank-line-
    # delimited paragraph starting "Company Name (TICKER): text …" — splitting
    # on paragraph boundaries (rather than up to the next ticker match) keeps
    # a paragraph's block from swallowing the next paragraph's section-header/
    # analyst-attribution line and the start of the following company name.
    # Some commentary paragraphs group two or more names before the colon,
    # e.g. "Conagra Brands, Inc. (CAG) / Campbell Soup Company (CPB): text…"
    # or "Moody's (MCO), S&P Global (SPGI), TransUnion (TRU): text…" — the
    # header (everything up to the first colon) is scanned for every
    # "(TICKER)" it contains, and the shared commentary is filed under all of
    # them, rather than requiring exactly one ticker immediately before ":".
    # The first 5 matched paragraphs are the Top-5 list; the rest is commentary.
    top_rows = []
    m = re.search(r"Top 5 Most Actionable(?: Stock Ideas)?(.+)", text, re.S)
    if m:
        seg = m.group(1)
        entries = []
        for para in re.split(r"(?:\r?\n){2,}", seg):
            para = para.strip()
            if not para:
                continue
            pm = re.match(r"([^\n:]*\([A-Z][A-Z0-9.\-/]{0,9}\)[^\n:]*):\s*(.+)",
                          para, re.S)
            if not pm:
                # Prose paragraphs where the tickers appear only after the
                # lead-in colon (e.g. "Position monitor tilted ...: Mastercard
                # (MA), Global Payments (GPN) ...") don't fit the "Company
                # (TICK): commentary" shape but still carry real tickers worth
                # keeping — file the whole paragraph as commentary.
                fallback_syms = sorted(set(s.upper() for s in _TICKER_PAREN.findall(para)))
                if fallback_syms:
                    full_text = re.sub(r"\s+", " ", para).strip()
                    tail_m = _TOP5_SIDE_TAIL_RE.search(full_text.rstrip())
                    side = tail_m.group(1).lower() if tail_m else side_for.get(fallback_syms[0], "long")
                    p.notes.append(_note(email, "the_call_commentary", full_text,
                                         tickers=fallback_syms, signal_kind=side))
                continue
            syms = [s.upper() for s in _TICKER_PAREN.findall(pm.group(1))]
            if not syms:
                continue
            block = re.sub(r"\s+", " ", pm.group(2)).strip()
            full_text = re.sub(r"\s+", " ", para).strip()
            if block and full_text:
                entries.append((syms, block, full_text))
        for i, (syms, block, full_text) in enumerate(entries):
            tail_m = _TOP5_SIDE_TAIL_RE.search(block.rstrip())
            side = tail_m.group(1).lower() if tail_m else side_for.get(syms[0], "long")
            if i < 5:
                for sym in syms:
                    top_rows.append({
                        "snapshot_date": email.edt_date, "message_id": email.message_id,
                        "rank": i + 1, "symbol": sym, "tos_symbol": sym,
                        "side": side,
                        "rationale_snippet": block[:400],
                    })
                p.notes.append(_note(email, "the_call_top5", full_text, tickers=syms, signal_kind=side))
            else:
                p.notes.append(_note(email, "the_call_commentary", full_text, tickers=syms, signal_kind=side))
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
        # Each takeaway is its own blank-line-separated paragraph in the source
        # email. Collapse whitespace *within* a paragraph but keep paragraph
        # breaks as an explicit "\n• " bullet delimiter so the UI can
        # render the original bullet list instead of one run-on paragraph.
        paras = [re.sub(r"\s+", " ", para).strip()
                 for para in re.split(r"\n\s*\n", m.group(1).strip())]
        take = "\n• ".join(para for para in paras if para)[:2000]
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
    p.images = _chart_image_urls(email.html)
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
# 12) Macro Show — Access/Top 3 Things -> note_repo
# ---------------------------------------------------------------------------

# "1) KOSPI – text..." — number, a short label, an en-dash/em-dash/hyphen
# separator, then the takeaway itself (up to the next numbered item).
_TOP3_ITEM = re.compile(
    r"(\d)\)\s*([^\n–—-]+?)\s*[–—-]\s*(.+?)(?=\n\s*\d\)|\Z)", re.S)

# Fallback for emails where Hedgeye's <ol><li> renders as bare paragraphs with
# no visible numbering (e.g. "USD – Post a Counter...\n\nGOLD – ..."). Each
# item is its own blank-line-separated paragraph starting with a short
# ALL-CAPS label — this excludes the trailing "Immediate-term @Hedgeye Risk
# Ranges..." and "KM" sign-off lines, which aren't short/all-caps.
_TOP3_ITEM_UNNUMBERED = re.compile(
    r"^\s*([A-Z][A-Z0-9 &/]{0,20})\s*[–—-]\s*(.+?)\s*$", re.S | re.M)


def parse_macro_show_top3(email: Email) -> Parsed:
    p = Parsed("macro_show_top3")
    text = email.plaintext
    lines: list[str] = []
    m = re.search(r"Hedgeye's top 3 things\s*(.+?)(?:Immediate-term\s*@Hedgeye Risk Ranges|Please visit|$)",
                  text, re.S | re.I)
    if m:
        section = m.group(1)
        for num, label, body in _TOP3_ITEM.findall(section):
            label = label.strip()
            body = re.sub(r"\s+", " ", body).strip()
            if label and body:
                lines.append(f"{num}) {label} – {body}")
        if not lines:
            for para in re.split(r"\n\s*\n", section.strip()):
                im = _TOP3_ITEM_UNNUMBERED.match(para.strip())
                if not im:
                    continue
                label = im.group(1).strip()
                body = re.sub(r"\s+", " ", im.group(2)).strip()
                if label and body:
                    lines.append(f"{len(lines) + 1}) {label} – {body}")
    take = "\n".join(lines)[:4000]
    if not take:
        p.warnings.append("macro_show_top3: no items parsed, falling back to subject")
    tickers = sorted(set(_TICKER_PAREN.findall(text)))[:20] or email.meta_symbols
    q = _quad(email.subject + " " + text)
    p.notes.append(_note(email, "macro_show_top3", take or email.subject,
                         tickers=tickers, quad=q))
    return p


# ---------------------------------------------------------------------------
# Registry: email_type -> parser
# ---------------------------------------------------------------------------

PARSERS: dict[str, Callable[[Email], Parsed]] = {
    "risk_range": parse_risk_range,
    "real_time_alert": parse_real_time_alert,
    "investing_ideas": parse_investing_ideas,
    "etf_changes": parse_etf_changes,
    "etf_weekly": parse_etf_weekly,
    "ii_weekly": parse_ii_weekly,
    "signal_strength": parse_signal_strength,
    "portfolio_solutions": parse_portfolio_solutions,
    "macro_show_summary": parse_macro_show_summary,
    "the_call": parse_the_call,
    "early_look": parse_early_look,
    "market_situation": parse_market_situation,
    "inflation_nowcast": parse_inflation_nowcast,
    "quarterly_outlook": parse_quarterly_outlook,
    "macro_show_top3": parse_macro_show_top3,
}
