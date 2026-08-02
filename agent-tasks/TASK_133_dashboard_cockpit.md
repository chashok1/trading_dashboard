# TASK_133 — Dashboard Cockpit (complete build)

## Goal

Replace the Dashboard landing screen (`/`) with a **daily risk cockpit**. Every
decision in this spec is final — **do not stop to ask questions.** Where a choice is
not covered here, pick the option most consistent with the existing codebase, implement
it, and record the choice in `DEV_HANDOFF.md`.

Design reference: `docs/dashboard_cockpit_design.md` (authoritative).
Supersedes: `docs/dashboard_attention_panel_design.md` (delete at Phase 8).

**Cowork has no DB access.** Every SQL statement, migration, derive run and threshold
calibration in this task is yours to execute.

### Ship order

Eight phases. Each is independently verifiable and independently useful — **commit-ready
at every phase boundary**. If you run out of time, stop at a phase boundary and write
`PHASE_<n>_DONE` in `DEV_HANDOFF.md` instead of `ALL_DONE`.

| Phase | Scope | Blocking? |
|---|---|---|
| 1 | Bug fixes + switch on data already being fetched | No |
| 2 | Reference tables + seeds | Blocks 3, 6 |
| 3 | Self-computed inputs → `drv_market_stat` | Blocks 6 |
| 4 | New feeds (ToS internals, KOSPI, VVIX, ETH, Cboe RVOL) | No |
| 5 | `drv_category_perf` (factor scorecard) | Blocks 6 |
| 6 | API endpoints | Blocks 7 |
| 7 | Frontend cockpit | — |
| 8 | Docs + tests | — |

Repo conventions that apply throughout: derives idempotent (`DELETE WHERE as_of_date=D`
→ INSERT); schema changes go in `db/baseline.sql`; **SQL command length ≤ 965 bytes**;
`tos_symbol` never raw `symbol` in `drv_*`; DB access via SQLAlchemy + psycopg v3 only;
**no commits or pushes — the user commits from Windows.**

---

# PHASE 1 — Fixes and free wins

Three live bugs and two disabled feeds. All small, all independently valuable.

### 1.1 MOVE volatility zone returns null

`/api/marketbar` returns `vol_low`/`vol_high` = `NULL` for metric_key `MOVE`, so the
MOVE tile renders with no zone badge. Cause: the lookup keys off `MOVE` but
`ref_vol_threshold` stores `MOVE:GIF`. In-code note at `web/market_bar.js:427-433`.

**Fix:** in `api/routers/marketbar.py`, make `_METRIC_TO_VOL_SYM` map `MOVE` →
`MOVE:GIF` (mirroring how `_METRIC_TO_RR_SYMBOL` already handles this class of
mismatch). Audit every other key in `_METRIC_TO_VOL_SYM` against the 8 rows actually in
`ref_vol_threshold` (`VIX`, `VVIX`, `RVX`, `VXN:CGI`, `GVZ:CGI`, `OVX:CGI`, `MOVE:GIF`,
`VXD`) and fix any other mismatches found. Remove the now-stale comment in
`market_bar.js`.

### 1.2 Two live definitions of "extended"

The server flags `is_hot`/`is_cold` at **0.85 / 0.15** (`ref_settings`
`macro_area_hot_pct` / `macro_area_cold_pct`). The rail JS defaults to **0.80 / 0.20**
because `/api/macro-areas` never sends `hot_pct` / `cold_pct` on the area objects,
so `web/macro_areas.js:209-211` always falls through to its hardcoded default.

**Fix:** add `hot_pct` and `cold_pct` to each area object in the `/api/macro-areas`
response, read from `ref_settings`. The JS fallback stays as a defensive default but
will no longer be reached. **Server value wins — 0.85 / 0.15 is canonical.**

### 1.3 `REF_MAPS` is redeclared and blanked

`etl/mappings.py:510` has `REF_MAPS: dict = {}`, which overwrites the populated dict
defined at line 31 (`Sctr`, `RRT`, `Desc`, `ISMH`). If this is reached at import time,
the `Sctr` → `ref_sector` and `RRT` → `ref_rrt` reference loads are silently dead.

**Do this in order:**
1. Verify against the live DB first — `SELECT COUNT(*), MAX(...) FROM ref_sector;` and
   the same for `ref_rrt`. Check `meta_etl_run` for recent Sctr/RRT loads.
2. If the tables are stale or empty, this is a real bug → delete line 510, reload the
   workbook, confirm row counts recover.
3. If they are current, something else populates them → leave the line, add a comment
   explaining why it is harmless.

**Record which case it was in `DEV_HANDOFF.md`.** Do not delete the line without
checking first.

### 1.4 Switch on the real HY spread

`BAMLH0A0HYM2` (ICE BofA US High Yield Option-Adjusted Spread) is enabled in
`ref_macro_series` and lands in `hist_macro` daily. But the `ref_market_metric` row
`HY` is `enabled=FALSE`, and `_METRIC_TO_RR_SYMBOL['HY'] = 'HYG'` — so the tape tile
labelled "HY" is showing the **HYG ETF price**, not a credit spread. Anyone reading
that tile believes they are watching spreads and is not.

**Fix:**
- Add a new metric_key **`HYOAS`** to `ref_market_metric`, `enabled=TRUE`, sourced
  `fred:BAMLH0A0HYM2`, label `HY Spread`, `value_format` = basis points (the FRED
  series is in percent — multiply by 100 for display, or keep percent with 2dp;
  pick one, be consistent, document it).
- **Leave the existing `HY` → `HYG` tile alone but relabel it `HYG`** so it is honest
  about what it shows.
- Higher value = worse (spread widening = stress). Add `HYOAS` to the `INVERTED`
  colour set in `web/market_bar.js` and to `_INVERTED_SYMBOLS` in
  `api/routers/macro_areas.py`.

### 1.5 Switch on the 2s10s curve

`T10Y2Y` is enabled in `ref_macro_series` and lands in `hist_macro` daily. The
`ref_market_metric` row `T2S10` is `enabled=FALSE` and nothing renders it.

**Fix:** set `enabled=TRUE`, confirm it resolves against `fred:T10Y2Y`, verify it
appears in `/api/macro`. Display in basis points.

### Phase 1 verification

```sql
-- 1.4 / 1.5 : both series have current data
SELECT series_id, MAX(obs_date), COUNT(*) FROM hist_macro
 WHERE series_id IN ('BAMLH0A0HYM2','T10Y2Y') GROUP BY 1;
-- 1.3 : reference tables are populated
SELECT 'ref_sector' t, COUNT(*) FROM ref_sector
UNION ALL SELECT 'ref_rrt', COUNT(*) FROM ref_rrt;
```
- `curl -s localhost:8000/api/marketbar | jq '.items[]|select(.metric_key=="MOVE")|{vol_low,vol_high}'`
  → both non-null.
- `curl -s localhost:8000/api/macro-areas | jq '.areas[0]|{hot_pct,cold_pct}'` → `0.85` / `0.15`.
- `/api/macro` includes `HYOAS` and `T2S10`.

---

# PHASE 2 — Reference tables and seeds

Four new `ref_*` tables. DDL into `db/baseline.sql`, seeds into new
`db/seeds_cockpit.sql`. All are tuning surfaces — **evaluation logic lives in Python,
not in these tables.** They carry weights, labels, active flags and transmission
mappings only.

```sql
-- Risk-dial gauge registry. Predicate logic is in etl/derive_risk_dial.py::GAUGES;
-- this table controls weight and on/off only.
CREATE TABLE IF NOT EXISTS ref_risk_gauge (
    gauge_key   text PRIMARY KEY,
    label       text    NOT NULL,
    weight      numeric NOT NULL DEFAULT 1,
    is_active   boolean NOT NULL DEFAULT TRUE,
    category    text,                 -- equity | vol | credit | rates | fx | commodity | breadth | positioning
    notes       text
);

-- Round-number price/yield levels the user considers meaningful.
CREATE TABLE IF NOT EXISTS ref_level_watch (
    id          serial PRIMARY KEY,
    tos_symbol  text    NOT NULL,
    level_value numeric NOT NULL,
    tolerance   numeric NOT NULL,     -- same units as level_value
    label       text,
    is_active   boolean NOT NULL DEFAULT TRUE,
    UNIQUE (tos_symbol, level_value)
);

-- Which parts of the book each fired gauge / pattern hits.
CREATE TABLE IF NOT EXISTS ref_gauge_transmission (
    id          serial PRIMARY KEY,
    gauge_key   text NOT NULL,        -- ref_risk_gauge.gauge_key OR ref_market_pattern.pattern_key
    axis        text NOT NULL,        -- 'sector' | 'asset_class' | 'style'
    category    text NOT NULL,
    UNIQUE (gauge_key, axis, category)
);

-- Named cross-asset co-movement patterns.
CREATE TABLE IF NOT EXISTS ref_market_pattern (
    pattern_key text PRIMARY KEY,
    label       text    NOT NULL,
    read_text   text    NOT NULL,     -- shown verbatim in the UI
    severity    text    NOT NULL DEFAULT 'warn',   -- 'severe' | 'warn' | 'info'
    is_active   boolean NOT NULL DEFAULT TRUE
);
```

### 2.1 `ref_risk_gauge` seed

Total active weight = **29**. These are a starting hypothesis, not a fitted result —
that is exactly why they live in a table.

| gauge_key | label | weight | category |
|---|---|---|---|
| `spx_top_range` | SPX at top of risk range | 3 | equity |
| `spx_bottom_range` | SPX below risk range | 2 | equity |
| `vix_elevated` | Equity vol elevated | 3 | vol |
| `vix_chop` | Equity vol in chop zone | 1 | vol |
| `move_elevated` | Bond vol elevated | 3 | vol |
| `credit_stress` | Credit stress | 3 | credit |
| `yield_level_watch` | Yields at a watched level | 2 | rates |
| `curve_inverting` | Curve inverting fast | 1 | rates |
| `dollar_strong` | Dollar at top of range | 2 | fx |
| `oil_shock` | Oil shock | 2 | commodity |
| `vrp_gone` | Volatility discount gone | 2 | vol |
| `gamma_negative` | Dealer gamma negative | 2 | positioning |
| `breadth_deteriorating` | Breadth deteriorating | 2 | breadth |
| `gold_vol_elevated` | Gold vol elevated | 1 | vol |

### 2.2 `ref_level_watch` seed

| tos_symbol | level | tolerance | label |
|---|---|---|---|
| `TNX:CGI` | 5.00 | 0.10 | 10Y at 5% |
| `TNX:CGI` | 4.50 | 0.10 | 10Y at 4.5% |
| `TNX:CGI` | 4.00 | 0.10 | 10Y at 4% |
| `DGS2:FRED` | 4.00 | 0.10 | 2Y at 4% |
| `VIX` | 20.00 | 1.00 | VIX 20 |
| `VIX` | 30.00 | 1.50 | VIX 30 |
| `$DXY` | 100.00 | 1.00 | DXY 100 |
| `/CL` | 100.00 | 2.00 | WTI $100 |
| `/GC` | 4000.00 | 50.00 | Gold $4000 |

**Units must match the instrument's stored scale.** `TNX:CGI` in particular may be
stored as `45.0` for 4.50% rather than `4.50` — check `drv_quote` before seeding and
adjust the seed values to the stored scale. Note the scale you found in `DEV_HANDOFF.md`.

### 2.3 `ref_market_pattern` seed

`read_text` is shown to the user verbatim. It states co-movement and historical read.
**It never asserts a cause** — no "the Fed did X", no "Japan intervened". This is a
hard content rule; the user's standing instruction is "never hallucinate."

| pattern_key | label | severity | read_text |
|---|---|---|---|
| `yen_bid` | Yen bid / carry unwind | severe | Carry trades unwinding. Momentum and high-beta longs are the exposed side. |
| `dollar_wrecking_ball` | Dollar wrecking ball | warn | Global tightening impulse. Commodities and non-US exposure pressured. |
| `rates_shock` | Rates shock | severe | Duration and long-duration equity repricing. |
| `credit_leads_equity` | Credit leading equity | severe | Credit moving before equity confirms. De-risk. |
| `flight_to_quality` | Flight to quality | warn | Classic risk-off. Defensives outperform. |
| `vol_regime_break` | Volatility regime break | severe | Volatility crossed a zone boundary today. Halve sizes on an upward break. |
| `korea_semis` | Korea → US semis | warn | Overnight Korean chip read-through. Check SOXX / NVDA / AVGO before the open. |
| `oil_squeeze` | Oil supply squeeze | warn | Energy and inflation impulse. |

### 2.4 `ref_gauge_transmission` seed

Which categories each condition historically hurts. Used to attach *the user's own
dollar exposure* to every fired gauge. Seed at minimum:

| gauge/pattern | axis | categories |
|---|---|---|
| `move_elevated`, `rates_shock`, `yield_level_watch` | sector | Utilities, Real Estate, Information Technology |
| `move_elevated`, `rates_shock` | style | Secular, Low Beta, Dividend |
| `credit_stress`, `credit_leads_equity` | sector | Financials, Consumer Discretionary |
| `credit_stress`, `credit_leads_equity` | style | High Beta, Small Caps |
| `dollar_strong`, `dollar_wrecking_ball` | sector | Materials, Energy, Information Technology |
| `dollar_wrecking_ball` | asset_class | Commodities, Gold |
| `oil_shock`, `oil_squeeze` | sector | Energy, Industrials, Consumer Discretionary |
| `yen_bid` | style | Momentum, High Beta, Secular |
| `korea_semis` | sector | Information Technology |
| `vix_elevated`, `vol_regime_break`, `vrp_gone` | style | High Beta, Momentum, Small Caps |
| `spx_top_range`, `breadth_deteriorating` | style | High Beta, Momentum |
| `gold_vol_elevated` | asset_class | Gold |

Category strings **must exactly match** the values produced by `drv_ma.sector`,
`drv_technicals.asset_class` and `etl/derive_macro.py::_classify_style`. Verify with
`SELECT DISTINCT` on each before seeding — a typo here silently yields zero exposure.

### Phase 2 verification

```sql
SELECT SUM(weight) FROM ref_risk_gauge WHERE is_active;           -- expect 29
SELECT COUNT(*) FROM ref_market_pattern WHERE is_active;          -- expect 8
-- every transmission category must resolve to real data
SELECT t.category FROM ref_gauge_transmission t
 WHERE t.axis='sector'
   AND t.category NOT IN (SELECT DISTINCT sector FROM drv_ma WHERE sector IS NOT NULL);
-- expect zero rows
```

---

# PHASE 3 — Self-computed inputs → `drv_market_stat`

New deriver `etl/derive_market_stat.py`, wired into `derive_all()` **after**
`drv_technicals` and `drv_quote` (it reads both). One row per `as_of_date`.

```sql
CREATE TABLE IF NOT EXISTS drv_market_stat (
    as_of_date              date PRIMARY KEY,
    -- realized vol + variance risk premium (SPX)
    rv10                    numeric,
    rv21                    numeric,
    rv63                    numeric,
    vix                     numeric,
    vrp                     numeric,
    vrp_z                   numeric,
    -- breadth, computed on this system's own universe
    pct_above_sma50         numeric,
    pct_above_sma200        numeric,
    pct_above_sma50_5d_chg  numeric,
    universe_n              integer,
    -- participation
    spy_rvol                numeric,
    -- market internals (Phase 4; NULL until the INT feed lands)
    adv_issues              numeric,
    dec_issues              numeric,
    up_volume               numeric,
    down_volume             numeric,
    trin                    numeric,
    vol_breadth             numeric,
    -- risk dial
    risk_budget             integer,
    risk_label              text,
    gauges_fired            jsonb,
    detail                  jsonb
);
```

### 3.1 Yang–Zhang realized volatility

Compute on **SPX** daily OHLC from `drv_quote` (fall back to `hist_td` if `drv_quote`
history is short). Windows n = 10, 21, 63.

**Use Yang–Zhang, not close-to-close.** Close-to-close over 21 days is so noisy that a
VRP signal built on it fires on estimator error as often as on real premium
compression. Yang–Zhang uses the O/H/L/C already stored, handles overnight gaps and
intraday drift, and is roughly 14× more efficient for the same window.

```
o_t = ln(O_t / C_{t−1})                  overnight
c_t = ln(C_t / O_t)                      open-to-close
rs_t = ln(H_t/C_t)·ln(H_t/O_t) + ln(L_t/C_t)·ln(L_t/O_t)      Rogers–Satchell

σ²_o  = Σ(o_t − ō)² / (n − 1)
σ²_c  = Σ(c_t − c̄)² / (n − 1)
σ²_rs = Σ rs_t / n

k = 0.34 / (1.34 + (n + 1)/(n − 1))

σ_YZ = sqrt(σ²_o + k·σ²_c + (1 − k)·σ²_rs) × sqrt(252) × 100     → percent, annualized
```

Guards: skip any day with a non-positive or null O/H/L/C; require ≥ `n` clean
observations or write NULL for that window. Never silently substitute a shorter window.

### 3.2 Variance risk premium

```
vrp   = vix − rv21
vrp_z = (vrp − mean(vrp, trailing 252d)) / stdev(vrp, trailing 252d)
```
`vix` = `VIX` close for `as_of_date` from `drv_quote`.

Backfill `drv_market_stat` for at least **300 trading days** so `vrp_z` has a real
distribution from day one. Use `etl/backfill_derives.py` as the pattern.

### 3.3 Breadth on this system's own universe

```sql
-- percentage of the tracked universe trading above its own moving average
SELECT
  100.0 * COUNT(*) FILTER (WHERE last_price > sma_50)  / NULLIF(COUNT(*),0),
  100.0 * COUNT(*) FILTER (WHERE last_price > sma_200) / NULLIF(COUNT(*),0),
  COUNT(*)
FROM hist_tw
WHERE export_date = :d AND last_price IS NOT NULL AND sma_50 IS NOT NULL;
```

Restrict to equities/ETFs — exclude rows whose `tos_symbol` starts with `$` or `/`, and
exclude anything in the volatility gauge set. Statement must stay ≤ 965 bytes; split if
needed. `pct_above_sma50_5d_chg` = today's value minus the value 5 trading days back
(read from `drv_market_stat` itself; NULL on the first 5 days of backfill).

### 3.4 Participation

`spy_rvol` = `hist_tw.volume / NULLIF(hist_tw.volume_avg_10d, 0)` for `SPY` at date D.
Both columns already exist. If SPY is absent for D, fall back to `QQQ`, then `IWM`, and
record which was used in `detail`.

### 3.5 The Risk Dial

New module `etl/derive_risk_dial.py`, called by `derive_market_stat`. Define
`GAUGES: list[Gauge]` where each `Gauge` has a `key` and a pure predicate
`fired(ctx) -> bool | None`. `None` means "cannot evaluate — data missing"; a `None`
gauge is **excluded from both numerator and denominator**, never counted as passing.

| gauge_key | Fires when |
|---|---|
| `spx_top_range` | `rr_pos(SPX) ≥ 0.85` |
| `spx_bottom_range` | `rr_pos(SPX) ≤ 0.15` |
| `vix_elevated` | `VIX > ref_vol_threshold.high` (30) |
| `vix_chop` | `VIX` between `low` and `high` (19–30) |
| `move_elevated` | `MOVE:GIF > 120` |
| `credit_stress` | `rr_pos(HYG) ≤ 0.15` **OR** `BAMLH0A0HYM2` widened ≥ 25bp over 10 trading days |
| `yield_level_watch` | `TNX:CGI` within `tolerance` of any active `ref_level_watch` row **OR** `rr_pos(TNX:CGI) ≥ 0.85` |
| `curve_inverting` | `T10Y2Y` fell ≥ 15bp over 5 trading days |
| `dollar_strong` | `rr_pos($DXY) ≥ 0.85` |
| `oil_shock` | `rr_pos(/CL) ≥ 0.85` or `≤ 0.15`, **OR** `OVX:CGI > 50` |
| `vrp_gone` | `vrp ≤ 0` |
| `gamma_negative` | latest `hist_msr.gamma_throttle` indicates negative/red |
| `breadth_deteriorating` | `pct_above_sma50 < 40` **AND** `pct_above_sma50_5d_chg < 0` |
| `gold_vol_elevated` | `GVZ:CGI > 32` |

`rr_pos(sym) = (last_price − lrr) / NULLIF(trr − lrr, 0)` from `drv_rr` + `drv_quote`,
clamped to [0, 1]. This is the same formula already used in three places
(`macro_areas.py:386`, `actionable.js:4288`, `market_bar.js::rangeBar`) — **extract it
into `api/_helpers.py::rr_pos()` and have all four call sites use it.**

`gamma_throttle` is free text from the MSR email. Inspect the live distinct values
first (`SELECT DISTINCT gamma_throttle FROM hist_msr ORDER BY 1;`) and write the
matcher against what is actually there. If it is not parseable into a
negative/positive signal, return `None` from that gauge and say so in `DEV_HANDOFF.md`
— **do not guess.**

```
risk_budget = round(100 × (1 − fired_weight / evaluable_weight))
```

| Budget | `risk_label` |
|---|---|
| 80–100 | `CLEAR` |
| 55–79 | `CAUTION` |
| 30–54 | `DEFENSIVE` |
| 0–29 | `NOT INVESTABLE` |

`gauges_fired` JSONB — one entry per gauge, fired or not, so the UI can render both the
triggered list and the quiet list:

```json
[{"key":"spx_top_range","label":"SPX at top of risk range","fired":true,
  "weight":3,"value":0.91,"detail":"SPX 6412 — 91% of range (LRR 6180 / TRR 6435)"},
 {"key":"vix_elevated","fired":false,"weight":3,"value":14.2,"detail":"VIX 14.2 investable"}]
```

`detail` strings are user-facing. State the number and the threshold. No causes.

### Phase 3 verification

```sql
SELECT as_of_date, rv21, vix, vrp, pct_above_sma50, risk_budget, risk_label
  FROM drv_market_stat ORDER BY as_of_date DESC LIMIT 10;
SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date) FROM drv_market_stat;  -- ≥ 300 rows
SELECT jsonb_array_length(gauges_fired) FROM drv_market_stat
 WHERE as_of_date=(SELECT MAX(as_of_date) FROM drv_market_stat);          -- expect 14
```
- **Sanity:** `rv21` for SPX should sit roughly 8–25 in a normal regime. Three-digit or
  sub-1 values mean a units bug (log-return vs percent, or a missing `sqrt(252)`).
- **Cross-check:** compare `rv21` against Cboe's free `RVOL` series once Phase 4 lands.
  Same ballpark ⇒ correct. Persistent large divergence ⇒ your formula has a bug.
- **Idempotence:** re-run the derive for the same D twice; row count unchanged, values identical.

---

# PHASE 4 — New feeds

Four additions. Each independent; a failure in one must not block the others.

### 4.1 ToS market internals → `hist_internals`

Market-wide volume and breadth. The user already pays for ThinkOrSwim — **do not use
an outside source.** Yahoo's `^TICK`/`^TRIN` have no usable daily history, and
StockCharts' terms prohibit automated collection.

**These symbols must NOT go into the TL or TD watchlists.** The tracked universe is
`drv_symbols` = symbols in `hist_td` for date D. An internals symbol landing there
becomes a phantom "stock" with no Trend/Trade/BB study values and will render as a
broken row on Actionable.

New tab **`INT`**, new table:

```sql
CREATE TABLE IF NOT EXISTS hist_internals (
    snapshot_date date    NOT NULL,
    symbol        text    NOT NULL,
    sequence      integer NOT NULL,
    export_date   date,
    export_time   text,
    last_value    numeric,
    PRIMARY KEY (snapshot_date, symbol, sequence)
);
```

Follow the documented 5-step recipe in `CLAUDE.md` §"Adding a new source-file type":
row in `LoadFiles.xlsx` → `python -m etl.tickers_initial_load` →
`HIST_MAPS['INT']` in `mappings.py` (columns: `Export Date`, `Export Time`, `Symbol`,
`Last`; same `date_source_col`/`seq_source_col`/`symbol_source_col` pattern as `TL`) →
`hist_internals` in `baseline.sql` → `python -m db.init_db`.

Symbols the user adds to the ToS watchlist (NYSE primary; `/Q` suffix = Nasdaq):

| Symbol | Meaning |
|---|---|
| `$ADVN` | Advancing issues |
| `$DECN` | Declining issues |
| `$UVOL` | Up volume |
| `$DVOL` | Down volume |
| `$TRIN` | Arms index |

**`$TICK` is deliberately excluded** — it is an intraday oscillator whose closing print
carries almost no information. Do not add it.

Populate `drv_market_stat` from these (NULL-safe — the columns stay NULL until the feed
starts arriving, and the risk dial must not break in the meantime):

```
vol_breadth = up_volume / NULLIF(up_volume + down_volume, 0)
```

Add a 15th gauge `volume_breadth_weak`, weight **2**, category `breadth`, fires when
`vol_breadth < 0.35`. Seed it `is_active=FALSE`; flip to TRUE once the feed is
confirmed flowing. (Active weight becomes 31 at that point.)

### 4.2 KOSPI complex → Yahoo

Follow the existing pattern in `etl/yahoo_fetch.py`.

| Yahoo symbol | Instrument |
|---|---|
| `^KS11` | KOSPI Composite |
| `005930.KS` | Samsung Electronics |
| `000660.KS` | SK hynix |
| `EWY` | iShares MSCI South Korea ETF |

Two things that will otherwise bite:
- **Korean holidays ≠ US holidays.** These must sit on the **carry-forward** side of
  the derive-date logic (`snapshot_date <= D`), never exact-match `export_date = D`.
  See `docs/derive_date_logic.md`.
- `005930.KS` and `000660.KS` are quoted in **KRW**. Do not compare to USD instruments
  without dividing by `KRW=X`. For the Phase 6 `korea_semis` pattern, use **`^KS11` and
  `EWY` only** — `EWY` is USD and already embeds the currency move, which is what you
  want for a US read-through.

There is no US-listed Korea-specific semiconductor ETF; `EWY` is the correct proxy
(Samsung and SK hynix dominate its weight).

### 4.3 Cboe free CSVs → `hist_macro`

New `etl/fetch_cboe.py`, same shape as `etl/fetch_macro.py`. Writes to `hist_macro`
with `source='CBOE'`. No API key, no registration.

| series_id | URL | Purpose |
|---|---|---|
| `VVIX` | `https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv` | `ref_vol_threshold` already has a VVIX row (100/150) with no feed behind it |
| `RVOL` | `https://cdn.cboe.com/api/global/us_indices/daily_prices/RVOL_History.csv` | Independent cross-check on the Phase 3 Yang–Zhang calc |

Both are `DATE,<VALUE>` two-column CSVs, close only, decades of history. Fetch full
history once, then incremental. Wrap in try/except and log to `meta_macro_fetch` —
an unavailable CDN must not fail the derive.

### 4.4 Ethereum

`ETH-USD` via the existing Yahoo path, alongside `/BTC` in the `crypto` macro area.
Pick one convention for ETH's "close" against a US trading day (00:00 UTC or 16:00 ET),
apply it consistently, and document the choice — the choice materially changes any
correlation computed against SPX.

### Explicitly out of scope

Do **not** build any of these. Each was evaluated and rejected:

| Not building | Reason |
|---|---|
| Agricultural futures (corn/wheat/soy) | Near-zero read-through to this book. Yahoo `=F` symbols are rolling front contracts — each roll makes a multi-percent gap that is not a return and would fire false rules. |
| Full SPX dealer GEX / gamma-flip curve | Open interest is always prior-day; the dealer sign convention is an assumption; the signal is intraday while this dashboard is EOD. `hist_msr.gamma_throttle` already covers the need. |
| Paid economic consensus (Trading Economics, FMP, Finnhub) | $50–200/mo for information that decays within ~90 minutes of release, on an EOD dashboard. |
| News / headline APIs | Headlines follow price. The Hedgeye email feed already does this with a human filter. |
| StockCharts breadth symbols | Terms prohibit automated collection; no API. |
| Cboe put/call ratio CSVs | Confirmed dead — coverage ends 2019-10-04. |

### Phase 4 verification

```sql
SELECT symbol, MAX(snapshot_date), COUNT(*) FROM hist_internals GROUP BY 1;
SELECT series_id, MIN(obs_date), MAX(obs_date), COUNT(*) FROM hist_macro
 WHERE source='CBOE' GROUP BY 1;
```
- Compare `drv_market_stat.rv21` against `hist_macro` `RVOL` on the same dates —
  same ballpark. **If they diverge persistently, Phase 3.1 has a bug. Fix it.**
- Confirm no internals symbol leaked into `drv_symbols`:
  `SELECT * FROM drv_symbols WHERE tos_symbol LIKE '$%';` → zero rows.

---

# PHASE 5 — Factor scorecard → `drv_category_perf`

New deriver `etl/derive_category_perf.py`, wired into `derive_all()` after
`drv_portfolio`. Answers "my allocation % to each category and how I am doing over
1w / 3w / 1m / 2m / 3m."

```sql
CREATE TABLE IF NOT EXISTS drv_category_perf (
    as_of_date       date NOT NULL,
    axis             text NOT NULL,     -- 'sector' | 'asset_class' | 'style'
    category         text NOT NULL,
    market_value     numeric,
    weight_pct       numeric,
    target_min       numeric,
    target_max       numeric,
    twr_1w  numeric, twr_3w  numeric, twr_1m  numeric, twr_2m  numeric, twr_3m numeric,
    bench_1w numeric, bench_3w numeric, bench_1m numeric, bench_2m numeric, bench_3m numeric,
    bench_symbol     text,
    flows_confidence text,              -- 'green' | 'amber' | 'suspect'
    quad_stance      text,              -- BULLISH | NEUTRAL | BEARISH
    verdict          text,
    detail           jsonb,
    PRIMARY KEY (as_of_date, axis, category)
);
```

### 5.1 Axes

| axis | categories | symbol → category |
|---|---|---|
| `sector` | GICS 11 | `drv_ma.sector`; benchmark = `_SECTOR_ETF` proxy |
| `asset_class` | Equities, Fixed Income, Commodities, Gold, FX, Crypto, USD, **Cash** | `drv_technicals.asset_class`; Cash via `is_cash()` |
| `style` | Momentum, High Beta, Low Beta, Cyclical, Defensives, Secular, Value, Dividend, Small Caps, Mid Caps | `etl/derive_macro.py::_classify_style` — **reuse it, do not reimplement** |

Two rules that must not be skipped:
- **Style tags overlap and sum to more than 100%.** A symbol can be Momentum *and*
  High Beta *and* Secular — `_classify_style` assigns several tags by design. Do not
  normalize them to 100. The UI labels the tab "overlapping tags, not an allocation."
- **Never drop unmapped holdings.** Anything whose category will not resolve gets an
  explicit `Unmapped` row. A scorecard that quietly loses 8% of the book is worse than
  no scorecard.

### 5.2 Returns must be time-weighted

`V_end / V_start − 1` is **wrong** and would actively mislead: adding $50k of cash to
Tech raises Tech's value and the screen would report it as performance. The user trades
near-daily, so this error would be large and permanent.

```
for each trading day t in the window:
    r_t = (V_t − V_{t−1} − netflow_t) / V_{t−1}
TWR = Π(1 + r_t) − 1
```

- `V_t` = Σ market value of held symbols mapped to the category on date t, from
  `hist_cs` + `hist_f` daily snapshots.
- `netflow_t` = Σ buy/sell cash for that category from `hist_cst` / `hist_ft` on t.
- Windows: 1w=5, 3w=15, 1m=21, 2m=42, 3m=63 **trading days**, resolved the same way
  `macro_areas.py::_wow_pct` finds its offset date.

**Guards — the accuracy of every number here depends on the transaction feeds being
complete:**
1. If `|r_t| > 25%` for a whole category on one day, treat it as a flow artefact:
   set that day's `r_t = 0`, do not compound it, and mark the window `suspect`.
2. `flows_confidence`: `green` = every day in the window had a matching transaction
   snapshot; `amber` = gaps; `suspect` = a guard tripped. Surface this in the UI.
3. Record per-window day counts and the netflow total in `detail` so the numbers can
   be audited later.

**Mandatory validation before this phase is done:** pick a category with **no trades**
in the window. Its TWR must equal `V_end/V_start − 1` **exactly**. Paste the comparison
into `DEV_HANDOFF.md`. If it does not match, the flow mapping is wrong — fix it before
moving on.

### 5.3 Quad stance and verdict

`quad_stance` = `ref_quad_outlook` stance for that category evaluated against the
**effective 60-day window distribution** (`drv_macro_score.detail.eff`, TASK_126) — not
the current calendar month. Same number the MACRO column uses.

Over/under-weight band = **±3 percentage points** from target midpoint. Where
`ref_asset_allocation` has explicit `min_dollar`/`max_dollar` for the category, **those
win** — an explicit dollar limit is more informative than a generic band.

|  | Quad BULLISH | Quad NEUTRAL | Quad BEARISH |
|---|---|---|---|
| **Under-weight** | `ADD` | `WATCH` | `AVOID` |
| **At target** | `HOLD` (`PRESS` if `twr_1m > 0`) | `HOLD` | `TRIM` |
| **Over-weight** | `HOLD_NO_ADD` | `TRIM` | `TRIM_HARD` |

Two modifiers, applied after the matrix:
- **`ROTATE`** — replaces `ADD` when quad is BULLISH, weight is fine, but `twr` trails
  `bench` in **≥2 of the 5 windows**. This separates a bad *allocation* call from bad
  *stock-picking inside a good allocation*, which nothing in the system currently shows.
  Implement it exactly as specified.
- **Risk-dial cap** — when `drv_market_stat.risk_budget < 55`, every `ADD` and `PRESS`
  downgrades to `HOLD` for that date. Regime governs size, never direction.

### Phase 5 verification

```sql
SELECT axis, COUNT(*), ROUND(SUM(weight_pct),1) FROM drv_category_perf
 WHERE as_of_date=(SELECT MAX(as_of_date) FROM drv_category_perf) GROUP BY 1;
-- sector ≈ 100, asset_class ≈ 100, style > 100 (overlapping tags — expected)
SELECT category, verdict, weight_pct, twr_1m, bench_1m FROM drv_category_perf
 WHERE axis='sector' AND as_of_date=(SELECT MAX(as_of_date) FROM drv_category_perf)
 ORDER BY weight_pct DESC;
SELECT DISTINCT flows_confidence FROM drv_category_perf;
```
- Sum of `market_value` across the `asset_class` axis must reconcile to
  `/api/portfolio/summary` total (market + cash) within rounding. **This is the
  single most important check in the phase** — if it does not reconcile, the category
  mapping is dropping holdings.
- The no-trades-category TWR check from §5.2. Paste evidence.

---

# PHASE 6 — API

New router `api/routers/cockpit.py`, registered in `api/main.py`. All endpoints take
optional `?date=D` and default via `_resolve_date`. All are thin reads over the derived
tables — no heavy computation at request time.

### 6.1 `GET /api/cockpit/risk-dial`

```json
{"as_of":"2026-08-01","risk_budget":35,"risk_label":"DEFENSIVE",
 "headline":"Half size. SPX at the top of its range with credit weakening.",
 "fired":[{"key":"spx_top_range","label":"SPX at top of risk range","weight":3,
           "value":0.91,"detail":"SPX 6412 — 91% of range (LRR 6180 / TRR 6435)",
           "exposure":{"dollar":214000,"pct":18.2,
                       "categories":["Information Technology"],
                       "top_holdings":[{"symbol":"NVDA","dollar":61000}]}}],
 "quiet":[{"key":"vix_elevated","detail":"VIX 14.2 investable"}],
 "evaluable_weight":29,"fired_weight":19,
 "suggested_size_multiplier":0.35}
```

`headline` is assembled from the two highest-weight fired gauges. Template only — it
must never contain a causal claim.

`exposure` resolves via `ref_gauge_transmission` → `drv_category_perf.market_value` for
the current date. Top 3 holdings by dollar within the affected categories.

### 6.2 `GET /api/cockpit/events`

New table `drv_market_event`, written by `etl/derive_market_event.py` (wire into
`derive_all()` after `derive_market_stat`):

```sql
CREATE TABLE IF NOT EXISTS drv_market_event (
    as_of_date  date    NOT NULL,
    event_seq   integer NOT NULL,
    event_type  text    NOT NULL,   -- range_break | trend_flip | zscore | pattern | calendar | surprise
    severity    text    NOT NULL,   -- severe | warn | info
    tos_symbol  text,
    pattern_key text,
    title       text    NOT NULL,
    legs        jsonb,
    read_text   text,
    exposure    jsonb,
    PRIMARY KEY (as_of_date, event_seq)
);
```

Three detectors, **in this priority order**:

**(a) Risk-range events — primary.** Deterministic, no statistics. This is the signal
family the user actually trusts, and none of it is currently surfaced as an *event*
rather than a static bar position.

| event | condition |
|---|---|
| `range_break_up` | `last > trr` today, was inside yesterday |
| `range_break_down` | `last < lrr` today, was inside yesterday |
| `trend_flip` | `drv_rr.outlook` changed Bullish↔Bearish (already parsed as `trend_flips[]` in the Hedgeye payload — reuse it) |
| `entered_top_decile` | `rr_pos` crossed 0.85 today |
| `entered_bottom_decile` | `rr_pos` crossed 0.15 today |

**(b) Z-scores — only where risk ranges don't reach.**
`z = (today's % change − mean(60d)) / stdev(60d)` from `drv_quote`.
**Rates use basis-point change, not percent** — a percent change on a yield is
meaningless near zero. `|z| ≥ 2` → `warn`, `≥ 3` → `severe`.

**(c) Patterns** — the 8 seeded in Phase 2:

| pattern_key | condition |
|---|---|
| `yen_bid` | `z(/6J) ≥ +2` AND (`z(TNX:CGI) ≤ −1` OR `z(/GC) ≥ +1`) |
| `dollar_wrecking_ball` | `rr_pos($DXY) ≥ 0.85` AND mean z of `/CL,/GC,/HG,/NG` `≤ −1` |
| `rates_shock` | `\|Δ TNX bp\| ≥ 15` AND `\|z(TNX:CGI)\| ≥ 2` |
| `credit_leads_equity` | (`z(HYG) ≤ −2` OR `z(BAMLH0A0HYM2) ≥ +2`) AND `\|z(SPX)\| < 1` |
| `flight_to_quality` | `z(/GC) ≥ +2` AND `z(TNX:CGI) ≤ −1` AND `z(SPX) ≤ −1` |
| `vol_regime_break` | any `ref_vol_threshold` gauge **crossed** a boundary today |
| `korea_semis` | `z(^KS11) ≤ −2` OR `z(EWY) ≤ −2` |
| `oil_squeeze` | `rr_pos(/CL) ≥ 0.85` AND `OVX:CGI` rising into elevated |

**Crossings, not levels — this is the core rule of the whole band.** A VIX elevated for
nine days is not news on day nine; it is the ambient state and belongs in the Risk Dial.
Only the transition day emits an event here. The superseded design's vol trigger
(`last > high`) would have fired every single day of a sustained vol regime, which is
exactly the noise the user asked to be rid of.

**(d) Calendar + economic surprise.**

Calendar: `ref_calendar_event` where `event_date ∈ {D, D+1}`, high-impact categories
only (Fed Meeting, FOMC Minutes, CPI *, PPI, PCE, GDP, NFP, ADP NFP, ISM Mfg, ISM Svcs).

Surprise — be precise about what is and is not computable:

| Release | Expected value | Do |
|---|---|---|
| CPI / core CPI | Hedgeye Inflation Nowcast (already arriving by email, `hist_macro`) | `surprise_z = (actual_first_print − nowcast) / stdev(historical gap)`. First print via FRED ALFRED vintage params, not the revised number. |
| GDP | `GDPNOW` (free on FRED) | Same formula |
| Unemployment, NFP, ISM, PPI | **No free consensus exists** | Show `actual vs its own 3-month trend`, and **label it exactly that — a deviation, not a surprise.** |

**Do not invent a consensus for anything in the third row.** "Unemployment 4.3%, above
3-month trend" is honest. A fabricated surprise number is not.

**Quiet state.** When nothing fires, return `{"quiet": true, "instruments_checked": N,
"max_abs_z": 1.3, "max_z_symbol": "$DXY", "range_breaks": 0}`. The UI renders one muted
line. A blank panel is indistinguishable from a broken one.

### 6.3 `GET /api/cockpit/factor-scorecard?axis=sector|asset_class|style`

Thin read over `drv_category_perf`. Returns rows plus `flows_confidence`,
`risk_budget_cap_applied` (bool), and an `unmapped` row when present.

### 6.4 `GET /api/cockpit/shortlist`

Reuse the existing `/api/actionable` query path — **no new ranking logic.** Existing
default sort (dollar-weighted edge, TASK_120), filtered to the
`docs/actionable_playbook.md` §3.3 high-conviction subset:

- Buys: `final_code` in (BM, BMN) AND `winning_source` in (RR, SSS) AND
  `rr_bull_bear = 'B'`
- Sells: SA, or gate-confidence sells
- Excluded always: `stop_breached` buys, Gate/Mixed confidence

**Hard cap 3 rows.** The playbook's own measured expectation is 0–3 trades/day; a
longer list invites exactly the scroll-until-decisiveness-dies failure it warns about.

---

# PHASE 7 — Frontend

Rebuild `web/index.html` + `web/app.js`; extend `web/styles.css`.

### 7.1 Remove

`web/index.html`: the `.dash-grid` → `.card.ticker-grid` block (`#tickerSections`) and
the three standalone `.side-stack` cards (`quadsBody`, `econBody`, `earningsBody` in
their current card form).

`web/app.js`: `SECTIONS`, `SECTION_ORDER`, `SECTION_RANK`, `sectionRank()`,
`renderSectionChips()`, `rowMatches()`, `buildSectionBlock()`, `renderTickerGrid()`,
`loadTickers()`, and the now-dead `state.rows` / `state.section` / `state.search`.

`web/styles.css`: `.dash-grid`, `.sections-grid`, `.section-block`, `.ticker-grid` —
verified dashboard-only. **Keep** `.mini-grid`, `.side-scroll`, `.quad-mini` — they are
reused on other screens.

### 7.2 Build — six bands, top to bottom

```
TOPBAR + MINI-TAPE                                              unchanged
① RISK DIAL          #riskDial        /api/cockpit/risk-dial
② WHAT CHANGED       #cockpitEvents   /api/cockpit/events         hidden when quiet
③ REGIME             #regimeStrip     /api/quad-window + /api/quad/band-factors
④ FACTOR SCORECARD   #factorScorecard /api/cockpit/factor-scorecard   3 tabs
⑤ SHORTLIST          #shortlist       /api/cockpit/shortlist          3 rows max
⑥ HOUSEKEEPING       #housekeeping    anchor-status + ingest-log + econ + earnings
```

**Band ① — the most important element on the screen.** Big number, coloured by
`risk_label`, horizontal meter, headline sentence, then the fired list (each with its
dollar exposure) and a collapsed quiet list. Directly below the number, in plain text:

> `today's size = AMT$ × 0.35`

That line is the entire payoff of this screen — it turns market context into a number
that changes what the user types into the broker. Do not bury it.

Note `web/actionable.js::_regimeVerdictHtml()` already does a simplified 8-gauge
version of this. Read it before writing Band ① — the visual language should match, and
**leave it in place on Actionable** (do not refactor Actionable in this task).

**Band ③ — no new computation.** Promote the existing regime band. The hover popover
must be the **existing** `/api/quad/band-factors` factor table, unchanged, so
"pop over on any Quad text and see all the factors considered" behaves exactly as it
does today on Actionable.

**Band ④ —** three tabs, colour-scaled cells (green positive / red negative, intensity
by magnitude). One **"vs Mkt" delta column per window**, not raw benchmark alongside —
ten numeric columns will not be read, and the delta is the decision-relevant number.
The Style tab carries a visible label: *"overlapping tags — not an allocation."*
Show the `flows_confidence` badge; amber and suspect must be visible, not hidden.

**Band ⑥ —** one thin line, green tick when fine. **When it is red, Band ① must show a
warning** — a risk dial computed on stale data is worse than no risk dial.

### 7.3 Loading

All six bands load in parallel via `Promise.all`, each in its own try/catch so one
failure cannot blank the page. Date picker changes re-trigger all six. Keep the
existing 60s mini-tape poll; do not add new polling.

---

# PHASE 8 — Docs and tests

### 8.1 Docs

- `docs/dashboard_cockpit_design.md` — update to match what was actually built. Where
  implementation diverged from spec, change the doc, not the history.
- **Delete `docs/dashboard_attention_panel_design.md`** (superseded).
- `docs/dashboard_logic.md` — rewrite the UI-sections table for the six bands.
- `docs/migrations.md` — one dated entry covering all new tables and columns.
- `CLAUDE.md` Lookup index — replace the attention-panel row with rows for:
  cockpit design · risk dial (`etl/derive_risk_dial.py`, `ref_risk_gauge`) ·
  market stats / VRP / breadth (`drv_market_stat`) · category performance
  (`drv_category_perf`) · market events (`drv_market_event`) · ToS internals feed
  (`hist_internals`). **One line each — `CLAUDE.md` is an index, not a detail doc.**
- `COMMANDS.md` — any new `python -m` entry points.

### 8.2 Tests (convention #18)

Pure-Python, no DB, in `tests/`:

| File | Covers |
|---|---|
| `tests/test_yang_zhang.py` | Known-input vector; constant-price series → 0; k coefficient at n=10/21/63; NULL on insufficient data |
| `tests/test_risk_dial.py` | Weight arithmetic; `None` gauges excluded from both numerator and denominator; every budget→label boundary (29/30, 54/55, 79/80) |
| `tests/test_twr.py` | Chain-linking; **a flow-only day produces r_t = 0**; the 25% guard trips and does not compound; no-flow window equals the naive ratio |
| `tests/test_market_patterns.py` | Each of the 8 patterns fires on a crafted vector and does not fire on a near-miss; crossing-not-level for `vol_regime_break` |

Acceptance tests in `tests/acceptance/`, marked `@pytest.mark.acceptance` (excluded
from the default run, deletable after commit): each new table populated for the anchor
date; each endpoint returns 200 with the documented shape; `drv_category_perf`
asset_class total reconciles to `/api/portfolio/summary`.

---

## How to verify (tester reference — runs only on explicit request)

1. `pytest tests/` → green. `pytest tests/ -m acceptance` → green.
2. Each phase's own verification block above, in order.
3. `python -m etl.derive` for the anchor date **twice** → all new `drv_*` tables
   byte-identical. Idempotence is non-negotiable.
4. `/` loads with all six bands. No console errors. No reference to `#tickerSections`.
5. Risk dial cross-check: pick the anchor date, evaluate all 14 gauges by hand from
   `drv_rr` / `ref_vol_threshold` / `hist_macro`, confirm `risk_budget` matches.
6. Factor scorecard: `asset_class` market-value total reconciles to
   `/api/portfolio/summary`.
7. Events band: force the quiet state (a date with no breaks and no |z| ≥ 2) →
   one muted line, not an empty panel.
8. `rv21` vs Cboe `RVOL` — same ballpark.
9. Verify `/api/marketbar` MOVE zone is non-null and the `HYOAS` tile shows a spread.

## Files expected to change

**New:** `api/routers/cockpit.py`, `etl/derive_market_stat.py`,
`etl/derive_risk_dial.py`, `etl/derive_market_event.py`,
`etl/derive_category_perf.py`, `etl/fetch_cboe.py`, `db/seeds_cockpit.sql`,
`tests/test_yang_zhang.py`, `tests/test_risk_dial.py`, `tests/test_twr.py`,
`tests/test_market_patterns.py`, `tests/acceptance/test_cockpit.py`.

**Modified:** `db/baseline.sql`, `api/main.py`, `api/_helpers.py` (shared `rr_pos()`),
`api/routers/marketbar.py`, `api/routers/macro_areas.py`, `etl/derive.py`,
`etl/mappings.py`, `etl/yahoo_fetch.py`, `web/index.html`, `web/app.js`,
`web/styles.css`, `web/market_bar.js`, `CLAUDE.md`, `COMMANDS.md`,
`docs/dashboard_cockpit_design.md`, `docs/dashboard_logic.md`, `docs/migrations.md`.

**Deleted:** `docs/dashboard_attention_panel_design.md`.

## Standing rules for this task

- **Do not ask questions.** Every decision is in this spec. Where it is silent, choose
  the option most consistent with existing code and note it in `DEV_HANDOFF.md`.
- **Do not commit or push.** The user commits from Windows.
- **Do not refactor the Actionable screen.** Read `_regimeVerdictHtml()` for reference;
  leave it in place.
- **Do not invent causes in user-facing text.** State what moved and what it co-moves
  with. Never why. This is a hard content rule.
- **Verify large edits** — `node --check` for JS, `ast.parse` for Python. Large edits
  can land truncated even when the tool reports success (see `CLAUDE.md`).
- End `DEV_HANDOFF.md` with `ALL_DONE`, or `PHASE_<n>_DONE` if you stopped at a
  phase boundary.
