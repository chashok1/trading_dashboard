# Hedgeye Email Feeds — Consumption & Automation Design

## Decision log (walkthrough outcome)

| # | Email | Destination | Decision |
|---|---|---|---|
| 1 | Risk Range Signals | DATA `hist_rr` | Full 38-row parse. TREND CHANGE = derived (`drv_rr_trend_change`), not stored; printed block = transient QA only |
| 2 | Real-Time Alerts | DATA `hist_rta` + RULES | Parse action/price/durations; coaching notes → `note_repo`. Corrections **auto-reverse** the prior alert |
| 3 | Investing Ideas Add/Remove | DATA `hist_ii`/`hist_iichg` | action+side+ticker. Treated **independent** of RTAs |
| 4 | ETF Pro changes | DATA `hist_etfchg` | add/remove only — **no price ranges** |
| 5 | Signal Strength Stocks | DATA `hist_sss` | **Deltas only** from email (full list = image → export) |
| 6 | Portfolio Solutions re-rank | DATA `hist_ps` | **Full table** parsed from email HTML (it's a real `<table>`, not image) |
| 7 | Macro Show — Summary Notes | DATA `hist_hedgeye_stance` + ANALYSIS | TL;DR positions parsed (name→symbol lookup for non-tickers); prose → `note_repo` |
| 8 | Macro Show — Access / Top 3 | — | Analysis-only → `note_repo` |
| 9 | KM's Top 3 Things | — | Analysis-only → `note_repo` |
| 10 | Early Look | ANALYSIS + RULES | Key Takeaways → `note_repo` |
| 11 | The Call — Replay & Summary | DATA | **Ignore "Access Here."** `hist_call` ← HEDGEYE POSITIONS (long/short/neutral); **new `hist_call_top5`** ← Top 5 Actionable Ideas (stored **and** shown on actionable screen) |
| 12 | Market Situation Report | ANALYSIS | Snippet → `note_repo`; **archive all chart images** to configurable folder (positional names + drift guard) |
| 13 | MOMO Tracker | — | **Ignore** |
| 14 | Monthly Inflation Nowcast | DATA macro series | Parse headline % + bp direction; **no chart** |
| 15 | Quarterly Investment Outlook | RULES | Quad thesis → `note_repo`; triggers permanent macro-rule review; no chart |
| — | Marketing (`hedgeye@hedgeye.com`), "Access Here" links | — | **Drop** |

**Cross-cutting:** Gmail is the archive (no raw bodies; keep `message_id` for re-fetch/backfill) ·
`note_repo` deterministic, always-on · optional configurable LLM enrichment (local-model capable,
licensing-aware, display-only) · interactive rule-builder (`rule_candidate`) with provenance ·
image archiving is a shared, configurable option · classify by subject + header image + meta tag.

---


> Design doc only. No code, no DB writes here. Implementation goes to the developer
> agent via `agent-tasks/TASK_*.md` (Cowork Rule 17). Status: proposal awaiting approval.

**Goal (Ashok's words):** *make money — the information should let me take action
easily and without confusion, based on the rules.* Every Hedgeye email must end up in
exactly one of three destinations, decided deterministically by Python with **no LLM in
the runtime path**, running headless whether or not Cowork is open:

1. **DATA** → a `hist_*` source table (then your existing derive + rules cascade).
2. **ANALYSIS** → a searchable note store (context for you, not auto-traded).
3. **MACRO RULES** → a *rule-candidate queue* you review to build/adjust permanent rules.

The mailbox that actually receives these is **chilukua14@gmail.com**. An unattended job
needs its own headless read access (Gmail API token or IMAP app-password) — the Cowork
Gmail connector is not available to a background service.

---

## 1. Key finding — you already have tables for most of this

Your DB already defines source tables that line up almost 1:1 with Hedgeye products,
currently fed by hand from the `Tickers YYYY-MM-DD.xlsx` tabs:

| Hedgeye email | Existing table (tab in `mappings.py`) | Coverage from email alone |
|---|---|---|
| Risk Range™ Signals | `hist_rr` (`RR`) | **Full** — 38 rows, all fields in plaintext |
| ETF Pro Plus changes | `hist_etfchg` (`load_etfchg`) | **Full** — add/remove + ranges in text |
| Investing Ideas "Add/Remove … LONG/SHORT" | `hist_ii` / `hist_iichg` (`II`, `load_iichg`) | **Full** — action + side + ticker |
| Signal Strength Stocks | `hist_sss` (`SSS`/`ssH`) | **Delta only** from email (full 80-name list is a chart image → export) |
| Portfolio Solutions weekly re-rank | `hist_ps` (`ps`) | **Full table** — parsed from the email's real HTML `<table>` |
| The Call | `hist_call` + new `hist_call_top5` | `hist_call` ← HEDGEYE POSITIONS list; Top 5 Actionable → new table |

So the automation is mostly **"email → the same tab shape → your existing loader"**, not
new plumbing. New stores needed: Real-Time Alerts (`hist_rta`), macro stance
(`hist_hedgeye_stance`), Top-5 actionable (`hist_call_top5`), notes (`note_repo`), the
rule-candidate workspace, and optional `llm_analysis` / `hist_media`. See §5 and §8a.

---

## 2. Full inbox taxonomy

Observed 24–26 Jun 2026. Two senders matter:

- **`info@hedgeye.com`** = research (always carries Gmail label `Label_8414…`). **Keep.**
- **`hedgeye@hedgeye.com`** = marketing/promo ("$5,001 off Macro Pro"). **Drop.**

| # | Email type | Cadence | Payload shape | Destination |
|---|---|---|---|---|
| 1 | **Risk Range™ Signals** | Daily ~07:34 ET | Structured 38-row table | DATA `hist_rr` |
| 2 | **Real-Time Alert** | Many/day | Action + price + TRADE/TREND/TAIL + coaching notes | DATA (new `hist_rta`) + RULES (coaching) |
| 3 | **Add/Remove … LONG/SHORT** (Investing Ideas) | Intraday, as needed | Action, side, ticker | DATA `hist_ii`/`hist_iichg` |
| 4 | **ETF Pro Plus changes** | Intraday, as needed | Add/Remove Long/Short | DATA `hist_etfchg` (add/remove only, no ranges) |
| 5 | **Signal Strength Stocks** | 1–2/day | Added/Removed tickers (+ image of full list) | DATA delta `hist_sss` (full list via export) |
| 6 | **Portfolio Solutions** weekly re-rank | Weekly (Fri) | Full HTML rank table | DATA full `hist_ps` (parsed from email) |
| 7 | **The Macro Show — Summary Notes** | Daily ~late AM | `TL;DR POSITIONS` Bullish/Bearish list + prose | DATA `hist_hedgeye_stance` + ANALYSIS |
| 8 | **The Macro Show — Access / Top 3** | Daily AM | Prose + slide link | ANALYSIS → `note_repo` |
| 9 | **KM's Top 3 Things** | Daily | 3 short prose points | ANALYSIS → `note_repo` |
| 10 | **Early Look** | Daily ~07:49 ET | `Key Takeaways` bullets + macro essay | ANALYSIS + RULES → `note_repo` |
| 11 | **The Call @ Hedgeye** — Replay & Summary | Daily | HEDGEYE POSITIONS + Top 5 Actionable Ideas | DATA `hist_call` + new `hist_call_top5`; **ignore "Access Here"** |
| 12 | **Market Situation Report** (Tier1 Alpha) | Daily ~06:30 ET | Dealer-gamma prose + charts | ANALYSIS → `note_repo` + **archive images** to configurable folder |
| 13 | **MOMO Tracker** | Daily | Momentum readout (mostly image) | **Ignore** |
| 14 | **Monthly Inflation Nowcast** | Weekly→monthly | Headline nowcast %, y/y + bp change, CPI date | DATA (macro series); no chart |
| 15 | **Quarterly Investment Outlook** | Quarterly | The Quad regime thesis (deck) | RULES — quarterly rule-review reminder |

---

## 3. Deterministic classification (no LLM)

Every research email carries three stable, machine-readable handles — any one works, use
them in combination for robustness:

1. **Subject regex** — e.g. `^RISK RANGE.*SIGNALS`, `^\*\*Real-Time Alert:`,
   `^(Add|Remove) .*\((LONG|SHORT) Side|to (LONG|SHORT) Side)`, `ETF Pro Changes`,
   `^Signal Strength Stocks`, `^MARKET SITUATION REPORT`, `^EARLY LOOK`,
   `^THE MACRO SHOW`, `Monthly Inflation Nowcast`, `Quarterly Investment Outlook`.
2. **Header image asset name** in the HTML (very reliable): `stock_alerts_800px.png`
   = Real-Time Alert; `signal_strength_stocks_800px.png`; `market_situation_report_800px.png`;
   `etf_pro_plus_1_800px.png`; `investing_ideas_800px.png`; `macro_select_800px.png`.
3. **Meta tags**: `<meta type="hedgeye-headline">` and `<meta type="hedgeye-stock-symbols">`
   (gives you the affected ticker(s) directly).

Encode this as a table-driven router, e.g. `ref_hedgeye_email_type(pattern, asset_name,
email_type, handler, destination, cadence)`. Adding a future Hedgeye product = one row,
no code change — mirrors how `LoadFiles.xlsx` already drives your file loader.

---

## 4. Per-type processing spec

### Bucket A — DATA (parse → existing/new hist table)

**Risk Range Signals → `hist_rr`** (full mapping already exists). From `plaintextBody`:
match `^(\S+) \((BULLISH|BEARISH|NEUTRAL)\)$`, take the next line, the last 3 whitespace
tokens are BUY / SELL / PREV (strip commas; trim trailing `#OUTBUCKET` on the last row).
Map → `symbol`+`tos_symbol`, `outlook`, `buy_trade`, `sell_trade`, `last_price`,
`market_close` = email date. Stop at `#OUTBUCKET`.

**ETF Pro changes → `hist_etfchg`.** Parse the `We are ADDING/REMOVING Long|Short:` blocks;
each `<li>` = `Name (TICKER) - (low - high)`. Emit rows: `action` (add/remove),
`side` (long/short), `symbol`, `range_low`, `range_high`, `ts`.

**Investing Ideas Add/Remove → `hist_ii` (state) + `hist_iichg` (event).** Subject +
body give `action` (add/remove), `side` (long/short), `symbol` (also in the
`hedgeye-stock-symbols` meta tag). One event row per email.

**Real-Time Alert → new `hist_rta`.** The most trade-relevant feed. Parse:
- Headline: `SELL SIGNAL - SHORTING ROP $339.80` → `action` (buy/sell/cover/short),
  `side`, `symbol`, `price`.
- Subject: `**Real-Time Alert: <Analyst> <Signal> Signal (<note>): <Name> (<TICKER>) -KM`
  → `analyst`, `signal_kind` (Buy/Sell/Sell-SOME/Cover-SOME/Macro), `coaching_subject`.
- `Durations` row → three booleans `dur_trade/dur_trend/dur_tail` (active = colored).
- `Coaching Notes:` ordered list → `coaching_notes` (text). **This is the rule-building
  fuel** — also copied to the rule-candidate queue (§5).
- `feed_items/<id>` URL → `source_url` (dedupe key).

**Macro Show "TL;DR POSITIONS" → new `hist_hedgeye_stance`.** The Summary Notes email
contains an explicit, parseable list: `BULLISH: XLV, TLT, VXF, …` / `BEARISH: Bitcoin,
MSTR, …`. Emit `(date, ticker, stance)` rows = Keith's current macro book, a clean daily
signal you can cross-check against your `drv_actionable`.

**Inflation Nowcast → macro series** (`hist_macro`/`ref_macro_series`, your FRED-style
store). Parse `base-case nowcast for June is +3.85% y/y`, the `-40 bp` sequential change,
and `CPI Release Date: July 14th`. Direction (accel/decel) is a macro-regime input (§7).

**The Call (Replay & Summary) → `hist_call` + new `hist_call_top5`.** Ignore the "Access
Here" email; process only Replay & Summary. Parse the `HEDGEYE POSITIONS` section
(`LONGS:` / `SHORTS:` / `NEUTRAL:` lines) → `hist_call(symbol, outlook)`. Parse the
`Top 5 Most Actionable Stock Ideas` (`Name (TICKER): rationale…`) → new
`hist_call_top5(date, symbol, side, rank, rationale_snippet, message_id)`; `side` derived
by matching each ticker to the same email's LONGS/SHORTS lists. Stored **and** surfaced as
a panel on the actionable screen.

### Bucket B — ANALYSIS (store extract, don't auto-trade)

Market Situation Report, Macro Show prose, Early Look essay, Top 3 Things. (MOMO Tracker
is ignored.) We do **not** store the email body (see Storage policy below). Instead these
land in `note_repo` (§8a) — only the small extracted snippet plus tags and a Gmail deep-link.
Cheap deterministic extraction: pull the `Key Takeaways` list (Early Look), the `TL;DR`
block (Macro Show), and any `hedgeye-stock-symbols`. This is for search / morning review /
back-reference, the per-symbol dossier, and (on request) LLM enrichment — not a trade trigger.

### Bucket C — MACRO RULES (notes → interactive builder)

Coaching notes (RTA), Early Look takeaways, Macro Show themes (e.g. "#Quad4 was the lead
signal"), Inflation Nowcast direction, and the Quarterly Outlook Quad call all land in
`note_repo`, tagged by ticker/theme/`quad` (§8a). The pipeline **does not author rules** —
you build them in the `rule_candidate` workspace from selected notes, optionally LLM-assisted
on request, then test against `v_rule_scorecard` and promote into `ref_trig_*` / the MACRO
overlay. The Quarterly Outlook additionally fires a **quarterly rule-review reminder**.

---

## 5. Architecture — automated, headless, no-LLM

Model it on `etl/yahoo_fetch.py` (your existing background fetcher): cross-process state
in `ref_settings`, ET-time/trading-day awareness, idempotent, survives restarts.

```
                       ┌─────────────────────────────────────────────┐
                       │ etl/hedgeye_fetch.py   (poll every ~3–5 min) │
                       │  - Gmail API / IMAP, read-only               │
                       │  - since last_seen; skip marketing sender    │
                       └───────────────┬─────────────────────────────┘
                                       │ new message
                       ┌───────────────▼───────────────┐
                       │ classify()  (ref_hedgeye_email_type) │
                       │  subject regex + header asset + meta │
                       └───────────────┬───────────────┘
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
   ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
   │ DATA handlers │          │ ANALYSIS      │          │ RULES         │
   │ parse→rows    │          │ note_repo +   │          │ rule_candidate│
   │ ON CONFLICT   │          │ (opt) llm/img │          │ workspace     │
   │ DO NOTHING    │          └───────────────┘          └───────────────┘
   ▼
  hist_rr / hist_etfchg / hist_ii(+chg) / hist_rta / hist_ps /
  hist_sss / hist_call / hist_call_top5 / hist_hedgeye_stance / hist_macro
   │
   ▼ (trigger, reuse existing path)
  derive_all(D)  →  drv_*  →  rules engine  →  drv_actionable  →  your dashboard
```

**Idempotency / dedupe.** Keep a `meta_hedgeye_msg(message_id, email_type, processed_at,
status)` ledger — exactly the role `meta_file_processed` plays for files. Re-runs and
re-deliveries are no-ops. Gmail `message_id` (or the `feed_items/<id>`) is the natural key.

**Storage policy — Gmail IS the archive.** We do not persist raw email bodies or `.eml`
in the DB. The ledger stores the `message_id` for every email; the typed handlers persist
only the extracted projections (`hist_*`) and small snippets (`note_repo`). To **re-parse
or backfill** when a handler is added or fixed, the fetcher re-pulls those messages from
Gmail by `message_id` and runs the new handler — Gmail retention is the safety net, so no
local raw copy is needed. Trade-off: backfill makes API calls instead of local reads, and
depends on Gmail staying reachable (a safe assumption here).

**Two integration options for DATA (pick in §10):**
- **(Recommended) Reuse the loader.** Each DATA handler writes the corresponding tab as a
  small `.xlsx` into the watched source dir, and your existing `scheduler.py` +
  `etl_load.py` ingest + derive it — *zero* new load/derive code, and it satisfies "use
  the existing method." Best for Risk Range, SSS, PS, ETF, II (tabs already mapped).
- **Direct rows.** Handler upserts straight into the hist table via SQLAlchemy. Simpler
  for the *new* tables (`hist_rta`, `hist_hedgeye_stance`) that have no tab.

**Cadence is handled for free.** Because the fetcher is event-driven on arrival, one poll
loop covers daily / intraday / weekly / monthly / quarterly automatically — a Real-Time
Alert is processed minutes after it lands; the Quarterly Outlook is processed the day it
arrives. Add only two *scheduled roll-ups* (see §7): a pre-open digest and a weekly/monthly
macro review.

**Runs without Cowork/LLM.** `hedgeye_fetch.py` is plain Python on a timer (Windows Task
Scheduler, a service, or folded into your existing `scheduler.py`). No model calls in the
hot path.

---

## 6. What email *cannot* give you (honest caveats)

- **Signal Strength Stocks** email = only *Added/Removed* tickers; the full 80-name table
  (Days On, Signal Date, prior/last close, % delta) is a **chart image** + the app. Email
  gives you reliable change-events; the full `hist_sss` snapshot still needs the workbook/
  app export. Recommendation: store the deltas as events, reconcile against the periodic
  full export you already load.
- **Portfolio Solutions** weekly re-rank: *not* image-gated — the full rank table is real
  HTML and is parsed straight from the email into `hist_ps`. (Corrected during walkthrough.)
- **Market Situation Report**: the email is commentary + charts; the full quantitative
  report (gamma levels, dealer positioning numbers) sits behind the "Click Here" link.
  Treat the email as ANALYSIS; if you want the numbers as DATA later, that's a separate
  authenticated-fetch project, not email parsing.
- **Charts/images** generally: numbers rendered only inside PNGs are out of scope for a
  no-LLM text parser.

---

## 7. Consumption playbook (daily / weekly / monthly)

**Pre-open (one digest, ~08:15 ET).** Auto-assemble from already-parsed emails:
Market Situation (dealer gamma: short-gamma = expect volatility), Early Look `Key
Takeaways`, Macro Show Top 3, and overnight Real-Time Alerts. One screen, no clicking.

**Open / intraday (the money-makers).**
- **Risk Range** loaded → your dashboard's buy/sell bands + TREND flips are live.
- **Real-Time Alerts** → immediate, explicit stock actions. These feed your existing
  `drv_actionable` engine as high-priority candidates; you execute the trade yourself.
- **ETF Pro / Investing Ideas changes** → position add/remove events into `hist_*`.

**EOD.** Macro Show `TL;DR` stance list + Signal Strength deltas reconcile against your
book and `drv_actionable`. Flag disagreements (you long a name Keith just flipped Bearish).

**Weekly.** Portfolio Solutions re-rank; Inflation Nowcast trend (the weekly cadence of
that "monthly" nowcast). A short weekly macro-review roll-up.

**Monthly / Quarterly.** Inflation Nowcast monthly print; **Quarterly Investment Outlook**
→ scheduled review to update your **permanent macro rules / MACRO overlay** (the Quad
regime). This is the one cadence that should *force* a rules review.

---

## 8. How each feed builds macro rules

You already have the machinery: the **Quad → MACRO overlay** (`docs/quad_design.md`,
TASK_74) and the rules engine. The email pipeline feeds it like this:

- **Quarterly Outlook + Macro Show themes** → detect Quad label (`#Quad4`), set/confirm the
  current **regime** that your MACRO overlay applies across the book.
- **Inflation Nowcast direction** (accel/decel, the 2nd-derivative sign Hedgeye publishes)
  → a macro-series input to the same overlay / `ref_macro_series`.
- **Coaching notes** (RTA) and **Early Look takeaways** → `rule_candidate` rows tagged by
  ticker/theme; you promote recurring, validated patterns into `ref_trig_*` composites.
- **Macro Show stance list** → a daily corroboration signal: when Keith's Bullish/Bearish
  list agrees with a fired rule, that's a higher-confidence setup (a natural composite
  member / weight input).

The deterministic rule: *quantitative + explicit-action feeds become DATA and can auto-
drive the engine; qualitative feeds become tagged candidates you approve.* That keeps you
in control of permanent rules while removing all the manual copy/paste.

---

## 8a. Notes repository + optional LLM enrichment

Two strictly separated lanes. The repository is deterministic and always runs; the LLM is
an optional, configurable, user-invoked enrichment that never touches the runtime/trade path.

### Lane 1 — `note_repo` (deterministic, store-first, always on)

Every coaching note (RTA) and macro/analytical note (Early Look, Macro Show, The Call,
Market Situation, Top 3, Quarterly Outlook, Inflation) is captured as one structured row.
No model involved — pure parse + tag.

```
note_repo(
  note_id, note_date, source_type, message_id, gmail_link,
  analyst, tickers[], asset_class, theme_tags[], quad, signal_kind,
  note_text,          -- small extracted snippet only (NOT the email body; Gmail is archive)
  status              -- new / triaged / linked / archived
)
```

Tagging is deterministic: tickers from the `hedgeye-stock-symbols` meta tag + `(TICKER)`
regex; `quad` from `#Quad[1-4]`; `theme_tags` from a keyword map. This store powers the
per-symbol dossier (§ per-symbol view) and is the searchable corpus you build rules from.
`message_id` lets you re-fetch full context from Gmail anytime.

### Lane 2 — optional, configurable LLM enrichment (on request)

A separate step reads selected notes/analytical docs and calls a **configurable** LLM to
produce structured, dashboard-ready analysis. Triggered by you (a dashboard button) or a
once-per-morning batch — never automatically in the ingest path.

- **Use it for the qualitative ANALYSIS docs** (Market Situation, Early Look, Macro Show,
  The Call, Quarterly Outlook): extract stance, key risks, affected tickers, Quad regime,
  a short summary, and cross-document synthesis ("consensus on AAPL this week").
- **Do NOT use it for the structured DATA feeds** (Risk Range, RTA, ETF/II changes) —
  already cleanly parsed; an LLM adds cost, not value.

**Configuration** (in `ref_settings` / `.env`), so the model is swappable and can run locally:

```
llm_enabled            true/false
llm_provider           openai | anthropic | azure | local | ...
llm_endpoint           URL (enables self-hosted / local model)
llm_model              model name
llm_api_key            secret (.env only)
llm_prompt_template    versioned prompt id
llm_output_schema      JSON schema the dashboard renders
llm_cost_cap           per-day token/$ ceiling
```

**Behaviour**
- **On-demand or batched, and cached.** Cache keyed by `message_id + llm_model +
  prompt_version` → never re-pay for the same note. Output lands in a separate store:
  `llm_analysis(message_id, model, schema_version, json_output, created_at)`.
- **Structured output, not a blob** — dashboard renders fields; you can later judge which
  summaries were worth it.
- **Display-only, non-authoritative.** Labeled "AI summary," links to the Gmail source,
  and **never triggers a trade or writes a rule.** Ingest / parse / rules stay 100% no-LLM;
  this is a side lane the dashboard reads.

**⚠ Licensing caveat.** Every Hedgeye email states it *"may not be forwarded or otherwise
provided to any unauthorized party."* Sending this proprietary research to a third-party
hosted LLM may breach that clause. Strong reason to keep `llm_endpoint` configurable with
a **local / self-hosted** option so content never leaves your machine. Check Hedgeye ToS
before routing notes to any hosted API.

### Rule-building (interactive, separate)

`note_repo` is the front of the funnel. Building actual rules is a separate, human-led step
(`rule_candidate` workspace): filter notes → select a cluster → draft a `ref_trig_*`
definition → test with existing `compute_firing_outcomes` / `v_rule_scorecard` → promote.
The LLM may *assist* clustering/drafting **only when you invoke it**, inside this workspace.

```
note_repo  ──(you filter/cluster)──►  rule_candidate  ──(test vs scorecard)──►  ref_trig_* / MACRO overlay
     │                                      ▲
     └──(optional, on request)──► LLM ──────┘   (suggest clusters / draft predicates)
```

---

## 9. New objects this introduces

| Object | Kind | Purpose |
|---|---|---|
| `hist_rta` | table | Real-Time Alert actions (analyst, action, side, symbol, price, durations, notes, url); corrections auto-reverse prior alert |
| `hist_call_top5` | table | The Call — Top 5 Most Actionable Stock Ideas (date, symbol, side, rank, rationale_snippet, message_id) |
| `hist_hedgeye_stance` | table | Daily Macro Show Bullish/Bearish ticker list |
| `drv_rr_trend_change` | derived | Day-over-day Risk Range TREND flips (computed from `hist_rr`, not stored raw) |
| `note_repo` | table | Deterministic store of all coaching + analytical notes (snippet + tags + message_id + Gmail link; no raw body). Powers dossier + rule-building |
| `llm_analysis` | table | Optional, cached LLM output per note/doc (display-only, non-authoritative) |
| `hist_media` | table | Archived chart images (path + source URL) for feeds that carry charts (MSR etc.); folder configurable |
| `rule_candidate` | table/queue | Interactive rule-building workspace; links to `note_repo` rows for provenance |
| `ref_hedgeye_email_type` | ref | Router: pattern/asset → type → handler → destination → cadence |
| `meta_hedgeye_msg` | meta | Processed-message ledger (idempotency); keeps `message_id` for re-fetch/backfill |
| `etl/hedgeye_fetch.py` | module | Headless poller + classifier + dispatcher (yahoo_fetch.py-style) |

All DDL lands in `db/baseline.sql`; new tab parsers extend `mappings.py`/`load_raw.py`
per the existing "Adding a new source-file type" recipe in `CLAUDE.md`.

---

## 10. Suggested build sequence (highest money-value first)

- **P1 — Backbone + Risk Range.** `hedgeye_fetch.py` (auth, poll, dedupe ledger,
  classifier) + Risk Range handler → `hist_rr` via the existing loader. Proves the whole
  path end-to-end on the feed you already understand.
- **P2 — Action feeds.** Real-Time Alerts (`hist_rta`, new) + ETF Pro changes
  (`hist_etfchg`) + Investing Ideas add/remove (`hist_ii`/`hist_iichg`). These are the
  direct trade drivers.
- **P3 — Analysis + candidates.** `doc_hedgeye` note store + `rule_candidate` queue,
  populated from Early Look, Macro Show, Market Situation, Top 3.
- **P4 — Macro overlay tie-in.** Inflation Nowcast → macro series; Quarterly Outlook +
  Macro Show stance → Quad regime / MACRO overlay; pre-open + weekly roll-up digests.

Per Cowork Rule 17, each P-phase becomes a developer `TASK_*.md` (DB work included, since
Cowork has no DB access). This doc is the spec source.

---

## Decisions needed before P1

1. **Email access**: Gmail API (OAuth token / service account) or IMAP app-password?
2. **DATA integration**: write tab `.xlsx` into the watched folder (reuse loader, my
   recommendation) vs. direct hist upserts?
3. **Scope of v1**: backbone + Risk Range only, or backbone + all three action feeds (P1+P2)?
