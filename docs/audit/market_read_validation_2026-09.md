# Market Read validation — does theme stance predict anything? (TASK_147)

**Date:** 2026-09-21 · **Status:** report-only, nothing wired to the decision
path. Standing rule (Addendum E3): a theme stance may influence an action
only after its own forward-return scorecard is positive on **≥ 30 samples**;
this report establishes the baseline the nightly refresh (`etl/scheduler.py::
run_nightly_outcomes`) grows from. Same conventions as
`docs/audit/signal_validation_2026-09.md`: `n`, HELD / THIN verdicts, no
verdict rests on `n < 30`.

**Data window at time of writing:** `drv_theme_stance`/`drv_sss_breadth`/
`drv_source_breadth` were backfilled 60 anchor dates (2026-06-27 →
2026-09-18) as part of TASK_143/144's own build/verify step — this is the
**entire available history**, not a curated sample. Read every number below
with that in mind (see Caveats).

---

## A. `v_theme_stance_scorecard` — theme × stance × source cell

Query: `SELECT * FROM v_theme_stance_scorecard WHERE cell='stance' ORDER BY n
DESC`. 18 of 22 themes have an ETF-side proxy in `ref_symbol_theme` and
therefore a row here; **4 do not** (excluded, not silently missing):
**Breadth, Industrial metals, Large caps, Volatility** — none of these has
an ETF/PS member seeded (Breadth/Volatility have no natural single-ETF
proxy; Large caps/Industrial metals were seeded RR-only). They stay
display-only until a proxy is added.

| Theme | Stance | n | edge_20d | win_rate_20d | Verdict |
|---|---|---:|---:|---:|---|
| Cash/short FI | B | 41 | −0.06% | 27% | THIN (n≥30 but edge ~0, low win rate) |
| Precious metals | B | 41 | +3.32% | 56% | **HELD-candidate** (positive, n≥30) |
| Healthcare | B | 41 | +3.32% | 66% | **HELD-candidate** |
| Small caps | B | 41 | −1.04% | 39% | HELD-candidate (negative edge on B — see caveat) |
| Cyclicals | B | 41 | −2.36% | 32% | HELD-candidate (negative) |
| Crypto | S | 32 | −15.87% | 6% | **HELD-candidate**, strong (short crypto themes right) |
| Rates up | B | 32 | +4.93% | 81% | **HELD-candidate**, strong |
| Tech/software | B | 32 | +6.56% | 50% | HELD-candidate (positive edge, coin-flip win rate) |
| Defensives | B | 28 | −2.62% | 11% | THIN (n<30) |
| all others | — | <25 | — | — | **THIN — do not act on these** |

Only 5 rows clear n≥30 with a plainly consistent sign+win-rate story:
**Precious metals/B, Healthcare/B, Rates up/B, Crypto/S** read positive;
**Cash/short FI/B** reads flat (edge ≈ 0). Everything else is THIN.

**By `agree_n` bucket** (does more sources agreeing help): `Tech/software`
at `agree_n=1` already shows edge_20d +9.17% (n=20, thin) vs its combined
+6.56% (n=32) — inconclusive at this sample size, no bucket clears n≥30 on
its own for any theme yet.

**By `quad_conflict`**: `Tech/software` non-conflicted rows show edge_20d
+10.23% (n=19, thin); `Cyclicals` conflicted rows show −2.52% (n=35) vs its
overall −2.36% (n=41) — conflict doesn't obviously change the read yet, but
no cell here is both n≥30 AND isolates the conflict effect cleanly (splitting
n=41 by a boolean roughly halves the sample). **Not enough data to say
"conflict hurts" or "conflict doesn't matter" — re-check after more weeks.**

## B. `v_sss_sector_scorecard` — SSS row/book changes vs sector ETF

| Sector | n | corr(rows_chg%, fwd20) | corr(book_chg%, fwd20) | n_divergence | avg fwd20 on divergence |
|---|---:|---:|---:|---:|---:|
| Retail | 28 | −0.13 | +0.46 | — | — |
| Industrials | 24 | −0.23 | +0.44 | — | — |
| Healthcare | 24 | −0.03 | — | — | — |
| Software | 20 | −0.05 | +0.41 | — | — |
| Consumer Staples | 20 | +0.23 | +0.23 | — | — |
| Global Tech | 12 | −0.82 | −0.83 | — | — |
| Financials | 12 | +0.17 | −0.17 | — | — |
| Energy | 8 | +0.88 | — | — | — |

**No sector cleared 30 observations of a genuine 4-week-apart pair** (56
calendar rows but only ~8-28 non-overlapping 4-week comparisons per sector
in a 60-date window) — **every row here is THIN by the ≥30 rule.** `Global
Tech`'s −0.82/−0.83 correlation is the only value large enough to be
interesting if it holds up, but n=12 is nowhere near enough. `n_divergence`
never populated in this window (no sector satisfied "rows fell >25% while
book didn't fall" against a same-sector observation 4 weeks back) — the
metric works (confirmed structurally against the design's own 2026-09-14
example while building TASK_144), it just hasn't fired again since.

## C. `v_source_breadth_scorecard` — list-breadth turns vs SPX 20d drawdowns

| Source | Turn type | Hits (SPX dd≤−5% within 20d) | False alarms |
|---|---|---:|---:|
| RR | flip_day | 0 | 11 |
| RR | net_crossed_zero | 0 | 6 |
| CALL | net_crossed_zero | 0 | 23 |
| CALL | rows_down_25pct_4wk | 0 | 13 |
| ETF | net_crossed_zero | 0 | 1 |
| PS | rows_down_25pct_4wk | 0 | 1 |
| everything else | 0 | 0 |

**Zero hits across every turn type — SPX had no 20d drawdown ≥5% at all in
this 60-date window** (an up-trending 3 months, consistent with TASK_139's
own carried-forward note: "SPX +3.0%, VIX ~16.5"). This says nothing about
whether these turns predict drawdowns — **there were no drawdowns to
predict against.** Re-run this view once the market has actually had a
correction; until then every row is "0 hits / N false alarms," which is the
expected, honest shape of a validation check with no positive-class events
yet, not evidence the signal doesn't work.

## D. CALL long/short split (Addendum D1) — confirmed

`v_source_edge_scorecard` now separates `side`. Reproducing the design
doc's own July finding on the live view:

| source | action | side | n | edge_20d | win_rate_20d |
|---|---|---|---:|---:|---:|
| CALL | REMOVE | **short** | 75 | **+6.30%** | 76% |
| CALL | ADD | long | 13,259 | +0.48% | 49% |
| CALL | REMOVE | long | 7 | −10.27% | 0% |

The short leg's +6.30% (n=75) closely reproduces July's cited +5.26%
(n=82) — the pooled-vs-split gap the design doc flagged is real and
reproducible on this system's own view, not a one-off from the original
investigation. **n=75 clears the ≥30 bar** — this is the strongest single
finding in this report. Per Addendum D1, the short leg is eligible to enter
the vote for bear stances (still gated behind TASK_140/141's switch
mechanism, not auto-enabled here); the long leg (n=13,259 but edge ≈ +0.5%,
not distinguishing) stays muted regardless.

## E. Per-theme one-line summary (all 22)

| Theme | Best cell with a positive ≥30-sample edge | Note |
|---|---|---|
| Rates up | RR/B stance, edge_20d +4.93%, n=32 | strongest macro read so far |
| Precious metals | stance/B, edge_20d +3.32%, n=41 | consistent with "extended bull" read |
| Healthcare | stance/B, edge_20d +3.32%, n=41 | — |
| Crypto | stance/S, edge_20d −15.87% (i.e. right to be short), n=32 | strong but single-regime (one crypto drawdown) |
| Tech/software | stance/B, edge_20d +6.56%, n=32 | win rate only 50% — volatile, not high-conviction yet |
| Cash/short FI | none (edge ≈ 0) | n≥30 but no edge — "being long T-bills" isn't a return driver by construction |
| Small caps | none positive (edge_20d −1.04% on B, n=41) | the lists' bull tilt on Small caps hasn't paid off yet in this window |
| Cyclicals | none positive (edge_20d −2.36% on B, n=41) | same caveat |
| Defensives, USD, Developed intl, Emerging, Momentum, Duration, Energy, Semis | none — all THIN (n<30) | — |
| Breadth, Industrial metals, Large caps, Volatility | **excluded — no proxy ETF seeded** | — |
| SSS sectors (all 8 with data) | none — all THIN (n<30 non-overlapping observations) | — |

**Nothing here is proposed for the decision path.** Per Addendum E3 the bar
is n≥30 AND a scorecard that's been re-checked more than once; this is the
first check.

## F. Verdicts

| # | Claim | n | Verdict |
|---|---|---|---|
| 1 | Theme stance (B/S) predicts the theme's proxy ETF forward 20d return | up to 41 | **THIN overall — 5 of 18 scored themes clear n≥30 with a clean sign**; re-check after another 4-8 weeks of history before using any of them |
| 2 | Agreement count (`agree_n`) strengthens the read | ≤20 per bucket | **THIN — no bucket cleared n≥30 in isolation** |
| 3 | Quad conflict weakens/changes the read | ≤35 per bucket | **THIN — inconclusive** |
| 4 | SSS row/book 4wk change predicts sector ETF forward return | ≤28 | **THIN — no sector cleared n≥30** |
| 5 | List-breadth turns (net-cross-zero, −25%, flip-day) precede SPX 20d drawdowns | 0-23 | **UNTESTABLE this window — zero qualifying drawdown events occurred** |
| 6 | CALL short-leg (Addendum D1) has a real, separate edge from the pooled series | 75 | **HELD** — reproduces the design doc's July finding almost exactly |

**Bottom line:** one claim (#6, CALL short-side split) clears the bar today.
Everything else needs more calendar time — the nightly refresh
(`run_nightly_outcomes`, TASK_147 step 5) keeps growing `n` without a manual
step; re-run this report in 4-8 weeks.

---

## Caveats

1. **Autocorrelation, not independent samples.** A theme's daily/weekly vote
   rarely flips day to day — 41 "samples" for a theme that only changed
   stance twice in the window is much closer to 2-3 independent events than
   41. Every n above should be read as an upper bound on independence, not
   a literal sample-size guarantee. This is the single biggest reason to
   treat even the n≥30 rows here as "candidates," not settled findings.
2. **Single regime.** All 60 dates sit inside one continuing up-trend
   (TASK_139's carried-forward finding). None of these scorecards has been
   tested through a drawdown, a chop, or a genuine regime change yet.
3. **SSS/ETF/PS are weekly.** 60 calendar dates ≈ 8-9 weekly snapshots for
   these sources — `v_sss_sector_scorecard`'s "n" already reflects that
   (max 28, not 60); it will grow roughly 1/week going forward.
4. Nothing in this report, `derive_actionable.py`, `ref_trig_*`,
   `ref_settings` decision switches, or `ref_risk_gauge.is_active` changed
   as part of building it (diffed before commit).
