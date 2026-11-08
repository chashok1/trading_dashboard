# Next session — where we stopped (2026-11-08)

Read this first when you come back. Detail lives in the linked reports.

## Done today
- Repo root cleaned: logs, debug scripts, old notes, archived agent tasks deleted. Batch files moved to `bat/`, one-off scripts to `scripts/`, your data files to `data/` (git-ignored). New-file rule added to `CLAUDE.md`.
- Windows auto-start registration removed everywhere (File Monitor UI, API, docs, 3 bats). Any Task Scheduler / Startup-folder entry you created earlier must be deleted by hand.
- All earlier uncommitted work committed in 8 groups.
- Reviews written (all in `docs/audit/`): `prework_2026-11-08.md`, `rules_engine_review_2026-11-08.md`, `screens_and_llm_proposal_2026-11-08.md`.
- Factor Weights: calculation core built and tested (`etl/factor_lab_core.py`, `tests/test_factor_lab_pure.py`, 9 tests pass). **Not** wired to the database, no tables, no API, no screen yet.

## Not committed yet
`docs/audit/*_2026-11-08.md` (3 reports + this file), `etl/factor_lab_core.py`, `tests/test_factor_lab_pure.py`. `.claude/settings.local.json` is yours; leave it out.

## Decisions waiting for you
**A. Rules engine** (report: `rules_engine_review_2026-11-08.md`). It runs daily but never won the Final Call (0 of 244,814 rows); it only fills the Trig column, a Why-card line and a display-only low-confidence flag.
1. Should it ever drive the Final Call? Recommend **no** (evidence display only).
2. Hide Rules, Rule Groups, Composite Edit, Param Sets, Rules Health, Trig from the menu (delete code later)? Recommend **yes**. Keep Rule Flow, Rule Performance, Trace.
3. Delete the 2 test groups and 6 never-fired composites? Recommend **yes**; leave the 46 unused atomic rules for now.
4. Fix the scorecard baseline (market-relative, trading-day counts) and restart the stale outcomes job (ends 2026-10-07)? Recommend **yes**. Same fix Factor Weights needs.
5. Hide the Trig column (keep the Rule Flow link)? Recommend **yes**.

**B. Spec 12** (`DESIGN_SPEC_12.md`, you said "we will come back"; all recommended yes; Final Call unchanged)
1. Replace the 🎯 score with an Entry label; rename Trade/Trade2 to "Buy now"/"Pullback".
2. "Buy now" = bottom 25% of the range.
3. MACRO veto only, plus a "MACRO says no" pill.
4. Drop the PVV AVOID veto and BUY_DIP boost.
5. Hide MACD / MACDH / PVV / CALC / P(↑20d) / Agree by default.
6. Keep your "BUY TO MIN only above the Trade line" rule.

**C. Factor Weights** (`DESIGN_SPEC_13.md`; you approved building it). Next steps in order: baseline fix (A4) → schema in `db/baseline.sql` → `etl/derive_factor_lab.py` → `etl/compute_factor_weights.py` → scheduler hook → API → screen → docs. Needs DB access to validate; the review agent showed read-only DB queries work through an agent.

**D. Screens** (`screens_and_llm_proposal_2026-11-08.md`)
1. Retire Test Results? Recommend yes.
2. Fold Ingest Log into File Monitor? Recommend yes.
3. Add a two-week page-view counter to decide on Digest, Notes and the rules screens with real numbers? Recommend yes.

**E. Local LLM** (same report). Machine: 4-core CPU, 32 GB RAM, no GPU. Local first, configurable (`ollama` / Hugging Face / OpenAI-compatible / Claude API fallback), off by default, display-only. Approve phase 1 (install Ollama + one 3B model, `etl/llm.py`, daily market paragraph)?

## Other open items
- `CLAUDE.md` Lookup index has no row yet for Factor Weights or the new audit reports.
- Old backlog: volume-rule re-classification (on hold), macro quad time-decay (not designed), quad-rotation idea (not scoped).
- Spec 12 bugs to fix with that work: scorecard baseline mismatch, dead "3rd strict pass" in `_isTradeModeQualifyingBuy`, stale comment in `_signalReasons`.
- Technical sell steps look weak (Sell All followed by a rise 56.5% of the time, n=36,895): worth a separate look.
- Spec 12 "worth reconsidering": no buy layer has beaten the average stock in 8 months; wait 4–6 weeks of history for the 23 Oct Technical rules, then prune weak buy sources (TOP5, PS) — changes the Final Call, needs your approval.
