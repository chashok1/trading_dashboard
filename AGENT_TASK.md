# AGENT TASK 23 — Phase 4: how much history do we have? (read-only)

**You (VS Code agent) have DB access.** READ-ONLY — change nothing. Write to
**`AGENT_RESULT_23.md`**. Heartbeat: append `⏳ HH:MM:SS — <step>` lines as you go.

Goal: size the firing-based outcome approach. Plan is to validate each rule firing
against the stock's forward return. That needs: (a) rule firings across many past
dates (drv_trig/drv_stks), (b) price history to compute forward returns (drv_ma),
(c) enough dates ≥20 trading days old. We mostly have derives for 6/4–6/5 today;
this measures how far back we can backfill and how many samples that yields.

## Q1 — raw price-history depth (drives backfill range)
```sql
SELECT 'hist_td' t, MIN(export_date) lo, MAX(export_date) hi,
       COUNT(DISTINCT export_date) n_dates FROM hist_td
UNION ALL
SELECT 'hist_tl', MIN(export_date), MAX(export_date), COUNT(DISTINCT export_date) FROM hist_tl
UNION ALL
SELECT 'hist_tw', MIN(snapshot_date), MAX(snapshot_date), COUNT(DISTINCT snapshot_date) FROM hist_tw;
```

## Q2 — price source for forward returns (drv_ma)
`compute_outcomes` reads forward prices from `drv_ma.last_price` by date. Check it:
```sql
SELECT MIN(as_of_date) lo, MAX(as_of_date) hi, COUNT(DISTINCT as_of_date) n_dates
FROM drv_ma;
```
(If drv_ma is a view over the component tables, this still reflects available dates.)

## Q3 — existing derive coverage (where firings already exist)
```sql
SELECT 'drv_cat_atomic_input' t, MIN(as_of_date) lo, MAX(as_of_date) hi, COUNT(DISTINCT as_of_date) n FROM drv_cat_atomic_input
UNION ALL SELECT 'drv_trig', MIN(as_of_date), MAX(as_of_date), COUNT(DISTINCT as_of_date) FROM drv_trig
UNION ALL SELECT 'drv_stks', MIN(as_of_date), MAX(as_of_date), COUNT(DISTINCT as_of_date) FROM drv_stks;
```

## Q4 — sample-size estimate
1. Firings per date (composite level), on the dates we DO have:
```sql
SELECT as_of_date, COUNT(*) FILTER (WHERE triggered) AS fires
FROM drv_trig GROUP BY as_of_date ORDER BY as_of_date;
```
2. Trading dates that are ≥20 trading days old AND have price data (eligible for a
   20d forward label). Approximate from hist_td:
```sql
SELECT COUNT(*) AS dates_20d_eligible FROM (
  SELECT DISTINCT export_date FROM hist_td
  WHERE export_date <= (SELECT MAX(export_date) FROM hist_td) - INTERVAL '28 days'
) x;
```

## Q5 — can we backfill derives across history?
Backfilling firings for a past date D needs hist_td/tl/tw (+ periodic feeds) loaded
for/around D. Based on Q1, state: roughly how many past trading dates have the
source data needed to run `derive_all(D)`? Is the price history weeks, months, or
just the last few days?

## Verdict
State plainly:
1. Price history span (dates, from–to).
2. Derive coverage now (how many dates have firings).
3. Rough usable training-date count (≥20d old with data) and estimated total
   firing samples if we backfilled (dates × avg fires/date).
4. Your read: is there enough history to make the firing-based approach worthwhile
   now, or is the loaded history too shallow (just a few days)?

Write `DONE` at the bottom of `AGENT_RESULT_23.md`.
