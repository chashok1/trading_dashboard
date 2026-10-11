# TASK_135 — Risk Dial: show the math

> **Queued behind TASK_134.** Do not start until `DEV_HANDOFF.md` records TASK_134 as
> `ALL_DONE`. Both tasks touch `api/routers/cockpit.py` and `web/app.js`.

## Goal

The Risk Dial prints `79 CAUTION — today's size = AMT$ × 0.79` and gives no way to see
how 79 was reached. Every other headline number in this app has a "why" path — the MACRO
cell has its tooltip, Sources has its popover, rules link to Rule Flow. The dial is the
only number that asserts without explaining, and it is the number that changes position
size on every trade.

**Do not change any calculation, threshold, or weight.** This task exposes arithmetic
that already happens. `python -m etl.derive` twice must still produce byte-identical
`drv_market_stat` rows.

---

# PART A — Bug: "no data" is being displayed as "passed"

`api/routers/cockpit.py` splits gauges into two buckets:

```python
fired = [g for g in gauges if g.get("fired") is True]
quiet = [g for g in gauges if g.get("fired") is not True]     # ← line 122
```

But `fired` is **three-valued** in `etl/derive_risk_dial.py`: `True` (fired), `False`
(checked, passed), `None` (could not evaluate — source data missing). The scoring loop
handles this correctly:

```python
if g.get("fired") is None:
    continue                    # excluded from BOTH numerator and denominator
```

The UI does not. A `None` gauge lands in `quiet` and reads as "checked, fine."

**Why this matters.** `evaluable_weight` shrinks when a gauge can't be evaluated, so the
score is computed against a smaller denominator. `79` out of 14 evaluable gauges and
`79` out of 9 evaluable gauges are very different statements about how much is actually
known — and right now they are indistinguishable on screen. A dial quietly running on
half its inputs during a data outage is the worst failure mode this screen has, because
it looks exactly like a calm day.

**Fix — three buckets, not two:**

```python
fired    = [g for g in gauges if g.get("fired") is True]
clear    = [g for g in gauges if g.get("fired") is False]
no_data  = [g for g in gauges if g.get("fired") is None]
```

Return all three. Keep `quiet` as an alias for `clear` for one release if anything else
consumes it, but the UI must use the new fields.

**UI:** when `no_data` is non-empty, Band 1 shows an amber line directly under the meter:

```
⚠ 3 of 14 gauges could not be evaluated — score is out of 22, not 29. [details]
```

Use `--warn` from `:root`. This is not hidden behind the popover; a degraded score must
be visible without a click.

---

# PART B — Show the arithmetic inline

`evaluable_weight` and `fired_weight` are already in the API response and are **never
rendered**. Put the formula on screen, next to the number:

```
  79   CAUTION                              today's size = AMT$ × 0.79
  ███████████████████████░░░░░░
  6 of 29 gauge-points fired  ·  3 of 14 gauges  ·  how this is calculated ▾
```

- 12px, `--text-3`, directly under the meter.
- `6 of 29 gauge-points` = `fired_weight` / `evaluable_weight`.
- `3 of 14 gauges` = counts, so weight and count are not confused with each other.
- `how this is calculated` opens Part C.

---

# PART C — The full breakdown panel

Clicking the number, the label, or "how this is calculated" opens a panel showing every
gauge. Match the app's existing popover behaviour (`_showDataPop` in `web/actionable.js`)
— but note `web/app.js` has **no popover helper today**. Either extract a shared one into
`web/_common.js` and have both screens use it, or build a self-contained inline expander
in `app.js`. **Prefer extracting the shared helper**; if that proves invasive, use the
inline expander and say why in `DEV_HANDOFF.md`.

## C.1 Panel contents, in order

**1 — The formula, with this date's numbers substituted:**

```
risk_budget = round( 100 × (1 − fired_weight / evaluable_weight) )
            = round( 100 × (1 − 6 / 29) )
            = 79   →   CAUTION
```

**2 — All 14 gauges in one table, fired first, then clear, then no-data.** Within each
group sort by weight descending.

| Gauge | Wt | State | Reading | Fires when |
|---|---|---|---|---|
| SPX at top of risk range | 3 | ● FIRED | 91% of range (LRR 6180 / TRR 6435) | rr_pos ≥ 0.85 |
| Credit stress | 3 | ○ clear | HYG 47% of range; HY OAS +4bp/10d | rr_pos ≤ 0.15 or OAS +25bp/10d |
| Dealer gamma negative | 2 | — no data | `gamma_throttle` unparsed | MSR reports negative |

- **State** uses icon + word, never colour alone.
- **Reading** is the gauge's own `detail` string.
- **Fires when** is the threshold in plain terms — add a `trigger_text` column to
  `ref_risk_gauge` and seed it, one short phrase per gauge. Reading a number without
  its threshold beside it is exactly the gap this task exists to close.
- Rows carry the Part A severity rail from TASK_134 so weight is visible at a glance.

**3 — Band boundaries, with today marked:**

```
NOT INVESTABLE │ DEFENSIVE │  CAUTION  │ CLEAR
0            29│30       54│55       79│80      100
                                     ▲ 79
```

Shows how close today sits to a boundary. 79 is one point from CLEAR; that is worth
knowing and is invisible now.

**4 — Provenance footer:** `as_of` date, and for each fired gauge the table its value
came from (`drv_rr`, `ref_vol_threshold`, `hist_macro`, `hist_msr`, `drv_market_stat`).
When a number looks wrong, this is where the user starts.

## C.2 Where the data comes from

`drv_market_stat.gauges_fired` JSONB already carries `key`, `label`, `fired`, `weight`,
`value`, `detail` for all 14. Only `trigger_text` is new (from `ref_risk_gauge`, joined
in the endpoint). **No new derive, no new computation** — join and render.

---

# PART D — Docs

- `docs/dashboard_cockpit_design.md` — new "§3.6 Explaining the score" subsection: the
  three states, the inline formula line, the panel contents. State plainly that a `None`
  gauge changes the denominator.
- `CLAUDE.md` Lookup index — one row: *Risk-dial gauge definitions + thresholds →
  `etl/derive_risk_dial.py::GAUGES`, `ref_risk_gauge` (weight, `trigger_text`)*.

---

## Done when

- `/api/cockpit/risk-dial` returns `fired`, `clear` and `no_data` as three separate
  arrays, and their lengths sum to the active row count in `ref_risk_gauge`.
- Band 1 shows the inline `X of Y gauge-points` line, and the amber reduced-denominator
  warning whenever `no_data` is non-empty.
- The breakdown panel opens and lists all gauges with weight, state, reading and
  `trigger_text`.
- `python -m etl.derive` twice for the anchor date leaves `drv_market_stat` unchanged
  apart from `derived_at` — the guard that nothing here moved a number.

**No test files.** Do not write or extend anything under `tests/`. Standing user
instruction: tests only when explicitly requested.

## Files expected to change

`api/routers/cockpit.py`, `web/app.js`, `web/styles.css`, `db/baseline.sql`
(`ref_risk_gauge.trigger_text`), `db/seeds_cockpit.sql`,
`docs/dashboard_cockpit_design.md`, `CLAUDE.md`. Possibly `web/_common.js` if the
popover helper is extracted.

**Not touched:** `etl/derive_risk_dial.py` scoring logic, any weight, any threshold,
`web/actionable.js`, `web/actionable.html`, anything under `tests/`.

## Standing rules

- **No questions.** Where silent, match existing app conventions; note it in `DEV_HANDOFF.md`.
- **No tests.** Do not write, extend, or run test files. Do not hand off to the tester
  agent. This overrides repo convention #18 for this task — the user asks for tests
  explicitly when they want them.
- **No commits, no pushes.** The user commits from Windows.
- **No calculation changes.** If an edit would move a number, it is out of scope.
- Verify large edits (`node --check`, `ast.parse`) — truncation is silent. This is a
  file-integrity check, not testing, and still applies.
- Append a `# Dev Handoff — TASK_135` section; end `ALL_DONE`.
