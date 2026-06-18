"""Yahoo Finance quote fetcher — lazy TTL cache for ref_rrt symbols."""
from __future__ import annotations

import csv
import logging
import pathlib
import time
from datetime import date, datetime, timezone

from sqlalchemy import text

from etl.db import session_scope

logger = logging.getLogger(__name__)

HARD_FLOOR_SEC = 60  # never fetch more often than this regardless of config

# ref_settings keys (cross-process, survive crashes as date strings)
_FETCH_STARTED_KEY = 'yahoo_auto_fetch_date'   # set BEFORE EOD download starts
_EOD_DONE_KEY      = 'yahoo_eod_done_date'     # set AFTER EOD completes successfully
_RUNNING_KEY       = 'yahoo_fetch_running'     # ISO timestamp while any fetch runs

# --- module-level state ---
_last_fetch_ts: float = 0.0          # monotonic; last RRT fetch
_fetch_running: bool = False          # True while any fetch is in progress (this process)
_last_auto_fetch_date: date | None = None  # date of last successful auto-fetch

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_interval() -> int:
    """Read yahoo_fetch_interval_sec from ref_settings; floor at HARD_FLOOR_SEC."""
    try:
        with session_scope() as s:
            val = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = 'yahoo_fetch_interval_sec'"
            )).scalar()
            return max(HARD_FLOOR_SEC, int(val or 300))
    except Exception:
        return 300


def _is_after_market_close() -> bool:
    """True if current ET time is >= 4:30 PM."""
    if _ET:
        now = datetime.now(_ET)
    else:
        now = datetime.now(timezone.utc)
        return (now.hour, now.minute) >= (21, 30)
    return (now.hour, now.minute) >= (16, 30)


def _is_at_or_after(hour: int, minute: int) -> bool:
    """True if current ET time is >= the given hour:minute."""
    if _ET:
        now = datetime.now(_ET)
    else:
        now = datetime.now(timezone.utc)
        hour += 4
    return (now.hour, now.minute) >= (hour, minute)


def _is_trading_day(d: date | None = None) -> bool:
    """True if the given date (default: today) is Mon-Fri."""
    if d is None:
        d = date.today()
    return d.weekday() < 5


def _init_last_auto_fetch_date() -> None:
    """On startup, read the last detail_fetched_at date from the DB."""
    global _last_auto_fetch_date
    try:
        with session_scope() as s:
            val = s.execute(text(
                "SELECT MAX(detail_fetched_at)::date FROM cache_yahoo_quote"
            )).scalar()
        if val:
            _last_auto_fetch_date = val
            logger.info("Auto-fetch: last detail fetch was %s", val)
    except Exception as e:
        logger.warning("Auto-fetch: could not read last detail date: %s", e)


def _mark_fetch_started(d: date) -> None:
    """Write today's date to ref_settings BEFORE the long download begins.
    Both the scheduler and the FastAPI loop read this to avoid double-runs."""
    try:
        with session_scope() as s:
            s.execute(text("""
                INSERT INTO ref_settings (setting_name, setting_value)
                VALUES (:k, :v)
                ON CONFLICT (setting_name) DO UPDATE SET setting_value = EXCLUDED.setting_value
            """), {'k': _FETCH_STARTED_KEY, 'v': d.isoformat()})
    except Exception as e:
        logger.warning("Auto-fetch: could not mark started: %s", e)


def _already_fetched_today() -> bool:
    """Cross-process check: has today's EOD fetch started (by either process)?"""
    today = date.today()
    if _last_auto_fetch_date == today:
        return True
    try:
        with session_scope() as s:
            val = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = :k"
            ), {'k': _FETCH_STARTED_KEY}).scalar()
        return val == today.isoformat()
    except Exception:
        return False


def _is_eod_done_today() -> bool:
    """True when today's EOD full fetch completed successfully."""
    try:
        with session_scope() as s:
            val = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = :k"
            ), {'k': _EOD_DONE_KEY}).scalar()
        return val == date.today().isoformat()
    except Exception:
        return False


def _mark_eod_done(d: date) -> None:
    try:
        with session_scope() as s:
            s.execute(text("""
                INSERT INTO ref_settings (setting_name, setting_value)
                VALUES (:k, :v)
                ON CONFLICT (setting_name) DO UPDATE SET setting_value = EXCLUDED.setting_value
            """), {'k': _EOD_DONE_KEY, 'v': d.isoformat()})
    except Exception as e:
        logger.warning("Could not mark EOD done: %s", e)


def _mark_fetch_running(running: bool) -> None:
    """Write or clear cross-process running flag (ISO timestamp = set, absent = clear)."""
    try:
        with session_scope() as s:
            if running:
                s.execute(text("""
                    INSERT INTO ref_settings (setting_name, setting_value)
                    VALUES (:k, :v)
                    ON CONFLICT (setting_name) DO UPDATE SET setting_value = EXCLUDED.setting_value
                """), {'k': _RUNNING_KEY, 'v': datetime.now(timezone.utc).isoformat()})
            else:
                s.execute(text(
                    "DELETE FROM ref_settings WHERE setting_name = :k"
                ), {'k': _RUNNING_KEY})
    except Exception as e:
        logger.warning("Could not update running flag: %s", e)


def _is_any_fetch_running() -> bool:
    """True if a fetch is active in this process or another (stale after 60 min)."""
    if _fetch_running:
        return True
    try:
        with session_scope() as s:
            val = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = :k"
            ), {'k': _RUNNING_KEY}).scalar()
        if val:
            started = datetime.fromisoformat(val)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - started).total_seconds() < 3600
    except Exception:
        pass
    return False


def _get_all_symbols() -> list[tuple[str, str]]:
    """Return [(tos_symbol, y_ticker)] for TOSD symbols + ref_rrt symbols only.

    Sources from hist_td (today's TOSD, ~882 symbols) not drv_symbols, so
    periodic feeds (call/rr/etf/ii) that inflate drv_symbols are excluded.
    ref_rrt adds a small number of extra watchlist symbols with Yahoo mappings.
    """
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT t.tos_symbol,
                   COALESCE(r.y_ticker, t.tos_symbol) AS y_ticker
            FROM hist_td t
            LEFT JOIN ref_rrt r ON r.tos_ticker = t.tos_symbol
            WHERE t.export_date = (SELECT MAX(export_date) FROM hist_td)
            UNION
            SELECT r.tos_ticker, r.y_ticker
            FROM ref_rrt r
            WHERE r.tos_ticker IS NOT NULL AND r.y_ticker IS NOT NULL
            ORDER BY 1
        """)).fetchall()
    # Drop symbols Yahoo can't handle:
    #   $xxx  — TOS-specific indices / foreign stocks
    #   /xxx  — futures contracts (slash prefix)
    #   [Q26] — futures contract-month notation
    #   :FRED — FRED macro series tickers
    return [
        (r[0], r[1]) for r in rows
        if r[0] and r[1]
        and not r[1].startswith('$')
        and not r[1].startswith('/')
        and '[' not in r[1]
        and ':FRED' not in r[1]
    ]


# ---------------------------------------------------------------------------
# Low-level batch fetch → cache_yahoo_quote (RRT symbols, lazy TTL)
# ---------------------------------------------------------------------------

def _fetch_and_store(tickers: list[tuple[str, str]]) -> dict:
    """
    Fetch (tos_symbol, y_ticker) pairs from Yahoo in one batch call.
    Upserts raw OHLCV + prev_close into cache_yahoo_quote.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed — run: pip install yfinance")

    if not tickers:
        return {"ok": 0, "error": 0, "fetched_at": None}

    ytickers = [t[1] for t in tickers]
    fetched_at = datetime.now(timezone.utc)

    try:
        raw = yf.download(
            ytickers, period="2d", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker",
        )
    except Exception as e:
        logger.error("Yahoo batch download failed: %s", e)
        return {"ok": 0, "error": len(tickers), "fetched_at": None}

    rows = []
    errors = 0

    for tos_symbol, y_ticker in tickers:
        try:
            closes = raw[y_ticker]["Close"].dropna() if y_ticker in raw else None
            if closes is None or closes.empty:
                rows.append(dict(tos_symbol=tos_symbol, y_ticker=y_ticker,
                                 open_price=None, high_price=None, low_price=None,
                                 last_price=None, prev_close=None, volume=None,
                                 fetched_at=fetched_at, fetch_status="no_data"))
                errors += 1
                continue

            last_price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
            opens = raw[y_ticker]["Open"].dropna()
            highs = raw[y_ticker]["High"].dropna()
            lows  = raw[y_ticker]["Low"].dropna()
            vols  = raw[y_ticker]["Volume"].dropna()

            rows.append(dict(
                tos_symbol=tos_symbol, y_ticker=y_ticker,
                open_price=float(opens.iloc[-1]) if not opens.empty else None,
                high_price=float(highs.iloc[-1]) if not highs.empty else None,
                low_price=float(lows.iloc[-1])  if not lows.empty  else None,
                last_price=last_price,
                prev_close=prev_close,
                volume=int(vols.iloc[-1]) if not vols.empty else None,
                fetched_at=fetched_at, fetch_status="ok",
            ))
        except Exception as ex:
            logger.warning("Yahoo parse error for %s: %s", y_ticker, ex)
            rows.append(dict(tos_symbol=tos_symbol, y_ticker=y_ticker,
                             open_price=None, high_price=None, low_price=None,
                             last_price=None, prev_close=None, volume=None,
                             fetched_at=fetched_at, fetch_status="error"))
            errors += 1

    if rows:
        with session_scope() as s:
            s.execute(text("""
                INSERT INTO cache_yahoo_quote
                    (tos_symbol, y_ticker, open_price, high_price, low_price,
                     last_price, prev_close, volume, fetched_at, fetch_status)
                VALUES (:tos_symbol, :y_ticker, :open_price, :high_price, :low_price,
                        :last_price, :prev_close, :volume, :fetched_at, :fetch_status)
                ON CONFLICT (tos_symbol) DO UPDATE SET
                    y_ticker     = EXCLUDED.y_ticker,
                    open_price   = EXCLUDED.open_price,
                    high_price   = EXCLUDED.high_price,
                    low_price    = EXCLUDED.low_price,
                    last_price   = EXCLUDED.last_price,
                    prev_close   = EXCLUDED.prev_close,
                    volume       = EXCLUDED.volume,
                    fetched_at   = EXCLUDED.fetched_at,
                    fetch_status = EXCLUDED.fetch_status
            """), rows)

    ok = len(rows) - errors
    logger.info("Yahoo fetch: %d ok, %d errors", ok, errors)
    return {"ok": ok, "error": errors, "fetched_at": fetched_at.isoformat()}


# ---------------------------------------------------------------------------
# Public: RRT quotes (lazy TTL — used by market-quotes API)
# ---------------------------------------------------------------------------

def fetch_rrt_quotes(force: bool = False) -> dict:
    """
    Lazy fetch: calls Yahoo only if cache is stale (older than config interval).
    force=True bypasses TTL check (used by manual fetch button).
    """
    global _last_fetch_ts
    now = time.monotonic()
    interval = _get_interval()

    if not force and (now - _last_fetch_ts) < interval:
        remaining = int(interval - (now - _last_fetch_ts))
        return {"skipped": True, "reason": f"cache fresh, {remaining}s remaining"}

    with session_scope() as s:
        rows = s.execute(text(
            "SELECT tos_ticker, y_ticker FROM ref_rrt WHERE y_ticker IS NOT NULL"
        )).fetchall()

    tickers = [(r[0], r[1]) for r in rows if r[0] and r[1]]
    result = _fetch_and_store(tickers)
    _last_fetch_ts = time.monotonic()
    return result


# ---------------------------------------------------------------------------
# Phase 1: batch OHLCV → cache_yahoo_quote (no hist_y write)
# ---------------------------------------------------------------------------

def _fetch_ohlcv_to_cache(tickers: list[tuple[str, str]],
                           batch_size: int = 100,
                           delay_sec: float = 3.0) -> dict:
    """
    Batch-download OHLCV for all tickers and upsert into cache_yahoo_quote only.
    Does NOT write to hist_y — caller does that after all cache data is ready.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed")

    total = len(tickers)
    ok_total = 0
    err_total = 0
    batches = 0
    fetched_at = datetime.now(timezone.utc)

    for i in range(0, total, batch_size):
        batch = tickers[i: i + batch_size]
        ytickers = [t[1] for t in batch]
        batches += 1
        num_batches = (total + batch_size - 1) // batch_size
        logger.info("batch %d/%d: %s", batches, num_batches, ", ".join(ytickers))

        try:
            raw = yf.download(
                ytickers, period="2d", interval="1d",
                progress=False, auto_adjust=True, group_by="ticker",
            )
        except Exception as e:
            logger.error("Yahoo OHLCV batch %d download failed: %s", batches, e)
            err_total += len(batch)
            if i + batch_size < total:
                time.sleep(delay_sec)
            continue

        cache_rows = []
        for tos_symbol, y_ticker in batch:
            try:
                closes = raw[y_ticker]["Close"].dropna() if y_ticker in raw else None
                if closes is None or closes.empty:
                    err_total += 1
                    continue
                last_price = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
                opens = raw[y_ticker]["Open"].dropna()
                highs = raw[y_ticker]["High"].dropna()
                lows  = raw[y_ticker]["Low"].dropna()
                vols  = raw[y_ticker]["Volume"].dropna()
                cache_rows.append(dict(
                    tos_symbol=tos_symbol, y_ticker=y_ticker,
                    open_price=float(opens.iloc[-1]) if not opens.empty else None,
                    high_price=float(highs.iloc[-1]) if not highs.empty else None,
                    low_price=float(lows.iloc[-1])   if not lows.empty  else None,
                    last_price=last_price,
                    prev_close=prev_close,
                    volume=int(vols.iloc[-1]) if not vols.empty else None,
                    fetched_at=fetched_at, fetch_status="ok",
                ))
                ok_total += 1
            except Exception as ex:
                logger.warning("Yahoo OHLCV parse error %s: %s", y_ticker, ex)
                err_total += 1

        if cache_rows:
            with session_scope() as s:
                s.execute(text("""
                    INSERT INTO cache_yahoo_quote
                        (tos_symbol, y_ticker, open_price, high_price, low_price,
                         last_price, prev_close, volume, fetched_at, fetch_status)
                    VALUES
                        (:tos_symbol, :y_ticker, :open_price, :high_price, :low_price,
                         :last_price, :prev_close, :volume, :fetched_at, :fetch_status)
                    ON CONFLICT (tos_symbol) DO UPDATE SET
                        y_ticker=EXCLUDED.y_ticker, open_price=EXCLUDED.open_price,
                        high_price=EXCLUDED.high_price, low_price=EXCLUDED.low_price,
                        last_price=EXCLUDED.last_price, prev_close=EXCLUDED.prev_close,
                        volume=EXCLUDED.volume, fetched_at=EXCLUDED.fetched_at,
                        fetch_status=EXCLUDED.fetch_status
                """), cache_rows)

        if i + batch_size < total:
            time.sleep(delay_sec)

    logger.info("OHLCV to cache: %d ok, %d errors, %d batches", ok_total, err_total, batches)
    return {"total": total, "batches": batches, "ok": ok_total, "errors": err_total}


# ---------------------------------------------------------------------------
# Phase 2: per-symbol detail → cache_yahoo_quote (after market close only)
# ---------------------------------------------------------------------------

def fetch_y_detail(delay_sec: float = 1.5) -> dict:
    """
    Fetch per-symbol detail (company_name, short_ratio, float, shares_out) via
    individual yf.Ticker().info calls. Upserts cache_yahoo_quote detail columns.
    Called after market close only — takes ~20 min for 750+ symbols.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed")

    symbols = _get_all_symbols()
    detail_fetched_at = datetime.now(timezone.utc)
    updated = 0
    errors = 0

    for tos_symbol, y_ticker in symbols:
        try:
            info = yf.Ticker(y_ticker).info
            company_name  = info.get("longName") or info.get("shortName")
            short_ratio   = info.get("shortRatio")
            float_shares  = info.get("floatShares")
            shares_out    = info.get("sharesOutstanding")

            with session_scope() as s:
                s.execute(text("""
                    INSERT INTO cache_yahoo_quote
                        (tos_symbol, y_ticker, detail_fetched_at,
                         company_name, short_ratio, float_shares, shares_outstanding)
                    VALUES (:sym, :ytk, :dat, :cn, :sr, :fs, :so)
                    ON CONFLICT (tos_symbol) DO UPDATE SET
                        detail_fetched_at  = EXCLUDED.detail_fetched_at,
                        company_name       = EXCLUDED.company_name,
                        short_ratio        = EXCLUDED.short_ratio,
                        float_shares       = EXCLUDED.float_shares,
                        shares_outstanding = EXCLUDED.shares_outstanding
                """), dict(sym=tos_symbol, ytk=y_ticker, dat=detail_fetched_at,
                           cn=company_name, sr=short_ratio,
                           fs=float_shares, so=shares_out))
            updated += 1
        except Exception as ex:
            logger.warning("Y detail error %s: %s", y_ticker, ex)
            errors += 1

        time.sleep(delay_sec)

    logger.info("Y detail fetch done: %d updated, %d errors", updated, errors)
    return {"total": len(symbols), "updated": updated, "errors": errors}


# ---------------------------------------------------------------------------
# Phase 3: cache_yahoo_quote → hist_y  (complete rows, one INSERT)
# ---------------------------------------------------------------------------

def _load_cache_to_hist_y(load_date: date) -> dict:
    """
    INSERT from cache_yahoo_quote into hist_y using ON CONFLICT DO NOTHING.
    Called after the cache is fully populated (OHLCV + optionally detail) so
    hist_y always gets complete rows — never a partial write.
    Also marks YFiles as done in meta_file_processed.
    """
    with session_scope() as s:
        result = s.execute(text("""
            INSERT INTO hist_y
                (snapshot_date, symbol, tos_symbol, sequence,
                 export_date, export_time,
                 last_price, change_amt, change_pct,
                 open_price, high_price, low_price,
                 company_name, short_ratio, float_str, shares_out_str,
                 source_file)
            SELECT
                :ld, y_ticker, tos_symbol, 0,
                fetched_at::date,
                TO_CHAR(fetched_at AT TIME ZONE 'UTC', 'HH24:MI:SS'),
                last_price,
                CASE WHEN prev_close IS NOT NULL
                     THEN last_price - prev_close END,
                CASE WHEN prev_close > 0
                     THEN (last_price - prev_close) / prev_close * 100 END,
                open_price, high_price, low_price,
                company_name,
                short_ratio,
                CASE WHEN float_shares       IS NOT NULL
                     THEN float_shares::TEXT END,
                CASE WHEN shares_outstanding IS NOT NULL
                     THEN shares_outstanding::TEXT END,
                'yahoo_fetch'
            FROM cache_yahoo_quote
            WHERE last_price IS NOT NULL
              AND tos_symbol IN (
                  SELECT tos_symbol FROM drv_symbols
                   WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td)
                  UNION
                  SELECT tos_ticker FROM ref_rrt WHERE tos_ticker IS NOT NULL
              )
            ON CONFLICT DO NOTHING
        """), {'ld': load_date})
        inserted = result.rowcount

    logger.info("cache → hist_y: %d rows inserted for %s", inserted, load_date)

    # Mark YFiles done in today's schedule (even though no file was dropped)
    try:
        import time as _time
        with session_scope() as s:
            s.execute(text("""
                INSERT INTO meta_file_processed
                    (file_path, file_mtime, file_type, file_date, processed_at)
                VALUES (:fp, :fm, 'YFiles', :fd, now())
                ON CONFLICT (file_path) DO UPDATE SET processed_at = now()
            """), {'fp': f'yahoo_auto:{load_date.isoformat()}',
                   'fm': _time.time(), 'fd': load_date})
    except Exception as e:
        logger.warning("Could not mark YFiles processed: %s", e)

    return {"inserted_hist_y": inserted}


# ---------------------------------------------------------------------------
# Post-load tos_symbol fix — run after CSV load, before derive
# ---------------------------------------------------------------------------

def _fix_hist_y_tos_symbol(load_date: date) -> None:
    """Populate hist_y.tos_symbol from cache_yahoo_quote after a CSV load.
    CSV mapping writes symbol=y_ticker but leaves tos_symbol NULL.
    cache_yahoo_quote has the y_ticker→tos_symbol mapping we need.
    Fallback: tos_symbol = symbol for any unmatched rows."""
    try:
        with session_scope() as s:
            s.execute(text("""
                UPDATE hist_y h
                SET tos_symbol = c.tos_symbol
                FROM cache_yahoo_quote c
                WHERE h.symbol = c.y_ticker
                  AND h.snapshot_date = :d
                  AND h.tos_symbol IS NULL
            """), {"d": load_date})
            s.execute(text("""
                UPDATE hist_y
                SET tos_symbol = symbol
                WHERE snapshot_date = :d AND tos_symbol IS NULL
            """), {"d": load_date})
    except Exception as e:
        logger.warning("Could not fix hist_y.tos_symbol: %s", e)


def _load_yfiles_csv(csv_path: pathlib.Path, load_date: date) -> dict:
    """Load a YFiles CSV with do_derive=False, fix tos_symbol, then derive."""
    from etl.etl_load import load_one_file
    load_result = load_one_file(str(csv_path), do_derive=False)
    _fix_hist_y_tos_symbol(load_date)
    try:
        from etl.derive import derive_all, get_anchor_date
        with session_scope() as s:
            anchor = get_anchor_date(s)
        if anchor:
            with session_scope() as s:
                derive_all(s, anchor)
    except Exception as e:
        logger.warning("Derive after Y load failed: %s", e)
    return load_result


# ---------------------------------------------------------------------------
# CSV helpers — write cache_yahoo_quote as a YFiles-format CSV
# ---------------------------------------------------------------------------

def _get_yfiles_dir() -> "pathlib.Path | None":
    """Read source_dir from ref_load_files for the YFiles file type."""
    try:
        with session_scope() as s:
            val = s.execute(text("""
                SELECT source_dir FROM ref_load_files
                WHERE UPPER(file_type) = 'YFILES' LIMIT 1
            """)).scalar()
        return pathlib.Path(val) if val else None
    except Exception as e:
        logger.warning("Could not read YFiles source_dir: %s", e)
        return None


def _fmt_num(v) -> str:
    """Format a numeric value for CSV output (empty string for None)."""
    if v is None:
        return ""
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return ""


def _write_yfiles_csv(load_date: date,
                      target_dir: pathlib.Path,
                      force_time: "str | None" = None) -> "pathlib.Path | None":
    """
    Generate a YFiles CSV from cache_yahoo_quote and write it to target_dir.
    Column order matches HIST_MAPS['Y'] CSV-alt names so load_one_file() picks
    it up correctly.  force_time overrides the Time column (e.g. '1630' for EOD).
    If the file already exists it is sent to the recycle bin before being replaced.
    Returns the written Path, or None on failure.
    """
    try:
        with session_scope() as s:
            rows = s.execute(text("""
                SELECT
                    y_ticker, company_name, last_price,
                    CASE WHEN prev_close IS NOT NULL
                         THEN last_price - prev_close END,
                    CASE WHEN prev_close > 0
                         THEN (last_price - prev_close) / prev_close * 100 END,
                    open_price, high_price, low_price,
                    short_ratio, float_shares, shares_outstanding
                FROM cache_yahoo_quote
                WHERE last_price IS NOT NULL
                ORDER BY y_ticker
            """)).fetchall()
    except Exception as e:
        logger.error("Could not read cache for YFiles CSV: %s", e)
        return None

    if not rows:
        logger.warning("cache_yahoo_quote empty — no CSV written")
        return None

    now_et = datetime.now(_ET) if _ET else datetime.now(timezone.utc)
    date_str = f"{load_date.month}/{load_date.day}/{load_date.year}"
    time_str = force_time if force_time is not None else now_et.strftime("%H%M")
    filename = f"YFiles {load_date.isoformat()}.csv"
    csv_path = target_dir / filename

    # Send existing file to recycle bin before overwriting
    if csv_path.exists():
        try:
            import send2trash
            send2trash.send2trash(str(csv_path))
            logger.info("Recycled existing YFiles CSV: %s", csv_path.name)
        except Exception as e:
            logger.warning("Could not recycle %s (%s) — deleting permanently", csv_path.name, e)
            try:
                csv_path.unlink()
            except Exception:
                pass

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([
                "Date", "Time", "Symbol", "Company Name",
                "Last Price", "Change", "Change (%)",
                "Open", "High", "Low",
                "Short Ratio", "Float", "Shares Out",
            ])
            for (sym, co, lp, chg, chgp, op, hi, lo, sr, fs, so) in rows:
                w.writerow([
                    date_str, time_str, sym, co or "",
                    _fmt_num(lp), _fmt_num(chg), _fmt_num(chgp),
                    _fmt_num(op), _fmt_num(hi), _fmt_num(lo),
                    _fmt_num(sr),
                    int(fs) if fs is not None else "",
                    int(so) if so is not None else "",
                ])
        logger.info("YFiles CSV: %d rows -> %s", len(rows), csv_path)
        return csv_path
    except Exception as e:
        logger.error("Failed to write YFiles CSV %s: %s", csv_path, e)
        return None


# ---------------------------------------------------------------------------
# Public: Y Load (manual button — OHLCV only, no detail)
# ---------------------------------------------------------------------------

def fetch_y_load(batch_size: int = 100, delay_sec: float = 3.0) -> dict:
    """
    Manual Y load: batch OHLCV -> cache_yahoo_quote, then write a YFiles CSV
    and process it immediately via load_one_file() so the scheduler can't
    double-process it. Falls back to direct cache->hist_y if YFiles dir is
    unavailable.
    """
    tickers = _get_all_symbols()
    cache_result = _fetch_ohlcv_to_cache(tickers, batch_size, delay_sec)
    today = date.today()
    total = cache_result.get("total", 0)
    batches = cache_result.get("batches", 0)

    yfiles_dir = _get_yfiles_dir()
    if yfiles_dir is not None:
        csv_path = _write_yfiles_csv(today, yfiles_dir)
        if csv_path is not None:
            load_result = _load_yfiles_csv(csv_path, today)
            logger.info("fetch_y_load: %d symbols, %d batches, csv=%s",
                        total, batches, csv_path.name)
            return {"total": total, "batches": batches,
                    "csv": str(csv_path), "load": load_result}

    # Fallback: direct cache -> hist_y (no CSV written)
    hist_result = _load_cache_to_hist_y(today)
    inserted = hist_result.get("inserted_hist_y", 0)
    logger.info("fetch_y_load (fallback): %d symbols, %d batches, %d inserted",
                total, batches, inserted)
    return {"total": total, "batches": batches, "inserted_hist_y": inserted}


# ---------------------------------------------------------------------------
# Public: Full after-market load (OHLCV + detail, then cache → hist_y)
# ---------------------------------------------------------------------------

def fetch_y_load_full() -> dict:
    """Internal: full after-market Y load. Use fetch_y_smart() from outside."""
    global _fetch_running, _last_auto_fetch_date
    if _fetch_running:
        return {"skipped": True, "reason": "already running"}
    _fetch_running = True
    _mark_fetch_running(True)
    today = date.today()
    _mark_fetch_started(today)  # cross-process guard: written BEFORE download
    try:
        tickers = _get_all_symbols()

        logger.info("Y full fetch phase 1: OHLCV for %d symbols...", len(tickers))
        cache_result = _fetch_ohlcv_to_cache(tickers)

        logger.info("Y full fetch phase 2: detail fetch...")
        detail_result = fetch_y_detail()

        logger.info("Y full fetch phase 3: write CSV (time=1630) and load...")
        yfiles_dir = _get_yfiles_dir()
        if yfiles_dir is not None:
            csv_path = _write_yfiles_csv(today, yfiles_dir, force_time="1630")
            if csv_path is not None:
                hist_result = {"csv": str(csv_path),
                               "load": _load_yfiles_csv(csv_path, today)}
            else:
                hist_result = _load_cache_to_hist_y(today)
        else:
            hist_result = _load_cache_to_hist_y(today)

        _last_auto_fetch_date = today
        _mark_eod_done(today)
        logger.info("Y full fetch complete for %s", today)
        return {"cache": cache_result, "detail": detail_result,
                "hist": hist_result, "date": str(today)}
    except Exception as ex:
        logger.error("Y full fetch error: %s", ex)
        return {"error": str(ex)}
    finally:
        _fetch_running = False
        _mark_fetch_running(False)


# ---------------------------------------------------------------------------
# Public: unified smart fetch (single entry point for button + auto-fetcher)
# ---------------------------------------------------------------------------

def fetch_y_smart() -> dict:
    """
    Unified Y fetch called by the manual button and both auto-fetch paths.

    Rules:
    - EOD done today          → skip (button is disabled)
    - Any fetch running       → skip (concurrent-run guard, cross-process)
    - Before 4 PM ET          → batch OHLCV only; CSV time = current HHMM
    - At/after 4 PM ET        → full fetch (OHLCV + detail); CSV time = 1630;
                                marks EOD done — never runs again today
    """
    if _is_eod_done_today():
        return {"skipped": True, "reason": "eod_done",
                "msg": "EOD Y load already completed for today"}
    # Cross-process guard: _already_fetched_today covers the window between
    # EOD starting and EOD completing (e.g. scheduler started at 4:15, app
    # fallback wakes at 4:30 while download still running).
    if _already_fetched_today() or _is_any_fetch_running():
        return {"skipped": True, "reason": "running",
                "msg": "A fetch is already in progress"}

    global _fetch_running, _last_auto_fetch_date
    _fetch_running = True
    _mark_fetch_running(True)
    today = date.today()

    try:
        tickers = _get_all_symbols()

        if _is_at_or_after(16, 0):
            # ── EOD path ──────────────────────────────────────────────────
            _mark_fetch_started(today)  # cross-process guard before slow download

            logger.info("Y smart (EOD): OHLCV for %d symbols...", len(tickers))
            cache_result = _fetch_ohlcv_to_cache(tickers)

            logger.info("Y smart (EOD): detail fetch...")
            detail_result = fetch_y_detail()

            logger.info("Y smart (EOD): writing CSV with time=1630...")
            yfiles_dir = _get_yfiles_dir()
            if yfiles_dir is not None:
                csv_path = _write_yfiles_csv(today, yfiles_dir, force_time="1630")
                if csv_path is not None:
                    hist_result = {"csv": str(csv_path),
                                   "load": _load_yfiles_csv(csv_path, today)}
                else:
                    hist_result = _load_cache_to_hist_y(today)
            else:
                hist_result = _load_cache_to_hist_y(today)

            _last_auto_fetch_date = today
            _mark_eod_done(today)
            logger.info("Y smart (EOD) complete for %s", today)
            return {"eod": True, "cache": cache_result,
                    "detail": detail_result, "hist": hist_result}

        else:
            # ── Intraday batch path ────────────────────────────────────────
            logger.info("Y smart (intraday): OHLCV for %d symbols...", len(tickers))
            cache_result = _fetch_ohlcv_to_cache(tickers)

            yfiles_dir = _get_yfiles_dir()
            if yfiles_dir is not None:
                csv_path = _write_yfiles_csv(today, yfiles_dir)   # uses current HHMM
                if csv_path is not None:
                    hist_result = {"csv": str(csv_path),
                                   "load": _load_yfiles_csv(csv_path, today)}
                else:
                    hist_result = _load_cache_to_hist_y(today)
            else:
                hist_result = _load_cache_to_hist_y(today)

            logger.info("Y smart (intraday) complete for %s", today)
            return {"eod": False, "cache": cache_result, "hist": hist_result}

    except Exception as ex:
        logger.error("Y smart fetch error: %s", ex)
        return {"error": str(ex)}
    finally:
        _fetch_running = False
        _mark_fetch_running(False)


# ---------------------------------------------------------------------------
# Public: status helper (for API endpoint)
# ---------------------------------------------------------------------------

def get_auto_fetch_status() -> dict:
    """Return current auto-fetch state for the File Monitor status display."""
    today = date.today()
    is_trading = _is_trading_day(today)
    is_after   = _is_after_market_close()
    eod_done   = _is_eod_done_today()

    if _fetch_running:
        next_info = "running now"
    elif not is_trading:
        next_info = "weekend — skipped"
    elif eod_done:
        next_info = "done for today"
    elif is_after:
        next_info = "pending — will start shortly"
    else:
        next_info = "today at 4:15 PM ET (scheduler) / 4:30 PM ET (app)"

    return {
        "running":               _fetch_running,
        "eod_done":              eod_done,
        "last_auto_fetch_date":  str(_last_auto_fetch_date) if _last_auto_fetch_date else None,
        "is_after_market_close": is_after,
        "is_trading_day":        is_trading,
        "next_fetch":            next_info,
    }


# ---------------------------------------------------------------------------
# Background async loop (started by api/main.py on startup)
# ---------------------------------------------------------------------------

async def auto_fetch_loop() -> None:
    """
    FastAPI fallback: fires at 4:30 PM ET if the scheduler didn't already run
    at 4:15. Checks _already_fetched_today() via DB so both processes coordinate.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yahoo-auto")

    await loop.run_in_executor(executor, _init_last_auto_fetch_date)

    logger.info("Auto-fetch loop started — fallback fires at 4:30 PM ET (checks every 60 s)")
    while True:
        await asyncio.sleep(60)
        try:
            today = date.today()
            if (
                _is_trading_day(today)
                and _is_at_or_after(16, 30)
                and not _is_eod_done_today()
                and not _already_fetched_today()
                and not _fetch_running
            ):
                logger.info("Auto-fetch (app fallback): triggering Y load for %s", today)
                await loop.run_in_executor(executor, fetch_y_smart)
        except Exception as e:
            logger.error("auto_fetch_loop error: %s", e)
