# TASK_115 — Market panel consolidation, part 1: backend payload

Source: `docs/market_panel_consolidation_design.md` (read it first).
Part 1 of 2 (115 backend → 116 frontend). This task must leave the UI
looking exactly as it does today — the rail simply ignores the new fields
until TASK_116 consumes them.

Goal: make `/api/macro-areas` a superset of what the three market tapes
render, so the frontend merge in TASK_116 needs no second fetch.

Files expected to change: the `/api/macro-areas` endpoint (locate via
`grep -rn "macro-areas" api/`), its supporting queries, possibly a seed for
area membership (`ref_*` table or in-code membership list — follow however
the existing areas are defined), `tests/` additions.

## Confirmed decisions (user, 2026-07-04)

- **Hybrid** consolidation: one mini-tape survives, rail absorbs the rest.
- Side panel **pinned by default** — accepted (fresh profiles now show the
  260px rail).
- `/` and `/portfolio` lose tape bars 2/3 with no panel equivalent —
  **accepted**; the mini-tape is the only market context there by design.

## Preflight — mini-tape instrument availability (do FIRST, before item 1)

TASK_116's mini-tape renders exactly these 8 instruments:
`SPX · VIX · DXY · GC · WTI · 10Y · HY · BTC`. Before any code, dump the live
keys and confirm each is reachable, then record the exact identifiers in
`DEV_HANDOFF.md` for TASK_116 to consume verbatim:

- `SPX`/`VIX`/`DXY`/`GC`/`WTI` → confirm `metric_key` in `/api/marketbar`.
- `10Y` → confirm the symbol in the `/api/rr-bar` **Rates** group.
- `HY` → confirm the symbol in the `/api/rr-bar` **Credit** group.
- `BTC` → confirm it is exposed by `/api/marketbar` **or** an `/api/rr-bar`
  group; if it is exposed by neither, flag it in `DEV_HANDOFF.md` and propose
  the nearest available crypto key (do not silently drop it).

Any instrument not found is a blocker to log, not to work around.

## Items

1. **Per-member enrichment.** For every member row that `/api/macro-areas`
   returns, add: `open`, `high`, `low` (for the 7×14 candle; source =
   `drv_quote`/`hist_y` same as `/api/rr-bar` uses), and ensure `pct_change`
   and `last` are present for all members (some currently only carry
   `rr_pos`). Reuse the exact source logic from `/api/rr-bar` — factor a
   shared helper if that avoids duplication, don't copy-paste.
2. **Vol thresholds.** Volatility-area members get `vol_low` / `vol_high`
   (same source as `/api/marketbar` items' fields of the same name) so the
   frontend can render the 3-zone bar per instrument.
3. **Credit area.** Add a Credit area (HY, IG, HYSPRD — match the symbols
   the rr-bar 'Credit' group serves). Include an `inverted: true` flag on
   members whose color convention flips (HY spread up = red), mirroring
   market_bar.js's `INVERTED` set, so the client doesn't need its own list.
4. **Tape-only instruments.** Ensure the rail universe covers what tape
   bars 1–3 show and the rail currently lacks — check membership for: vol
   pairs (VXN, VXD, RVX, GVZ, OVX), futures/commodities (GC, WTI, BZ), and
   anything in the rr-bar Tech/ETFs/Indexes/FX groups missing from the
   existing areas. Add to the appropriate existing area (vol pairs →
   Volatility; GC/WTI/BZ → Commodities; etc.) — do NOT create new areas
   beyond Credit.
5. **Payload hygiene.** New fields are additive and nullable; existing
   consumers (`macro_areas.js`) must render identically before/after
   (verify by diffing the rendered rail HTML for one date, or at minimum
   confirming no console errors and same row counts).
6. **Tests.** Add a durable test (behavior/schema per the new test policy —
   no point-in-time values): response contains the new keys for a sampled
   member; Credit area present; inverted flag set for HY/HYSPRD.

## Guardrails

- SQL ≤ 965 bytes per statement (convention #7); SQLAlchemy + psycopg only.
- If membership lives in a `ref_*` table: seed via `db/seeds_*.sql`,
  idempotent, `python -m db.init_db` twice must be clean.
- No frontend changes in this task.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. `GET /api/macro-areas?date=<D>`: pick one Major Markets member → has
   `open/high/low/last/pct_change`; one Volatility member → has
   `vol_low/vol_high`; Credit area present with HY carrying
   `inverted: true`.
2. Coverage check: every symbol rendered by tape bars 1–3 today (dump
   `/api/marketbar` item keys + `/api/rr-bar` group members) appears in
   some `/api/macro-areas` area. List any deliberate exceptions in
   `DEV_HANDOFF.md`.
3. Load /actionable with the side panel pinned: rail renders exactly as
   before (row counts per section unchanged except new members, no console
   errors).
4. New tests pass; `python -m db.init_db` idempotent if a seed was added.
