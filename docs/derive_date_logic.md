# Derive Date Logic — the anchor model

How the derive date `D` is chosen for each load, and which rule each source
follows. This replaces the old "derive for whatever date is in the filename"
behaviour. `CLAUDE.md` carries a one-line pointer; detail lives here.

Introduced 2026-06-05.

## The one rule that matters

**`D = MAX(export_date) FROM hist_td` (TOSD).**

TOSD is exported once per session, at market close, with `export_time` fixed at
16:30. Its latest `export_date` is therefore the most recent *completed* market
session, and it is the **only** thing that advances the derive date.

Consequences:

- `snapshot_date` on every `hist_*` table is **informational only**. Derivation
  keys off `export_date`. (`snapshot_date` is synthesised from the file's Export
  Date column and is kept for provenance/PK, but no derive decision depends on
  it.)
- A load never derives "the date in its filename". Every load — intraday TOSL/Y,
  a periodic RR/PS/ETF file, a CS/F position file — re-derives the **current
  anchor** `D`. Only a TOSD load can move `D` forward.
- If `hist_td` is empty / has no `export_date`, `get_anchor_date()` returns
  `None`: the loader raises a "TOSD missing" warning and does **not** derive.

`get_anchor_date(session)` (in `etl/derive.py`) is the single resolver.

## Worked example (today = Fri 6/5)

- **Intraday 6/5, before the close.** TOSD's latest `export_date` is still 6/4
  (Thursday's close), so `D = 6/4`. You load an intraday TOSL or Y for fresh
  prices; its own `export_date` is 6/5, which ≠ D — so it is **excluded** from
  the anchored fields and only updates `drv_quote`, tagged `as_of_date = 6/4`
  ("last market close bucket").
- **After the 6/5 close.** TOSD 6/5 lands → `D` advances to 6/5. The EOD
  TOSL/TOSW/Y (`export_date = 6/5`) now feed the anchored fields for 6/5
  ("today's close bucket").
- **RR.** You load RR on 6/5 but it carries the prior close — `export_date =
  6/4`. It naturally lands in the 6/4 anchor via the carry-forward window.

## Per-source rules

| Source | Tables | Rule for anchor date D |
|---|---|---|
| **TOSD** | `hist_td` | **Anchor.** `D = MAX(export_date)`. Also defines the symbol universe: `drv_symbols` = symbols in `hist_td WHERE export_date = D`. |
| **TOSL, TOSW, Y** | `hist_tl`, `hist_tw`, `hist_y` | **Exact match `export_date = D`**, latest `sequence` per symbol. No carry-forward. A symbol absent from D's export is dropped from the anchored fields. |
| **drv_quote feed** | `hist_tl`, `hist_y`, `hist_td` | **Latest available price** (snapshot up to *today*, not capped at D) on the current anchor date, so an intraday export refreshes the live quote. Row tagged `as_of_date = D`. Historical re-derives are capped at their own date (no look-ahead). |
| **RR, CALL, ETF/ETFCHG, II/IICHG, SSS, PS** | `hist_rr`, `hist_call`, … | **Carry-forward**: latest `snapshot_date <= D` per symbol. These feeds are weekly/periodic and legitimately predate D. |
| **CS, F (positions)** | `hist_cs`, `hist_f` | **Carry-forward** latest `<= D`. Sold-position marking unchanged. |
| **TOSO** | `hist_to` | **Carry-forward** `<= D` (loaded only "maybe" each day — treated as periodic, not anchor-locked). |
| **CST, FT (transactions)** | `hist_cst`, `hist_ft` | Unaffected. Realized-gain path keyed by `trade_date`, never `derive_all`. |

### Symbol universe — the key leverage point

`drv_symbols` is the master ticker list for D, built **only** from
`hist_td WHERE export_date = D`. Every downstream component table
(`drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio`) is built
`FROM drv_symbols s ... WHERE s.as_of_date = D`, so a symbol not in the universe
is automatically excluded from the entire cascade. "Missing from today's TOSD =
excluded from all calculations for D." There is no `ref_sector` backfill and no
per-symbol carry-forward of the universe.

> Edge note: a symbol that appears only in a non-TOSD feed (e.g. an ETF tracked
> in `hist_etf`/`hist_ii` but never in TOSD) will *not* appear in the universe.
> This is intended by the anchor model. If such symbols must always be present,
> widen the `drv_symbols` source to a UNION of the daily-EOD sources at
> `export_date = D` — but keep it exact-date (no `<= D`).

## What the anchor-locked reads look like in code

In `etl/derive.py`, the daily-EOD CTEs changed from per-symbol carry-forward:

```sql
-- before
WHERE h.snapshot_date <= :d
ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
```

to exact-match on the anchor with sequence as the tie-breaker:

```sql
-- after
WHERE h.export_date = :d            -- anchor-locked
ORDER BY h.tos_symbol, h.sequence DESC
```

`sequence` (populated from Export Time) disambiguates multiple loads sharing the
same `export_date` — e.g. an intraday TOSL and the 16:30 EOD TOSL on the same
calendar day. The anchored fields take the **max-sequence** (latest) row.

`ANCHOR_LOCKED_SOURCES = ("hist_tl", "hist_td", "hist_tw", "hist_y")` lists the
daily-EOD tables these rules apply to.

## Loader behaviour (`etl/etl_load.py`)

After a successful load, `load_one_file` resolves `D = get_anchor_date()` and
runs `derive_all(session, D)` — it no longer derives the filename date. If `D`
is `None` (no TOSD yet) it logs a "cannot anchor a derive date" warning to
`meta_scheduler_log` and skips. The CST/FT transaction branches are untouched.

## Missing-file warnings

`warn_missing_eod_sources(session, D)` (called at the end of `derive_all`)
checks each `ANCHOR_LOCKED_SOURCES` table for rows at `export_date = D` and
writes a `meta_warning` row (screens `dashboard` + `actionable`,
`code='missing_eod_source'`) for any that are absent. The screens render the
notification bar via `GET /api/warnings`. Schedule-level "overdue/missing"
detection in the File Monitor (`docs/file_monitor_logic.md`) is unchanged and
complementary.

## Validating a change

There is no idempotency hazard — every derive still does
`DELETE WHERE as_of_date = D` then INSERT. To apply this logic across history,
use **Force Re-derive** in the File Monitor (or
`python -m etl.derive_freshness`-style re-runs). Spot-check by confirming a
symbol present in TOSD only on some dates appears in `drv_symbols` exactly on
those dates and is absent on others.
