import pyautogui
import time
import pandas as pd
import sys
import os
import pygetwindow as gw
import send2trash
from pyautogui import ImageNotFoundException
import threading
import shutil
import queue
from typing import List, Dict, Any
import csv
import datetime
import re
import chardet
import msvcrt

pyautogui.useImageNotFoundException(False)


# --- CONFIGURATION CONSTANTS ---
pyautogui.PAUSE = 0.5

COL_SET_COMBOBOX_X, COL_SET_COMBOBOX_Y = 270, 55
DESIRED_COL_SET_X, DESIRED_COL_SET_Y = 270, 196
WATCHLIST_COMBOBOX_X, WATCHLIST_COMBOBOX_Y = 115, 55
#hamburger_X, hamburger_Y =  871, 55
EXPORT_MENU_ENTRY_Y = 215

export_menu_X = 871
elapsed_time = 60
fd = None
incomplete_files = []
last_auto_pos = None

# 2026-08-16: merged in from MergeExports.py so one script (same 4 required
# CLI args as the old TOSDownloads.py) both downloads the TOS watchlist
# fragments AND merges them into the final consolidated file. See __main__
# and run_pipeline() at the bottom. Original standalone MergeExports.py is
# left untouched alongside this file for reference.
WORD_TO_FIND = 'loading'

# 2026-08-19: RELOADWL99 reprocess/retry tuning -- see run_recipe_rows()'s
# RELOADWL99 branch. RELOAD_SYMBOL_THRESHOLD is roughly what a single WL99
# reload+import can realistically absorb in one pass; above that, reprocess
# the individual stuck watchlists first rather than dumping everything on
# WL99 at once. Both attempt caps exist so a genuinely-stuck symbol (bad
# ticker, TOS glitch, delisted) can't loop the automation forever.
RELOAD_SYMBOL_THRESHOLD = 55
MAX_REPROCESS_ATTEMPTS = 3
MAX_WL99_RETRY_ATTEMPTS = 3

# 2026-08-20: column-set toggle, tried before each reprocess attempt (see
# toggle_column_set_away_and_back() / the RELOADWL99 branch). Every recipe
# CSV (TOSD/TOSL/TOSO/TOSW.csv) opens the same column-set combobox at
# (266,7) then picks its own entry from one vertical list, spaced 24px
# apart -- known entries today: TOSD=172, TOSL=196, TOSO=220, TOSW=244.
# COLUMN_SET_MAX_Y is the bottom-most of those, used only to pick which
# direction (+/-) lands on a valid, different entry instead of an offset
# beyond the last item. Deliberately generic (no per-type name mapping) --
# just "switch to *a* different entry, then back", repeated
# COLUMN_SET_TOGGLE_REPEAT times per reprocess attempt since a single
# switch doesn't always force TOS to recompute.
COLUMN_SET_ROW_SPACING = 24
COLUMN_SET_MAX_Y = 244
COLUMN_SET_TOGGLE_REPEAT = 3


# --- LOCKING (shared by both stages -- single copy; each original script
# had its own identical acquire_lock/release_lock) ---

def acquire_lock(lock_path, check_interval=0.5):
    global fd
    print("Trying to acquire lock....")
    # 'a+' opens for update (read/write) and creates file if needed
    fd = open(lock_path, 'a+')
    while True:
        try:
            # Move to the start of the file to lock from the beginning
            fd.seek(0)
            # Lock 1 byte. LK_NBLCK raises OSError if already locked
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            print("Lock Acquired")
            return
        except OSError:
            # Lock is held by another process
            time.sleep(check_interval)

def release_lock():
    global fd
    if fd:
        try:
            fd.seek(0)
            # Unlock the byte
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            print("Lock Released")
        finally:
            fd.close()
            # 2026-08-17: fd=None makes a second release_lock() call a safe
            # no-op (fd stays truthy on a closed file object otherwise, so a
            # repeat call would hit fd.seek(0) on an already-closed handle).
            # Needed now that run_pipeline() releases the lock itself right
            # after the download stage -- __main__'s own try/finally still
            # calls release_lock() unconditionally afterward as a safety net.
            fd = None

def _lock_free_snapshot(lock_path):
    """True non-blocking check: is TOS.lock free RIGHT NOW? Unlike
    acquire_lock(), this never waits or retries -- an immediate OSError just
    means "held by someone else at this instant", returned as False rather
    than looped on. Used by is_lock_free() below; acquire_lock() itself is
    the wrong building block for a contention check precisely because it
    blocks until it succeeds, silently absorbing however long the wait was."""
    fd_local = open(lock_path, 'a+')
    try:
        fd_local.seek(0)
        msvcrt.locking(fd_local.fileno(), msvcrt.LK_NBLCK, 1)
        fd_local.seek(0)
        msvcrt.locking(fd_local.fileno(), msvcrt.LK_UNLCK, 1)
        return True
    except OSError:
        return False
    finally:
        fd_local.close()

def is_lock_free(lock_path, wait_time=5):
    """Contention check for TOS.lock (2026-08-17, extracted so __main__'s
    end-of-run 'yield to other programs' loop and the Excel auto-open gate
    share one implementation instead of duplicating it): snapshot whether
    it's free right now, wait wait_time seconds, then snapshot again --
    returns True only if BOTH snapshots saw it free.

    2026-08-17 bug fix: the first version of this used acquire_lock() (which
    blocks/retries until it succeeds) for each ping, timing how long that
    took -- but that means active contention gets silently absorbed by the
    first ping's own wait, and by the time the second ping runs the holder
    has often already released, making the elapsed time look clean even
    though there WAS contention the whole time. Confirmed with a real
    holder process: the old version reported "free" while another process
    demonstrably held the lock throughout. Fixed by using true non-blocking
    snapshots (_lock_free_snapshot(), never waits) for both checks instead.

    The two-snapshot-with-a-wait shape (rather than a single check) is kept
    deliberately -- it also catches a contender that's about to grab the
    lock but hasn't yet (e.g. another TOSType queued right behind this one),
    giving it wait_time seconds to actually acquire before this declares
    the lock clear."""
    if not _lock_free_snapshot(lock_path):
        return False
    time.sleep(wait_time)
    return _lock_free_snapshot(lock_path)

def read_filenames_from_file(input_path: str) -> List[str]:
    """
    Reads the content of the specified text file, treating each line
    as a filename, and returns them as a list.
    """
    filenames = []
    try:
        # Use 'r' mode to open the file for reading
        with open(input_path, 'r') as f:
            # Read all lines from the file
            lines = f.readlines()

            # Strip whitespace (including the newline character '\n') from each line
            for line in lines:
                filenames.append(line.strip())

        print(f"✅ Successfully read {len(filenames)} filenames from: {os.path.abspath(input_path)}")
        return filenames

    except FileNotFoundError:
        print(f"❌ Error: The file was not found at '{input_path}'.")
        return []
    except IOError as e:
        print(f"❌ Error reading file '{input_path}': {e}")
        return []

def is_file_in_incomplete_list(target_filename: str) -> bool:
    """
    Checks if a target filename exists in the provided list of filenames.
    """
    if len(incomplete_files)==0:
        return False

    # The 'in' operator efficiently checks for membership in a list
    if target_filename in incomplete_files:
        return True
    else:
        return False

# --- WINDOW & FOCUS UTILITIES ---

def get_active_window_title():
    """Return the title of the currently active window."""
    try:
        win = gw.getActiveWindow()
        return win.title.lower() if win else None
    except Exception:
        return None

def resolve_image_path(image_path):
    """
    Resolves an image path to an absolute path.
    If the path is already absolute, returns it unchanged.
    If relative, prepends the folder where the script or executable resides.
    """
    if os.path.isabs(image_path):
        return image_path

    # Determine base directory (works for .py and .exe)
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    full_path = os.path.join(base_dir, image_path)
    return os.path.normpath(full_path)

def is_tos_active():
    """Check if ThinkorSwim is the current active window."""
    title = get_active_window_title()
    return title and "thinkorswim" in title.lower()
def ensure_tos_in_focus(expected_list=None):
    """
    Verify that either ThinkorSwim or one of the allowed expected windows
    (like 'Save As' or 'Watchlist <name>') is currently active.
    If not, pause automation and alert user.
    """
    if expected_list is None:
        # Accept ThinkorSwim main window and its export/save dialogs, plus
        # (2026-08-16) the Edit Watchlist / Symbols Import dialogs used by
        # ReloadWL99.csv -- every ui_click() call (including the ones inside
        # do_clickexists()) goes through this default list, so without these
        # it false-alarms "focus on another window" on every click while
        # legitimately inside that flow, not just once.
        expected_list = ["thinkorswim", "save", "open", "watchlist", "edit watchlist", "symbols import"]

    title = get_active_window_title()
    if not title:
        return

    title_lower = title.lower()
    for expected in expected_list:
        if expected.lower() in title_lower:
            return  # Active window matches an allowed title → OK

    # If focus moved elsewhere, alert and pause automation
    msg = (
        f"⚠️ Detected focus on another window:\n\n'{title}'\n\n"
        "This may indicate a popup or wrong click.\n\n"
        "Please check the ThinkorSwim window, then click Yes to continue."
    )
    response = pyautogui.confirm(text=msg, title='Confirmation', buttons=['Yes', 'No'])

    if response == 'Yes':
        return
    time.sleep(1)
    print("Exiiting... Start again")
    sys.exit(1)

def input_with_timeout(prompt, timeout=5):
    q = queue.Queue()

    def read_input():
        q.put(input(prompt))

    t = threading.Thread(target=read_input)
    t.daemon = True
    t.start()

    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return None

def wait_for_mouse_idle(idle_seconds=5):
    last_pos = pyautogui.position()
    idle_start = time.time()

    while True:
        time.sleep(1)
        current_pos = pyautogui.position()

        if current_pos != last_pos:
            print("Mouse moved → reset timer")
            last_pos = current_pos
            idle_start = time.time()
        else:
            # Check if idle time reached
            if time.time() - idle_start >= idle_seconds:
                return True

def ensure_tos_active(images_folder):

    burg_menu_img_path = os.path.join(images_folder,"export_menu.png")
    maximized_img_path = os.path.join(images_folder,"maximized.png")
    print("Waiting for ThinkorSwim window...")

    tos_window = None
    prev_active_win = ""
    while tos_window is None:

        windows = [w for w in gw.getWindowsWithTitle("thinkorswim") if not w.isMinimized]

        if windows:
            active_window = get_active_window_title()
            if active_window:
                if prev_active_win != active_window:
                    print(f"active window - {active_window}")
                    prev_active_win = active_window

                if "thinkorswim" in active_window:
                    tos_window = windows[0]
                    max_image_location = get_image_location(maximized_img_path)
                    if max_image_location:
                        print(f"active window - {active_window} {tos_window.left} {tos_window.top} {tos_window.width} {tos_window.height}")
                    #if (tos_window.top==0 and tos_window.left==0 and (tos_window.width==1366 or tos_window.width==1920) and (tos_window.height==720 or tos_window.height==1032)):
                        image_location = get_image_location(burg_menu_img_path)
                        if image_location:
                            print(f"Image {burg_menu_img_path} found")
                            print("✅ ThinkorSwim is now active and maximized. Waiting for mouse idle...")
                            wait_for_mouse_idle(10)
                            return tos_window
                            #break
                    else:
                        tos_window=None
                        print("⏳ ThinkorSwim found but not miximized.")


        if (not tos_window) or (not windows):
            # Ask user to exit with a 3-second timeout
            user_input = input_with_timeout("⏳ ThinkorSwim not found or not miximized. Please open and log in. Type 'y' to exit (Or will retry in 5 seconds...): ", 5)

            if user_input and user_input.lower() == 'y':
                print("\nExiting...")
                sys.exit(1)

            continue


    # # Window found, proceed to activate and maximize
    # try:
    #     time.sleep(5)
    #     tos_window.activate()
    #     time.sleep(1)
    #     tos_window.maximize()
    #     time.sleep(1)
    #     print("✅ ThinkorSwim is now active and maximized.")
    #     return tos_window
    # except Exception as e:
    #     print(f"⚠️ Could not activate or maximize ThinkorSwim: {e}")
    #     print("Please ensure it's open and visible.")
    #     sys.exit(1)

# --- CORE FUNCTIONS ---
def set_column_set():
    """Selects the desired column set for the watchlist."""
    print("Setting Column Set...")
    ui_click(COL_SET_COMBOBOX_X, COL_SET_COMBOBOX_Y)
    ui_click(DESIRED_COL_SET_X, DESIRED_COL_SET_Y)
    print("✅ Column set applied.")

def toggle_column_set_away_and_back(df, images_folder):
    """RELOADWL99 reprocess helper (2026-08-20): switches the column-set
    combobox to a different entry and back to this recipe's own entry,
    COLUMN_SET_TOGGLE_REPEAT times -- tried before each reprocess attempt,
    ahead of falling back to reloading the missing symbols into WL99.
    ThinkOrSwim sometimes gets individual cells stuck 'Loading' forever on
    the currently-applied column set but resolves them the moment the set
    changes and changes back, without needing any symbol re-import at all.

    Reads its own coordinates straight from df instead of a hardcoded
    per-type map: every recipe's first two rows are `Click, TOS Column Set`
    -- row 0 opens the combobox (266,7), row 1 picks this recipe's own
    entry (e.g. TOSL.csv's own Y=196) and carries a target_image
    (e.g. TOSL.png) confirming it applied. 'A different entry' is just
    that row's own Y +/- COLUMN_SET_ROW_SPACING, picking whichever
    direction stays within the known list (COLUMN_SET_MAX_Y) -- so this
    works for any of TOSD/TOSL/TOSO/TOSW.csv without naming them.

    No-op (with a warning) if a recipe doesn't have the expected two rows,
    e.g. if it's ever run standalone without them."""
    click_rows = df[(df['Type'] == 'Click') & (df['Name'] == 'TOS Column Set')]
    if len(click_rows) < 2:
        print("⚠️ toggle_column_set_away_and_back: recipe is missing its 'TOS Column Set' "
              "rows -- skipping the toggle.")
        return

    open_x, open_y = int(click_rows.iloc[0]['X']), int(click_rows.iloc[0]['Y'])
    own_x, own_y = int(click_rows.iloc[1]['X']), int(click_rows.iloc[1]['Y'])
    other_y = own_y + COLUMN_SET_ROW_SPACING if own_y + COLUMN_SET_ROW_SPACING <= COLUMN_SET_MAX_Y \
        else own_y - COLUMN_SET_ROW_SPACING

    print(f"--- Toggling column set away ({own_y}) and back, x{COLUMN_SET_TOGGLE_REPEAT}, "
          "to force TOS to recompute stuck cells before reprocessing. ---")
    for i in range(COLUMN_SET_TOGGLE_REPEAT):
        ui_click(open_x, open_y, "TOS Column Set (open)")
        ui_click(own_x, other_y, "TOS Column Set (switch away)")
        time.sleep(2.0)
        ui_click(open_x, open_y, "TOS Column Set (reopen)")
        ui_click(own_x, own_y, "TOS Column Set (switch back)")
        time.sleep(2.0)
        print(f"    toggle {i + 1}/{COLUMN_SET_TOGGLE_REPEAT} done.")

def wait_if_mouse_moved():
    """If the mouse has moved since our last automated action, someone's
    interacting with it by hand -- wait until it's idle again before the
    next automated action. Factored out of ui_click() (2026-08-16) so
    do_typefile() can reuse the same guard before typing, not just clicks."""
    global last_auto_pos
    if last_auto_pos and last_auto_pos != pyautogui.position():
        print("Mouse moved by user. Waiting for mouse idle...")
        wait_for_mouse_idle(10)

def ui_click(x, y, name=""):
    #print(f"{name}: clicking at ({x}, {y}) ...")
    global last_auto_pos
    wait_if_mouse_moved()
    ensure_tos_in_focus()
    time.sleep(0.5)
    pyautogui.click(x, y)
    last_auto_pos=pyautogui.position()
    time.sleep(0.25)

def count_image_instances(image_path, label="TargetImage", confidence=0.8, timeout=2):
    """
    Find and count the number of instances of an image visible on the screen.
    Returns (count, centers_list) — never raises an exception.
    """
    print(f"🔍 Scanning for instances of {label} via image: {image_path}")
    start = time.time()
    found_locations = []

    while time.time() - start < timeout:
        try:
            locations = list(pyautogui.locateAllOnScreen(image_path, confidence=confidence))
            if locations:
                found_locations = [pyautogui.center(loc) for loc in locations]
                print(f"✅ Found {len(found_locations)} instances of {label}")
                return len(found_locations), found_locations
        except ImageNotFoundException:
            pass
        except Exception as e:
            print(f"⚠️ Error while searching for {label}: {e}")
            break
        time.sleep(0.5)

    #print(f"❌ No instances of {label} found within {timeout} seconds.")
    return 0, []


def count_images_in_folder(folder_path, prefix, confidence=0.8, timeout=0.5):
    total_count = 0
    #print(f"\n📁 Searching folder '{folder_path}' for files starting with '{prefix}'")

    for file_name in os.listdir(folder_path):
        if file_name.lower().endswith(".png") and file_name.startswith(prefix):
            image_path = os.path.join(folder_path, file_name)
            label = os.path.splitext(file_name)[0]
            count, _ = count_image_instances(image_path, label=label,
                                             confidence=confidence, timeout=timeout)
            total_count += count

    print(f"📊 Total instances of '{prefix}*': {total_count}")

    return total_count

def get_image_location(image_path, label="BurgerMenu", confidence=0.8, timeout=5):
    # Try locating the image
    print(f"🔍 Looking for {label} via image: {image_path}")
    start = time.time()
    while time.time() - start < timeout:
        location = pyautogui.locateOnScreen(image_path, confidence=confidence)
        if location:
            return location
        time.sleep(0.5)
    return None

def click_image_or_capture_fallback(image_path, label="BurgerMenu", confidence=0.8, timeout=4):
    """
    Try to find an image on screen and click it. If not found, prompt user to click manually.
    Saves coordinates for future use.
    """
    global export_menu_X
    # Try locating the image
    print(f"🔍 Looking for {label} via image: {image_path}")
    start = time.time()
    while time.time() - start < timeout:
        location = pyautogui.locateOnScreen(image_path, confidence=confidence)
        if location:
            center = pyautogui.center(location)
            export_menu_X = center.x
            ui_click(center.x,center.y)
            print(f"✅ Clicked {label} at {center}")
            return center
        time.sleep(0.5)

    # Image not found — fallback
    print(f"⚠️ Could not find {label} on screen.")
    pyautogui.alert(
        text=f"Please manually click on the '{label}' in TOS window.\n"
             f"After clicking, press OK to capture its coordinates.",
        title="Manual Click Required",
        button="OK"
    )

    # Wait for user to click manually
    print("Waiting for your click...")
    time.sleep(5)  # Give time for user to click

    x, y = pyautogui.position()
    print(f"🖱️ Captured coordinates for {label}: ({x}, {y})")
    export_menu_X = x

    # Click on that point now
    ui_click(x, y)
    print(f"✅ Clicked {label} using captured coordinates.")
    return (x, y)

def add_to_incomplete_list(file_name):
    fname = os.path.basename(file_name)
    if fname not in incomplete_files:
        incomplete_files.append(fname)
        print(f"Added incomplete file {fname} to the list.")

def remove_from_incomplete_list(file_name):
    fname = os.path.basename(file_name)
    if fname in incomplete_files:
        incomplete_files.remove(fname)
        print(f"{fname} removed from the list")

def check_loading_threshold_from_csv(file_path: str, lines_to_skip: int = 3, target_word: str = 'loading', threshold: float = 0.70) -> bool:
    if not os.path.exists(file_path):
        print(f"Error: File not found at path: {file_path}")
        return False

    try:
        # Read the CSV file into a DataFrame
        df = pd.read_csv(file_path, skiprows=lines_to_skip)
    except pd.errors.EmptyDataError:
        print("Error: The CSV file is empty.")
        return False
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return False

    if df.empty:
        return False

    # Convert all object (string) columns to string type and fill NaNs
    df_str = df.select_dtypes(include=[object]).astype(str).fillna('')

    # Create a boolean mask indicating if the target_word is found in ANY column for each row
    # The 'str.contains' is applied element-wise. 'stack' converts the DataFrame to a Series,
    # and 'any(level=0)' checks if True exists for any column within a row (level 0 is the row index).
    contains_word = df_str.apply(
        lambda col: col.str.contains(target_word, case=False, na=False)
    ).any(axis=1)

    # Count the number of rows that DO NOT contain the word
    rows_without_word_count = len(df) - int(contains_word.sum())

    # Calculate the proportion
    proportion_without_word = rows_without_word_count / len(df)

    if proportion_without_word <1:
        add_to_incomplete_list(file_path)
    else:
        remove_from_incomplete_list(file_path)

    # Check the condition
    return proportion_without_word >= threshold or len(df)<5

def extract_loading_symbols(file_path: str, lines_to_skip: int = 3, target_word: str = 'loading') -> list:
    """Scan an exported watchlist fragment for rows still containing
    target_word and return the symbols (first column) for those rows.
    Companion to check_loading_threshold_from_csv() above -- that function
    only computes a file-level pass/fail threshold (a file can pass the
    70% threshold while still having a handful of individually-stuck
    symbols in it), so it can't be reused directly for this. Called right
    after each watchlist's own export (2026-08-17), so LoadingSymbols.txt
    accumulates from THIS run's own exports as they happen, not a stale
    snapshot from a previous run. Returns [] on any read error, same
    defensive spirit as check_loading_threshold_from_csv."""
    if not os.path.exists(file_path):
        return []
    try:
        df = pd.read_csv(file_path, skiprows=lines_to_skip)
    except Exception:
        return []
    if df.empty:
        return []
    df_str = df.select_dtypes(include=[object]).astype(str).fillna('')
    contains_word = df_str.apply(
        lambda col: col.str.contains(target_word, case=False, na=False)
    ).any(axis=1)
    stuck_rows = df[contains_word]
    if stuck_rows.empty:
        return []
    return stuck_rows.iloc[:, 0].astype(str).tolist()

def find_genuinely_stuck_symbols(save_folder, lines_to_skip: int = 3, target_word: str = 'loading') -> set:
    """Scans every fragment CSV in save_folder and returns only the symbols
    that are genuinely STILL stuck -- i.e. every sighting of that symbol,
    across every fragment, shows target_word, with no fragment anywhere
    holding resolved (non-loading) data for it.

    2026-08-17: this exists because a naive per-file union of
    extract_loading_symbols() results (what merge-only mode's RELOADWL99
    trigger first used) re-flags a symbol forever once it's ever been seen
    stuck in ANY fragment -- even after a later export (e.g. WL99's own
    reload+export) already resolved it elsewhere. Confirmed in practice:
    a second merge-only run kept reloading the original stuck list even
    though the newer WL99 export had proper data for some of them. This
    mirrors monitor_directory()'s own per-symbol logic instead (a resolved
    sighting always wins over a stuck one, regardless of which file or how
    old), so only symbols with NO resolved sighting anywhere come back."""
    stuck, resolved = set(), set()
    if not os.path.isdir(save_folder):
        return stuck
    for fname in os.listdir(save_folder):
        if not fname.lower().endswith('.csv'):
            continue
        fpath = os.path.join(save_folder, fname)
        try:
            df = pd.read_csv(fpath, skiprows=lines_to_skip)
        except Exception:
            continue
        if df.empty:
            continue
        df_str = df.select_dtypes(include=[object]).astype(str).fillna('')
        contains_word = df_str.apply(
            lambda col: col.str.contains(target_word, case=False, na=False)
        ).any(axis=1)
        symbols = df.iloc[:, 0].astype(str)
        stuck.update(symbols[contains_word])
        resolved.update(symbols[~contains_word])
    return stuck - resolved

def normalize_for_reimport(symbol):
    """TOS renders a specific-month futures contract with a bracketed
    expiration suffix in exports (e.g. "/BTC[Q26]"), but re-importing that
    exact text via Edit > Import > Load from File errors out -- confirmed
    2026-08-17. TOS's import only accepts the root symbol (e.g. "/BTC"),
    which resolves to whichever contract is currently front-month/
    continuous. Strips everything from the first "[" onward; symbols
    without brackets (the common case -- plain equities/ETFs) pass through
    unchanged. Deliberately NOT applied in find_genuinely_stuck_symbols()'s
    own stuck-vs-resolved comparison -- different expiration months are
    genuinely different instruments there, and collapsing them would wrongly
    treat one month's resolved data as covering another's. This only matters
    at the point a symbol is about to be typed into TOS's import dialog."""
    bracket_index = symbol.find('[')
    return symbol[:bracket_index] if bracket_index != -1 else symbol

def sync_loading_symbols_file(save_folder, symbols):
    """Overwrite (not append) LoadingSymbols.txt with exactly this symbol
    set. append_loading_symbols() below only ever unions new stuck symbols
    in -- it's never trimmed mid-run, so by the time do_reloadwl99() is
    retried a 2nd/3rd time, LoadingSymbols.txt still holds every symbol
    that was EVER stuck this run, including ones already resolved by an
    earlier reprocess pass or WL99 attempt. do_reloadwl99()'s reload step
    reads that file directly (not find_genuinely_stuck_symbols()), so
    without this it redundantly re-imports already-resolved symbols on
    every retry -- a full extra TOS click-through cycle for nothing.
    Call this with the current, accurate stuck set (from
    find_genuinely_stuck_symbols()) right before each do_reloadwl99() call
    in the RELOADWL99 branch's retry loop."""
    working_dir = os.path.dirname(os.path.normpath(save_folder))
    loading_symbols_file = os.path.join(working_dir, 'LoadingSymbols.txt')
    reimport_symbols = sorted({normalize_for_reimport(s) for s in symbols})
    write_filenames_to_file(reimport_symbols, loading_symbols_file, label="symbols")

def append_loading_symbols(save_folder, new_symbols):
    """Append newly-found stuck symbols (deduped, sorted) to this run's
    LoadingSymbols.txt -- working_dir/LoadingSymbols.txt, same convention
    derive_merge_params()/do_reloadwl99() use (working_dir = parent of
    save_folder). No-op if new_symbols is empty."""
    if not new_symbols:
        return
    working_dir = os.path.dirname(os.path.normpath(save_folder))
    loading_symbols_file = os.path.join(working_dir, 'LoadingSymbols.txt')
    existing = set()
    if os.path.exists(loading_symbols_file):
        with open(loading_symbols_file, 'r') as f:
            existing = {line.strip() for line in f if line.strip()}
    combined = sorted(existing | {normalize_for_reimport(s) for s in new_symbols})
    write_filenames_to_file(combined, loading_symbols_file, label="symbols")

def get_ref_image_location(watchlist_data, images_folder):
    ref_image = watchlist_data['ref_image']
    # 2026-08-16 fix: a truly blank CSV cell parses via pandas as NaN (a
    # float), not "" -- the old `ref_image != ""` check never actually
    # matched NaN, so a blank ref_image column fell through to
    # os.path.join(images_folder, NaN) and crashed with "join() argument
    # must be str, bytes, or os.PathLike object, not 'float'". Every
    # existing recipe row always had a real filename here, so this never
    # got exercised until ReloadWL99.csv's plain-Click row (no ref_image).
    if pd.notna(ref_image) and str(ref_image).strip() != "":
        ref_image_path = os.path.join(images_folder,ref_image)
        loc= get_image_location(ref_image_path)
        if loc:
            return loc
        else:
            raise ValueError("Ref image location not found")
    else:
        return None

def stop_or_prompt(message):
    """Shared 'safety checkpoint failed' stop procedure for CLICKEXISTS/EXISTS
    steps -- same Stop/Continue pattern already used elsewhere (ensure_tos_in_focus,
    download_watchlist's export-failure check). Default is to stop; "Continue
    Anyway" is an explicit human override for a false-negative image match.
    These steps guard flows (like ReloadWL99.csv) that modify a live watchlist,
    so failing safe by default matters more here than in the export flow."""
    print(f"⚠️ {message}")
    choice = pyautogui.confirm(
        text=f"{message}\n\nThis step is a safety checkpoint before an action that "
             "may modify a watchlist.\nContinuing without confirming may click the "
             "wrong thing or load stocks into the wrong watchlist.",
        title="Checkpoint Failed",
        buttons=["Stop", "Continue Anyway"]
    )
    if choice != "Continue Anyway":
        print("🛑 Stopping automation — checkpoint image not found.")
        sys.exit(1)
    print("⚠️ Continuing despite failed checkpoint (user override).")

def do_clickexists(row, images_folder):
    """CLICKEXISTS step: locate row['ref_image'] on screen; if found, click at
    the image's center offset by row['X']/row['Y'] (0,0 = click dead center,
    the common case for a tightly-cropped button screenshot). If not found,
    run the shared stop procedure rather than clicking blind.

    Settle delays match the existing Click/WL pattern (e.g.
    download_watchlist's Save-dialog step: sleep before acting, longer sleep
    after) -- ui_click() itself already sleeps 0.5s before/0.25s after the
    click, but a dialog opened BY that click can take longer than 0.25s to
    fully render, so this adds an extra post-click settle on top before the
    next recipe row (often an EXISTS check on that new dialog) runs."""
    image_path = os.path.join(images_folder, row['ref_image'])
    location = get_image_location(image_path, label=row['Name'])
    if not location:
        stop_or_prompt(f"CLICKEXISTS '{row['Name']}': image '{row['ref_image']}' not found on screen.")
        return
    center = pyautogui.center(location)
    x = center.x + int(row['X']) if not pd.isna(row['X']) else center.x
    y = center.y + int(row['Y']) if not pd.isna(row['Y']) else center.y
    time.sleep(0.5)
    ui_click(x, y, row['Name'])
    time.sleep(1.0)

def do_exists(row, images_folder):
    """EXISTS step: pure checkpoint -- locate row['ref_image'] on screen and
    confirm we're on the expected screen/step. No click. Stops (via the
    shared stop procedure) if the image isn't found.

    Settle delay before searching: gives whatever the previous row just did
    (usually a CLICKEXISTS that opened this dialog) time to finish
    rendering before we check for it -- same "delay between clicks" pattern
    the rest of the script already uses."""
    time.sleep(0.5)
    image_path = os.path.join(images_folder, row['ref_image'])
    location = get_image_location(image_path, label=row['Name'])
    if not location:
        stop_or_prompt(f"EXISTS '{row['Name']}': expected checkpoint image '{row['ref_image']}' not found -- "
                        "not on the expected screen.")
        return
    print(f"✅ Checkpoint confirmed: {row['Name']}")
    time.sleep(0.5)

def do_typefile(row, base_dir=None):
    """TYPEFILE step: types literal text (a file path, per ReloadWL99.csv's
    use of this step) into whatever currently has focus (e.g. a file-picker's
    filename field) and presses Enter -- same write+Enter pattern the export
    flow already uses for its Save-As dialog. The value to type is read from
    row['ref_image'] (repurposed as a text/path column for this step type,
    not an image filename -- see ReloadWL99.csv's TYPEFILE row). A later,
    separate program may swap in a dynamically-generated batch file path
    here instead of a static one; not built yet by design.

    2026-08-17: if the value isn't already an absolute path, it's resolved
    against base_dir (the folder of whichever recipe CSV is currently
    running -- main() passes its own watchlist_file's folder) so a recipe
    can just say "LoadingSymbols.txt" instead of hardcoding a full path.
    Already-absolute values (e.g. do_reloadwl99's own internal call, which
    builds a full path itself) pass through unchanged; base_dir=None (the
    default) also leaves the value untouched, for backward compatibility.

    Confirmed (2026-08-16, corrected): clicking "Select file..." actually
    opens a SEPARATE native "Open" file-browser dialog -- not the same
    "Symbols Import" window. Accept both, since which one has focus here
    depends on exactly how far the previous CLICKEXISTS step got. A short
    settle delay runs BEFORE the focus check too (not just after, like
    before) -- the "Open" dialog needs a moment to actually gain OS focus
    after the click that spawned it; checking immediately could still see
    the previous window as "active"."""
    text_to_type = str(row['ref_image'])
    if base_dir and not os.path.isabs(text_to_type):
        text_to_type = os.path.join(base_dir, text_to_type)
    time.sleep(0.75)
    wait_if_mouse_moved()
    ensure_tos_in_focus(["Symbols Import", "Open", "thinkorswim"])
    time.sleep(1.0)
    pyautogui.write(str(text_to_type), interval=0.01)
    pyautogui.press('enter')
    time.sleep(2.0)
    print(f"✅ Typed '{text_to_type}' and pressed Enter.")

def substitute_placeholders(value, row):
    """Replaces {ColumnName} tokens in `value` with that column's value from
    `row` (a dict or pandas Series) -- e.g. "menu_{watchlist_name}.png" with
    row['watchlist_name']=='WL99TL' becomes "menu_WL99TL.png". This is what
    lets one shared recipe CSV (like ReloadWL99.csv) work for any watchlist
    without editing it per-type -- the real name comes from whichever row
    triggered the replay, not from anything hardcoded in the recipe or in
    Python. A column that's missing or blank on `row` leaves the placeholder
    text as-is rather than silently blanking it -- a typo'd {column} should
    show up as an obvious "image not found", not vanish quietly."""
    if not isinstance(value, str):
        return value
    def _replace(m):
        col = m.group(1)
        try:
            col_value = row[col]
        except (KeyError, IndexError):
            return m.group(0)
        if pd.isna(col_value):
            return m.group(0)
        return str(col_value)
    return re.sub(r'\{(\w+)\}', _replace, value)

def check_recipe_images(watchlist_file, images_folder):
    """Dry-run preflight (2026-08-17): scans watchlist_file for every image
    it would need -- ref_image/target_image on every row, PLUS, for every
    RELOADWL99 row, its ReloadWL99.csv sub-recipe with {watchlist_name} (and
    any other {ColumnName}) substituted the same way do_reloadwl99() would --
    and reports which of those files are actually missing from
    images_folder. No clicking, no TOS interaction; just a lookup.

    This surfaces every missing screenshot as one list up front, instead of
    one at a time, mid-automation, the first time a CLICKEXISTS/EXISTS step
    hits a mismatch via stop_or_prompt.

    Returns a list of (source_label, row_name, image_filename) for anything
    checked and not found -- empty list means this recipe is ready to run.
    Prints a human-readable report either way."""
    recipe_dir = os.path.dirname(os.path.abspath(watchlist_file))
    missing = []

    def _check_row(source_label, row):
        if row.get('Type') == 'TYPEFILE':
            return  # ref_image is repurposed as a literal text/path here, not an image -- do_typefile()'s own docstring
        for col in ('ref_image', 'target_image'):
            if col not in row:
                continue
            val = row[col]
            if pd.isna(val) or str(val).strip() == "":
                continue
            if not os.path.exists(os.path.join(images_folder, str(val))):
                missing.append((source_label, row.get('Name', ''), str(val)))

    df = pd.read_csv(watchlist_file)
    watchlist_label = os.path.basename(watchlist_file)
    for _, row in df.iterrows():
        _check_row(watchlist_label, row)
        if row['Type'] == 'RELOADWL99':
            reload_recipe_path = os.path.join(recipe_dir, 'ReloadWL99.csv')
            if not os.path.exists(reload_recipe_path):
                missing.append((watchlist_label, row.get('Name', ''), 'ReloadWL99.csv (recipe file itself)'))
                continue
            reload_df = pd.read_csv(reload_recipe_path)
            reload_label = f"ReloadWL99.csv (via {watchlist_label}'s watchlist_name={row['watchlist_name']})"
            for _, rrow in reload_df.iterrows():
                rrow = rrow.copy()
                rrow['ref_image'] = substitute_placeholders(rrow['ref_image'], row)
                _check_row(reload_label, rrow)

    if missing:
        print(f"\n❌ {watchlist_label}: {len(missing)} missing image(s):")
        for source, name, img in missing:
            print(f"   [{source}] {name}: {img}")
    else:
        print(f"\n✅ {watchlist_label}: all images present.")
    return missing

def do_reloadwl99(row, save_folder, images_folder, recipe_dir):
    """RELOADWL99 step: one row, added to a TOSType's own recipe CSV (e.g.
    TOSL.csv), that:
      1. Loads whatever LoadingSymbols.txt currently holds into this row's
         own watchlist_name (e.g. WL99TL) via Edit > Import > Load from
         File -- by replaying ReloadWL99.csv (co-located with the calling
         recipe, in recipe_dir) through the exact same row-dispatcher
         main() uses (run_recipe_rows()), after substitute_placeholders()
         swaps {watchlist_name} (and any other {ColumnName} token) in its
         ref_image values for this row's own values. One shared
         ReloadWL99.csv now works for every TOSType/watchlist_name
         combination -- no per-type copy of the recipe, no hardcoded image
         names in Python (2026-08-17 redesign -- previously this called a
         hardcoded, WL99-only import_symbols_into_watchlist()).
      2. Does a REAL export of WL99 afterward, using this row's
         own Name/ref_image/X/Y/watchlist_name/watchlist_x/watchlist_y --
         the same columns a plain WL row already uses to navigate to it --
         so the coordinates only need to be correct in one place per
         TOSType CSV, same as any other WL row.

    Symbol source: LoadingSymbols.txt in this run's working_dir (parent of
    save_folder, same convention derive_merge_params()/monitor_directory()
    use). This is THIS run's own data, not a stale previous-run snapshot:
    main() clears it before exporting WL1, then download_watchlist() (via
    extract_loading_symbols()/append_loading_symbols()) accumulates stuck
    symbols into it fresh as each of WL1..WL16 actually export -- by the
    time this row runs (last), it holds the complete, current set from
    every watchlist in this same run. The merge stage afterward still does
    its own, more precise per-symbol tracking across all fragments (catches
    anything this per-file scan might miss) and will retry any leftovers on
    the NEXT run automatically, same as before."""
    working_dir = os.path.dirname(os.path.normpath(save_folder))
    loading_symbols_file = os.path.join(working_dir, 'LoadingSymbols.txt')

    # Skip the RELOAD/IMPORT part (not the export -- see below) if there's
    # nothing to reload: no file, or empty/blank-only content (monitor_
    # directory() writes an empty file via write_filenames_to_file([], ...)
    # when nothing's stuck, rather than deleting it, so "exists but empty"
    # is the normal steady-state case).
    has_symbols = False
    if os.path.exists(loading_symbols_file):
        with open(loading_symbols_file, 'r') as f:
            has_symbols = any(line.strip() for line in f)

    export_row = dict(row)

    if has_symbols:
        # 1. Pre-select this watchlist using the same reliable coordinate
        # mechanism a plain WL row already uses (ref_image + X/Y/watchlist_x/
        # watchlist_y) -- open_only=True so it just navigates to it, no
        # waiting for load or exporting. This gets TOS actually showing the
        # right watchlist BEFORE hunting for its Edit control, instead of
        # starting from whatever the previous WL row (WL17) left on screen --
        # and makes ReloadWL99.csv's own first few steps (open the big
        # dropdown -> Personal -> find the entry by name) unnecessary, since
        # that chain existed only to reach "this watchlist is now showing,"
        # which this coordinate-based call already does more reliably.
        download_watchlist(export_row, save_folder, images_folder, True, False, False)

        # 2. Reload sequence: replay ReloadWL99.csv (co-located with the
        # calling recipe) with this row's own values substituted into its
        # placeholders. Starts from "Click watchlist dropdown box" now
        # (2026-08-17) -- see step 1's note.
        reload_recipe_path = os.path.join(recipe_dir, 'ReloadWL99.csv')
        if not os.path.exists(reload_recipe_path):
            print(f"⚠️ RELOADWL99: reload recipe not found at {reload_recipe_path} -- skipping reload, still exporting.")
        else:
            reload_df = pd.read_csv(reload_recipe_path)
            reload_df['ref_image'] = reload_df['ref_image'].apply(lambda v: substitute_placeholders(v, row))
            run_recipe_rows(reload_df, save_folder, images_folder, working_dir, False)
    else:
        print(f"\n--- RELOADWL99: {loading_symbols_file} has no symbols -- nothing to reload, still exporting. ---")

    # 3. Real export of WL99 -- ALWAYS, even with nothing to reload above.
    # The merge stage expects this fragment to exist every run (same as any
    # WL1..WL17 fragment); skipping it here previously left it missing
    # whenever nothing happened to be stuck, causing a "missing file" error
    # downstream instead of just re-exporting WL99's current, unchanged
    # contents.
    #
    # already_selected=has_symbols (2026-08-20): only true when step 1's
    # pre-select actually ran -- in that branch nothing between here and
    # there switches watchlists (step 2's reload sequence edits WL99's
    # symbols without navigating away from it), so re-doing the same 3
    # selection clicks here would just reselect WL99 a second time for
    # nothing. When has_symbols is False, steps 1/2 above were skipped
    # entirely -- WL99 was never actually selected this call, so this
    # export still needs the real navigation.
    download_watchlist(export_row, save_folder, images_folder, False, False, False,
                        already_selected=has_symbols)

def edit_watchlist(watchlist_name, symbols_file, images_folder, recipe_dir,
                    recipe_name='EditWatchlist.csv'):
    """Generic 'import symbols into ANY watchlist' building block (2026-08-18)
    -- reused by both LoadWatchlists.py (imports a whole folder of watchlist
    files) and ImportAdditions.py (imports just a delta). Same mechanism
    do_reloadwl99() uses for WL99 (substitute_placeholders() + a shared,
    name-agnostic recipe replayed through run_recipe_rows()), generalized to
    any watchlist name with no coordinate/pre-select dependency -- unlike
    do_reloadwl99()'s trimmed ReloadWL99.csv (which skips the dropdown-hunt
    because download_watchlist() already pre-selected the watchlist by
    coordinate), this has no coordinates to work with for an arbitrary
    watchlist name, so recipe_name's default (EditWatchlist.csv) is the
    FULL untrimmed name-image-only navigation chain -- open dropdown ->
    Personal -> menu_{name} -> Watchlist_{name} -> Edit{name} ->
    EditDialog{name} -> Import -> ... -> Save.

    Requires 4 per-watchlist-name screenshots (menu_<name>.png,
    Watchlist_<name>.png, Edit<name>.png, EditDialog<name>.png) in
    images_folder -- same convention as WL99's own images. Returns True if
    it ran, False if skipped (missing images or recipe file), matching the
    old import_symbols_into_watchlist()'s skip-not-fail contract."""
    for template in ('menu_{n}.png', 'Watchlist_{n}.png', 'Edit{n}.png', 'EditDialog{n}.png'):
        img = template.format(n=watchlist_name)
        if not os.path.exists(os.path.join(images_folder, img)):
            print(f"⚠️ Skipping '{watchlist_name}': missing reference image '{img}' in "
                  f"{images_folder}. Capture it (same pattern as WL99's images) to enable this watchlist.")
            return False

    recipe_path = os.path.join(recipe_dir, recipe_name)
    if not os.path.exists(recipe_path):
        print(f"⚠️ {recipe_name} not found in {recipe_dir} -- cannot import '{watchlist_name}'.")
        return False

    substitution_row = {'Name': watchlist_name, 'watchlist_name': watchlist_name,
                         'symbols_file': symbols_file}
    recipe_df = pd.read_csv(recipe_path)
    recipe_df['ref_image'] = recipe_df['ref_image'].apply(
        lambda v: substitute_placeholders(v, substitution_row))
    print(f"\n--- Importing {symbols_file} into watchlist '{watchlist_name}' ---")
    run_recipe_rows(recipe_df, None, images_folder, recipe_dir, False)
    return True

def download_watchlist(watchlist_data, save_folder, images_folder, open_only, force_download, re_process,
                        already_selected=False):
    global elapsed_time
    """Navigate menus to export a specific watchlist.

    already_selected (2026-08-20): set True when the caller already knows
    this watchlist is the one currently showing on screen and nothing has
    navigated away from it since -- skips the dropdown/category/name
    re-navigation clicks below entirely (still runs the target_image
    checkpoint, since that's a cheap read-only confirmation, not a click).
    Only do_reloadwl99()'s final export call uses this: its own earlier
    open_only pre-select call already selected this exact watchlist, and
    the reload sequence in between (editing WL99's symbols) never switches
    away from it -- redoing the same 3 selection clicks there was pure
    waste, on every WL99 export/retry."""
    category = watchlist_data['Name']
    ref_image = watchlist_data['ref_image']
    w_name = watchlist_data['watchlist_name']

    filename = f"{category}_{w_name}.csv"
    if (not open_only) and re_process:
        if not is_file_in_incomplete_list(filename):
            print(f"\n--- Skipping: {category} → {w_name} ---")
            return True

    full_path = os.path.join(save_folder, filename)

    if (open_only):
        print(f"Opening {category} → {w_name} to refresh the list.")

    if already_selected:
        print(f"--- {category} → {w_name} already selected -- skipping re-navigation. ---")
    else:
        offset_location = get_ref_image_location(watchlist_data, images_folder)
        if offset_location:
            c_x = watchlist_data['X'] + int(offset_location.left)
            c_y = watchlist_data['Y'] + int(offset_location.top)
            w_x = watchlist_data['watchlist_x'] + int(offset_location.left)
            w_y = watchlist_data['watchlist_y'] + int(offset_location.top)
        else:
            c_x = watchlist_data['X']
            c_y = watchlist_data['Y']
            w_x = watchlist_data['watchlist_x']
            w_y = watchlist_data['watchlist_y']

        # Open watchlist dropdown
        ui_click(WATCHLIST_COMBOBOX_X, WATCHLIST_COMBOBOX_Y)

        # Click category
        ui_click(c_x, c_y)

        # Click watchlist name
        ui_click(w_x, w_y)

    # Optional identity checkpoint (2026-08-17): confirms the watchlist that's
    # now active on screen is actually the one this row meant to select --
    # the clicks above are coordinate offsets only, so without this there's
    # no proof they landed on the right item (e.g. list reordered/changed).
    # Blank/missing target_image (most rows, for now) skips the check --
    # same opt-in shape as get_ref_image_location()'s ref_image handling.
    # Kept even when already_selected=True -- it's a read-only check, not a
    # click, so it's still worth confirming nothing drifted.
    target_image = watchlist_data.get('target_image')
    if pd.notna(target_image) and str(target_image).strip() != "":
        do_exists({'Name': f'Confirm {w_name} is active', 'ref_image': target_image}, images_folder)

    if open_only:
        time.sleep(2)
        return True

    print(f"\n--- Processing: {category} → {w_name} ---")

    #time.sleep(wait_for_loading_sec)

    #images_folder = os.path.join(save_folder, "..", "images")
    #images_folder = os.path.abspath(images_folder)

    start = time.time()
    total_count = 0
    prev_count = 0
    no_change_count = 0

    #print(f"elapsed time {elapsed_time}")

    while time.time() - start < 180:
        # if prev_count==0:
        #     time.sleep(5)
        # else:
        #     time.sleep(2)
        total_count = count_images_in_folder(images_folder, "lo")

        if prev_count == total_count and (time.time() - start)>30:
            no_change_count = no_change_count + 1
        else:
            no_change_count = 0

        if total_count == 0 or (total_count < 10 and no_change_count>5):
            elapsed_time = time.time() - start
            break

        if no_change_count>5 and not force_download:
            print("No change in Loading word count")
            return False

        prev_count=total_count

    # Handle pre-existing file
    if os.path.exists(full_path):
        print(f"🗑 Existing file found: {full_path}. Moving to Recycle Bin...")
        send2trash.send2trash(full_path)
        time.sleep(1)

    # Open export menu
    click_image_or_capture_fallback(os.path.join(images_folder,"export_menu.png"))

    ui_click(export_menu_X, EXPORT_MENU_ENTRY_Y)
    ensure_tos_in_focus(["thinkorswim", "watchlist"])  # Expect the Save As dialog
    time.sleep(1.0)

    # Save dialog
    pyautogui.write(full_path, interval=0.01)
    pyautogui.press('enter')
    time.sleep(2.0)

    # Verify export succeeded
    if os.path.exists(full_path):
        print(f"✅ Successfully saved to: {full_path}")
        # 2026-08-17: pull the actual stuck symbols out of THIS export
        # (regardless of whether it passes the file-level threshold below)
        # and accumulate them into this run's LoadingSymbols.txt, so
        # RELOADWL99 (which runs after all 16 watchlists) sees this run's
        # real data instead of a stale snapshot from last time.
        append_loading_symbols(save_folder, extract_loading_symbols(full_path))
        if check_loading_threshold_from_csv(full_path):
            return True
        else:
            print("Lot of rows have word Loading")
            return False
    else:
        print(f"❌ File not found after export: {full_path}")
        user_choice = pyautogui.confirm(
            text=f"File not found after export:\n\n{full_path}\n\nDo you want to stop automation?",
            title="Export Failed",
            buttons=["Stop", "Continue"]
        )
        if user_choice == "Stop":
            print("🛑 Stopping automation as requested.")
            sys.exit(1)
        else:
            print("⚠️ Continuing to next watchlist.")

    return False

def run_recipe_rows(df, save_folder, images_folder, recipe_dir, re_process):
    """Runs Click/WL/CLICKEXISTS/EXISTS/TYPEFILE/RELOADWL99 rows from df, in
    order -- the row-dispatcher main() has always used, factored out
    (2026-08-17) so do_reloadwl99() can replay a *sub*-recipe (ReloadWL99.csv)
    through this exact same logic instead of duplicating it in Python.

    recipe_dir: folder a bare TYPEFILE value and RELOADWL99's own recipe
    lookup resolve against. main() passes the top-level recipe CSV's own
    folder; do_reloadwl99() passes its run's working_dir instead when
    replaying ReloadWL99.csv, so that recipe's own "LoadingSymbols.txt"
    TYPEFILE row resolves to THIS run's own file, not wherever
    ReloadWL99.csv itself happens to live."""
    openindex = 99
    firstopenindex = 99
    for index, row in df.iterrows():
        etype = row['Type']
        if etype == "Click":
            offset_location = get_ref_image_location(row, images_folder)
            if offset_location:
                ui_click(row['X']+ int(offset_location.left),row['Y']+ int(offset_location.top),row['Name'])
            else:
                ui_click(row['X'],row['Y'],row['Name'])
        elif etype == "WL":
            if firstopenindex==99:
                firstopenindex=index
                # 2026-08-19: disabled per user request -- this primed TOS by
                # open-only navigating to the SECOND watchlist (index+1)
                # before downloading the first one for real. No longer
                # needed now that the RELOADWL99 reprocess/retry logic
                # (below) handles stuck symbols reliably. firstopenindex
                # itself still needs to be set above -- the failure-retry
                # logic right below still reads it. Commented out rather
                # than deleted in case it needs to come back.
                # download_watchlist(df.iloc[firstopenindex+1], save_folder, images_folder, True, False, re_process)

            if not download_watchlist(row, save_folder, images_folder, False, False, re_process):
                if index==firstopenindex:
                    openindex = firstopenindex+1
                else:
                    openindex = firstopenindex

                if download_watchlist(df.iloc[openindex], save_folder, images_folder, True, False, re_process):
                    if not download_watchlist(row, save_folder, images_folder, False, False, re_process):
                        if download_watchlist(df.iloc[openindex], save_folder, images_folder, True, False, re_process):
                            download_watchlist(row, save_folder, images_folder, False, True, re_process)
        elif etype == "CLICKEXISTS":
            do_clickexists(row, images_folder)
        elif etype == "EXISTS":
            do_exists(row, images_folder)
        elif etype == "TYPEFILE":
            do_typefile(row, base_dir=recipe_dir)
        elif etype == "RELOADWL99":
            # 2026-08-19: reprocess gate -- if a lot of symbols are still
            # stuck 'Loading' across WL1..WL16, retry those specific
            # watchlists (via download_watchlist()'s own re_process=True
            # skip-if-not-incomplete check) BEFORE handing the leftover to
            # WL99's own reload. WL99's single reload+import can only
            # realistically absorb a couple dozen symbols in one go, not
            # the whole board -- dumping everything on it wastes the
            # reload on symbols other watchlists could have resolved
            # themselves. Excludes the RELOADWL99 row itself from the
            # re-run (that's handled separately below) to avoid recursing
            # back into this same branch.
            print(f"\n{'=' * 60}\n=== RELOADWL99 reached -- checking for stuck 'Loading' symbols ===\n{'=' * 60}")
            reprocess_attempts = 0
            stuck_symbols = find_genuinely_stuck_symbols(save_folder)
            stuck_count = len(stuck_symbols)
            print(f"Stuck symbols right now ({stuck_count}): {sorted(stuck_symbols)}")
            print(f"Incomplete watchlist fragments right now: {incomplete_files}")

            if stuck_count <= RELOAD_SYMBOL_THRESHOLD:
                print(f"{stuck_count} <= threshold ({RELOAD_SYMBOL_THRESHOLD}) -- skipping the reprocess "
                      "step, letting WL99's own reload handle these directly.")

            while stuck_count > RELOAD_SYMBOL_THRESHOLD and reprocess_attempts < MAX_REPROCESS_ATTEMPTS:
                print(f"\n--- {stuck_count} symbol(s) still 'Loading' (> {RELOAD_SYMBOL_THRESHOLD}) -- "
                      f"reprocessing incomplete watchlists before WL99 reload "
                      f"(attempt {reprocess_attempts + 1}/{MAX_REPROCESS_ATTEMPTS}). "
                      f"Watchlists being touched: {incomplete_files} ---")
                # 2026-08-20: try jarring TOS into recomputing the stuck cells
                # by switching the column set away and back (x3) BEFORE
                # re-hitting the same incomplete watchlists -- often resolves
                # them without needing any symbol reimport at all. Falls
                # through to the reprocess below regardless of whether this
                # helped; if it didn't, the reload-into-WL99 fallback after
                # this loop still runs.
                toggle_column_set_away_and_back(df, images_folder)
                run_recipe_rows(df[df['Type'] != 'RELOADWL99'], save_folder, images_folder, recipe_dir, True)
                reprocess_attempts += 1
                new_stuck_symbols = find_genuinely_stuck_symbols(save_folder)
                new_stuck_count = len(new_stuck_symbols)
                print(f"After reprocess attempt {reprocess_attempts}: {new_stuck_count} still stuck: "
                      f"{sorted(new_stuck_symbols)}")
                if new_stuck_count >= stuck_count:
                    print(f"Reminder: reprocess attempt {reprocess_attempts} made no progress "
                          f"({new_stuck_count} still 'Loading') -- stopping reprocessing early.")
                    stuck_symbols = new_stuck_symbols
                    break
                stuck_count = new_stuck_count
                stuck_symbols = new_stuck_symbols

            # WL99 reload+export retry loop -- TOS sometimes needs more than
            # one reload/export pass to actually resolve every symbol.
            # Retry up to MAX_WL99_RETRY_ATTEMPTS, stopping as soon as
            # nothing's stuck or a pass makes no further progress.
            #
            # 2026-08-19 bug fix: do_reloadwl99() reads LoadingSymbols.txt
            # directly to decide what to reload, but that file is monotonic
            # (append_loading_symbols() only ever unions symbols in, never
            # trims resolved ones out mid-run) -- so without the
            # sync_loading_symbols_file() call below, attempt 2/3 would
            # redundantly re-import every symbol EVER stuck this run,
            # including ones the reprocess step or a prior WL99 attempt
            # already resolved. Trim it to the current, accurate stuck set
            # (from find_genuinely_stuck_symbols()) before every attempt,
            # including the first, so TOS only ever gets re-clicked for
            # symbols that actually still need it.
            print(f"\n--- Proceeding to WL99 reload+export (up to {MAX_WL99_RETRY_ATTEMPTS} attempt(s)). ---")
            symbols_to_reload = stuck_symbols
            wl99_attempts = 0
            prev_remaining = None
            while wl99_attempts < MAX_WL99_RETRY_ATTEMPTS:
                sync_loading_symbols_file(save_folder, symbols_to_reload)
                print(f"LoadingSymbols.txt trimmed to the {len(symbols_to_reload)} symbol(s) actually still "
                      f"stuck before this attempt: {sorted(symbols_to_reload)}")
                print(f"\n--- WL99 reload+export attempt {wl99_attempts + 1}/{MAX_WL99_RETRY_ATTEMPTS} starting. ---")
                do_reloadwl99(row, save_folder, images_folder, recipe_dir)
                wl99_attempts += 1
                remaining_symbols = find_genuinely_stuck_symbols(save_folder)
                remaining = len(remaining_symbols)
                print(f"After WL99 attempt {wl99_attempts}: {remaining} still stuck: {sorted(remaining_symbols)}")
                if remaining == 0:
                    print("--- Nothing left stuck -- WL99 reload/retry loop done. ---")
                    break
                if prev_remaining is not None and remaining >= prev_remaining:
                    print(f"Reminder: WL99 reload attempt {wl99_attempts} made no progress "
                          f"({remaining} still 'Loading') -- stopping retries.")
                    break
                symbols_to_reload = remaining_symbols
                if wl99_attempts < MAX_WL99_RETRY_ATTEMPTS:
                    print(f"Reminder: {remaining} symbol(s) still stuck 'Loading' after WL99 reload "
                          f"attempt {wl99_attempts}/{MAX_WL99_RETRY_ATTEMPTS} -- retrying.")
                prev_remaining = remaining
            print(f"{'=' * 60}\n=== RELOADWL99 handling done ({wl99_attempts} WL99 attempt(s), "
                  f"{reprocess_attempts} reprocess attempt(s)) ===\n{'=' * 60}\n")
        else:
            print(f"Unknown type '{etype}' ")

def main(watchlist_file, save_folder, images_folder, re_process):

    """Main execution entrypoint for the DOWNLOAD stage only (unchanged from
    the original standalone TOSDownloads.py, except run_recipe_rows()'s own
    RELOADWL99 branch now reprocesses incomplete watchlists before WL99's
    reload, see that branch's comment). run_pipeline() below drives this
    plus the merge stage as one combined run."""
    ensure_tos_active(images_folder)

    if not os.path.exists(save_folder):
        os.makedirs(save_folder)
        print(f"Created save directory: {save_folder}")

    try:
        df = pd.read_csv(watchlist_file)
    except FileNotFoundError:
        print(f"Error: Input file '{watchlist_file}' not found.")
        sys.exit(1)

    # 2026-08-17: clear LoadingSymbols.txt AND any leftover fragment CSVs
    # already sitting in save_folder (the input dir) before exporting the
    # first watchlist. Both are about the same root cause: a previous run
    # that crashed/was interrupted before reaching delete_processed_files()
    # leaves old fragments (and old "loading" data) behind indefinitely --
    # monitor_directory() has no age check, it merges whatever .csv files
    # it finds, so stale leftovers from days-old runs were leaking into the
    # current run's "Summary of findings" (confirmed live: files reported
    # stuck that this run's own download pass hadn't even reached yet).
    # This run's download loop is about to regenerate every expected
    # fragment (WL1..WL16 + WL99) fresh anyway, so clearing first is safe.
    # Only on the first pass (re_process=False) -- main() gets called again
    # with re_process=True for the incomplete-files retry pass, which must
    # ADD to what the first pass already found/downloaded, not wipe it.
    if not re_process:
        working_dir = os.path.dirname(os.path.normpath(save_folder))
        write_filenames_to_file([], os.path.join(working_dir, 'LoadingSymbols.txt'), label="symbols")
        if os.path.isdir(save_folder):
            for fname in os.listdir(save_folder):
                if fname.lower().endswith('.csv'):
                    fpath = os.path.join(save_folder, fname)
                    print(f"🗑 Clearing stale leftover fragment: {fpath}")
                    send2trash.send2trash(fpath)

    #print("Starting automation in 2 seconds. Make sure TOS is visible and ready...")
    #time.sleep(2)

    #set_column_set()

    recipe_dir = os.path.dirname(os.path.abspath(watchlist_file))
    run_recipe_rows(df, save_folder, images_folder, recipe_dir, re_process)

    print("\n✅ All watchlists processed successfully!")


# =====================================================================
# ---- MERGE STAGE (merged in from MergeExports.py, 2026-08-16) ----
# Functions below are copied verbatim from the standalone MergeExports.py
# except: its own acquire_lock/release_lock/fd are dropped (the single
# copy above is shared), and monitor_directory() is called from
# run_pipeline() below with lock_file_path=None since the outer pipeline
# already holds the lock for the whole combined run.
# =====================================================================

def sync_and_validate_count(data, filename):
    current_count = len(data)

    if os.path.exists(filename):
        with open(filename, 'r') as f:
            stored_count = int(f.read().strip())

        if current_count != stored_count:
            print(f"Row count mismatch! Previous: {stored_count}, Current: {current_count}")
            # 2026-08-19: was a blocking console input() -- by the time the
            # merge stage reaches here, TOS automation has long since left
            # the terminal window out of focus, so the prompt sat there
            # invisibly waiting for a keystroke. A real GUI dialog (same
            # pattern as ensure_tos_in_focus()'s focus-loss check) is visible
            # regardless of which window currently has focus.
            user_choice = pyautogui.confirm(
                text=f"Row count mismatch!\n\nPrevious: {stored_count}\nCurrent: {current_count}\n\n"
                     "Do you wish to continue?",
                title="Row Count Mismatch",
                buttons=["Continue", "Abort"]
            )

            if user_choice != "Continue":
                print("Aborting process.")
                sys.exit()

    with open(filename, 'w') as f:
        f.write(str(current_count))

def get_encoding(file_path):
    # Detect the file encoding
    with open(file_path, 'rb') as raw_file:
        raw_data = raw_file.read()
        result = chardet.detect(raw_data)
        return result['encoding']

def is_locked(path):
    try:
        with open(path, 'r+b'):
            return False
    except PermissionError:
        return True
    except FileNotFoundError:
        return False

def open_and_wait(path, timeout=300, interval=0.5):
    """Launch the file and block until Excel has it open (locked), or timeout.
    Returns True if it opened, False if it timed out.

    2026-08-17: tried actively minimizing the newly-opened window (pygetwindow
    + a direct Win32 ShowWindow call) to stop it stealing foreground focus
    from another TOSType's active clicking -- worked in isolated testing but
    didn't hold up in practice, reverted. The actual fix is at the call site
    now: is_lock_free() gates whether this even gets called at all, rather
    than trying to make the open itself harmless."""
    os.startfile(path)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_locked(path):
            return True
        time.sleep(interval)
    return False

def wait_for_file_to_close(filename):
    """Waits until the specified file is closed."""
    while True:
        try:
            with open(filename, 'a'):
                pass
            break
        except IOError:
            print(f"File {filename} is currently open. Please close it to proceed.")
            time.sleep(30)

def read_headers(headers_file):
    if not os.path.isfile(headers_file):
        print(f"Error: File '{headers_file}' does not exist.")
        sys.exit(1)

    encoding = get_encoding(headers_file)

    with open(headers_file, 'r', encoding=encoding) as file:
        reader = csv.reader(file)

        try:
            input_headers = next(reader)
        except StopIteration:
            print("Error: Input Headers row is empty.")
            sys.exit(1)

        try:
            output_headers = next(reader)
        except StopIteration:
            print("Error: Output Headers row is empty.")
            sys.exit(1)

        def is_empty(row):
            return not row or all(cell.strip() == "" for cell in row)

        if is_empty(input_headers):
            print("Error: Input Headers row is empty.")
            sys.exit(1)

        if is_empty(output_headers):
            print("Error: Output Headers row is empty.")
            sys.exit(1)

    return input_headers, output_headers

def read_files_list(files_list_path):
    """Reads the FilesList.txt to get the list of already processed files."""
    if not os.path.exists(files_list_path):
        return []
    with open(files_list_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

def update_files_list(files_list_path, filename):
    """Updates the FilesList.txt by adding a new file entry, removing date prefix in 'YYYY-MM-DD-' format."""
    # Remove the date prefix in 'YYYY-MM-DD-' format from the filename
    filename_without_date = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename)
    # 2026-08-17: removed a stray "strip the character 5 from the end if it's
    # a letter" step that used to run here -- nothing in the current naming
    # scheme needs a trailing letter stripped (WL1..WL17 end in digits; the
    # WL99TD/TL/TO/TW suffix's trailing letter IS the type identifier, not
    # something to discard). It was silently corrupting entries like
    # "TOSL_WL99TL.csv" into "TOSL_WL99T.csv" -- exactly the stale name that
    # kept reappearing in FilesList.txt and triggering monitor_directory()'s
    # blocking "Do you want to remove '...' from FilesList.txt?" prompt.

    files = read_files_list(files_list_path)

    if filename_without_date not in files:
        with open(files_list_path, 'a') as file:
            file.write(filename_without_date + '\n')

def delete_processed_files(directory, file_dict):
    """
    Deletes each file specified in the provided dictionary of file names, appending the directory.

    Parameters:
    - file_dict (dict): Dictionary with file identifiers as keys and file names as values.
    - directory (str): Directory path to append to each file name.
    """
    for filename in file_dict.keys():
        file_path = os.path.join(directory, filename)
        try:
            if os.path.exists(file_path):
                wait_for_file_to_close(file_path)
                send2trash.send2trash(file_path)
                #os.remove(file_path)
                print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Error deleting {file_path} : {e}")

def is_file_empty(file_path):
    return os.path.getsize(file_path) == 0

def copy_and_add_empty_lines(source_file, dest_file, n):
    """
    Copies the content of source_file to dest_file,
    adding n empty lines at the beginning.
    """

    with open(source_file, 'r') as infile, open(dest_file, 'w') as outfile:
        for _ in range(n):
            outfile.write('\n')  # Write n empty lines

        for line in infile:
            outfile.write(line)

def get_lastest_file(path):
    files = os.listdir(path)
    paths = [os.path.join(path, basename) for basename in files]
    if len(paths) == 0:
        return ""
    latest= max(paths, key=os.path.getctime)
    return latest
def get_export_date(output_format="%Y-%m-%d"):  # Added output_format parameter
    """
    Returns the date in the specified format. If today is a working day (Monday-Friday),
    it returns today's date. Otherwise, it returns the date of the last working day.

    Args:
        output_format: The format string for the date (default: "%Y-%m-%d").
    """

    today = datetime.datetime.today()
    weekday = today.weekday()

    if 0 <= weekday <= 4:  # Monday to Friday
        return today.strftime(output_format)
    else:
        # Calculate the last working day
        days_to_subtract = weekday - 4  # How many days to go back to Friday
        last_working_day = today - datetime.timedelta(days=days_to_subtract)
        return last_working_day.strftime(output_format)

def get_export_time():
    """
    Checks the current time and returns 1630 if it's between 4 PM and 9 AM,
    otherwise returns the actual time in HHMM format.
    """
    today = datetime.datetime.today()
    weekday = today.weekday()

    if 0 <= weekday <= 4:  # Monday to Friday
        now = datetime.datetime.now()
        hour = now.hour

        if 16 <= hour or hour < 9: #check if time is between 4pm and 9am
            return "1630"
        else:
            return now.strftime("%H%M")
    else:
        return "1630"


def compare_lists(list1, list2):
    """
    Compares two lists for exact match, including length and element-wise equality.

    Args:
        list1: The first list.
        list2: The second list.

    Returns:
        A string reporting the comparison result. Returns "Match" if the lists are identical.
        If they are not identical returns a detailed message with number of elements mismatch and position wise mismatch if any.
    """

    if len(list1) != len(list2):
        return f"Mismatch: Different number of elements. List1 has {len(list1)} elements, List2 has {len(list2)} elements."

    mismatched_indices = []
    for i in range(len(list1)):
        if list1[i] != list2[i]:
            mismatched_indices.append(i)

    if not mismatched_indices:
        return "Match"  # Lists are identical

    report = "Mismatch:\n"
    report += "Elements at the following positions do not match:\n"
    for index in mismatched_indices:
        report += f"  - Index {index}: List1[{index}] = {list1[index]}, List2[{index}] = {list2[index]}\n"
    return report

def extract_filenames(summary_messages: Dict[str, str]) -> List[str]:
    """
    Extracts filenames from a dictionary where values are formatted as
    'filename - symbol'.
    """
    unique_filenames = {
        full_string.split(' - ')[0]
        for full_string in summary_messages.values()
    }
    return unique_filenames

def write_filenames_to_file(filenames: List[str], output_path: str, label: str = "filenames") -> bool:
    """
    Writes the list of strings to the text file specified by output_path,
    one per line. Despite the name (kept for the original IncompleteFilesList.txt
    caller), this is generic -- also reused for LoadingSymbols.txt (2026-08-17),
    where the entries are stock symbols, not filenames. `label` controls the
    console message's wording so it stays accurate per caller.

    Returns True on success, False on failure.
    """
    try:
        # Open in 'w' (write) mode to overwrite/create the file
        with open(output_path, 'w') as f:
            for filename in filenames:
                f.write(filename + '\n')

        print(f"✅ Wrote {len(filenames)} {label} to: {os.path.abspath(output_path)}")
        return True

    except IOError as e:
        print(f"❌ Error writing to file '{output_path}': {e}")
        return False

def monitor_directory(working_dir, final_partial_filename, lines_to_ignore, output_filename_prefix, update_exports, ignore_keyword_issues, lock_file_path, excel_open_lock_path=None):
    output_file=None
    archive_file=None

    try:
        if lock_file_path:
            acquire_lock(lock_file_path)

        input_dir = os.path.join(working_dir, 'input')
        output_dir = os.path.join(working_dir, 'output')
        archive_dir = os.path.join(working_dir, 'archive')
        headers_file = os.path.join(working_dir, 'Headers.csv')
        files_list_path = os.path.join(working_dir, 'FilesList.txt')
        incomplete_files_list_path = os.path.join(working_dir, 'IncompleteFilesList.txt')
        # 2026-08-17: the actual stuck SYMBOLS (not filenames -- that's what
        # IncompleteFilesList.txt records, via extract_filenames()), for
        # feeding into ReloadWL99.csv's TYPEFILE step. Designed earlier,
        # built now -- summary_messages is already keyed by symbol.
        loading_symbols_file = os.path.join(working_dir, 'LoadingSymbols.txt')
        rowcount_file = os.path.join(working_dir, output_filename_prefix + '_rowcount.txt')

        export_file_latest=""
        export_file_to_update=""
        export_file_to_update_indir=""
        if update_exports=='Y':
            export_file_latest=get_lastest_file(archive_dir)
            if export_file_latest=="":
                print(f"Archive file doesn't exist to update. Dir is empty")
                sys.exit(1)

            export_file_to_update=os.path.basename(export_file_latest)
            #if export file to update exists in the input directory. delete it.
            export_file_to_update_indir=os.path.join(input_dir, export_file_to_update)
            if os.path.isfile(export_file_to_update_indir):
                send2trash.send2trash(export_file_to_update_indir)

        if ignore_keyword_issues=="Y":
            if os.path.exists(incomplete_files_list_path):
                send2trash.send2trash(incomplete_files_list_path)

        # Read headers from Headers.csv
        input_headers, output_headers = read_headers(headers_file)
        output_list = {}
        processed_files = {}
        summary_messages = {}  # to hold summary messages
        last_file=""
        update_exports_prompt = False
        exit_update_exports = False

        # Monitoring loop
        while True:
            time.sleep(5)

            for filename in os.listdir(input_dir):
                filepath = os.path.join(input_dir, filename)
                if not filename.endswith('.csv'):
                    continue
                if is_file_empty(filepath):
                    continue
                # Check if the file needs reprocessing based on its modification time
                file_modified_time = os.path.getmtime(filepath)
                should_process = False

                if filename not in processed_files:
                    should_process = True  # New file
                elif processed_files[filename] < file_modified_time:
                    should_process = True  # File has been updated

                if should_process:
                    encoding = get_encoding(filepath)
                    with open(filepath, 'r', encoding=encoding) as file:
                        reader = csv.reader(file)
                        # Skip the specified number of lines
                        for _ in range(lines_to_ignore):
                            next(reader)

                        # Read the header line and check if it matches
                        actual_headers = next(reader)
                        if actual_headers != input_headers:
                            compare_lists(actual_headers, input_headers)
                            cont = input(f"Error: The headers in the file '{filename}' do not match the expected headers (First Row in headers file). Press y to continue: ").strip().lower()
                            if cont == 'y':
                                continue
                            else:
                                sys.exit(1)

                        dataexists = False
                        # Process the data rows
                        for row in reader:
                            if len(row)==0:
                                continue
                            symbol = row[0]  # Assuming the symbol is in the first column
                            #if symbol in ('NFLX'):
                            #    print (f"symbol {symbol}")

                            # if no symbol in the output list or word loading in outputlist or word loading not found in the source row
                            if (not symbol in output_list.keys()) or any(WORD_TO_FIND in cell for d in output_list[symbol] for cell in d) or ((filename!=export_file_to_update) and (not WORD_TO_FIND in row)):
                                output_list[symbol] = row
                                dataexists = True

                                # Check for 'loading' and display the information
                                if WORD_TO_FIND in row:
                                    #summary_messages[symbol] = f"{filename} - " + ', '.join(row)
                                    summary_messages[symbol] = f"{filename} - " + symbol
                                elif symbol in summary_messages:
                                    del summary_messages[symbol]

                        if dataexists:
                            if update_exports=="N":
                                update_files_list(files_list_path, filename)
                            elif filename!=export_file_to_update:
                                update_exports_prompt = True
                            else:
                                exit_update_exports=True
                            processed_files[filename] = file_modified_time
                            last_file=filename

            # Clear the terminal screen before displaying summary
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"Checking files in {input_dir}. Last file processed: {last_file}")

            # Print summary messages if any, and keep LoadingSymbols.txt in
            # sync with the current stuck-symbol set (refreshed every loop
            # iteration, not just written once) -- write_filenames_to_file
            # is reused even though these are symbols, not filenames; the
            # function itself is generic (one string per line).
            if summary_messages:
                print("Summary of findings:")
                sorted_summary_messages = sorted(summary_messages.keys())
                for key in sorted_summary_messages:
                    print(summary_messages[key])
                joined_string = ",".join(sorted_summary_messages)
                print(joined_string)
                # normalize_for_reimport() here, not on sorted_summary_messages
                # itself -- that list still needs its original bracketed form
                # for the summary_messages[key] lookups above.
                reimport_symbols = sorted({normalize_for_reimport(s) for s in sorted_summary_messages})
                write_filenames_to_file(reimport_symbols, loading_symbols_file, label="symbols")
            elif os.path.exists(loading_symbols_file):
                # No stuck symbols this pass -- clear stale data rather than
                # leaving a file that claims symbols are still stuck.
                write_filenames_to_file([], loading_symbols_file, label="symbols")

            # continue if no files with data is processed
            if not processed_files:
                continue

            if ignore_keyword_issues=="Y":
                if not any(final_partial_filename in f for f in processed_files):
                    continue

                # 1. Extract the filenames
                extracted_list = extract_filenames(summary_messages)

                if len(extracted_list)>0:
                    cnt = len(extracted_list)
                    print(f"--- Incomplete Files {cnt} ---")
                    for index, filename in enumerate(extracted_list):
                        print(f"[{index + 1}] {filename}")
                    # 2. Write to file directly
                    write_filenames_to_file(extracted_list, incomplete_files_list_path)
                    sys.exit(2)

            if any(WORD_TO_FIND in cell for row in output_list.values() for cell in row):
                continue

            # Exit condition check: Verify if the final file has been processed
            if update_exports=="N":
                if not any(final_partial_filename in f for f in processed_files):
                    continue

                # Verify all files are processed
                all_processed_files = read_files_list(files_list_path)
                processed_files_without_date = {re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename) for filename in processed_files}
                missed_files = set(all_processed_files) - processed_files_without_date

                if missed_files:
                    print("The following files were missed:")
                    for missed_file in missed_files:
                        print(missed_file)
                        remove = input(f"Do you want to remove '{missed_file}' from FilesList.txt? (y/Y to remove): ").strip().lower()
                        if remove == 'y':
                            with open(files_list_path, 'w') as file:
                                for f in all_processed_files:
                                    if f != missed_file:
                                        file.write(f + '\n')
                    continue

            else:
                if not exit_update_exports:
                    if update_exports_prompt:
                        comp = input(f"Process more files? Press y to process more files: ").strip().lower()
                        if comp != 'y':
                            copy_and_add_empty_lines(export_file_latest, export_file_to_update_indir, lines_to_ignore)
                        update_exports_prompt=False
                    continue

            break

        # Sort output list by Symbol (assumed to be in the first column)
        sorted_output_list = dict(sorted(output_list.items()))

        # Write to output CSV file
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(archive_dir, exist_ok=True)
        outfile_name = f"{output_filename_prefix} {get_export_date('%Y-%m-%d')}.csv"
        output_file = os.path.join(output_dir, outfile_name)
        archive_file = os.path.join(archive_dir, outfile_name)

        wait_for_file_to_close(output_file)

        with open(output_file, 'w', newline='', encoding="UTF-8") as file:
            writer = csv.writer(file)
            output_headers.insert(0,"Date")
            output_headers.insert(1,"Time")
            writer.writerow(output_headers)
            for symbol, data in sorted_output_list.items():
                data.insert(0, get_export_date("%m/%d/%Y"))
                data.insert(1, get_export_time())
                writer.writerow(data)

        sync_and_validate_count(sorted_output_list, rowcount_file)
        # delete processed files if everything is successful
        delete_processed_files(input_dir, processed_files)


    finally:
        if lock_file_path:
            release_lock()

    if output_file:
        # 2026-08-17: wait for TOS.lock (a real acquire, not just a check --
        # is_lock_free()'s skip-if-contended was tried and reverted), then
        # open Excel once it's actually acquired, then release it right
        # away -- bounded to just the open moment, not however long the
        # user leaves Excel open afterward.
        if excel_open_lock_path:
            acquire_lock(excel_open_lock_path)
        try:
            open_and_wait(output_file)
        finally:
            if excel_open_lock_path:
                release_lock()

        time.sleep(3)
        wait_for_file_to_close(output_file)
        wait_for_file_to_close(archive_file)
        shutil.move(output_file, archive_file)


# =====================================================================
# ---- COMBINED PIPELINE ORCHESTRATION (new, 2026-08-16) ----
# =====================================================================

def derive_merge_params(watchlist_file, save_folder):
    """Derive monitor_directory()'s extra parameters from the watchlist
    recipe CSV and save_folder, instead of requiring separate CLI args:
      - working_directory = parent of save_folder (save_folder IS the
        'input' subfolder monitor_directory watches -- per project
        convention, save_directory == working_dir/input).
      - output_filename_prefix = the 'Name' column (category, e.g. "TOSD")
        from the first WL row.
      - final_partial_filename = "{Name}_{watchlist_name}.csv" from the
        LAST 'WL' row (e.g. "TOSD_WL16.csv") -- the fragment that marks all
        watchlists as downloaded, same file download_watchlist() itself
        writes for that row.

    2026-08-17: deliberately does NOT consider 'RELOADWL99' rows here
    (tried that, reverted -- see git history/session notes). RELOADWL99
    skips its own export entirely when there's nothing to reload
    (LoadingSymbols.txt empty), so treating it as "the final fragment"
    means that fragment sometimes never arrives, and monitor_directory()'s
    loop then waits forever for a file that's never coming -- an actual
    hang, reproduced live. It doesn't need to be the marker anyway: main()
    fully finishes (RELOADWL99 included, skip or not) BEFORE monitor_
    directory() is even called, so by the time the merge loop starts
    scanning, whatever RELOADWL99 did or didn't produce is already final
    on disk -- final_partial_filename only needs to be A row that's
    guaranteed to always produce a fragment, which the last plain WL row
    always does.
    """
    df = pd.read_csv(watchlist_file)
    wl_rows = df[df['Type'] == 'WL']
    if wl_rows.empty:
        raise ValueError(f"No 'WL' rows found in watchlist recipe '{watchlist_file}' — "
                          "cannot derive merge parameters (output prefix / final fragment).")

    first_row = wl_rows.iloc[0]
    last_row = wl_rows.iloc[-1]
    output_filename_prefix = str(first_row['Name'])
    final_partial_filename = f"{last_row['Name']}_{last_row['watchlist_name']}.csv"
    working_directory = os.path.dirname(os.path.normpath(save_folder))
    return working_directory, output_filename_prefix, final_partial_filename


def run_pipeline(watchlist_file, save_folder, images_folder, update_exports='N',
                  ignore_keyword_issues='N', skip_download='N', lock_file_path=None):
    """Download stage (main(), same logic as the original standalone
    TOSDownloads.py's __main__ block -- reprocessing of incomplete
    watchlists now happens inside main()'s own RELOADWL99 handling, before
    WL99's reload/export, not as a separate pass here) followed by the
    merge stage (monitor_directory(), same logic as the original standalone
    MergeExports.py), as one combined run under a single lock.

    skip_download='Y' -- merge-only mode (2026-08-16, restored): skips the
    whole TOS GUI-automation download stage and goes straight to merging
    whatever fragment CSVs are already sitting in save_folder. Same purpose
    as the old ProcessTOSExports.bat's "TOSType Y" merge-only branch (which
    called standalone MergeExports.py directly) -- use when you exported
    watchlists by hand (e.g. via the empty placeholder files) instead of
    running the automated clicker, or when download succeeded but the merge
    step itself failed/was interrupted and you don't want to re-run the
    slow GUI automation just to retry the merge.
    """
    global incomplete_files

    if skip_download != 'Y':
        # 2026-08-19: no separate post-hoc retry pass here anymore -- the
        # reprocess decision now happens BEFORE WL99's own reload/export,
        # inside run_recipe_rows()'s RELOADWL99 branch (gated on loading
        # SYMBOL count, not incomplete FILE count), since reprocessing
        # after WL99 already exported was too late to matter: WL99 would
        # have reloaded from a stale LoadingSymbols.txt snapshot regardless.
        main(watchlist_file, save_folder, images_folder, False)

        if len(incomplete_files) > 0:
            print('\n')
            print('=' * 50)
            print(f"--- {len(incomplete_files)} fragment(s) still incomplete after WL1..WL16 + WL99 "
                  "reload/retry. Left for the merge stage / next run to resolve. ---")
            print(incomplete_files)
            print('=' * 50)
            print('\n')
    else:
        print("\n--- Merge-only mode: skipping the download stage ---")
        # 2026-08-17: merge-only mode never calls main(), so the RELOADWL99
        # row (and its WL99 reload+export) never fires on its own -- any
        # symbol still genuinely stuck "Loading" would otherwise just sit
        # there forever, since monitor_directory() only ever passively waits
        # on that word below, it never resolves it. find_genuinely_stuck_
        # symbols() (not a naive per-file union -- see its own docstring for
        # why that re-triggered already-resolved symbols on a second
        # merge-only run) finds what's ACTUALLY still stuck across every
        # fragment, write those into LoadingSymbols.txt (do_reloadwl99()'s
        # own input), and run the SAME RELOADWL99 entry point a normal run
        # would have hit.
        #
        # Also always ensure the WL99 fragment itself exists -- if it's
        # simply missing (not yet exported this run) with nothing stuck,
        # still run RELOADWL99 to export it (do_reloadwl99() itself already
        # skips the reload step when LoadingSymbols.txt is empty, same as a
        # normal run). But if it's ALREADY there and nothing's stuck, skip
        # touching TOS entirely -- a merge-only retry shouldn't re-open TOS
        # every time just to re-export something that's already correct.
        df = pd.read_csv(watchlist_file)
        reload_rows = df[df['Type'] == 'RELOADWL99']
        if not reload_rows.empty and os.path.isdir(save_folder):
            reload_row = reload_rows.iloc[0]
            stuck_symbols = find_genuinely_stuck_symbols(save_folder)
            wl99_fragment = os.path.join(save_folder, f"{reload_row['Name']}_{reload_row['watchlist_name']}.csv")

            if stuck_symbols or not os.path.exists(wl99_fragment):
                working_dir = os.path.dirname(os.path.normpath(save_folder))
                loading_symbols_file = os.path.join(working_dir, 'LoadingSymbols.txt')
                reimport_symbols = sorted({normalize_for_reimport(s) for s in stuck_symbols})
                write_filenames_to_file(reimport_symbols, loading_symbols_file, label="symbols")
                if stuck_symbols:
                    print(f"\n--- Merge-only mode: {len(stuck_symbols)} symbol(s) genuinely still "
                          "'Loading' (no fragment has resolved data for them) -- running RELOADWL99 "
                          "to reload and re-export WL99. ---")
                else:
                    print(f"\n--- Merge-only mode: {os.path.basename(wl99_fragment)} is missing -- "
                          "running RELOADWL99 to export it (nothing to reload). ---")
                # This IS real TOS-GUI automation (unlike the rest of
                # merge-only mode), so ensure_tos_active() first, same as
                # main() itself does before its own row loop.
                ensure_tos_active(images_folder)
                recipe_dir = os.path.dirname(os.path.abspath(watchlist_file))
                do_reloadwl99(reload_row, save_folder, images_folder, recipe_dir)

    # 2026-08-17: release the TOS.lock here -- right after every WL row AND
    # the RELOADWL99 row's WL99 export have all finished (main() processes
    # every row in order, WL99 last), not at the very end of this whole
    # function. The merge stage below (monitor_directory()) never touches
    # TOS/pyautogui -- it's pure file I/O -- and different TOSTypes write to
    # completely separate folders, so it needs neither the lock nor mutual
    # exclusion against another TOSType's own run. Holding the lock through
    # the merge-wait loop (which can run arbitrarily long while symbols are
    # still "Loading") previously blocked every other queued TOSType's
    # download stage for no reason -- now they can acquire it and start
    # their own download the moment this one's done exporting, while this
    # run's merge-wait keeps polling in the background with no lock held.
    # Safe to call even if the download stage was skipped (merge-only mode)
    # or already released for some other reason -- release_lock() is a
    # no-op once fd is already None.
    release_lock()

    # Recipes with no 'WL' rows (e.g. ReloadWL99.csv -- a click-sequence-only
    # recipe that loads symbols into a watchlist, nothing to export/merge)
    # have nothing for the merge stage to do. Skip it rather than crash in
    # derive_merge_params, which requires at least one WL row to derive the
    # output prefix / final fragment name from.
    if not (pd.read_csv(watchlist_file)['Type'] == 'WL').any():
        print("\n--- No 'WL' rows in this recipe -- nothing to merge, done. ---")
        return

    working_directory, output_filename_prefix, final_partial_filename = \
        derive_merge_params(watchlist_file, save_folder)
    print(f"\n--- Merging exports: {save_folder} → "
          f"{os.path.join(working_directory, 'output')} "
          f"(prefix='{output_filename_prefix}', final='{final_partial_filename}') ---")
    # lock_file_path=None: this call's own lock_file_path param guards
    # monitor_directory's OWN acquire/release around its whole merge-wait
    # loop (the old standalone-MergeExports.py behavior) -- must stay None
    # here, since the download stage above already released the lock and
    # re-acquiring it for the whole merge-wait would recreate the exact
    # blocking problem fixed earlier. excel_open_lock_path is different: this
    # run's real TOS.lock path, used only to gate the Excel auto-open on
    # is_lock_free() (see monitor_directory's own comment at that call site).
    monitor_directory(working_directory, final_partial_filename, 3,
                       output_filename_prefix, update_exports, ignore_keyword_issues, None,
                       excel_open_lock_path=lock_file_path)


# --- ENTRY POINT ---
if __name__ == "__main__":

    # --check-images: dry-run preflight, no TOS interaction -- checks every
    # image a recipe (and its RELOADWL99 sub-recipe, if any) would need
    # against images_folder and reports what's missing. Exits 1 if anything
    # was missing across ANY of the given CSVs, 0 if everything's present.
    if len(sys.argv) >= 2 and sys.argv[1] == '--check-images':
        if len(sys.argv) < 4:
            print("Usage: python TOSDownloads.py --check-images <images_folder> <watchlist_csv> [<watchlist_csv> ...]")
            print("Example: python TOSDownloads.py --check-images Images TOSD.csv TOSL.csv TOSO.csv TOSW.csv")
            sys.exit(1)
        images_directory = sys.argv[2]
        watchlist_files = sys.argv[3:]
        total_missing = sum(len(check_recipe_images(wf, images_directory)) for wf in watchlist_files)
        sys.exit(1 if total_missing else 0)

    if len(sys.argv) < 5:
        print("Usage: python TOSDownloads.py <path_to_watchlist_csv> <save_directory> <images_directory> "
              "<lock_file_path> [update_exports=N] [ignore_keyword_issues=N] [skip_download=N]")
        print("Example: python TOSDownloads.py watchlists.csv C:\\TOS_Downloads\\input c:\\TOS_images c:\\lf.lock")
        print("  save_directory is the 'input' folder (working_dir/input) -- output/ and archive/")
        print("  are created as siblings of it under working_dir.")
        print("  skip_download=Y -- merge-only mode: skip the TOS download stage entirely and just")
        print("  merge whatever fragment CSVs are already in save_directory.")
        sys.exit(1)

    try:
        watchlist_file_path = sys.argv[1]
        save_directory = sys.argv[2]
        images_directory = sys.argv[3]
        lock_file_path = sys.argv[4]
        update_exports_arg = sys.argv[5] if len(sys.argv) > 5 else 'N'
        ignore_keyword_issues_arg = sys.argv[6] if len(sys.argv) > 6 else 'N'
        skip_download_arg = sys.argv[7] if len(sys.argv) > 7 else 'N'

        try:
            acquire_lock(lock_file_path)
            run_pipeline(watchlist_file_path, save_directory, images_directory,
                         update_exports_arg, ignore_keyword_issues_arg, skip_download_arg,
                         lock_file_path=lock_file_path)
        finally:
            release_lock()

        time.sleep(30)
        wait_time=5
        print("Trying to acquire/release locks by yeield to other programs....")
        # 2026-08-17: was a hand-inlined double acquire/release + timing
        # check -- now shares is_lock_free()'s implementation instead of
        # duplicating it (that function also gates the Excel auto-open,
        # see monitor_directory()).
        while not is_lock_free(lock_file_path, wait_time):
            time.sleep(wait_time)

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1) # Error exit code
