# TASK_134 — Cockpit visual system + follow-ups from TASK_133

## Goal

TASK_133 shipped correct data and a correct layout. The screen **reads flat** because
Band 1 hardcoded its own colours instead of using this app's design tokens, and because
severity is not encoded anywhere. Fix the visual system, fix two content bugs, and close
three follow-ups TASK_133 deliberately deferred.

**Do not change any calculation, threshold, endpoint shape, or derive logic.** This is
presentation plus two string fixes plus one warning banner. If a change would alter a
number, it is out of scope.

Reference: `docs/dashboard_cockpit_design.md`. Prior work: `DEV_HANDOFF.md`,
`TEST_REPORT_39.md`, `TEST_REPORT_40.md`.

---

# PART A — Visual system (the "bland" fix)

## A.1 Root cause

`web/index.html`'s inline cockpit `<style>` block hardcodes a foreign palette —
`#16a34a`, `#f59e0b`, `#ea580c`, `#dc2626`, `#fef2f2`, `#dcfce7`, `#eef2ff`, `#3730a3`.

This app already has a deliberate, single-source-of-truth palette in `web/styles.css`
`:root` — `--bull`, `--bear`, `--warn`, `--ok`, `--accent`, `--text-1/2/3`, `--border`,
and the full `--act-*` action ramp (muted brick/sienna sells, muted sage/forest buys).
Every other screen uses it. The cockpit uses none of it, so it reads as a different
product bolted on — bright generic Tailwind next to the app's muted, considered hues.

**Rule for this task: no raw hex in the cockpit block. Every colour is a `var(--…)`.**
If a role is missing from `:root`, add the token to `:root` in `styles.css` and use it —
do not inline a literal.

## A.2 Move the cockpit styles out of `index.html`

The block is ~70 lines of page-specific CSS living inline. Move it into
`web/styles.css` under a `/* ===== Dashboard cockpit (TASK_133/134) ===== */` banner.
Rationale: it is no longer a small page-local tweak like `.briefing-card`, it is a
screen's whole visual system, and keeping it in `styles.css` is what makes it share the
token set instead of drifting again.

## A.3 Fix the hierarchy — the number leads

Current order inside `#riskDialBody`: headline (20px bold black) → number (34px) →
meter (8px) → size line → gauges.

The headline is a *supporting sentence*. The budget number is *the product of the whole
screen*. Right now the sentence is styled loud enough to compete with it, and the meter
is too thin to register at all.

Target order and weights:

```
┌──────────────────────────────────────────────────────────────┐
│  35        DEFENSIVE          today's size = AMT$ × 0.35     │   ← one row
│  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░                      │   ← 14px meter
│  Half size. 10Y at 4.75% — top of range; credit weakening.   │   ← 13px, --text-2
└──────────────────────────────────────────────────────────────┘
```

| Element | Change |
|---|---|
| `.rd-budget` | 34px → **48px**, `font-weight: 800`, `line-height: 1`, `font-variant-numeric: tabular-nums` |
| `.rd-label` | Same row as the number, `font-size: 14px`, sits on a tinted pill (see A.4) |
| `.rd-size-line` | **Promote** — same row, right-aligned, 15px, `font-weight: 700`, `--text-1`. This is the line that changes what the user types into the broker; it must not read as a footnote. Wrap the multiplier in `<strong>`. |
| `.rd-meter` | height 8px → **14px**, `max-width: 100%`, `border-radius: 7px`, track `--border` |
| `.rd-headline` | 20px bold → **13px, `--text-2`, weight 400**, moved **below** the meter |

## A.4 Severity encoding — the biggest single win

Today every fired gauge row is the same `#fef2f2` wash, so a weight-3 credit-stress
flag looks exactly like a weight-1 gold-vol flag. The dial's whole logic is that gauges
are not equal, and the UI throws that away.

Encode weight as severity, with a **coloured left rail plus a weight chip** — never
colour alone (a status colour must always ship with a label; see the app's own
`actionDisplay()` convention and the accessibility rule that identity is never
carried by hue unaided).

```css
.rd-gauge-row {
  display: grid;
  grid-template-columns: 3px 28px 1fr auto;
  gap: 8px;
  align-items: baseline;
  padding: 5px 8px 5px 0;
  border-bottom: 1px solid var(--border);
  background: none;                     /* drop the flat pink wash */
}
.rd-gauge-row .rd-rail { align-self: stretch; border-radius: 2px; }
.rd-gauge-row .rd-wt {
  font-size: 10px; font-weight: 700; text-align: center;
  padding: 1px 0; border-radius: 3px; font-variant-numeric: tabular-nums;
}
/* weight 3 — heaviest */
.rd-gauge-row.sev-3 .rd-rail { background: var(--bear); }
.rd-gauge-row.sev-3 .rd-wt   { background: var(--act-sell-strong-bg); color: var(--act-sell-strong); }
.rd-gauge-row.sev-3 strong   { color: var(--act-sell-strong); }
/* weight 2 */
.rd-gauge-row.sev-2 .rd-rail { background: var(--act-sell); }
.rd-gauge-row.sev-2 .rd-wt   { background: var(--act-sell-bg); color: var(--act-sell); }
/* weight 1 — lightest */
.rd-gauge-row.sev-1 .rd-rail { background: var(--act-sell-weak); }
.rd-gauge-row.sev-1 .rd-wt   { background: var(--act-sell-weak-bg); color: var(--act-sell-weak); }
```

Row markup becomes: `[rail] [wt chip] [label — detail] [exposure $]`.
`loadRiskDial()` already sorts `fired` by weight descending — keep that; the visual
weight now matches the sort order, which is the point.

The exposure figure gets `--text-1` and `font-variant-numeric: tabular-nums` so the
dollar column aligns down the list. It is currently `--text-3`-grey and unreadable,
despite being the thing that makes an alert personal rather than a news item.

## A.5 Meter fill by band, from tokens

```css
.rd-meter-fill.b-clear      { background: var(--ok); }
.rd-meter-fill.b-caution    { background: var(--warn); }
.rd-meter-fill.b-defensive  { background: var(--act-sell); }
.rd-meter-fill.b-notinv     { background: var(--bear); }
```

Set the class server-side-agnostic in JS from `risk_label`; **delete the inline
`style="background:${color}"` and the `const color = …` ternary in `loadRiskDial()`.**
Same for the number's colour — class, not inline style.

## A.6 Bands 2–6 — the rest of the flatness

| Band | Problem | Fix |
|---|---|---|
| **All** | `.band-num` chip is `#eef2ff`/`#3730a3` indigo — an accent used nowhere else | `background: var(--bg)`, `color: var(--text-3)`, `border: 1px solid var(--border)`. It is a wayfinding number, not a highlight. |
| **All** | `h2` is 12px uppercase `--text-3` — louder than it earns while saying nothing | Keep the size, drop to `--text-3`, add `font-weight: 600`. Let the content lead. |
| **2 — events** | `.ev-sev` pills use raw hex | `severe` → `--act-sell-strong` on `--act-sell-strong-bg`; `warn` → `--act-mixed` on `--act-mixed-bg`; `info` → `--neutral` on `--act-neutral-bg` |
| **2 — events** | Rows are undifferentiated grey text | Add the same 3px left rail, coloured by severity |
| **4 — scorecard** | Numbers are plain black — no read of good/bad | Colour `twr_*` and the vs-Mkt delta by sign: positive `--bull`, negative `--bear`, zero `--text-3`. Add `font-variant-numeric: tabular-nums` to every numeric cell so columns align. |
| **4 — scorecard** | `verdict` is plain text | Render through the app's existing action-badge language: ADD/PRESS → `--act-buy*`, HOLD → `--act-neutral`, TRIM/TRIM_HARD → `--act-sell*`, ROTATE → `--act-mixed`. **Reuse `actionDisplay()` from `_common.js` if it is importable; otherwise mirror its class names.** Consistency with Actionable matters more than novelty here. |
| **4 — scorecard** | Weight % has no visual scale | Add a 3px inline bar behind the `You %` cell, width = weight%, `background: var(--accent)` at 15% opacity. Cheap, and makes concentration visible at a glance. |
| **4 — scorecard** | `.fs-conf` badges raw hex | `green` → `--ok`/`--act-buy-weak-bg`; `amber` → `--warn`/`--act-mixed-bg`; `suspect` → `--bear`/`--act-sell-strong-bg` |
| **5 — shortlist** | Rows are plain text; this is the one band with real trades on it | Symbol in the app's mono face, action through `actionDisplay()`, AMT$ bold `--text-1` tabular, stop in `--bear` when breached |
| **6 — housekeeping** | Fine as-is | Only swap raw hex for `--ok` / `--bear` |

## A.7 Empty and quiet states

`.ev-quiet` is italic grey and currently used for both "nothing happened" (good) and
"unavailable" (bad). Split them: quiet keeps italic `--text-3`; a failure state gets
`--bear` text and a `⚠` so a dead endpoint never masquerades as a calm market.

## A.8 Do NOT

- Do not touch `web/actionable.*`. There is an unrelated uncommitted diff in those files
  (sector/style filter chips) that is the user's own in-progress work — leave it.
- Do not introduce a chart library. Bars and rails here are `<div>`s with a width.
- Do not add a dark-mode variant. The app has no theme toggle; adding a half-supported
  one is worse than none.

---

# PART B — Content bugs

## B.1 Gauge detail must lead with the leg that actually fired

`etl/derive_risk_dial.py::_g_oil_shock` returns both legs joined unconditionally:

```
"WTI 39% of range; OVX 63"
```

WTI at 39% is mid-range and did **not** fire — the gauge fired on OVX. Leading with the
non-triggering leg makes the user distrust the dial, correctly. This surfaced in the
headline, which is the most-read string on the screen.

**Fix, applied to every multi-leg gauge** (`_g_oil_shock`, `_g_credit_stress`,
`_g_yield_level_watch`, and any other returning a joined `parts` list):

- When `fired` is True → the detail string contains **only the legs whose condition is
  true**, most-decisive first.
- When `fired` is False → summarise the nearest-to-firing leg only.
- Never include a leg that neither fired nor is the closest miss.

Example: OVX 63 above a 50 threshold, WTI mid-range → `"OVX 63 — above elevated (50)"`.
If both fire → `"WTI 91% of range; OVX 63 — above elevated (50)"`.

Add a case to `tests/test_risk_dial.py`: a multi-leg gauge firing on exactly one leg
must not mention the other.

## B.3 Band 2 must only use genuine Hedgeye risk ranges

**This is the highest-priority item in the task.** Band 2 currently reports things like
*"ATRO entered the top decile of its risk range"* — obscure small-caps, not market
context. Those symbols have no Hedgeye risk range at all.

`drv_rr` carries a **`source`** column, set in `etl/derive.py::_derive_rr_impl`:

| `source` | Meaning | Coverage |
|---|---|---|
| `'RR'` | Genuine Hedgeye risk range (`hist_rr.buy_trade` / `sell_trade`) | ~55 curated instruments |
| `'BB'` | **Fallback** — TOS Bollinger bands (`hist_td.a_bb_bottom` / `a_bb_top`) | the entire ~1,000-symbol universe |

`etl/derive_market_event.py::_risk_range_events` (line ~140) queries `drv_rr` with **no
source filter**, so every BB-approximated band in the universe emits range-break and
decile-crossing events. The user's instruction is explicit: Band 2 is for the
instruments that arrive in the Hedgeye Risk Range feed, nothing else.

**Fix:**

```sql
SELECT tos_symbol, lrr, trr FROM drv_rr
 WHERE as_of_date = :d AND source = 'RR'
```

Apply the same restriction to **every** range-derived event in that function —
`range_break_up`, `range_break_down`, `entered_top_decile`, `entered_bottom_decile`.

Also check `drv_rr_trend_change` (the `trend_flip` source). `outlook` is NULL for BB
rows, so trend flips *should* already be RR-only — **verify that and say so in
`DEV_HANDOFF.md` rather than assuming.** If BB rows can reach it, filter there too.

Leave the `_Z_SYMBOLS` z-score list and the pattern detectors alone — they are already
a curated market-instrument list and are working as intended.

Add to `tests/test_market_patterns.py`: a fixture containing both an `RR`-source and a
`BB`-source symbol at the top decile must emit **exactly one** event.

Expected effect: Band 2 goes near-silent on ordinary days — which is correct. The design
contract is that silence is the default state and only genuine market events surface.

## B.2 Headline should name the budget

`_RISK_SIZE_PHRASE` yields e.g. `"Reduce size."`. The number sits directly beside it
after A.3, so the phrase should be the *instruction*, not a restatement of the label.
Keep the phrase but ensure it reads as an imperative with a target — e.g.
`DEFENSIVE` → `"Half size."`, `CAUTION` → `"Three-quarter size."`,
`CLEAR` → `"Full size."`, `NOT INVESTABLE` → `"No new risk."`

Single source of truth: keep it in `_RISK_SIZE_PHRASE` in `api/routers/cockpit.py`,
and make sure the phrase and `suggested_size_multiplier` cannot disagree — derive the
phrase from the same band boundaries the multiplier uses.

---

# PART C — Follow-ups TASK_133 deferred

## C.1 Transaction-feed gaps — surface them, do not hide them

`DEV_HANDOFF.md` Part A found two real, ongoing data gaps, independently confirmed in
`TEST_REPORT_40.md`:

| Account | Gap |
|---|---|
| Schwab `Rollover_IRA …892` | `hist_cst` has loaded **nothing since 2026-06-02** while `hist_cs` positions keep updating daily |
| Fidelity `261408079` ("Rollover IRA") | `hist_ft` has **zero rows, ever** — and this account holds AAPL, MSFT, META, NFLX |

Consequence: every trade in those accounts is invisible to netflow detection, which is
why `flows_confidence` reads `suspect` almost everywhere and why the factor scorecard's
returns are degraded. **This is a data-source problem, not a code bug** — but the screen
must say so rather than quietly showing weakened numbers.

**Build:** extend Band 6 (housekeeping) with a per-account transaction-feed staleness
check — for each account present in `hist_cs`/`hist_f`, compare
`MAX(snapshot_date)` in positions vs. `MAX(transaction_date)` in `hist_cst`/`hist_ft`.
Any account more than **10 trading days** apart renders a red line naming the account
and the gap in days. Reuse the existing `/api/anchor-status` + ingest-log rendering
pattern; add the check to `GET /api/cockpit/housekeeping` (or the existing housekeeping
data path).

When any account is flagged, Band 4 shows a one-line caption above the table:
*"Returns degraded — N account(s) missing transaction history. See Housekeeping."*

## C.2 `REF_MAPS` — the confirmed landmine

`etl/mappings.py:556` still has `REF_MAPS: dict = {}` overwriting the populated dict at
line 31. TASK_133 investigated and left an accurate comment: the blanking is live and
will silently no-op Sctr/RRT/Desc reloads and raise if `refresh_ref.py --table
ref_sector` is ever run. Deferring was the right call then; it needs closing now.

**Do:** delete line 556 and its comment block. Reload the Tickers workbook
(`python -m etl.tickers_initial_load`). Confirm `ref_sector`, `ref_rrt`, `ref_rule_desc`
row counts before and after — **paste both in `DEV_HANDOFF.md`.** If any count *drops*,
restore the line and stop.

## C.3 MOVE volatility zone — verify, do not assume

`api/routers/marketbar.py` was never modified by TASK_133 (mtime unchanged), yet
`_METRIC_TO_VOL_SYM` already maps `'MOVE': 'MOVE:GIF'`. Either the bug was elsewhere or
it was already fixed. Phase 1.1 was reported done but the evidence is ambiguous.

**Do:** with the server running, `curl -s localhost:8000/api/marketbar` and confirm the
`MOVE` item returns non-null `vol_low`/`vol_high` and the tile renders a zone badge. If
null, trace the real cause and fix it. Record the actual result either way.

## C.4 Restart trap

Both test reports flagged the same operational trap: a long-running `uvicorn` on :8000
404s every `/api/cockpit/*` path because it predates the router. Add one line to
`COMMANDS.md` under troubleshooting: *"New endpoints 404 → the running server predates
them; `api/` hot-reloads but new routers need a restart, and `etl/` never hot-reloads."*

---

## How to verify (tester reference — on request only)

1. `grep -nE '#[0-9a-fA-F]{3,6}' web/styles.css` within the cockpit banner block →
   **zero raw hex** (tokens only). Same check on `web/index.html`'s remaining inline
   style — the cockpit block should be gone entirely.
2. Load `/` — Band 1 shows a 48px number, a 14px meter, the size line on the top row,
   and fired gauges with distinct rails/weight chips at weights 3 / 2 / 1.
3. A weight-3 and a weight-1 gauge are visually distinguishable in a screenshot.
4. `/api/cockpit/risk-dial` — pick a multi-leg gauge that fired on one leg; its `detail`
   must not mention the non-firing leg. Confirm the headline inherits that.
4b. **`/api/cockpit/events` contains only Hedgeye-fed symbols.** Cross-check every
   `tos_symbol` in the response against
   `SELECT DISTINCT tos_symbol FROM drv_rr WHERE source='RR' AND as_of_date=D;`
   → zero symbols outside that set. Re-derive the date that produced the ATRO/PNDRY
   events and confirm both are gone.
5. Band 4 — `twr` numbers coloured by sign, verdicts rendered as action badges matching
   Actionable's vocabulary, `You %` bars present.
6. Band 6 — both known-bad accounts (Schwab `…892`, Fidelity `261408079`) appear as red
   staleness lines; Band 4 shows the degraded-returns caption.
7. `pytest tests/test_risk_dial.py -q` → green, including the new single-leg case.
8. `python -m etl.derive` twice → all `drv_*` byte-identical (nothing in this task may
   change a number).
9. C.2 row counts pasted in `DEV_HANDOFF.md`, before and after.

## Files expected to change

`web/styles.css`, `web/index.html`, `web/app.js`, `api/routers/cockpit.py`,
`etl/derive_risk_dial.py`, `etl/mappings.py`, `tests/test_risk_dial.py`,
`COMMANDS.md`, `docs/dashboard_cockpit_design.md` (visual-system section).

**Not touched:** `web/actionable.js`, `web/actionable.html`, any derive that produces a
number, any threshold, any endpoint response shape (Band 6 gains fields; nothing is
removed or renamed).

## Standing rules

- **No questions.** Where this spec is silent, match the existing app's conventions and
  note the choice in `DEV_HANDOFF.md`.
- **No commits, no pushes.** The user commits from Windows.
- **No calculation changes.** If a change would move a number, it is out of scope.
- Verify large edits (`node --check`, `ast.parse`) — truncation is silent.
- End `DEV_HANDOFF.md` with `ALL_DONE`, or `PART_<X>_DONE` if you stop early.
