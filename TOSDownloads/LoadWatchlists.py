"""
LoadWatchlists.py (2026-08-18 rewrite -- Program 1: full watchlist import)

Reads stock-symbol files from a folder and imports each into its
correspondingly-named TOS watchlist, via TOSDownloads.py's edit_watchlist()
-- the same generic, placeholder-substituted "Edit > Import > Load from
File" mechanism do_reloadwl99() now uses for WL99. One shared recipe
(TOSDownloads/EditWatchlist.csv) works for any watchlist name; nothing
here is specific to WL99 or hardcoded per watchlist.

2026-08-18: rewritten -- the original version of this file called
import_symbols_into_watchlist(), which was removed the same day this file
was first written (in a parallel session, as part of the multi-watchlist
redesign) -- it never actually ran successfully. This version calls
edit_watchlist() instead, which replaced it.

File naming convention: <WatchlistName>.csv or <WatchlistName>.txt in the
given symbols folder. The file's own basename (without extension) IS the
target watchlist's name -- e.g. WL1.csv's symbols get imported into the
watchlist named "WL1". Files are otherwise untouched: this program only
reads them (to type their path into TOS's file picker), it never writes
or deletes them.

Per-watchlist screenshots required -- same convention as WL99's images,
for a watchlist named e.g. "WL1":
    menu_WL1.png        -- the dropdown's hover/context-menu item for WL1
    Watchlist_WL1.png   -- the secondary dropdown/arrow revealed after that
    EditWL1.png         -- the "Edit 'WL1'..." menu item
    EditDialogWL1.png   -- confirms the Edit Watchlist dialog opened for WL1
A watchlist with no matching images in the images folder is skipped with a
warning, not treated as a fatal error, so you can add watchlists
incrementally as you capture their screenshots. Everything else (Import /
Load from File / Select file / Found / OK / Save) reuses the SAME shared
generic images already captured for WL99's own reload flow.

This program is import-only, by design -- it does not export the
watchlist afterward (unlike RELOADWL99, which needs the merge stage to
pick up its result). If you want an export+merge to follow, that's a
straightforward extension reusing download_watchlist().

Usage:
    python LoadWatchlists.py <symbols_folder> <images_folder> <lock_file_path>
"""
import os
import sys

# Reuse TOSDownloads.py's already-built, already-tested automation
# primitives rather than duplicating them -- this file lives alongside it.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from TOSDownloads import (
    acquire_lock, release_lock, ensure_tos_active, edit_watchlist,
)


def find_watchlist_files(symbols_folder):
    """Returns {watchlist_name: absolute_file_path} for every .csv/.txt
    file directly in symbols_folder, keyed by basename without extension.
    If both <name>.csv and <name>.txt exist for the same name, .csv wins
    (arbitrary but deterministic) and a warning is printed."""
    found = {}
    for fname in sorted(os.listdir(symbols_folder)):
        base, ext = os.path.splitext(fname)
        if ext.lower() not in ('.csv', '.txt'):
            continue
        full_path = os.path.abspath(os.path.join(symbols_folder, fname))
        if base in found:
            print(f"⚠️ Both a .csv and .txt exist for '{base}' -- keeping {found[base]}, ignoring {full_path}")
            continue
        found[base] = full_path
    return found


def main(symbols_folder, images_folder):
    if not os.path.isdir(symbols_folder):
        print(f"Error: symbols folder '{symbols_folder}' does not exist.")
        sys.exit(1)

    ensure_tos_active(images_folder)

    watchlist_files = find_watchlist_files(symbols_folder)
    if not watchlist_files:
        print(f"No .csv/.txt files found in {symbols_folder} -- nothing to load.")
        return

    print(f"Found {len(watchlist_files)} watchlist file(s): {', '.join(watchlist_files.keys())}")

    recipe_dir = os.path.dirname(os.path.abspath(__file__))
    done, skipped = [], []
    for watchlist_name, file_path in watchlist_files.items():
        ran = edit_watchlist(watchlist_name, file_path, images_folder, recipe_dir)
        (done if ran else skipped).append(watchlist_name)

    print(f"\n✅ Loaded: {', '.join(done) if done else '(none)'}")
    if skipped:
        print(f"⚠️ Skipped (missing images): {', '.join(skipped)}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python LoadWatchlists.py <symbols_folder> <images_folder> <lock_file_path>")
        print("Example: python LoadWatchlists.py C:\\TOS_WatchlistLoads C:\\...\\Images C:\\...\\TOS.lock")
        print("  symbols_folder: <WatchlistName>.csv or .txt per watchlist to load (e.g. WL1.csv -> \"WL1\").")
        sys.exit(1)

    symbols_folder_arg = sys.argv[1]
    images_folder_arg = sys.argv[2]
    lock_file_path_arg = sys.argv[3]

    try:
        acquire_lock(lock_file_path_arg)
        main(symbols_folder_arg, images_folder_arg)
    finally:
        release_lock()
