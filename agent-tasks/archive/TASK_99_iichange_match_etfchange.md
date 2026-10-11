# TASK_99 — IIChange file = ETFChange structure (exactly)

**Type:** implementation (revises TASK_95's `emit.py`). **Author:** Cowork. **Owner:** Developer.
**Depends on / revises:** TASK_95. **Run BEFORE** the TASK_95 tester round so the tester
verifies the corrected format.

## Decision (Ashok, 2026-06-27)

There is no historical IIChange sample. Decision: **make the emitted IIChange file
byte-for-byte identical in structure and columns to the ETFChange file.** Same sheet,
same headers (including the leading spaces), same column order and value mapping — only
the filename differs (`IIChange …xlsx` vs `ETFChange …xlsx`).

## Target format (copy ETFChange exactly)

- Sheet: **`Data Sheet`**
- Header row: **`Date`**, **` Description`**, **` Ticker`**, **` Outlook`**, **` Action`**
  (leading spaces on columns 2–5 — must match ETFChange so Excel import parity holds).
- Value mapping per row (same as `render_etf_changes`):
  `snapshot_date → Date`, `description → " Description"`, `symbol (or tos_symbol) → " Ticker"`,
  `side → " Outlook"`, `action → " Action"`.

## Steps

1. **`etl/hedgeye/emit.py` — rewrite `render_investing_ideas`** so it produces the format
   above. Simplest correct implementation: make it identical to `render_etf_changes`
   (same sheet, headers, and value mapping); only the caller/filename differ. Update the
   docstring to note it now mirrors ETFChange by decision.
2. **`tests/test_hedgeye_emit.py` — update the investing_ideas tests** to assert the new
   shape (sheet `Data Sheet`; headers `Date`, ` Description`, ` Ticker`, ` Outlook`,
   ` Action` with leading spaces; correct values/order). They currently assert the old
   `IIchg`-sheet format and will fail until updated.
3. **Confirm the loader still ingests it.** `load_iichg` resolves the sheet via
   single-sheet fallback and maps columns by **header name** (case-insensitive,
   space-stripped), so `Date/ Ticker/ Outlook/ Description/ Action` all map correctly
   regardless of order: Date→event_date, Ticker→symbol, Outlook→outlook,
   Description→description, Action→change_str. Verify on the live DB that an emitted
   IIChange file loads into `hist_iichg` with the same values the old direct-insert
   produced (incl. the add and the MDB-style remove).

## How to verify

- `pytest tests/test_hedgeye_emit.py -q` → green with the updated assertions.
- Diff a generated `IIChange 2026-06-26.xlsx` against a real `ETFChange …xlsx`: sheet
  name + header row (with leading spaces) identical; only the data differs.
- Live: emit + scheduler load → `hist_iichg` rows match the prior direct-insert output
  (symbol, outlook, change_str/action); add + remove both land.
- Full `pytest tests/` → no new failures.

## Done criteria

`render_investing_ideas` emits an ETFChange-identical file (`Data Sheet`; the five
leading-space-matched headers); tests updated and green; `load_iichg` ingests it into
`hist_iichg` correctly. Log to `DEV_HANDOFF.md`, end `ALL_DONE`. No commits — Ashok
commits from Windows.
