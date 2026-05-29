"""Pydantic response models for the FastAPI app."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    db: str
    server_time: datetime
    pg_database: str


class DashRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    as_of_date: date
    section: str
    tos_symbol: str
    description: Optional[str] = None
    last_price: Optional[float] = None
    a_trend_value: Optional[float] = None
    a_trade_value: Optional[float] = None
    pct_brr: Optional[float] = None
    rr_outlook: Optional[str] = None
    rr_brr: Optional[float] = None
    call_outlook: Optional[str] = None
    sector: Optional[str] = None
    asset_class: Optional[str] = None
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    zone_signal: Optional[str] = None


class StksRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    as_of_date: date
    tos_symbol: str
    description: Optional[str] = None
    sector: Optional[str] = None
    asset_class: Optional[str] = None
    sub_asset_class: Optional[str] = None
    equity_sector: Optional[str] = None
    last_price: Optional[float] = None
    a_trend_value: Optional[float] = None
    a_trade_value: Optional[float] = None
    a_bb_top: Optional[float] = None
    a_bb_bottom: Optional[float] = None
    a_bb_streak: Optional[float] = None
    a_macd_brr: Optional[float] = None
    a_macdh_d_brr: Optional[float] = None
    pct_brr: Optional[float] = None
    rr_outlook: Optional[str] = None
    rr_brr: Optional[float] = None
    call_outlook: Optional[str] = None
    call_modifier: Optional[str] = None
    etf_outlook: Optional[str] = None
    ii_outlook: Optional[str] = None
    ssh_signal_sign: Optional[float] = None
    iv_percentile: Optional[float] = None
    imp_volatility: Optional[float] = None
    hv_percentile: Optional[float] = None
    range_compression: Optional[float] = None
    d_iv_to_hv: Optional[float] = None
    rsi: Optional[float] = None
    earnings_days: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    volume: Optional[int] = None
    vlm_projected: Optional[float] = None
    market_cap_str: Optional[str] = None
    beta: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    div_yield: Optional[float] = None
    composite_outlook: Optional[float] = None
    composite_label: Optional[str] = None
    triggered_atomic_ids: Optional[list] = None
    triggered_composite_ids: Optional[list] = None


class DashSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    as_of_date: date
    total_symbols: Optional[int] = None
    n_bullish: Optional[int] = None
    n_bearish: Optional[int] = None
    n_neutral: Optional[int] = None
    avg_brr: Optional[float] = None
    n_in_zone: Optional[int] = None
    n_out_of_zone: Optional[int] = None
    n_above_trend: Optional[int] = None
    n_below_trend: Optional[int] = None
    next_econ_event: Optional[str] = None
    next_econ_event_dt: Optional[date] = None
    next_holiday: Optional[str] = None
    next_holiday_dt: Optional[date] = None


class SymbolHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    as_of_date: date
    last_price: Optional[float] = None
    rr_brr: Optional[float] = None
    pct_brr: Optional[float] = None
    rr_outlook: Optional[str] = None
    sector: Optional[str] = None


# Ref Table Management Models
class RefTableColumn(BaseModel):
    name: str
    is_pk: bool


class RefTableData(BaseModel):
    table: str
    columns: list[RefTableColumn]
    rows: list[dict]
    total: int
    # Optional human-readable description of the filter applied to produce
    # this result set (e.g. "snapshot_date = 2026-05-06" or
    # "latest snapshot_date <= 2026-05-06 (resolved to 2026-05-04)").
    # Populated by /api/data/{table_name}; left null by /api/ref/{table_name}.
    filter_description: Optional[str] = None


class RefTableMeta(BaseModel):
    name: str
    row_count: int
    tunable: bool


class RefRowUpdateResult(BaseModel):
    ok: bool
    updated: int


class RefReloadResult(BaseModel):
    ok: bool
    table: str
    rows_read: int
    rows_inserted: int
    rows_skipped: int


class DataTableMeta(BaseModel):
    name: str
    category: str
    row_count: int
    date_col: Optional[str] = None


class RefRowInsertResult(BaseModel):
    ok: bool
    inserted: int


# Rule Engine v2 Models
# Note: AtomicRuleResponse, CompositeRuleResponse, TriggeredRule, UserActionResponse,
# and RulePerformanceRow were removed on 2026-05-12 — they were declared but never
# used as response_model or referenced anywhere. Re-add (and wire as response_model
# on the appropriate endpoint) if/when the rule-engine routes start returning typed
# objects instead of plain dicts.


class UserActionRequest(BaseModel):
    as_of_date: date
    symbol: str
    # Trig codes:        SA, STM, SS, BM, HOLD
    # Actionable codes:  REMOVE, REDUCE, INCREASE, ADD, HOLD
    # Cockpit meta:      ACTED (resolved server-side to drv_actionable.consolidated_action), SKIP
    action_code: str
    notes: Optional[str] = None


class AtomicRuleCreateRequest(BaseModel):
    rule_id: str
    rule_name: Optional[str] = None
    category: Optional[str] = None
    intent_text: Optional[str] = None
    ma_column_name: Optional[str] = None
    scoring_mode: str = 'jump'
    score_params: Optional[dict] = None
    brkeout_from: Optional[float] = None
    brkeout_to: Optional[float] = None
    wt_below: Optional[float] = None
    wt_between: Optional[float] = None
    wt_above: Optional[float] = None


class AtomicRuleUpdateRequest(BaseModel):
    rule_name: Optional[str] = None
    category: Optional[str] = None
    intent_text: Optional[str] = None
    scoring_mode: Optional[str] = None
    score_params: Optional[dict] = None
    brkeout_from: Optional[float] = None
    brkeout_to: Optional[float] = None
    wt_below: Optional[float] = None
    wt_between: Optional[float] = None
    wt_above: Optional[float] = None


class CompositeRuleCreateRequest(BaseModel):
    rule_code: str
    category: Optional[str] = None
    intent_text: Optional[str] = None
    precondition_expr: Optional[str] = None
    # ref_trig_atomic_rule.atomic_rule_id is INTEGER — accept int or numeric str
    atomic_rule_ids: list[int] = []


class CompositeRuleUpdateRequest(BaseModel):
    category: Optional[str] = None
    intent_text: Optional[str] = None
    precondition_expr: Optional[str] = None


class TableStats(BaseModel):
    name: str
    category: str
    row_count: int
    size_pretty: Optional[str] = None
    min_date: Optional[date] = None
    max_date: Optional[date] = None
