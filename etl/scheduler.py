"""
Folder watcher for the 17 source directories listed in ref_load_files.

For every .xlsx file event (created or modified) in a watched folder,
we call etl.etl_load.load_one_file() which:
  - copies source to ETL_WORKING_DIR (NEVER deletes)
  - inserts into the right hist_* table (skipping duplicates)
  - rebuilds drv_* for the snapshot date

In addition, the scheduler fires a nightly job once per local day:
  - etl.compute_outcomes — score logged user actions against forward returns
The hour is configurable via ref_settings.outcomes_compute_hour (default 22).

Usage:
    python -m etl.scheduler            # watch all enabled dirs from ref_load_files
    python -m etl.scheduler --dirs C:\\path1 C:\\path2  # override
    python -m etl.scheduler --no-nightly                # disable nightly job
"""
from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

# Enable faulthandler EARLY so segfaults / fatal Python errors leave a stack
# trace on stderr (which the launcher redirects to scheduler_crash.log).
# Without this a C-extension crash (pandas/psycopg/watchdog) just exits the
# process silently — leaving an orphan heartbeat behind.
try:
    faulthandler.enable()
except Exception:
    pass

# Force stderr/stdout to be unbuffered so a hard crash doesn't lose the last
# few log lines. The launcher captures both streams to scheduler_crash.log.
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

from sqlalchemy import text
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from config.settings import settings
from etl.db import session_scope
from etl.etl_load import load_one_file

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("scheduler")

# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle log — writes EVERY major step to a separate plain-text file. The
# log/db pipeline can be slow or fail; this file has no dependencies and is
# the absolute last-chance breadcrumb when the scheduler dies for any reason
# (external SIGTERM, OOM kill, Windows process termination, segfault, etc.).
# ─────────────────────────────────────────────────────────────────────────────
def _lifecycle(msg: str) -> None:
    try:
        wdir = Path(settings.etl_working_dir)
        wdir.mkdir(parents=True, exist_ok=True)
        with open(wdir / "scheduler_lifecycle.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().isoformat()} pid={os.getpid()} {msg}\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except Exception:
                pass
    except Exception:
        pass


_lifecycle("=== scheduler.py module imported ===")


# ─────────────────────────────────────────────────────────────────────────────
# Signal handlers — distinguish "we got killed externally" from "we crashed
# inside Python". On Windows, SIGBREAK comes from Ctrl-Break / job-object kill;
# SIGTERM from taskkill/another process; SIGINT from Ctrl-C.
# ─────────────────────────────────────────────────────────────────────────────
def _install_signal_handlers() -> None:
    import signal

    def _handler(signum, frame):
        try:
            sig_name = signal.Signals(signum).name
        except Exception:
            sig_name = str(signum)
        _lifecycle(f"!!! received signal {sig_name} ({signum}) — exiting")
        try:
            log.warning("scheduler received signal %s — exiting", sig_name)
        except Exception:
            pass
        # Drop the heartbeat so the UI shows the process as stopped immediately.
        try:
            release_lock(Path(settings.etl_working_dir) / "scheduler.lock")
        except Exception:
            pass
        # legacy cleanup of old heartbeat file (no longer used)
        try:
            (Path(settings.etl_working_dir) / "scheduler_heartbeat.txt").unlink(missing_ok=True)
        except Exception:
            pass
        # Don't raise — just exit cleanly.
        os._exit(0)

    # NOTE: SIGABRT intentionally NOT handled here — leave it for faulthandler
    # so a native abort() in a C extension produces a Python stack trace
    # instead of being silently swallowed by our handler.
    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        try:
            s = getattr(signal, sig_name)
            signal.signal(s, _handler)
            _lifecycle(f"installed handler for {sig_name}")
        except Exception:
            pass


try:
    _install_signal_handlers()
except Exception:
    pass

# Register an atexit hook so we know Python itself initiated the shutdown
# (vs. an external kill, which bypasses atexit).
import atexit
@atexit.register
def _atexit_marker():
    _lifecycle("<<< Python atexit fired (interpreter shutting down normally)")


# Debounce: same file may fire many events as it's being written.
# We track {abs_path: last_seen} and ignore events for the same file within
# DEBOUNCE_SECS. Windows commonly emits a redundant on_modified a few seconds
# after the file is loaded, so 30 s avoids re-processing the same file twice.
_LAST_SEEN: dict[str, float] = {}
DEBOUNCE_SECS = 30.0
QUIESCE_SECS = 2.0   # wait this long after last write before processing

# ─────────────────────────────────────────────────────────────────────────────
# OS-level file lock — sole source of truth for "is the scheduler running?".
# The handle is opened at startup, byte 0 is locked exclusively, the handle
# is kept open in this module variable for the scheduler's entire lifetime.
# On clean exit we unlock + close; on hard crash the OS releases the lock
# automatically. Readers (API) try to acquire the same lock — if they can,
# scheduler is NOT running; if they can't, it IS.
# ─────────────────────────────────────────────────────────────────────────────
_LOCK_FP = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Single-instance lock — prevents two schedulers from racing on the same file
# ─────────────────────────────────────────────────────────────────────────────

def _is_pid_alive(pid: int) -> bool:
    """Cross-platform liveness check for a PID.

    On Windows: os.kill(pid, 0) raises if the process doesn't exist; raises
    PermissionError for processes we can't signal (returns True in that case,
    because something *is* there using that PID).
    On Unix: same semantics via signal 0.
    """
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but belongs to another user/elevated process — still alive
        return True
    except OSError:
        return False




def acquire_lock(lock_path: Path, force: bool = False) -> int | None:
    """Acquire an exclusive byte-range lock on `lock_path`.

    On success: the file handle is stored in module-level `_LOCK_FP` so the
    lock stays held for the scheduler's entire lifetime. The OS releases it
    automatically when the process exits, even on a hard crash.

    On failure (another process holds it): returns -1 to signal "blocked"
    so main() exits with non-zero. The legacy PID return type is dropped.

    `force` is accepted but unused — the OS lock is the only truth here.
    """
    global _LOCK_FP
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        _LOCK_FP = open(lock_path, "ab+")   # create if missing, keep existing bytes
        _try_lock(_LOCK_FP)
        return None
    except OSError as e:
        log.error("Another scheduler holds the lock on %s (%s) — exiting",
                  lock_path, e)
        try:
            if _LOCK_FP is not None:
                _LOCK_FP.close()
        except Exception:
            pass
        _LOCK_FP = None
        return -1


def release_lock(lock_path: Path) -> None:
    """Release the exclusive lock and close the file handle. Idempotent —
    safe to call from atexit + finally + signal handlers."""
    global _LOCK_FP
    fp = _LOCK_FP
    _LOCK_FP = None
    if fp is None:
        return
    try:
        _try_unlock(fp)
    except Exception:
        pass
    try:
        fp.close()
    except Exception:
        pass


def _try_lock(fp) -> None:
    """Acquire exclusive non-blocking lock on byte 0 of fp."""
    if sys.platform == "win32":
        import msvcrt
        # Seek to 0 — locking is byte-range from current position.
        fp.seek(0)
        msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _try_unlock(fp) -> None:
    """Release the byte-range lock acquired via _try_lock."""
    if sys.platform == "win32":
        import msvcrt
        try:
            fp.seek(0)
            msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
    else:
        import fcntl
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass


def get_watch_dirs() -> list[str]:
    """Read distinct enabled source dirs from ref_load_files."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT source_dir FROM ref_load_files
            WHERE enabled = TRUE AND source_dir IS NOT NULL
        """)).fetchall()
    return [r[0] for r in rows]


def is_target(path: Path) -> bool:
    """Only .xlsx/.xlsm/.csv files matter; skip Excel lock files (~$*)."""
    if not path.is_file():
        return False
    if path.name.startswith("~$"):
        return False
    if path.suffix.lower() not in (".xlsx", ".xlsm", ".csv"):
        return False
    return True


def _wait_until_readable(path: Path, max_wait: float = 60.0) -> bool:
    """Probe-open the file until Windows actually releases its sharing lock."""
    try:
        deadline = time.time() + max_wait
        backoff = 1.0
        while time.time() < deadline:
            try:
                with open(path, 'rb') as fh:
                    fh.read(1)
                return True
            except PermissionError as e:
                try:
                    log.info("waiting for lock release on %s (errno=%s): %s",
                             path.name, getattr(e, 'errno', '?'), e,
                             extra={'file_name': path.name})
                except Exception:
                    pass
                try:
                    time.sleep(backoff)
                except Exception:
                    pass
                backoff = min(backoff * 1.5, 5.0)
            except FileNotFoundError:
                return False
            except Exception:
                return True
        return False
    except BaseException:
        try:
            log.exception("_wait_until_readable failed unexpectedly for %s",
                          getattr(path, 'name', path))
        except Exception:
            pass
        return False


def quiesce_then_load(path: Path) -> None:
    """Wait for the file to stop changing, then process it. Bulletproofed —
    no error in any sub-step can take down the scheduler."""
    _lifecycle(f"qtl: ENTER {getattr(path, 'name', path)}")
    try:
        try:
            abs_path = str(path.resolve())
        except Exception:
            abs_path = str(path)
        _lifecycle(f"qtl: resolved -> {abs_path}")
        try:
            log.info("queued: %s", abs_path, extra={'file_name': path.name})
        except Exception:
            pass
        _lifecycle("qtl: log.info(queued) done")

        _lifecycle("qtl: starting quiesce loop")
        last_mtime = -1.0
        last_size = -1
        stable_since = None
        deadline = time.time() + 60
        _qtl_iter = 0
        while time.time() < deadline:
            _qtl_iter += 1
            _lifecycle(f"qtl: quiesce iter {_qtl_iter} (last_mtime={last_mtime}, last_size={last_size})")
            try:
                stat = path.stat()
                _lifecycle(f"qtl: stat ok mtime={stat.st_mtime} size={stat.st_size}")
            except FileNotFoundError:
                try:
                    log.warning("file disappeared before load: %s", abs_path,
                                extra={'file_name': path.name})
                except Exception:
                    pass
                return
            except Exception as e:
                try:
                    log.warning("stat failed on %s (%s); skipping", abs_path, e,
                                extra={'file_name': path.name})
                except Exception:
                    pass
                return
            if stat.st_mtime == last_mtime and stat.st_size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif (time.time() - stable_since) >= QUIESCE_SECS:
                    break
            else:
                stable_since = None
                last_mtime = stat.st_mtime
                last_size = stat.st_size
            try:
                time.sleep(0.5)
            except Exception:
                pass
            _lifecycle(f"qtl: after sleep, iter {_qtl_iter} done")

        _lifecycle("qtl: quiesce loop done, about to _wait_until_readable")
        try:
            ready = _wait_until_readable(path)
        except Exception:
            try:
                log.exception("_wait_until_readable threw for %s — skipping", path.name)
            except Exception:
                pass
            return
        if not ready:
            try:
                log.error("gave up waiting for lock release on %s; deferring",
                          path.name, extra={'file_name': path.name})
            except Exception:
                pass
            return

        _lifecycle(f"qtl: about to call load_one_file({path.name})")
        try:
            result = load_one_file(abs_path)
            _lifecycle(f"qtl: load_one_file returned: status={result.get('status') if isinstance(result, dict) else type(result).__name__}")
            try:
                if isinstance(result, dict) and result.get("status") == "error":
                    log.error("loaded %s -> %s", path.name, result, extra={'file_name': path.name})
                else:
                    log.info("loaded %s -> %s", path.name, result, extra={'file_name': path.name})
            except Exception:
                pass
        except Exception:
            try:
                log.exception("load_one_file failed for %s", abs_path)
            except Exception:
                pass
    except BaseException as _qtl_exc:
        _lifecycle(f"qtl: BaseException {_qtl_exc!r}")
        try:
            log.exception("quiesce_then_load: unexpected failure on %s",
                          getattr(path, 'name', path))
        except Exception:
            pass
    _lifecycle(f"qtl: EXIT {getattr(path, 'name', path)}")


class XlsxHandler(FileSystemEventHandler):
    """Watchdog handler: debounces events and dispatches to quiesce_then_load."""

    def _maybe_handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not is_target(path):
            return
        now = time.time()
        last = _LAST_SEEN.get(str(path), 0.0)
        if now - last < DEBOUNCE_SECS:
            return
        _LAST_SEEN[str(path)] = now
        try:
            quiesce_then_load(path)
        except Exception:
            log.exception("XlsxHandler: error processing %s (continuing)", path.name)

    def on_created(self, event):
        self._maybe_handle(event)

    def on_modified(self, event):
        self._maybe_handle(event)


def _get_nightly_hour(default: int = 22) -> int:
    """Read scheduled hour for nightly compute_outcomes from ref_settings."""
    try:
        with session_scope() as s:
            row = s.execute(text(
                "SELECT value FROM ref_settings WHERE key = 'outcomes_compute_hour'"
            )).first()
            return int(row[0]) if row and row[0] else default
    except Exception:
        return default


def run_nightly_outcomes() -> None:
    """Fire compute_outcomes + derive_rr for today + the drv_actionable stale-heal."""
    log.info("nightly: compute_outcomes starting")
    try:
        from etl.compute_outcomes import compute_outcomes
        result = compute_outcomes(dry_run=False)
        log.info("nightly: compute_outcomes done: %s", result)
    except Exception:
        log.exception("nightly: compute_outcomes crashed")

    log.info("nightly: derive_rr for today starting")
    try:
        from etl.db import session_scope
        from etl.derive import derive_rr
        today = date.today()
        with session_scope() as s:
            n = derive_rr(s, today)
        log.info("nightly: derive_rr done: %d rows for %s", n, today)
    except Exception:
        log.exception("nightly: derive_rr crashed")

    log.info("nightly: stale-heal starting")
    try:
        from etl.derive_freshness import run_stale_heal
        heal = run_stale_heal()
        log.info("nightly: stale-heal done: %s", heal)
    except Exception:
        log.exception("nightly: stale-heal crashed")


def _read_nightly_state(state_path: Path):
    """Return the ISO date in the state file, or None if missing/invalid.

    The file just contains a single line like '2026-05-18'. Used so the
    nightly job only fires once per day even if the scheduler restarts.
    """
    try:
        if not state_path.exists():
            return None
        raw = state_path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        from datetime import date as _date
        return _date.fromisoformat(raw)
    except Exception:
        return None


def _write_nightly_state(state_path: Path, day) -> None:
    """Record today's date so maybe_run_nightly won't re-fire today."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(day.isoformat(), encoding="utf-8")
    except Exception:
        log.exception("nightly: failed to write state file %s", state_path)


def maybe_run_nightly(state_path: Path) -> None:
    """If now >= scheduled hour and we haven't run today, fire the nightly job."""
    now = datetime.now()
    sched_hour = _get_nightly_hour()
    if now.hour < sched_hour:
        return
    last_run = _read_nightly_state(state_path)
    if last_run == now.date():
        return
    run_nightly_outcomes()
    _write_nightly_state(state_path, now.date())


def get_latest_processed_time() -> float:
    """Get the most recent processed_at timestamp from meta_file_processed.
    Returns 0 if no files have been processed yet (process all files).
    """
    with session_scope() as s:
        row = s.execute(text("""
            SELECT EXTRACT(EPOCH FROM MAX(processed_at)) FROM meta_file_processed
        """)).first()
    return float(row[0]) if row and row[0] else 0.0


def scan_initial(dirs: list[Path], handler: XlsxHandler) -> None:
    """
    On startup, scan each watched directory and queue files that need processing.

    We use a STRICT per-file check against meta_file_processed (file_path +
    file_mtime). A file is queued only if it has no record OR its mtime has
    changed since the last successful load. This replaces the older "global
    MAX(processed_at)" heuristic, which let recently-downloaded files leak
    through and be re-processed every restart even though they were already
    in meta_file_processed.
    """
    log.info("initial scan of %d dirs", len(dirs))

    # Pull the entire meta_file_processed table once (cheap — < 1k rows) so
    # the per-file check is a dict lookup, not a roundtrip per file.
    processed: dict[str, float] = {}
    processed_ci: dict[str, float] = {}
    try:
        with session_scope() as s:
            rows = s.execute(text("""
                SELECT file_path, file_mtime FROM meta_file_processed
                WHERE file_mtime IS NOT NULL
            """)).all()
            processed = {r[0]: float(r[1]) for r in rows}
            processed_ci = {r[0].lower(): float(r[1]) for r in rows}
    except Exception:
        log.exception("scan_initial: failed to load meta_file_processed; "
                      "falling back to per-file query path")

    log.info("scan_initial: %d files already in meta_file_processed", len(processed))

    skipped_count = 0
    queued_count = 0
    for d in dirs:
        if not d.exists():
            log.warning("watched dir missing: %s", d)
            continue
        for pattern in ["*.xlsx", "*.csv"]:
            for child in sorted(d.glob(pattern)):
                if not is_target(child):
                    continue
                try:
                    file_mtime = child.stat().st_mtime
                except Exception as e:
                    log.warning("could not stat %s: %s", child, e)
                    continue
                # Try both the raw path and the resolved path so a stored
                # canonical form still matches a glob result (Windows
                # case-insensitive paths, .resolve() normalization, etc.).
                try:
                    resolved = str(child.resolve())
                except Exception:
                    resolved = str(child)
                # Path lookup is case-insensitive on Windows. Build a
                # lowercase index of the processed dict so casing differences
                # between meta_file_processed and glob() don't cause re-loads.
                pcs = processed_ci.get(str(child).lower()) or processed_ci.get(resolved.lower())
                # CRITICAL: meta_file_processed.file_mtime is stored as REAL
                # (single-precision float, ~7 digits). Unix epoch timestamps
                # have 10+ digits so REAL loses ~30s of precision. Compare
                # as integer seconds with a 2-second tolerance to be safe.
                if pcs is not None and abs(int(pcs) - int(file_mtime)) <= 2:
                    skipped_count += 1
                    continue
                queued_count += 1
                _lifecycle(f"scan: about to process {child.name}")
                try:
                    quiesce_then_load(child)
                except Exception:
                    log.exception("scan_initial: error processing %s (continuing)",
                                  child.name)
                except BaseException:
                    _lifecycle(f"scan: BaseException from {child.name} — continuing")
                _lifecycle(f"scan: finished {child.name}")
                # Aggressively reclaim memory / handles between files to
                # delay native-extension leaks (psycopg, pandas, openpyxl)
                # that accumulate over many files and eventually crash.
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
                try:
                    from etl.db import get_engine
                    get_engine().dispose()
                except Exception:
                    pass

    log.info("scan_initial: queued %d, skipped %d already-processed files",
             queued_count, skipped_count)


def main() -> int:
    _lifecycle(">>> main() entered")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dirs", nargs="*", default=None,
                        help="Override watch dirs (otherwise read from ref_load_files)")
    parser.add_argument("--no-initial-scan", action="store_true",
                        help="Skip the startup scan of existing files")
    parser.add_argument("--no-nightly", action="store_true",
                        help="Disable the nightly compute_outcomes job")
    parser.add_argument("--force", action="store_true",
                        help="Override the single-instance lock (use only if "
                             "a previous scheduler crashed without cleaning up)")
    args = parser.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD is empty in .env.")
        return 2

    # Single-instance check — refuse to start if another scheduler is alive.
    heartbeat_path = Path(settings.etl_working_dir) / "scheduler.lock"
    blocked = acquire_lock(heartbeat_path, force=args.force)
    if blocked is not None:
        return 3

    src_dirs = args.dirs or get_watch_dirs()
    if not src_dirs:
        log.error("No source dirs found. Run tickers_initial_load.py first to populate ref_load_files.")
        return 2

    paths = [Path(d) for d in src_dirs]
    _lifecycle(f"watching {len(paths)} directories")
    # Per-directory listing demoted to debug (was noisy on every restart).
    # Missing dirs are still flagged at WARNING level so they don't go silent.
    missing = [p for p in paths if not p.exists()]
    log.info("watching %d directories (%d missing)", len(paths), len(missing))
    for p in paths:
        if p.exists():
            log.debug("  [exists]  %s", p)
        else:
            log.warning("  [MISSING] %s", p)

    # Write the heartbeat FIRST — before scan_initial — so the File Monitor
    # UI sees the scheduler as Running immediately. Otherwise scan_initial
    # can process several files synchronously (each waiting up to QUIESCE_SECS
    # + the actual load time) before main() ever gets to write the heartbeat,
    # leaving the UI's "Starting…" button hanging.
    log.info("scheduler lock acquired: %s (PID %d)", heartbeat_path, os.getpid())

    handler = XlsxHandler()

    try:
        observer = Observer()
    except Exception:
        log.exception("Observer() construction failed — running without watchdog")
        observer = None
    nightly_state_path = Path(settings.etl_working_dir) / "scheduler_nightly_last.txt"
    stop_flag_path = Path(settings.etl_working_dir) / "scheduler_stop.txt"
    if not args.no_nightly:
        log.info("nightly compute_outcomes scheduled (hour=%d, state=%s)",
                 _get_nightly_hour(), nightly_state_path)

    # Run scan_initial FIRST, single-threaded, BEFORE starting the watchdog.
    # Otherwise the watchdog Observer's C-extension worker thread runs in
    # parallel with our scan — any kernel error in ReadDirectoryChangesW
    # (and there are several on Windows when watched dirs see file churn)
    # can take down the whole process WITHOUT a Python exception.
    if not args.no_initial_scan:
        _lifecycle("about to call scan_initial() (BEFORE observer.start)")
        try:
            scan_initial(paths, handler)
            _lifecycle("scan_initial() returned cleanly")
        except Exception:
            try:
                log.exception("scan_initial failed — continuing to startup")
            except Exception:
                pass
        except BaseException:
            _lifecycle("scan_initial raised BaseException — continuing anyway")

    # NOW it is safe to start the watchdog.
    if observer is not None:
        for p in paths:
            try:
                if p.exists():
                    observer.schedule(handler, str(p), recursive=False)
            except Exception:
                log.exception("observer.schedule failed for %s (continuing)", p)

    if observer is not None:
        _lifecycle("about to call observer.start()")
        try:
            observer.start()
        except Exception:
            log.exception("observer.start failed — running without watchdog")
            observer = None
    _lifecycle("observer.start() returned; entering main loop")
    log.info("scheduler running. Ctrl+C to stop.")
    try:
        _lifecycle("entering main while-loop")
        tick = 0
        while True:
            time.sleep(1)
            tick += 1
            if tick <= 5 or tick % 10 == 0:
                _lifecycle(f"tick {tick}")
            if stop_flag_path.exists():
                log.info("stop flag detected - shutting down gracefully")
                stop_flag_path.unlink(missing_ok=True)
                observer.stop()
                break
            if not args.no_nightly and tick % 60 == 0:
                try:
                    maybe_run_nightly(nightly_state_path)
                except Exception:
                    try:
                        log.exception("maybe_run_nightly failed (continuing)")
                    except Exception:
                        pass
    except KeyboardInterrupt:
        _lifecycle("KeyboardInterrupt caught in main")
        try:
            log.info("shutting down...")
        except Exception:
            pass
        try:
            if observer is not None:
                observer.stop()
        except Exception:
            pass
    except Exception as e:
        _lifecycle(f"Exception caught in main: {e!r}")
        try:
            log.exception("scheduler encountered unexpected error: %s", e)
        except Exception:
            pass
        try:
            if observer is not None:
                observer.stop()
        except Exception:
            pass
    finally:
        _lifecycle("main() finally block — releasing lock")
        try:
            release_lock(heartbeat_path)
        except Exception:
            pass
    try:
        if observer is not None:
            observer.join(timeout=5)
    except Exception:
        pass
    return 0


def _safe_main() -> int:
    _lifecycle("_safe_main() entered")
    """Wrap main() so a crash leaves a readable traceback in the crash log
    AND in meta_scheduler_log, instead of dying silently behind DETACHED_PROCESS.
    Also releases the heartbeat lock so the UI does not show a phantom scheduler."""
    try:
        return main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt at module level - exiting")
        return 130
    except BaseException as exc:
        _lifecycle(f"_safe_main caught BaseException: {exc!r}")
        tb = traceback.format_exc()
        try:
            log.error("FATAL scheduler crash: %s\n%s", exc, tb)
        except Exception:
            pass
        try:
            sys.stderr.write(f"\nFATAL scheduler crash: {exc!r}\n{tb}\n")
            sys.stderr.flush()
        except Exception:
            pass
        try:
            from config.settings import settings as _s
            hb = Path(_s.etl_working_dir) / "scheduler_heartbeat.txt"
            hb.unlink(missing_ok=True)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    _lifecycle("=== __main__ entry ===")
    raise SystemExit(_safe_main())
