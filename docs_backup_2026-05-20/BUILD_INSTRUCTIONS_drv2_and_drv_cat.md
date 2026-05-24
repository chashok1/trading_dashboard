# Trading Dashboard — drv2_* and drv_cat_* Layer Build Instructions

> **Audience:** A future Claude (or human) implementing the new derive layers from scratch.
> **Status:** Design + categorization. Source-of-truth artifacts produced 2026-05-08, refined 2026-05-10.
> **Inputs you will need (already on disk):**
> - `docs/ma_columns_v2.csv` — **PRIMARY.** Every one of the 641 MA columns mapped to its `pipeline_stage`, `concept`, `drv_cat_*` table, color island id, and Excel formula. This file supersedes `ma_columns_full.csv`.
> - `docs/ma_columns_full.csv` — earlier single-axis categorization (kept for reference).
> - `docs/drv_cat_summary.csv` — counts per `drv_cat_*` table.
> - `docs/ma_columns_registry_seed.csv` — earlier version with PG-name suggestions and types.
> - The Excel workbook: `C:\Ashok\Invest\Projects\Cluade\Tickers 2026-04-30.xlsx` — keep it open; many decisions need a quick visual look at the MA tab.

---

## 0. Mental model — two axes that organize MA

Every MA column has TWO orthogonal tags and the categorizer must capture both:

**Axis 1 — `pipeline_stage` (left-to-right progression in MA)**

The MA tab is laid out as a left-to-right pipeline of a trading decision. Reading the headers from column A to column XQ you traverse: raw lookups → derived intermediates → atomic-rule inputs → composite-rule outputs → rule summaries → portfolio context → final decisions. The categorization preserves this order:

| Stage | Cols | Excel range | What lives here |
|---|---|---|---|
| `lookup_identity`   |  10 | A..J          | Key, Symbol, Y Symbol, Company Name, first prices |
| `lookup_data`       | 114 | K..DT         | Raw imports from Y, TL, TD, RR, II, ssH, etfchg, etc. |
| `derived_features`  | 141 | DU..JE        | BB families, percentiles, slopes, MA, fundamentals, Quad outlook, IV/HV |
| `separator`         |   2 | JF, NP        | Literal `Begin` / `End` markers (skip in DDL) |
| `atomic_input`      | 113 | JG..NO        | **Atomic rule input columns** — what the rules engine reads |
| `composite`         |  66 | NQ..QD        | **Composite rule outputs** — pre-computed by Excel via `=Trig!<col>1` |
| `rule_summary`      |  94 | QE..TT        | Matched-rule labels, II/SS/HE/PS entry-cont rollups, BBRng action |
| `decision`          |  29 | TU..UD + WY..XQ | OverAll, Action Type, ^L1/^L2/^L3, Final Action, top matched rules |
| `holdings`          |  72 | UE..WX        | Fidelity / CS / RH / Long$ / Short$ / Stocks$ / dollar amounts + adjacent decision context |

**Axis 2 — `concept` (trading-domain category)**

What the column is *about*: bollinger, rsi, macd, ivhv, volume, risk_range, trend_trade, moving_avg, perf_extremes, quad_outlook, fundamentals, holdings_dollars, action_decision, trig_summary, identity, price, etf, ii, ps, signal_strength, earnings, index_volatility, volatility_regime, sector_rollup, he_outlook, levels, atomic_input, composite, separator. (~28 distinct concepts.)

**Why both axes matter:**

- **Storage uses concept** — `drv_cat_bollinger`, `drv_cat_rsi`, `drv_cat_macd`, etc. — because BB columns appear in multiple stages (lookup BB raw values, derived BB slopes, atomic BB rules) and storing them together makes formula edits localized.
- **UI / API filtering uses stage** — "Show me everything in the lookup stage" reproduces a left-side slice of MA; "Show me the decision stage" gets the actionable-output columns. The pipeline view in the Cockpit drawer can show the *path* a symbol took: lookup values → derived features → which atomic rules fired → which composites scored → final decision.
- **The two privileged categories collapse onto stages** — `drv_cat_atomic_input` IS the `atomic_input` stage; `drv_cat_composite` IS the `composite` stage. The rule engine reads from one and writes / mirrors to the other.

The categorizer should populate both `pipeline_stage` and `concept` on every registry row. They are independent.

---

## 0.1 Color is a HINT, not authority

The MA tab uses cell-fill colors as a visual organizing aid, but the same color may appear at opposite ends of the workbook for unrelated columns. Treat color as a hint with two specific rules:

1. **Same-color + adjacent (within ~4 columns) → strong evidence of same concept.** The color blocks the categorizer detected (181 of them in row 1) are valid as long as you stay within an island.
2. **Same-color + far apart → evidence of nothing.** Two `theme:5` blocks 200 columns apart are almost certainly unrelated. Do not auto-merge them into one drv_cat_* table.

Implementation in the categorizer (already done in `ma_columns_v2.csv`): walk the columns left-to-right, group by color but reset the island id whenever the gap from the previous same-color column exceeds `ISLAND_GAP = 4`. Result: 134 distinct color *islands* (vs 181 raw color *blocks*) — the islands are what you trust.

In practice the precedence order for any column's concept assignment is:

```
1. Hard column range (atomic_input JG..NO, composite NQ..QD, separators JF/NP)
2. Header keyword match (e.g. "RSI" in header → concept=rsi)
3. Formula content (e.g. references to td.bb_top_15d → concept=bollinger)
4. Color island agreement (same island as a column with a known concept → inherit it)
5. Proximity fallback (inherit previous column's concept)
```

Color sits at #4 — useful only as a tiebreaker, never overriding a header or formula match.

---

## 1. The four-tier model

```
Tier 1   hist_*        raw imported rows        (UNCHANGED)
Tier 2   drv_*         per-row, single-source cleanup  (UNCHANGED)
Tier 3   drv2_*        per-source feature tables (NEW — "by where it came from")
Tier 4   drv_cat_*     per-domain category tables (NEW — "by trading concept")
Tier 5   drv_ma        thin gold layer (VIEW or thin table) joining drv2_* + drv_cat_*
```

`drv2_*` and `drv_cat_*` describe the **same set of columns from two perpendicular angles**:

| Angle | Question it answers | Example |
|---|---|---|
| `drv2_*` (source) | "Which Excel tab / hist_* table did this column come from?" | `drv2_td.bb_top_15d` (came from the TD daily file) |
| `drv_cat_*` (category) | "Which trading concept does this column belong to?" | `drv_cat_bollinger.bb_top_15d` (it's a Bollinger band column) |

Pick **drv_cat_* as the storage layer** and let drv2_* be a *VIEW pivot* over the per-source filter, OR vice versa. Storing both physically would duplicate ~640 columns — pick one.

**Recommended: store in `drv_cat_*` (domain) tables and expose `drv2_*` as VIEWs.** Reasons:

- The rules engine, Cockpit drawer, and dashboard organize by concept, not by file. "Show me all Bollinger triggers" is a real query; "show me all TD-sourced columns" is not.
- Authoring evolves by concept too: a future BB-streak tweak touches one table.
- The number of `drv_cat_*` tables (~30) is closer to the natural granularity than the ~14 `drv2_*` tables.
- `drv2_*` becomes a thin VIEW: `CREATE VIEW drv2_td AS SELECT as_of_date, symbol, <all columns whose source is TD> FROM drv_cat_bollinger b JOIN drv_cat_rsi r USING(...) JOIN drv_cat_ivhv v USING(...) ...`. Cheap.

---

## 2. The category map (drv_cat_*) — refined v2 counts

Read `docs/ma_columns_v2.csv` for the per-column assignment (every row also has `pipeline_stage`). Refined counts:

| drv_cat_* table | Cols | Stages it spans | What lives here |
|---|---|---|---|
| `drv_cat_atomic_input`     | **113** | atomic_input | Every column in MA range **JG..NO** — the atomic-rule input columns. **RULES-ENGINE GOLD TABLE.** |
| `drv_cat_price`            | 69  | lookup_identity, lookup_data, derived_features | Open/High/Low/Close/Last/Net Chng/%Change variants from Y, TL, TD across all stages |
| `drv_cat_composite`        | **66**  | composite | Every column in MA range **NQ..QD** — composite-rule scores via `=Trig!<col>1` |
| `drv_cat_quad_outlook`     | 50  | derived_features, holdings | Hedgeye-style monthly + quarterly Quad outlook (M-OL, Q-OL, +ves/-ves, Asset Class, Equity Sector) |
| `drv_cat_trig_summary`     | 41  | rule_summary, decision | "Trig Matched Rule1..N", "M Rule1..N" — top-N triggered-rule labels |
| `drv_cat_holdings_dollars` | 38  | holdings | Fidelity / CS / RH / Long$ / Short$ / Stocks$ + dollar amounts |
| `drv_cat_bollinger`        | 35  | lookup_data, derived_features, rule_summary | All BB band, BB-Streak, BB-HighLow, BB-Threshold-Crossover columns |
| `drv_cat_action_decision`  | 30  | rule_summary, decision, holdings | ^L1/^L2/^L3, OverAll, Action Type, Final Action, Entry, Cont, Outlook |
| `drv_cat_volume`           | 24  | derived_features | Volume, VolumeSpike, W_Avg_Vlm_10d, Vlm_RuleCode, Vlm_Action |
| `drv_cat_trend_trade`      | 23  | lookup_data, derived_features, holdings | A_TrendValue, A_TradeValue, Trend_sd, Trade_sd, TrTn-Relation |
| `drv_cat_risk_range`       | 20  | lookup_data, derived_features, rule_summary, holdings | RR_*, BRR%, BullRiskRng-Action, RR LRR/TRR, RR_Bottom/Top |
| `drv_cat_perf_extremes`    | 16  | lookup_data | 52-Wk High/Low, 3mn-High/Low, Perf3M, Perf2M, Perf3WK |
| `drv_cat_ii`               | 15  | rule_summary, derived_features | II Final, II Cont, II Chg, II date |
| `drv_cat_signal_strength`  | 12  | rule_summary, decision | SS Entry, SS Cont, SSS Cont, SSH/SSL date |
| `drv_cat_identity`         | 11  | lookup_identity, lookup_data | Key, Symbol, Y Symbol, Sort Symbol, Company Name, export dates |
| `drv_cat_he_outlook`       | 11  | rule_summary, decision, holdings | HE Entry, HE Cont, HE OL - Sector, HE Outlook |
| `drv_cat_fundamentals`     | 10  | derived_features | Beta, Market Cap, P/E, Long-term Debt, Float, Short Ratio |
| `drv_cat_sector_rollup`    | 9   | derived_features | Per-sector rollups (Sector, VS Volatility, etc.) |
| `drv_cat_etf`              | 8   | derived_features, rule_summary | ETF_Bottom, ETF_Top, ETF Date, ETF Cont, ETF Final |
| `drv_cat_rsi`              | 7   | lookup_data, derived_features | D_RSI, L_RSI, RSI variants |
| `drv_cat_ps`               | 6   | rule_summary | PS Rk, PSRk Chg, PS Date, PS Outlook, PS Cont |
| `drv_cat_macd`             | 5   | derived_features | A_MACD_BRR, MACD_BRR, A_MACDH_D_BRR |
| `drv_cat_volatility_regime`| 5   | derived_features | "Volatility regime", "Price zone" classification |
| `drv_cat_index_volatility` | 5   | derived_features | SP500/Nasdaq/Dow/Russell/VIX volatility |
| `drv_cat_moving_avg`       | 4   | derived_features, holdings | 20 DMA, 50 DMA, 200 DMA |
| `drv_cat_ivhv`             | 3   | derived_features | IVPercentile, HVPercentile, IVHV |
| `drv_cat_earnings`         | 3   | derived_features | EarningsDays, P/E |
| `drv_cat_separator`        | 2   | separator | The literal `Begin` (JF) and `End` (NP) markers — skip in DDL |

**Total: 641 — every MA column has a home, no `drv_cat_misc`.** The two-axis (stage × concept) categorization eliminates the need for a catch-all bucket the previous pass needed.

**Reading the table:** the `Stages it spans` column is the cross-tab. A concept like `bollinger` legitimately appears in multiple stages — raw BB values in `lookup_data`, derived BB slopes in `derived_features`, BB-related rule summaries in `rule_summary`. The same drv_cat_bollinger table holds all of them, with `pipeline_stage` distinguishing rows-as-data within. (Or, if one drv_cat_* table holds columns from multiple stages, you can still split by stage in code via `WHERE pipeline_stage = 'derived_features'` against the registry.)

---

## 3. The two privileged categories: atomic_input and composite

These two together are what the rules engine reads and writes. Every other `drv_cat_*` table is "for information" / dashboard display.

### 3.1 `drv_cat_atomic_input` (113 columns from JG..NO)

Each column is the **value an atomic rule consumes**. Today `ref_trig_atomic_rule.ma_column_name` stores values like `'drv_ma.rsi'`. After this migration it should store `'drv_cat_atomic_input.rsi'` (or just `'rsi'` since the table is implied by the rule kind).

Create the table from the JG..NO header row in MA. Use snake-case. Sample DDL:

```sql
CREATE TABLE drv_cat_atomic_input (
  as_of_date DATE NOT NULL,
  symbol     TEXT NOT NULL,
  -- 113 columns from MA range JG..NO, snake-cased.  Examples:
  macdh_direction        NUMERIC,
  macd_direction         NUMERIC,
  bb_direction           NUMERIC,
  bbthresh_crossover     NUMERIC,
  bbthresh_co_days       NUMERIC,
  trend_cross_over       NUMERIC,
  trend_rule             NUMERIC,
  brr_pct_rule           NUMERIC,        -- 'BRR% Rule'
  iv_percentile          NUMERIC,
  iv_percentile_puts     NUMERIC,
  hv_percentile          NUMERIC,
  rsi_rule               NUMERIC,
  rsi_top                NUMERIC,
  rsi_puts               NUMERIC,
  bb_streak_rule         NUMERIC,
  bb_streak_days_rule    NUMERIC,
  macd_rule              NUMERIC,
  macdh_rule             NUMERIC,
  three_mn_outlook       NUMERIC,        -- '3mn Outlook'
  three_wk_outlook       NUMERIC,
  fifty_dma_rule         NUMERIC,
  two_hundred_dma_rule   NUMERIC,
  -- ... see ma_columns_full.csv for the full list filtered by drv_cat_table = 'drv_cat_atomic_input'
  source_run_id BIGINT,
  computed_at   TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (as_of_date, symbol)
);
```

Generate this DDL from `ma_columns_full.csv` with a tiny Python script — do NOT hand-write 113 columns.

### 3.2 `drv_cat_composite` (66 columns from NQ..QD)

Each column is one composite rule's score for that (date, symbol). Excel pre-computes these via `=Trig!<col>1`-style references; the Trig tab applies the composite formula to the atomic-input row and emits a numeric score.

Two approaches — pick one based on whether you trust Excel's composites or our code's:

**Option A (recommended, parity-friendly):** Compute composites in code (the existing `_derive_stks_impl`) AND extract Excel's composites into `drv_cat_composite` for parity testing. The rule of thumb: drv_cat_composite is the *snapshot from Excel* (the workbook of record); `drv_stks.triggered_composite_ids` is what *our engine* computed. Diff them daily, alert on drift.

**Option B (Excel-of-record):** Drop the in-code composite aggregation; treat `drv_cat_composite` as the source of truth. Simpler but ties the engine to Excel forever. Not recommended once the registry is mature.

DDL pattern (option A):

```sql
CREATE TABLE drv_cat_composite (
  as_of_date  DATE NOT NULL,
  symbol      TEXT NOT NULL,
  -- 66 composite-rule columns. Header in MA is "=Trig!O1", which resolves at workbook
  -- open time to a string like "899-SA-Trend-Breaks". Use the resolved name.
  c899_sa_trend_breaks    NUMERIC,
  c898_xx_yy              NUMERIC,
  -- ...
  source_run_id BIGINT,
  computed_at   TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (as_of_date, symbol)
);
```

Snake-case the composite rule code: `899-SA-Trend-Breaks` → `c899_sa_trend_breaks`. Prefix with `c` because PG identifiers can't start with a digit.

---

## 4. Naming rules (apply uniformly)

**Table names:**
- `drv_cat_<concept>` lower-snake. Concept stays short and stable: `bollinger`, `rsi`, `macd`, `ivhv`, `volume`, `risk_range`, `trend_trade`, `moving_avg`, `perf_extremes`, `quad_outlook`, `holdings`, `action`, `atomic_input`, `composite`, `trig_summary`, `identity`, `price`, `etf`, `ii`, `ps`, `signal_strength`, `earnings`, `index_volatility`, `volatility_regime`, `fundamentals`, `sector_rollup`, `he_outlook`, `misc`.
- `drv2_<source>` lower-snake matching the hist_*/drv_* source: `drv2_td`, `drv2_tw`, `drv2_tl`, `drv2_y`, `drv2_rr`, `drv2_ii`, `drv2_ssh`, `drv2_ssl`, `drv2_sss`, `drv2_etf`, `drv2_etfchg`, `drv2_call`, `drv2_ps`, `drv2_to`, `drv2_holdings` (combines F + CS), and `drv2_ma_thin` (the cross-source residue).

**Column names:**
- Snake-case the Excel header. Drop spaces, `%`, `()`, etc.
- Resolve naming collisions with a context prefix from the column block: `last_price` (in `drv_cat_price`), `td_last_price` if both TD and TL versions need to coexist in the same target. Inside one drv_cat_* table there should be NO collisions — the categorization eliminates most of them.
- Composite names: prefix with `c` then snake-case the rule code.

**Primary keys:** every drv_cat_* table is keyed by `(as_of_date, symbol)`.

**Audit columns:** every table has `source_run_id BIGINT` (FK conceptually to `meta_derived_run.run_id`) and `computed_at TIMESTAMPTZ DEFAULT now()`.

**Idempotency:** every per-table derive function is `DELETE WHERE as_of_date = D` then `INSERT`. Same pattern as today's `drv_*` tables.

---

## 5. Registry-driven codegen contract

**Do not hand-write 30 derive functions × 600+ columns.** Build a generator.

### 5.1 The registry table

```sql
CREATE TABLE ref_ma_columns (
  column_name        TEXT PRIMARY KEY,        -- snake_case, unique across the project
  excel_header       TEXT NOT NULL,           -- original Excel cell text
  excel_col_letter   TEXT NOT NULL,           -- 'JG' etc.
  excel_col_idx      INT  NOT NULL,
  pipeline_stage     TEXT NOT NULL,           -- 'lookup_identity' | 'lookup_data' | 'derived_features'
                                              -- | 'separator' | 'atomic_input' | 'composite'
                                              -- | 'rule_summary' | 'decision' | 'holdings'
  concept            TEXT NOT NULL,           -- 'bollinger' | 'rsi' | 'macd' | 'ivhv' | ...
  drv_cat_table      TEXT NOT NULL,           -- e.g. 'drv_cat_bollinger' (= 'drv_cat_' || concept)
  drv2_table         TEXT,                    -- e.g. 'drv2_td' (NULL if pure cross-source)
  color_island_id    INT,                     -- reset whenever the same color is > 4 cols away
                                              -- (use as a sanity flag, NOT as the storage key)
  pg_type            TEXT NOT NULL,           -- 'NUMERIC' | 'TEXT' | 'DATE' | 'BOOLEAN'
  source_kind        TEXT NOT NULL,           -- 'passthrough' | 'lookup' | 'arithmetic'
                                              -- | 'conditional' | 'aggregate' | 'static_input'
                                              -- | 'array_formula' | 'cross_source'
  source_table       TEXT,                    -- Postgres source table for the value
  source_expr        TEXT,                    -- SQL fragment that produces the value
                                              -- e.g. (LOOKUP)   "td.bb_top_15d"
                                              -- e.g. (ARITH)    "tl.last_price - tl.prev_close"
                                              -- e.g. (COND)     "CASE WHEN s.is_y='Y' THEN y.close ELSE rr.close END"
  excel_formula      TEXT,                    -- original Excel formula (for audit / debug)
  exposed_to_rules   BOOLEAN DEFAULT false,   -- atomic_input columns are TRUE; others usually FALSE
  exposed_to_dashboard BOOLEAN DEFAULT true,  -- whether /api/stks should expose it
  display_label      TEXT,                    -- pretty label for the UI ("BB Top (15d)")
  notes              TEXT,
  loaded_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_ref_ma_columns_cat   ON ref_ma_columns(drv_cat_table);
CREATE INDEX ix_ref_ma_columns_stage ON ref_ma_columns(pipeline_stage);
CREATE INDEX ix_ref_ma_columns_drv2  ON ref_ma_columns(drv2_table);
```

`pipeline_stage` and `concept` are independent — index both. The two combined are what the UI / API filter on:

```
GET /api/ma/columns?stage=atomic_input              -- the 113 rule-input cols
GET /api/ma/columns?stage=decision                  -- the 29 decision cols
GET /api/ma/columns?concept=bollinger               -- all 35 BB cols across stages
GET /api/ma/columns?stage=derived_features&concept=bollinger  -- BB derived-features only (~13 cols)
```

Seed it from `docs/ma_columns_full.csv` plus a one-time hand-pass to fill in `pg_type`, `source_expr`, `exposed_to_rules`, and `display_label`.

### 5.2 The generator (`etl/ma_codegen.py`)

```python
def build_ddl(session) -> dict[str, str]:
    """Return {drv_cat_table_name: CREATE TABLE ddl} for every drv_cat_* table.
    Each DDL is `CREATE TABLE IF NOT EXISTS ... (PK..., col col_type, ..., source_run_id, computed_at)`.
    """
    rows = session.execute("SELECT * FROM ref_ma_columns ORDER BY drv_cat_table, excel_col_idx").mappings().all()
    by_cat = group_by(rows, lambda r: r["drv_cat_table"])
    out = {}
    for cat, cols in by_cat.items():
        if cat == "drv_cat_separator": continue   # skip Begin/End markers
        col_defs = [f"  {c['column_name']:<32} {c['pg_type']}" for c in cols]
        out[cat] = (
            f"CREATE TABLE IF NOT EXISTS {cat} (\n"
            f"  as_of_date DATE NOT NULL,\n"
            f"  symbol     TEXT NOT NULL,\n"
            + ",\n".join(col_defs) + ",\n"
            f"  source_run_id BIGINT,\n"
            f"  computed_at   TIMESTAMPTZ DEFAULT now(),\n"
            f"  PRIMARY KEY (as_of_date, symbol)\n"
            f");"
        )
    return out

def build_dml(session, cat_table: str) -> str:
    """Return the INSERT…SELECT that populates one drv_cat_* table for :as_of_date.
    Joins are derived from the union of source_table values; SELECT list from source_expr values.
    """
    cols = session.execute(
        "SELECT * FROM ref_ma_columns WHERE drv_cat_table = :c ORDER BY excel_col_idx",
        {"c": cat_table},
    ).mappings().all()
    if not cols:
        return ""
    sources = unique([c["source_table"] for c in cols if c["source_table"]])
    join_clauses = " ".join(JOIN_PATTERNS[s] for s in sources)
    select_list = ",\n  ".join(f"{c['source_expr']} AS {c['column_name']}" for c in cols)
    return (
        f"INSERT INTO {cat_table} (as_of_date, symbol, {','.join(c['column_name'] for c in cols)}, source_run_id)\n"
        f"SELECT :d AS as_of_date, syms.symbol,\n  {select_list},\n  :run_id AS source_run_id\n"
        f"FROM (SELECT DISTINCT symbol FROM ref_sector) syms\n  {join_clauses};"
    )
```

`JOIN_PATTERNS` is a dict mapping each `source_table` to its standard `LEFT JOIN ... ON syms.symbol = X.symbol AND X.snapshot_date = (SELECT MAX(snapshot_date) FROM X WHERE snapshot_date <= :d AND symbol = syms.symbol)` pattern (one entry per hist_*/drv_*).

### 5.3 Wire into `etl/derive.py`

Add a single new function per drv_cat_* table:

```python
def _derive_cat_table_impl(session, as_of_date, run_id, cat_table):
    session.execute(text(f"DELETE FROM {cat_table} WHERE as_of_date = :d"), {"d": as_of_date})
    dml = ma_codegen.build_dml(session, cat_table)
    if not dml: return 0
    result = session.execute(text(dml), {"d": as_of_date, "run_id": run_id})
    return result.rowcount

# Then in derive_all(), after derive_tw / etf / ii / ssh etc.:
for cat in ALL_DRV_CAT_TABLES:
    counts[cat] = _wrap(cat, lambda s,d,rid,c=cat: _derive_cat_table_impl(s,d,rid,c))(session, as_of_date, run_id)
```

Each per-cat call is now driven by data, not code.

---

## 6. drv2_* as VIEWs over drv_cat_*

Once `drv_cat_*` tables are physical, expose `drv2_*` as VIEWs:

```sql
CREATE OR REPLACE VIEW drv2_td AS
SELECT  i.as_of_date, i.symbol,
        b.bb_top_15d, b.bb_bot_15d, b.bb_streak,    -- from drv_cat_bollinger
        r.rsi,                                      -- from drv_cat_rsi
        v.iv_percentile, v.hv_percentile,           -- from drv_cat_ivhv
        ...
FROM    drv_cat_identity   i
LEFT JOIN drv_cat_bollinger b ON (i.as_of_date, i.symbol) = (b.as_of_date, b.symbol)
LEFT JOIN drv_cat_rsi       r ON (i.as_of_date, i.symbol) = (r.as_of_date, r.symbol)
LEFT JOIN drv_cat_ivhv      v ON (i.as_of_date, i.symbol) = (v.as_of_date, v.symbol)
WHERE   ...;
```

The view membership is itself derived from `ref_ma_columns WHERE drv2_table = 'drv2_td'`. Generate the views from the same registry.

This way `/api/data/drv2_td` keeps working as a per-source browser without doubling storage.

---

## 7. Rebuild the thin `drv_ma`

Replace the current 50-column `drv_ma` table with a thin gold layer that joins the drv_cat_* tables on `(as_of_date, symbol)`. Two options:

**Option A — VIEW (simpler):**
```sql
CREATE OR REPLACE VIEW drv_ma AS
SELECT  i.as_of_date, i.symbol, i.description, i.sector, i.asset_class,
        p.last_price, p.prev_close,
        rr.rr_outlook, rr.rr_brr,
        tt.a_trend_value, tt.a_trade_value,
        b.bb_top_15d, b.bb_bot_15d, b.bb_streak,
        r.rsi,
        v.iv_percentile, v.hv_percentile,
        m.a_macd_brr, m.a_macdh_d_brr,
        ma.sma_50, ma.sma_200, e.earnings_days,
        -- genuinely cross-source computed columns:
        (tt.a_trend_value - p.last_price) * 100.0 /
            NULLIF(tt.a_trend_value - tt.a_trade_value, 0)  AS pct_brr,
        ...
FROM    drv_cat_identity      i
LEFT JOIN drv_cat_price       p  USING (as_of_date, symbol)
LEFT JOIN drv_cat_risk_range  rr USING (as_of_date, symbol)
LEFT JOIN drv_cat_trend_trade tt USING (as_of_date, symbol)
LEFT JOIN drv_cat_bollinger   b  USING (as_of_date, symbol)
LEFT JOIN drv_cat_rsi         r  USING (as_of_date, symbol)
LEFT JOIN drv_cat_ivhv        v  USING (as_of_date, symbol)
LEFT JOIN drv_cat_macd        m  USING (as_of_date, symbol)
LEFT JOIN drv_cat_moving_avg  ma USING (as_of_date, symbol)
LEFT JOIN drv_cat_earnings    e  USING (as_of_date, symbol);
```

**Option B — materialized table** with a `_derive_ma_thin_impl` populated from the same registry. Use this if VIEW read latency exceeds 200 ms locally.

The cross-source derived columns (`pct_brr`, `composite_outlook`, etc.) live in option A's VIEW expression list, or in the materialized table's INSERT SELECT. Keep them small in number — most of MA's 641 columns are NOT cross-source; the categorization made that obvious.

---

## 8. Rules engine integration

**Today** `ref_trig_atomic_rule.ma_column_name` looks like `'drv_ma.rsi'`. The current `_derive_stks_impl` parses that string against `_MA_COL_MAP` and reads `drv_ma`. After this migration:

1. Update the migration script to rewrite `ma_column_name` from `'drv_ma.rsi'` → `'drv_cat_atomic_input.rsi'`. Provide a small lookup helper: `column_to_cat(col_name)` that consults `ref_ma_columns` and returns the table.
2. In `_derive_stks_impl`, change the read source from `drv_ma` to `drv_cat_atomic_input`. **All 113 atomic-input columns are colocated in one table — no per-column join needed.** Massive speedup vs the current row-by-row Python loop over drv_ma.
3. The Rules Manager UI's "Pick column" typeahead now hits `GET /api/ma/columns?exposed_to_rules=true`, which returns rows from `ref_ma_columns WHERE exposed_to_rules = true` — the 113 atomic-input columns by default, plus any drv_cat_* column the user explicitly opts in.
4. `drv_cat_composite` enables a new sanity check: nightly diff between `drv_cat_composite.<rule>` (Excel) and the score in `drv_stks.triggered_composite_ids[<rule>]` (our code). Drift > epsilon → alert.

---

## 9. Build sequence

Each step is independently shippable; each ends with a parity test passing before moving on.

1. **Build `ref_ma_columns` and seed it** from `docs/ma_columns_full.csv`.
   - Hand-disambiguate the 78 name collisions noted in `docs/ma_columns_registry_seed.csv`.
   - Hand-classify the 208 array-formula columns by opening MA in Excel and reading the formula bar.
   - Tighten the 79-column `drv_cat_misc` bucket.
   - Populate `pg_type`, `source_expr`, `exposed_to_rules`, `display_label` for every row.
2. **Implement `etl/ma_codegen.py`** with `build_ddl()` and `build_dml(cat_table)`.
3. **Generate and apply DDL** for the smallest two cat tables first: `drv_cat_identity` (11 cols) and `drv_cat_macd` (5 cols). Run derive_all for one date. Confirm row counts match the symbol universe.
4. **Parity test** — pull 20 representative symbols × 5 dates from both the new `drv_cat_*` tables and the original Excel MA columns (open the workbook with openpyxl, read `data_only=True`). Diff column-by-column. Any divergence is a `source_expr` bug; fix it in the registry, regenerate, re-run.
5. **Tackle one cat table per day** in this order: `drv_cat_price`, `drv_cat_risk_range`, `drv_cat_trend_trade`, `drv_cat_bollinger`, `drv_cat_rsi`, `drv_cat_ivhv`, `drv_cat_volume`, `drv_cat_moving_avg`, `drv_cat_earnings`, `drv_cat_perf_extremes`, `drv_cat_quad_outlook`, `drv_cat_fundamentals`, `drv_cat_index_volatility`, `drv_cat_volatility_regime`, `drv_cat_atomic_input` ← **biggest payoff, do this carefully**, `drv_cat_composite` ← ditto, then the action / holdings / trig_summary / sector_rollup tables.
6. **Wire `drv_cat_atomic_input` into the rules engine** — rewrite `ma_column_name` values, change `_derive_stks_impl` to read from the colocated table.
7. **Add `drv2_*` VIEWs** generated from the registry.
8. **Rebuild the thin `drv_ma`** as a VIEW (or materialized table) over the cat tables.
9. **Drop the old wide `drv_ma` columns** that are now duplicated in cat tables. Keep only the cross-source derived ones (~50). This is the only physical-schema teardown step.
10. **Update the dashboard** — `/api/stks` reads from the thin `drv_ma`; `/api/data/drv_cat_<x>` browser endpoints become available; Rules Manager exposes the column typeahead.

---

## 10. Parity test pattern

Single test that covers any cat table:

```python
# tests/test_cat_parity.py
import pytest
from openpyxl import load_workbook
from etl.db import session_scope
from sqlalchemy import text

WB = "C:/Ashok/Invest/Projects/Cluade/Tickers 2026-04-30.xlsx"
SAMPLE_SYMBOLS = ["AAPL","SPY","TLT","GLD","VIX","XLE","ZM","NVDA","MSFT","TSLA",
                  "QQQ","IWM","HYG","UUP","SLV","BTC","ETHE","BIIB","CVX","JPM"]
SNAPSHOT = date(2026, 4, 30)

@pytest.mark.parametrize("cat_table,column_name,excel_col_letter", load_registry_subset())
def test_parity(cat_table, column_name, excel_col_letter):
    excel_value = read_ma_cell(WB, "MA", excel_col_letter, sample_symbol_row(SAMPLE_SYMBOLS[0]))
    with session_scope() as s:
        db_value = s.execute(text(f"SELECT {column_name} FROM {cat_table} "
                                  f"WHERE as_of_date=:d AND symbol=:sym"),
                             {"d": SNAPSHOT, "sym": SAMPLE_SYMBOLS[0]}).scalar()
    assert close_enough(excel_value, db_value), f"{cat_table}.{column_name} ({excel_col_letter}) Excel={excel_value} DB={db_value}"
```

Expand `SAMPLE_SYMBOLS` to cover ETF / equity / index / commodity / treasury / volatility / international / small-cap. 20 is enough; 100 is plenty.

---

## 11. No `drv_cat_misc` in v2

The v1 categorization produced 79 misc columns. The refined v2 categorization (with the pipeline-stage axis and the proximity-fallback rule) eliminates the misc bucket entirely — every one of the 641 columns now resolves to a real concept.

If after your hand-pass any columns still look like misc, the right answer is almost always:
- **It's actually a date / identity column** → `drv_cat_identity`, `pipeline_stage = lookup_identity`.
- **It's a holdings $ column** → `drv_cat_holdings_dollars`, `pipeline_stage = holdings`.
- **It's a final action / decision column** → `drv_cat_action_decision`, `pipeline_stage = decision`.
- **It's a one-off cross-source computed column** → goes in the thin `drv_ma`, NOT in any drv_cat_*.

---

## 12. The 208 array-formula columns

openpyxl flags array formulas as opaque objects, so they didn't translate in the audit. Strategy:

1. Open MA in Excel.
2. For each `source_kind = 'array_formula'` row in the registry, click the cell, copy the formula from the formula bar, paste it back into `excel_formula` in `ref_ma_columns`.
3. Re-run the categorizer / SQL-translator; most array formulas are simple BB-band slope (linear regression over 3-15 day windows), distance-to-MA, or stdev-over-window — all PostgreSQL window functions: `regr_slope()`, `stddev_samp()`, `(value - LAG(value, n) OVER ...) / NULLIF(...)`.
4. Update `source_expr` in `ref_ma_columns`.

Budget: half a day for the 208 array formulas, most of which are variants of three or four window-function patterns.

---

## 13. What stays unchanged

These pieces of the system don't need to be touched by this work:

- `hist_*` ingestion (load_raw, etl_load, scheduler).
- `drv_*` per-row cleanup (drv_tl, drv_td, drv_tw, drv_call, drv_etf, drv_ii, drv_ssh, drv_ssl, drv_sss, drv_ps).
- `meta_*` audit tables.
- `ref_*` lookup tables (other than `ref_trig_atomic_rule.ma_column_name` rewrites and the new `ref_ma_columns` registry).
- `drv_dash`, `drv_dash_summary`, `drv_missing_symbols`, `drv_trig` (will need a follow-up to point them at `drv_cat_atomic_input` like `drv_stks` does).
- The watchdog scheduler / etl_load entry points.
- The FastAPI routing (only the SQL behind a few endpoints changes).
- The Cockpit / dashboard / Rules Manager UI structure (drawer content gains category grouping but the page layout is unchanged).

---

## 14. Files this design will create or modify

**Create:**
- `db/14_drv_cat_tables.sql` — generated DDL for ~30 drv_cat_* tables.
- `db/15_drv2_views.sql` — generated VIEWs for ~14 drv2_* views.
- `db/16_thin_drv_ma.sql` — thin drv_ma (VIEW or table).
- `db/17_ref_ma_columns.sql` — the registry table DDL.
- `db/18_atomic_rule_ma_column_rewrite.sql` — rewrite `ref_trig_atomic_rule.ma_column_name`.
- `etl/ma_codegen.py` — generator (build_ddl, build_dml).
- `etl/seed_ref_ma_columns.py` — one-time loader from `docs/ma_columns_full.csv`.
- `etl/extract_ma_registry.py` — utility that re-extracts the registry from a workbook.
- `tests/test_cat_parity.py` — parametrized parity test.
- `tests/test_eval_atomic_rule.py` — covers the existing eval logic; should keep passing unchanged.

**Modify:**
- `etl/derive.py` — `derive_all` calls `_derive_cat_table_impl` for each drv_cat_* table; `_derive_stks_impl` reads from `drv_cat_atomic_input` instead of `drv_ma`; `_MA_COL_MAP` is removed (replaced by the registry).
- `etl/derive_v2.py` — unchanged (the v2 overrides for tw/etf/ii/ssh/ps/sss are upstream of the new layer).
- `api/main.py` — new endpoint `GET /api/ma/columns` + `/api/data/drv_cat_<x>` patterns.
- `api/models.py` — add `MaColumnMeta` model.
- `web/rules.js` — pick-column typeahead now backed by the registry.
- `web/cockpit.js` — drawer groups triggered atomics by category from `drv_cat_atomic_input.<col>` joined to `ref_ma_columns.drv_cat_table`.
- `CLAUDE.md` — add a "Tier 4: drv_cat_*" section linking back to this document.

---

## 15. Quick-start checklist for the implementing model

```
[ ] Read docs/ma_columns_full.csv and docs/drv_cat_summary.csv (already on disk).
[ ] Open Tickers 2026-04-30.xlsx; keep MA tab visible during the work.
[ ] Implement db/17_ref_ma_columns.sql + etl/seed_ref_ma_columns.py and load the registry.
[ ] Tighten the registry: hand-resolve 78 name collisions, push drv_cat_misc < 20, capture the 208 array formulas.
[ ] Implement etl/ma_codegen.py (build_ddl, build_dml).
[ ] Generate db/14_drv_cat_tables.sql and apply.
[ ] Add per-cat derive functions to etl/derive.py and wire into derive_all.
[ ] Run derive_all for 2026-04-30. Confirm row counts in every drv_cat_* table = symbol count.
[ ] Run tests/test_cat_parity.py. Drive failures to zero by editing source_expr in the registry, NOT in code.
[ ] Generate drv2_* VIEWs (db/15_drv2_views.sql).
[ ] Build thin drv_ma (db/16_thin_drv_ma.sql). Confirm /api/stks still returns the same JSON (a separate parity test).
[ ] Rewrite ref_trig_atomic_rule.ma_column_name to point at drv_cat_atomic_input.* (db/18_...).
[ ] Update _derive_stks_impl to read from drv_cat_atomic_input. Run; confirm drv_stks composites unchanged.
[ ] Wire Rules Manager typeahead to GET /api/ma/columns?exposed_to_rules=true.
[ ] Drop the legacy wide drv_ma columns that are now duplicated. Keep cross-source columns only.
[ ] Update CLAUDE.md.
```

That checklist is the entire migration. Each step is reversible up until the final drop.

---

## 16. Anti-goals (do NOT do these)

- **Do not** physically materialize both `drv_cat_*` and `drv2_*` — pick `drv_cat_*` as the storage and let `drv2_*` be VIEWs.
- **Do not** keep the wide `drv_ma` table after the cat tables exist — drop the duplicate columns; thin drv_ma should only carry cross-source / final-derived columns.
- **Do not** hand-write the per-cat-table derive functions — generate them from the registry. If you find yourself typing `INSERT INTO drv_cat_bollinger (col1, col2, ...)`, stop and use the codegen.
- **Do not** remove `eval_atomic_rule` or the in-code composite aggregation — `drv_cat_composite` (from Excel) is for parity, not for replacement.
- **Do not** put atomic-rule **outputs** (rule scores) into `drv_cat_atomic_input` — that table is strictly the value side of the rule comparison. Rule outputs live in `drv_stks.triggered_atomic_ids` / `drv_cat_composite`.
- **Do not** treat color as authority. Same color far apart in MA does NOT mean same concept. Apply the proximity rule (ISLAND_GAP ≤ 4 cols) and let header keyword + formula content drive concept assignment.
- **Do not** discard the `pipeline_stage` axis — even if storage is by concept, the stage tag is what makes the Cockpit drawer useful as a "show me the path AAPL took from raw data to final action" view.
- **Do not** create a `drv_cat_misc` table — the v2 categorization eliminates it; if you find yourself wanting one, the column is misclassified.

---

## 17. Suggested UI use of the two axes

Once stage + concept are in the registry, two natural new views become free:

**Cockpit drawer — "Path of the symbol"** — left-to-right strip showing AAPL on 2026-05-07 traversing the seven stages:

```
[ lookup_identity ]   AAPL · Apple Inc · sector=IT · last_price=$214.50
       ▼
[ lookup_data ]       hist_y close=$214.50 · hist_tl iv=0.27 · hist_td bb=$220/$200 · hist_rr brr=+0.52
       ▼
[ derived_features ]  bb_top_15d, range_compression, sma_50=$212, iv_percentile=44, rsi=63, a_macd_brr=+
       ▼
[ atomic_input ]      ▶ 6 atomic rules fired in this stage  (RSI Rule, MACD Direction, 200-DMA-Rule, BRR% Rule, BB Top, IVPercentile)
       ▼
[ composite ]         ▶ 2 composite rules triggered  (BM-Momentum-Up score=+4, 899-SA-Trend-Breaks score=+6)
       ▼
[ rule_summary ]      Trig Matched Rule1=BM-Momentum-Up · HE Entry=BuyMore · SS Entry=BuyMore
       ▼
[ decision ]          OverAll=BULLISH · Final Action=BM · ^L1=Long · ^L2=Long · ^L3=Bench
       ▼
[ holdings ]          Fidelity=12 sh · CS=0 · Long$=$2,574 · Stocks$=$2,574 · My=Yes
```

Each stage is collapsible. Clicking a stage opens a panel showing only the columns from that stage for the current symbol — exactly the slice of the MA tab the user would scroll to in Excel.

**Rules Manager — "Pick column" typeahead** — lists by `concept`, with `pipeline_stage` as a filter:

```
Concept: [bollinger ▼]   Stage: [atomic_input ▼]   →   [BBStreak Rule, BBStreak Days Rule, BB Top, BB Bottom, ...]
Concept: [bollinger ▼]   Stage: [derived_features ▼] → [bb_top_15d, bb_bot_15d, bb_top_slope, bb_bot_slope, ...]
```

Rules engineers think in concepts; the stage filter exists to keep them inside `atomic_input` by default (since that's the only stage rules are *supposed* to read from).

---

End of instructions.
