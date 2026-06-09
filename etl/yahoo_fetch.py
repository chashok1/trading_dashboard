"""Yahoo Finance quote fetcher — lazy TTL cache for ref_rrt symbols."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

from sqlalchemy import text

from etl.db import session_scope

logger = logging.getLogger(__name__)

HARD_FLOOR_SEC = 60  # never fetch more often than this regardless of config

# ref_settings key written at the START of fetch_y_load_full() so both the
# scheduler process and the FastAPI process can see it and avoid double-runs.
_FETCH_STARTED_KEY = 'yahoo_auto_fetch_date'

# --- module-level state ---
_last_fetch_ts: float = 0.0          # monotonic; last RRT fetch
_y_load_running: bool = False         # True while full Y load is in progress
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
    """Cross-process check: has today's auto-fetch started (by either process)?"""
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


def _get_all_symbols() -> list[tuple[str, str]]:
    """Return [(tos_symbol, y_ticker)] for all current drv_symbols."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT s.tos_symbol,
                   COALESCE(r.y_ticker, s.tos_symbol) AS y_ticker
            FROM drv_symbols s
            LEFT JOIN ref_rrt r ON r.tos_ticker = s.tos_symbol
            WHERE s.as_of_date = (SELECT MAX(as_of_date) FROM drv_symbols)
            ORDER BY s.tos_symbol
        """)).fetchall()
    return [(r[0], r[1]) for r in rows if r[0] and r[1]]


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
                           delay_sec: float = 30.0) -> dict:
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
                :ld, tos_symbol, tos_symbol, 0,
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
# Public: Y Load (manual button — OHLCV only, no detail)
# ---------------------------------------------------------------------------

def fetch_y_load(batch_size: int = 100, delay_sec: float = 30.0) -> dict:
    """
    Manual Y load: batch OHLCV → cache_yahoo_quote, then cache → hist_y.
    No per-symbol detail fetch (use fetch_y_load_full for that).
    hist_y is written only after the cache is fully populated.
    """
    tickers = _get_all_symbols()
    cache_result = _fetch_ohlcv_to_cache(tickers, batch_size, delay_sec)
    hist_result  = _load_cache_to_hist_y(date.today())
    total = cache_result.get("total", 0)
    batches = cache_result.get("batches", 0)
    inserted = hist_result.get("inserted_hist_y", 0)
    logger.info("fetch_y_load: %d symbols, %d batches, %d inserted hist_y",
                total, batches, inserted)
    return {"total": total, "batches": batches, "inserted_hist_y": inserted}


# ---------------------------------------------------------------------------
# Public: Full after-market load (OHLCV + detail, then cache → hist_y)
# ---------------------------------------------------------------------------

def fetch_y_load_full() -> dict:
    """
    Full after-market Y load — three phases:
      1. Batch OHLCV → cache_yahoo_quote (fast, ~4 min)
      2. Per-symbol detail → cache_yahoo_quote (slow, ~20 min)
      3. cache_yahoo_quote → hist_y (one clean INSERT, complete rows)
    hist_y is written only after both cache phases are done so it always
    gets full data. ON CONFLICT DO NOTHING — TOS rows always win.
    """
    global _y_load_running, _last_auto_fetch_date
    if _y_load_running:
        return {"skipped": True, "reason": "already running"}
    _y_load_running = True
    today = date.today()
    _mark_fetch_started(today)  # write DB flag BEFORE download — cross-process lock
    try:
        tickers = _get_all_symbols()

        logger.info("Auto-fetch phase 1: OHLCV for %d symbols...", len(tickers))
        cache_result = _fetch_ohlcv_to_cache(tickers)

        logger.info("Auto-fetch phase 2: detail fetch...")
        detail_result = fetch_y_detail()

        logger.info("Auto-fetch phase 3: cache -> hist_y...")
        hist_result = _load_cache_to_hist_y(today)

        _last_auto_fetch_date = today
        logger.info("Auto-fetch complete for %s: cache=%s detail=%s hist_y=%s",
                    today, cache_result, detail_result, hist_result)
        return {"cache": cache_result, "detail": detail_result,
                "hist_y": hist_result, "date": str(today)}
    except Exception as ex:
        logger.error("Auto-fetch error: %s", ex)
        return {"error": str(ex)}
    finally:
        _y_load_running = False


# ---------------------------------------------------------------------------
# Public: status helper (for API endpoint)
# ---------------------------------------------------------------------------

def get_auto_fetch_status() -> dict:
    """Return current auto-fetch state for the File Monitor status display."""
    today = date.today()
    is_trading = _is_trading_day(today)
    is_after   = _is_after_market_close()

    if _y_load_running:
        next_info = "running now"
    elif not is_trading:
        next_info = "weekend — skipped"
    elif _last_auto_fetch_date == today:
        next_info = "done for today"
    elif is_after:
        next_info = "pending — will start shortly"
    else:
        next_info = "today at 4:15 PM ET (scheduler) / 4:30 PM ET (app)"

    return {
        "running":               _y_load_running,
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
                and not _already_fetched_today()
                and not _y_load_running
            ):
                logger.info("Auto-fetch (app fallback): triggering full Y load for %s", today)
                loop.run_in_executor(executor, fetch_y_load_full)
        except Exception as e:
            logger.error("auto_fetch_loop error: %s", e)
