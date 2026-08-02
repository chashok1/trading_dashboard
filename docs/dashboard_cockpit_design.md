# Dashboard Cockpit — design

**Status:** PROPOSAL v2, awaiting sign-off. Nothing handed to the developer agent.
**Date:** 2026-08-01
**Supersedes:** `docs/dashboard_attention_panel_design.md`

Rebuild of `/` (`web/index.html` + `web/app.js`) from a ticker dump into a **daily
risk cockpit**: one screen that answers *how much risk should I take today, what
changed, where is my money, and what should I do about it.*

v2 rewrite: v1 was built around a generic "unusual move" detector. After inventorying
the Actionable screen and the live data, the design is re-centred on **Hedgeye risk
ranges** — the thing the user actually trusts — with statistics used only where risk
ranges don't reach.

---

## 0. The headline finding

The user listed 14 things he wants to see. **Nine of them are already in the database
and simply are not rendered on any screen.** Three need data he already pays for
(ThinkOrSwim market internals). Only two need an outside source.

This is not a data problem. It is a **presentation and aggregation** problem.

| # | What the user asked for | Status | Where it already is |
|---|---|---|---|
| 1 | Market situation graph | ✅ HAVE | `hist_msr` — MSR image, ingested daily from Hedgeye email. On Actionable only. |
| 2 | **Dealer gamma** | ✅ HAVE | `hist_msr.gamma_throttle` — a market-level dealer-gamma scalar, **already ingested**, rendered as small grey text on Actionable. |
| 3 | SPX at top of risk range → stocks fall | ✅ HAVE | `drv_rr.lrr/trr` + `rr_pos`; `is_hot` at ≥0.85 already computed server-side. Never aggregated, never on `/`. |
| 4 | Bond yields near a level that matters (5%) | ✅ HAVE | `TNX:CGI` risk range in `drv_rr`; `DGS10` in `hist_macro`. |
| 5 | CPI above expected → stocks fall | ⚠️ PARTIAL | Actual: `CPIAUCSL`/`CPILFESL` in `hist_macro`. **Expected: Hedgeye Inflation Nowcast, already arriving by email.** |
| 6 | Unemployment above expected | ⚠️ PARTIAL | Actual: `UNRATE`/`PAYEMS`/`ICSA`. No expected — and no free consensus exists. |
| 7 | SPX volatility discount | ✅ INPUTS HAVE | `VIX` + your own SPX daily OHLC. Nothing computes it yet. |
| 8 | KOSPI → US chip stocks | ❌ MISSING | Not tracked. Free via Yahoo; you already run `etl/yahoo_fetch.py`. |
| 9 | Oil disruption via risk ranges | ✅ HAVE | `/CL`, `/BZ` risk ranges + `OVX:CGI` with 30/50 thresholds. |
| 10 | MOVE index | ✅ HAVE | `MOVE:GIF`, threshold 100/120. **Has a live display bug** — see §8. |
| 11 | Cross-asset / cross-vol impact | ✅ INPUTS HAVE | 7 vol gauges + every underlying, all with risk ranges. Nothing correlates them. |
| 12 | Sector performance over periods | ⚠️ PARTIAL | Sector *breadth* and 1-day %chg exist. **Multi-period returns do not.** |
| 13 | Market volume | ⚠️ PARTIAL | Per-symbol volume yes. Market-wide none — but ToS publishes it and you own ToS. |
| 14 | Commodities / metals / gold / credit via risk ranges | ✅ MOSTLY | `/GC /SI /HG /NG /CL /BZ`, `HYG`, `LQD` all carry risk ranges. Ag grains missing — **recommend skipping**, see §8. |

**Free wins sitting unused right now** (data already ingested, display disabled or absent):

- `BAMLH0A0HYM2` — the real high-yield **spread** is enabled in `hist_macro`, but the
  `ref_market_metric` `HY` row is disabled and the tape's "HY" tile actually shows the
  **HYG ETF** instead. You are looking at an ETF price where you think you see a spread.
- `T10Y2Y` — the **2s10s yield curve** is being fetched into `hist_macro` every day, and
  its `ref_market_metric` row `T2S10` is disabled. Nothing displays it.
- `/api/macro-areas` already computes and returns `top_down` (a posture sentence),
  `extremes_hot[]`, `extremes_cold[]`, `stance`, and `conviction` per area — **and
  nothing renders any of them.** The only consumer is dead code.

---

## 1. Design contract

| # | Rule | Why |
|---|---|---|
| **C1** | **Silence is the default.** Nothing abnormal → one quiet line, not an empty box. | "If normal, I don't want to see it." |
| **C2** | **Describe, never narrate.** State what moved and what it historically co-moves with. Never invent a cause. | The system has prices, not order flow. "Never hallucinate." |
| **C3** | **Risk ranges first, statistics second.** Where Hedgeye publishes a range, the range *is* the threshold. Z-scores are used only for instruments with no range and for "is this move unusual for *this* instrument." | The user trusts Trade/Trend/risk ranges. Deterministic and explainable beats clever. |
| **C4** | **Regime governs SIZE, not DIRECTION.** Everything on this screen adjusts how much exposure to carry. It never issues a buy or sell on a name. | `docs/actionable_playbook.md` §5 measured the broad signal set as net-negative. A 21st opinion makes it worse. Sizing is where regime information actually pays. |
| **C5** | **Every market condition must name the holdings it hits.** | An alert without your exposure attached is a news ticker. |
| **C6** | **Decide here, act on `/actionable`.** | Prevents building a second Actionable screen. |

---

## 2. Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR + MINI-TAPE                                              (unchanged) │
├─────────────────────────────────────────────────────────────────────────────┤
│ ① RISK DIAL                                                                 │
│                                                                             │
│      RISK BUDGET  35 / 100        ●───────────────○─────────────○           │
│      "Half size. SPX at the top of its range with credit weakening."        │
│                                                                             │
│      TRIGGERED (4 of 12 gauges)                                             │
│        ▲ SPX 6,412 — 91% of risk range (LRR 6,180 / TRR 6,435)             │
│        ▲ HY spread 342bp — widened 18bp in 5 days                          │
│        ▲ MOVE 118 — chop,近 elevated (100/120)                              │
│        ◆ Dealer gamma throttle: NEGATIVE  (Hedgeye MSR, 07/31)             │
│      QUIET  VIX 14.2 · DXY 43% of range · Gold 55% · Oil 38% · 10Y 61% ... │
├─────────────────────────────────────────────────────────────────────────────┤
│ ② WHAT CHANGED TODAY — exception-only, hidden when nothing fires            │
│    ● Yen bid  /6J +1.9% (+3.1σ) · 10Y −9bp · Gold +1.4%                    │
│      Carry unwind pattern. Your exposure: $214k momentum/high-beta (18%)   │
│    ▲ XLE broke ABOVE its risk range (TRR 94.10, last 95.02)                │
│    ◆ CPI tomorrow 8:30am — Hedgeye nowcast 2.8% vs last actual 3.1%        │
├─────────────────────────────────────────────────────────────────────────────┤
│ ③ REGIME — quad path, one line, hover for all factors                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ④ FACTOR SCORECARD  [Sector] [Asset Class] [Style]                          │
│    allocation % · your return 1w/3w/1m/2m/3m · market · ADD/HOLD/TRIM       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⑤ TODAY'S SHORTLIST — 3 rows max, high-conviction subset only               │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⑥ HOUSEKEEPING — feeds, derives, econ, earnings. Red only when broken.      │
└─────────────────────────────────────────────────────────────────────────────┘
```

Removed: `#tickerSections` (the ~180-row grid) and the three standalone side cards.

---

## 3. Band ① — The Risk Dial

**This is the single most important element on the screen** and the direct answer to
"based on that I should be able to invest / hold / reduce."

### 3.1 What it is

One number, 0–100, meaning *what fraction of normal position size should I use today.*
It is a **count of broken gauges**, not a model. Every gauge is deterministic and
traceable to a published level — mostly Hedgeye risk ranges.

```
risk_budget = 100 × (1 − triggered_weight / total_weight)
```

### 3.2 The gauges

Each gauge is on/off. Weight reflects how reliably it has historically preceded
drawdowns — starting values below, all stored in a new `ref_risk_gauge` table so they
are tunable without a code change.

| # | Gauge | Fires when | Wt | Data |
|---|---|---|---|---|
| 1 | **SPX at top of range** | `rr_pos(SPX) ≥ 0.85` | 3 | `drv_rr` — **the user's #1 ask** |
| 2 | SPX below range | `rr_pos(SPX) ≤ 0.15` | 2 | `drv_rr` (opposite tail — buyable, not risk-off) |
| 3 | **Equity vol elevated** | `VIX` zone = elevated (>30) | 3 | `ref_vol_threshold` |
| 4 | Equity vol chop | `VIX` in 19–30 | 1 | " |
| 5 | **Bond vol elevated** | `MOVE` > 120 | 3 | " — **the user's MOVE ask** |
| 6 | **Credit stress** | `HYG` `rr_pos ≤ 0.15` **OR** `BAMLH0A0HYM2` widened ≥ 25bp over 10d | 3 | `drv_rr` + `hist_macro` |
| 7 | **Yields at a watched level** | `TNX` within 10bp of any level in `ref_level_watch` (5.00%, 4.50%, …) **OR** `rr_pos(TNX) ≥ 0.85` | 2 | `drv_rr` + new table — **the user's 5% ask** |
| 8 | Curve inverting fast | `T10Y2Y` fell ≥ 15bp in 5d | 1 | `hist_macro` — **currently fetched, never shown** |
| 9 | **Dollar strong** | `rr_pos($DXY) ≥ 0.85` | 2 | `drv_rr` |
| 10 | **Oil shock** | `rr_pos(/CL) ≥ 0.85 or ≤ 0.15`, **or** `OVX` elevated (>50) | 2 | `drv_rr` + `ref_vol_threshold` — **the user's oil ask** |
| 11 | **Vol discount gone** | `VRP = VIX − RV21 ≤ 0` (see §5) | 2 | new derive — **the user's vol-discount ask** |
| 12 | **Dealer gamma negative** | `hist_msr.gamma_throttle` negative/red | 2 | already ingested — **the user's dealer-gamma ask** |
| 13 | Breadth deteriorating | `% of your universe above 50-DMA` < 40% and falling 5d | 2 | self-computed (§6) |
| 14 | Gold vol elevated | `GVZ` > 32 | 1 | `ref_vol_threshold` |

Total weight 29. Four typical fires ≈ risk budget 65; the example in §2 shows a heavier day.

### 3.3 Why a dial and not a light

A binary "risk on / risk off" forces a decision the market rarely justifies. A budget
maps directly onto the thing the playbook already does — **AMT$ sizing**. The intended
use is literal:

> `today's size = AMT$ × (risk_budget / 100)`

That single line is the whole payoff of this screen. It turns market context into a
number that changes what you type into the broker.

| Budget | Reading | Action |
|---|---|---|
| 80–100 | Clear | Full AMT$ |
| 55–79 | Caution | 75% size, no new highest-beta adds |
| 30–54 | Defensive | Half size, exits only in flagged categories |
| 0–29 | Not investable | No new risk. Manage existing only. |

### 3.4 This already half-exists

`web/actionable.js::_regimeVerdictHtml()` (added 2026-08-01) already reads 8 gauges
from `/api/macro-areas` and prints `NOT INVESTABLE` / `CAUTION` at ≥3 flags. The Risk
Dial is that function, promoted to the landing page, extended from 8 to 14 gauges,
weighted, and converted from a label to a number. **Low new-concept risk — the pattern
is already live and working.**

### 3.5 Transmission map (C5)

Every fired gauge names what it hits, via a seeded `ref_gauge_transmission` table
(gauge → affected sector / asset class / style), so the dial resolves to *your* dollars:

```
▲ Bond vol elevated (MOVE 118)
  → hits: Utilities, Real Estate, long-duration Tech, TLT
  → your exposure: $186,000 = 15.8% of book
```

---

## 4. Band ② — What changed today

The Risk Dial is the *level*. This band is the *change*. Three kinds of item.

### 4.1 Risk-range events (primary — C3)

Deterministic, no statistics, straight from Hedgeye:

| Event | Condition |
|---|---|
| **Broke above range** | `last > trr` when it was inside yesterday |
| **Broke below range** | `last < lrr` when it was inside yesterday |
| **Trend flip** | `drv_rr.outlook` changed Bullish↔Bearish (already parsed as `trend_flips[]` in the Hedgeye payload) |
| **Entered top/bottom decile** | `rr_pos` crossed 0.85 or 0.15 today |

These are exactly the signals the user says he trusts, and none of them are currently
surfaced as *events* — only as a static bar position.

### 4.2 Statistical moves (secondary — only where ranges don't reach)

For instruments with no risk range, or to answer "is this move unusual *for this
instrument*": `z = (today's % change − 60d mean) / 60d stdev`, from `drv_quote`.
Rates use basis points, not percent. `|z| ≥ 2` notable, `≥ 3` severe.

This is what catches the yen example: a 1.8% move in `/6J` is 3σ; the same move in
`/BTC` is a Tuesday. No fixed threshold can express that.

### 4.3 Cross-asset patterns

Named combinations, seeded in `ref_market_pattern` so they are tunable. Each pattern
states the co-movement and the historical read — **never a cause** (C2).

| Pattern | Condition | Read |
|---|---|---|
| **Yen bid / carry unwind** | `z(/6J) ≥ +2` AND (`z(TNX) ≤ −1` OR `z(/GC) ≥ +1`) | Carry unwinding. Momentum + high-beta exposed. |
| **Dollar wrecking ball** | `rr_pos($DXY) ≥ 0.85` AND commodities composite `≤ −1σ` | Global tightening. Commodities + non-US pressured. |
| **Rates shock** | `\|Δ TNX\| ≥ 15bp` AND `\|z\| ≥ 2` | Duration + long-duration equity repricing. |
| **Credit leading equity** | `z(HYG) ≤ −2` or HY spread `≥ +2σ`, while `\|z(SPX)\| < 1` | Credit moving first. De-risk before equity confirms. |
| **Flight to quality** | `z(/GC) ≥ +2` AND `z(TNX) ≤ −1` AND `z(SPX) ≤ −1` | Classic risk-off. |
| **Vol regime break** | Any gauge **crosses** a `ref_vol_threshold` boundary today | Halve sizes on an upward break. |
| **Korea → US semis** | `z(^KS11) ≤ −2` or `z(EWY) ≤ −2` | Overnight chip read-through. Check SOXX/NVDA/AVGO before the open. **The user's KOSPI ask.** |
| **Oil supply squeeze** | `rr_pos(/CL) ≥ 0.85` AND `OVX` rising into elevated | Energy + inflation impulse. |

**Crossings, not levels.** A VIX elevated for nine days is not news on day nine. Only
the transition day fires here; the persistent state lives in the Risk Dial. This is C1
applied strictly, and the biggest single fix versus the superseded design, whose vol
trigger would have fired every day of a sustained vol regime.

### 4.4 Economic surprise (the CPI / unemployment ask)

Honest position on what is possible:

| Release | Expected value | Verdict |
|---|---|---|
| **CPI / core CPI** | **Hedgeye Inflation Nowcast** — already arriving by email, already designed to land in `hist_macro`. Free backup: Cleveland Fed daily nowcast. | ✅ **Surprise is computable.** |
| **GDP** | Atlanta Fed **GDPNow**, free on FRED as `GDPNOW` | ✅ Computable |
| **NFP / unemployment / ISM / PPI** | **No free consensus exists anywhere.** Everything is paywalled (Bloomberg, Trading Economics, FMP). | ❌ **Do not fake it.** |

**Decision:** compute a real surprise for CPI and GDP. For unemployment and the rest,
show *actual vs its own 3-month trend* and label it exactly that — a deviation, not a
surprise. A dashboard that says "CPI surprise +0.3σ" next to "Unemployment: 4.3%, above
3-mo trend" is honest. One that invents a consensus is not.

`surprise_z = (actual_first_print − nowcast) / stdev(historical gap)`
First print, not revised — via FRED's ALFRED vintage parameters, which your existing
key already covers.

### 4.5 Quiet state

```
○ Nothing unusual — 47 instruments checked, 0 range breaks, max |z| 1.3 (DXY).
```

One muted line. A blank panel is indistinguishable from a broken one.

---

## 5. Volatility discount (VRP) — the user's ask, and the one genuinely new calculation

`VRP = VIX − realized volatility`. When positive and wide, options are expensive
relative to what the market actually delivers — the classic "vol discount" condition
where selling premium and holding beta both work. When it compresses to zero or
inverts, that regime has ended, historically before price confirms.

**Fully self-computable.** No external source, no key, no cost. You already store SPX
daily OHLC.

Estimator choice matters more than it looks. Close-to-close realized vol over 21 days
is so noisy that a VRP signal built on it fires on estimator error as often as on real
premium compression. **Use Yang–Zhang**, which uses the O/H/L/C you already have and
handles both overnight gaps and intraday drift — roughly 14× more statistically
efficient than close-to-close for the same window. That efficiency gain is the
difference between a VRP column that works and one that is noise.

Windows: 10 / 21 / 63 days. Cross-check against Cboe's free `RVOL_History.csv` — if
your number and theirs diverge, you have a bug. A permanent, free correctness test.

---

## 6. Market volume and breadth — the user's ask

Market-wide volume does not exist in the database. **But it exists in ThinkOrSwim,
which you already pay for**, and flows through the Excel export path you already run.

**Decision: use ToS. Do not go outside.**

| Metric | ToS symbol |
|---|---|
| NYSE TICK | `$TICK` |
| TRIN / Arms | `$TRIN` |
| Advancing / declining issues | `$ADVN` / `$DECN` |
| Up volume / down volume | `$UVOL` / `$DVOL` |

Add them to a ToS watchlist → they arrive in the next TL/TD export → one new
`HIST_MAPS` entry. No new API, no new key, no new failure mode.

Separately, and **higher value**: `% of stocks above the 50-day and 200-day moving
average`, computed on **your own ~1,000-symbol universe**. You already store daily
closes and already compute moving averages in `_derive_technicals_impl`. This is
roughly twenty lines inside the existing derive cascade, has zero external dependency,
and is more relevant to your book than any exchange-wide series — because it is
measured on the stocks you actually own and watch.

Yahoo's `^TICK`/`^TRIN`/`^ADD` are unreliable with no usable daily history.
StockCharts' `$NYAD`/`$SPXA50R` are legally off-limits — their terms explicitly
prohibit automated collection, and there is no API.

---

## 7. Bands ③–⑥

### ③ Regime (one line, no new computation)

Promotes what exists on `/actionable`: quad path from `/api/quad-window`, Favors/Avoids
from `/api/quad/band-factors`, breadth from `/api/macro-areas`. **The hover popover is
the existing factor table**, unchanged — so "pop over on any Quad text and see all the
factors considered" works exactly as it does today.

### ④ Factor scorecard

Unchanged from v1 — this is where "my allocation % to each one and how I am doing over
periods" lives. Three tabs on the same three axes `ref_quad_outlook` uses, so allocation
lines up 1:1 with the quad's call.

| Column | Definition |
|---|---|
| Quad | BULLISH / NEUTRAL / BEARISH from the effective 60-day window distribution |
| You % | Your market value in the category ÷ total portfolio |
| vs tgt | Deviation from `ref_asset_allocation` min/max where mapped |
| 1w · 3w · 1m · 2m · 3m | **Your** time-weighted return. 5/15/21/42/63 trading days. |
| Mkt | Proxy ETF return, same windows |
| Verdict | ADD / HOLD / TRIM |

**Returns must be time-weighted.** `V_end / V_start − 1` is wrong: add $50k to Tech and
the screen reports it as +40% performance. Since you trade near-daily this error would
be large and permanent.

```
r_t = (V_t − V_{t−1} − netflow_t) / V_{t−1}      TWR = Π(1 + r_t) − 1
```

`V_t` from `hist_cs`/`hist_f` daily snapshots; `netflow_t` from `hist_cst`/`hist_ft`.
Risk: accuracy depends on transaction feeds being complete. Mitigations — a per-day
sanity gate (`|r_t| > 25%` flags rather than compounds), a `flows_confidence` badge,
and a flow-immune fallback (held-throughout return). **Validate against a category with
no trades in the window, where TWR must equal the naive number exactly, before trusting
any column.**

Verdict matrix:

|  | Quad BULLISH | Quad NEUTRAL | Quad BEARISH |
|---|---|---|---|
| **Under-weight** | **ADD** | watch | avoid |
| **At target** | **HOLD** — press if 1m > 0 | HOLD | **TRIM** |
| **Over-weight** | hold, no adds | **TRIM** | **TRIM HARD** |

Two modifiers:
- **`ROTATE (not ADD)`** — quad bullish, weight fine, but *your* return trails the
  market proxy in ≥2 of 5 windows. Separates a bad allocation call from bad
  stock-picking inside a good allocation. Nothing in the system shows this today.
- **Risk-dial cap** — budget < 55 downgrades every ADD to hold for the day.

Honesty notes: style tags **overlap and sum > 100%** (a symbol can be Momentum *and*
High Beta *and* Secular) — the tab must say "overlapping tags, not an allocation."
Unmappable holdings get an explicit `Unmapped` row rather than being silently dropped.

Storage: new `drv_category_perf`, written by `etl/derive_category_perf.py` in the
derive cascade, idempotent per `as_of_date`. Chain-linking 63 days × ~30 categories
per page load is too slow live, and precomputing makes the numbers auditable — which
matters given the flow risk above.

### ⑤ Today's shortlist

**Three rows, hard cap.** From the existing `/api/actionable` under its existing
default sort, filtered to the playbook §3.3 high-conviction subset (BM/BMN buys backed
by RR or SSS with `rr_bull_bear = B`; SA/gate sells). No new ranking, no new endpoint —
a `limit` and `conviction=high` param on what exists.

Three, not eight, because the playbook's own measured expectation is 0–3 trades a day.
A longer list invites exactly the scrolling-until-decisiveness-dies failure it warns
about.

### ⑥ Housekeeping

One thin line, red only when broken: `/api/anchor-status`, `/api/ingest-log`,
`/api/health/derive-status`, plus near-term econ and earnings in compact form. This is
the playbook §3.1 pre-flight, automated. If it is red, Band ① must say so — the risk
dial is meaningless on stale data.

---

## 8. Data decisions — made, with reasons

### ✅ Build (already have the data)

| Item | Why |
|---|---|
| Risk Dial from risk ranges + vol thresholds | Everything needed is in `drv_rr` and `ref_vol_threshold` today |
| Range-break / trend-flip events | `drv_rr` daily; the flips are already parsed |
| Dealer gamma | `hist_msr.gamma_throttle` already ingested — just render it as a gauge |
| Turn on **HY spread** (`BAMLH0A0HYM2`) and **2s10s** (`T10Y2Y`) | Already fetched daily, display rows disabled. Flip a flag. |
| Render `top_down`, `extremes_hot/cold`, area `stance`/`conviction` | API already returns them; the only consumer is dead code |
| Yang–Zhang realized vol + VRP | Free, self-contained, from OHLC you already store |
| % above 50/200-DMA on your own universe | ~20 lines in the existing derive cascade, zero dependency |
| Multi-period sector / asset-class / style returns | The gap behind ask #12 |
| CPI + GDP surprise vs Hedgeye nowcast / GDPNow | Both already free and already arriving |

### ✅ Add (free, low risk)

| Item | Source | Note |
|---|---|---|
| **ToS internals** `$TICK $TRIN $ADVN $DECN $UVOL $DVOL` | ThinkOrSwim — **already paid for** | Watchlist entry + one `HIST_MAPS` row |
| **KOSPI complex** `^KS11`, `005930.KS`, `000660.KS`, `EWY` | Yahoo, via existing `yahoo_fetch.py` | Put Korea on the **carry-forward** side — Korean holidays ≠ US holidays. Divide by `KRW=X` for USD comparison. |
| **VVIX** | Cboe free CSV `VVIX_History.csv`, no key | Threshold row 100/150 already seeded, feed missing |
| **ETH** `ETH-USD` | Yahoo | Trivial |
| **Cboe `RVOL`** | Free CSV | Cross-check for your own VRP calc |

### ❌ Skip — with reasons

| Item | Why not |
|---|---|
| **Paid economic consensus** (Trading Economics, FMP, Finnhub) | $50–200/mo for a number whose information content decays within ~90 minutes of release — and you run an **EOD** dashboard anchored to a TOSD export. The Hedgeye + Cleveland Fed + GDPNow path covers the two releases that matter, free. |
| **News / headline APIs** | Every free tier is calibrated too small to do entity resolution and dedup properly, and headlines *follow* price. Your Hedgeye email feed already does this better, with a human filter attached. |
| **Agricultural futures** (corn/wheat/soy) | Near-zero read-through to a US equity book on a daily horizon. Worse, Yahoo's `=F` symbols are **rolling front contracts** — every roll produces a multi-percent price gap that is not a return, which would fire false rules. Negative expected value. |
| **Full SPX dealer GEX / gamma-flip level** | Computable free from Cboe's undocumented delayed-quote JSON, but: open interest is always prior-day, the dealer sign convention is an assumption, and the signal is mostly an *intraday* mean-reversion phenomenon. **You already have Hedgeye's `gamma_throttle` scalar.** Use it; skip building the curve unless a specific rule consumes the level. |
| **StockCharts breadth symbols** | Terms explicitly prohibit automated collection, no API. You own ToS, which has the same data legally. |
| **Cboe put/call CSVs** | Confirmed dead — coverage ends 2019-10-04. |
| **Geopolitical oil-event feed** | Does not exist free, and the paid ones aren't good. `OVX` + WTI backwardation *is* the market's own disruption gauge, arrives with zero latency, and never hallucinates. |

### 🐛 Bugs found during this review (worth fixing regardless)

1. `/api/marketbar` returns `vol_low`/`vol_high` = null for `MOVE` — key mismatch
   against `ref_vol_threshold`'s `MOVE:GIF`. The MOVE tile shows no zone.
   (`web/market_bar.js:427-433` documents it in-code.)
2. Hot/cold threshold mismatch: the server flags at **0.85/0.15**, the rail JS defaults
   to **0.80/0.20** because the API never sends `hot_pct`/`cold_pct`. Two different
   definitions of "extended" are live at once.
3. `etl/mappings.py:510` re-declares `REF_MAPS: dict = {}`, overwriting the populated
   dict at line 31 — which would silently kill the Sctr→`ref_sector` and RRT→`ref_rrt`
   reference loads. **Needs confirming against the live DB by the developer agent.**

---

## 9. Answers to the v1 open questions — decided, not asked

The user asked me to make these calls. Here they are, with reasoning.

| Question | Decision | Why |
|---|---|---|
| Over/under-weight band | **±3 percentage points**, and `ref_asset_allocation` min/max wins wherever it exists | Percentage points, not % of target: a 3pp move on a 5% position is a 60% change in that position, which is the scale at which you would actually trade. Your explicit dollar limits are more informative than any generic band, so they take precedence. |
| Benchmark column | **One "vs Mkt" delta per window**, not raw benchmark alongside | Ten numeric columns will not be read. The delta is the decision-relevant number, and it drives the `ROTATE` verdict directly. |
| Pattern list | **Ship the 8 in §4.3**, seeded and tunable | They cover the user's named scenarios (yen, dollar, rates, credit, oil, Korea) plus flight-to-quality and vol breaks. Seeded rather than hardcoded so removals cost nothing. |
| Shortlist size | **3 rows, hard cap** | The playbook's own measured expectation is 0–3 trades/day. |
| Derived table vs live | **Derived table (`drv_category_perf`)** | 63-day chain-linking is too slow live, and precomputing makes the numbers reproducible — which matters because the TWR flow risk means these numbers *will* need auditing. |
| Risk-dial weights | **Start at §3.2 values, store in `ref_risk_gauge`** | They are a starting hypothesis, not a result. Storing them in a table means they can be tuned against outcomes later without touching code — the same pattern `ref_settings` already uses. |

---

## 10. Proposed phasing (after sign-off — nothing handed off yet)

| Task | Scope | Value | Depends |
|---|---|---|---|
| **TASK_133** | **Risk Dial backend** — `ref_risk_gauge` + `ref_level_watch` + `ref_gauge_transmission` seeds, `/api/cockpit/risk-dial`. Turn on HY spread + 2s10s. Fix the 3 bugs in §8. | **Highest** — this is the invest/hold/reduce answer | — |
| **TASK_134** | **Events backend** — range breaks, z-scores, `ref_market_pattern`, CPI/GDP surprise, `/api/cockpit/events` | High | 133 (shares helpers) |
| **TASK_135** | **Self-computed inputs** — Yang–Zhang RV + VRP, % above 50/200-DMA, both into the derive cascade | High, cheap | — |
| **TASK_136** | **Factor scorecard** — `drv_category_perf` + `etl/derive_category_perf.py` + endpoint | High | — |
| **TASK_137** | **New feeds** — ToS internals watchlist + mapping, KOSPI complex, VVIX, ETH, Cboe RVOL | Medium | — |
| **TASK_138** | **Cockpit frontend** — rebuild `index.html`/`app.js`/`styles.css`, retire ticker grid, doc sync | — | all above |

133, 135, 136 and 137 are independent. **If only one ships, it should be TASK_133** —
the Risk Dial alone changes how you size every trade, and it needs no new data at all.

---

## 11. Implementation notes (2026-08-01 — built as TASK_133, all 8 phases)

The separate TASK_134–138 above were folded into one task, `TASK_133_dashboard_cockpit.md`,
and shipped in two agent rounds. Where the build diverged from this design doc, this
section records what actually happened — full reasoning + evidence is in the
archived `DEV_HANDOFF_*.md` rounds (see `git log`/round history) and `docs/migrations.md`'s
2026-08-01 entry.

- **§3.2 gauges**: all 14 non-internals gauges built as specified in
  `etl/derive_risk_dial.py`; `volume_breadth_weak` (15th, needs `hist_internals`)
  seeded `is_active=FALSE` pending the user adding the ToS watchlist symbols.
- **§4.3 patterns**: all 8 built in `etl/derive_market_event.py` — 6 as a pure
  z-score function (`_pattern_events`), `vol_regime_break` and `oil_squeeze`
  separately (both need a DB lookup `_pattern_events` doesn't have: a
  day-over-day `ref_vol_threshold` zone check, and `drv_rr`'s `/CL` lrr/trr).
- **§4.4 CPI/GDP surprise**: CPI wired to the Hedgeye Nowcast (`HE_CPI_NOWCAST`
  in `hist_macro`) as designed. GDP: no `GDPNOW` series was added (out of the
  API-only Phase 6 scope) — GDP falls to the same "deviation from its own
  3-month trend" honest label as NFP/ISM/PPI/Unemployment, not a true surprise.
- **§7④ factor scorecard "vs Mkt" column**: implemented exactly as specified —
  one delta (`twr - bench`) column per window, not raw benchmark alongside.
- **§7③ Regime hover popover**: implemented as a plain-text `title` attribute
  (bull/bear ticker lists from `/api/quad/band-factors`), not a full duplicate
  of `web/actionable.js::_regimeVerdictHtml()`'s richer interactive popover —
  a documented simplification given the no-Actionable-refactor constraint and
  round-2 time budget. Same data source, same "no new computation" rule.
- **Round-2 addition, not in this design doc originally**: `drv_category_perf`
  gained a symbol-level qty-gap detector (any-action flow-row match, not just
  Buy/Sell) that forces a day's `r_t=0` + `flows_confidence='suspect'`
  independent of the existing 25%-magnitude guard — see `docs/migrations.md`
  2026-08-01 and the archived round-2 `DEV_HANDOFF.md` for the investigation
  that found this gap.
- Everything else (Risk Dial size-multiplier line, six-band frontend layout,
  factor scorecard tabs, shortlist 3-row cap, housekeeping→Risk-Dial warning
  propagation) matches this design doc as written.

## 12. Implementation notes (2026-08-01 — TASK_134 visual system + follow-ups)

TASK_133 shipped correct data and layout but hardcoded a foreign palette and
encoded no gauge severity. TASK_134 fixed the visual system and two content
bugs, plus closed three deferred follow-ups. Full evidence in `DEV_HANDOFF.md`
("Dev Handoff — TASK_134").

- **Visual system**: the cockpit's inline `<style>` block in `web/index.html`
  (raw hex: `#16a34a`/`#f59e0b`/`#dc2626`/`#eef2ff`/etc.) moved to
  `web/styles.css` under a "Dashboard cockpit (TASK_133/134)" banner, every
  color replaced with an existing `:root` token (`--bull`/`--bear`/`--warn`/
  `--ok`/`--accent`/`--text-*`/`--border`/the `--act-*` action ramp) — no new
  tokens were needed. Band 1's hierarchy now leads with the 48px budget
  number (was a 20px headline sentence competing with a 34px number); gauge
  severity is a coloured left rail + weight chip (`sev-1/2/3`, matching
  `ref_risk_gauge.weight`'s seeded 1/2/3 scale) instead of one flat pink wash.
- **B.1 (multi-leg gauge detail)**: `etl/derive_risk_dial.py` gained a shared
  `_leg_detail()` helper used by `_g_oil_shock`/`_g_credit_stress`/
  `_g_yield_level_watch` — when a gauge fires, the detail string names only
  the leg(s) that fired, in the gauge's own leg-definition order (chosen over
  a magnitude-based reorder because the spec's own combined example, "WTI 91%
  of range; OVX 63 — above elevated (50)", keeps WTI first even though OVX's
  relative excess over its threshold is the larger of the two under any
  normalization tried — reproducing that example required preserving
  definition order, not computing a ranking).
- **B.3 (Band 2 BB-fallback noise)**: `etl/derive_market_event.py::
  _risk_range_events` now filters `drv_rr` to `source = 'RR'`. Verified (not
  assumed) that `drv_rr_trend_change` needs no equivalent filter: it's a VIEW
  built directly off `hist_rr` (the raw Hedgeye feed table, populated only
  for the curated ~55 instruments), not off `drv_rr`, so BB-fallback rows
  (which exist only in `drv_rr`) can never reach it.
- **B.2 (headline phrase)**: `_RISK_SIZE_PHRASE` in `api/routers/cockpit.py`
  updated to CAUTION→"Three-quarter size.", NOT INVESTABLE→"No new risk."
  (CLEAR/DEFENSIVE unchanged). The phrase and `suggested_size_multiplier`
  share the same `risk_label` lookup key, which is itself derived from the
  same budget boundaries the multiplier scales from — they were already
  structurally unable to disagree; no separate banding bug found.
- **C.1 (transaction-feed gaps)**: new `GET /api/cockpit/housekeeping` +
  `_txn_feed_gaps()` compares `MAX(snapshot_date)` in `hist_cs`/`hist_f`
  against `MAX(trade_date)` in `hist_cst`/`hist_ft` per account, using
  `COUNT(DISTINCT hist_td.export_date)` in the gap interval as the
  trading-day count (no dedicated trading-calendar helper existed to reuse).
  Flags >10 trading days or zero transactions ever. Band 6 renders a red line
  per flagged account; Band 4 shows a degraded-returns caption when any
  account is flagged.
- **C.2 (`REF_MAPS` landmine)**: the `REF_MAPS: dict = {}` re-declaration in
  `etl/mappings.py` (previously blanking the populated Sctr/RRT/Desc/ISMH
  dict) is removed. Verified safe first: `ref_*` tab loads use
  `insert_skip_duplicates` (`ON CONFLICT DO NOTHING`), which cannot drop or
  overwrite an existing row — only add ones missing from the DB. Row counts
  before/after in `DEV_HANDOFF.md`.
- **C.3 (MOVE zone)**: confirmed already correct — `GET /api/marketbar`'s
  `MOVE` item returns non-null `vol_low`/`vol_high`. No code changed.
