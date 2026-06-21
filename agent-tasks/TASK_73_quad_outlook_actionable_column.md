# TASK_73 — Quad-outlook columns on the Actionable screen

## Goal

Add the macro **quad regime outlook** for each symbol to the Actionable screen as
**two new columns** — a **Monthly** quad outlook and a **Quarterly** quad outlook —
each rendered as a buy / sell / neutral badge.

Source data already exists but is currently dormant:

- `ref_quad_periods` (HQds tab) — maps each calendar period to a quad. Columns:
  `period_type` ('monthly' | 'quarterly'), `start_date`, `end_date`, `quad`.
- `ref_quad_outlook` (HQuad tab) — per `(category, sub_category)` outlook under each
  regime. Columns: `category`, `sub_category`, `ticker`, `eco_sensitivity`,
  `quad1`..`quad4` (outlook text per regime). **Currently no reader anywhere in the
  codebase.**

> **DO NOT use `m_outlook`, `m_score`, `q_outlook`, `q_score`.** Per the user, these
> columns are off-limits. Both the Monthly and Quarterly columns must be derived
> **only** from the active quad (via `ref_quad_periods`) selecting `quad1..quad4`.
> Do not read or display those four columns anywhere.

The chain per symbol/date:
1. From `ref_quad_periods`, resolve the **active monthly quad** and **active
   quarterly quad** for the screen's as-of date `D`.
2. Map the symbol to a `ref_quad_outlook` row **by category** (see Decision 1).
3. Pick the `quadN` column matching each active quad → the outlook text.
4. Map outlook text → buy / sell / neutral and render two badge columns.

## Decisions already made by the user

- **Period:** **show both** — Monthly and Quarterly quad outlook columns.
- **Do NOT use** `m_outlook` / `m_score` / `q_outlook` / `q_score` (see banner above).

## The join — resolved from the workbook formulas (`docs/ma_columns_v2.csv`)

The original HQuad lookups reveal the real join key is **`sub_category` (HQuad column
B)**, NOT `category`. `category` (column A) is only the block label. HQuad is laid out
in row-blocks and matched on column B:

- **Asset-class block:** `XLOOKUP(AssetClass, HQuad!$B$2:$B$9, …)` → match the symbol's
  **asset class** to `sub_category`.
- **Equity-sector block:** `IF(AssetClass="Equities", XLOOKUP(Sector,
  HQuad!$B$10:$B$23, …), assetClassOutlook)` → for equities, match the symbol's
  **sector** to `sub_category`; otherwise use the asset-class outlook.
- Rows 24–39 are style factors (Growth/Scale/Value/…) — out of scope for this task.

Mapped to the Actionable row (fields already present: `real_asset_class`, `sector`):

```
quad outlook for a symbol =
  IF real_asset_class = 'Equities' AND a sector match exists:
      ref_quad_outlook row WHERE sub_category = a.sector            (equity-sector block)
  ELSE:
      ref_quad_outlook row WHERE sub_category = a.real_asset_class  (asset-class block)
```

Use `category` (col A) only to disambiguate which block a `sub_category` belongs to if
sub_category values are not unique across blocks.

NOTE: `docs/ma_columns_v2.csv` maps these to a `drv_cat_quad_outlook` table, but that
table is **never built** (no derive, not in `baseline.sql`) — there is no precomputed
shortcut; do the join live in the enrichment query.

## Confirmation queries the DEVELOPER runs first (then proceed)

The join above is derived from the workbook formulas; confirm the string values line
up in the live DB before coding. Run these and record results in `DEV_HANDOFF.md`:

```sql
-- Block labels + lookup keys in HQuad
SELECT DISTINCT category, sub_category FROM ref_quad_outlook ORDER BY 1,2;

-- Asset-class labels carried on Actionable rows (must match sub_category in the
-- asset-class block) and sector labels (must match the equity-sector block)
SELECT DISTINCT asset_class FROM drv_technicals ORDER BY 1;     -- = real_asset_class
SELECT DISTINCT sector      FROM drv_symbols   ORDER BY 1;      -- or wherever sector lives

-- Coverage sanity: how many of today's actionable symbols get a match each way
-- (fill :d with the anchor date)
```

Confirm:
1. `real_asset_class` values ⊆ `ref_quad_outlook.sub_category` (asset-class block).
2. For equities, `sector` values ⊆ `ref_quad_outlook.sub_category` (equity block).
3. Whether `sub_category` is unique across blocks; if not, also filter by `category`.
   **Record the final join (and any value-normalization, e.g. trim/case) in
   `DEV_HANDOFF.md`.**

**Decision 2 — quad value format.** Confirm how `ref_quad_periods.quad` is stored
(`'1'` vs `'Quad 1'` vs `'Quad1'`) so the `CASE` that selects `quad1..quad4` matches.
`SELECT DISTINCT period_type, quad FROM ref_quad_periods;`

**Decision 3 — outlook text → buy/sell/neutral.** Inspect the distinct text values
to build the badge map:
`SELECT DISTINCT quad1 FROM ref_quad_outlook UNION SELECT DISTINCT quad2 ... ;`
(only `quad1..quad4` — NOT `m_outlook`/`q_outlook`). Map each label to
`buy` / `sell` / `neutral`. Put the mapping in JS so it reuses the existing
`actionDisplay()` color classes (green / red / grey). Unknown/blank → neutral/blank.

## Implementation

### 1. API — `api/routers/dash.py :: get_actionable()`

The main query already runs ~11 LEFT JOINs and the code comments warn about staying
under the Postgres GEQO threshold (12). **Do NOT add a 12th join to the main query.**
Instead:

- Resolve the two active quads once (two cheap queries on `ref_quad_periods`,
  reusing the pattern in `/api/dashboard/quads` in `api/routers/health.py`):
  ```sql
  SELECT quad FROM ref_quad_periods
  WHERE period_type = :pt AND :d >= start_date
    AND (:d <= end_date OR end_date IS NULL)
  ORDER BY start_date DESC LIMIT 1;   -- run for 'monthly' and 'quarterly'
  ```
- Build a per-symbol quad-outlook lookup in a **separate query** and merge into the
  result rows in Python (same enrichment pattern already used for other derived
  fields). For each row, attach:
  - `quad_m_outlook`  — text of the `quadN` column for the active monthly quad
  - `quad_q_outlook`  — text of the `quadN` column for the active quarterly quad
  - (optional) `quad_m`, `quad_q` — the active quad numbers, for tooltips.
  Keyed by the sub_category join above (`real_asset_class`, falling back from
  `sector` for equities). Use the resolved quad numbers to choose the `quadN`
  column via a `CASE` in that separate query.
- Keep this resilient: if `ref_quad_periods` has no row for `D`, or the symbol has no
  category match, return blank/None (no error).

### 2. View template — `web/actionable.html`

Add two `<th>` headers near the existing classification columns (after
`Other Sources`, alongside `Sector` / `Real Asset Class`):
`Quad (M)` and `Quad (Q)`.

### 3. Grid + CSV — `web/actionable.js`

- Add a small text→side map and a badge renderer, e.g.:
  ```js
  function quadBadge(text) {
    if (!text) return '<span style="color:#cbd5e1">—</span>';
    const side = QUAD_OUTLOOK_SIDE[text.trim().toLowerCase()] || 'neutral'; // buy|sell|neutral
    // reuse actionDisplay() color classes for green/red/grey
    ...
  }
  ```
- Render `r.quad_m_outlook` and `r.quad_q_outlook` in the two new grid cells.
  Optional hover title showing the active quad number (`Quad 2`, etc.).
- Add both columns to the `exportCsv()` `cols` array (around line 2245), e.g.
  `['Quad M', r => r.quad_m_outlook || '']`, `['Quad Q', r => r.quad_q_outlook || '']`.
- Match column ordering between the `<th>` row, the cell render, and CSV.

## Files expected to change

- `api/routers/dash.py` (get_actionable enrichment)
- `web/actionable.html` (two `<th>`)
- `web/actionable.js` (badge map + cell render + CSV)
- No schema change (tables already exist). No new derive.

## How to verify (tester / dev sanity)

1. **Period resolution.** For today's `D`, confirm the monthly and quarterly quad
   resolved from `ref_quad_periods` match `/api/dashboard/quads` for the same date.
2. **API payload.** `GET /api/actionable?date=<D>` returns `quad_m_outlook` and
   `quad_q_outlook` on each row; spot-check 3 symbols against a manual lookup:
   active quad → `ref_quad_outlook.quadN` for that symbol's category.
3. **Ambiguity rule.** Pick a category with multiple sub_categories; confirm the
   value shown follows the rule recorded in `DEV_HANDOFF.md` (no silent arbitrary pick).
4. **Badge mapping.** Every distinct outlook label renders as the correct side
   (buy=green / sell=red / neutral=grey); unknown/blank → blank, no crash.
5. **No regression.** Row count and existing columns unchanged; the main query still
   plans without crossing the GEQO join limit (no added join). CSV export includes
   the two new columns in the right order.
6. **Edge cases.** A symbol with no category match, and a date with no
   `ref_quad_periods` row, both render blank rather than erroring.

## Notes

- Reuse `/api/dashboard/quads` logic in `api/routers/health.py` for period resolution
  rather than re-deriving it.
- Keep all SQL statements ≤ 965 bytes (CLAUDE.md convention #7).
- Do not commit/push — user commits from Windows after review.
