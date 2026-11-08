# Screens review + local LLM proposal — 2026-11-08

Basis: code and git history only. There is no page-view log, so "use" is inferred from how the screen is wired in, what it is linked from, and how recently it got real work. Rules-screen verdicts wait for `rules_engine_review_2026-11-08.md`.

## 1. Do I need this screen? (keep / decide / retire)

| Screen | What it is | Verdict | Why |
|---|---|---|---|
| Actionable, Dashboard (/), Portfolio, Universe, Builder | Core daily screens | **Keep** | Almost all recent work goes here. |
| Risk detail, Technical Rules Map | Detail pages opened from Dashboard / Technical | **Keep** | Reached by links, new, small. |
| Stock Hedgeye dossier | Opened from the Hedgeye panel on Actionable | **Keep** | Linked from a live panel; not in the menu on purpose. |
| File Monitor | Load status, scheduler control | **Keep** | You use it to see data lands. |
| Ingest Log | One list of file + email loads | **Decide (merge)** | Overlaps File Monitor. Suggest folding it into File Monitor as a tab and dropping the menu entry. |
| Ref Data | Edit lookup tables | **Keep** | Only place to edit reference tables. |
| DB Stats | Table sizes plus admin tools (rename symbol, missing symbols) | **Keep** | The admin tools have no other home. |
| DB Data (Explore) | Generic table viewer | **Keep, low priority** | Developer convenience. Could hide from the menu. |
| Digest | Pre-open and weekly digest from Hedgeye | **Decide** | Only worth it if you read it or the email replaces it. Counter below will tell. |
| Notes (rule candidates) | List of suggested rules | **Decide with rules review** | Tied to the rules engine. |
| Test Results | Shows test-run results | **Retire (suggest)** | Developer-only. `pytest` in the terminal does the same job. Not linked from anywhere except the menu config. |
| Rules, Rule Groups, Param Sets, Trace, Rule Flow, Rules Health, Trig, Composite Edit, Performance | Rules-engine editing and diagnosis | **Wait for rules review** | Keep or retire depends on whether the rules still drive the Final Call. Performance has value either way (it scores sources and actions). |

Smallest safe step: retire Test Results now, merge Ingest Log into File Monitor, and add a two-week page-view counter (one tiny table `meta_page_hit`, one line per page load) so the Digest/Notes/rules-screen decisions use real numbers instead of my guesses.

## 2. Local LLM — proposal

**Principle:** local first, one setting to switch. The model only rewords facts the database already holds. It never decides an action, never changes the Final Call, and numbers always come from the database, not from the model.

**What your machine can do:** 4-core laptop CPU (i5-8365U), 32 GB RAM, no graphics card. A 3B-parameter model (4-bit) runs about 3–5 words-ish (tokens) per second. 200 held symbols x 80 tokens would take about an hour, so the first uses must be small and overnight, not "explain every row".

**Configurable design (one small module, `etl/llm.py`):**
| Setting (in `ref_settings`) | Example | Meaning |
|---|---|---|
| `llm_provider` | `ollama` / `hf_local` / `openai_compat` / `anthropic` / `off` | Which engine. Default `off`. |
| `llm_model` | `qwen2.5:3b-instruct` | Model name for that engine. |
| `llm_fallback` | `anthropic` or `none` | Used only if local fails or times out. |
| `llm_max_tokens`, `llm_timeout_s` | 120, 60 | Safety limits. |

- **ollama:** easiest local route. It can also pull Hugging Face models directly (`ollama run hf.co/<repo>`), so you still get the Hugging Face catalog without extra Python code.
- **hf_local:** Hugging Face `transformers` on CPU. Works (`transformers` is already installed) but is 3–10x slower than ollama/llama.cpp for the same model. Fine for small jobs (embeddings, classifiers), poor for text writing.
- **openai_compat:** any local server speaking the OpenAI format (LM Studio, llama.cpp server).
- **anthropic:** the Claude API as the fallback or later upgrade. Needs a key in `.env` only.
- Output is cached in a table keyed by (date, symbol, hash of the input), so nothing is generated twice and the screen never waits on the model.

**Suggested models for this PC:** Qwen2.5-3B-Instruct or Llama-3.2-3B (writing), Phi-3.5-mini (short summaries), `bge-small` / `all-MiniLM` for search-by-meaning (tiny, fast, runs fine through Hugging Face on CPU).

**Use cases, best first:**
1. **Daily market paragraph** on the Dashboard, built from existing Why-cards + Macro Week + Hedgeye changes. One paragraph a day, generated overnight. Low cost, high readability.
2. **Plain-English rewrite of the Why-this-action card** for held names and today's top actions only (~20 rows).
3. **Email digest wording** (pre-open / weekly).
4. **Search by meaning over Notes and Hedgeye emails** (embeddings, no text generation).
5. **Hedgeye email classification fallback** when the rule-based classifier fails.

**Not for:** picking buys/sells, scoring, anything numeric, anything needing instant response.

**Phases:** (1) install Ollama + pull one 3B model, add `etl/llm.py`, switch off by default, one test script; (2) daily market paragraph; (3) Why-card rewrite for held/top rows; (4) embeddings search. Each phase is independent and reversible; `llm_provider=off` removes all of it from the screens.

## 3. Open choices for the user (answers needed)
1. Retire Test Results and fold Ingest Log into File Monitor?
2. OK to add the two-week page-view counter?
3. LLM: approve phase 1 (install Ollama, small model, default off)?
