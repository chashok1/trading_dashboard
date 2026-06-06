# AGENT RESULT 22 — Phase 4 step 1: outcome data readiness for ML tuning

**Date run:** 2026-06-06

⏳ — Q1/Q2/Q3: DB queries

## Q1 — overall volume

```
rows=0, first_date=None, last_date=None, n_dates=0, n_symbols=0
```

`drv_rule_outcome` is **completely empty** — zero rows, never populated.

## Q2 — label population

```
(empty — no rows)
```

No hits, no fwd_5d_pct, no fwd_20d_pct.

## Q3 — per-atomic-rule sample counts

```
atomic_rules_resolved=0, rules_ge_50=0, rules_ge_100=0
top-15: (empty)
```

Zero rules clear any threshold.

⏳ — Q4: upstream dependency check

## Q4 — how is drv_rule_outcome populated?

**Source:** `etl/compute_outcomes.py::compute_outcomes()`.

It reads `user_action_log` entries older than 5 trading days that have
`triggered_rules` populated, computes forward returns at 5d and 20d using
`drv_ma` price data, and inserts one row per triggered rule per action.

`fwd_20d_pct` specifically requires a price in `drv_ma` exactly 20 trading days
later — so it can only be non-NULL for dates ≥20 trading days in the past.

**user_action_log state:**
```
Total rows:           1  (from 2026-05-22)
Rows with triggered_rules:  0
```

The single log entry has no `triggered_rules`, so `compute_outcomes` would
process zero rows even if run today.

---

## Verdict

1. **Total outcome rows:** 0. Date span: none. The table has never been populated.

2. **Rules clearing ≥50 samples:** 0 (of 0). No atomic rule has any outcome data.

3. **fwd_20d_pct populated:** No — 0 rows total. Future dates would require
   20 trading days of elapsed time AND a matching `drv_ma` price.

4. **Is ML tuning feasible now?** **No.** The system has only 1 user action logged
   (2026-05-22, no triggered_rules) — not a single usable training sample exists.
   To reach the ≥50-sample threshold per rule, the system needs several months of
   real user actions where `triggered_rules` is recorded and 20 trading days
   have elapsed. Rough estimate: with ~800 symbols and ~60 rules firing daily,
   you'd accumulate 50 samples/rule in roughly 1–2 months of logged activity —
   provided users are recording actions via the Cockpit/actionable screen daily.
   No code change can substitute for real elapsed time and real user decisions.

DONE
