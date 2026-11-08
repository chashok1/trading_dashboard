# Design Spec — DESIGN_WORK_9 (revision 3: allocate by area, using the Universe screen's controls)

## Goal
Inside each asset-class bucket of the account-first Builder, let the user split the money **by area** (sectors
inside Equities, duration/credit inside Fixed Income). One button, **Fill from Macro and Quad**, does the split:
favoured areas get more, Sell areas get zero, and the user can overwrite any weight. Everything reuses the
Universe screen's controls, wording and code wherever they mean the same thing.

> Supersedes `DESIGN_SPEC_10.md` (left untouched; `DESIGN_SPEC_9.md` also untouched). Everything in spec 10, and
> in spec 9 where spec 10 did not change it, still applies unless this spec says otherwise. Mockup updated in
> place: `docs/mockups/builder_mockup.html`.
> Read-only database queries were blocked in all three design sessions, so every number in the examples is
> **illustrative**. Build task 1 replaces them with real data.

---

## One-page summary (plain English)

**What I checked.** I read every control on the Universe screen to see what it really calculates and from
what data. The question for each was whether it describes an **area** (a sector, an asset class, a style), a
**single stock**, or only how the screen looks. Only area-level controls can allocate money by area.

**What the Builder takes from Universe:**
- **Factors view → the area stance table.** It is the Hedgeye Quad playbook (`ref_quad_outlook`): for every
  sector, asset class, style and bond type, Bullish / Neutral / Bearish in each Quad. This is the real "area"
  data, and it drives the fill.
- **Quad buttons (Qd, Q1, Q2, Q3, Q4) → "assume this Quad".**
  - Nothing picked (Qd): each area's stance is the expected Quad mix over your holding period.
  - Q2 picked: stances as if Quad 2 were certain.
  - Several picked: the same AND rule as Universe. An area counts as favoured only if it is Bullish in every
    Quad you picked.
- **Macro (Mcro / B / S / H) → the area's stance chip.** Each area shows B, S or H, worked out for the area
  itself rather than copied from single stocks. One stance per area: Macro and Quad are never added together,
  because both come from the same playbook.
- **Asset view → the shape of the area list.** Asset class first, then sectors inside Equities. The labels
  follow the Portfolio pie, not Universe (Universe uses a different, broker-supplied asset-class field; see
  Notes).
- **Style buttons → optional "flavour" filters** inside Equities: Defensive (Def, Lo-B, Div), Offensive (Cyc,
  Hi-B, Small), Value (Val), Growth (Sec).
  - **Mom is left out on purpose.** On Universe it means "RSI above 65 today", which changes day to day. It is
    not a trend you can hold for months, and the Momentum recipe already covers real momentum.
- **Color (B / S / H) → kept only as the existing "skip funds the Final Call sells" rule.** It is one stock's
  own Final Call, not an area.
- **Act (by account) → already in Builder** as the step-0 account picker.

**What the Builder leaves out:** All, Src# / Src$ (Hedgeye lists per stock), Held / Actionable, the Risk Range
slider, Gains / Losses and the tile-size buttons (%, $, =). These describe single stocks, your current P&L, or
only how tiles look.

**How the fill works, in one sentence:** start every area at an equal share of its bucket, double the most
favoured ones, zero the Sell ones, keep at least three areas, cap any area at 40% of the bucket, then let the
bucket's pick rule (Low vol, Low beta or Momentum) choose the fund inside each area.

**Simpler than spec 10:**
- The separate "Quad" recipe is gone. It *is* the area fill now.
- Equities has two ways to split:
  - **By area (Macro and Quad)**, with a pick rule inside each area;
  - **By recipe** (Low vol, Low beta or Momentum across all equity funds), as in spec 10.
- The account picker, mix presets, Risk Dial, keep-as-is list and Final Call skip all work exactly as in spec 10.

---

## Open questions

### Still pending from spec 10 (not yet answered; my recommendation first)
1. **One running model per account,** where accepting a new one replaces it? *Recommend:* yes.
2. **Keep-as-is list:** *Recommend:* a new per-account list, with a one-click helper that adds your LT Hold names
   held in that account.
3. **What counts as Cash:** *Recommend:* exactly what the Portfolio pie counts (`is_cash()` rows). Short bond
   funds such as BUXX stay in Fixed Income.
4. **Preset numbers:** *Recommend:* store them in an editable table. Please confirm All-weather
   30/55/7.5/7.5/0 and the Quad tilt (±25% on each bucket's stance); both are GUESSes.
5. **Account type** (Taxable / IRA / Roth / HSA / 401k), set on Ref Data: *Recommend:* yes. In v1 it is used only
   for the taxable gain line and to hide the trade list for a 401k.
6. **Whole book:** *Recommend:* preview only, never frozen.

### New in this revision
7. **Starting point before the tilt, inside Equities.** *Recommend:* equal share per area: simple to explain,
   and no data we lack. *Alternative:* S&P 500-like sector weights (Tech ~30%). That needs a small hand-kept
   sector-weight table, updated quarterly.
8. **Sell areas.** *Recommend:* zero, as you asked, with a minimum of 3 areas kept per bucket. *Alternative:*
   halve them instead of zeroing.
9. **Several Quad buttons picked at once.** *Recommend:* the same AND rule as Universe: favoured only if
   Bullish in every Quad picked, and zeroed if Bearish in any of them. *Alternative:* average the picked Quads.

---

## Design

### Per-control decision table (Universe → Builder)

Verified in `web/universe.html`, `web/universe.js`, `api/routers/universe.py`, `etl/derive_macro.py` and
`etl/derive_category_perf.py`.

| Universe control (exact label) | What it really does | Level | Builder decision | Why |
|---|---|---|---|---|
| View **All** | Flat treemap of every symbol | display | Leave out | No area meaning |
| View **Act** | Treemap by account (held positions only), drilling to Asset → Sector → Symbol | account | **Already adopted** (step-0 account picker, grouped by `short_name`) | Builder is account-first |
| View **Asset** | Hierarchy: asset class → sector (Equities only) → symbol. Asset class = `drv_actionable.real_asset_class` (broker's tag), merged to Equities / Fixed Income / "FX / Currency"; ~43% Unclassified | area | **Adapt:** adopt the *shape* (asset class → sectors inside Equities), but take the labels from the Portfolio pie's map (`_category_axis_map`), not `real_asset_class` | The buckets must match the pie, and the pie deliberately moved off `real_asset_class` |
| View **Src#** / **Src$** | Treemap by Hedgeye source (RR / CALL / ETF / II / SSS / PS) that flagged each symbol; # = count, $ = capital | symbol | Leave out | A list membership per stock, not an area; Hedgeye already feeds Momentum's "no Bearish" rule |
| View **Factors** | `ref_quad_outlook` table: category → sub-category, Bullish / Neutral / Bearish per Quad (`GET /api/universe/quad-factors`); Q buttons filter rows Bullish in every picked Quad | **area** | **Adopt** as the stance source for every area, with the same Q1-Q4 pills | It is the only real per-area data on the screen |
| Filter **All / Held / Actionable** (also on screen) | Narrows symbols to held or actionable | symbol | Leave out | "Held" is already the "vs your account" view |
| Color **All / B / S / H** | Final Call of one symbol (`final_code` through `actionSide()`: all buy tiers = B, all sell tiers = S, anything else = H) | symbol | **Keep only** as the spec 9 skip-Sell rule, using the same `actionSide` grouping | A stock's own signal, not an area's |
| Style **All / Cyc / Def / Div / Hi-B / Lo-B / Mid / Mom / Sec / Small / Val** | Tags per symbol from `drv_macro_score.style_stances` (rules in `_classify_style`: Hi-B beta >= 1.5, Lo-B <= 0.7, Def / Cyc by sector, Val P/E < 15, Sec P/E > 30, Div yield > 2%, Mom RSI > 65, Small < $2B, Mid $2-10B). A symbol can carry several. Only tags that occur are shown | symbol (multi-tag) | **Adapt** as optional flavour filters inside Equities (OR within a flavour). **Mom excluded**; **Mid** offered only as its own flavour | Filters never add weight, so multi-tags cannot double count; Mom is a one-day RSI reading |
| Risk Range slider (on screen) | Position inside the Hedgeye risk range, 0-100% | symbol, short-term | Leave out | A days-to-weeks reading; the Final Call already uses it |
| Macro **Mcro / B / S / H** | One symbol's MACRO badge (`macro_value`: BM / BS → B, STM / SA → S, HOLD → H; no value = excluded). MacroNet = sector x2 + asset class x1 + styles x0.5 over a fixed 60-day Quad window | symbol | **Adapt** to area level: an area chip B / S / H from the area's *own* stance over *your* holding period | The symbol score mixes several memberships, and its cut-offs (1.25 / 1.05 / -0.6 / -1.0) are on a different scale |
| Quad **Qd / Q1 / Q2 / Q3 / Q4** (multi-select) | Symbol level: `quadN_net > 0` (stance if Quad N were certain), AND across picks. Factors level: area Bullish for every picked Quad | symbol + **area** | **Adopt the area version** as "assume this Quad": overrides the window mix, AND rule (Q9) | Same meaning, same data |
| Gain **All / Gains / Losses** | Filters by unrealised gain % (rollups use the group's own gain) | holding P&L | Leave out | Allocation should not depend on what is up or down in the account; the taxable line covers tax |
| Size **% / $ / =** (and hidden **Sig%**, **Rank**) | Tile sizing only | display | Leave out | Display only |

### Where the area step sits in the flow

```
0 Account (spec 10) -> 1 How long -> 2 Mix by asset class (presets, Risk Dial; spec 10)
-> 3 Split each bucket  <- NEW: by area (Macro and Quad) or by recipe
-> 4 Warnings -> Proposed model -> Accept
```

**Step 3, Equities bucket** (left column: settings; right column: the area table, because it needs width):

```
Equities  42% = $173,200     Split: (•) By area (Macro and Quad)   ( ) By recipe
  Quad:     [Qd] [Q1] [Q2] [Q3] [Q4]     Qd = the expected Quad mix over your 3 months (Q2 71%, Q1 29%)
  Flavour:  [All] [Defensive: Def Lo-B Div] [Offensive: Cyc Hi-B Small] [Value: Val] [Growth: Sec] [Mid]
            (Mom not offered: it means "RSI above 65 today")
  Pick inside each area: [ Low volatility v ]      [ Fill from Macro and Quad ]  [ Reset ]

AREAS (Equities)                                   Q1   Q2   Q3   Q4   Base   Fill   Your %   $        Funds
Information Technology      [B]  +0.71             Bull Bull Bear Bear  8.3%  15.0%  15.0%   25,980   XLK
Industrials                 [B]  +0.71             Bull Bull Neut Bear  8.3%  15.0%  15.0%   25,980   XLI
Financials                  [B]  +0.71             ...                  8.3%  15.0%  [12.0] ✎ 20,780  XLF
Consumer Discretionary      [H]  +0.13             ...                  8.3%   9.4%   ...
Utilities                   [S]  -0.71             ...                  8.3%   0.0%    0.0%       0   (none)
Broad US                    [H]  ...                                    8.3%   ...                     SPY, IWM -> SPY (calmest)
Foreign                     [H]  ...                                    8.3%   ...                     EFA, EEM -> EFA
Kept: AAPL ($38,000) and MSFT ($23,200) count inside Information Technology   🔒
```

- **Chips** reuse Universe's look: B / S / H in the action colours (`--act-buy-strong`, `--act-sell-strong`,
  `--act-neutral`, light backgrounds), and the Q1-Q4 pills reuse the `uv-factor-pill bull / bear / neutral`
  classes. The number next to the chip is the stance (-1 to +1).
- **Hover on a chip:** a bulleted list showing the window months and their Quad shares, this area's outlook in
  each Quad, and "Stance +0.71 = 71% x Bullish + 29% x Bullish ...".
- **Your %** is an editable box. Editing it locks the row (✎ shows), and Fill then re-spreads only the unlocked
  rows. **Reset** clears all locks.
- **Totals line** under the table: "Areas add to 100% of Equities. 2 locked. 1 at zero (Utilities: Sell)."
- **Fixed Income** gets the same table, with its own areas (below). Gold, Commodities, Crypto and Currency have
  one area each, so they show no table.

### Areas per bucket (one area per fund, fixed in `ref_pb_universe.area`)

| Bucket | Areas | Stance comes from (`ref_quad_outlook` category / sub-category) |
|---|---|---|
| Equities | the 11 GICS sectors (sector funds XLK ... XLC) | "Equity Sectors" / that sector |
| Equities | **Broad US** (SPY, QQQ, IWM, DIA, MTUM, SPLV, VYM ...) | "Asset Class" / Equities |
| Equities | **Foreign** (EFA, EEM, EWJ, EWZ, EWG ...) | "Asset Class" / Equities (no country rows exist; Task 1 confirms) |
| Fixed Income | one area per bond type in the fund list's `sub_asset_class` (for example Long Bond, IG Credit, HY Credit, Short duration / cash-like) | "Fixed Income" / that sub-class, matched as in `derive_macro` |
| Gold / Commodities / Crypto / Currency | one area each | "Asset Class" / that class (for the chip only) |

- **A fund belongs to exactly one area.** A broad fund does not also count toward Tech, and its style tags never
  add weight. This is the main guard against double counting.
- Kept single stocks are placed in their sector area using the pie's sector map
  (`/api/portfolio/sector-map`). Unmapped ones go to Broad US.

---

## Rules & numbers

### S1 — One stance per area
- **Default (Qd):** stance_a = sum over Quads k of share_k x outlook(a, k).
  - outlook: Bullish +1, Neutral 0, Bearish -1, compared case-insensitively (Universe's `QUAD_IS_BULLISH`).
  - share_k: the horizon-matched Quad mix from spec 9 R2: `window_weights` + `build_effective_distribution`,
    with the window set to the holding period, plus the HOLDING / WATCH / TRANSITION blend from
    `drv_quad_check`.
  - This is the same calculation as `drv_macro_score.sector_stance` and `drv_category_perf.quad_stance`, except
    the window is your period instead of the fixed 60 days.
- **Quad override (Q buttons picked):** shares are ignored.
  - One Quad picked: stance_a = outlook(a, that Quad).
  - Several picked (AND rule, Q9): +1 if Bullish in all of them; -1 if Bearish in any; else 0.
- **Chip:**
  - B when stance >= +0.25;
  - S when stance <= -0.25;
  - H otherwise (GUESS band; shown in the hover).
- Macro and Quad are **not added together**: the chip *is* the Macro read, and the Q buttons only change which
  Quad mix it is computed from.
- **Missing outlook row** for an area: stance 0, a grey chip "—" and hover "No Quad view for this area". The area
  keeps its base share and is never zeroed.
- **Stale or short Quad data:** if the Quad mix covers under 50% of the period, the step shows "Quad outlook
  covers only X of your N months". Stances are still computed from what is covered.
  - If `drv_quad_check` is NO_DATA, no transition blend is applied and a note says so.
  - If `ref_quad_periods` has nothing for the start month, Qd is disabled and the user must pick a Quad.

### S2 — Fill from Macro and Quad (inside one bucket)
1. **Eligible areas** = areas with at least one eligible fund (spec 9 R0) that passes the flavour filter, or
   holding a kept position.
2. **Base share** = 1 / (number of eligible areas). Option Q7: S&P-like weights instead.
3. **Raw weight:**
   - S chip → 0;
   - otherwise raw = base x (1 + k x stance), with k = 1 (GUESS).
   - So a fully Bullish area gets 2x base, an H area 0.75-1.25x base, and a negative-but-H area a little less
     than base.
4. **Minimum 3 areas:** if zeroing leaves fewer than 3 non-zero areas in Equities (2 in Fixed Income), restore
   the best-stance zeroed areas at 0.5 x base until the minimum is met. The hover says why.
5. **Locked rows** (user edits) keep their %. The unlocked rows are scaled so the bucket adds to 100%. If the
   locked rows already exceed 100%, Fill stops and shows "Locked areas add to 112%: lower one".
6. **Cap:** no area above **40% of the bucket** (spec 10's sector cap, unchanged). Excess is shared out pro-rata
   to uncapped, unlocked, non-zero areas, repeating up to 10 times.
7. **Floor:** an unlocked area under **3% of the bucket** (GUESS) is set to 0 and shared out (the minimum-areas
   rule still applies).
8. **Kept holdings:** an area's kept $ is counted first.
   - If kept $ is more than the area's fill $, the area shows "Kept holdings already exceed this area by $X".
     Its funds are not bought, and the excess comes **off the other unlocked areas pro-rata**, so the bucket
     total stays on target.
   - The kept floor from spec 10 still stops the bucket itself from going below its kept share.
9. Round shares to 0.1% for display. Dollars = share x bucket $.

Fill runs automatically the first time a bucket is opened and again on every change to the Quad buttons,
flavour or period, but **never overwrites locked rows**.

### S3 — Inside an area: which fund(s)
- **Funds per area:** usually 1 for a sector area. Broad US and Foreign get 2 when their share is at least 15% of
  the bucket (GUESS).
- **Pick rule** (bucket setting): Low volatility (default), Low beta or Momentum, scored as in spec 9 R2 but
  ranked only inside the area. If the top fund fails Momentum's "must be above its Trend line", the next one is
  tried. If none passes, the area's money stays in the area and the "Fund" cell shows "None qualifies → cash".
  It is **not** moved silently to another area.
- **Several funds in one area:** inverse-swing weights inside the area (spec 9 R3 step 1).
- **Final Call skip** (spec 9 R6) applies here. A skipped fund is replaced by the next in the same area. If the
  area has no other fund, its money goes to cash for that area, with the reason shown.

### S4 — Flavour filters (Equities only, optional)

| Flavour button | Includes funds tagged (any of) | Note |
|---|---|---|
| All | no filter | default |
| Defensive | Def, Lo-B, Div | |
| Offensive | Cyc, Hi-B, Small | |
| Value | Val | needs P/E; many funds have none, so Task 1 checks coverage |
| Growth | Sec | same |
| Mid | Mid | |
| *(Mom)* | not offered | RSI > 65 today; use the Momentum pick rule instead |

- Tags come from the same `drv_macro_score.style_stances` labels Universe uses. Abbreviations are reused from
  Universe's `STYLE_TAG_ABBR` (Cyc, Def, Div, Hi-B, Lo-B, Mid, Mom, Sec, Small, Val).
- **Within a flavour the tags combine with OR.** This differs from Universe's single-tag match, so the button
  hover lists the tags it includes.
- One flavour at a time (single-select, like Universe's Style row).
- A flavour that leaves fewer than 4 eligible funds in the bucket shows "Only N funds have this flavour" and
  still runs. Areas with no flavoured fund drop out of the fill (rule S2.1), unless they hold a kept position.
- Tags are read on the **build day** and frozen with the model. A fund later losing a tag changes nothing.

### S5 — Fixed Income
- Same table and rules. Areas = bond types. Pick rule options: Core (all funds in the area, inverse-swing) or
  Low volatility.
- If the bucket has only 1-2 eligible areas, the table shows them with no fill, and the minimum-areas rule does
  not apply.

### S6 — How it combines with spec 10
**Order of operations:**
1. Account value.
2. Mix preset, or the user's sliders; for the Quad-tilted preset, apply the Quad tilt.
3. Risk Dial trims the risky buckets into Cash.
4. Each bucket's $.
5. Kept floors.
6. **Area fill inside each bucket.**
7. Funds inside each area.
8. Final Call skip.
9. Whole shares, with the leftover to that bucket's cash line.

Other interactions:
- **Risk Dial** never changes area shares, only bucket totals. Area $ shrink proportionally.
- **Quad-tilted preset and area fill** use the same stance function (asset-class rows for the bucket tilt,
  sector or bond-type rows for areas). The Q buttons affect both, so the bucket tilt and the areas always use
  the same Quad assumption.
- **Accept** stores: the area table (stance, base, fill %, final %, locked yes/no), the Q buttons, the flavour and
  the pick rule. The detail page shows them frozen, with today's live chips next to them as "now". That is a
  display only; nothing changes.
- **Back-test** (spec 9 R10): the area fill is replayed with the Quad mix as stored at each past date. That
  history only exists from 2026-09, so "By area" back-tests show "Not enough Quad history" for most periods.
  The flavour filter and the pick rule replay normally.
- **Allocation drift card** (spec 10) gains a second level: click Equities to see target vs model-now vs
  account-now per area. Amber when 5 points or more apart.

### Example (ILLUSTRATIVE)
F-A, Balanced, Risk Dial x0.70, so Equities is 42% = $173,200. 3M window Q2 71% / Q1 29%. Flavour All. Pick rule
Low volatility. 13 eligible areas, so base = 7.7%.

| Area | Chip | Stance | Raw (base x (1+stance)) | Fill % of Equities | $ | Fund |
|---|---|---|---|---|---|---|
| Information Technology | B | +1.00 | 15.4 | 15.6 | 27,000 (kept AAPL / MSFT $61,200, so buys 0; excess $34,200 taken off the others) | — |
| Industrials | B | +1.00 | 15.4 | 15.6 | 27,000 | XLI |
| Financials | B | +1.00 | 15.4 | 15.6 | 27,000 | XLF |
| Consumer Discretionary | B | +0.42 | 10.9 | 11.1 | 19,200 | XLY |
| Materials / Energy / Comm. Svcs | H | 0 to +0.2 | 7.7-9.2 | ... | ... | XLB / XLE / XLC |
| Health Care, Staples, Real Estate | S / H | ... | ... | ... | ... | ... |
| Utilities | S | -1.00 | 0 | 0 | 0 | — |
| Broad US | H | +0.10 | 8.5 | 8.6 | 14,900 | SPY |
| Foreign | H | +0.10 | 8.5 | 8.6 | 14,900 | EFA |

Rows marked "..." are left open on purpose; the real table comes from Task 1.

### Edge cases
- **All areas S** (for example "assume Q4"): the minimum-areas rule keeps the 3 best at 0.5 x base. A banner
  says "Every area is a Sell under Quad 4. Consider a lower Equities share in step 2."
- **The account holds a sector fund that the fill zeroes:** shown in "vs your account" as "Held, not in model",
  unless it is kept.
- **An area whose only fund is missing from today's TOS export:** that area's money goes to cash, with the reason
  shown.
- **User locks rows adding to exactly 100%:** Fill does nothing, and a note says so.
- **Two areas tie on stance:** they get the same share.

---

## Files likely touched (in addition to spec 10's list)
- `db/seeds_portfolio_builder.sql`: `ref_pb_universe.area` uses the area names above. Each area also carries its
  `ref_quad_outlook (category, sub_category)` key, so the stance is a join and not a second map.
- `etl/derive_model_portfolio.py`: pure functions `area_stance`, `fill_areas` (base, tilt, zero, minimum, locks,
  cap, floor, kept), `pick_in_area`. Unit tests for each rule above.
- `etl/derive_macro.py`: no change. Reuse `window_weights`, `build_effective_distribution` and the outlook lookup.
- `api/routers/builder.py`: preview body gains, per bucket: `split_mode` (area | recipe), `quad_override` (list),
  `flavour`, `pick_rule`, `locked_areas` {area: pct}. Response gains, per bucket, the area rows (stance, chip, q1-q4
  outlooks, base, fill, final, funds, notes).
- `api/routers/universe.py`: none. Builder calls the same `ref_quad_outlook` read, or reuses
  `/api/universe/quad-factors`.
- `web/_common.js`: **move** (not copy) `STYLE_TAG_ABBR`, `QUAD_IS_BULLISH / QUAD_IS_BEARISH` and the
  `actionSide` / `macroSide` groupings out of `web/universe.js` into small shared helpers. `universe.js` then
  uses them from there; a tiny behaviour-neutral change, and it needs a cache-bust bump.
- `web/styles.css`: if the `uv-factor-pill` and `uv-color-dot` styles live in `universe.html`, move them to
  `styles.css` so Builder can use them.
- `web/builder.js` / `builder.html`: step 3 settings, the area table with editable locked rows, Fill / Reset, and
  the area level of the drift card.

## Phasing (replaces spec 10's list; one afternoon each)

| # | Task | Change vs spec 10 |
|---|---|---|
| 1 | Data check + fund list (+ area and outlook key per fund; style-tag coverage per fund; check that every area has an outlook row) | + areas / tags |
| 2 | Measures + pick rules (Low vol, Low beta, Momentum, Core) as pure functions + `drv_pb_score` | Quad recipe removed |
| 3 | Build engine incl. `area_stance` + `fill_areas` + preview API | + area fill |
| 4 | Builder page: account, mix, step-3 area table (chips, Q buttons, flavours, Fill / Reset, locks) | + area UI; shared-helper move |
| 5 | Accept / freeze + marks + list view with accounts | same |
| 6 | Detail: drift card with the area level + "vs your account" | + area level |
| 7 | Back-test | area mode labelled "limited Quad history" |
| 8 | Warnings, promise check, review / roll / close | same |

### Worth reconsidering
- **Using both "By area" and a flavour filter at once** can leave very few funds: for example Defensive under
  Quad 2 zeroes most defensive sectors. The UI warns, but you may prefer flavours to be available only in
  "By recipe" mode. I kept both because you asked for both; it can be dropped later with no data change.
- **Universe's own asset-class grouping disagrees with the Portfolio pie** (see Notes). Fixing Universe to use
  the pie's map would make all three screens agree. That is a separate small task, not part of the Builder.

### Notes (found during the review; not changed)
- **Universe "Asset" view vs the Portfolio pie.** Universe's Asset view groups by
  `drv_actionable.real_asset_class`, the broker's tag (`api/routers/universe.py::_norm_asset_class`; about 43%
  Unclassified). The Portfolio pie groups by `_category_axis_map` (`drv_ma.asset_class`, falling back to
  `ref_sector`). The pie's own docstring says it moved off `real_asset_class` because the two disagree. The
  Builder follows the pie.
- Universe's Style row lists only the tags present in the data. If no symbol currently has, say, Val, that button
  is missing there. The Builder shows all flavours and greys out empty ones.

## Open questions
Pending from spec 10:
1. One running model per account, where accepting a new one replaces it? (Recommend yes.)
2. Keep-as-is list per account, with an LT Hold helper? (Recommend yes.)
3. Cash = what the pie counts; short bond funds stay in Fixed Income? (Recommend yes.)
4. Confirm All-weather 30/55/7.5/7.5/0 and the ±25% Quad tilt (GUESSes), kept in an editable table.
5. Account type on each account, used only for the taxable gain line and the 401k paper-only mode? (Recommend yes.)
6. Whole book preview only? (Recommend yes.)

New:
7. Equal starting share per area (recommend) or S&P-like sector weights?
8. Sell areas to zero with a 3-area minimum (recommend), or halve them?
9. Several Quad buttons: AND like Universe (recommend), or an average?

Data note: read-only database queries were blocked; all numbers are illustrative.

## Status
READY_FOR_DEV
