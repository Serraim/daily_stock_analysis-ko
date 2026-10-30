# -*- coding: utf-8 -*-
"""Backtest API schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from api.v1.schemas.market_phase import MarketPhaseSummary
from src.schemas.decision_action import DecisionAction


class BacktestRunRequest(BaseModel):
    code: Optional[str] = Field(None, description="지정한 종목만 백테스트")
    force: bool = Field(False, description="강제로 다시 계산")
    eval_window_days: Optional[int] = Field(None, ge=1, le=120, description="평가 기간 (거래일 수)")
    min_age_days: Optional[int] = Field(None, ge=0, le=365, description="분석 기록 최소 경과 일수 (0=제한 없음)")
    analysis_date_from: Optional[date] = Field(None, description="분석일 시작 (포함)")
    analysis_date_to: Optional[date] = Field(None, description="분석일 끝 (포함)")
    limit: int = Field(200, ge=1, le=2000, description="처리할 분석 기록 최대 수")


class BacktestRunResponse(BaseModel):
    processed: int = Field(..., description="후보 기록 수")
    saved: int = Field(..., description="기록한 백테스트 결과 수")
    completed: int = Field(..., description="백테스트 완료 수")
    insufficient: int = Field(..., description="데이터 부족 수")
    errors: int = Field(..., description="오류 수")
    applied_eval_window_days: Optional[int] = Field(
        ...,
        description="실제로 적용된 평가 기간 (거래일 수)",
    )
    message: Optional[str] = Field(None, description="결과가 비었거나 일부만 처리됐을 때의 진단 설명")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="백테스트 필터·진단 정보")


class BacktestResultItem(BaseModel):
    analysis_history_id: int
    code: str
    stock_name: Optional[str] = None
    analysis_date: Optional[str] = None
    eval_window_days: int
    engine_version: str
    eval_status: str
    evaluated_at: Optional[str] = None
    operation_advice: Optional[str] = None
    action: Optional[DecisionAction] = None
    action_label: Optional[str] = None
    trend_prediction: Optional[str] = None
    market_phase: Optional[str] = None
    market_phase_summary: Optional[MarketPhaseSummary] = None
    position_recommendation: Optional[str] = None
    start_price: Optional[float] = None
    end_close: Optional[float] = None
    max_high: Optional[float] = None
    min_low: Optional[float] = None
    stock_return_pct: Optional[float] = None
    actual_return_pct: Optional[float] = None
    actual_movement: Optional[str] = None
    direction_expected: Optional[str] = None
    direction_correct: Optional[bool] = None
    outcome: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    hit_stop_loss: Optional[bool] = None
    hit_take_profit: Optional[bool] = None
    first_hit: Optional[str] = None
    first_hit_date: Optional[str] = None
    first_hit_trading_days: Optional[int] = None
    simulated_entry_price: Optional[float] = None
    simulated_exit_price: Optional[float] = None
    simulated_exit_reason: Optional[str] = None
    simulated_return_pct: Optional[float] = None


class BacktestResultsResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[BacktestResultItem] = Field(default_factory=list)


class PerformanceMetrics(BaseModel):
    scope: str
    code: Optional[str] = None
    eval_window_days: int
    engine_version: str
    computed_at: Optional[str] = None

    total_evaluations: int
    completed_count: int
    insufficient_count: int
    long_count: int
    cash_count: int
    win_count: int
    loss_count: int
    neutral_count: int

    direction_accuracy_pct: Optional[float] = None
    win_rate_pct: Optional[float] = None
    neutral_rate_pct: Optional[float] = None
    avg_stock_return_pct: Optional[float] = None
    avg_simulated_return_pct: Optional[float] = None

    stop_loss_trigger_rate: Optional[float] = None
    take_profit_trigger_rate: Optional[float] = None
    ambiguous_rate: Optional[float] = None
    avg_days_to_first_hit: Optional[float] = None

    advice_breakdown: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
