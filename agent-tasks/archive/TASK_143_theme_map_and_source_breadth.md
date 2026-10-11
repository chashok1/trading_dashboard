# TASK_143 — Theme map + source breadth + theme stance (data layer for Market Read)

## Context

Design: `docs/market_state_factor_sss_design.md` (§1–§3 for the analysis, the
**Addendum A–H** for what was decided; A–H win where they differ). Mockup with
real values: `docs/mockups/market_read_one_picture_mockup.html`.

Four Hedgeye lists are loaded daily/weekly (`hist_rr`, `hist_etf`, `hist_ps`,
`hist_sss`, plus `hist_call`) and nothing aggregates them over time. RR alone is
a complete macro board (rates, credit, USD, FX, commodities, indexes, sector
ETFs) with a stance per symbol; ETF Pro is a factor stance list; PS its
conviction ranking; SSS sector breadth. This task builds the tables everything
else reads.

## Goal

1. **`ref_symbol_theme`** (`db/baseline.sql` + `db/seeds_symbol_theme.sql`):
   `(symbol TEXT, source_code TEXT, theme TEXT, weight NUMERIC DEFAULT 1,
   inverted BOOLEAN DEFAULT FALSE, quad_category TEXT, quad_sub_category TEXT,
   PRIMARY KEY (symbol, source_code, theme))`.
   - `source_code` because the same idea has different symbols per feed
     (RR `USD` vs ETF `UUP`/`DBMF`; RR `UST10Y` vs ETF `PFIX`/`TLT`).
   - `inverted`: RR FX crosses quoted vs USD (EUR/USD bearish ⇒ USD bullish);
     RR yields (UST bullish ⇒ "Rates ↑").
   - `quad_category`/`quad_sub_category` = the `ref_quad_outlook` key so the
     Quad column is a join, never a second map.
   - Seed the 22 themes in Addendum B with every symbol that appears in the
     Sep 2026 RR / ETF / PS files (`etl/working/`), ~90 rows. Themes:
     Rates↑ · Duration · Credit · USD · Volatility · Cash/short FI · Large
     caps · Small caps · Breadth · Momentum · Defensives · Cyclicals ·
     Healthcare · Tech/software · Semis · Energy · Precious metals ·
     Industrial metals · Ags · Crypto · Developed intl · Emerging.
   - Stocks (SSS, CALL) are NOT seeded here — they map to themes through
     `ref_sector` (sector → theme) at derive time.

2. **`drv_source_breadth`** `(as_of_date, source_code, n_bull, n_bear,
   n_neutral, net, n_total, flips_vs_prior, PRIMARY KEY (as_of_date,
   source_code))`. RR daily from `hist_rr` (`outlook`); ETF from `hist_etf`
   (`outlook` BULLISH/BEARISH); PS = count on list; SSS = rows; CALL from
   `hist_call` (`outlook`). `flips_vs_prior` = symbols whose outlook differs
   from the prior snapshot (RR only; NULL elsewhere). Idempotent per date.

3. **`drv_theme_stance`** `(as_of_date, theme, rr, etf, ps, sss, call, price,
   stance, agree_n, trend_1w, trend_4w, quad_says, quad_conflict, members
   JSONB, PRIMARY KEY (as_of_date, theme))`:
   - each source cell ∈ {'B','S','N','M','—'}: B/S when ≥ 2/3 of that
     source's members with a stance agree; M(ixed) otherwise; '—' no member;
   - `price` = `n_above/n_tracked` from the exact query behind
     `/api/actionable/quad-rotation` (`api/routers/dash.py`) — reuse, don't
     reimplement — stored as `"pct (n_above/n_tracked)"` text + numeric cols;
   - `stance` = majority of RR/ETF/PS/SSS (B vs S; N if tie or all N);
     **CALL never votes** (Addendum D); `agree_n` = count of those four
     voting the stance direction;
   - `quad_says` = the monthly-weighted stance the Quad Rotation tiles use
     (`/api/quad/band-factors` logic) via `quad_category/sub_category` —
     **never a hard-coded quad** (Addendum F);
   - `quad_conflict` = stance and quad_says both non-neutral and opposite;
   - `trend_1w/4w` = stance vs 5 / 20 anchor dates ago ('up','down','flat');
   - `members` = per-source symbol lists + each symbol's stance, for hover.

4. **`etl/derive_market_read.py`** builds 2 and 3; wired into `derive_all()`
   after `drv_category_perf` and `drv_market_stat`, non-critical
   (`_safe`, failure can't break the cascade).

5. **`GET /api/market-read?date=`** (`api/routers/cockpit.py`): returns
   `{as_of, headline, breadth:[…13-wk per source…], flip_days:[…],
   themes:[…], quad:{label, blend, conflicts}}`. `headline` is generated
   from theme stances by rule (which macro themes are B/S), one sentence,
   plus the conflict summary ("lists more defensive than the model on: …").

6. **Freshness contract rows** for both new tables (`ref_freshness_contract`,
   TASK_142): `max_lag_days` 1 for RR-driven, 8 for weekly.

7. Docs: `docs/migrations.md`; `docs/market_state_factor_sss_design.md`
   status line → "built (TASK_143)".

## Files expected to change

- `db/baseline.sql`, `db/seeds_symbol_theme.sql` (new)
- `etl/derive_market_read.py` (new), `etl/derive.py` (cascade wiring)
- `api/routers/cockpit.py`
- `docs/migrations.md`, `docs/market_state_factor_sss_design.md`
- `DEV_HANDOFF.md`

Nothing on the decision path (`derive_actionable.py`, rules, thresholds).

## How to verify

1. `python -m db.init_db` idempotent; `ref_symbol_theme` seeded; every
   seeded `(symbol, source_code)` exists in the matching `hist_*` table for
   the latest snapshot (report any that don't).
2. Re-derive the anchor; `drv_source_breadth` for 2026-09-20/21 matches the
   mockup's numbers: RR macro net 0, ETF 17/20, PS 18, SSS rows 46;
   `flips_vs_prior` for RR on 2026-09-14 = 10, 09-17 = 9, 09-18 = 9.
3. `drv_theme_stance` for the anchor: Small caps S (RR S, ETF S), Energy B
   (RR B, ETF B, PS B), Defensives S, Credit S, Cash/short FI B. `quad_says`
   equals the Quad Rotation tile arrow for the same category on the same
   date; `quad_conflict` count is reported (expected ~6 under the Q2 blend).
4. Backfill 60 anchor dates; `trend_1w/4w` populated; idempotent re-run
   changes nothing.
5. `/api/market-read` returns in < 500 ms; `headline` names the B and S
   macro themes and the conflict list.
6. `daily_health_check` shows both tables under the freshness contract, no
   breach.
