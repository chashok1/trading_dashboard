"""
ARCHIVED 2026-05-12.

Workbook-seed loaders for the historical ssL and sss tabs.

Originally these populated drv_ssl and drv_sss as one-time backfill data,
after which the live drv_ssl/drv_sss were rebuilt by derive_ssl / derive_sss
(see ssl_sss_derive.py).

Both layers were retired because the new actionable pipeline reads
hist_ssh directly via ref_outlook_source.source_code='SSH'.

Kept here for reference / replay in case the lag-week / signal-series
analytics get revived.
"""
# (Original code preserved verbatim — see git history of etl/load_raw.py
# functions seed_sss / seed_ssl prior to commit 2026-05-12.)
