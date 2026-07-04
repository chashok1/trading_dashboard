# TASK_103 — Actionable screen bug sweep (batch 1 of review)

Source: `docs/audit/actionable_screen_review.md` (2026-07-03), bugs B1–B4, B6
plus dead-code cleanup §3. All line numbers verified against current files.

Goal: fix the five confirmed bugs and delete confirmed-dead code on the
Actionable screen. No feature work, no layout changes, no schema changes.

Files expected to change:
- `web/actionable.js` (most items)
- `api/routers/dash.py` (items 1 and 3)
- `web/actionable.html` (optional CSS removal, item 6)

---

## Item 1 — Inline/bulk/focus Snooze never sticks (B1)

**Problem.** `inlineAction(sym,'SNOOZED')` (actionable.js ~2961–2984, wired at
~3896 row button, ~3928 bulk, ~3935 focus) posts `user_action=SNOOZED` with no
`snooze_until`. Server-side hiding (dash.py ~1112–1116) only skips SNOOZED rows
when `snooze_until >= d`; client `matchesBaseFilters` (~1187–1188) and
`_hiddenReason` (~1829–1831) only treat DONE/SKIPPED/OVERRIDDEN. Result: a
snoozed row reappears on the next reload.

**Fix — semantics:** a SNOOZED action with NULL `snooze_until` means
"hidden for this as_of_date" (same lifetime as SKIPPED, distinct label).
A SNOOZED action with a date keeps existing until-date behavior.

1. `api/routers/dash.py` (~1112–1116) — replace the two checks with:
   - hide if `last_user_action in ('DONE','SKIPPED','OVERRIDDEN')`
   - hide if `last_user_action == 'SNOOZED' and (snooze is None or snooze >= d)`
2. `web/actionable.js` — mirror in `matchesBaseFilters` and `_hiddenReason`:
   treat SNOOZED (null-or-future `snooze_until`) as acted/hidden. The row's
   `snooze_until` field is already selected by the API.

## Item 2 — Atomic-popover × button dead (B2)

`web/actionable.js:4022`:
```js
$('closePop').addEventListener('click', () => $('detailPop')?.classList.remove('open'));
```
`#detailPop` does not exist. Replace the handler body with `closeAtomicPopover()`.

## Item 3 — Snoozed rows can't be un-snoozed (B3)

`api/routers/dash.py` `clear_actionable_action` (~1481–1496) deletes only
`user_action = 'SKIPPED'`. Change to `user_action IN ('SKIPPED','SNOOZED')`
so the Show-Hidden un-snooze path clears both. Update the docstring.

## Item 4 — CSV `Metric` column always empty + dead sort case (B4)

- `web/actionable.js:3072` — remove the `['Metric', r => r._metric]` column
  from `exportCsv` (`_metric` is never assigned anywhere).
- `web/actionable.js:2796` — remove the `'_metric'` special case in
  `initSorting` (no column carries `data-key="_metric"`); the line becomes
  `state.sort.dir = 1;`.

## Item 5 — Focus card shows Sources action but logs Final Call (B6)

`_renderFocusCard` (~3006–3032) renders the badge from
`_badgeAction(r)` / `actionLabel(r)` (consolidated action), while the Done
button logs `r._fc_code` (Final Call). Make the card display the Final Call:

- badge: use `finalCall(r)` → `actionText`/`colorCls` (same rendering the
  grid ACTION column uses via `_finalCallHtml`, minus the confidence badge or
  including it — implementer's choice, keep it readable at 16px).
- keep AMT$ and "why" as they are.

## Item 6 — Dead-code deletion

All confirmed single-occurrence (definition only, no callers) in
`web/actionable.js`; delete:

- `_srcSubLineHtml`, `_renderOtherSources`, `_convictionHtml`,
  `_sourceWeightDelta`, `_rowMetric`, `_fcStrengthToAction`, `_outlookChip`,
  `_assetClass`
- `_metricAscending` (its only caller is the special case removed in Item 4)
- `.btn-suppress` click delegation block (~3911–3914) — no such button is
  rendered. Optionally also the `.btn-suppress` CSS block in actionable.html
  (~370–387).
- Filter localStorage persistence: `saveFiltersToStorage`,
  `loadFiltersFromStorage` (~1545–1567) and their call sites
  (`applyClientFilter` ~1249, DOMContentLoaded ~3849). Current behavior
  (filters reset on page open) is intentional per the in-code comment; the
  writes are dead.
- Nested `document.addEventListener('DOMContentLoaded', setupRRActionCol)` at
  ~4044 (inside an already-fired DOMContentLoaded — never runs). Keep the
  direct `setupRRActionCol()` call on the next line.

Do NOT touch the Top-N collapse remnants (`state.showAll`, `TOP_N`,
`.show-all-bar`) — reserved for a later task that finishes the feature.

**Careful:** keep `_isPctSource`, `_weightToOutlook`, `fmtPct` — they have live
callers (drilldown modal).

## Guardrails

- `actionable.js` is 4,300+ lines — per CLAUDE.md file-truncation warning,
  verify after editing: `node --check web/actionable.js` and `tail -10`.
- No behavior changes beyond the items above; default filters, sort, and
  layout must be unchanged.
- Do not commit — user commits from Windows.

---

## How to verify

Prereq: app running (`start.bat` / uvicorn), current anchor date has rows.

1. **Snooze sticks (Item 1).** On /actionable click a row's 💤 button → row
   grays out. Click Refresh → row is gone. DB check:
   `SELECT user_action, snooze_until FROM user_action_log WHERE tos_symbol='<SYM>' ORDER BY acted_at DESC LIMIT 1;`
   → `SNOOZED`, NULL snooze. API check: row absent from
   `GET /api/actionable?date=<D>`, present with `show_acted=true`.
2. **Un-snooze (Item 3).** Toggle Show Hidden on → snoozed row visible.
   `DELETE /api/actionable/<SYM>/action?date=<D>` (or UI path) → returns
   `{cleared: >=1}`; after Refresh with Show Hidden off the row is back.
3. **Popover close (Item 2).** Open a drilldown, click a rule pill → atomic
   popover opens; click its × → popover closes.
4. **CSV (Item 4).** Export CSV → no `Metric` header; other columns intact.
   Column sorting still works (click POS$, Symbol, P(↑20d) headers).
5. **Focus card (Item 5).** Open Focus mode on a row where the ACTION column
   badge differs from the Sources column — card badge must match the ACTION
   (Final Call) column and the Done button code.
6. **No regressions.** `node --check web/actionable.js` passes; browser
   console clean on load, hover popovers (source, MACRO, Vol, IV, RR) all
   still work; grid renders same row count as before for the same filters;
   drilldown modal opens/closes.
7. `pytest tests/` — no new failures.
