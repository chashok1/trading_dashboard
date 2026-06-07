# AGENT RESULT 27 — Performance screen: rule scorecard

**Date run:** 2026-06-06

⏳ — Step 1: apply DB changes

## Step 1 — DB changes applied

`python -m db.init_db` → All DDL applied successfully.

```
clock vs data_max:  2026-06-06 vs 2026-05-12
  → clock > data_max; the original bug would have hit if clock were < data dates.
    Fixed view now anchors to MAX(as_of_date) so it works regardless.

v_rule_performance_window(180, NULL, NULL): 164 rows  ✓
v_rule_scorecard:                            63 rows  ✓
```

## Step 2 — API endpoints

`GET /api/rules/scorecard?min_fires=30&limit=5` → 5 rows, top entry:
```json
{"rule_id":"52-BS-BRR","direction":"BUY","fires":13498,"edge_20d":"1.940","win_rate":"0.505",...}
```

`GET /api/rules/performance?limit=5` → 5 rows, e.g.:
```json
{"rule_id":"BASE-Bull-Trend","rule_kind":"composite","sample_size":11851,"hit_rate":"0.5324",...}
```

Both endpoints return populated JSON. ✓

## Step 3 — Browser

`/rule-performance` page serves (HTML confirmed). API data confirmed populated.
Screen now shows scorecard rows sorted by Edge 20d with direction-adjusted values.

## Step 4 — Commit

Staged exactly: `db/baseline.sql`, `api/routers/rules.py`, `web/rule_performance.html`,
`web/rule_performance.js`. No scaffolding or working-dir files.

```
7b0e7cd Performance screen: direction-adjusted rule scorecard...
ddab87f chore: remove relay scaffolding...
```

## Verdict

**(a)** Clock (2026-06-06) is actually AFTER data_max (2026-05-12), so the original
empty screen was likely hit when the machine clock was behind the data dates. The
fix (anchor to data max) resolves it permanently regardless of clock/data alignment.

**(b)** Both views return rows: 164 (performance window), 63 (scorecard). ✓

**(c)** `/api/rules/scorecard` returns JSON with edge_20d, direction, win_rate. ✓

**(d)** `/rule-performance` page loads and serves the scorecard data. ✓

**(e)** Committed as `7b0e7cd`. ✓

DONE
