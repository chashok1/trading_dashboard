# Trading Dashboard — Rule Engine v2 Design

**Status:** Design only. No code changes yet.
**Author context:** Hand-off doc — use this to implement in a fresh conversation.
**Repo:** `C:\Ashok\Invest\Projects\trading-dashboard`
**Stack:** PostgreSQL 17 (`trading` DB) + FastAPI (127.0.0.1:8000) + vanilla JS frontend + Chart.js.

---

## 1. Background and Motivation

The current system replaces a 34-tab Excel workbook (`Tickers YYYY-MM-DD.xlsx`) for stock trading rule evaluation. It has:

- ~115 atomic rules (read MA column → compare to `brkeout_from`/`brkeout_to` thresholds → assign `wt_below`/`wt_between`/`wt_above`).
- ~70 composite rules (sum of weighted contributions from participating atomic rules).
- Action codes: **SA** = Sell All, **STM** = Sell To Minimum, **SS** = Sell Some, **BM** = Buy More.
- Rule naming convention example: `899-SA-Trend-Breaks` = numeric ID + action prefix + descriptive name.

**Pain points to fix:**
1. STKS (action-driving) and DASH tabs need a better web UI.
2. No web-based CRUD for rules — they live in Excel/DB only.
3. No traceability from a recommended action back to the rules that triggered it.
4. Jump conditions (e.g., RSI 30/70) are intentional for some fields, but other fields would benefit from smooth scoring. Engine currently only supports jumps.
5. No feedback loop — we don't measure which rules actually predict outcomes.

**Design constraint from user:** SA/STM/SS/BM are meaningful action codes (not cryptic). Jump conditions are correct for regime-indicator fields (RSI thresholds, MACD sign, BB streak, IV percentile, earnings days, Quad regime). Smooth scoring should be opt-in per rule, not global.

---

## 2. Schema Changes (DDL)

All additions are backward-compatible. New columns default to safe values so existing rules keep working.

### 2.1 `ref_trig_atomic_rule` — add columns

```sql
ALTER TABLE ref_trig_atomic_rule
  ADD COLUMN category        text,                       -- Trend / Momentum / Volatility / Sentiment / Event / Fundamental
  ADD COLUMN intent_text     text,                       -- Human-readable hypothesis: "RSI < 30 implies oversold bounce setup"
  ADD COLUMN scoring_mode    text NOT NULL DEFAULT 'jump',  -- 'jump' | 'linear' | 'sigmoid'
  ADD COLUMN score_params    jsonb;                      -- e.g. {"k": 0.15, "x0": 50} for sigmoid, {"min": 0, "max": 100} for linear
```

### 2.2 `ref_trig_composite_mapping` — add columns

```sql
ALTER TABLE ref_trig_composite_mapping
  ADD COLUMN category          text,
  ADD COLUMN intent_text       text,
  ADD COLUMN precondition_expr text;   -- SQL boolean expr; if false, composite is skipped (e.g. "sector <> 'ETF'")
```

### 2.3 New table — `user_action_log`

```sql
CREATE TABLE user_action_log (
  id                bigserial PRIMARY KEY,
  as_of_date        date        NOT NULL,
  symbol            text        NOT NULL,
  action_code       text        NOT NULL,        -- SA / STM / SS / BM / HOLD / SKIP
  triggered_rules   jsonb       NOT NULL,        -- [{rule_id, kind:'atomic'|'composite', weight, intent}]
  notes             text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  user_email        text                              -- optional, for multi-user later
);
CREATE INDEX ix_user_action_log_symbol_date ON user_action_log(symbol, as_of_date);
```

### 2.4 New table — `drv_rule_outcome`

```sql
CREATE TABLE drv_rule_outcome (
  rule_id        text       NOT NULL,
  rule_kind      text       NOT NULL,    -- 'atomic' | 'composite'
  as_of_date     date       NOT NULL,
  symbol         text       NOT NULL,
  action_code    text,
  fwd_5d_pct     numeric,
  fwd_20d_pct    numeric,
  hit            boolean,                -- true if return moved in the predicted direction by threshold
  computed_at    timestamptz DEFAULT now(),
  PRIMARY KEY (rule_id, as_of_date, symbol)
);
```

### 2.5 New view — `v_rule_performance`

```sql
CREATE OR REPLACE VIEW v_rule_performance AS
SELECT
  rule_id,
  rule_kind,
  COUNT(*)                              AS sample_size,
  AVG(CASE WHEN hit THEN 1 ELSE 0 END)  AS hit_rate,
  AVG(CASE WHEN NOT hit THEN 1 ELSE 0 END) AS false_positive_rate,
  AVG(fwd_5d_pct)                       AS avg_fwd_5d,
  AVG(fwd_20d_pct)                      AS avg_fwd_20d,
  MIN(as_of_date)                       AS first_seen,
  MAX(as_of_date)                       AS last_seen
FROM drv_rule_outcome
WHERE as_of_date >= CURRENT_DATE - INTERVAL '180 days'
GROUP BY rule_id, rule_kind;
```

### 2.6 Backfill (one-time)

```sql
-- Tag categories from rule name prefixes / known mappings
UPDATE ref_trig_atomic_rule SET category = 'Trend'      WHERE rule_name ILIKE '%trend%' OR rule_name ILIKE '%MA%';
UPDATE ref_trig_atomic_rule SET category = 'Momentum'   WHERE rule_name ILIKE '%RSI%'   OR rule_name ILIKE '%MACD%';
UPDATE ref_trig_atomic_rule SET category = 'Volatility' WHERE rule_name ILIKE '%BB%'    OR rule_name ILIKE '%ATR%' OR rule_name ILIKE '%IV%';
UPDATE ref_trig_atomic_rule SET category = 'Event'      WHERE rule_name ILIKE '%earn%'  OR rule_name ILIKE '%div%';
UPDATE ref_trig_atomic_rule SET category = 'Sentiment'  WHERE rule_name ILIKE '%II%'    OR rule_name ILIKE '%senti%';
UPDATE ref_trig_atomic_rule SET category = 'Fundamental' WHERE category IS NULL;

-- Default scoring_mode = 'jump' (already set by DEFAULT). Mark fields better suited for smooth scoring:
UPDATE ref_trig_atomic_rule SET scoring_mode = 'linear'
  WHERE rule_name ILIKE '%pct_change%' OR rule_name ILIKE '%distance_to_MA%';
UPDATE ref_trig_atomic_rule SET scoring_mode = 'sigmoid', score_params = '{"k":0.1,"x0":50}'
  WHERE rule_name ILIKE '%composite_strength%';
```

---

## 3. Derive Layer Changes (`etl/derive.py` + `derive_v2.py`)

### 3.1 Extend `eval_atomic_rule()` to branch on `scoring_mode`

```python
def eval_atomic_rule(value, rule):
    if value is None:
        return 0.0
    mode = rule.get('scoring_mode', 'jump')
    lo, hi = rule['brkeout_from'], rule['brkeout_to']
    if mode == 'jump':
        if value < lo:  return rule['wt_below']
        if value > hi:  return rule['wt_above']
        return rule['wt_between']
    if mode == 'linear':
        # Map [lo, hi] linearly between wt_below and wt_above
        if value <= lo: return rule['wt_below']
        if value >= hi: return rule['wt_above']
        t = (value - lo) / (hi - lo)
        return rule['wt_below'] + t * (rule['wt_above'] - rule['wt_below'])
    if mode == 'sigmoid':
        import math
        params = rule.get('score_params') or {}
        k  = params.get('k', 0.1)
        x0 = params.get('x0', (lo + hi) / 2)
        s = 1 / (1 + math.exp(-k * (value - x0)))
        return rule['wt_below'] + s * (rule['wt_above'] - rule['wt_below'])
    return 0.0
```

### 3.2 Persist traceability into `drv_stks`

Add two columns to `drv_stks`:

```sql
ALTER TABLE drv_stks
  ADD COLUMN triggered_atomic_ids  jsonb,   -- [{rule_id, weight, value}]
  ADD COLUMN triggered_composite_ids jsonb; -- [{rule_id, score, contributors:[atomic_ids]}]
```

In the derive function, while computing each composite score, accumulate the atomic IDs whose contribution was non-zero, then write the array back. Cost: one extra JSONB column write per row, negligible.

### 3.3 Honor `precondition_expr`

Before evaluating a composite, run its `precondition_expr` against the row. If false, skip the composite entirely (don't even write zero — leave NULL so downstream can distinguish "didn't apply" from "scored zero").

---

## 4. Outcome ETL (new daily job)

New script: `etl/compute_outcomes.py`

**Inputs:** `user_action_log` rows older than 5 trading days that don't yet have a row in `drv_rule_outcome`.

**For each such (symbol, as_of_date, action_code):**
1. Look up close price on `as_of_date` from `hist_td`.
2. Look up close price 5 trading days later, 20 trading days later.
3. Compute `fwd_5d_pct`, `fwd_20d_pct`.
4. Determine `hit`:
   - SA / STM / SS → expected forward return ≤ 0 → `hit = (fwd_5d_pct <= -0.5%)`
   - BM → expected forward return ≥ 0 → `hit = (fwd_5d_pct >= +0.5%)`
   - HOLD → `hit = (abs(fwd_5d_pct) < 1%)`
5. For each rule in `triggered_rules` JSONB, write a `drv_rule_outcome` row.

**Schedule:** nightly via Windows Task Scheduler (or the existing watchdog runner) after market close + 1 day.

---

## 5. API Endpoints (FastAPI — `api/main.py`)

### Read
- `GET /stks/{date}` — existing; **add** `triggered_rules` summary per row (just IDs + counts; full detail via `/why`).
- `GET /stks/{date}/{symbol}/why` — full rule trace: list of triggered atomics + composites with weights, intents, contributing values.
- `GET /rules/atomic` — list with category filter, search, pagination.
- `GET /rules/atomic/{rule_id}` — single rule detail.
- `GET /rules/composite` — list.
- `GET /rules/composite/{rule_id}` — detail with member atomic rules.
- `GET /rules/performance` — joined to `v_rule_performance`; supports sort by hit_rate / sample_size / category.
- `GET /rules/performance/{rule_id}/symbols` — symbols where this rule fired in last N days, with outcomes.

### Write
- `POST /rules/atomic` — create.
- `PUT /rules/atomic/{rule_id}` — update; validates `referenced_columns` exist in schema; runs dry-run against latest snapshot and returns affected-row count + score-distribution preview.
- `DELETE /rules/atomic/{rule_id}` — soft delete (add `deprecated_at` column).
- `POST /rules/composite`, `PUT /rules/composite/{rule_id}`, `DELETE /rules/composite/{rule_id}` — same pattern.
- `POST /actions` — log a user decision: `{as_of_date, symbol, action_code, notes}`. Backend snapshots the current `triggered_rules` from `drv_stks` into `user_action_log`.

### Validation rules for rule edits
- `referenced_columns` must all exist in the schema (introspect `information_schema.columns`).
- `brkeout_from < brkeout_to`.
- If `scoring_mode = 'sigmoid'`, `score_params` must include `k` and `x0`.
- Dry-run before commit; reject if dry-run errors.

---

## 6. Frontend — Three New Pages

### 6.1 Action Cockpit (`/cockpit`) — replaces Stks tab
- Top: date picker, action filter (SA/STM/SS/BM/All), sector filter, symbol search.
- Main: table of recommended actions — symbol, name, sector, last price, action code, composite score, top 3 contributing rules (chips).
- Click row → right-side drawer:
  - Symbol header + last price + 1-day chart.
  - Triggered atomic rules (sortable by weight): rule name, category, intent_text, value, weight contribution.
  - Triggered composite rules: rule name, score, breakdown by contributor.
  - "I took this action" button → `POST /actions` with current snapshot.
  - "Skip" button → logs HOLD/SKIP for outcome tracking.

### 6.2 Rules Manager (`/rules`)
- Two tabs: Atomic | Composite.
- Table with inline edit on weight thresholds + scoring mode.
- "New rule" button → modal with full form.
- Each edit triggers dry-run preview: "This change would affect 47 symbols on 2026-05-07 snapshot. Score distribution: [histogram]."
- Validation errors shown inline.
- Soft-delete toggle ("Deprecate") instead of hard delete.

### 6.3 Rule Performance (`/rule-performance`)
- Sortable table: rule_id, name, category, sample_size, hit_rate, false_positive_rate, avg_fwd_5d, avg_fwd_20d.
- Color code: hit_rate > 60% green, 40-60% yellow, < 40% red.
- Click rule → detail page with:
  - Time series of fired/hit counts per week.
  - Symbol list of recent fires with outcomes.
  - Suggested action: "Deprecate" button if hit_rate < 40% with sample_size > 30.

### 6.4 Navigation
Add to `web/index.html` topbar links: existing links + `/cockpit`, `/rules`, `/rule-performance`.

---

## 7. Feedback Loop (closes the system)

```
Action Cockpit "took action" button
        ↓ writes
   user_action_log
        ↓ nightly outcome ETL
   drv_rule_outcome
        ↓ aggregated by view
  v_rule_performance
        ↓ surfaced in
   Rule Performance UI
        ↓ user deprecates bad rules in
    Rules Manager
        ↓ next derive run
  Better Action Cockpit recommendations
```

---

## 8. Implementation Order

Build in this sequence. Each step is independently shippable.

1. **Schema migrations** (Section 2) — single SQL file `db/10_schema_rule_engine_v2.sql`. Run once. Backward compatible.
2. **Backfill metadata** (Section 2.6) — one-time UPDATE script.
3. **Read-only API** (Section 5 read endpoints) — exposes existing data with new fields.
4. **Action Cockpit** (Section 6.1) — read-only first; "took action" button writes to `user_action_log`.
5. **Derive layer changes** (Section 3) — `scoring_mode` branching + traceability JSONB columns.
6. **Rules Manager** (Section 6.2) — CRUD + dry-run.
7. **Outcome ETL** (Section 4) — nightly job.
8. **Rule Performance UI** (Section 6.3) — surfaces feedback loop.

---

## 9. Files to Create / Modify

**Create:**
- `db/10_schema_rule_engine_v2.sql` — all DDL from Section 2.
- `db/11_backfill_metadata.sql` — Section 2.6.
- `etl/compute_outcomes.py` — Section 4.
- `web/cockpit.html` + `cockpit.js` — Section 6.1.
- `web/rules.html` + `rules.js` — Section 6.2.
- `web/rule_performance.html` + `rule_performance.js` — Section 6.3.

**Modify:**
- `etl/derive.py` — extend `eval_atomic_rule()`, persist traceability, honor preconditions.
- `etl/derive_v2.py` — same, in case the v2-rebound functions are the live ones.
- `api/main.py` — new endpoints from Section 5.
- `api/models.py` — Pydantic models for new request/response shapes.
- `web/index.html` — add nav links to three new pages.
- `web/styles.css` — drawer styles for Action Cockpit, modal for Rules Manager.

---

## 10. Open Questions for Implementer

- Should `user_action_log` be per-user (multi-tenant) or single-user? Schema includes optional `user_email`; default to NULL for now.
- Threshold for `hit` (0.5%, 1%) — pick from latest historical volatility per symbol, or keep flat? Start flat, refine later.
- Soft-delete vs hard-delete on rules — design says soft (`deprecated_at`). Confirm.
- Outcome window — 5d / 20d picked arbitrarily. Make these configurable via `ref_settings` table? Probably yes, low cost.

---

## 11. What This Does NOT Do (out of scope)

- Backtest engine on historical decisions (separate project).
- Auto-tuning of weights via ML (separate project).
- Multi-user permissions / auth (single local user assumed).
- Real-time intraday updates (snapshot-based remains).
- Replacing the Excel reference doc workflow (parallel, not replaced).

---

**End of design.**
