# AGENT RESULT 32 — Macro fetch throttle + manual refresh: apply, verify, commit

## Step 1 — Schema + seed

```
meta_macro_fetch: meta_macro_fetch        ← to_regclass not null ✓
macro_fetch_min_interval_min: 360         ← ref_settings seeded ✓
meta_macro_fetch rows (baseline): 0
```

## Step 2 — Throttle verification

**(a) `python -m etl.fetch_macro --force`** — hit FRED, 20 series, 2400 rows inserted:
```
2026-06-07 01:07:11 [INFO] fetch_macro: macro fetch complete: 20 series, 2400 obs fetched, 2400 new rows
meta_macro_fetch rows after: 1  ← +1 row, status ok ✓
```

**(b) `python -m etl.fetch_macro`** — immediately throttled, NO new row:
```
2026-06-07 01:07:31 [INFO] fetch_macro: throttled: last fetch 0 min ago (< 360 min); use --force to override.
meta_macro_fetch rows: 1  ← unchanged ✓
```

**(c) `python -m etl.fetch_macro --min-interval 0`** — override proves tunability, +1 row:
```
2026-06-07 01:07:55 [INFO] fetch_macro: macro fetch complete: 20 series, 2400 obs fetched, 2400 new rows
meta_macro_fetch rows after: 2  ← +1 row ✓
```

## Step 3 — Endpoints

**GET /api/macro** `last_fetch` block:
```json
{
  "started_at": "2026-06-07T01:07:49.329657",
  "finished_at": "2026-06-07T01:07:55.690678",
  "status": "ok",
  "rows_inserted": 2400,
  "series_ok": 20,
  "series_failed": 0,
  "note": null
}
```

**POST /api/macro/refresh** (ran moments after step 2 — throttled as expected):
```json
{
  "skipped": true,
  "series": 0,
  "fetched": 0,
  "inserted": 0,
  "failed": [],
  "reason": "throttled",
  "age_min": 1,
  "min_interval_min": 360
}
```

## Step 4 — Compile + commit

```
py_compile etl/fetch_macro.py api/routers/macro.py → OK_compile ✓
```

## Verdict

(a) `meta_macro_fetch` exists + setting seeded ✓  
(b) throttle proven: forced run logs, immediate plain run is a no-op, `--min-interval 0` overrides ✓  
(c) GET returns `last_fetch`, POST `/refresh` respects throttle ✓  
(d) committed ✓

DONE
