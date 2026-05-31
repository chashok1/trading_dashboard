# Architecture & Data-Flow Diagrams

Easy-to-read Mermaid diagrams of the whole system. These render in GitHub, VS Code, and
most Markdown viewers. They complement the per-screen SVGs in `docs/diagrams/`.

Last verified against code: **2026-05-31** (post `drv_ma → VIEW` migration; post unused-code cleanup).

> Note: `v_dash(D)` and `v_stks(D)` are parameterised **functions** (not simple views) —
> they accept a date arg and return `SETOF drv_dash` / `SETOF drv_stks`.

---

## 1. End-to-end pipeline (source files → screens)

```mermaid
flowchart LR
    subgraph SRC["17 source feeds (etl/working/)"]
        F["TOS / Y / ETF / II / RR /\nCS / F / PS / call ... .xlsx/.csv"]
    end

    subgraph LOAD["Ingest — etl/scheduler.py"]
        W["watchdog folder watch"] --> L["etl_load.load_one_file"]
        L --> MAP["mappings.HIST_MAPS /\nload_raw.CUSTOM_HANDLERS"]
    end

    subgraph DB["PostgreSQL (trading)"]
        H[("hist_*  raw, append-only\nON CONFLICT DO NOTHING")]
        D[("drv_*  derived, idempotent")]
        R[("ref_*  lookup / tunable")]
        M[("meta_*  run audit")]
    end

    subgraph API["FastAPI (127.0.0.1:8000)"]
        V["v_dash(D) · v_stks(D) · drv_ma VIEW\nv_rule_performance · v_available_dates"]
        RT["routers: dash, monitor, ref,\nrules, trace, pages, health"]
    end

    subgraph UI["web/ screens (vanilla JS + Chart.js)"]
        S["Dashboard · Cockpit · Actionable · Portfolio\nTrace · Rules · Groups · Composite-Edit\nPerformance · Rules-Health · Trig\nFile Monitor · Ref · Explore · DB Stats · Test Results"]
    end

    F --> W
    MAP --> H
    MAP --> M
    L -- "derive_all(D)" --> D
    H --> D
    R --> D
    D --> V --> RT --> S
    S -- "user acts / skips" --> ULOG[("user_action_log")]
    ULOG --> CO["compute_outcomes (nightly)"] --> D
```

---

## 2. Derive cascade (what `derive_all(session, D)` runs, in order)

`drv_ma` is **not materialized** — it is a VIEW over the 5 component tables, so the cascade
populates those five, then everything downstream reads them through the VIEW.

```mermaid
flowchart TD
    Q["drv_quote\n(latest-loaded-wins merge)"] --> SYM
    RR["drv_rr"] --> OUT
    subgraph COMP["5 component tables (drv_ma VIEW joins these)"]
        SYM["drv_symbols"]
        TEC["drv_technicals"]
        FUN["drv_fundamentals"]
        OUT["drv_outlooks"]
        POR["drv_portfolio"]
    end
    SYM --> TEC
    SYM --> FUN
    SYM --> OUT
    SYM --> POR
    COMP -. "JOIN" .-> MAV{{"drv_ma  (VIEW)"}}
    MAV --> CAT["drv_cat_atomic_input"]
    CAT --> DASH["drv_dash"]
    DASH --> STKS["drv_stks"]
    MAV --> OA["drv_outlook_action"]
    STKS --> ACT["drv_actionable\n(consolidated_action, trig_action,\ntriggered_group_ids)"]
    OA --> ACT
    ACT --> TRIG["drv_trig"]

    classDef view fill:#fef3c7,stroke:#b45309,color:#92400e;
    class MAV view;
```

> Each step is idempotent: `DELETE WHERE as_of_date=D` then `INSERT`. Re-running for date D
> is safe. `derive_v2.py` overrides v1 for **tw** and **sss** only — etf / ii / ps overrides
> were archived 2026-05-12; ssh was never implemented (drv_ssh retired).

---

## 3. Snapshot-date mental model (a read on the Dashboard)

```mermaid
flowchart LR
    U["user picks date D"] --> GET["GET /api/dash?date=D"]
    GET --> VD["SELECT * FROM v_dash(D)"]
    VD --> DD[("drv_dash WHERE as_of_date=D")]
    DD --> MA{{"drv_ma VIEW"}}
    MA --> C1[("drv_symbols")]
    MA --> C2[("drv_technicals")]
    MA --> C3[("drv_fundamentals")]
    MA --> C4[("drv_outlooks")]
    MA --> C5[("drv_portfolio")]
    C1 --> HS[("latest hist_* where snapshot_date ≤ D")]
    HS --> XL["Excel source files"]
    classDef view fill:#fef3c7,stroke:#b45309,color:#92400e;
    class MA view;
```

---

## 4. Rules engine (three tiers → recommendation)

```mermaid
flowchart TD
    subgraph INPUT["per-symbol wide row"]
        IN["drv_ma VIEW  LEFT JOIN  drv_cat_atomic_input\n(by as_of_date, tos_symbol)"]
    end
    IN --> AT["Atomic rules\nref_trig_atomic_rule"]
    AT --> CM["Composite rules\nref_trig_composite_mapping"]
    CM --> RG["Rule groups\nref_trig_rule_group + ref_trig_group_member\n(AND/OR over composites)"]
    RG --> SYN["Fired groups → synthetic action candidates"]
    SYN --> ACT["drv_actionable\n(consolidated + trig_action)"]
    AT --> TRIG["drv_trig (per-rule fire log)"]

    NOTE["Rebuild after editing rules:\npython -m etl.rebuild_rules"]
```

---

## 5. Feedback loop (action → outcome → performance)

```mermaid
flowchart LR
    A["User acts/skips on a screen"] --> UL[("user_action_log\n+ snapshot of firing rules")]
    UL --> CO["compute_outcomes.py (nightly,\nentries ≥ 5 days old)"]
    CO --> FR["forward return via drv_ma VIEW\n(drv_technicals / drv_quote)"]
    FR --> RO[("drv_rule_outcome\n1 row per triggered rule")]
    RO --> VP["v_rule_performance(_window)\nhit rate · avg return"]
    VP --> PERF["Performance screen"]
```
