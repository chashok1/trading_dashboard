"""
ARCHIVED 2026-05-12.

Live derive functions for drv_ssl and drv_sss:
  - derive_ssl: drv_ssl was the 7-day lag of hist_ssh ("Signal Strength
    Last week"), built per as_of_date.
  - derive_sss: drv_sss was a per-symbol weekly history with multi-window
    deltas vs ssL ("Signal Strength Series").

Both retired because the new actionable pipeline derives its signal
freshly from hist_ssh.pct_delta + days_on without needing a lag table.

Original implementations lived in etl/derive.py (_derive_ssl_impl) and
etl/derive_v2.py (_derive_sss_v2_impl). Drop migration is db/28_drop_ssl_sss.sql.
"""
