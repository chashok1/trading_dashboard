-- 2026-08-10 -- RSP and SPY were tagged equity_sector='Industrials' by
-- etl/yahoo_fetch.py::fill_ref_sector_gaps -- the same Yahoo Finance
-- issuer-artifact quirk documented in seeds_country_etf_sector.sql, just
-- landing on broad-market index ETFs instead of country ETFs. Neither fund
-- is remotely Industrials-heavy; both track the whole S&P 500 (RSP
-- equal-weighted, SPY cap-weighted) and span every GICS sector, so a single-
-- sector tag is simply wrong. Cleared to NULL, which the app already
-- renders as "Unmapped" on the Sector axis (see etl/derive_category_perf.py)
-- -- consistent with how a genuinely unclassifiable symbol is handled.
-- Idempotent (safe to re-run). Durable: fill_ref_sector_gaps() only INSERTs
-- rows for tickers with none yet (ON CONFLICT ticker DO NOTHING) -- it never
-- overwrites an existing row, so this won't be re-populated by a later
-- Yahoo refresh.
--
-- Scope: only RSP and SPY. QQQ (Nasdaq-100, tagged 'Information Technology')
-- deliberately left alone -- it's still a multi-sector index, but genuinely
-- tech-concentrated (~50%+), so the tag isn't the same kind of nonsense;
-- left for a separate decision if it comes up.
--
-- User: "Stock symbol 'RSP' is S&P 500 equal weight, shouldn't it be
-- categorized as 'unmapped' as it spans multiple industries?" -> confirmed
-- fix RSP + SPY, leave QQQ.

UPDATE ref_sector
SET equity_sector = NULL
WHERE ticker IN ('RSP', 'SPY')
  AND equity_sector = 'Industrials';

-- 2026-08-10 follow-up -- user: "what about other index related ETFs IWM
-- etc?" -> full sweep of held ETFs still carrying an equity_sector. Three
-- more groups, same root quirk, escalating from clear-cut to judgment call:
--
-- 1) Broad cap/style index funds -- same exact shape as RSP/SPY (a "Tracks
--    an index of [small/large]-cap [growth/value] stocks in the U.S."
--    description, no sector concentration by construction, all mistagged
--    'Industrials'). IWM=Russell 2000, IWF=Russell 1000 Growth, IWN=Russell
--    2000 Value, IWO=Russell 2000 Growth, IJT=S&P SmallCap 600 Growth.
UPDATE ref_sector
SET equity_sector = NULL
WHERE ticker IN ('IWM', 'IWF', 'IWN', 'IWO', 'IJT')
  AND equity_sector = 'Industrials';

-- 2) Multi-sector factor/strategy screens -- select across all sectors by a
--    factor (momentum, value, quality, top-N by cap, recent IPO) rather
--    than holding a single sector; also mistagged 'Industrials'. Less
--    clean-cut than group 1 (a screen CAN happen to tilt one sector) but
--    none of these are sector funds by design, so a single-sector tag is
--    still misleading. XLG=S&P 500 Top 50, MTUM/QMOM=momentum,
--    SPMO=S&P 500 momentum, GVAL=global deep value, JOET=quality
--    (cash-flow/low-leverage) screen, IPO=recent-IPO companies.
UPDATE ref_sector
SET equity_sector = NULL
WHERE ticker IN ('XLG', 'MTUM', 'QMOM', 'SPMO', 'GVAL', 'JOET', 'IPO')
  AND equity_sector = 'Industrials';

-- 3) The group already named-and-deferred in this file's original comment
--    above ("a separate, unrelated group of factor/strategy ETFs... that
--    also got mistagged 'Financials' by the same Yahoo quirk") -- same
--    multi-sector-screen shape as group 2, just landed on 'Financials'
--    instead of 'Industrials'. BULL deliberately excluded here: unlike the
--    others, ref_sector's BULL row is stale (still describes an old 3x
--    leveraged-index ETF) -- the held BULL position is actually Webull
--    Corp stock, a real single company where 'Financials' is plausibly
--    correct, not a fund-classification mistag. Left as a separate
--    data-quality question, not touched by this sweep.
UPDATE ref_sector
SET equity_sector = NULL
WHERE ticker IN ('BTAL', 'GVIP', 'INFL', 'SPHD', 'SPLV')
  AND equity_sector = 'Financials';

-- NOTE -- a much larger, separate bug was spotted during this sweep and
-- deliberately NOT touched here: ~25 held bond/currency ETFs (TLT, IEF,
-- HYG, JNK, LQD, FXA/FXB/FXC/FXE/FXY, TIP, UUP, etc.) carry an
-- equity_sector tag ('Financials'/'USD') despite not being equities at
-- all -- a different root cause (non-equity vehicle getting an
-- equity-sector classification in the first place) than the broad-index/
-- factor-fund quirk this file addresses. Needs its own pass.
