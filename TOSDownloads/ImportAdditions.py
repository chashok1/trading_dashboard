"""
ImportAdditions.py (2026-08-18 -- Program 2: additions-only import)

Imports just a delta of new symbols into their target watchlists, instead
of a full re-import of everything (LoadWatchlists.py, Program 1). Reuses
the exact same edit_watchlist() building block -- the only difference is
where the symbol list comes from: one shared additions file (grouped by
target watchlist) instead of one file per watchlist.

Additions file format -- one row per symbol, two columns:
    tos_symbol,watchlist_name
    AAPL,WL1
    MSFT,WL1
    XOM,WL3
Header row optional (skipped automatically if the first cell isn't a
plausible symbol -- see _looks_like_header()). Rows are grouped by
watchlist_name; one edit_watchlist() call per group, so a single additions
file can target many different watchlists in one run.

Per-watchlist screenshots required -- same convention as LoadWatchlists.py/
WL99 (menu_<name>.png, Watchlist_<name>.png, Edit<name>.png,
EditDialog<name>.png). A watchlist with no matching images is skipped with
a warning, same skip-not-fail contract as everything else in this tool.

Each group's symbol list is written to a small per-watchlist temp file (one
symbol per line) in working_dir -- working_dir/additions_work/<watchlist>.txt
-- since edit_watchlist() (like do_reloadwl99()) needs an actual file path
to type into TOS's file picker, not an in-memory list. These temp files are
overwritten fresh every run and never read as an input by anything else --
safe to ignore/delete between runs.

Usage:
    python ImportAdditions.py <additions_file> <working_dir> <images_folder> <lock_file_path>
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from TOSDownloads import (
    acquire_lock, release_lock, ensure_tos_active, edit_watchlist,
    write_filenames_to_file,
)


def _looks_like_header(row):
    """True if `row`'s first cell reads like a column header ('tos_symbol',
    'symbol', ...) rather than an actual ticker -- so a header row, if
    present, is skipped rather than typed into TOS as a literal symbol."""
    if not row:
        return False
    first = row[0].strip().lower()
    return first in ('tos_symbol', 'symbol', 'ticker')


def read_additions(additions_file):
    """Returns {watchlist_name: [symbols]} grouped from the additions file.
    Blank lines and a possible header row are skipped; rows with fewer
    than 2 columns are skipped with a warning (malformed, not fatal)."""
    groups: dict = {}
    with open(additions_file, newline='') as f:
        reader = csv.reader(f)
        rows = [r for r in reader if any(c.strip() for c in r)]
    if rows and _looks_like_header(rows[0]):
        rows = rows[1:]
    for row in rows:
        if len(row) < 2:
            print(f"⚠️ Skipping malformed row (need tos_symbol,watchlist_name): {row}")
            continue
        symbol, watchlist_name = row[0].strip(), row[1].strip()
        if not symbol or not watchlist_name:
            continue
        groups.setdefault(watchlist_name, []).append(symbol)
    return groups


def main(additions_file, working_dir, images_folder):
    if not os.path.exists(additions_file):
        print(f"Error: additions file '{additions_file}' does not exist.")
        sys.exit(1)

    groups = read_additions(additions_file)
    if not groups:
        print(f"No additions found in {additions_file} -- nothing to import.")
        return

    total_symbols = sum(len(v) for v in groups.values())
    print(f"Found {total_symbols} addition(s) across {len(groups)} watchlist(s): "
          f"{', '.join(groups.keys())}")

    ensure_tos_active(images_folder)

    work_dir = os.path.join(working_dir, 'additions_work')
    os.makedirs(work_dir, exist_ok=True)
    recipe_dir = os.path.dirname(os.path.abspath(__file__))

    done, skipped = [], []
    for watchlist_name, symbols in groups.items():
        symbols_file = os.path.join(work_dir, f"{watchlist_name}.txt")
        write_filenames_to_file(sorted(set(symbols)), symbols_file, label="symbols")
        ran = edit_watchlist(watchlist_name, symbols_file, images_folder, recipe_dir)
        (done if ran else skipped).append(watchlist_name)

    print(f"\n✅ Added to: {', '.join(done) if done else '(none)'}")
    if skipped:
        print(f"⚠️ Skipped (missing images): {', '.join(skipped)}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python ImportAdditions.py <additions_file> <working_dir> <images_folder> <lock_file_path>")
        print("Example: python ImportAdditions.py additions.csv C:\\TOS_WatchlistLoads C:\\...\\Images C:\\...\\TOS.lock")
        print("  additions_file: tos_symbol,watchlist_name per row (header row optional).")
        sys.exit(1)

    additions_file_arg = sys.argv[1]
    working_dir_arg = sys.argv[2]
    images_folder_arg = sys.argv[3]
    lock_file_path_arg = sys.argv[4]

    try:
        acquire_lock(lock_file_path_arg)
        main(additions_file_arg, working_dir_arg, images_folder_arg)
    finally:
        release_lock()
