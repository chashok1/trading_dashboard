-- Volatility regime thresholds for ref_vol_threshold
-- Below low = Investable | low–high = Chop | above high = Not Investable

INSERT INTO ref_vol_threshold (tos_symbol, low, high) VALUES
    ('VIX',      19,  30),
    ('VVIX',    100, 150),
    ('RVX',      22,  40),
    ('VXN:CGI',  22,  32),
    ('GVZ:CGI',  26,  32),
    ('OVX:CGI',  30,  50),
    ('MOVE:GIF', 100, 120),
    ('VXD',      20,  30)
ON CONFLICT (tos_symbol) DO NOTHING;
