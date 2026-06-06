# AGENT_RESULT_05 — probe 697-STM-Earnings-Date (days-based member)
Date run: 2026-06-05

---

## Q1 — atomic rule 107 definition

Note: `condition_operator` column does not exist in `ref_trig_atomic_rule` — excluded.

```
  atomic_rule_id | rule_name | ma_column_name                | brkeout_from | brkeout_to | neg_brkeout_from | neg_brkeout_to | wt_below | wt_between | wt_above
  ------------------------------------------------------------------------------------------
  107            | earnings  | drv_cat_atomic_input.earnings | 5            | 10         | None             | None           | -3       | -2         | 1
```

Interpretation: `earnings_days < 5` → wt_below = **-3**; `5 ≤ earnings_days ≤ 10` → wt_between = **-2**; `earnings_days > 10` → wt_above = **1**.

---

## Q2a — 697 firing for AAPL/AAL/NVDA/CRM/MSFT

```
  tos_symbol | atomic_earnings | db_697_fired | score
  ------------------------------------------------------------------------------------------
  AAL        | 1               | True         | 10
  AAPL       | 1               | True         | 10
  CRM        | 1               | True         | 10
  MSFT       | 1               | True         | 10
  NVDA       | 1               | True         | 10
```

**All five have atomic_earnings = 1 (far from earnings) yet db_697_fired = True.**
This confirms the DB is over-firing 697: the gate condition (`atomic_value <= -3`)
is not suppressing far-earnings stocks.

---

## Q2b — symbols with earnings = -3

```
  tos_symbol | earnings | triggered | score
  ------------------------------------------------------------------------------------------
  ASO        | -3       | True      | 10
  AVO        | -3       | True      | 10
  CASY       | -3       | True      | 10
  CBRL       | -3       | True      | 10
  CHWY       | -3       | True      | 10
  DOCU       | -3       | True      | 10
  ORCL       | -3       | True      | 10
  OXM        | -3       | True      | 10
  SJM        | -3       | True      | 10
  STKL       | -3       | True      | 10
```

These correctly fire (earnings imminent, atomic = -3). Both near and far symbols
fire, which is the bug.

---

## Q3 — categorize the 564 mismatches

Excel column index 409 confirmed as `697-STM-Earnings-Date`.

```
  Bucket A (NULL earn, xl=True  db=False):   0
  Bucket B (earn +1/-2, xl=True db=False):   0
  Bucket C (db=True  xl=False):            564
  Bucket D (other):                          0

  Total mismatches: 564
```

**All 564 mismatches are Bucket C — DB fires, Excel does not.**

Sample Bucket C (5 of 564):
```
  Symbol         earn   raw_days  xl_deficit
  AAL               1         33          10
  AAPL              1         39          10
  ABBV              1         38          10
  ABNB              1         42          10
  ABR               1         39          10
  ... (559 more)
```

`xl_deficit = 10` for all → Excel considers 697 NOT fired (deficit ≥ 10 means
at least one gate unfired). DB fires it anyway. No Bucket A (no NULL-earnings
tradeable symbols in the mismatch set) and no Bucket B (Excel never fires 697
for any stock in the comparison set — consistent deficit = 10 across the board).

---

## Q4 — Excel 697 deficit for AAPL and ASO (earnings=-3)

```
  AAPL: atomic_earn=1   raw_days=39  xl_deficit=10  xl_fired=False  db_fired=True
  ASO:  atomic_earn=-3  raw_days=3   xl_deficit=0   xl_fired=True   db_fired=True
```

- **AAPL** (far, 39 days out): Excel deficit = 10 → NOT fired. DB fires (wrong).
- **ASO** (imminent, 3 days out): Excel deficit = 0 → fired. DB fires (correct).
  ASO does NOT appear in the mismatch list — it is a true match.

---

## Root-cause diagnosis

The gate member for 697 is `atomic_rule_id=107`, `data_brkeout_from=-3`,
`condition_operator=<=`, `weight_override=10`.

**Gate condition**: fires when `atomic_value <= -3`.
- For AAPL: `atomic_value = 1` → `1 <= -3` is **False** → gate should fail → 697 should NOT fire.
- DB fires anyway → the gate is being ignored or the condition logic is inverted/absent.

The 564-mismatch problem is entirely a Python gate-evaluation bug: `_composite_fire`
is either not applying the `condition_operator`/`data_brkeout_from` check for gate
members, or is applying it with the wrong sign. The fix is to ensure the gate member
in `_atomic_member_weight` or `_composite_fire` respects `atomic_value <= data_brkeout_from`
and returns weight=0 (gate fail) when the condition is not met.

DONE
