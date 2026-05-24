# Trig tab extracts — 2026-05-12

Source: `C:\Ashok\Invest\Projects\Cluade\Tickers 2026-04-30.xlsx`

## Files

| File | Rows | Description |
|------|------|-------------|
| `atomic_rules.csv`       | 115 | One row per atomic rule. Columns A-L from Trig rows 4-118 plus the notes/default in col M. |
| `composite_rules.csv`    | 67  | Composite rule codes from Trig row 1 (cols O, Q, S, …). |
| `composite_mapping.csv`  | 502 | (composite_rule_code, atomic_row, weight) — which atomics feed each composite. |
| `ma_headers.csv`         | 641 | MA tab column names (row 1). Used to validate `ma_column_name` references. |

These extracts are the input to the gap analysis between the workbook
(source of truth) and the live database (`ref_trig_atomic_rule` and
`ref_trig_composite_mapping` populated from `baseline.sql`).
