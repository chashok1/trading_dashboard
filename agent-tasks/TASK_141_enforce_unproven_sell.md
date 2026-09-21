# TASK_141 — Stop unproven SELL rules winning the row (enforce, don't annotate)

## Context

`docs/audit/loss_diagnosis_2026-07.md` §B: **every** SELL-direction rule with
`fires >= 20` — 30 of 30 — has *negative* direction-adjusted 20d edge. Price
tends to recover after these fire. All 34 BUY rules are positive. §E.2 found
that *ignoring* REDUCE/REMOVE beat following it (+2.01% vs −1.40% fwd-20d).

TASK_118 Part A responded with `drv_actionable.low_confidence` — and
`db/baseline.sql` says so explicitly: *"Annotation only — consolidated_action
is never changed by this flag."* Read `derive_actionable.py` around the
`group_candidates` / `_order()` block: an unproven-sell rule group still enters
`candidates`, still wins the slot, still sets the headline. It just renders
with a sub-label.

Separately, `v_final_call_scorecard` (2026-07) found the **confidence badge is
inverted on the sell side**:

| badge | edge_20d | win rate | n |
|---|---|---|---|
| `SS` / **high** | **−5.03** (wrong direction) | 37.3% | 59 |
| `SS` / **mixed** | +0.73 (correct) | 53.4% | 58 |

The most confident sell badge is the least reliable signal on the screen.

**Prerequisite: TASK_139 must confirm the SELL-side finding still holds**
(its step 5, question 3) — the July window contained no sustained downtrend, so
a genuine drawdown in the new data could rehabilitate these rules. If TASK_139
marks it FLIPPED, stop and re-scope.

## Goal

An unproven sell rule can no longer be the *sole* reason a row says sell, and
the sell-side confidence badge stops asserting confidence it has not earned.

### Part A — enforcement in the winner contest

In `etl/derive_actionable.py`, the existing `low_confidence` computation
already identifies exactly the right rows: `has_unproven_sell and not
has_proven_sell and not source_driven_sell`. Reuse it — do not write a second
classifier.

- Add **`ref_settings.unproven_sell_mode`**, seeded `'annotate'`
  (= today's behaviour, unchanged). New value: `'suppress'`.
- Under `'suppress'`: when that same condition is true, the group candidates
  backing it are **excluded from `candidates`** before the sort — they cannot
  win `consolidated_action`. Everything else about the row is preserved:
  - the original action and its rule ids stay in `source_actions` /
    `triggered_group_ids` so the drilldown still shows what the system would
    have said;
  - `suppressed_reason = 'UNPROVEN SELL'`, following the existing suppression
    pattern (`NOT HELD`, `AT CEILING`, `STOP BREACHED`);
  - `low_confidence` still set, so nothing downstream regresses.
- **Scope strictly to the sell side.** BUY rules, thresholds, `ref_trig_*` and
  the atomic engine are untouched. A sell backed by a *proven* rule, or by any
  source `REMOVE`/`REDUCE`, is untouched — this only removes the case where
  the **only** evidence is a rule measured to be wrong.
- If excluding those candidates leaves no candidate at all, the row resolves to
  `HOLD` through the existing no-winner path. Do not synthesize an action.

### Part B — sell-side confidence badge

In `_compute_final_call` (and its JS mirror `finalCall()` in
`web/actionable.js` — both, or the two drift, see `bull_calc_analysis.md` D6):

- A sell-side call that would return `fc_confidence = 'high'` **and** whose
  supporting evidence is flagged `low_confidence` must not render `high`.
  Return `'mixed'` instead.
- Do **not** silently invert or re-letter the badge. Behaviour stays gated by
  `unproven_sell_mode`: `'annotate'` = today's badge, `'suppress'` = the
  downgrade above.
- Buy-side confidence is untouched.

### Part C — measure it

Add `drv_actionable.unproven_sell_suppressed BOOLEAN NOT NULL DEFAULT FALSE`,
set when Part A actually removed a candidate. Without it there is no way to
score afterwards whether suppression helped — and scoring it is the point.

### Part D — UI

- Rows where `unproven_sell_suppressed` is true show the existing suppression
  treatment with reason "UNPROVEN SELL"; the drilldown shows the suppressed
  action and the rule ids that produced it.
- Legend ("?" panel): one line explaining it.

## Files expected to change

- `db/baseline.sql` (two columns + `ref_settings` seed)
- `etl/derive_actionable.py`
- `api/routers/dash.py`, `web/actionable.js`
- `docs/migrations.md`, `docs/actionable_logic.md`,
  `docs/actionable_playbook.md` (§5 A3 row, §3.3 "distrust SS/high")
- `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db` idempotent.
2. **Mode `'annotate'` (default): re-derive the anchor and diff
   `consolidated_action` + `final_code` + `fc_confidence` per symbol against
   the pre-change run — byte-identical, zero rows changed.**
3. `SELECT COUNT(*) FROM v_unproven_sell_rules;` is non-zero (else the whole
   task is a no-op and that itself is the finding — report it).
4. Set `unproven_sell_mode = 'suppress'`, re-derive, then report:
   - `SELECT COUNT(*) FROM drv_actionable WHERE as_of_date=D AND
     unproven_sell_suppressed;`
   - the list of symbols whose action changed, with before → after.
   Hand that to the user; **revert to `'annotate'` before `ALL_DONE`.**
5. Confirm a row with a source-driven `REMOVE` **plus** an unproven sell rule
   is *not* suppressed under either mode.
6. Confirm a row with a *proven* sell rule is not suppressed under either mode.
7. Confirm no BUY-side row changes action or confidence under either mode.
8. Part B: find a row that renders `SS`/`high` with `low_confidence` true under
   `'annotate'`; under `'suppress'` it renders `SS`/`mixed`. Server and JS
   agree (check the payload against the rendered badge).
