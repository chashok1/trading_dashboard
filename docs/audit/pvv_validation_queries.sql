-- =====================================================================
-- Price / Volume / Volatility — LIVE DATA VALIDATION PACK
-- Run against the `trading` DB (localhost:5432). Cowork has no DB access,
-- so this is executed by the developer/tester agent (or by hand in psql).
-- Each query is labelled Q1.. and maps to a row in the report's
-- "Live Data Validation" results table (docs/audit/price_volume_volatility_analysis.md).
--
-- Convention: :d is the anchor date. Resolve it first:
--   SELECT MAX(export_date) AS anchor FROM hist_td;
-- Then substitute that date wherever :d appears (psql: \set d '2026-06-20').
-- =====================================================================

-- Q0 ANCHOR ----------------------------------------------------------
SELECT MAX(export_date) AS anchor_date FROM hist_td;

-- =====================================================================
-- A. JOIN COVERAGE  (universe vs component tables on the anchor)
-- =====================================================================
-- Q1 row counts across the universe + component tables (expect symbols >= each)
SELECT
  (SELECT count(*) FROM drv_symbols     WHERE as_of_date=:d) AS symbols,
  (SELECT count(*) FROM drv_technicals  WHERE as_of_date=:d) AS technicals,
  (SELECT count(*) FROM drv_quote       WHERE as_of_date=:d) AS quotes,
  (SELECT count(*) FROM drv_rr          WHERE as_of_date=:d) AS rr_rows,
  (SELECT count(*) FROM drv_cat_atomic_input WHERE as_of_date=:d) AS atomic_rows;

-- Q2 symbols in universe with NO technicals / NO quote (should be ~0 for active names)
SELECT s.tos_symbol
FROM drv_symbols s
LEFT JOIN drv_technicals t USING (as_of_date, tos_symbol)
LEFT JOIN drv_quote      q USING (as_of_date, tos_symbol)
WHERE s.as_of_date=:d AND (t.tos_symbol IS NULL OR q.tos_symbol IS NULL)
ORDER BY 1 LIMIT 100;

-- =====================================================================
-- B. PRICE — null rates, ranges, OHLC sanity, intraday/Close selection
-- =====================================================================
-- Q3 price null rates + ranges on the anchor
SELECT count(*) AS n,
  count(*) FILTER (WHERE last_price IS NULL) AS null_last,
  count(*) FILTER (WHERE last_price<=0)      AS nonpos_last,
  count(*) FILTER (WHERE high_price=0)       AS zero_high,
  count(*) FILTER (WHERE low_price=0)        AS zero_low,
  count(*) FILTER (WHERE open_price=0)       AS zero_open,
  min(last_price), max(last_price), round(avg(last_price)::numeric,2) AS avg_last
FROM drv_quote WHERE as_of_date=:d;

-- Q4 OHLC integrity violations (high<low, last outside [low,high]) — expect 0
SELECT count(*) AS ohlc_violations
FROM drv_quote
WHERE as_of_date=:d AND high_price>0 AND low_price>0
  AND (high_price < low_price
       OR last_price > high_price*1.001
       OR last_price < low_price*0.999);

-- Q5 intraday flag + freshness: how many quotes are intraday on the anchor
SELECT count(*) AS n,
  count(*) FILTER (WHERE is_intraday) AS intraday_rows,
  count(*) FILTER (WHERE NOT is_intraday) AS eod_rows
FROM drv_quote WHERE as_of_date=:d;

-- Q6 Close-selection cross-check: drv_quote.last vs TOSD prior-session last (D_Last)
--    big gaps may indicate stale or wrong-source selection
SELECT count(*) AS n,
  count(*) FILTER (WHERE q.last_price IS NOT NULL AND td.last_price IS NOT NULL
                   AND abs(q.last_price-td.last_price)/NULLIF(td.last_price,0) > 0.25) AS gt_25pct_gap
FROM drv_quote q
LEFT JOIN LATERAL (
  SELECT last_price FROM hist_td h
  WHERE h.tos_symbol=q.tos_symbol AND h.export_date<=:d
  ORDER BY h.export_date DESC LIMIT 1) td ON true
WHERE q.as_of_date=:d;

-- =====================================================================
-- C. VOLATILITY — SD denominator divergence (TOP FINDING), BB, RR, IV
-- =====================================================================
-- Q7 How many symbols have median_sd < standard_dev (where LEAST() would bite)
--    NOTE: in derive_cat_atomic_input the column "median_sd" is the LATEST
--    standard_dev (not a real median); the true running median lives only in
--    the SQL twin (_derive_trend_trade_rules_impl, percentile_cont).
SELECT count(*) AS n_with_tw,
  count(*) FILTER (WHERE med.median_sd < latest.standard_dev) AS median_lt_sd,
  count(*) FILTER (WHERE med.median_sd = latest.standard_dev) AS median_eq_sd
FROM (SELECT DISTINCT ON (tos_symbol) tos_symbol, standard_dev
        FROM hist_tw WHERE snapshot_date<=:d AND standard_dev IS NOT NULL
        ORDER BY tos_symbol, snapshot_date DESC, sequence DESC) latest
JOIN LATERAL (
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY standard_dev) AS median_sd
  FROM hist_tw h WHERE h.tos_symbol=latest.tos_symbol
    AND h.snapshot_date<=:d AND h.standard_dev IS NOT NULL) med ON true;

-- Q8 Direct divergence: trend_sd/trade_sd as stored by the two engines.
--    drv_cat_atomic_input (Python, AC=standard_dev) vs drv_tn_td_bb_rr (SQL, AC=LEAST).
--    Adjust table/column names if they differ in your schema.
SELECT count(*) AS n,
  count(*) FILTER (WHERE abs(coalesce(a.trend_sd,0)-coalesce(b.trend_sd,0))>0.01) AS trend_sd_diffs,
  count(*) FILTER (WHERE abs(coalesce(a.trade_sd,0)-coalesce(b.trade_sd,0))>0.01) AS trade_sd_diffs
FROM drv_cat_atomic_input a
JOIN drv_tn_td_bb_rr b USING (as_of_date, tos_symbol)
WHERE a.as_of_date=:d;

-- Q9 SD% range sanity (AD = AC/D). Flag absurd values (>0.5 => SD half of price)
SELECT count(*) AS n,
  count(*) FILTER (WHERE sd_pct IS NULL) AS null_sdpct,
  count(*) FILTER (WHERE sd_pct>0.5)     AS sdpct_gt_50pct,
  round(min(sd_pct)::numeric,4), round(max(sd_pct)::numeric,4)
FROM drv_cat_atomic_input WHERE as_of_date=:d;   -- column name may be ad / sd_pct

-- Q10 Risk Range source mix + null rate (RR feed vs BB fallback)
SELECT source, count(*),
  count(*) FILTER (WHERE lrr IS NULL OR trr IS NULL) AS null_bounds,
  count(*) FILTER (WHERE trr < lrr) AS inverted_bounds
FROM drv_rr WHERE as_of_date=:d GROUP BY source ORDER BY 2 DESC;

-- Q11 ImpVolatility: COALESCE(...,0) masks missing as 0 — count zeros vs nulls
SELECT count(*) AS n,
  count(*) FILTER (WHERE imp_volatility IS NULL) AS null_iv,
  count(*) FILTER (WHERE imp_volatility=0)       AS zero_iv,
  round(min(imp_volatility)::numeric,3), round(max(imp_volatility)::numeric,3)
FROM drv_technicals WHERE as_of_date=:d;

-- Q12 Index-volatility symbols present & sane (VIX family)
SELECT tos_symbol, last_price, imp_volatility
FROM drv_technicals
WHERE as_of_date=:d
  AND tos_symbol IN ('^VIX','^VVIX','^RVX','^VXN','^GVZ','^OVX','^MOVE','^VXD')
ORDER BY tos_symbol;

-- =====================================================================
-- D. VOLUME — vlm_projected, VolumeSpike decode, weekly ratios
-- =====================================================================
-- Q13 vlm_projected null rate + sanity (projected should be >= raw intraday volume)
SELECT count(*) AS n,
  count(*) FILTER (WHERE vlm_projected IS NULL) AS null_proj,
  count(*) FILTER (WHERE vlm_projected IS NOT NULL AND volume IS NOT NULL
                   AND vlm_projected < volume) AS proj_lt_raw,
  count(*) FILTER (WHERE vlm_projected > volume*50) AS proj_gt_50x
FROM drv_technicals WHERE as_of_date=:d;

-- Q14 sequence distribution feeding the projection (pre-open <930 => NULL by design)
SELECT
  count(*) FILTER (WHERE sequence < 930)             AS preopen,
  count(*) FILTER (WHERE sequence>=930 AND sequence<1600) AS intraday,
  count(*) FILTER (WHERE sequence>=1600)             AS closed
FROM hist_tl WHERE export_date=:d;

-- Q15 VolumeSpike padding-bug exposure: how many a_volume_spike values are
--     "small" (string form of ABS(value) shorter than 9 chars) where Python's
--     dropped REPT padding diverges from Excel. Tune the 9-char threshold.
SELECT count(*) AS n_nonzero,
  count(*) FILTER (WHERE length(to_char(abs(a_volume_spike),'FM999999990.00')) < 9) AS short_fg_at_risk
FROM hist_tw
WHERE snapshot_date<=:d AND a_volume_spike IS NOT NULL AND a_volume_spike<>0;

-- Q16 Weekly volume ratios (rvol = w_volume / avg_vlm_10d) sanity
SELECT count(*) AS n,
  count(*) FILTER (WHERE rvol IS NULL) AS null_rvol,
  round(min(rvol)::numeric,2), round(max(rvol)::numeric,2),
  round(avg(rvol)::numeric,2) AS avg_rvol
FROM drv_tw WHERE as_of_date=:d;   -- column names: rvol / w_vlm_expn_ratio

-- =====================================================================
-- E. FRESHNESS / CARRY-FORWARD
-- =====================================================================
-- Q17 TW staleness on the anchor: how far behind is each symbol's TW snapshot?
SELECT
  count(*) AS n,
  count(*) FILTER (WHERE :d - max_snap = 0)  AS fresh_today,
  count(*) FILTER (WHERE :d - max_snap BETWEEN 1 AND 7)  AS d1_7,
  count(*) FILTER (WHERE :d - max_snap > 7)   AS gt_7d
FROM (SELECT tos_symbol, max(snapshot_date) AS max_snap
      FROM hist_tw WHERE snapshot_date<=:d GROUP BY tos_symbol) z;

-- Q18 RR feed staleness (periodic — carry-forward expected)
SELECT
  count(*) AS n,
  count(*) FILTER (WHERE :d - max_snap > 7)  AS gt_7d,
  max(:d - max_snap) AS worst_lag_days
FROM (SELECT tos_symbol, max(snapshot_date) AS max_snap
      FROM hist_rr WHERE snapshot_date<=:d GROUP BY tos_symbol) z;

-- Q19 Daily-EOD presence: symbols in universe missing TODAY's TOSD export
SELECT count(*) AS universe,
  count(*) FILTER (WHERE td.tos_symbol IS NULL) AS missing_tosd_today
FROM drv_symbols s
LEFT JOIN (SELECT DISTINCT tos_symbol FROM hist_td WHERE export_date=:d) td
  USING (tos_symbol)
WHERE s.as_of_date=:d;
