# Macro Areas — design

Turn the existing market-context data into a top-down, money-making **decision
layer** on the Actionable screen. Concept lifted from a weekly macro note
(Hedgeye-style): the *areas* are a stable scaffold; each carries a directional
**stance** across two durations (immediate **TRADE**, intermediate **TREND**),
disciplined by a **risk range** (trim at the top, add at the bottom). The prose
changes weekly; the framework doesn't. We reproduce the framework from our own
daily TOS/Y data — **no FRED for price areas, no new feed.**

---

## What already exists (do NOT rebuild)

| Layer | Where | Gives us |
|---|---|---|
| Three market ribbons | `web/market_bar.js` → `/api/marketbar`, `/api/rr-bar` | Per-symbol chip: risk-range bar (`drv_rr.lrr/trr`), outlook color, day %, VIX vol zones (`ref_vol_threshold`), candle, tooltip |
| Econ panel | `#econPanel` (`buildEconHtml`) → `/api/macro` | FRED econ values (CPI/jobs/rates) — the only place FRED still earns its keep |
| Regime band | `#macroBand` (TASK_74) → quad tables | Month · Quarter · Favoring tilt |
| MACRO column | `drv_actionable.macro_value` | Per-symbol quad overlay (SA/STM/…) |
| Correlation matrix | TASK_60 (`drv_usd_correlation`, `/api/correlations`) — **status to confirm** | USD vs SPX/Gold/BTC/oil rolling corr |

The ribbons already wire essentially every commentary area: USD `$DXY`; indexes
`SPX`/`$COMP`/`RUT`; vol `VIX`; curve `DGS2`/`TNX:CGI`/`TYX:CGI`; credit
`HYG`/`LQD`; commodities `/CL`/`/BZ`/`/GC`/`/HG`/`/NG`/`/SI`; crypto `/BTC`; FX
crosses; sectors `XLE…XLY`; tech megacaps; thematic ETFs.

**Conclusion:** the data + per-chip viz are done. The gap is *synthesis*.

---

## The gap — a synthesis / decision strip

A compact, area-organized card that reads the existing data and answers "what do
I do?" It adds four things the ribbons don't:

1. **Explicit stance per area** — Long / Short / Neutral, not just an outlook color.
2. **Dual-duration call** — TRADE vs TREND, so divergence (trend up, trade
   rolling) is visible.
3. **Extremes → action** — which members are at the top of range (trim) or
   bottom (add).
4. **One-line top-down read** — regime + USD switch + breadth of overbought →
   a posture (press / hold / harvest / raise cash).

---

## Areas (stable scaffold) → member proxies (already loaded)

| Area | RR/outlook members (`drv_rr`/`hist_rr`) | Dual-duration members (`drv_technicals`) |
|---|---|---|
| USD | `$DXY` | `UUP` |
| US equities / breadth | `SPX`, `$COMP`, `RUT` | `SPY`, `QQQ`, `IWM` |
| Volatility (gauge only) | `VIX` (vol zones) | — |
| Rates / curve | `DGS2`, `TNX:CGI`, `TYX:CGI` (2s/10s/30s) | `TLT`, `IEF` (tradable duration) |
| Credit (risk-on/off) | `HYG`, `LQD` | — |
| Commodities | `/CL`, `/BZ`, `/GC`, `/HG`, `/NG`, `/SI` | `GLD`, `SLV` |
| Crypto | `/BTC` | `IBIT`, `MSTR`, `BITO` |
| Global equities | `$SSEC`, `GDAXI:DE`, `N225:JP` | `EEM`, `EWZ`, `EWG`, `EWM` |
| Sectors (ranked) | `XLE…XLY` (outlook) | all 11 SPDRs ranked by TRADE/TREND |

**Why two member lists per area:** the futures/index/FX/curve tickers (`/CL`,
`$DXY`, `DGS2`, …) have **no `drv_technicals` row** (confirmed: DEV_HANDOFF
TASK_76 — `USO`, `$DXY`, `$VIX` etc. carry no `a_trade_value`/`a_trend_value`).
They give a risk-range + outlook stance but **not** a dual-duration call. The
ETF/stock members do have technicals, so they carry the TRADE/TREND detail. The
design uses each where it's available and never fakes the missing one.

---

## Computation (all from existing columns)

Stance map: Bullish +1 · Neutral 0 · Bearish −1.

```
# per member with technicals (drv_technicals + drv_quote)
trade_sig = sign(last_price - a_trade_value)     # immediate-term
trend_sig = sign(last_price - a_trend_value)     # intermediate-term

# per member with only RR (drv_rr + outlook)
outlook_sig = stance(outlook)                    # Bullish/Neutral/Bearish
rr_pos = (last_price - lrr) / (trr - lrr)        # 0..1 position in risk range

# area roll-up
area_stance   = sign( Σ member_sig )             # Long / Short / Neutral
area_conv     = |Σ member_sig| / n               # conviction 0..1
area_rr_pos   = median(member rr_pos)            # where the area sits in range
extremes      = members with rr_pos ≥ HOT (trim) or ≤ COLD (add)
```

Volatility is a **gauge, not a stance** — render the `ref_vol_threshold` zone
(investable / chop / elevated), no Long/Short.

Curve is a **slope read**, not a single stance: `TNX − DGS2` (10s2s) direction +
duration call from `TLT`/`IEF`. Label it "duration / curve," never a fake 2-sided
crossover.

**Top-down read (one derived sentence):**

```
posture = f( regime(quad), usd_switch, count(area_rr_pos ≥ HOT), breadth(area_stance) )
```

e.g. *"Trend up but stretched — 5 of 7 equity areas > 85% of range; harvest
extended longs, nothing oversold to buy, raise cash."*

---

## Proof on real data (18 Jun 2026, from DEV_HANDOFF TASK_76)

Already computed from your pipeline — the synthesis works:

| Area member | TRADE | TREND | rr_pos | Read |
|---|---|---|---|---|
| SPY | bear (747<754) | bull (>629) | 56% | Long, rolling near-term |
| QQQ | bull | bull | 76% | Long |
| IWM | bull | bull | **91%** | Long — overbought, trim |
| EEM | bull | bull | **88%** | Long — overbought, trim |
| XLK | bull | bull | **87%** | Long — overbought, trim |
| TLT | bull | bull | **>100%** | Duration extended |
| GLD | bear | bear | 42% | Short |

Read: intermediate **uptrend intact** (risk-on), but **broadly stretched** —
harvest the extended longs, nothing oversold to add. Exactly the note's
discipline, derived from your data.

---

## Surfacing

- **New collapsible card** "Macro read" in the existing market-context area of
  `/actionable` (with the econ panel + regime band — not a new screen, not new
  ribbons). Self-contained `web/macro_areas.js`, reuses `macro-tile` / `rr-rb`
  CSS so it can't disturb actionable logic.
- One row per area: name · **stance pill** · TRADE/TREND chips (or "gauge" /
  "curve") · area risk-range bar with median marker · extremes (trim/add symbols).
- **Master-switch row** from `drv_usd_correlation` (TASK_60) when present: USD ↔
  SPX/Gold/BTC/oil, colored by the TASK_60 thresholds. Gate behind TASK_60.
- **Top-down read** as a single highlighted line at the top of the card.

## Backend

Thin endpoint `GET /api/macro-areas?date=D` that does the roll-up server-side
(keeps stance logic next to the MACRO-column logic, not duplicated in JS):
reads `drv_rr`, `drv_technicals`, `drv_quote`, `ref_vol_threshold`, the area→member
map (a new `ref_macro_area` seed, mirroring `_RR_META`), returns per-area
`{stance, conviction, trade, trend, rr_pos, extremes[], members[]}` + the derived
`top_down` sentence. No new ingest; reuses the anchor-date pattern.

## Edge cases (locked)

- Members without technicals → RR/outlook stance only; duration shown as "—", not faked.
- `VIX` → zone gauge, no stance. Oil → prefer `/CL` (has RR/outlook) over `USO` (price-only).
- Sector strings have case drift ("Health care" vs "Health Care") → group case-insensitively (DEV_HANDOFF note).
- Exclude NULL `asset_class` / NULL-signal rows from area roll-ups.
- FRED stays **only** for the econ regime axes (CPI/PCE/jobs) feeding the quad — no price area uses it.

## Tunables (`ref_settings`)

`macro_area_hot_pct` (0.85), `macro_area_cold_pct` (0.15), `macro_area_conv_min`,
per-area member weights, correlation color thresholds (reuse TASK_60).

## USD correlations card (TASK_60 + 52-wk stats)

Reproduces the "Key $USD Correlations" table the user supplied: rolling Pearson
correlation of **USD** vs **SPX, Brent oil, CRB index, Gold, Bitcoin** across
**15 / 30 / 90 / 120 / 180** trading-day windows, **plus** a 52-week
rolling-30D stats block: **High, Low, % time positive, % time negative**.

- **Placement:** standalone collapsible **"USD correlations"** card in the
  market-context band, next to the Macro read card. The Macro read **master-switch
  row** is a one-line summary (USD ↔ SPX/Gold/BTC) that expands into this card.
- **Stats block math:** compute the trailing **252-day series of 30D
  correlations**; `High`/`Low` = max/min of that series, `%pos`/`%neg` = share of
  days the 30D corr is > 0 / < 0. Needs ≈ 282 trading days of history.
- **History (the real work):** `drv_quote` holds only 105 days (from 2026-01-30)
  and lacks **Brent** and **CRB** entirely. So build the **Stooq daily-CSV
  backfill feed** (TASK_60: `etl/fetch_quotes.py`, keyless, throttled like
  `fetch_macro`) → new `hist_quote_daily` (long history) → coalesce with TOS
  `$DXY` (TOS wins on overlap) → `drv_usd_correlation`. Catalog of asset rows +
  source priority in new `ref_corr_asset` (seed `db/seeds_corr.sql`).
- **Schema additions to TASK_60's `drv_usd_correlation`:** the 52-wk stat cols
  `roll30_high`, `roll30_low`, `roll30_pct_pos`, `roll30_pct_neg`.
- **API:** `GET /api/correlations?date=D` → rows + windows + stats, read straight
  from `drv_usd_correlation`.
- **Color thresholds (tunable):** green `r ≥ +0.50`; moderate-neg `−0.70 < r ≤
  −0.50`; strong-neg `r ≤ −0.70`; plain otherwise. NULL cells render "—" until
  enough history backfills the long windows.

Flow: `docs/diagrams/*` (Stooq → hist_quote_daily → drv_usd_correlation →
/api/correlations → card).

## Build sequence — two tracks

**Track A — Macro read card (ships first, no new history):**
1. `ref_macro_area` seed (area → member symbols + which list, GICS-11 sector
   filter, case-fix via `initcap(lower())`, skip `rr_pos` for the rate-×10
   tickers `DGS2`/`TNX`/`TYX`) + `/api/macro-areas` roll-up endpoint.
2. `web/macro_areas.js` card in the market-context area (reuse CSS) + top-down read.

**Track B — USD correlations card (needs the backfill):**
3. `ref_corr_asset` seed + `etl/fetch_quotes.py` Stooq feed + `hist_quote_daily`.
4. `drv_usd_correlation` derive (5 windows + 52-wk stats) wired into `derive_all`.
5. `/api/correlations` endpoint + `web/` USD correlations card; backfill long
   windows as history accrues.

Discovery complete: TASK_76 + TASK_77 (`DEV_HANDOFF.md`, both ALL_DONE) — all 47
proxies validated, column names + quirks pinned, WoW confirmed, TASK_60 confirmed
not-yet-built.
