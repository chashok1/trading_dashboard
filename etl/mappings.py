"""
Tab -> table column mappings for every Excel tab we load.

Each entry has:
    sheet:        Excel tab name
    table:        target DB table name
    columns:      ordered list of (excel_header, db_column, type_caster_or_None)
    pk_columns:   list of DB column names that form the primary key
                  (only used to decide what counts as a duplicate)
    skip_first_n: extra header rows to skip BEYOND the standard header at row 1
                  (e.g. some tabs have a "row 2 = sub-header" pattern)

Type casters are applied in load_raw.py before insert.
"""
from __future__ import annotations

from typing import Callable, Optional

from etl.casters import (
    to_date, to_int, to_bigint, to_numeric, to_text, to_char1, to_time
)


ColMap = list[tuple[str, str, Optional[Callable]]]


# =============================================================================
# REFERENCE TABLES (load once, refresh full table on each run)
# =============================================================================

REF_MAPS = {
    # Sctr tab -> ref_sector
    "Sctr": dict(
        sheet="Sctr",
        table="ref_sector",
        skip_first_n=0,
        pk_columns=["ticker"],
        columns=[
            ("Ticker",        "ticker",          to_text),
            ("Description",   "description",     to_text),
            ("Industry",      "industry",        to_text),
            ("SP500",         "sp500",           to_char1),
            ("Nasdaq",        "nasdaq",          to_char1),
            ("Dow",           "dow",             to_char1),
            ("RusSell",       "russell",         to_char1),
            ("Vehicle Type",  "vehicle_type",    to_text),
            ("Asset Class",   "asset_class",     to_text),
            ("Sub-Asset Class","sub_asset_class",to_text),
            ("Equity Sector", "equity_sector",   to_text),
            ("Growth",        "growth",          to_text),
            ("Valuation",     "valuation",       to_text),
            ("Price Action",  "price_action",    to_text),
        ],
    ),
    # RRT tab -> ref_rrt
    "RRT": dict(
        sheet="RRT",
        table="ref_rrt",
        skip_first_n=0,
        pk_columns=["rr_name"],
        columns=[
            ("RR Name",     "rr_name",    to_text),
            ("Y Ticker",    "y_ticker",   to_text),
            ("TOS Ticker",  "tos_ticker", to_text),
            ("Reverse",     "reverse",    to_char1),
            ("Contracts",   "contracts",  to_char1),
        ],
    ),
    # Desc tab -> ref_rule_desc
    "Desc": dict(
        sheet="Desc",
        table="ref_rule_desc",
        skip_first_n=0,
        pk_columns=["rule_code"],
        columns=[
            ("Rule",        "rule_code",   to_text),
            ("Description", "description", to_text),
        ],
    ),
    # Note: 'Miss' tab has NO loader. It is purely derived data
    #       (missing stock symbols from MA), populated by
    #       derive_missing_symbols() into drv_missing_symbols.

    # ISMH tab -> ref_ismh (reference data - periodically refreshed,
    #   conceptually similar to the Data tab)
    "ISMH": dict(
        sheet="ISMH",
        table="ref_ismh",
        skip_first_n=0,
        pk_columns=["for_month", "index_name"],
        columns=[
            ("For Month",                    "for_month",                to_text),
            ("Index",                        "index_name",               to_text),
            ("Series Index cur Month",       "series_index_cur_month",   to_numeric),
            ("Series Index Prior Month",     "series_index_prior_month", to_numeric),
            ("Percentage Point Change",      "pct_point_change",         to_numeric),
            ("Direction",                    "direction",                to_text),
            ("Rate of Change",               "rate_of_change",           to_text),
            ("Trend* (Months)",              "trend_months",             to_numeric),
        ],
    ),
}


# =============================================================================
# HISTORY TABLES (append-only, skip duplicates)
# =============================================================================
#
# Note for raw history tables:
# We always synthesize snapshot_date from the export-date col, sequence
# from the export-time col. The mapping uses the RAW source columns;
# extra synthesized cols are added by load_raw.py (synthesize_keys=True).

HIST_MAPS = {
    # Y tab -> hist_y (raw exported quotes)
    "Y": dict(
        sheet="Y",
        table="hist_y",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol", "sequence"],
        # snapshot_date <- "Export Date", sequence <- "Export Time"
        date_source_col="Export Date",
        seq_source_col="Export Time",
        symbol_source_col="Symbol",
        columns=[
            ("Export Date",  "export_date",     to_date),
            ("Date",         "export_date",     to_date),  # CSV alt
            ("Export Time",  "export_time",     to_text),
            ("Time",         "export_time",     to_text),  # CSV alt
            ("Symbol",       "symbol",          to_text),
            ("Company Name", "company_name",    to_text),
            ("Last Price",   "last_price",      to_numeric),
            ("Change",       "change_amt",      to_numeric),
            ("Change (%)",   "change_pct",      to_numeric),
            ("Open",         "open_price",      to_numeric),
            ("High",         "high_price",      to_numeric),
            ("Low",          "low_price",       to_numeric),
            ("Short Ratio",  "short_ratio",     to_numeric),
            ("Float",        "float_str",       to_text),
            ("Shares Out",   "shares_out_str",  to_text),
        ],
    ),

    # TL tab -> hist_tl (raw cols I-T only; vlm_projected + imp_volatility
    # cleaning are derived inline in the drv_ma `tl` CTE - drv_tl retired 2026-05-20)
    "TL": dict(
        sheet="TL",
        table="hist_tl",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol", "sequence"],
        date_source_col="Export Date",
        seq_source_col="Export Time",
        symbol_source_col="Symbol",
        columns=[
            ("Export Date",     "export_date",        to_date),
            ("Date",            "export_date",        to_date),  # CSV alt
            ("Export Time",     "export_time",        to_text),
            ("Time",            "export_time",        to_text),  # CSV alt
            ("Symbol",          "symbol",             to_text),
            ("Last",            "last_price",         to_numeric),
            ("Net Chng",        "net_chng",           to_numeric),
            ("%Change",         "change_pct",         to_numeric),
            ("Open",            "open_price",         to_numeric),
            ("High",            "high_price",         to_numeric),
            ("Low",             "low_price",          to_numeric),
            ("Volume",          "volume",             to_bigint),
            ("RSI",             "rsi",                to_numeric),
            ("ImpVolatility",   "imp_volatility_raw", to_numeric),
        ],
    ),

    # TD tab -> hist_td (raw cols AM-BI plus BB_Bot_Prev/BB_Top_Prev from L/P)
    "TD": dict(
        sheet="TD",
        table="hist_td",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol", "sequence"],
        date_source_col="Export Date",
        seq_source_col="Export Time",
        symbol_source_col="Symbol",
        columns=[
            ("Export Date",          "export_date",         to_date),
            ("Date",                 "export_date",         to_date),  # CSV alt
            ("Export Time",          "export_time",         to_text),
            ("Time",                 "export_time",         to_text),  # CSV alt
            ("Symbol",               "symbol",              to_text),
            ("Last",                 "last_price",          to_numeric),
            ("Net Chng",             "net_chng",            to_numeric),
            ("%Change",              "change_pct",          to_numeric),
            ("Open",                 "open_price",          to_numeric),
            ("High",                 "high_price",          to_numeric),
            ("Low",                  "low_price",           to_numeric),
            ("RSI",                  "rsi",                 to_numeric),
            ("HistoricalVolatility", "historical_vol",      to_numeric),
            ("ImpVolatility",        "imp_volatility",      to_numeric),
            ("A_TrendValue",         "a_trend_value",       to_numeric),
            ("A_TradeValue",         "a_trade_value",       to_numeric),
            ("A_BB_Bottom",          "a_bb_bottom",         to_numeric),
            ("A_BB_Top",             "a_bb_top",            to_numeric),
            ("A_BB_Streak",          "a_bb_streak",         to_numeric),
            ("A_BBHighLow",          "a_bb_high_low",       to_numeric),
            ("A_BBHighLowDays",      "a_bb_high_low_days",  to_numeric),
            ("A_IVPercentile",       "a_iv_percentile",     to_numeric),
            ("A_HVPercentile",       "a_hv_percentile",     to_numeric),
            ("A_BB_Top_Slope",       "a_bb_top_slope",      to_numeric),
            ("A_BB_Bot_Slope",       "a_bb_bot_slope",      to_numeric),
        ],
    ),

    # TW tab -> hist_tw (raw cols Y-BC)
    "TW": dict(
        sheet="TW",
        table="hist_tw",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol", "sequence"],
        date_source_col="Export Date",
        seq_source_col="Export Time",
        symbol_source_col="Symbol",
        columns=[
            ("Export Date",                "export_date",        to_date),
            ("Date",                       "export_date",        to_date),  # CSV alt
            ("Export Time",                "export_time",        to_text),
            ("Time",                       "export_time",        to_text),  # CSV alt
            ("Symbol",                     "symbol",             to_text),
            ("Last",                       "last_price",         to_numeric),
            ("%Change",                    "change_pct",         to_numeric),
            # 2026-05-28: Removed beta, market_cap_str, sector, fcf_per_share.
            # Consolidated on hist_to as single source for these fields.
            ("StandardDeviation",          "standard_dev",       to_numeric),
            ("52High",                     "high_52",            to_numeric),
            ("52Low",                      "low_52",             to_numeric),
            ("SimpleMovingAvg",            "sma_20",             to_numeric),  # AJ
            ("A_MACDays_Streak",           "a_macdays_streak",   to_numeric),
            ("A_MACD_BRR",                 "a_macd_brr",         to_numeric),
            ("A_MACDH_D_BRR",              "a_macdh_d_brr",      to_numeric),
            ("Volume",                     "volume",             to_bigint),
            ("A_VolumeSpike",              "a_volume_spike",     to_numeric),
            ("VolumeAvg",                  "volume_avg_10d",     to_numeric),  # AR
            ("VolumeRateOfChange",         "volume_rate_change", to_numeric),
            ("A_Perf2M",                   "a_perf_2m",          to_numeric),
            ("A_Perf2Wk",                  "a_perf_2wk",         to_numeric),
            ("A_Perf3D",                   "a_perf_3d",          to_numeric),
            ("A_3mnHigh",                  "a_3mn_high",         to_numeric),
            ("A_3mnLow",                   "a_3mn_low",          to_numeric),
            ("A_3mnHighLow",               "a_3mn_high_low",     to_numeric),
            ("A_3wkHighLow",               "a_3wk_high_low",     to_numeric),
            ("A_EarningsDays",             "a_earnings_days",    to_numeric),
        ],
        # NOTE: TW has 3 columns named "SimpleMovingAvg" and 2 named
        # "VolumeAvg". load_raw.py handles duplicates by index when needed.
    ),

    # TO tab -> hist_to (fundamentals - mostly all raw)
    "TO": dict(
        sheet="TO",
        table="hist_to",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol", "sequence"],
        date_source_col="Export Date",
        seq_source_col="Export Time",
        symbol_source_col="Symbol",
        columns=[
            ("Export Date",                            "export_date",     to_date),
            ("Date",                                   "export_date",     to_date),  # CSV alt
            ("Export Time",                            "export_time",     to_text),
            ("Time",                                   "export_time",     to_text),  # CSV alt
            ("Symbol",                                 "symbol",          to_text),
            ("Beta",                                   "beta",            to_numeric),
            ("Market Cap",                             "market_cap_str",  to_text),
            ("Long-term Debt to Capital - Current (LTM)", "ltd_to_capital", to_numeric),
            ("Price / Earnings Ratio - Current",       "pe_ratio",        to_numeric),
            ("Price / Book Value Ratio - Current",     "pb_ratio",        to_numeric),
            ("Return on Equity (ROE) - Current (LTM)", "roe",             to_numeric),
            ("EPS",                                    "eps",             to_numeric),
            ("Div. Yield - Current",                   "div_yield",       to_numeric),
            ("Sector",                                 "sector",          to_text),
            ("Free Cash Flow Per Share - Current (LTM)", "fcf_per_share",  to_numeric),
        ],
    ),

    # RR tab -> hist_rr
    "RR": dict(
        sheet="Table_Section",
        table="hist_rr",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="RR Date",
        seq_source_col=None,
        symbol_source_col="Index",
        columns=[
            ("Index",          "symbol",         to_text),
            ("Index",          "tos_symbol",     to_text),
            ("RR Date",        "market_close",   to_date),
            ("Prev Close",     "last_price",     to_numeric),
            ("BUY TRADE",      "buy_trade",      to_numeric),
            ("SELL TRADE",     "sell_trade",     to_numeric),
            ("Description",    "description",    to_text),
            ("Outlook",        "outlook",        to_text),
        ],
    ),

    # call tab -> hist_call (RAW only: Imported Date, Symbol, Outlook, Outlook Modifier)
    # Excel-derived cols (Key, Weight, Entry, Cont, Lookups) -> drv_call via derive_call.
    "call": dict(
        sheet="call",
        table="hist_call",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="Imported Date",
        seq_source_col=None,
        symbol_source_col="Symbol",
        columns=[
            # NOTE: source has TWO "Symbol" cols (B derived, T raw) and TWO
            # "Outlook" cols (D derived, U raw). The mapping picks the LAST
            # occurrence of each header (right-side), which is the raw source.
            ("Imported Date",    "snapshot_date",    to_date),
            ("Symbol",           "symbol",           to_text),
            ("Outlook",          "outlook",          to_text),
            ("Outlook Modifier", "outlook_modifier", to_text),
        ],
    ),

    # etf tab -> hist_etf (RAW cols R-AA only)
    "etf": dict(
        sheet="etf",
        table="hist_etf",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="Imported Date",
        seq_source_col=None,
        symbol_source_col="Ticker",
        columns=[
            ("Imported Date", "snapshot_date", to_date),
            ("Sector",        "sector",        to_text),
            ("Ticker",        "symbol",        to_text),
            ("Date Added",    "date_added",    to_date),
            ("Recent Price",  "recent_price",  to_numeric),
            ("BRR",           "brr",           to_numeric),
            ("TRR",           "trr",           to_numeric),
            ("Asset Class",   "asset_class",   to_text),
        ],
    ),

    # II tab -> hist_ii (RAW cols O-T only)
    "II": dict(
        sheet="II",
        table="hist_ii",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="Imported Date",
        seq_source_col=None,
        symbol_source_col="Ticker",
        columns=[
            ("Imported Date", "snapshot_date", to_date),
            ("Outlook",       "outlook",       to_text),
            ("Ticker",        "symbol",        to_text),
        ],
    ),

    # ssH tab -> hist_sss (RAW cols S-AB only)
    "ssH": dict(
        sheet="ssH",
        table="hist_sss",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="Imported Date",
        seq_source_col=None,
        symbol_source_col=" Ticker",
        columns=[
            ("Imported Date",         "snapshot_date",        to_date),
            ("Days On",               "days_on",              to_int),
            (" Ticker",               "symbol",               to_text),
            (" Signal Date",          "signal_date",          to_text),
            (" Prior Close of Signal","prior_close",          to_numeric),
            (" Last Close Price",     "last_close",           to_numeric),
            (" % Delta Since Initial","pct_delta",            to_numeric),
            (" Sector",               "sector",               to_text),
            (" Analyst",              "analyst",              to_text),
            (" Anlyst Best Idea Rank","anlst_best_idea_rank", to_text),
        ],
    ),

    # SSS -> hist_sss (same DB table as ssH, new column names from the
    # 2026-05 Hedgeye export. NOTE: excel_io.get_headers() strips whitespace
    # from header cells, so the mapping uses column names WITHOUT the
    # leading space that the source workbook actually has.
    # Column differences vs ssH:
    #   "Date" instead of "Imported Date"
    #   "Prior Close of Signal Price" (extra "Price" word)
    #   "Siganl Strength" (typo retained in source) → pct_delta
    #   "Analyst Rank" → anlst_best_idea_rank (renamed in source)
    "SSS": dict(
        sheet="SSS",
        table="hist_sss",
        skip_first_n=0,
        pk_columns=["snapshot_date", "symbol"],
        date_source_col="Date",
        seq_source_col=None,
        symbol_source_col="Ticker",
        columns=[
            ("Date",                        "snapshot_date",        to_date),
            ("Days On",                     "days_on",              to_int),
            ("Ticker",                      "symbol",               to_text),
            ("Signal Date",                 "signal_date",          to_text),
            ("Prior Close of Signal Price", "prior_close",          to_numeric),
            ("Last Close Price",            "last_close",           to_numeric),
            ("Siganl Strength",             "pct_delta",            to_numeric),
            ("Sector",                      "sector",               to_text),
            ("Analyst",                     "analyst",              to_text),
            ("Analyst Rank",                "anlst_best_idea_rank", to_text),
        ],
    ),

    # ps tab -> hist_ps
    "ps": dict(
        sheet="ps",
        table="hist_ps",
        skip_first_n=0,
        pk_columns=["snapshot_date", "ticker"],
        date_source_col="Date",
        seq_source_col=None,
        columns=[
            ("Date",           "snapshot_date",  to_date),
            ("RANK",           "rank",           to_numeric),
            ("TICKER",         "ticker",         to_text),
            ("1-WEEKCHANGE",   "wk_ago",         to_numeric),
            ("1-MONTHCHANGE",  "mn_ago",         to_numeric),
            ("ENTRYDATE",      "date_added",     to_date),
            ("ASSET CLASS",    "asset_class",    to_text),
            ("POSITIONSIZING", "position_sizing", to_text),
        ],
    ),

    # F tab -> hist_f (Fidelity holdings)
    "F": dict(
        sheet="F",
        table="hist_f",
        skip_first_n=0,
        pk_columns=["snapshot_date", "account_number", "symbol"],
        date_source_col="Date",
        seq_source_col=None,
        symbol_source_col="Symbol",
        columns=[
            ("Symbol",                    "symbol",           to_text),
            ("Date",                      "snapshot_date",    to_date),
            ("Qty",                       "qty",              to_numeric),
            ("Cur Val",                   "current_value",    to_numeric),
            ("Export Date",               "export_date",      to_date),
            ("Account Number",            "account_number",   to_text),
            ("Account Name",              "account_name",     to_text),
            ("Description",               "description",      to_text),
            ("Quantity",                  "qty",              to_numeric),
            ("Last Price",                "last_price",       to_numeric),
            ("Last Price Change",         "last_price_change",to_numeric),
            ("Current Value",             "current_value",    to_numeric),
            ("Today's Gain/Loss Dollar",  "today_gl_dollar",  to_numeric),
            ("Today's Gain/Loss Percent", "today_gl_pct",     to_numeric),
            ("Total Gain/Loss Dollar",    "total_gl_dollar",  to_numeric),
            ("Total Gain/Loss Percent",   "total_gl_pct",     to_numeric),
            ("Percent Of Account",        "pct_of_account",   to_numeric),
            ("Cost Basis Total",          "cost_basis_total", to_numeric),
            ("Average Cost Basis",        "avg_cost_basis",   to_numeric),
            ("Type",                      "type",             to_text),
        ],
    ),

    # CS tab -> hist_cs (Schwab holdings)
    "CS": dict(
        sheet="CS",
        table="hist_cs",
        skip_first_n=0,
        pk_columns=["snapshot_date", "account", "symbol"],
        date_source_col="Date",
        seq_source_col=None,
        symbol_source_col="Symbol",
        columns=[
            ("Symbol",                        "symbol",             to_text),
            ("Date",                          "snapshot_date",      to_date),
            ("Qty",                           "qty",                to_numeric),
            ("Qty (Quantity)",                "qty",                to_numeric),
            ("Section",                       "account",            to_text),
            ("Imported Date",                 "imported_date",      to_date),
            ("Description",                   "description",        to_text),
            ("Price",                         "price",              to_numeric),
            ("Mkt Val (Market Value)",        "market_value",       to_numeric),
            ("Price Chng $ (Price Change $)", "price_chng_dollar",  to_numeric),
            ("Price Chng % (Price Change %)", "price_chng_pct",     to_numeric),
            ("Day Chng $ (Day Change $)",     "day_chng_dollar",    to_numeric),
            ("Day Chng % (Day Change %)",     "day_chng_pct",       to_numeric),
            ("Cost Basis",                    "cost_basis",         to_numeric),
            ("Gain $ (Gain/Loss $)",          "gain_dollar",        to_numeric),
            ("Gain % (Gain/Loss %)",          "gain_pct",           to_numeric),
            ("Reinvest?",                     "reinvest",           to_text),
            ("Reinvest Capital Gains?",       "reinvest_cap_gains", to_text),
            ("Security Type",                 "security_type",      to_text),
        ],
    ),

    # Note: ISMH moved to REF_MAPS (it is periodically refreshed reference data,
    #       not append-only history).
    # Note: ssL is a DERIVED table (drv_ssl) - not loaded directly. SSS is loaded
    #       directly from the Hedgeye export and stored in hist_sss.
}


# =============================================================================
# REF table mappings — periodically refreshed reference data (vs append-only
# history). Currently empty but kept here for future reference loads.
# =============================================================================
REF_MAPS: dict = {}
