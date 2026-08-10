-- 2026-08-10 -- Country/region ETFs were tagged equity_sector='Financials'
-- by etl/yahoo_fetch.py::fill_ref_sector_gaps -- a well-known Yahoo Finance
-- quirk (the fund/issuer gets classified as a "Financial Services" product
-- regardless of what the fund actually holds), not a real GICS sector read.
-- Relabeled to 'Country ETF', a new Sector-axis bucket, so a diversified
-- country/region fund (e.g. EWZ -- Brazil) stops inflating the Financials
-- sector's $ exposure/count. Idempotent (safe to re-run) -- only touches
-- rows that are still 'Financials'; a later manual correction on one of
-- these tickers is not clobbered by a re-run.
--
-- Scope: only genuine country/region-tracking ETFs. Left alone: real
-- Financials-sector ETFs (XLF/KRE/IAK/KBWP/KCE) and a separate, unrelated
-- group of factor/strategy ETFs (BTAL/BULL/GVIP/INFL/SPHD/SPLV) that also
-- got mistagged 'Financials' by the same Yahoo quirk -- not country ETFs,
-- a different classification problem, deliberately out of scope here.
--
-- User: "Somehow i need to categorize country ETFs differently, right?" ->
-- "can we put them in different buckets?" -> "why can't name them as
-- 'Country ETF'?"

UPDATE ref_sector
SET equity_sector = 'Country ETF'
WHERE equity_sector = 'Financials'
  AND ticker IN (
    'AFK', 'ARGT', 'EPHE', 'EPOL', 'EWA', 'EWC', 'EWH', 'EWI', 'EWJV',
    'EWM', 'EWO', 'EWP', 'EWS', 'EWZ', 'EWZS', 'EZA', 'FLG', 'FXI',
    'INDY', 'KBA', 'KSA', 'QAT', 'SMIN', 'THD', 'TUR', 'UAE', 'VNM'
  );
