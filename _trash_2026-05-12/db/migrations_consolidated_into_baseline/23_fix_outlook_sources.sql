-- =============================================================================
-- 23_fix_outlook_sources.sql
-- Fix: hist_etf has no 'outlook' column (the outlook is derived in drv_etf).
-- Point the ETF source rows at drv_etf instead so derive_outlook_action runs
-- without "column outlook does not exist".
-- Idempotent.
-- =============================================================================

UPDATE ref_outlook_source
   SET source_table = 'drv_etf'
 WHERE source_code  = 'ETF'
   AND source_table = 'hist_etf';

-- ETFCHG uses event_date and has 'outlook' directly — already correct.
-- IICHG  uses event_date and has 'outlook' directly — already correct.
-- II     uses hist_ii (has 'outlook')              — already correct.
-- RR     uses hist_rr (has 'outlook' + 'modifier') — already correct.
-- CALL   uses hist_call (has both)                  — already correct.
-- SSH    uses hist_ssh (uses days_on + pct_delta)  — already correct.
-- PSRK   uses hist_psrk (has 'rank' + 'ticker')    — already correct.
