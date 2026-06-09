"""Yahoo Finance quote fetcher — lazy TTL cache for ref_rrt symbols."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

from sqlalchemy import text

from etl.db import session_scope

logger = logging.getLogger(__name__)

HARD_FLOOR_SEC = 60  # never fetch more often than this regardless of config

# --- module-level state ---
_last_fetch_ts: float = 0.0          # monotonic; last RRT fetch
_y_load_running: bool = False         # True while full Y load is in progress
_last_auto_fetch_date: date | None = None  # date of last successful auto-fetch

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None  # fallback: treat UTC as ET (acceptable if zoneinfo missing)


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
        # UTC fallback: 4:30 PM ET = ~21:30 UTC (EST) or ~20:30 UTC (EDT)
        # Use 21:30 UTC as a conservative estimate
        now = datetime.now(timezone.utc)
        return (now.hour, now.minute) >= (21, 30)
    return (now.hour, now.minute) >= (16, 30)


def _is_trading_day(d: date | None = None) -> bool:
    """True if the given date (default: today) is Mon–Fri."""
    if d is None:
        d = date.today()
    return d.weekday() < 5  # 0=Mon .. 4=Fri


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


# ---------------------------------------------------------------------------
# Low-level batch fetch → cache_yahoo_quote
# ---------------------------------------------------------------------------

def _fetch_and_store(tickers: list[tuple[str, str]]) -> dict:
    """
    Fetch (tos_symbol, y_ticker) pairs from Yahoo in one batch call.
    Upserts raw OHLCV + prev_close into cache_yahoo_quote.
    Returns {'ok': N, 'error': N, 'fetched_at': iso_str}.
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
# Public: Y Load (batch OHLCV for all drv_symbols → hist_y + cache)
# ---------------------------------------------------------------------------

def fetch_y_load(batch_size: int = 100, delay_sec: float = 30.0) -> dict:
    """
    Fetch Yahoo Finance OHLCV for all drv_symbols and insert into hist_y.
    ON CONFLICT DO NOTHING so real TOS data always wins.
    Also upserts cache_yahoo_quote.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed")

    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT s.tos_symbol,
                   COALESCE(r.y_ticker, s.tos_symbol) AS y_ticker
            FROM drv_symbols s
            LEFT JOIN ref_rrt r ON r.tos_ticker = s.tos_symbol
            WHERE s.as_of_date = (SELECT MAX(as_of_date) FROM drv_symbols)
            ORDER BY s.tos_symbol
        """)).fetchall()

    tickers = [(r[0], r[1]) for r in rows if r[0] and r[1]]
    total = len(tickers)
    inserted = 0
    batches = 0
    fetched_at = datetime.now(timezone.utc)
    today = fetched_at.date()
    export_time = fetched_at.strftime("%H:%M:%S")

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
            logger.error("Yahoo Y load batch %d download failed: %s", batches, e)
            if i + batch_size < total:
                time.sleep(delay_sec)
            continue

        hist_rows = []
        cache_rows = []

        for tos_ticker, y_ticker in batch:
            try:
                closes = raw[y_ticker]["Close"].dropna() if y_ticker in raw else None
                if closes is None or closes.empty:
                    continue
                last_price = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
                chg  = round(last_price - prev_close, 6) if prev_close else None
                pct  = round(chg / prev_close * 100, 4)  if chg and prev_close else None
                opens = raw[y_ticker]["Open"].dropna()
                highs = raw[y_ticker]["High"].dropna()
                lows  = raw[y_ticker]["Low"].dropna()
                vols  = raw[y_ticker]["Volume"].dropna()
                open_p  = float(opens.iloc[-1]) if not opens.empty else None
                high_p  = float(highs.iloc[-1]) if not highs.empty else None
                low_p   = float(lows.iloc[-1])  if not lows.empty  else None
                vol     = int(vols.iloc[-1])     if not vols.empty  else None

                hist_rows.append(dict(
                    snapshot_date=today, symbol=tos_ticker, tos_symbol=tos_ticker,
                    sequence=0, export_date=today, export_time=export_time,
                    last_price=last_price, change_amt=chg, change_pct=pct,
                    open_price=open_p, high_price=high_p, low_price=low_p,
                    source_file="yahoo_fetch",
                ))
                cache_rows.append(dict(
                    tos_symbol=tos_ticker, y_ticker=y_ticker,
                    open_price=open_p, high_price=high_p, low_price=low_p,
                    last_price=last_price, prev_close=prev_close, volume=vol,
                    fetched_at=fetched_at, fetch_status="ok",
                ))
            except Exception as ex:
                logger.warning("Yahoo Y load parse error %s: %s", y_ticker, ex)

        if hist_rows:
            with session_scope() as s:
                result = s.execute(text("""
                    INSERT INTO hist_y
                        (snapshot_date, symbol, tos_symbol, sequence, export_date,
                         export_time, last_price, change_amt, change_pct,
                         open_price, high_price, low_price, source_file)
                    VALUES
                        (:snapshot_date, :symbol, :tos_symbol, :sequence, :export_date,
                         :export_time, :last_price, :change_amt, :change_pct,
                         :open_price, :high_price, :low_price, :source_file)
                    ON CONFLICT DO NOTHING
                """), hist_rows)
                inserted += result.rowcount

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

    logger.info("Yahoo Y load: %d total, %d inserted into hist_y, %d batches",
                total, inserted, batches)
    return {"total": total, "batches": batches, "inserted_hist_y": inserted}


# ---------------------------------------------------------------------------
# Public: Detail fetch (company info — after market close only)
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

    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT s.tos_symbol, COALESCE(r.y_ticker, s.tos_symbol) AS y_ticker
            FROM drv_symbols s
            LEFT JOIN ref_rrt r ON r.tos_ticker = s.tos_symbol
            WHERE s.as_of_date = (SELECT MAX(as_of_date) FROM drv_symbols)
            ORDER BY s.tos_symbol
        """)).fetchall()

    symbols = [(r[0], r[1]) for r in rows if r[0] and r[1]]
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
# Public: Full after-market load (batch OHLCV + detail)
# ---------------------------------------------------------------------------

def fetch_y_load_full() -> dict:
    """
    Full after-market Y load: batch OHLCV (fetch_y_load) then per-symbol
    detail (fetch_y_detail). Sets _last_auto_fetch_date on success.
    """
    global _y_load_running, _last_auto_fetch_date
    if _y_load_running:
        return {"skipped": True, "reason": "already running"}
    _y_load_running = True
    try:
        logger.info("Auto-fetch: starting batch Y load...")
        batch_result = fetch_y_load()
        logger.info("Auto-fetch: batch done %s; starting detail fetch...", batch_result)
        detail_result = fetch_y_detail()
        today = date.today()
        _last_auto_fetch_date = today
        logger.info("Auto-fetch complete for %s: batch=%s detail=%s",
                    today, batch_result, detail_result)
        return {"batch": batch_result, "detail": detail_result, "date": str(today)}
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
        next_info = "today at 4:30 PM ET"

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
    Async task started at FastAPI startup. Checks every 60 s whether to trigger
    the after-market Y load. Conditions: Mon–Fri, after 4:30 PM ET, not yet run
    today, not already running.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yahoo-auto")

    # Re-read last fetch date from DB so server restarts don't re-run same day
    loop.run_in_executor(executor, _init_last_auto_fetch_date)

    logger.info("Auto-fetch loop started (checks every 60 s)")
    while True:
        await asyncio.sleep(60)
        try:
            today = date.today()
            if (
                _is_trading_day(today)
                and _is_after_market_close()
                and _last_auto_fetch_date != today
                and not _y_load_running
            ):
                logger.info("Auto-fetch: triggering full Y load for %s", today)
                loop.run_in_executor(executor, fetch_y_load_full)
        except Exception as e:
            logger.error("auto_fetch_loop error: %s", e)
