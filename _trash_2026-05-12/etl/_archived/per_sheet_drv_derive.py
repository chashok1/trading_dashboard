"""
ARCHIVED 2026-05-12.

Per-sheet derivers retired:
  - derive_call (drv_call)  — was: outlook → weight via ref_param + entry/cont action lookups
  - derive_etf  (drv_etf)   — was: outlook from BRR/TRR sign + weight + entry/cont
                               actions; superseded by hist_etf carrying outlook
                               directly (see etl/load_raw.py:load_etf and
                               db/26_etf_outlook.sql)
  - derive_ii   (drv_ii)    — was: outlook → weight + entry/cont actions
  - derive_ps   (drv_ps)    — was: rebuild of broken ps tab from
                               hist_psrk + hist_ps5 + hist_pstn + computed weights;
                               not joined into drv_dash and never read downstream.

Retired because:
  - drv_dash now reads hist_call.outlook + ref_param outlook→weight inline
  - drv_dash now reads hist_ii.outlook + ref_param outlook→weight inline
  - drv_dash now reads hist_etf.outlook directly (loaded from BULLISH/BEARISH headers)
  - drv_ps had no downstream readers

Original implementations lived in etl/derive.py (_derive_call_impl) and
etl/derive_v2.py (_derive_etf_v2_impl, _derive_ii_v2_impl, _derive_ps_v2_impl).
Drop migrations: db/29_drop_drv_etf.sql, db/30_drop_drv_ps.sql,
                 db/31_drop_drv_call.sql, db/32_drop_drv_ii.sql.
"""
