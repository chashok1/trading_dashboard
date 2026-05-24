# MA Tab JG..NO — Source Audit & Flattening Proposal

_Generated from `Tickers 2026-04-30.xlsx` MA tab, columns JG (267) through NO (379) — 113 columns total._

## TL;DR

The JG..NO range is the **rules-engine evaluation layer** of the MA tab. It contains **no new external data sources** — every formula in this range is either:

* a lookup against the `Trig!` threshold sheet (72 cols), already in the DB as `ref_trig_atomic_rule` + `ref_trig_composite_mapping`, or
* an in-row arithmetic / conditional expression (41 cols) that operates on EARLIER MA columns and a few constants.

Every output of this range is **already produced by the Python rules engine** in `drv_stks` (atomic + composite fires) and `drv_actionable` (the consolidated decision). **No new tables are needed and the existing rules engine already replicates this entire layer.**

Of the upstream tables that feed this range, only **two carry their weight**: `drv_td` (34 ref-instances) and `drv_tw` (61 ref-instances). `hist_rr` appears in 2 cells. **The other per-sheet derived tables (`drv_call`, `drv_ii`, `drv_etf`, `drv_ps`, `drv_tl`) are not referenced anywhere in JG..NO.**

---

## 2026-05-12 update — rules engine plumbing now wired end to end

This section is the canonical "what's the current state of the rule engine?"
read. The 113-column analysis below remains correct; this addendum reports
the fixes made on 2026-05-12 and the remaining deferred work.

### What changed

**1. `ref_trig_atomic_rule.rule_name` now populated.**
The workbook loader (`etl/load_raw.py:load_trig_rules`) used to write only
`ma_column_name` (Trig col L) and leave `rule_name` NULL. The resolver in
`etl/derive.py:_resolve_atomic_input_column` keys lookups on `rule_name`, so
**every atomic rule silently evaluated to 0** — the rule engine was running but
producing nothing. Loader now mirrors col L into both `rule_name` and
`ma_column_name`. The resolver additionally falls back from `rule_name` →
`ma_column_name` so an unreloaded DB keeps working until the next workbook
ingest. Backfill SQL: `db/seeds_rule_engine_backfill.sql` (idempotent).

**2. Loader skip-condition fixed.**
`load_trig_rules` was skipping any Trig row where both col A and col B were
empty. Many real atomic rules (e.g. row 5 "MACDH Direction", row 7 "BB
Direction", row 11 "Trade Cross Over") have only col L populated and were
never inserted. Skip condition is now "skip iff col L is empty". On the next
workbook reload, the missing rows will appear in `ref_trig_atomic_rule`.

**3. `/api/trace/{sym}` bugs fixed.**
Two unbound-name bugs in `api/routers/trace.py` were preventing the endpoint
from returning successfully:
* `d.isoformat()` → `snap.isoformat()` (the snapshot date variable is `snap`)
* `n_atomic_fired` was referenced in the summary dict but never initialized
  or incremented; counter is now zeroed before the atomic loop and bumped
  whenever an atomic rule fires.

**4. Actionable screen now shows atomic-rule contributions.**
`web/actionable.js` was rendering composite-rule pills with no drill-down.
Each pill is now clickable: it fetches `/api/trace/{sym}` (cached per
session) and opens an inline popover listing every atomic rule that maps to
the clicked composite, with value / breakouts / weight / fired status. The
popover sorts fired rules first by absolute weight.

**5. Dismiss button added to the actionable modal.**
A second button next to **Save** posts `user_action='SKIPPED'` with no
snooze and notes defaulting to "dismissed". Reuses the existing
`/api/actionable/{symbol}/action` endpoint and the existing `SKIPPED`
CHECK-constraint value — no schema change.

### Files touched 2026-05-12

| File | Change |
|------|--------|
| `etl/load_raw.py`                     | `load_trig_rules`: skip iff col L empty; mirror col L into `rule_name`. |
| `etl/derive.py`                       | `_resolve_atomic_input_column`: prefetch includes `ma_column_name`; added fallback step 5 (bare lookup) and step 6 (legacy map by ma_column_name). |
| `api/routers/trace.py`                | Fixed `d.isoformat()` → `snap.isoformat()`; initialize & increment `n_atomic_fired`. |
| `web/actionable.html`                 | Popover container; Dismiss button; CSS for popover and clickable pills. |
| `web/actionable.js`                   | Clickable pill handler `openAtomicPopover()`; `dismissUserAction()`; per-session trace cache. |
| `db/seeds_rule_engine_backfill.sql`   | New. Backfills `rule_name = ma_column_name` for existing DB rows. |
| `docs/extracts_2026-05-12_trig/`      | New. Workbook Trig tab extracted: 115 atomic rules, 67 composites, 502 mappings, 641 MA headers. |

### How to apply on an existing database

```cmd
:: 1. Backfill rule_name for rows already in the DB:
psql -d trading -f db\seeds_rule_engine_backfill.sql

:: 2. Reload the Trig tab from the workbook (picks up rules previously
::    dropped by the skip-condition bug, and stamps rule_name on new rows):
python -m etl.tickers_initial_load

:: 3. Rebuild drv_stks / drv_trig for the snapshot dates you care about:
python -m etl.derive --target drv_stks --as-of YYYY-MM-DD
```

The atomic-rule popover lights up automatically once the underlying data is
present — no app restart needed.

### Deferred

**`drv_cat_atomic_input` is still empty.**
The wide table exists in `baseline.sql` (~113 columns) but nothing populates
it. The rules engine has a fallback that reads from `drv_ma`, so this is a
performance question rather than a correctness one. Populating it is a
straightforward but careful ETL change — a `derive_cat_atomic_input` step
that reads from `drv_ma` and the per-sheet `drv_*` tables, then writes the
113 columns in one batch. **Estimated**: half a day to write, half a day to
verify parity against the legacy fallback path. **Trigger to do this**: when
the `_resolve_atomic_input_column` warnings start mentioning the same rule
names repeatedly OR when the rules engine becomes a perf bottleneck.

**Workbook composites that aren't in the DB.**
The 2026-04-30 Trig tab contains 67 composite codes (`composite_rules.csv`).
`load_trig_rules` uses `ON CONFLICT DO NOTHING` on the
`ref_trig_composite_mapping` PK `(composite_rule_code, atomic_rule_id)`, so
it inserts new mappings but **never deletes mappings the workbook has
removed**. If the workbook is the source of truth, the loader should
DELETE-then-INSERT each composite's mappings, or set `deprecated_at` on
mappings whose composite_rule_code is absent from the latest workbook. Not
done in this pass.

**No automated test covers the rule engine end-to-end.**
The fixes above are intentionally small and reviewable, but a regression
would not be caught until a user notices. Adding a fixture xlsx with 2-3
known stocks, a known Trig tab, and expected `drv_stks.triggered_atomic_ids`
output would be the highest-leverage test to write.

---


## Classification of the 113 columns

| Kind | Count | Description |
|------|-------|-------------|
| `rule_threshold_lookup` | 72 | Pattern: `IFS($X2 >= XLOOKUP(X$1, Trig!$B$4:$B$144, Trig!$D$4:$D$144,…))` — compares a per-symbol value against a per-rule threshold from the `Trig!` sheet. |
| `arithmetic`            | 14 | Pure math on earlier MA cells (e.g. `JO = (-1)*JN2`). |
| `conditional`           | 26 | `IF(...)` chains over earlier MA cells (e.g. `JG = IF(CK2=0,-1,SIGN(CK2))`). |
| `other`                 | 1 | Misc — single-cell ref or non-pattern. |

## What feeds this range — DB tables

Every upstream MA cell referenced by JG..NO traces back to one of:

| DB table | Direct refs from JG..NO | Comment |
|----------|-------------------------|---------|
| `drv_tw` | 61 | SMAs, MACDs, weekly volume, perf metrics — heavy use |
| `drv_td` | 34 | BB band family, IV/HV percentiles, RSI variants |
| `hist_rr` | 2 | Risk Range buy/sell prices |
| (in-MA computed)        | 328 | Pure arithmetic on earlier MA cells — no extra tables needed |
| (unmapped MA cells)     | 82 | See section below |

## Notably ABSENT from JG..NO

These per-sheet derived tables are **not referenced anywhere** in this range:

* `drv_call`
* `drv_ii`
* `drv_etf`
* `drv_ps`
* `drv_tl`

`drv_ssl` / `drv_sss` are also absent (and already retired in `db/28_drop_ssl_sss.sql`).

**Implication for flattening:** if `drv_call`, `drv_ii`, `drv_etf`, `drv_ps`, `drv_tl` only exist to back the *outlook-action pipeline* (and not the rules engine), they may be candidates for inlining or removal — see the recommendations below.

## Top 25 upstream MA columns

| Letter | Col # | Times referenced | Header | Source |
|--------|-------|------------------|--------|--------|
| D | 4 | 37 | Close | (in-MA derived) |
| AZ | 52 | 24 | BB_Streak_Days | (in-MA derived) |
| AC | 29 | 23 | SDorMedian | (in-MA derived) |
| EE | 135 | 21 | BRR% | (in-MA derived) |
| DT | 124 | 21 | ImpVolatility | (scalar from drv_dash) |
| AY | 51 | 20 | BB_Streak | (in-MA derived) |
| DS | 123 | 18 | RSI | (scalar from drv_dash) |
| CG | 85 | 14 | 50 DMA | drv_tw |
| CH | 86 | 14 | 200 DMA | drv_tw |
| FR | 174 | 12 | IVHV | (in-MA derived) |
| CM | 91 | 12 | A_MACDays_Streak | drv_tw |
| AX | 50 | 11 | BBThresh_CO_Days | (in-MA derived) |
| BY | 77 | 9 | Perf3D_sd | (in-MA derived) |
| AF | 32 | 8 | A_TradeValue | drv_td |
| CX | 102 | 8 | IVPercentile | drv_td |
| FK | 167 | 7 | VS Price Change SD | (in-MA derived) |
| FI | 165 | 7 | VS Volume Spike | (in-MA derived) |
| FL | 168 | 7 | VS Volatility | (in-MA derived) |
| FM | 169 | 7 | VS Days | (in-MA derived) |
| H | 8 | 7 | Last %Change | (in-MA derived) |
| AD | 30 | 7 | SD% | (in-MA derived) |
| GB | 184 | 7 | Vlm 3m % | (in-MA derived) |
| AH | 34 | 6 | Trade_sd | (in-MA derived) |
| AE | 31 | 6 | A_TrendValue | drv_td |
| BZ | 78 | 6 | Perf3D_Value | (in-MA derived) |

## Unmapped MA cells (in seed but missing pg_name)

These letters appear in JG..NO formulas but our `ma_columns_registry_seed.csv` doesn't have a `proposed_pg_name` for them — either pure passthrough/identity cols or the seed was incomplete:

| Letter | Col # | Header (from row 1) |
|--------|-------|----------------------|
| AC | 29 | SDorMedian |
| DT | 124 | ImpVolatility |
| DS | 123 | RSI |
| H | 8 | Last %Change |
| EF | 136 | Prev Close |
| EI | 139 | Low |
| J | 10 | Low |
| I | 9 | High |
| EH | 138 | High |

## Per-column inventory (full 113 rows)

| Letter | Header | Formula (truncated 100 chars) |
|--------|--------|-------------------------------|
| JG | MACDH Direction | `=IF(CK2=0,-1,SIGN(CK2))` |
| JH | MACD Direction | `=IF(CI2=0,-1,SIGN(CI2))` |
| JI | BB Direction | `=AN2` |
| JJ | BB Threshold | `=IF(AX2=1,AW2,0)` |
| JK | BBThresh CO Days | `=_xlfn.IFS($AX2>=_xlfn.XLOOKUP(AX$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AX$1,Trig!$` |
| JL | BBThresh_CO_Days2 | `=_xlfn.IFS($AX2>=_xlfn.XLOOKUP(JL$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(JL$1,Trig!$` |
| JM | Trade Cross Over | `=_xlfn.IFS(AND(D2>AF2,AF2>MIN(EF2,J2)), 1, AND(MAX(EF2,I2)>AF2,AF2>D2), -1, TRUE,0)` |
| JN | Trade-Rule | `=_xlfn.IFS($AH2>=_xlfn.XLOOKUP(AH$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AH$1,Trig!$` |
| JO | !Trade Rule | `=(-1)*JN2` |
| JP | Trend Cross Over | `=_xlfn.IFS(AND(D2>AE2,AE2>MIN(BZ2,EF2,J2)), 1, AND(MAX(BZ2,EF2,I2)>AE2,AE2>D2), -1, TRUE,0)` |
| JQ | Trend-Rule | `=_xlfn.IFS($AG2>=_xlfn.XLOOKUP(AG$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AG$1,Trig!$` |
| JR | !Trend Rule | `=(-1)*JQ2` |
| JS | Trend Trade Dep Rule | `=IF(AE2<=AF2,JQ2,JN2)` |
| JT | TrTn Relation | `=IF(AE2<=AF2,1,-1)` |
| JU | !TrTn Relation | `=(-1)*JT2` |
| JV | Trade Trend SD Rule | `=_xlfn.IFS($AI2>_xlfn.XLOOKUP(AI$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AI$1,Trig!$B` |
| JW | BRR% Rule | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(JW$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""), _xlfn.XLOOKUP(JW$1,Trig!$` |
| JX | BRR% LRR | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(JX$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""), _xlfn.XLOOKUP(JX$1,Trig!$` |
| JY | BRR% R2 | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(JY$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""), _xlfn.XLOOKUP(JY$1,Trig!$` |
| JZ | BRR% LRR2 | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(JZ$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""), _xlfn.XLOOKUP(JZ$1,Trig!$` |
| KA | BRR% TRR | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(KA$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""), _xlfn.XLOOKUP(KA$1,Trig!$` |
| KB | BRR% Puts | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(KB$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""),  _xlfn.XLOOKUP(KB$1,Trig!` |
| KC | BRR% TRR Puts | `=_xlfn.IFS($EE2<=_xlfn.XLOOKUP(KC$1,Trig!$B$4:$B$144,Trig!$C$4:$C$144,""),  _xlfn.XLOOKUP(KC$1,Trig!` |
| KD | BRR% Dir | `=_xlfn.IFS(AND(JI2=1,JG2=1), JW2, AND(JI2=-1,JG2=-1),KB2, LG2>0, JW2, LG2<0, KB2)` |
| KE | High TRR | `=_xlfn.IFS($EO2>=_xlfn.XLOOKUP(KE$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KE$1,Trig!$` |
| KF | Low LRR | `=_xlfn.IFS($EP2>=_xlfn.XLOOKUP(KF$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KF$1,Trig!$` |
| KG | Trend below TRR | `=IF(EQ2<0,-1,0)` |
| KH | LRR above Trade | `=IF(ER2>0,1,0)` |
| KI | TRR_Idx | `=_xlfn.IFS($ES2>=_xlfn.XLOOKUP(KI$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KI$1,Trig!$` |
| KJ | MRR_Idx | `=_xlfn.IFS($ET2>=_xlfn.XLOOKUP(KJ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KJ$1,Trig!$` |
| KK | LRR_Idx | `=_xlfn.IFS($EU2>=_xlfn.XLOOKUP(KK$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KK$1,Trig!$` |
| KL | HVAbsolute | `=_xlfn.IFS($CV2>=_xlfn.XLOOKUP(KL$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KL$1,Trig!$` |
| KM | IVAbsolute | `=_xlfn.IFS(DT2=0,0,$DT2>=_xlfn.XLOOKUP(KM$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KM$` |
| KN | IVPercentile | `=_xlfn.IFS(OR(DT2=0,CX2=0),0,$CX2>=_xlfn.XLOOKUP(KN$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.X` |
| KO | IVPercentile Puts | `=_xlfn.IFS(OR(DT2=0,CX2=0),0,$CX2>_xlfn.XLOOKUP(KO$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XL` |
| KP | HVPercentile | `=_xlfn.IFS(OR(DT2=0),0,$CW2>=_xlfn.XLOOKUP(KP$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP` |
| KQ | HVPercentile Puts | `=_xlfn.IFS(OR(DT2=0),0,$CW2>_xlfn.XLOOKUP(KQ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(` |
| KR | IVHV | `=_xlfn.IFS(DT2=0,0,$FR2>=_xlfn.XLOOKUP(KR$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KR$` |
| KS | IVHV Puts | `=_xlfn.IFS(DT2=0,0,$FR2>=_xlfn.XLOOKUP(KS$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KS$` |
| KT | IVRule | `=_xlfn.IFS(DT2=0,0,AND(KN2>=3,KP2>=3,KR2>=3),3,AND(KN2>=2,KP2>=2,KR2>=2),2,TRUE,1)` |
| KU | RSI Rule | `=_xlfn.IFS($DS2>=_xlfn.XLOOKUP(DS$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(DS$1,Trig!$` |
| KV | RSI Top | `=_xlfn.IFS($DS2>=_xlfn.XLOOKUP(KV$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KV$1,Trig!$` |
| KW | RSI Puts | `=_xlfn.IFS($DS2>_xlfn.XLOOKUP(KW$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(KW$1,Trig!$B` |
| KX | 3m-Low-Rule | `=_xlfn.IFS($BB2>=_xlfn.XLOOKUP(BB$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BB$1,Trig!$` |
| KY | 3m-Low-Days Rule | `=_xlfn.IFS($BC2>=_xlfn.XLOOKUP(BC$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BC$1,Trig!$` |
| KZ | 3mn-High-Rule | `=_xlfn.IFS($BE2>=_xlfn.XLOOKUP(BE$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BE$1,Trig!$` |
| LA | 3mn-High-Days Rule | `=_xlfn.IFS($BF2>=_xlfn.XLOOKUP(BF$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BF$1,Trig!$` |
| LB | 3m-Long | `=_xlfn.IFS(AND(KX2>=3,KY2>=2,KZ2>=-2,LA2>=3),3,AND(KZ2<=-3,LA2>=2,KX2<=2,KY2>=3),-3,TRUE,INT((KX2+KY` |
| LC | Perf3mn SD Rule | `=_xlfn.IFS($BQ2>=_xlfn.XLOOKUP(BQ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BQ$1,Trig!$` |
| LD | Perf2M SD Rule | `=_xlfn.IFS($BS2>=_xlfn.XLOOKUP(BS$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BS$1,Trig!$` |
| LE | Perf3WK SD Rule | `=_xlfn.IFS($BU2>=_xlfn.XLOOKUP(BU$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BU$1,Trig!$` |
| LF | Perf2WK SD Rule | `=_xlfn.IFS($BW2>=_xlfn.XLOOKUP(BW$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BW$1,Trig!$` |
| LG | Perf3D SD Rule | `=_xlfn.IFS($BY2>=_xlfn.XLOOKUP(BY$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BY$1,Trig!$` |
| LH | Perf1D SD Rule | `=_xlfn.IFS($CA2>=_xlfn.XLOOKUP(CA$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(CA$1,Trig!$` |
| LI | !Perf1D_sd | `=(-1)*LH2` |
| LJ | Perf3D_sd_1off | `=_xlfn.IFS(ABS($BY2)>=_xlfn.XLOOKUP(LJ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LJ$1,T` |
| LK | Perf SD Rule | `=_xlfn.IFS(AND(LC2>=3,LD2>=3,LE2>=3,LF2>=1,LJ2>=3),3,AND(LC2>=3,LD2>=3,LE2>=2,LF2>=1,LJ2>=3),2,AND(L` |
| LL | !Perf SD Rule | `=(-1)*LK2` |
| LM | !Perf3D Rule | `=(-1)*LG2` |
| LN | BBHighLow_SD Rule | `=_xlfn.IFS($AO2>_xlfn.XLOOKUP(AO$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AO$1,Trig!$B` |
| LO | BBHighLow Days Rule | `=_xlfn.IFS($AM2>_xlfn.XLOOKUP(AM$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AM$1,Trig!$B` |
| LP | BBStreak Rule | `=_xlfn.IFS($AY2>=_xlfn.XLOOKUP(AY$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AY$1,Trig!$` |
| LQ | BBStreakRule1 | `=_xlfn.IFS($AY2>=_xlfn.XLOOKUP(LQ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LQ$1,Trig!$` |
| LR | BBStreak Rule2 | `=_xlfn.IFS($AY2>=_xlfn.XLOOKUP(LR$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LR$1,Trig!$` |
| LS | BBStreak Days Rule | `=_xlfn.IFS($AZ2>=_xlfn.XLOOKUP(AZ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AZ$1,Trig!$` |
| LT | BBStreak Days Rule2 | `=_xlfn.IFS($AZ2>=_xlfn.XLOOKUP(LT$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LT$1,Trig!$` |
| LU | BBStreak Days Rule3 | `=_xlfn.IFS($AZ2>=_xlfn.XLOOKUP(LU$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LU$1,Trig!$` |
| LV | BBStreak Days Rule4 | `=_xlfn.IFS($AZ2>=_xlfn.XLOOKUP(LV$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(LV$1,Trig!$` |
| LW | BB Bull Rule | `=_xlfn.IFS(AND(LP2>=3,LS2>=3),3,AND(LP2<=-3,LS2<=-3),-3,TRUE,LN2)` |
| LX | BB Bull Puts | `=(-1)*LW2` |
| LY | BBHighDays | `=_xlfn.IFS($AQ2>_xlfn.XLOOKUP(AQ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AQ$1,Trig!$B` |
| LZ | BBLowDays | `=_xlfn.IFS($AR2>_xlfn.XLOOKUP(AR$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(AR$1,Trig!$B` |
| MA | MACD Rule | `=_xlfn.IFS($CJ2>=_xlfn.XLOOKUP(CJ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(CJ$1,Trig!$` |
| MB | MACDH Rule | `=_xlfn.IFS($CL2>=_xlfn.XLOOKUP(CL$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(CL$1,Trig!$` |
| MC | MACD and H Rule | `=INT((MA2+MB2)/2)` |
| MD | MACD_BRR Puts | `=_xlfn.IFS($CJ2>_xlfn.XLOOKUP(MD$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(MD$1,Trig!$B` |
| ME | MACDH_BRR Puts | `=_xlfn.IFS($CL2>_xlfn.XLOOKUP(ME$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(ME$1,Trig!$B` |
| MF | MACD and H Rule Puts | `=INT((MD2+ME2)/2)` |
| MG | MACDH Days | `=_xlfn.IFS($CM2>_xlfn.XLOOKUP(MG$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(MG$1,Trig!$B` |
| MH | MACDH Days2 | `=_xlfn.IFS($CM2>_xlfn.XLOOKUP(MH$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(MH$1,Trig!$B` |
| MI | Overbought | `=_xlfn.IFS(AND(KV2>=3,MA2>=3,MB2>=3),3,AND(KV2<=-3,MA2<=-3,MB2<=-3),-3,TRUE,0)` |
| MJ | !Overbought | `=(-1)*MI2` |
| MK | 3mn Outlook | `=_xlfn.IFS($BJ2>=_xlfn.XLOOKUP(BJ$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BJ$1,Trig!$` |
| ML | 3mn Outlook Days | `=_xlfn.IFS($BK2>=_xlfn.XLOOKUP(BK$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BK$1,Trig!$` |
| MM | 3wk Outlook | `=_xlfn.IFS($BN2>=_xlfn.XLOOKUP(BN$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BN$1,Trig!$` |
| MN | 3wk Outlook Days | `=_xlfn.IFS($BO2>=_xlfn.XLOOKUP(BO$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(BO$1,Trig!$` |
| MO | !3wk ol | `=(-1)*MM2` |
| MP | !3wk ol days | `=(-1)*MN2` |
| MQ | BULL | `=_xlfn.IFS(AND(JN2>=3,JQ2>=2,JV2>=2,LZ2>=3),3,AND(KH2>0,JV2>=2),3,AND(JN2>=2,JQ2>=2,JV2>=2,LZ2>=2),2` |
| MR | !BULL | `=(-1)*MQ2` |
| MS | PerfOrBull | `=_xlfn.IFS(OR(LK2>=3,MQ2>=3),3,OR(LK2<=-3,MQ2<=-3),-3, TRUE, INT((LK2+MQ2)/2))` |
| MT | !PerfOrBull | `=(-1)*MS2` |
| MU | 50-DMA-Rule | `=_xlfn.IFS(D2>=$CG2+_xlfn.XLOOKUP(CG$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,"")*AC2, _xlfn.XLOOKUP(CG$1` |
| MV | 50-DMA-Crossover | `=_xlfn.IFS(AND(D2>CG2,CG2>BZ2), 1, AND(BZ2>CG2,CG2>D2), -1, TRUE,0)` |
| MW | 200-DMA-Rule | `=_xlfn.IFS(D2>=$CH2+_xlfn.XLOOKUP(CH$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,"")*AC2, _xlfn.XLOOKUP(CH$1` |
| MX | 200-DMA-Crossover | `=_xlfn.IFS(AND(D2>CH2,CH2>BZ2), 1, AND(BZ2>CH2,CH2>D2), -1, TRUE,0)` |
| MY | 52-Wk Low Rule | `=_xlfn.IFS(D2>=$CC2+_xlfn.XLOOKUP(CC$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,"")*AC2, _xlfn.XLOOKUP(CC$1` |
| MZ | 52-Wk High Rule | `=_xlfn.IFS(D2>=$CD2+_xlfn.XLOOKUP(CD$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,"")*AC2, _xlfn.XLOOKUP(CD$1` |
| NA | BRRTrade | `=IF(ABS(DX2-AF2)<=AC2*0.5,1,0)` |
| NB | TRRTrade | `=IF(ABS(DY2-AF2)<=AC2*0.5,-1,0)` |
| NC | Up Resistance | `=IF(AND((EH2+0.05*AC2)>CG2,D2<CG2),-0.5,0)+IF(AND((EH2+0.05*AC2)>CH2,D2<CH2),-0.5,0)` |
| ND | Down Resistance | `=IF(AND((EI2+0.05*AC2)<BA2,D2>BA2),1,0)+IF(AND((EI2+0.05*AC2)>CG2,D2>CG2),0.5,0)+IF(AND((EI2+0.05*AC` |
| NE | Earnings | `=_xlfn.IFS($JB2>_xlfn.XLOOKUP(JB$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(JB$1,Trig!$B` |
| NF | VS Price | `=_xlfn.IFS(FK2=0,0,$FK2>_xlfn.XLOOKUP(FK$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(FK$1` |
| NG | VS Volume Spike | `=_xlfn.IFS(FI2=0,0,$FI2>_xlfn.XLOOKUP(FI$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(FI$1` |
| NH | VS Volatility | `=_xlfn.IFS(FL2=0,0,$FL2>_xlfn.XLOOKUP(FL$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(FL$1` |
| NI | VS Days | `=_xlfn.IFS(FM2=0,0,$FM2>_xlfn.XLOOKUP(FM$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(FM$1` |
| NJ | VS LT Outlook Rule | `=_xlfn.IFS(AND(NF2>2,NG2>0,NH2>2,NI2>2),3,AND(NF2>2,NG2>0,NH2<=2,NI2>=2),2,AND(NF2<-2,NG2>0,NH2>2,NI` |
| NK | Current Price SD Rule | `=_xlfn.IFS(OR(H2=0,AD2=0),0,(H2/$AD2)>_xlfn.XLOOKUP(NK$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlf` |
| NL | Current Volume Rule | `=_xlfn.IFS(GB2=0,0,$GB2>_xlfn.XLOOKUP(NL$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(NL$1` |
| NM | Current Volatility Rule | `=_xlfn.IFS(DT2=0,0,$DT2>_xlfn.XLOOKUP(NM$1,Trig!$B$4:$B$144,Trig!$D$4:$D$144,""), _xlfn.XLOOKUP(NM$1` |
| NN | Short Term Oulook (If LT Bullish) | `=_xlfn.IFS(AND(NK2>2,NL2>2,NM2<2),3,AND(NK2>2,NL2>2),2,AND(NK2<-2,NL2>2,NM2<2),-3,AND(NK2<-2,NL2>2),` |
| NO | Short Term Oulook (If LT Bearish) | `=_xlfn.IFS(AND(NK2>2,NL2>2,NM2<2),3,AND(NK2>2,NL2>2),2,AND(NK2<-2,NL2>2,NM2<2),-3,AND(NK2<-2,NL2>2),` |

## Flattening recommendations

### A. Within JG..NO itself

**Nothing to flatten — this range is purely formula evaluation, no data tables required.** The Python rules engine (`drv_cat_atomic_input` + `ref_trig_atomic_rule` + `drv_stks`) already produces the equivalent outputs. You do **not** need to mirror these MA columns into any DB table. The existing `drv2_*` retirement plan stands.

### B. Tables that ARE needed (keep)

* `drv_td` — feeds 34 references in JG..NO (BB family, percentiles, RSI). **Keep.**
* `drv_tw` — feeds 61 references (SMAs, MACD, weekly volume, perf). **Keep.**
* `hist_rr` — feeds 2 references (Risk Range thresholds). **Keep raw.**

### C. Tables NOT used by JG..NO (review for retirement after consulting other downstream consumers)

These derived tables don't show up anywhere in the rules-engine evaluation range. Their only justification is the outlook-action / dashboard pipelines. Each has a different story:

| Table | Outlook-action pipeline reads it? | Other readers? | Verdict |
|-------|-----------------------------------|----------------|---------|
| `drv_call`  | No (reads `hist_call` directly)              | `drv_dash` LEFT JOIN at derive.py:569 (descriptive cols only) | Could probably **drop**; inline the 2-3 cols into `drv_dash` query |
| `drv_ii`    | No (reads `hist_ii` directly)                | `drv_dash` LEFT JOIN at derive.py:589 (1-2 cols) | Could probably **drop**; same approach |
| `drv_etf`   | Was needed (workaround) — now reads `hist_etf` after `db/27_etf_use_hist.sql` | `drv_dash` LEFT JOIN at derive.py:581 | **Drop candidate** now that `hist_etf.outlook` exists |
| `drv_ps`    | No (`drv_actionable` reads `hist_psrk` directly via `ref_outlook_source`) | `drv_dash` JOIN | **Drop candidate** — `hist_psrk` has rank + asset_class already |
| `drv_tl`    | No                                            | `drv_dash` LEFT JOIN at derive.py:527 (vlm_projected, imp_volatility_clean) | **Keep** — derives 2 columns that don't exist on hist_tl |

### D. Recommended retirement order (lowest risk → highest)

1. `drv_etf` — already orphaned by the ETF outlook fix in `db/27_etf_use_hist.sql`. Verify nothing else reads it, drop next.
2. `drv_ps` — `hist_psrk` carries rank + asset_class natively. Inline the 2 cols `drv_dash` needs.
3. `drv_call` — the only derived field is `weight` from outlook lookup. Inline into `drv_dash` query as a CASE expr.
4. `drv_ii` — same shape as `drv_call`. Inline.
5. `drv_tl` — keep for now; only 2 derived cols and they're useful for `vlm_projected`. Could be folded into `drv_dash` if you want to be aggressive.

### E. Retirement counter-arguments

Before dropping any of the above, consider that the registry's `source_expr` values still reference them in ~20 ref_ma_columns rows (from `db/24_backfill_source_expr.sql`). Dropping a table will leave those `source_expr` values pointing at vanished targets. Mitigation: re-run the backfill generator after each drop to re-resolve those rows (or accept that those MA-mirror cells stop working — they're not consumed by anything live anyway).

## Files generated for this audit

* `docs/ma_jg_no_audit.md` — this document
* `docs/_ma_jg_no_raw.json` — raw header + formula per cell
* `docs/_ma_jg_no_classified.json` — classified inventory
* `docs/_ma_jg_no_full.json` — full dependency map (upstream refs + table demand)
* `docs/_ma_jg_no_2nd_level.json` — 2nd-level trace of computed cells

---

## Status update — 2026-05-12 (changes applied)

The flattening proposal in this document has been **executed**. Summary of what shipped:

### Tables dropped

| Table | Migration | Reason |
|-------|-----------|--------|
| `drv_etf` | `db/29_drop_drv_etf.sql` | `hist_etf.outlook` now loaded from BULLISH/BEARISH section headers (`db/26_etf_outlook.sql` + `etl/load_raw.py:load_etf`); the `drv_dash` ETF CTE now reads `hist_etf.outlook` directly with the existing BRR-fallback CASE. |
| `drv_ps`  | `db/30_drop_drv_ps.sql` | Was built every run but never JOIN-ed into `drv_dash`, `drv_stks`, or any API endpoint. Pure dead weight. |
| `drv_call` | `db/31_drop_drv_call.sql` | The only field `drv_dash` consumed was `weight`. Replaced with an inline `LEFT JOIN ref_param ON sheet='outlook' AND UPPER(param_name)=UPPER(h.outlook)` returning `CAST(value AS NUMERIC) AS call_weight`. |
| `drv_ii`   | `db/32_drop_drv_ii.sql`   | Same shape as `drv_call`. Same inline `ref_param` JOIN replacement. |

(Also dropping the corresponding `drv2_*` mirrors as part of each migration.)

### Code changes

* `etl/derive.py` — replaced `cl`, `ef`, `ii` CTEs in the `drv_dash` query (no more `drv_call`/`drv_etf`/`drv_ii` JOINs); removed orchestration calls; cleaned `derive_v2` import block.
* `etl/derive.py` — removed `_derive_call_impl` and the `derive_call = _wrap(...)` line.
* `etl/derive_v2.py` — removed `_derive_etf_v2_impl`, `_derive_ii_v2_impl`, `_derive_ps_v2_impl` + their wraps.
* `etl/derive_outlook_action.py` — removed `drv_etf` from `_TABLE_MODIFIER_COL`.
* `etl/ma_codegen.py` and `etl/enrich_ref_ma_columns.py` — removed alias entries for the four tables.
* `db/reset_db.py` — removed the four tables from the cleanup list.

### Archived (preserved for replay)

* `etl/_archived/per_sheet_drv_derive.py` — documents what each retired deriver did and where its original implementation lived.

### Backfill regenerated

`db/24_backfill_source_expr.sql` was regenerated. Highlights:

* Adds a leading `UPDATE ref_ma_columns SET source_expr = NULL, source_table = NULL WHERE source_table IN ('drv_etf','drv_call','drv_ii','drv_ps','drv_ssl','drv_sss')` so any rows that previously pointed at the retired tables get re-resolved.
* Total UPDATE statements: **103**, all routing through `hist_*` tables (zero references to retired drv_*).
* MA columns that were previously mapped to `drv_etf.etf_entry` / `drv_ii.ii_entry` / `drv_ps.ps_rank` etc. now point at the equivalent column on the underlying hist_* table (e.g. `etf_entry → hist_etf.outlook_modifier`, `ps_rk → hist_psrk.rank`).
* Rows that depended on `drv_ssl` / `drv_sss` (already retired in the previous round) are NULL'd and not re-populated — those Excel MA cells (sg_rk, km, sgrk_chg, sg_strength, sgs_chg, sss_entry) no longer have a DB source.

### To apply locally

```
cd C:\Ashok\Invest\Projects\trading-dashboard
.venv\Scripts\activate
python -m db.init_db                       # picks up db/29..32 + regenerated db/24
python -m etl.derive --date <as_of_date>   # re-runs derive_all without the retired derivers
```

### Final state of the per-sheet drv_* layer

| Table | Status |
|-------|--------|
| `drv_td`, `drv_tw` | **Kept** — heavy users by JG..NO rules layer. |
| `drv_tl`           | **Kept** — derives `vlm_projected` + `imp_volatility_clean` (NaN cleaning); 2 cols not on `hist_tl`. |
| `drv_etf`, `drv_call`, `drv_ii`, `drv_ps` | **Dropped** (this round). |
| `drv_ssl`, `drv_sss` | Dropped (previous round). |
| `drv2_*` (the wide MA-tab projection layer) | All scheduled for drop in conjunction. |

The `drv_*` per-sheet layer now consists only of the three tables that genuinely add derived value beyond what the raw `hist_*` carries.
