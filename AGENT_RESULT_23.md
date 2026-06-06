# AGENT RESULT 23 — Phase 4: history depth for firing-based ML approach

**Date run:** 2026-06-06

⏳ — running Q1–Q4

## Q1 — raw price-history depth

| Source  | From       | To         | Dates |
|---------|------------|------------|-------|
| hist_td | 2026-02-02 | 2026-06-05 | 79    |
| hist_tl | 2026-01-30 | 2026-06-05 | 80    |
| hist_tw | 2026-01-30 | 2026-06-05 | 78    |

~4 months of raw TOSD/TOSL/TOSW data loaded. This is the derive backfill ceiling.

## Q2 — drv_ma price range (needed for forward returns)

```
lo=2026-05-06  hi=2026-06-05  n_dates=25
```

Only ~1 month of derived prices. Derives have only been run for the last 25 dates.
To compute fwd_20d_pct for earlier dates, backfill derives are needed — they will
populate drv_ma for those earlier dates too.

## Q3 — existing derive coverage (firings on disk)

| Table                | From       | To         | Dates |
|----------------------|------------|------------|-------|
| drv_cat_atomic_input | 2025-01-01 | 2026-06-05 | 26    |
| drv_stks             | 2025-01-01 | 2026-06-05 | 26    |
| drv_trig             | 2025-01-01 | 2026-06-05 | 26    |

26 dates: one stub (2025-01-01, likely a test/seed derive) + 25 real dates
2026-05-06 to 2026-06-05.

## Q4a — firings per date

| Date range          | Fires/date     | Notes                              |
|---------------------|----------------|------------------------------------|
| 2025-01-01          | 10,647         | stub/seed date — not a real day    |
| 2026-05-06 to 06-03 | ~56,000–56,600 | 23 full-universe dates             |
| 2026-05-25          | 33,297         | Memorial Day (partial universe)    |
| 2026-05-30, 05-31   | 33,754         | weekend derives (small universe)   |
| 2026-06-04, 06-05   | 1,974 / 2,856  | new-format dates (partial — Phase 2 rebuild in progress?) |

Stable full-universe average: **~56,500 composite firings/date**.

## Q4b — dates ≥20 trading days old (eligible for 20d label)

```
dates_20d_eligible = 60
```

60 hist_td dates are ≥28 calendar days before the max date. However, fwd_20d_pct
requires a drv_ma price ~20 trading days later — currently drv_ma only covers
2026-05-06 onward. Once backfill derives are run, these 60 dates would have both
the firing data AND the forward price available.

⏳ — Q5 + Verdict

## Q5 — backfill feasibility

hist_td/tl/tw cover 2026-02-02 to 2026-06-05 (79 dates). `derive_all(D)` needs
hist_td/tl/tw for date D plus periodic feeds (carry-forward ≤D). The periodic feeds
are already loaded through 2026-06-05.

**Dates that can be backfilled:** all 79 hist_td dates — roughly 54 additional
dates from 2026-02-02 to 2026-05-05. `File Monitor → Force Re-derive` (or a loop
over `agent_rederive_all.py` per date) would populate drv_cat_atomic_input,
drv_trig, drv_stks, AND drv_ma for those dates.

After a full backfill, the firing-based dataset would look like:

| Metric | Now (25 dates) | After backfill (79 dates) |
|--------|----------------|---------------------------|
| Firing dates usable | 25 | 79 |
| Dates with ≥20d fwd price | ~5 | ~59 |
| Total firing samples | ~1.4M | ~3.3M |
| Samples per composite rule (avg) | ~350 | ~2,400 |
| Samples per atomic rule (est.) | varies | varies |

With ~59 eligible dates × ~56k fires/date = **~3.3M firing samples** available
after backfill. At 64 composite codes and ~884 symbols, average per-rule coverage
is ~2,400 samples — well above the ≥50 threshold.

---

## Verdict

1. **Price history span:** hist_td 2026-02-02 → 2026-06-05, 79 trading dates (~4 months).
   drv_ma currently only covers 2026-05-06 → 2026-06-05 (25 dates).

2. **Derive coverage now:** 25 real dates (2026-05-06 → 2026-06-05) + 1 stub. Firings
   exist for those 25 dates only (~1.4M composite firing records).

3. **Usable training dates after backfill:** ~59 dates ≥20 trading days old, yielding
   ~3.3M firing samples. Every composite rule would have thousands of samples.

4. **Is the firing-based approach worthwhile?** **Yes, after a backfill.**
   The history is only 4 months — shallow but enough for a first-pass validation.
   Key next step: run `derive_all` for the 54 missing dates (2026-02-02 to 2026-05-05)
   via File Monitor Force Re-derive or a batch script looping over those dates.
   Once backfilled, the tuner can be pointed at drv_trig/drv_ma directly (bypassing
   user_action_log entirely) and will have 2,000+ samples per rule to work with.

DONE
