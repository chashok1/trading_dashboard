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

-- 2026-08-10 follow-up -- the first pass above only searched tickers
-- mistagged 'Financials' specifically, but the same Yahoo issuer-artifact
-- quirk scatters country/region ETFs across OTHER sectors too, wherever
-- Yahoo's own per-fund classifier happened to land (e.g. ENZL -- New
-- Zealand -- tagged "Health care"; EWJ -- Japan -- tagged "Industrials").
-- Found via a broader description sweep ("Tracks an index of companies
-- listed in/on <country>", vehicle_type ETF/Index, cross-checked against
-- individual ADR/stock false positives that just happen to mention a
-- country in their business description, e.g. PBR/NIO/YUMC -- those are
-- real single companies, correctly sector-tagged, left alone). ENZL (285
-- sh) and COLO (400 sh, previously equity_sector=NULL/Unmapped rather than
-- wrong) are actual held positions; the rest are reference-universe only.
-- User: "ENZL is a country ETF and why is it showing in health care?"
UPDATE ref_sector
SET equity_sector = 'Country ETF'
WHERE ticker IN (
    '^N225', 'COLO', 'ECH', 'EFNL', 'EIS', 'ENZL', 'EPU', 'EWD', 'EWG',
    'EWJ', 'EWK', 'EWN', 'EWQ', 'EWUS', 'EWW', 'EWY', 'IDX', 'INDA',
    'JPXN', 'KWEB', 'MKOR', 'SCJ', 'VGK'
  );
