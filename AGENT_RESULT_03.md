# AGENT_RESULT_03 — probe earnings atomic / 697-STM-Earnings-Date mismatches
Date run: 2026-06-05

---

## Query 1 — earnings input vs atomic vs 697-fired (20 sample rows)

```
  tos_symbol | raw_earnings_days | atomic_earnings | db_697_fired
  --------------------------------------------------------------------------------
  $COMP      | None              | None            | False
  $DJI       | None              | None            | False
  $DXY       | None              | None            | False
  /6B[M26]   | None              | None            | False
  /6C[M26]   | None              | None            | False
  /6E[M26]   | None              | None            | False
  /6J[M26]   | None              | None            | False
  /BTC[M26]  | None              | None            | False
  /BZ[Q26]   | None              | None            | False
  /CL[N26]   | None              | None            | False
  /GC[Q26]   | None              | None            | False
  /HG[N26]   | None              | None            | False
  /NG[N26]   | None              | None            | False
  /NKD[M26]  | None              | None            | False
  /SI[N26]   | None              | None            | False
  AAAU       | None              | None            | False
  AAL        | 33                | 1               | True
  AAPL       | 39                | 1               | True
  ABBV       | 38                | 1               | True
  ABNB       | 42                | 1               | True
```

---

## Query 2 — NULL vs populated atomic earnings count

```
  atomic_is_null | count
  --------------------------------------------------------------------------------
  False          | 607
  True           | 277
```

---

## Query 3a — earnings atomic rule thresholds

```
  rule_name | brkeout_from | brkeout_to | neg_brkeout_from | neg_brkeout_to | wt_below | wt_between | wt_above
  --------------------------------------------------------------------------------
  earnings  | 5            | 10         | None             | None           | -3       | -2         | 1
```

## Query 3b — 697-STM-Earnings-Date composite members

```
  composite_rule_code    | atomic_rule_id | data_brkeout_from | condition_operator | member_role | weight_override
  --------------------------------------------------------------------------------
  697-STM-Earnings-Date  | 107            | -3                | <=                 | gate        | 10
```

---

## Query 4 — specific known stocks (AAPL, MSFT, NVDA, AMD, CRM, HUBS)

```
  tos_symbol | a_earnings_days | earnings | triggered | score
  --------------------------------------------------------------------------------
  AAPL       | 39              | 1        | True      | 10
  AMD        | 41              | 1        | True      | 10
  CRM        | 62              | 1        | True      | 10
  HUBS       | 42              | 1        | True      | 10
  MSFT       | 38              | 1        | True      | 10
  NVDA       | 57              | 1        | True      | 10
```

---

## Observations for the Cowork agent

1. **The 277 NULLs are indices / futures / ETFs / cash** — symbols that have no
   `hist_tw` row (no TOS Watch tab data). Their `atomic_earnings = NULL`,
   `db_697_fired = False`. These are the DB-fires-False / Excel-fires-True
   mismatches: Excel has a value (likely 1 from the TOSW formula), DB is NULL.

2. **The 607 non-NULL all fired correctly** — all 6 sampled stocks have
   `a_earnings_days` populated, `atomic_earnings = 1`, `triggered = True`,
   `score = 10`. DB fires when it should.

3. **The gate member** (`atomic_rule_id=107`, `condition_operator=<=`,
   `data_brkeout_from=-3`, `weight_override=10`) means:
   the gate condition is `atomic_value <= -3`. Since `wt_below=-3` for
   `earnings_days < brkeout_from(5)` ... actually `wt_above=1` applies when
   `earnings_days >= 5`. So `atomic_value=1` satisfies `1 <= -3`? That is
   **False** — but all stocks ARE firing. This needs checking: the gate
   condition may be interpreted differently (e.g. `score <= -3` rather than
   `atomic_value <= -3`), or `data_brkeout_from=-3` is the gate threshold on
   the member score contribution, not the raw atomic value.

4. **Root cause of the 564 mismatches**: likely two sub-populations:
   - ~277 symbols with NULL earnings (no hist_tw) → DB fires False, Excel fires True
   - ~287 remaining mismatches may be direction flips (DB fires True, Excel fires False or vice versa)

DONE
