# -*- coding: utf-8 -*-
"""Market phase summary schemas."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


MarketPhaseValue = Literal[
    "premarket",
    "intraday",
    "lunch_break",
    "closing_auction",
    "postmarket",
    "non_trading",
    "unknown",
]


class MarketPhaseSummary(BaseModel):
    """Low-sensitivity market phase metadata exposed on report meta."""

    market: Optional[str] = Field(None, description="시장 지역")
    phase: MarketPhaseValue = Field(..., description="시장 국면")
    market_local_time: Optional[str] = Field(None, description="시장 현지 시각")
    session_date: Optional[str] = Field(None, description="시장 현지 날짜")
    effective_daily_bar_date: Optional[str] = Field(None, description="다시 쓸 수 있는 최신 완성 일봉 날짜")
    is_trading_day: Optional[bool] = Field(None, description="거래일 여부")
    is_market_open_now: Optional[bool] = Field(None, description="지금 장이 열려 있는지")
    is_partial_bar: Optional[bool] = Field(None, description="최신 일봉이 아직 미완성일 수 있는지")
    minutes_to_open: Optional[int] = Field(None, description="장 시작까지 남은 분")
    minutes_to_close: Optional[int] = Field(None, description="장 마감까지 남은 분")
    trigger_source: Optional[str] = Field(None, description="실행 경로")
    analysis_intent: Optional[str] = Field(None, description="분석 의도")
    warnings: List[str] = Field(default_factory=list, description="국면 추정이 불완전할 때의 경고 코드")
