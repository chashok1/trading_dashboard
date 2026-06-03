# Rule Flow Screen Logic

Diagnostic trace screen (`/rule-flow`) that re-evaluates all rule engine tiers live for a single symbol and date, showing exactly how the final Trig Action is derived.

---

## Data Flow

```
hist_* tables
    down  (ETL loads raw source data)
drv_cat_atomic_input          <- pre-computed indicator weights per (symbol, date)
    down
    [Atomic Rules - live]
    ref_trig_atomic_rule: column -> value -> weight
    down
    [Composite Rules - live]
    ref_trig_composite_mapping: condition_operator + threshold per member
    ALL members must meet condition for composite to fire
    down
    [Rule Groups - live]
    ref_trig_rule_group + ref_trig_group_member: AND/OR over composite fires
    down
Final Output
    Trig Action          <- derived live from fired groups + buysell scores
    Consolidated Action  <- read from drv_actionable (outlook pipeline, stored)
```

---

## Sections and Data Sources

| Section | Source | Live? | Default |
|---|---|---|---|
| Atomic Rules | `drv_cat_atomic_input` + `ref_trig_atomic_rule` | Yes | Collapsed |
| Composite Rules | atomic weights + `ref_trig_composite_mapping` | Yes | **Open, Fired only** |
| Rule Groups | composite fires + `ref_trig_rule_group/member` | Yes | Collapsed |
| Final Output - Trig Action | rule groups + `ref_param_lookup` buysell | Yes | **Open** |
| Final Output - Consolidated Action | `drv_actionable` | No (stored) | **Open** |
| Raw Source Data | `hist_td/tw/to/tl/y` + drv tables | No (stored) | Collapsed |

---

## Atomic Rules Panel

Cards arranged in a 5-column grid. Each card: `column_name (value)  weight  down-arrow`

- **Value** - pre-threshold input: for Threshold rules, the last intermediate in the `_CHAIN` map (e.g. `AR=5` for BBLowDays); for Direct rules, the `drv_cat_atomic_input` column value (equals weight).
- **Weight** - the `drv_cat_atomic_input` score (set by ETL).
- **T/D badge** - `T` = Threshold (has zone + wt_below/between/above), `D` = Direct.
- **arrow** - expands inline within the card to show the Data Flow chain.

### Data Flow Panel

Loaded eagerly on symbol load via `GET /api/rule-flow/{sym}/intermediates`.

`_CHAIN` in `web/rule_flow.js` maps each `drv_cat_atomic_input` column to its ordered intermediate keys. `_KEY_LABEL` provides human-readable names; `_KEY_FORMULA` provides formula strings shown as dotted-underline tooltips. Keys are tagged `source` (from hist tables) or `computed` (derived intermediates). For crossover columns, clause-by-clause formula evaluation is shown.

Clicking an atomic member row in Composite Rules opens the same panel (shared `_intermediatesCache`).

---

## Composite Rules Panel

Each composite shows members with:

| Field | Meaning |
|---|---|
| role badge | `GATE` (mandatory) or `WATCH` (corroborating evidence) — `member_role` |
| check/x | Condition met |
| val | Atomic weight from `drv_cat_atomic_input` |
| cond | `operator threshold` e.g. `>= 2` |
| weight | Assigned weight (`weight_override` if set, else val) |

**Firing rule (gate / WATCH, 2026-06-03):** a composite fires when **all GATE
members hit AND the WATCH evidence clears `evidence_cutoff`** (NULL cutoff = WATCH
never blocks; WATCH members are informational). A composite with no gates falls
back to strict all-members-hit unless a cutoff is set. The header shows the
breakdown: `gates G_hit/G_total · watch W_hit/W_total (need ≥cutoff)` plus a
verdict (`✓ FIRED`, `gate failed`, or `watch short`). This mirrors
`etl/derive.py` exactly. See `docs/rule_engine_redesign.md`.

> Note: before this change the trace endpoint fired composites on `score > 0`
> (any member), which diverged from the derive layer's all-members rule. The
> endpoint now applies the same gate/WATCH logic as the live derive cascade.

**Condition operator precedence** (first wins):
1. `ref_trig_composite_mapping.condition_operator` - explicit: `>=` `<=` `>` `<` `=`
2. Rule-code prefix - BUY (`B`, `BS`, `BR`, `BW`, `BM`, `BMN`) -> `>=`; SELL (`SA`, `SS`, `STM`, `SW`, `SH`) -> `<=`
3. Threshold sign fallback - positive -> `>=`, negative -> `<=`

**Active flag:** `active = FALSE` disables a composite (skipped in evaluation). Toggle via `PUT /api/rules/composite/{id}/active`.

---

## Rule Groups Panel

Boolean AND/OR expression over composite codes. A group fires when its expression evaluates True. Fired action groups carry an `action_label` and `priority` that feed Final Output.

---

## Final Output - Trig Action

Computed live from the Rule Groups evaluation:

1. Collect all fired action groups.
2. Look up each group's `action_label` in `ref_param_lookup` (table=`buysell`) for a numeric score.
3. **If any score is negative** (bearish) -> pick minimum score (most bearish wins).
   **Otherwise** -> pick maximum score (most bullish wins).
4. Result = `trig_action` shown in Final Output.

Consolidated Action is read from `drv_actionable` (last ETL run). It may differ from live Trig Action when rules changed since last derive.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/rule-flow/{sym}?date=YYYY-MM-DD` | Full live trace - atomics, composites, groups, final, raw panels |
| `GET /api/rule-flow/{sym}/intermediates?date=YYYY-MM-DD` | Intermediate computed values for Data Flow panel |

Both default to the latest `drv_stks` date when `date` is omitted.

---

## Key Files

| File | Role |
|---|---|
| `api/routers/trace.py::get_rule_flow` | Live evaluation endpoint |
| `api/routers/trace.py::get_rule_flow_intermediates` | Intermediates endpoint |
| `etl/derive_cat_atomic_input.py::get_symbol_intermediates` | Computes intermediates |
| `etl/derive.py::_composite_operator` | Operator fallback (BUY/SELL prefix) |
| `web/rule_flow.js` | All rendering: `_CHAIN`, `_KEY_LABEL`, `_KEY_FORMULA`, card grid, composite members, data flow panel |
| `web/rule_flow.html` | HTML shell + CSS |
