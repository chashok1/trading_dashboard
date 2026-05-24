-- =============================================================================
-- 26_etf_outlook.sql
-- Add outlook + outlook_modifier to hist_etf so the ETF source can populate
-- outlook from the file's BULLISH / BEARISH section headers directly,
-- matching the pattern hist_call / hist_rr already use.
-- Idempotent.
-- =============================================================================

ALTER TABLE hist_etf
    ADD COLUMN IF NOT EXISTS outlook          TEXT,
    ADD COLUMN IF NOT EXISTS outlook_modifier TEXT;

CREATE INDEX IF NOT EXISTS ix_hist_etf_outlook ON hist_etf(outlook) WHERE outlook IS NOT NULL;
