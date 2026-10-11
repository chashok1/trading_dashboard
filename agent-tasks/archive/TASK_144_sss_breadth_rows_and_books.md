# TASK_144 — SSS breadth: rows AND analyst books per sector; CALL long/short split

## Context

`hist_sss` carries `sector`, `days_on`, `pct_delta` and `anlst_best_idea_rank`
("4/10", "Bench", "KMSignal"). `etl/derive_source_standing.py::_build_sss`
parses the numerator into `rank` and **discards the denominator** — which is
the size of that analyst's ranked long book. Nothing counts rows or books per
sector over time. The user's read ("restaurants: 80 → 35") is correct on the
row side; the book side tells a different story (Sep 14: rows 86 → 46, −47%;
books 110 → 105, −5%; Restaurants rows 10 → 3 but book 1 → 4). Both counts
are required — Addendum B/§3.

## Goal

1. **`drv_sss_breadth`** `(as_of_date, snapshot_date, sector, n_rows,
   n_ranked, n_bench, n_km, book_size, book_size_asof, top3 JSONB,
   avg_strength, median_days_on, n_rows_med13, n_rows_med26, adds, removes,
   PRIMARY KEY (as_of_date, sector))` + a `sector='_TOTAL'` row per date.
   - `n_rows` = your original count (everything on the list);
   - `book_size` = MAX denominator among ranked rows; if a sector has no
     ranked row that snapshot, **carry the last known value forward** and
     set `book_size_asof` to its date (Global Tech, Sep 14 — 3 KMSignal
     rows, no ranked names);
   - `top3` = names with rank ≤ 3, ordered; `avg_strength` = mean
     `pct_delta`; `adds/removes` from `hist_sss_change` in the week;
   - sector strings normalized via a small map (`Sof tware`→`Software`,
     `Industnals`→`Industrials` …). **First run
     `SELECT DISTINCT sector, analyst FROM hist_sss ORDER BY 1` and put the
     result in DEV_HANDOFF** — the user says the DB copy is clean; confirm.
2. `etl/derive_sss_breadth.py`, wired in `derive_all()` next to
   `derive_market_read` (TASK_143), non-critical.
3. **`GET /api/market-read/sectors?date=`**: per sector the columns above,
   13-wk row sparkline series, RR/ETF chips for the sector's proxy ETF
   (via `ref_symbol_theme`), and the user's $ in the sector
   (`drv_category_perf` axis='sector'). A `divergence` flag when
   `n_rows` fell >25% while `book_size` did not fall.
4. **CALL long/short split (Addendum D1)** — in `db/baseline.sql`
   `v_source_edge_scorecard`: add `side` ('long'/'short') so CALL, RR and
   ETF longs and shorts are separate rows; `etl/derive_source_edge.py`
   reads the long side only for the weak-buy list (unchanged behaviour).
5. Freshness contract row for `drv_sss_breadth` (weekly, `max_lag_days` 8).
6. Docs: `docs/migrations.md`; design doc status line.

## Files expected to change

- `db/baseline.sql`, `etl/derive_sss_breadth.py` (new), `etl/derive.py`
- `api/routers/cockpit.py`, `etl/derive_source_edge.py`
- `docs/migrations.md`, `docs/market_state_factor_sss_design.md`, `DEV_HANDOFF.md`

## How to verify

1. Distinct sector/analyst list captured in `DEV_HANDOFF.md`; normalization
   map covers every variant.
2. For snapshot 2026-09-14 the table reproduces the mockup's sector cards:
   Software rows 10 / book 6; Financials 7 / 14; Healthcare 4 / 6;
   Restaurants 3 / 4 (was 1 on Aug 24); Industrials 0 / carried 13 with
   `book_size_asof`=2026-08-24-ish; Energy 3 / 18 (new); `_TOTAL` rows 46,
   books 105. For 2026-08-24: rows 86, books 110.
3. Global Tech on 2026-09-14: `n_km`=3, `n_ranked`=0, `book_size` carried
   from the prior snapshot with `book_size_asof` set.
4. `divergence` true for Restaurants on 2026-09-14, false for Financials.
5. `v_source_edge_scorecard` has separate `side` rows; CALL short-side
   `edge_20d` and `n` reported in the handoff (July pooled: +5.26, n=82).
6. Idempotent re-derive; freshness check passes.
