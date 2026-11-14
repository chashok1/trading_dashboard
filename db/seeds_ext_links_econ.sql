-- 2026-11-10, user-directed: "Econ" link (MarketWatch economic calendar) next to the Yahoo and CNBC links in the Hedgeye panel header.
INSERT INTO ext_links (panel_key, label, url, sort_order)
SELECT 'market_news_econ', 'Econ', 'https://www.marketwatch.com/economy-politics/calendar', 16
WHERE NOT EXISTS (SELECT 1 FROM ext_links WHERE panel_key = 'market_news_econ');
