# TASK_125 — PVV multi-bucket signal + decision column on Actionable

## Goal

New derive `drv_pvv`: a Price/Volume/Volatility (PVV, Hedgeye-style ROC) signal
computed in 4 time buckets per symbol, consolidated into one decision (e.g.
`BUY_DIP`), surfaced on the Actionable screen as a new column with a rich hover
tooltip showing per-bucket detail (same tooltip mechanism as existing columns).

This is an **informational column** in v1: do NOT wire it into
`consolidated_action` / `drv_actionable` scoring. That is a future task.

---

## 1. New table `drv_pvv` (db/baseline.sql)

```sql
CREATE TABLE IF NOT EXISTS drv_pvv (
    as_of_date  DATE NOT NULL,
    tos_symbol  TEXT NOT NULL,
    sig_today   TEXT,        -- signal code per bucket (see §3)
    sig_5d      TEXT,
    sig_3w      TEXT,
    sig_3m      TEXT,
    decision    TEXT,        -- consolidated (see §4)
    detail      JSONB,       -- per-bucket inputs for the tooltip (see §5)
    derived_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
```

Idempotent derive: `DELETE WHERE as_of_date=D` → INSERT (convention #2).
`tos_symbol` only, never raw `symbol` (convention #15). Universe =
`drv_symbols` for D. Keep each SQL command ≤ 965 bytes (convention #7).

## 2. New module `etl/derive_pvv.py`, wired into `derive_all`

Insert into the cascade **after** the 5 component tables (needs
`drv_technicals` for vlm_projected/SMAs), before `drv_dash`. Follow the
`_wrap(...)` pattern in `etl/derive.py`.

Put all thresholds in a module-level `PVV_CONFIG` dict (constants for v1; a
later task may move them to `ref_param`).

### Bucket inputs (per tos_symbol, anchor date D)

| Bucket | Price ROC | Volume ROC | Volatility ROC | Flat band |
|---|---|---|---|---|
| `today` | tl last_price vs prior-day TD last_price | drv_technicals.vlm_projected vs 20d avg EOD volume | tl imp_volatility_raw vs prior TD imp_volatility | **1.0σ** (alert-only, wide) |
| `5d` | 5d ROC of hist_td last_price | 5d ROC of EOD volume | 5d ROC of hist_td imp_volatility | 0.5σ |
| `3w` | 15d ROC of hist_td last_price | 15d ROC of EOD volume | 15d ROC of imp_volatility | 0.5σ |
| `3m` | structure, not ROC (see below) | none (skip) | iv_percentile level | n/a |

Definitions:
- **EOD volume** = hist_tl volume at max(sequence) per export_date per symbol
  (hist_td has no volume column). Missing days → treat that day as NULL, use
  nearest available; if fewer than 3 usable points in the window → bucket
  signal `NA`.
- **Flat band**: |ROC| < k × trailing σ of that symbol's own ROC series
  (σ over trailing 60 obs, min 20; else fall back to cross-sectional σ for D).
  Within band → direction = Flat.
- **IV null fallback** (futures/indices): use `historical_vol` (and
  `hv_percentile` for 3m) — record which source was used in `detail`.
- **3m bucket**: price direction = ↑ if last_price > sma_50 AND sma_50 > sma_200;
  ↓ if last_price < sma_50 AND sma_50 < sma_200; else Flat. Vol direction =
  ↑ if iv_percentile ≥ 70, ↓ if ≤ 30, else Flat. (SMAs/percentiles from
  drv_technicals / hist_tw.)

### 3w gate

After classifying 3w, apply duration-level gate: if signal is bullish but
last_price < `a_trend_value`, demote one notch (STRONG_BULL→WEAK_BULL,
WEAK_BULL→NEUTRAL); mirror for bearish above a_trend_value. Record
`gated: true` in detail.

## 3. Per-bucket signal table (P / V / Vol directions → signal code)

| Price | Volume | Vol | Code |
|---|---|---|---|
| ↑ | ↑ | ↓ | `STRONG_BULL` |
| ↑ | ↑ | ↑ | `OVEREXT_BULL` |
| ↑ | ↓ | ↓ | `WEAK_BULL` |
| ↑ | ↓ | ↑ | `BEAR_DIV` |
| ↓ | ↑ | ↑ | `STRONG_BEAR` |
| ↓ | ↑ | ↓ | `MILD_BEAR` |
| ↓ | ↓ | ↓ | `DRIFT` |
| ↓ | ↓ | ↑ | `BEAR_LEAN` |
| Flat price | any | any | `NEUTRAL` |
| insufficient data | | | `NA` |

Volume Flat: resolve toward ↓ (unconfirmed). Vol Flat: resolve toward ↓
(calm). 3m bucket has no volume → classify on Price/Vol only: ↑ + vol↓ =
STRONG_BULL, ↑ + vol↑ = OVEREXT_BULL, ↓ + vol↑ = STRONG_BEAR, ↓ + vol↓ =
DRIFT, Flat = NEUTRAL.

Implement as a **pure function** `classify_pvv(p_dir, v_dir, vol_dir) -> str`
so it's unit-testable without DB.

## 4. Consolidated decision (first match wins)

Bull-ish = {STRONG_BULL, OVEREXT_BULL, WEAK_BULL}; Bear-ish = {STRONG_BEAR,
MILD_BEAR, BEAR_LEAN, BEAR_DIV}.

| # | Condition | decision |
|---|---|---|
| 1 | sig_5d, sig_3w, sig_3m all bull-ish AND sig_today bull-ish | `BUY` |
| 2 | sig_5d, sig_3w, sig_3m all bull-ish AND sig_today bear-ish/NEUTRAL/DRIFT | `BUY_DIP` |
| 3 | sig_3m bull-ish AND sig_5d & sig_3w both bear-ish | `REDUCE` (trend break) |
| 4 | sig_today bull-ish AND sig_5d & sig_3w both bear-ish | `AVOID` (bounce, don't chase) |
| 5 | sig_5d = STRONG_BEAR AND sig_3w bear-ish | `SELL` |
| 6 | sig_5d = OVEREXT_BULL or BEAR_DIV (regardless of others) | `TRIM` |
| 7 | any bucket NA that rules 1–6 needed | `WATCH` |
| 8 | otherwise | `WATCH` |

## 5. `detail` JSONB shape (drives the tooltip)

```json
{"today": {"sig":"MILD_BEAR","p_roc":-0.012,"v_roc":0.35,"vol_roc":-0.04,
           "p_dir":"down","v_dir":"up","vol_dir":"down","vol_src":"iv"},
 "d5":    {...}, "w3": {..., "gated": false}, "m3": {"sig":"STRONG_BULL",
           "price_vs_sma50": 1.03, "sma50_vs_sma200": 1.02, "iv_pctile": 22}}
```

## 6. API

Extend the Actionable payload (`api/routers/dash.py`, same query that feeds
the screen) with `pvv_decision` and `pvv_detail` via LEFT JOIN on
`drv_pvv(as_of_date, tos_symbol)`. NULL-safe when no row.

## 7. UI (`web/actionable.html` / `web/actionable.js`)

- New column **PVV** rendering `decision` as a colored badge — follow the
  existing badge pattern (`firesCellHtml` / `ruleEdgeBadge`). Colors:
  BUY/BUY_DIP green (BUY_DIP distinct shade), SELL/REDUCE red, TRIM/AVOID
  amber, WATCH gray, empty when no row.
- **Rich hover tooltip** using the same tooltip mechanism as existing detail
  columns: a small 4-row table (Today / 5d / 3w / 3m) showing per bucket the
  signal code plus P/V/Vol arrows with the ROC values from `detail`
  (percentages, 1 decimal). Mark gated 3w with "(gated)"; show vol source
  when hv fallback used.
- Column sortable by decision rank (BUY > BUY_DIP > TRIM > WATCH > AVOID >
  REDUCE > SELL is NOT the sort order — sort by actionability: BUY_DIP, BUY,
  SELL, REDUCE, TRIM, AVOID, WATCH).

## 8. Backfill

After wiring, run derive for the current anchor D. Then backfill history via
`etl/backfill_derives.py` pattern for all dates with hist_td (so scorecard
work later has history). If backfill runtime is excessive, backfill the last
120 anchor dates only and note it in DEV_HANDOFF.

## 9. Tests (convention #18)

- `tests/test_pvv_classify.py` — pure-Python unit tests of `classify_pvv`
  and the decision matrix (all 9 signal rows + decisions 1–8). No DB needed.
- Acceptance checks (marked `@pytest.mark.acceptance`, in `tests/acceptance/`):
  drv_pvv populated for anchor date; API returns pvv fields.

## How to verify (tester reference — run only on explicit request)

1. `pytest tests/test_pvv_classify.py` → all pass.
2. `psql`: `SELECT decision, COUNT(*) FROM drv_pvv WHERE as_of_date =
   (SELECT MAX(export_date) FROM hist_td) GROUP BY 1;` → rows exist, mix of
   decisions, no bucket 100% NA.
3. `psql`: pick one symbol with decision='BUY_DIP' (if any) and confirm
   sig_5d/sig_3w/sig_3m bull-ish per §4 rule 2.
4. `curl "http://127.0.0.1:8000/api/actionable?date=<D>"` (or actual
   endpoint) → items include `pvv_decision`, `pvv_detail`.
5. Open `/actionable` in browser: PVV column visible, badge colors correct,
   hover shows 4-bucket tooltip with ROC values.

## Files expected to change

- `db/baseline.sql` (new table)
- `etl/derive_pvv.py` (new)
- `etl/derive.py` (wire into derive_all)
- `api/routers/dash.py`
- `web/actionable.js`, `web/actionable.html` (if column header markup needed)
- `tests/test_pvv_classify.py`, `tests/acceptance/...`
- `docs/pvv_logic.md` (new — copy §2–§5 tables as the detail doc; add one
  Lookup row to CLAUDE.md)

No commits — user commits from Windows (workflow rule).
