-- =============================================================================
-- 27_etf_use_hist.sql
-- Now that hist_etf carries outlook directly (loaded from BULLISH/BEARISH
-- section headers in the source file), point the ETF outlook source at
-- hist_etf instead of drv_etf. Reverses the workaround in 23_fix_outlook_sources.sql.
-- Idempotent.
-- =============================================================================

UPDATE ref_outlook_source
   SET source_table = 'hist_etf'
 WHERE source_code  = 'ETF'
   AND source_table = 'drv_etf';
